# ============================================================
# 渔船作业强度系数 (alpha_work / α) 查询模块
# ============================================================
# 基于 PNAS (Rousseau et al., 2019) 全球渔业努力量数据集
# (TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv)，
# 提取核心物理不变量 α — 单日发动机运行时间中用于捕捞的比例。
#
#   α = T_work / T_total = NomActiveHours / (NomActive × H_day)
#
# 数学推导 (DAS 相消定理):
#   NomActive      = P × DAS           (总功率 × 出海天数)
#   NomActiveHours = P × Fishing_Hours (总功率 × 纯作业捕捞小时)
#   →
#   α = (P × Fishing_Hours) / (P × DAS × H_day)
#     = Fishing_Hours / (DAS × H_day)
#     = DAStoFH / H_day                ← DAS 完美约分! P 也约分!
#
# α 是独立于 P (功率) 和 DAS (年出海天数) 的纯物理常数，
# 仅反映单日作业强度: 发动机每运行1小时, 有 α 比例用于捕捞。
#
# ════════════════════════════════════════════════════════════
# 双轨制 H_day (每日发动机运行小时):
# ════════════════════════════════════════════════════════════
#   'I'   — Industrial:  H_day = 24h  (远洋全天候运行)
#            α_median ≈ 0.38 (38%捕捞, 62%远洋航行)
#
#   'APW' — Artisanal:   H_day = 12h  (近岸日间作业, 工业船的一半)
#            α_median ≈ 0.75 (75%捕捞, 25%近岸短途航行)
#            (H_day=6→99.5%异常, H_day=10→16.9%异常,
#             H_day=12→仅1.77%α>1需裁剪, 且恰好为工业船一半)
#
#   'UP'  — Unpowered:   排除
#
# 路由规则:
#   VesselType ∈ {PS, TS, SA} → Industrial ('I')
#   Length >= 12m → Industrial ('I')
#   Length <  12m → Artisanal ('APW')
#
# 反算公式 (供 GHG 模型使用):
#   T_work = α × DAS_vessel × H_day
#   T_move = (1 - α) × DAS_vessel × H_day
#
# 提供:
#   1. 四级回退查询: 精确年 → 组均值 → 全球均值 → 保守常量
#   2. 标量 & 向量化查询 (供蒙特卡洛主循环高效调用)
#   3. α 变异性分析 (按 Gear / LenCat / Sector / Country)
#   4. 双轨制汇总表: 年度统计 + 综合平均
# ============================================================

import os
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')

# ============================================================
# Section 1: 映射表 — ISO3 / Gear / Length Category
# ============================================================

# Flag 现在统一为 ISO3 代码 (来自统一管道)，无需转换
# (PNAS CSV 查询键直接使用 ISO3)

# VesselType → CSV Gear 映射
# Carrier / Transport / Support 统一映射为 Others_Support
GEAR_MAPPING = {
    'LL': 'Lines_Longlines',
    'PS': 'Seine_Purse_Seine',
    'TS': 'Others_Support',
    'TP': 'Others_Support',
    'SA': 'Others_Support',
    'Carrier': 'Others_Support',
    'Transport': 'Others_Support',
    'Support': 'Others_Support',
}

# CSV Gear → 短名称 (用于报告输出)
CSV_GEAR_SHORT = {
    'Lines_Longlines': 'LL',
    'Seine_Purse_Seine': 'PS',
    'Others_Support': 'Carrier',
}

# 本模块关注的三大目标船型
TARGET_GEARS = ['Seine_Purse_Seine', 'Lines_Longlines', 'Others_Support']


def map_length_to_csv_category(length_m):
    """将数值 Length(m) 映射到 CSV 中的 Length_Category 分箱"""
    if length_m < 6:
        return 'Less than 6m'
    elif length_m < 12:
        return '6-12m'
    elif length_m < 24:
        return '12-24m'
    elif length_m < 50:
        return '24-50m'
    else:
        return 'Over 50m'


# ============================================================
# Section 2: Sector 路由 — 工业船 vs 机动手工船
# ============================================================

def route_vessel_to_sector(length_m, vessel_type):
    """
    双轨制核心：根据船舶物理属性路由到正确的 PNAS Sector 查询轨道。

    路由规则:
        VesselType ∈ {PS, TS, SA} → Industrial ('I') — 围网/运输/辅助船均为工业船
        Length >= 12m → Industrial ('I') — 12m以上为工业金枪鱼船
        Length <  12m → Artisanal ('APW') — 12m以下为近岸手工船

    注意: 路由规则基于金枪鱼渔业特征设计。
          PS (围网) 几乎都是大型工业船；
          TS (运输船) 和 SA (辅助船) 纯为工业渔业服务；
          12m 为 FAO/PNAS 工业 vs 手工渔业的标准分界线。

    返回: 'I' 或 'APW'
    """
    if vessel_type in ('PS', 'TS', 'TP', 'SA'):
        return 'I'
    if length_m >= 12.0:
        return 'I'
    return 'APW'


# ============================================================
# Section 3: 数据读取与时间物理切割
# ============================================================

