#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
main_v2.py — Global Tuna Fleet Dynamics Scenario Simulator (v2.0)
=============================================================================
CALCULATION-MODEL INTERFACE (2026-09-17): this module provides fleet-
dynamics functions to drivers; it has NO standalone simulation entry
point and writes nothing on import. Drivers:
    figures/Fig5/fig5_run.py          Fig5 BAU / mitigation chain
                                      (81 + 648 sims, multiprocessing)
    figures/Fig4/preprocess_fig4.py   Fig4 panels
    main_v2.export_meco_tables()      Meco proxy tables
Running `python main_v2.py` only prints this notice. The legacy full-
factorial runner (build_scenario_matrix: 139,968 combos, no downstream
consumers, ~8-13 days single-process) is retired from the CLI path.
=============================================================================
Simulates multi-decadal fleet evolution under policy scenarios:
  1. Capacity expansion via nested-probability cloning (capacity_growth_rate)
  2. Retirement scenario switch (retirement_scenario: 1=natural, 2=rebuild, 3=natural+forced)
  3. GHG-power-intensity-based alternative-fuel targeting (alt_fuel_target_rate)

GHG computation uses ghg_lca's operational parameter framework:
  - SFCbase + SFOC load correction (IMO Fourth GHG Study)
  - Per-vessel T_map, H_main, LF, SFR, AUX_Ratio, Alpha
  - Hull lifespan (30yr) & engine replacement (10yr) cycles
  - Effective_Hull_Year & Engine_Vintage tracked per vessel

