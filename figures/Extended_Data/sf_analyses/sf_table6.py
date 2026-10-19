# -*- coding: utf-8 -*-
"""
Supplementary Table 6: robustness matrix for the central conclusion.
Combines SF5 (elasticity), SF9 (creep), and by-dimension splits of the
existing chain data (WEO / growth / retirement / refrigerant / quota rule).
Output: Supplementary_Table6_Robustness_Matrix.csv (scenario/output/fig5)
"""
from pathlib import Path
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import pandas as pd, numpy as np

OUT = str(Path(__file__).resolve().parents[3] / 'scenario/output/fig5')
bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))
mit = pd.read_csv(os.path.join(OUT, 'Mitigation_Results_Annual.csv'))
q = pd.read_csv(os.path.join(OUT, 'Fig5_QuotaOnly_Annual.csv'))
f = pd.read_csv(os.path.join(OUT, 'Fig5_Final_Combination_Annual.csv'))
sf5b = pd.read_csv(os.path.join(OUT, 'SF5_PanelB_Abatement.csv'))
sf9 = pd.read_csv(os.path.join(OUT, 'SF9_Creep_Robustness.csv'))

rows = []

def push(dim, level, bau50, quota_red, fuel_red, final_mt, note=""):
    rows.append({
        'Dimension': dim, 'Level': level,
        'BAU_2050_median_Mt': round(float(bau50), 1),
        'QuotaOnly_reduction_pct': round(float(quota_red), 1),
        'FuelOnly_reduction_pct': round(float(fuel_red), 1),
        'Final_2050_median_Mt': round(float(final_mt), 2),
        'Quota_gt_Fuel': bool(quota_red > fuel_red), 'Notes': note})

# by WEO
for w in ['STEPS', 'APS', 'NZE']:
    ids = set(bau[(bau.WEO == w)].BAU_ID)
    b50 = bau[(bau.Year == 2050) & (bau.WEO == w)].GHG_Mt.median()
    qr = q[(q.Year == 2050) & (q.BAU_ID.isin(ids))].Reduction_pct.median()
    fr = mit[(mit.Year == 2050) & (mit.BAU_ID.isin(ids)) & (mit.Mitigation_Pathway == 'Fuel')].GHG_Reduction_pct.median()
    fm = f[(f.Year == 2050) & (f.BAU_ID.isin(ids))].GHG_Final.median()
    push('WEO pathway', w, b50, qr, fr, fm)

# by growth
for g, name in [(0.0021, 'Low'), (0.0136, 'Medium'), (0.0272, 'High')]:
    ids = set(bau[np.isclose(bau.Growth, g)].BAU_ID)
    b50 = bau[(bau.Year == 2050) & np.isclose(bau.Growth, g)].GHG_Mt.median()
    qr = q[(q.Year == 2050) & (q.BAU_ID.isin(ids))].Reduction_pct.median()
    fr = mit[(mit.Year == 2050) & (mit.BAU_ID.isin(ids)) & (mit.Mitigation_Pathway == 'Fuel')].GHG_Reduction_pct.median()
    fm = f[(f.Year == 2050) & (f.BAU_ID.isin(ids))].GHG_Final.median()
    push('Fleet capacity growth', name, b50, qr, fr, fm)

# by retirement
for r in ['Natural', 'Renewal', 'Forced']:
    ids = set(bau[bau.Retirement == r].BAU_ID)
    b50 = bau[(bau.Year == 2050) & (bau.Retirement == r)].GHG_Mt.median()
    qr = q[(q.Year == 2050) & (q.BAU_ID.isin(ids))].Reduction_pct.median()
    fr = mit[(mit.Year == 2050) & (mit.BAU_ID.isin(ids)) & (mit.Mitigation_Pathway == 'Fuel')].GHG_Reduction_pct.median()
    fm = f[(f.Year == 2050) & (f.BAU_ID.isin(ids))].GHG_Final.median()
    push('Retirement regime', r, b50, qr, fr, fm)

# technology creep (from SF9)
for _, r in sf9.iterrows():
    push('Technology creep', '%.1f%%/yr' % (100 * r.TechCreep), r.BAU2050_Mt, r.QuotaOnly_red, r.Fuel_red, r.Final_Mt)

# economic elasticity (from SF5 panel b medians)
for beta in sorted(sf5b.Beta.unique()):
    s = sf5b[sf5b.Beta == beta]
    push('Economic effort elasticity', 'beta = %.1f' % beta,
         np.nan, s.Quota_red.median(), s.Fuel_red.median(), np.nan,
         'post-processed from captured multiplier paths')

# refrigerant leak rate / quota rule: qualitative from the design
push('Refrigerant leak rate', 'LN2 vs R22 (representative)', np.nan, np.nan, np.nan, np.nan,
     'LN2 arm neutral-to-negative in large RFMOs, +37% in CCSBT; does not affect the rule-vs-fuel ordering')
push('Quota rule', 'C (fixed catch) vs F (harvest rate)', np.nan, np.nan, np.nan, np.nan,
     'core mechanism: required effort rises under C, stable/declining under F (Fig. 4c; SF8)')

df = pd.DataFrame(rows)
p = os.path.join(OUT, 'Supplementary_Table6_Robustness_Matrix.csv')
df.to_csv(p, index=False)
print(df.to_string(index=False))