def _load_and_decompose(csv_path, sector_filter=None, verbose=True,
                        engine_hours_per_day=24.0):
    """
    读取 PNAS CSV，只保留三大目标船型，
    按 (Country, Gear, Length_Category, Year) 聚合，
    提取核心物理不变量 alpha_work (α)。

    α = NomActiveHours / (NomActive × H_day)
      = DAStoFH / H_day (P 和 DAS 完全约分)

    H_day 双轨制:
      - Industrial (I):  24h  (远洋全天候)
      - Artisanal (APW): 12h  (近岸日间, 工业船的一半)

    Parameters
    ----------
    csv_path : str
    sector_filter : str or None
    verbose : bool
    engine_hours_per_day : float
        I=24, APW=12。

    返回 DataFrame 列: Country, Gear, Length_Category, Year, NV, P, DAS, alpha_work
    """
    if verbose:
        sector_label = f" (Sector={sector_filter})" if sector_filter else " (跨Sector聚合)"
        print(f"[预处理] 读取 PNAS 历史船队数据{sector_label}: {csv_path} ...")

    df_raw = pd.read_csv(csv_path, skiprows=[1])

    # 类型转换
    for col in ['NV', 'P', 'Year', 'NomActive', 'NomActiveHours']:
        df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')

    df_raw['Country'] = df_raw['Country'].astype(str).str.strip()
    df_raw['Gear'] = df_raw['Gear'].astype(str).str.strip()
    df_raw['Length_Category'] = df_raw['Length_Category'].astype(str).str.strip()
    df_raw['Sector'] = df_raw['Sector'].astype(str).str.strip()

    # --- Sector 过滤 (双轨制核心) ---
    if sector_filter is not None:
        n_before = len(df_raw)
        df_raw = df_raw[df_raw['Sector'] == sector_filter].copy()
        if verbose:
            print(f"   Sector 过滤: {n_before:,} → {len(df_raw):,} 行 "
                  f"(保留 '{sector_filter}', 丢弃 {n_before - len(df_raw):,})")

    # 过滤无效记录: P > 0, NomActive > 0, NomActiveHours > 0
    df_raw = df_raw[
        (df_raw['P'] > 0) &
        (df_raw['NomActive'] > 0) &
        (df_raw['NomActiveHours'] > 0)
    ].copy()

    # 只保留三大目标船型
    df_raw = df_raw[df_raw['Gear'].isin(TARGET_GEARS)].copy()

    if verbose:
        print(f"   三大船型有效数据行数: {len(df_raw):,}")
        print(f"   年份跨度: {int(df_raw['Year'].min())} - {int(df_raw['Year'].max())}")

    # ---- 聚合: 同一 (Country, Gear, Length_Category, Year) ----
    # 当 sector_filter=None 时跨 Sector 求和; 否则 Sector 已经过滤，不需要额外聚合
    agg_cols = {'NV': 'sum', 'P': 'sum', 'NomActive': 'sum', 'NomActiveHours': 'sum'}
    df = df_raw.groupby(
        ['Country', 'Gear', 'Length_Category', 'Year'], as_index=False
    ).agg(agg_cols)

    if verbose:
        print(f"   聚合后行数: {len(df):,}")

    # ---- DAS (仅用于报告, 不参与 α 计算) ----
    df['DAS'] = df['NomActive'] / df['P']

    # ---- 核心物理不变量: alpha_work ----
    # α = NomActiveHours / (NomActive × H_day)
    #   = (P × Fishing_Hours) / (P × DAS × H_day)
    #   = DAStoFH / H_day
    # P 和 DAS 完全约分, α 是独立于船队规模和出海天数的纯物理常数
    df['alpha_work'] = df['NomActiveHours'] / (df['NomActive'] * engine_hours_per_day)

    # 裁剪: α ∈ [0, 1] (极少数原始数据 T_work > T_total 导致 α>1)
    n_clip = (df['alpha_work'] > 1.0).sum()
    if n_clip > 0:
        if verbose:
            print(f"   [WARNING] alpha_work > 1.0: {n_clip} 行 "
                  f"({100*n_clip/len(df):.2f}%) → 裁剪至 1.0")
        df['alpha_work'] = df['alpha_work'].clip(0.0, 1.0)

    if verbose:
        print(f"   最终有效行数: {len(df):,}")
        print(f"   唯一国家数:   {df['Country'].nunique()}")
        print(f"   唯一 Gear:     {sorted(df['Gear'].unique())}")
        print(f"   Length_Category: {sorted(df['Length_Category'].unique())}")
        print(f"   DAS 范围:       {df['DAS'].min():.1f} - {df['DAS'].max():.1f} 天")
        print(f"   alpha_work 范围: {df['alpha_work'].min():.3f} - {df['alpha_work'].max():.3f}")
        print(f"   alpha_work 中位数: {df['alpha_work'].median():.3f}")

    return df


# ============================================================
# Section 4: 构建三级查询字典
# ============================================================

def _build_lookups(df, verbose=True):
    """
    基于预处理后的 DataFrame 构建三级 alpha_work 查询字典。

    lookup_exact:       (Country_ISO3, Gear_CSV, LenCat, Year) → α
    lookup_group_mean:  (Country_ISO3, Gear_CSV, LenCat) → α_mean
    lookup_global_mean: (Gear_CSV, LenCat) → α_mean

    α = DAStoFH / H_day, 独立于 P 和 DAS 的纯物理常数。
    """
    # Level 1: 精确年份
    lookup_exact = {}
    for _, row in df.iterrows():
        key = (row['Country'], row['Gear'], row['Length_Category'], int(row['Year']))
        lookup_exact[key] = float(row['alpha_work'])

    # Level 2: 组历史均值 (跨年份)
    group_means = df.groupby(
        ['Country', 'Gear', 'Length_Category']
    )['alpha_work'].mean()
    lookup_group_mean = {}
    for (c, g, lc), val in group_means.items():
        lookup_group_mean[(c, g, lc)] = float(val)

    # Level 3: 全球均值 (跨国家跨年份)
    global_means = df.groupby(
        ['Gear', 'Length_Category']
    )['alpha_work'].mean()
    lookup_global_mean = {}
    for (g, lc), val in global_means.items():
        lookup_global_mean[(g, lc)] = float(val)

    if verbose:
        print(f"   Level-1 精确键数:   {len(lookup_exact):>8,}")
        print(f"   Level-2 组均值键数: {len(lookup_group_mean):>8,}")
        print(f"   Level-3 全球均值键数: {len(lookup_global_mean):>8,}")

    return lookup_exact, lookup_group_mean, lookup_global_mean


# ============================================================
# Section 5: 查询接口 (标量 & 向量化, Sector-aware)
# ============================================================

def _resolve_flag_to_iso3(flag):
    """
    将 vessel Flag 转换为 ISO3 代码。
    Flag 已通过统一管道 (flag_utils.py) 标准化为 ISO3 — 直接返回。
    """
    if not flag or pd.isna(flag):
        return None
    return str(flag).strip()


def _resolve_gear_to_csv(gear):
    """VesselType → CSV Gear 名称 (含 Carrier→Others_Support 转换)。"""
    return GEAR_MAPPING.get(gear, gear)


