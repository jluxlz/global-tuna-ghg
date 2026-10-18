import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')

# ============================================================
# Step 1 & 2: 历史马力演进查询表 -- 数据预处理与查询函数
# 基于 PNAS (Rousseau et al., 2019) 真实历史船队物理参数
# ============================================================

# ---- Flag 说明 ----
# vessel 数据中的 Flag 现在统一为 ISO3 代码 (flag_utils.py)
# 无需转换 — 直接作为查询键使用

# ---- Gear 映射 ----
# 将 vessel 数据中的 VesselType (LL, PS, TS) 映射到 CSV 中的 Gear 类别
GEAR_MAPPING = {
    'LL': 'Lines_Longlines',
    'PS': 'Seine_Purse_Seine',
    'TS': 'Trawl_Midwater_or_Unsp',
}

# ---- Length(m) -> CSV Length_Category 映射 ----
def map_length_to_csv_category(length_m):
    """将数值 Length(m) 映射到 CSV 中的 Length_Category 分箱"""
    if length_m < 6:
        return '6-12m'   # 兜底：极小的船归入最小档
    elif length_m < 12:
        return '6-12m'
    elif length_m < 24:
        return '12-24m'
    elif length_m < 50:
        return '24-50m'
    else:
        return 'Over 50m'


# ============================================================
# 主预处理函数
# ============================================================

