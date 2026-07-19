FROM mambaorg/micromamba:1.5.8-jammy

# Build the runtime with micromamba so Bioconda's AMRFinderPlus package is
# installed without relying on Streamlit Community Cloud's Conda solver.
COPY --chown=$MAMBA_USER:$MAMBA_USER app/environment.yml /tmp/environment.yml
RUN micromamba create --yes --name genome-firewall-cloud --file /tmp/environment.yml \
    && micromamba clean --all --yes \
    && rm -f /tmp/environment.yml

WORKDIR /home/mambauser/app
COPY --chown=$MAMBA_USER:$MAMBA_USER . .

ENV HOME=/home/mambauser \
    ENV_NAME=genome-firewall-cloud \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false

EXPOSE 7860

CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=7860"]
