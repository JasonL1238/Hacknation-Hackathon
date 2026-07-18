# Genome Firewall — reproducible pipeline. Targets call into src/genome_firewall/*.
.PHONY: all amr-setup acquire annotate featurize split train calibrate evaluate app clean

all: acquire annotate featurize split train calibrate evaluate   ## full pipeline

amr-setup:  ## install NCBI AMRFinderPlus (conda 'amr' env, falls back to docker ncbi/amr)
	bash scripts/setup_amrfinder.sh

acquire:    ## BV-BRC genomes + lab AST -> data/processed/labels.csv
	python -m genome_firewall.acquire

annotate:   ## AMRFinderPlus over FASTAs -> data/interim/amrfinder/
	python -m genome_firewall.annotate

featurize:  ## TSVs -> data/processed/features.parquet + feature_spec.json
	python -m genome_firewall.featurize

split:      ## de-dup + grouped split -> data/processed/splits.json
	python -m genome_firewall.split

train:      ## per-antibiotic logistic regression
	python -m genome_firewall.model_baseline

calibrate:  ## isotonic calibration on cal split
	python -m genome_firewall.calibrate

evaluate:   ## metrics.json + reliability/PR plots
	python -m genome_firewall.evaluate

app:        ## launch the Streamlit demo
	streamlit run app/streamlit_app.py

clean:
	rm -rf data/interim/amrfinder/* data/processed/models reports/*.png
