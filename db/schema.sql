-- ============================================================================
-- Genome Firewall — Supabase schema, Row Level Security, triggers, and storage.
--
-- Run this ONCE against a fresh Supabase project:
--   Supabase Dashboard → SQL Editor → paste this file → Run.
-- It is idempotent-ish (uses IF NOT EXISTS / CREATE OR REPLACE where possible);
-- re-running is safe, but dropping/recreating policies is included explicitly.
--
-- Security model: every row is owned by exactly one authenticated user
-- (user_id = auth.uid()). RLS is enabled on every table so a user can only ever
-- read or write their own rows, even though the app connects with the anon key.
-- Patient genome data is sensitive: the storage bucket is PRIVATE and access is
-- restricted, per-user, by folder prefix.
-- ============================================================================

-- ─── Tables ─────────────────────────────────────────────────────────────────

-- users (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT,
    organization TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- patients
CREATE TABLE IF NOT EXISTS public.patients (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    patient_name TEXT NOT NULL,
    patient_id TEXT,
    date_of_birth DATE,
    gender TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- genome_analyses
CREATE TABLE IF NOT EXISTS public.genome_analyses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
    genome_id TEXT NOT NULL,
    species TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    -- Stores the storage OBJECT PATH ("{user_id}/{file}"), not a public URL:
    -- the bucket is private and short-lived signed URLs are generated on demand.
    fasta_file_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- predictions
CREATE TABLE IF NOT EXISTS public.predictions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    analysis_id UUID NOT NULL REFERENCES public.genome_analyses(id) ON DELETE CASCADE,
    antibiotic TEXT NOT NULL,
    verdict TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    evidence_category TEXT NOT NULL,
    supporting_genes TEXT[],
    target_present BOOLEAN DEFAULT TRUE,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Helpful indexes for the app's list/lookup queries.
CREATE INDEX IF NOT EXISTS idx_patients_user_id         ON public.patients(user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_user_id         ON public.genome_analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_patient_id      ON public.genome_analyses(patient_id);
CREATE INDEX IF NOT EXISTS idx_predictions_user_id      ON public.predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_analysis_id  ON public.predictions(analysis_id);


-- ─── updated_at maintenance ─────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_patients_updated_at ON public.patients;
CREATE TRIGGER trg_patients_updated_at
    BEFORE UPDATE ON public.patients
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_analyses_updated_at ON public.genome_analyses;
CREATE TRIGGER trg_analyses_updated_at
    BEFORE UPDATE ON public.genome_analyses
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ─── Auto-create a public.users profile on sign-up ──────────────────────────
-- Fires for BOTH email/password and Google OAuth sign-ups. full_name comes from
-- the metadata we pass at sign_up() (or Google's profile). Runs as the table
-- owner (SECURITY DEFINER) so it bypasses RLS for this single controlled insert.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, full_name)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(
            NEW.raw_user_meta_data ->> 'full_name',
            NEW.raw_user_meta_data ->> 'name'      -- Google uses 'name'
        )
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ─── Row Level Security ─────────────────────────────────────────────────────

ALTER TABLE public.users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.patients        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.genome_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions     ENABLE ROW LEVEL SECURITY;

-- users: a user sees and edits only their own profile row.
DROP POLICY IF EXISTS users_select_own ON public.users;
CREATE POLICY users_select_own ON public.users
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS users_insert_own ON public.users;
CREATE POLICY users_insert_own ON public.users
    FOR INSERT WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS users_update_own ON public.users;
CREATE POLICY users_update_own ON public.users
    FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- Reusable pattern for the owned tables: full CRUD where user_id = auth.uid().
DROP POLICY IF EXISTS patients_all_own ON public.patients;
CREATE POLICY patients_all_own ON public.patients
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS analyses_all_own ON public.genome_analyses;
CREATE POLICY analyses_all_own ON public.genome_analyses
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS predictions_all_own ON public.predictions;
CREATE POLICY predictions_all_own ON public.predictions
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);


-- ─── Storage: private genome-files bucket + per-user access ──────────────────
-- Files are uploaded under the path "{user_id}/{uuid}_{filename}". The policies
-- below restrict every operation to objects whose FIRST path segment equals the
-- caller's uid, so no user can list, read, or overwrite another user's genomes.

INSERT INTO storage.buckets (id, name, public)
VALUES ('genome-files', 'genome-files', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS genome_files_select_own ON storage.objects;
CREATE POLICY genome_files_select_own ON storage.objects
    FOR SELECT USING (
        bucket_id = 'genome-files'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

DROP POLICY IF EXISTS genome_files_insert_own ON storage.objects;
CREATE POLICY genome_files_insert_own ON storage.objects
    FOR INSERT WITH CHECK (
        bucket_id = 'genome-files'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

DROP POLICY IF EXISTS genome_files_update_own ON storage.objects;
CREATE POLICY genome_files_update_own ON storage.objects
    FOR UPDATE USING (
        bucket_id = 'genome-files'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

DROP POLICY IF EXISTS genome_files_delete_own ON storage.objects;
CREATE POLICY genome_files_delete_own ON storage.objects
    FOR DELETE USING (
        bucket_id = 'genome-files'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- ============================================================================
-- Done. Next: create a user via the app's Register tab (or enable the Google
-- provider in Authentication → Providers), then verify a row appears in
-- public.users automatically via the on_auth_user_created trigger.
-- ============================================================================
