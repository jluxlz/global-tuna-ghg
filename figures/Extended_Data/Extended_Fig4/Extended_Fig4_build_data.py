# -*- coding: utf-8 -*-
"""Build the ED4 panel data CSVs (decomposition of grid-attributed emission
growth, ANNUAL Mt yr-1 basis). OUTPUT: figures/Extended_Data/Extended_Fig4/
Panel A: era totals (per-year); B: common/entered/left decomposition per
transition (per-year); C: common-cell drivers (full grid vs sufficient-data
sample); D: weighted CEI per era, all cells and each gear."""
import sys, os, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
OUT = HERE

g = pd.read_csv(os.path.join(R, 'GHG_Calculation', 'Base_3_Spatial_Grid_Enriched.csv'))
g = g[(g.Year >= 1970) & (g.Total_Catch > 0) & (g.GHG_emissions_median > 0)]
g['Era'] = pd.cut(g.Year, bins=[1969, 1990, 2005, 2025], labels=['E1', 'E2', 'E3']).astype(str)
# Match Fig2's 5-degree cell centres before defining footprint identities.
# Native RFMO tables contain several grid resolutions; raw lon/lat keys
# cannot be described as a common 5-degree footprint.
g['lon'] = np.floor(g.lon / 5.0) * 5.0 + 2.5
g['lat'] = np.floor(g.lat / 5.0) * 5.0 + 2.5
g['key'] = g.Gear.astype(str) + '_' + g.lon.astype(str) + '_' + g.lat.astype(str)

# ---- Panel A: annualised era totals ----
rows_a = []
for era in ['E1', 'E2', 'E3']:
    sub = g[g.Era == era]
    ny = sub.Year.nunique()
    rows_a.append(dict(Era=era, Years=ny, Cells=sub.key.nunique(),
                       GHG_Mt_yr=sub.GHG_emissions_median.sum() / 1e6 / ny,
                       Catch_Mt_yr=sub.Total_Catch.sum() / 1e6 / ny,
                       CEI=sub.GHG_emissions_median.sum() / sub.Total_Catch.sum()))
pd.DataFrame(rows_a).to_csv(os.path.join(OUT, 'ED4_PanelA_EraTotals.csv'), index=False)

# ---- Panel B: annualised decomposition (per-year shares) ----
rows_b = []
for a, b in [('E1', 'E2'), ('E2', 'E3')]:
    ga = g[g.Era == a]; gb = g[g.Era == b]
    ka, kb = set(ga.key.unique()), set(gb.key.unique())
    ya, yb = ga.Year.nunique(), gb.Year.nunique()
    dE = gb.GHG_emissions_median.sum() / yb - ga.GHG_emissions_median.sum() / ya
    com = gb[gb.key.isin(ka)].GHG_emissions_median.sum() / yb - ga[ga.key.isin(kb)].GHG_emissions_median.sum() / ya
    ent = gb[~gb.key.isin(ka)].GHG_emissions_median.sum() / yb
    lft = ga[~ga.key.isin(kb)].GHG_emissions_median.sum() / ya
    rows_b.append(dict(Transition='%s-%s' % (a, b), Years_prev=ya, Years_next=yb,
                       GHG_delta_Mt_yr=dE / 1e6, Common_Mt_yr=com / 1e6,
                       Entered_Mt_yr=ent / 1e6, Left_Mt_yr=-lft / 1e6,
                       Common_pct=100 * com / dE if dE != 0 else np.nan,
                       Entered_pct=100 * ent / dE if dE != 0 else np.nan,
                       Left_pct=-100 * lft / dE if dE != 0 else np.nan,
                       Cells_prev=len(ka), Cells_next=len(kb)))
pd.DataFrame(rows_b).to_csv(os.path.join(OUT, 'ED4_PanelB_Decomposition.csv'), index=False)