Key function: process_fleet_dynamics_pipeline()
=============================================================================
"""

import os, sys, warnings, time, json
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# =============================================================================
# Paths
# =============================================================================
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.dirname(BASE_DIR)
PMM_PATH    = os.path.join(ROOT_DIR, "PMM_Imputation", "After_PMM_Vessels.csv")
GHG_DIR     = os.path.join(ROOT_DIR, "GHG_Calculation")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

sys.path.insert(0, GHG_DIR)
import ghg_lca  # historical-LCA engine (GHG_Calculation/ghg_lca.py)

# Grid catch data path (for gear-specific species composition)
GRID_PATH = os.path.join(ROOT_DIR, "GHG_Calculation", "Base_3_Spatial_Grid_Enriched.csv")

# =============================================================================
# 0. Gear-Specific Catch Composition Weights
# =============================================================================
_GEAR_WEIGHTS_CACHE = None

# =============================================================================
# Share5 (E_tuna) correction - 2026-09-18 user directive
# Same (flag, gear) x year allocation as ghg_lca Base_1-4; held at the latest
# available factor (ref_year, nearest-year fallback) so every vessel-level GHG
# number in the scenario chain is reported on the corrected emission basis.
# =============================================================================
SHARE5_LOOKUP_PATH = os.path.join(ROOT_DIR, "effort_data", "Share5_Lookup_FlagGearYear.csv")
_SHARE5_LUT = None
_SHARE5_FACTOR_CACHE = {}

def _load_share5_lookup():
    global _SHARE5_LUT
    if _SHARE5_LUT is None:
        lut = {}
        try:
            s5 = pd.read_csv(SHARE5_LOOKUP_PATH)
            s5.columns = [str(c).strip() for c in s5.columns]
            for (fl, gr), grp in s5.groupby(["flag", "gear"]):
                lut[(str(fl), str(gr))] = {
                    int(y): float(v) for y, v in zip(grp["Year"], grp["share5"]) if pd.notna(v)}
        except FileNotFoundError:
            print("[share5] WARNING: Share5_Lookup_FlagGearYear.csv not found -> factor = 1.0")
        _SHARE5_LUT = lut
    return _SHARE5_LUT

def _share5_factor_map(ref_year=2025):
    """{(flag, gear): factor} at ref_year with nearest-year fallback."""
    if ref_year in _SHARE5_FACTOR_CACHE:
        return _SHARE5_FACTOR_CACHE[ref_year]
    lut = _load_share5_lookup()
    fac = {}
    for key, ymap in lut.items():
        if not ymap:
            continue
        if ref_year in ymap:
            fac[key] = ymap[ref_year]
        else:
            fac[key] = ymap[min(ymap, key=lambda y: abs(y - ref_year))]
    _SHARE5_FACTOR_CACHE[ref_year] = fac
    return fac

def compute_gear_catch_weights(grid_path=GRID_PATH, ref_year=2024):
    """
    Compute historical species catch proportion per gear type from Base_3 grid data.

    Only PS and LL have catch records in Base_3 (TP and SA are support vessels).

    Returns
    -------
    dict: {gear: {species: weight}}
        e.g. {"PS": {"SKJ": 0.735, "YFT": 0.237, "BET": 0.028, "ALB": 0.0, "SBT": 0.0},
              "LL": {"ALB": 0.378, "BET": 0.293, "YFT": 0.286, "SBT": 0.038, "SKJ": 0.005}}
    """
    global _GEAR_WEIGHTS_CACHE
    if _GEAR_WEIGHTS_CACHE is not None:
        return _GEAR_WEIGHTS_CACHE

    # 2026-09-17: reuse the process-wide Base_3 cache instead of re-reading
    # the 495k-row CSV (~2.5 s) just to filter one reference year.
    if grid_path == GRID_PATH:
        df = _load_base3()
    else:
        df = pd.read_csv(grid_path)
    df = df[df["Year"] == ref_year]

    species_cols = ["SBT_Tonnes", "SKJ_Tonnes", "BET_Tonnes", "YFT_Tonnes", "ALB_Tonnes"]
    species_names = [c.replace("_Tonnes", "") for c in species_cols]

    weights = {}
    for gear in ["PS", "LL"]:
        gear_df = df[df["Gear"] == gear]
        totals = gear_df[species_cols].sum()
        total = totals.sum()
        weights[gear] = {sp: (totals[col] / total) if total > 0 else 0.0
                         for col, sp in zip(species_cols, species_names)}

    _GEAR_WEIGHTS_CACHE = weights

    print(f"  Gear catch weights (ref_year={ref_year}):")
    for gear in ["PS", "LL"]:
        w = weights[gear]
        top_sp = sorted(w.items(), key=lambda x: -x[1])
        print(f"    {gear}: " + ", ".join(f"{sp}={wt:.1%}" for sp, wt in top_sp if wt > 0.001))

    return weights


# =============================================================================
# 1. Baseline Data Loading
# =============================================================================
def load_baseline_fleet(pmm_path=PMM_PATH):
    """
    Load 2025 baseline fleet with per-vessel GHG from ghg_lca framework.

    Adds two key fields:
      - Effective_Hull_Year: most recent hull renewal year (30yr cycle)
      - Engine_Vintage:      most recent engine replacement year (10yr cycle)

    Returns
    -------
    fleet_df : DataFrame
    pm_dict  : Prior_Matrix parameter dictionary
    """
    print("=" * 70)
    print("  LOADING 2025 BASELINE FLEET (ghg_lca GHG framework)")
    print("=" * 70)

    # ---- 1a. Load Prior_Matrix ----
    pm_dict = ghg_lca.load_prior_matrix(ghg_lca.PRIOR_MATRIX_PATH)

    # ---- 1a2. Override WtT with Excel data (ecoinvent → Scenario_Fuel_Parameters) ----
    pm_dict = inject_wtt_from_excel(pm_dict)

    # ---- 1b. Load PMM-imputed vessels ----
    df, pool_dict = ghg_lca.run_imputation_pipeline(
        pmm_path, pm_dict, random_seed=42, write_output=False)
    df = ghg_lca.impute_builtdate_deterministic(df, pool_dict)

    # ---- 1d. GT -> LSW ----
    df = ghg_lca.convert_gt_to_lsw(df, pm_dict)

    # ---- 1e. Compute operational parameters (T_map, H, LF, SFR, etc.) ----
    df = ghg_lca.assign_operational_params(df, pm_dict)

    # ---- 1f. Compute Effective_Hull_Year & Engine_Vintage ----
    HULL_LIFESPAN = ghg_lca.get_best(pm_dict, "LIFESPAN_HULL", 30)
    ENG_LIFESPAN  = ghg_lca.get_best(pm_dict, "LIFESPAN_ENGINE", 10)
    REF_YEAR = 2025

    original_bd = df["Builtdate"].values.astype(float)
    df["Effective_Hull_Year"] = original_bd + \
        ((REF_YEAR - original_bd) // HULL_LIFESPAN) * HULL_LIFESPAN
    df["Engine_Vintage"] = original_bd + \
        ((REF_YEAR - original_bd) // ENG_LIFESPAN) * ENG_LIFESPAN
    # Clip to valid range
    df["Effective_Hull_Year"] = df["Effective_Hull_Year"].clip(
        lower=original_bd.min(), upper=REF_YEAR)
    df["Engine_Vintage"] = df["Engine_Vintage"].clip(
        lower=original_bd.min(), upper=REF_YEAR)

    # ---- 1g. Compute per-vessel 2025 GHG (baseline: no effort adjustment) ----
    df = compute_fleet_ghg(df, pm_dict, ref_year=REF_YEAR, gear_effort=None)

    # ---- 1h. Add Organization ----
    if "Organization" not in df.columns:
        if "Authorized_Oceans" in df.columns:
            df["Organization"] = (
                df["Authorized_Oceans"].astype(str)
                .str.split(";").str[0].str.strip()
            ).fillna("GLOBAL")
        else:
            df["Organization"] = "GLOBAL"

    # ---- 1i. Rename + select columns ----
    fleet_df = df.rename(columns={
        "Length":       "LOA",
        "Tonnage":      "Tonnage_GT",
        "Enginepower":  "Power_kW",
        "Builtdate":    "Built_Year",
    })
    fleet_df["Size_Class"] = np.where(fleet_df["LOA"] < 12, "Small", "Large")
    fleet_df["Vessel_ID"] = range(1, len(fleet_df) + 1)
    fleet_df["GHG_Power_Intensity"] = np.where(
        fleet_df["Power_kW"] > 0,
        fleet_df["GHG_Emissions"] / fleet_df["Power_kW"],
        0.0
    )

    out_cols = [
        "Vessel_ID", "Flag", "VesselType", "Organization",
        "LOA", "Power_kW", "Tonnage_GT", "Built_Year",
        "Effective_Hull_Year", "Engine_Vintage",
        "Size_Class", "GHG_Emissions", "GHG_Power_Intensity",
        "Sector", "T_map", "H_main", "H_aux",
        "LF_move", "LF_work", "LF_aux",
        "SFR_main_move", "SFR_main_work", "SFR_aux",
        "Engine_Type", "Fuel_Type", "Has_Aux", "AUX_Ratio",
        "LSW", "EF_Build", "EF_Maint", "R22_Leak",
        "Gear_Intensity", "Gear_Lifespan", "Gear_Maint_Rate",
        "Alpha",
        # v3.0: GHG breakdown + alt fuel metadata
        "GHG_Fuel_CO2", "GHG_Fuel_CH4", "GHG_Fuel_N2O", "GHG_Fuel_WtT",
        "GHG_Build", "GHG_Refrig", "Fuel_Label", "LHV_MJ_kg",
        "SFR_main_move_eff", "SFR_main_work_eff",
    ]
    out_cols = [c for c in out_cols if c in fleet_df.columns]
    fleet_df = fleet_df[out_cols].copy()

    total_ghg = fleet_df["GHG_Emissions"].sum()
    print(f"  Fleet: {len(fleet_df):,} vessels")
    print(f"  Total power: {fleet_df['Power_kW'].sum():,.0f} kW")
    print(f"  Total GHG (2025): {total_ghg:,.0f} tCO2e ({total_ghg/1e6:.1f} Mt)")
    print(f"  Effective_Hull_Year range: {fleet_df['Effective_Hull_Year'].min():.0f} - "
          f"{fleet_df['Effective_Hull_Year'].max():.0f}")
    print(f"  Engine_Vintage range: {fleet_df['Engine_Vintage'].min():.0f} - "
          f"{fleet_df['Engine_Vintage'].max():.0f}")
    print()

    return fleet_df, pm_dict


# =============================================================================
# 2. Fuel Cost Ratio — Energy-Normalised P/LHV Approach
# =============================================================================
#
# Derivation (ICE-to-ICE, η_k cancels out):
#   C_work = P / (LHV × η_k)          [USD / MJ_mech]
#   Cost_Ratio = (P_new / LHV_new) / (P_base / LHV_base)
#
# Unit of P/LHV: USD/MJ of heat content.
# This strips away the deceptive weight difference between low-LHV fuels
# (NH₃ at 18.6 MJ/kg) and high-LHV fuels (MGO at 42.7 MJ/kg), comparing
# them purely on a "price per unit of energy" basis.
#
# Assumption: all competing fuels use internal combustion engines (ICE)
# with thermal efficiencies in the 38-43% range.  η_k differences are
# within engineering noise and cancel out in the ratio.
# If a fuel pathway uses a fundamentally different power system (e.g.
# hydrogen fuel cell at 55%+), pass eta_override to disable the cancel.
# =============================================================================

FUEL_DATABASE = {
    # key          LHV (MJ/kg)   EF_CO2 (kg/kg)   EF_CH4 (kg/kg)   EF_N2O (kg/kg)
    "MGO":        (42.7, 3.206, 0.00005, 0.00018),   # Marine Gas Oil (baseline)
    "HFO":        (40.2, 3.114, 0.00005, 0.00018),   # Heavy Fuel Oil (VLSFO)
    "LFO":        (41.2, 3.151, 0.00005, 0.00018),   # Light Fuel Oil
    "LPG_Propane":(46.3, 3.000, 0.00005, 0.00018),   # LPG Propane
    "LPG_Butane": (45.7, 3.030, 0.00005, 0.00018),   # LPG Butane
    "LNG_Fossil": (48.0, 2.750, 0.0,     0.00011),   # LNG fossil
    "LNG_Bio":    (48.0, 2.750, 0.0,     0.00011),   # LNG biogenic (same LHV, zero net CO2)
    "FAME":       (37.2, 0.0,   0.0,     0.0),       # FAME biodiesel (biogenic)
    "HVO":        (44.0, 0.0,   0.0,     0.0),       # HVO renewable diesel
    "GASOLINE":   (44.0, 3.158, 0.0015,  0.00004),   # <12m outboard petrol: LHV 44 MJ/kg
        # (EU tech reg., Order on subsidies for energy savings...); EF_CO2/CH4/N2O
        # from Prior_Matrix C (EF_CO2_Gasoline 3.158, EF_CH4_GASOLINE_4STROKE
        # 1.5 g/kgFuel, EF_N2O_GASOLINE 0.04 g/kgFuel — EPA 2025); SFR = EPA direct
        # (SFR_GASOLINE_4STROKE), price follows MGO (no gasoline price series)
    "H2_Fossil":  (120.0,0.0,   0.0,     0.0),       # Hydrogen (SMR+CCS)
    "H2_Green":   (120.0,0.0,   0.0,     0.0),       # Green H2 (grid electrolysis)
    "NH3_Green":  (18.6, 0.0,   0.0,     0.0),       # Green ammonia (e-NH3)
}

# GWP-100 values for CO2eq computation (IPCC AR6)
_GWP_CH4 = 28.5
_GWP_N2O = 273.0

# Baseline MGO LHV (MJ/kg) — reference for SFC conversion
_LHV_BASE_MGO = 42.7


def _fuel_co2eq(fuel_name: str) -> float:
    """
    Total combustion CO2-equivalent per kg fuel.

    CO2eq = CfCO2 + CfCH4 × GWP_CH4 + CfN2O × GWP_N2O

    For biogenic fuels (FAME, HVO) CfCO2=0 but WtT emissions are upstream.
    WtT (Well-to-Tank) is NOT included here — carbon pricing in real markets
    (EU ETS, IMO CII) taxes direct combustion emissions only.
    """
    lhv, co2, ch4, n2o = FUEL_DATABASE.get(fuel_name, (42.7, 3.206, 0.00005, 0.00018))
    return co2 + ch4 * _GWP_CH4 + n2o * _GWP_N2O


# =============================================================================
# LHV-based Dynamic SFC for Alternative Fuels
# =============================================================================
# Core physics: SFC (Specific Fuel Consumption, g/kWh or tFuel/kWh) is
# inversely proportional to fuel energy density (LHV, Lower Heating Value).
#
#   SFC_alt = SFC_base × (LHV_base / LHV_alt)
#
# This preserves the two-tier SFC structure from ghg_lca:
#   - SFC_move: LF=0.80 → SFOC correction factor ≈ 1.003
#   - SFC_work: LF=0.20 → SFOC correction factor ≈ 1.156
# Each tier scales independently by the LHV ratio.
#
# For blended fuels:
#   LHV_blend = (1 - ratio) × LHV_base + ratio × LHV_alt
#   SFC_blend = SFC_base × (LHV_base / LHV_blend)
# =============================================================================

def compute_alt_fuel_sfc(fuel_name, sfc_base_move, sfc_base_work,
                          lhv_base=_LHV_BASE_MGO):
    """
    Compute alternative fuel SFC preserving two-tier (move/work) structure.

    Parameters
    ----------
    fuel_name : str — key into FUEL_DATABASE
    sfc_base_move : float — baseline MGO SFC for move phase (tFuel/kWh)
    sfc_base_work : float — baseline MGO SFC for work phase (tFuel/kWh)
    lhv_base : float — baseline fuel LHV (default MGO = 42.7 MJ/kg)

    Returns
    -------
    (sfc_move, sfc_work) — alt fuel SFCs in tFuel/kWh
    """
    lhv_alt = FUEL_DATABASE.get(fuel_name, (42.7,))[0]
    if lhv_alt <= 0:
        lhv_alt = 42.7
    ratio = lhv_base / lhv_alt
    return sfc_base_move * ratio, sfc_base_work * ratio


def compute_blended_sfc(blend_share, alternative_fuel_type,
                         sfc_base_move, sfc_base_work,
                         lhv_base=_LHV_BASE_MGO):
    """
    Compute blended-fuel SFC for drop-in biofuel blends.

    LHV_blend = (1 - share) × LHV_base + share × LHV_alt
    SFC_blend = SFC_base × (LHV_base / LHV_blend)

    Parameters
    ----------
    blend_share : float — fraction of alternative fuel (0.0–1.0)
    alternative_fuel_type : str — key into FUEL_DATABASE for the blend component
    sfc_base_move, sfc_base_work : float — baseline MGO SFCs (tFuel/kWh)
    lhv_base : float — baseline fuel LHV

    Returns
    -------
    (sfc_move, sfc_work, lhv_blend) — blended SFCs + effective LHV
    """
    lhv_alt = FUEL_DATABASE.get(alternative_fuel_type, (37.2,))[0]
    if lhv_alt <= 0:
        lhv_alt = 37.2
    lhv_blend = (1.0 - blend_share) * lhv_base + blend_share * lhv_alt
    if lhv_blend <= 0:
        return sfc_base_move, sfc_base_work, lhv_base
    ratio = lhv_base / lhv_blend
    return sfc_base_move * ratio, sfc_base_work * ratio, lhv_blend


def get_fuel_ef_co2(fuel_name):
    """Get combustion CO2 emission factor (kgCO2/kg fuel). Biogenic=0."""
    return FUEL_DATABASE.get(fuel_name, (42.7, 3.206, 0, 0))[1]


def get_fuel_lhv(fuel_name):
    """Get fuel LHV (MJ/kg)."""
    return FUEL_DATABASE.get(fuel_name, (42.7,))[0]


# =============================================================================
# WtT (Well-to-Tank) Upstream Emission Factors
# =============================================================================
# Override ecoinvent values in Prior_Matrix with Scenario_Fuel_Parameters.xlsx data.
# Excel WtT values in gCO2eq/MJ → converted to kgCO2eq/kg fuel via LHV.
# If a fuel is not in Excel, fall back to ecoinvent (Prior_Matrix).

# Mapping from vessel Fuel_Type → Excel fuel name (for WtT lookup)
_WTT_FUEL_MAP = {
    "MDO":      "MDO/MGO (ULSFO, max 0.10% S)",
    "HFO":      "HFO (VLSFO, 0.10<S<=0.50%)",
    "GASOLINE": None,   # Not in Excel — keep ecoinvent
}

# Mapping from vessel Fuel_Type → Prior_Matrix WtT key
_WTT_PM_KEY_MAP = {
    "MDO":      "EF_WTT_DIESEL",
    "HFO":      "EF_WTT_HFO",
    "GASOLINE": "EF_WTT_GASOLINE",
}


def inject_wtt_from_excel(pm_dict):
    """
    Override Prior_Matrix WtT values with Scenario_Fuel_Parameters.xlsx data.

    Excel WtT (gCO2eq/MJ) → kgCO2eq/kg fuel via LHV conversion.
    Falls back to existing ecoinvent values for fuels not in Excel.

    Updates pm_dict['by_code'][code][*]['Value_Best'] in-place.
    Returns pm_dict for chaining.
    """
    try:
        import price_loader as _pl
        fuel_props = _pl.load_fuel_props()
        for alias, name in _pl._FUEL_ALIASES.items():
            if alias in FUEL_DATABASE and name in fuel_props:
                prop = fuel_props[name]
                FUEL_DATABASE[alias] = (prop["LHV_MJ_kg"], prop["CfCO2"], prop["CfCH4"], prop["CfN2O"])
    except Exception:
        print("  [WtT] Cannot load Excel fuel props; keeping ecoinvent values.")
        return pm_dict

    # pm_dict structure: {'params': DataFrame, 'lookup': {...}, 'by_code': {Param_Code: [entries]}}
    by_code = pm_dict.get("by_code", {})
    overrides = 0

    for fuel_type, excel_name in _WTT_FUEL_MAP.items():
        pm_key = _WTT_PM_KEY_MAP.get(fuel_type)
        if pm_key is None:
            continue

        # Read current ecoinvent value via get_best
        ecoinvent_val = ghg_lca.get_best(pm_dict, pm_key, 0.0)

        if excel_name is not None and excel_name in fuel_props:
            # Excel WtT: gCO2eq/MJ → kgCO2eq/kg
            wtt_g_per_mj = fuel_props[excel_name].get("WtT_GHG_gCO2eq_MJ", 0.0)
            lhv_mj_kg = fuel_props[excel_name].get("LHV_MJ_kg", 42.7)
            if wtt_g_per_mj > 0 and lhv_mj_kg > 0:
                wtt_kg_per_kg = wtt_g_per_mj * lhv_mj_kg / 1000.0
            else:
                wtt_kg_per_kg = 0.0

            if wtt_kg_per_kg > 0:
                # Update all entries for this Param_Code in by_code
                if pm_key in by_code:
                    for entry in by_code[pm_key]:
                        entry["Value_Best"] = wtt_kg_per_kg
                overrides += 1
                print(f"  [WtT] {pm_key}: ecoinvent={ecoinvent_val:.3f} → "
                      f"Excel={wtt_kg_per_kg:.3f} kgCO2eq/kg "
                      f"({wtt_g_per_mj:.0f} gCO2eq/MJ × {lhv_mj_kg:.0f} MJ/kg)")
            else:
                print(f"  [WtT] {pm_key}: WtT=0 in Excel, keeping ecoinvent={ecoinvent_val:.3f}")
        else:
            # Fuel not in Excel — keep ecoinvent
            print(f"  [WtT] {pm_key}: not in Excel, keeping ecoinvent={ecoinvent_val:.3f}")

    if overrides == 0:
        print("  [WtT] No overrides applied (all Excel WtT values missing or zero).")
    else:
        print(f"  [WtT] {overrides} WtT value(s) overridden from Excel.")

    return pm_dict


# Default scenario fuel prices (USD/tonne) — will be superseded by Excel data
DEFAULT_FUEL_PRICES = {
    "MGO":          700,
    "HFO":          400,
    "LNG_Fossil":   500,
    "FAME":         1200,
    "HVO":          1500,
    "NH3_Green":    900,
    "H2_Fossil":    3000,
}


# =============================================================================
# TWO-PATH FUEL TRANSITION (2026-09-04 user directive — supersedes the shared
# alternative_fuel_adoption_rate):
#   Path A — BIOFUEL BLEND (FAME/HVO): s_bio ∈ [0,1] is the per-vessel fuel
#            mixing ratio; LHV/EF/price/WtT are blend-weighted.
#   Path B — NEW-FUEL VESSEL RENEWAL (NH3/H2/LNG): r_new ∈ [0,1] is the share
#            of NEWBUILD vessels that are renewed with a dedicated new-fuel
#            power system; renewed vessels run 100% new fuel (NO blending).
# The two paths NEVER share an adoption parameter.
# =============================================================================


def get_biofuel_adoption_rate(scenario_params, year, ref_year=2025):
    """Share of the FLEET (all vessels, drop-in) running biofuel — fuels
    FAME/HVO are plug-and-play and do NOT depend on newbuild renewal
    (2026-09-11 user directive). Two modes:
      - 'biofuel_nodes' {2030:v, 2040:v, 2050:v}: piecewise-LINEAR adoption
        (0 at ref_year), clipped to [0,1].
      - fallback: rate x (1+growth)^(t-ref_year)."""
    nodes = scenario_params.get("biofuel_nodes")
    if nodes:
        nodes = {int(k): float(v) for k, v in nodes.items()}   # JSON keys -> str
        yrs = sorted(nodes)
        yrs_full = [int(ref_year)] + yrs
        vals_full = [0.0] + [nodes[y] for y in yrs]
        return float(np.clip(np.interp(year, yrs_full, vals_full), 0.0, 1.0))
    share = float(scenario_params.get("biofuel_blend_share",
                                      scenario_params.get("blend_share", 0.0)))
    growth = float(scenario_params.get("biofuel_annual_growth", 0.0))
    years = max(int(year) - int(ref_year), 0)
    return float(np.clip(share * ((1.0 + growth) ** years), 0.0, 1.0))


# Physical blending limits of drop-in biofuels (fraction of bio in the tank):
# FAME is limited to B30 (oxidation/cold-flow/microbial issues, OEM warranty),
# HVO is a true drop-in (EN 15940, B100). 2026-09-11 user directive.
BIO_BLEND_LIMIT = {"FAME": 0.30, "HVO": 1.00}


def get_biofuel_blend_limit(scenario_params, bio_type):
    """Blend limit gamma for the selected biofuel: explicit override
    (biofuel_blend_limit) else the fuel table (FAME 0.30 / HVO 1.00)."""
    ov = scenario_params.get("biofuel_blend_limit")
    if ov is not None:
        return float(np.clip(ov, 0.0, 1.0))
    return float(BIO_BLEND_LIMIT.get(bio_type, 0.0))


def get_biofuel_blend_share(scenario_params, year, ref_year=2025):
    """LEGACY (blend-mixing semantics, pre-2026-09-11). Kept for the LHS
    sensitivity sampler; the fleet model now uses get_biofuel_adoption_rate."""
    nodes = scenario_params.get("biofuel_nodes")
    if nodes:
        nodes = {int(k): float(v) for k, v in nodes.items()}   # JSON keys -> str
        yrs = sorted(nodes)
        yrs_full = [int(ref_year)] + yrs
        vals_full = [0.0] + [nodes[y] for y in yrs]
        return float(np.clip(np.interp(year, yrs_full, vals_full), 0.0, 1.0))
    share = float(scenario_params.get("biofuel_blend_share",
                                      scenario_params.get("blend_share", 0.0)))
    growth = float(scenario_params.get("biofuel_annual_growth", 0.0))
    years = max(int(year) - int(ref_year), 0)
    return float(np.clip(share * ((1.0 + growth) ** years), 0.0, 1.0))


def get_newfuel_renewal_rate(scenario_params, year, ref_year=2025):
    """Fraction of NEWBUILD vessels renewed with dedicated new-fuel
    propulsion. Two modes (2026-09-08):
      - 'newfuel_nodes' {2030:v, 2040:v, 2050:v}: piecewise-LINEAR between
        the nodes (0 at ref_year) — the Fig.5 mitigation pathway definition.
      - fallback: r_new,t = rate x (1+growth)^(t-ref_year)."""
    nodes = scenario_params.get("newfuel_nodes")
    if nodes:
        nodes = {int(k): float(v) for k, v in nodes.items()}   # JSON keys -> str
        yrs = sorted(nodes)
        yrs_full = [int(ref_year)] + yrs
        vals_full = [0.0] + [nodes[y] for y in yrs]
        return float(np.clip(np.interp(year, yrs_full, vals_full), 0.0, 1.0))
    rate = float(scenario_params.get("newfuel_renewal_rate", 0.0))
    growth = float(scenario_params.get("newfuel_annual_growth", 0.0))
    years = max(int(year) - int(ref_year), 0)
    return float(np.clip(rate * ((1.0 + growth) ** years), 0.0, 1.0))


# WtT (Well-to-Tank) kgCO2eq/kg per fuel — Scenario_Fuel_Parameters.xlsx
# (gCO2eq/MJ × LHV / 1000); fuels absent from Excel fall back to ecoinvent.
_WTT_EXCEL_MAP = {
    "MGO":       "MDO/MGO (ULSFO, max 0.10% S)",
    "HFO":       "HFO (VLSFO, 0.10<S<=0.50%)",
    "LNG_Fossil": "LNG -- Fossil (Methane)",
    "LNG_Bio":   "LNG -- Biogenic (Methane)",
    "FAME":      "FAME Biodiesel (waste FOGs)",
    "HVO":       "HVO Renewable Diesel (2nd gen)",
    "NH3_Green": "Ammonia -- Renewable (e-NH3)",
    "H2_Fossil": "Hydrogen -- Fossil (SMR + CCS)",
    "LPG_Propane": "LPG (Propane)",
    "LPG_Butane": "LPG (Butane)",
}
_WTT_ECONVENT = {
    "MDO": "EF_WTT_DIESEL", "HFO": "EF_WTT_HFO", "GASOLINE": "EF_WTT_GASOLINE",
}
_WTT_CACHE = None


def _wtt_kg_per_kg(fuel, pm_dict):
    """kgCO2eq/kg upstream WtT EF for a FUEL_DATABASE key (Excel first)."""
    global _WTT_CACHE
    if _WTT_CACHE is None:
        _WTT_CACHE = {}
        try:
            import price_loader as _pl
            fp = _pl.load_fuel_props()
        except Exception:
            fp = {}
        for key, excel_name in _WTT_EXCEL_MAP.items():
            rec = fp.get(excel_name)
            if rec and rec.get("WtT_GHG_gCO2eq_MJ", 0.0) > 0 and rec.get("LHV_MJ_kg", 0) > 0:
                _WTT_CACHE[key] = rec["WtT_GHG_gCO2eq_MJ"] * rec["LHV_MJ_kg"] / 1000.0
    if fuel in _WTT_CACHE:
        return _WTT_CACHE[fuel]
    pm_key = _WTT_ECONVENT.get(fuel)
    return ghg_lca.get_best(pm_dict, pm_key, 0.369 if fuel == "MDO" else 0.252) if pm_key else 0.0


def _blended_fuel_props(fuel_name: str, alternative_fuel_adoption_rate: float, alternative_fuel_type: str = "FAME"):
    """
    Compute effective fuel properties with drop-in blend.

    blended_EF  = (1 - share) × base_EF + share × alt_EF
    blended_LHV = (1 - share) × base_LHV + share × alt_LHV
                  (ARITHMETIC weighted average — 2026-09-04; the old harmonic
                  mean is superseded by the two-path fuel logic)

    For biogenic drop-ins (FAME, HVO), alt_EF = 0 (net-zero rated).
    """
    base_lhv, base_ef, base_ch4, base_n2o = FUEL_DATABASE[fuel_name]
    alt_lhv,  alt_ef,  _, _               = FUEL_DATABASE.get(alternative_fuel_type, (37.2, 0.0, 0.0, 0.0))

    blended_ef  = (1 - alternative_fuel_adoption_rate) * base_ef  + alternative_fuel_adoption_rate * alt_ef
    blended_lhv = (1 - alternative_fuel_adoption_rate) * base_lhv + alternative_fuel_adoption_rate * alt_lhv
    blended_ch4 = (1 - alternative_fuel_adoption_rate) * base_ch4
    blended_n2o = (1 - alternative_fuel_adoption_rate) * base_n2o

    return blended_lhv, blended_ef, blended_ch4, blended_n2o


def _price_per_MJ(price_USD_tonne: float, LHV_MJ_kg: float,
                  carbon_tax_USD_tonne: float = 0.0,
                  EF_CO2eq_kg_kg: float = 0.0) -> float:
    """
    Energy-normalised fuel + carbon cost (USD / MJ of heat).

    P_USD_kg       = price_USD_tonne / 1000                       (USD / kg)
    Carbon_USD_kg  = carbon_tax_USD_tonne / 1000 × EF_CO2eq       (USD / kg)
    Total_USD_kg   = P_USD_kg + Carbon_USD_kg
    USD_per_MJ     = Total_USD_kg / LHV_MJ_kg

    EF_CO2eq_kg_kg = combustion CO2-equivalent per kg fuel
                     (CO2 + CH4×GWP + N2O×GWP), NOT just CO2.
    """
    fuel_usd_kg   = price_USD_tonne / 1000.0
    carbon_usd_kg = (carbon_tax_USD_tonne / 1000.0) * EF_CO2eq_kg_kg
    return (fuel_usd_kg + carbon_usd_kg) / LHV_MJ_kg


def calculate_effective_cost_ratio(
    fuel_name_current:             str   = "MGO",
    fuel_name_base:                str   = "MGO",
    price_fuel_current_USD_tonne:  float = 700.0,
    price_carbon_current_USD_tonne: float = 0.0,
    price_fuel_base_USD_tonne:     float = 700.0,
    price_carbon_base_USD_tonne:    float = 0.0,
    eta_override:                  float = None,
    tech_creep:                    float = 0.0,
) -> dict:
    """
    Compute effective cost ratio using energy-normalised P/LHV.

    Core formula (ICE-to-ICE):  Cost_Ratio = (P_new / LHV_new) / (P_base / LHV_base)

    Parameters
    ----------
    fuel_name_current, fuel_name_base : keys into FUEL_DATABASE.
    price_fuel_*_USD_tonne : wholesale fuel price (USD / metric tonne).
    price_carbon_*_USD_tonne : carbon tax (USD / t CO2).
    eta_override : if not None, the current-fuel engine efficiency η_k;
                   used only when the power system differs fundamentally
                   (e.g. fuel cell vs. ICE).  When None, η_k cancels out.
    tech_creep : hull/gear efficiency improvement (amortises unit cost).
    """
    base_lhv = FUEL_DATABASE[fuel_name_base][0]
    curr_lhv = FUEL_DATABASE[fuel_name_current][0]
    base_co2eq = _fuel_co2eq(fuel_name_base)
    curr_co2eq = _fuel_co2eq(fuel_name_current)

    # Energy-normalised cost (USD / MJ heat)
    base_usd_MJ = _price_per_MJ(price_fuel_base_USD_tonne,    base_lhv,
                                price_carbon_base_USD_tonne,  base_co2eq)
    curr_usd_MJ = _price_per_MJ(price_fuel_current_USD_tonne, curr_lhv,
                                price_carbon_current_USD_tonne, curr_co2eq)

    # η_k override for non-ICE power systems (e.g. H2 fuel cell)
    eta_note = "cancelled (ICE-to-ICE)"
    if eta_override is not None:
        curr_usd_MJ = curr_usd_MJ / eta_override
        base_usd_MJ = base_usd_MJ / 0.42  # baseline MGO η_k = 0.42
        eta_note = f"current η={eta_override:.2f} applied"

    # ---- Final ratio (no tech discount — tech_creep only affects Meco) ----
    Cost_Ratio = curr_usd_MJ / base_usd_MJ

    return {
        "base_USD_per_MJ":         round(base_usd_MJ, 6),
        "current_USD_per_MJ":      round(curr_usd_MJ, 6),
        "Cost_Ratio":              Cost_Ratio,
        "eta_treatment":           eta_note,
    }


# =============================================================================
# 3b. Vessel-Level Economic Effort (2025–2050, user directive 2026-08-26)
# =============================================================================
# Per vessel v per year t (vessel-level FIRST, aggregation LAST):
#   Meco_v        = quota_ratio_g/[biomass_ratio_g × (1+tc)^ΔT]   (gear-blended;
#                   E_required ≡ Meco — same quantity, ecological multiplier)
#   FuelShare_v   = biofuel blend share (Path A) OR 1.0 on new-fuel
#                   renewed vessels (Path B, NO blending)
#   CurrentCost_v = _price_per_MJ(P_fuel(v,t), LHV(v,t), CarbonPrice(flag,t), CO2eq(v,t))
#   Cost_Ratio_v  = CurrentCost_v / BaselineCost_{s,2025,MGO}     (FIXED baseline)
#   M_econ_raw_v  = Cost_Ratio_v ^ elasticity_v                   (economic response;
#                   >1 rebound allowed — NO cap, NO floor, 2026-09-04)
#   E_final_v     = Meco_v × M_econ_raw_v
#   M_econ_realized_v = M_econ_raw_v
#   T_eff          = T_map × E_final_v   → bottom-up GHG (compute_fleet_ghg)
# -----------------------------------------------------------------------------

def compute_vessel_econ_effort(fleet_df, scenario, year, gear_blended, scenario_params,
                               meco_eff_map=None):
    """Vectorised per-vessel economic effort for one simulation year.

    TWO-PATH FUEL TRANSITION (2026-09-04 user directive):
      Path A — BIOFUEL BLEND (FAME/HVO): s_bio,t applies to every non-renewed
               vessel; LHV/EF/price are blend-weighted.
      Path B — NEW-FUEL RENEWAL (NH3/H2/LNG): newbuild vessels (Engine_Vintage
               == year) are renewed with a dedicated new-fuel system, chosen
               deterministically by power (largest first) up to r_new,t; they
               run 100% new fuel — NO blending.
    Meco_v is the MACRO multiplier Meco_eff_{Flag,Organization,year} (same for
    all vessels of a flag×org fleet — by design); M_econ_v stays vessel-level.
    E_final = Meco × M_econ_raw — NO cap, NO floor (rebound allowed;
    cap_enabled kept only for backward compatibility and NOT used).

    Returns a DataFrame indexed like fleet_df with columns:
    Meco, FuelShare, Fuel_Label, Current_USD_per_MJ, Baseline_USD_per_MJ,
    Cost_Ratio, Elasticity, M_econ_raw, E_final, M_econ_realized, NewFuel.
    """
    n = len(fleet_df)
    vtype = fleet_df["VesselType"].values
    tc = float(scenario_params.get("tech_creep", 0.0))
    el = float(scenario_params.get("elasticity", -0.3))
    bio_type = scenario_params.get("biofuel_type",
                                   scenario_params.get("alternative_fuel_type", "FAME"))
    newfuel_type = scenario_params.get("newfuel_type",
                                       scenario_params.get("newbuild_fuel", "MGO"))
    base_fuel = _FUEL_ALIAS.get(str(scenario_params.get("fuel_name", "MGO")), "MGO")

    # ---- Meco (= E_required): macro Organization×Species×Year multiplier ----
    if meco_eff_map is not None:
        flags = fleet_df["Flag"].astype(str).values
        orgs = fleet_df["Organization"].astype(str).values
        Meco = np.array([meco_eff_map.get((f, o), np.nan) for f, o in zip(flags, orgs)])
        Meco = np.where(np.isnan(Meco), 1.0, Meco)
    else:  # backward-compatible gear-blended fallback
        def _gm(gb):
            return gb["quota_ratio"] / max(
                gb["biomass_ratio"] * (1.0 + tc) ** max(int(year) - 2025, 0), 0.01)
        m_ps, m_ll = _gm(gear_blended["PS"]), _gm(gear_blended["LL"])
        Meco = np.where(vtype == "PS", m_ps, np.where(vtype == "LL", m_ll, (m_ps + m_ll) / 2.0))

    # ============================================================
    # Fuel transition state (two independent paths, 2026-09-11 revision)
    # ============================================================
    # A. Biofuel ADOPTION (drop-in: FAME/HVO are plug-and-play, no newbuild
    #    dependency): share of the whole fleet running the biofuel at the
    #    fuel's physical blend limit gamma (FAME B30, HVO B100). No persistence.
    bio_rate = get_biofuel_adoption_rate(scenario_params, year)
    bio_gamma = get_biofuel_blend_limit(scenario_params, bio_type)
    # B. New-fuel renewal (DEVICE-DEPENDENT, persistent): vessels already
    #    flagged NewFuel_Flag KEEP their new fuel; this year's NEWBUILD vessels
    #    (Engine_Vintage == year) additionally become renewed up to
    #    newfuel_rate (deterministic by power, largest first).
    newfuel_rate = get_newfuel_renewal_rate(scenario_params, year)
    if "NewFuel_Flag" in fleet_df.columns:
        is_newfuel = fleet_df["NewFuel_Flag"].fillna(False).values.astype(bool).copy()
    else:
        is_newfuel = np.zeros(n, dtype=bool)
    is_nb = (fleet_df["Engine_Vintage"].values == year)
    if newfuel_rate > 0 and is_nb.any():
        nb_idx = np.where(is_nb)[0]
        k = int(round(len(nb_idx) * newfuel_rate))
        k = min(k, len(nb_idx))
        order = nb_idx[np.argsort(-fleet_df["Power_kW"].values[nb_idx])]
        is_newfuel[order[:k]] = True
    # Bio vessels: selected from the NON-newfuel pool (device retrofits take
    # precedence), largest power first — same rule as the device path.
    is_biofuel = np.zeros(n, dtype=bool)
    if bio_rate > 0 and bio_type != "MGO" and bio_gamma > 0:
        pool = np.where(~is_newfuel)[0]
        k = min(int(round(len(pool) * bio_rate)), len(pool))
        if k > 0:
            order = pool[np.argsort(-fleet_df["Power_kW"].values[pool])]
            is_biofuel[order[:k]] = True

    # ---- Base fuel per vessel (historical-fossil BAU, ghg_lca C0 rules):
    #      TP → HFO; <12m APW → GASOLINE; LL/PS/SA ≥12m → MDO ----
    is_apw_small = (vtype != "TP") & (fleet_df["Sector"].values == "APW") \
        & (fleet_df["LOA"].values < 12)
    base_fuel_v = np.where(vtype == "TP", "HFO",
                           np.where(is_apw_small, "GASOLINE", "MGO"))
    base_lhv = FUEL_DATABASE["MGO"][0]
    base_co2eq = _fuel_co2eq("MGO")
    hfo_lhv, hfo_co2eq = FUEL_DATABASE["HFO"][0], _fuel_co2eq("HFO")
    gas_lhv, gas_co2eq = FUEL_DATABASE["GASOLINE"][0], _fuel_co2eq("GASOLINE")
    base_lhv_v = np.where(base_fuel_v == "HFO", hfo_lhv,
                          np.where(base_fuel_v == "GASOLINE", gas_lhv, base_lhv))
    base_co2eq_v = np.where(base_fuel_v == "HFO", hfo_co2eq,
                            np.where(base_fuel_v == "GASOLINE", gas_co2eq, base_co2eq))

    # ============================================================
    # Effective fuel properties (economic layer)
    # ============================================================
    bio_lhv, bio_co2eq = FUEL_DATABASE[bio_type][0], _fuel_co2eq(bio_type)
    new_lhv, new_co2eq = FUEL_DATABASE[newfuel_type][0], _fuel_co2eq(newfuel_type)
    blend_lhv = (1.0 - bio_gamma) * base_lhv_v + bio_gamma * bio_lhv
    blend_co2eq = (1.0 - bio_gamma) * base_co2eq_v + bio_gamma * bio_co2eq
    lhv_eff = np.where(is_newfuel, new_lhv,
                       np.where(is_biofuel, blend_lhv, base_lhv_v))
    co2eq_eff = np.where(is_newfuel, new_co2eq,
                         np.where(is_biofuel, blend_co2eq, base_co2eq_v))
    share = np.where(is_newfuel, 1.0, np.where(is_biofuel, bio_gamma, 0.0))

    # ---- Prices: WEO annual trajectories; bio/new fuel prices ----
    import price_loader as pl
    flags = fleet_df["Flag"].astype(str).values
    regions = np.array([pl.get_vessel_region(f, scenario)[0] for f in flags])
    def prices(fuel):
        by_region = {r: _fuel_price_annual(fuel, scenario, year, r) for r in pd.unique(regions)}
        return np.array([by_region[r] for r in regions])
    p_mgo, p_hfo, p_bio, p_new = prices("MGO"), prices("HFO"), prices(bio_type), prices(newfuel_type)
    p_base = np.where(base_fuel_v == "HFO", p_hfo, p_mgo)
    price_eff = np.where(is_newfuel, p_new,
                         np.where(is_biofuel,
                                  (1.0 - bio_gamma) * p_base + bio_gamma * p_bio,
                                  p_base))

    # ---- Flag-specific carbon price (172-flag map → carbon regime) ----
    flags = fleet_df["Flag"].astype(str).values
    ckey = (scenario, year)
    for f in pd.unique(flags):
        get_vessel_carbon_price(f, scenario, year)   # caches per (scenario, year, flag)
    csub = _CARBON_PRICE_CACHE.setdefault(ckey, {})
    cprice = np.array([csub[f] for f in flags])

    # ---- Current / baseline energy cost (USD/MJ) ----
    curr_usd_mj = _price_per_MJ_vec(price_eff, lhv_eff, cprice, co2eq_eff)
    base_usd_mj = get_baseline_cost(scenario)

    # ---- Cost ratio → M_econ → E_final ----
    # NO cap, NO floor: economic conditions amplify or suppress effort freely;
    # M_econ > 1 (cheap fuel) is a legitimate economic rebound.
    Cost_Ratio = curr_usd_mj / base_usd_mj
    M_econ_raw = Cost_Ratio ** el
    E_final = Meco * M_econ_raw
    M_econ_realized = M_econ_raw

    Fuel_Label = np.where(is_newfuel, newfuel_type,
                          np.where(is_biofuel,
                                   np.char.add(np.char.add(bio_type, "_B"),
                                               np.round(bio_gamma * 100).astype(int).astype(str)),
                                   np.where(base_fuel_v == "HFO", "HFO",
                                            np.where(base_fuel_v == "GASOLINE", "GASOLINE",
                                                     base_fuel))))
    return pd.DataFrame({
        "Meco": Meco, "FuelShare": share, "Fuel_Label": Fuel_Label,
        "Current_USD_per_MJ": curr_usd_mj, "Baseline_USD_per_MJ": np.full(n, base_usd_mj),
        "Cost_Ratio": Cost_Ratio, "Elasticity": np.full(n, el),
        "M_econ_raw": M_econ_raw, "E_final": E_final,
        "M_econ_realized": M_econ_realized,
        "NewFuel": is_newfuel.astype(int)}, index=fleet_df.index)


def _price_per_MJ_vec(price_eff, lhv_eff, carbon_price, co2eq_eff):
    """Vectorised _price_per_MJ: (P/1000 + carbon/1000 × CO2eq) / LHV."""
    return (price_eff / 1000.0 + (carbon_price / 1000.0) * co2eq_eff) / lhv_eff


def calculate_vessel_econ_effort(vessel_row, year, scenario, quota_ratio, biomass_ratio,
                                 tech_creep, fuel_state, fuel_price, carbon_price,
                                 elasticity, cap_enabled=True, baseline_cost=None):
    """Single-vessel interface (user spec §19) — pure function, no fleet context.

    fuel_state : dict with Fuel, LHV_MJ_kg, EF_CO2eq, FuelShare.
    Returns: E_required(=Meco), Current_Fuel, Fuel_Share, Current_USD_per_MJ,
             Baseline_USD_per_MJ, Cost_Ratio, M_econ_raw, E_final, M_econ_realized.
    """
    Meco = quota_ratio / max(
        biomass_ratio * (1.0 + tech_creep) ** max(int(year) - 2025, 0), 0.01)
    lhv = float(fuel_state.get("LHV_MJ_kg", FUEL_DATABASE["MGO"][0]))
    co2eq = float(fuel_state.get("EF_CO2eq", _fuel_co2eq("MGO")))
    curr = _price_per_MJ(float(fuel_price), lhv, float(carbon_price), co2eq)
    base = baseline_cost if baseline_cost is not None else get_baseline_cost(scenario)
    cr = curr / base
    m_raw = cr ** elasticity
    # E = Meco × M_econ — NO cap, NO floor (2026-09-04; rebound allowed)
    e_final = Meco * m_raw
    return {"E_required": Meco,
            "Current_Fuel": fuel_state.get("Fuel", "MGO"),
            "Fuel_Share": fuel_state.get("FuelShare", 0.0),
            "Current_USD_per_MJ": curr, "Baseline_USD_per_MJ": base,
            "Cost_Ratio": cr, "M_econ_raw": m_raw, "E_final": e_final,
            "M_econ_realized": m_raw}


# =============================================================================
# 4. Compute Fleet GHG (using ghg_lca framework, deterministic, no MC)
# =============================================================================
def compute_fleet_ghg(df, pm_dict, ref_year=2025, gear_effort=None,
                      vessel_econ_df=None,
                      alternative_fuel_adoption_rate=0.0, alternative_fuel_type="FAME",
                      newbuild_fuel="MGO",
                      bio_share=None, bio_type=None, newfuel_type=None,
                      newfuel_rate=None, refrigerant_type=None,
                      upsize_beta=0.0, upsize_progress=0.0,
                      bio_adopt=None, bio_gamma=None, grid_ef=None):
    """
    Compute per-vessel annual GHG using ghg_lca operational parameters.

    TWO-PATH FUEL TRANSITION (2026-09-04 user directive):
      A. BIOFUEL BLEND (FAME/HVO): non-renewed vessels use blend share s_bio;
         LHV_blend = (1−s)LHV_base + s·LHV_bio; SFR × LHV_base/LHV_blend;
         EF_CO2 / WtT blend-weighted.
      B. NEW-FUEL RENEWAL (NH3/H2/LNG): renewed vessels (NewFuel flag, or
         Engine_Vintage==ref_year selected deterministically by power up to
         newfuel_rate) run 100% new fuel: LHV_new, SFR × LHV_MGO/LHV_new,
         EF_CO2_new, WtT_new — NO blending, NO share_arr multiplication.
    The two paths NEVER share an adoption parameter.

    gear_effort : dict or None
        {"PS": {"E_final": float, ...}, "LL": {"E_final": float, ...}}
        Each vessel's VesselType → gear → per-vessel E_final.
        If None, E_final=1.0 for all vessels.
        TP/SA vessels (no Base_3 catch) use average of PS+LL E_final.

    vessel_econ_df : DataFrame or None (vessel-level economics, 2026-08-26)
        Columns E_final + FuelShare (+ optional NewFuel) per vessel
        (index matches df). When provided it takes precedence over
        gear_effort: per-vessel E_final / fuel share / new-fuel flag enter
        T_eff and the two-path SFC/EF/WtT chain.
    """
    n = len(df)

    # ---- parameter resolution (new two-path names; old names as fallback) ----
    if bio_type is None:
        bio_type = alternative_fuel_type
    if newfuel_type is None:
        newfuel_type = newbuild_fuel
    bio_share_s = bio_share if bio_share is not None else alternative_fuel_adoption_rate
    if newfuel_rate is None:
        newfuel_rate = 1.0 if newbuild_fuel != "MGO" else 0.0

    # ---- Build per-vessel E_final array: vessel-level economics first ----
    if vessel_econ_df is not None:
        idx = df.index
        E_final_arr = vessel_econ_df.loc[idx, "E_final"].values
        share_arr = vessel_econ_df.loc[idx, "FuelShare"].values
        _eff_ref = {}
    elif gear_effort is not None:
        # Extract per-gear E_final
        e_ps = gear_effort["PS"]["E_final"]
        e_ll = gear_effort["LL"]["E_final"]
        e_other = (e_ps + e_ll) / 2.0  # TP/SA: no catch records, use fleet avg

        v_type_arr = df["VesselType"].values
        E_final_arr = np.where(v_type_arr == "PS", e_ps,
                               np.where(v_type_arr == "LL", e_ll, e_other))
        # Pull global params from one gear's effort dict (same for all gears)
        _eff_ref = gear_effort["PS"]
        share_arr = np.full(n, bio_share_s)
    else:
        E_final_arr = np.ones(n)
        share_arr = np.full(n, bio_share_s)
        _eff_ref = {}

    # ---- Vectors from operational params (handle both naming conventions) ----
    def _col(name_a, name_b, default=None):
        if name_a in df.columns: return df[name_a].values
        if name_b in df.columns: return df[name_b].values
        return np.full(n, default) if default is not None else np.zeros(n)

    power      = np.maximum(_col("Power_kW", "Enginepower", 0.0), 0.0)
    v_type     = _col("VesselType", "VesselType", "LL")
    T_map      = _col("T_map", "T_map", 250)
    H_main     = _col("H_main", "H_main", 12)
    H_aux      = _col("H_aux", "H_aux", 24)
    LF_move    = _col("LF_move", "LF_move", 0.80)
    LF_work    = _col("LF_work", "LF_work", 0.20)
    LF_aux     = _col("LF_aux", "LF_aux", 0.40)
    SFR_m_move = _col("SFR_main_move", "SFR_main_move", 0.0002)
    SFR_m_work = _col("SFR_main_work", "SFR_main_work", 0.0002)
    SFR_a      = _col("SFR_aux", "SFR_aux", 0.0002)
    aux_ratio  = _col("AUX_Ratio", "AUX_Ratio", 0.39)
    has_aux    = _col("Has_Aux", "Has_Aux", 1.0)
    alpha      = np.clip(_col("Alpha", "Alpha", 0.3125), 0, 1)

    engine_type = _col("Engine_Type", "Engine_Type", "MSD")
    fuel_type   = _col("Fuel_Type", "Fuel_Type", "MDO")
    # Historical-fossil BAU — mirrors ghg_lca.get_fuel_type (Prior_Matrix C0):
    # TP → HFO; <12m APW → GASOLINE; LL/PS/SA ≥12m → MDO — drives the
    # CO2/N2O/WtT emission factors below.
    sector = _col("Sector", "Sector", "I")
    is_apw_small = (v_type != "TP") & (sector == "APW") \
        & (_col("LOA", "Length", 20.0) < 12)
    fuel_type = np.where(v_type == "TP", "HFO",
                         np.where(is_apw_small, "GASOLINE", fuel_type))
    lsw         = np.maximum(_col("LSW", "LSW", 0.0), 0.0)
    ef_build    = _col("EF_Build", "EF_Build", 2.421)
    ef_maint    = _col("EF_Maint", "EF_Maint", 6.744)
    r22_leak    = _col("R22_Leak", "R22_Leak", 500.0)
    gear_int    = _col("Gear_Intensity", "Gear_Intensity", 0.0)
    length      = _col("LOA", "Length", 20.0)

    # ---- Engine vintage for SFCbase ----
    eng_vintage = df["Engine_Vintage"].values
    hull_year   = df["Effective_Hull_Year"].values

    # ============================================================
    # TWO-PATH FUEL TRANSITION (2026-09-04): effective SFC / LHV / CO2 EF
    #   A. Biofuel blend:  LHV_b = (1−s)LHV_base + s·LHV_bio; SFR scaled by
    #      LHV_base/LHV_b; EF_CO2 blend-weighted. Applies to NON-renewed ships.
    #   B. New-fuel renewal: renewed ships run 100% new fuel — LHV_new,
    #      SFR × LHV_MGO/LHV_new, EF_CO2_new. NO share_arr multiplication.
    # ============================================================
    if vessel_econ_df is not None and "NewFuel" in vessel_econ_df.columns:
        is_newfuel = vessel_econ_df.loc[df.index, "NewFuel"].values.astype(bool)
    elif "NewFuel_Flag" in df.columns:
        # persisted renewal state on the fleet itself (ρ recomputation path)
        is_newfuel = df["NewFuel_Flag"].fillna(False).values.astype(bool)
    else:
        # deterministic renewal by power (largest newbuilds first) up to rate
        is_newbuild = (eng_vintage == ref_year)
        is_newfuel = np.zeros(n, dtype=bool)
        if newfuel_rate > 0 and is_newbuild.any():
            nb_idx = np.where(is_newbuild)[0]
            k = min(int(round(len(nb_idx) * newfuel_rate)), len(nb_idx))
            order = nb_idx[np.argsort(-power[nb_idx])]
            is_newfuel[order[:k]] = True
    if newfuel_type is None or newfuel_type == "MGO":
        is_newfuel = is_newfuel & np.zeros(n, dtype=bool)   # no renewal when type=MGO

    # ---- A-bis. Bio ADOPTION fallback (2026-09-11): when no vessel_econ_df is
    # supplied, select bio vessels from the NON-newfuel pool (largest power
    # first — same rule as the economic layer) and set their tank blend to the
    # fuel's physical limit gamma. share_arr is the per-vessel mixing ratio:
    # 1.0 for dedicated new-fuel vessels, gamma for bio vessels, 0 otherwise.
    if vessel_econ_df is None and bio_adopt is not None:
        share_arr = np.zeros(n)
        bio_gamma_s = float(bio_gamma if bio_gamma is not None else 1.0)
        if float(bio_adopt) > 0 and bio_type != "MGO" and bio_gamma_s > 0:
            pool = np.where(~is_newfuel)[0]
            k = min(int(round(len(pool) * float(bio_adopt))), len(pool))
            if k > 0:
                order = pool[np.argsort(-power[pool])]
                share_arr[order[:k]] = bio_gamma_s

    base_lhv_v = np.where(fuel_type == "HFO", FUEL_DATABASE["HFO"][0],
                          np.where(fuel_type == "GASOLINE", FUEL_DATABASE["GASOLINE"][0], _LHV_BASE_MGO))
    lhv_eff = base_lhv_v.copy()
    sfc_label = np.where(fuel_type == "MDO", "MGO", fuel_type).astype(object)
    SFR_m_move_eff = SFR_m_move.copy()
    SFR_m_work_eff = SFR_m_work.copy()
    SFR_a_eff = SFR_a.copy()

    # ---- B. Dedicated new-fuel vessels (100% new fuel, no blending) ----
    if np.any(is_newfuel) and newfuel_type != "MGO":
        new_lhv = get_fuel_lhv(newfuel_type)
        lhv_ratio_new = base_lhv_v / max(new_lhv, 0.01)
        SFR_m_move_eff = np.where(is_newfuel, SFR_m_move * lhv_ratio_new, SFR_m_move_eff)
        SFR_m_work_eff = np.where(is_newfuel, SFR_m_work * lhv_ratio_new, SFR_m_work_eff)
        SFR_a_eff      = np.where(is_newfuel, SFR_a * lhv_ratio_new, SFR_a_eff)
        lhv_eff        = np.where(is_newfuel, new_lhv, lhv_eff)
        sfc_label      = np.where(is_newfuel, newfuel_type, sfc_label)

    # ---- A. Biofuel blend on non-renewed vessels ----
    is_bio_blend = (~is_newfuel) & (share_arr > 0)
    if np.any(is_bio_blend):
        # per-vessel BASE LHV matching the ECONOMIC layer and ghg_lca fuel
        # rules (TP→HFO, small APW→GASOLINE [Prior_Matrix LHV_GASOLINE=44.0],
        # else MGO) — blend and SFR ratio use the vessel's OWN base fuel, so
        #   LHV_blend = (1−s)·LHV_base + s·LHV_bio
        #   SFR_blend = SFR_base · LHV_base / LHV_blend
        # holds per vessel (2026-09-04 consistency fix).
        base_lhv_v = np.where(fuel_type == "HFO", FUEL_DATABASE["HFO"][0],
                              np.where(fuel_type == "GASOLINE",
                                       ghg_lca.get_best(pm_dict, "LHV_GASOLINE", 44.0),
                                       _LHV_BASE_MGO))
        bio_lhv = get_fuel_lhv(bio_type)
        blend_lhv = (1.0 - share_arr) * base_lhv_v + share_arr * bio_lhv
        lhv_ratio_blend = base_lhv_v / np.maximum(blend_lhv, 0.01)
        SFR_m_move_eff = np.where(is_bio_blend, SFR_m_move * lhv_ratio_blend, SFR_m_move_eff)
        SFR_m_work_eff = np.where(is_bio_blend, SFR_m_work * lhv_ratio_blend, SFR_m_work_eff)
        SFR_a_eff      = np.where(is_bio_blend, SFR_a * lhv_ratio_blend, SFR_a_eff)
        lhv_eff        = np.where(is_bio_blend, blend_lhv, lhv_eff)
        sfc_label      = np.where(is_bio_blend,
                                  np.char.add(np.char.add(bio_type, "_B"),
                                              (share_arr * 100).astype(int).astype(str)),
                                  sfc_label)
    SFR_m_move, SFR_m_work, SFR_a = SFR_m_move_eff, SFR_m_work_eff, SFR_a_eff

    # ---- FC lookup (engine efficiency correction) ----
    fc_lu = {
        1950:1.21,1951:1.21,1952:1.20,1953:1.20,1954:1.20,1955:1.20,
        1956:1.20,1957:1.20,1958:1.20,1959:1.19,1960:1.19,1961:1.19,1962:1.19,
        1963:1.18,1964:1.18,1965:1.18,1966:1.18,1967:1.17,1968:1.16,1969:1.16,
        1970:1.15,1971:1.14,1972:1.14,1973:1.13,1974:1.12,1975:1.11,1976:1.11,
        1977:1.10,1978:1.09,1979:1.09,1980:1.08,1981:1.07,1982:1.07,1983:1.06,
        1984:1.06,1985:1.05,1986:1.05,1987:1.04,1988:1.04,1989:1.04,1990:1.03,
        1991:1.03,1992:1.03,1993:1.02,1994:1.02,1995:1.02,1996:1.01,1997:1.01,
        1998:1.01,1999:1.00,2000:1.00,2001:1.00,2002:1.00,2003:1.00,2004:0.99,
        2005:0.99,2006:0.99,2007:0.99,2008:0.99,2009:0.99,2010:0.99,2011:0.99,
        2012:0.99,2013:0.99,2014:0.99,2015:0.99,2016:0.99,
    }
    fc = np.ones(n)
    for y, val in fc_lu.items():
        fc[eng_vintage == y] = val
    fc[eng_vintage < 1950] = 1.21
    fc[eng_vintage > 2016] = 0.99

    # ---- Emission factors (TWO-PATH) ----
    EF_CO2_MDO = ghg_lca.get_best(pm_dict, "EF_CO2_MDO", 3.206)
    EF_CO2_HFO = ghg_lca.get_best(pm_dict, "EF_CO2_HFO", 3.114)
    EF_CO2_GAS = ghg_lca.get_best(pm_dict, "EF_CO2_Gasoline", 3.158)
    ef_co2 = np.where(fuel_type == "HFO", EF_CO2_HFO,
                      np.where(fuel_type == "GASOLINE", EF_CO2_GAS, EF_CO2_MDO))
    ef_co2_eff = ef_co2.copy()
    # B. new-fuel vessels: 100% new-fuel EF (biogenic/zero-carbon fuels = 0)
    if np.any(is_newfuel) and newfuel_type != "MGO":
        ef_co2_eff = np.where(is_newfuel, get_fuel_ef_co2(newfuel_type), ef_co2_eff)
    # A. biofuel blend on non-renewed vessels: blend-weighted EF
    if np.any(is_bio_blend):
        bio_ef_co2 = get_fuel_ef_co2(bio_type)
        ef_co2_eff = np.where(is_bio_blend,
                              (1.0 - share_arr) * ef_co2 + share_arr * bio_ef_co2,
                              ef_co2_eff)
    ef_co2 = ef_co2_eff

    # CH4 EF (g/kWh)
    ch4_main = np.where(engine_type == "SSD",
                        ghg_lca.get_best(pm_dict, "EF_CH4_SSD", 0.010),
                        ghg_lca.get_best(pm_dict, "EF_CH4_MSD", 0.010))
    ch4_aux  = ghg_lca.get_best(pm_dict, "EF_CH4_AUX", 0.010)
    GWP_CH4  = ghg_lca.get_best(pm_dict, "GWP_CH4_100YR", 28.5)

    # N2O EF (g/kWh)
    n2o_main = np.where(engine_type == "SSD",
                        np.where(fuel_type == "HFO",
                                 ghg_lca.get_best(pm_dict, "EF_N2O_SSD_HFO", 0.031),
                                 ghg_lca.get_best(pm_dict, "EF_N2O_SSD_MDO", 0.030)),
                        ghg_lca.get_best(pm_dict, "EF_N2O_MSD_MDO", 0.030))
    n2o_aux  = ghg_lca.get_best(pm_dict, "EF_N2O_AUX_MDO", 0.036)
    GWP_N2O  = ghg_lca.get_best(pm_dict, "GWP_N2O_100YR", 273.0)

    R22_GWP = ghg_lca.get_best(pm_dict, "R22_GWP", 1810)

    # ---- Refrigerant type ----
    ref_type = _eff_ref.get("refrigerant_type",
                            refrigerant_type if refrigerant_type else "R22")
    R22_GWP = ghg_lca.get_best(pm_dict, "R22_GWP", 1810)
    R404A_GWP = 3922
    ref_gwp_map = {"R22": R22_GWP, "R404a": R404A_GWP, "LN2": 0}
    ref_gwp = ref_gwp_map.get(ref_type, R22_GWP)
    grid_ef_gCO2 = grid_ef if grid_ef is not None else _eff_ref.get("grid_ef_gCO2_kWh", 458)

    # ---- Hours (T_map scaled by per-vessel gear-specific effort multiplier) ----
    # Fleet-consolidation efficiency (2026-09-08): structural upscaling raises
    # unit catch efficiency -> eta_upsize,t = 1 - beta*S_upsize,t multiplies
    # every vessel's effective effort (beta calibrated from Small vs Large
    # catch/kW of the baseline fleet, ~0.243).
    eta_up = 1.0 - float(upsize_beta) * min(float(upsize_progress), 1.0)
    T_eff = T_map * E_final_arr * eta_up
    hm_move = (1 - alpha) * T_eff * H_main
    hm_work = alpha * T_eff * H_main
    haux    = T_eff * H_aux

    # ---- Fuel CO2 ----
    co2_move = power * LF_move * SFR_m_move * hm_move * ef_co2 * fc
    co2_work = power * LF_work * SFR_m_work * hm_work * ef_co2 * fc
    co2_aux  = power * has_aux * LF_aux * aux_ratio * SFR_a * haux * ef_co2 * fc
    fuel_co2 = co2_move + co2_work + co2_aux

    # ---- Fuel CH4 (diesel: g/kWh → tCO2e; gasoline: g/kgFuel, ghg_lca-consistent) ----
    hm_tot  = hm_move + hm_work
    lf_main_avg = np.where(hm_tot > 0,
                           (LF_move * hm_move + LF_work * hm_work) / hm_tot, 0)
    is_gas = (fuel_type == "GASOLINE")
    ch4_m = np.where(~is_gas, power * lf_main_avg * hm_tot * ch4_main / 1e6 * GWP_CH4 * fc, 0.0)
    ch4_a = np.where(~is_gas, power * has_aux * LF_aux * aux_ratio * haux * ch4_aux / 1e6 * GWP_CH4 * fc, 0.0)
    # gasoline path: CH4 = fuel_t × 1000 × EF(g/kgFuel) / 1e6 × GWP  (EPA)
    ch4_gas_ef = ghg_lca.get_best(pm_dict, "EF_CH4_GASOLINE_4STROKE", 1.5)
    fuel_total_gas = (power * LF_move * SFR_m_move * hm_move
                      + power * LF_work * SFR_m_work * hm_work) * fc
    ch4_gas = np.where(is_gas, fuel_total_gas * 1000.0 * ch4_gas_ef / 1e6 * GWP_CH4, 0.0)
    fuel_ch4 = ch4_m + ch4_a + ch4_gas

    # ---- Fuel N2O (diesel: g/kWh → tCO2e; gasoline: g/kgFuel, ghg_lca-consistent) ----
    n2o_m = np.where(~is_gas, power * lf_main_avg * hm_tot * n2o_main / 1e6 * GWP_N2O * fc, 0.0)
    n2o_a = np.where(~is_gas, power * has_aux * LF_aux * aux_ratio * haux * n2o_aux / 1e6 * GWP_N2O * fc, 0.0)
    n2o_gas_ef = ghg_lca.get_best(pm_dict, "EF_N2O_GASOLINE", 0.04)
    n2o_gas = np.where(is_gas, fuel_total_gas * 1000.0 * n2o_gas_ef / 1e6 * GWP_N2O, 0.0)
    fuel_n2o = n2o_m + n2o_a + n2o_gas

    # ---- WtT (Well-to-Tank) upstream — TWO-PATH (2026-09-04) ----
    # Compute total fuel consumption from existing SFR × hours × power
    fuel_t_move = power * LF_move * SFR_m_move * hm_move * fc   # tonnes fuel
    fuel_t_work = power * LF_work * SFR_m_work * hm_work * fc
    fuel_t_aux  = power * has_aux * LF_aux * aux_ratio * SFR_a * haux * fc
    fuel_total_t = fuel_t_move + fuel_t_work + fuel_t_aux        # tonnes fuel

    # Fuel-specific CfCH4/CfN2O are kg gas per kg fuel. Preserve the historical
    # engine-based factors for fossil vessels and the fossil fraction of a blend.
    if np.any(is_newfuel):
        _, _, cf_ch4, cf_n2o = FUEL_DATABASE[newfuel_type]
        fuel_ch4 = np.where(is_newfuel, fuel_total_t * cf_ch4 * GWP_CH4, fuel_ch4)
        fuel_n2o = np.where(is_newfuel, fuel_total_t * cf_n2o * GWP_N2O, fuel_n2o)
    if np.any(is_bio_blend):
        _, _, cf_ch4, cf_n2o = FUEL_DATABASE[bio_type]
        fuel_ch4 = np.where(is_bio_blend, (1 - share_arr) * fuel_ch4 + share_arr * fuel_total_t * cf_ch4 * GWP_CH4, fuel_ch4)
        fuel_n2o = np.where(is_bio_blend, (1 - share_arr) * fuel_n2o + share_arr * fuel_total_t * cf_n2o * GWP_N2O, fuel_n2o)

    # base WtT per vessel (Excel-overridden; GASOLINE keeps ecoinvent)
    wtt_mdo = _wtt_kg_per_kg("MDO", pm_dict)
    wtt_hfo = _wtt_kg_per_kg("HFO", pm_dict)
    wtt_gas = ghg_lca.get_best(pm_dict, "EF_WTT_GASOLINE", 0.535)
    wtt_base_arr = np.where(fuel_type == "HFO", wtt_hfo,
                            np.where(fuel_type == "GASOLINE", wtt_gas, wtt_mdo))
    wtt_ef_eff = wtt_base_arr.copy()
    # B. new-fuel vessels: WtT of the new fuel (Excel; e-NH3 = 0)
    if np.any(is_newfuel) and newfuel_type != "MGO":
        if newfuel_type in ("H2_Green", "NH3_Green"):
            # grid-electrolysis e-fuels: WtT = grid EF x electricity per kg
            # (H2: 50 kWh/kg -> grid x 50/1000 kgCO2/kg fuel; NH3: 9.3 kWh/kg
            # -> grid x 9.3/1000). 2026-09-11, mirrors Fig4e panel_e.
            _g = float(grid_ef) if grid_ef is not None else 458.0
            wtt_new = (_g * 50.0 / 1000.0 if newfuel_type == "H2_Green"
                       else _g * 9.3 / 1000.0)
        else:
            wtt_new = _wtt_kg_per_kg(newfuel_type, pm_dict)
        wtt_ef_eff = np.where(is_newfuel, wtt_new, wtt_ef_eff)
    # A. biofuel blend: blend-weighted WtT (FAME 20.8 / HVO 14.9 gCO2eq/MJ)
    if np.any(is_bio_blend):
        wtt_bio = _wtt_kg_per_kg(bio_type, pm_dict)
        wtt_ef_eff = np.where(is_bio_blend,
                              (1.0 - share_arr) * wtt_base_arr + share_arr * wtt_bio,
                              wtt_ef_eff)
    # WtT EF is kgCO2eq/kg fuel = tCO2eq/tonne fuel
    fuel_wtt = fuel_total_t * wtt_ef_eff  # tCO2eq

    # ---- Build (hull construction, v3-consistent: FULL cost in build year) ----
    # ghg_lca: build_annual = (age == 0) × lsw × EF_Build,  age = year − Built_Year
    built_year = np.maximum(_col("Built_Year", "Builtdate", 2000.0), 1900.0)
    age = ref_year - built_year
    build = np.where(age == 0, lsw * ef_build, 0.0)

    # ---- Maint (steel replacement, v3-consistent: every MAINT_INTERVAL=2 yrs) ----
    # ghg_lca: is_steel_maint = (age % 2 == 0) & (age >= 2)
    #          maint_annual = lsw × MAINT_RATE_STEEL(0.12) × EF_Maint
    MAINT_INTERVAL = 2
    MAINT_RATE_STEEL = 0.12
    is_steel_maint = (age % MAINT_INTERVAL == 0) & (age >= 2)
    maint = is_steel_maint * lsw * MAINT_RATE_STEEL * ef_maint

    # ---- Gear (net/hook construction, v3-consistent: replace every gear_lifespan,
    #       maintenance rate in other years; PS/LL-specific material EF) ----
    # ghg_lca: gear_w = length × Gear_Intensity;
    #          is_gear_repl = (age % gear_lifespan == 0) → full; else × Gear_Maint_Rate
    gear_lifespan = np.maximum(_col("Gear_Lifespan", "Gear_Lifespan", 5.0), 1.0)
    gear_maint_rate = _col("Gear_Maint_Rate", "Gear_Maint_Rate", 0.25)
    ef_nylon = ghg_lca.get_best(pm_dict, "EMISSION_FACTOR_NYLON_PA6", 9.885)
    ef_steel_g = ghg_lca.get_best(pm_dict, "EMISSION_FACTOR_STEEL_GEAR", 3.07)
    nylon_frac = np.where(v_type == "PS",
                          ghg_lca.get_best(pm_dict, "GEAR_MATERIAL_NYLON_PS", 0.739),
                          ghg_lca.get_best(pm_dict, "GEAR_MATERIAL_NYLON_LL", 0.739))
    steel_frac = 1.0 - nylon_frac
    ef_gear_arr = nylon_frac * ef_nylon + steel_frac * ef_steel_g
    gear_w = length * gear_int
    is_gear_repl = (age % gear_lifespan == 0)
    gear = (is_gear_repl * gear_w * ef_gear_arr
            + (~is_gear_repl) * gear_w * gear_maint_rate * ef_gear_arr)

    # ---- Refrig (R22/R404a leak or LN2 upstream) ----
    if ref_type == "LN2":
        # LN2 upstream: E = M * SEC * EF_grid
        # M = total catch per vessel × mass ratio (kg LN2/kg fish)
        # SEC = 0.56 kWh/kg LN2, mass_ratio = 1.15 kg/kg
        # Approximate catch per vessel from power share
        catch_proxy = power * T_eff * H_main / 24.0 * 0.005  # rough t/vessel/yr
        ln2_kg = catch_proxy * 1000 * 1.15                 # kg LN2 needed
        # Units: kg × kWh/kg × g/kWh = g CO2 → /1e6 → t CO2 (matches t-scale of
        # fuel terms; previous /1000 left kg CO2 and inflated LN2 GHG 1000×)
        refrig = ln2_kg * 0.56 * grid_ef_gCO2 / 1e6
    else:
        refrig = r22_leak * ref_gwp / 1000.0

    # ---- Bait (LL only) ----
    hooks_per_day = ghg_lca.get_best(pm_dict, "HOOKS_PER_DAY", 3000)
    bait_wt = ghg_lca.get_best(pm_dict, "BAIT_WEIGHT_PER_HOOK_KG", 0.1)
    ef_bait = ghg_lca.get_best(pm_dict, "EMISSION_FACTOR_BAIT", 1.606)
    bait = np.where(v_type == "LL",
                    T_eff * (H_main / 24.0) * hooks_per_day * bait_wt * ef_bait / 1000.0,
                    0.0)

    # ---- Total ----
    df["GHG_Emissions"] = (fuel_co2 + fuel_ch4 + fuel_n2o + fuel_wtt +
                           build + maint + gear + refrig + bait)
    df["GHG_Fuel_CO2"] = fuel_co2
    df["GHG_Fuel_CH4"] = fuel_ch4
    df["GHG_Fuel_N2O"] = fuel_n2o
    df["GHG_Fuel_WtT"] = fuel_wtt
    df["GHG_Build"] = build
    df["GHG_Refrig"] = refrig
    # ---- share5: per-vessel E_tuna correction (2026-09-18) ------------------
    # Applied to every emission component and the total, exactly as ghg_lca does
    # for Base_1-4; (flag, gear) pairs absent from the lookup (support vessels,
    # multi-flag entries) keep a factor of 1.0.
    _fac = _share5_factor_map(ref_year)
    if _fac:
        _key = pd.Series(list(zip(df["Flag"].astype(str), df["VesselType"].astype(str))),
                         index=df.index)
        _sf = _key.map(_fac).fillna(1.0).to_numpy(dtype=float)
        df["GHG_Emissions"] = df["GHG_Emissions"] * _sf
        for _c in ["GHG_Fuel_CO2", "GHG_Fuel_CH4", "GHG_Fuel_N2O", "GHG_Fuel_WtT",
                   "GHG_Build", "GHG_Refrig"]:
            df[_c] = df[_c] * _sf
    df["Fuel_Label"] = sfc_label
    df["LHV_MJ_kg"] = lhv_eff
    df["SFR_main_move_eff"] = SFR_m_move
    df["SFR_main_work_eff"] = SFR_m_work

    return df


# =============================================================================
# 3. Build Template Pool
# =============================================================================
def build_template_pool(fleet_df, modern_year=2015):
    """Build cloning template pool from modern vessels."""
    major_rfmos = ["WCPFC", "IATTC", "ICCAT", "IOTC", "CCSBT"]
    pool = fleet_df[
        (fleet_df["Built_Year"] >= modern_year) &
        (fleet_df["Organization"].isin(major_rfmos))
    ].copy()
    if len(pool) < 100:
        pool = fleet_df[fleet_df["Organization"].isin(major_rfmos)].copy()
    print(f"  Template pool: {len(pool):,} vessels (built >= {modern_year})")
    return pool


# =============================================================================
# 4. Core Pipeline: One-Year Fleet Dynamics
# =============================================================================
_CAPACITY_BUFFER = 0.10      # γ: keep 10% effort surplus above demand
_CAP_TMAP_CACHE = None       # {(org, gear): Σ T_map of the 2025 baseline fleet}
_CAP_E0_CACHE = None         # {(org, s, gear): baseline effort (Base3 window)}
_CAP_MECO_CACHE = {}         # {(scenario, qt, year, tc_rounded, s): Meco}


def _cap_meco(scen, qt, year, tc, s):
    scen_key = tuple(sorted(scen.items())) if isinstance(scen, dict) else scen
    qt_key = tuple(sorted(qt.items())) if isinstance(qt, dict) else qt
    key = (scen_key, qt_key, int(year), round(float(tc), 6), s)
    if key not in _CAP_MECO_CACHE:
        _CAP_MECO_CACHE[key] = _meco_of_species(scen, qt, year, tc, s)
    return _CAP_MECO_CACHE[key]


def _cap_e0():
    """Baseline effort per (org, s, gear) — Base3 window (fig5_allocation)."""
    global _CAP_E0_CACHE
    if _CAP_E0_CACHE is None:
        try:
            import fig5_allocation as _fa
            _CAP_E0_CACHE = _fa.build_shares()["E0"]
        except Exception:
            _CAP_E0_CACHE = {}
    return _CAP_E0_CACHE


def _cap_base_tmap(fleet):
    """Effort reference from this simulation's explicit baseline (no cross-run cache)."""
    g = fleet[fleet.VesselType.isin(["PS", "LL"])].groupby(
        ["Organization", "VesselType"])["T_map"].sum()
    return {(str(o), gear): float(v) for (o, gear), v in g.items()}


