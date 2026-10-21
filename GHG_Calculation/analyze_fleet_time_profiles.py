"""
analyze_fleet_time_profiles.py
================================
Based PNAS Macro Data Set (TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv), 
The three core ocean fleets around the globe (purse seine, longline, transshipment vessel/support vessel) , By total power P Weighted calculations
Days of sailing (DAS), Operational hours (T_work) ♪ And pure sailing time ♪ (T_move). 

Description of programme (Details GHG_Calculation/readme.txt):
  NomActive      Units: kW × days at sea   (Nominal fishing effort, power×Days)
  NomActiveHours Units: kW × fishing hours  (Nominal fishing effort, power×hours)
  P              Units: kW                  (Total engine power)

  DAS_Weighted    = Σ(kW·days) / Σ(kW) = days (days)
  T_work_Weighted = Σ(kW·hours) / Σ(kW) = hours (hours)
  T_move_Weighted = 24×days - hours = hours (hours)

Core principles: Elimination"Simpsons paradox", All aggregate indicators with P (kW) Weighted for weights, 
Not just a simple arithmetic. 

Author: Claude
Date: 2026-06-04
"""

import pandas as pd
import numpy as np
import os
import sys

# ============================================================
# 0. Global configuration compatible with version
# ============================================================

# Test pandas Version, Compatibility include_groups parameter (pandas >= 2.2.0 Introduction)
_PANDAS_VERSION = tuple(map(int, pd.__version__.split('.')[:2]))
_HAS_INCLUDE_GROUPS = _PANDAS_VERSION >= (2, 2)
print(f"[INFO] pandas Version: {pd.__version__} "
      f"(include_groups parameter{'Available' if _HAS_INCLUDE_GROUPS else 'Not available'})")

# Target fleet (Gear Field Filter)
TARGET_GEARS = [
    'Seine_Purse_Seine',   # purse seine
    'Lines_Longlines',     # longline
    'Others_Support',      # transshipment vessel / support vessel
]

# Data Filter Conditions
MIN_P = 0           # Low Power Limit (Strictly greater than)
MIN_NOM_ACTIVE = 0  # Lower limit on number of days out of the ocean (Strictly greater than)
MIN_NOM_HOURS = 0   # Lower working hours (Strictly greater than)

# File Path (Table of contents relative to script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(
    SCRIPT_DIR,
    'TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv'
)

# Output file
OUTPUT_YEARLY = os.path.join(SCRIPT_DIR, 'TimeProfile_Yearly_by_Length.csv')
OUTPUT_OVERALL = os.path.join(SCRIPT_DIR, 'TimeProfile_Overall_by_Length.csv')


# ============================================================
# 1. Data loading and cleansing
# ============================================================

def load_and_clean_data(filepath: str) -> pd.DataFrame:
    """
    Read CSV And do the cleaning: 
    1. Remove Empty Lines (Like a D 2 Line metadata)
    2. Filter P > 0, NomActive > 0, NomActiveHours > 0
    3. Only the target fleet will be retained Gear Type
    """
    print(f"[INFO] Reading data: {filepath}")

    # Read CSV, pandas ♪ Will be ♪ NA String is automatically recognised as NaN
    df = pd.read_csv(filepath, na_values=['NA', 'na', 'NaN', ''])

    # Remove All Key Columns NaN Yes (Like CSV Its... its... its... its... its 2 The metadata line of the line is in place)
    key_cols = ['P', 'NomActive', 'NomActiveHours', 'Gear', 'Length_Category', 'Year']
    df = df.dropna(subset=key_cols, how='all')

    n_raw = len(df)
    print(f"[INFO] Number of valid original lines: {n_raw}")

    # Ensure values are classified as numeric types (To prevent reading object)
    for col in ['P', 'NomActive', 'NomActiveHours', 'NV', 'GT', 'Year']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # ---- Data Filter ----
    n_before = len(df)

    # Filter P > 0
    mask_p = df['P'] > MIN_P
    # Filter NomActive > 0
    mask_das = df['NomActive'] > MIN_NOM_ACTIVE
    # Filter NomActiveHours > 0
    mask_hours = df['NomActiveHours'] > MIN_NOM_HOURS

    df = df[mask_p & mask_das & mask_hours].copy()
    n_after_filter = len(df)
    print(f"[INFO] Filter P>0 & NomActive>0 & NomActiveHours>0 After: {n_after_filter} "
          f"(Cut {n_before - n_after_filter} Okay)")

    # ---- Target fleet screening ----
    df = df[df['Gear'].isin(TARGET_GEARS)].copy()
    n_after_gear = len(df)
    print(f"[INFO] Were gonna have a target fleet ({TARGET_GEARS}) After: {n_after_gear} "
          f"(Cut {n_after_filter - n_after_gear} Okay)")

    # Check if theres any missing Gear Type
    present_gears = df['Gear'].unique()
    missing = set(TARGET_GEARS) - set(present_gears)
    if missing:
        print(f"[WARN] The following target fleet types do not exist in the data: {missing}")

    # Overview of output data
    print(f"[INFO] Data year range: {int(df['Year'].min())} - {int(df['Year'].max())}")
    print(f"[INFO] Actual Gear Type: {sorted(present_gears)}")
    print(f"[INFO] vessel-length category: {sorted(df['Length_Category'].unique())}")

    return df


