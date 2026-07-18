#!/usr/bin/env bash
# Sets up NCBI AMRFinderPlus (https://github.com/ncbi/amr) for Person B's
# annotation pipeline (src/genome_firewall/annotate.py). Tries conda first
# (installs into a dedicated 'amr' env, isolated from environment.yml so
# dependency solving never conflicts with the main project env), falls back
# to the official ncbi/amr Docker image. See docs/subplans/PERSON_B_features.md.
set -euo pipefail

ENV_NAME="amr"

if command -v conda >/dev/null 2>&1; then
  echo "==> Installing AMRFinderPlus into conda env '${ENV_NAME}'..."
  if conda env list | grep -qE "^${ENV_NAME}[[:space:]]"; then
    echo "conda env '${ENV_NAME}' already exists, skipping create"
  else
    conda create -y -n "${ENV_NAME}" -c conda-forge -c bioconda ncbi-amrfinderplus
  fi

  echo "==> Downloading/updating the AMRFinderPlus database..."
  conda run -n "${ENV_NAME}" amrfinder -u

  echo "==> Verifying install..."
  conda run -n "${ENV_NAME}" amrfinder --version

  cat <<EOF

Done. To use it:
  conda activate ${ENV_NAME}
  amrfinder -n contigs.fna --organism Staphylococcus_aureus --plus -o out.tsv
EOF

elif command -v docker >/dev/null 2>&1; then
  echo "==> conda not found; falling back to Docker image ncbi/amr"
  docker pull ncbi/amr

  cat <<EOF

Done. To use it (mounts the current directory as /data):
  docker run --rm -v "\$PWD":/data ncbi/amr \\
    amrfinder -n /data/contigs.fna --organism Staphylococcus_aureus --plus -o /data/out.tsv
EOF

else
  echo "Neither conda nor docker found on PATH. Install one of them first." >&2
  exit 1
fi
