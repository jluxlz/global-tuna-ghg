# -*- coding: utf-8 -*-
"""
SF5 (step 1, parallel): capture annual Cost_Ratio / M_econ / E_final paths per
WEO for the BAU arm and the WEO-bound fuel arm (beta=-0.3), plus verification
runs at beta=-0.7. 3 WEO x {BAU(-0.3, -0.7), fuel(-0.3)} = 9 sims in parallel.
Output: scenario/output/fig5/SF5_Multiplier_Paths.csv
"""
import os, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import pandas as pd
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scenario"))
sys.path.insert(0, os.path.join(ROOT, "figures", "Fig5"))
import fleet_model, fig5_run as F

OUT = F.OUT
_FF = json.load(open(os.path.join(OUT, "Fig5_Final_Fuel.json")))


def _capture(args):
    weo, arm, beta, seed = args
    p = F.make_params(weo=weo, growth=0.0136, tc=0.024)
    p["retirement_scenario"] = 1
    p["forced_retirement_rate"] = 0.0
    p["elasticity"] = beta
    if arm == "fuel":
        p.update(_FF[weo])
    hist, final = fleet_model.run_scenario_simulation(
        F._W["fleet"], F._W["pm"], p, start_year=2025, end_year=2050,
        random_seed=seed)
    h = pd.DataFrame(hist)
    d = h[["Year", "Cost_Ratio", "M_econ", "E_final", "Total_GHG_tCO2e"]].copy()
    d["WEO"] = weo; d["Arm"] = arm; d["Beta"] = beta; d["Seed"] = seed
    return d


def main():
    fleet, pm = fleet_model.load_baseline_fleet()
    args = []
    for i, weo in enumerate(["STEPS", "APS", "NZE"]):
        args.append((weo, "BAU", -0.3, F.paired_seed((weo, 0.0136, 1, 0.024))))
        args.append((weo, "BAU", -0.7, F.paired_seed((weo, 0.0136, 1, 0.024))))
        args.append((weo, "fuel", -0.3, F.paired_seed((weo, 0.0136, 1, 0.024))))
    with Pool(int(os.environ.get("FIGURE_CAPTURE_WORKERS", "3")), initializer=F._init_worker, initargs=(fleet, pm)) as pool:
        res = pool.map(_capture, args)
    df = pd.concat(res, ignore_index=True)
    p = os.path.join(OUT, "SF5_Multiplier_Paths.csv")
    df.to_csv(p, index=False)
    print("saved", p, len(df))


if __name__ == "__main__":
    main()
