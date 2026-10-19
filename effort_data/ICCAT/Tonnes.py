from pathlib import Path
import pandas as pd
import sys, os
import time

# Record start time to test performance
start_time = time.time()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

# --- 1. Basic Configuration ---
# Its on you Data.csv Documentation
t1nc_file_path = str(Path(__file__).resolve().parents[2] / 'effort_data/ICCAT/source_data/t1nc-20260129_ALL.xlsx')

target_species = ['SKJ', 'BET', 'ALB', 'YFT']
target_gears = ['LL', 'PS']

# --- 2. Extremely enabling reading and filtering ---
print("🚀 Start reading and optimizing processing T1NC Data...")

# Optimize 1: Read only what is needed 5 Columns, The rest 20 Row to discard, Extremely reduced memory occupancy
needed_columns = ['YearC', 'FlagName', 'GearCode', 'Species', 'Qty_t']
df = pd.read_excel(t1nc_file_path, sheet_name='Data', usecols=needed_columns)

# Optimize 2: Before the complex replacement of country names, Its done with simple species and gear"Sieve"
# Itll shrink the amount of data, Speed up subsequent string processing
df = df[df['Species'].isin(target_species) & df['GearCode'].isin(target_gears)].copy()

# --- 3. Purge and White List Validation ---
# National name map ISO3 And filter the white list
df['Flag'] = df['FlagName'].astype(str).str.strip().apply(normalize_flag_to_iso3)
df = df[df['Flag'].apply(is_allowed_iso3)]

# --- 4. Aggregation & & Columns ---
print("🔄 A multi-dimensional aggregation and perspective is in progress...")

# Press years/Country/Fishing gear/species Total tons
grouped_series = df.groupby(['YearC', 'Flag', 'GearCode', 'Species'])['Qty_t'].sum()

# Optimize 3: Use unstack Expand species index into columns, By comparison pivot_table More efficient
df_pivot = grouped_series.unstack(fill_value=0).reset_index()

# Security mechanisms: If in filtered data, One of these species has never been caught by any of these dozens of countries (The probability is extremely low) , 
# Force the creation of this column and fill it out 0, To prevent the reporting of errors
for sp in target_species:
    if sp not in df_pivot.columns:
        df_pivot[sp] = 0

# Extract and strictly sort the final column
final_df = df_pivot[['YearC', 'Flag', 'GearCode', 'ALB', 'YFT', 'BET', 'SKJ']]

# Decrease by year, National Sorting, Make the data look better
final_df = final_df.sort_values(by=['YearC', 'Flag'], ascending=[False, True]).reset_index(drop=True)

# --- 5. Results check and export ---
end_time = time.time()
print(f"✅ Were done！Time-consuming: {end_time - start_time:.2f} sec, Total rows: {len(final_df)} Okay")
print("\n🔍 Before final data 5 Row Preview: ")
print(final_df.head())

# Save final clean data
output_path = str(Path(__file__).resolve().parents[2] / 'effort_data/ICCAT/ICCAT_Annual_Catch.csv')
final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"\n📁 The official annual ton of fishing is perfectly extracted and preserved to: {output_path}")