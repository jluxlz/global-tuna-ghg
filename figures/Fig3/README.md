# Fig3 Index to current files and archives

Collate Date: 2026-10-12. 

Keep the current version at the top: a Trends in logarithms for grids; b/c For Gray Grid–Period bubbles, Three-year period RFMO Aggregation Point and Time Arrows. b/c retain RFMO Colours, Time shape, Bubble Emission Legend, Removed diagram description text specified by the user. 

## Current entrance

Run from Project Root Directory: 

```powershell
& C:/CONDA/python figures/Fig3/preprocess_fig3.py
$env:R_HOME='C:/Users/11401/Desktop/r_env/R_4.5.2/lib/R'
$env:PATH='C:/Users/11401/Desktop/r_env/R_4.5.2/lib/R/bin/x64;C:/Users/11401/Desktop/r_env/R_4.5.2/Library/bin;' + $env:PATH
& C:/Users/11401/Desktop/r_env/R_4.5.2/lib/R/bin/x64/Rscript.exe --vanilla figures/Fig3/Fig3_Phase_Decoupling.r
```

Default Output As `Fig3_Era_Background_Preview.png/.pdf/.tiff`. Name of file name following preview phase, Its the current version. R Add the entrance `a` Only out a; Add `bc` or `bc-era` Only out b/c. Python Add `bc` or `bc-era` Only update the current b/c Data. Original `era-background` Parameters can still be used for complete drawings. 

Current code only: 

- `preprocess_fig3.py`: Current a, b, c Data build and upstream catch record verification. 
- `Fig3_Phase_Decoupling.r`: Full Chart Entry. 
- `Fig3_PanelA_Decomposition.r`: a Rendering Modules. 
- `Fig3_PanelBC_Era_Background.r`: b/c Rendering Modules. 

Current on top layer panel CSV, Audit JSON, Single Panel PNG/PDF and `Fig3_Revision_Notes.md` Keep together. Do not read the current build and render `_archive_*`, The removal of the archive will not affect the current entrance. 

## Archiving Group

| Folder | Save Content | Compare focus |
|---|---|---|
| `_archive_pre_decomposition_20261011` | Original CPUE–CEI Figure, Code and panel data | Change a Original analysis in front of coordinates |
| `_archive_newspace_prototypes_20261011` | a of NewSpace Data and preview 1–6 The code of the code, PNG, PDF, Total 19 File | Early design test; Not As Current Statistics |
| `_archive_pre_bc_aggregation_20261011` | Rewrite b/c Maps saved before aggregation method, Code and data | b/c Old method for taking median numbers separately |
| `_archive_decade_aggregation_20261011` | b/c Changed to the trajectories of the total margin, Sensitivity data, Audit, Old complete diagram; Also attach precodes and shares a Enter Snapshot | The multi-year trajectories were compared to the current three-time background bubble design |
| `_archive_legacy_exports_20260928` | `Fig3_new.pdf/.png/.tif` and `Rplots.pdf` | Early Export Diagram; No corresponding generation code confirmed |
| `_archive_runtime_cache_20261012` | Old Python Build Cache | Cache Save, Not used as source code |

Archiving Code Keep Moves/Copy Pre-Purpose, For Version Comparison. Some History Scripts By Original Fig3 Top-level Path Prepared, You cant expect to come back when youre in the subdirectories. Copies of existing maps and data can be viewed directly. 

`Fig3_Archive_Manifest_20261012.json` Save this move, Copy List, Size and SHA-256 Verify value. Two original archive folders remain as they are. No File Deleted. 

## Adobe Original

`Fig3.ai`, `Fig3.pdf`, `Fig3.png`, `Fig3.tif` Original for User, Keep position as agreed at the warehouse, No change in content. The analysis is based on the current output and the analytical output in the archive. 

Run Environment Tip: This is the base R Returns status after completion of export 1, No computational error occurred. Direct check of output files and data claims; See for details `Fig3_Revision_Notes.md`. 
