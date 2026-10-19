from pathlib import Path
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def safe_decode_cwp_grid(df, grid_col='FISHING_GROUND_CODE'):
    """Its extremely safe CWP Grid Coordinates Decoding Function, To prevent error due to unknown code"""
    df = df.copy()
    
    # Clear String, Get rid of the possibility ".0" Suffix
    grids = df[grid_col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    # Filter strictly in line 7 Digits Legal grid code
    valid_mask = grids.str.match(r'^\d{7}$') & grids.str[0].isin(['5','6']) & grids.str[1].isin(['1','2','3','4'])
    valid_mask &= pd.to_numeric(grids.str[2:4], errors='coerce').lt(90) & pd.to_numeric(grids.str[4:7], errors='coerce').lt(180)
    
    df['SquareTypeCode'] = 'Unknown'
    df['Lat'] = np.nan
    df['Lon'] = np.nan
    
    valid_grids = grids[valid_mask]
    
    if len(valid_grids) > 0:
        size_code = valid_grids.str[0]
        quadrant = valid_grids.str[1]
        lat_val = valid_grids.str[2:4].astype(int)
        lon_val = valid_grids.str[4:7].astype(int)
        
        # Extract grid size (6: 5x5, 5: 1x1)
        sq_types = np.where(size_code == '6', '5x5', 
                   np.where(size_code == '5', '1x1', 'Unknown'))
        
        # Deciding Quantities or Negatives (1=NE: +,+ ; 2=SE: -,+ ; 3=SW: -,- ; 4=NW: +,-)
        lat_sign = np.where(quadrant.isin(['1', '4']), 1, -1)
        lon_sign = np.where(quadrant.isin(['1', '2']), 1, -1)
        
        df.loc[valid_mask, 'SquareTypeCode'] = sq_types
        df.loc[valid_mask, 'Lat'] = lat_val * lat_sign
        df.loc[valid_mask, 'Lon'] = lon_val * lon_sign
        
    return df

def process_iotc_data(file_path):
    print("Load raw data...")
    df = pd.read_csv(file_path)

    # ==========================================
    # 1. Core Filter: Fishing gear and species
    # ==========================================
    # Only keep PS(purse seine) and LL(Longline)
    df = df[df['GEAR_CODE'].isin(['LL', 'PS'])]
    
    target_species = ['BET', 'SKJ', 'YFT', 'ALB']
    # Keep all LL/PS operation effort, including records without the five target species.

    # ==========================================
    # 2. State Purge and Filtering
    # ==========================================
    print("Purge and filter the country...")
    df['Flag'] = df['FLEET_CODE'].apply(normalize_flag_to_iso3)
    df = df[df['Flag'].apply(is_allowed_iso3)]

    # ==========================================
    # 3. Space Latitude Decoding
    # ==========================================
    print("Decoding Space Latitude...")
    df = safe_decode_cwp_grid(df, 'FISHING_GROUND_CODE')
    
    # Discard the trash data that cannot be deciphered by coordinates
    df = df.dropna(subset=['Lat', 'Lon'])

    # ==========================================
    # 4. Data Perspective (flatten): Prevention EFFORT Double-counting of effort
    # ==========================================
    print("Treatment effort and capture flattening vision...")
    # Put it on“Species Code”and“Units”Sting, For example BET_MT(Tonnes of big eyes), BET_NO(Number of big-eye bars)
    df['Species_Unit'] = df['SPECIES_CODE'] + '_' + df['CATCH_UNIT_CODE']

    # Handle empty value
    df['EFFORT'] = df['EFFORT'].fillna(0)
    df['EFFORT_UNIT_CODE'] = df['EFFORT_UNIT_CODE'].fillna('UNKNOWN')
    for col in ['FISHERY_CODE','EFFORT_SCHOOL_TYPE_CODE']:
        if col not in df:
            df[col] = 'UNKNOWN'
        df[col] = df[col].fillna('UNKNOWN')

    # Definitions“A stand-alone fishing operation”Dimensions
    operation_keys = [
        'YEAR', 'MONTH_START', 'MONTH_END', 'FISHING_GROUND_CODE', 
        'SquareTypeCode', 'Lat', 'Lon', 'Flag', 'GEAR_CODE', 
        'EFFORT', 'EFFORT_UNIT_CODE', 'FISHERY_CODE', 'EFFORT_SCHOOL_TYPE_CODE'
    ]
    
    effort_rows = df.drop_duplicates(operation_keys)[operation_keys].copy()
    catch_rows = df[df['SPECIES_CODE'].isin(target_species)].copy()
    if 'FATE_TYPE_CODE' in catch_rows:
        catch_rows = catch_rows[catch_rows['FATE_TYPE_CODE'].eq('RETAINED')]
    # Additional fishery and effort-school dimensions prevent distinct strata from collapsing.
    df_pivot = pd.pivot_table(catch_rows,
                              values='CATCH', index=operation_keys,
                              columns='Species_Unit', aggfunc='sum', fill_value=0).reset_index()
    catch_columns = [c for c in df_pivot if c not in operation_keys]
    df_pivot = effort_rows.merge(df_pivot, on=operation_keys, how='left', validate='one_to_one')
    df_pivot[catch_columns] = df_pivot[catch_columns].fillna(0)

    # ==========================================
    # 5. Aggregation of Time and Space: Year of the monthly transition, Grid Merge
    # ==========================================
    print("aggregate by year and grid cell...")
    # Aggregation by: Remove the month field, Summary by these fields below
    agg_group = ['YEAR', 'Flag', 'GEAR_CODE', 'SquareTypeCode', 'EFFORT_UNIT_CODE', 'Lat', 'Lon']
    
    # Find out all the names of the target fish after the viewing
    catch_cols = [c for c in df_pivot.columns if any(c.startswith(s) for s in target_species)]
    
    # Build a polygonal dictionary (Im trying to make peace, Harvesting to sum up)
    agg_dict = {'EFFORT': 'sum'}
    for col in catch_cols:
        agg_dict[col] = 'sum'
        
    df_yearly = df_pivot.groupby(agg_group, as_index=False).agg(agg_dict)

    # ==========================================
    # 6. Final normativeization (Format before alignment)
    # ==========================================
    # Renaming of the base column
    df_yearly.rename(columns={
        'YEAR': 'Year',
        'GEAR_CODE': 'GearTypeCode',
        'EFFORT_UNIT_CODE': 'EffortType'
    }, inplace=True)

    # Purge catch columns: Weight(MT)Remove the suffix, Number(NO)Lower case n
    rename_cols = {}
    for col in catch_cols:
        if col.endswith('_MT'):
            rename_cols[col] = col.replace('_MT', '')
        elif col.endswith('_NO'):
            rename_cols[col] = col.replace('_NO', 'n')
            
    df_yearly.rename(columns=rename_cols, inplace=True)

    # Standardized presentation of listings
    base_cols = ['Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'EffortType', 'Lat', 'Lon', 'EFFORT']
    
    # Let each species weigh in (Like BET) and Quantity Columns (Like BETn) Neighborhood
    ordered_catch = []
    for s in target_species:
        if s in df_yearly.columns: ordered_catch.append(s)
        if f"{s}n" in df_yearly.columns: ordered_catch.append(f"{s}n")
        
    final_cols = base_cols + ordered_catch
    
    return df_yearly[final_cols]

# ==========================================
# Execute and save entrances
# ==========================================
if __name__ == "__main__":
    # Please fill in your place here IOTC CE The real path to the data set
    input_file = str(Path(__file__).resolve().parents[2] / 'effort_data/IOTC/source_data/IOTC-DATASETS-2026-02-23-CE-1952-2024.csv')
    output_file = str(Path(__file__).resolve().parents[2] / 'effort_data/IOTC/IOTC_Grid_Catch_Effort.csv')
    
    try:
        final_df = process_iotc_data(input_file)
        final_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        print("\n===============================")
        print(f"Processed！\n Data successfully saved to: {output_file}")
        print("===============================\n")
        print("Data foreground:")
        print(final_df.head())
    except FileNotFoundError:
        print(f"Sorry, No files found in the specified path: {input_file}")