# Reproducing the scientific version

Use Python 3.13 and R 4.5.2 with the dependencies in requirements.txt and install_r_dependencies.R. Use the frozen vessel, spatial and stock inputs supplied in the complete release. An R/JAGS installation is required only when refitting stocks.

Run python reproduce.py verify before other stages. Run python reproduce.py figures to render the saved source tables. Extended Data Figs. 1 and 2 are conceptual and have no quantitative inputs. The 35 other figures retain their paper numbering. See data/figure_inputs.csv for source-data locations and data/file_manifest.csv for file checksums.

Historical recalculation uses the 500-draw multimode inventory and tests spatial catch and effort conservation using the supplied tables. The scenarios stage runs the order and worker-context regressions before the primary and sensitivity ensembles. The optional --extra-experiments flag adds iterative matched-catch search and regional runs. A full recalculation can take hours. Retain the original ZIP before recomputing: model and plotting commands update outputs in the extracted tree. Stocks are reused by default; use --refit-stocks only if the fitted biological inputs are to be regenerated.

Current source outputs use constant catch (C), constant harvest rate (F) and a biomass threshold (T) under common stock and fleet feedback. Supplementary Figs. 19, 20, 22 and archival regional contrasts in Fig. 23 are labeled historical comparators. They do not define the current baseline.
