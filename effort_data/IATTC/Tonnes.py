from pathlib import Path
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def extract_catch_data(file_path):
    # ==========================================
    # 1. Loading data
    # ==========================================
    df = pd.read_csv(file_path)
    
    # ==========================================
    # 2. Data Filter (Filter gear LL and PS, Target species)
    # ==========================================
    # [Modify Point]: Its been deleted 'PBF' (Blue fin), Im in 'ALB' (Long fins)
    target_species = ['SKJ', 'BET', 'YFT', 'ALB']
    
    # Only keep LL (Longline) and PS (purse seine)
    df = df[df['ArteGear'].isin(['LL', 'PS'])]
    
    # Only four target tunas are retained
    df = df[df['EspeciesSpecies'].isin(target_species)]
    
    # ==========================================
    # 3. Convert and Filter Countries (Flag)
    # ==========================================
    df['Flag'] = df['BanderaFlag'].apply(normalize_flag_to_iso3)
    df = df[df['Flag'].apply(is_allowed_iso3)]
    
    # ==========================================
    # 4. View Table Aggregation (Tons of species converted to listing)
    # ==========================================
    df_pivot = pd.pivot_table(df,
                              values='t', # This is the ton numeral in the original file
                              index=['AnoYear', 'Flag', 'ArteGear'],
                              columns='EspeciesSpecies',
                              aggfunc='sum',
                              fill_value=0).reset_index()

    # Organization of listings and sequencing
    df_pivot.rename(columns={'AnoYear': 'Year', 'ArteGear': 'Gear'}, inplace=True)
    df_pivot.columns.name = None # Remove the top names from the lens

    # Make sure the columns are sorted according to norms
    species_cols = [s for s in target_species if s in df_pivot.columns]
    df_final = df_pivot[['Year', 'Flag', 'Gear'] + species_cols]
    
    return df_final

if __name__ == "__main__":
    # Please use your local file path to modify it
    input_file = str(Path(__file__).resolve().parents[2] / 'effort_data/IATTC/source_data/CatchByFlagGear1918-2024.csv')
    output_file = str(Path(__file__).resolve().parents[2] / 'effort_data/IATTC/IATTC_Annual_Catch.csv')
    
    print("Processing of historical total ton data...")
    result_df = extract_catch_data(input_file)
    
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"Processed！\n Data successfully saved to: {output_file}")
    
    print("\n Data Preview (Front 5 Okay):")
    print(result_df.head())