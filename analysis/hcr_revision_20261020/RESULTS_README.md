# C F T quota-rule revision verified on 21 October 2026

This revision replaces fixed Catch2024 as the primary future baseline. Observed 2024 catch remains a reference-calibration input. C, F and T share fitted stocks, initial fleets, exogenous futures, physical capacity, fuel-cost constraints and realized-removal feedback. Rules are representative mechanisms, not assessments of current RFMO policy.

## Completed calculations

- 1,944 primary simulations: 81 futures × three HCRs × eight subsets of fuel, refrigeration and consolidation.
- 1,620 full stock–fleet sensitivity simulations: operating days, harvest fractions, threshold pairs and fixed alternative-fuel prices.
- Original C/F reproduction: 18 annual runs, preserving the original SBT coefficient and 19.3623% median cumulative GHG difference.
- New matching: 384 candidates retained, nine common C/F/T actual-catch targets and all 27 matched pairs. Maximum absolute pairwise catch gap is 0.8135%.
- Verified complete checkpoints: 3,963, with 19,815 output files checked against their recorded hashes. This total includes validation and matching runs and is not the primary design count.

`Final_Scientific_QC.json` records input, parameter-pairing, common initial-state, output-hash, stock balance, process allocation, LMDI and three-technology Shapley checks. These are numerical/design checks, not independent biological validation.

## Principal outputs

No-transition medians over 2025–2050:

| Rule | Cumulative catch Mt | Cumulative GHG Mt CO2e | Period CEI t CO2e/t |
|---|---:|---:|---:|
| C | 23.1 | 795.4 | 34.5 |
| F | 77.2 | 341.1 | 4.4 |
| T | 77.7 | 306.5 | 3.9 |

Paired cumulative fuel reductions are 45.3%, 34.0% and 33.7% under C/F/T; all three technical measures give 60.5%, 63.1% and 63.4%. Each percentage uses its own no-transition rule reference. These are cumulative effects, not the superseded 2050 BAU-based reductions.

New comparable-catch medians are 40.3% for F relative to C, 41.7% for T relative to C and 2.0% for T relative to F. Fractions apply uniformly across species and are selected using catch alone. Matched F/T fractions can differ. The original 19.4% family applies its retained SBT coefficient and original parameter design; it is preserved separately and is not contradicted or overwritten by the new estimand.

Effort per catch is the largest absolute C/F and C/T accounting term. F/T has a different balance, including timing and support activity. Common species–year intensity comparisons are particularly sensitive to near-zero late C catches and must not be reported as 99.5% whole-fleet or biological-efficiency savings. All zero cells and fixed/support terms remain explicit.

## Source tables

- `analysis/HCR_Period.csv`: catch, GHG, period CEI and endpoint quantities for all primary runs.
- `analysis/HCR_Technical_Effects.csv`: within-HCR paired technical effects.
- `analysis/HCR_Three_Technical_Shapley.csv`: exact three-technology attribution.
- `HCR_Matched_Pairs.csv`: every selected pair, fractions, actual catches and emissions.
- `Catch_Matching_All_Candidates.csv`: all candidate trials.
- `analysis/HCR_Matched_LMDI_Terms.csv`: all five factors, structural zeros, fixed processes and support contributions.
- `analysis/HCR_Matched_Stock_Effort.csv`: all matched annual stock, effort and catch records.
- `analysis/HCR_Matched_Mechanism_Summary.csv`: whole-fleet and common-weight intensity contrasts and coverage.
- `analysis/HCR_Sensitivity_Period.csv`: complete sensitivity periods.

Each updated figure folder also contains its panel inputs and R-rendered CSVs. Supplementary Fig. 19 retains the original C/F family; Supplementary Fig. 21 contains the new three-rule mechanism analysis. Superseded document and figure backups are archived privately; only the current scientific files are retained locally.

## Price correction

Eighteen nonpositive upstream price records were diagnosed. The approved positive inverse carbon-price relationship replaces the old negated growth formula for HVO, FAME and biogenic LNG. It is a prescribed scenario assumption. Fixed-2023-price sensitivities rerun complete states. Cost, activity and vessel-GHG guards reject invalid values rather than silently omit them. Regional price interpolation uses one consistent series. Unfuelled HCR baselines and original C/F results are numerically unchanged by this correction.

Historical inventory, Fig. 1–3 and JABBA fits are unchanged. Fig. 4b/f inputs and physical fuel factors are retained; only approved cost-dependent HVO/FAME entries change in Fig. 4d/e. The current scientific distribution uses this verified C/F/T result set.

