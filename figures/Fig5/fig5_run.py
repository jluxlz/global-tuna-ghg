#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fig5_run.py — Fig.5 pipeline executor (2026-08-24).

Stage A — Parameter sensitivity (120 LHS sims): RandomForest + SHAP + standardized OLS
           on CUMULATIVE 2025–2050 GHG (full fleet sim response, incl. effort/cost
           channels; sim window 2025–2050, not the 2050 endpoint).
Stage B — Management portfolio (28 combos + baseline = 29 sims, WEO=APS),
           RFMO-SPECIFIC over the 2025–2050 transition period:
           ER_cum (cumulative reduction vs cumulative baseline), ΔmeanMeco
           (period-mean ecological improvement), ΔGHG_cum (Mt), ΔHPY (supplementary);
           2050-endpoint metrics kept as secondary. Pareto front per RFMO on
           [ER_cum, DeltaMeanMeco, Intensity] (NEVER a global front), synergy
           SI_mn = ER_cum(m+n) − ER_cum(m) − ER_cum(n) per RFMO + global mean.
           5 measures  Q quota (MSY_100→80)  G gear shift (LL→PS δ=0.10)
                       F fuel (FAME B30 drop-in)  T tech-creep (steady→rapid)
                       R retirement (2→3, forced 0.05)
           ρ_ef,g(c) = pure-EF multiplier from fleet_model fleet sims
           (combo fuel params vs baseline fuel params on the SAME final fleet,
           gear_effort=None → E_final = 1, so the effort channel is NOT double-counted).
Stage C — GLOBAL priority (2025–2050 cumulative): I1/I2 = cumulative GHG / catch
           share with a GLOBAL denominator (cum_i/Σ_all cum) — directly comparable
           across RFMOs; I3 = period-mean Meco; I4 management potential = max over
           that RFMO's OWN Pareto set of the OBJECT-LEVEL CUMULATIVE ER
           (ER_i,c,cum, links panel b → c); TOPSIS with global Min-Max
           standardisation across ALL objects, 4 weight sets; Consensus = global
           top tercile in >=3 of 4, Robust = 4/4. Global_Rank (global) +
           Priority_local / RFMO_Local_Rank (within-RFMO, secondary) both saved.

