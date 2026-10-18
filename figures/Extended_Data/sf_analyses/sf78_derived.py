# -*- coding: utf-8 -*-
"""
SF7/SF8/SF9 derived tables (code-generated, validated 2026-10-10):
  SF7_Fuel_Intensity  : E_adj min/median across fuels per WEO x year
                        (from Fig4_PanelE_Intensity.csv).
  SF7_Meco_Trajectory : Fig4 PanelC STEADY (2.4%/yr) E_req series.
  SF8_Effort_Ratio    : same steady C/F effort + ratio per gear x year.
  SF9_Creep_Robustness: per-creep medians (BAU 2050 median; per-object
                        Reduction_pct median for fuel/consolidation/quota/
                        final; final 2050 median Mt).
Sources: BAU_81_Annual, Mitigation_Results_Annual, Fig5_QuotaOnly_Annual,
         Fig5_Final_Combination_Annual, Fig4 panel CSVs. No simulations.
"""
import os, sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
ROOT = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission'
OUT = os.path.join(ROOT, 'scenario', 'output', 'fig5')
F5 = os.path.join(ROOT, 'figures', 'Fig5')
F4 = os.path.join(ROOT, 'figures', 'Fig4')

# ---------- SF7_Fuel_Intensity ----------
pe = pd.read_csv(os.path.join(F4, 'Fig4_PanelE_Intensity.csv'))
fi = pe.groupby(['WEO', 'Year']).Intensity_gCO2e_kWh.agg(['min', 'median']).reset_index()
fi.columns = ['WEO', 'Year', 'E_adj_min', 'E_adj_med']
fi.to_csv(os.path.join(OUT, 'SF7_Fuel_Intensity.csv'), index=False)
print('SF7_Fuel_Intensity written (%d)' % len(fi))

# ---------- SF7_Meco_Trajectory + SF8_Effort_Ratio (steady) ----------
pc = pd.read_csv(os.path.join(F4, 'Fig4_PanelC_Effort_Required.csv'))
st = pc[pc.Tech_Creep == 'steady'][['Year', 'Gear', 'Design', 'E_req']].copy()
st.to_csv(os.path.join(OUT, 'SF7_Meco_Trajectory.csv'), index=False)
piv = st.pivot_table(index='Year', columns=['Gear', 'Design'], values='E_req')
rows = []
for y, r in piv.iterrows():
    for gear in ['LL', 'PS']:
        c = float(r[(gear, 'C')]); f = float(r[(gear, 'F')])
        rows.append({'Year': y, 'Gear': gear, 'C': c, 'F': f,
                     'C_over_F': round(c / f, 2)})
pd.DataFrame(rows).to_csv(os.path.join(OUT, 'SF8_Effort_Ratio.csv'), index=False)
print('SF7_Meco_Trajectory + SF8_Effort_Ratio written')

# ---------- SF9_Creep_Robustness ----------
bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))
mit = pd.read_csv(os.path.join(OUT, 'Mitigation_Results_Annual.csv'))
quo = pd.read_csv(os.path.join(OUT, 'Fig5_QuotaOnly_Annual.csv'))
fin = pd.read_csv(os.path.join(OUT, 'Fig5_Final_Combination_Annual.csv'))
b50 = bau[bau.Year == 2050]
m50 = mit[mit.Year == 2050]
q50 = quo[quo.Year == 2050]
f50 = fin[fin.Year == 2050]
rows = []
for cr in sorted(bau.TechCreep.unique()):
    bb = b50[b50.TechCreep == cr]
    mm = m50[m50.TechCreep == cr]
    qq = q50[q50.TechCreep == cr]
    ff = f50[f50.TechCreep == cr]
    def med_pct(df, path):
        s = df[df.Mitigation_Pathway == path]
        return s.GHG_Reduction_pct.median() if len(s) else np.nan
    fuel = med_pct(mm, 'Fuel')
    cons = med_pct(mm, 'Consolidation')
    qr = qq.Reduction_pct.median() if len(qq) else np.nan
    fr = ff.Reduction_pct.median() if len(ff) else np.nan
    quotalast = qq.GHG_QuotaOnly.median() if len(qq) else np.nan
    rows.append({'TechCreep': cr, 'BAU2050_Mt': bb.GHG_Mt.median(),
                 'Fuel_red': fuel, 'Consol_red': cons, 'QuotaOnly_red': qr,
                 'Final_red': fr, 'Final_Mt': ff.GHG_Final.median(),
                 'Quota_gt_Fuel': bool(fuel < qr)})
sf9 = pd.DataFrame(rows)
sf9.to_csv(os.path.join(OUT, 'SF9_Creep_Robustness.csv'), index=False)
print('SF9_Creep_Robustness written')
print(sf9.round(3).to_string(index=False))

# ---------- validation ----------
print()
print('== validation ==')
def diff(name, vals):
    old = pd.read_csv(os.path.join(OUT, name))
    new = vals if name != 'SF9_Creep_Robustness.csv' else sf9
    if name == 'SF9_Creep_Robustness.csv':
        old['Quota_gt_Fuel'] = old.Quota_gt_Fuel.astype(bool)
    d = (new.select_dtypes('number') - old.select_dtypes('number')).abs().max().max()
    print('%-28s max diff %.3e' % (name, d))
fi_old = pd.read_csv(os.path.join(OUT, 'SF7_Fuel_Intensity.csv'))
d = (fi[['E_adj_min', 'E_adj_med']] - fi_old[['E_adj_min', 'E_adj_med']]).abs().max().max()
print('%-28s max diff %.3e' % ('SF7_Fuel_Intensity', d))