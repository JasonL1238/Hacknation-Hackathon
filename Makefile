# Genome Firewall — reproducible pipeline.
# Owner: Person D (end-to-end wiring). Targets call into src/genome_firewall/*.
.PHONY: all synth acquire annotate featurize split train calibrate evaluate app clean

all: acquire annotate featurize split train calibrate evaluate   ## full pipeline

synth:      ## generate schema-valid synthetic data so anyone can build immediately
	python -m genome_firewall._synth

acquire:    ## Person A: BV-BRC genomes + lab AST -> data/processed/labels.csv
	python -m genome_firewall.acquire

annotate:   ## Person B: AMRFinderPlus over FASTAs -> data/interim/amrfinder/
	python -m genome_firewall.annotate

featurize:  ## Person B: TSVs -> data/processed/features.parquet + feature_spec.json
	python -m genome_firewall.featurize

split:      ## Person C: de-dup + grouped split -> data/processed/splits.json
	python -m genome_firewall.split

train:      ## Person C: per-antibiotic logistic regression
	python -m genome_firewall.model_baseline

calibrate:  ## Person C: isotonic calibration on cal split
	python -m genome_firewall.calibrate

evaluate:   ## Person C: metrics.json + reliability/PR plots
	python -m genome_firewall.evaluate

app:        ## Person D: launch the Streamlit demo
	streamlit run app/streamlit_app.py

clean:
	rm -rf data/interim/amrfinder/* data/processed/models reports/*.png