def _dynamic_capacity_retire(fleet_df, scenario_params, year, gamma=0.10,
                             base_frame=None):
    """Boolean mask (index-aligned) of vessels to retire under dynamic
    capacity balance (retirement_scenario=3). Per (Organization, gear):
    retire the SURPLUS effort S_rel − D_rel − γ, oldest vessels first
    (age is the high-emission proxy), never below the effort demand.
    base_frame = the pre-retirement fleet (2025 baseline when first called)
    used to seed the Σ T_map reference."""
    coupling = scenario_params.get('_fishery_state')
    if coupling is not None:
        return coupling.retire_mask(fleet_df, gamma=gamma)
    sch = scenario_params.get("schaefer_scenario", "C2024")
    qt = scenario_params.get("quota_type", "C")
    tc = float(scenario_params.get("tech_creep", 0.0))
    e0 = _cap_e0()
    base_tmap = _cap_base_tmap(base_frame if base_frame is not None else fleet_df)
    spp = ["SKJ", "YFT", "BET", "ALB", "SBT"]
    mask = np.zeros(len(fleet_df), dtype=bool)
    for (o, g), idx in fleet_df[fleet_df.VesselType.isin(["PS", "LL"])] \
            .groupby(["Organization", "VesselType"]).groups.items():
        o = str(o)
        denom = sum(e0.get((o, s, g), 0.0) * _cap_meco(sch, qt, 2025, tc, s) for s in spp)
        if denom <= 0:
            continue
        d_rel = sum(e0.get((o, s, g), 0.0) * _cap_meco(sch, qt, year, tc, s)
                    for s in spp) / denom
        baseline_t = base_tmap.get((o, g), 0.0)
        if baseline_t <= 0:
            continue
        s_rel = float(fleet_df.loc[idx, "T_map"].sum()) / baseline_t
        surplus = s_rel - d_rel - gamma
        if surplus <= 0:
            continue
        target_tmap = surplus * base_tmap.get((o, g), 0.0)
        grp = fleet_df.loc[idx].sort_values("Age", ascending=False)
        # Whole vessels only: do not remove the vessel that would exceed the surplus.
        count = int(np.searchsorted(grp["T_map"].cumsum().to_numpy(), target_tmap, side="right"))
        mask[fleet_df.index.get_indexer(grp.index[:count])] = True
    return mask


