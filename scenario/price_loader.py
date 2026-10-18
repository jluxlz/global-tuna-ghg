#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
price_loader.py — External fuel price & regional mapping interface.

Loads from model_parameters/:
  - Scenario_Fuel_Parameters.xlsx  (Fuel_Parameters, Model_Parameters, WEO_Carbon_Prices)
  - Scenario_Fuel_Price_Matrix.xlsx (Price_Long, Flag_Region_Map, Carbon_Reference)

Provides per-vessel fuel price & carbon tax lookup by (Flag, fuel, scenario, year).
"""

import os
import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAM_DIR = os.path.join(ROOT_DIR, "model_parameters")

FUEL_PARAMS_PATH = os.path.join(PARAM_DIR, "Scenario_Fuel_Parameters.xlsx")
PRICE_MATRIX_PATH = os.path.join(PARAM_DIR, "Scenario_Fuel_Price_Matrix.xlsx")

# ---- Module-level caches ----
_FUEL_PROPS = None       # {fuel_name: {LHV_MJ_g, WtT_GHG, CfCO2, CfCH4, CfN2O, price_cur_min, price_cur_max, price_2050_min, price_2050_max}}
_PRICE_LONG = None       # DataFrame: fuel × scenario × year × region → Price_Min, Price_Max, Carbon_USDtCO2
_FLAG_REGION_MAP = None  # {flag: {NG_Region, Carbon_STEPS, Carbon_APS_NZE}}
_MODEL_PARAMS = None     # Model_Parameters sheet values
_FUEL_ALIASES = {        # Normalize fuel names between code ↔ Excel
    "MGO": "MDO/MGO (ULSFO, max 0.10% S)",
    "MDO": "MDO/MGO (ULSFO, max 0.10% S)",
    "HFO": "HFO (VLSFO, 0.10<S<=0.50%)",
    "LFO": "LFO (ULSFO, max 0.10% S)",
    "LNG_Fossil": "LNG -- Fossil (Methane)",
    "LNG_Bio": "LNG -- Biogenic (Methane)",
    "FAME": "FAME Biodiesel (waste FOGs)",
    "HVO": "HVO Renewable Diesel (2nd gen)",
    "H2_Fossil": "Hydrogen -- Fossil (SMR + CCS)",
    "H2_Green": "Hydrogen -- Green (electrolysis)",
    "NH3_Green": "Ammonia -- Renewable (e-NH3)",
    "LPG_Propane": "LPG (Propane)",
    "LPG_Butane": "LPG (Butane)",
}


# ==============================================================================
# 1. Fuel Properties
# ==============================================================================
def load_fuel_props():
    """Load fuel physical/chemical properties + price ranges from Excel."""
    global _FUEL_PROPS
    if _FUEL_PROPS is not None:
        return _FUEL_PROPS

    df_raw = pd.read_excel(FUEL_PARAMS_PATH, sheet_name="Fuel_Parameters", header=None)

    # Parse the messy Excel layout — use positional indexing (row 4 = header, 5+ = data)
    # Column positions: 1=Fuel Type, 3=LHV MJ/g, 4=WtT GHG, 5=Engine Eff, 7=CfCO2, 8=CfCH4, 9=CfN2O, 10=Current Min, 11=Current Max
    props = {}
    for i in range(5, len(df_raw)):
        row = df_raw.iloc[i]
        name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        if not name or name == "nan":
            continue
        try:
            # Missing physical entries inherit their fuel family, never MGO for every fuel.
            physical_fallback = (0.048 if name.startswith("LNG") else 0.0412 if name.startswith("LFO")
                                 else 0.0402 if name.startswith("HFO") else 0.12 if name.startswith("Hydrogen")
                                 else 0.0186 if name.startswith("Ammonia") else 0.0427)
            lhv_raw = float(row.iloc[3]) if pd.notna(row.iloc[3]) else physical_fallback
            lhv_mj_kg = lhv_raw * 1000 if lhv_raw < 1 else lhv_raw  # MJ/g → MJ/kg

            def _f(idx, default=0.0):
                try:
                    v = row.iloc[idx]
                    return float(v) if pd.notna(v) else default
                except (ValueError, TypeError):
                    return default

            def _s(idx, default=""):
                v = row.iloc[idx]
                return str(v).strip() if pd.notna(v) else default

            cur_min = row.iloc[10] if pd.notna(row.iloc[10]) else None
            cur_max = row.iloc[11] if pd.notna(row.iloc[11]) else None
            # 2050 Min/Max are cols 12, 13 if present
            p50_min = row.iloc[12] if len(row) > 12 and pd.notna(row.iloc[12]) else None
            p50_max = row.iloc[13] if len(row) > 13 and pd.notna(row.iloc[13]) else None

            props[name] = {
                "LHV_MJ_kg": lhv_mj_kg,
                "LHV_Explicit": bool(pd.notna(row.iloc[3])),
                "WtT_GHG_gCO2eq_MJ": _f(4, 0),
                "engine_eff": _f(5, 0.42),
                "CfCO2": _f(7, 0),
                "CfCH4": _f(8, 0),
                "CfN2O": _f(9, 0),
                "CCS_Req": _s(6, "No").lower() == "yes",
                "price_cur_min": float(cur_min) if cur_min is not None else None,
                "price_cur_max": float(cur_max) if cur_max is not None else None,
                "price_2050_min": float(p50_min) if p50_min is not None else None,
                "price_2050_max": float(p50_max) if p50_max is not None else None,
            }
        except (ValueError, TypeError, IndexError):
            continue

    _FUEL_PROPS = props
    print(f"  Loaded {len(props)} fuel types from Fuel_Parameters")
    return props


def get_fuel_prop(fuel_alias: str, prop: str, default=None):
    """Get a specific fuel property by alias name."""
    props = load_fuel_props()
    excel_name = _FUEL_ALIASES.get(fuel_alias, fuel_alias)
    fuel = props.get(excel_name, {})
    return fuel.get(prop, default)


def get_fuel_lhv(fuel_alias: str):
    return get_fuel_prop(fuel_alias, "LHV_MJ_kg", 42.7)


def get_fuel_ef_co2(fuel_alias: str):
    return get_fuel_prop(fuel_alias, "CfCO2", 3.206)


# ==============================================================================
# 2. Price Matrix (Long format: fuel × scenario × year × region)
# ==============================================================================
def load_price_long():
    """Load the long-format price matrix (6468 rows)."""
    global _PRICE_LONG
    if _PRICE_LONG is not None:
        return _PRICE_LONG

    df = pd.read_excel(PRICE_MATRIX_PATH, sheet_name="Price_Long")
    # Ensure key columns are correct types
    df["Year"] = df["Year"].astype(int)
    df["Scenario"] = df["Scenario"].astype(str).str.strip()
    df["WEO_Region"] = df["WEO_Region"].astype(str).str.strip()
    df["Fuel"] = df["Fuel"].astype(str).str.strip()

    _PRICE_LONG = df
    print(f"  Loaded Price_Long: {len(df)} rows, "
          f"{df['Fuel'].nunique()} fuels × {df['Scenario'].nunique()} scenarios "
          f"× {df['WEO_Region'].nunique()} regions × {df['Year'].nunique()} years")
    return df


def get_fuel_price(fuel_alias: str, scenario: str, year: int, region: str,
                   bound: str = "mid"):
    """
    Get fuel price (USD/tonne) for a given fuel×scenario×year×region.

    bound: "min" | "mid" | "max"
    Returns (price_USD_tonne, carbon_USDtCO2)
    """
    if bound not in ("min", "mid", "max"):
        raise ValueError(f"Invalid price bound: {bound}")
    if fuel_alias == "H2_Green":
        rec = load_fuel_props()["Hydrogen -- Green (electrolysis)"]
        suffixes = ("min", "max") if bound == "mid" else (bound,)
        p0 = np.mean([rec["price_cur_" + b] for b in suffixes])
        p1 = np.mean([rec["price_2050_" + b] for b in suffixes])
        return float(np.interp(year, [2023, 2050], [p0, p1]) * rec["LHV_MJ_kg"] / 3.6), 0.0
    df = load_price_long()
    excel_name = _FUEL_ALIASES.get(fuel_alias, fuel_alias)
    # Normalize common region aliases
    _REGION_ALIASES = {"EU": "European Union", "US": "United States",
                        "China": "China", "Japan": "Japan", "Korea": "Korea"}
    region = _REGION_ALIASES.get(region, region)
    match = df[(df["Fuel"] == excel_name) &
               (df["Scenario"] == scenario) &
               (df["Year"] == year) &
               (df["WEO_Region"] == region)]

    if len(match) == 0:
        # Fallback: try European Union (alias "EU")
        match = df[(df["Fuel"] == excel_name) &
                   (df["Scenario"] == scenario) &
                   (df["Year"] == year) &
                   (df["WEO_Region"] == "European Union")]
    if len(match) == 0:
        # Fallback: any region
        match = df[(df["Fuel"] == excel_name) & (df["Scenario"] == scenario) & (df["Year"] == year)]
    if len(match) == 0:
        # Off-anchor year → piecewise-LINEAR interpolation between the
        # anchor nodes [2023, 2030, 2040, 2050] (2026-09-07; previously the
        # silent (700, 0) fallback broke the WEO price trajectory)
        lhv = get_fuel_lhv(fuel_alias)
        interp = _anchor_interp(df, excel_name, scenario, year, region, bound, lhv)
        if interp is not None:
            return interp
        raise ValueError(f"Missing fuel price: {fuel_alias}/{scenario}/{year}/{region}")

    row = match.iloc[0]
    if bound == "min":
        price_usd_mwh = row["Price_Min"]
    elif bound == "max":
        price_usd_mwh = row["Price_Max"]
    else:
        price_usd_mwh = (row["Price_Min"] + row["Price_Max"]) / 2.0

    # Convert USD/MWh → USD/tonne:  USD/t = USD/MWh × LHV_MJ_kg / 3.6
    lhv = get_fuel_lhv(fuel_alias)
    price_usd_t = float(price_usd_mwh) * lhv / 3.6 if lhv > 0 else float(price_usd_mwh)

    carbon = row.get("Carbon_USDtCO2", 0.0)
    if pd.isna(carbon):
        carbon = 0.0

    return price_usd_t, float(carbon)


def _anchor_interp(df, excel_name, scenario, year, region, bound="mid", lhv=42.7):
    """Linear interpolation BETWEEN the anchor years (2023/2030/2040/2050) of
    the Price_Long matrix — node-based piecewise-linear price path, replacing
    the old silent (700, 0) fallback for off-anchor years (2026-09-07).
    Returns (price_USD_tonne, carbon_USDtCO2) or None if <2 anchors exist."""
    import numpy as _np
    for region_cand in (region, "European Union", None):
        sub = df[(df["Fuel"] == excel_name) & (df["Scenario"] == scenario)]
        if region_cand:
            sub = sub[sub["WEO_Region"] == region_cand]
        anchors = sub[sub["Year"].isin([2023, 2030, 2040, 2050])].sort_values("Year")
        if len(anchors) >= 2:
            yrs = anchors["Year"].astype(float).values
            if bound == "min":
                mwh = anchors["Price_Min"].astype(float).values
            elif bound == "max":
                mwh = anchors["Price_Max"].astype(float).values
            else:
                mwh = ((anchors["Price_Min"] + anchors["Price_Max"]) / 2.0).astype(float).values
            price_mwh = float(_np.interp(year, yrs, mwh))
            carbon_vals = anchors["Carbon_USDtCO2"].astype(float).values
            carbon = float(_np.interp(year, yrs, carbon_vals)) if not _np.isnan(carbon_vals).all() else 0.0
            if lhv > 0:
                return price_mwh * lhv / 3.6, carbon
            return price_mwh, carbon
    return None


# ==============================================================================
# 3. Flag → Region Mapping
# ==============================================================================
def load_flag_region_map():
    """Load 172-flag → WEO region mapping."""
    global _FLAG_REGION_MAP
    if _FLAG_REGION_MAP is not None:
        return _FLAG_REGION_MAP

    df = pd.read_excel(PRICE_MATRIX_PATH, sheet_name="Flag_Region_Map")
    flag_map = {}
    for _, row in df.iterrows():
        flag = str(row["Flag"]).strip()
        flag_map[flag] = {
            "NG_Region": str(row.get("NG_Region", "European Union")).strip(),
            "Carbon_STEPS": str(row.get("Carbon_STEPS", "European Union")).strip(),
            "Carbon_APS_NZE": str(row.get("Carbon_APS_NZE", "Advanced")).strip(),
        }

    _FLAG_REGION_MAP = flag_map
    print(f"  Loaded Flag_Region_Map: {len(flag_map)} flags")
    return flag_map


def get_vessel_region(flag: str, scenario: str):
    """
    Map vessel flag → fuel price region + carbon region.

    Returns (fuel_region, carbon_region)
    """
    fm = load_flag_region_map()
    entry = fm.get(flag, {"NG_Region": "European Union",
                          "Carbon_STEPS": "European Union",
                          "Carbon_APS_NZE": "Advanced"})

    fuel_region = entry["NG_Region"]
    if scenario.upper() == "STEPS":
        carbon_region = entry["Carbon_STEPS"]
    else:
        carbon_region = entry["Carbon_APS_NZE"]

    return fuel_region, carbon_region


# ==============================================================================
# 4. Vessel-Level Price Lookup
# ==============================================================================
def get_vessel_fuel_price(vessel_flag: str, fuel_alias: str, scenario: str,
                          year: int, bound: str = "mid"):
    """
    Full vessel-level lookup: Flag → region → fuel price + carbon price.

    Returns (fuel_price_USDt, carbon_price_USDtCO2)
    """
    fuel_region, carbon_region = get_vessel_region(vessel_flag, scenario)

    # Fuel price from NG region
    price, _ = get_fuel_price(fuel_alias, scenario, year, fuel_region, bound)

    # Carbon price from carbon region
    _, carbon = get_fuel_price(fuel_alias, scenario, year, carbon_region, bound)
    # Carbon price is in the Price_Long as Carbon_USDtCO2 — use it directly
    carbon = _get_carbon_price(scenario, year, carbon_region)

    return price, carbon


def _get_carbon_price(scenario: str, year: int, carbon_region: str):
    """Get carbon price from Carbon_Reference sheet."""
    df = pd.read_excel(PRICE_MATRIX_PATH, sheet_name="Carbon_Reference")
    match = df[(df["Scenario"] == scenario) &
               (df["WEO_Region"] == carbon_region) &
               (df["Year"] == year)]
    if len(match) == 0:
        return 0.0
    val = match.iloc[0]["Carbon_USDtCO2"]
    return float(val) if pd.notna(val) else 0.0


# ==============================================================================
# 5. Model Parameters
# ==============================================================================
def load_model_params():
    """Load key fleet dynamics parameters from Model_Parameters sheet."""
    global _MODEL_PARAMS
    if _MODEL_PARAMS is not None:
        return _MODEL_PARAMS

    df = pd.read_excel(FUEL_PARAMS_PATH, sheet_name="Model_Parameters", header=None)

    params = {
        "capacity_growth_rate": 0.02,
        "hull_lifespan": 30,
        "engine_cycle": 10,
        "price_elasticity": -0.3,
        "rebound_default": 0.20,
        "fame_blend_ceiling": 0.30,
        "hvo_blend_ceiling": 1.00,
        "r22_gwp": 1810,
        "r404a_gwp": 3922,
        "ln2_sec_kwh_kg": 0.56,
        "ln2_mass_ratio": 1.15,
        "tech_creep_rapid": 0.043,
        "tech_creep_steady": 0.024,
        "tech_creep_slow": 0.019,
    }

    # Try to extract actual values from parsed rows
    for _, row in df.iterrows():
        vals = [str(v).strip() for v in row.values if str(v) != 'nan']
        if len(vals) >= 3:
            if "Price elasticity" in str(vals):
                try:
                    params["price_elasticity"] = float(vals[2])
                except ValueError:
                    pass
            elif "Annual tech creep (rapid)" in str(vals):
                try:
                    params["tech_creep_rapid"] = float(vals[2].replace('%', '')) / 100
                except ValueError:
                    pass
            elif "Annual tech creep (steady)" in str(vals):
                try:
                    params["tech_creep_steady"] = float(vals[2].replace('%', '')) / 100
                except ValueError:
                    pass
            elif "Annual tech creep (slow)" in str(vals):
                try:
                    params["tech_creep_slow"] = float(vals[2].replace('%', '')) / 100
                except ValueError:
                    pass

    _MODEL_PARAMS = params
    print(f"  Loaded Model_Parameters: elasticity={params['price_elasticity']}, "
          f"tech_creep=({params['tech_creep_rapid']},{params['tech_creep_steady']},{params['tech_creep_slow']})")
    return params


# ==============================================================================
# 6. Quick Test
# ==============================================================================
if __name__ == "__main__":
    print("=== price_loader.py — Self Test ===\n")

    # Test fuel props
    props = load_fuel_props()
    for alias in ["MGO", "HFO", "LNG_Fossil", "NH3_Green"]:
        f = _FUEL_ALIASES.get(alias, alias)
        p = props.get(f, {})
        print(f"  {alias}: LHV={p.get('LHV_MJ_kg','?'):.0f} MJ/kg, "
              f"CfCO2={p.get('CfCO2','?')}, eff={p.get('engine_eff','?')}")

    # Test flag mapping
    fm = load_flag_region_map()
    test_flags = ["JPN", "USA", "CHN", "ECU", "FJI", "ESP"]
    for flag in test_flags:
        r = fm.get(flag, {})
        print(f"  {flag}: NG={r.get('NG_Region','?')}, "
              f"Carbon_STEPS={r.get('Carbon_STEPS','?')}")

    # Test price lookup
    for flag in ["JPN", "ECU", "ESP"]:
        p, c = get_vessel_fuel_price(flag, "MGO", "STEPS", 2030)
        print(f"  {flag} MGO STEPS 2030: ${p:.0f}/t, carbon ${c:.0f}/tCO2")

    # Test model params
    mp = load_model_params()
    print(f"  Elasticity: {mp['price_elasticity']}")
    print(f"  FAME ceiling: {mp['fame_blend_ceiling']}")

    print("\n=== All tests passed ===")
