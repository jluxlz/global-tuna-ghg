# Global tuna-fishery greenhouse gas emissions

## Download the complete package

**[Download global-tuna-ghg-complete.zip](https://github.com/jluxlz/global-tuna-ghg/releases/download/v2026.10.20.2/global-tuna-ghg-complete.zip)**

Download this one ZIP and extract it. It contains the scientific code, supplied original and frozen inputs, current model results, figure inputs and figure renderers in their working folders. No older release or update archive is needed. The two source-code archives automatically added by GitHub are not the full data package.

Open a terminal in the extracted `global-tuna-ghg` folder:

```sh
python restore_data.py --verify
python reproduce.py verify
```

Install Python dependencies from `requirements.txt` and R packages with `install_r_dependencies.R` before running analyses. See [START_HERE.md](START_HERE.md) for the short workflow and [REPRODUCING.md](REPRODUCING.md) for model stages and assumptions.

If you prefer a Git clone, run `python restore_data.py --download --verify`. It downloads the same complete archive from this release and restores the data. Existing modified files are protected unless `--overwrite` is supplied. `--assets /path/to/downloads --verify` uses a local archive.

## Scientific workflow

The study combines vessel-level historical life-cycle accounting (1950–2025) with exploratory stock–fleet projections (2026–2050). Original RFMO vessel records, accepted supplementary query results, engineering parameters, catch–effort inputs and spatial boundaries are supplied. Reproduction starts from the accepted vessel registry; live website scraping is optional.

`GHG_Calculation/ghg_lca.py` calculates the historical inventory. `scenario/fleet_model.py`, `price_loader.py` and `jabba_fit.r` implement fleet projections, fuel prices and stock fits. Figure drivers are in `figures/` and scientific robustness calculations in `analysis/`. Python handles calculation and data preparation; scientific figures use R and ggplot2. Saved stock fits and figure inputs permit work without repeating every fit and simulation.

The complete package includes the coherent 2026-10-20 result set: 4,288 recalculated configurations and 18 additional matched-rule process captures. The earlier 500-draw historical reconstruction remains verified; frozen stock fits were reused. This packaging update changes no scientific result. Detailed verification is in `data/reproduction_verification.json` and `data/execution_context_validation.json`.

## Data provenance and limits

`data/source_inputs.csv` documents 84 original source inputs. `data/file_manifest.csv` records file checksums, and `data/figure_inputs.json` identifies inputs for the 33 quantitative figures. Extended Data Figs. 1–2 are conceptual diagrams. Public paths and authored code use English; original provider tables retain their original bytes, headers and units.

Historical operating schedules include assumptions, the longline fuel-intensity benchmark discrepancy remains unresolved, and pooled global stock models do not replace official regional assessments. Numerical consistency is distinct from independent empirical validation. Fixed-target and feasible-catch simulations retain their own matched baselines.

Manuscript drafts, SI prose, editorial automation and agent configuration are excluded. Previous releases are marked as historical archives. Use this complete package for the current scientific version.