def build_power_discount_lookup(csv_path, baseline_year=2015, verbose=True):
    """
    构建"历史马力演进查询表"。

    参数
    ----------
    csv_path : str
        PNAS 历史船队数据 CSV 的路径。
    baseline_year : int
        基准年份 (默认 2015)，用于提取现代基准功率。
    verbose : bool
        是否打印预处理日志。

    返回
    -------
    lookup : dict
        主查询字典，键为 (Country_ISO3, Gear_CSV, Length_Category, Year)，
        值为 Power_Discount_Factor。
    fallback_global : dict
        全球平均兜底字典，键为 (Gear_CSV, Length_Category, Year)。
    fallback_group_nearest : dict
        按组最近年份兜底字典，键为 (Country_ISO3, Gear_CSV, Length_Category)，
        值为 (years_array, factors_array) 元组，用于线性插值或最近邻。
    fallback_global_nearest : dict
        全球维度的最近年份兜底，键为 (Gear_CSV, Length_Category)。
    """
    if verbose:
        print(f"[预处理] 正在读取 PNAS 历史船队数据: {csv_path} ...")

    df_raw = pd.read_csv(csv_path, skiprows=[1])

    # ---- 清理 ----
    for col in ['NV', 'P', 'Year']:
        df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')
    df_raw['Country'] = df_raw['Country'].astype(str).str.strip()
    df_raw['Gear'] = df_raw['Gear'].astype(str).str.strip()
    df_raw['Length_Category'] = df_raw['Length_Category'].astype(str).str.strip()

    # 剔除无效行 (NV <= 0 或 P <= 0)
    df = df_raw[(df_raw['NV'] > 0) & (df_raw['P'] > 0)].copy()

    # ---- 计算单船平均真实功率 ----
    df['Avg_Power'] = df['P'] / df['NV']

    if verbose:
        print(f"   有效数据行数: {len(df):,}")
        print(f"   年份跨度: {int(df['Year'].min())} - {int(df['Year'].max())}")
        print(f"   唯一国家数: {df['Country'].nunique()}")
        print(f"   唯一 Gear 类型: {df['Gear'].nunique()}")
        print(f"   唯一 Length_Category: {sorted(df['Length_Category'].unique())}")

    # ---- 提取基准年份的 Base_Power ----
    # 如果 baseline_year 不存在，则取该组最近的有效年份
    base_data = df[df['Year'] == baseline_year].copy()

    # 对于 baseline_year 缺失的组，向前/向后搜索最近年份
    all_groups = df[['Country', 'Gear', 'Length_Category']].drop_duplicates()
    base_power_map = {}

    for _, row in all_groups.iterrows():
        c, g, lc = row['Country'], row['Gear'], row['Length_Category']
        subset = base_data[(base_data['Country'] == c) &
                           (base_data['Gear'] == g) &
                           (base_data['Length_Category'] == lc)]
        if len(subset) > 0:
            # 取该组在 baseline_year 的所有记录加权平均
            base_power_map[(c, g, lc)] = (subset['P'].sum() / subset['NV'].sum())
        else:
            # 寻找最近有效年份
            hist = df[(df['Country'] == c) &
                      (df['Gear'] == g) &
                      (df['Length_Category'] == lc)]
            if len(hist) > 0:
                # 找最接近 baseline_year 的年份
                hist_years = hist['Year'].values
                nearest_idx = np.argmin(np.abs(hist_years - baseline_year))
                nearest_year = hist_years[nearest_idx]
                nearest_subset = hist[hist['Year'] == nearest_year]
                base_power_map[(c, g, lc)] = (nearest_subset['P'].sum() /
                                              nearest_subset['NV'].sum())

    if verbose:
        print(f"   基准 (Base_Power) 覆盖组数: {len(base_power_map)}")

    # ---- 合并 Base_Power 回主表，计算 Power_Discount_Factor ----
    base_df = pd.DataFrame([
        {'Country': k[0], 'Gear': k[1], 'Length_Category': k[2],
         'Base_Power': v}
        for k, v in base_power_map.items()
    ])
    df = df.merge(base_df, on=['Country', 'Gear', 'Length_Category'], how='inner')
    df['Power_Discount_Factor'] = df['Avg_Power'] / df['Base_Power']

    # 裁剪极端值：折扣因子不应 > 1.5（历史船不可能比现代船强太多）且 > 0
    df['Power_Discount_Factor'] = df['Power_Discount_Factor'].clip(0.01, 1.5)

    if verbose:
        f = df['Power_Discount_Factor']
        print(f"   Power_Discount_Factor 分布:")
        print(f"      均值={f.mean():.3f}, 中位数={f.median():.3f}, "
              f"P5={f.quantile(0.05):.3f}, P95={f.quantile(0.95):.3f}")

    # ---- 构建 O(1) 查询字典 ----
    # Level 1: 精确查询 (Country, Gear, Length_Category, Year) -> Discount Factor
    lookup = {}
    for _, row in df.iterrows():
        key = (row['Country'], row['Gear'], row['Length_Category'], int(row['Year']))
        lookup[key] = row['Power_Discount_Factor']

    # Level 2: 全球平均兜底 (Gear, Length_Category, Year) -> Discount Factor
    global_avg = df.groupby(['Gear', 'Length_Category', 'Year'])['Power_Discount_Factor'].mean()
    fallback_global = {}
    for (g, lc, y), val in global_avg.items():
        fallback_global[(g, lc, int(y))] = val

    # Level 3: 按组最近年份数组 (Country, Gear, Length_Category) -> (years_array, factors_array)
    fallback_group_nearest = {}
    for (c, g, lc), grp in df.groupby(['Country', 'Gear', 'Length_Category']):
        grp_sorted = grp.sort_values('Year')
        fallback_group_nearest[(c, g, lc)] = (
            grp_sorted['Year'].values.astype(int),
            grp_sorted['Power_Discount_Factor'].values
        )

    # Level 4: 全球维度最近年份数组
    fallback_global_nearest = {}
    for (g, lc), grp in df.groupby(['Gear', 'Length_Category']):
        grp_sorted = grp.sort_values('Year')
        fallback_global_nearest[(g, lc)] = (
            grp_sorted['Year'].values.astype(int),
            grp_sorted['Power_Discount_Factor'].values
        )

    if verbose:
        print(f"   Level-1 精确查询键数: {len(lookup):,}")
        print(f"   Level-2 全球平均键数: {len(fallback_global):,}")
        print(f"   Level-3 分组最近年键数: {len(fallback_group_nearest):,}")
        print(f"   Level-4 全球最近年键数: {len(fallback_global_nearest):,}")

    return (lookup, fallback_global,
            fallback_group_nearest, fallback_global_nearest)


# ============================================================
# 查询函数 -- 供蒙特卡洛主循环调用 (O(1) 摊销)
# ============================================================

