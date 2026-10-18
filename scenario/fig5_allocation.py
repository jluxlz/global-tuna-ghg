#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fig5_allocation.py — Fig.5 historical allocation module (2026-08-24).

Schaefer (jabba_fit.r) outputs SPECIES-LEVEL totals only: C_{s,t}, B_{s,t},
quota_ratio, biomass_ratio. RFMO × Gear attribution is an INDEPENDENT
historical-downscaling module — never conflate the two (user directive).

Core identities:
    C_{o,s,g,t}      = C_{s,t} × P_{o,g|s}                      (joint proportion, 2015-2024)
    Meco_{s,t,c}     = quota_ratio_{s,t,c} / [biomass_ratio_{s,t,c} × (1+tc)^Δt]
    Effort_{o,s,g,t,c} = Effort0_{o,s,g} × Meco_{s,t,c}         (2024-level baseline scaled)
    GHG_{o,s,g,t,c}  = Effort × EF_hist_g × ρ_ef,g(c)          (ρ_ef from fleet_model fleet sims)
    CEI              = GHG / Catch

Closed-sum checks: Σ_{o,g} P_{o,g|s} = 1; Σ_{o,g} C_{o,s,g,t} = C_{s,t};
Σ_s Effort_{o,s,g} = Effort_{o,g}; Σ_{o,s,g} GHG = fleet GHG × (Effort scaling).
"""

import os
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
GRID_PATH = os.path.join(ROOT_DIR, "GHG_Calculation", "Base_3_Spatial_Grid_Enriched.csv")
SCHAEFER_PATH   = os.path.join(BASE_DIR, "output", "schaefer_biomass_annual.csv")
SCHAEFER_PATH_F = os.path.join(BASE_DIR, "output", "schaefer_biomass_annual_F.csv")

SPECIES = ["SBT", "SKJ", "BET", "YFT", "ALB"]
ORGANS  = ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]
GEARS   = ["LL", "PS"]
SP_COLS = [s + "_Tonnes" for s in SPECIES]

YEARS = range(2025, 2051)   # 2025–2050 dynamic transition period (26 years)

_CACHE = {}


def load_grid():
    if "grid" not in _CACHE:
        _CACHE["grid"] = pd.read_csv(GRID_PATH)
    return _CACHE["grid"]


def load_schaefer(quota_type="C"):
    """Schaefer projections for quota_type 'C' (fixed catch) or 'F' (harvest rate)."""
    key = ("sch", quota_type)
    if key not in _CACHE:
        path = SCHAEFER_PATH_F if quota_type == "F" else SCHAEFER_PATH
        _CACHE[key] = pd.read_csv(path)
    return _CACHE[key]


def build_shares(win=(2015, 2024)):
    """Joint proportions P_{o,g|s}, annual effort baselines, gear EF, org-species weights."""
    key = ("shares", win)
    if key in _CACHE:
        return _CACHE[key]

    df = load_grid()
    rec = df[(df.Year >= win[0]) & (df.Year <= win[1])]
    n_yr = win[1] - win[0] + 1

    og = rec.groupby(["Organization", "Gear"])[SP_COLS].sum()

    # ---- Joint proportion P[o,g|s] (w_t = 1 over the window) ----
    P = {}
    for s, col in zip(SPECIES, SP_COLS):
        v = og[col]
        P[s] = {(o, g): (v[o, g] / v.sum()) if v.sum() > 0 else 0.0
                for o in ORGANS for g in GEARS}

    # ---- Annual effort baseline per (o,s,g):  Effort_{o,g} × species catch share ----
    eog = rec.groupby(["Organization", "Gear"])["Standard_Effort"].sum() / n_yr
    cog = rec.groupby(["Organization", "Gear"])[SP_COLS].sum()
    E0 = {}
    for o in ORGANS:
        for g in GEARS:
            tot_s = cog.loc[(o, g)].sum()
            for s, col in zip(SPECIES, SP_COLS):
                E0[(o, s, g)] = eog[(o, g)] * (cog.loc[(o, g), col] / tot_s) if tot_s > 0 else 0.0

    # ---- Annual CATCH baseline per (o,s,g): real landed tonnes from Base3 ----
    # (2026-09-04 fix: effort units are NOT comparable across gears — PS days vs
    # LL hooks differ by ~10⁴, so Effort0-based catch proxies crushed PS shares;
    # catch shares must use actual catches, not effort.)
    cog_ann = cog / n_yr
    C0 = {}
    for o in ORGANS:
        for g in GEARS:
            for s, col in zip(SPECIES, SP_COLS):
                C0[(o, s, g)] = float(cog_ann.loc[(o, g), col]) if (o, g) in cog_ann.index else 0.0

    # ---- Historical unit-effort emission factor per gear (tCO2e / effort unit) ----
    gghg = rec.groupby("Gear")["GHG_emissions_median"].sum()
    gef  = rec.groupby("Gear")["Standard_Effort"].sum()
    EF_hist = {g: (gghg[g] / gef[g]) if gef[g] > 0 else 0.0 for g in GEARS}

    # ---- Org × species catch weights (RFMO-level Meco weighting, panel b) ----
    os_ = rec.groupby("Organization")[SP_COLS].sum()
    w_os = {}
    for o in ORGANS:
        tot = os_.loc[o].sum()
        w_os[o] = {s: (os_.loc[o, col] / tot) if tot > 0 else 0.0
                   for s, col in zip(SPECIES, SP_COLS)}

    Q = {s: {(o, g): (float(cog.loc[(o, g), col] / cog.loc[(o, g)].sum())
                      if (o, g) in cog.index and cog.loc[(o, g)].sum() > 0 else 0.0)
              for o in ORGANS for g in GEARS}
         for s, col in zip(SPECIES, SP_COLS)}
    out = {"P": P, "Q": Q, "E0": E0, "C0": C0, "EF_hist": EF_hist, "w_os": w_os,
           "n_objects": sum(1 for v in E0.values() if v > 0)}
    _CACHE[key] = out
    return out


def meco_s(scen="MSY_100", year=2050, tc=0.024, quota_type="C"):
    """Species-level ecological effort multiplier (user definition, Δt = year - 2025)."""
    sch = load_schaefer(quota_type)
    out = {}
    for s in SPECIES:
        row = sch[(sch.Stock == s) & (sch.Scenario == scen) & (sch.Year == year)]
        if len(row) == 0:
            out[s] = 1.0
            continue
        qr, br = float(row.quota_ratio.iloc[0]), float(row.biomass_ratio.iloc[0])
        out[s] = qr / max(br * (1.0 + tc) ** max(int(year) - 2025, 0), 0.01)
    return out


# =============================================================================
# Dynamic-period (2025–2050) helpers — every year t has its own quota_ratio_t /
# biomass_ratio_t from the JABBA projections; Meco_{s,t} = qr_t/[br_t × (1+tc)].
# Cumulative quantities factorise because Effort0 / EF_hist / rho are
# time-invariant in the allocation layer: Σ_t GHG_t = E0 × (Σ_t Meco_t) × EF × ρ.
# =============================================================================

def meco_series(scen="MSY_100", tc=0.024, quota_type="C", years=YEARS):
    """Per-species per-year Meco over the period: {species: {year: Meco}}."""
    years = tuple(years)
    key = ("mseries", scen, tc, quota_type, years)
    if key in _CACHE:
        return _CACHE[key]
    sch = load_schaefer(quota_type)
    out = {}
    for s in SPECIES:
        sub = sch[(sch.Stock == s) & (sch.Scenario == scen)]
        d = {}
        for _, row in sub.iterrows():
            y = int(row.Year)
            if y in years:
                qr, br = float(row.quota_ratio), float(row.biomass_ratio)
                d[y] = qr / max(br * (1.0 + tc) ** max(y - 2025, 0), 0.01)
        out[s] = d
    _CACHE[key] = out
    return out


def cum_meco(scen="MSY_100", tc=0.024, quota_type="C", years=YEARS):
    """Σ_t Meco_{s,t} per species (cumulative effort multiplier over the period)."""
    return {s: sum(d.values()) for s, d in meco_series(scen, tc, quota_type, years).items()}


def mean_meco(scen="MSY_100", tc=0.024, quota_type="C", years=YEARS):
    """mean_t Meco_{s,t} per species (period-mean ecological pressure)."""
    ms = meco_series(scen, tc, quota_type, years)
    return {s: (sum(d.values()) / len(d)) if d else 0.0 for s, d in ms.items()}


def meco_highpressure_years(scen="MSY_100", tc=0.024, quota_type="C", years=YEARS):
    """Σ_t I(Meco_{s,t} > 1): years under high ecological pressure per species."""
    ms = meco_series(scen, tc, quota_type, years)
    return {s: sum(1 for v in d.values() if v > 1.0) for s, d in ms.items()}


def cum_catch(scen="MSY_100", quota_type="C", years=YEARS):
    """Σ_t Catch (tonnes) per species over the period."""
    key = ("ccatch", scen, quota_type)
    if key in _CACHE:
        return _CACHE[key]
    sch = load_schaefer(quota_type)
    out = {}
    for s in SPECIES:
        sub = sch[(sch.Stock == s) & (sch.Scenario == scen) & (sch.Year.isin(years))]
        out[s] = float(sub.Catch_Mt.sum()) * 1e6 if len(sub) else 0.0
    _CACHE[key] = out
    return out


def dyn_alloc_table(scen="MSY_100", tc=0.024, gear_shift=0.0, rho_ef=None,
                    quota_type="C", years=YEARS, drop_zero=True):
    """Per-object (RFMO × Species × Gear) dynamic-period table.

    Cumulative (2025–2050) + 2050-endpoint (secondary) metrics in one table:
        Cum_GHG_t / Cum_Catch_t / Mean_Meco   — fleet_model dynamic metrics
        GHG_2050_t / Catch_2050_t / Meco_2050 — endpoint, supplementary

    rho_ef : dict {gear: float} — pure-EF multiplier from fleet_model fleet sims
             (combo / baseline, E_final = 1, same fleet). None → 1.0.
    """
    sh = build_shares()
    P = adjust_gear_share(sh["P"], gear_shift) if gear_shift != 0.0 else sh["P"]
    cm = cum_meco(scen, tc, quota_type, years)
    mm = mean_meco(scen, tc, quota_type, years)
    m2050 = {s: ms.get(2050, 1.0) for s, ms in meco_series(scen, tc, quota_type, years).items()}
    cc = cum_catch(scen, quota_type, years)
    sch = load_schaefer(quota_type)
    c2050 = {}
    for s in SPECIES:
        row = sch[(sch.Stock == s) & (sch.Scenario == scen) & (sch.Year == 2050)]
        c2050[s] = float(row.Catch_Mt.iloc[0]) * 1e6 if len(row) else 0.0

    rows = []
    for s in SPECIES:
        for o in ORGANS:
            for g in GEARS:
                p = P[s][(o, g)]
                if p <= 0 and drop_zero:
                    continue
                e0 = sh["E0"][(o, s, g)]
                rho = rho_ef[g] if rho_ef else 1.0
                rows.append({"Organization": o, "Species": s, "Gear": g,
                             "Cum_GHG_t": e0 * cm[s] * sh["EF_hist"][g] * rho,
                             "Cum_Catch_t": cc[s] * p,
                             "Mean_Meco": mm[s],
                             "GHG_2050_t": e0 * m2050[s] * sh["EF_hist"][g] * rho,
                             "Catch_2050_t": c2050[s] * p,
                             "Meco_2050": m2050[s]})
    return pd.DataFrame(rows)


def adjust_gear_share(P, shift=0.10):
    """Scenario-adjusted proportions: gear-management measure (LL → PS by `shift`
    of each species' org-level total, then renormalise per species)."""
    P2 = {s: dict(P[s]) for s in SPECIES}
    for s in SPECIES:
        for o in ORGANS:
            p_ll, p_ps = P2[s].get((o, "LL"), 0.0), P2[s].get((o, "PS"), 0.0)
            move = shift * (p_ll + p_ps)
            P2[s][(o, "LL")] = max(p_ll - move, 0.0)
            P2[s][(o, "PS")] = p_ps + move
        tot = sum(P2[s].values())
        if tot > 0:
            for k in P2[s]:
                P2[s][k] /= tot
    return P2


def alloc_table(scen="MSY_100", year=2050, tc=0.024, gear_shift=0.0,
                rho_ef=None, drop_zero=True):
    """Per-object (RFMO × Species × Gear) 2050 table: Catch, Effort, GHG, CEI, Meco.

    rho_ef : dict {gear: float} — pure-EF multiplier from fleet_model fleet sims
             (combo / baseline, E_final = 1, same fleet). None → 1.0.
    """
    sh = build_shares()
    P = adjust_gear_share(sh["P"], gear_shift) if gear_shift != 0.0 else sh["P"]
    Meco = meco_s(scen, year, tc)
    sch = load_schaefer()

    rows = []
    for s in SPECIES:
        cs = sch[(sch.Stock == s) & (sch.Scenario == scen) & (sch.Year == year)]
        c_t = float(cs.Catch_Mt.iloc[0]) * 1e6 if len(cs) else 0.0  # tonnes
        for o in ORGANS:
            for g in GEARS:
                p = P[s][(o, g)]
                if p <= 0 and drop_zero:
                    continue
                catch = c_t * p
                effort = sh["E0"][(o, s, g)] * Meco[s]
                ghg = effort * sh["EF_hist"][g] * (rho_ef[g] if rho_ef else 1.0)
                rows.append({"Organization": o, "Species": s, "Gear": g,
                             "Catch_t": catch, "Effort": effort,
                             "Meco": Meco[s], "GHG_t": ghg,
                             "CEI": ghg / catch if catch > 0 else np.nan})
    return pd.DataFrame(rows)


def closed_sum_checks():
    """Verify the closed-sum identities against raw data (one-time audit)."""
    sh = build_shares()
    for s in SPECIES:
        assert abs(sum(sh["P"][s].values()) - 1.0) < 1e-9, s
    # Σ_s E0(o,g,s) vs window-mean effort of (o,g): recompute directly
    df = load_grid()
    rec = df[(df.Year >= 2015) & (df.Year <= 2024)]
    eog = rec.groupby(["Organization", "Gear"])["Standard_Effort"].sum() / 10
    max_dev = 0.0
    for o in ORGANS:
        for g in GEARS:
            lhs = sum(sh["E0"][(o, s, g)] for s in SPECIES)
            rhs = eog[(o, g)]
            max_dev = max(max_dev, abs(lhs - rhs))
    print(f"  [check] sum_s E0(o,g,s) vs mean-annual effort (o,g): max abs dev = {max_dev:.4f}")
    print(f"  [check] sum_{{o,g}} P = 1 per species: OK")


if __name__ == "__main__":
    sh = build_shares()
    print(f"Objects with positive effort: {sh['n_objects']}")
    closed_sum_checks()
    t = alloc_table()
    print(t.sort_values("GHG_t", ascending=False).head(8).to_string(index=False))
    print(f"Σ GHG (base 2050) = {t.GHG_t.sum():,.0f} tCO2e")
