# Supplementary Figure 14 external benchmarking

This folder preserves the external comparisons added on 15 October 2026. The analysis reads the frozen historical inventory and does not run JABBA, the LCA engine or future fleet scenarios.

`Supplementary_Table10_Benchmark.csv` contains all plotted comparisons and the native Word table values. `Model_Matched_Summaries.csv` retains the matched catch, fuel mass, recovered litres and separate combustion, upstream-plus-combustion and full-LCA intensities. `Matched_Flag_Gear_Sector_Audit.csv` preserves every scope weight and sector process numerator. `Fleet_Characteristics_Context.csv` and `Annual_Fuel_Totals_Context.csv` retain descriptive comparisons for populations that cannot be fully matched. `Workbook_Row_Adjudication.csv` accounts for every original spreadsheet row. `Benchmark_QC.json` records conservation checks and source problems.

To reproduce numerical tables from the project root:

```powershell
C:/CONDA/python figures/supplement/Supplementary_Fig14/benchmark_external.py
```

Required model inputs are `GHG_Calculation/Base_2_Fleet_GHG.csv`, `Base_3_Spatial_Grid_Enriched.csv` and `PMM_Imputation/After_PMM_Vessels.csv`. The original `cross_analysis` workbook is read directly, including its three worksheets. File hashes are recorded in the audit. Official UK fuel properties and the unmodified downloaded workbook are preserved under `sources`.

To redraw from the saved panel source CSV, without access to the large inventory:

```powershell
C:/CONDA/python analysis/full_chain_20261012/render_single.py figures/supplement/Supplementary_Fig14/Supplementary_Fig14.r
```

The R script also runs directly in the configured R 4.5.2 environment. It writes a data CSV for each panel plus vector PDF, 300 dpi PNG and 900 dpi TIFF at 183 mm width.

Interpretation: percentage differences are descriptive, not statistical bias estimates. The model and surveys differ in exact fleet, target-catch and sampling coverage. The 2009 PS survey family supplies activity parameters, so that comparison is calibration-linked. The 2023 survey provides independent fuel outcomes. Its LL sample is Pacific only. Carriers are excluded from fishing-vessel comparisons. A full-LCA contextual row has deliberately different boundaries and shared background sources. Source inconsistencies and unresolved LL discrepancies are disclosed in SI S6.4; no blanket external-validation claim is made.

The recoverable formula for model fuel litres is the sum, over sectors, of allocated combustion CO₂ divided by its fixed carbon factor and fuel density. Never recover fuel by dividing complete CEI by a diesel emission factor. Sector-specific fuel and the same matched catch records are essential.

Species matching allocates both emissions and catch: ALB only for the 2009 LL survey; SKJ plus YFT for Spanish PS in 2003; SKJ/YFT/BET/ALB for the other comparisons. It does not identify the operating behaviour of separate target fleets. Survey fuel may include scouting craft/helicopters, while model service-vessel processes are excluded; this residual boundary difference is explicit.

## Visualization update 21 October 2026

Panels a and b retain absolute fuel comparisons; c adds the six descriptive relative gaps. Panel d separates modeled combustion, upstream fuel supply and other LCA components, alongside survey combustion only. Panel e retains the boundary-mismatched full-LCA context. The new components are exact differences between preserved matched process totals. No parameter fitting, new model simulation or confidence intervals are introduced. Panel CSVs document the plotted quantities.