def _is_carrier_type(gear):
    """判断是否为转运船/辅助母船类型。"""
    return gear in ('TP', 'TS', 'SA', 'Carrier', 'Transport', 'Support', 'Others_Support')


def query_time_profile(flag, gear, length, year, lookup_data, sector=None):
    """
    查询 (T_move, T_work) 绝对小时 (向后兼容接口, 基于 α 反算)。

    内部通过 query_alpha_work() 获取 α, 然后用参考 DAS × H_day 反算:
        T_work = α × DAS_ref × H_day
        T_move = (1-α) × DAS_ref × H_day

    返回 (t_move, t_work) 绝对小时。
    """
    alpha = query_alpha_work(flag, gear, length, year, lookup_data, sector=sector)
    if sector is None:
        sector = route_vessel_to_sector(length, gear)
    h_day = 24.0 if sector == 'I' else 12.0
    das_ref = 200.0  # PNAS 全球参考 DAS
    t_total = das_ref * h_day
    t_work = alpha * t_total
    t_move = t_total - t_work
    return t_move, t_work


def query_alpha_work(flag, gear, length, year, lookup_data, sector=None):
    """
    查询 alpha_work (α) — 单日发动机运行时间中用于捕捞的比例。

    α = NomActiveHours / (NomActive × H_day) = DAStoFH / H_day
    独立于 P (功率) 和 DAS (年出海天数), 是纯物理常数。

    参数
    ----------
    flag : str   — Flag 全名或 ISO3 代码
    gear : str   — VesselType (LL/PS/Carrier/...)
    length : float — Length(m)
    year : int   — 目标年份
    lookup_data : dict — init_time_profile_lookup() 返回值
    sector : str or None — 'I'/'APW', None=自动路由

    返回
    -------
    alpha_work : float  [0, 1]

    反算公式:
        T_work = α × DAS_vessel × H_day
        T_move = (1-α) × DAS_vessel × H_day
        其中 H_day: I=24h, APW=12h
    """
    if sector is None:
        sector = route_vessel_to_sector(length, gear)

    sector_lookups = lookup_data.get(sector)
    if sector_lookups is None:
        sector_lookups = lookup_data.get('I', lookup_data.get('APW'))

    lookup_exact, lookup_group_mean, lookup_global_mean = sector_lookups

    country_iso3 = _resolve_flag_to_iso3(flag)
    gear_csv = _resolve_gear_to_csv(gear)
    len_cat = map_length_to_csv_category(length)
    is_carrier = _is_carrier_type(gear)

    # Level 1: 精确年份
    if country_iso3 is not None:
        key = (country_iso3, gear_csv, len_cat, int(year))
        if key in lookup_exact:
            return lookup_exact[key]

    # Level 2: 组历史均值
    if country_iso3 is not None:
        key = (country_iso3, gear_csv, len_cat)
        if key in lookup_group_mean:
            return lookup_group_mean[key]

    # Level 3: 全球均值
    key = (gear_csv, len_cat)
    if key in lookup_global_mean:
        return lookup_global_mean[key]

    # Level 4: 兜底常量
    # I non-carrier: α≈1500/(1500+3300)=0.3125; I carrier: α≈500/(500+4000)=0.1111
    # APW non-carrier: α≈1000/(1000+2200)=0.3125; APW carrier: α≈400/(400+3000)=0.1176
    if sector == 'APW':
        return 0.1176 if is_carrier else 0.3125
    else:
        return 0.1111 if is_carrier else 0.3125


def query_time_profile_vectorized(flags, gears, lengths, years, lookup_data,
                                   sectors=None):
    """
    批量查询 (T_move, T_work) 绝对小时 (向后兼容, 基于 α 反算)。

    先通过 query_alpha_work_vectorized 获取 α, 再反算绝对小时。
    """
    alpha_arr = query_alpha_work_vectorized(flags, gears, lengths, years,
                                             lookup_data, sectors=sectors)
    n = len(flags)
    if sectors is None:
        sectors = np.array([
            route_vessel_to_sector(lengths[i], gears[i]) for i in range(n)
        ], dtype=object)
    else:
        sectors = np.asarray(sectors, dtype=object)

    t_move_arr = np.full(n, np.nan, dtype=float)
    t_work_arr = np.full(n, np.nan, dtype=float)

    for i in range(n):
        if np.isnan(alpha_arr[i]):
            continue
        alpha = alpha_arr[i]
        h_day = 24.0 if sectors[i] == 'I' else 12.0
        das = 200.0  # PNAS 全球参考 DAS
        t_total = das * h_day
        t_work_arr[i] = alpha * t_total
        t_move_arr[i] = t_total - t_work_arr[i]

    return t_move_arr, t_work_arr


def query_alpha_work_vectorized(flags, gears, lengths, years, lookup_data,
                                 sectors=None):
    """
    批量查询 alpha_work (α) — 核心物理不变量。

    参数同 query_time_profile_vectorized()。

    返回
    -------
    alpha_arr : np.ndarray  (shape: (n,))  [0, 1]
    """
    n = len(flags)

    if sectors is None:
        sectors = np.array([
            route_vessel_to_sector(lengths[i], gears[i]) for i in range(n)
        ], dtype=object)
    else:
        sectors = np.asarray(sectors, dtype=object)

    alpha_arr = np.full(n, np.nan, dtype=float)

    countries_iso3 = np.array([
        _resolve_flag_to_iso3(f) for f in flags
    ], dtype=object)
    gears_csv = np.array([
        _resolve_gear_to_csv(g) for g in gears
    ], dtype=object)
    len_cats = np.array([
        map_length_to_csv_category(l) for l in lengths
    ], dtype=object)
    years_int = np.array(years, dtype=int)

    for sector_id in ['I', 'APW']:
        mask_sector = sectors == sector_id
        if not mask_sector.any():
            continue

        sector_lookups = lookup_data.get(sector_id)
        if sector_lookups is None:
            continue
        lookup_exact, lookup_group_mean, lookup_global_mean = sector_lookups

        idx_list = np.where(mask_sector)[0]

        for i in idx_list:
            ci = countries_iso3[i]
            gi = gears_csv[i]
            li = len_cats[i]
            yi = years_int[i]

            if ci is not None:
                key = (ci, gi, li, yi)
                if key in lookup_exact:
                    alpha_arr[i] = lookup_exact[key]
                    continue
                key = (ci, gi, li)
                if key in lookup_group_mean:
                    alpha_arr[i] = lookup_group_mean[key]
                    continue
            key = (gi, li)
            if key in lookup_global_mean:
                alpha_arr[i] = lookup_global_mean[key]
                continue

            # Fallback
            if _is_carrier_type(gears[i]):
                alpha_arr[i] = 0.1176 if sector_id == 'APW' else 0.1111
            else:
                alpha_arr[i] = 0.3125

    return alpha_arr


