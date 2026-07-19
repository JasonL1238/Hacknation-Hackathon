# Deploy BioShield AI to Streamlit Community Cloud

The repository already contains the app, six final XGBoost artifacts, the exact
AMRFinderPlus feature contract, Streamlit theme, and a complete Conda environment.
No training job, model API, database migration, or Supabase Storage bucket is needed
for this research-demo deployment.

## 1. Configure Supabase authentication

1. Create or open a Supabase project.
2. In **Project Settings → API Keys**, copy:
   - the project URL;
   - a **publishable** key (`sb_publishable_...`). A legacy `anon` key also works.
3. Do **not** use a secret (`sb_secret_...`) or legacy `service_role` key. The app
   rejects privileged keys to prevent an accidental high-privilege deployment.
4. In **Authentication → URL Configuration**, set the **Site URL** to the final
   Streamlit URL, for example `https://bioshield-ai.streamlit.app`.
5. Add that same URL to **Redirect URLs**. Also add
   `https://bioshield-ai.streamlit.app/**` if account-confirmation redirects are
   rejected.

Email/password authentication is enabled by default on hosted Supabase projects.
Supabase normally requires new users to confirm their email. After confirmation, the
user returns to the app and signs in normally. Google sign-in and self-service password
recovery are intentionally not offered because Streamlit's server session does not
reliably survive the required external token redirect. Account recovery must be handled
by the project owner or added later through a dedicated recovery frontend.

You do **not** need to run [`db/schema.sql`](../db/schema.sql). Supabase is used only
for user authentication in this deployment. Patient, case, and result records are held
only in each visitor's Streamlit session and are not persisted.

## 2. Deploy the Streamlit app

1. Push the prepared repository and branch to GitHub.
2. Open [Streamlit Community Cloud](https://share.streamlit.io) and select
   **Create app**.
3. Use these values:

   | Field | Value |
   |---|---|
   | Repository | `JasonL1238/Hacknation-Hackathon` |
   | Branch | `main` |
   | Entrypoint | `app/streamlit_app.py` |
   | Python | `3.11` |

4. Open **Advanced settings → Secrets** and paste:

   ```toml
   SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
   SUPABASE_KEY = "YOUR_PUBLISHABLE_KEY"
   ```

5. Click **Deploy**. The first build can take several minutes while Conda installs
   the pinned runtime. The first real genome analysis also provisions the compatible
   AMRFinderPlus database and can take longer than later analyses.
6. Once Streamlit assigns the final app URL, put that URL into the Supabase Site URL
   and Redirect URLs from step 1, then test account creation, email confirmation,
   sign-in, and one synthetic FASTA upload.

## What the deployed server does

For each uploaded genome, the Streamlit server runs AMRFinderPlus, creates the exact
genotype feature row expected by the final models, and runs six calibrated XGBoost
classifiers. It does not call a separate model API. Uploaded FASTA bytes and temporary
AMRFinder output are removed after success or failure.

The app is an unaudited research demonstration. Do not upload protected health
information or use its output to make clinical decisions.

Supabase configuration is mandatory. If either required value is missing, the app
fails closed with a configuration error; there is no guest or URL-based bypass.
