# -*- coding: utf-8 -*-
"""
Fig5_PanelD_Org_Summary.csv generator (documented method, 2026-10-10):
  - Input : scenario/output/fig5/Heterogeneous_Mitigation_Results.csv
  - Method: per Organization x pathway, MEDIAN of the object-level Reduction_pct
            restricted to each config's WEO-bound mitigation level
            (STEPS -> Low, APS -> Medium, NZE -> High).
  - Output: figures/Fig5/Fig5_PanelD_Org_Summary.csv
Runtime < 30 s. Deterministic.
"""
from pathlib import Path
import os, sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import pandas as pd
ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0,os.path.join(ROOT,'scenario'))
from scenario_seeds import require_seed_protocol
require_seed_protocol(os.path.join(ROOT,'scenario','output','fig5'),['Heterogeneous_Mitigation_Results.csv'])
he = pd.read_csv(os.path.join(ROOT, 'scenario', 'output', 'fig5', 'Heterogeneous_Mitigation_Results.csv'))
bound = {'STEPS': 'Low', 'APS': 'Medium', 'NZE': 'High'}
he['bound'] = he.WEO.map(bound)
sub = he[(he.Mitigation_Level == he.bound) | he.Mitigation_Level.isna()]
COLS = {
    'Fuel_pct': ['Fuel'],
    'Fuel+Refrigerant_pct': ['Fuel+Refrigerant'],
    'Fuel+Refrigerant+Consolidation_pct': ['Fuel+Refrigerant+Consolidation'],
    'Refrigerant_pct': ['Refrigerant'],
    'Consolidation_pct': ['Consolidation'],
}
rows = []
for org, g in sub.groupby('Organization'):
    r = {'Organization': org}
    for col, paths in COLS.items():
        s = g[g.Mitigation_Pathway.isin(paths)]
        r[col] = round(s.Reduction_pct.median(), 2)
    rows.append(r)
df = pd.DataFrame(rows).set_index('Organization')[list(COLS)]
df = df[['Fuel_pct', 'Fuel+Refrigerant_pct', 'Fuel+Refrigerant+Consolidation_pct',
         'Refrigerant_pct', 'Consolidation_pct']]
out = os.path.join(ROOT, 'figures', 'Fig5', 'Fig5_PanelD_Org_Summary.csv')
df.to_csv(out)
print(df.round(2).to_string())
print('written to', out)
print()
old = pd.read_csv(os.path.join(ROOT, 'figures', 'Fig5', '_bak_Org_Summary_0923.csv')) if os.path.exists(
    os.path.join(ROOT, 'figures', 'Fig5', '_bak_Org_Summary_0923.csv')) else None
if old is not None:
    old = old.set_index('Organization')
    print('vs 9/23 snapshot (diff):')
    print((df - old).round(2).to_string())