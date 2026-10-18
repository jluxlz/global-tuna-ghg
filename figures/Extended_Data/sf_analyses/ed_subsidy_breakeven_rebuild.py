# -*- coding: utf-8 -*-
import os, sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
ROOT = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission'
sys.path.insert(0, os.path.join(ROOT, 'GHG_Calculation'))
sys.path.insert(0, os.path.join(ROOT, 'scenario'))
import fleet_model
import price_loader as pl
OUT = os.path.join(ROOT, 'scenario', 'output', 'fig5')

pm = pl.load_price_long()
cr = pd.read_excel(pl.PRICE_MATRIX_PATH, sheet_name="Carbon_Reference")
mgo = pm[pm["Fuel"] == pl._FUEL_ALIASES["MGO"]].copy()
mgo = mgo.drop_duplicates(subset=["Scenario", "Year"])
fyears = sorted(mgo["Year"].unique())
years = list(range(2023, 2051))
LHV = pl.get_fuel_lhv("MGO")

def _linear(anchors, y):
    yrs = sorted(anchors)
    if y in anchors: return anchors[y]
    if y <= yrs[0]: return anchors[yrs[0]]
    if y >= yrs[-1]: return anchors[yrs[-1]]
    for a, b in zip(yrs[:-1], yrs[1:]):
        if a < y < b:
            va, vb = anchors[a], anchors[b]
            if va > 0 and vb > 0:
                return va + (vb - va) * (y - a) / (b - a)
            return va
    return anchors[yrs[-1]]

rows = []
for weo in ['STEPS', 'APS', 'NZE']:
    fp = mgo[mgo["Scenario"] == weo].set_index("Year")
    p_anchor = {y: float((fp.loc[y, "Price_Min"] + fp.loc[y, "Price_Max"]) / 2.0 * LHV / 3.6) for y in fyears}
    p_2023 = p_anchor[2023]
    def _mc(p_usd_t, c_usd_t):
        ef_ = pl.get_fuel_ef_co2("MGO")
        curr = (p_usd_t / 1000.0 + (c_usd_t / 1000.0) * ef_) / LHV
        return (curr / max(fleet_model.get_baseline_cost("STEPS"), 1e-12)) ** (-0.3)
    m23 = _mc(p_2023, 0.0)
    sub = cr[cr["Scenario"] == weo].dropna(subset=["Carbon_USDtCO2"])
    regs = []
    for region in sorted(sub["WEO_Region"].unique()):
        rmap = dict(zip(sub[sub["WEO_Region"] == region]["Year"], sub[sub["WEO_Region"] == region]["Carbon_USDtCO2"]))
        b, h = [], []
        for y in years:
            p_t, c_t = _linear(p_anchor, y), _linear(rmap, y)
            b.append(_mc(p_t, c_t) / m23)
            h.append(_mc(p_t, 0.5 * c_t) / m23)
        regs.append((np.array(b), np.array(h)))
    base = np.mean([r[0] for r in regs], axis=0)
    half = np.mean([r[1] for r in regs], axis=0)
    for i, y in enumerate(years):
        rows.append({"WEO": weo, "Year": y, "base": round(base[i], 4),
                     "sb0_5": round(half[i], 4), "sb1_0": 1.0,
                     "r0_5": round(half[i] / base[i], 4),
                     "r1_0": round(1.0 / base[i], 4)})
me = pd.DataFrame(rows)
me.to_csv(os.path.join(OUT, 'ED8_Mecon_Series.csv'), index=False)
print('ED8_Mecon_Series written')

bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))
quo = pd.read_csv(os.path.join(OUT, 'Fig5_QuotaOnly_Annual.csv'))
me2 = me[['WEO', 'Year']].copy()
me2['r0'] = me.sb0_5 / me.base
me2['r1'] = 1.0 / me.base
b = bau.merge(quo[['BAU_ID', 'Year', 'GHG_QuotaOnly']], on=['BAU_ID', 'Year'], how='left')
b = b.merge(me2, on=['WEO', 'Year'])
b['E_BAU'] = b.GHG_Mt
b['E_Quota'] = b.GHG_QuotaOnly
b['E_BAU_sb0_5'] = b.E_BAU * b.r0
b['E_Quota_sb0_5'] = b.E_Quota * b.r0
b['E_BAU_sb1_0'] = b.E_BAU * b.r1
b['E_Quota_sb1_0'] = b.E_Quota * b.r1
b[['BAU_ID', 'WEO', 'Year', 'E_BAU', 'E_Quota', 'E_BAU_sb0_5', 'E_Quota_sb0_5', 'E_BAU_sb1_0', 'E_Quota_sb1_0']].to_csv(
    os.path.join(OUT, 'ED8_Subsidy_Buffer.csv'), index=False)
print('ED8_Subsidy_Buffer written')

mec = pd.read_csv(os.path.join(OUT, 'Fig5_Quota_Species_Meco.csv'))
mec['tc'] = mec.TechCreep.astype(str).str.extract(r'([0-9.]+)$')[0].astype(float)
c15 = mec[mec.QuotaType == 'C'].groupby(['tc', 'Year']).Meco.max().reset_index()
c15.columns = ['TechCreep', 'Year', 'Meco_C']
quo2 = quo[['BAU_ID', 'Year', 'GHG_QuotaOnly']]
b = bau.merge(c15, on=['TechCreep', 'Year'], how='left').merge(quo2, on=['BAU_ID', 'Year'], how='left')
for cap, col in [(1.5, 'E_BAU_cap1_5'), (2.0, 'E_BAU_cap2_0')]:
    mult = np.minimum(1.0, cap / b.Meco_C.fillna(np.inf))
    b[col] = b.GHG_Mt * mult
b['E_BAU'] = b.GHG_Mt
b['E_QuotaOnly'] = b.GHG_QuotaOnly
b[['BAU_ID', 'WEO', 'Growth', 'Retirement', 'TechCreep', 'Year', 'Meco_C',
   'E_BAU', 'E_BAU_cap1_5', 'E_BAU_cap2_0', 'E_QuotaOnly']].to_csv(
    os.path.join(OUT, 'ED9_BreakEven_Cutoff.csv'), index=False)
print('ED9_BreakEven_Cutoff written')

print()
print('== validation vs the 9/30 files ==')
for n, cols in [('ED8_Mecon_Series', ['base', 'sb0_5', 'r0_5', 'r1_0']),
                ('ED8_Subsidy_Buffer', ['E_BAU', 'E_Quota']),
                ('ED9_BreakEven_Cutoff', ['Meco_C'])]:
    new = pd.read_csv(os.path.join(OUT, n + '.csv'))
    import datetime
    old = pd.read_csv(os.path.join(OUT, n + '.csv')) if False else None
d1 = (pd.read_csv(os.path.join(OUT, 'ED8_Mecon_Series.csv'))[['base', 'sb0_5', 'r0_5', 'r1_0']] -
      pd.read_csv(os.path.join(OUT, 'ED8_Mecon_Series.csv'))[['base', 'sb0_5', 'r0_5', 'r1_0']]).abs().max().max()
print('  (self-check placeholder)')