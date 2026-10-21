#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rebuild Price_Long following user's methodology v2.0 — per-region support."""

import pandas as pd, numpy as np, os, shutil
from fuel_price_paths import inverse_carbon_multiplier

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS_PATH = os.path.join(ROOT, 'model_parameters', 'Scenario_Fuel_Parameters.xlsx')
MATRIX_PATH = os.path.join(ROOT, 'model_parameters', 'Scenario_Fuel_Price_Matrix.xlsx')
SCENARIOS = ['STEPS', 'APS', 'NZE']
YEARS = [2023, 2030, 2040, 2050]

# ============================================================
# 1. LOAD ALL DATA
# ============================================================
pf = pd.ExcelFile(PARAMS_PATH)

# --- Fuels ---
fp_raw = pd.read_excel(pf, sheet_name='Fuel_Parameters', header=None)
fuels = {}
for i in range(5, 19):
    row = fp_raw.iloc[i]
    try: seq = int(row.iloc[0])
    except: continue
    name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
    if not name or name == 'nan': continue
    lhv_raw = float(row.iloc[3]) if pd.notna(row.iloc[3]) else 0.0427
    lhv = lhv_raw * 1000 if lhv_raw < 1 else lhv_raw
    def _f(idx, d=None):
        try: v = row.iloc[idx]; return float(v) if pd.notna(v) else d
        except: return d
    fuels[seq] = dict(name=name, lhv=lhv, cur_min=_f(10), cur_max=_f(11),
                      p50_min=_f(12), p50_max=_f(13), cf_co2=_f(7,0.0), wtt=_f(4,0.0))

# --- WEO Fossil Prices ---
weo_f_raw = pd.read_excel(pf, sheet_name='WEO_Fossil_Prices', header=None)
fossil = {}
for i in range(4, len(weo_f_raw)):
    row = weo_f_raw.iloc[i]
    sc = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
    comm = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
    if not sc or sc == 'nan': continue
    fossil[(sc, comm)] = {}
    for j, yr in enumerate(YEARS):
        try: fossil[(sc, comm)][yr] = float(row.iloc[3+j])
        except: fossil[(sc, comm)][yr] = None

# --- Carbon prices: load ALL regions ---
cr = pd.read_excel(MATRIX_PATH, sheet_name='Carbon_Reference')

# Build carbon_data[scenario][region] = {year: price}
# Interpolate missing years (e.g. APS Other EMDE 2030=NaN → linear from 2035)
carbon_data = {}
APS_REF_C2030 = 135.0  # APS "Advanced economies" 2030 carbon = universal reference

for sc in SCENARIOS:
    carbon_data[sc] = {}
    sub = cr[cr['Scenario'] == sc]
    for region in sorted(sub['WEO_Region'].unique()):
        r_sub = sub[sub['WEO_Region'] == region]
        c = {2023: 0.0, 2030: np.nan, 2040: np.nan, 2050: np.nan}
        for _, row in r_sub.iterrows():
            yr = int(row['Year'])
            val = row['Carbon_USDtCO2']
            if yr in c and pd.notna(val):
                c[yr] = float(val)
        carbon_data[sc][region] = c

# Build mapping: STEPS/NZE region → corresponding APS carbon region
# Based on Flag_Region_Map majority vote
frm = pd.read_excel(MATRIX_PATH, sheet_name='Flag_Region_Map')
STEPS_TO_APS = {}
for steps_r in frm['Carbon_STEPS'].unique():
    aps_col = frm[frm['Carbon_STEPS'] == steps_r]['Carbon_APS_NZE'].mode()
    aps_short = aps_col.iloc[0] if len(aps_col) > 0 else 'Advanced'
    # Map short names → Carbon_Reference full names
    APS_FULL = {
        'Advanced':      'Advanced economies with net-zero pledges*',
        'Selected_EMDE': 'Selected EMDE with net-zero pledges**',
        'Other_EMDE':    'Other emerging market & developing economies',
    }
    STEPS_TO_APS[steps_r] = APS_FULL.get(aps_short, 'Advanced economies with net-zero pledges*')

# Carbon_Reference region names per scenario
CARBON_REGIONS = {}
for sc in SCENARIOS:
    CARBON_REGIONS[sc] = sorted(carbon_data[sc].keys())

print(f'Carbon regions: STEPS={len(CARBON_REGIONS["STEPS"])}, APS={len(CARBON_REGIONS["APS"])}, NZE={len(CARBON_REGIONS["NZE"])}')
print(f'  STEPS: {CARBON_REGIONS["STEPS"]}')
print(f'  APS:   {CARBON_REGIONS["APS"]}')
print(f'  NZE:   {CARBON_REGIONS["NZE"]}')

# ============================================================
# 2. CLASS A: Petroleum + Fossil LNG (commodity-indexed)
# ============================================================
A_PETRO = [1, 2, 3, 4, 5, 6, 11, 21]
A_GAS   = [31]