# ============================================================
# 2. core weighted aggregation function
# ============================================================

def weighted_aggregate(group: pd.DataFrame) -> pd.Series:
    """
    For individual group Execute at total power P weighted aggregation. 

    Description of programme (From readme.txt):
      NomActive      Units: kW × days at sea   (power × Days of sailing)
      NomActiveHours Units: kW × fishing hours  (power × Operational hours)
      P              Units: kW                  (Total engine power)

    Core formula (♪ The Simpson Paradox ♪):
      DAS_Weighted    = Σ(NomActive)       / Σ(P)   → Units: days (days)
      T_work_Weighted = Σ(NomActiveHours)  / Σ(P)   → Units: hours (hours)
      T_move_Weighted = (DAS_Weighted × 24) - T_work_Weighted   → Units: hours (hours)

    Physical meaning:
      DAS_Weighted  = Average number of days per year of sea departure weighted by power (The bigger the power, the higher the weight of the ship)
      T_work_Weighted = Average number of hours of operation per year weighted by power
      T_move_Weighted = Average annual pure voyage weighted by power/Number of hours flown

    parameter:
        group: pandas DataFrame — Single groupby Grouping

    Back:
        pandas Series Include weighted results
    """
    total_p = group['P'].sum()                         # Σ(P), Units: kW
    total_nom_active = group['NomActive'].sum()         # Σ(NomActive), Units: kW·days
    total_nom_hours = group['NomActiveHours'].sum()     # Σ(NomActiveHours), Units: kW·hours

    # Weighted average number of days out of the ocean — Quantities: (kW·days) / kW = days
    das_weighted = total_nom_active / total_p
    # Weighted average operational hours — Quantities: (kW·hours) / kW = hours
    t_work_weighted = total_nom_hours / total_p
    # - Its purely sailing time = 24h × Days of sailing - Operational hours
    t_move_weighted = (das_weighted * 24.0) - t_work_weighted

    return pd.Series({
        'Total_P': total_p,
        'DAS_Weighted': das_weighted,
        'T_work_Weighted': t_work_weighted,
        'T_move_Weighted': t_move_weighted,
    })


# ============================================================
# 3. Width 1: Time series statistics (Press Year, Gear, Length_Category)
# ============================================================

