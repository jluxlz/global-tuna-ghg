# Global tuna-fishery greenhouse gas emissions

**Current complete version: v2026.10.21.** [Download the complete code and data package](https://github.com/jluxlz/global-tuna-ghg/releases/download/v2026.10.21/global-tuna-ghg-complete.zip). Download this one ZIP; no earlier release is needed. GitHub's automatic source-code archives do not include all large inputs.

The primary future comparison uses constant-catch (C), constant-harvest-rate (F) and biomass-threshold (T) rules under common stock, realized-catch, economic and fleet-capacity feedback. It contains 1,944 primary simulations and 1,620 sensitivity simulations. Nine additional matched-output triples provide 27 paired comparisons; all 384 matching candidates are retained. The original C/F comparator remains separate for Supplementary Fig. 19. Fixed 2024 catch is not the primary current-management baseline.

Historical accounting covers 1950-2025. Future models retain 81 exogenous configurations per rule and evaluate all subsets of fuel transition, refrigeration transition and fleet consolidation. Current figure scripts, panel inputs and saved results match the final scientific version, including Fig. 5e and Supplementary Figs. 10, 14 and 21.

Extract the complete ZIP and run:

```sh
python restore_data.py --verify
python reproduce.py verify
```

Install Python requirements and R packages before computation. Use `python reproduce.py figures` to redraw supplied results or follow [REPRODUCING.md](REPRODUCING.md) to recalculate model stages. Git-clone users can run `python restore_data.py --download --verify` to retrieve the same complete package. Live scraping is optional: accepted vessel data, original provider inputs and saved vessel-query results are supplied. Sources retain their original identities, native field names and bytes; authored code, documentation and public paths are English.

The two core algorithms are `GHG_Calculation/ghg_lca.py` and `scenario/fleet_model.py`. Scientific robustness and HCR drivers are in `analysis/`. Python handles model/data calculations; figures use R/ggplot2. The package includes saved stock inputs, so stock refitting is optional. Model stages can take hours.

## Evidence and scope

The longline absolute-fuel discrepancy remains unresolved. Nonfishing time is approximated as transit, refrigeration service equivalence is exploratory, some fuel factors retain source-specific boundary qualifications, and pooled stock models do not replace official RFMO assessments. Saved scenario and accounting checks verify implementation and pairing, not universal management superiority or empirical biological validation. See `analysis/hcr_revision_20261020/RESULTS_README.md` and the source tables.

Manuscripts, SI prose, editorial automation, agent configuration, old code copies and the former local audit workspace are excluded. `data/source_inputs.csv`, `data/file_manifest.csv` and `data/figure_inputs.json` document supplied inputs and figure data. Historical releases are archives; use this version for the current scientific code and results.