Outputs → scenario/output/fig5/  (CSVs; Fig5B_RFMO_*.csv, Fig5C_RFMO_SpeciesGear_Priority.csv)
Renders  → figures/Fig5/          (plot_fig5.r)
Record   → figures/Fig5/fig5.md
"""

import os
import sys
import time
import json
import warnings
import io
import contextlib
import numpy as np
import pandas as pd
from multiprocessing import Pool

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scenario"))
sys.path.insert(0, HERE)
import fleet_model
from scenario_seeds import paired_seed, record_seed_protocol, require_seed_protocol
import price_loader as pl
import fig5_allocation as alloc

OUT = os.path.join(ROOT, "scenario", "output", "fig5")
os.makedirs(OUT, exist_ok=True)

N_WORKERS = max(2, min(16, os.cpu_count() - 4))
_W = {}  # worker state

# One explicit seed per future, shared by its baseline and every policy.
# Separate futures retain seeds 42..122; policy/task offsets are forbidden.
SEED_OFFSET = 42
# =====================================================================
# BAU (baseline) parameter centre — user directive 2026-08-28:
#   catch  = 2024 ACTUAL level (schaefer scenario C2024, no quota inflation)
#   growth = lowest historical fit 0.21%/yr (2008-2017, analyze_capacity_growth.py)
#   tc     = lowest tech-creep 1.9%/yr (slow, Palomares & Pauly 2019)
#   ret    = mode 2 (rebuild/refresh only)
#   weo    = STEPS (established external background)
#   fuel   = historical fossil only (MGO fleet_model; TP/SA = HFO), no alternative fuels
# =====================================================================
BASE_CENTER = dict(weo="STEPS", msy="C2024", tc=0.019, ret=2, forced=0.0,
                   target=0, biofuel_blend_share=0.0, biofuel_type="FAME",
                   newfuel_type="MGO", newfuel_renewal_rate=0.0,
                   growth=0.0021, lifespan=30, elasticity=-0.3)


# ---------------------------------------------------------------- parameters
def make_params(weo="APS", msy="C2024", tc=0.024, ret=2, forced=0.0,
                target=0, biofuel_blend_share=0.0, biofuel_type="FAME",
                newfuel_type="MGO", newfuel_renewal_rate=0.0,
                growth=0.02, lifespan=30, elasticity=-0.3, quota_type="C",
                consol=0, ref="R22"):
    p = dict(fleet_model._BASE_FLEET)
    p.update({
        "tech_creep": tc, "schaefer_scenario": msy, "WEO": weo,
        "fuel_name": "MGO",
        # TWO-PATH fuel transition (2026-09-04):
        "biofuel_type": biofuel_type, "biofuel_blend_share": biofuel_blend_share,
        "newfuel_type": newfuel_type, "newfuel_renewal_rate": newfuel_renewal_rate,
        "retirement_scenario": ret, "forced_retirement_rate": forced,
        "alt_fuel_target_type": target, "capacity_growth_rate": growth,
        "max_lifespan": lifespan, "elasticity": elasticity,
        "quota_type": quota_type,
        "consolidation_type": consol, "refrigerant_type": ref,
        "price_fuel_USD_tonne": fleet_model.get_weo_params(weo, 2050)[0],
        "price_carbon_USD_tonne": fleet_model.get_weo_params(weo, 2050)[1],
        "grid_ef_gCO2_kWh": fleet_model.get_grid_ef(weo, 2050),
    })
    nb_p, _ = pl.get_fuel_price(newfuel_type, weo, 2050, "EU", "mid")
    p["price_newbuild_USD_tonne"] = nb_p
    return p


# ---------------------------------------------------------------- workers
def _quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), \
         contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **k)


def _init_worker(fleet, pm):
    _W["fleet"] = fleet
    _W["pm"] = pm


def _sim(params, seed, return_econ=False):
    if return_econ:
        hist, final, rfmo_agg, spec_agg, rfmo_ghg, spec_ghg, teff = _quiet(
            fleet_model.run_scenario_simulation, _W["fleet"], _W["pm"],
            params, start_year=2025, end_year=2050, random_seed=seed,
            return_econ_agg=True)
        return hist, final, rfmo_agg, spec_agg, rfmo_ghg, spec_ghg, teff
    hist, final = _quiet(fleet_model.run_scenario_simulation, _W["fleet"], _W["pm"],
                         params, start_year=2025, end_year=2050, random_seed=seed)
    return hist, final


def _sens_task(args):
    params, seed = args
    hist, _ = _sim(params, seed)
    return float(hist.Total_GHG_tCO2e.sum())   # 2025–2050 cumulative GHG


def _rho_task(args):
    """ρ_ef per gear: combo fuel params vs baseline fuel params, SAME final fleet,
    gear_effort=None → E_final = 1 (pure emission-factor/tech ratio).
    FUEL TRANSITION (2026-09-11): bio ADOPTION (drop-in fleet share at the
    fuel's blend limit gamma) + new-fuel renewal (device-dependent) enter the
    EF ratio exactly like the fleet_model simulation.
    NOTE: compute_fleet_ghg mutates df in place — each call needs its own copy,
    otherwise the second call overwrites the first (rho would be 1.0 exactly).
    Also collects from the same sim: (i) vessel-level M_econ aggregates
    (RFMO × Year, Organization × Species × Gear × Year, effort-weighted) and
    (ii) RFMO × Year fleet-simulation GHG (all mechanisms)."""
    params, seed, base_fuel = args
    hist, final, rfmo_agg, spec_agg, rfmo_ghg, spec_ghg, _teff = _sim(params, seed, return_econ=True)

    def _node_2050(p, key):
        nodes = p.get(key)
        if nodes:
            kk = max(int(k) for k in nodes)
            v = nodes.get(kk, nodes.get(str(kk)))   # JSON keys are str
            return float(v)
        return None
    _bio_adopt = _node_2050(params, "biofuel_nodes")
    if _bio_adopt is None:
        _bio_adopt = float(params.get("biofuel_blend_share", 0.0))
    _new_rate = _node_2050(params, "newfuel_nodes")
    if _new_rate is None:
        _new_rate = float(params.get("newfuel_renewal_rate", 0.0))
    _bio_type = params.get("biofuel_type", "FAME")
    g = fleet_model.compute_fleet_ghg(final.copy(), _W["pm"], ref_year=2050, gear_effort=None,
                                  bio_adopt=_bio_adopt,
                                  bio_gamma=fleet_model.get_biofuel_blend_limit(params, _bio_type),
                                  bio_type=_bio_type,
                                  newfuel_type=params.get("newfuel_type", "MGO"),
                                  newfuel_rate=_new_rate,
                                  refrigerant_type=params.get("refrigerant_type", "R22"),
                                  grid_ef=fleet_model.get_grid_ef(params.get("WEO", "APS"), 2050))
    b = fleet_model.compute_fleet_ghg(final.copy(), _W["pm"], ref_year=2050, gear_effort=None,
                                  bio_adopt=0.0, bio_type="FAME",
                                  newfuel_type="MGO", newfuel_rate=0.0,
                                  refrigerant_type=params.get("refrigerant_type", "R22"))
    rho = {}
    for gear in ["PS", "LL"]:
        a = g[g.VesselType == gear].GHG_Emissions.sum()
        c = b[b.VesselType == gear].GHG_Emissions.sum()
        rho[gear] = (a / c) if c > 0 else 1.0
    return rho, rfmo_agg, spec_agg, rfmo_ghg, spec_ghg


def _policy_task(args):
    """Policy-package simulation: full sim + WtT decomposition + PS/LL GHG.
    Returns (rfmo_ghg, spec_ghg, wtt_share, rho, rfmo_agg)."""
    params, seed, base_fuel = args
    hist, final, rfmo_agg, spec_agg, rfmo_ghg, spec_ghg, teff = _sim(params, seed, return_econ=True)
    g = fleet_model.compute_fleet_ghg(final.copy(), _W["pm"], ref_year=2050, gear_effort=None,
                                  bio_share=params.get("biofuel_blend_share", 0.0),
                                  bio_type=params.get("biofuel_type", "FAME"),
                                  newfuel_type=params.get("newfuel_type", "MGO"),
                                  newfuel_rate=params.get("newfuel_renewal_rate", 0.0),
                                  refrigerant_type=params.get("refrigerant_type", "R22"))
    b = fleet_model.compute_fleet_ghg(final.copy(), _W["pm"], ref_year=2050, gear_effort=None,
                                  bio_share=0.0, bio_type="FAME",
                                  newfuel_type="MGO", newfuel_rate=0.0,
                                  refrigerant_type="R22")
    rho = {}
    for gear in ["PS", "LL"]:
        a = g[g.VesselType == gear].GHG_Emissions.sum()
        c = b[b.VesselType == gear].GHG_Emissions.sum()
        rho[gear] = (a / c) if c > 0 else 1.0
    tot_ghg = float(g.GHG_Emissions.sum())
    wtt_share = float(g.GHG_Fuel_WtT.sum() / tot_ghg) if tot_ghg > 0 else 0.0
    return rfmo_ghg, spec_ghg, wtt_share, rho, rfmo_agg


# ---------------------------------------------------------------- Stage A
def run_sensitivity(N=120):
    rng = np.random.default_rng(SEED_OFFSET)
    feats = {
        "growth":        lambda: rng.uniform(0.00, 0.05),
        "lifespan":      lambda: rng.uniform(20, 40),
        "forced":        lambda: rng.uniform(0.0, 0.10),
        "tc":            lambda: rng.uniform(0.010, 0.050),
        "elasticity":    lambda: rng.uniform(-0.50, -0.10),
        "bio_share":     lambda: rng.uniform(0.0, 0.30),
        "ret":           lambda: int(rng.choice([1, 2, 3])),
        "target":        lambda: int(rng.choice([0, 1, 2])),
        "msy":           lambda: str(rng.choice(["MSY_100", "MSY_90", "MSY_80", "MSY_70"])),
        "quota":         lambda: str(rng.choice(["C", "F"])),
        "weo":           lambda: str(rng.choice(["STEPS", "APS", "NZE"])),
        "nbf":           lambda: str(rng.choice(["MGO", "LNG_Fossil", "NH3_Green"])),
        "consol":        lambda: int(rng.choice([0, 1, 2])),
        "ref":           lambda: str(rng.choice(["R22", "R404a", "LN2"])),
        "altfuel":       lambda: str(rng.choice(["FAME", "HVO"])),
    }
    rows, tasks = [], []
    for i in range(N):
        s = {k: f() for k, f in feats.items()}
        p = make_params(weo=s["weo"], msy=s["msy"], tc=s["tc"], ret=s["ret"],
                        forced=s["forced"], target=s["target"],
                        biofuel_blend_share=s["bio_share"], biofuel_type=s["altfuel"],
                        newfuel_type=s["nbf"], newfuel_renewal_rate=0.0,
                        growth=s["growth"], lifespan=s["lifespan"],
                        elasticity=s["elasticity"], quota_type=s["quota"],
                        consol=s["consol"], ref=s["ref"])
        rows.append(s)
        tasks.append((p, SEED_OFFSET + i))

    t0 = time.time()
    with Pool(N_WORKERS, initializer=_init_worker, initargs=pool_args) as pool:
        ys = pool.map(_sens_task, tasks, chunksize=4)
    dt = time.time() - t0
    X = pd.DataFrame(rows)
    X["GHG_Mt_2050"] = np.array(ys) / 1e6

    # ---- RandomForest + SHAP ----
    import shap
    from sklearn.ensemble import RandomForestRegressor
    Xd = X.drop(columns=["GHG_Mt_2050"])
    Xe = Xd.copy()
    for c in ["ret", "target"]:
        Xe[c] = Xe[c].astype(int)
    for c in ["msy", "weo", "nbf", "ref"]:
        Xe = pd.concat([Xe.drop(columns=[c]),
                        pd.get_dummies(Xe[c], prefix=c, dtype=float)], axis=1)
    # Binary quota type as a single 0/1 feature (C=0, F=1) — avoids collinear dummies
    Xe["quota_F"] = (Xd["quota"] == "F").astype(float)
    Xe = Xe.drop(columns=["quota"])
    # Binary alt-fuel type as a single 0/1 feature (FAME=0, HVO=1)
    Xe["altfuel_HVO"] = (Xd["altfuel"] == "HVO").astype(float)
    Xe = Xe.drop(columns=["altfuel"])
    # consol is ordinal 0/1/2 — kept as numeric (monotone consolidation intensity)
    rf = RandomForestRegressor(n_estimators=400, max_depth=8, random_state=SEED_OFFSET,
                               n_jobs=-1)
    rf.fit(Xe, X["GHG_Mt_2050"])
    expl = shap.TreeExplainer(rf)
    sv = expl.shap_values(Xe)
    imp = np.abs(sv).mean(axis=0)

    # ---- standardized OLS (sign + magnitude check) ----
    Zn = Xe.astype(float)
    Zn = (Zn - Zn.mean()) / (Zn.std(ddof=0) + 1e-12)
    yn = (X["GHG_Mt_2050"] - X["GHG_Mt_2050"].mean()) / (X["GHG_Mt_2050"].std(ddof=0) + 1e-12)
    Xmat = np.column_stack([np.ones(len(Zn)), Zn.values])
    beta = np.linalg.lstsq(Xmat, yn.values, rcond=None)[0][1:]
    r2 = 1 - np.sum((Xmat @ np.linalg.lstsq(Xmat, yn.values, rcond=None)[0] - yn.values) ** 2) \
         / np.sum((yn.values - yn.values.mean()) ** 2)

    out = pd.DataFrame({"Feature": Xe.columns,
                        "Importance_SHAP": imp,
                        "OLS_beta_std": beta}).sort_values("Importance_SHAP", ascending=False)
    out.to_csv(os.path.join(OUT, "Fig5A_Sensitivity.csv"), index=False)
    X.to_csv(os.path.join(OUT, "Fig5A_Samples.csv"), index=False)
    rec = {"N": N, "R2": float(r2), "secs": round(dt, 1),
           "n_sims": N, "stage": "A"}
    with open(os.path.join(OUT, "Fig5A_meta.json"), "w") as f:
        json.dump(rec, f, indent=1)
    print(f"[A] sensitivity: {N} sims in {dt:.0f}s, R2={r2:.3f}")
    print(out.head(10).to_string(index=False))
    return out, X


# ---------------------------------------------------------------- Stage B
# MANAGEMENT-MEASURE library (2026-09-06 classification): ONLY true management
# measures a government can implement. WEO / growth / tech creep are EXTERNAL
# SCENARIO DRIVERS (future world) — their sensitivity is Stage A; quota is a
# REGIME (C = fixed-2024 catch, F = harvest-rate HCR), never a free measure.
#   lifespan:   L20/L25/L35/L40 (baseline 30)
#   retirement: R1/R2/R3 (R3 = dynamic capacity balance)
#   fuel blend: B1/B2/B3 = FAME 10/20/30%; H3/H6/H10 = HVO 30/60/100%
#   target:     T3/T6 = alt-fuel target 30/60% by 2050
#   newbuild:   NL/NH/N2 = LNG/NH3/H2 (baseline MGO)
#   upscale:    U1/U2 = 50/100% to large
#   refrig:     R404/LN = R404a/LN2 (baseline R22)
MEASURES = {
    # lifespan
    "L20": ("max_lifespan", 20),
    "L25": ("max_lifespan", 25),
    "L35": ("max_lifespan", 35),
    "L40": ("max_lifespan", 40),
    # retirement (three modes — R3 = dynamic capacity balance, no fixed rate)
    "R1":  ("retirement_scenario", 1),
    "R2":  ("retirement_scenario", 2),
    "R3":  ("retirement_scenario", 3),
    # fuel blend (Path A — biofuel blend)
    "B1":  ("fuel", "FAME", 0.10),
    "B2":  ("fuel", "FAME", 0.20),
    "B3":  ("fuel", "FAME", 0.30),
    "H3":  ("fuel", "HVO", 0.30),
    "H6":  ("fuel", "HVO", 0.60),
    "H10": ("fuel", "HVO", 1.00),
    # alt-fuel target / renewal rate (all three levels)
    "T3":  ("target", 1),
    "T6":  ("target", 2),
    # new-fuel vessel renewal (Path B — dedicated new-fuel propulsion on newbuilds)
    "NL":  ("newfuel", "LNG_Fossil"),
    "NH":  ("newfuel", "NH3_Green"),
    "N2":  ("newfuel", "H2_Fossil"),
    # consolidation
    "U1":  ("consol", 1),
    "U2":  ("consol", 2),
    # refrigerant
    "R404": ("refrigerant", "R404a"),
    "LN":  ("refrigerant", "LN2"),
}

SINGLE_MEASURES = ["L20", "L25", "L35", "L40",
                   "R1", "R2", "R3",
                   "B1", "B2", "B3", "H3", "H6", "H10",
                   "T3", "T6",
                   "NL", "NH", "N2",
                   "U1", "U2",
                   "R404", "LN"]

# ---- FUEL POLICY PACKAGES (2026-09-07): concrete decarbonisation routes,
#      evaluated as POLICY PACKAGES (not algorithmically-optimised measures).
#      Each package is a defensible, industry-real policy option. ----
POLICY_PACKAGES = {
    "Path-Bio":      {"biofuel_blend_share": 0.30, "biofuel_type": "HVO"},
    "Path-Gas":      {"newfuel_type": "LNG_Fossil", "newfuel_renewal_rate": 0.30},
    "Path-Ammonia":  {"newfuel_type": "NH3_Green", "newfuel_renewal_rate": 0.30},
    "Path-Hybrid":   {"biofuel_blend_share": 0.30, "biofuel_type": "HVO",
                      "newfuel_type": "NH3_Green", "newfuel_renewal_rate": 0.30},
    "Path-Hybrid+":  {"biofuel_blend_share": 0.30, "biofuel_type": "HVO",
                      "newfuel_type": "NH3_Green", "newfuel_renewal_rate": 0.30,
                      "retirement_scenario": 3, "refrigerant_type": "LN2",
                      "consolidation_type": 1},
}

# Single source of measure metadata — exported to Fig5B_Measures.csv so the
# FIGURES read the SAME measure set the model computed (no hand-maintained
# lists in the plotting scripts; fleet_model/fig5_run are the algorithm authority).
MEASURE_LABELS = {
    "L20": "L20 (lifespan 20)", "L25": "L25 (lifespan 25)",
    "L35": "L35 (lifespan 35)", "L40": "L40 (lifespan 40)",
    "R1": "R1 (retire 1)", "R2": "R2 (retire 2)", "R3": "R3 (retire 3, dynamic balance)",
    "B1": "B1 (FAME 10%)", "B2": "B2 (FAME 20%)", "B3": "B3 (FAME 30%)",
    "H3": "H3 (HVO 30%)", "H6": "H6 (HVO 60%)", "H10": "H10 (HVO 100%)",
    "T3": "T3 (target 30%)", "T6": "T6 (target 60%)",
    "NL": "NL (newbuild LNG)", "NH": "NH (newbuild NH3)", "N2": "N2 (newbuild H2)",
    "U1": "U1 (upscale 50%)", "U2": "U2 (upscale 100%)",
    "R404": "R404 (R404a)", "LN": "LN (LN2)",
}

# ---- candidate portfolios: COMPLETE enumeration + unbounded greedy beam
#      (2026-09-03): every scenario parameter is a candidate measure, NO
#      measure-count cap; the search space is generated inside run_portfolio
#      (generate_all_portfolios + greedy_beam_expand).
import fig5_optimizer as opt
from fig5_optimizer import (best_portfolio_by_n, incremental_benefit,
                            best_by_group, incremental_benefit_by_group)
WEO_SINGLE_COMBOS = set()   # filled in run_portfolio (WS/WA/WN)


def combo_params(combo):
    """Apply named measures on top of BASE_CENTER via make_params."""
    p = make_params(**{k: v for k, v in BASE_CENTER.items() if k not in ("weo",)})
    for m in combo:
        spec = MEASURES[m]
        kind, val = spec[0], spec[1]
        if kind == "fuel":                     # Path A — biofuel blend
            p["biofuel_type"] = val
            p["biofuel_blend_share"] = spec[2]
        elif kind == "newfuel":                  # Path B — new-fuel renewal
            p["newfuel_type"] = val
            p["newfuel_renewal_rate"] = 1.0     # all newbuilds renewed
        elif kind == "target":
            p["alt_fuel_target_type"] = val
        elif kind == "retirement_scenario":
            p["retirement_scenario"] = val
            p["forced_retirement_rate"] = 0.0   # R3 = dynamic balance, no fixed rate
        elif kind == "max_lifespan":
            p["max_lifespan"] = val
        elif kind == "consol":
            p["consolidation_type"] = val
        elif kind == "refrigerant":
            p["refrigerant_type"] = val
    return p


# ---- MITIGATION PATHWAY DEFINITIONS (2026-09-08 FINAL) ----
# External BAU = (WEO x Growth x Retirement x TechCreep) — 81 free combos.
# Mitigation = Fuel / Refrigerant / Consolidation pathways (NOT part of BAU).
BAU_WEO    = ["STEPS", "APS", "NZE"]
BAU_GROWTH = [0.0021, 0.0136, 0.0272]        # Low / Medium / High
BAU_RETIRE = {"Natural": 1, "Renewal": 2, "Forced": 3}
BAU_TECH   = [0.019, 0.024, 0.043]           # Slow / Steady / Rapid

FUEL_NODE_YEARS = [2030, 2040, 2050]
# User-confirmed top schemes (2026-09-11): HVO bio adoption + device fuel
# per WEO — STEPS/APS -> H2_Green, NZE -> NH3_Green. Other combos go to SI.
WEO_DEVICE_FUEL = {"STEPS": "H2_Green", "APS": "H2_Green", "NZE": "NH3_Green"}


def _fuel_nodes(level, weo=None):
    """v16 Fuel scheme params for one intensity: bio = fleet adoption share
    (drop-in HVO), device = newbuild renewal (per-WEO top device fuel)."""
    lv = FUEL_LEVELS_V16[level]
    dev = WEO_DEVICE_FUEL.get(weo, "NH3_Green")
    return {"biofuel_nodes": {y: v for y, v in zip(FUEL_NODE_YEARS, lv["bio"])},
            "biofuel_type": "HVO",
            "newfuel_nodes": {y: v for y, v in zip(FUEL_NODE_YEARS, lv["renewal"])},
            "newfuel_type": dev}

# mitigation pathways (2026-09-08 FINAL): FUEL transition intensity is BOUND
# to the WEO of the BAU:
#   STEPS -> Fuel-Low (current-policy continuation)
#   APS   -> Fuel-Medium (announced climate pledges realised)
#   NZE   -> Fuel-High (2050 net-zero path)
# Refrigerant / Consolidation use their representative (High) level; the 7
# combinations required by the design are applied per BAU.
WEO_FUEL_LEVEL = {"STEPS": "Low", "APS": "Medium", "NZE": "High"}
REFRIGERANT_MIT = {"refrigerant_type": "LN2"}
CONSOLIDATION_MIT = {"consolidation_type": 2}


def _schemes_for_bau(weo):
    """7 mitigation schemes for one BAU (Fuel intensity bound to its WEO)."""
    fuel = _fuel_nodes(WEO_FUEL_LEVEL[weo], weo)
    ref = dict(REFRIGERANT_MIT)
    cs = dict(CONSOLIDATION_MIT)
    return [
        ("Fuel", fuel),
        ("Refrigerant", ref),
        ("Consolidation", cs),
        ("Fuel+Refrigerant", {**fuel, **ref}),
        ("Fuel+Consolidation", {**fuel, **cs}),
        ("Refrigerant+Consolidation", {**ref, **cs}),
        ("Fuel+Refrigerant+Consolidation", {**fuel, **ref, **cs}),
    ]


def run_portfolio():
    """81-EXTERNAL-BAU x MITIGATION-PATHWAY evaluation (2026-09-08 FINAL).

    Stage 1: 81 free-combination BAU scenarios (WEO x Growth x Retirement x
             TechCreep) — future-world baselines with NO proactive mitigation.
    Stage 2: every BAU receives the mitigation schemes (Fuel / Refrigerant /
             Consolidation, 3 levels + High-level combinations) — reduction is
             measured RELATIVE to that BAU.
    """
    import itertools
    bau_grid = [(w, g, r, t) for w in BAU_WEO for g in BAU_GROWTH
                for r in BAU_RETIRE.values() for t in BAU_TECH]
    bau_ids = {k: f"BAU_{i + 1:03d}" for i, k in enumerate(bau_grid)}

    def _task(bau, mit_pkg, idx):
        w, g, r, t = bau
        p = make_params(weo=w, growth=g, tc=t)
        p["retirement_scenario"] = int(r)
        p["forced_retirement_rate"] = 0.0   # R3 = dynamic balance
        p.update(mit_pkg)
        return (p, paired_seed(bau), None)

    _POOL = Pool(N_WORKERS, initializer=_init_worker, initargs=pool_args)
    def _run_tasks(tasks, fn, chunksize=8):
        return _POOL.map(fn, tasks, chunksize=chunksize)
    def _close_pool():
        _POOL.close(); _POOL.join()

    GHG, SPEC_GHG = {}, {}
    t0 = time.time()

    # ---- Stage 1: 81 BAU baselines ----
    t1 = [_task(b, {}, i) for i, b in enumerate(bau_grid)]
    r1 = _run_tasks(t1, _rho_task)
    for b, (r, ra, sa, rg, sg) in zip(bau_grid, r1):
        GHG[bau_ids[b]] = rg
        SPEC_GHG[bau_ids[b]] = sg

    # ---- Stage 2: mitigation schemes x 81 BAU (Fuel bound to WEO) ----
    t2, k2 = [], []
    for b in bau_grid:
        for name, pkg in _schemes_for_bau(b[0]):
            t2.append(_task(b, pkg, 0))
            k2.append((bau_ids[b], name))
    r2 = _run_tasks(t2, _rho_task)
    for (bid, name), (r, ra, sa, rg, sg) in zip(k2, r2):
        GHG[(bid, name)] = rg
        SPEC_GHG[(bid, name)] = sg
    _close_pool()
    print(f"[B] Stage1 {len(bau_grid)} BAU + Stage2 7 schemes x "
          f"{len(bau_grid)} = {len(t2) + len(t1)} sims in {time.time() - t0:.0f}s")

    # ================= CSV OUTPUTS =================
    idx_cols = ["Organization", "Species", "Gear"]

    # ---- 1) BAU_81_Annual.csv (fleet-level annual) ----
    bau_rows = []
    for b in bau_grid:
        rg = GHG[bau_ids[b]]
        if len(rg):
            g = rg.groupby("Year")["GHG_tCO2e"].sum()
            for y, v in g.items():
                bau_rows.append({"BAU_ID": bau_ids[b],
                                 "WEO": b[0], "Growth": b[1],
                                 "Retirement": [k for k, v2 in BAU_RETIRE.items()
                                                if v2 == b[2]][0],
                                 "TechCreep": b[3],
                                 "Year": int(y), "GHG_Mt": float(v / 1e6)})
    pd.DataFrame(bau_rows).to_csv(os.path.join(OUT, "BAU_81_Annual.csv"), index=False)

    # ---- 2) Mitigation_Results_Annual.csv (reduction vs own BAU) ----
    mit_rows = []
    for b in bau_grid:
        bid = bau_ids[b]
        base = GHG[bid].groupby("Year")["GHG_tCO2e"].sum()
        for name, pkg in _schemes_for_bau(b[0]):
            m = GHG[(bid, name)].groupby("Year")["GHG_tCO2e"].sum()
            lv = WEO_FUEL_LEVEL[b[0]] if name.startswith("Fuel") else ""
            for y in base.index:
                gb, gm = float(base[y]), float(m[y])
                red = 100 * (gb - gm) / gb if gb > 0 else 0.0
                mit_rows.append({"BAU_ID": bid, "WEO": b[0], "Growth": b[1],
                                 "Retirement": [k for k, v2 in BAU_RETIRE.items()
                                                if v2 == b[2]][0],
                                 "TechCreep": b[3],
                                 "Mitigation_Pathway": name,
                                 "Mitigation_Level": lv,
                                 "Year": int(y), "GHG_BAU": gb / 1e6,
                                 "GHG_Mitigation": gm / 1e6,
                                 "GHG_Reduction_pct": round(red, 3)})
    pd.DataFrame(mit_rows).to_csv(
        os.path.join(OUT, "Mitigation_Results_Annual.csv"), index=False)

    # ---- 3) Heterogeneous_Mitigation_Results.csv (object-level cumulative) ----
    het_rows = []
    for b in bau_grid:
        bid = bau_ids[b]
        sg_b = SPEC_GHG[bid].groupby(idx_cols)["GHG_tCO2e"].sum() if len(SPEC_GHG[bid]) else {}
        for name, pkg in _schemes_for_bau(b[0]):
            sg_m = SPEC_GHG[(bid, name)]
            if not len(sg_b) or not len(sg_m):
                continue
            mg = sg_m.groupby(idx_cols)["GHG_tCO2e"].sum()
            lv = WEO_FUEL_LEVEL[b[0]] if name.startswith("Fuel") else ""
            for (o, s, gg), gb in sg_b.items():
                gm = float(mg.get((o, s, gg), 0.0))
                red = 100 * (gb - gm) / gb if gb > 0 else 0.0
                het_rows.append({"BAU_ID": bid, "WEO": b[0], "Growth": b[1],
                                 "Retirement": [k for k, v2 in BAU_RETIRE.items()
                                                if v2 == b[2]][0],
                                 "TechCreep": b[3],
                                 "Gear": gg, "Organization": o, "Species": s,
                                 "Mitigation_Pathway": name,
                                 "Mitigation_Level": lv,
                                 "GHG_BAU": float(gb / 1e6),
                                 "GHG_Mitigation": gm / 1e6,
                                 "Reduction_pct": round(red, 3)})
    pd.DataFrame(het_rows).to_csv(
        os.path.join(OUT, "Heterogeneous_Mitigation_Results.csv"), index=False)

    # ---- 4) Optimal_Mitigation_By_Object.csv (frequency across 81 BAU) ----
    opt_rows = []
    if len(het_rows):
        hdf = pd.DataFrame(het_rows)
        for (o, s, gg), g in hdf.groupby(["Organization", "Species", "Gear"]):
            best = g.groupby("Mitigation_Pathway")["Reduction_pct"].mean().idxmax()
            n_bau = int((g[g.Mitigation_Pathway == best].groupby("BAU_ID").ngroups))
            opt_rows.append({"Gear": gg, "Organization": o, "Species": s,
                             "Optimal_Pathway": best,
                             "Optimal_Reduction": round(
                                 g[g.Mitigation_Pathway == best].Reduction_pct.mean(), 3),
                             "N_BAU_Optimal": n_bau,
                             "P_BAU_Optimal": n_bau / len(bau_grid)})
    pd.DataFrame(opt_rows).to_csv(
        os.path.join(OUT, "Optimal_Mitigation_By_Object.csv"), index=False)

    print(f"[B] outputs: BAU_81_Annual / Mitigation_Results_Annual / "
          f"Heterogeneous_Mitigation_Results / Optimal_Mitigation_By_Object")
    record_seed_protocol(OUT, ["BAU_81_Annual.csv", "Mitigation_Results_Annual.csv",
        "Heterogeneous_Mitigation_Results.csv", "Optimal_Mitigation_By_Object.csv"])
    return GHG, SPEC_GHG


def run_priority(spec_ghg_map, econ_map, ref_w="STEPS"):
    """OBJECT-LEVEL EXPOSURE & PRIORITY (2026-09-07): assessed under a real,
    representative policy package (Path-Hybrid), NOT an algorithmic optimum.
    Reference scenario (STEPS + G021 + TS) is used. Five real-governance
    indicators (higher = more urgent):
        I1 = BAU GHG share       GHG_i(baseline)/ΣGHG(baseline)  — emission exposure
        I2 = Catch share         C0_i/ΣC0                        — food-supply importance
        I3 = Mean Meco           period-mean ecological pressure (stock overburden)
        I4 = Fuel-cost response  ΔM_econ (Hybrid vs baseline, org-level)
        I5 = ER under Path-Hybrid  object-level cumulative reduction under the
                                   representative dual-track package
    Zero-catch objects (C0 < 100 t/yr) are EXCLUDED from the ranking.
    """
    idx_cols = ["Organization", "Species", "Gear"]
    HYBRID = "Path-Hybrid"
    if (ref_w, "") not in spec_ghg_map or (ref_w, HYBRID) not in spec_ghg_map:
        return pd.DataFrame()
    bau = spec_ghg_map[(ref_w, "")].groupby(idx_cols)["GHG_tCO2e"].sum()
    hyb = spec_ghg_map[(ref_w, HYBRID)].groupby(idx_cols)["GHG_tCO2e"].sum()
    tot_ghg = bau.sum()
    sh = alloc.build_shares()
    C0 = sh["C0"]
    mm_bau_s = alloc.mean_meco(BASE_CENTER["msy"], BASE_CENTER["tc"])
    # org-level M_econ (Hybrid vs baseline) — objects share their org's response
    def _mecon_org(ck):
        ra = econ_map.get((ref_w, ck), (None, None))[0]
        if ra is None or not len(ra):
            return {}
        return dict(zip(ra.RFMO, ra.M_econ_realized))
    me_bau = _mecon_org("")
    me_hyb = _mecon_org(HYBRID)

    rows = []
    for (o, s, g) in bau.index:
        gb = float(bau[(o, s, g)])
        if gb <= 0:
            continue
        c0 = float(C0.get((o, s, g), 0.0))
        g_h = float(hyb.get((o, s, g), 0.0))
        er_hyb = 1 - g_h / gb if gb > 0 else 0.0
        dme = float(me_bau.get(o, 1.0)) - float(me_hyb.get(o, 1.0))
        rows.append({"Organization": o, "Species": s, "Gear": g,
                     "GHG_BAU": gb, "Catch_BAU": c0,
                     "I1_GHG": gb / tot_ghg,
                     "I2_Catch": c0 / max(sum(C0.values()), 1e-9),
                     "I3_Meco": mm_bau_s[s],
                     "I4_Mecon": dme,
                     "I5_Mitigation": er_hyb})
    obj = pd.DataFrame(rows)

    # zero-catch exclusion
    CATCH_MIN_T = 100.0
    obj["zero_catch"] = obj.Catch_BAU < CATCH_MIN_T
    n_zero = int(obj.zero_catch.sum())
    obj = obj[~obj.zero_catch].reset_index(drop=True)

    # ---- Min-Max TOPSIS (all benefit-direction) ----
    cols = ["I1_GHG", "I2_Catch", "I3_Meco", "I4_Mecon", "I5_Mitigation"]

    def minmax(rows_sub):
        Z = rows_sub[cols].copy()
        for c in cols:
            lo, hi = Z[c].min(), Z[c].max()
            Z[c] = (Z[c] - lo) / (hi - lo + 1e-12)
        return Z

    def topsis(Z, wgt):
        W = Z.values * np.array(wgt)
        ideal, anti = W.max(axis=0), W.min(axis=0)
        d_pos = np.sqrt(((W - ideal) ** 2).sum(axis=1))
        d_neg = np.sqrt(((W - anti) ** 2).sum(axis=1))
        return d_neg / (d_pos + d_neg + 1e-12)

    Zg = minmax(obj)
    for wname, wgt in TOPSIS_WEIGHTS.items():
        obj[f"Priority_{wname}"] = topsis(Zg, wgt)
    obj["Priority_global"] = obj["Priority_equal"]
    pri_cols = [f"Priority_{w}" for w in TOPSIS_WEIGHTS]
    thr = obj[pri_cols].quantile(0.67)
    obj["N_Top_Sets"] = np.sum([obj[c] >= thr[c] for c in pri_cols], axis=0)
    obj["Consensus"] = obj.N_Top_Sets >= 3
    obj["Robust"] = obj.N_Top_Sets >= 4
    obj["Global_Rank"] = obj["Priority_global"].rank(
        ascending=False, method="min").astype(int)
    obj = obj.sort_values("Priority_global", ascending=False)
    obj.to_csv(os.path.join(OUT, "Fig5F_Object_Priority.csv"), index=False)
    print(f"[C] {len(obj)} objects ranked ({n_zero} zero-catch excluded); "
          f"consensus={obj.Consensus.sum()} robust={obj.Robust.sum()} "
          f"(Hybrid-package exposure TOPSIS)")
    return obj


# =====================================================================
# Fig.5 v15 PROXY EXPORTS (2026-09-08) — zero-simulation panels:
#   Panel b: fuel option comparison from the Fig4e proxy
#            (E_adj = SFC x EF x M_econ, per engine-kWh, power-normalised)
#   Panel c: quota x tech-creep x species Meco proxy with Schaefer
#            sustainability constraint (B/Bmsy >= 0.5)
# =====================================================================
# v16 FUEL PATHWAYS (2026-09-11 user directive): TWO DISTINCT MECHANISMS
#   BIO (drop-in, FAME/HVO)  -> fleet ADOPTION share x physical blend limit
#                               gamma (FAME = 0.30 B30, HVO = 1.00 B100)
#   DEVICE (LNG/NH3/H2)      -> NEWBUILD renewal rate (persistent retrofit)
# Same-fuel dual paths (FAME+FAME) do not exist: bio has ONE correct path.
BIO_FUELS = ["FAME", "HVO"]
DEVICE_FUELS = ["LNG_Fossil", "NH3_Green", "H2_Fossil", "H2_Green"]
ALL_FUELS = ["MGO"] + BIO_FUELS + DEVICE_FUELS
FUEL_LEVELS_V16 = {
    # bio = fleet adoption share nodes (drop-in, allow up to 100%)
    # renewal = newbuild dedicated-device rate nodes
    "Low":    {"bio": [0.20, 0.40, 0.60], "renewal": [0.10, 0.25, 0.40]},
    "Medium": {"bio": [0.40, 0.70, 1.00], "renewal": [0.20, 0.50, 0.70]},
    "High":   {"bio": [0.60, 0.90, 1.00], "renewal": [0.30, 0.70, 0.90]},
}
H2GREEN_KWH_PER_KG = 50.0     # grid kWh per kg H2 (electrolysis)
# Green-H2 parameters read from model_parameters/Scenario_Fuel_Parameters.xlsx
# (Fuel_Parameters sheet, "Hydrogen -- Green" row): LHV 0.12 MJ/g; price
# Current/2050 mid USD/MWh (IRENA 2021 + Commun. Eng. 2025 7->3 EUR/kg) ->
# USD/t via x33.33 (120 MJ/kg = 33.33 kWh/kg), linear 2023-2050.
QUOTA_TC = [0.019, 0.024, 0.043]
SUSTAIN_B_THRESH = 0.25  # B/K below this (equiv. B/Bmsy < 0.5 for Schaefer) fails the screen
# Per-species MSY fraction for the harvest-rate quota arms: the precautionary
# fraction for the most depleted stock (SBT) so it meets the B/Bmsy screen.
MSY_FRAC = {"SKJ": "MSY_100", "YFT": "MSY_100", "BET": "MSY_100",
            "ALB": "MSY_100", "SBT": "MSY_70"}


def _fuel_option_specs(level):
    """All v16 fuel options for one intensity:
    2 bio-only (adoption) + 4 device-only (newbuild renewal) + 8 dual."""
    lv = FUEL_LEVELS_V16[level]
    specs = []
    for bf in BIO_FUELS:
        specs.append({"FuelOption": bf, "Type": "Bio", "BioFuel": bf,
                      "DevFuel": "", "S_bio": lv["bio"][-1], "S_new": 0.0})
    for df_ in DEVICE_FUELS:
        specs.append({"FuelOption": df_, "Type": "Device", "BioFuel": "",
                      "DevFuel": df_, "S_bio": 0.0, "S_new": lv["renewal"][-1]})
    for bf in BIO_FUELS:
        for df_ in DEVICE_FUELS:
            specs.append({"FuelOption": f"{bf}+{df_}", "Type": "Dual",
                          "BioFuel": bf, "DevFuel": df_,
                          "S_bio": lv["bio"][-1], "S_new": lv["renewal"][-1]})
    return specs


def _mix_intensity(e, me, spec):
    """Proxy blend of the v16 mechanisms on one fleet average:
      bio share:    E_bio_mix = (1 - S_bio*gamma) MGO + S_bio*gamma BIO
      device share: E = (1 - s_n) E_bio_mix + s_n E_dev
    (E and me are the Fig4e intensity / M_econ dicts keyed by fuel)."""
    ea, ma = e["MGO"], me["MGO"]
    if spec["BioFuel"]:
        w = spec["S_bio"] * BIO_GAMMA[spec["BioFuel"]]
        ea = (1.0 - w) * ea + w * e[spec["BioFuel"]]
        ma = (1.0 - w) * ma + w * me[spec["BioFuel"]]
    if spec["DevFuel"]:
        ea = (1.0 - spec["S_new"]) * ea + spec["S_new"] * e[spec["DevFuel"]]
        ma = (1.0 - spec["S_new"]) * ma + spec["S_new"] * me[spec["DevFuel"]]
    return ea, ma


BIO_GAMMA = {"FAME": 0.30, "HVO": 1.00}   # physical drop-in blend limits


def export_fuel_options_proxy(out_dir=None):
    """Panel a: 14 v16 fuel options (2 bio + 4 device + 8 dual) x 3 intensities,
    evaluated with the Fig4e per-kWh proxy:
        bio:    E_bio_mix = (1 - S_bio*gamma) E_MGO + S_bio*gamma E_bio
        device: E = (1 - s_n) E_bio_mix + s_n E_dev
    Reduction_2050 = 1 - E_eff(2050)/E_MGO(2050); M_econ effort-weighted.
    """
    out_dir = out_dir or OUT
    fig4_dir = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "Fig4"))
    pe = pd.read_csv(os.path.join(fig4_dir, "Fig4_PanelE_Intensity.csv"))
    pe = pe[(pe.Year == 2050) & (pe.Fuel.isin(ALL_FUELS))]
    if pe.duplicated(["WEO", "Year", "Fuel"]).any():
        raise ValueError("Duplicate Fig4 fuel-intensity keys")
    if set(ALL_FUELS) - set(pe.Fuel):
        raise ValueError("Run current Fig4 preprocessing for every fuel first")
    rows = []
    for weo in BAU_WEO:
        e = {f: float(pe[(pe.WEO == weo) & (pe.Fuel == f)].Intensity_gCO2e_kWh.iloc[0])
             for f in ALL_FUELS}
        me = {f: float(pe[(pe.WEO == weo) & (pe.Fuel == f)].M_econ.iloc[0])
              for f in ALL_FUELS}
        e_mgo = e["MGO"]
        for level in FUEL_LEVELS_V16:
            for spec in _fuel_option_specs(level):
                ea, ma = _mix_intensity(e, me, spec)
                rows.append({"WEO": weo, **spec, "Intensity": level,
                             "Reduction_2050": round(100 * (1 - ea / e_mgo), 2),
                             "M_econ_2050": round(ma, 3)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(out_dir, "Fig5_Fuel_Options.csv"), index=False)
    print(f"[a] fuel options proxy: {len(df)} rows -> Fig5_Fuel_Options.csv")
    return df


def export_quota_species_proxy(out_dir=None, msy_scenario="MSY_100"):
    """Panel b: quota regime (C vs F) x tech creep x species Meco proxy with
    the Schaefer sustainability guard:
        Meco = quota_ratio / (biomass_ratio * (1+tc)^dt)
    The MSY_100 reference keeps the regime contrast crisp (C-type fracMSY
    collapses the sensitive stocks, F-type HCR stays healthy -> recommend F).
    NOTE: C2024 is used ONLY for the 81-scenario BASELINE simulations
    (make_params default) — never for this regime-comparison proxy."""
    out_dir = out_dir or OUT
    rows = []
    for qt in ["C", "F"]:
        source = pd.read_csv(os.path.join(ROOT, "scenario", "output",
                             "schaefer_biomass_annual" + ("_F" if qt == "F" else "") + ".csv"))
        biomass = source.set_index(["Stock", "Scenario", "Year"])
        if not biomass.index.is_unique:
            raise ValueError("Duplicate Schaefer projection keys")
        for tc in QUOTA_TC:
            msy_in = dict(MSY_FRAC) if qt == "F" else msy_scenario
            t = fleet_model.compute_meco_org_species(msy_in, qt, tc,
                                                 range(2025, 2051))
            for _, r in t.iterrows():
                rows.append({"QuotaType": qt, "TechCreep": tc,
                             "Species": r["Species"], "Year": int(r["Year"]),
                             "QuotaRatio": r["QuotaRatio"],
                             "BiomassRatio": r["BiomassRatio"],
                             "B_K": float(biomass.loc[(r["Species"],
                                 MSY_FRAC[r["Species"]] if qt == "F" else msy_scenario,
                                 int(r["Year"])), "Biomass_Mt"] /
                                 biomass.loc[(r["Species"],
                                 MSY_FRAC[r["Species"]] if qt == "F" else msy_scenario,
                                 int(r["Year"])), "K_Mt"]),
                             "Meco": r["Meco"]})
    df = pd.DataFrame(rows)
    key = ["QuotaType", "TechCreep", "Species", "Year"]
    metrics = ["QuotaRatio", "BiomassRatio", "B_K", "Meco"]
    if df.groupby(key)[metrics].nunique(dropna=False).gt(1).any().any():
        raise ValueError("Species quota factors unexpectedly differ across organisations")
    df = df.drop_duplicates(key).reset_index(drop=True)
    df.to_csv(os.path.join(out_dir, "Fig5_Quota_Species_Meco.csv"), index=False)
    # recommendation: per species x tc, the regime with better Meco (sustainable)
    rec = []
    d2050 = df[df.Year == 2050]
    for tc in QUOTA_TC:
        for sp in sorted(d2050.Species.unique()):
            sub = d2050[(d2050.TechCreep == tc) & (d2050.Species == sp)]
            cand = [(r.QuotaType, r.Meco, r.B_K, r.BiomassRatio) for _, r in sub.iterrows()]
            good = [c for c in cand if c[2] >= SUSTAIN_B_THRESH]
            pool = good if good else cand
            best = max(pool, key=lambda c: c[1])
            rec.append({"TechCreep": tc, "Species": sp, "BestQuota": best[0],
                        "Meco": round(best[1], 3),
                        "B_K_2050": round(best[2], 3),
                        "BiomassRatio": round(best[3], 3),
                        "Sustainable": bool(good)})
    pd.DataFrame(rec).to_csv(
        os.path.join(out_dir, "Fig5_Quota_Recommendation.csv"), index=False)
    print(f"[c] quota-species proxy: {len(df)} rows -> "
          f"Fig5_Quota_Species_Meco.csv + Fig5_Quota_Recommendation.csv")
    return df


def run_final_combination(final_fuel=None, quota_species=None, out_dir=None,
                          bau_ghg=None):
    """Panel e: FINAL COMBINATION over all 81 BAU — per BAU apply its
    WEO-BOUND fuel pathway (final_fuel: {"STEPS": {fuel params}, "APS": ...,
    "NZE": ...}) + species-level mixed quota (quota_species: {"SKJ": "C",
    ...}) + ALL other measures (Refrigerant LN2 + Consolidation U2).
    ALSO simulates the QUOTA-ONLY variant (species quota change alone, no
    other measures) so panel (e) can show the quota regime's own line.
    Outputs: Fig5_Final_Combination_Annual.csv + Fig5_QuotaOnly_Annual.csv.
    """
    out_dir = out_dir or OUT
    require_seed_protocol(out_dir, ["BAU_81_Annual.csv"])
    if final_fuel is None:
        raise ValueError("final_fuel must map each WEO to fuel params")
    if quota_species is None:
        raise ValueError("quota_species must map each species to C/F")
    import itertools
    bau_grid = [(w, g, r, t) for w in BAU_WEO for g in BAU_GROWTH
                for r in BAU_RETIRE.values() for t in BAU_TECH]
    bau_ids = {k: f"BAU_{i + 1:03d}" for i, k in enumerate(bau_grid)}

    def _task(bau, idx):
        w, g, r, t = bau
        p = make_params(weo=w, growth=g, tc=t)
        p["retirement_scenario"] = int(r)
        p["forced_retirement_rate"] = 0.0
        p["quota_type"] = dict(quota_species)
        p["schaefer_scenario"] = dict(MSY_FRAC)
        p.update(final_fuel[w])          # WEO-bound fuel pathway
        p.update({"refrigerant_type": "LN2", "consolidation_type": 2})
        return (p, paired_seed(bau), None)

    def _task_quota_only(bau, idx):
        """ONLY the quota regime changes (C2024 -> species-level F/HCR);
        fuel stays historical-fossil, no LN2, no consolidation."""
        w, g, r, t = bau
        p = make_params(weo=w, growth=g, tc=t)
        p["retirement_scenario"] = int(r)
        p["forced_retirement_rate"] = 0.0
        p["quota_type"] = dict(quota_species)
        p["schaefer_scenario"] = dict(MSY_FRAC)
        return (p, paired_seed(bau), None)

    _POOL = Pool(N_WORKERS, initializer=_init_worker, initargs=pool_args)
    t0 = time.time()
    t1 = [_task(b, i) for i, b in enumerate(bau_grid)]
    t1 += [_task_quota_only(b, i) for i, b in enumerate(bau_grid)]
    r1 = _POOL.map(_rho_task, t1, chunksize=8)
    _POOL.close(); _POOL.join()
    rows = []
    for b, (r, ra, sa, rg, sg) in zip(bau_grid, r1):
        bid = bau_ids[b]
        fin = rg.groupby("Year")["GHG_tCO2e"].sum()
        base = (bau_ghg or {}).get(bid)   # reuse existing BAU (same seed grid)
        if base is None:
            continue
        bb = base.groupby("Year")["GHG_tCO2e"].sum()
        for y in bb.index:
            rows.append({"BAU_ID": bid, "WEO": b[0], "Growth": b[1],
                         "Retirement": [k for k, v2 in BAU_RETIRE.items()
                                        if v2 == b[2]][0],
                         "TechCreep": b[3], "Year": int(y),
                         "GHG_BAU": bb[y] / 1e6,
                         "GHG_Final": fin.get(y, 0.0) / 1e6,
                         "Reduction_pct": round(
                             100 * (bb[y] - fin.get(y, 0.0)) / bb[y], 3)})
    pd.DataFrame(rows).to_csv(
        os.path.join(out_dir, "Fig5_Final_Combination_Annual.csv"), index=False)

    # ---- quota-only variant (second half of the task list) ----
    qrows = []
    for b, (r0, ra, sa, rg, sg) in zip(bau_grid, r1[len(bau_grid):]):
        bid = bau_ids[b]
        q = rg.groupby("Year")["GHG_tCO2e"].sum()
        base = (bau_ghg or {}).get(bid)
        if base is None:
            continue
        bb = base.groupby("Year")["GHG_tCO2e"].sum()
        for y in bb.index:
            qrows.append({"BAU_ID": bid, "WEO": b[0], "Growth": b[1],
                          "Retirement": [k for k, v2 in BAU_RETIRE.items()
                                         if v2 == b[2]][0],
                          "TechCreep": b[3], "Year": int(y),
                          "GHG_BAU": bb[y] / 1e6,
                          "GHG_QuotaOnly": q.get(y, 0.0) / 1e6,
                          "Reduction_pct": round(
                              100 * (bb[y] - q.get(y, 0.0)) / bb[y], 3)})
    pd.DataFrame(qrows).to_csv(
        os.path.join(out_dir, "Fig5_QuotaOnly_Annual.csv"), index=False)
    print(f"[e] final combination: {len(rows)} rows + quota-only "
          f"{len(qrows)} rows in {time.time() - t0:.0f}s")
    record_seed_protocol(out_dir, ["Fig5_Final_Combination_Annual.csv", "Fig5_QuotaOnly_Annual.csv"])
    return rows


def export_fuel_curves(out_dir=None):
    """Panel c (fuel-expanded): ANNUAL proxy curves for all 14 v16 fuel options
    (2026-09-11): bio adoption share S_bio(t) x gamma blend limit + device
    newbuild rate s_n(t), node-linear (2025=0 -> 2030/2040/2050):
        bio:    E_bio_mix(t) = (1-S_bio*gamma) E_MGO(t) + S_bio*gamma E_bio(t)
        device: E(t) = (1-s_n) E_bio_mix(t) + s_n E_dev(t)
    Reduction(t) = 1 - E(t)/E_MGO(t). Fig4e per-kWh intensities.
    """
    out_dir = out_dir or OUT
    fig4_dir = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "Fig4"))
    pe = pd.read_csv(os.path.join(fig4_dir, "Fig4_PanelE_Intensity.csv"))
    pe = pe[(pe.Year >= 2025) & (pe.Fuel.isin(ALL_FUELS))]
    if pe.duplicated(["WEO", "Year", "Fuel"]).any():
        raise ValueError("Duplicate Fig4 fuel-intensity keys")
    if set(ALL_FUELS) - set(pe.Fuel):
        raise ValueError("Run current Fig4 preprocessing for every fuel first")
    yrs = sorted(pe.Year.unique())
    b_years = [2025, 2030, 2040, 2050]
    rows = []
    for weo in BAU_WEO:
        sub = pe[pe.WEO == weo]
        e = {f: {int(r.Year): float(r.Intensity_gCO2e_kWh)
                 for _, r in sub[sub.Fuel == f].iterrows()}
             for f in ALL_FUELS}
        me = {f: {int(r.Year): float(r.M_econ)
                  for _, r in sub[sub.Fuel == f].iterrows()}
              for f in ALL_FUELS}
        for level in FUEL_LEVELS_V16:
            lv = FUEL_LEVELS_V16[level]
            b_nodes = [0.0] + lv["bio"]
            n_nodes = [0.0] + lv["renewal"]
            for y in yrs:
                s_b = float(np.clip(np.interp(y, b_years, b_nodes), 0, 1))
                s_n = float(np.clip(np.interp(y, b_years, n_nodes), 0, 1))
                for spec in _fuel_option_specs(level):
                    # per-year version of _mix_intensity (year-keyed dicts)
                    ea, ma = e["MGO"][y], me["MGO"][y]
                    if spec["BioFuel"]:
                        w = s_b * BIO_GAMMA[spec["BioFuel"]]
                        ea = (1.0 - w) * ea + w * e[spec["BioFuel"]][y]
                        ma = (1.0 - w) * ma + w * me[spec["BioFuel"]][y]
                    if spec["DevFuel"]:
                        ea = (1.0 - s_n) * ea + s_n * e[spec["DevFuel"]][y]
                        ma = (1.0 - s_n) * ma + s_n * me[spec["DevFuel"]][y]
                    rows.append({"WEO": weo, **spec, "Intensity": level,
                                 "Year": int(y),
                                 "E_adj_gCO2_kWh": round(ea, 1),
                                 "M_econ": round(ma, 3),
                                 "Reduction_pct": round(
                                     100 * (1 - ea / e["MGO"][y]), 2)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(out_dir, "Fig5_Fuel_Curves.csv"), index=False)
    print(f"[c] fuel curves proxy: {len(df)} rows -> Fig5_Fuel_Curves.csv")
    return df


def run_fuel_only():
    """INCREMENTAL rebuild (2026-09-11): re-simulate ONLY the 4 fuel-bearing
    mitigation schemes (Fuel / Fuel+Consolidation / Fuel+Refrigerant /
    Fuel+Refrigerant+Consolidation) x 81 BAU = 324 sims. BAU and the 3
    non-fuel schemes (Refrigerant / Consolidation / Refrigerant+Consolidation)
    are reused from the existing CSVs — they do not depend on the fuel
    transition logic. Merged outputs are rewritten in place.
    """
    require_seed_protocol(OUT, ["BAU_81_Annual.csv", "Mitigation_Results_Annual.csv",
        "Heterogeneous_Mitigation_Results.csv"])
    import itertools
    bau_grid = [(w, g, r, t) for w in BAU_WEO for g in BAU_GROWTH
                for r in BAU_RETIRE.values() for t in BAU_TECH]
    bau_ids = {k: f"BAU_{i + 1:03d}" for i, k in enumerate(bau_grid)}

    def _task(bau, pkg, idx):
        w, g, r, t = bau
        p = make_params(weo=w, growth=g, tc=t)
        p["retirement_scenario"] = int(r)
        p["forced_retirement_rate"] = 0.0
        p.update(pkg)
        return (p, paired_seed(bau), None)

    _POOL = Pool(N_WORKERS, initializer=_init_worker, initargs=pool_args)
    t0 = time.time()
    t2, k2 = [], []
    for b in bau_grid:
        for name, pkg in _schemes_for_bau(b[0]):
            if "Fuel" not in name:
                continue
            t2.append(_task(b, pkg, 0))
            k2.append((bau_ids[b], name))
    r2 = _POOL.map(_rho_task, t2, chunksize=8)
    _POOL.close(); _POOL.join()
    print(f"[fuelonly] {len(t2)} fuel-scheme sims in {time.time() - t0:.0f}s")
    fuel_ghg = {k: v[3] for k, v in zip(k2, r2)}
    fuel_spec = {k: v[4] for k, v in zip(k2, r2)}

    # ================= merge & rewrite outputs =================
    idx_cols = ["Organization", "Species", "Gear"]

    # ---- Mitigation_Results_Annual.csv ----
    mit = pd.read_csv(os.path.join(OUT, "Mitigation_Results_Annual.csv"))
    fuel_rows = []
    for b in bau_grid:
        bid = bau_ids[b]
        base = mit[(mit.BAU_ID == bid) &
                   (~mit.Mitigation_Pathway.str.contains("Fuel"))]
        base_g = mit[(mit.BAU_ID == bid) &
                     (mit.Mitigation_Pathway == "Refrigerant")]
        bb = base_g.set_index("Year")["GHG_BAU"]
        for name in ["Fuel", "Fuel+Consolidation", "Fuel+Refrigerant",
                     "Fuel+Refrigerant+Consolidation"]:
            rg = fuel_ghg[(bid, name)]
            fin = rg.groupby("Year")["GHG_tCO2e"].sum()
            for y in bb.index:
                gb, gm = float(bb[y]), float(fin.get(y, 0.0))
                red = 100 * (gb - gm) / gb if gb > 0 else 0.0
                lv = WEO_FUEL_LEVEL[b[0]] if name.startswith("Fuel") else ""
                fuel_rows.append({"BAU_ID": bid, "WEO": b[0], "Growth": b[1],
                                  "Retirement": [k for k, v2 in BAU_RETIRE.items()
                                                 if v2 == b[2]][0],
                                  "TechCreep": b[3], "Mitigation_Pathway": name,
                                  "Mitigation_Level": lv, "Year": int(y),
                                  "GHG_BAU": gb / 1e6, "GHG_Mitigation": gm / 1e6,
                                  "GHG_Reduction_pct": round(red, 3)})
    new_mit = pd.concat([mit[~mit.Mitigation_Pathway.str.contains("Fuel")],
                         pd.DataFrame(fuel_rows)], ignore_index=True)
    new_mit = new_mit.sort_values(["BAU_ID", "Mitigation_Pathway", "Year"])
    new_mit.to_csv(os.path.join(OUT, "Mitigation_Results_Annual.csv"), index=False)

    # ---- Heterogeneous_Mitigation_Results.csv ----
    het = pd.read_csv(os.path.join(OUT, "Heterogeneous_Mitigation_Results.csv"))
    het_fuel = []
    for b in bau_grid:
        bid = bau_ids[b]
        ref = het[(het.BAU_ID == bid) &
                  (het.Mitigation_Pathway == "Refrigerant")]
        sg_b = ref.groupby(idx_cols)["GHG_BAU"].first()
        for name in ["Fuel", "Fuel+Consolidation", "Fuel+Refrigerant",
                     "Fuel+Refrigerant+Consolidation"]:
            sg = fuel_spec[(bid, name)]
            if not len(sg) or not len(sg_b):
                continue
            mg = sg.groupby(idx_cols)["GHG_tCO2e"].sum()
            for (o, s_, gg), gb in sg_b.items():
                gm = float(mg.get((o, s_, gg), 0.0))
                red = 100 * (gb - gm) / gb if gb > 0 else 0.0
                het_fuel.append({"BAU_ID": bid, "WEO": b[0], "Growth": b[1],
                                 "Retirement": [k for k, v2 in BAU_RETIRE.items()
                                                if v2 == b[2]][0],
                                 "TechCreep": b[3], "Gear": gg, "Organization": o,
                                 "Species": s_, "Mitigation_Pathway": name,
                                 "Mitigation_Level": WEO_FUEL_LEVEL[b[0]],
                                 "GHG_BAU": float(gb / 1e6),
                                 "GHG_Mitigation": gm / 1e6,
                                 "Reduction_pct": round(red, 3)})
    new_het = pd.concat([het[~het.Mitigation_Pathway.str.contains("Fuel")],
                         pd.DataFrame(het_fuel)], ignore_index=True)
    new_het.to_csv(os.path.join(OUT, "Heterogeneous_Mitigation_Results.csv"),
                   index=False)

    # ---- Optimal_Mitigation_By_Object.csv (recomputed from merged hetero) ----
    opt_rows = []
    for (o, s_, gg), g in new_het.groupby(["Organization", "Species", "Gear"]):
        best = g.groupby("Mitigation_Pathway")["Reduction_pct"].mean().idxmax()
        n_bau = int((g[g.Mitigation_Pathway == best].groupby("BAU_ID").ngroups))
        opt_rows.append({"Gear": gg, "Organization": o, "Species": s_,
                         "Optimal_Pathway": best,
                         "Optimal_Reduction": round(
                             g[g.Mitigation_Pathway == best].Reduction_pct.mean(), 3),
                         "N_BAU_Optimal": n_bau,
                         "P_BAU_Optimal": n_bau / len(bau_grid)})
    pd.DataFrame(opt_rows).to_csv(
        os.path.join(OUT, "Optimal_Mitigation_By_Object.csv"), index=False)
    print("[fuelonly] merged Mitigation / Heterogeneous / Optimal rewritten")
    record_seed_protocol(OUT, ["Mitigation_Results_Annual.csv",
        "Heterogeneous_Mitigation_Results.csv", "Optimal_Mitigation_By_Object.csv"])


if __name__ == "__main__":
    import json, sys as _sys
    # no-arg = FULL pipeline (Stage A + portfolio); "proxies" / "final" explicit
    mode = _sys.argv[1] if len(_sys.argv) > 1 else "full"
    if mode == "fuelonly":
        # incremental: Fuel-bearing schemes only (BAU + non-fuel reused)
        fleet, pm = fleet_model.load_baseline_fleet()
        pool_args = (fleet, pm)
        run_fuel_only()
        _sys.exit(0)
    if mode == "proxies":
        # Panel b/c zero-simulation proxy exports (v15 decision chain)
        export_fuel_options_proxy()
        export_quota_species_proxy()
        export_fuel_curves()
        print("[run] proxy exports done (panels a/d reuse existing data)")
        _sys.exit(0)
    print(f"[run] workers = {N_WORKERS}; loading baseline fleet (one-off)...")
    fleet, pm = fleet_model.load_baseline_fleet()
    pool_args = (fleet, pm)

    t_all = time.time()
    if mode == "final":
        # Panel e: final combination — 81 BAU x (WEO-bound fuel + species
        # quota + LN2 + U2), plus quota-only: 162 sims (verified BAU reused;
        # Stage A / portfolio are NOT rerun).
        ff_path = os.path.join(OUT, "Fig5_Final_Fuel.json")
        qs_path = os.path.join(OUT, "Fig5_Final_Quota.json")
        ff = json.load(open(ff_path)) if os.path.exists(ff_path) else None
        qs = json.load(open(qs_path)) if os.path.exists(qs_path) else None
        if ff is None or qs is None:
            raise SystemExit("Fig5_Final_Fuel.json / Fig5_Final_Quota.json missing")
        b = pd.read_csv(os.path.join(OUT, "BAU_81_Annual.csv"))
        bau_ghg = {bid: df[["Year", "GHG_Mt"]].rename(
            columns={"GHG_Mt": "GHG_tCO2e"})
            for bid, df in b.groupby("BAU_ID")}
        for df in bau_ghg.values():
            df["GHG_tCO2e"] = df["GHG_tCO2e"] * 1e6
        run_final_combination(final_fuel=ff, quota_species=qs, bau_ghg=bau_ghg)
    else:
        # Fig.5 v16 panels need ONLY: 81 BAU + 7 mitigation schemes x 81.
        # The LHS sensitivity (Stage A) is NOT used by any current panel
        # (2026-09-12 user directive: never run data the figure does not use).
        GHG, SPEC_GHG = run_portfolio()
    print(f"[run] total wall time {(time.time() - t_all) / 60:.1f} min")
    print(f"[run] outputs → {OUT}")
