# -*- coding: utf-8 -*-
"""REGRESSION GUARD (2026-09-29): the flags_orgs cache-collision bug.

get_meco_eff_map cached results keyed by (msy, quota_type, year, tc) but NOT by
flags_orgs, so whichever sim ran FIRST in a process polluted the shared cache
for all later sims on that worker (order-dependent outputs, up to ~48 Mt at
2050 peak; whole 9/22-9/29 Fig5/SF chain + manuscript numbers were affected).

Guard: run the same future TWICE in one process, once FIRST (clean state) and
once AFTER 9 other futures that exercise the same cache keys. Assert the two
runs are bit-identical. Run this after ANY edit to fleet_model/fig5_run or the
price/schaefer inputs, BEFORE the production chain.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\figures\Fig5')
import fig5_run as F
import pandas as pd
import fleet_model

fleet, pm = fleet_model.load_baseline_fleet()
F._init_worker(fleet, pm)
grid = [(w, g, r, t) for w in F.BAU_WEO for g in F.BAU_GROWTH
        for r in F.BAU_RETIRE.values() for t in F.BAU_TECH]

def run_one(i):
    w, g, r, t = grid[i]
    p = F.make_params(weo=w, growth=g, tc=t)
    p['retirement_scenario'] = int(r); p['forced_retirement_rate'] = 0.0
    res = F._rho_task((p, F.SEED_OFFSET + i, None))
    return res[3].groupby('Year')['GHG_tCO2e'].sum() / 1e6

CLEAN = run_one(8)                 # BAU_009 first (clean process state)
for i in [0, 1, 2, 3, 4, 5, 6, 7, 16]:   # same cache keys: STEPS C2024 tcs 1-3, R3
    run_one(i)
SECOND = run_one(8)                # BAU_009 again, AFTER other futures
d = (CLEAN - SECOND).abs().max()
print('BAU_009 clean vs after-others: max |diff| = %.6f Mt' % d)
if d > 1e-9:
    print('FAIL: order-dependent output — cache-key bug present. Abort the chain.')
    sys.exit(1)
print('PASS: deterministic across run orders (cache keys include all inputs).')
sys.exit(0)