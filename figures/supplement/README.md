# Supplementary figures matching the current SI

Current scientific figure set: 2026-10-19, with frozen-input reproducibility repair on 2026-10-20. Manuscript and editorial files are excluded from this repository.
Folder, renderer, panel CSV, caption and output numbers all match the SI figure number.
For example, `Supplementary_Fig3/Supplementary_Fig3.r` draws SI Fig. 3, historical missing-capacity reconstruction.

| SI figure | Content | Folder and renderer |
|---|---|---|
| 1 | Fleet composition and annual inventory | `Supplementary_Fig1/Supplementary_Fig1.r` |
| 2 | PMM donor diagnostics | `Supplementary_Fig2/Supplementary_Fig2.r` |
| 3 | Historical missing-capacity reconstruction | `Supplementary_Fig3/Supplementary_Fig3.r` |
| 4 | Historical data coverage and reconstruction balance | `Supplementary_Fig4/Supplementary_Fig4.r` |
| 5 | Historical stock and fishing-effort context | `validation_20261018/Supplementary_Fig5/Supplementary_Fig5.r` |
| 6 | All retained JABBA CPUE series | `Supplementary_Fig6/Supplementary_Fig6.r` |
| 7 | Production JABBA chain trajectories | `Supplementary_Fig7/Supplementary_Fig7.r` |
| 8 | Future configurations and simulation stages | `Supplementary_Fig8/Supplementary_Fig8.r` |
| 9 | Fuel properties, screening and transition depth | `Supplementary_Fig9/Supplementary_Fig9.r` |
| 10 | Consolidation schedule and accounting | `Supplementary_Fig10/Supplementary_Fig10.r` |
| 11 | Species quota assignments and effort screening | `Supplementary_Fig11/Supplementary_Fig11.r` |
| 12 | Global sensitivity and SHAP attribution | `Supplementary_Fig12/Supplementary_Fig12.r` |
| 13 | Historical parameter ranges and future configuration ranges | `Supplementary_Fig13/Supplementary_Fig13.r` |
| 14 | External benchmarking of fuel use and GHG emission estimates | `Supplementary_Fig14/Supplementary_Fig14.r` |
| 15 | Longline fuel intensity and operating assumptions | `validation_20261018/Supplementary_Fig15/Supplementary_Fig15.r` |
| 16 | Regional and fleet-object technology-based mitigation | `Supplementary_Fig16/Supplementary_Fig16.r` |
| 17 | Baseline factor contrasts | `Supplementary_Fig17/Supplementary_Fig17.r` |
| 18 | Whole-chain capacity and resource sensitivity | `Supplementary_Fig18/Supplementary_Fig18.r` |
| 19 | Matched-catch GHG differences and accounting decomposition | `validation_20261018/Supplementary_Fig19/Supplementary_Fig19.r` |
| 20 | Regional conditional refits and historical-state feasibility checks | `Supplementary_Fig20/Supplementary_Fig20.r` |

## Rendering and data refresh

All scientific figures use R. From the project root:

```powershell
python figures/supplement/render_all.py
python figures/supplement/render_all.py 3 14 15
```

The first command renders all 20 figures; the second renders selected current numbers. It reads saved panel data and does not run the LCA, JABBA or fleet scenarios.
Individual R entrypoints can also be run with the configured R environment. The batch driver uses the project runtime wrapper to validate PNG/PDF/TIFF before promotion.

`refresh_data.py` refreshes dependent saved-data bridges using current numbering. Per-figure builders remain with the figures that have them. Initial scaffold builders are retired because they use obsolete numbering and overwrite approved layouts.

## Tables and provenance

Numbered table CSVs use current SI table numbers. The external benchmark is `Supplementary_Fig14/Supplementary_Table10_Benchmark.csv`; engineering conversions are `tables/Supplementary_Table3_Engineering_Conversions.csv`; engine clocks are `tables/Supplementary_Table11_Engine_Clock.csv`.
`Current_SI_Numbering.csv` lists current captions and actual asset directories. Its Previous_number column records provenance only.
The complete pre-alignment tree is archived at `analysis/si_filename_alignment_20261016/before/supplement/`. Nested `_archive*` directories retain historical filenames and are not current SI assets.

The optional `spider/` collectors are not part of offline reproduction. Use the accepted frozen registry and saved query results described in `REPRODUCING.md`.
