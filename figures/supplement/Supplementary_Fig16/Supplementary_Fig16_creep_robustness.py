# -*- coding: utf-8 -*-
"""Extended Data Fig. 5 data: SF9_Creep_Robustness (per-creep medians:
BAU 2050 median; per-object Reduction_pct median for fuel/consolidation/
quota/final; final 2050 median Mt)."""
import os, sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
OUT = os.path.join(ROOT, 'scenario', 'output', 'fig5')

bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))
mit = pd.read_csv(os.path.join(OUT, 'Mitigation_Results_Annual.csv'))
quo = pd.read_csv(os.path.join(OUT, 'Fig5_QuotaOnly_Annual.csv'))
fin = pd.read_csv(os.path.join(OUT, 'Fig5_Final_Combination_Annual.csv'))
b50 = bau[bau.Year == 2050]
m50 = mit[mit.Year == 2050]
q50 = quo[quo.Year == 2050]
f50 = fin[fin.Year == 2050]

def med_pct(df, path):
    s = df[df.Mitigation_Pathway == path]
    return s.GHG_Reduction_pct.median() if len(s) else np.nan

rows = []
for cr in sorted(bau.TechCreep.unique()):
    bb = b50[b50.TechCreep == cr]
    mm = m50[m50.TechCreep == cr]
    qq = q50[q50.TechCreep == cr]
    ff = f50[f50.TechCreep == cr]
    fuel = med_pct(mm, 'Fuel')
    cons = med_pct(mm, 'Consolidation')
    qr = qq.Reduction_pct.median() if len(qq) else np.nan
    fr = ff.Reduction_pct.median() if len(ff) else np.nan
    rows.append({'TechCreep': cr, 'BAU2050_Mt': bb.GHG_Mt.median(),
                 'Fuel_red': fuel, 'Consol_red': cons, 'QuotaOnly_red': qr,
                 'Final_red': fr, 'Final_Mt': ff.GHG_Final.median(),
                 'Quota_gt_Fuel': bool(fuel < qr)})
sf9 = pd.DataFrame(rows)
sf9.to_csv(os.path.join(OUT, 'SF9_Creep_Robustness.csv'), index=False)
print(sf9.round(3).to_string(index=False))