# ============================================================
# Section 6: 便捷初始化函数 (双轨制)
# ============================================================

def init_time_profile_lookup(csv_path, verbose=True):
    """
    一次性初始化双轨制 Time Profile 查询结构。

    返回 dict，包含两个独立 Sector 的查询结构:
        {
            'I':   (exact, group_mean, global_mean)  — Industrial 工业船
            'APW': (exact, group_mean, global_mean)  — Artisanal Powered 机动手工船
        }

    用法:
        lookup_tp = init_time_profile_lookup(csv_path)

        # 标量查询 (自动路由)
        t_move, t_work = query_time_profile(flag, gear, length, year, lookup_tp)

        # 标量查询 (强制 Sector)
        t_move, t_work = query_time_profile(flag, gear, length, year, lookup_tp, sector='I')

        # 向量化查询
        t_move_arr, t_work_arr = query_time_profile_vectorized(
            flags, gears, lengths, years, lookup_tp
        )
    """
    # Sector → engine_hours_per_day 映射
    # Industrial: 远洋24h连续运行
    # APW: 近岸小船12h/天 (工业船的一半, α中位数=0.75)
    hours_per_day_map = {'I': 24.0, 'APW': 12.0}

    lookups = {}
    for sector_id, sector_label in [('I', 'Industrial'), ('APW', 'Artisanal Powered')]:
        hpd = hours_per_day_map[sector_id]
        if verbose:
            print(f"\n{'─' * 60}")
            print(f"  构建 Sector={sector_id} ({sector_label}) 查询结构 "
                  f"[engine_hours_per_day={hpd:.0f}h]")
            print(f"{'─' * 60}")
        df_sector = _load_and_decompose(csv_path, sector_filter=sector_id,
                                         engine_hours_per_day=hpd, verbose=verbose)
        lookups[sector_id] = _build_lookups(df_sector, verbose=verbose)

    if verbose:
        print(f"\n[Done] 双轨制 Time Profile 查询表初始化完成。")
        # 打印 Sector 对比摘要
        for sector_id in ['I', 'APW']:
            exact, grp, glb = lookups[sector_id]
            print(f"  Sector={sector_id}: exact={len(exact):,}, "
                  f"group={len(grp):,}, global={len(glb):,}")

    return lookups


# ============================================================
# Section 7: 三大船队历年作业时间演变报告
# ============================================================

def print_trend_report(df):
    """
    打印《三大船队历年作业时间演变报告》。

    针对主要远洋国家 (JPN, CHN, KOR, TWN)、大型船只 (24-50m, Over 50m)，
    在关键节点年份 (1970, 1990, 2010, 2015) 展示 DAS 和 T_work，
    以观察各国出海天数与纯作业时间是否随技术发展发生历史变化。
    """
    target_countries = ['JPN', 'CHN', 'KOR', 'TWN']
    target_gears = ['Lines_Longlines', 'Seine_Purse_Seine', 'Others_Support']
    target_lens = ['24-50m', 'Over 50m']
    key_years = [1970, 1990, 2010, 2015]

    # 辅助: 取最近年份的值 (原始数据未必精确落在 key_years)
    def _get_nearest(df_sub, target_year, col, window=3):
        """在 df_sub 中查找 target_year ± window 范围内最近年份的 col 均值"""
        candidates = df_sub[
            (df_sub['Year'] >= target_year - window) &
            (df_sub['Year'] <= target_year + window)
        ]
        if len(candidates) == 0:
            return np.nan
        # 取最接近 target_year 的年份
        candidates = candidates.copy()
        candidates['_dist'] = (candidates['Year'] - target_year).abs()
        best = candidates.loc[candidates['_dist'].idxmin()]
        return best[col]

    print("\n" + "=" * 100)
    print("  三大船队历年作业时间演变报告")
    print("  (主要远洋国家 × 大型船只 × 关键年份: DAS 出海天数 / T_work 纯作业小时)")
    print("=" * 100)

    for gear in target_gears:
        short = CSV_GEAR_SHORT.get(gear, gear)
        for lc in target_lens:
            print(f"\n{'─' * 100}")
            print(f"  [{short}] {lc}")
            print(f"  {'Country':8s} {'指标':10s}", end="")
            for yr in key_years:
                print(f"  {yr:>10d}", end="")
            print(f"  {'历年均值':>12s}  {'CV':>8s}")
            print(f"  {'─' * 8} {'─' * 10}", end="")
            for _ in key_years:
                print(f"  {'─' * 10}", end="")
            print(f"  {'─' * 12}  {'─' * 8}")

            for country in target_countries:
                subset = df[(df['Country'] == country) &
                           (df['Gear'] == gear) &
                           (df['Length_Category'] == lc)]
                if len(subset) == 0:
                    continue

                # DAS 行
                vals = []
                for yr in key_years:
                    v = _get_nearest(subset, yr, 'DAS')
                    vals.append(v)
                das_mean = subset['DAS'].mean()
                das_cv = subset['DAS'].std() / das_mean if das_mean > 0 else np.nan
                print(f"  {country:8s} {'DAS (天)':10s}", end="")
                for v in vals:
                    if np.isnan(v):
                        print(f"  {'N/A':>10s}", end="")
                    else:
                        print(f"  {v:10.1f}", end="")
                print(f"  {das_mean:10.1f}  {das_cv:8.4f}")

                # alpha_work 行
                vals = []
                for yr in key_years:
                    v = _get_nearest(subset, yr, 'alpha_work')
                    vals.append(v)
                aw_mean = subset['alpha_work'].mean()
                aw_cv = subset['alpha_work'].std() / aw_mean if aw_mean > 0 else np.nan
                print(f"  {country:8s} {'alpha':10s}", end="")
                for v in vals:
                    if np.isnan(v):
                        print(f"  {'N/A':>10s}", end="")
                    else:
                        print(f"  {v:10.4f}", end="")
                print(f"  {aw_mean:10.4f}  {aw_cv:8.4f}")

    # ---- 全球汇总 ----
    print(f"\n{'─' * 100}")
    print(f"  【全球汇总: 24m+ 均值 (跨所有国家)】")
    print(f"  {'Gear':10s} {'LenCat':12s} {'N_groups':>8s}  "
          f"{'DAS_mean':>10s}  {'alpha_mean':>12s}")
    print(f"  {'─' * 10} {'─' * 12} {'─' * 8}  {'─' * 10}  {'─' * 12}")

    for gear in target_gears:
        short = CSV_GEAR_SHORT.get(gear, gear)
        for lc in target_lens:
            sub = df[(df['Gear'] == gear) & (df['Length_Category'] == lc)]
            if len(sub) > 0:
                n_grp = sub.groupby('Country').ngroups
                print(f"  {short:10s} {lc:12s} {n_grp:8d}  "
                      f"{sub['DAS'].mean():10.1f}  {sub['alpha_work'].mean():12.4f}")

    # ---- CV 分析 (α 稳定性) ----
    print(f"\n{'─' * 100}")
    print(f"  【α 时序恒定性: 按 (Country, Gear, LenCat) 分组的 CV 分布】")
    print(f"  (CV = Std/Mean 跨年变异系数, CV < 0.05 可视为物理常数)")

    cv_records = []
    for (c, g, lc), grp in df.groupby(['Country', 'Gear', 'Length_Category']):
        if len(grp) < 3:
            continue
        for col_name, col_label in [('DAS', 'DAS'), ('alpha_work', 'alpha')]:
            vals = grp[col_name].values
            mean_v = float(np.mean(vals))
            cv = float(np.std(vals)) / mean_v if mean_v > 0 else float('inf')
            cv_records.append({
                'Country': c, 'Gear': g, 'LenCat': lc, 'Metric': col_label,
                'N_Years': len(grp), 'Mean': mean_v, 'CV': cv,
                'Is_Constant': cv < 0.05,
            })

    cv_df = pd.DataFrame(cv_records)

    for metric in ['DAS', 'alpha_work']:
        sub = cv_df[cv_df['Metric'] == metric]
        n_tot = len(sub)
        n_const = int(sub['Is_Constant'].sum())
        print(f"  {metric:10s}: n={n_tot:5d}  "
              f"P25_CV={sub['CV'].quantile(0.25):.4f}  "
              f"Median_CV={sub['CV'].quantile(0.50):.4f}  "
              f"P75_CV={sub['CV'].quantile(0.75):.4f}  "
              f"P95_CV={sub['CV'].quantile(0.95):.4f}  "
              f"恒定率={100*n_const/max(n_tot,1):.1f}% (CV<0.05)")

    print("\n" + "=" * 100)
    return cv_df


