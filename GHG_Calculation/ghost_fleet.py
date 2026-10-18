# -*- coding: utf-8 -*-
"""Ghost-fleet reconstruction v4 (2026-09-18, plan A + smooth phase-out).

Plan A core (user-approved):
  - Only fill where the registry is smaller: gap = max(0, target - registry).
  - Target = f * PNAS * catch-mod, f = min(1, registry_anchor/pnas_anchor),
    anchor 2015-17; PS uses length-matched PNAS classes, LL uses all classes;
    flags with registry/pnas > 1.5 are skipped (PNAS unreliable).
  - 5-species catch gate: ghosts only in years with tuna catch records.

v4 fixes the 2018 retirement cliff found in production:
  - GAP FADE: the late-2000s "gap" is largely a registry-imputation artifact,
    so the gap fades out over 1995 -> 2017 (PNAS data end; fully retired before 2025).
  - YEARLY CAP: active ghost power can never exceed the (faded) gap of that
    year - ghosts phase out exactly as the registry catches up, no cliff.
"""
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from power_discount_factor import map_length_to_csv_category

GEAR_FROM_PNAS = {"Lines_Longlines": "LL", "Seine_Purse_Seine": "PS"}
YEARS = list(range(1950, 2025))
ANCHOR = (2015, 2016, 2017)


def _load_pnas_power(pnas_path):
    p = pd.read_csv(pnas_path, skiprows=[1])
    for c in ["NV", "P", "Year"]:
        p[c] = pd.to_numeric(p[c], errors="coerce")
    p = p[(p.P > 0) & p.Year.notna()]
    out = {}
    for (ctry, gear_pnas, lc), g in p.groupby(["Country", "Gear", "Length_Category"]):
        gear = GEAR_FROM_PNAS.get(str(gear_pnas).strip())
        if gear is None:
            continue
        key = (str(ctry), gear)
        out.setdefault(key, {})
        for y, v in g.groupby("Year")["P"].sum().items():
            out[key][(str(lc).strip(), int(y))] = float(v)
    return out


def _load_tuna_catch(catch_path):
    sp = ["SBT_Tonnes", "SKJ_Tonnes", "BET_Tonnes", "YFT_Tonnes", "ALB_Tonnes"]
    c = pd.read_csv(catch_path, usecols=["Year", "Flag", "Gear"] + sp)
    c["catch"] = c[sp].sum(axis=1)
    c = c[c.catch > 0]
    return c.groupby(["Year", "Flag", "Gear"])["catch"].sum().to_dict()


def _active_power_series(sub, years):
    by = pd.to_numeric(sub["Builtdate"], errors="coerce")
    pw = pd.to_numeric(sub["Enginepower"], errors="coerce").fillna(0.0)
    ok = by.notna()
    by = by[ok].to_numpy()
    pw = pw[ok].to_numpy()
    order = np.argsort(by)
    by = by[order]
    cum = np.cumsum(pw[order])
    out = np.zeros(len(years))
    for i, t in enumerate(years):
        k = np.searchsorted(by, t, side="right")
        out[i] = cum[k - 1] if k > 0 else 0.0
    return out


def _fade(t, full_until=1995, zero_from=2017):
    if t <= full_until:
        return 1.0
    if t >= zero_from:
        return 0.0
    return (zero_from - t) / float(zero_from - full_until)


