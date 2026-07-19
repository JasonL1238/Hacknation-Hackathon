# Genome Firewall — reproducible pipeline. Targets call into src/genome_firewall/*.
.PHONY: all amr-setup acquire annotate featurize split train ensemble final-train select calibrate evaluate app clean

all: acquire annotate featurize split final-train   ## full XGBoost production pipeline

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

train:      ## historical per-antibiotic L2 baseline
	PYTHONPATH=src python -m genome_firewall.model_baseline

ensemble:   ## genotype-only L1 LR + HistGradientBoosting + XGBoost
	PYTHONPATH=src python -m genome_firewall.model_ensemble --setups genotype_only --voting inverse-brier

final-train: ## deployment refit of per-antibiotic XGBoost on every labeled genome
	PYTHONPATH=src python -m genome_firewall.final_train

calibrate:  ## calibrate the app baseline on the dedicated cal split (backed up by select)
	PYTHONPATH=src python -m genome_firewall.calibrate

select:     ## historical bakeoff -> best-3 soft ensemble experiment
	PYTHONPATH=src python -m genome_firewall.model_select

evaluate:   ## evaluate legacy models on the held-out grouped test
	PYTHONPATH=src python -m genome_firewall.evaluate

app:        ## launch the Streamlit demo
	streamlit run app/streamlit_app.py

clean:
	rm -rf data/interim/amrfinder/* data/processed/models reports/*.png
