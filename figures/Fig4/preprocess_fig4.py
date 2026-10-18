#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fig4 analytical mechanisms. Python exports data; R renders all figures.

References are deliberately different: b = own-WEO 2023 MGO; d/e = same-year
MGO; fleet_model = own-WEO 2025 MGO. Panel c preserves the original dynamic
gear ratio-of-blends illustration, rather than the production flag/org
weighted mean of species Meco. See Fig4_Audit_Report.md.
"""
import os
import sys
import time
from functools import lru_cache
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FIG_DIR = HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCEN = os.path.join(ROOT, "scenario")
SCOUT = os.path.join(SCEN, "output")
sys.path.insert(0, os.path.join(ROOT, "GHG_Calculation"))
sys.path.insert(0, SCEN)
import fleet_model
import price_loader as pl

TECH = {"slow": .019, "steady": .024, "rapid": .043}
MSYS = ["MSY_100", "MSY_90", "MSY_80", "MSY_70"]
WEO = ["STEPS", "APS", "NZE"]
SPECIES = ["SBT", "SKJ", "BET", "YFT", "ALB"]
SP_COLS = [s + "_Tonnes" for s in SPECIES]
FUELS = ["MGO", "HFO", "FAME", "HVO", "LNG_Fossil", "H2_Fossil", "NH3_Green", "H2_Green"]
GROUP_ORDER = ["Advanced economies with net-zero pledges*",
               "Selected EMDE with net-zero pledges**",
               "Selected EMDE without net-zero pledges",
               "Other emerging market & developing economies"]
REGION_GROUP = dict(zip(GROUP_ORDER, GROUP_ORDER))
REGION_GROUP.update({"European Union": GROUP_ORDER[0], "Canada": GROUP_ORDER[0],
                     "Korea": GROUP_ORDER[0], "China": GROUP_ORDER[1],
                     "Chile & Colombia": GROUP_ORDER[1]})
REGION = {"STEPS": "European Union", "APS": GROUP_ORDER[0], "NZE": GROUP_ORDER[0]}


def export(df, name, keys):
    if df.empty or df.duplicated(keys).any():
        raise ValueError(f"Empty or duplicate {name}: {keys}")
    numeric = df.select_dtypes(include="number")
    if np.isinf(numeric.to_numpy()).any():
        raise ValueError(f"Infinite values in {name}")
    df.to_csv(os.path.join(FIG_DIR, name), index=False)


def projection(design):
    suffix = "_F" if design == "F" else ""
    d = pd.read_csv(os.path.join(SCOUT, f"schaefer_biomass_annual{suffix}.csv"))
    d = d[d.Stock != "All"].copy()
    scenarios = MSYS + (["C2024"] if design == "C" else [])
    expected = pd.MultiIndex.from_product([range(2024, 2051), SPECIES, scenarios],
                                          names=["Year", "Stock", "Scenario"])
    idx = pd.MultiIndex.from_frame(d[["Year", "Stock", "Scenario"]])
    assert idx.is_unique and set(idx) == set(expected), f"Incomplete {design} projection"
    cols = ["Catch_Mt", "Biomass_Mt", "K_Mt", "biomass_ratio", "quota_ratio"]
    assert np.isfinite(d[cols]).all().all() and (d[cols] > 0).all().all()
    assert (d.Biomass_Mt <= d.K_Mt + .06).all(), "Biomass exceeds carrying capacity"
    return d


def linear(anchors, year, policy=False):
    """Linear prices; carbon stays zero until the first positive policy anchor."""
    yrs = sorted(anchors)
    assert len(yrs) >= 2 and np.isfinite(list(anchors.values())).all()
    if year in anchors:
        return float(anchors[year])
    if policy:
        for a, b in zip(yrs[:-1], yrs[1:]):
            if a < year < b and anchors[a] == 0:
                return 0.0
    return float(np.interp(year, yrs, [anchors[y] for y in yrs]))


@lru_cache(maxsize=1)
def carbon_reference():
    cr = pd.read_excel(pl.PRICE_MATRIX_PATH, sheet_name="Carbon_Reference")
    cr = cr.dropna(subset=["Carbon_USDtCO2"])
    assert not cr.duplicated(["Scenario", "WEO_Region", "Year"]).any()
    assert np.isfinite(cr.Carbon_USDtCO2).all() and (cr.Carbon_USDtCO2 >= 0).all()
    return cr


@lru_cache(maxsize=None)
def fuel_price(fuel, weo, year):
    """Validate the exact anchor row before calling the canonical price loader.

    Explicit aggregate regions avoid its silent EU/first-row fallback in APS/NZE.
    """
    pm = pl.load_price_long()
    row = pm[(pm.Fuel == pl._FUEL_ALIASES[fuel]) & (pm.Scenario == weo)
             & (pm.Year == year) & (pm.WEO_Region == REGION[weo])]
    assert len(row) == 1, f"Missing/duplicate price: {fuel}/{weo}/{year}/{REGION[weo]}"
    assert np.isfinite(row[["Price_Min", "Price_Max"]]).all().all()
    assert (row.Price_Min > 0).all() and (row.Price_Max >= row.Price_Min).all()
    return pl.get_fuel_price(fuel, weo, year, REGION[weo], "mid")


def historical_catch():
    return pd.read_csv(fleet_model.GRID_PATH, usecols=["Gear"] + SP_COLS).groupby("Gear")[SP_COLS].sum()


def panel_a():
    rows = []
    for design in ["C", "F"]:
        d = projection(design)
        d["B_K"] = d.Biomass_Mt / d.K_Mt
        d["Type"] = design
        rows.append(d[d.Year >= 2025])
    export(pd.concat(rows, ignore_index=True), "Fig4_PanelA_Biomass.csv", ["Year", "Stock", "Scenario", "Type"])


def panel_b():
    pm = pl.load_price_long()
    mgo = pm[pm.Fuel == pl._FUEL_ALIASES["MGO"]]
    assert (mgo.groupby(["Scenario", "Year"])[["Price_Min", "Price_Max"]].nunique() == 1).all().all()
    cr = carbon_reference()
    lhv, cf = pl.get_fuel_lhv("MGO"), pl.get_fuel_ef_co2("MGO")
    rows = []
    for weo in WEO:
        pa = {y: fuel_price("MGO", weo, y)[0] for y in [2023, 2030, 2040, 2050]}
        for region, sub in cr[cr.Scenario == weo].groupby("WEO_Region"):
            ca = dict(zip(sub.Year, sub.Carbon_USDtCO2))
            assert {2023, 2040, 2050} <= set(ca) <= {2023, 2030, 2035, 2040, 2050} and ca[2023] == 0
            base = pa[2023] / 1000 / lhv
            for y in range(2023, 2051):
                p, c = linear(pa, y), linear(ca, y, policy=True)
                cost = (p + c * cf) / 1000 / lhv
                rows.append(dict(WEO=weo, Region=region, Group=REGION_GROUP[region], Year=y,
                                 Fuel_Price_USD_t=p, Carbon_USD_t=c, Current_USD_MJ=cost,
                                 Reference_USD_MJ=base, Reference="own-WEO 2023 MGO",
                                 Cost_Ratio=cost/base, M_econ=(cost/base)**-.3))
    export(pd.DataFrame(rows), "Fig4_PanelB_Yearly_M.csv", ["WEO", "Region", "Year"])


def panel_c():
    gc = historical_catch()
    split = gc.div(gc.sum(axis=0), axis=1)
    rows, components = [], []
    for design in ["C", "F"]:
        p = projection(design)
        for gear in ["PS", "LL"]:
            for year in range(2025, 2051):
                sub = p[(p.Year == year) & (p.Scenario == "MSY_100")].set_index("Stock").loc[SPECIES]
                shares = split.loc[gear, SP_COLS].to_numpy()
                wt = sub.Catch_Mt.to_numpy() * shares
                assert wt.sum() > 0
                wt /= wt.sum()
                br, qr = sub.biomass_ratio.to_numpy(), sub.quota_ratio.to_numpy()
                bio, qua = float(wt @ br), float(wt @ qr)
                for label, tc in TECH.items():
                    creep = (1+tc)**(year-2025)
                    meco = qua / max(bio * creep, .01)
                    individual = qr / np.maximum(br * creep, .01)
                    rows.append(dict(Year=year, Gear=gear, Design=design, Tech_Creep=label,
                                     Tech_Rate=tc, Tech_Factor=creep, Biomass_Ratio=bio,
                                     Quota_Ratio=qua, E_req=meco, Meco=meco,
                                     Weighted_Species_Meco=float(wt @ individual),
                                     Aggregation="ratio of dynamic gear blends"))
                    for i, sp in enumerate(SPECIES):
                        components.append(dict(Year=year, Gear=gear, Design=design, Tech_Creep=label,
                                               Stock=sp, Historical_Gear_Share=shares[i],
                                               Catch_Mt=sub.loc[sp, "Catch_Mt"], Species_Weight=wt[i],
                                               Biomass_Ratio=br[i], Quota_Ratio=qr[i], Species_Meco=individual[i]))
    export(pd.DataFrame(rows), "Fig4_PanelC_Effort_Required.csv", ["Year", "Gear", "Design", "Tech_Creep"])
    export(pd.DataFrame(components), "Fig4_PanelC_Species_Components.csv", ["Year", "Gear", "Design", "Tech_Creep", "Stock"])


@lru_cache(maxsize=1)
def _h2green_params():
    fp = pd.read_excel(os.path.join(ROOT, "model_parameters", "Scenario_Fuel_Parameters.xlsx"),
                       sheet_name="Fuel_Parameters", header=None)
    rows = fp[fp[1].astype(str).str.contains("Hydrogen -- Green", regex=False)]
    assert len(rows) == 1
    r = rows.iloc[0]
    lhv = float(r[3]) * 1000  # MJ/g -> MJ/kg
    prices = {2023: (float(r[10])+float(r[11]))/2 * lhv/3.6,
              2050: (float(r[12])+float(r[13]))/2 * lhv/3.6}  # USD/MWh -> USD/t
    return lhv, prices


def economics(f, weo, year):
    lhv_h2, prices_h2 = _h2green_params() if f == "H2_Green" else (None, None)
    if f == "H2_Green":
        p, lhv, cf = linear(prices_h2, year), lhv_h2, 0.0
    else:
        pa = {a: fuel_price(f, weo, a)[0] for a in [2023, 2030, 2040, 2050]}
        p, lhv, cf = linear(pa, year), pl.get_fuel_lhv(f), pl.get_fuel_ef_co2(f)
    cr = carbon_reference()
    sub = cr[(cr.Scenario == weo) & (cr.WEO_Region == REGION[weo])]
    ca = dict(zip(sub.Year, sub.Carbon_USDtCO2))
    assert {2023, 2030, 2040, 2050} <= set(ca) <= {2023, 2030, 2035, 2040, 2050}
    c = linear(ca, year, policy=True)
    mgo_p = linear({a: fuel_price("MGO", weo, a)[0] for a in [2023, 2030, 2040, 2050]}, year)
    base = (mgo_p+c*pl.get_fuel_ef_co2("MGO"))/1000/pl.get_fuel_lhv("MGO")
    cost = (p+c*cf)/1000/lhv
    return dict(Fuel_Price_USDt=p, Carbon_Price_USDtCO2=c, Carbon_Region=REGION[weo],
                LHV_MJ_kg=lhv, Combustion_CO2_kg_kg=cf, Current_USD_MJ=cost,
                Reference_USD_MJ=base, Reference="same-year MGO", Cost_Ratio_vs_MGO=cost/base,
                M_econ=(cost/base)**-.3)


def panel_d():
    rows = [dict(WEO=w, Year=y, Fuel=f, **economics(f, w, y))
            for w in WEO for y in [2030, 2040, 2050] for f in FUELS]
    export(pd.DataFrame(rows), "Fig4_PanelD_Fuel_Cost.csv", ["WEO", "Year", "Fuel"])


def panel_e():
    pm, rows = pl.load_price_long(), []
    for w in WEO:
        for f in FUELS:
            matrix, topup = 0.0, 0.0
            if f not in ["H2_Green", "NH3_Green"]:
                ef = pm.loc[pm.Fuel == pl._FUEL_ALIASES[f], "Total_EF_gCO2_MJ"]
                assert ef.notna().all() and ef.nunique() == 1, f"Nonconstant EF: {f}"
                matrix = float(ef.iloc[0])
                # Restrict the guard to the documented fossil LNG/H2 pathways.
                # MGO/HFO totals include non-CO2 combustion gases; do not infer
                # their WtT by subtracting the CO2-only combustion factor.
                if f in ["LNG_Fossil", "H2_Fossil"]:
                    combustion = pl.get_fuel_ef_co2(f)/pl.get_fuel_lhv(f)*1000
                    wtt = pl.get_fuel_prop(f, "WtT_GHG_gCO2eq_MJ", 0)
                    topup = max(0., wtt-(matrix-combustion))
            for y in range(2023, 2051):
                eco = economics(f, w, y)
                lhv = eco["LHV_MJ_kg"]
                grid = fleet_model.get_grid_ef(w, y)
                kwh = {"NH3_Green": 9.3, "H2_Green": 50.0}.get(f, 0.)
                ef = grid*kwh/lhv if kwh else matrix+topup
                sfc = 175.*pl.get_fuel_lhv("MGO")/lhv
                physical = sfc*ef*lhv/1000
                rows.append(dict(WEO=w, Year=y, Fuel=f, **eco, SFC_g_kWh=sfc,
                                 Matrix_EF_gCO2e_MJ=matrix, WtT_Topup_gCO2e_MJ=topup,
                                 Grid_EF_gCO2e_kWh=grid, Electricity_kWh_kg=kwh,
                                 EF_gCO2e_MJ=ef, Physical_Intensity_gCO2e_kWh=physical,
                                 Intensity_gCO2e_kWh=physical*eco["M_econ"]))
    df = pd.DataFrame(rows)
    # Independent panel-d file must cover every anchor, not an arbitrary subset.
    d = pd.read_csv(os.path.join(FIG_DIR, "Fig4_PanelD_Fuel_Cost.csv"))
    chk = d.merge(df, on=["WEO", "Year", "Fuel"], validate="one_to_one", suffixes=("_d", "_e"))
    assert len(chk) == len(d) == 72
    assert np.allclose(chk.M_econ_d, chk.M_econ_e, rtol=0, atol=1e-12)
    export(df, "Fig4_PanelE_Intensity.csv", ["WEO", "Year", "Fuel"])


def panel_f():
    sch = projection("F")
    sch = sch[sch.Scenario == "MSY_100"].groupby("Year").Catch_Mt.sum()
    gc = historical_catch()
    share = float(gc.loc["PS"].sum()/gc.to_numpy().sum())
    vessels = pd.read_csv(os.path.join(ROOT, "PMM_Imputation", "After_PMM_Vessels.csv"))
    ships = int((vessels.VesselType == "PS").sum())
    assert ships > 0 and 0 < share < 1
    # A fixed registry fleet for a per-ship illustration, not an active-year count.
    # The projection starts in 2024; use that initial state explicitly for 2023.
    annual = []
    for w in WEO:
        for y in range(2023, 2051):
            source_year = max(y, 2024)
            catch = float(sch.loc[source_year])
            ship_catch = catch*share/ships*1e6
            grid = fleet_model.get_grid_ef(w, y)
            annual.append(dict(WEO=w, Year=y, Catch_Source_Year=source_year, Catch_Mt=catch,
                               PS_Catch_Share=share, Registry_PS_Ships=ships,
                               Ship_Catch_t=ship_catch, Grid_EF_gCO2e_kWh=grid,
                               LN2_kg_kg_Fish=1.15, Electricity_kWh_kg_LN2=.56,
                               LN2_tCO2e_ship=ship_catch*1000*1.15*.56*grid/1e6))
    annual = pd.DataFrame(annual)
    leaks = np.unique(np.round(np.r_[np.geomspace(10, 1000, 41), 150., 200., 250., 500.], 1))
    rows = []
    for w in WEO:
        sub = annual[annual.WEO == w].sort_values("Year")
        for leak in leaks:
            r22 = leak*1810/1000
            win = sub[sub.LN2_tCO2e_ship < r22]
            rows.append(dict(WEO=w, Leak_kg_yr=leak, Cross_Year=win.Year.iloc[0] if len(win) else np.nan,
                             Crossed=bool(len(win)), R22_tCO2e_ship=r22, R22_GWP=1810,
                             PS_Catch_Share=share, Registry_PS_Ships=ships))
    export(annual, "Fig4_PanelF_Annual_Components.csv", ["WEO", "Year"])
    export(pd.DataFrame(rows), "Fig4_PanelF_Crossover_By_Leak.csv", ["WEO", "Leak_kg_yr"])


def main():
    args = [a.lower() for a in sys.argv[1:]]
    assert all(a in [*"abcdef", "all"] for a in args), "Use a/b/c/d/e/f/all"
    panels = "abcdef" if not args or "all" in args else "".join(dict.fromkeys(args))
    # e depends on d; regenerate it to prevent comparison against a stale file.
    if "e" in panels and "d" not in panels:
        panels = "d" + panels
    from audit_fig4 import upstream_checks
    upstream_checks()
    t0 = time.time()
    for p in panels:
        globals()["panel_"+p]()
        print(f"Panel {p}: data exported")
    print(f"Fig4 preparation finished in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
