import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def process_iotc_nominal_catch(file_path):
    print(f"Reading data: {file_path}")
    df = pd.read_csv(file_path)

    # ==========================================
    # 2. Core Filter: Fishing gear and species
    # ==========================================
    # Only keep Longline(LL) and purse seine(PS)
    df = df[df['GEAR_CODE'].isin(['LL', 'PS'])]
    
    # Only keep BET(Big Eye), SKJ(skipjack tuna), YFT(Yellow fin), ALB(Long fins)
    target_species = ['BET', 'SKJ', 'YFT', 'ALB']
    df = df[df['SPECIES_CODE'].isin(target_species)]

    if df.empty:
        print("This function is EXPERIMENTAL: I dont see any eligible ones after filtering LL/PS Data on target species！")
        return pd.DataFrame()

    # ==========================================
    # 3. National Translation and Filtering
    # ==========================================
    df['Flag'] = df['FLEET_CODE'].apply(normalize_flag_to_iso3)
    df = df[df['Flag'].apply(is_allowed_iso3)]

    if df.empty:
        print("This function is EXPERIMENTAL: White List filtered with empty data！")
        return pd.DataFrame()

    # ==========================================
    # 4. Summary to annual data (Straight ahead CATCH Peace)
    # ==========================================
    df['CATCH'] = df['CATCH'].fillna(0)
    
    # Perspective: Press Year, country, Fishing gear Aggregation, Spread the tons of different species horizontally
    df_pivot = pd.pivot_table(df, 
                              values='CATCH', 
                              index=['YEAR', 'Flag', 'GEAR_CODE'], 
                              columns='SPECIES_CODE', 
                              aggfunc='sum', 
                              fill_value=0).reset_index()

    # Rename the base column to align the table format before you
    df_pivot.rename(columns={'YEAR': 'Year', 'GEAR_CODE': 'GearTypeCode'}, inplace=True)
    df_pivot.columns.name = None
    
    # Keep the list of species that exist, And make sure the order is done
    existing_species = [s for s in target_species if s in df_pivot.columns]
    final_cols = ['Year', 'Flag', 'GearTypeCode'] + existing_species
    
    df_final = df_pivot[final_cols].copy()
    
    # Add total annual catches by tonnes, Its easy for you to be the denominator of carbon emissions
    if existing_species:
        df_final['Total_Catch_MT'] = df_final[existing_species].sum(axis=1)

    return df_final

# ==========================================
# Run master program
# ==========================================
if __name__ == "__main__":
    # Please replace this place with the one you just showed IOTC Nominal Catch Actual path of the file
    input_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IOTC\source_data\IOTC-DATASETS-2026-02-23-RC-SCI-1950-2024.csv'
    output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IOTC\IOTC_Annual_Catch.csv'
    
    try:
        result_df = process_iotc_nominal_catch(input_file)
        
        if not result_df.empty:
            result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print("\n==============================")
            print("Extract complete！")
            print(f"Data successfully saved to: {output_file}")
            print("==============================\n")
            print("Preview of processed data on pure tons (Front 5 Okay):")
            print(result_df.head())
            
    except FileNotFoundError:
        print(f"File Not Found, Make sure the input path is correct: {input_file}")