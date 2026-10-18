import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def optimize_iattc_data(df_ll_raw, df_ps_raw):
    # [Modify Point]: The blue fin was removed 'PBF', New fins 'ALB' 
    # We only care about target species (Yellow fin=YFT, Long fins=ALB, skipjack tuna=SKJ, Big Eye=BET)
    target_species = ['SKJ', 'BET', 'YFT', 'ALB'] 
    
    # ==========================================
    # 1. Processing long-line data (LL) - Extract mt(Tons) and n(Number)
    # ==========================================
    df_ll = df_ll_raw.copy()
    
    # Build LL Columns to Retain: Base Columns + Tungsten ton of species + Number of species
    ll_cols_to_keep = ['Year', 'Flag', 'LatC5', 'LonC5', 'Hooks'] 
    ll_cols_to_keep += [f"{s}mt" for s in target_species if f"{s}mt" in df_ll.columns]
    ll_cols_to_keep += [f"{s}n" for s in target_species if f"{s}n" in df_ll.columns]
    
    # Filter Bar
    existing_ll_cols = [c for c in ll_cols_to_keep if c in df_ll.columns]
    df_ll = df_ll[existing_ll_cols]
    
    # Rename columns to align standard formatting (Put it on mt The end of the suffix is for tons, Take it n Closing reservations n)
    rename_ll = {'LatC5': 'Lat', 'LonC5': 'Lon', 'Hooks': 'Effort'}
    for s in target_species:
        if f"{s}mt" in df_ll.columns:
            rename_ll[f"{s}mt"] = s
    df_ll = df_ll.rename(columns=rename_ll)
    
    df_ll['GearTypeCode'] = 'LL'
    df_ll['SquareTypeCode'] = '5x5'
    df_ll['EffortType'] = 'HOOKS'  # New effort type
    
    # ==========================================
    # 2. process purse-seine data (PS) - Only tons
    # ==========================================
    df_ps = df_ps_raw.copy()
    
    # Build PS Columns to Retain: Base Columns + Direct species tonn
    ps_cols_to_keep = ['Year', 'Flag', 'LatC1', 'LonC1', 'NumSets'] 
    ps_cols_to_keep += [s for s in target_species if s in df_ps.columns]
    
    # Filter Bar
    existing_ps_cols = [c for c in ps_cols_to_keep if c in df_ps.columns]
    df_ps = df_ps[existing_ps_cols]
    
    # Rename Columns
    df_ps = df_ps.rename(columns={'LatC1': 'Lat', 'LonC1': 'Lon', 'NumSets': 'Effort'})
    df_ps['GearTypeCode'] = 'PS'
    df_ps['SquareTypeCode'] = '1x1'
    df_ps['EffortType'] = 'SETS'  # New effort type
    
    # ==========================================
    # 3. Merge Data with National White List Filter
    # ==========================================
    combined_df = pd.concat([df_ll, df_ps], ignore_index=True)
    
    # Convert Country Name ISO3 & Filter
    combined_df['Flag'] = combined_df['Flag'].apply(normalize_flag_to_iso3)
    combined_df = combined_df[combined_df['Flag'].apply(is_allowed_iso3)]
    
    # Ensure that target species Weight(mt) and Number(n) Columns exist (PS Theres no amount left to be added here 0) 
    target_value_cols = target_species + [f"{s}n" for s in target_species]
    for col in target_value_cols:
        if col not in combined_df.columns:
            combined_df[col] = 0.0
            
    # ==========================================
    # 4. aggregated data (Merged with grids by year)
    # ==========================================
    # Increase EffortType dimension in the aggregation groups
    group_cols = ['Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'EffortType', 'Lat', 'Lon']
    
    # Setup Add Rule
    agg_dict = {'Effort': 'sum'}
    for col in target_value_cols:
        agg_dict[col] = 'sum'
        
    # fill before aggregation NaN is 0, Avoid add-up and remain as NaN
    cols_to_fillna = ['Effort'] + target_value_cols
    combined_df[cols_to_fillna] = combined_df[cols_to_fillna].fillna(0)
    
    # Execute Aggregation (Groupby)
    aggregated_df = combined_df.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # Reorder the order of the final output (Show the variety and the number together)
    final_cols = group_cols + ['Effort']
    for s in target_species:
        final_cols.extend([s, f"{s}n"]) # Weight first(tonnes), Number to be placed(Article)
        
    aggregated_df = aggregated_df[final_cols]
    
    return aggregated_df

# --- Run the operative part ---
if __name__ == "__main__":
    print("Start processing and optimization IATTC Data...")
    
    # 1. Reading raw data
    df_ll_raw = pd.read_csv(r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\source_data\PublicLLTunaBillfish\PublicLLTunaBillfishMt.csv')
    df_ps_raw = pd.read_csv(r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\source_data\PublicPSTuna\PublicPSTunaFlag.csv')
    
    # 2. Call Optimization Functions
    final_data = optimize_iattc_data(df_ll_raw, df_ps_raw)

    # 3. Save File
    output_filename = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\IATTC_Grid_Catch_Effort.csv'
    final_data.to_csv(output_filename, index=False, encoding='utf-8-sig')
    print(f"\n Data successfully saved to: {output_filename}")