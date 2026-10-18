#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
Stratified Hot-Deck Imputation — Builtdate + Monte Carlo LCA
=============================================================================
Reads After_PMM_Vessels.csv (Tonnage & Enginepower already PMM-imputed),
applies stratified hot-deck imputation with dynamic fallback for missing
Builtdate, then runs a Monte Carlo LCA simulation.

Key improvement over previous version:
  - NO mean imputation — Tonnage/Enginepower from PMM are preserved as-is
  - Stratified hot-deck with 4-tier dynamic fallback for Builtdate
  - Uses the canonical LCA emission model from GHG_Calculation/

Imputation strategy for Builtdate:
  Level 1: Exact match — VesselType + LengthCategory + Flag
  Level 2: Drop Flag     — VesselType + LengthCategory
  Level 3: Drop both     — VesselType only
  Level 4: Global        — all valid Builtdate values

Output:
  - imputation_summary.csv  — donor pool statistics per stratum
  - MC_Results.csv          — Monte Carlo simulation results
=============================================================================
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# =============================================================================
# Paths
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # Stratified_Hot-Deck_Imputation/
ROOT_DIR = os.path.dirname(BASE_DIR)
PMM_OUTPUT = os.path.join(ROOT_DIR, "PMM_Imputation", "After_PMM_Vessels.csv")
IMPUTATION_SUMMARY = os.path.join(BASE_DIR, "imputation_summary.csv")
MC_RESULTS = os.path.join(BASE_DIR, "MC_Results.csv")
FINAL_OUTPUT = os.path.join(BASE_DIR, "After_HotDeck_Vessels.csv")

# =============================================================================
# 1. Emission model parameters
# =============================================================================

FC_LOOKUP = {
    1950: 1.21, 1951: 1.21, 1952: 1.20, 1953: 1.20, 1954: 1.20, 1955: 1.20,
    1956: 1.20, 1957: 1.20, 1958: 1.20, 1959: 1.19, 1960: 1.19, 1961: 1.19,
    1962: 1.19, 1963: 1.18, 1964: 1.18, 1965: 1.18, 1966: 1.18, 1967: 1.17,
    1968: 1.16, 1969: 1.16, 1970: 1.15, 1971: 1.14, 1972: 1.14, 1973: 1.13,
    1974: 1.12, 1975: 1.11, 1976: 1.11, 1977: 1.10, 1978: 1.09, 1979: 1.09,
    1980: 1.08, 1981: 1.07, 1982: 1.07, 1983: 1.06, 1984: 1.06, 1985: 1.05,
    1986: 1.05, 1987: 1.04, 1988: 1.04, 1989: 1.04, 1990: 1.03, 1991: 1.03,
    1992: 1.03, 1993: 1.02, 1994: 1.02, 1995: 1.02, 1996: 1.01, 1997: 1.01,
    1998: 1.01, 1999: 1.00, 2000: 1.00, 2001: 1.00, 2002: 1.00, 2003: 1.00,
    2004: 0.99, 2005: 0.99, 2006: 0.99, 2007: 0.99, 2008: 0.99, 2009: 0.99,
    2010: 0.99, 2011: 0.99, 2012: 0.99, 2013: 0.99, 2014: 0.99, 2015: 0.99,
    2016: 0.99,
}


def get_fc(year):
    if pd.isna(year):
        return 1.0
    if year < 1950:
        return 1.21
    if year > 2016:
        return 0.99
    return FC_LOOKUP.get(int(year), 1.0)


# =============================================================================
# 2. Data preparation & donor pool construction
# =============================================================================

