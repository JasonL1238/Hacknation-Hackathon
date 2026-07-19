# Deploy BioShield AI to Hugging Face Docker Spaces

This deployment path runs the existing Streamlit application inside a Docker
container. The image installs the Cloud-specific Conda environment with
micromamba, including AMRFinderPlus, the pinned XGBoost runtime, and the final
model artifacts copied from the repository.

## 1. Create the Space

1. Create a new Hugging Face Space.
2. Choose **Docker** as the Space SDK.
3. Use a public Space for a public research demonstration.
4. The repository metadata already declares port `7860` through `README.md`.

To copy this repository into the Space repository, add the Space as a Git remote
and push the prepared branch:

```bash
git remote add huggingface https://huggingface.co/spaces/<HF_USERNAME>/<SPACE_NAME>.git
git push huggingface main
```

Authenticate with Hugging Face before pushing if the Space is private or your
account requires authentication.

## 2. Add runtime secrets

In the Space's **Settings → Variables and secrets**, create these runtime secrets:

```text
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-publishable-or-anon-key
```

Optional demo mode:

```text
ENABLE_DEMO_MODE=true
```

Do not use a Supabase secret or `service_role` key. Do not put `.env` or
`.streamlit/secrets.toml` into the Space repository.

After the Space receives its final URL, add that URL to Supabase **Authentication
→ URL Configuration → Site URL** and **Redirect URLs**. If email confirmation
redirects need a wildcard, add the final URL followed by `/**` as well.

## 3. What the container runs

The Docker image starts:

```text
streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.port=7860
```

Each upload runs AMRFinderPlus, creates the frozen genotype feature vector, and
loads the six calibrated XGBoost models from `data/processed/final_models/`.
The AMRFinderPlus database is provisioned lazily at first inference under the
container's temporary directory. Uploaded FASTA bytes and temporary annotation
output are deleted after analysis.

## Limitations

This is a research demonstration, not a clinical deployment. Free or sleeping
Space hardware can have cold starts, limited memory, and ephemeral storage. Do
not upload protected health information. All predictions require confirmation by
standard laboratory AST and clinical judgment.