def process_fleet_dynamics_pipeline(
    active_fleet_df, template_pool_df, pm_dict,
    scenario_params, current_year=2026, rng=None, capacity_baseline=None
):
    """
    Simulate one year of fleet dynamics.

    Phase 1: Capacity expansion via nested-probability cloning
    Phase 2: Retirement scenario switch (1=natural, 2=rebuild, 3=natural+forced)
    Phase 3: GHG-power-intensity-based alternative-fuel targeting
    """
    if rng is None:
        rng = np.random.RandomState(42)

    cap_growth             = scenario_params.get("capacity_growth_rate", 0.02)
    max_lifespan           = scenario_params.get("max_lifespan", 30)
    retirement_scenario    = scenario_params.get("retirement_scenario", 2)
    forced_retirement_rate = scenario_params.get("forced_retirement_rate", 0.02)  # only for scenario 3
    # Annual rates from 2050 targets (compound over 25 years)
    yrs_to_2050 = 2050 - current_year + 1
    if yrs_to_2050 > 0:
        consol_type = scenario_params.get("consolidation_type", 0)
        # 0=none, 1=50%→large by 2050, 2=100%→large by 2050
        consol_targets = {0: 0.0, 1: 0.50, 2: 1.00}
        consol_shift = (1 + consol_targets[consol_type]) ** (1/25) - 1 if consol_type > 0 else 0.0

        target_type = scenario_params.get("alt_fuel_target_type", 0)
        # 0=none, 1=30% by 2050, 2=60% by 2050
        target_shares = {0: 0.02, 1: 0.30, 2: 0.60}  # type 0 keeps default 2%
        target_share = target_shares[target_type]
        alt_fuel_target_rate = (1 + target_share) ** (1/25) - 1 if target_share > 0 else 0.0
    else:
        consol_shift = 0.0
        alt_fuel_target_rate = 0.02

    major_rfmos = ["WCPFC", "IATTC", "ICCAT", "IOTC", "CCSBT"]

    # =====================================================================
    # PHASE 1: Capacity Expansion via Cloning
    # =====================================================================
    print(f"  [Phase 1] Capacity expansion (growth={cap_growth:+.1%})...")

    total_kW = active_fleet_df["Power_kW"].sum()
    new_capacity_kW = total_kW * max(cap_growth, 0.0)

    # Layer 1: RFMO power distribution
    rfmo_power = active_fleet_df[
        active_fleet_df["Organization"].isin(major_rfmos)
    ].groupby("Organization")["Power_kW"].sum()
    rfmo_prob = (rfmo_power / rfmo_power.sum()).to_dict()

    # Layer 2: Size-class distribution per RFMO
    size_prob = {}
    for org in major_rfmos:
        org_fleet = active_fleet_df[active_fleet_df["Organization"] == org]
        n_small = (org_fleet["Size_Class"] == "Small").sum()
        n_large = (org_fleet["Size_Class"] == "Large").sum()
        total_n = n_small + n_large
        if total_n == 0:
            size_prob[org] = {"Small": 0.5, "Large": 0.5}
        else:
            p_large = np.clip(n_large / total_n + consol_shift, 0.0, 1.0)
            size_prob[org] = {"Small": 1.0 - p_large, "Large": p_large}

    # Cloning loop
    accumulated_newbuild_kW = 0.0
    new_vessels = []
    rfmo_list = list(rfmo_prob.keys())
    rfmo_vals = list(rfmo_prob.values())

    while accumulated_newbuild_kW < new_capacity_kW and len(new_vessels) < 10000:
        org = rng.choice(rfmo_list, p=rfmo_vals)
        size_key = "Large" if rng.random() < size_prob[org]["Large"] else "Small"
        candidates = template_pool_df[
            (template_pool_df["Organization"] == org) &
            (template_pool_df["Size_Class"] == size_key)
        ]
        if len(candidates) == 0:
            candidates = template_pool_df[template_pool_df["Organization"] == org]
        if len(candidates) == 0:
            candidates = template_pool_df[template_pool_df["Size_Class"] == size_key]
        if len(candidates) == 0:
            candidates = template_pool_df

        clone = candidates.sample(1, random_state=rng.randint(0, 2**31 - 1)).copy()
        clone["Built_Year"] = current_year
        clone["Effective_Hull_Year"] = current_year
        clone["Engine_Vintage"] = current_year
        clone["NewFuel_Flag"] = 0
        clone["Vessel_ID"] = active_fleet_df["Vessel_ID"].max() + len(new_vessels) + 1
        accumulated_newbuild_kW += clone["Power_kW"].values[0]
        new_vessels.append(clone)

    # Merge
    base_cols = [c for c in active_fleet_df.columns if c not in ("Age", "cumul_kW")]
    active_clean = active_fleet_df[base_cols]
    if new_vessels:
        new_fleet = pd.concat(new_vessels, ignore_index=True)
        # Ensure new vessels have all columns (fill missing with NaN)
        for c in base_cols:
            if c not in new_fleet.columns:
                new_fleet[c] = np.nan
        expanded_fleet = pd.concat(
            [active_clean, new_fleet[base_cols]], ignore_index=True)
    else:
        expanded_fleet = active_clean.copy()

    expanded_fleet["Age"] = current_year - expanded_fleet["Built_Year"]
    n_new = len(new_vessels)
    print(f"    Built {n_new} new vessels ({accumulated_newbuild_kW:,.0f} kW)")

    # =====================================================================
    # Phase 1b: FLEET CONSOLIDATION / LARGE-SCALE TRANSITION (2026-09-08)
    # The SMALLEST vessels of each (Organization x VesselType) group are
    # retired and rebuilt from the group's OWN large templates at SAME total
    # engine power (structural upscaling: fewer, larger vessels, org x gear
    # structure preserved). The efficiency gain is NOT injected here — it is
    # applied at the effort layer as eta_upsize,t = 1 - beta*S_t on T_eff
    # (unit catch efficiency rises -> less effort per unit catch -> less
    # fuel -> less GHG). consolidation_type: 1 = 50% by 2050, 2 = 100%.
    # =====================================================================
    upscale_type = int(scenario_params.get("consolidation_type", 0))
    upscale_targets = {0: 0.0, 1: 0.50, 2: 1.00}
    up_target = upscale_targets.get(upscale_type, 0.0)
    if up_target > 0 and len(expanded_fleet):
        loa = pd.to_numeric(expanded_fleet["LOA"], errors="coerce").fillna(20.0)
        yrs_left = 2050 - current_year + 1
        retire_pos, up_new = [], []
        next_id = int(expanded_fleet["Vessel_ID"].max()) + 1
        for (o, g), idx in expanded_fleet.groupby(["Organization", "VesselType"], sort=False).groups.items():
            gi = sorted(idx, key=lambda i: loa[i])
            n_replace = max(0, min(int(round(len(gi) * up_target / 25.0)), len(gi) - 1))
            if n_replace == 0:
                continue
            retired = gi[:n_replace]
            remaining = gi[n_replace:]
            threshold = float(loa[remaining].quantile(0.75))
            template = expanded_fleet.loc[[i for i in remaining if loa[i] >= threshold]]
            power_budget = float(expanded_fleet.loc[retired, "Power_kW"].sum())
            retire_pos.extend(retired)
            used = 0.0
            while used < power_budget - 1e-8:
                clone = template.iloc[[rng.randint(len(template))]].copy()
                # Representative replacement engine capacity; hull remains a large template.
                clone["Power_kW"] = min(float(clone["Power_kW"].iloc[0]), power_budget - used)
                clone["Built_Year"] = current_year
                clone["Effective_Hull_Year"] = current_year
                clone["Engine_Vintage"] = current_year
                clone["NewFuel_Flag"] = 0
                clone["Vessel_ID"] = next_id
                next_id += 1
                used += float(clone["Power_kW"].iloc[0])
                up_new.append(clone)
        if retire_pos:
            before_power = expanded_fleet.groupby(["Organization", "VesselType"])["Power_kW"].sum()
            expanded_fleet = pd.concat([expanded_fleet.drop(retire_pos), *up_new], ignore_index=True)
            after_power = expanded_fleet.groupby(["Organization", "VesselType"])["Power_kW"].sum()
            if not np.allclose(before_power, after_power.reindex(before_power.index), rtol=1e-12, atol=1e-7):
                raise AssertionError("Consolidation changed org x gear capacity")
            expanded_fleet["Age"] = current_year - expanded_fleet["Built_Year"]
            print(f"    [Upsize] retired {len(retire_pos)} smallest -> built {len(up_new)} (group power conserved)")

    # =====================================================================
    # PHASE 2: Retirement Mode Switch
    # =====================================================================
    print(f"  [Phase 2] Retirement (scenario={retirement_scenario}, lifespan={max_lifespan}yr)...")

    if retirement_scenario == 1:
        survived = expanded_fleet[expanded_fleet["Age"] < max_lifespan].copy()
        n_retired = len(expanded_fleet) - len(survived)
        print(f"    Scenario 1: {n_retired} retired (Age >= {max_lifespan})")

    elif retirement_scenario == 2:
        # Scenario 2: Rebuild ALL end-of-life vessels (ghg_lca GHG logic)
        overage = expanded_fleet["Age"] >= max_lifespan
        n_overage = overage.sum()
        expanded_fleet.loc[overage, "Built_Year"] = current_year
        expanded_fleet.loc[overage, "Effective_Hull_Year"] = current_year
        expanded_fleet.loc[overage, "Engine_Vintage"] = current_year
        expanded_fleet.loc[overage, "Age"] = 0
        survived = expanded_fleet.copy()
        print(f"    Scenario 2: {n_overage} rebuilt, 0 retired")

    elif retirement_scenario == 3:
        # ---- DYNAMIC CAPACITY BALANCE + Overage REPLACEMENT (2026-09-05) ----
        # 1) OVERAGE vessels (Age ≥ lifespan) retire — but their power is
        #    replaced by equal-power LOW-CARBON newbuilds (template clones with
        #    Engine_Vintage = year → they flow into the newfuel/blend paths),
        #    so the fleet never shrinks to a "stopped-fishery" state.
        # 2) Any remaining capacity SURPLUS (per Organization×Gear,
        #    S_rel − D_rel − γ, demand driven by Schaefer Meco) is retired,
        #    oldest vessels first, never below the effort demand.
        overage = expanded_fleet["Age"] >= max_lifespan
        n_over = int(overage.sum())
        keep = expanded_fleet[~overage].copy()
        base_cols3 = [c for c in expanded_fleet.columns if c != "Age"]
        over = expanded_fleet[overage]
        if len(over) > 0:
            # effort-conserving replacement per (Organization, Gear): each
            # org×gear's retired Σ T_map is exactly replaced by newbuilds that
            # KEEP the same Organization / VesselType and carry the retired
            # group's mean T_map. (Global replacement shuffled org/gear and
            # made some org×gear temporarily surplus → mis-retired.)
            reps = []
            next_id = int(expanded_fleet["Vessel_ID"].max()) + 1
            for (o, g), grp in over.groupby(["Organization", "VesselType"]):
                pool = template_pool_df[(template_pool_df["VesselType"] == g) &
                                        (template_pool_df["Organization"] == o)]
                if pool.empty:
                    pool = grp
                # One replacement per retired hull; batch sampling avoids a float-sum
                # stopping error and thousands of one-row DataFrame copies.
                cand = pool.iloc[rng.randint(0, len(pool), size=len(grp))].copy()
                cand["T_map"] = float(grp["T_map"].sum()) / len(grp)
                cand["Power_kW"] *= float(grp["Power_kW"].sum()) / cand["Power_kW"].sum()
                cand["Built_Year"] = current_year
                cand["Effective_Hull_Year"] = current_year
                cand["Engine_Vintage"] = current_year
                cand["NewFuel_Flag"] = 0
                cand["Vessel_ID"] = np.arange(next_id, next_id + len(cand))
                next_id += len(cand)
                reps.append(cand)
            rdf = pd.concat(reps, ignore_index=True) if reps else pd.DataFrame()
            for c_ in base_cols3:
                if c_ not in rdf.columns:
                    rdf[c_] = np.nan
            survived = pd.concat([keep[base_cols3], rdf[base_cols3]],
                                 ignore_index=True)
            survived["Age"] = current_year - survived["Built_Year"]
            print(f"    Scenario 3: {n_over} overage retired, "
                  f"{len(rdf)} low-carbon replacements "
                  f"(Σ T_map conserved per org×gear)")
        else:
            survived = keep.copy()
        retire_idx = _dynamic_capacity_retire(
            survived, scenario_params, current_year, gamma=_CAPACITY_BUFFER,
            base_frame=capacity_baseline if capacity_baseline is not None else active_fleet_df)
        n_dyn = int(retire_idx.sum())
        dyn_tmap = float(survived.loc[retire_idx, "T_map"].sum())
        survived = survived[~retire_idx].copy()
        print(f"    Scenario 3: +{n_dyn} dynamic-capacity retired "
              f"(org×gear surplus removal)")

    else:
        raise ValueError(f"Unknown retirement_scenario: {retirement_scenario}")

    survived_fleet = survived.copy()
    engine_cycle = ghg_lca.get_best(pm_dict, "LIFESPAN_ENGINE", 10)
    replace_engine = current_year - survived_fleet["Engine_Vintage"] >= engine_cycle
    survived_fleet.loc[replace_engine, "Engine_Vintage"] = current_year
    # Refresh SFC after either a hull or engine renewal, using engine age rather than hull age.
    era = np.where(survived_fleet["Engine_Vintage"] <= 1983, 1983,
                   np.where(survived_fleet["Engine_Vintage"] <= 2000, 2000, 2001))
    for (eng, fuel, vintage), positions in survived_fleet.groupby(
            ["Engine_Type", "Fuel_Type", pd.Series(era, index=survived_fleet.index)]).groups.items():
        if eng == "GASOLINE":
            continue
        base_sfc = ghg_lca.get_sfcbase(eng, fuel, vintage, pm_dict)
        for out_col, lf_col in [("SFR_main_move", "LF_move"), ("SFR_main_work", "LF_work"), ("SFR_aux", "LF_aux")]:
            survived_fleet.loc[positions, out_col] = ghg_lca.apply_sfoc_formula(
                base_sfc, survived_fleet.loc[positions, lf_col], pm_dict) / 1e6

    # ---- Vessel-level bio-economic effort (2025–2050, user directive 2026-08-26) ----
    # Meco (ecological) and M_econ (economic) are computed PER VESSEL, then
    # aggregated to fleet/gear level — never a fleet-wide M_econ first.
    sch_scen = scenario_params.get("schaefer_scenario", "MSY_100")
    qt_raw = scenario_params.get("quota_type", "C")
    # per-species mixed quota: keep the dict ({"SKJ": "C", ...}); str() would
    # destroy it (2026-09-08)
    quota_type = qt_raw if isinstance(qt_raw, dict) else str(qt_raw)
    coupling = scenario_params.get('_fishery_state')
    gear_blended = (get_gear_blended_params(sch_scen, current_year, quota_type=quota_type)
                    if coupling is None else
                    {g: {'quota_ratio': 1.0, 'biomass_ratio': 1.0} for g in ('PS', 'LL')})
    weo = scenario_params.get("WEO", "APS")
    tc_yr = float(scenario_params.get("tech_creep", 0.0))
    fo_pairs = list(zip(survived_fleet["Flag"].astype(str),
                        survived_fleet["Organization"].astype(str)))
    meco_eff_map = (get_meco_eff_map(sch_scen, quota_type, current_year, tc_yr,
                                    flags_orgs=fo_pairs) if coupling is None else
                    {pair: 1.0 for pair in fo_pairs})
    econ_df = compute_vessel_econ_effort(survived_fleet, weo, current_year,
                                         gear_blended, scenario_params,
                                         meco_eff_map=meco_eff_map)
    if coupling is not None:
        econ_df = coupling.resolve(survived_fleet, econ_df)
        for gear in ('PS', 'LL'):
            ratios = [coupling.b[s] / coupling.b0[s] for s in coupling.stocks.index]
            gear_blended[gear]['biomass_ratio'] = float(np.mean(ratios))

    # ---- Fleet-average effort_mult (effort-weighted aggregates for history) ----
    w_meco = econ_df["Meco"].sum()
    e_ps = survived_fleet.loc[survived_fleet["VesselType"] == "PS", "VesselType"]
    e_ll = survived_fleet.loc[survived_fleet["VesselType"] == "LL", "VesselType"]
    effort_mult = {
        "Meco": float(econ_df["Meco"].mean()),
        "Cost_Ratio": float((econ_df["Meco"] * econ_df["Cost_Ratio"]).sum() / max(w_meco, 1e-9)),
        "M_econ": float((econ_df["Meco"] * econ_df["M_econ_raw"]).sum() / max(w_meco, 1e-9)),
        "M_econ_realized": float(econ_df["E_final"].sum() / max(w_meco, 1e-9)),
        "E_final": float(econ_df["E_final"].mean()),
        "E_final_PS": float(econ_df.loc[e_ps.index, "E_final"].mean()) if len(e_ps) else 1.0,
        "E_final_LL": float(econ_df.loc[e_ll.index, "E_final"].mean()) if len(e_ll) else 1.0,
        "bio_ratio_PS": gear_blended["PS"]["biomass_ratio"],
        "bio_ratio_LL": gear_blended["LL"]["biomass_ratio"],
        "base_USD_per_MJ": float(econ_df["Baseline_USD_per_MJ"].iloc[0]),
        "curr_USD_per_MJ": float((econ_df["Meco"] * econ_df["Current_USD_per_MJ"]).sum() / max(w_meco, 1e-9)),
        "eta_treatment": "vessel-level (η_k cancels ICE-to-ICE)",
    }
    print(f"    Effort PS:  bio={gear_blended['PS']['biomass_ratio']:.3f}, "
          f"E_final_PS={effort_mult['E_final_PS']:.3f}")
    print(f"    Effort LL:  bio={gear_blended['LL']['biomass_ratio']:.3f}, "
          f"E_final_LL={effort_mult['E_final_LL']:.3f}")
    print(f"      P/LHV: base={effort_mult['base_USD_per_MJ']:.4f} $/MJ, "
          f"curr={effort_mult['curr_USD_per_MJ']:.4f} $/MJ, "
          f"M_econ_raw_wtd={effort_mult['M_econ']:.4f}, "
          f"M_econ_realized={effort_mult['M_econ_realized']:.4f}")

    # ---- Recompute GHG for survivors (Built_Year/Engine_Vintage may have changed) ----
    # TWO-PATH fuel transition (2026-09-11): bio ADOPTION (drop-in, fleet
    # share x blend-limit gamma) + new-fuel renewal (device-dependent).
    bio_type_t = scenario_params.get("biofuel_type",
                                     scenario_params.get("alternative_fuel_type", "FAME"))
    bio_rate_t = get_biofuel_adoption_rate(scenario_params, current_year)
    bio_gamma_t = get_biofuel_blend_limit(scenario_params, bio_type_t)
    newfuel_type_t = scenario_params.get("newfuel_type",
                                         scenario_params.get("newbuild_fuel", "MGO"))
    newfuel_rate_t = get_newfuel_renewal_rate(scenario_params, current_year)
    # fleet-consolidation efficiency: S_t = consolidation progress 0 -> up_target
    up_t = {0: 0.0, 1: 0.50, 2: 1.00}.get(
        int(scenario_params.get("consolidation_type", 0)), 0.0)
    up_prog = up_t * min(max(current_year - 2025, 0) / 25.0, 1.0)
    up_beta = float(scenario_params.get("upsize_beta", 0.243))
    survived_fleet = compute_fleet_ghg(survived_fleet, pm_dict,
                                       ref_year=current_year,
                                       vessel_econ_df=econ_df,
                                       bio_adopt=bio_rate_t,
                                       bio_gamma=bio_gamma_t,
                                       bio_type=bio_type_t,
                                       newfuel_type=newfuel_type_t,
                                       newfuel_rate=newfuel_rate_t,
                                       refrigerant_type=scenario_params.get("refrigerant_type", "R22"),
                                       upsize_beta=up_beta,
                                       upsize_progress=up_prog,
                                       grid_ef=get_grid_ef(scenario_params.get("WEO", "APS"),
                                                           current_year))
    if coupling is not None and 'Accounting_Weight' in survived_fleet:
        survived_fleet['GHG_Emissions'] *= survived_fleet['Accounting_Weight']
    # persist the new-fuel renewal state for the NEXT year (renewed vessels
    # keep their dedicated fuel; only non-renewed vessels may be blended)
    survived_fleet["NewFuel_Flag"] = econ_df["NewFuel"].values
    # Also update GHG-power intensity
    survived_fleet["GHG_Power_Intensity"] = np.where(
        survived_fleet["Power_kW"] > 0,
        survived_fleet["GHG_Emissions"] / survived_fleet["Power_kW"], 0.0)

    n_survived = len(survived_fleet)
    total_ghg = survived_fleet["GHG_Emissions"].sum()
    print(f"    Surviving fleet: {n_survived:,} vessels, "
          f"{total_ghg/1e6:.1f} Mt GHG")

    # =====================================================================
    # PHASE 3: Alternative Fuel Targeting
    # =====================================================================
    print(f"  [Phase 3] Alternative-fuel targeting (rate={alt_fuel_target_rate:.1%})...")

    # sort WITHOUT reset_index: econ_df carries the pre-sort index — resetting
    # here breaks econ_df.join(survived[["Organization"]]) downstream
    # (label mismatch → all-NaN Organization → empty groupby). 2026-09-04 fix.
    survived_fleet = survived_fleet.sort_values(
        "GHG_Power_Intensity", ascending=False)
    kW_to_target = survived_fleet["Power_kW"].sum() * alt_fuel_target_rate
    survived_fleet["cumul_kW"] = survived_fleet["Power_kW"].cumsum()
    target_idx = (min(int(np.searchsorted(survived_fleet["cumul_kW"].to_numpy(),
                                         kW_to_target)), len(survived_fleet) - 1)
                  if kW_to_target > 0 and len(survived_fleet) else -1)

    alt_fuel_targets = survived_fleet.iloc[:target_idx + 1].drop(columns=["cumul_kW"])
    unchanged        = survived_fleet.iloc[target_idx + 1:].drop(columns=["cumul_kW"])

    print(f"    Alt-fuel targets: {len(alt_fuel_targets):,} vessels "
          f"({alt_fuel_targets['Power_kW'].sum():,.0f} kW)")
    print(f"    Unchanged: {len(unchanged):,} vessels")

    return (survived_fleet.drop(columns=["cumul_kW"], errors="ignore"),
            alt_fuel_targets, unchanged, effort_mult, econ_df)


