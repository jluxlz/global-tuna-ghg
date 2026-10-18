"""
analyze_fleet_time_profiles.py
================================
基于 PNAS 宏观数据集 (TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv)，
对全球三大核心远洋船队（围网、延绳钓、转运船/辅助船），按总功率 P 加权计算
出海天数 (DAS)、作业时间 (T_work) 和纯航行时间 (T_move)。

量纲说明 (详见 GHG_Calculation/readme.txt):
  NomActive      单位: kW × days at sea   (名义捕捞努力量, 功率×天数)
  NomActiveHours 单位: kW × fishing hours  (名义捕捞努力量, 功率×小时)
  P              单位: kW                  (总发动机功率)

  DAS_Weighted    = Σ(kW·天) / Σ(kW) = 天 (days)
  T_work_Weighted = Σ(kW·小时) / Σ(kW) = 小时 (hours)
  T_move_Weighted = 24×天 - 小时 = 小时 (hours)

核心原则：消除"辛普森悖论"，所有聚合指标均以 P (kW) 为权重进行加权计算，
而非简单的算术平均。

Author: Claude
Date: 2026-06-04
"""

import pandas as pd
import numpy as np
import os
import sys

# ============================================================
# 0. 全局配置与版本兼容
# ============================================================

# 检测 pandas 版本，兼容 include_groups 参数 (pandas >= 2.2.0 引入)
_PANDAS_VERSION = tuple(map(int, pd.__version__.split('.')[:2]))
_HAS_INCLUDE_GROUPS = _PANDAS_VERSION >= (2, 2)
print(f"[INFO] pandas 版本: {pd.__version__} "
      f"(include_groups 参数{'可用' if _HAS_INCLUDE_GROUPS else '不可用'})")

# 目标船队 (Gear 字段筛选)
TARGET_GEARS = [
    'Seine_Purse_Seine',   # 围网
    'Lines_Longlines',     # 延绳钓
    'Others_Support',      # 转运船 / 辅助船
]

# 数据过滤条件
MIN_P = 0           # 功率下限 (严格大于)
MIN_NOM_ACTIVE = 0  # 出海天数下限 (严格大于)
MIN_NOM_HOURS = 0   # 作业小时下限 (严格大于)

# 文件路径 (相对于脚本所在目录)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(
    SCRIPT_DIR,
    'TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv'
)

# 输出文件
OUTPUT_YEARLY = os.path.join(SCRIPT_DIR, 'TimeProfile_Yearly_by_Length.csv')
OUTPUT_OVERALL = os.path.join(SCRIPT_DIR, 'TimeProfile_Overall_by_Length.csv')


# ============================================================
# 1. 数据加载与清洗
# ============================================================

def load_and_clean_data(filepath: str) -> pd.DataFrame:
    """
    读取 CSV 并执行清洗：
    1. 移除全空行 (如第 2 行元数据)
    2. 过滤 P > 0, NomActive > 0, NomActiveHours > 0
    3. 仅保留目标船队 Gear 类型
    """
    print(f"[INFO] 正在读取数据: {filepath}")

    # 读取 CSV，pandas 会将 NA 字符串自动识别为 NaN
    df = pd.read_csv(filepath, na_values=['NA', 'na', 'NaN', ''])

    # 移除所有关键列均为 NaN 的行 (如 CSV 第 2 行的元数据占位行)
    key_cols = ['P', 'NomActive', 'NomActiveHours', 'Gear', 'Length_Category', 'Year']
    df = df.dropna(subset=key_cols, how='all')

    n_raw = len(df)
    print(f"[INFO] 原始有效行数: {n_raw}")

    # 确保数值列为数值类型 (防止被读成 object)
    for col in ['P', 'NomActive', 'NomActiveHours', 'NV', 'GT', 'Year']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # ---- 数据过滤 ----
    n_before = len(df)

    # 过滤 P > 0
    mask_p = df['P'] > MIN_P
    # 过滤 NomActive > 0
    mask_das = df['NomActive'] > MIN_NOM_ACTIVE
    # 过滤 NomActiveHours > 0
    mask_hours = df['NomActiveHours'] > MIN_NOM_HOURS

    df = df[mask_p & mask_das & mask_hours].copy()
    n_after_filter = len(df)
    print(f"[INFO] 过滤 P>0 & NomActive>0 & NomActiveHours>0 后: {n_after_filter} "
          f"(剔除 {n_before - n_after_filter} 行)")

    # ---- 目标船队筛选 ----
    df = df[df['Gear'].isin(TARGET_GEARS)].copy()
    n_after_gear = len(df)
    print(f"[INFO] 筛选目标船队 ({TARGET_GEARS}) 后: {n_after_gear} "
          f"(剔除 {n_after_filter - n_after_gear} 行)")

    # 检查是否有缺失的 Gear 类型
    present_gears = df['Gear'].unique()
    missing = set(TARGET_GEARS) - set(present_gears)
    if missing:
        print(f"[WARN] 以下目标船队类型在数据中不存在: {missing}")

    # 输出数据概览
    print(f"[INFO] 数据年份范围: {int(df['Year'].min())} - {int(df['Year'].max())}")
    print(f"[INFO] 实际 Gear 类型: {sorted(present_gears)}")
    print(f"[INFO] 船长类别: {sorted(df['Length_Category'].unique())}")

    return df


