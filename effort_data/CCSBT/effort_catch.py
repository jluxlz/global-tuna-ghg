import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3

def process_ccsbt_data_v2(ll_file_path, ps_file_path, output_path):

    # ==========================================
    # 1. 处理延绳钓 (Longline) 数据
    # ==========================================
    print("正在处理延绳钓 (Longline) 数据...")
    ll_df = pd.read_excel(ll_file_path)
    
    ll_df = ll_df.rename(columns={
        'YEAR': 'Year',
        'COUNTRY\nCODE': 'Flag',
        'LATITUDE': 'Latitude',
        'LONGITUDE': 'Longitude',
        'NUMBER\nOF\nHOOKS': 'Effort' 
    })
    
    # 映射国家名称为 ISO3
    ll_df['Flag'] = ll_df['Flag'].apply(normalize_flag_to_iso3)
    
    # 补充齿轮类型、网格尺寸和努力量类型标识
    ll_df['Gear'] = 'LL'
    ll_df['SquareTypeCode'] = '5x5' 
    ll_df['Effort_Type'] = 'Number of Hooks' # 延绳钓(LL)的努力量类型为钓钩数
    
    # 筛选列
    ll_subset = ll_df[['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type', 'Effort']].copy()
    
    # 数据清洗并聚合
    ll_subset = ll_subset.dropna(subset=['Effort'])
    ll_subset['Effort'] = pd.to_numeric(ll_subset['Effort'], errors='coerce')
    
    ll_agg = ll_subset.groupby(
        ['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type'], 
        as_index=False
    )['Effort'].sum()
    
    # ==========================================
    # 2. 处理表层渔业 (Surface / Purse Seine) 数据
    # ==========================================
    print("正在处理表层 (Surface - PS) 数据...")
    ps_df = pd.read_excel(ps_file_path)
    
    ps_df = ps_df.rename(columns={
        'YEAR': 'Year',
        'COUNTRY\nCODE': 'Flag',
        'GEAR\nCODE': 'Gear',
        'LATITUDE': 'Latitude',
        'LONGITUDE': 'Longitude',
        'NUMBER\nOF HOURS\nSEARCHED': 'Effort'
    })
    
    # 筛选围网数据
    ps_df = ps_df[ps_df['Gear'] == 'PS'].copy()
    
    # 映射国家名称为 ISO3
    ps_df['Flag'] = ps_df['Flag'].apply(normalize_flag_to_iso3)
    
    # 补充网格尺寸和努力量类型标识
    ps_df['SquareTypeCode'] = '1x1' 
    ps_df['Effort_Type'] = 'Hours Searched' # 围网(PS)的努力量类型为搜索时间
    
    # 筛选列
    ps_subset = ps_df[['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type', 'Effort']].copy()
    
    # 数据清洗并聚合
    ps_subset = ps_subset.dropna(subset=['Effort'])
    ps_subset['Effort'] = pd.to_numeric(ps_subset['Effort'], errors='coerce')
    
    ps_agg = ps_subset.groupby(
        ['Year', 'Flag', 'Gear', 'SquareTypeCode', 'Latitude', 'Longitude', 'Effort_Type'], 
        as_index=False
    )['Effort'].sum()

    # ==========================================
    # 3. 合并数据并导出
    # ==========================================
    print("正在合并并保存结果...")
    combined_df = pd.concat([ll_agg, ps_agg], ignore_index=True)
    combined_df.to_csv(output_path, index=False)
    
    print(f"处理完成！文件已保存至: {output_path}")
    return combined_df

# 你可以通过调用下面的代码执行处理过程
ll_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\source_data\CEData_Longline.xlsx'
ps_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\source_data\CEData_Surface.xlsx'
output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\CCSBT_Grid_Catch_Effort.csv'

final_data = process_ccsbt_data_v2(ll_file, ps_file, output_file)