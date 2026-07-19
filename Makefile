# Genome Firewall — reproducible pipeline. Targets call into src/genome_firewall/*.
.PHONY: all amr-setup acquire annotate featurize split train ensemble calibrate evaluate app clean

all: acquire annotate featurize split train calibrate evaluate ensemble   ## full pipeline

amr-setup:  ## install NCBI AMRFinderPlus (conda 'amr' env, falls back to docker ncbi/amr)
	bash scripts/setup_amrfinder.sh

acquire:    ## BV-BRC genomes + lab AST -> data/processed/labels.csv
	PYTHONPATH=src python -m genome_firewall.acquire

annotate:   ## AMRFinderPlus over FASTAs -> data/interim/amrfinder/
	PYTHONPATH=src python -m genome_firewall.annotate

featurize:  ## TSVs -> data/processed/features.parquet + feature_spec.json
	PYTHONPATH=src python -m genome_firewall.featurize

split:      ## de-dup + grouped split -> data/processed/splits.json
	PYTHONPATH=src python -m genome_firewall.split

train:      ## per-antibiotic L2 baseline used by the app
	PYTHONPATH=src python -m genome_firewall.model_baseline

ensemble:   ## L1 LR + HistGradientBoosting + XGBoost, with optional embeddings
	PYTHONPATH=src python -m genome_firewall.model_ensemble

calibrate:  ## calibrate the app baseline on the dedicated cal split
	PYTHONPATH=src python -m genome_firewall.calibrate

evaluate:   ## evaluate the app baseline on held-out grouped test
	PYTHONPATH=src python -m genome_firewall.evaluate

app:        ## launch the Streamlit demo
	streamlit run app/streamlit_app.py

clean:
	rm -rf data/interim/amrfinder/* data/processed/models reports/*.png
