import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def parse_coordinate(coord_str):
    """将 '05S', '130E' 转换为数字 -5.0, 130.0"""
    if pd.isna(coord_str): return np.nan
    coord_str = str(coord_str).strip()
    if not coord_str: return np.nan
    
    val = float(coord_str[:-1])
    direction = coord_str[-1].upper()
    if direction in ['S', 'W']:
        val = -val
    return val

# 目标物种
TARGET_SPECIES = ['BET', 'SKJ', 'YFT', 'ALB']

def prepare_wcpfc_base_data(ll_file, ps_file):
    """底层预处理：清洗并合并 LL 和 PS 数据，提取所需列"""
    df_l = pd.read_csv(ll_file)
    df_s = pd.read_csv(ps_file)
    
    # --- 1. 处理长线 (LL) ---
    df_ll = df_l.copy()
    df_ll.rename(columns={'YY': 'Year', 'HHOOKS': 'EffortValue'}, inplace=True)
    df_ll['GearTypeCode'] = 'LL'
    df_ll['EffortType'] = 'HHOOKS' # WCPFC的钩数是百钩(Hundreds of hooks)
    
    # 提取物种吨数
    for sp in TARGET_SPECIES:
        col_c = f"{sp}_C"
        df_ll[sp] = df_ll[col_c] if col_c in df_ll.columns else 0.0

    # --- 2. 处理围网 (PS) ---
    df_ps = df_s.copy()
    df_ps.rename(columns={'YY': 'Year'}, inplace=True)
    df_ps['GearTypeCode'] = 'PS'
    df_ps['EffortType'] = 'SETS'
    
    # WCPFC围网努力量按不同网次拆分了，我们求总网次
    set_cols = ['SETS_UNA', 'SETS_LOG', 'SETS_DFAD', 'SETS_AFAD', 'SETS_OTH']
    existing_sets = [c for c in set_cols if c in df_ps.columns]
    df_ps['EffortValue'] = df_ps[existing_sets].fillna(0).sum(axis=1)
    
    # 提取物种吨数(把各种鱼群模式捕获的相加)
    for sp in TARGET_SPECIES:
        sp_cols = [col for col in df_ps.columns if col.startswith(f"{sp}_C_")]
        df_ps[sp] = df_ps[sp_cols].fillna(0).sum(axis=1) if sp_cols else 0.0

    # --- 3. 合并与国家过滤 ---
    cols_to_keep = ['Year', 'flag_code', 'LAT5', 'LON5', 'GearTypeCode', 'EffortType', 'EffortValue'] + TARGET_SPECIES
    df_ll = df_ll[[c for c in cols_to_keep if c in df_ll.columns]]
    df_ps = df_ps[[c for c in cols_to_keep if c in df_ps.columns]]
    
    df_combined = pd.concat([df_ll, df_ps], ignore_index=True)
    df_combined['Flag'] = df_combined['flag_code'].apply(normalize_flag_to_iso3)
    df_combined = df_combined[df_combined['Flag'].apply(is_allowed_iso3)]
    
    return df_combined

# ==========================================
# Step 1: 提取网格级 Catch and Effort 数据
# ==========================================
def generate_step1_grid_ce(base_df):
    df = base_df.copy()
    
    # 转换经纬度为数字
    df['Lat'] = df['LAT5'].apply(parse_coordinate)
    df['Lon'] = df['LON5'].apply(parse_coordinate)
    df['SquareTypeCode'] = '5x5' # WCPFC 这两个公开文件默认都是 5度网格
    
    # 丢掉无法解析经纬度的脏数据
    df = df.dropna(subset=['Lat', 'Lon'])
    
    # 分组聚合：同一网格，同一年，同一个国家，同一种渔具聚合成一行
    group_cols = ['Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'Lat', 'Lon', 'EffortType']
    
    agg_dict = {'EffortValue': 'sum'}
    for sp in TARGET_SPECIES:
        if sp in df.columns: agg_dict[sp] = 'sum'
            
    df_grid = df.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # 计算当前网格的目标物种总吨数 (用于碳排的质量分配)
    existing_species = [s for s in TARGET_SPECIES if s in df_grid.columns]
    df_grid['Grid_Catch_MT'] = df_grid[existing_species].sum(axis=1)
    
    # 过滤掉完全没有捕获和努力量的数据
    df_grid = df_grid[(df_grid['EffortValue'] > 0) | (df_grid['Grid_Catch_MT'] > 0)]
    
    final_cols = group_cols + ['EffortValue'] + existing_species + ['Grid_Catch_MT']
    return df_grid[final_cols]

# ==========================================
# Step 2: 提取年度纯吨数数据 (无经纬度)
# ==========================================
def generate_step2_annual_catch(base_df):
    df = base_df.copy()
    
    # 不需要经纬度和努力量，直接按年份、国家、渔具聚合吨数
    group_cols = ['Year', 'Flag', 'GearTypeCode']
    
    agg_dict = {}
    for sp in TARGET_SPECIES:
        if sp in df.columns: agg_dict[sp] = 'sum'
            
    df_annual = df.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # 计算年度总吨数 (用于算碳排放强度基准)
    existing_species = [s for s in TARGET_SPECIES if s in df_annual.columns]
    df_annual['Total_Annual_Catch_MT'] = df_annual[existing_species].sum(axis=1)
    
    # 过滤掉吨数为 0 的行
    df_annual = df_annual[df_annual['Total_Annual_Catch_MT'] > 0]
    
    final_cols = group_cols + existing_species + ['Total_Annual_Catch_MT']
    return df_annual[final_cols]

# ==========================================
# 运行主程序
# ==========================================
if __name__ == "__main__":
    # 替换为你本地的文件路径
    ll_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\WCPFC\source_data\WCPFC_L_PUBLIC_BY_YY_FLAG_1\WCPFC_L_PUBLIC_BY_YY_FLAG.csv'
    ps_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\WCPFC\source_data\WCPFC_S_PUBLIC_BY_YY_QTR_FLAG_0\WCPFC_S_PUBLIC_BY_YY_QTR_FLAG.csv'
    
    output_step1 = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\WCPFC\WCPFC_Grid_Catch_Effort.csv'
    output_step2 = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\WCPFC\WCPFC_Annual_Catch.csv'
    
    try:
        print("开始处理 WCPFC 基础数据...")
        base_df = prepare_wcpfc_base_data(ll_file, ps_file)
        
        # 运行 Step 1
        print("正在生成 第一步：网格级 Catch and Effort 数据...")
        df_step1 = generate_step1_grid_ce(base_df)
        df_step1.to_csv(output_step1, index=False, encoding='utf-8-sig')
        print(f"--> 第一步完成！已保存至: {output_step1}")
        
        # 运行 Step 2
        print("正在生成 第二步：年度纯吨数数据...")
        df_step2 = generate_step2_annual_catch(base_df)
        df_step2.to_csv(output_step2, index=False, encoding='utf-8-sig')
        print(f"--> 第二步完成！已保存至: {output_step2}")
        
        print("\n处理全部大功告成！")
        
    except FileNotFoundError as e:
        print(f"找不到文件，请确认路径是否正确: {e}")