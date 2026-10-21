# Current Extended Data inventory

The 2026-10-12 manuscript audit retains ten Extended Data figures, matching the Nature Food maximum of ten display figures. See [journal guidance](https://www.nature.com/natfood/submission-guidelines/aip-and-formatting).

| Figure | Purpose | Current treatment |
|---|---|---|
| ED1 | System boundary | Retain the author-made diagram |
| ED2 | Modelling framework | Retain the author-made diagram; caption reflects coastal and industrial coverage |
| ED3 | Fleet affiliation versus area attribution | Essential; distinct coverage and paired-draw uncertainty |
| ED4 | Recorded footprint and annual catch/CEI components | Essential; harmonised 5° cells, observed era durations, exact log-mean decomposition |
| ED5 | Actual JABBA fits and sampling diagnostics | Essential; replaces unsupported official-B/K concordance |
| ED6 | Economic elasticity | Retain as a stylised post-processing sensitivity |
| ED7 | Future technology creep | Retain; show all configurations alongside rate medians |
| ED8 | Subsidy sensitivity | Retain; all three groups restored, including no subsidy |
| ED9 | Implied effort caps | Retain; analytical post-processing, not profitability optimisation |
| ED10 | Four-measure Shapley decomposition | Essential to the relative-contribution claim; formerly ED11 |

Former ED10 is now `figures/supplement/Supplementary_Fig17`, preserving baseline factor contrasts. `figures/supplement/Supplementary_Fig4` documents historical coverage and reconstruction balance. Directory, script and output numbers follow the current SI. Previous code and figure files are preserved under the dated audit archives.

ED5 uses current `jabba_diagnostics/*_fit.rds` and actual JAGS chain arrays. The isolated audit run reproduces the production C/F projection CSVs byte for byte. It does **not** resolve limited MCMC mixing. Its official-reference table preserves region, year, native metric and uncertainty, without conversion to global total-biomass B/K.

Still needed for stronger biological conclusions: adequately mixed stock fits, retrospective/hindcast checks, matched regional populations and metrics, a fresh historical technology-rate sensitivity with repaired inputs, and stock-posterior propagation into scenarios. Current projections remain conditional exploratory comparisons.

Figures use R/ggplot2 exclusively, Arial typography, consistent gear/WEO colours, 183 mm canvases, vector PDF, 300 dpi PNG and 900 dpi LZW TIFF. All plotted panel data are exported alongside each renderer. A task renderer can refresh the current figures without rerunning fleet models:

```powershell
C:/CONDA/python analysis/manuscript_extended_20261012/render_current_figures.py
```