# =============================================================================
# 5. Multi-Year Simulation
# =============================================================================
def run_scenario_simulation(fleet_df, pm_dict, scenario_params,
                            start_year=2026, end_year=2050, random_seed=42,
                            save_vessel_econ=False, return_econ_agg=False,
                            write_econ_csv=False):
    """Run fleet dynamics for multiple years.

    save_vessel_econ : bool — write per-vessel economic effort detail file
        Vessel_Economic_Effort_Annual.csv (Year × vessel: fuel state, Cost_Ratio,
        M_econ_raw/realized, E_final, GHG).
    return_econ_agg : bool — additionally return (rfmo_agg, spec_agg):
        rfmo_agg : Year × RFMO × {M_econ_raw, M_econ_realized, E_required_total,
                   E_final_total, Rebound_Effect, Cost_Ratio_weighted} (effort-weighted)
        spec_agg : Year × Organization × Species × Gear × {E_required, E_final,
                   M_econ_raw, M_econ_realized} (P(Species|Org,Gear)-allocated, §27)
    write_econ_csv : bool — persist the two aggregate tables to CSV.
    """
    # Local state only: no mutable biological trajectories are shared between
    # futures, pool tasks, or the legacy fixed-catch stress-test path.
    coupling = None
    if scenario_params.get('fishery_coupling') is not None:
        from fishery_coupling import FisheryCoupling
        scenario_params = dict(scenario_params)
        coupling = FisheryCoupling(fleet_df, scenario_params['fishery_coupling'], scenario_params)
        scenario_params['_fishery_state'] = coupling
    np.random.seed(random_seed)          # isolate from the pool worker's module-level state
    rng = np.random.RandomState(random_seed)
    template_pool = build_template_pool(fleet_df)
    current_fleet = fleet_df.copy()
    history = []
    teff_rows = []
    rfmo_econ_rows = []
    rfmo_ghg_rows = []
    spec_ghg_rows = []
    spec_econ_rows = []
    vessel_rows = []

    for year in range(start_year, end_year + 1):
        if coupling is not None:
            coupling.begin_year(year)
        print(f"\n{'='*60}")
        print(f"  YEAR {year}")
        print(f"{'='*60}")

        survived, alt_fuel_target_fleet, unchanged, effort_mult, econ_df = \
            process_fleet_dynamics_pipeline(
                current_fleet, template_pool, pm_dict, scenario_params,
                current_year=year, rng=rng, capacity_baseline=fleet_df
            )

        history.append({
            "Year": year,
            "N_Vessels": len(survived),
            "Total_Power_kW": survived["Power_kW"].sum(),
            "Total_GHG_tCO2e": survived["GHG_Emissions"].sum(),
            "N_AltFuel_Targets": len(alt_fuel_target_fleet),
            "AltFuel_Target_Power_kW": alt_fuel_target_fleet["Power_kW"].sum(),
            "Mean_Age": survived["Age"].mean(),
            "Mean_LOA": survived["LOA"].mean(),
            "Meco": effort_mult["Meco"],
            "Cost_Ratio": effort_mult["Cost_Ratio"],
            "M_econ": effort_mult["M_econ"],
            "M_econ_realized": effort_mult.get("M_econ_realized", effort_mult["M_econ"]),
            "E_final": effort_mult["E_final"],
            "E_final_PS": effort_mult.get("E_final_PS", effort_mult["E_final"]),
            "E_final_LL": effort_mult.get("E_final_LL", effort_mult["E_final"]),
            "bio_ratio_PS": effort_mult.get("bio_ratio_PS", 1.0),
            "bio_ratio_LL": effort_mult.get("bio_ratio_LL", 1.0),
        })

        # ---- RFMO × Year economic aggregates (effort-weighted, §26) ----
        agg = econ_df.join(survived[["Organization"]])
        agg = agg[["Organization", "Meco", "E_final", "M_econ_raw", "M_econ_realized",
                   "Cost_Ratio", "Current_USD_per_MJ"]]
        g = agg.groupby("Organization")
        rfmo_econ_rows.append(pd.DataFrame({
            "Year": year, "RFMO": g.size().index,
            "M_econ_raw": g.apply(lambda x: float((x["Meco"] * x["M_econ_raw"]).sum() / max(x["Meco"].sum(), 1e-9))).values,
            "M_econ_realized": g.apply(lambda x: float(x["E_final"].sum() / max(x["Meco"].sum(), 1e-9))).values,
            "E_required_total": g["Meco"].sum().values,
            "E_final_total": g["E_final"].sum().values,
            "Rebound_Effect": g.apply(lambda x: float((x["Meco"] * x["M_econ_raw"]).sum() / max(x["Meco"].sum(), 1e-9)) - 1.0).values,
            "Cost_Ratio_weighted": g.apply(lambda x: float((x["Meco"] * x["Cost_Ratio"]).sum() / max(x["Meco"].sum(), 1e-9))).values,
        }))

        # ---- RFMO × Species × Gear economic aggregates (§27, effort-weighted via
        #     historical P(Species|RFMO,Gear) allocation of E_required) ----
        try:
            import fig5_allocation as _fa
            _P = _fa.build_shares()["Q"]
            _ORGANS = _fa.ORGANS
            _SP = _fa.SPECIES
            psg = survived[survived.VesselType.isin(["PS", "LL"])][["Organization", "VesselType"]].copy()
            psg = psg.join(econ_df[["Meco", "E_final", "M_econ_raw"]])
            rows = []
            for (org, vt), gv in psg.groupby(["Organization", "VesselType"]):
                gear = vt
                if (org not in _ORGANS) or (gear not in ["PS", "LL"]):
                    continue
                for s in _SP:
                    p = float(_P[s].get((org, gear), 0.0))
                    if p <= 0:
                        continue
                    er_s = (gv["Meco"] * p).sum()
                    if er_s <= 0:
                        continue
                    rows.append({
                        "Year": year, "Organization": org, "Species": s, "Gear": gear,
                        "E_required": er_s,
                        "E_final": (gv["E_final"] * p).sum(),
                        "M_econ_raw": float((gv["Meco"] * p * gv["M_econ_raw"]).sum() / er_s),
                        "M_econ_realized": float((gv["E_final"] * p).sum() / er_s)})
            spec_econ_rows.extend(rows)
        except Exception as _e:
            raise RuntimeError(f"Species economic allocation failed in {year}") from _e

        # ---- RFMO × Year GHG from the FLEET SIMULATION (all mechanisms: Meco ×
        #     M_econ effort, retirement, growth, lifespan, fuel, refrigerant) ----
        g_by_org = survived.groupby("Organization")["GHG_Emissions"].sum()
        for org, ghg in g_by_org.items():
            rfmo_ghg_rows.append({"Year": year, "RFMO": org, "GHG_tCO2e": float(ghg)})

        # ---- GEAR-LEVEL T_eff + T_map (capacity verification: per org×gear effort
        #      SUPPLY vs the Schaefer effort DEMAND; T_map = PHYSICAL capacity,
        #      independent of the economy — retirement is a fleet-structure
        #      mechanism, M_econ does NOT enter it) ----
        teff_g = survived[["Organization", "VesselType", "T_map"]].copy()
        teff_g = teff_g.join(econ_df[["E_final"]])
        teff_g["T_eff"] = teff_g["T_map"] * teff_g["E_final"]
        g = teff_g.groupby(["Organization", "VesselType"])
        teff_rows.append(pd.DataFrame({
            "Year": year, "Organization": g["T_map"].sum().index.get_level_values(0),
            "Gear": g["T_map"].sum().index.get_level_values(1),
            "T_map": g["T_map"].sum().values,
            "T_eff": g["T_eff"].sum().values}))

        # ---- OBJECT-LEVEL GHG: vessel GHG × P(Species|Flag,Org,Gear) from Base3
        #     composition (2026-09-04 fix: GEAR-level shares — the old
        #     (flag, org) mixed composition assigned PS-dominated shares to
        #     longline vessels, creating GHG for combos with zero Base3 catch).
        #     PS/LL vessels only (objects are RFMO×Species×Gear); TP/SA GHG stays
        #     at the RFMO level only. ----
        try:
            fg_shares = _flag_org_gear_shares()
            og_shares = _org_gear_shares()
            psg = survived[survived["VesselType"].isin(["PS", "LL"])][
                ["Flag", "Organization", "VesselType", "GHG_Emissions"]]
            for (flag, org, gear), gv in psg.groupby(["Flag", "Organization", "VesselType"]):
                shares = fg_shares.get((str(flag), str(org), gear)) or \
                         og_shares.get((str(org), gear))
                if not shares:
                    continue
                ghg_tot = float(gv["GHG_Emissions"].sum())
                for s in _SP_NAMES:
                    sh = shares.get(s, 0.0)
                    if sh > 0:
                        spec_ghg_rows.append({"Year": int(year), "Organization": org,
                                              "Species": s, "Gear": gear,
                                              "GHG_tCO2e": ghg_tot * sh})
        except Exception as _e:
            raise RuntimeError(f"Species GHG allocation failed in {year}") from _e


        # ---- Optional vessel-level detail (§25) ----
        if save_vessel_econ:
            vd = survived[["Vessel_ID", "Flag", "Organization", "VesselType", "GHG_Emissions"]].copy()
            vd = vd.join(econ_df[["Meco", "FuelShare", "Fuel_Label", "Current_USD_per_MJ",
                                  "Baseline_USD_per_MJ", "Cost_Ratio", "Elasticity",
                                  "M_econ_raw", "E_final", "M_econ_realized"]])
            vd.insert(0, "Year", year)
            vessel_rows.append(vd)

        # Age the fleet by 1 year for next iteration
        current_fleet = survived.copy()

    if write_econ_csv and rfmo_econ_rows:
        pd.concat(rfmo_econ_rows, ignore_index=True).to_csv(
            os.path.join(OUTPUT_DIR, "Effort_Economic_RFMO_Annual.csv"), index=False)
    if write_econ_csv and spec_econ_rows:
        pd.DataFrame(spec_econ_rows).to_csv(
            os.path.join(OUTPUT_DIR, "Effort_Economic_RFMO_SpeciesGear_Annual.csv"), index=False)
    if save_vessel_econ and vessel_rows:
        pd.concat(vessel_rows, ignore_index=True).to_csv(
            os.path.join(OUTPUT_DIR, "Vessel_Economic_Effort_Annual.csv"), index=False)

    history_df = pd.DataFrame(history)
    if coupling is not None:
        history_df = coupling.attach(history_df)
    if return_econ_agg:
        rfmo_agg = pd.concat(rfmo_econ_rows, ignore_index=True) if rfmo_econ_rows \
            else pd.DataFrame()
        spec_agg = pd.DataFrame(spec_econ_rows) if spec_econ_rows else pd.DataFrame()
        rfmo_ghg = pd.DataFrame(rfmo_ghg_rows) if rfmo_ghg_rows \
            else pd.DataFrame()
        spec_ghg = pd.DataFrame(spec_ghg_rows) if spec_ghg_rows \
            else pd.DataFrame()
        teff_df = pd.concat(teff_rows, ignore_index=True) if teff_rows \
            else pd.DataFrame()
        return history_df, current_fleet, rfmo_agg, spec_agg, rfmo_ghg, spec_ghg, teff_df
    return history_df, current_fleet


