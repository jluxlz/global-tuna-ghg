import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def process_iotc_nominal_catch(file_path):
    print(f"正在读取数据: {file_path}")
    df = pd.read_csv(file_path)

    # ==========================================
    # 2. 核心过滤：渔具与物种
    # ==========================================
    # 只保留 长线(LL) 和 围网(PS)
    df = df[df['GEAR_CODE'].isin(['LL', 'PS'])]
    
    # 只保留 BET(大眼), SKJ(鲣鱼), YFT(黄鳍), ALB(长鳍)
    target_species = ['BET', 'SKJ', 'YFT', 'ALB']
    df = df[df['SPECIES_CODE'].isin(target_species)]

    if df.empty:
        print("警告: 过滤后没有发现符合条件的 LL/PS 和目标鱼种数据！")
        return pd.DataFrame()

    # ==========================================
    # 3. 国家翻译与过滤
    # ==========================================
    df['Flag'] = df['FLEET_CODE'].apply(normalize_flag_to_iso3)
    df = df[df['Flag'].apply(is_allowed_iso3)]

    if df.empty:
        print("警告: 白名单过滤后数据为空！")
        return pd.DataFrame()

    # ==========================================
    # 4. 汇总为年度数据 (直接对 CATCH 求和)
    # ==========================================
    df['CATCH'] = df['CATCH'].fillna(0)
    
    # 透视：按 年份、国家、渔具 聚合，把不同物种的吨数横向展开
    df_pivot = pd.pivot_table(df, 
                              values='CATCH', 
                              index=['YEAR', 'Flag', 'GEAR_CODE'], 
                              columns='SPECIES_CODE', 
                              aggfunc='sum', 
                              fill_value=0).reset_index()

    # 重命名基础列以对齐你之前的表格格式
    df_pivot.rename(columns={'YEAR': 'Year', 'GEAR_CODE': 'GearTypeCode'}, inplace=True)
    df_pivot.columns.name = None
    
    # 把存在的物种列保留下来，并确保顺序
    existing_species = [s for s in target_species if s in df_pivot.columns]
    final_cols = ['Year', 'Flag', 'GearTypeCode'] + existing_species
    
    df_final = df_pivot[final_cols].copy()
    
    # 增加年度总捕获吨数列，方便你直接做碳排放的分母
    if existing_species:
        df_final['Total_Catch_MT'] = df_final[existing_species].sum(axis=1)

    return df_final

# ==========================================
# 运行主程序
# ==========================================
if __name__ == "__main__":
    # 请把这里替换为你刚展示的那个 IOTC Nominal Catch 文件的实际路径
    input_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IOTC\source_data\IOTC-DATASETS-2026-02-23-RC-SCI-1950-2024.csv'
    output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IOTC\IOTC_Annual_Catch.csv'
    
    try:
        result_df = process_iotc_nominal_catch(input_file)
        
        if not result_df.empty:
            result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print("\n==============================")
            print("提取完成！")
            print(f"数据已成功保存至：{output_file}")
            print("==============================\n")
            print("处理后的纯吨数数据预览 (前 5 行):")
            print(result_df.head())
            
    except FileNotFoundError:
        print(f"找不到文件，请确认输入路径是否正确：{input_file}")