def prepare_data_and_pools(file_path, current_year=2024, min_n=5):
    """
    Load PMM-imputed data, build stratified donor pools for Builtdate.
    Does NOT impute Tonnage/Enginepower — those are already done by PMM.
    """
    print(f"Loading PMM-imputed data: {file_path}")
    df = pd.read_csv(file_path, encoding="utf-8-sig")
    print(f"  {len(df)} vessels loaded.")

    # Normalize column names — handle both English and Chinese variants
    rename_map = {}
    for col in df.columns:
        if col == "Length(m)":
            rename_map[col] = "Length"
        elif col == "Tonnage(t)":
            rename_map[col] = "Tonnage"
        elif col == "Enginepower(kw)":
            rename_map[col] = "Enginepower"
    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    # Ensure numeric types (but do NOT fill NaNs — PMM already handled)
    for col in ["Length", "Tonnage", "Enginepower", "Builtdate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Report current state ---
    print("\n  Current data completeness (after PMM):")
    for col in ["Length", "Tonnage", "Enginepower", "Builtdate"]:
        n_miss = df[col].isna().sum()
        n_zero = ((df[col].fillna(1) == 0) & df[col].notna()).sum()
        pct = (n_miss + n_zero) / len(df) * 100
        print(f"    {col}: {len(df) - n_miss - n_zero} present, "
              f"{n_miss + n_zero} missing ({pct:.1f}%)")

    # --- Length categorization ---
    df["LengthCategory"] = np.where(df["Length"].fillna(999) < 12, "< 12m", ">= 12m")

    # --- Remove small vessels > 60 years old ---
    mask_remove = (df["LengthCategory"] == "< 12m") & (df["Builtdate"].notna()) & \
                  (df["Builtdate"] < (current_year - 60))
    n_remove = mask_remove.sum()
    if n_remove > 0:
        print(f"\n  Removing {n_remove} small vessels with Builtdate < {current_year - 60}")
        df = df[~mask_remove].copy()
    else:
        print(f"\n  No vessels removed by age filter.")

    # --- Build donor pools for Builtdate ---
    valid_data = df.dropna(subset=["Builtdate"])
    print(f"  Donor pool: {len(valid_data)} vessels with known Builtdate")

    def get_donor_pool(v_type, length_cat, flag):
        """Dynamic fallback donor pool for Builtdate."""
        # Level 1: Perfect match
        pool = valid_data[(valid_data["VesselType"] == v_type) &
                          (valid_data["LengthCategory"] == length_cat) &
                          (valid_data["Flag"] == flag)]["Builtdate"].values
        if len(pool) >= min_n:
            return pool, "Level 1 (VesselType + LengthCategory + Flag)"

        # Level 2: Drop Flag
        pool = valid_data[(valid_data["VesselType"] == v_type) &
                          (valid_data["LengthCategory"] == length_cat)]["Builtdate"].values
        if len(pool) >= min_n:
            return pool, "Level 2 (VesselType + LengthCategory)"

        # Level 3: Drop LengthCategory
        pool = valid_data[(valid_data["VesselType"] == v_type)]["Builtdate"].values
        if len(pool) >= min_n:
            return pool, "Level 3 (VesselType only)"

        # Level 4: Global fallback
        return valid_data["Builtdate"].values, "Level 4 (Global)"

    # Build donor pool dictionary & metrics table
    metrics = []
    pool_dict = {}

    stratum_combinations = df[["VesselType", "LengthCategory", "Flag"]].drop_duplicates()

    for _, row in stratum_combinations.iterrows():
        vt, lc, fl = row["VesselType"], row["LengthCategory"], row["Flag"]
        if pd.isna(vt) or pd.isna(lc):
            continue
        pool, level = get_donor_pool(vt, lc, fl)
        pool_dict[(vt, lc, fl)] = pool

        metrics.append({
            "VesselType": vt,
            "LengthCategory": lc,
            "Flag": fl,
            "Pool_Size": len(pool),
            "Median_Year": int(np.median(pool)),
            "Min_Year": int(np.min(pool)),
            "Max_Year": int(np.max(pool)),
            "Fallback_Level": level,
        })

    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(IMPUTATION_SUMMARY, index=False, encoding="utf-8-sig")
    print(f"\n  Donor pools: {len(pool_dict)} strata → {IMPUTATION_SUMMARY}")

    # Print fallback distribution
    fb_counts = metrics_df["Fallback_Level"].value_counts()
    for level, count in fb_counts.items():
        print(f"    {level}: {count} strata")

    return df, pool_dict


# =============================================================================
# 3. Emission calculation (canonical LCA model)
# =============================================================================

def calculate_yearly_emissions(df_year, calc_year):
    """
    Calculate per-vessel GHG emissions for a given year.
    Expects columns: 建造日期, Length(m), Enginepower(kw), Tonnage(t), VesselType
    (Column names are mapped to Chinese before calling.)
    """
    df_year = df_year.copy()

    # Fuel carbon factor
    df_year["FC"] = df_year["建造日期"].apply(get_fc)

    SFR = {"small": 0.00035, "large": 0.0002}
    T = {"LL": 334, "PS": 195, "TS": 300}
    H = {"LL": 6, "PS": 24, "TS": 24}
    EF_fuel = {"small": 3.01, "large": 3.17}

    df_year["Size_Cat"] = np.where(df_year["Length(m)"].fillna(0) < 16, "small", "large")

    # 1. Fuel emissions
    def calc_fuel_row(row):
        v_type = row["VesselType"]
        size = row["Size_Cat"]
        if v_type not in ["PS", "LL", "TS"]:
            return 0
        power = row["Enginepower(kw)"]
        if pd.isna(power) or power <= 0:
            return 0
        t_val = T.get(v_type, 300)
        h_val = H.get(v_type, 24)
        sfr_val = SFR.get(size, 0.0002)
        ef_val = EF_fuel.get(size, 3.17)
        fc_val = row["FC"]
        return power * t_val * sfr_val * fc_val * h_val * ef_val

    df_year["CE_Fuel"] = df_year.apply(calc_fuel_row, axis=1)

    # 2. Gear emissions
    EF_gear = 8.63211
    gear_intensity_PS = {"small": (17.9 + 9.12) / (2 * 1000),
                         "large": (251 + 54) / (2 * 1000)}
    gear_intensity_LL = (0.49 + 0.12) / (2 * 0.0036 * 1000)

    def calc_gear_row(row):
        v_type = row["VesselType"]
        length_val = row["Length(m)"]
        size = row["Size_Cat"]
        if pd.isna(length_val) or length_val <= 0:
            return 0
        if v_type == "PS":
            intensity = gear_intensity_PS.get(size, 0)
        elif v_type == "LL":
            intensity = gear_intensity_LL
        else:
            return 0
        return length_val * intensity * EF_gear

    df_year["CE_Gear"] = df_year.apply(calc_gear_row, axis=1)

    # 3. Build emissions (only in construction year)
    EF_build = 2.228
    df_year["CE_Build"] = np.where(
        df_year["建造日期"] == calc_year,
        df_year["Tonnage(t)"].fillna(0) * EF_build,
        0,
    )

    # 4. Bait emissions
    EF_bait = 0.454
    a_bait = 0.0036
    G_bait = 0.1

    def calc_bait_row(row):
        if row["VesselType"] == "LL" and pd.notna(row["Length(m)"]) and row["Length(m)"] > 0:
            return (row["Length(m)"] / a_bait) * G_bait * EF_bait * 0.01
        return 0

    df_year["CE_Bait"] = df_year.apply(calc_bait_row, axis=1)

    # Total
    df_year["CE_Total"] = (
        df_year["CE_Fuel"].fillna(0)
        + df_year["CE_Gear"].fillna(0)
        + df_year["CE_Build"].fillna(0)
        + df_year["CE_Bait"].fillna(0)
    )
    return df_year


# =============================================================================
# 4. Monte Carlo simulation (stratified hot-deck for Builtdate only)
# =============================================================================

def run_monte_carlo_lca(df_cleaned, pool_dict, calc_year=2024, n_simulations=1000):
    """
    Monte Carlo simulation: in each iteration, impute Builtdate via stratified
    hot-deck sampling, then run the LCA emission model.

    Other parameters (Tonnage, Enginepower) are already imputed by PMM
    and are NOT perturbed here.
    """
    print(f"\n{'='*60}")
    print(f"  Monte Carlo LCA Simulation")
    print(f"  {n_simulations} iterations, calc_year={calc_year}")
    print(f"{'='*60}")

    # Map column names to Chinese for the emission model
    df_cleaned = df_cleaned.rename(columns={
        "Builtdate": "建造日期",
        "Length": "Length(m)",
        "Tonnage": "Tonnage(t)",
        "Enginepower": "Enginepower(kw)",
    })

    # Identify which vessels need Builtdate imputation
    missing_indices = df_cleaned[df_cleaned["建造日期"].isna()].index
    n_missing = len(missing_indices)
    print(f"  Vessels needing Builtdate imputation: {n_missing}")

    if n_missing == 0:
        print("  All vessels have Builtdate. Running single deterministic calculation.")
        df_result = calculate_yearly_emissions(df_cleaned, calc_year)
        total = df_result["CE_Total"].sum()
        print(f"  Total emissions: {total:,.2f} kg CO2eq")
        return {
            "Total_Mean": total,
            "Total_Median": total,
            "Total_P2_5": total,
            "Total_P97_5": total,
            "Fuel_Mean": df_result["CE_Fuel"].sum(),
            "Gear_Mean": df_result["CE_Gear"].sum(),
            "Build_Mean": df_result["CE_Build"].sum(),
            "Bait_Mean": df_result["CE_Bait"].sum(),
        }

    mc_results = {
        "Total_Emissions": [],
        "Fuel_Emissions": [],
        "Gear_Emissions": [],
        "Build_Emissions": [],
        "Bait_Emissions": [],
    }

    for i in range(n_simulations):
        df_sim = df_cleaned.copy()

        # Sample Builtdate from donor pools (hot-deck)
        simulated_years = []
        for idx in missing_indices:
            vt = df_sim.loc[idx, "VesselType"]
            lc = df_sim.loc[idx, "LengthCategory"]
            fl = df_sim.loc[idx, "Flag"]
            key = (vt, lc, fl)
            donor_pool = pool_dict.get(key)
            if donor_pool is None or len(donor_pool) == 0:
                # Global fallback
                donor_pool = df_cleaned["建造日期"].dropna().values
            sampled_year = np.random.choice(donor_pool, size=1, replace=True)[0]
            simulated_years.append(sampled_year)

        df_sim.loc[missing_indices, "建造日期"] = simulated_years

        # Run LCA
        df_sim_result = calculate_yearly_emissions(df_sim, calc_year)

        mc_results["Total_Emissions"].append(df_sim_result["CE_Total"].sum())
        mc_results["Fuel_Emissions"].append(df_sim_result["CE_Fuel"].sum())
        mc_results["Gear_Emissions"].append(df_sim_result["CE_Gear"].sum())
        mc_results["Build_Emissions"].append(df_sim_result["CE_Build"].sum())
        mc_results["Bait_Emissions"].append(df_sim_result["CE_Bait"].sum())

        if (i + 1) % 200 == 0:
            print(f"    {i + 1}/{n_simulations} simulations completed...")

    # --- Summaries ---
    summary = {}
    for key, values in mc_results.items():
        arr = np.array(values)
        summary[f"{key}_Mean"] = np.mean(arr)
        summary[f"{key}_Median"] = np.median(arr)
        summary[f"{key}_P2_5"] = np.percentile(arr, 2.5)
        summary[f"{key}_P97_5"] = np.percentile(arr, 97.5)

    print(f"\n  {'='*50}")
    print(f"  MC Results ({calc_year}, {n_simulations} simulations)")
    print(f"  {'='*50}")
    print(f"  Total Emissions:")
    print(f"    Mean:   {summary['Total_Emissions_Mean']:,.2f} kg CO2eq")
    print(f"    Median: {summary['Total_Emissions_Median']:,.2f} kg CO2eq")
    print(f"    95% CI: [{summary['Total_Emissions_P2_5']:,.2f}, "
          f"{summary['Total_Emissions_P97_5']:,.2f}]")
    print(f"  {'='*50}")

    # Save MC results
    mc_df = pd.DataFrame(mc_results)
    mc_df.to_csv(MC_RESULTS, index=False, encoding="utf-8-sig")
    print(f"\n  MC results saved to: {MC_RESULTS}")

    return summary


# =============================================================================
# 5. Save final (deterministic) imputed dataset
# =============================================================================

def save_deterministic_imputation(df_cleaned, pool_dict):
    """
    Produce a single deterministic imputation (using median donor year)
    and save as the final vessel dataset.
    """
    df_final = df_cleaned.copy()

    # Rename for emission model
    df_final = df_final.rename(columns={
        "Builtdate": "建造日期",
        "Length": "Length(m)",
        "Tonnage": "Tonnage(t)",
        "Enginepower": "Enginepower(kw)",
    })

    missing_indices = df_final[df_final["建造日期"].isna()].index
    if len(missing_indices) > 0:
        for idx in missing_indices:
            vt = df_final.loc[idx, "VesselType"]
            lc = df_final.loc[idx, "LengthCategory"]
            fl = df_final.loc[idx, "Flag"]
            key = (vt, lc, fl)
            donor_pool = pool_dict.get(key)
            if donor_pool is None or len(donor_pool) == 0:
                donor_pool = df_final["建造日期"].dropna().values
            # Deterministic: use median of donor pool
            df_final.loc[idx, "建造日期"] = int(np.median(donor_pool))

    # Rename back to English for output
    df_final = df_final.rename(columns={
        "建造日期": "Builtdate",
        "Length(m)": "Length",
        "Tonnage(t)": "Tonnage",
        "Enginepower(kw)": "Enginepower",
    })

    # Drop temporary columns
    cols_to_drop = [c for c in ["LengthCategory", "Size_Cat", "FC"] if c in df_final.columns]
    if cols_to_drop:
        df_final.drop(columns=cols_to_drop, inplace=True)

    df_final.to_csv(FINAL_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"  Deterministic imputation saved to: {FINAL_OUTPUT}")
    return df_final


# =============================================================================
# 6. Main entry
# =============================================================================

def main():
    print("=" * 70)
    print("  STRATIFIED HOT-DECK IMPUTATION — Builtdate")
    print("  + Monte Carlo LCA Simulation")
    print("=" * 70)

    target_calc_year = 2024
    n_simulations = 1000

    # Step 1: Load PMM-imputed data, build donor pools
    df_base, pools = prepare_data_and_pools(PMM_OUTPUT, current_year=target_calc_year)

    # Step 2: Save deterministic hot-deck imputation
    save_deterministic_imputation(df_base.copy(), pools)

    # Step 3: Monte Carlo LCA
    mc_summary = run_monte_carlo_lca(df_base.copy(), pools,
                                     calc_year=target_calc_year,
                                     n_simulations=n_simulations)

    print("\n" + "=" * 70)
    print("  PIPELINE COMPLETE")
    print("=" * 70)

    return df_base, mc_summary


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
