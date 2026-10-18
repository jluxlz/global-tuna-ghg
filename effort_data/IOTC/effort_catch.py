import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def safe_decode_cwp_grid(df, grid_col='FISHING_GROUND_CODE'):
    """极其安全的 CWP 网格坐标解码函数，防止因未知代码报错"""
    df = df.copy()
    
    # 清理字符串，去掉可能的 ".0" 后缀
    grids = df[grid_col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    # 筛选出严格符合 7位数字 的合法网格代码
    valid_mask = grids.str.match(r'^\d{7}$') & grids.str[0].isin(['5','6']) & grids.str[1].isin(['1','2','3','4'])
    valid_mask &= pd.to_numeric(grids.str[2:4], errors='coerce').lt(90) & pd.to_numeric(grids.str[4:7], errors='coerce').lt(180)
    
    df['SquareTypeCode'] = 'Unknown'
    df['Lat'] = np.nan
    df['Lon'] = np.nan
    
    valid_grids = grids[valid_mask]
    
    if len(valid_grids) > 0:
        size_code = valid_grids.str[0]
        quadrant = valid_grids.str[1]
        lat_val = valid_grids.str[2:4].astype(int)
        lon_val = valid_grids.str[4:7].astype(int)
        
        # 提取网格大小 (6: 5x5, 5: 1x1)
        sq_types = np.where(size_code == '6', '5x5', 
                   np.where(size_code == '5', '1x1', 'Unknown'))
        
        # 判断正负号 (1=NE: +,+ ; 2=SE: -,+ ; 3=SW: -,- ; 4=NW: +,-)
        lat_sign = np.where(quadrant.isin(['1', '4']), 1, -1)
        lon_sign = np.where(quadrant.isin(['1', '2']), 1, -1)
        
        df.loc[valid_mask, 'SquareTypeCode'] = sq_types
        df.loc[valid_mask, 'Lat'] = lat_val * lat_sign
        df.loc[valid_mask, 'Lon'] = lon_val * lon_sign
        
    return df

def process_iotc_data(file_path):
    print("加载原始数据...")
    df = pd.read_csv(file_path)

    # ==========================================
    # 1. 核心过滤: 渔具与物种
    # ==========================================
    # 只保留 PS(围网) 和 LL(长线)
    df = df[df['GEAR_CODE'].isin(['LL', 'PS'])]
    
    target_species = ['BET', 'SKJ', 'YFT', 'ALB']
    # Keep all LL/PS operation effort, including records without the five target species.

    # ==========================================
    # 2. 国家清洗与过滤
    # ==========================================
    print("清洗并过滤国家...")
    df['Flag'] = df['FLEET_CODE'].apply(normalize_flag_to_iso3)
    df = df[df['Flag'].apply(is_allowed_iso3)]

    # ==========================================
    # 3. 空间经纬度解码
    # ==========================================
    print("解码空间经纬度...")
    df = safe_decode_cwp_grid(df, 'FISHING_GROUND_CODE')
    
    # 丢弃那些无法解析坐标的垃圾数据
    df = df.dropna(subset=['Lat', 'Lon'])

    # ==========================================
    # 4. 数据透视 (扁平化): 防止 EFFORT 努力量重复计算
    # ==========================================
    print("处理努力量与捕获量扁平化透视...")
    # 把“物种代码”和“单位”拼接，例如 BET_MT(大眼吨数), BET_NO(大眼条数)
    df['Species_Unit'] = df['SPECIES_CODE'] + '_' + df['CATCH_UNIT_CODE']

    # 处理空值
    df['EFFORT'] = df['EFFORT'].fillna(0)
    df['EFFORT_UNIT_CODE'] = df['EFFORT_UNIT_CODE'].fillna('UNKNOWN')
    for col in ['FISHERY_CODE','EFFORT_SCHOOL_TYPE_CODE']:
        if col not in df:
            df[col] = 'UNKNOWN'
        df[col] = df[col].fillna('UNKNOWN')

    # 定义“一次独立的捕捞作业”的维度
    operation_keys = [
        'YEAR', 'MONTH_START', 'MONTH_END', 'FISHING_GROUND_CODE', 
        'SquareTypeCode', 'Lat', 'Lon', 'Flag', 'GEAR_CODE', 
        'EFFORT', 'EFFORT_UNIT_CODE', 'FISHERY_CODE', 'EFFORT_SCHOOL_TYPE_CODE'
    ]
    
    effort_rows = df.drop_duplicates(operation_keys)[operation_keys].copy()
    catch_rows = df[df['SPECIES_CODE'].isin(target_species)].copy()
    if 'FATE_TYPE_CODE' in catch_rows:
        catch_rows = catch_rows[catch_rows['FATE_TYPE_CODE'].eq('RETAINED')]
    # Additional fishery and effort-school dimensions prevent distinct strata from collapsing.
    df_pivot = pd.pivot_table(catch_rows,
                              values='CATCH', index=operation_keys,
                              columns='Species_Unit', aggfunc='sum', fill_value=0).reset_index()
    catch_columns = [c for c in df_pivot if c not in operation_keys]
    df_pivot = effort_rows.merge(df_pivot, on=operation_keys, how='left', validate='one_to_one')
    df_pivot[catch_columns] = df_pivot[catch_columns].fillna(0)

    # ==========================================
    # 5. 时空终极聚合: 月转年，网格合并
    # ==========================================
    print("执行年维度与网格维度的终极聚合...")
    # 聚合依据：去掉月份字段，按下面这些字段进行汇总
    agg_group = ['YEAR', 'Flag', 'GEAR_CODE', 'SquareTypeCode', 'EFFORT_UNIT_CODE', 'Lat', 'Lon']
    
    # 找出透视后所有属于目标鱼类的列名
    catch_cols = [c for c in df_pivot.columns if any(c.startswith(s) for s in target_species)]
    
    # 构建聚合字典 (努力量求和，捕捞量求和)
    agg_dict = {'EFFORT': 'sum'}
    for col in catch_cols:
        agg_dict[col] = 'sum'
        
    df_yearly = df_pivot.groupby(agg_group, as_index=False).agg(agg_dict)

    # ==========================================
    # 6. 最终的规范化 (对齐之前的格式)
    # ==========================================
    # 基础列重命名
    df_yearly.rename(columns={
        'YEAR': 'Year',
        'GEAR_CODE': 'GearTypeCode',
        'EFFORT_UNIT_CODE': 'EffortType'
    }, inplace=True)

    # 清洗捕获列：重量(MT)去掉后缀，数量(NO)变为小写 n
    rename_cols = {}
    for col in catch_cols:
        if col.endswith('_MT'):
            rename_cols[col] = col.replace('_MT', '')
        elif col.endswith('_NO'):
            rename_cols[col] = col.replace('_NO', 'n')
            
    df_yearly.rename(columns=rename_cols, inplace=True)

    # 按标准顺序整理列名展示
    base_cols = ['Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'EffortType', 'Lat', 'Lon', 'EFFORT']
    
    # 让每一个物种的重量列（如 BET）和数量列（如 BETn）相邻排布
    ordered_catch = []
    for s in target_species:
        if s in df_yearly.columns: ordered_catch.append(s)
        if f"{s}n" in df_yearly.columns: ordered_catch.append(f"{s}n")
        
    final_cols = base_cols + ordered_catch
    
    return df_yearly[final_cols]

# ==========================================
# 执行与保存入口
# ==========================================
if __name__ == "__main__":
    # 请在这里填入你本地 IOTC CE 数据集的真实路径
    input_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IOTC\source_data\IOTC-DATASETS-2026-02-23-CE-1952-2024.csv'
    output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IOTC\IOTC_Grid_Catch_Effort.csv'
    
    try:
        final_df = process_iotc_data(input_file)
        final_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        print("\n===============================")
        print(f"处理完成！\n数据已成功保存至：{output_file}")
        print("===============================\n")
        print("数据前瞻:")
        print(final_df.head())
    except FileNotFoundError:
        print(f"抱歉，没有在指定路径找到文件：{input_file}")