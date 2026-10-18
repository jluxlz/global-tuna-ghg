# -*- coding: utf-8 -*-
"""
SF6 (reduced): exact Shapley over {quota, fuel, refrigerant, consolidation}
on a stratified subset of futures (3 WEO x 3 TechCreep, central Growth +
Natural retirement) with COMMON RANDOM NUMBERS per future.
16 combos x 9 futures = 144 sims, 2050 endpoints only.

Output: scenario/output/fig5/SF6_Combos_2050.csv
"""
import os, sys, time, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import numpy as np
import pandas as pd
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scenario"))
sys.path.insert(0, os.path.join(ROOT, "figures", "Fig5"))
import fig5_run as F
import fleet_model

OUT = F.OUT
from scenario_seeds import paired_seed, record_seed_protocol


def main():
    fleet, pm = fleet_model.load_baseline_fleet()
    pool_args = (fleet, pm)

    # FULL 81-future factorial (common random numbers per future)
    subset = [(w, g, r, t) for w in F.BAU_WEO for g in F.BAU_GROWTH
              for r in F.BAU_RETIRE.values() for t in F.BAU_TECH]
    print("[SF6r] futures: %d" % len(subset), flush=True)

    ff = json.load(open(os.path.join(OUT, "Fig5_Final_Fuel.json")))
    qs = json.load(open(os.path.join(OUT, "Fig5_Final_Quota.json")))

    def task(bi, combo):
        w, g, r, t = subset[bi]
        p = F.make_params(weo=w, growth=g, tc=t)
        p["retirement_scenario"] = int(r)
        p["forced_retirement_rate"] = 0.0
        q, f_, rf, cs = combo
        if q:
            p["quota_type"] = dict(qs)
            p["schaefer_scenario"] = dict(F.MSY_FRAC)
        if f_:
            p.update(ff[w])
        if rf:
            p["refrigerant_type"] = "LN2"
        if cs:
            p["consolidation_type"] = 2
        return (p, paired_seed(subset[bi]), None)   # common seed per future

    combos = [(q, f_, rf, cs) for q in (0, 1) for f_ in (0, 1)
              for rf in (0, 1) for cs in (0, 1)]
    tasks, keys = [], []
    for bi in range(len(subset)):
        for c in combos:
            tasks.append(task(bi, c))
            keys.append((bi, c))
    print("[SF6r] %d sims" % len(tasks), flush=True)

    t0 = time.time()
    pool = Pool(F.N_WORKERS, initializer=F._init_worker, initargs=pool_args)
    res = pool.map(F._rho_task, tasks, chunksize=4)
    pool.close(); pool.join()
    print("[SF6r] done in %.0fs" % (time.time() - t0), flush=True)

    rows = []
    for (bi, c), out in zip(keys, res):
        rg = out[3]
        ghg = rg.groupby("Year")["GHG_tCO2e"].sum()
        w, g, r_, t = subset[bi]
        rows.append({
            "Future": "F%02d" % (bi + 1),
            "WEO": w, "Growth": g,
            "Retirement": [k for k, v2 in F.BAU_RETIRE.items() if v2 == r_][0],
            "TechCreep": t,
            "Combo": "%d%d%d%d" % c,
            "GHG_2050_Mt": ghg.get(2050, np.nan) / 1e6,
        })
    df = pd.DataFrame(rows)
    p = os.path.join(OUT, "SF6_Combos_2050.csv")
    df.to_csv(p, index=False)
    record_seed_protocol(OUT, ["SF6_Combos_2050.csv"])
    print("[SF6r] saved %d rows -> %s" % (len(df), p), flush=True)


if __name__ == "__main__":
    main()
