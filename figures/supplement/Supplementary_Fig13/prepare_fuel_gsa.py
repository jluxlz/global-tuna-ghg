"""Rebuild the terminal-year RF/SHAP diagnostic with multi-state fuel input draws."""

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

HERE = Path(__file__).resolve().parent
CALC = HERE.parents[2] / "GHG_Calculation"
sys.path.insert(0, str(CALC))
import ghg_lca as lca
from fuel_operation import draw_operating_days


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    draws, seed = 2000, 42
    pm = lca.load_prior_matrix(lca.PRIOR_MATRIX_PATH)
    fleet, pools = lca.run_imputation_pipeline(lca.VESSEL_REGISTRY_PATH, pm, random_seed=seed, write_output=False)
    fleet = lca.impute_builtdate_deterministic(lca.convert_gt_to_lsw(fleet, pm), pools)
    fleet = lca.assign_operational_params(fleet, pm)
    _, features, results = lca.run_monte_carlo_lca(
        fleet, pm, start_year=2025, end_year=2025, n_simulations=draws, random_seed=seed,
        lookup_data_power=lca.init_power_discount_lookup(lca.PNAS_POWER_PATH, baseline_year=2015),
        lookup_data_alpha=lca.init_time_profile_lookup(lca.PNAS_POWER_PATH, verbose=False),
        return_draws=True, multi_mode_fuel=True,
    )
    operating = draw_operating_days(draws, seed, lambda load: lca.apply_sfoc_formula(1., load, pm))
    features = features.drop(columns=["H_map", "LF_move", "LF_work", "Alpha"])
    for group, result in operating.items():
        features[f"{group} annual fuel days"] = result[:, 0]
        features[f"{group} main fuel-weighted hours"] = result[:, 2]
        if group != "LL_gasoline":
            features[f"{group} auxiliary fuel-weighted hours"] = result[:, 4]
    features = features.loc[:, features.nunique().gt(1)]
    y = results["Total"][:, -1]
    train, test = train_test_split(np.arange(draws), test_size=.2, random_state=seed)
    forest = RandomForestRegressor(n_estimators=200, max_depth=12, random_state=seed, n_jobs=4)
    forest.fit(features.iloc[train], y[train])
    prediction = forest.predict(features.iloc[test])
    qc = {"Draws": draws, "Features": features.shape[1], "Holdout_R2": r2_score(y[test], prediction),
          "Holdout_RMSE_Mt": mean_squared_error(y[test], prediction)**.5/1e6,
          "Holdout_MAE_Mt": mean_absolute_error(y[test], prediction)/1e6,
          "Holdout_MAPE_pct": float(np.mean(np.abs(prediction/y[test]-1))*100)}
    forest.fit(features, y)
    shap_values = pd.DataFrame(shap.TreeExplainer(forest).shap_values(features), columns=features.columns)
    importance = shap_values.abs().mean().sort_values(ascending=False).head(10)
    importance.rename_axis("Parameter").rename("Mean_SHAP").to_csv(HERE / "Supplementary_Fig13_PanelA_Importance.csv")
    data = []
    for feature in importance.index:
        data.append(pd.DataFrame({"Parameter": feature, "Draw": np.arange(draws),
                     "SHAP_Mt": shap_values[feature]/1e6,
                     "Feature_Rank": features[feature].rank(pct=True)}))
    pd.concat(data).to_csv(HERE / "Supplementary_Fig13_PanelB_SHAP.csv", index=False)
    (HERE / "Fuel_GSA_Holdout.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")
    print(qc)


if __name__ == "__main__":
    main()
