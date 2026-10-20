# Global tuna-fishery greenhouse gas emissions

Scientific algorithms, original source inputs, figure data and saved scenario results for a two-part study of global tuna fisheries: historical vessel-level life-cycle accounting (1950–2025) and exploratory stock–fleet projections (2026–2050).

## Restore the data before running analyses

The Git tree contains source code, parameter tables and small original inputs. Large inputs and saved results are in the versioned release **v2026.10.20.1**. A clone alone is not the complete data distribution.

```sh
python restore_data.py --download --verify
```

This downloads the three unchanged base ZIP assets and the current result delta, restores their content to the original relative paths and verifies every scientific file against `data/file_manifest.csv`. `--figure-data` restores only saved figure files; it is insufficient to rerun upstream models. Use `--assets /path/to/downloads --verify` with previously downloaded assets. The restorer refuses to overwrite modified files unless `--overwrite` is explicitly supplied.

## Offline reproduction boundary

Live vessel-query scraping is optional. Start from the supplied accepted registry, which already contains the accepted spider-derived construction dates and characteristics. See [REPRODUCING.md](REPRODUCING.md) for input checks, model stages and saved-fit choices. Run `python reproduce.py verify` after restoring data.

## Scientific workflow

1. Original RFMO vessel tables are in `raw_vessel_data/`, `spider/output/` and `vessel_data_extract/new_extracted_vessel_data_raw/`; intermediate extracted tables are in `extracted_vessel_data/`. Source catch/effort tables and spatial boundaries are in `effort_data/` and `shape_file/`.
2. Vessel extraction, imputation and historical reconstruction feed `GHG_Calculation/ghg_lca.py`, the historical Monte Carlo life-cycle model.
3. `scenario/jabba_fit.r`, `scenario/fleet_model.py` and `scenario/price_loader.py` implement stock fits, fleet projections and fuel prices. Figure-level simulation drivers live with the corresponding figure or in `analysis/`.
4. Each quantitative figure retains its R renderer and saved CSV inputs. `data/figure_inputs.json` records the inputs actually opened in an isolated restoration-and-render check. Extended Data Figs. 1–2 are conceptual diagrams and do not require numeric panel data.

Python is used for model calculations and data preparation; figures are rendered in R with ggplot2. Install Python packages from `requirements.txt` and R packages with `install_r_dependencies.R`. Existing saved inputs permit figure rendering without repeating the long model fits and scenario sweeps. Fitting stocks and rerunning the entire model requires substantially more time than redrawing the figures.

## Source provenance and scope

`data/source_inputs.csv` lists 84 original input files, their providers, sizes and SHA-256 checksums. These include the CCSBT registry source and extracted tables. Public paths and authored code/descriptions use English. Original provider tables and workbooks retain their original bytes, including native headers, names and units; translations must not silently replace scientific source records.

The `analysis/` directory holds scientific robustness calculations required by the saved results. Editorial automation, manuscript drafts, SI prose and agent configuration are excluded. The earlier scientific `audits/` paths were relocated to `analysis/` with dependent paths updated; there is no `audits/` directory in this release.

The simulations are exploratory. Pooled global stock models do not replace official regional assessments. Historical operating schedules include assumptions, and the longline fuel-intensity discrepancy against an independent survey remains a limitation. Numerical convergence, internal consistency and sensitivity checks are distinct from independent empirical validation. Fixed-catch-target and feasible-catch simulations use different activity and stock feedback structures and must be compared with their own paired baselines.

## Provenance checks

`data/file_manifest.csv` identifies scientific files distributed through Git and release assets. `data/release_assets.json` records archive checksums. `data/figure_inputs.json` and `data/figure_inputs.csv` identify quantitative figure dependencies. Restoring saved files and redrawing figures verifies file availability and rendering; it does not constitute a fresh production model rerun.

## Execution-context reconciliation

Release v2026.10.20.1 corrects inconsistent fuel-property initialization in serial and Windows-spawn execution. Decimal unit conversion is performed before binary floating-point evaluation. Both execution modes now use the same workbook properties. The original parameter workbook and paired seeds were retained.

The current scientific result set was rebuilt with 4,288 frozen-input simulations, with 18 additional matched-rule process captures. This is a coherent replacement of the affected results, not a claim that all new trajectories equal older archives. Central manuscript reductions remain unchanged, while some trajectories and scenario ranges change. See `data/reproduction_verification.json` and `data/execution_context_validation.json`. The earlier 500-draw historical reconstruction remains valid; frozen stock fits were not refitted in this correction.

For an existing restored checkout, `python restore_data.py --download --verify --overwrite` installs this release's saved results. Asset tags are recorded individually; the base archives remain under v2026.10.19 and the result delta under v2026.10.20.1.
