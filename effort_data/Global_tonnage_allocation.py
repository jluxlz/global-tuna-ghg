import pandas as pd
import numpy as np
import sys, os
from pathlib import Path

# Use a path to the directory where the script is
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from flag_utils import normalize_flag_to_iso3

def ensure_flag_iso3(df):
    """common Flag Column: Processing 'Country'→'Flag' Rename + ISO3 standardisation"""
    if 'Flag' not in df.columns:
        if 'Country' in df.columns:
            df.rename(columns={'Country': 'Flag'}, inplace=True)
        elif 'country' in df.columns:
            df.rename(columns={'country': 'Flag'}, inplace=True)
    if 'Flag' in df.columns:
        df['Flag'] = df['Flag'].astype(str).str.strip().apply(normalize_flag_to_iso3)
        df = df[df['Flag'] != ''].copy()
    return df

def build_allocation(input_dir=None, output_dir=None):
    input_dir = Path(input_dir or SCRIPT_DIR)
    output_dir = Path(output_dir or SCRIPT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    print("Start Grid Catch Allocation Data processing...")

    # ==========================================
    # 1. Processing CCSBT Customise Data (ISO3 common)
    # ==========================================

    # --- read and clean albacore longline records (LL) ---
    ll_df = pd.read_excel(os.path.join(SCRIPT_DIR, 'CCSBT', 'source_data', 'CEData_Longline.xlsx'))
    ll_df = ll_df.rename(columns={
        'YEAR': 'Year', 'COUNTRY\nCODE': 'Flag', 'LATITUDE': 'Lat', 'LONGITUDE': 'Lon',
        'NUMBER\nOF\nHOOKS': 'EffortValue', 'NUMBER\nOF SBT\nRETAINED': 'Retained'
    })
    ll_df['Gear'] = 'LL'
    ll_df['SquareTypeCode'] = '5x5'
    ll_df['EffortType'] = 'Number of Hooks'
    # [Optimize 1]No more cutting Retained <= 0 Yes, Fill empty values only as 0, Make sure Effort Keeped！
    ll_df['Retained'] = pd.to_numeric(ll_df['Retained'], errors='coerce').fillna(0)

    # --- read and clean surface purse-seine records (PS) ---
    ps_df = pd.read_excel(os.path.join(SCRIPT_DIR, 'CCSBT', 'source_data', 'CEData_Surface.xlsx'))
    ps_df = ps_df.rename(columns={
        'YEAR': 'Year', 'COUNTRY\nCODE': 'Flag', 'GEAR\nCODE': 'Gear',
        'LATITUDE': 'Lat', 'LONGITUDE': 'Lon',
        'NUMBER\nOF HOURS\nSEARCHED': 'EffortValue', 'WEIGHT (Kg)\nOF SBT\nRETAINED': 'Retained'
    })
    ps_df = ps_df[ps_df['Gear'] == 'PS'].copy()
    ps_df['SquareTypeCode'] = '1x1'
    ps_df['EffortType'] = 'Hours Searched'
    # [Optimize 1]Same thing, purse seine retains grids without output
    ps_df['Retained'] = pd.to_numeric(ps_df['Retained'], errors='coerce').fillna(0)

    # Merge and Convey
    ccsbt_ce = pd.concat([ll_df, ps_df], ignore_index=True)
    ccsbt_ce['Flag'] = ccsbt_ce['Flag'].apply(normalize_flag_to_iso3)
    ccsbt_ce['EffortValue'] = pd.to_numeric(ccsbt_ce['EffortValue'], errors='coerce')
    # Just cut out the whole thing Effort or missing invalid dirty data at longitude
    invalid_ce = ccsbt_ce[['EffortValue','Lat','Lon']].isna().any(axis=1) | ~ccsbt_ce['Lat'].between(-90,90) | ~ccsbt_ce['Lon'].between(-180,180)
    ccsbt_ce[invalid_ce].to_csv(output_dir / 'CCSBT_Invalid_Grid_Rows.csv', index=False, encoding='utf-8-sig')
    ccsbt_ce = ccsbt_ce[~invalid_ce].copy()
    ccsbt_ce_agg = ccsbt_ce.groupby(['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Lat', 'Lon', 'EffortType'], as_index=False)[['EffortValue', 'Retained']].sum()

    # Merge CatchByYMGOLoLa Total ton of grids
    catch_grid = pd.read_excel(os.path.join(SCRIPT_DIR, 'CCSBT', 'source_data', 'CatchByYMGOLoLa.xlsx'), skiprows=6)
    catch_grid.columns = catch_grid.columns.str.replace('\n', ' ').str.strip()
    catch_grid = catch_grid.rename(columns={'Calendar Year': 'Year', 'Latitude': 'Lat', 'Longitude': 'Lon'})
    catch_grid_agg = catch_grid.groupby(['Year', 'Gear', 'Lat', 'Lon'], as_index=False)['Tonnes'].sum()

    # [Key point]Use left join (Left Connection) . If theres a grid that only tries to measure, But catch_grid No output, The grid remains. 
    ccsbt_merged = pd.merge(ccsbt_ce_agg, catch_grid_agg, on=['Year', 'Gear', 'Lat', 'Lon'], how='left')
    ccsbt_merged['Tonnes'] = ccsbt_merged['Tonnes'].fillna(0)

    # Calculating grid totals Retained, Tons to be used for pro rata fraction
    grid_retained_totals = ccsbt_merged.groupby(['Year', 'Gear', 'Lat', 'Lon'], as_index=False)['Retained'].sum().rename(columns={'Retained': 'TotalGridRetained'})
    ccsbt_merged = pd.merge(ccsbt_merged, grid_retained_totals, on=['Year', 'Gear', 'Lat', 'Lon'])

    # If that is the case Retained is 0, Score 0 tonnes; If its worth it, proportionally divided
    ccsbt_merged.loc[(ccsbt_merged['TotalGridRetained'] <= 0) & (ccsbt_merged['Tonnes'] > 0)].to_csv(
        output_dir / 'CCSBT_Unallocated_Grid_Catch.csv', index=False, encoding='utf-8-sig')
    orphan = catch_grid_agg.merge(ccsbt_ce_agg[['Year','Gear','Lat','Lon']].drop_duplicates(),
                                  on=['Year','Gear','Lat','Lon'],how='left',indicator=True)
    orphan.loc[orphan['_merge'].eq('left_only')].to_csv(output_dir / 'CCSBT_Unmatched_Catch_Grids.csv',index=False,encoding='utf-8-sig')
    ccsbt_merged['SBT_Tonnes'] = np.where(
        ccsbt_merged['TotalGridRetained'] > 0,
        ccsbt_merged['Tonnes'] * (ccsbt_merged['Retained'] / ccsbt_merged['TotalGridRetained']),
        0.0
    )

    ccsbt_final = ccsbt_merged[['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Lat', 'Lon', 'EffortType', 'EffortValue', 'SBT_Tonnes']].copy()
    ccsbt_final['Organization'] = 'CCSBT'
    for col in ['SKJ_Tonnes', 'BET_Tonnes', 'YFT_Tonnes']: ccsbt_final[col] = 0.0


    # ==========================================
    # 2. Processing global data (Not CCSBT Other organizations)
    # ==========================================
    df_ann = pd.read_csv(input_dir / 'Global_Annual_Catch.csv')
    df_grid = pd.read_csv(input_dir / 'Global_Grid_Catch_Effort.csv')

    # ISO3 Flag standardisation
    df_ann = ensure_flag_iso3(df_ann)
    df_grid = ensure_flag_iso3(df_grid)

    df_ann = df_ann[df_ann['Organization'] != 'CCSBT'].copy()
    df_ann = df_ann.groupby(['Organization','Year','Flag','GearTypeCode'], as_index=False)[['SKJ','BET','YFT','SBT','ALB']].sum()
    df_grid = df_grid[df_grid['Organization'] != 'CCSBT'].copy()

    df_grid['EffortValue'] = pd.to_numeric(df_grid['EffortValue'], errors='coerce')
    invalid = df_grid[['EffortValue','Lat','Lon']].isna().any(axis=1) | ~df_grid['Lat'].between(-90,90) | ~df_grid['Lon'].between(-180,180)
    df_grid[invalid].to_csv(output_dir / 'Allocation_Invalid_Grid_Rows.csv',index=False,encoding='utf-8-sig')
    df_grid = df_grid[~invalid].copy()

    # Unit-homogeneous allocation per RFMO x year x flag x gear x species.
    # Prefer reported tonnes. If the group has only fish counts, use count shares;
    # never add counts to tonnes or invent fish mass. Missing reference coverage is reported.
    reference_qc = []
    keys = ['Organization', 'Year', 'Flag', 'GearTypeCode']
    for sp in ['SKJ', 'BET', 'YFT', 'SBT', 'ALB']:
        for col in [sp, sp+'n']:
            if col not in df_grid:
                df_grid[col] = 0.0
            df_grid[col] = pd.to_numeric(df_grid[col], errors='coerce').fillna(0.0)
            if (df_grid[col] < 0).any():
                raise ValueError(f'Negative catch reference: {col}')
        totals_w = df_grid.groupby(keys)[sp].transform('sum')
        df_grid[f'Ref_{sp}'] = df_grid[sp].where(totals_w > 0, df_grid[sp+'n'])
        for key, group in df_grid.groupby(keys, sort=False):
            wt = group[sp].sum()
            ct = group[sp+'n'].sum()
            reference_qc.append(dict(zip(keys, key), Species=sp,
                Reference_Unit='tonnes' if wt>0 else 'fish_count' if ct>0 else 'none',
                Weight_tonnes=wt, Fish_Count=ct,
                Count_Only_Rows_Excluded=int(((group[sp]==0)&(group[sp+'n']>0)).sum()) if wt>0 else 0))
    pd.DataFrame(reference_qc).to_csv(output_dir / 'Allocation_Reference_QC.csv', index=False, encoding='utf-8-sig')

    # Aggregation of grid data
    grid_agg = df_grid.groupby(
        ['Organization', 'Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'Lat', 'Lon', 'EffortType'],
        as_index=False
    ).agg({
        'EffortValue': 'sum',
        'Ref_SKJ': 'sum', 'Ref_BET': 'sum', 'Ref_YFT': 'sum', 'Ref_SBT': 'sum', 'Ref_ALB': 'sum'
    })

    # Calculated vertically: Some countrys gear in one year“Overall global reference outputs”
    totals = grid_agg.groupby(['Organization', 'Year', 'Flag', 'GearTypeCode'], as_index=False).agg({
        'Ref_SKJ': 'sum', 'Ref_BET': 'sum', 'Ref_YFT': 'sum', 'Ref_SBT': 'sum', 'Ref_ALB': 'sum'
    }).rename(columns={
        'Ref_SKJ': 'Tot_SKJ', 'Ref_BET': 'Tot_BET', 'Ref_YFT': 'Tot_YFT', 'Ref_SBT': 'Tot_SBT', 'Ref_ALB': 'Tot_ALB'
    })

    # Consolidated summary tables and nominal production tables (df_ann)
    global_merged = pd.merge(grid_agg, totals, on=['Organization', 'Year', 'Flag', 'GearTypeCode'], how='left')
    global_merged = pd.merge(global_merged, df_ann, on=['Organization', 'Year', 'Flag', 'GearTypeCode'], how='left', validate='many_to_one')

    for sp in ['SKJ', 'BET', 'YFT', 'SBT', 'ALB']:
        global_merged[sp] = global_merged[sp].fillna(0.0)
    allocated = global_merged.groupby(keys)[['SKJ','BET','YFT','SBT','ALB']].first()
    coverage = df_ann.set_index(keys)[['SKJ','BET','YFT','SBT','ALB']].join(
        totals.set_index(keys)[['Tot_SKJ','Tot_BET','Tot_YFT','Tot_SBT','Tot_ALB']])
    for sp in ['SKJ','BET','YFT','SBT','ALB']:
        coverage[sp+'_Unallocated_Tonnes'] = coverage[sp].where(coverage['Tot_'+sp].fillna(0)<=0,0)
    coverage.reset_index().to_csv(output_dir / 'Allocation_Coverage_QC.csv', index=False, encoding='utf-8-sig')

    # [Optimize 2 Implementation]In proportion to the real output of the species in different grids (No, its not Effort) , Number of nominal tons of the species in nominal terms
    # If theres a grid Ref = 0, Then well get a cut Tonnes is 0, But its EffortValue Still complete！
    global_merged['SKJ_Tonnes'] = np.where(global_merged['Tot_SKJ'] > 0, global_merged['SKJ'] * (global_merged['Ref_SKJ'] / global_merged['Tot_SKJ']), 0.0)
    global_merged['BET_Tonnes'] = np.where(global_merged['Tot_BET'] > 0, global_merged['BET'] * (global_merged['Ref_BET'] / global_merged['Tot_BET']), 0.0)
    global_merged['YFT_Tonnes'] = np.where(global_merged['Tot_YFT'] > 0, global_merged['YFT'] * (global_merged['Ref_YFT'] / global_merged['Tot_YFT']), 0.0)
    global_merged['SBT_Tonnes'] = np.where(global_merged['Tot_SBT'] > 0, global_merged['SBT'] * (global_merged['Ref_SBT'] / global_merged['Tot_SBT']), 0.0)
    global_merged['ALB_Tonnes'] = np.where(global_merged['Tot_ALB'] > 0, global_merged['ALB'] * (global_merged['Ref_ALB'] / global_merged['Tot_ALB']), 0.0)

    global_final = global_merged.rename(columns={'GearTypeCode': 'Gear'})
    global_final = global_final[['Organization', 'Year', 'Flag', 'Gear', 'SquareTypeCode', 'Lat', 'Lon', 'EffortType', 'EffortValue', 'SKJ_Tonnes', 'BET_Tonnes', 'YFT_Tonnes', 'SBT_Tonnes', 'ALB_Tonnes']]

    # ==========================================
    # 3. Final summary and export
    # ==========================================
    master_df = pd.concat([ccsbt_final, global_final], ignore_index=True)
    master_df['ALB_Tonnes'] = master_df['ALB_Tonnes'].fillna(0)
    key = ['Year','Flag','Gear','SquareTypeCode','Lat','Lon','EffortType','Organization']
    if master_df.duplicated(key).any():
        raise ValueError('Duplicate catch-record keys in allocation output')
    num_cols = ['EffortValue','SBT_Tonnes','SKJ_Tonnes','BET_Tonnes','YFT_Tonnes','ALB_Tonnes']
    if not np.isfinite(master_df[num_cols].to_numpy()).all() or (master_df[num_cols] < 0).any().any():
        raise ValueError('Invalid or negative allocated catch / effort')

    master_df.to_csv(output_dir / 'Grid_Catch_Allocation.csv', index=False, encoding='utf-8-sig')
    print(f"Were done！Grid_Catch_Allocation.csv Generated, Total {len(master_df)} Okay. ")
    return master_df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=SCRIPT_DIR)
    parser.add_argument("--output-dir", default=SCRIPT_DIR)
    args = parser.parse_args()
    build_allocation(args.input_dir, args.output_dir)
