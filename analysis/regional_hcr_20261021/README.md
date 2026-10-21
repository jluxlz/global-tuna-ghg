# Conditional Indian Ocean BET quota and fuel experiments

This extension uses the accepted regional BET refit through 2024, its complete assessment-catch input and the same fixed species-accounting weights as the regional source check. It compares C/F/T harvest rules with fuel/no-fuel conditions across the 81 exogenous futures: 486 full 2025–2050 stock–fleet runs. The accounting component is conditional and does not represent total IOTC emissions or an official assessment.

The paired designs share initial fleets, stock parameters, seeds, costs and capacity constraints. `QC.json` checks 1,458 output hashes, 162 paired parameter sets, stock balance, removal ceilings, capacity and catch–GHG identities. Regional T never triggers; the F/T trajectories are numerically identical. These numerical checks do not establish external biological validity.

The regional result qualifies the pooled model: higher cumulative catch can offset lower CEI, and a biomass threshold has no additional effect while the stock remains above its trigger. Fuel-transition benefits include cost-related activity and catch changes. The analysis distinguishes cumulative and annual endpoint effects.

Run the scenario order guard, save its PASS log as `order_guard.log`, then run `run_regional_hcr.py pilot`, `run_regional_hcr.py full` and `analyse_regional_hcr.py`. The root reproduction driver includes the full regional extension with `--extra-experiments`. Source inputs are in `analysis/p0_revision_20261013/regional_inputs/`. Each run retains Annual, Stocks, Effort and Complete records; all figure bridges are in Extended Data Fig. 9.

The historical YFT archive remains a historical-state diagnostic and is not advanced as a current regional fit in this extension. No historical inventory, pooled fit or global scenario value is recalibrated here.
