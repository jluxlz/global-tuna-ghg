# Global tuna-fishery greenhouse gas emissions

Models, processed data, saved simulations and figure source data supporting
*The climate advantage of tuna quota rules over fuel transition depends on achievable catches*.

This release preserves the historical inventory (1950–2025), exploratory
stock–fleet scenarios (2025–2050), fixed-catch pressure tests, feasible-catch
comparisons and the nine additional matched-catch experiments. Historical
associations and exploratory stock trajectories do not establish causal effects
or substitute for RFMO stock assessments.

## Get the data

The code and smaller compiled-parameter/panel tables are in this Git tree.
Large author-generated outputs are in the [versioned data release](https://github.com/jluxlz/global-tuna-ghg/releases/tag/v2026.10.18).
The release archives use content-addressed storage to avoid copying identical
outputs repeatedly. File paths and SHA-256 checksums are recorded in
`data/file_manifest.csv`; `data/release_files.json.gz` maps archived files to assets.

```sh
git clone https://github.com/jluxlz/global-tuna-ghg.git
cd global-tuna-ghg
python restore_data.py --download --verify
```

`gh` is optional for public downloads. To fetch only large figure data, use
`python restore_data.py --download --figure-data`. This restores the original
directory structure, rather than requiring manual extraction of blob names.
`data/release_assets.json` provides archive checksums.

## Model and data map

| Directory | Contents |
| --- | --- |
| `GHG_Calculation/` | Historical Monte Carlo LCA, operational phases, reconstructed fleet, historical inventory products |
| `scenario/` | Stock–fleet coupling, price loading, quota rules, scenario seeds and JABBA fitting |
| `model_parameters/` | Parameter builders and author-compiled CSV matrices with source annotations |
| `vessel_data_extract/`, `PMM_Imputation/`, `Stratified_Hot-Deck_Imputation/` | Registry harmonisation and missing-value reconstruction |
| `effort_data/` | RFMO catch/effort extraction, aggregation and grid allocation |
| `figures/Fig1/`–`Fig5/` | R figure renderers, Python data bridges and panel source tables |
| `figures/Extended_Data/`, `figures/supplement/` | Extended and supplementary figure code and data |
| `audits/` | Selected scientific validation algorithms, saved experiments and computational diagnostics |

The `audits` paths are retained because several figure/data bridges import their
scientific results. They contain no manuscript-authoring tools in this release.
Original RFMO downloads, vessel-registry microdata, third-party assessment
archives, large bundled fit objects, source parameter workbooks and boundary
shapefiles are not redistributed here. They remain in the author's private
working project. `data/external_inputs.csv` identifies the excluded source paths
and provider links. Re-rendering maps or recomputing models can require obtaining
these inputs under the providers' terms. This release supports the saved-result
analyses and provides the scientific algorithms; it does not claim that a fresh
full-chain run works without those external inputs. Source licences and terms
continue to apply; depositing generated files does not grant a new licence for
third-party artwork or external code.

## Reproduce figures from saved data

Use Python 3.13 and R 4.5.2 with the dependencies in `requirements.txt` and
`install_r_dependencies.R`. R/JAGS is required for fresh stock fits. Python
exports calculations and CSV bridges; the publication figures are drawn in R.

Run R commands from the repository root after restoring release data:

```sh
Rscript figures/Fig1/Fig1_Multi_Dimensional.r
Rscript figures/Fig2/Fig2_Spatial_Temporal_CEI.r
Rscript figures/Fig3/Fig3_Phase_Decoupling.r
Rscript figures/Fig4/Fig4_Coupled_Mechanisms.r
Rscript figures/Fig5/Fig5_Mitigation_Evidence.r
```

Fig. 4's independent feasible-catch stock panel is rendered by
`figures/Fig4/Fig4_Coupled_Validation.r`. Fig. 3's aligned layout is sourced by
its main renderer and is not a standalone script.

The scientific-validation release replaces supplementary figures 5, 15 and 19
with the R renderers in `figures/supplement/validation_20261018/`; their original
numbers are retained. All other supplementary renderers remain under
`figures/supplement/Supplementary_FigN/`.

## Recompute the models

Preserve a copy of the saved results before rerunning: the original scientific
scripts write to their documented output locations. Long model chains may take
hours. Re-rendering the figures does not require refitting every model.

1. Reconstruct vessel inputs using the registry and imputation directories.
2. Run `GHG_Calculation/ghg_lca.py` from its directory for the historical inventory.
3. Run `scenario/jabba_fit.r` for species-level exploratory stock projections.
4. Run `python scenario/regression_check_order_dependence.py` before future sweeps.
5. In `figures/Fig5/`, use `fig5_run.py proxies`, then `fig5_run.py`, then
   `fig5_run.py final` for the fixed-catch chain. `fleet_model.py` is an imported
   model interface, not the sweep entry point.
6. `audits/p0_revision_20261013/run_ensemble.py` and its matched-catch drivers
   implement the separate feasible-catch branch. Their saved runs and selection
   records are deposited; do not interpret these as the fixed-catch branch.
7. `audits/scientific_validation_20261018/` contains the targeted fuel,
   technology-correction and matched-catch mechanism analyses. Its
   `build_figure_inputs.py` refreshes the three revised supplementary panels.

The deposited seed/configuration records accompany the saved runs. Numerical
and convergence diagnostics address implementation and sampling; the global
stock aggregation and historical operating assumptions retain the limitations
reported with the scientific analyses.

## Scope of this repository

This public release contains model algorithms, scientific analysis and plotting
code, compiled parameter CSVs, saved aggregate outputs and figure data. Manuscripts, SI documents,
editorial automation, agent configuration, conversation material, local caches
and historical editing archives are excluded. The complete working project is
maintained separately by the author. No archival DOI is claimed by this GitHub
release.
