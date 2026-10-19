# -*- coding: utf-8 -*-
"""
SF7: Decompose the projected BAU emission increase (2025 -> 2050).
Method (documented): sequential counterfactual fixing to the central grid
levels (APS / Medium growth / Natural retirement / Steady creep). The grand
mean increase is split into factor contributions + interaction residual.
Sources: BAU_81_Annual.csv only (no new sims).
Outputs: SF7_Increase_Decomposition.csv, SF7_WEO_dE.csv, SF7_Meco_Trajectory.csv
"""
from pathlib import Path
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import numpy as np, pandas as pd

ROOT = str(Path(__file__).resolve().parents[3])
OUT = os.path.join(ROOT, 'scenario', 'output', 'fig5')

bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))
piv = bau.pivot_table(index='BAU_ID', columns='Year', values='GHG_Mt')
dE = (piv[2050] - piv[2025]).rename('dE').reset_index()
meta = bau[['BAU_ID', 'WEO', 'Growth', 'Retirement', 'TechCreep']].drop_duplicates()
d = dE.merge(meta, on='BAU_ID')

CENTRAL = {'WEO': 'APS', 'Growth': 0.0136, 'Retirement': 'Natural', 'TechCreep': 0.024}
grand = d.dE.mean()

# sequential counterfactual (single documented order: WEO -> Growth -> Retirement -> Creep)
rows = []
cur = d
prev = grand
for f, lv in CENTRAL.items():
    cur = cur[cur[f] == lv] if len(rows) == 0 else cur[cur[f] == lv]
    m = cur.dE.mean()
    rows.append({'Factor': f, 'fix_to': lv, 'contribution_Mt': prev - m})
    prev = m
rows.append({'Factor': 'residual (central future)', 'fix_to': '-', 'contribution_Mt': prev})
dec = pd.DataFrame(rows)
print('SF7 grand mean 2025->2050 increase: %.1f Mt' % grand)
print(dec.round(1).to_string(index=False))
dec.to_csv(os.path.join(OUT, 'SF7_Increase_Decomposition.csv'), index=False)

# WEO medians of the increase and of 2050
w = d.groupby('WEO').agg(
    dE_median=('dE', 'median'),
    dE_p5=('dE', lambda x: x.quantile(.05)),
    dE_p95=('dE', lambda x: x.quantile(.95)),
    E2050_median=('dE', 'size')).reset_index()
w2 = bau[bau.Year == 2050].groupby('WEO').GHG_Mt.median().rename('BAU2050_Mt').reset_index()
w = w.merge(w2, on='WEO')
print(); print('SF7 WEO summary:'); print(w.round(1).to_string(index=False))
w.to_csv(os.path.join(OUT, 'SF7_WEO_dE.csv'), index=False)

# stock-driven effort (Meco) trajectory from the Schaefer paths (C-type fixed catch)
sch = pd.read_csv(os.path.join(ROOT, 'scenario', 'output', 'schaefer_biomass_annual.csv'))
print(); print('schaefer cols:', list(sch.columns)[:8])