# =============================================================================
# =============================================================================
# 6. WEO 2024 Scenario Price Database
# =============================================================================
# Fuel price (USD/tonne) and carbon price (USD/tCO2) by WEO scenario and year.
# Values interpolated linearly between key years; annual granularity.

CRUDE_TO_MGO = 8.5   # crude bbl → MGO USD/tonne
CRUDE_TO_HFO = 6.5

WEO_OIL = {  # USD/barrel, 2023 real
    "STEPS": {2023: 82, 2030: 79, 2040: 77, 2050: 75},
    "APS":   {2023: 82, 2030: 72, 2040: 63, 2050: 58},
    "NZE":   {2023: 82, 2030: 42, 2040: 30, 2050: 25},
}

WEO_CARBON = {  # USD/tCO2, Advanced economies
    "STEPS": {2030: 140, 2035: 145, 2040: 149, 2050: 158},
    "APS":   {2030: 135, 2035: 160, 2040: 175, 2050: 200},
    "NZE":   {2030: 140, 2035: 180, 2040: 205, 2050: 250},
}

def _interp_year(data_dict, year):
    """Linear interpolation for WEO price lookup."""
    yrs = sorted(data_dict.keys())
    vals = [data_dict[y] for y in yrs]
    return float(np.interp(year, yrs, vals))

def get_weo_params(scenario, year):
    """Return (MGO_price_USDt, carbon_USDtCO2) for given WEO scenario year."""
    import price_loader as pl
    price = pl.get_fuel_price("MGO", scenario, year, "European Union", "mid")[0]
    carbon = _interp_year(WEO_CARBON[scenario], year) if year >= 2030 else 0.0
    return price, carbon

# WEO grid carbon intensity (g CO2/kWh)
WEO_GRID_EF = {
    "STEPS": {2023: 458, 2030: 312, 2035: 219, 2050: 111},
    "APS":   {2023: 458, 2030: 270, 2035: 140, 2050: 29},
    "NZE":   {2023: 458, 2030: 195, 2035: 50,  2050: -4},
}

def get_grid_ef(scenario, year):
    """Return grid carbon intensity (gCO2/kWh) for WEO scenario year.
    NO truncation at 0 (2026-09-09 user directive): NZE 2050 is -4 g/kWh
    (net-negative grid) and is used as-is."""
    yrs = sorted(WEO_GRID_EF[scenario].keys())
    vals = [WEO_GRID_EF[scenario][y] for y in yrs]
    return float(np.interp(year, yrs, vals))


# =============================================================================
# 6b. Vessel-level economic rebound: fixed 2025 WEO-MGO baseline (user directive
# 2026-08-26). Cost_Ratio_{v,t,s} = CurrentCost_{v,t,s} / BaselineCost_{s,2025}
# — the baseline is FIXED per WEO scenario at 2025 (NOT a year-over-year ratio,
# NOT a hardcoded 700 USD/t). 700 survives only inside DEFAULT_FUEL_PRICES as a
# relative-price anchor, never as the Cost_Ratio denominator.
# =============================================================================

BASELINE_YEAR = 2025
BASELINE_FUEL = "MGO"
BASELINE_PRICE_SOURCE = "WEO"

_BASELINE_COST_CACHE = {}   # {scenario: USD/MJ}

def get_baseline_cost(scenario, baseline_year=BASELINE_YEAR):
    """Fixed 2025 WEO-scenario MGO baseline, energy-normalised (USD/MJ).

    Every year t compares against this same baseline:
        Cost_Ratio_t = CurrentCost_t / BaselineCost_{s,2025}
    """
    key = (scenario, int(baseline_year))
    if key not in _BASELINE_COST_CACHE:
        mgo_p, carbon_p = get_weo_params(scenario, baseline_year)
        _BASELINE_COST_CACHE[key] = _price_per_MJ(
            mgo_p, FUEL_DATABASE[BASELINE_FUEL][0], carbon_p,
            _fuel_co2eq(BASELINE_FUEL))
    return _BASELINE_COST_CACHE[key]


def get_fuel_share(scenario_params, year, ref_year=2025, target_year=2050):
    """Annual alternative-fuel share (never a one-shot first-year switch).

    - alternative_fuel_annual_growth: compounded annual rate (matrix definition).
    - blend_share: treated as the TARGET share by target_year, ramping linearly
      from 0 at ref_year (2025: 0% → 2050: blend_share).
    FAME blend capped at 30% (blend_type FAME ≤30% / HVO ≤100%).
    """
    ag = scenario_params.get("alternative_fuel_annual_growth")
    if ag:
        share = min(0.95, ag * (year - ref_year))
    else:
        bs = scenario_params.get("blend_share", 0.0) or 0.0
        if bs <= 0:
            return 0.0
        frac = min((year - ref_year) / max(target_year - ref_year, 1), 1.0)
        share = bs * frac
    blend_max = 0.30 if scenario_params.get("blend_type", "FAME") == "FAME" else 1.0
    return min(share, blend_max)


_FUEL_ALIAS = {"MDO": "MGO", "GASOLINE": "MGO", "MGO": "MGO", "HFO": "HFO",
               "LFO": "LFO", "LNG": "LNG_Fossil"}

_CARBON_REF_CACHE = None
_CARBON_PRICE_CACHE = {}   # {(scenario, year): {flag: USD/tCO2}}

def _carbon_ref_table():
    """Carbon_Reference sheet (scenario × region × anchor-year carbon price)."""
    global _CARBON_REF_CACHE
    if _CARBON_REF_CACHE is None:
        import price_loader as pl
        _CARBON_REF_CACHE = pd.read_excel(pl.PRICE_MATRIX_PATH,
                                          sheet_name="Carbon_Reference")
    return _CARBON_REF_CACHE


def get_vessel_carbon_price(flag, scenario, year):
    """Flag → carbon-price regime → USD/tCO2 (linearly interpolated between
    Carbon_Reference anchors, 0 before 2030 per project convention).

    Uses price_loader's Flag_Region_Map (172 flags); falls back to the WEO_CARBON
    Advanced-economies trajectory when the sheet has no usable row for the region.
    Interface is deliberately extensible (future per-flag multipliers plug in here).
    """
    key = (scenario, year)
    flag_price = _CARBON_PRICE_CACHE.setdefault(key, {})
    if flag in flag_price:
        return flag_price[flag]
    cp = 0.0
    resolved = False
    if year >= 2030:
        try:
            import price_loader as pl
            _, carbon_region = pl.get_vessel_region(flag, scenario)
            df = _carbon_ref_table()
            sub = df[(df.Scenario == scenario) & (df.WEO_Region == carbon_region)]
            if len(sub):
                years = sorted(y for y in sub.Year.unique() if int(y) >= 2030)
                if years:
                    vals = []
                    for y in years:
                        v = sub[sub.Year == y]["Carbon_USDtCO2"].iloc[0]
                        vals.append(float(v) if pd.notna(v) else 0.0)
                    cp = float(np.interp(year, years, vals))
                    resolved = True
        except Exception:
            cp = 0.0
        if not resolved:
            cp = _interp_year(WEO_CARBON[scenario], year)
    flag_price[flag] = cp
    return cp


_H2G_PRICE_CACHE = None