def compute_yearly_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Width 1 — Annual, Distribute fishing gear, weighted operating-time profiles by vessel length. 

    Group Keys: ['Gear', 'Length_Category', 'Year']

    Use groupby().apply(weighted_aggregate) Press for each group P Weighted calculations, 
    To avoid the Simpson paradox of arithmetic averages. 
    """
    print(f"\n[INFO] ===== Width 1: Time series statistics =====")

    # Version Compatibility: pandas >= 2.2 To be clearly specified include_groups=False, 
    # The old version does not support this parameter, Call Directly apply
    if _HAS_INCLUDE_GROUPS:
        result = (
            df.groupby(['Gear', 'Length_Category', 'Year'])
              .apply(weighted_aggregate, include_groups=False)
              .reset_index()
        )
    else:
        result = (
            df.groupby(['Gear', 'Length_Category', 'Year'])
              .apply(weighted_aggregate)
              .reset_index()
        )

    # Collate the order of the rows
    result = result[['Gear', 'Length_Category', 'Year',
                     'Total_P', 'DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']]

    # Press Gear, Length_Category, Year Sort
    result = result.sort_values(['Gear', 'Length_Category', 'Year']).reset_index(drop=True)

    print(f"[INFO] Time Series Results: {len(result)} Okay")
    print(f"[INFO] Year span: {int(result['Year'].min())} - {int(result['Year'].max())}")

    # Save CSV
    result.to_csv(OUTPUT_YEARLY, index=False, float_format='%.6f')
    print(f"[INFO] Exported: {OUTPUT_YEARLY}")

    return result


# ============================================================
# 4. Width 2: Cross-sectional comprehensive statistics (No years, Press Gear, Length_Category)
# ============================================================

def compute_overall_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Width 2 — The ultimate weighted average across all historical years. 

    Group Keys: ['Gear', 'Length_Category']

    attention: By Direct to Full Data (Gear, Length_Category) Grouping for weighted aggregation, 
    Equivalent to calculate a weighted average after consolidating data for all years into one pool, 
    And not a year-by-year weight (Theres a mathematical difference between the two, The former is used here). 
    """
    print(f"\n[INFO] ===== Width 2: Cross-sectional comprehensive statistics =====")

    # Version Compatibility: pandas >= 2.2 To be clearly specified include_groups=False
    if _HAS_INCLUDE_GROUPS:
        result = (
            df.groupby(['Gear', 'Length_Category'])
              .apply(weighted_aggregate, include_groups=False)
              .reset_index()
        )
    else:
        result = (
            df.groupby(['Gear', 'Length_Category'])
              .apply(weighted_aggregate)
              .reset_index()
        )

    # Collate the order of the rows
    result = result[['Gear', 'Length_Category',
                     'Total_P', 'DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']]

    # Press Gear Sort
    result = result.sort_values(['Gear', 'Length_Category']).reset_index(drop=True)

    print(f"[INFO] Cross section synthesis results: {len(result)} Okay")

    # Save CSV
    result.to_csv(OUTPUT_OVERALL, index=False, float_format='%.6f')
    print(f"[INFO] Exported: {OUTPUT_OVERALL}")

    return result


# ============================================================
# 5. Glorified Console Output
# ============================================================

def pretty_print_overall(df_overall: pd.DataFrame):
    """
    Prints cross section of the statistical results at the control table (Show only core columns). 
    """
    print(f"\n{'='*80}")
    print("  Cross-sectional comprehensive statistics — Press Gear and Length_Category Weighted time profile")
    print(f"{'='*80}")

    # Show only core indicator columns
    display_cols = ['Gear', 'Length_Category',
                    'DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']
    display_df = df_overall[display_cols].copy()

    # Formatting As 4 bits
    for col in ['DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']:
        display_df[col] = display_df[col].round(4)

    # Use pandas Internal Formatting Print
    print(display_df.to_string(index=False))

    # Extra Output Statistical Summary
    print(f"\n{'='*80}")
    print("  Press Gear Summary statistical summary")
    print(f"{'='*80}")
    for gear in TARGET_GEARS:
        subset = df_overall[df_overall['Gear'] == gear]
        if len(subset) == 0:
            print(f"\n  [{gear}] — Data does not exist")
            continue
        n_cats = len(subset)
        total_p = subset['Total_P'].sum()
        # Gear Weighted average for grade (With separate Length_Category of Total_P Aggregation for weights)
        das_gear = (subset['DAS_Weighted'] * subset['Total_P']).sum() / total_p
        t_work_gear = (subset['T_work_Weighted'] * subset['Total_P']).sum() / total_p
        t_move_gear = (subset['T_move_Weighted'] * subset['Total_P']).sum() / total_p

        print(f"\n  [{gear}]")
        print(f"    number of vessel-length categories: {n_cats}")
        print(f"    Total power (kW): {total_p:,.1f}")
        print(f"    Weighted average DAS (days):        {das_gear:.4f}")
        print(f"    Weighted average T_work (hours):   {t_work_gear:.4f}")
        print(f"    Weighted average T_move (hours):   {t_move_gear:.4f}")

    print(f"\n{'='*80}")
    print("  Completed")
    print(f"{'='*80}\n")


# ============================================================
# 6. Main entrance
# ============================================================

if __name__ == '__main__':
    # ---- Check input file ----
    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] Input file not found: {INPUT_FILE}")
        print("Please confirm the file path, Or will CSV Place in GHG_Calculation/ Under Contents. ")
        sys.exit(1)

    # ---- Data loading and cleansing ----
    df = load_and_clean_data(INPUT_FILE)

    if len(df) == 0:
        print("[ERROR] Purge data is empty, Could not continue analysis. Please check the filter conditions or data content. ")
        sys.exit(1)

    # ---- Width 1: Time series statistics ----
    df_yearly = compute_yearly_profiles(df)

    # ---- Width 2: Cross-sectional comprehensive statistics ----
    df_overall = compute_overall_profiles(df)

    # ---- Align output from the Console ----
    pretty_print_overall(df_overall)