# ============================================================
# 2. 加权聚合核心函数
# ============================================================

def weighted_aggregate(group: pd.DataFrame) -> pd.Series:
    """
    对单个 group 执行按总功率 P 加权的聚合计算。

    量纲说明 (来自 readme.txt):
      NomActive      单位: kW × days at sea   (功率 × 出海天数)
      NomActiveHours 单位: kW × fishing hours  (功率 × 作业小时)
      P              单位: kW                  (总发动机功率)

    核心公式 (消除辛普森悖论):
      DAS_Weighted    = Σ(NomActive)       / Σ(P)   → 单位: 天 (days)
      T_work_Weighted = Σ(NomActiveHours)  / Σ(P)   → 单位: 小时 (hours)
      T_move_Weighted = (DAS_Weighted × 24) - T_work_Weighted   → 单位: 小时 (hours)

    物理含义:
      DAS_Weighted  = 按功率加权的平均年出海天数 (功率越大的船权重越高)
      T_work_Weighted = 按功率加权的平均年作业小时数
      T_move_Weighted = 按功率加权的平均年纯航行/航行小时数

    参数:
        group: pandas DataFrame — 单个 groupby 分组

    返回:
        pandas Series 包含加权计算结果
    """
    total_p = group['P'].sum()                         # Σ(P), 单位: kW
    total_nom_active = group['NomActive'].sum()         # Σ(NomActive), 单位: kW·天
    total_nom_hours = group['NomActiveHours'].sum()     # Σ(NomActiveHours), 单位: kW·小时

    # 加权平均出海天数 — 量纲: (kW·天) / kW = 天
    das_weighted = total_nom_active / total_p
    # 加权平均作业时间 — 量纲: (kW·小时) / kW = 小时
    t_work_weighted = total_nom_hours / total_p
    # 纯航行时间 = 24h × 出海天数 - 作业小时
    t_move_weighted = (das_weighted * 24.0) - t_work_weighted

    return pd.Series({
        'Total_P': total_p,
        'DAS_Weighted': das_weighted,
        'T_work_Weighted': t_work_weighted,
        'T_move_Weighted': t_move_weighted,
    })


# ============================================================
# 3. 维度 1：时间序列统计 (按 Year, Gear, Length_Category)
# ============================================================