# ---- Panel C: common-cell drivers (full grid vs sample) ----
ag = g.groupby(['Era', 'key']).agg(Catch=('Total_Catch', 'sum'), GHG=('GHG_emissions_median', 'sum')).reset_index()
# Use the same annualised basis as panels a/b despite unequal era duration.
years_per_era = g.groupby('Era').Year.nunique()
ag['Catch'] /= ag.Era.map(years_per_era)
ag['GHG'] /= ag.Era.map(years_per_era)
def common_decomp(keys_filter=None):
    out = []
    for a, b in [('E1', 'E2'), ('E2', 'E3')]:
        ga = ag[ag.Era == a]; gb = ag[ag.Era == b]
        if keys_filter is not None:
            ga = ga[ga.key.isin(keys_filter)]; gb = gb[gb.key.isin(keys_filter)]
        m = ga.merge(gb, on='key', suffixes=('_1', '_2'))
        C1, C2 = m.Catch_1, m.Catch_2
        G1, G2 = m.GHG_1, m.GHG_2
        CEI1, CEI2 = G1 / C1, G2 / C2
        dE = (G2 - G1).sum()
        # Exact additive log-mean decomposition. Avoid extrapolating the
        # first era's tiny-catch CEI over the second era's entire catch base.
        # Positive catch and emissions are enforced upstream.
        log_delta = np.log(G2) - np.log(G1)
        same = np.abs(log_delta) < 1e-10
        weights = np.empty(len(m))
        weights[same] = (G1[same] + G2[same]) / 2
        weights[~same] = (G2[~same] - G1[~same]) / log_delta[~same]
        effC = (weights * np.log(C2 / C1)).sum()
        effI = (weights * np.log(CEI2 / CEI1)).sum()
        effX = 0.0  # no residual or interaction under the log-mean identity
        assert np.isclose(effC + effI + effX, dE, rtol=1e-10, atol=1e-6)
        out.append(dict(Transition='%s-%s' % (a, b), n_cells=len(m), dE_Mt=dE / 1e6,
                        Catch_effect_Mt=effC / 1e6, Intensity_effect_Mt=effI / 1e6,
                        Interaction_Mt=effX / 1e6, Method='additive log-mean (LMDI)', Catch_effect_pct=100 * effC / dE,
                        Intensity_effect_pct=100 * effI / dE, Interaction_pct=100 * effX / dE))
    return pd.DataFrame(out)
full = common_decomp(None)
full['View'] = 'Full grid'
sm = pd.read_csv(os.path.join(R, 'figures', 'Fig2', 'Fig2_PanelBC_Grid_Slopes.csv'))
keys = set((sm.Gear.astype(str) + '_' + sm.lon.astype(str) + '_' + sm.lat.astype(str)))
samp = common_decomp(keys)
samp['View'] = 'Sufficient-data sample'
pd.concat([full, samp]).to_csv(os.path.join(OUT, 'ED4_PanelC_Drivers.csv'), index=False)

# Retain the former full/eligible comparison as supplementary source data.
rows_d = []
for era in ['E1', 'E2', 'E3']:
    sub = ag[ag.Era == era]
    rows_d.append(dict(Era=era, View='Full grid', CEI=sub.GHG.sum() / sub.Catch.sum()))
    ss = sub[sub.key.isin(keys)]
    rows_d.append(dict(Era=era, View='Sufficient-data sample', CEI=ss.GHG.sum() / ss.Catch.sum()))
pd.DataFrame(rows_d).to_csv(os.path.join(OUT, 'ED4_PanelD_CEI_Sample_Comparison.csv'), index=False)
# ---- Panel D: identical ratio-of-totals accounting, pooled and by gear ----
rows_d = []
for era in ['E1', 'E2', 'E3']:
    all_cells = g[g.Era == era]
    for label, subset in [('Full grid', all_cells),
                          ('LL grid', all_cells[all_cells.Gear == 'LL']),
                          ('PS grid', all_cells[all_cells.Gear == 'PS'])]:
        catch = subset.Total_Catch.sum()
        ghg = subset.GHG_emissions_median.sum()
        rows_d.append(dict(Era=era, View=label, CEI=ghg/catch,
                           Catch_t=catch, GHG_t=ghg,
                           Catch_share=catch/all_cells.Total_Catch.sum(),
                           Grid_gear_cells=subset.key.nunique()))
panel_d = pd.DataFrame(rows_d)
for era, sub in panel_d.groupby('Era'):
    pooled = sub[sub.View == 'Full grid'].iloc[0]
    gears = sub[sub.View != 'Full grid']
    assert np.isclose(gears.Catch_t.sum(), pooled.Catch_t)
    assert np.isclose(gears.GHG_t.sum(), pooled.GHG_t)
    assert np.isclose((gears.CEI*gears.Catch_share).sum(), pooled.CEI)
panel_d.to_csv(os.path.join(OUT, 'ED4_PanelD_CEI_Views.csv'), index=False)
# Preserve the gear composition behind the pooled ratio. A falling pooled CEI
# can coexist with increasing LL CEI and positive within-cell LMDI effects.
context = g.groupby(['Era', 'Gear']).agg(
    Catch_t=('Total_Catch', 'sum'), GHG_t=('GHG_emissions_median', 'sum')).reset_index()
context['CEI'] = context.GHG_t / context.Catch_t
context['Catch_share'] = context.Catch_t / context.groupby('Era').Catch_t.transform('sum')
context.to_csv(os.path.join(OUT, 'ED4_PanelD_Gear_Context.csv'), index=False)
print('ED4 panels written to', OUT)
