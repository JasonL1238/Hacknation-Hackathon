# RISKS.md — running risk register

| Risk | Impact | Mitigation | Status |
|---|---|---|---|
| BV-BRC access friction / label sparsity | Blocks real data | precomputed BV-BRC AMR tables / NCBI Pathogen Detection; pick drugs by coverage | open |
| AMRFinderPlus install/runtime | Blocks features | conda first (`make amr-setup`), Docker `ncbi/amr` fallback; cache TSVs | open |
| Data leakage inflates scores | Judges penalize | grouped split by Mash cluster (× MLST CC); assert no cluster spans splits | open |
| Overclaiming causation | Fails honesty rubric | evidence categories separate catalog hits from statistical signal | open |
| Pipeline stage wired to stale/missing upstream output | Broken `make all` | contracts frozen in DATA_SPEC; whoever picks up integration keeps `make all` green | open |