def compute_yearly_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    维度 1 — 每年、分渔具、分船长的加权时间剖面。

    分组键: ['Gear', 'Length_Category', 'Year']

    使用 groupby().apply(weighted_aggregate) 对每个分组按 P 加权计算，
    避免算术平均导致的辛普森悖论。
    """
    print(f"\n[INFO] ===== 维度 1: 时间序列统计 =====")

    # 版本兼容: pandas >= 2.2 需显式指定 include_groups=False，
    # 旧版本不支持该参数，直接调用 apply
    if _HAS_INCLUDE_GROUPS:
        result = (
            df.groupby(['Gear', 'Length_Category', 'Year'])
              .apply(weighted_aggregate, include_groups=False)
              .reset_index()
        )
    else:
        result = (
            df.groupby(['Gear', 'Length_Category', 'Year'])
              .apply(weighted_aggregate)
              .reset_index()
        )

    # 整理列顺序
    result = result[['Gear', 'Length_Category', 'Year',
                     'Total_P', 'DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']]

    # 按 Gear, Length_Category, Year 排序
    result = result.sort_values(['Gear', 'Length_Category', 'Year']).reset_index(drop=True)

    print(f"[INFO] 时间序列结果: {len(result)} 行")
    print(f"[INFO] 年份跨度: {int(result['Year'].min())} - {int(result['Year'].max())}")

    # 保存 CSV
    result.to_csv(OUTPUT_YEARLY, index=False, float_format='%.6f')
    print(f"[INFO] 已导出: {OUTPUT_YEARLY}")

    return result


# ============================================================
# 4. 维度 2：截面综合统计 (不分年份，按 Gear, Length_Category)
# ============================================================

def compute_overall_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    维度 2 — 跨越所有历史年份的终极加权平均。

    分组键: ['Gear', 'Length_Category']

    注意: 直接对全量数据按 (Gear, Length_Category) 分组进行加权聚合，
    等效于将所有年份的数据合并为一个池子后计算加权平均，
    而非先算每年再加权平均 (两者数学上不等价，此处采用前者)。
    """
    print(f"\n[INFO] ===== 维度 2: 截面综合统计 =====")

    # 版本兼容: pandas >= 2.2 需显式指定 include_groups=False
    if _HAS_INCLUDE_GROUPS:
        result = (
            df.groupby(['Gear', 'Length_Category'])
              .apply(weighted_aggregate, include_groups=False)
              .reset_index()
        )
    else:
        result = (
            df.groupby(['Gear', 'Length_Category'])
              .apply(weighted_aggregate)
              .reset_index()
        )

    # 整理列顺序
    result = result[['Gear', 'Length_Category',
                     'Total_P', 'DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']]

    # 按 Gear 排序
    result = result.sort_values(['Gear', 'Length_Category']).reset_index(drop=True)

    print(f"[INFO] 截面综合结果: {len(result)} 行")

    # 保存 CSV
    result.to_csv(OUTPUT_OVERALL, index=False, float_format='%.6f')
    print(f"[INFO] 已导出: {OUTPUT_OVERALL}")

    return result


# ============================================================
# 5. 美化控制台输出
# ============================================================

def pretty_print_overall(df_overall: pd.DataFrame):
    """
    在控制台打印截面综合统计结果 (仅显示核心列)。
    """
    print(f"\n{'='*80}")
    print("  截面综合统计 — 按 Gear 和 Length_Category 的加权时间剖面")
    print(f"{'='*80}")

    # 仅显示核心指标列
    display_cols = ['Gear', 'Length_Category',
                    'DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']
    display_df = df_overall[display_cols].copy()

    # 格式化数值为 4 位小数
    for col in ['DAS_Weighted', 'T_work_Weighted', 'T_move_Weighted']:
        display_df[col] = display_df[col].round(4)

    # 使用 pandas 内置格式化打印
    print(display_df.to_string(index=False))

    # 额外输出统计摘要
    print(f"\n{'='*80}")
    print("  按 Gear 汇总的统计摘要")
    print(f"{'='*80}")
    for gear in TARGET_GEARS:
        subset = df_overall[df_overall['Gear'] == gear]
        if len(subset) == 0:
            print(f"\n  [{gear}] — 数据不存在")
            continue
        n_cats = len(subset)
        total_p = subset['Total_P'].sum()
        # Gear 级别的加权平均 (用各 Length_Category 的 Total_P 为权重二次聚合)
        das_gear = (subset['DAS_Weighted'] * subset['Total_P']).sum() / total_p
        t_work_gear = (subset['T_work_Weighted'] * subset['Total_P']).sum() / total_p
        t_move_gear = (subset['T_move_Weighted'] * subset['Total_P']).sum() / total_p

        print(f"\n  [{gear}]")
        print(f"    船长类别数: {n_cats}")
        print(f"    总功率 (kW): {total_p:,.1f}")
        print(f"    加权平均 DAS (天):        {das_gear:.4f}")
        print(f"    加权平均 T_work (小时):   {t_work_gear:.4f}")
        print(f"    加权平均 T_move (小时):   {t_move_gear:.4f}")

    print(f"\n{'='*80}")
    print("  完成")
    print(f"{'='*80}\n")


# ============================================================
# 6. 主入口
# ============================================================

if __name__ == '__main__':
    # ---- 检查输入文件 ----
    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] 找不到输入文件: {INPUT_FILE}")
        print("请确认文件路径，或将 CSV 放置在 GHG_Calculation/ 目录下。")
        sys.exit(1)

    # ---- 数据加载与清洗 ----
    df = load_and_clean_data(INPUT_FILE)

    if len(df) == 0:
        print("[ERROR] 清洗后数据为空，无法继续分析。请检查过滤条件或数据内容。")
        sys.exit(1)

    # ---- 维度 1: 时间序列统计 ----
    df_yearly = compute_yearly_profiles(df)

    # ---- 维度 2: 截面综合统计 ----
    df_overall = compute_overall_profiles(df)

    # ---- 控制台美化输出 ----
    pretty_print_overall(df_overall)
