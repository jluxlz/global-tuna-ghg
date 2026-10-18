import pandas as pd
import numpy as np

def extract_specific_flags_catch(file_path, output_path):
    # ==========================================
    # 1. Read data and skip before 7 Line description text and complex header
    # ==========================================
    # Multiple rows in the original table header, Its... its... its... its... its 8 Okay (Index 7) Thats the real starting point
    df = pd.read_excel(file_path, header=None, skiprows=7)
    
    # According to us, Excel Parses, Manually Named DataTeam
    # In the original table: Year, Australia(Commercial), Australia(Amateur), Japan, New Zealand(Commercial), New Zealand(Amateur), South Korea, Taiwan, Philippines, Indonesia, South Africa, European Union, Miscellaneous, Research
    df.columns = [
        'Year', 
        'AU_Com', 'AU_Ama', 
        'JP', 
        'NZ_Com', 'NZ_Ama', 
        'KR', 'TW', 'PH', 'ID', 'ZA', 'EU', 'Misc', 'Res'
    ]
    
    # Convert all columns to a numeric type, Unable to convert (Like an empty string) Will be turned into NaN
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # Purge: Remove empty rows (For example, summary notes at the end of the document) , and the year to the integer
    df = df.dropna(subset=['Year']).copy()
    df['Year'] = df['Year'].astype(int)
    
    # ==========================================
    # 2. Only the images appear in the extract 6 Country/Region, and aggregates specific columns
    # ==========================================
    df_flags = pd.DataFrame()
    df_flags['Year'] = df['Year']
    
    # Add commercial and amateur catches, Use of listings ISO3 Code
    df_flags['AUS'] = df['AU_Com'].fillna(0) + df['AU_Ama'].fillna(0)
    df_flags['NZL'] = df['NZ_Com'].fillna(0) + df['NZ_Ama'].fillna(0)

    # Extracting data from other stand-alone countries, Use of listings ISO3 Code
    df_flags['JPN'] = df['JP'].fillna(0)
    df_flags['KOR'] = df['KR'].fillna(0)
    df_flags['TWN'] = df['TW'].fillna(0)
    df_flags['ZAF'] = df['ZA'].fillna(0)
    
    # ==========================================
    # 3. Export Results
    # ==========================================
    df_flags.to_csv(output_path, index=False)
    print(f"Extract complete！Data saved to {output_path}")
    
    return df_flags

# Run code extraction of data
input_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\source_data\GlobalCatch_Flag_Gear.xlsx'
output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\CCSBT_Annual_Catch.csv'

final_flags_df = extract_specific_flags_catch(input_file, output_file)

# Print the first row preview results
print("\n Data preview after extraction:")
print(final_flags_df.head())