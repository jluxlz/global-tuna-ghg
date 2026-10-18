#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fig5_optimizer.py — Fig.5 management-portfolio OPTIMIZER (2026-09-03).

STANDALONE optimisation module (user directive): the optimisation functions
live HERE; figure rendering lives in figures/Fig5/plot_fig5.r; model
algorithms in fleet_model.py are NOT touched.

Core rules (2026-09-03 directive, supersedes the Pareto-era v7)
---------------------------------------------------------------
1. The ONLY objective is the final-GHG outcome:  max  DeltaGHG_cum(S)
   (cumulative absolute reduction, 2025–2050, relative to the WEO-specific
   baseline). ER_cum is kept as a REFERENCE column only — NEVER an objective
   (it is mathematically collinear with DeltaGHG_cum for a fixed baseline:
   ER = DeltaGHG / GHG_baseline).
2. Meco / M_econ / E_final are MECHANISM variables inside the model
   (E_final <= Meco is a hard constraint) — never optimisation objectives.
3. Management dimensions: at most ONE active level per dimension (or none);
   in-dimension conflicts (e.g. QC80 + QC70) are forbidden.
4. N_measures is a FEASIBILITY CONSTRAINT, not an objective:
       N_measures(S) <= MAX_MEASURES   (tunable, default 4)
5. Optimal portfolio per (WEO, RFMO, N):
       S*_{r,N} = argmax_{S: N_measures(S)=N} DeltaGHG_cum(S)
   Figure 5(c) plots max DeltaGHG_cum vs N (diminishing returns view).
6. Incremental benefit of expanding the portfolio (Figure 5(d)):
       MC_1 = DeltaGHG(S*_1)
       MC_N = DeltaGHG(S*_N) - DeltaGHG(S*_{N-1})   (N >= 2)
   NOTE: S*_N and S*_{N-1} need NOT be nested (the optimal portfolio may
   re-combine) — this is the incremental benefit of INCREASING PORTFOLIO
   SIZE, not the marginal contribution of an individual measure.
7. WEO (STEPS/APS/NZE) is a scenario background layer: every candidate runs
   under all three WEOs; WEO background singles (WS/WA/WN) are sensitivity-
   only and excluded from the portfolio optimisation.