def query_power_discount(flag_full, gear_vessel, length_m, year,
                         lookup_data, hard_floor=0.6,
                         annual_decay_rate=0.018):
    """
    查询给定船只参数对应的 Power_Discount_Factor。

    参数
    ----------
    flag_full : str
        vessel 数据中的 Flag (全名, 如 'Australia', 'South Korea')。
    gear_vessel : str
        vessel 数据中的 VesselType (如 'LL', 'PS', 'TS')。
    length_m : float
        vessel 数据中的 Length(m) 数值。
    year : int
        目标年份 (通常是 Builtdate / 建造年份)。
    lookup_data : tuple
        build_power_discount_lookup() 的返回值。
    hard_floor : float
        硬保底最低折扣系数 (默认 0.6)。
    annual_decay_rate : float
        极早期全局兜底时的年衰减率 (默认 ~1.8%，约等于 0.982/年)。

    返回
    -------
    discount_factor : float
        历史功率折减乘数，范围 [hard_floor, 1.5]。
    """
    (lookup, fallback_global,
     fallback_group_nearest, fallback_global_nearest) = lookup_data

    # ---- 转换参数到 CSV 键空间 ----
    # Country: already ISO3 from unified pipeline
    country_iso3 = flag_full

    # Gear: LL/PS/TS -> CSV Gear 名称
    gear_csv = GEAR_MAPPING.get(gear_vessel)
    if gear_csv is None:
        gear_csv = gear_vessel  # 直接尝试原始值

    # Length_Category: 数值 -> CSV 分箱
    len_cat_csv = map_length_to_csv_category(length_m)

    # ---- Level 1: 精确查询 (Country, Gear, Length_Category, Year) ----
    if country_iso3 is not None and gear_csv is not None:
        key = (country_iso3, gear_csv, len_cat_csv, int(year))
        if key in lookup:
            return np.clip(lookup[key], hard_floor, 1.5)

    # ---- Level 2: 全球平均兜底 (Gear, Length_Category, Year) ----
    if gear_csv is not None:
        key = (gear_csv, len_cat_csv, int(year))
        if key in fallback_global:
            return np.clip(fallback_global[key], hard_floor, 1.5)

    # ---- Level 3: 按组最近年份插值 (Country, Gear, Length_Category) ----
    if country_iso3 is not None and gear_csv is not None:
        group_key = (country_iso3, gear_csv, len_cat_csv)
        if group_key in fallback_group_nearest:
            years_arr, factors_arr = fallback_group_nearest[group_key]
            return _nearest_or_interpolate(year, years_arr, factors_arr, hard_floor)

    # ---- Level 4: 全球维度最近年份插值 (Gear, Length_Category) ----
    if gear_csv is not None:
        group_key = (gear_csv, len_cat_csv)
        if group_key in fallback_global_nearest:
            years_arr, factors_arr = fallback_global_nearest[group_key]
            return _nearest_or_interpolate(year, years_arr, factors_arr, hard_floor)

    # ---- Level 5: 极早期全局兜底 ----
    # 以 2015 为锚点，每年按 annual_decay_rate 指数衰减
    ref_year = 2015
    year_diff = max(0, ref_year - int(year))
    hard_decay = np.exp(-annual_decay_rate * year_diff)
    return np.clip(hard_decay, hard_floor, 1.5)


def _nearest_or_interpolate(target_year, years_arr, factors_arr, hard_floor):
    """
    从 (years_arr, factors_arr) 中提取最接近 target_year 的折扣因子。
    使用最近邻；如果 target_year 在两个已知年份之间则线性插值。
    """
    if len(years_arr) == 0:
        return hard_floor

    # 精确匹配
    exact_idx = np.where(years_arr == int(target_year))[0]
    if len(exact_idx) > 0:
        return np.clip(factors_arr[exact_idx[0]], hard_floor, 1.5)

    # 线性插值 / 最近邻
    idx = np.searchsorted(years_arr, int(target_year))

    if idx == 0:
        # 目标年份早于所有已知年份 -> 最近邻 (最早年份)
        return np.clip(factors_arr[0], hard_floor, 1.5)
    elif idx >= len(years_arr):
        # 目标年份晚于所有已知年份 -> 最近邻 (最晚年)
        return np.clip(factors_arr[-1], hard_floor, 1.5)
    else:
        # 在两个已知年份之间 -> 线性插值
        y1, y2 = years_arr[idx - 1], years_arr[idx]
        f1, f2 = factors_arr[idx - 1], factors_arr[idx]
        frac = (int(target_year) - y1) / (y2 - y1)
        return np.clip(f1 + frac * (f2 - f1), hard_floor, 1.5)


# ============================================================
# 便捷初始化函数 -- 一次性构建并返回 lookup 包
# ============================================================

def init_power_discount_lookup(csv_path, baseline_year=2015):
    """
    一次性初始化所有查询结构，返回可直接传入 query_power_discount 的 tuple。
    用法:
        lookup_data = init_power_discount_lookup(csv_path)
        factor = query_power_discount(flag, gear, length, year, lookup_data)
    """
    return build_power_discount_lookup(csv_path, baseline_year)