def _h2g_price_annual(year):
    """Green-H2 price (USD/t), read once from Scenario_Fuel_Parameters.xlsx
    (Fuel_Parameters 'Hydrogen -- Green' row, USD/MWh Current & 2050 mids ->
    USD/t via x33.33) and linearly interpolated. 2026-09-11."""
    global _H2G_PRICE_CACHE
    if _H2G_PRICE_CACHE is None:
        import price_loader as _pl
        mp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "model_parameters", "Scenario_Fuel_Parameters.xlsx")
        fp = pd.read_excel(mp, sheet_name="Fuel_Parameters", header=None)
        r = fp[fp[1].astype(str).str.contains("Hydrogen -- Green")].iloc[0]
        p_cur = (float(r[10]) + float(r[11])) / 2.0 * 33.33
        p_2050 = (float(r[12]) + float(r[13])) / 2.0 * 33.33
        _H2G_PRICE_CACHE = {2023: p_cur, 2050: p_2050}
    yrs = sorted(_H2G_PRICE_CACHE)
    return float(np.interp(year, yrs, [_H2G_PRICE_CACHE[a] for a in yrs]))


def _fuel_price_annual(fuel, scenario, year, region="European Union"):
    """Annual regional price from the canonical price matrix interface."""
    import price_loader as pl
    if fuel == "GASOLINE":
        fuel = "MGO"  # Explicit existing assumption: no separate gasoline series.
    return pl.get_fuel_price(fuel, scenario, year, region, "mid")[0]


# =============================================================================
# 6c. Meco — Organization × Species × Year macro resource multiplier (2026-08-26)
# -----------------------------------------------------------------------------
# Top-down chain (NEVER vessel-specific, NEVER a global constant):
#   Base3 grid history  →  Flag×Organization×Species×Year species composition
#   Schaefer (species)  →  QuotaRatio_{s,t} / BiomassRatio_{s,t}
#   Meco_{o,s,t}        = QuotaRatio_{o,s,t} / [BiomassRatio_{o,s,t} × (1+tc)^ΔT]
#   SpeciesShare_{f,o,s,t} × Meco_{o,s,t}  →  Meco_eff_{f,o,t}   (share-weighted;
#                         E_required-weighted preferred when available — §14)
#   Meco_v,t            = Meco_eff_{Flag_v, Organization_v, t}   (same flag×org
#                         fleet shares the macro multiplier; vessel heterogeneity
#                         lives in M_econ_v,t)
# Species composition is the BRIDGE only — it does NOT predict "one vessel = one
# species". Composition stability is tested (CV + trend p-value + hold-out
# validation): stable → historical mean; unstable with a real trend → log-ratio
# linear extrapolation, renormalised (Σ share = 1).
# =============================================================================

_SP_COLS = ["SBT_Tonnes", "SKJ_Tonnes", "BET_Tonnes", "YFT_Tonnes", "ALB_Tonnes"]
_SP_NAMES = ["SBT", "SKJ", "BET", "YFT", "ALB"]
_MECO_ORGANS = ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]

_BASE3_CACHE = None
_BASE3_WINDOW_META = None
_SHARE_HIST_CACHE = None
_SP_GEAR_SHARE_CACHE = None
_ORG_GEAR_SHARE_CACHE = None
_SHARE_STATS_CACHE = None
_SHARE_FORECAST_CACHE = None      # {window_key: {"by_year": {y: {f: {o: {s: share}}}},
                                  #               "method": DataFrame, "validation": DataFrame}}
_MECO_ORG_MEAN_CACHE = None       # {org: {s: share}} — fallback for unknown flag×org
_MECO_EFF_CACHE = {}              # {(msy, quota_type, year, tc_rounded): {(flag, org): Meco_eff}}


def _load_base3():
    global _BASE3_CACHE
    if _BASE3_CACHE is None:
        _BASE3_CACHE = pd.read_csv(GRID_PATH)
    return _BASE3_CACHE


def base3_window(min_flags=15, min_grids=4000, min_catch_frac=0.05):
    """Auto-select the longest continuous, quality-filtered Base3 window (§5).

    Year qualifies if: flags ≥ min_flags AND grids ≥ min_grids AND
    total catch ≥ median × min_catch_frac. Then the LONGEST CONSECUTIVE run of
    qualifying years is kept. Window is written into the output metadata.
    """
    global _BASE3_WINDOW_META
    if _BASE3_WINDOW_META is not None:
        return _BASE3_WINDOW_META
    df = _load_base3()
    py = df.groupby("Year").agg(catch=("Total_Catch", "sum"),
                                grids=("lat", "count"),
                                nflags=("Flag", "nunique"),
                                orgs=("Organization", "nunique"))
    good = py[(py["nflags"] >= min_flags) & (py["grids"] >= min_grids) &
              (py["catch"] >= py["catch"].median() * min_catch_frac)]
    yrs = sorted(int(y) for y in good.index)
    best, cur = [], []
    for y in yrs:
        if cur and y != cur[-1] + 1:
            if len(cur) > len(best):
                best = cur
            cur = []
        cur.append(y)
    if len(cur) > len(best):
        best = cur
    meta = {"year_min": int(best[0]), "year_max": int(best[-1]),
            "n_years": len(best),
            "rule": "flags>=%d & grids>=%d & catch>=median*%.2f" % (min_flags, min_grids, min_catch_frac),
            "years_available": yrs}
    _BASE3_WINDOW_META = meta
    print(f"  [Base3 window] auto-selected {meta['year_min']}–{meta['year_max']} "
          f"({meta['n_years']} yrs, rule: {meta['rule']})")
    return meta


def _flag_org_gear_shares():
    """Historical species composition per (Flag, Organization, Gear) from
    Base3 (2026-09-04 fix): object-level GHG allocation must use GEAR-level
    shares — the old (flag, org) mixed composition applied PS-dominated
    shares (e.g. SKJ≈0.94 for JPN) to longline vessels, giving WCPFC-SKJ-LL
    GHG where Base3 catches are zero. Same source as C0 (Base3 grid)."""
    global _SP_GEAR_SHARE_CACHE
    if _SP_GEAR_SHARE_CACHE is not None:
        return _SP_GEAR_SHARE_CACHE
    df = _load_base3()
    g = df.groupby(["Flag", "Organization", "Gear"])[_SP_COLS].sum()
    tot = g.sum(axis=1)
    share = g.div(tot.replace(0, np.nan), axis=0).fillna(0.0)
    out = {}
    for (flag, org, gear), row in share.iterrows():
        out[(str(flag), str(org), gear)] = {
            s.replace("_Tonnes", ""): float(v) for s, v in row.items()}
    _SP_GEAR_SHARE_CACHE = out
    return out


def _org_gear_shares():
    """Organization × Gear species composition (Base3, all years) — fallback
    when a (flag, org, gear) combo has no records. Same source as C0."""
    global _ORG_GEAR_SHARE_CACHE
    if _ORG_GEAR_SHARE_CACHE is not None:
        return _ORG_GEAR_SHARE_CACHE
    df = _load_base3()
    g = df.groupby(["Organization", "Gear"])[_SP_COLS].sum()
    tot = g.sum(axis=1)
    share = g.div(tot.replace(0, np.nan), axis=0).fillna(0.0)
    out = {}
    for (org, gear), row in share.iterrows():
        out[(str(org), gear)] = {
            s.replace("_Tonnes", ""): float(v) for s, v in row.items()}
    _ORG_GEAR_SHARE_CACHE = out
    return out


def build_species_share_history():
    """Year × Flag × Organization × Species catch + share (long table, §4)."""
    global _SHARE_HIST_CACHE
    if _SHARE_HIST_CACHE is not None:
        return _SHARE_HIST_CACHE
    meta = base3_window()
    df = _load_base3()
    rec = df[(df.Year >= meta["year_min"]) & (df.Year <= meta["year_max"])]
    g = rec.groupby(["Year", "Flag", "Organization"])[_SP_COLS].sum()
    g = g[g.sum(axis=1) > 0]                     # drop zero-catch combos
    tot = g.sum(axis=1)
    share = g.div(tot.replace(0, np.nan), axis=0).fillna(0.0)
    long = share.reset_index().melt(id_vars=["Year", "Flag", "Organization"],
                                    value_vars=_SP_COLS, var_name="Species",
                                    value_name="Share")
    long["Species"] = long["Species"].str.replace("_Tonnes", "")
    catch = g.reset_index().melt(id_vars=["Year", "Flag", "Organization"],
                                 value_vars=_SP_COLS, var_name="Species",
                                 value_name="Catch")
    long["Catch"] = catch["Catch"].values
    _SHARE_HIST_CACHE = long
    return long


def species_share_stats(hist=None, min_years=8):
    """Per Flag×Organization×Species: Mean/SD/CV/trend slope+p/N_years (§9)."""
    global _SHARE_STATS_CACHE
    if _SHARE_STATS_CACHE is not None:
        return _SHARE_STATS_CACHE
    hist = hist if hist is not None else build_species_share_history()
    rows = []
    for (flag, org), g in hist.groupby(["Flag", "Organization"]):
        for s in _SP_NAMES:
            sub = g[g.Species == s].sort_values("Year")
            n = len(sub)
            if n == 0:
                continue
            mean = float(sub.Share.mean())
            sd = float(sub.Share.std(ddof=1)) if n > 1 else 0.0
            cv = sd / mean if mean > 1e-12 else np.nan
            slope, pval = np.nan, np.nan
            if n >= 3:
                x = sub.Year.values.astype(float)
                y = sub.Share.values
                slope = float(np.polyfit(x, y, 1)[0])
                try:
                    from scipy import stats as _st
                    pval = float(_st.linregress(x, y).pvalue)
                except Exception:
                    pval = np.nan
            rows.append({"Flag": flag, "Organization": org, "Species": s,
                         "N_years": n, "MeanShare": mean, "SDShare": sd,
                         "CVShare": cv, "TrendSlope": slope, "TrendPvalue": pval})
    _SHARE_STATS_CACHE = pd.DataFrame(rows)
    return _SHARE_STATS_CACHE


def _fo_share_matrix(hist, flag, org):
    """Wide share matrix (Year × Species) for one flag×org fleet."""
    sub = hist[(hist.Flag == flag) & (hist.Organization == org)]
    piv = sub.pivot(index="Year", columns="Species", values="Share").fillna(0.0)
    return piv


def _predict_fo(fo_piv, years_future, ref=None, holdout_frac=0.25,
                min_years=8, cv_thresh=0.30, p_thresh=0.05, eps=1e-6):
    """One flag×org fleet: decide stable-mean vs log-ratio trend (§10–12, §19).

    - Stable (N<min_years OR no species with CV≥thresh & trend p<thresh):
      historical mean.
    - Candidate dynamic: per-species log-ratio Z_s = log(share_s/share_ref),
      linear in year, extrapolated, renormalised (softmax-style, Σ share = 1).
    - Hold-out validation on the LAST holdout_frac of years: MAE of the two
      models; the better one wins (trend only if it beats the mean).
    Returns (pred_dict {year: {s: share}}, method, validation_row).
    """
    species = [s for s in _SP_NAMES if s in fo_piv.columns]
    years = sorted(fo_piv.index)
    n = len(years)
    future = sorted(years_future)
    mean_share = {s: float(fo_piv[s].mean()) for s in species}
    def _norm(share_dict):
        tot = sum(share_dict.values())
        return {s: v / tot for s, v in share_dict.items()} if tot > 0 else {s: 0.0 for s in species}
    mean_pred = {y: _norm(mean_share) for y in future}
    if n < min_years:
        return mean_pred, "historical_mean", None

    n_tr = min(max(int(n * (1 - holdout_frac)), 3), n - 1)
    tr_years, va_years = years[:n_tr], years[n_tr:]
    train = fo_piv.loc[tr_years]
    train_mean = {s: float(train[s].mean()) for s in species}

    # ---- stability test on training years only ----
    dynamic_candidate = False
    # (stats are computed globally; filter by the caller-provided identity below)
    for s in species:
        if train[s].std(ddof=1) < 1e-12:
            continue
        cv = train[s].std(ddof=1) / max(train[s].mean(), 1e-12)
        pv = np.nan
        if n >= 3:
            try:
                from scipy import stats as _st
                pv = float(_st.linregress(tr_years, train[s].values).pvalue)
            except Exception:
                pv = np.nan
        if cv >= cv_thresh and (pv < p_thresh if pv == pv else False):
            dynamic_candidate = True
    if not dynamic_candidate:
        return mean_pred, "historical_mean", None

    # ---- log-ratio trend model (reference = largest mean share) ----
    ref = ref or max(species, key=lambda s: train_mean[s])
    trend_pred, val = {}, None
    def _trend_fit(fo_piv, fit_years, out_years, ref, species, eps=1e-6):
        """Pure log-ratio linear extrapolation (predictions only — the validation
        years are NOT read back from the observations)."""
        xs = np.array(fit_years, dtype=float) - fit_years[0]
        coef = {}
        for s in species:
            if s == ref:
                continue
            zs = np.log((fo_piv.loc[fit_years, s].values + eps) /
                        (fo_piv.loc[fit_years, ref].values + eps))
            coef[s] = np.polyfit(xs, zs, 1)
        out = {}
        for y in out_years:
            Z = {s: coef[s][0] * (y - fit_years[0]) + coef[s][1] for s in coef}
            Z[ref] = 0.0
            zmax = max(Z.values())
            e = {s: np.exp(Z[s] - zmax) for s in species}
            tot = sum(e.values())
            out[y] = {s: e[s] / tot for s in species}
        return out
    # hold-out: fit on train, evaluate on validation (§19)
    trend_va = _trend_fit(fo_piv, tr_years, va_years, ref, species)
    mean_va = {y: _norm(train_mean) for y in va_years}
    def _mae(pred):
        errs = []
        for y in va_years:
            for s in species:
                errs.append(abs(pred[y][s] - fo_piv.loc[y, s]))
        return float(np.mean(errs)) if errs else 9e9
    mae_mean, mae_trend = _mae(mean_va), _mae(trend_va)
    val = {"Flag": fo_piv.attrs.get("flag", ""), "Organization": fo_piv.attrs.get("org", ""),
           "N_years": n, "Train_years": n_tr, "Validate_years": len(va_years),
           "MAE_mean": round(mae_mean, 5), "MAE_trend": round(mae_trend, 5)}
    if mae_trend < mae_mean:
        trend_pred = _trend_fit(fo_piv, years, future, ref, species)
        return trend_pred, "logratio_trend", val
    return mean_pred, "historical_mean", val


def species_share_forecast(years_future=range(2025, 2051), holdout_frac=0.25,
                           cv_thresh=0.30, p_thresh=0.05, min_years=8):
    """Forecast P(Species|Flag,Organization,Year) for the simulation window.

    Cached. Returns dict: {"by_year": {y: {f: {o: {s: share}}}},
                           "method": DataFrame(Year,Flag,Organization,Species,Share,Method),
                           "validation": DataFrame}.
    """
    global _SHARE_FORECAST_CACHE
    years_future = tuple(years_future)
    key = (years_future, holdout_frac, cv_thresh, p_thresh, min_years)
    if _SHARE_FORECAST_CACHE is None:
        _SHARE_FORECAST_CACHE = {}
    if key in _SHARE_FORECAST_CACHE:
        return _SHARE_FORECAST_CACHE[key]
    hist = build_species_share_history()
    by_year = {y: {} for y in years_future}
    method_rows, val_rows = [], []
    for (flag, org), g in hist.groupby(["Flag", "Organization"]):
        piv = _fo_share_matrix(hist, flag, org)
        piv.attrs["flag"], piv.attrs["org"] = flag, org
        pred, method, val = _predict_fo(piv, years_future,
                                        holdout_frac=holdout_frac,
                                        cv_thresh=cv_thresh, p_thresh=p_thresh,
                                        min_years=min_years)
        if not pred or not pred[years_future[0]]:   # no valid species record
            om = _org_species_mean_share().get(org, {s: 0.2 for s in _SP_NAMES})
            pred = {y: dict(om) for y in years_future}
            method = "historical_mean"
        for y in years_future:
            by_year[y].setdefault(flag, {})[org] = pred[y]
            for s, sh in pred[y].items():
                method_rows.append({"Year": y, "Flag": flag, "Organization": org,
                                    "Species": s, "Share": sh, "Method": method})
        if val is not None:
            val_rows.append(val)
    out = {"by_year": by_year, "method": pd.DataFrame(method_rows),
           "validation": pd.DataFrame(val_rows) if val_rows else pd.DataFrame()}
    _SHARE_FORECAST_CACHE[key] = out
    return out


def _org_species_mean_share():
    """{org: {s: share}} fallback for flags without grid records (§15)."""
    global _MECO_ORG_MEAN_CACHE
    if _MECO_ORG_MEAN_CACHE is not None:
        return _MECO_ORG_MEAN_CACHE
    hist = build_species_share_history()
    g = hist.groupby(["Organization", "Species"])["Catch"].sum()
    tot = g.groupby("Organization").sum()
    _MECO_ORG_MEAN_CACHE = {org: {s: float(g[org][s] / tot[org])
                                  for s in _SP_NAMES} for org in _MECO_ORGANS}
    return _MECO_ORG_MEAN_CACHE


def compute_meco_org_species(msy_scenario, quota_type, tech_creep, years,
                             organs=None):
    """Meco_{o,s,t} — Organization × Species × Year (§8).

    Quota/biomass ratios are species-level Schaefer outputs (identical across
    organisations under the current species-level quota design; the o dimension
    is retained so an organisation-level quota can plug in later).
    """
    lu = _load_schaefer_species(quota_type)
    organs = organs or _MECO_ORGANS
    rows = []
    for s in _SP_NAMES:
        for y in years:
            scen = msy_scenario.get(s, "MSY_100") if isinstance(msy_scenario, dict) else msy_scenario
            rec = lu.get((scen, int(y), s))
            qr = float(rec["quota_ratio"]) if rec else 1.0
            br = float(rec["biomass_ratio"]) if rec else 1.0
            meco = qr / max(br * (1.0 + tech_creep) ** max(int(y) - 2025, 0), 0.01)
            for o in organs:
                rows.append({"Year": int(y), "Organization": o, "Species": s,
                             "QuotaRatio": qr, "BiomassRatio": br,
                             "TechCreep": tech_creep, "Meco": meco})
    return pd.DataFrame(rows)


def get_meco_eff_map(msy_scenario, quota_type, year, tech_creep, flags_orgs=None):
    """Meco_eff_{f,o,t} = Σ_s Share_{f,o,s,t} × Meco_{o,s,t} (§14, share-weighted;
    E_required-weighted is preferred once species-specific E_required exists).

    Returns {(flag, org): Meco_eff} for every flag×org in the forecast table
    (or the requested flags_orgs subset). Unknown combos fall back to the
    organisation-level species mean. Cached per (msy, quota_type, year, tc).
    """
    qt_key = tuple(sorted(quota_type.items())) if isinstance(quota_type, dict) \
        else quota_type
    msy_key = tuple(sorted(msy_scenario.items())) if isinstance(msy_scenario, dict) else msy_scenario
    key = (msy_key, qt_key, int(year), round(float(tech_creep), 6),
           frozenset(flags_orgs) if flags_orgs is not None else None)
    if key in _MECO_EFF_CACHE:
        return _MECO_EFF_CACHE[key]
    fc = species_share_forecast()
    meco_s = {s: _meco_of_species(msy_scenario, quota_type, year, tech_creep, s)
              for s in _SP_NAMES}
    out = {}
    ymap = fc["by_year"].get(int(year), {})
    for flag, orgs in ymap.items():
        for org, shares in orgs.items():
            out[(flag, org)] = sum(shares.get(s, 0.0) * meco_s[s] for s in _SP_NAMES)
    if flags_orgs is not None:
        om = _org_species_mean_share()
        for (flag, org) in flags_orgs:
            if (flag, org) not in out and org in om:
                out[(flag, org)] = sum(om[org].get(s, 0.0) * meco_s[s] for s in _SP_NAMES)
            elif (flag, org) not in out:
                out[(flag, org)] = sum(meco_s[s] for s in _SP_NAMES) / len(_SP_NAMES)
    _MECO_EFF_CACHE[key] = out
    return out


def _meco_of_species(msy_scenario, quota_type, year, tech_creep, s):
    lu = _load_schaefer_species(quota_type)
    scen = msy_scenario.get(s, "MSY_100") if isinstance(msy_scenario, dict) else msy_scenario
    rec = lu.get((scen, int(year), s))
    qr = float(rec["quota_ratio"]) if rec else 1.0
    br = float(rec["biomass_ratio"]) if rec else 1.0
    return qr / max(br * (1.0 + tech_creep) ** max(int(year) - 2025, 0), 0.01)


