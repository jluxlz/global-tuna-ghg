# -*- coding: utf-8 -*-
"""
SF5 (step 2): economic-elasticity sensitivity by POST-PROCESSING.
  * BAU / quota arms scale with the BAU-arm M_econ path per WEO
  * fuel arm scales with the fuel-arm M_econ path per WEO
  * verification: linear-scaling check against the captured beta=-0.7 runs
Outputs: SF5_PanelA_Multiplier.csv, SF5_PanelB_Abatement.csv,
         SF5_PanelC_Rebound.csv
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import numpy as np, pandas as pd

OUT = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\scenario\output\fig5'
BETAS = [0.0, -0.1, -0.3, -0.5, -0.7]
B0 = -0.3

paths = pd.read_csv(os.path.join(OUT, 'SF5_Multiplier_Paths.csv'))

# ---- verification: E_final ratio vs GHG ratio (beta -0.7 / -0.3, BAU arm) ----
print('== linear-scaling verification (BAU arm) ==')
for weo in ['STEPS', 'APS', 'NZE']:
    a = paths[(paths.WEO == weo) & (paths.Arm == 'BAU') & (paths.Beta == -0.3)].set_index('Year')
    b = paths[(paths.WEO == weo) & (paths.Arm == 'BAU') & (paths.Beta == -0.7)].set_index('Year')
    r_ef = (b.E_final / a.E_final)
    r_ghg = (b.Total_GHG_tCO2e / a.Total_GHG_tCO2e)
    if r_ghg.notna().all():
        dev = float(np.nanmax(np.abs(r_ghg - r_ef)))
        print('  %-6s max |GHG ratio - E_final ratio| = %.3f (2050 GHG ratio %.3f, E ratio %.3f)' % (
            weo, dev, r_ghg.loc[2050], r_ef.loc[2050]))
    else:
        print('  %-6s GHG columns missing; E_final ratio 2050 = %.3f' % (weo, r_ef.loc[2050]))

# ---- build scaled curves ----
bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))           # GHG_Mt
mit = pd.read_csv(os.path.join(OUT, 'Mitigation_Results_Annual.csv'))
q = pd.read_csv(os.path.join(OUT, 'Fig5_QuotaOnly_Annual.csv'))
mit_fuel = mit[mit.Mitigation_Pathway == 'Fuel'][['BAU_ID', 'Year', 'GHG_Mitigation']].rename(columns={'GHG_Mitigation': 'GHG_Fuel'})
q = q[['BAU_ID', 'Year', 'GHG_QuotaOnly']]

def mecon_ratio(arm, weo, beta):
    # M_econ(beta) = CR^beta; recover CR from the beta0 path: CR = M0^(1/B0)
    a = paths[(paths.WEO == weo) & (paths.Arm == arm) & (paths.Beta == B0)].set_index('Year')['M_econ']
    if beta == B0:
        return pd.Series(1.0, index=a.index)
    return (a ** (beta / B0)) / a

panelA, panelB, panelC = [], [], []
for beta in BETAS:
    bau_s = bau.copy()
    bau_s['f'] = bau_s.apply(lambda r: mecon_ratio('BAU', r.WEO, beta).get(r.Year, 1.0), axis=1)
    bau_s['GHG_s'] = bau_s.GHG_Mt * bau_s.f
    bau50 = bau_s[bau_s.Year == 2050][['BAU_ID', 'GHG_Mt', 'GHG_s']].rename(columns={'GHG_s': 'BAU_s'})

    ml = mit_fuel.merge(bau, on=['BAU_ID', 'Year'])[['BAU_ID', 'WEO', 'Year', 'GHG_Fuel']]
    ml['f'] = ml.apply(lambda r: mecon_ratio('fuel', r.WEO, beta).get(r.Year, 1.0), axis=1)
    ml['Fuel_s'] = ml.GHG_Fuel * ml.f
    f50 = ml[ml.Year == 2050][['BAU_ID', 'Fuel_s']]

    qq = q.merge(bau, on=['BAU_ID', 'Year'])[['BAU_ID', 'WEO', 'Year', 'GHG_QuotaOnly']]
    qq['f'] = qq.apply(lambda r: mecon_ratio('BAU', r.WEO, beta).get(r.Year, 1.0), axis=1)
    qq['Q_s'] = qq.GHG_QuotaOnly * qq.f
    q50 = qq[qq.Year == 2050][['BAU_ID', 'Q_s']]

    m = bau50.merge(f50, on='BAU_ID').merge(q50, on='BAU_ID')
    m['Fuel_red'] = 100 * (1 - m.Fuel_s / m.BAU_s)
    m['Quota_red'] = 100 * (1 - m.Q_s / m.BAU_s)
    m['Beta'] = beta
    panelB.append(m)

    # panel A: 2050 M_econ by beta (both arms)
    for arm in ['BAU', 'fuel']:
        for weo in ['STEPS', 'APS', 'NZE']:
            r = mecon_ratio(arm, weo, beta).get(2050)
            a0 = paths[(paths.WEO == weo) & (paths.Arm == arm) & (paths.Beta == B0)].set_index('Year').loc[2050, 'M_econ']
            panelA.append({'Beta': beta, 'Arm': arm, 'WEO': weo, 'M_econ_2050': a0 * r})

    # panel C: rebound (fuel arm)
    st = ml.copy()
    st['f0'] = st.apply(lambda r: mecon_ratio('fuel', r.WEO, 0.0).get(r.Year, 1.0), axis=1)
    st['Fuel_static'] = st.GHG_Fuel * st.f0
    s50 = st[st.Year == 2050][['BAU_ID', 'Fuel_static', 'Fuel_s']]
    mm = bau50.merge(s50, on='BAU_ID')
    mm['Rebound'] = (mm.Fuel_s - mm.Fuel_static) / (mm.BAU_s - mm.Fuel_static)
    mm['Beta'] = beta
    panelC.append(mm[['BAU_ID', 'Beta', 'Rebound']])

pd.DataFrame(panelA).to_csv(os.path.join(OUT, 'SF5_PanelA_Multiplier.csv'), index=False)
pb = pd.concat(panelB, ignore_index=True)
pb.to_csv(os.path.join(OUT, 'SF5_PanelB_Abatement.csv'), index=False)
pc = pd.concat(panelC, ignore_index=True)
pc.to_csv(os.path.join(OUT, 'SF5_PanelC_Rebound.csv'), index=False)

print()
print('== Panel B medians (2050 reduction %%) ==')
summ = pb.groupby('Beta')[['Fuel_red', 'Quota_red']].median().round(1)
print(summ.to_string())
print()
print('== Panel C rebound medians ==')
print(pc.groupby('Beta').Rebound.median().round(3).to_string())
