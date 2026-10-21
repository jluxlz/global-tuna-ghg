# Reproducing the current scientific version

The input boundary is the supplied accepted registry, original provider tables, saved vessel-query results and frozen stock fits. Live scraping is optional. All scientific analysis dependencies now live in `analysis/`. No editorial backup workspace is required.

Run `python reproduce.py verify` first. Stages are `historical`, `stocks`, `scenarios`, `refresh`, `figures` and `all`. `all` reuses frozen stock fits unless `--refit-stocks` is supplied. Install Python requirements and R packages before computation. Put Rscript on PATH or set RSCRIPT; the optional local reproduction_config.json provides this computer's R paths.

## Current scenario chain

The primary comparison is C/F/T under common realized-catch, biomass, effort and fleet-capacity feedback: 81 exogenous futures times three quota rules times eight technical subsets, or 1,944 simulations. The 1,620 sensitivity simulations rerun operating bounds, harvest fractions, thresholds and alternative-fuel prices. The original 18 matched C/F runs remain a distinct comparator for Supplementary Fig. 19. They are not the primary baseline. Observed 2024 catch initializes reference quantities and is not a current-management BAU.

`scenarios` performs order/execution-context guards, pilots and validation before production runs. Use HCR_WORKERS to control memory use. `--extra-experiments` reruns iterative comparable-catch matching and regional experiments. All supplied matched candidates and outputs are retained, so saved results can be analyzed or redrawn without repeating the search. Model stages may take hours; rendering saved data does not rerun the models.

`refresh` rebuilds the current panel bridges. `figures` renders Fig. 1-5, Extended Data Fig. 3-10 and Supplementary Fig. 1-21 using R/ggplot2. Extended Data Fig. 1-2 are conceptual diagrams. Old fixed-target outputs are retained only where a supplementary archival comparison explicitly uses them.

Historical operating assumptions, the unresolved longline absolute-fuel discrepancy, exploratory refrigeration service equivalence, adopted fuel-factor boundaries and pooled-stock biological limitations remain applicable. Numerical and reproducibility checks do not establish empirical validation or an optimal RFMO policy.