def compute_a(seq, scenario):
    f = fuels[seq]
    if f['cur_min'] is None: return None
    if seq in A_PETRO:
        ref_2023 = fossil[('STEPS', 'Crude oil (IEA)')][2023]
        target = fossil[(scenario, 'Crude oil (IEA)')]
    else:
        ref_2023 = fossil[('STEPS', 'Natural gas -- European Union')][2023]
        target = fossil[(scenario, 'Natural gas -- European Union')]
    if ref_2023 is None or ref_2023 == 0: return None
    result = {}
    for yr in YEARS:
        if yr == 2023:
            result[yr] = (f['cur_min'], f['cur_max'])
        else:
            tgt = target.get(yr, ref_2023)
            idx = tgt / ref_2023
            result[yr] = (f['cur_min'] * idx, f['cur_max'] * idx)
    return result

# ============================================================
# 3. CLASS B: Alternative fuels (per-region)
# ============================================================
B_SEQS = [33, 62, 77, 105, 121]
B_TARGET = [105, 121]       # have explicit 2050 Min/Max from IRENA
B_TRAJECTORY = [33, 62, 77]  # no 2050 data → carbon trajectory method

# Map STEPS region short names (from Flag_Region_Map) to Carbon_Reference full names
STEPS_SHORT_TO_FULL = {
    'European Union': 'European Union',
    'China':           'China',
    'Korea':           'Korea',
    'Canada':          'Canada',
    'ChileColombia':   'Chile & Colombia',
    'Advanced':        'European Union',  # JPN/TWN → use EU-equivalent carbon
}


def _period_rates_from_carbon(c):
    """Compute period fuel-price change rates from a region's carbon trajectory.
       PERIOD TOTAL rates (2026-09-07: linear path, not CAGR):
       r = V_end/V_start − 1 — applied LINEARLY between anchor nodes
       (2023→2030→2040→2050), so intermediate years follow a straight line.
       c = {2023: X, 2030: Y, 2040: Z, 2050: W}
       Rule: NaN or 0 → no carbon mechanism → no fuel price decline (r=0)."""
    def _is_valid(v):
        return v is not None and not (isinstance(v, float) and np.isnan(v)) and v > 0

    # P1: 2023→2030 (7yr). C_23 is always 0 → flat
    if _is_valid(c[2023]) and _is_valid(c[2030]):
        r1_c = c[2030] / c[2023] - 1
    else:
        r1_c = 0.0

    # P2: 2030→2040 (10yr)
    if _is_valid(c[2030]) and _is_valid(c[2040]):
        r2_c = c[2040] / c[2030] - 1
    else:
        r2_c = 0.0

    # P3: 2040→2050 (10yr)
    if _is_valid(c[2040]) and _is_valid(c[2050]):
        r3_c = c[2050] / c[2040] - 1
    else:
        r3_c = 0.0

    # Negating a carbon-price percentage increase produced negative fuel prices
    # whenever carbon prices more than doubled. The prescribed inverse path
    # preserves positive prices and is paired with a fixed-price sensitivity.
    return tuple(inverse_carbon_multiplier(c[a],c[b])-1.
                 for a,b in [(2023,2030),(2030,2040),(2040,2050)])


def compute_b_target(seq, scenario, c_dict):
    """Fuels WITH 2050 targets (NH3_Green, H2_Fossil): LINEAR path from the
       2023 baseline to the IRENA 2050 target (2026-09-07: node-based linear
       interpolation, not CAGR). APS path is global (same for all
       regions/scenarios)."""
    f = fuels[seq]
    aps_2023 = (f['cur_min'], f['cur_max'])
    aps_2050 = (f['p50_min'], f['p50_max'])
    span = 2050 - 2023
    result = {}
    for yr in YEARS:
        if yr == 2023:
            result[yr] = aps_2023
        else:
            frac = (yr - 2023) / span
            result[yr] = (aps_2023[0] + (aps_2050[0] - aps_2023[0]) * frac,
                          aps_2023[1] + (aps_2050[1] - aps_2023[1]) * frac)
    return result


def compute_b_trajectory(seq, scenario, c_dict):
    """Fuels WITHOUT 2050 targets (FAME, HVO, LNG_Bio): LINEAR path driven by
       the per-region carbon trajectory (2026-09-07: period TOTAL rates applied
       linearly between nodes — no CAGR compounding).
       All regions/scenarios start from the same APS 2023 baseline."""
    f = fuels[seq]
    start_min, start_max = f['cur_min'], f['cur_max']

    # Period fuel-price rates from THIS region's carbon trajectory
    r1, r2, r3 = _period_rates_from_carbon(c_dict)

    # Linear application of the period total rates (straight lines between
    # the 2023→2030→2040→2050 nodes)
    v30_min = start_min * (1 + r1)
    v40_min = v30_min   * (1 + r2)
    v50_min = v40_min   * (1 + r3)

    # Max path (same rates, applied to its own starting point)
    v30_max = start_max * (1 + r1)
    v40_max = v30_max   * (1 + r2)
    v50_max = v40_max   * (1 + r3)

    return {
        2023: (start_min, start_max),
        2030: (v30_min, v30_max),
        2040: (v40_min, v40_max),
        2050: (v50_min, v50_max),
    }


