import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

def optimize_iattc_data(df_ll_raw, df_ps_raw):
    # 【修改点】: 删除了蓝鳍 'PBF'，新增了长鳍 'ALB' 
    # 我们只关心的目标物种 (黄鳍=YFT, 长鳍=ALB, 鲣鱼=SKJ, 大眼=BET)
    target_species = ['SKJ', 'BET', 'YFT', 'ALB'] 
    
    # ==========================================
    # 1. 处理长线数据 (LL) - 提取 mt(吨数) 和 n(数量)
    # ==========================================
    df_ll = df_ll_raw.copy()
    
    # 构建 LL 需要保留的列：基础列 + 物种吨数列 + 物种数量列
    ll_cols_to_keep = ['Year', 'Flag', 'LatC5', 'LonC5', 'Hooks'] 
    ll_cols_to_keep += [f"{s}mt" for s in target_species if f"{s}mt" in df_ll.columns]
    ll_cols_to_keep += [f"{s}n" for s in target_species if f"{s}n" in df_ll.columns]
    
    # 过滤列
    existing_ll_cols = [c for c in ll_cols_to_keep if c in df_ll.columns]
    df_ll = df_ll[existing_ll_cols]
    
    # 重命名列以对齐标准格式 (把 mt 结尾的去掉后缀以代表吨，带 n 结尾的保留 n)
    rename_ll = {'LatC5': 'Lat', 'LonC5': 'Lon', 'Hooks': 'Effort'}
    for s in target_species:
        if f"{s}mt" in df_ll.columns:
            rename_ll[f"{s}mt"] = s
    df_ll = df_ll.rename(columns=rename_ll)
    
    df_ll['GearTypeCode'] = 'LL'
    df_ll['SquareTypeCode'] = '5x5'
    df_ll['EffortType'] = 'HOOKS'  # 新增努力量类型
    
    # ==========================================
    # 2. 处理围网数据 (PS) - 只有吨数
    # ==========================================
    df_ps = df_ps_raw.copy()
    
    # 构建 PS 需要保留的列：基础列 + 直接的物种吨数列
    ps_cols_to_keep = ['Year', 'Flag', 'LatC1', 'LonC1', 'NumSets'] 
    ps_cols_to_keep += [s for s in target_species if s in df_ps.columns]
    
    # 过滤列
    existing_ps_cols = [c for c in ps_cols_to_keep if c in df_ps.columns]
    df_ps = df_ps[existing_ps_cols]
    
    # 重命名列
    df_ps = df_ps.rename(columns={'LatC1': 'Lat', 'LonC1': 'Lon', 'NumSets': 'Effort'})
    df_ps['GearTypeCode'] = 'PS'
    df_ps['SquareTypeCode'] = '1x1'
    df_ps['EffortType'] = 'SETS'  # 新增努力量类型
    
    # ==========================================
    # 3. 合并数据与国家白名单过滤
    # ==========================================
    combined_df = pd.concat([df_ll, df_ps], ignore_index=True)
    
    # 转换国家名为 ISO3 并过滤
    combined_df['Flag'] = combined_df['Flag'].apply(normalize_flag_to_iso3)
    combined_df = combined_df[combined_df['Flag'].apply(is_allowed_iso3)]
    
    # 确保目标物种的 重量(mt) 和 数量(n) 列都存在（PS没有的数量会在这里被补成0）
    target_value_cols = target_species + [f"{s}n" for s in target_species]
    for col in target_value_cols:
        if col not in combined_df.columns:
            combined_df[col] = 0.0
            
    # ==========================================
    # 4. 聚合数据 (按年份与同网格合并聚合)
    # ==========================================
    # 增加 EffortType 维度进入聚合分组
    group_cols = ['Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'EffortType', 'Lat', 'Lon']
    
    # 设置相加规则
    agg_dict = {'Effort': 'sum'}
    for col in target_value_cols:
        agg_dict[col] = 'sum'
        
    # 聚合前填充 NaN 为 0，避免相加后仍为 NaN
    cols_to_fillna = ['Effort'] + target_value_cols
    combined_df[cols_to_fillna] = combined_df[cols_to_fillna].fillna(0)
    
    # 执行聚合 (Groupby)
    aggregated_df = combined_df.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # 重新排列最终输出的列顺序 (把种类和数量放在一起展示)
    final_cols = group_cols + ['Effort']
    for s in target_species:
        final_cols.extend([s, f"{s}n"]) # 先放重量(吨)，再放数量(条)
        
    aggregated_df = aggregated_df[final_cols]
    
    return aggregated_df

# --- 运行执行部分 ---
if __name__ == "__main__":
    print("开始处理并优化 IATTC 数据...")
    
    # 1. 读取原始数据
    df_ll_raw = pd.read_csv(r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\source_data\PublicLLTunaBillfish\PublicLLTunaBillfishMt.csv')
    df_ps_raw = pd.read_csv(r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\source_data\PublicPSTuna\PublicPSTunaFlag.csv')
    
    # 2. 调用优化函数
    final_data = optimize_iattc_data(df_ll_raw, df_ps_raw)

    # 3. 保存文件
    output_filename = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\IATTC\IATTC_Grid_Catch_Effort.csv'
    final_data.to_csv(output_filename, index=False, encoding='utf-8-sig')
    print(f"\n数据已成功保存至：{output_filename}")