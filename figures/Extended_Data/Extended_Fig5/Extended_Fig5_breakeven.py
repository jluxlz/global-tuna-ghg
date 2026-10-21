# -*- coding: utf-8 -*-
"""Extended Data Fig. 11 data: ED11_BreakEven_Cutoff (all fleet_model-model components).

Meco_C(t,tc) = Σ_s  share_s(2024, all fleet) × quota_ratio_s(t) / biomass_ratio_s(t)
               / (1+tc)^max(t−2025,0)          [fleet_model Meco formula]
  - share_s(2024) : all-fleet species shares, built from fleet_model.compute_gear_catch_weights
                    (PS+LL gear weights combined by each gear's 2024 catch)
  - quota/biomass : C2024 (fixed-2024-catch) scenario rows of
                    scenario/output/schaefer_biomass_annual.csv (jabba output)
  - tc             : per-future technology-creep rate (fleet_model chain parameter)

Effort-cap variants (1.5x / 2.0x) apply where Meco_C exceeds the cap:
E = E_BAU × min(1, cap / Meco_C).
"""
import os, sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'GHG_Calculation'))   # keep BEFORE scenario so the
sys.path.insert(0, os.path.join(ROOT, 'scenario'))          # canonical scenario/fleet_model wins
import fleet_model
OUT = os.path.join(ROOT, 'scenario', 'output', 'fig5')
SP = ['SKJ', 'YFT', 'BET', 'ALB', 'SBT']

bau = pd.read_csv(os.path.join(OUT, 'BAU_81_Annual.csv'))
quo = pd.read_csv(os.path.join(OUT, 'Fig5_QuotaOnly_Annual.csv'))
sch = pd.read_csv(os.path.join(ROOT, 'scenario', 'output', 'schaefer_biomass_annual.csv'))
s24 = sch[sch.Scenario == 'C2024']

# ---- all-fleet 2024 species shares via the fleet_model model's gear weights ----
gw = fleet_model.compute_gear_catch_weights(ref_year=2024)          # per-gear shares
b3 = fleet_model.get_base3() if hasattr(fleet_model, 'get_base3') else None
if b3 is None:
    b3 = pd.read_csv(os.path.join(ROOT, 'GHG_Calculation', 'Base_3_Spatial_Grid_Enriched.csv'),
                     usecols=['Gear', 'Year'] + [s + '_Tonnes' for s in SP])
b24 = b3[b3.Year == 2024]
gear_tot = {g: b24.loc[b24.Gear == g, [s + '_Tonnes' for s in SP]].sum().sum() for g in ['PS', 'LL']}
gsum = sum(gear_tot.values())
share = {s: sum(gw[g][s] * gear_tot[g] for g in ['PS', 'LL']) / gsum for s in SP}
print('all-fleet 2024 shares:', {s: round(v, 4) for s, v in share.items()})

# ---- Meco_C per (tech_creep, year) ----
rows_mc = []
for cr in sorted(bau.TechCreep.unique()):
    for y in range(int(bau.Year.min()), int(bau.Year.max()) + 1):
        sub = s24[s24.Year == y].set_index('Stock')
        vals = [share[s] * sub.loc[s, 'quota_ratio'] / sub.loc[s, 'biomass_ratio'] /
                (1.0 + cr) ** max(y - 2025, 0) for s in SP]
        rows_mc.append({'TechCreep': cr, 'Year': y, 'Meco_C': float(np.sum(vals))})
mc = pd.DataFrame(rows_mc)

b = bau.merge(mc, on=['TechCreep', 'Year'], how='left').merge(quo[['BAU_ID', 'Year', 'GHG_QuotaOnly']], on=['BAU_ID', 'Year'], how='left')
for cap, col in [(1.5, 'E_BAU_cap1_5'), (2.0, 'E_BAU_cap2_0')]:
    mult = np.minimum(1.0, cap / b.Meco_C.fillna(np.inf))
    b[col] = b.GHG_Mt * mult
b['E_BAU'] = b.GHG_Mt
b['E_QuotaOnly'] = b.GHG_QuotaOnly
b[['BAU_ID', 'WEO', 'Growth', 'Retirement', 'TechCreep', 'Year', 'Meco_C',
   'E_BAU', 'E_BAU_cap1_5', 'E_BAU_cap2_0', 'E_QuotaOnly']].to_csv(
    os.path.join(OUT, 'ED11_BreakEven_Cutoff.csv'), index=False)
print('ED11_BreakEven_Cutoff written (%d rows)' % len(b))

# ---- validation vs canonical 9/30 series ----
assert not b.duplicated(['BAU_ID','Year']).any()
assert np.isfinite(b[['Meco_C','E_BAU','E_QuotaOnly']]).all().all()
v = b[b.Year == 2050]
print('2050 caps below Quota: cap1_5 %d/81, cap2_0 %d/81' % (
    (v.E_BAU_cap1_5 < v.E_QuotaOnly).sum(), (v.E_BAU_cap2_0 < v.E_QuotaOnly).sum()))