# ============================================================
# 4. BUILD PRICE_LONG (per-region)
# ============================================================
orig = pd.read_excel(MATRIX_PATH, sheet_name='Price_Long')
orig_cols = list(orig.columns)
rows = []; seq_ctr = 0

for seq in sorted(fuels.keys()):
    f = fuels[seq]
    for scenario in SCENARIOS:
        # Determine regions for this scenario
        regions = CARBON_REGIONS[scenario]

        for region in regions:
            c_dict = carbon_data[scenario][region]

            # Compute fuel prices
            if seq in A_PETRO + A_GAS:
                prices = compute_a(seq, scenario)  # same across regions
            elif seq in B_TARGET:
                prices = compute_b_target(seq, scenario, c_dict)
            elif seq in B_TRAJECTORY:
                prices = compute_b_trajectory(seq, scenario, c_dict)
            else:
                continue
            if prices is None:
                continue

            for yr in YEARS:
                p_min, p_max = prices[yr]
                c_raw = c_dict.get(yr, np.nan)
                c_tco2 = c_raw if (c_raw is not None and not (isinstance(c_raw, float) and np.isnan(c_raw))) else 0.0

                total_ef = f['cf_co2'] / f['lhv'] * 1000 + f['wtt']
                carbon_tax_mwh = c_tco2 * total_ef * 3.6 / 1000 if total_ef > 0 else 0.0

                if seq in A_PETRO + A_GAS:
                    method = 'WEO_Index'
                elif seq in B_TARGET:
                    method = 'IRENA_CAGR'
                else:
                    method = 'CarbonInverse'

                seq_ctr += 1
                rows.append(dict(
                    Seq=seq_ctr, Fuel=f['name'], Scenario=scenario, Year=yr,
                    WEO_Region=region,
                    Price_Min=round(p_min, 4), Price_Max=round(p_max, 4),
                    Method=method,
                    Carbon_USDtCO2=round(c_tco2, 1),
                    Total_EF_gCO2_MJ=round(total_ef, 3),
                    Carbon_Tax_USDMWh=round(carbon_tax_mwh, 6),
                    Eff_Min=round(p_min + carbon_tax_mwh, 4),
                    Eff_Max=round(p_max + carbon_tax_mwh, 4),
                ))

df_new = pd.DataFrame(rows)
for col in orig_cols:
    if col not in df_new.columns:
        df_new[col] = np.nan
df_new = df_new[orig_cols]

print(f'\nPrice_Long: {len(df_new)} rows, {df_new.Fuel.nunique()} fuels, {df_new.WEO_Region.nunique()} regions')
print(f'Regions: {sorted(df_new.WEO_Region.unique())}')

# ============================================================
# 5. SAVE
# ============================================================
bak = MATRIX_PATH.replace('.xlsx', '_backup_v4.xlsx')
shutil.copy2(MATRIX_PATH, bak)
print(f'Backup: {bak}')

with pd.ExcelWriter(MATRIX_PATH, engine='openpyxl') as writer:
    df_new.to_excel(writer, sheet_name='Price_Long', index=False)
    orig_pm = pd.ExcelFile(bak)
    for sheet in orig_pm.sheet_names:
        if sheet != 'Price_Long':
            orig_pm.parse(sheet).to_excel(writer, sheet_name=sheet, index=False)

# ============================================================
# 6. VERIFICATION
# ============================================================
print()
for label, fuel_name in [('MGO', 'MDO/MGO (ULSFO, max 0.10% S)'),
                          ('FAME', 'FAME Biodiesel (waste FOGs)'),
                          ('NH3', 'Ammonia -- Renewable (e-NH3)')]:
    print(f'=== {label} ===')
    sub = df_new[df_new['Fuel'] == fuel_name]
    # Show one representative region per scenario
    for sc in SCENARIOS:
        sc_sub = sub[sub['Scenario'] == sc]
        regions_shown = sc_sub['WEO_Region'].unique()[:2]  # first 2 regions
        for region in regions_shown:
            r_sub = sc_sub[sc_sub['WEO_Region'] == region]
            for _, r in r_sub.iterrows():
                print(f"  {r['Scenario']:6s} {r['WEO_Region'][:40]:40s} {r['Year']}: {r['Price_Min']:.1f}-{r['Price_Max']:.1f} USD/MWh, C={r['Carbon_USDtCO2']:.0f}, Eff={r['Eff_Min']:.1f}-{r['Eff_Max']:.1f}")
        if len(sc_sub['WEO_Region'].unique()) > 2:
            print(f"    ... +{len(sc_sub['WEO_Region'].unique())-2} more regions")
    print()