def export_meco_tables(msy_scenario="MSY_100", quota_type="C", tc=0.024,
                       years=range(2025, 2051), out_dir=None):
    """Write the two Meco layers (§18):
    1. Meco_Organization_Species_Annual.csv — Year,Organization,Species,QuotaRatio,
       BiomassRatio,TechCreep,Meco
    2. Meco_Flag_Organization_Annual.csv — Year,Flag,Organization,Meco_eff,
       SpeciesShare_weighted,Method (+ per-species Share columns)
    """
    out_dir = out_dir or OUTPUT_DIR
    t1 = compute_meco_org_species(msy_scenario, quota_type, tc, years)
    t1.to_csv(os.path.join(out_dir, "Meco_Organization_Species_Annual.csv"), index=False)
    fc = species_share_forecast()
    rows = []
    for y in years:
        for flag, orgs in fc["by_year"][y].items():
            for org, shares in orgs.items():
                meco_s = {s: _meco_of_species(msy_scenario, quota_type, y, tc, s)
                          for s in _SP_NAMES}
                eff = sum(shares.get(s, 0.0) * meco_s[s] for s in _SP_NAMES)
                meth = fc["method"][(fc["method"].Year == y) &
                                    (fc["method"].Flag == flag) &
                                    (fc["method"].Organization == org)].Method.iloc[0]
                row = {"Year": y, "Flag": flag, "Organization": org,
                       "Meco_eff": eff, "SpeciesShare_weighted": 1.0,
                       "Method": meth}
                for s in _SP_NAMES:
                    row["Share_" + s] = shares.get(s, 0.0)
                rows.append(row)
    t2 = pd.DataFrame(rows)
    t2.to_csv(os.path.join(out_dir, "Meco_Flag_Organization_Annual.csv"), index=False)
    fc["validation"].to_csv(os.path.join(out_dir, "SpeciesShare_Validation.csv"), index=False)
    meta = base3_window()
    with open(os.path.join(out_dir, "Meco_meta.json"), "w") as f:
        json.dump({"window": meta, "holdout_frac": 0.25, "cv_thresh": 0.30,
                   "p_thresh": 0.05, "min_years": 8,
                   "n_validation": len(fc["validation"])}, f, indent=1)
    print(f"  [Meco export] tables -> {out_dir} "
          f"(window {meta['year_min']}–{meta['year_max']})")
    return t1, t2


# =============================================================================
# 7. Scenario Matrix Builder
# =============================================================================
# Each WEO background (STEPS/APS/NZE) has sub-scenarios varying:
#   tech_creep  — annual efficiency gain (0, 0.01, 0.02)
#   alternative_fuel — annual blend-growth (0, 0.02, 0.05 → reaches X% by 2050)
#   newbuild_fuel — what fuel new ships use
#
# All rates compound annually:  X_year = X_2025 * (1 + rate)^(year-2025)

# Base fleet params
_BASE_FLEET = {
    "capacity_growth_rate": 0.02,    # fleet power grows 2%/yr
    "max_lifespan": 30,              # hull life (30yr default)
    "quota_type": "C",               # C = fixed-catch quota (schaefer_biomass_annual.csv)
                                     # F = harvest-rate HCR (schaefer_biomass_annual_F.csv)
    "retirement_scenario": 2,        # 1=natural, 2=rebuild, 3=natural+forced
    "forced_retirement_rate": 0.0,   # used only in retirement scenario 3
    "alt_fuel_target_type": 0,       # 0=none, 1=30% by 2050, 2=60% by 2050
    "consolidation_type": 0,     # 0=none, 1=50%→large, 2=100%→large by 2050
    "refrigerant_type": "R22",   # R22 / R404a / LN2
    "blend_type": "FAME",        # FAME (≤30%) / HVO (≤100%)
    "blend_share": 0.0,          # biofuel blend fraction
    "newbuild_fuel": "MGO",      # fuel for new vessels
    "elasticity": -0.3,
    "regulatory_regime": "CPS",
}

# Tech creep annual rates from Palomares & Pauly (2019)
# C% = 13.8 * Y^(-0.511)
# Y=10: 4.3%/yr (rapid), Y=30: 2.4%/yr (steady), Y=50: 1.9%/yr (slow)
TECH_CREEP_LEVELS = {
    "rapid":  0.043,   # 10-year horizon: AI, sonar, big data revolution
    "steady": 0.024,   # 30-year horizon: BAU tech progress
    "slow":   0.019,   # 50-year horizon: diminishing returns
}

# ---- Load JABBA species-level biomass projections ----
# Generated by jabba_fit.r (5 species × 4 MSY scenarios × 2 quota designs)
# Columns: Year, Stock, Scenario, biomass_ratio, quota_ratio, Catch_Mt, Biomass_Mt, K_Mt
# Stocks: SBT, SKJ, BET, YFT, ALB (aggregate "All" not used)
# Scenarios: MSY_100, MSY_90, MSY_80, MSY_70
# Quota designs (jabba_fit.r):
#   C-type (default, fixed absolute catch): C_t = frac * MSY
#        -> schaefer_biomass_annual.csv   (quota_ratio constant across years)
#   F-type (harvest-rate HCR):             C_t = frac * F_MSY * B_t  (self-limiting)
#        -> schaefer_biomass_annual_F.csv  (quota_ratio time-varying)
_SCHAEFER_PATH   = os.path.join(OUTPUT_DIR, "schaefer_biomass_annual.csv")
_SCHAEFER_PATH_F = os.path.join(OUTPUT_DIR, "schaefer_biomass_annual_F.csv")
_SCHAEFER_SPECIES_LOOKUP = {}     # {quota_type: {(scenario, year, stock): {...}}}
_GEAR_BLENDED_CACHE = {}          # {(scenario, year, quota_type): {"PS": {...}, "LL": {...}}}

def _load_schaefer_species(quota_type="C"):
    """Load species-level Schaefer projections, build fast lookup dict.

    quota_type : "C" (fixed-catch quota), "F" (harvest-rate HCR), or a
    per-species dict {"SKJ": "C", "YFT": "F", ...} selecting the quota
    regime species-by-species (mixed-species quota, 2026-09-08). Selects
    between schaefer_biomass_annual.csv and schaefer_biomass_annual_F.csv.
    """
    global _SCHAEFER_SPECIES_LOOKUP
    if isinstance(quota_type, dict):
        key = tuple(sorted(quota_type.items()))
        if key not in _SCHAEFER_SPECIES_LOOKUP:
            base = {}
            for sp, qt in quota_type.items():
                sub = _load_schaefer_species(qt)
                for (scen, yr, st), rec in sub.items():
                    if st == sp:
                        base[(scen, yr, st)] = dict(rec)
            _SCHAEFER_SPECIES_LOOKUP[key] = base
            print(f"  Loaded mixed species-level Schaefer ({len(base)} entries, "
                  f"{dict(key)})")
        return _SCHAEFER_SPECIES_LOOKUP[key]
    if quota_type not in ("C", "F"):
        raise ValueError(f"Invalid quota_type: {quota_type!r}")
    if quota_type not in _SCHAEFER_SPECIES_LOOKUP:
        path = _SCHAEFER_PATH_F if quota_type == "F" else _SCHAEFER_PATH
        if os.path.exists(path):
            df = pd.read_csv(path)
            lu = {}
            for _, row in df.iterrows():
                key = (str(row["Scenario"]), int(row["Year"]), str(row["Stock"]))
                lu[key] = {
                    "biomass_ratio": float(row["biomass_ratio"]),
                    "quota_ratio": float(row["quota_ratio"]),
                }
            _SCHAEFER_SPECIES_LOOKUP[quota_type] = lu
            print(f"  Loaded {len(lu)} species-level Schaefer entries "
                  f"({df['Stock'].nunique()} stocks × {df['Scenario'].nunique()} scenarios, "
                  f"quota_type={quota_type})")
        else:
            raise FileNotFoundError(f"Required biomass projections are missing: {path}")
    return _SCHAEFER_SPECIES_LOOKUP[quota_type]


def get_gear_blended_params(scenario: str, year: int, quota_type="C"):
    """
    Compute gear-specific blended biomass_ratio and quota_ratio.

    Uses species-level JABBA projections × gear-specific catch composition weights.

    Parameters
    ----------
    scenario : str — one of MSY_100, MSY_90, MSY_80, MSY_70
    year : int  — projection year (2024-2050)
    quota_type : str — "C" (fixed-catch quota) or "F" (harvest-rate HCR)

    Returns
    -------
    dict : {"PS": {"biomass_ratio": float, "quota_ratio": float},
            "LL": {"biomass_ratio": float, "quota_ratio": float}}
    """
    scen_key = tuple(sorted(scenario.items())) if isinstance(scenario, dict) else scenario
    qt_key2 = tuple(sorted(quota_type.items())) if isinstance(quota_type, dict) else quota_type
    cache_key = (scen_key, year, qt_key2)
    if isinstance(quota_type, dict):
        cache_key = (scen_key, year, tuple(sorted(quota_type.items())))
    if cache_key in _GEAR_BLENDED_CACHE:
        return _GEAR_BLENDED_CACHE[cache_key]

    lu = _load_schaefer_species(quota_type)
    gear_weights = compute_gear_catch_weights()
    species_list = ["SKJ", "YFT", "BET", "ALB", "SBT"]

    blended = {}
    for gear in ["PS", "LL"]:
        bio_r = 0.0
        quota_r = 0.0
        w = gear_weights[gear]
        for sp in species_list:
            wt = w.get(sp, 0.0)
            if wt == 0.0:
                continue
            scen = scenario.get(sp, "MSY_100") if isinstance(scenario, dict) else scenario
            key = (scen, year, sp)
            if key in lu:
                bio_r += wt * lu[key]["biomass_ratio"]
                quota_r += wt * lu[key]["quota_ratio"]
            else:
                # Species not in lookup — fall back to 1.0 (no projection available)
                bio_r += wt * 1.0
                quota_r += wt * 1.0

        # If no species matched at all, default to 1.0
        if bio_r == 0.0:
            bio_r = 1.0
            quota_r = 1.0

        blended[gear] = {"biomass_ratio": round(bio_r, 6),
                         "quota_ratio": round(quota_r, 6)}

    _GEAR_BLENDED_CACHE[cache_key] = blended
    return blended


# Legacy wrapper for backward compatibility
def get_schaefer_params(scenario: str, year: int, quota_type="C"):
    """Return (biomass_ratio, quota_ratio) — fleet average of PS+LL blends."""
    b = get_gear_blended_params(scenario, year, quota_type=quota_type)
    bio_r = (b["PS"]["biomass_ratio"] + b["LL"]["biomass_ratio"]) / 2.0
    quota_r = (b["PS"]["quota_ratio"] + b["LL"]["quota_ratio"]) / 2.0
    return bio_r, quota_r

# ---------------------------------------------------------------------------
# LEGACY helpers (kept importable; NOT on the Fig5/Fig4 driver path since
# 2026-09-17). Full factorial = 139,968 combos with no downstream consumers;
# call only from a custom multiprocessing driver if ever needed.
# ---------------------------------------------------------------------------
def build_scenario_matrix():
    """
    Full factorial (user directive 2026-08-28: quota regime is TWO-TIER —
    quota TYPE first, then LEVEL within the type):
      2 quota_types × 4 Schaefer × 3 tech_creep × 3 alt_fuel × 3 WEO ×
      3 retirement × 3 consolidation × 3 target × 3 refrigerant × 2 blend
      = 11664 scenarios
    """
    scenarios = []

    quota_types   = ["C", "F"]                      # C: fixed-catch / F: harvest-rate
    schaefer_list = ["MSY_100", "MSY_90", "MSY_80", "MSY_70"]
    tc_names      = list(TECH_CREEP_LEVELS.keys())     # rapid, steady, slow
    weo_list      = ["STEPS", "APS", "NZE"]            # 3 WEO
    retirement_scenarios = [1, 2, 3]                   # natural, rebuild all, natural+forced
    consol_types         = [0, 1, 2]                   # none, 50%→large, 100%→large
    target_types         = [0, 1, 2]                   # none, 30%, 60% by 2050
    ref_types     = ["R22", "R404a", "LN2"]            # 3 refrigerant
    # TWO-PATH fuel transition (2026-09-04): the two paths are fully
    # independent in the scenario matrix —
    biofuel_growths = [0.0, 0.02, 0.05]                # FAME annual growth
    biofuel_blend_shares = [0.0, 0.30]                 # FAME blend share
    newfuel_types = ["MGO", "NH3_Green"]               # MGO = no renewal
    newfuel_renewal_rates = [0.0, 0.30]                # newbuild renewal rate

    for qt in quota_types:
      for sch in schaefer_list:
        for tc_name in tc_names:
            for weo in weo_list:
                for ret_scen in retirement_scenarios:
                    for cs in consol_types:
                        for target_type in target_types:
                            for ref in ref_types:
                                for bio_growth in biofuel_growths:
                                    for bs in biofuel_blend_shares:
                                        for nft in newfuel_types:
                                            for nr in newfuel_renewal_rates:
                                                p = dict(_BASE_FLEET)
                                                p["quota_type"] = qt
                                                p["schaefer_scenario"] = sch
                                                p["tech_creep_annual"] = TECH_CREEP_LEVELS[tc_name]
                                                p["WEO"] = weo
                                                p["fuel_name"] = "MGO"
                                                p["biofuel_type"] = "FAME"
                                                p["biofuel_annual_growth"] = bio_growth
                                                p["biofuel_blend_share"] = bs
                                                p["newfuel_type"] = nft
                                                p["newfuel_renewal_rate"] = nr
                                                p["retirement_scenario"] = ret_scen
                                                p["consolidation_type"] = cs
                                                p["alt_fuel_target_type"] = target_type
                                                p["refrigerant_type"] = ref
                                                p["elasticity"] = -0.3
                                                p["regulatory_regime"] = "CPS"
                                                if sch in ("MSY_80","MSY_70"):
                                                    p["regulatory_regime"] = "STEPS"
                                                p["forced_retirement_rate"] = 0.05 if ret_scen == 3 else 0.0
                                                p["label"] = (f"{qt}{sch}_{tc_name}_bio{bio_growth:.0%}_{weo}_r{ret_scen}"
                                                              f"_cs{cs}_rn{target_type}_{ref}_b{bs:.0%}_"
                                                              f"nf{nft}_nr{nr:.0%}"
                                                              .replace(".","p"))
                                                scenarios.append(p)

    print(f"  Built {len(scenarios)} scenario combinations")
    return scenarios


def compute_annual_params(base_params, year, ref_year=2025):
    """
    Compute compounded parameter values for a given year.

    Annual compounding:
      tech_creep_year = (1 + tech_creep_annual)^(yrs) - 1    (Palomares & Pauly 2019)
      quota_ratio     = (1 + quota_annual_change)^(yrs)
      alternative_fuel_adoption_rate = min(0.95, alternative_fuel_annual_growth * yrs)
      biomass_ratio   = biomass_ratio_annual (fixed, from climate SPM projection)

    WEO prices queried dynamically per year.
    """
    yrs = year - ref_year
    p = dict(base_params)

    p["tech_creep"]      = (1 + base_params["tech_creep_annual"]) ** yrs - 1
    # TWO-PATH fuel transition (2026-09-04): the two paths are FULLY
    # independent — biofuel blend (share ramp) vs new-fuel renewal (rate ramp).
    p["biofuel_blend_share"] = get_biofuel_blend_share(base_params, year, ref_year=ref_year)
    p["biofuel_type"] = base_params.get("biofuel_type",
                                        base_params.get("alternative_fuel_type", "FAME"))
    p["newfuel_type"] = base_params.get("newfuel_type",
                                        base_params.get("newbuild_fuel", "MGO"))
    p["newfuel_renewal_rate"] = get_newfuel_renewal_rate(base_params, year, ref_year=ref_year)
    # legacy key kept ONLY for old-caller compatibility — never participates
    # in the core calculation (compute_vessel_econ_effort reads the new keys)
    p["alternative_fuel_adoption_rate"] = 0.0
    # Gear-blended biomass_ratio / quota_ratio are resolved dynamically
    # in process_fleet_dynamics_pipeline() via get_gear_blended_params().
    # schaefer_scenario triggers the correct species-level JABBA projections.
    p["schaefer_scenario"] = base_params.get("schaefer_scenario", "MSY_100")

    mgo_p, carbon_p = get_weo_params(base_params["WEO"], year)
    p["price_fuel_USD_tonne"]   = mgo_p
    p["price_carbon_USD_tonne"] = carbon_p
    p["grid_ef_gCO2_kWh"]       = get_grid_ef(base_params["WEO"], year)
    p["refrigerant_type"]       = base_params.get("refrigerant_type", "R22")

    return p


# =============================================================================
# 8. Full Scenario Runner
# =============================================================================
def run_full_scenario_matrix(fleet_df, pm_dict,
                              start_year=2026, end_year=2050):
    """
    Run every scenario in the matrix.  Each WEO background × parameter
    combination runs independently, with parameters compounding annually.
    """
    all_scens = build_scenario_matrix()
    rng = np.random.RandomState(42)
    all_hist = {}

    for idx, scen in enumerate(all_scens):
        label = scen["label"]
        print(f"\n[{idx+1}/{len(all_scens)}] {label}")

        template_pool = build_template_pool(fleet_df)
        current_fleet = fleet_df.copy()
        history = []

        for year in range(start_year, end_year + 1):
            # Compute this year's compounded parameters
            yr_params = compute_annual_params(scen, year)

            survived, alt_fuel_target_fleet, unchanged, effort_mult, _econ = \
                process_fleet_dynamics_pipeline(
                    current_fleet, template_pool, pm_dict, yr_params,
                    current_year=year, rng=rng)

            history.append({
                "Year": year, "WEO": scen["WEO"],
                "Scenario": scen.get("schaefer_scenario", "MSY_100"),
                "tech_creep": yr_params["tech_creep"],
                "alternative_fuel_adoption_rate": yr_params["alternative_fuel_adoption_rate"],
                "N_Vessels": len(survived),
                "Total_Power_MW": survived["Power_kW"].sum() / 1000,
                "Total_GHG_Mt": survived["GHG_Emissions"].sum() / 1e6,
                "MGO_Price_USDt": yr_params["price_fuel_USD_tonne"],
                "Carbon_USDtCO2": yr_params["price_carbon_USD_tonne"],
                "Meco": effort_mult["Meco"],
                "E_final": effort_mult["E_final"],
                "E_final_PS": effort_mult.get("E_final_PS", effort_mult["E_final"]),
                "E_final_LL": effort_mult.get("E_final_LL", effort_mult["E_final"]),
                "bio_ratio_PS": effort_mult.get("bio_ratio_PS", 1.0),
                "bio_ratio_LL": effort_mult.get("bio_ratio_LL", 1.0),
            })

            survived["Age"] = survived["Age"] + 1
            current_fleet = survived.copy()

        hist_df = pd.DataFrame(history)
        all_hist[label] = hist_df
        hist_df.to_csv(os.path.join(OUTPUT_DIR, f"{label}_Annual.csv"), index=False)

    # ================================================================
    # Build summary tables for each key year
    # ================================================================
    for yr in [2030, 2040, 2050]:
        rows = []
        for label, hist in all_hist.items():
            if yr in hist["Year"].values:
                row = hist[hist["Year"] == yr].iloc[0]
                # extract scenario parameters from label
                parts = label.split("_")
                rows.append({
                    "Scenario":   parts[0],
                    "tech_creep": parts[1] if len(parts) > 1 else "",
                    "alt_fuel":   parts[2] if len(parts) > 2 else "af0%",
                    "GHG_Mt":     round(row["Total_GHG_Mt"], 2),
                    "N_Vessels":  int(row["N_Vessels"]),
                    "Power_MW":   round(row["Total_Power_MW"], 0),
                    "E_final":    round(row["E_final"], 3),
                    "E_final_PS": round(row.get("E_final_PS", row["E_final"]), 3),
                    "E_final_LL": round(row.get("E_final_LL", row["E_final"]), 3),
                })
        comp = pd.DataFrame(rows)
        comp.to_csv(os.path.join(OUTPUT_DIR, f"Summary_{yr}.csv"), index=False)

    # Master: all scenarios, all years
    master = pd.concat(all_hist.values())
    master.to_csv(os.path.join(OUTPUT_DIR, "Master_All_Scenarios.csv"), index=False)
    print(f"\n  {len(all_scens)} scenarios complete. Results in {OUTPUT_DIR}/")

    return all_hist


# =============================================================================
# 9. Main Entry
# =============================================================================
def main():
    """CLI stub — main_v2 is a calculation-model interface (2026-09-17).

    Model drivers:
      - figures/Fig5/fig5_run.py        (Fig5 chain; multiprocessing)
      - figures/Fig4/preprocess_fig4.py (Fig4 panels)
    Legacy helpers (build_scenario_matrix / run_full_scenario_matrix) remain
    importable but are not called from here.
    """
    print("main_v2.py is a calculation-model interface - nothing to run here.")
    print("  Fig5 chain : cd figures/Fig5 && C:/CONDA/python fig5_run.py")
    print("  Fig4 panels: cd figures/Fig4 && C:/CONDA/python preprocess_fig4.py")
    return None


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
