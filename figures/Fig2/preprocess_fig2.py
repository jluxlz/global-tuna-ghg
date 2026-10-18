#!/usr/bin/env python
# ==============================================================================
# preprocess_fig2.py — Grid-level trend computation for Fig2 (v4.0)
# ==============================================================================
# Outputs:
#   1. Fig2_PanelA_Era_CEI.csv       — 3-era mean CEI + Dominant_Species (5 deg grid)
#   2. Fig2_PanelBC_Grid_Slopes.csv  — per-grid x Gear slopes (CEI, GHG, Catch, CPUE)
#
# Key changes (v4.0):
#   - Added CPUE slope computation (CPUE = Catch / Standard_Effort)
#   - Retained Gear dimension throughout grid x year aggregation
#   - Replaced Mann-Kendall with unified linregress p-value for all metrics
#   - Added low-value noise filter: pct slopes -> NaN if Mean_Catch < 1.0 t
# ==============================================================================

import pandas as pd
import numpy as np
from scipy import stats
import os
import sys
import time
import json
import hashlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# 0. Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "..", "GHG_Calculation")
os.chdir(SCRIPT_DIR)

# ---------------------------------------------------------------------------
# 1. Read & filter raw data
# ---------------------------------------------------------------------------
print("Reading Base_3_Spatial_Grid_Enriched.csv...")
t0 = time.time()
df_raw = pd.read_csv(os.path.join(DATA_DIR, "Base_3_Spatial_Grid_Enriched.csv"))
print(f"  {len(df_raw):,} rows in {time.time()-t0:.1f}s")

df_raw = df_raw[
    (df_raw["Gear"].isin(["LL", "PS"])) &
    (df_raw["Total_Catch"] > 0) &
    (df_raw["GHG_emissions_median"].notna()) & (df_raw["GHG_emissions_median"] > 0) &
    (df_raw["Grid_CEI"].notna()) & (df_raw["Grid_CEI"] > 0) &
    (df_raw["Year"] >= 1950) & (df_raw["Year"] <= 2025)
].copy()
print(f"  After filter: {len(df_raw):,} rows")

SP_COLS = ["SBT_Tonnes", "SKJ_Tonnes", "BET_Tonnes", "YFT_Tonnes", "ALB_Tonnes"]

# ---------------------------------------------------------------------------
# 3. Snap to uniform 5 deg grid (skip bilinear downscaling — Base_3 already
#    provides multi-resolution inputs that are self-consistent at 5 deg)
# ---------------------------------------------------------------------------
print("Snapping to uniform 5 deg grid...")
t0 = time.time()

df_ds = df_raw.copy()
# Snap coordinates to 5 deg grid centre
df_ds["lon"] = np.floor(df_ds["lon"].values / 5) * 5 + 2.5
df_ds["lat"] = np.floor(df_ds["lat"].values / 5) * 5 + 2.5

# Aggregate to grid x year x gear (no weighting needed — Base_3 already
# provides Effort_Prop-weighted values)
agg_dict = {
    "Total_Catch":           "sum",
    "Standard_Effort":       "sum",
    "GHG_emissions_median":  "sum",
}
for sp in SP_COLS:
    agg_dict[sp] = "sum"

df_ds = df_ds.groupby(["Year", "Gear", "lon", "lat"], as_index=False).agg(agg_dict)

# Derived metrics
df_ds["Grid_CEI"] = df_ds["GHG_emissions_median"] / df_ds["Total_Catch"]
df_ds = df_ds[
    df_ds["Grid_CEI"].notna() & (df_ds["Grid_CEI"] > 0) & np.isfinite(df_ds["Grid_CEI"])
]

print(f"  Snapped: {len(df_ds):,} rows, "
      f"{df_ds[['lon','lat']].drop_duplicates().shape[0]:,} grids")
print(f"  Time: {time.time()-t0:.1f}s")

# ---------------------------------------------------------------------------
# 4. Derive CPUE from downscaled data (already at grid x year x gear)
# ---------------------------------------------------------------------------
print("Computing CPUE from downscaled data...")
t0 = time.time()