# ============================================================
# 向量化批量查询 -- 供蒙特卡洛主循环高效调用
# ============================================================

def query_power_discount_vectorized(flags_full, gears_vessel, lengths_m, years,
                                    lookup_data, hard_floor=0.6,
                                    annual_decay_rate=0.018):
    """
    批量查询 Power_Discount_Factor，返回与输入等长的 numpy 数组。
    对于大多数 hit 走快速字典查询路径，少数 miss 走逐元素兜底。

    参数 -- 均为等长 1D array-like。
    """
    n = len(flags_full)
    results = np.full(n, np.nan, dtype=float)

    (lookup, fallback_global,
     fallback_group_nearest, fallback_global_nearest) = lookup_data

    # 预处理转换
    countries_iso3 = np.array(flags_full, dtype=object)  # Already ISO3 from unified pipeline
    gears_csv = np.array([
        GEAR_MAPPING.get(g, g) for g in gears_vessel
    ], dtype=object)
    len_cats_csv = np.array([
        map_length_to_csv_category(l) for l in lengths_m
    ], dtype=object)
    years_int = np.array(years, dtype=int)

    # ---- Pass 1: Level-1 精确查询 (向量化) ----
    # 构建查询键列表，批量检查
    for i in range(n):
        ci = countries_iso3[i]
        gi = gears_csv[i]
        li = len_cats_csv[i]
        yi = years_int[i]
        if ci is not None and gi is not None:
            key = (ci, gi, li, yi)
            if key in lookup:
                results[i] = lookup[key]

    # ---- Pass 2: Level-2 全球平均兜底 ----
    mask_miss = np.isnan(results)
    for i in np.where(mask_miss)[0]:
        gi = gears_csv[i]
        li = len_cats_csv[i]
        yi = years_int[i]
        if gi is not None:
            key = (gi, li, yi)
            if key in fallback_global:
                results[i] = fallback_global[key]

    # ---- Pass 3-5: 兜底逐元素处理 ----
    mask_still_miss = np.isnan(results)
    for i in np.where(mask_still_miss)[0]:
        ci = countries_iso3[i]
        gi = gears_csv[i]
        li = len_cats_csv[i]
        yi = years_int[i]

        # Level 3: 按组最近年份
        found = False
        if ci is not None and gi is not None:
            group_key = (ci, gi, li)
            if group_key in fallback_group_nearest:
                years_arr, factors_arr = fallback_group_nearest[group_key]
                results[i] = _nearest_or_interpolate(yi, years_arr, factors_arr, hard_floor)
                found = True

        # Level 4: 全球最近年份
        if not found and gi is not None:
            group_key = (gi, li)
            if group_key in fallback_global_nearest:
                years_arr, factors_arr = fallback_global_nearest[group_key]
                results[i] = _nearest_or_interpolate(yi, years_arr, factors_arr, hard_floor)
                found = True

        # Level 5: 硬兜底
        if not found:
            ref_year = 2015
            year_diff = max(0, ref_year - yi)
            results[i] = np.exp(-annual_decay_rate * year_diff)

    # 全局裁剪
    results = np.clip(results, hard_floor, 1.5)
    return results


# ============================================================
# 诊断 / 检验工具
# ============================================================

def print_lookup_summary(lookup_data):
    """打印查询表的覆盖度摘要"""
    (lookup, fallback_global,
     fallback_group_nearest, fallback_global_nearest) = lookup_data

    print("\n" + "=" * 50)
    print("  Power Discount Factor 查询表 -- 覆盖度摘要")
    print("=" * 50)
    print(f"  Level-1 精确键数:           {len(lookup):>10,}")
    print(f"  Level-2 全球平均键数:       {len(fallback_global):>10,}")
    print(f"  Level-3 分组最近年键数:     {len(fallback_group_nearest):>10,}")
    print(f"  Level-4 全球最近年键数:     {len(fallback_global_nearest):>10,}")

    # 各 Gear 的覆盖度
    print("\n  各 Gear x Length_Category 的 Base_Power 覆盖:")
    for gear in sorted(set(k[0] for k in fallback_global_nearest.keys())):
        for lc in sorted(set(k[1] for k in fallback_global_nearest.keys() if k[0] == gear)):
            key = (gear, lc)
            if key in fallback_global_nearest:
                years = fallback_global_nearest[key][0]
                print(f"    {gear:30s} | {lc:16s} | {len(years):4d} yrs  "
                      f"({years.min()}-{years.max()})")
    print("=" * 50)
