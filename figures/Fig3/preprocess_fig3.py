"""Build the two-factor CEI trend plane from annual data (no plotting).

E_star = Standard_Effort / (1 - PD_gear)**(Year - 1970).
OLS[ln(E_star/C)] + OLS[ln(GHG/E_star)] = OLS[ln(GHG/C)].
Hooks and sets are NEVER summed together. Each bubble is grid x gear x era;
the species label denotes dominant catch, not species-specific emissions.
"""

from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import linregress

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv"
SPECIES = ["SBT", "SKJ", "BET", "YFT", "ALB"]
SP_COLS = [f"{s}_Tonnes" for s in SPECIES]
ERAS = ["1970-1990", "1991-2005", "2006-2025"]
PD_BY_GEAR = {"LL": 0.0186, "PS": 0.0426}
ORGS = ["WCPFC", "IATTC", "ICCAT", "IOTC", "CCSBT"]
KEY = ["Year", "Flag", "Gear", "squaretypecode", "lat", "lon",
       "EffortType", "Organization"]


def aggregate_bc(d, group_cols):
    """Ratios of totals: correct annual effort before summing across years."""
    g = d.groupby(group_cols, as_index=False, observed=True).agg(
        Sum_Effort=("Standard_Effort", "sum"),
        Sum_Corrected_Effort=("Corrected_Effort", "sum"),
        Sum_Catch=("Total_Catch", "sum"), Sum_GHG=("GHG_emissions_median", "sum"),
        N_Records=("Year", "size"), N_Years=("Year", "nunique"),
        First_Year=("Year", "min"), Last_Year=("Year", "max"))
    g["Plottable"] = (g.Sum_Catch > 0) & (g.Sum_Corrected_Effort > 0) & (g.Sum_GHG > 0)
    scale = np.where(g.Gear == "LL", 100.0, 1.0)
    g["Xm"] = g.Sum_Corrected_Effort / g.Sum_Catch.replace(0, np.nan) * scale
    g["Ym"] = g.Sum_GHG / g.Sum_Corrected_Effort * scale
    g["Nominal_Xm"] = g.Sum_Effort / g.Sum_Catch.replace(0, np.nan) * scale
    g["Nominal_Ym"] = g.Sum_GHG / g.Sum_Effort * scale
    g["CEI"] = g.Sum_GHG / g.Sum_Catch.replace(0, np.nan)
    g["GHG"] = g.Sum_GHG / 1e6
    g["Mean_Annual_GHG_Mt"] = g.GHG / g.N_Years
    g["Effective_Correction"] = g.Sum_Effort / g.Sum_Corrected_Effort
    g["Identity_Relative_Residual"] = (g.Xm * g.Ym / scale**2) / g.CEI - 1
    np.testing.assert_allclose(g.Xm * g.Ym / scale**2, g.CEI, rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(g.Nominal_Xm * g.Nominal_Ym / scale**2, g.CEI, rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(g.Sum_GHG.sum(), d.GHG_emissions_median.sum(), rtol=1e-12)
    np.testing.assert_allclose(g.Sum_Catch.sum(), d.Total_Catch.sum(), rtol=1e-12)
    np.testing.assert_allclose(g.Sum_Corrected_Effort.sum(), d.Corrected_Effort.sum(), rtol=1e-12)
    return g.sort_values(group_cols)


def build_bc_era(raw):
    """Preview: grid-era distributions and RFMO ratios of totals, 1970 onward.

    Background coverage is descriptive; it has no trend-fit year threshold.
    Both layers use the same positive source records. Foreground coordinates
    are ratios of sums, NOT averages of the background coordinates.
    """
    with SOURCE.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    matched_records = validate_upstream_catch(raw)
    d = raw.loc[raw.Gear.isin(PD_BY_GEAR) & raw.Organization.isin(ORGS)
        & raw.Year.between(1970, 2025) & (raw.Standard_Effort > 0)
        & (raw.GHG_emissions_median > 0) & (raw.Total_Catch > 0)].copy()
    d["Corrected_Effort"] = d.Standard_Effort / (
        (1 - d.Gear.map(PD_BY_GEAR)) ** (d.Year - 1970))
    d["lon"] = np.floor(d.lon / 5) * 5 + 2.5
    d["lat"] = np.floor(d.lat / 5) * 5 + 2.5
    d["Era"] = pd.Categorical(np.select(
        [d.Year <= 1990, d.Year <= 2005], ERAS[:2], default=ERAS[2]),
        categories=ERAS, ordered=True)
    regional_keys = ["Gear", "Organization", "Era"]
    grid_keys = regional_keys + ["lon", "lat"]
    grid = aggregate_bc(d, grid_keys)
    region = aggregate_bc(d, regional_keys)
    grid["Record_Scope"] = region["Record_Scope"] = "positive_catch_positive_effort_positive_GHG"
    rebuilt = grid.groupby(regional_keys, as_index=False, observed=True)[
        ["Sum_Catch", "Sum_Corrected_Effort", "Sum_GHG"]].sum()
    check = region.merge(rebuilt, on=regional_keys, validate="one_to_one", suffixes=("", "_grids"))
    for col in ["Sum_Catch", "Sum_Corrected_Effort", "Sum_GHG"]:
        np.testing.assert_allclose(check[col], check[f"{col}_grids"], rtol=1e-12)
    for gear, letter in [("LL", "B"), ("PS", "C")]:
        grid.loc[grid.Gear == gear].to_csv(HERE / f"Fig3_Panel{letter}_Era_Grid_Factors.csv", index=False)
        region.loc[region.Gear == gear].to_csv(HERE / f"Fig3_Panel{letter}_Era_Regional_Factors.csv", index=False)
    audit = dict(source_sha256=source_hash, upstream_catch_record_identity="PASS",
        upstream_matched_records=matched_records,
        retained_source_records=len(d), background_grid_era_rows=len(grid),
        foreground_regional_era_rows=len(region), eras=ERAS, pd_by_gear=PD_BY_GEAR,
        background_eligibility="At least one positive-catch, positive-effort, positive-GHG record; no trend-fit threshold",
        foreground="Ratios of regional totals; not a centroid of background coordinates",
        total_retained_GHG_Mt=float(d.GHG_emissions_median.sum()/1e6),
        max_abs_factor_identity_relative_residual=float(max(
            grid.Identity_Relative_Residual.abs().max(), region.Identity_Relative_Residual.abs().max())),
        grid_to_region_conservation="PASS", factor_identity="PASS")
    (HERE / "Fig3_PanelBC_Era_Audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))


def validate_upstream_catch(raw):
    """Validate catch records directly, without depending on archived audits."""
    upstream_path = HERE.parents[1] / "effort_data/Grid_Catch_Allocation.csv"
    upstream = pd.read_csv(upstream_path).rename(columns={
        "SquareTypeCode": "squaretypecode", "Lat": "lat", "Lon": "lon"})
    if upstream.duplicated(KEY).any():
        raise ValueError("Duplicate upstream catch-record key; abort Fig3 b/c.")
    matched = raw[KEY + SP_COLS].merge(upstream[KEY + SP_COLS], on=KEY,
        how="outer", validate="one_to_one", indicator=True, suffixes=("_base", "_upstream"))
    if not (matched._merge == "both").all():
        raise ValueError("Base_3 catch keys do not match the upstream allocation table.")
    for col in SP_COLS:
        np.testing.assert_allclose(matched[f"{col}_base"], matched[f"{col}_upstream"],
                                   rtol=1e-12, atol=1e-9)
    return len(matched)


def build():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cols = list(dict.fromkeys(KEY + SP_COLS +
                ["Standard_Effort", "Total_Catch", "GHG_emissions_median"]))
    raw = pd.read_csv(SOURCE, usecols=cols)
    if raw.duplicated(KEY).any():
        raise ValueError("Duplicate catch-record keys in Base_3; abort Fig3.")
    numeric = ["Year", "lat", "lon", "Standard_Effort", "Total_Catch",
               "GHG_emissions_median"] + SP_COLS
    if not np.isfinite(raw[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite source values; resolve before aggregation.")
    if any(arg in {"bc", "bc-era"} for arg in sys.argv[1:]):
        build_bc_era(raw)
        return
    d = raw.loc[raw.Gear.isin(PD_BY_GEAR) & raw.Year.between(1970, 2025)
                & (raw.Standard_Effort > 0) & (raw.Total_Catch > 0)
                & (raw.GHG_emissions_median > 0)].copy()
    # Use the same uniform 5-degree centres as preprocess_fig2.py.
    d["lon"] = np.floor(d.lon / 5) * 5 + 2.5
    d["lat"] = np.floor(d.lat / 5) * 5 + 2.5
    sums = ["Standard_Effort", "Total_Catch", "GHG_emissions_median"] + SP_COLS
    annual = d.groupby(["Gear", "lon", "lat", "Year"], as_index=False)[sums].sum()
    np.testing.assert_allclose(annual[sums].sum(), d[sums].sum(), rtol=1e-12)
    annual = annual.rename(columns={"GHG_emissions_median": "GHG"})
    annual["Creep_Factor"] = (1 - annual.Gear.map(PD_BY_GEAR)) ** (annual.Year - 1970)
    annual["Corrected_Effort"] = annual.Standard_Effort / annual.Creep_Factor
    annual["Effort_per_tonne"] = annual.Corrected_Effort / annual.Total_Catch
    annual["GHG_per_effort"] = annual.GHG / annual.Corrected_Effort
    annual["CEI"] = annual.GHG / annual.Total_Catch
    np.testing.assert_allclose(annual.Effort_per_tonne * annual.GHG_per_effort,
                               annual.CEI, rtol=1e-12)
    annual["Era"] = pd.cut(annual.Year, bins=[1969, 1990, 2005, 2025], labels=ERAS)
    annual.to_csv(HERE / "Fig3_PanelA_Annual_Factors.csv", index=False)

    fits = []
    for (gear, lon, lat, era), g in annual.groupby(
            ["Gear", "lon", "lat", "Era"], observed=True, sort=True):
        g = g.sort_values("Year")
        sp = g[SP_COLS].sum()
        dominant = sp.idxmax().replace("_Tonnes", "") if sp.max() > 0 else "None"
        row = dict(Gear=gear, lon=lon, lat=lat, Era=str(era), N_Years=len(g),
                   First_Year=int(g.Year.min()), Last_Year=int(g.Year.max()),
                   Dominant_Species=dominant, Mean_GHG=g.GHG.mean(),
                   Total_GHG=g.GHG.sum(), Mean_Catch=g.Total_Catch.mean(),
                   Mean_CEI=g.CEI.mean())
        # Retain the original era-fit criteria: >=8 years, mean CEI >0.01.
        row["Eligible"] = len(g) >= 8 and row["Mean_CEI"] > 0.01 and dominant != "None"
        if len(g) >= 2:
            for col, prefix in [("Effort_per_tonne", "Effort"),
                                ("GHG_per_effort", "GHG_Effort"), ("CEI", "CEI")]:
                fit = linregress(g.Year, np.log(g[col]))
                row[f"{prefix}_log_trend_pct"] = 100 * fit.slope
                row[f"{prefix}_pvalue"] = fit.pvalue
                row[f"{prefix}_stderr_pct"] = 100 * fit.stderr
            row["Slope_Identity_Residual"] = (row["Effort_log_trend_pct"]
                + row["GHG_Effort_log_trend_pct"] - row["CEI_log_trend_pct"])
        fits.append(row)
    all_fits = pd.DataFrame(fits)
    eligible = all_fits.loc[all_fits.Eligible].copy()
    if eligible.empty:
        raise ValueError("No eligible era fits.")
    np.testing.assert_allclose(eligible.Effort_log_trend_pct
        + eligible.GHG_Effort_log_trend_pct, eligible.CEI_log_trend_pct, atol=1e-10)
    x, y = eligible.Effort_log_trend_pct, eligible.GHG_Effort_log_trend_pct
    eligible["Quadrant"] = np.select(
        [(x > 0) & (y > 0), (x < 0) & (y > 0),
         (x < 0) & (y < 0), (x > 0) & (y < 0)],
        ["Q1_both_increase", "Q2_effort_decreases_GHG_effort_increases",
         "Q3_both_decrease", "Q4_effort_increases_GHG_effort_decreases"], default="Axis")
    eligible["CEI_Increases"] = eligible.CEI_log_trend_pct > 0
    all_fits.to_csv(HERE / "Fig3_PanelA_Fit_Eligibility.csv", index=False)
    eligible.to_csv(HERE / "Fig3_PanelA_Factor_Trends.csv", index=False)

    # All is an overlay for plotting only. Never count that duplicate in statistics.
    all_panel = eligible.assign(Dominant_Species="All")
    plot_data = pd.concat([all_panel, eligible], ignore_index=True)
    centroids, quadrants = [], []
    for (species, era), g in plot_data.groupby(["Dominant_Species", "Era"], sort=False):
        w = g.Total_GHG
        centroids.append(dict(Dominant_Species=species, Era=era,
            Xc=np.average(g.Effort_log_trend_pct, weights=w),
            Yc=np.average(g.GHG_Effort_log_trend_pct, weights=w),
            CEIc=np.average(g.CEI_log_trend_pct, weights=w),
            Total_GHG=w.sum(), N_Grid_Gear=len(g), N_LL=int((g.Gear == "LL").sum()),
            N_PS=int((g.Gear == "PS").sum())))
        for quadrant in ["Q1_both_increase", "Q2_effort_decreases_GHG_effort_increases",
                         "Q3_both_decrease", "Q4_effort_increases_GHG_effort_decreases", "Axis"]:
            mask = g.Quadrant == quadrant
            quadrants.append(dict(Dominant_Species=species, Era=era, Quadrant=quadrant,
                N_Grid_Gear=int(mask.sum()), N_Total=len(g), Count_pct=100 * mask.mean(),
                Emissions_pct=100 * w.loc[mask].sum() / w.sum()))
    cent = pd.DataFrame(centroids)
    np.testing.assert_allclose(cent.Xc + cent.Yc, cent.CEIc, atol=1e-10)
    cent.to_csv(HERE / "Fig3_PanelA_Weighted_Centroids.csv", index=False)
    quad = pd.DataFrame(quadrants)
    quad["Era"] = pd.Categorical(quad.Era, categories=ERAS, ordered=True)
    quad.sort_values(["Dominant_Species", "Era", "Quadrant"]).to_csv(
        HERE / "Fig3_PanelA_Quadrant_Summary.csv", index=False)
    era_summary = []
    for gear in ["All", "LL", "PS"]:
        subset = eligible if gear == "All" else eligible.loc[eligible.Gear == gear]
        for era in ERAS:
            g = subset.loc[subset.Era == era]
            if g.empty:
                continue
            q4 = g.Quadrant == "Q4_effort_increases_GHG_effort_decreases"
            q1 = g.Quadrant == "Q1_both_increase"
            increases = g.CEI_Increases
            era_summary.append(dict(Gear=gear, Era=era, N_Grid_Gear=len(g),
                N_Unique_Spatial_Grids=len(g[["lon", "lat"]].drop_duplicates()),
                Q1_Count=int(q1.sum()), Q1_Count_pct=100 * q1.mean(),
                Q1_Emissions_pct=100 * g.loc[q1, "Total_GHG"].sum() / g.Total_GHG.sum(),
                CEI_Increase_Count=int(increases.sum()), CEI_Increase_Count_pct=100 * increases.mean(),
                Q4_CEI_Increase_Count=int((q4 & increases).sum()),
                Q4_CEI_Increase_pct_of_all=100 * (q4 & increases).mean()))
    pd.DataFrame(era_summary).to_csv(HERE / "Fig3_PanelA_Era_Summary.csv", index=False)
    with SOURCE.open("rb") as source_stream:
        source_hash = hashlib.file_digest(source_stream, "sha256").hexdigest()
    audit = dict(source=str(SOURCE), source_sha256=source_hash, source_rows=len(raw),
        retained_source_rows=len(d), annual_grid_gear_rows=len(annual),
        eligible_grid_gear_era_rows=len(eligible), pd_by_gear=PD_BY_GEAR,
        min_years=8, min_mean_cei=0.01, weight="Total_GHG within eligible grid x gear x era",
        max_abs_slope_identity_residual=float(eligible.Slope_Identity_Residual.abs().max()),
        annual_factor_identity="PASS", aggregation_conservation="PASS",
        source_unique_catch_key="PASS", slope_identity="PASS", centroid_identity="PASS")
    (HERE / "Fig3_Decomposition_Audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    build_bc_era(raw)


if __name__ == "__main__":
    build()
