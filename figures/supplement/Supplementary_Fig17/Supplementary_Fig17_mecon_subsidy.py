# -*- coding: utf-8 -*-
"""Extended Data Fig. 8 data: ED10_Mecon_Series + ED10_Subsidy_Buffer.
Mecon = chained M_econ per WEO x year (region-mean, rebased 2023) with
carbon-halved ('sb0_5') and price-insulated ('sb1_0') variants plus the
subsidy/base ratios (r columns); Subsidy_Buffer scales BAU/Quota annual
emissions by those ratios."""
import os, sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'GHG_Calculation'))
sys.path.insert(0, os.path.join(ROOT, 'scenario'))
import fleet_model
import price_loader as pl
OUT = os.path.join(ROOT, 'scenario', 'output', 'fig5')

cr = pd.read_excel(pl.PRICE_MATRIX_PATH, sheet_name="Carbon_Reference")
years = list(range(2023, 2051))
LHV = pl.get_fuel_lhv("MGO")
CF = pl.get_fuel_ef_co2("MGO")
rows = []
for weo in ['STEPS', 'APS', 'NZE']:
    regions = sorted(cr.loc[cr.Scenario.eq(weo), 'WEO_Region'].dropna().unique())
    base_regions, half_regions = [], []
    for region in regions:
        p0, c0 = pl.get_fuel_price("MGO", weo, 2023, region, "mid")
        reference = (p0 + c0*CF)/1000/LHV
        assert reference > 0
        base, half = [], []
        for year in years:
            p, c = pl.get_fuel_price("MGO", weo, year, region, "mid")
            base.append(((p+c*CF)/1000/LHV/reference)**(-.3))
            half.append(((p+.5*c*CF)/1000/LHV/reference)**(-.3))
        base_regions.append(base); half_regions.append(half)
    base = np.mean(base_regions, axis=0)
    half = np.mean(half_regions, axis=0)
    assert np.isclose(base[0], 1.)
    for i, year in enumerate(years):
        rows.append(dict(WEO=weo, Year=year, base=float(base[i]), sb0_5=float(half[i]),
                         sb1_0=1., r0_5=float(half[i]/base[i]), r1_0=float(1./base[i])))
me = pd.DataFrame(rows)
me.to_csv(os.path.join(OUT, 'ED10_Mecon_Series.csv'), index=False)
me2 = me[['WEO', 'Year']].copy()
me2['r0'] = me.sb0_5 / me.base
me2['r1'] = 1.0 / me.base

bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))
quo = pd.read_csv(os.path.join(OUT, 'Fig5_QuotaOnly_Annual.csv'))
b = bau.merge(quo[['BAU_ID', 'Year', 'GHG_QuotaOnly']], on=['BAU_ID', 'Year'], how='left')
b = b.merge(me2, on=['WEO', 'Year'])
b['E_BAU'] = b.GHG_Mt
b['E_Quota'] = b.GHG_QuotaOnly
for col, r in [('E_BAU_sb0_5', 'r0'), ('E_Quota_sb0_5', 'r0'), ('E_BAU_sb1_0', 'r1'), ('E_Quota_sb1_0', 'r1')]:
    b[col] = b.E_BAU * b[r] if col.startswith('E_BAU') else b.E_Quota * b[r]
b[['BAU_ID', 'WEO', 'Year', 'E_BAU', 'E_Quota', 'E_BAU_sb0_5', 'E_Quota_sb0_5',
   'E_BAU_sb1_0', 'E_Quota_sb1_0']].to_csv(os.path.join(OUT, 'ED10_Subsidy_Buffer.csv'), index=False)
print('ED10_Mecon_Series + ED10_Subsidy_Buffer written')