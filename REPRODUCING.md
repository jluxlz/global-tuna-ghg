# Reproduction from supplied scientific inputs

## Boundary

Reproduction starts from the supplied **accepted vessel registry**. It includes construction dates and engineering information obtained from the author's saved registry queries. Live websites, browser automation and a fresh `spider/` crawl are **not required**. The five RFMO query spreadsheets, original/extracted records and harmonization code remain available for provenance. Repeating a live query may retrieve different records and is a separate data-update exercise.

`vessel_data_extract/Unified_Vessel_Registry.csv` is the canonical accepted pre-imputation checkpoint. `PMM_Imputation/After_PMM_Vessels.csv` is its saved PMM checkpoint. The historical LCA regenerates PMM from the accepted registry. `effort_data/Share5_Lookup_FlagGearYear.csv` defines the five-species allocation and must never be omitted. `data/frozen_inputs.json` records the supplied checkpoints and checksums.

## Installation and restoration

Install Python dependencies in `requirements.txt`, R and `install_r_dependencies.R`. JAGS and JABBA are needed only for fresh stock fits. Set `RSCRIPT` if Rscript is not on PATH. The scripts use their own locations to resolve project paths; the author's desktop directory is not required.

```sh
python restore_data.py --verify
python reproduce.py verify
python reproduce.py figures
```

Download `global-tuna-ghg-complete.zip` from release v2026.10.20.2 and extract it. The expanded package already contains all supplied scientific inputs, code and current results. It needs no older release. Git-clone users instead run `python restore_data.py --download --verify` once; this retrieves the same single complete archive. `--assets /path/to/downloads --verify` supports an offline archive cache. The archive checksum is published as `SHA256SUMS.txt`; the complete ZIP cannot contain its own checksum, so its download-control file refers to that sidecar only if repair is required. Ordinary scientific files are always checked against `data/file_manifest.csv`.

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

### Corrected execution-context consistency

The archived F81/1111 discrepancy has been traced to parent-process fuel initialization that was not inherited by Windows-spawn workers. In the old code, converting the workbook's 0.0186 MJ/g produced 18.599999999999998 MJ/kg in the parent, while workers used 18.6. Small vessel-intensity differences changed sorting and later discrete fleet choices. A controlled one-property intervention reproduced the original archived path. The correction consistently initializes workbook values and converts decimal units before binary arithmetic. It does not adjust model output precision or random seeds to force archive agreement.

The new coherent replay includes 1,782 stock-and-capacity simulations, 1,296 fixed-target factorial simulations, 220 pilot replicates, 18 matched-rule checks and 972 regional simulations. Another 18 process captures reproduce the matched-rule accounting states. Affected quantitative figures are regenerated from these results. The 500-draw historical inventory and grid reconstruction had already matched the frozen historical products; no new JABBA or GSA fit is claimed by this correction.

The paired-seed and constrained drivers include runtime, seed, code and input dependencies in their checkpoint guards. The constrained guard also fingerprints the actual weighted baseline fleet and regional allocation table. `reproduce.py scenarios --extra-experiments` regenerates selected matched-rule metadata and process captures instead of requiring the author's old absolute paths. Order and execution-context regression guards run before production.

See `data/reproduction_verification.json` for the exact scope. Pooled-stock, activity and empirical-validation limitations remain as documented in the study. These numerical checks do not establish biological or observational completeness.