# Tech-creep correction (2026-09-17): gear-specific fixed rates selected from
# the Palomares & Pauly (2019) spectrum (Ecol. Soc. 24(3):31; C% = 13.8*Y^-0.511)
# by fit to stock-assessment benchmarks (SKJ -> PP-10 = 4.26%/yr; LL-caught
# stocks -> PP-54 = 1.86%/yr). Mirrors jabba_fit.r's PD_PS/PD_LL and its
# 1970 correction base exactly.
PD_BY_GEAR = {"PS": 0.0426, "LL": 0.0186}
def tech_creep_factor(year_arr, gear_arr):
    """Multiplicative factor: nominal CPUE -> tech-creep-corrected CPUE."""
    pd_g = np.where(np.asarray(gear_arr) == "PS",
                    PD_BY_GEAR["PS"], PD_BY_GEAR["LL"])
    return (1.0 - pd_g) ** (np.asarray(year_arr, dtype=float) - 1970.0)

# df_ds columns: Year, Gear, lon, lat, Total_Catch, Standard_Effort,
#                GHG_emissions_median, Grid_CEI, SBT_Tonnes, ...
df_grid_yr = df_ds[df_ds["Year"] >= 1970].copy()
df_grid_yr = df_grid_yr.rename(columns={"GHG_emissions_median": "GHG"})
df_grid_yr["Grid_CPUE"] = (
    df_grid_yr["Total_Catch"] / df_grid_yr["Standard_Effort"].replace(0, np.nan)
)
# Standardize CPUE — remove technological efficiency creep
df_grid_yr["Grid_CPUE"] = (
    df_grid_yr["Grid_CPUE"] * tech_creep_factor(df_grid_yr["Year"].values,
                                                df_grid_yr["Gear"].values)
)
df_grid_yr = df_grid_yr[
    df_grid_yr["Grid_CEI"].notna()  & (df_grid_yr["Grid_CEI"] > 0)  & np.isfinite(df_grid_yr["Grid_CEI"]) &
    df_grid_yr["Grid_CPUE"].notna() & (df_grid_yr["Grid_CPUE"] > 0) & np.isfinite(df_grid_yr["Grid_CPUE"])
]

print(f"  Valid grid x year x gear: {len(df_grid_yr):,} rows")
print(f"  Time: {time.time()-t0:.1f}s")

# ---------------------------------------------------------------------------
# 5. Per-grid x Gear slope computation (unified linregress for all metrics)
# ---------------------------------------------------------------------------
print("Computing per-grid x gear slopes (linregress for CEI, GHG, Catch, CPUE)...")
t0 = time.time()

def compute_grid_stats(grp):
    """Compute linregress slopes, p-values, and dominant species for one grid x gear.
    Note: Gear/lon/lat are grouping columns; NOT returned from here.
    """
    grp = grp.sort_values("Year")
    n_years = grp["Year"].nunique()

    if n_years < 10:
        return pd.Series({
            "N_Years":    n_years,
            "CEI_slope":  np.nan, "GHG_slope": np.nan,
            "Catch_slope": np.nan, "CPUE_slope": np.nan,
            "CEI_pvalue":  np.nan, "GHG_pvalue": np.nan,
            "Catch_pvalue": np.nan, "CPUE_pvalue": np.nan,
            "Mean_CEI":   np.nan, "Mean_GHG":  np.nan,
            "Mean_Catch": np.nan, "Mean_CPUE": np.nan,
            "Dominant_Species": "None"
        })

    # Linear regression for each metric — unified via linregress
    years = grp["Year"].values
    slope_cei,   _, _, pval_cei,   _ = stats.linregress(years, grp["Grid_CEI"].values)
    slope_ghg,   _, _, pval_ghg,   _ = stats.linregress(years, grp["GHG"].values)
    slope_catch, _, _, pval_catch, _ = stats.linregress(years, grp["Total_Catch"].values)
    slope_cpue,  _, _, pval_cpue,  _ = stats.linregress(years, grp["Grid_CPUE"].values)

    # Dominant species by total catch across all years
    sp_totals = {
        "SBT": grp["SBT_Tonnes"].sum(), "SKJ": grp["SKJ_Tonnes"].sum(),
        "BET": grp["BET_Tonnes"].sum(), "YFT": grp["YFT_Tonnes"].sum(),
        "ALB": grp["ALB_Tonnes"].sum(),
    }
    dom_sp = max(sp_totals, key=sp_totals.get)
    if sp_totals[dom_sp] == 0:
        dom_sp = "None"

    return pd.Series({
        "N_Years":       n_years,
        "CEI_slope":     slope_cei,   "CEI_pvalue":  pval_cei,
        "GHG_slope":     slope_ghg,   "GHG_pvalue":  pval_ghg,
        "Catch_slope":   slope_catch, "Catch_pvalue": pval_catch,
        "CPUE_slope":    slope_cpue,  "CPUE_pvalue":  pval_cpue,
        "Mean_CEI":      grp["Grid_CEI"].mean(),
        "Mean_GHG":      grp["GHG"].mean(),
        "Mean_Catch":    grp["Total_Catch"].mean(),
        "Mean_CPUE":     grp["Grid_CPUE"].mean(),
        "Dominant_Species": dom_sp
    })

