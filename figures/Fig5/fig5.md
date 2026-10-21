# Fig. 5 quota design and technical mitigation

Current analysis, 21 October 2026: C/F/T harvest control rules share one realized-catch stock–fleet model. Catch2024 calibrates the reference pulse; it is not a primary BAU. Each of 81 exogenous futures is crossed with three rules and eight subsets of fuel transition, refrigeration transition and fleet consolidation: 1,944 primary cases. Three-measure Shapley attribution is performed within each HCR. There is no binary quota-reform contribution.

Current figure: `Fig5_Mitigation_Evidence.png/pdf/tiff`, rendered by `Fig5_HCR_Evidence.r`. The canonical `Fig5_Mitigation_Evidence.r` and `plot_fig5.r` forward to it. Panels show annual no-transition GHG; period catch/GHG/CEI and minimum stock ratio; within-HCR fuel benefits; technical packages; and 27 matched comparisons from nine common-target C/F/T triples.

Run from the project root:

```powershell
C:/CONDA/python figures/Fig5/prepare_hcr_panels.py
C:/CONDA/python analysis/full_chain_20261012/render_single.py figures/Fig5/Fig5_HCR_Evidence.r
```

The builder reads current verified analyses from `analysis/hcr_revision_20261020/analysis` and writes every panel's CSV locally. That current audit directory contains scientific drivers, full simulation ledgers and provenance and must not be deleted as preview cache. `run_hcr.py`, `match_hcr.py` and `analyse_hcr.py` provide the experiments, catch-only parameter matching and exact accounting. `launch_validated.py` / `production_chain.py` orchestrate production. Inspect `PLAN.md`, `Pilot_QC.json`, `Production_Complete.json` and `Final_Scientific_QC.json` before recomputation. Core/input changes require fresh order-dependence and pilot checks; fingerprints prevent reusing mismatched caches.

Primary fractions equal one for all species. T uses total-biomass/K trigger and closure proxies of 0.4/0.1, not current RFMO spawning-biomass references. Sensitivities comprise 1,620 full annual state reruns for days, fractions, thresholds and fixed biofuel prices. The inverse carbon-to-biofuel price relation is a prescribed scenario assumption, not an estimated causal law.

The new matching sources retain 384 candidates, nine common triples and all 27 contrasts, including annual stocks, catch, effort, GHG and threshold events. Five-factor accounting keeps structural zeros, LL/PS fixed processes and support vessels and closes to whole-fleet GHG. Common-weight activity intensities have a narrower scope and can be sensitive to near-zero catch. Matched F/T fractions can differ; the result is not a threshold-only causal effect.

The original C/F design and SBT coefficient remain in Supplementary Fig. 19; its 19.4% median saving was reproduced. New uniform-fraction comparisons are in Supplementary Fig. 21. Earlier regional checks in Supplementary Fig. 20 qualify pooled-model scope, not universal T-type optimality. Original Adobe files remain read-only.

This HCR revision is locally verified. Existing public release assets have not automatically been replaced.

## Archived pre-HCR design and commands

The instructions below document the superseded comparison. `prepare_story_panels.py`, legacy `fig5_run.py full/final` and four-factor Shapley outputs do not regenerate the current C/F/T main figure.

Current figure: Fig5_Mitigation_Evidence.pdf/png/tiff. Five panels: (a) fixed-catch vs resource-and-capacity BAU, (b) paired annual 2050 reductions, (c) quota/fuel ordering, (d) cumulative catch/GHG/period CEI, (e) nine matched cumulative-catch experiments.

Run C:/CONDA/python figures/Fig5/prepare_story_panels.py, then Rscript figures/Fig5/plot_fig5.r in the configured R environment. On this host, analysis/full_chain_20261012/render_single.py supplies the documented R runtime and validates graphics before promotion. Every panel keeps its raw and rendered CSV; configurations are joined by WEO/growth/retirement/technology, not row order. These commands read saved simulations and do not rerun fleet or stock models.

Pressure-test sources: scenario/output/fig5; constrained sources: analysis/p0_revision_20261013/ensemble and analysis. After any production/model input change, regenerate and verify both branches before updating the figure. The source hashes and displayed statistics are in analysis/fig5_story_layout_20261013/Data_QC.json.

Fuel properties, screening and transition curves are in Supplementary_Fig9; quota assignment/screening in Supplementary_Fig11; regional technical and object effects in Supplementary_Fig16. Full operating-bound/Shapley, LMDI/matched-catch and regional checks remain in Supplementary Figs. 18–20.

The decision-chain renderer and prior panel images/data are archived under _archive_before_story_layout_20261013. Fig5.png and Fig5.pdf are original Adobe products and remain read-only.


## 2026-10-17 paired seed protocol (started 2026-10-16)

The canonical helper is scenario/scenario_seeds.py. Each of the documented 81 futures uses seed 42+future_index; every baseline/measure subset shares that future seed. Replicate seeds add 81 per replicate. Task positions and policy names must never offset seeds. Key input/output hashes and Seed_Provenance.json gate reuse. The portfolio, quota-only, fuel-only, Shapley and economic capture drivers follow this policy.

The one-time checkpointed migration is figures/Fig5/fig5_paired_rerun.py (dated audit folder). It replaces all 16-subset pressure-test simulations, reuses pilot checkpoints, checks exact baseline reproduction and refreshes the current figure consumers. Ordinary production retains fig5_run.py full/final and the Shapley driver; run scenario/regression_check_order_dependence.py after model/driver/input changes, before production. Same initial seeds are not a guarantee of identical policy-dependent draw streams.

Current supplementary object effects are rebuilt from Heterogeneous_Mitigation_Results.csv by prepare_story_panels.py. Never restore the archived object panel over current data. Updated values, source hashes and replicated-seed checks are in analysis/paired_seed_revision_20261016/.