# ============================================================
# Section 8: 双轨制汇总表生成 — 年度表 & 综合平均表
# ============================================================

def generate_summary_tables(csv_path, output_dir=None, verbose=True):
    """
    基于 PNAS 双轨制数据生成两张汇总表:

    Table 1 (Annual): 年度统计表 — 按 (Year, Gear, Length_Category, Sector) 汇总
        Time_Profile_Annual_Summary.csv
        列: Year, Gear, Gear_Short, Length_Category, Sector,
             N_Countries, NV_sum, P_sum_kW,
             DAS_mean, DAS_std, DAS_median, DAS_p25, DAS_p75,
             alpha_mean, alpha_std, alpha_median, alpha_p25, alpha_p75

    Table 2 (Comprehensive): 综合平均表 — α 跨年稳定性
        Time_Profile_Comprehensive_Summary.csv
        列: Gear, Gear_Short, Length_Category, Sector,
             N_Years, N_Countries_total,
             NV_sum_mean, NV_sum_std, P_sum_kW_mean, P_sum_kW_std,
             DAS_mean, DAS_std_interannual, DAS_median_interannual,
             alpha_mean, alpha_std_interannual, alpha_median_interannual,
             alpha_CV_interannual, DAS_CV_interannual

    Parameters
    ----------
    csv_path : str
        PNAS CSV 文件路径
    output_dir : str or None
        输出目录。默认: csv_path 所在目录
    verbose : bool

    Returns
    -------
    (df_annual, df_comprehensive) : tuple of DataFrames
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(csv_path))

    # ---- 分别加载 I / APW 数据，打上 Sector 标签 ----
    hours_per_day_map = {'I': 24.0, 'APW': 12.0}
    dfs = []
    for sector_id in ['I', 'APW']:
        hpd = hours_per_day_map[sector_id]
        df_s = _load_and_decompose(csv_path, sector_filter=sector_id,
                                    engine_hours_per_day=hpd, verbose=verbose)
        df_s['Sector'] = sector_id
        dfs.append(df_s)

    df_combined = pd.concat(dfs, ignore_index=True)

    # 添加短船型名
    df_combined['Gear_Short'] = df_combined['Gear'].map(CSV_GEAR_SHORT).fillna(df_combined['Gear'])

    if verbose:
        print(f"\n{'─' * 70}")
        print(f"  双轨制合并数据: {len(df_combined):,} 行")
        print(f"  Sector I:   {(df_combined['Sector']=='I').sum():,}")
        print(f"  Sector APW: {(df_combined['Sector']=='APW').sum():,}")
        print(f"  年份范围:   {int(df_combined['Year'].min())} - {int(df_combined['Year'].max())}")

    # ════════════════════════════════════════════════════════
    # Table 1: 年度统计表 (α 为核心指标)
    # ════════════════════════════════════════════════════════
    if verbose:
        print(f"\n[Table 1] 生成年度统计表...")

    group_cols_annual = ['Year', 'Gear', 'Gear_Short', 'Length_Category', 'Sector']

    annual_agg = df_combined.groupby(group_cols_annual, as_index=False).agg(
        N_Countries=('Country', 'nunique'),
        NV_sum=('NV', 'sum'),
        P_sum_kW=('P', 'sum'),
        DAS_mean=('DAS', 'mean'),
        DAS_std=('DAS', 'std'),
        DAS_median=('DAS', 'median'),
        alpha_mean=('alpha_work', 'mean'),
        alpha_std=('alpha_work', 'std'),
        alpha_median=('alpha_work', 'median'),
    )

    pcts_annual = df_combined.groupby(group_cols_annual).agg(
        DAS_p25=('DAS', lambda x: x.quantile(0.25)),
        DAS_p75=('DAS', lambda x: x.quantile(0.75)),
        alpha_p25=('alpha_work', lambda x: x.quantile(0.25)),
        alpha_p75=('alpha_work', lambda x: x.quantile(0.75)),
    ).reset_index()

    annual_agg = annual_agg.merge(pcts_annual, on=group_cols_annual, how='left')

    # 四舍五入
    for c in ['DAS_mean', 'DAS_std', 'DAS_median', 'DAS_p25', 'DAS_p75']:
        annual_agg[c] = annual_agg[c].round(1)
    for c in ['alpha_mean', 'alpha_std', 'alpha_median', 'alpha_p25', 'alpha_p75']:
        annual_agg[c] = annual_agg[c].round(4)
    annual_agg['P_sum_kW'] = annual_agg['P_sum_kW'].round(0)

    annual_agg = annual_agg.sort_values(['Year', 'Sector', 'Gear', 'Length_Category']).reset_index(drop=True)

    # 保存
    annual_path = os.path.join(output_dir, 'Time_Profile_Annual_Summary.csv')
    try:
        annual_agg.to_csv(annual_path, index=False, encoding='utf-8-sig')
        if verbose:
            print(f"  保存: {annual_path}")
    except PermissionError:
        annual_path = os.path.join(output_dir, 'Time_Profile_Annual_Summary_NEW.csv')
        annual_agg.to_csv(annual_path, index=False, encoding='utf-8-sig')
        if verbose:
            print(f"  [WARNING] 原文件被锁定, 已保存至: {annual_path}")
    if verbose:
        print(f"  行数: {len(annual_agg):,}  列数: {len(annual_agg.columns)}")

    # ════════════════════════════════════════════════════════
    # Table 2: 综合平均表 (α 跨年稳定性分析)
    # ════════════════════════════════════════════════════════
    if verbose:
        print(f"\n[Table 2] 生成综合平均表...")

    group_cols_comp = ['Gear', 'Gear_Short', 'Length_Category', 'Sector']

    # 先按年度聚合
    yearly = df_combined.groupby(
        ['Year', 'Gear', 'Gear_Short', 'Length_Category', 'Sector'], as_index=False
    ).agg(
        N_Countries=('Country', 'nunique'),
        NV_sum=('NV', 'sum'),
        P_sum_kW=('P', 'sum'),
        DAS_mean=('DAS', 'mean'),
        alpha_mean=('alpha_work', 'mean'),
    )

    # 跨年统计
    comp_agg = yearly.groupby(group_cols_comp, as_index=False).agg(
        N_Years=('Year', 'nunique'),
        N_Countries_total=('N_Countries', 'sum'),
        NV_sum_mean=('NV_sum', 'mean'),
        NV_sum_std=('NV_sum', 'std'),
        P_sum_kW_mean=('P_sum_kW', 'mean'),
        P_sum_kW_std=('P_sum_kW', 'std'),
        DAS_mean=('DAS_mean', 'mean'),
        DAS_std_interannual=('DAS_mean', 'std'),
        DAS_median_interannual=('DAS_mean', 'median'),
        alpha_mean=('alpha_mean', 'mean'),
        alpha_std_interannual=('alpha_mean', 'std'),
        alpha_median_interannual=('alpha_mean', 'median'),
    )

    # α 跨年变异系数 (CV = std/mean, 衡量时序稳定性)
    comp_agg['alpha_CV_interannual'] = (
        comp_agg['alpha_std_interannual'] / comp_agg['alpha_mean'].replace(0, np.nan)
    )
    comp_agg['DAS_CV_interannual'] = (
        comp_agg['DAS_std_interannual'] / comp_agg['DAS_mean'].replace(0, np.nan)
    )

    # 四舍五入
    for c in ['DAS_mean', 'DAS_std_interannual', 'DAS_median_interannual']:
        comp_agg[c] = comp_agg[c].round(1)
    for c in ['alpha_mean', 'alpha_std_interannual', 'alpha_median_interannual',
              'alpha_CV_interannual', 'DAS_CV_interannual']:
        comp_agg[c] = comp_agg[c].round(4)
    for c in ['NV_sum_mean', 'NV_sum_std', 'P_sum_kW_mean', 'P_sum_kW_std']:
        comp_agg[c] = comp_agg[c].round(1)

    comp_agg = comp_agg.sort_values(['Sector', 'Gear', 'Length_Category']).reset_index(drop=True)

    # 保存
    comp_path = os.path.join(output_dir, 'Time_Profile_Comprehensive_Summary.csv')
    try:
        comp_agg.to_csv(comp_path, index=False, encoding='utf-8-sig')
        if verbose:
            print(f"  保存: {comp_path}")
    except PermissionError:
        comp_path = os.path.join(output_dir, 'Time_Profile_Comprehensive_Summary_NEW.csv')
        comp_agg.to_csv(comp_path, index=False, encoding='utf-8-sig')
        if verbose:
            print(f"  [WARNING] 原文件被锁定, 已保存至: {comp_path}")
    if verbose:
        print(f"  行数: {len(comp_agg):,}  列数: {len(comp_agg.columns)}")

    # ---- 控制台摘要 ----
    if verbose:
        _print_summary_preview(annual_agg, comp_agg)

    return annual_agg, comp_agg


def _print_summary_preview(df_annual, df_comprehensive):
    """打印汇总表控制台预览"""
    print(f"\n{'=' * 100}")
    print(f"  【Table 1 年度统计表预览 — 最近 5 年 (α 为核心指标)】")
    print(f"{'=' * 100}")
    recent_years = sorted(df_annual['Year'].unique())[-5:]
    preview = df_annual[df_annual['Year'].isin(recent_years)].head(30)
    cols_show = ['Year', 'Gear_Short', 'Length_Category', 'Sector',
                 'N_Countries', 'NV_sum', 'DAS_mean', 'alpha_mean', 'alpha_median']
    print(preview[cols_show].to_string(index=False))

    print(f"\n{'=' * 100}")
    print(f"  【Table 2 综合平均表预览 — α 跨年稳定性 (核心物理不变量)】")
    print(f"  α = NomActiveHours/(NomActive×H_day) = DAStoFH/H_day, 独立于 P 和 DAS")
    print(f"{'=' * 100}")
    cols_show2 = ['Gear_Short', 'Length_Category', 'Sector',
                  'N_Years', 'N_Countries_total',
                  'DAS_mean', 'alpha_mean', 'alpha_CV_interannual']
    print(df_comprehensive[cols_show2].to_string(index=False))

    # α 稳定性统计
    print(f"\n{'─' * 100}")
    print(f"  【α 跨年稳定性分析】")
    for sector_id in ['I', 'APW']:
        sub = df_comprehensive[df_comprehensive['Sector'] == sector_id]
        avg_alpha = sub['alpha_mean'].mean()
        avg_cv = sub['alpha_CV_interannual'].mean()
        print(f"  Sector={sector_id}: {len(sub)} (Gear×LenCat) 组合, "
              f"mean_α={avg_alpha:.4f}, "
              f"mean_CV_α={avg_cv:.4f} "
              f"({'[高度恒定 CV<0.05]' if avg_cv < 0.05 else '[中等恒定 CV<0.10]' if avg_cv < 0.10 else '[显著变异 CV>=0.10]'})")


# ============================================================
# Section 9: __main__ 测试与报告 (双轨制)
# ============================================================

if __name__ == '__main__':
    import os as _os
    _script_dir = _os.path.dirname(_os.path.abspath(__file__))
    csv_path = _os.path.join(_script_dir,
        'TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv')

    # ---- 初始化 (双轨制) ----
    lookup_data = init_time_profile_lookup(csv_path, verbose=True)

    # ---- 加载用于报告的 df (跨 Sector 聚合, 兼容旧报告) ----
    print(f"\n{'─' * 60}")
    print("  加载跨Sector聚合数据用于趋势报告")
    print(f"{'─' * 60}")
    df_all = _load_and_decompose(csv_path, sector_filter=None, verbose=True)

    # ---- 报告 1: 三大船队历年作业时间演变 ----
    cv_df = print_trend_report(df_all)

    # ---- 报告 2: 双轨制全球均值 α 对比 ----
    print("\n" + "=" * 100)
    print("  【双轨制 Sector 全球均值 α 对比 — I vs APW】")
    print("  α = NomActiveHours/(NomActive×H_day), H_day: I=24h, APW=12h")
    print("=" * 100)
    print(f"  {'Gear':22s} {'LenCat':12s}  "
          f"{'I_α':>8s}  {'I_T_work*':>10s}  |  "
          f"{'APW_α':>8s}  {'APW_T_work*':>10s}  |  "
          f"{'Δα%':>8s}")
    print(f"  {'─' * 22} {'─' * 12}  "
          f"{'─' * 8}  {'─' * 10}  |  "
          f"{'─' * 8}  {'─' * 10}  |  "
          f"{'─' * 8}")
    print(f"  (*T_work = α × DAS_ref × H_day, DAS_ref=200)")

    for gear in TARGET_GEARS:
        for lc in sorted(df_all['Length_Category'].unique()):
            i_alpha = a_alpha = np.nan
            i_glb = lookup_data['I'][2]  # global_mean
            a_glb = lookup_data['APW'][2]
            if (gear, lc) in i_glb:
                i_alpha = i_glb[(gear, lc)]
            if (gear, lc) in a_glb:
                a_alpha = a_glb[(gear, lc)]

            if not np.isnan(i_alpha) or not np.isnan(a_alpha):
                short = CSV_GEAR_SHORT.get(gear, gear)
                i_tw = i_alpha * 200 * 24 if not np.isnan(i_alpha) else np.nan
                a_tw = a_alpha * 200 * 12 if not np.isnan(a_alpha) else np.nan
                da = f"{(a_alpha/i_alpha - 1)*100:+.0f}%" if not np.isnan(i_alpha) and i_alpha > 0 else 'N/A'
                print(f"  {short:22s} {lc:12s}  "
                      f"{i_alpha:8.4f}  {i_tw:10.0f}  |  "
                      f"{a_alpha:8.4f}  {a_tw:10.0f}  |  "
                      f"{da:>8s}")

    # ---- 查询接口测试 (双轨制, 展示 Sector 路由) ----
    print("\n" + "=" * 100)
    print("  【双轨制查询接口测试 — query_time_profile (标量, 含 Sector 路由)】")
    print("=" * 100)

    test_cases = [
        # (Flag, Gear, Length, Year, Sector_override, 说明)
        ('South Korea', 'LL', 45.0, 2010, None, 'KOR 大型LL 2010 — 自动路由→I'),
        ('South Korea', 'LL', 20.0, 2010, None, 'KOR 小型LL 2010 — 自动路由→APW'),
        ('South Korea', 'PS', 55.0, 2010, None, 'KOR Over 50m 围网 — 自动路由→I (PS强制I)'),
        ('South Korea', 'LL', 20.0, 2010, 'I', 'KOR 小型LL 2010 — 强制I(对比)'),
        ('Taiwan', 'LL', 45.0, 1995, None, 'TWN 大型LL 1995 — 自动路由→I'),
        ('Taiwan', 'LL', 15.0, 1995, None, 'TWN 小型LL 1995 — 自动路由→APW'),
        ('Vanuatu', 'LL', 20.0, 2020, None, 'VUT 小型LL 2020 — 小国 APW'),
        ('Vanuatu', 'LL', 20.0, 2020, 'I', 'VUT 小型LL 2020 — 强制I(对比)'),
        ('Japan', 'Carrier', 55.0, 2010, None, 'JPN 大型转运船 — 自动路由→I'),
        ('China', 'PS', 30.0, 2000, None, 'CHN 围网 — 自动路由→I (PS强制I)'),
        ('Vanuatu', 'LL', 12.0, 2020, None, 'VUT 极小LL 2020 — APW兜底'),
    ]

    for flag, gear, length, year, sector_override, desc in test_cases:
        routed = route_vessel_to_sector(length, gear) if sector_override is None else sector_override
        t_move, t_work = query_time_profile(flag, gear, length, year,
                                             lookup_data, sector=sector_override)
        hday = 24.0 if routed == 'I' else 12.0
        tt = t_move + t_work
        print(f"  [{routed}] {desc:48s} → "
              f"T_move={t_move:8.0f} h  T_work={t_work:8.0f} h  "
              f"T_total={tt:8.0f} h  DAS={tt/hday:6.1f} d")

    # ---- 向量化批量测试 (双轨制) ----
    print("\n" + "=" * 100)
    print("  【双轨制向量化批量查询测试 — query_time_profile_vectorized】")
    print("=" * 100)
    test_flags = ['South Korea', 'Japan', 'Taiwan', 'China', 'Vanuatu', 'Vanuatu']
    test_gears = ['LL', 'PS', 'LL', 'PS', 'LL', 'LL']
    test_lengths = [45.0, 55.0, 15.0, 30.0, 20.0, 12.0]
    test_years = [2010, 2010, 1995, 2000, 2020, 2020]

    tm_arr, tw_arr = query_time_profile_vectorized(
        test_flags, test_gears, test_lengths, test_years, lookup_data
    )
    print(f"  {'Flag':15s} {'Gear':8s} {'Len':>5s} {'Year':>6s} {'Route':>6s}  "
          f"{'T_move':>8s}  {'T_work':>8s}  {'T_total':>8s}  {'DAS':>6s}")
    print(f"  {'─'*15} {'─'*8} {'─'*5} {'─'*6} {'─'*6}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*6}")
    for i in range(len(test_flags)):
        sector = route_vessel_to_sector(test_lengths[i], test_gears[i])
        tt = tm_arr[i] + tw_arr[i]
        h_day = 24.0 if sector == 'I' else 12.0
        das = tt / h_day
        print(f"  {test_flags[i]:15s} {test_gears[i]:8s} {test_lengths[i]:5.1f} "
              f"{test_years[i]:6d} [{sector}]  "
              f"{tm_arr[i]:8.0f}  {tw_arr[i]:8.0f}  {tt:8.0f}  {das:6.1f}")

    # ---- alpha_work 查询测试 (核心物理不变量) ----
    print("\n" + "=" * 100)
    print("  【alpha_work 查询测试 — 核心物理不变量 (独立于 DAS)】")
    print("  公式: α = NomActiveHours/(NomActive×H_day) = DAStoFH/H_day")
    print("  反算: T_work = α × DAS_vessel × H_day, T_move = (1-α) × DAS_vessel × H_day")
    print("=" * 100)
    print(f"  {'Flag':15s} {'Gear':8s} {'Len':>5s} {'Year':>6s} {'Sec':>4s}  "
          f"{'α_work':>8s}  {'H_day':>6s}  {'→T_work(h)':>12s}  {'→T_move(h)':>12s}  {'→DAS(d)':>8s}")
    print(f"  {'─'*15} {'─'*8} {'─'*5} {'─'*6} {'─'*4}  {'─'*8}  {'─'*6}  {'─'*12}  {'─'*12}  {'─'*8}")

    # 演示: 同一alpha, 不同DAS得到不同绝对小时
    for flag, gear, length, year, desc in [
        ('South Korea', 'LL', 45.0, 2010, 'KOR I-LL 2010'),
        ('South Korea', 'LL', 11.0, 2010, 'KOR APW-LL 2010'),
        ('Japan', 'PS', 55.0, 2010, 'JPN I-PS 2010'),
        ('Vanuatu', 'LL', 10.0, 2020, 'VUT APW-LL 2020'),
    ]:
        sector = route_vessel_to_sector(length, gear)
        alpha = query_alpha_work(flag, gear, length, year, lookup_data, sector=sector)
        h_day = 24.0 if sector == 'I' else 12.0
        # 反算示范: 使用 PNAS 典型 DAS=200 天
        das_demo = 200.0
        tw_demo = alpha * das_demo * h_day
        tm_demo = (1 - alpha) * das_demo * h_day
        print(f"  {flag:15s} {gear:8s} {length:5.1f} {year:6d} [{sector}]  "
              f"{alpha:8.4f}  {h_day:6.0f}  {tw_demo:12.0f}  {tm_demo:12.0f}  {das_demo:8.0f}")

    # 向量化 alpha_work 测试
    print(f"\n  【向量化 alpha_work】")
    alpha_arr = query_alpha_work_vectorized(
        test_flags, test_gears, test_lengths, test_years, lookup_data
    )
    for i in range(len(test_flags)):
        sector = route_vessel_to_sector(test_lengths[i], test_gears[i])
        print(f"  {test_flags[i]:15s} {test_gears[i]:8s} {test_lengths[i]:5.1f} "
              f"{test_years[i]:6d} [{sector}]  α={alpha_arr[i]:.4f}")

    # ---- Sector 路由分布统计 ----
    print("\n" + "=" * 100)
    print("  【Sector 路由规则验证】")
    print("=" * 100)
    test_combos = [
        ('LL', 10.0), ('LL', 20.0), ('LL', 30.0), ('LL', 55.0),
        ('PS', 10.0), ('PS', 20.0), ('PS', 55.0),
        ('TS', 15.0), ('TS', 55.0),
        ('SA', 15.0), ('SA', 55.0),
    ]
    for gear, length in test_combos:
        sector = route_vessel_to_sector(length, gear)
        print(f"  VesselType={gear:4s}  Length={length:5.1f}m → Sector='{sector}'")

    # ---- 报告 3: 双轨制汇总表 (年度 + 综合平均) ----
    print("\n" + "=" * 100)
    print("  【双轨制汇总表生成 — Table 1 年度统计 + Table 2 综合平均】")
    print("=" * 100)
    df_annual, df_comp = generate_summary_tables(csv_path, verbose=True)

    print("\n  [Done] 双轨制测试与报告已完成。")
