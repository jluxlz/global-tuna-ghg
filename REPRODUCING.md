# Reproduction from supplied scientific inputs

## Boundary

Reproduction starts from the supplied **accepted vessel registry**. It includes construction dates and engineering information obtained from the author's saved registry queries. Live websites, browser automation and a fresh `spider/` crawl are **not required**. The five RFMO query spreadsheets, original/extracted records and harmonization code remain available for provenance. Repeating a live query may retrieve different records and is a separate data-update exercise.

`vessel_data_extract/Unified_Vessel_Registry.csv` is the canonical accepted pre-imputation checkpoint. `PMM_Imputation/After_PMM_Vessels.csv` is its saved PMM checkpoint. The historical LCA regenerates PMM from the accepted registry. `effort_data/Share5_Lookup_FlagGearYear.csv` defines the five-species allocation and must never be omitted. `data/frozen_inputs.json` records the supplied checkpoints and checksums.

## Installation and restoration

Install Python dependencies in `requirements.txt`, R and `install_r_dependencies.R`. JAGS and JABBA are needed only for fresh stock fits. Set `RSCRIPT` if Rscript is not on PATH. The scripts use their own locations to resolve project paths; the author's desktop directory is not required.

```sh
python restore_data.py --download --verify
python reproduce.py verify
python reproduce.py figures
```

Three unchanged large data assets remain under release v2026.10.19. This source repair ships missing small model inputs directly in Git. `restore_data.py --assets /path/to/downloaded/archives --verify` supports an offline data-asset cache. File and archive SHA-256 checks are mandatory; this is not permission to substitute unrelated local data.

`figures` redraws all 33 current quantitative figures from saved numerical inputs. Extended Data Figs. 1–2 are conceptual diagrams. SI Figs. 5, 15 and 19 use `validation_20261018` versions. Rendering is a saved-result replay and does not recompute the model ensemble.

## Recomputing models

```sh
python reproduce.py historical
python reproduce.py stocks
python reproduce.py scenarios --extra-experiments
python reproduce.py refresh
python reproduce.py figures
```

`historical` runs the production 2,000-draw sensitivity selection and 500-draw historical inventory, using the supplied accepted registry and the same Python PMM implementation as the fleet model. It writes Base_1–Base_5 and retained draw data. It does not rerun the registry spider.

`stocks` runs the configured JABBA chains from provided catch/CPUE inputs; it can take substantial time. The saved stock parameters and trajectories are also supplied as frozen model inputs. To recompute the inventory and fleet chain while retaining those fitted stock inputs, use `python reproduce.py all`. Add `--refit-stocks` for a fresh JABBA fit and `--extra-experiments` to include regional and iterative matched-catch experiments. These are distinct reuse choices; no saved fit is described as a new biological refit.

`scenarios` first runs the order-dependence guard, then the paired-seed fixed-target four-measure design and the complete feasible-catch stock–fleet design. Extra experiments include two regional stocks and the iterative catch-matching exercise. Existing checkpoints may be reused only when their parameter and input signatures match. Logs are under `reproduction_logs/`. Set `PAIRED_WORKERS` and `P0_WORKERS` to control process counts on memory-limited computers.

`refresh` rebuilds main-figure numerical bridges. Some supplementary diagnostics are separate scientific experiments and retain their own builders and saved inputs. Recomputing a core ensemble does not imply that every archival sensitivity or posterior has also been refit. The current source/input inventory and figure dependency manifests identify those boundaries.

## Optional reconstruction before the accepted registry

FAO classification reference files and the saved standardized RFMO extractions are included. The optional sequence is extraction, deduplication, accepted supplementary-query updates and PMM. The accepted registry is supplied so that reproducing emission estimates does not depend on reproducing historical website behavior or undocumented manual query choices. Optional legacy R imputation experiments are not the canonical PMM algorithm.

## Scope of verification

See `data/reproduction_verification.json` for the actual tests performed on this distribution. A successful file restoration or figure render is not evidence of a fresh Monte Carlo, scenario or MCMC run. Scientific limitations of stock pooling, operating schedules and the longline fuel-intensity benchmark remain unchanged.

### Archived trajectory exception

The verification reran the full 500-draw historical inventory and grid allocation successfully. Representative fixed-target, feasible-catch and central matched-catch runs executed; one extreme feasible-catch portfolio (F81/1111) differs from its archived trajectory by up to 0.122363 Mt annual GHG. The unchanged local project produces the same fresh trajectory as this repaired distribution. This discrepancy predates the distribution repair and remains unresolved. Stored scientific results were retained, not silently replaced. The release therefore establishes a runnable offline workflow and the explicitly passed numerical checks, not full numerical identity of every stored future. Fresh checkpoint signatures now include omitted frozen baseline dependencies, preventing their unnoticed reuse after input changes.

### Archived trajectory exception

The verification reran the full 500-draw historical inventory and grid allocation successfully. Representative fixed-target, feasible-catch and central matched-catch runs executed; one extreme feasible-catch portfolio (F81/1111) differs from its archived trajectory by up to 0.122363 Mt annual GHG. The unchanged local project produces the same fresh trajectory as this repaired distribution. This discrepancy predates the distribution repair and remains unresolved. Stored scientific results were retained, not silently replaced. The release therefore establishes a runnable offline workflow and the explicitly passed numerical checks, not full numerical identity of every stored future. Fresh checkpoint signatures now include omitted frozen baseline dependencies, preventing their unnoticed reuse after input changes.