"""
import numpy as np
import pandas as pd

MAX_MEASURES = 4          # feasibility: N_measures(S) <= MAX_MEASURES
MAX_PORTFOLIOS = 600      # candidate-portfolio budget (runtime control)

# ---- MANAGEMENT DIMENSIONS (2026-09-06 classification): only TRUE management
#      measures that a government can implement. WEO / growth / tech creep are
#      EXTERNAL SCENARIO DRIVERS (future world), NOT candidate measures;
#      quota is a REGIME (C = fixed-2024 catch, F = harvest-rate HCR), not a
#      freely-optimised measure. ≤ 1 level per dimension ----
DIMENSIONS = {
    "lifespan":    ["L20", "L25", "L35", "L40"],
    "retirement":  ["R1", "R2", "R3"],
    "fuel":        ["B1", "B2", "B3", "H3", "H6", "H10"],
    "target":      ["T3", "T6"],              # T0 ≡ no target (baseline)
    "newbuild":    ["NL", "NH", "N2"],
    "upscale":     ["U1", "U2"],
    "refrigerant": ["R404", "LN"],
}

# ---- EXTERNAL SCENARIO GRID (2026-09-06): future world, optimised NOTHING ----
# S = (WEO, growth, tech). Each cell is a scenario background under which the
# management optimisation runs independently.
SCENARIO_WEO    = ["STEPS", "APS", "NZE"]
SCENARIO_GROWTH = [0.0021, 0.0136, 0.0272]     # G021 / G136 / G272 values
SCENARIO_TECH   = [0.019, 0.024, 0.043]        # TS / TM / TR values
# WEO background singles (sensitivity only — NOT part of the portfolio search)
WEO_SINGLES = ["WS", "WA", "WN"]


def generate_portfolios(max_measures=MAX_MEASURES, budget=MAX_PORTFOLIOS,
                        seed=42, with_weo=True):
    """[deprecated legacy] Random-budget candidate generator — superseded by
    generate_all_portfolios + greedy_beam_extend (2026-09-03): the budget
    sampler MISSED key combos (e.g. QC70+R10+L20+H10), biasing the optimum.
    Kept only for backward compatibility."""
    dims = list(DIMENSIONS.keys())
    levels = DIMENSIONS

    rng = np.random.default_rng(seed)
    out = []
    is_weo = []

    # WEO background singles (sensitivity only)
    if with_weo:
        for w in WEO_SINGLES:
            out.append([w])
            is_weo.append(True)

    # all single measures (one level of one dimension)
    for d in dims:
        for m in levels[d]:
            out.append([m])
            is_weo.append(False)

    # pairwise combinations across dimensions (≈40% of the budget)
    pair_pool = []
    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            for a in levels[dims[i]]:
                for b in levels[dims[j]]:
                    pair_pool.append([a, b])

    n_pair = max(int((budget - len(out)) * 0.40), 0)
    if len(pair_pool) <= n_pair:
        picked = pair_pool
    else:
        idx = rng.choice(len(pair_pool), size=n_pair, replace=False)
        picked = [pair_pool[k] for k in idx]
    for p in picked:
        out.append(p)
        is_weo.append(False)

    # multi-dimension combinations (3..max_measures) to fill the budget
    while len(out) < budget:
        k = int(rng.integers(3, max_measures + 1))
        ds = rng.choice(dims, size=min(k, len(dims)), replace=False)
        combo = [str(rng.choice(levels[d])) for d in ds]
        if combo not in out:
            out.append(combo)
            is_weo.append(False)

    # feasibility: N_measures <= max_measures
    keep = [i for i, c in enumerate(out) if len(c) <= max_measures]
    return ([out[i] for i in keep], [is_weo[i] for i in keep])


def generate_all_portfolios(with_weo=True):
    """COMPLETE candidate enumeration (no measure-count cap, 2026-09-03):
    every single measure + ALL cross-dimension pairs + ALL triples
    (≤1 level per dimension). Nothing is left to random sampling — the
    optimisation can only be as good as its search space.
    Returns (portfolios, is_weo)."""
    dims = list(DIMENSIONS.keys())
    levels = DIMENSIONS
    out = []
    is_weo = []

    if with_weo:
        for w in WEO_SINGLES:
            out.append([w])
            is_weo.append(True)

    for d in dims:
        for m in levels[d]:
            out.append([m])
            is_weo.append(False)

    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            for a in levels[dims[i]]:
                for b in levels[dims[j]]:
                    out.append([a, b])
                    is_weo.append(False)

    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            for k in range(j + 1, len(dims)):
                for a in levels[dims[i]]:
                    for b in levels[dims[j]]:
                        for c in levels[dims[k]]:
                            out.append([a, b, c])
                            is_weo.append(False)
    return out, is_weo


def greedy_beam_expand(combos, seen=None):
    """One expansion round: for every combo, try EVERY remaining level of
    every dimension NOT yet active in the combo (≤1 level per dimension —
    in-dimension conflicts like QC100+QF70 are forbidden; unbounded depth,
    no MAX_MEASURES cap). Returns new candidate combos not yet seen. The
    caller simulates, scores, keeps the top beam, and calls again until no
    improvement (see fig5_run.greedy search)."""
    dims = list(DIMENSIONS.keys())
    levels = DIMENSIONS
    seen = set() if seen is None else seen
    out = []
    for combo in combos:
        # active dimensions of the combo (its levels' dimensions)
        used_dims = set()
        for m in combo:
            for d in dims:
                if m in levels[d]:
                    used_dims.add(d)
                    break
        for d in dims:
            if d in used_dims:
                continue                     # ≤1 level per dimension
            for m in levels[d]:
                cand = tuple(sorted(combo + [m]))
                if cand in seen:
                    continue
                seen.add(cand)
                out.append(list(cand))
    return out


def select_top_candidates(score_df, k_per_n=5, top_total=120):
    """Top candidates for cross-WEO robustness checks: the best k portfolios
    per N layer plus the global best (STEPS search result). Returns a
    deduplicated list of combo strings."""
    d = score_df[score_df.Combo != ""]
    picks = []
    for n, g in d.groupby("N_Measures"):
        picks += g.sort_values("Score", ascending=False).head(k_per_n).Combo.tolist()
    picks += d.sort_values("Score", ascending=False).head(top_total).Combo.tolist()
    return list(dict.fromkeys(picks))


def best_portfolio_by_n(df, exclude=None, weo_col="WEO", rfmo_col="RFMO",
                        n_col="N_Measures", ghg_col="DeltaGHG_cum"):
    """Optimal portfolio per (WEO, RFMO, N):

        S*_{r,N} = argmax_{S: N_measures(S)=N} DeltaGHG_cum(S)

    Returns a copy of the best row per group (all other columns preserved).
    `exclude` = set of Combo strings (WEO singles) excluded from the search.
    """
    d = df.copy()
    if exclude is not None:
        d = d[~d["Combo"].isin(exclude)]
    d = d[d[n_col] >= 1]
    idx = d.groupby([weo_col, rfmo_col, n_col])[ghg_col].idxmax()
    return d.loc[idx].copy()


def best_by_group(df, group_cols, exclude=None, n_col="N_Measures",
                  ghg_col="DeltaGHG_cum", obj_id_cols=None):
    """Object-level (Organization × Species × Gear) optimal portfolio:

        S*_{i,N} = argmax_{S: N_measures(S)=N} DeltaGHG_{i,cum}(S)

    per group (WEO, <obj_id_cols>, N). Object GHG rows carry an object-level
    DeltaGHG_cum column (already referenced to the object's own WEO baseline).
    Returns the best row per group.
    """
    d = df.copy()
    if exclude is not None:
        d = d[~d["Combo"].isin(exclude)]
    d = d[d[n_col] >= 1]
    idx = d.groupby(group_cols)[ghg_col].idxmax()
    return d.loc[idx].copy()


def incremental_benefit_by_group(best, group_id_cols, n_col="N_Measures",
                                 ghg_col="DeltaGHG_cum"):
    """Object-level incremental benefit of expanding portfolio size:

        MC_{i,1} = ΔGHG_{i,1};  MC_{i,N} = ΔGHG_{i,N} − ΔGHG_{i,N−1}

    per (WEO, object). S*_{i,N} need NOT nest S*_{i,N−1} (re-combination
    allowed) — this is the incremental benefit of INCREASING PORTFOLIO SIZE.
    """
    rows = []
    gcols = ["WEO"] + list(group_id_cols)
    for key, g in best.groupby(gcols):
        g = g.sort_values(n_col)
        weo = key[0]
        prev = {}
        for _, r in g.iterrows():
            n = int(r[n_col])
            ghg = float(r[ghg_col])
            prev_ghg = prev.get(n - 1, 0.0)
            row = {"WEO": weo, "N_Measures": n,
                   "BestPortfolio": r["Combo"],
                   "DeltaGHG_cum": ghg,
                   "IncrementalBenefit": ghg - prev_ghg}
            for c, v in zip(group_id_cols, key[1:]):
                row[c] = v
            rows.append(row)
            prev[n] = ghg
    return pd.DataFrame(rows)


def incremental_benefit(best):
    """Incremental benefit of expanding the optimal portfolio size (Fig.5d):

        MC_1 = DeltaGHG(S*_1)
        MC_N = DeltaGHG(S*_N) − DeltaGHG(S*_{N−1})     (N ≥ 2)

    S*_N and S*_{N−1} need NOT be nested — the quantity is the incremental
    benefit of increasing the portfolio SIZE (one more allowed measure), not
    the marginal contribution of an individual measure. Percentage is
    relative to the previous best: MC_N / DeltaGHG(S*_{N−1}).
    """
    rows = []
    for (weo, rfmo), g in best.groupby(["WEO", "RFMO"]):
        g = g.sort_values("N_Measures")
        prev = {}
        for _, r in g.iterrows():
            n = int(r["N_Measures"])
            ghg = float(r["DeltaGHG_cum"])
            prev_ghg = prev.get(n - 1, 0.0)
            rows.append({
                "WEO": weo, "RFMO": rfmo, "N_measures": n,
                "BestPortfolio": r["Combo"],
                "DeltaGHG_cum": ghg,
                "Previous_DeltaGHG_cum": prev_ghg,
                "Incremental_DeltaGHG": ghg - prev_ghg,
                "Incremental_DeltaGHG_pct":
                    (ghg - prev_ghg) / prev_ghg if prev_ghg > 1e-9 else np.nan,
            })
            prev[n] = ghg
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pf, weo = generate_portfolios()
    print("candidate portfolios:", len(pf), "| WEO singles:", sum(weo))
    n = [len(c) for c in pf]
    print("N_measures distribution:", {k: n.count(k) for k in sorted(set(n))})
    print("max N_measures:", max(n), "<= MAX_MEASURES:", MAX_MEASURES)
    from collections import Counter
    dims_used = Counter(m for c in pf for m in c)
    print("measure usage:", dict(dims_used.most_common(5)))