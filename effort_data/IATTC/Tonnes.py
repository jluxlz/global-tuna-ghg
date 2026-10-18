import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def extract_catch_data(file_path):
    # ==========================================
    # 1. 加载数据
    # ==========================================
    df = pd.read_csv(file_path)
    
    # ==========================================
    # 2. 数据过滤 (过滤渔具 LL 和 PS，目标物种)
    # ==========================================
    # 【修改点】：删除了 'PBF' (蓝鳍)，加入了 'ALB' (长鳍)
    target_species = ['SKJ', 'BET', 'YFT', 'ALB']
    
    # 仅保留 LL (长线) 和 PS (围网)
    df = df[df['ArteGear'].isin(['LL', 'PS'])]
    
    # 仅保留四种目标金枪鱼
    df = df[df['EspeciesSpecies'].isin(target_species)]
    
    # ==========================================
    # 3. 转换并过滤国家 (Flag)
    # ==========================================
    df['Flag'] = df['BanderaFlag'].apply(normalize_flag_to_iso3)
    df = df[df['Flag'].apply(is_allowed_iso3)]
    
    # ==========================================
    # 4. 透视表聚合 (将物种转为列名展示吨数)
    # ==========================================
    df_pivot = pd.pivot_table(df,
                              values='t', # 这是原始文件里的吨数字段
                              index=['AnoYear', 'Flag', 'ArteGear'],
                              columns='EspeciesSpecies',
                              aggfunc='sum',
                              fill_value=0).reset_index()

    # 整理列名和顺序
    df_pivot.rename(columns={'AnoYear': 'Year', 'ArteGear': 'Gear'}, inplace=True)
    df_pivot.columns.name = None # 去掉透视产生的层次名

    # 确保列按规范排序
    species_cols = [s for s in target_species if s in df_pivot.columns]
    df_final = df_pivot[['Year', 'Flag', 'Gear'] + species_cols]
    
    return df_final

if __name__ == "__main__":
    # 请根据你本地的文件路径进行修改
    input_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\source_data\CatchByFlagGear1918-2024.csv'
    output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\IATTC_Annual_Catch.csv'
    
    print("正在处理历史捕捞总吨数数据...")
    result_df = extract_catch_data(input_file)
    
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"处理完成！\n数据已成功保存至：{output_file}")
    
    print("\n数据预览 (前5行):")
    print(result_df.head())