def build_ghost_vessels(df_vessels, pnas_path, catch_path,
                        anchor_years=ANCHOR, lifespan=30, len_share_min=0.05,
                        skip_ratio=1.5, fade_full_until=1995, fade_zero_from=2017,
                        max_new_per_year=None, max_ghosts_per_flag=None,
                        seed=42, verbose=True, qc_path=None):
    rng = np.random.RandomState(seed)
    # Row-count limits are optional diagnostics, not part of the approved power-gap model.
    max_new_per_year = np.inf if max_new_per_year is None else max_new_per_year
    max_ghosts_per_flag = np.inf if max_ghosts_per_flag is None else max_ghosts_per_flag
    registered = df_vessels["Is_Ghost"].fillna(0).eq(0) if "Is_Ghost" in df_vessels else pd.Series(True,index=df_vessels.index)
    reg = df_vessels[registered & df_vessels["VesselType"].isin(["LL", "PS"])].copy()
    pnas = _load_pnas_power(pnas_path)
    catch = _load_tuna_catch(catch_path)
    year_idx = {t: i for i, t in enumerate(YEARS)}

    ghosts = []
    vid = -1
    summary, skipped, qc = [], [], []
    if lifespan <= 0 or fade_zero_from <= fade_full_until:
        raise ValueError("Invalid ghost lifespan or fade interval")

    for (flag, gear), sub in reg.groupby(["Flag", "VesselType"]):
        key = (str(flag), str(gear))
        if key not in pnas:
            continue
        p_lc = pnas[key]
        A = _active_power_series(sub, YEARS)

        # ---- R0 (plan A): PS = length-matched classes; LL = all classes
        lengths = pd.to_numeric(sub["Length"], errors="coerce")
        pw = pd.to_numeric(sub["Enginepower"], errors="coerce").fillna(0.0)
        if gear == "PS":
            lc_series = lengths.apply(
                lambda v: map_length_to_csv_category(v) if pd.notna(v) else None)
            prof = pw.groupby(lc_series).sum()
            tot_prof = prof.sum()
            if tot_prof <= 0:
                continue
            relevant_lcs = [str(lc) for lc, v in prof.items()
                            if v / tot_prof >= len_share_min]
        else:
            relevant_lcs = sorted({str(lc) for (lc, y) in p_lc.keys()})

        def p_target(t):
            return sum(p_lc.get((lc, t), 0.0) for lc in relevant_lcs)
        p_series = np.array([p_target(t) for t in YEARS])

        a_anchor = sum(A[year_idx[t]] for t in anchor_years if t in year_idx)
        p_anchor = sum(p_series[year_idx[t]] for t in anchor_years if t in year_idx)
        if p_anchor <= 0 or a_anchor <= 0:
            continue
        ratio = a_anchor / p_anchor
        if ratio > skip_ratio:
            skipped.append((key[0], key[1], round(ratio, 2)))
            continue
        f = min(1.0, ratio)

        # R2: catch modulation (anchor = 1, clipped 0.3-2.0)
        c_anchor = np.mean([catch.get((t, key[0], key[1]), 0.0) for t in anchor_years])
        mod = np.ones(len(YEARS))
        if c_anchor > 0:
            for i, t in enumerate(YEARS):
                c = catch.get((t, key[0], key[1]), 0.0)
                mod[i] = np.clip(c / c_anchor, 0.3, 2.0) if c > 0 else 0.3

        # gap series + fade (v4)
        gap = np.zeros(len(YEARS))
        for i, t in enumerate(YEARS):
            if catch.get((t, key[0], key[1]), 0.0) <= 0:
                continue
            target = f * p_series[i] * mod[i]
            g = (target - A[i]) * _fade(t, fade_full_until, fade_zero_from)
            if g > 0:
                gap[i] = g

        # ---- cohort construction with YEARLY CAP (active ghosts <= gap[t])
        pool = reg[(reg.Flag == flag) & (reg.VesselType == gear)]
        if len(pool) < 5:
            pool = reg[reg.VesselType == gear]
        if pool.empty:
            raise ValueError(f"No {gear} templates for ghost reconstruction")
        pool = pool[pd.to_numeric(pool["Enginepower"], errors="coerce").gt(0)].copy()
        if pool.empty:
            raise ValueError(f"No positive-power ghost templates: {flag}/{gear}")
        cohorts = []          # list of dicts: built, power, rows(list)
        n_flag = 0
        total_power = 0.0
        for i, t in enumerate(YEARS):
            active = [c for c in cohorts if c["built"] <= t < c["retire"]]
            act_power = sum(c["power"] for c in active)
            if act_power > gap[i]:
                for c in sorted(active, key=lambda c: c["built"]):
                    if act_power <= gap[i]:
                        break
                    c["retire"] = t          # expire the oldest first
                    act_power -= c["power"]
            if gap[i] <= 0:
                qc.append(dict(Flag=flag, Gear=gear, Year=t, Registry_kW=A[i], Target_kW=f*p_series[i]*mod[i], Gap_kW=gap[i], Ghost_kW=0.0, Unfilled_kW=0.0))
                continue
            need = gap[i] - act_power
            if need <= 0:
                qc.append(dict(Flag=flag, Gear=gear, Year=t, Registry_kW=A[i], Target_kW=f*p_series[i]*mod[i], Gap_kW=gap[i], Ghost_kW=act_power, Unfilled_kW=0.0))
                continue
            coh = {"built": t, "retire": t + lifespan, "power": 0.0, "rows": []}
            n_new = 0
            while coh["power"] < need and n_new < max_new_per_year \
                    and n_flag < max_ghosts_per_flag:
                donor = pool.sample(1, random_state=rng).iloc[0]
                row = donor.copy()
                # Donor dimensions may be borrowed; attribution belongs to the missing fleet.
                row["Template_Flag"] = donor["Flag"]
                row["Flag"] = flag
                row["VesselType"] = gear
                for attr in ("Authorized_Oceans", "Organization"):
                    if attr in sub:
                        row[attr] = sub[attr].mode().iloc[0] if not sub[attr].mode().empty else "GLOBAL"
                row["Builtdate"] = float(t)
                row["Retire_Year"] = coh["retire"]   # finalised after the cap pass
                row["Is_Ghost"] = 1
                row["Vessel_ID"] = vid
                vid -= 1
                p = float(donor["Enginepower"])
                # Fractional final representative vessel preserves all component ratios.
                row["Ghost_Weight"] = min(1.0, (need - coh["power"]) / p)
                coh["power"] += p * row["Ghost_Weight"]
                coh["rows"].append(row)
                n_new += 1
                n_flag += 1
            cohorts.append(coh)
            realized = act_power + coh["power"]
            if realized > gap[i] + 1e-6:
                raise AssertionError(f"Ghost capacity exceeds gap: {flag}/{gear}/{t}")
            qc.append(dict(Flag=flag, Gear=gear, Year=t, Registry_kW=A[i], Target_kW=f*p_series[i]*mod[i], Gap_kW=gap[i], Ghost_kW=realized, Unfilled_kW=max(gap[i]-realized,0.0)))
            total_power += coh["power"]
            for r in coh["rows"]:
                ghosts.append((r, coh))          # keep link for retirement update
        if n_flag:
            summary.append((key[0], key[1], round(f, 3), n_flag, round(total_power, 0)))

    # finalise retirement years (cap pass may have shortened cohorts)
    rows_out = []
    for r, coh in ghosts:
        r["Retire_Year"] = int(coh["retire"])
        rows_out.append(r)

    qc_df = pd.DataFrame(qc)
    if qc_path is not None:
        qc_df.to_csv(qc_path, index=False, encoding="utf-8-sig")
    if verbose:
        print(f"[Ghost] built {len(rows_out):,} ghosts for {len(summary)} combos")
        for s in summary[:20]:
            print("   %-4s %s f=%.3f ghosts=%d power=%.0f kW" % s)
        print(f"[Ghost] skipped (ratio>{skip_ratio}): {len(skipped)} combos")

    if not rows_out:
        return None
    result = pd.DataFrame(rows_out).reset_index(drop=True)
    result.attrs["capacity_qc"] = qc_df
    return result
