import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3

def process_ccsbt_data_v2(ll_file_path, ps_file_path, output_path):

    # ==========================================
    # 1. process longline records (Longline) Data
    # ==========================================
    print("processing longline records (Longline) Data...")
    ll_df = pd.read_excel(ll_file_path)
    
    ll_df = ll_df.rename(columns={
        'YEAR': 'Year',
        'COUNTRY\nCODE': 'Flag',
        'LATITUDE': 'Latitude',
        'LONGITUDE': 'Longitude',
        'NUMBER\nOF\nHOOKS': 'Effort' 
    })
    
    # Map Country Name ISO3
    ll_df['Flag'] = ll_df['Flag'].apply(normalize_flag_to_iso3)
    
    # Supplementary gear type, Grid size and type of effort
    ll_df['Gear'] = 'LL'
    ll_df['SquareTypeCode'] = '5x5' 
    ll_df['Effort_Type'] = 'Number of Hooks' # longline(LL)The number of hooks is the type of effort
    
    # Filter Rows
    ll_subset = ll_df[['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type', 'Effort']].copy()
    
    # Data cleansing and aggregation
    ll_subset = ll_subset.dropna(subset=['Effort'])
    ll_subset['Effort'] = pd.to_numeric(ll_subset['Effort'], errors='coerce')
    
    ll_agg = ll_subset.groupby(
        ['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type'], 
        as_index=False
    )['Effort'].sum()
    
    # ==========================================
    # 2. Treatment of surface fisheries (Surface / Purse Seine) Data
    # ==========================================
    print("Processing surface layer (Surface - PS) Data...")
    ps_df = pd.read_excel(ps_file_path)
    
    ps_df = ps_df.rename(columns={
        'YEAR': 'Year',
        'COUNTRY\nCODE': 'Flag',
        'GEAR\nCODE': 'Gear',
        'LATITUDE': 'Latitude',
        'LONGITUDE': 'Longitude',
        'NUMBER\nOF HOURS\nSEARCHED': 'Effort'
    })
    
    # filter purse-seine data
    ps_df = ps_df[ps_df['Gear'] == 'PS'].copy()
    
    # Map Country Name ISO3
    ps_df['Flag'] = ps_df['Flag'].apply(normalize_flag_to_iso3)
    
    # Complementary grid size and type of effort
    ps_df['SquareTypeCode'] = '1x1' 
    ps_df['Effort_Type'] = 'Hours Searched' # purse seine(PS)The number of effort is the search time
    
    # Filter Rows
    ps_subset = ps_df[['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type', 'Effort']].copy()
    
    # Data cleansing and aggregation
    ps_subset = ps_subset.dropna(subset=['Effort'])
    ps_subset['Effort'] = pd.to_numeric(ps_subset['Effort'], errors='coerce')
    
    ps_agg = ps_subset.groupby(
        ['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type'], 
        as_index=False
    )['Effort'].sum()

    # ==========================================
    # 3. Merge data and export
    # ==========================================
    print("Merge and save results...")
    combined_df = pd.concat([ll_agg, ps_agg], ignore_index=True)
    combined_df.to_csv(output_path, index=False)
    
    print(f"Processed！File saved to: {output_path}")
    return combined_df

# You can execute the process by calling the code below
ll_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\source_data\CEData_Longline.xlsx'
ps_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\source_data\CEData_Surface.xlsx'
output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\CCSBT_Grid_Catch_Effort.csv'

final_data = process_ccsbt_data_v2(ll_file, ps_file, output_file)