# Group by Gear + lon + lat — explicit loop to avoid pandas 2.2 apply issues
records = []
for (gear, lon, lat), grp in df_grid_yr.groupby(["Gear", "lon", "lat"]):
    row = compute_grid_stats(grp)
    row["Gear"] = gear
    row["lon"]  = lon
    row["lat"]  = lat
    records.append(row)
df_slopes = pd.DataFrame(records)

# Remove rows with invalid slopes
df_slopes = df_slopes[
    df_slopes["CEI_slope"].notna()  & np.isfinite(df_slopes["CEI_slope"]) &
    df_slopes["GHG_slope"].notna()  & np.isfinite(df_slopes["GHG_slope"]) &
    df_slopes["Catch_slope"].notna() & np.isfinite(df_slopes["Catch_slope"]) &
    df_slopes["CPUE_slope"].notna()  & np.isfinite(df_slopes["CPUE_slope"])
].copy()

# --- Percentage slopes ---
df_slopes["CEI_slope_pct"]   = np.where(
    df_slopes["Mean_CEI"] > 0,
    df_slopes["CEI_slope"] / df_slopes["Mean_CEI"] * 100, np.nan)
df_slopes["GHG_slope_pct"]   = np.where(
    df_slopes["Mean_GHG"] > 0,
    df_slopes["GHG_slope"] / df_slopes["Mean_GHG"] * 100, np.nan)
df_slopes["Catch_slope_pct"] = np.where(
    df_slopes["Mean_Catch"] > 0,
    df_slopes["Catch_slope"] / df_slopes["Mean_Catch"] * 100, np.nan)
df_slopes["CPUE_slope_pct"]  = np.where(
    df_slopes["Mean_CPUE"] > 0,
    df_slopes["CPUE_slope"] / df_slopes["Mean_CPUE"] * 100, np.nan)

# --- Low-value noise filter ---
# Suppress percentage slopes where the mean level is extremely low
# (prevents extreme % values from division by near-zero denominators)
# NOTE: CPUE threshold removed — LL uses hooks (small CPUE ~1e-4) vs PS uses sets
low_catch_mask  = df_slopes["Mean_Catch"] < 1.0         # t
low_cei_mask    = df_slopes["Mean_CEI"]   < 0.01        # kg CO2e / kg
low_ghg_mask    = df_slopes["Mean_GHG"]   < 0.1         # t CO2e
low_mask = low_catch_mask | low_cei_mask | low_ghg_mask

for col in ["CEI_slope_pct", "GHG_slope_pct", "Catch_slope_pct", "CPUE_slope_pct"]:
    df_slopes.loc[low_mask, col] = np.nan

# Drop rows where ALL pct slopes are NaN
df_slopes = df_slopes[
    df_slopes[["CEI_slope_pct", "GHG_slope_pct",
               "Catch_slope_pct", "CPUE_slope_pct"]].notna().any(axis=1)
]

print(f"  Valid slopes: {len(df_slopes):,} grids (with Gear dimension)")
print(f"  CEI  slope pct range:  {df_slopes['CEI_slope_pct'].min():.3f} to "
      f"{df_slopes['CEI_slope_pct'].max():.3f} %/yr")
print(f"  CPUE slope pct range:  {df_slopes['CPUE_slope_pct'].min():.3f} to "
      f"{df_slopes['CPUE_slope_pct'].max():.3f} %/yr")
for m in ["CEI", "GHG", "Catch", "CPUE"]:
    n_sig = len(df_slopes[df_slopes[f"{m}_pvalue"] < 0.05])
    print(f"  {m} p<0.05: {n_sig:,} ({n_sig/len(df_slopes)*100:.1f}%)")
print(f"  Time: {time.time()-t0:.1f}s")

# ---------------------------------------------------------------------------
# 6. 3-era CEI means (Panel A — retains Gear dimension)
# ---------------------------------------------------------------------------
print("Computing 3-era CEI means...")
t0 = time.time()

# Era boundaries: data begins ~1970 (>50 grids). Three roughly equal periods.
df_ds["Era"] = pd.cut(
    df_ds["Year"],
    bins=[1969, 1990, 2005, 2025],
    labels=["1970-1990", "1991-2005", "2006-2025"]
)

