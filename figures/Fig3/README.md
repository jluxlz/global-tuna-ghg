# Figure 3: effort requirements and per-effort emissions

Panel a compares logarithmic trends in standardised effort per unit catch and
GHG per unit standardised effort. Panels b and c show longline and purse-seine
factor trajectories, respectively, with grid-era background bubbles and RFMO
ratios of totals. The two RFMO rows share aligned column boundaries.

From the repository root, after restoring the source data:

```sh
python figures/Fig3/preprocess_fig3.py
Rscript figures/Fig3/Fig3_Phase_Decoupling.r
```

The main R entry point sources `Fig3_PanelA_Decomposition.r` and
`Fig3_PanelBC_Era_Background.r`. The `a` and `bc` arguments select individual
panels. The current composite uses the inherited output basename
`Fig3_Era_Background_Preview`; the basename does not denote a separate analysis.
Panel CSVs preserve the plotted quantities and aggregation definitions.

Historical design archives and authoring notes are excluded from this public
distribution. Use the deposited analysis outputs for scientific comparisons.
