# RISKS.md — running risk register

| Risk | Impact | Owner | Mitigation | Status |
|---|---|---|---|---|
| BV-BRC access friction / label sparsity | Blocks real data | A | precomputed BV-BRC AMR tables / NCBI Pathogen Detection; pick drugs by coverage | open |
| AMRFinderPlus install/runtime | Blocks features | B | conda first, Docker `ncbi/amr` fallback; cache TSVs | open |
| Data leakage inflates scores | Judges penalize | C | grouped split by Mash cluster (× MLST CC); assert no cluster spans splits | open |
| Overclaiming causation | Fails honesty rubric | C/D | evidence categories separate catalog hits from statistical signal | open |
| Integration drift (synthetic vs real) | Broken `make all` | D | contracts frozen in DATA_SPEC; D keeps `make all` green | open |