# Compute Dominant_Species per grid x gear x era (from species tonnage)
era_sp = df_ds.groupby(["Era", "Gear", "lon", "lat"], observed=True).agg(
    Sum_GHG   = ("GHG_emissions_median", "sum"),
    Sum_Catch = ("Total_Catch",          "sum"),
    SBT_Tonnes = ("SBT_Tonnes", "sum"),
    SKJ_Tonnes = ("SKJ_Tonnes", "sum"),
    BET_Tonnes = ("BET_Tonnes", "sum"),
    YFT_Tonnes = ("YFT_Tonnes", "sum"),
    ALB_Tonnes = ("ALB_Tonnes", "sum"),
).reset_index()
era_sp["Mean_CEI"] = era_sp["Sum_GHG"] / era_sp["Sum_Catch"]

# Dominant species per grid x gear x era
sp_map = {"SBT": "SBT_Tonnes", "SKJ": "SKJ_Tonnes", "BET": "BET_Tonnes",
          "YFT": "YFT_Tonnes", "ALB": "ALB_Tonnes"}
def get_dom_sp(row):
    totals = {sp: row[col] for sp, col in sp_map.items()}
    dom = max(totals, key=totals.get)
    return dom if totals[dom] > 0 else "None"
era_sp["Dominant_Species"] = era_sp.apply(get_dom_sp, axis=1)
era_sp["Dominant_Share"] = era_sp[SP_COLS].max(axis=1)/era_sp["Sum_Catch"]

df_era = era_sp[
    era_sp["Mean_CEI"].notna() & (era_sp["Mean_CEI"] > 0) & np.isfinite(era_sp["Mean_CEI"])
].copy()

print(f"  Era data: {len(df_era):,} rows")
print(f"  Time: {time.time()-t0:.1f}s")

# ---------------------------------------------------------------------------
# 7. Export CSVs
# ---------------------------------------------------------------------------
print("\nExporting...")

# Panel A: era means with Dominant_Species
df_era_out = df_era[[
    "Era", "Gear", "lon", "lat", "Mean_CEI", "Sum_GHG", "Sum_Catch",
    "Dominant_Species", "Dominant_Share"
]]
df_era_out.to_csv("Fig2_PanelA_Era_CEI.csv", index=False)
print(f"  => Fig2_PanelA_Era_CEI.csv ({len(df_era_out):,} rows)")

# Panel B: grid x gear slopes (LL and PS kept separate by Gear column)
df_slopes_out = df_slopes[[
    "Gear", "lon", "lat", "N_Years",
    "CEI_slope", "CEI_slope_pct", "CEI_pvalue",
    "GHG_slope", "GHG_slope_pct", "GHG_pvalue",
    "Catch_slope", "Catch_slope_pct", "Catch_pvalue",
    "CPUE_slope", "CPUE_slope_pct", "CPUE_pvalue",
    "Mean_CEI", "Mean_GHG", "Mean_Catch", "Mean_CPUE",
    "Dominant_Species"
]]
df_slopes_out.to_csv("Fig2_PanelBC_Grid_Slopes.csv", index=False)
print(f"  => Fig2_PanelBC_Grid_Slopes.csv ({len(df_slopes_out):,} rows)")

# Summary stats
print("\n=== Summary Statistics ===")
for m in ["CEI", "GHG", "Catch", "CPUE"]:
    col = f"{m}_slope_pct"
    print(f"  {m} slope pct: min={df_slopes[col].min():.3f}, "
          f"median={df_slopes[col].median():.3f}, max={df_slopes[col].max():.3f}")

print("\nDone!")

with open("Fig2_Data_QC.json", "w", encoding="utf-8") as f:
    json.dump(dict(Trend_Period=[1970,2025], Minimum_Years=10,
        Actual_Grid_Years=[int(df_ds.Year.min()),int(df_ds.Year.max())],
        Trend_Method="linear slope divided by temporal mean, percent per year",
        Era_CEI="ratio of period totals", PD_By_Gear=PD_BY_GEAR,
        Gear_Units_Kept_Separate=True, Era_Rows=len(df_era_out), Trend_Rows=len(df_slopes_out),
        Source_SHA256=hashlib.file_digest(open(os.path.join(DATA_DIR,"Base_3_Spatial_Grid_Enriched.csv"),"rb"),"sha256").hexdigest()), f, indent=2)
