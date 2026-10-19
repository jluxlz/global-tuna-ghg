from pathlib import Path
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def parse_coordinate(coord_str):
    """Will '05S', '130E' Convert to Number -5.0, 130.0"""
    if pd.isna(coord_str): return np.nan
    coord_str = str(coord_str).strip()
    if not coord_str: return np.nan
    
    val = float(coord_str[:-1])
    direction = coord_str[-1].upper()
    if direction in ['S', 'W']:
        val = -val
    return val

# Target species
TARGET_SPECIES = ['BET', 'SKJ', 'YFT', 'ALB']

def prepare_wcpfc_base_data(ll_file, ps_file):
    """Bottom pre-treatment: Purge and merge LL and PS Data, Draw the required rows"""
    df_l = pd.read_csv(ll_file)
    df_s = pd.read_csv(ps_file)
    
    # --- 1. Handle Longlines (LL) ---
    df_ll = df_l.copy()
    df_ll.rename(columns={'YY': 'Year', 'HHOOKS': 'EffortValue'}, inplace=True)
    df_ll['GearTypeCode'] = 'LL'
    df_ll['EffortType'] = 'HHOOKS' # WCPFC hook counts are recorded in hundreds of hooks(Hundreds of hooks)
    
    # Tungsten of species extracted
    for sp in TARGET_SPECIES:
        col_c = f"{sp}_C"
        df_ll[sp] = df_ll[col_c] if col_c in df_ll.columns else 0.0

    # --- 2. process purse-seine records (PS) ---
    df_ps = df_s.copy()
    df_ps.rename(columns={'YY': 'Year'}, inplace=True)
    df_ps['GearTypeCode'] = 'PS'
    df_ps['EffortType'] = 'SETS'
    
    # WCPFC The net effort has been split up according to the network, Were looking for a headline
    set_cols = ['SETS_UNA', 'SETS_LOG', 'SETS_DFAD', 'SETS_AFAD', 'SETS_OTH']
    existing_sets = [c for c in set_cols if c in df_ps.columns]
    df_ps['EffortValue'] = df_ps[existing_sets].fillna(0).sum(axis=1)
    
    # Tungsten of species extracted(Im adding up the catch of the various fish species)
    for sp in TARGET_SPECIES:
        sp_cols = [col for col in df_ps.columns if col.startswith(f"{sp}_C_")]
        df_ps[sp] = df_ps[sp_cols].fillna(0).sum(axis=1) if sp_cols else 0.0

    # --- 3. Merge with National Filters ---
    cols_to_keep = ['Year', 'flag_code', 'LAT5', 'LON5', 'GearTypeCode', 'EffortType', 'EffortValue'] + TARGET_SPECIES
    df_ll = df_ll[[c for c in cols_to_keep if c in df_ll.columns]]
    df_ps = df_ps[[c for c in cols_to_keep if c in df_ps.columns]]
    
    df_combined = pd.concat([df_ll, df_ps], ignore_index=True)
    df_combined['Flag'] = df_combined['flag_code'].apply(normalize_flag_to_iso3)
    df_combined = df_combined[df_combined['Flag'].apply(is_allowed_iso3)]
    
    return df_combined

# ==========================================
# Step 1: Grid Level Catch and Effort Data
# ==========================================
def generate_step1_grid_ce(base_df):
    df = base_df.copy()
    
    # Convert longitude to number
    df['Lat'] = df['LAT5'].apply(parse_coordinate)
    df['Lon'] = df['LON5'].apply(parse_coordinate)
    df['SquareTypeCode'] = '5x5' # WCPFC Both public documents are by default 5 & Grid
    
    # Drop the dirty data from the longitude which cannot be deconstructed
    df = df.dropna(subset=['Lat', 'Lon'])
    
    # Group Aggregation: Same grid, Same year, Same country, Its the same fishing gear thats all in one row
    group_cols = ['Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'Lat', 'Lon', 'EffortType']
    
    agg_dict = {'EffortValue': 'sum'}
    for sp in TARGET_SPECIES:
        if sp in df.columns: agg_dict[sp] = 'sum'
            
    df_grid = df.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # Calculate total tonnage of target species in the current grid (Quality distribution for carbon emissions)
    existing_species = [s for s in TARGET_SPECIES if s in df_grid.columns]
    df_grid['Grid_Catch_MT'] = df_grid[existing_species].sum(axis=1)
    
    # remove records with neither catch nor effort
    df_grid = df_grid[(df_grid['EffortValue'] > 0) | (df_grid['Grid_Catch_MT'] > 0)]
    
    final_cols = group_cols + ['EffortValue'] + existing_species + ['Grid_Catch_MT']
    return df_grid[final_cols]

# ==========================================
# Step 2: Data on annual pure tonnage extracted (No longitude)
# ==========================================
def generate_step2_annual_catch(base_df):
    df = base_df.copy()
    
    # We dont need longitude and effort, Directly by year, country, Tons of fishing gear
    group_cols = ['Year', 'Flag', 'GearTypeCode']
    
    agg_dict = {}
    for sp in TARGET_SPECIES:
        if sp in df.columns: agg_dict[sp] = 'sum'
            
    df_annual = df.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # Calculated total annual tonnage (For carbon emission intensity baseline)
    existing_species = [s for s in TARGET_SPECIES if s in df_annual.columns]
    df_annual['Total_Annual_Catch_MT'] = df_annual[existing_species].sum(axis=1)
    
    # Filter Ton as 0 Yes
    df_annual = df_annual[df_annual['Total_Annual_Catch_MT'] > 0]
    
    final_cols = group_cols + existing_species + ['Total_Annual_Catch_MT']
    return df_annual[final_cols]

# ==========================================
# Run master program
# ==========================================
if __name__ == "__main__":
    # Replace with your local file path
    ll_file = str(Path(__file__).resolve().parents[2] / 'effort_data/WCPFC/source_data/WCPFC_L_PUBLIC_BY_YY_FLAG_1/WCPFC_L_PUBLIC_BY_YY_FLAG.csv')
    ps_file = str(Path(__file__).resolve().parents[2] / 'effort_data/WCPFC/source_data/WCPFC_S_PUBLIC_BY_YY_QTR_FLAG_0/WCPFC_S_PUBLIC_BY_YY_QTR_FLAG.csv')
    
    output_step1 = str(Path(__file__).resolve().parents[2] / 'effort_data/WCPFC/WCPFC_Grid_Catch_Effort.csv')
    output_step2 = str(Path(__file__).resolve().parents[2] / 'effort_data/WCPFC/WCPFC_Annual_Catch.csv')
    
    try:
        print("Start Process WCPFC Basic data...")
        base_df = prepare_wcpfc_base_data(ll_file, ps_file)
        
        # Run Step 1
        print("Generating Step one: Grid Level Catch and Effort Data...")
        df_step1 = generate_step1_grid_ce(base_df)
        df_step1.to_csv(output_step1, index=False, encoding='utf-8-sig')
        print(f"--> First step complete！Saved to: {output_step1}")
        
        # Run Step 2
        print("Generating Step two: Data on net tons for the year...")
        df_step2 = generate_step2_annual_catch(base_df)
        df_step2.to_csv(output_step2, index=False, encoding='utf-8-sig')
        print(f"--> Step two complete！Saved to: {output_step2}")
        
        print("\n Its all done！")
        
    except FileNotFoundError as e:
        print(f"File Not Found, Please confirm if the path is correct: {e}")