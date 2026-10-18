#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
数据清洗与矩阵重构管道 (Data Preprocessing Pipeline)
=============================================================================
将 Model_parameters.xlsx 中的 4 个非结构化 Sheet 转化为 4 个标准化的、
机器可读的关系型矩阵 (DataFrame)，供下游 LCA 模型直接调用。

输入:  model_parameters/Model_parameters.xlsx (4 sheets)
输出:  4 个 CSV + 1 个合并 Excel:
       - model_parameters/Prior_Matrix.csv
       - model_parameters/Species_CF_Matrix.csv
       - model_parameters/Scenario_Multiplier_Matrix.csv
       - model_parameters/MonteCarlo_Config_Matrix.csv
       - model_parameters/Cleaned_Parameter_Matrices.xlsx (4 sheets)

设计原则:
  1. 原始 Sheet 1（动态生命周期模型）是"文献笔记本"，数据嵌入在中文叙述中，
     无法稳健地自动化解析 → 采用"硬编码提取 + 文献溯源注释"策略。
  2. Sheet 2/3/4 结构相对规整 → 直接解析 + 文本正则提取。
  3. 所有输出矩阵中的缺失值用 NaN 标记，不在计算核心中使用空字符串。
  4. 每个矩阵包含完整的列级中文注释 (via DataFrame.attrs)。

作者: Claude Code 辅助构建
日期: 2026-06-18
=============================================================================
"""

import os
import sys
import re
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# =============================================================================
# Paths
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XLSX_PATH = os.path.join(BASE_DIR, "Model_parameters.xlsx")
OUT_CSV_PRIOR = os.path.join(BASE_DIR, "Prior_Matrix.csv")
OUT_CSV_SPECIES = os.path.join(BASE_DIR, "Species_CF_Matrix.csv")
OUT_CSV_SCENARIO = os.path.join(BASE_DIR, "Scenario_Multiplier_Matrix.csv")
OUT_CSV_MC = os.path.join(BASE_DIR, "MonteCarlo_Config_Matrix.csv")
OUT_XLSX = os.path.join(BASE_DIR, "Cleaned_Parameter_Matrices.xlsx")


# =============================================================================
# Utility functions
# =============================================================================

def safe_str(val) -> str:
    """Convert any value to a cleaned string."""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", ""):
        return ""
    return s


def parse_percent_range(text: str):
    """
    Parse a Chinese/English percentage string into numeric multipliers.

    ONLY matches numbers that are clearly percentage reductions or direct fractions
    of baseline. Skips values with physical units (L/kg, kW, g/kWh, etc.).

    Examples
    --------
    "燃料节省 35–61%"    → (0.65, 0.39, 0.52)  # reduction → multiplier = 1-pct
    "GHG排放减少 22%"     → (1-0.22, 1-0.22, 0.78)
    "碳排放仅为柴油的50%"  → (0.50, 0.50, 0.50)  # direct fraction, NOT reduction
    "0.1 - 0.4 L/kg"     → (None, None, None)   # physical units, skip

    Returns
    -------
    (low_mult, high_mult, central_mult) or (None, None, None)
    """
    text = safe_str(text)
    if not text:
        return None, None, None

    # ---- Reject physical-unit values ----
    unit_patterns = [
        r'L\s*/\s*kg', r'g\s*/\s*kWh', r'kW\s*/\s*m',
        r'\d+\s*(?:ton|吨|t)\s*(?:CO|C)', r'次作业',
    ]
    for pat in unit_patterns:
        if re.search(pat, text):
            return None, None, None

    # ---- Detect "direct fraction" pattern: "为/是/仅为...的 X%" ----
    # "碳排放仅为柴油的 50.24%" → multiplier = 0.5024 (direct, NOT 1-pct)
    direct_frac_match = re.search(
        r'(?:仅为|仅为|为|是)\s*(?:\S+\s*的)?\s*(\d+\.?\d*)\s*%', text
    )
    if direct_frac_match:
        val = float(direct_frac_match.group(1)) / 100.0
        return val, val, val

    # ---- Detect saving/reduction language ----
    is_saving = any(kw in text for kw in [
        '节省', '减少', '降低', '下降', '节约', '减排', 'saving', 'reduce'
    ])

    # Pattern: "35–61%" or "35-61%"
    range_with_pct = r'(\d+\.?\d*)\s*[–\-—~]\s*(\d+\.?\d*)\s*%'
    # Pattern: "22%"
    single_pct = r'(\d+\.?\d*)\s*%'

    # Try range with explicit %
    range_match = re.search(range_with_pct, text)
    if range_match:
        lo = float(range_match.group(1)) / 100.0
        hi = float(range_match.group(2)) / 100.0
        if is_saving:
            return 1.0 - hi, 1.0 - lo, 1.0 - (lo + hi) / 2.0
        else:
            # % range without saving keywords → descriptive proportion, skip
            return None, None, None

    # Try single percentage
    single_match = re.search(single_pct, text)
    if single_match:
        val = float(single_match.group(1)) / 100.0
        if is_saving:
            return 1.0 - val, 1.0 - val, 1.0 - val
        else:
            # Single % without saving keywords — ambiguous, return raw
            return val, val, val

    # Try range without % but with saving keywords
    if is_saving:
        range_no_pct = r'(\d+\.?\d*)\s*[–\-—~]\s*(\d+\.?\d*)'
        range_match2 = re.search(range_no_pct, text)
        if range_match2:
            lo = float(range_match2.group(1)) / 100.0
            hi = float(range_match2.group(2)) / 100.0
            if lo <= 1.0 and hi <= 1.0:
                return 1.0 - hi, 1.0 - lo, 1.0 - (lo + hi) / 2.0

    # Try single number with saving keywords but no % (e.g., "减少40")
    if is_saving:
        single_no_pct = re.search(
            r'(?:节省|减少|降低|下降|节约|减排)\s*(\d+\.?\d*)', text
        )
        if single_no_pct:
            val = float(single_no_pct.group(1)) / 100.0
            if val <= 1.0:
                return 1.0 - val, 1.0 - val, 1.0 - val

    return None, None, None


def parse_ghg_change(text: str):
    """
    Parse GHG-specific change from text.

    Examples
    --------
    "GHG排放减少 22%"     → 0.78
    "GHG排放减少 >30%"    → 0.70
    "CO₂排放因子 0.9 吨"  → 0.9 (direct factor, not multiplier)

    Returns
    -------
    float or None
    """
    text = safe_str(text)
    if not text:
        return None

    # Pattern: GHG/CO2 减少/降低/下降 X% (with optional > or ~)
    pct_match = re.search(
        r'(?:GHG|CO₂?|CO2|温室|碳排放?)\s*(?:排放)?\s*'
        r'(?:减少|降低|下降|减排)\s*[>~]?\s*(\d+\.?\d*)\s*%',
        text
    )
    if pct_match:
        reduction = float(pct_match.group(1)) / 100.0
        return round(1.0 - reduction, 3)

    # Pattern: direct CO2 emission factor
    ef_match = re.search(
        r'(?:CO₂?|CO2)\s*(?:排放因子)?\s*[：:]\s*(\d+\.?\d*)', text
    )
    if ef_match:
        return float(ef_match.group(1))

    return None


def normalize_distribution_name(text: str) -> str:
    """
    Map Chinese distribution descriptions to standard English names.

    Examples
    --------
    "三角分布" → "Triangular"
    "正态分布" → "Normal"
    "对数正态分布" → "Lognormal"
    "连续概率分布" → "Continuous" (generic)
    """
    text = safe_str(text).lower()
    if '三角' in text or 'triangular' in text:
        return 'Triangular'
    if 'pert' in text:
        return 'PERT'
    if '对数正态' in text or 'lognormal' in text or 'log normal' in text:
        return 'Lognormal'
    if '正态' in text or 'normal' in text:
        return 'Normal'
    if '均匀' in text or 'uniform' in text:
        return 'Uniform'
    if '截断' in text or 'truncat' in text:
        return 'Truncated'
    if '离散' in text or 'discrete' in text:
        return 'Discrete'
    if '连续' in text or 'continuous' in text:
        return 'Continuous'
    return 'Continuous'


# =============================================================================
# Matrix 1: Prior_Matrix (先验参数矩阵 — 排放模型完整参数表)
# =============================================================================
#
# 设计说明:
#   Prior_Matrix 是排放模型的"参数主表"，以长格式 (long format) 组织。
#   每条记录代表一个参数在特定维度组合 (Flag × Gear × Sector × LengthCategory)
#   下的取值。所有参数共表，下游模型按 Param_Code + 维度键 直接索引。
#
#   参数来源: Model_parameters.xlsx → Sheet 1「动态生命周期模型」(108 rows)
#   该 Sheet 是文献笔记本，参数嵌入在中文叙述中，需人工提取。
#
#   参数覆盖 8 大类:
#     A. 船舶分类标准            (Vessel Classification)
#     B. 船舶作业活动参数        (Fishing Activity Parameters)
#     C. 核心燃料与排放参数      (Core Fuel & Emission Parameters)
#     D. 辅机功率参数            (Auxiliary Engine Power)
#     E. 船体材料与建造参数      (Hull Material & Construction)
#     F. 渔具材料消耗参数        (Gear Material Consumption)
#     G. 延绳钓饵料消耗参数      (Longline Bait Consumption)
#     H. 制冷剂参数              (Refrigerant Parameters)
#     I. 努力量标准化参数        (Effort Standardization)
#     J. 历史功率演进参数        (Power Discount / Historical Evolution)
#     K. GT-LDT 吨位转换参数     (Gross Tonnage → Light Displacement Tonnage)
#
#   LONG-FORMAT 列定义:
#     Param_Section    — 参数大类 (A-L)
#     Param_Code       — 模型代码中的变量名 (e.g., T_map, SFR_map)
#     Param_Name_CN    — 参数中文名称
#     Flag             — 适用船旗国/区域 (ALL = 全局通用)
#     Gear             — 适用渔具类型: LL/PS/TP/ALL
#     Sector           — 适用部门: I (Industrial) / APW (Artisanal) / ALL
#     Length_Category  — 船长分类: <12m / >=12m / ALL
#     Value_Best       — 最佳估计值 (中位数/众数/均值)
#     Value_Low        — 参数下限
#     Value_High       — 参数上限
#     Unit             — 物理单位
#     Distribution     — 推荐蒙特卡洛分布类型
#     Source_Citation  — 文献来源 (作者, 年份, 期刊)
#     Sheet1_Row       — 原始 Sheet 1 中的行号
#     Note             — 说明备注 (提取逻辑、假设、与模型的关系)
#
#   SCALAR 参数统一使用: Flag=ALL, Gear=ALL, Sector=ALL, Length_Category=ALL
#   GEAR-SPECIFIC 参数:   Flag=ALL, Gear=LL|PS|TP, Sector=ALL
#   SECTOR-SPECIFIC 参数: Flag=ALL, Gear=ALL, Sector=I|APW
#   REGION-SPECIFIC 参数: Flag=Africa|Asia|..., Gear=LL|PS, Sector=I|APW
# =============================================================================

def build_prior_matrix(xlsx_path=None):
    """
    Build the comprehensive Prior_Matrix from Sheet 1 data.

    DESIGN NOTES:
    - Sheet1_Row format: "R3" (single), "R5-R7" (range), "R13,R22" (multiple)
      The "R" prefix prevents Excel from interpreting "5-7" as a date (May 7).
    - Emission factors for construction materials, gear, and bait are left as NaN
      because the user has not yet provided definitive values. Fuel CO2 EFs are
      populated from the literature cited in Sheet 1.
    - Source attribution: each parameter cites the specific literature reference
      mentioned in Sheet 1, NOT a generic fallback.

    Returns
    -------
    pd.DataFrame — long-format unified parameter matrix (102 rows × 15 cols)
    """
    print("\n" + "=" * 70)
    print("  Building Matrix 1: Prior_Matrix (先验参数矩阵 — v2 修正版)")
    print("  Fixes: Sheet1_Row 'R' prefix + Bastos LF corrected + EFs gapped")
    print("=" * 70)

    rows = []

    def add_row(section, code, name_cn, flag, gear, sector, len_cat,
                v_best, v_low, v_high, unit, dist, source, s1_row, note):
        rows.append({
            'Param_Section':    section,
            'Param_Code':       code,
            'Param_Name_CN':    name_cn,
            'Flag':             flag,
            'Gear':             gear,
            'Sector':           sector,
            'Length_Category':  len_cat,
            'Value_Best':       v_best,
            'Value_Low':        v_low,
            'Value_High':       v_high,
            'Unit':             unit,
            'Distribution':     dist,
            'Source_Citation':  source,
            'Sheet1_Row':       s1_row,
            'Note':             note,
        })

    # ========================================================================
    # A. 船舶分类标准 (Vessel Classification) — Sheet 1 Row 4-5
    # ========================================================================
    # Row 4: "手工渔业与工业渔业划分标准 — 船长12m" (EU definition)
    # Row 5: 保留为模型注释行（原Greer 16m阈值已弃用，统一使用EU 12m标准）
    # Model usage:
    #   - 12m: 统一船长阈值，用于Sector、SFR_map、EF_fuel_map等所有阶梯函数
    #   - EU标准: Council Regulation (EC) No 1198/2006, Article 26

    add_row(
        'A', 'LENGTH_THRESHOLD_SECTOR_M', 'Sector划分船长阈值 (EU标准)',
        'ALL', 'ALL', 'ALL', 'ALL',
        12.0, np.nan, np.nan, 'm', 'Discrete',
        'Council Regulation (EC) No 1198/2006 of 27 July 2006 on the European Fisheries Fund, Article 26',
        'R4',
        'I (Industrial): >=12m; APW (Artisanal): <12m. 按欧盟标准统一划分。用于Sector二元分类。'
    )
    add_row(
        'A', 'LENGTH_THRESHOLD_SFR_M', 'SFR/EF阶梯分界船长阈值 (统一EU标准)',
        'ALL', 'ALL', 'ALL', 'ALL',
        12.0, np.nan, np.nan, 'm', 'Discrete',
        'Council Regulation (EC) No 1198/2006; Greer et al. (2019) Mar. Policy 107:103382',
        'R4-R5',
        '<12m vs >=12m. 统一使用EU 12m标准。原Row 5 (Greer 16m)已弃用，所有阶梯函数统一按12m划分。'
    )

    # ========================================================================
    # B. 船舶作业活动参数 (Fishing Activity Parameters) — Sheet 1 Row 6-28
    # ========================================================================

    # ------------------------------------------------------------------
    # B1. DAS — Days at Sea (T_map) — Row 6-13
    # ------------------------------------------------------------------
    # 数据优先级体系 (Data Hierarchy):
    #   Tier 1 (最高): Parker et al. (2014) — 现代金枪鱼围网船队, 按大洋,
    #                  反映1990年后FAD策略下的真实高强度作业
    #   Tier 2 (次级): Jha et al. (2026) — 印度洋/阿拉伯海机械化延绳钓, 最新区域修正
    #   Tier 3 (兜底): Anticamara et al. (2011) — 宏观历史基线 (1950-2010),
    #                  适用于非主要目标船型(TP)、历史回溯、缺数据区域
    #
    # 地理映射 (Geographic Mapping):
    #   Pacific  → 亚洲/大洋洲 (西太) 或 美洲 (东太)
    #   Indian   → 亚洲 或 非洲
    #   Atlantic → 欧洲/美洲 或 非洲
    # RFMO对应: IATTC+WCPFC→Pacific, IOTC→Indian, ICCAT→Atlantic
    #
    # 完整文献引用见各条目 Source_Citation 字段.
    #
    # Row 6: Table header — Gear × Region
    # Row 7: Longline DAS table (Anticamara et al. 2011)
    # Row 8: Purse Seine DAS table (Anticamara et al. 2011)
    # Row 9: PS China = 200 (expert: 谢斌老师咨询)
    # Row 10: Transport = 15 days/month → ~180 days/year
    # Row 11: Fleet characteristics table (Atlantic/Indian/Pacific averages)
    # Row 12: PS trip profile: 33.1 days, 68% transit, 8% fishing, 381t fuel/trip
    # Row 13: LL 234-256 days/year for 16-20m (Jha et al. 2026, SE Arabian Sea)

    # ──────────────────────────────────────────────────────────────
    # Tier 1: Parker et al. (2014) — Modern PS by Ocean (post-1990, FAD era)
    # ──────────────────────────────────────────────────────────────
    # Parker RWR, Vázquez-Rowe I, Tyedmers PH. (2014).
    # Fuel performance and carbon footprint of the global purse seine tuna fleet.
    # Journal of Cleaner Production, 103, 517-524.
    # DOI: 10.1016/j.jclepro.2014.05.017
    # 数据: 93艘围网船 (占全球鲣鱼/黄鳍金枪鱼捕捞量28%), 按大洋分层统计.

    parker_citation = (
        'Parker RWR, Vázquez-Rowe I, Tyedmers PH. (2014). '
        'Fuel performance and carbon footprint of the global purse seine tuna fleet. '
        'J. Clean. Prod. 103:517-524. DOI:10.1016/j.jclepro.2014.05.017'
    )

    # Atlantic PS: 297 days (n=9 vessels, avg LOA=70.6m)
    add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS Atlantic',
            'Atlantic', 'PS', 'I', 'ALL', 297, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            'Tier 1 — 大西洋围网 (Parker et al. 2014): 297 days/year. '
            'n=9 vessels, avg LOA=70.6m. 适用于ICCAT水域, 1990年后FAD时代. '
            'RFMO: ICCAT → Atlantic.')

    # Indian PS: 289 days (n=9 vessels, avg LOA=81.7m)
    add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS Indian',
            'Indian', 'PS', 'I', 'ALL', 289, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            'Tier 1 — 印度洋围网 (Parker et al. 2014): 289 days/year. '
            'n=9 vessels, avg LOA=81.7m. 适用于IOTC水域, 1990年后FAD时代. '
            'RFMO: IOTC → Indian.')

    # Pacific PS: 244 days (n=75 vessels, avg LOA=68.9m)
    add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS Pacific',
            'Pacific', 'PS', 'I', 'ALL', 244, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            'Tier 1 — 太平洋围网 (Parker et al. 2014): 244 days/year. '
            'n=75 vessels, avg LOA=68.9m. 适用于WCPFC+IATTC水域, 1990年后FAD时代. '
            'RFMO: WCPFC+IATTC → Pacific.')

    # PS fallback for unmapped RFMOs: mean of 3 oceans
    parker_mean = round((297 + 289 + 244) / 3, 1)  # = 276.7 ≈ 277
    add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS 缺省均值',
            'ALL', 'PS', 'I', 'ALL', parker_mean, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            f'Tier 1 — 未映射组织默认值: mean(Atlantic 297, Indian 289, Pacific 244) '
            f'= {parker_mean} days/year. '
            '适用于无法明确归入三大洋的RFMO (如CCSBT跨洋水域) 或数据库缺失RFMO标签的船只. '
            'Parker et al. (2014) 全球加权均值=253 days (含小型船), '
            f'三大洋算术均值={parker_mean} days (仅大型商业围网船).')

    # ──────────────────────────────────────────────────────────────
    # Tier 2: Jha et al. (2026) — Indian Ocean Mechanized Longline
    # ──────────────────────────────────────────────────────────────
    # Jha PN, VS Y, MV B, Edwin L. (2026).
    # Environmental Burden of Fishing: Assessment of Fuel Consumption and the
    # Carbon Footprint by Mechanized Fishing Vessels Operating in the
    # Southeastern Arabian Sea.
    # Thalassas: An International Journal of Marine Sciences, 42, Article 18.
    # DOI: 10.1007/s41208-025-01026-8

    jha_citation = (
        'Jha PN, VS Y, MV B, Edwin L. (2026). '
        'Environmental burden of fishing: Assessment of fuel consumption and the '
        'carbon footprint by mechanized fishing vessels operating in the '
        'southeastern Arabian Sea. '
        'Thalassas: Int. J. Mar. Sci. 42:18. DOI:10.1007/s41208-025-01026-8'
    )

    # LL small-scale, SE Arabian Sea (Row 13): 234-256 days for 16-20m vessels
    add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 2: Jha LL Indian Ocean',
            'Asia', 'LL', 'APW', '<12m', 245, 234, 256,
            'days/year', 'Triangular', jha_citation,
            'R13',
            'Tier 2 — 印度洋机械化延绳钓 (Jha et al. 2026): '
            '234-256 days/year, Best=245 (midpoint). '
            '16-20m mechanized longline-cum-gillnet vessels, SE Arabian Sea. '
            '提供最新区域时间切片, 比历史基线更能反映当前捕捞努力量. '
            '地理映射: Indian Ocean → Asia (南亚/阿拉伯海沿岸).')

    # ──────────────────────────────────────────────────────────────
    # Tier 3: Anticamara et al. (2011) — Historical Baseline (ALL flags, ALL sectors)
    # ──────────────────────────────────────────────────────────────
    # Anticamara JA, Watson R, Gelchu A, Pauly D. (2011).
    # Global fishing effort (1950-2010): Trends, gaps, and implications.
    # Fisheries Research, 107(1-3), 131-136.
    # DOI: 10.1016/j.fishres.2010.10.016

    anticamara_citation = (
        'Anticamara JA, Watson R, Gelchu A, Pauly D. (2011). '
        'Global fishing effort (1950-2010): Trends, gaps, and implications. '
        'Fish. Res. 107(1-3):131-136. DOI:10.1016/j.fishres.2010.10.016'
    )

    # Longline DAS by continent (Row 7) — Tier 3 fallback
    ll_das = {
        'Africa': 274, 'Asia': 334, 'Australia & Oceania': 334,
        'Europe': 304, 'North America': 304, 'South America': 304,
    }
    for region, das in ll_das.items():
        add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 3: Anticamara LL',
                region, 'LL', 'ALL', 'ALL', das, np.nan, np.nan,
                'days/year', 'Triangular', anticamara_citation,
                'R7',
                f'Tier 3 — LL {region} (Anticamara et al. 2011): {das} days/year. '
                '宏观历史基线 (1950-2010), Flag=ALL, Sector=ALL. '
                '适用于缺乏高精度区域数据的延绳钓船队历史回溯.')

    # Purse Seine DAS by continent (Row 8) — Tier 3 fallback
    ps_das = {
        'Africa': 159, 'Asia': 195, 'Australia & Oceania': 195,
        'Europe': 177, 'North America': 177, 'South America': 177,
    }
    for region, das in ps_das.items():
        add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 3: Anticamara PS',
                region, 'PS', 'ALL', 'ALL', das, np.nan, np.nan,
                'days/year', 'Triangular', anticamara_citation,
                'R8',
                f'Tier 3 — PS {region} (Anticamara et al. 2011): {das} days/year. '
                '宏观历史基线 (1950-2010), Flag=ALL, Sector=ALL. '
                '适用于1990年前(无FAD)围网船队历史回溯或缺乏Parker数据的区域.')

    # PS China expert consultation (Row 9) — specific override
    add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — China PS expert',
            'Asia', 'PS', 'I', 'ALL', 200, np.nan, np.nan,
            'days/year', 'Triangular',
            'Expert consultation (谢斌老师咨询) — China PS fleet. '
            'Overrides Anticamara Asia PS (195 days) for Chinese-flagged vessels.',
            'R9',
            'China-specific PS DAS=200, 高于亚洲区域均值(195). '
            '适用于中国籍围网船, 覆盖Anticamara Asia PS条目.')

    # Transport vessel (Row 10) — Anticamara inferred
    add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Transport vessel',
            'ALL', 'TP', 'I', 'ALL', 180, np.nan, np.nan,
            'days/year', 'Triangular',
            'Inferred from Sheet 1 Row 10: "Transport 15 days per month" '
            '→ 15×12=180 days/year. '
            'Reference: Anticamara et al. (2011) for non-fishing vessel DAS baseline.',
            'R10',
            'Transport/refrigerated carrier vessel (转运船/冷藏运输船). '
            '15 days/month × 12 = 180 days/year.')

    # ──────────────────────────────────────────────────────────────
    # ALL-region fallbacks (computed as mean of region-specific values)
    # ──────────────────────────────────────────────────────────────
    # NOTE: For PS, the ALL fallback includes both Parker (Tier 1) ocean values
    # AND Anticamara (Tier 3) continent values → use with caution.
    # Prefer Parker mean ({parker_mean}) for modern PS; use Anticamara mean for pre-1990.
    for gear, gear_label in [('LL', 'Longline'), ('PS', 'Purse Seine'), ('TP', 'Transport')]:
        gear_vals = [r['Value_Best'] for r in rows
                     if r['Param_Code'] == 'T_map_DAS' and r['Gear'] == gear
                     and r['Flag'] != 'ALL']
        if gear_vals:
            mean_das = round(np.mean(gear_vals), 1)
            add_row('B', 'T_map_DAS', '年出海天数 (Days at Sea)',
                    'ALL', gear, 'ALL', 'ALL', mean_das, np.nan, np.nan,
                    'days/year', 'Triangular', anticamara_citation,
                    'R7-R11',
                    f'ALL-region fallback: mean of {len(gear_vals)} regional values '
                    f'= {mean_das} days/year. '
                    'Use when vessel Flag does not match any specific region/ocean. '
                    'Note for PS: includes both Parker (ocean) and Anticamara (continent) values.')

    # ------------------------------------------------------------------
    # B2. H_day — Daily Engine Hours (H_map) — Row 14-19
    # ------------------------------------------------------------------
    # Row 14: Detailed time breakdown (Bastos et al. 2021): transit 18.7%, fishing 81.3%
    #         → [TIME PROPORTIONS, NOT engine hours directly]
    # Row 15: PS ghg_lca engine=4h, auxiliary=15h (Korican et al. 2023)
    # Row 16: "24h(Industrial) 4h(Smallscale)" — general guidance
    # Row 17: "出海行程时长 (Trip duration) | 6h"
    # Row 18: "24h(Industrial)"
    # Row 19: "6h(Smallscale)"
    #
    # Current model (ghg_lca.py) uses: H_map = {'LL': 6, 'PS': 24, 'TS': 24}
    # This is a simplified approach. The Prior_Matrix records provide a more
    # nuanced Sector-aware parameterization for future model refinement.

    # Industrial: 24h continuous deep-sea operation
    add_row('B', 'H_map_Hday', '日主机运行小时数 (Daily Engine Hours)',
            'ALL', 'ALL', 'I', 'ALL', 24.0, np.nan, np.nan,
            'h/day', 'Triangular',
            'Greer et al. (2019) Mar. Policy 107:103382; '
            'Korican et al. (2023) Ocean Eng. 286:115734',
            'R16,R18',
            'Industrial: 24h continuous deep-sea operation (Row 16, Row 18).')

    # APW: 12h coastal daytime (based on PNAS α-analysis, median ~9h → 12h)
    add_row('B', 'H_map_Hday', '日主机运行小时数 (Daily Engine Hours)',
            'ALL', 'ALL', 'APW', 'ALL', 12.0, 4.0, 12.0,
            'h/day', 'Triangular',
            'Greer et al. (2019) smallscale=4h (Row 16, Row 19); '
            'PNAS α-analysis: observed median ~9h/day → 12h (half of Industrial)',
            'R16,R19',
            'APW: coastal daytime operation. Sheet 1 says 4-6h (Row 16, 19), '
            'but PNAS empirical data shows median ~9h. '
            '保守取12h作为最佳估计, 4h作为下限.')

    # PS-specific: ghg_lca engine vs auxiliary (Row 15, Korican et al. 2023)
    add_row('B', 'H_map_Main_PS', 'PS主机日运行小时数',
            'ALL', 'PS', 'I', 'ALL', 4.0, np.nan, np.nan,
            'h/day', 'Triangular',
            'Korican et al. (2023) Ocean Eng. 286:115734',
            'R15',
            'PS ghg_lca engine: ~4h/day (short high-power bursts for setting/hauling).')
    add_row('B', 'H_map_Aux_PS', 'PS辅机日运行小时数',
            'ALL', 'PS', 'I', 'ALL', 15.0, np.nan, np.nan,
            'h/day', 'Triangular',
            'Korican et al. (2023) Ocean Eng. 286:115734',
            'R15',
            'PS auxiliary engine: ~15h/day (hydraulic pumps, refrigeration, lighting).')

    # ------------------------------------------------------------------
    # B3. Load Factors (LF_move, LF_work) — Row 20-28
    # ------------------------------------------------------------------
    # CRITICAL FIX (v2): Bastos et al. (2021) describes Brazilian BOTTOM longline,
    # which is small-scale. Load factors from Bastos map to APW, NOT Industrial.
    #
    # Source mapping:
    #   Row 20-21: Detailed load profile for a specific vessel (~31kW total)
    #   Row 22: Eyring et al. (2005) — operating mode definitions
    #           Berthing ~0%, Manoeuvring <20%, Low-cruise 20-65%, Cruise ≥65%
    #   Row 23: Eyring et al. (2005) — Load F_MCR=80%, 2500h/yr (non-cargo ships)
    #   Row 24: Eyring et al. (2005) — Load F_MCR=65-75%, 3000h/yr (non-cargo)
    #   Row 25: Generator 450kVA operating profile (specific vessel data)
    #   Row 26: "0.85" — load factor or efficiency coefficient (source unclear)
    #   Row 27: Perčić et al. (2020) — Main=0.8, Aux=0.5 (general marine engines)
    #   Row 28: Kim et al. (2023) — Coastal 79%/19%, Offshore 73%/20%, Other 76%/14%

    # --- Industrial Longline ---
    add_row('B', 'LF_move', '航行阶段发动机负荷因子 (Transit Load Factor)',
            'ALL', 'LL', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) JGR 112:D12305 — cruise MCR≥65%, typical load 80%',
            'R22-R23',
            'LL Industrial transit: 80% MCR cruise (Eyring et al. 2005, Row 22-23).')

    add_row('B', 'LF_work', '捕捞作业阶段发动机负荷因子 (Fishing Load Factor)',
            'ALL', 'LL', 'I', 'ALL', 0.50, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Perčić et al. (2020) — general marine auxiliary engines, Aux=0.5',
            'R27',
            'LL Industrial fishing: Aux=0.5 (Perčić et al. 2020, Row 27). '
            'Fishing phase uses auxiliary engines at ~50% load for hauling gear. '
            'NOTE: Bastos et al. (2021) is SMALL-SCALE (see APW entries below).')

    # --- Industrial Purse Seine ---
    add_row('B', 'LF_move', '航行阶段发动机负荷因子 (Transit Load Factor)',
            'ALL', 'PS', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) JGR 112:D12305 — cruise MCR≥65%, typical load 80%',
            'R22-R23',
            'PS Industrial transit: 80% MCR cruise (same as LL).')

    add_row('B', 'LF_work', '捕捞作业阶段发动机负荷因子 (Fishing Load Factor)',
            'ALL', 'PS', 'I', 'ALL', 0.65, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) JGR 112:D12305 — non-cargo ships, load 65-75%',
            'R24',
            'PS Industrial fishing: 65% MCR (Eyring non-cargo 65-75%, Row 24). '
            'Higher than LL because PS uses hydraulics during setting/hauling.')

    # --- Industrial Transport ---
    add_row('B', 'LF_move', '航行阶段发动机负荷因子 (Transit Load Factor)',
            'ALL', 'TP', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) — general vessel cruise parameters',
            'R22-R23',
            'Transport vessel transit: 80% MCR cruise.')

    add_row('B', 'LF_work', '捕捞作业阶段发动机负荷因子 (Fishing Load Factor)',
            'ALL', 'TP', 'I', 'ALL', 0.50, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Perčić et al. (2020) — general marine auxiliary engines, Aux=0.5',
            'R27',
            'Transport vessel operations (transshipment, refrigeration): Aux=0.5.')

    # --- APW / Small-scale ---
    # Kim et al. (2023) JMSE 11:1488 — Korean coastal small fishing vessels
    # Row 28: Coastal 79%/19%, Offshore 73%/20%, Other 76%/14%
    # Using coastal as best estimate for APW sector.
    # Bastos et al. (2021) — Brazilian bottom longline (Row 13-14) provides
    #   additional time-breakdown context for small-scale LL operations.

    add_row('B', 'LF_move', '航行阶段发动机负荷因子 (Transit Load Factor)',
            'ALL', 'ALL', 'APW', 'ALL', 0.79, 0.73, 0.80,
            'fraction of MCR', 'Triangular',
            'Kim et al. (2023) JMSE 11:1488 — coastal small fishing vessels',
            'R28',
            'APW transit: Coastal vessels 79% load (Row 28). '
            'Range 73-80% covers coastal-to-offshore variation.')

    add_row('B', 'LF_work', '捕捞作业阶段发动机负荷因子 (Fishing Load Factor)',
            'ALL', 'ALL', 'APW', 'ALL', 0.19, 0.14, 0.20,
            'fraction of MCR', 'Triangular',
            'Kim et al. (2023) JMSE 11:1488 — coastal small fishing vessels',
            'R28',
            'APW fishing: Coastal vessels 19% load (Row 28). '
            'Range 14-20% covers coastal-to-other variation. '
            'Bastos et al. (2021) time breakdown (Row 13-14): '
            'LL small-scale spends 81.3% time in fishing phase, '
            'but engine load during this phase is low (~19%).')

    # --- Industrial general fallback ---
    add_row('B', 'LF_move', '航行阶段发动机负荷因子 (Transit Load Factor)',
            'ALL', 'ALL', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) + Perčić et al. (2020) — general marine engines',
            'R22-R23,R27',
            'General Industrial fallback: 80% MCR cruise.')

    add_row('B', 'LF_work', '捕捞作业阶段发动机负荷因子 (Fishing Load Factor)',
            'ALL', 'ALL', 'I', 'ALL', 0.50, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Perčić et al. (2020) — general marine auxiliary engines, Aux=0.5',
            'R27',
            'General Industrial fallback: 50% aux load.')

    # ========================================================================
    # C. 核心燃料与排放参数 (Core Fuel & Emission) — Sheet 1 Row 30-43
    # ========================================================================

    # ------------------------------------------------------------------
    # C1. SFR — Specific Fuel Consumption Rate — Row 31-37
    # ------------------------------------------------------------------
    # Row 31: 0.00020 tFuel/kWh (Industrial) — Endresen et al. (2007)
    # Row 32: 0.00035 tFuel/kWh (Smallscale) — Winther (2007)
    # Row 33: Diesel: 224.69 g/kWh (reference value)
    # Row 34: Methanol-diesel 80%: 438.58 g/kWh
    # Row 35: H2-diesel 80%: 112.32 g/kWh
    # Row 36: Main engine diesel: 215 g/kWh (Sustainable Ships 2022)
    # Row 37: Aux engine diesel: 210 g/kWh (Sustainable Ships 2022)

    sfr_source_main = 'Endresen et al. (2007) JGR 112:D12305; Sustainable Ships (2022)'

    # Industrial SFR (>=12m, diesel)
    add_row('C', 'SFR_map', '特定燃油消耗率 (Specific Fuel Consumption Rate)',
            'ALL', 'ALL', 'I', '>=12m', 0.000200, 0.000155, 0.000250,
            'tFuel/kWh', 'Lognormal',
            sfr_source_main,
            'R31,R36',
            'Industrial ghg_lca engine diesel: 200 g/kWh = 0.00020 t/kWh. '
            'Range 155-250 g/kWh from literature. '
            'Row 31: 0.00020 tFuel/kWh; Row 36: ghg_lca=215 g/kWh.')

    # Smallscale SFR (<12m, gasoline/diesel mix)
    add_row('C', 'SFR_map', '特定燃油消耗率 (Specific Fuel Consumption Rate)',
            'ALL', 'ALL', 'APW', '<12m', 0.000350, 0.000250, 0.000450,
            'tFuel/kWh', 'Lognormal',
            'Winther (2007) Danish navigation emissions; Greer et al. (2019)',
            'R32',
            'Smallscale: 350 g/kWh. Higher SFR due to less efficient small engines. '
            'Range 250-450 g/kWh. Row 32: 0.00035 tFuel/kWh.')

    # Main vs Aux diesel SFR (for detailed fuel modeling)
    add_row('C', 'SFR_Main_Diesel', '主机柴油特定燃油消耗率',
            'ALL', 'ALL', 'I', 'ALL', 0.000215, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sustainable Ships (2022)',
            'R36',
            'Main engine diesel: 215 g/kWh (Row 36).')

    add_row('C', 'SFR_Aux_Diesel', '辅机柴油特定燃油消耗率',
            'ALL', 'ALL', 'I', 'ALL', 0.000210, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sustainable Ships (2022)',
            'R37',
            'Auxiliary engine diesel: 210 g/kWh (Row 37).')

    # Alternative fuel SFR (for scenario modeling — S4, S14)
    add_row('C', 'SFR_Methanol_Diesel_80', '甲醇-柴油混合 (80%能量替代) SFR',
            'ALL', 'ALL', 'ALL', 'ALL', 0.000439, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sheet 1 Row 34',
            'R34',
            '438.58 g/kWh = 0.000439 t/kWh. Used in scenario S4, S14.')

    add_row('C', 'SFR_H2_Diesel_80', '氢-柴油混合 (80%能量替代) SFR',
            'ALL', 'ALL', 'ALL', 'ALL', 0.000112, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sheet 1 Row 35',
            'R35',
            '112.32 g/kWh = 0.000112 t/kWh. Used in scenario S14.')

    # ------------------------------------------------------------------
    # C1b. SFOC-负荷转换公式 (柴油机负荷-油耗拟合) — Row 30
    # ------------------------------------------------------------------
    # Row 30: SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28)
    #   L = 发动机负荷因子 (Load Factor, fraction of rated power)
    #   适用条件: ≥12m, 四冲程柴油主机
    #   来源: Jalkanen et al. (2012) ACP 12:2641-2659
    #   示例计算:
    #     L=0.80 (巡航): factor = 0.455×0.64 − 0.71×0.80 + 1.28 = 1.003
    #     L=0.50 (LL作业): factor = 0.455×0.25 − 0.71×0.50 + 1.28 = 1.039
    #     L=0.19 (APW作业): factor = 0.455×0.0361 − 0.71×0.19 + 1.28 = 1.162

    add_row('C', 'SFOC_LOAD_COEFF_A', 'SFOC-负荷二次项系数 (L²)',
            'ALL', 'ALL', 'ALL', '>=12m', 0.455, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Jalkanen et al. (2012) Atmos. Chem. Phys. 12:2641-2659',
            'R30',
            'SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28). '
            '仅适用于≥12m四冲程柴油主机。L=发动机负荷因子(LF, 额定功率比例).')

    add_row('C', 'SFOC_LOAD_COEFF_B', 'SFOC-负荷一次项系数 (L)',
            'ALL', 'ALL', 'ALL', '>=12m', -0.71, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Jalkanen et al. (2012) Atmos. Chem. Phys. 12:2641-2659',
            'R30',
            '一次项系数。抛物线公式在L=0.78附近取最小值(最经济工况).')

    add_row('C', 'SFOC_LOAD_COEFF_C', 'SFOC-负荷常数项系数',
            'ALL', 'ALL', 'ALL', '>=12m', 1.28, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Jalkanen et al. (2012) Atmos. Chem. Phys. 12:2641-2659',
            'R30',
            '常数项。L=0(怠速)时SFOC为基准值的1.28倍; L=1(全负荷)时≈1.025倍.')

    add_row('C', 'SFOC_LOAD_APPLICABILITY', 'SFOC-负荷公式适用范围',
            'ALL', 'ALL', 'I', '>=12m', 1.0, np.nan, np.nan,
            'binary flag', 'Discrete',
            'Jalkanen et al. (2012); 仅适用于≥12m四冲程柴油主机',
            'R30',
            '1=适用。辅机应使用固定高效负荷(75%)+固定SFR(220 g/kWh)，不适用此公式。')

    # ------------------------------------------------------------------
    # C2. Emission Factors (EF) — Row 38, 40-42
    # ------------------------------------------------------------------
    # Row 38: CO2=3206 g/kgfuel, CH4=0.019 g/kgfuel, N2O=0.14 g/kgfuel
    #         (Korican et al. 2023)
    # Row 40: 3.17 tCO2/tFuel (Industrial diesel)
    # Row 41: 3.01 tCO2/tFuel (Smallscale gasoline)
    # Row 42: 3.1 kg CO2-e/L (per-litre reference)

    # ------------------------------------------------------------------
    # C2a. Upstream (Well-to-Tank, WTT) Emission Factors — ecoinvent v3
    # ------------------------------------------------------------------
    # 燃料上游生产/运输过程的间接碳排放因子。
    # 来源: ecoinvent v3 cutoff 数据库, 1000次蒙特卡洛模拟。
    # 单位: kg CO₂eq / kg fuel (功能单位 = 1 kg 燃料供应)

    add_row('C', 'EF_WTT_DIESEL', '柴油上游(WTT)碳排放因子',
            'ALL', 'ALL', 'ALL', 'ALL', 0.369, 0.318, 0.441,
            'kg CO₂eq/kg diesel', 'Lognormal',
            'Ecoinvent v3 — market for diesel | diesel | Cutoff, U - RoW '
            '(1000 MC simulations)',
            'Ecoinvent_Diesel_WTT',
            '1 kg 柴油上游生产与运输碳排放 (Cradle-to-Tank)。'
            '过程: market for diesel | Cutoff, U - RoW。'
            'Mean=0.369, SD=0.031, Median=0.366, 95% CI [0.318, 0.441]. '
            '此因子与燃烧因子(EF_CO2_Diesel)相加得到完整Well-to-Wake排放。')

    add_row('C', 'EF_WTT_GASOLINE', '汽油上游(WTT)碳排放因子',
            'ALL', 'ALL', 'APW', 'ALL', 0.535, 0.489, 0.595,
            'kg CO₂eq/kg petrol', 'Lognormal',
            'Ecoinvent v3 — market for petrol, two-stroke blend | '
            'petrol, two-stroke blend | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_Gasoline_WTT',
            '1 kg 汽油上游生产与运输碳排放 (Cradle-to-Tank)。'
            '过程: market for petrol, two-stroke blend | Cutoff, U - GLO。'
            'Mean=0.535, SD=0.029, Median=0.532, 95% CI [0.489, 0.595]. '
            '此因子与燃烧因子(EF_CO2_Gasoline)相加得到完整Well-to-Wake排放。')

    # ------------------------------------------------------------------
    # C2b. Combustion (Tank-to-Wake, TTW) — CO₂ Emission Factors
    # ------------------------------------------------------------------
    # 燃料燃烧直接CO₂排放因子。

    # CO2 from diesel — IMO (2020) Fourth GHG Study
    add_row('C', 'EF_CO2_Diesel', '柴油CO₂燃烧排放因子',
            'ALL', 'ALL', 'I', 'ALL', 3.206, 3.206, 3.206,
            'tCO2/tFuel', 'Discrete',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            '船用轻柴油(MDO)燃烧CO₂排放因子。'
            '基于碳元素质量占比(~87.44%)化学计量完全氧化方程计算的无量纲转换系数(CF)。'
            '3.206 kg CO₂/kg diesel = 3206 g/kgFuel. '
            '原值: 3.17 (Korican 2023), 更新为IMO官方值.')

    # CO2 from gasoline — EPA (2025)
    add_row('C', 'EF_CO2_Gasoline', '汽油CO₂燃烧排放因子',
            'ALL', 'ALL', 'APW', 'ALL', 3.158, np.nan, np.nan,
            'tCO2/tFuel', 'Normal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Climate Leadership. Washington, DC.',
            'EPA_2025',
            '车用/船用汽油燃烧CO₂排放因子。'
            '原始: 8.78 kg/gallon ÷ 2.78 kg/gallon = 3.158 kg CO₂/kg 汽油。'
            '来源: EPA Table 2 Mobile Combustion CO2, Motor Gasoline. '
            '原值: 3.01, 更新为EPA官方值.')

    # ------------------------------------------------------------------
    # C2c. Combustion — CH₄ (Methane) Emission Factors
    # ------------------------------------------------------------------
    # 甲烷排放因发动机冲程技术和燃料类型差异显著, 按燃料和机型分别设定。

    # Diesel CH4 — IMO (2020) Fourth GHG Study (g/kWh, IMO标准单位)
    add_row('C', 'EF_CH4_DIESEL_MSD', '柴油CH₄排放因子—中速四冲程(MSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.010, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            '中速柴油机 (Medium-Speed Diesel, MSD) 甲烷逃逸因子。'
            '远洋渔船绝大多数采用中速四冲程柴油机，适用于主力渔船和辅机。'
            '0.010 g/kWh (IMO标准单位).')

    add_row('C', 'EF_CH4_DIESEL_SSD', '柴油CH₄排放因子—低速二冲程(SSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.010, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            '低速柴油机 (Slow-Speed Diesel, SSD) 甲烷逃逸因子。'
            '适用于大型转运船主机。'
            '0.010 g/kWh (IMO标准单位).')

    # Gasoline CH4 — EPA (2025) Table 5, Ships and Boats
    add_row('C', 'EF_CH4_GASOLINE_2STROKE', '汽油CH₄排放因子—二冲程舷外机',
            'ALL', 'ALL', 'APW', 'ALL', 3.76, np.nan, np.nan,
            'g/kgFuel', 'Lognormal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Table 5: Mobile Combustion CH4 and N2O for Non-Road Vehicles, Ships and Boats.',
            'EPA_2025',
            '老式二冲程汽油舷外机甲烷排放因子。'
            '原始: 10.45 g/gallon ÷ 2.78 kg/gallon = 3.76 g CH₄/kg 汽油. '
            '二冲程发动机因扫气过程导致未燃碳氢化合物(含CH₄)逃逸量显著偏高.')

    add_row('C', 'EF_CH4_GASOLINE_4STROKE', '汽油CH₄排放因子—四冲程舷外机',
            'ALL', 'ALL', 'APW', 'ALL', 1.50, np.nan, np.nan,
            'g/kgFuel', 'Lognormal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Table 5: Mobile Combustion CH4 and N2O for Non-Road Vehicles, Ships and Boats.',
            'EPA_2025',
            '现代四冲程汽油舷外机甲烷排放因子。'
            '原始: 4.18 g/gallon ÷ 2.78 kg/gallon = 1.50 g CH₄/kg 汽油. '
            '四冲程机燃烧更完全, CH₄排放约为二冲程的40%.')

    # ------------------------------------------------------------------
    # C2d. Combustion — N₂O (Nitrous Oxide) Emission Factors
    # ------------------------------------------------------------------

    add_row('C', 'EF_N2O_DIESEL_MSD', '柴油N₂O排放因子—中速四冲程(MSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.030, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            '中速柴油机 (MSD) N₂O排放因子。'
            '适用于主力渔船和辅机。'
            '0.030 g/kWh (IMO标准单位). '
            '原通用值: 0.14 g/kgFuel (Korican 2023).')

    add_row('C', 'EF_N2O_DIESEL_SSD', '柴油N₂O排放因子—低速二冲程(SSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.020, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            '低速柴油机 (SSD) N₂O排放因子。'
            '适用于大型转运船主机。'
            '0.020 g/kWh (IMO标准单位).')

    add_row('C', 'EF_N2O_GASOLINE', '汽油N₂O排放因子',
            'ALL', 'ALL', 'APW', 'ALL', 0.04, np.nan, np.nan,
            'g/kgFuel', 'Lognormal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Table 5: Mobile Combustion CH4 and N2O for Non-Road Vehicles, Ships and Boats.',
            'EPA_2025',
            '汽油机N₂O排放因子（二冲程与四冲程无显著差异, EPA统一基准）。'
            '原始: 0.11 g/gallon ÷ 2.78 kg/gallon = 0.04 g N₂O/kg 汽油.')

    # ------------------------------------------------------------------
    # C3. GWP — Global Warming Potential — Row 39
    # ------------------------------------------------------------------
    add_row('C', 'GWP_CH4_100yr', '甲烷 100年全球增温潜势',
            'ALL', 'ALL', 'ALL', 'ALL', 28.5, 27.0, 30.0,
            'kgCO2e/kgCH4', 'Uniform',
            'IPCC AR5/AR6; Sheet 1 Row 39',
            'R39',
            'CH4 GWP-100: IPCC range 27-30, midpoint 28.5 (Row 39).')

    add_row('C', 'GWP_N2O_100yr', '氧化亚氮 100年全球增温潜势',
            'ALL', 'ALL', 'ALL', 'ALL', 273.0, np.nan, np.nan,
            'kgCO2e/kgN2O', 'Discrete',
            'IPCC AR6; Sheet 1 Row 39',
            'R39',
            'N2O GWP-100: 273 (IPCC AR6, Row 39).')

    # ------------------------------------------------------------------
    # C4. FC_LOOKUP — Fuel Coefficient time series — Row 43
    # ------------------------------------------------------------------
    add_row('C', 'FC_LOOKUP_Baseline_Year', '燃料效率时间系数基准年份',
            'ALL', 'ALL', 'ALL', 'ALL', 2000, np.nan, np.nan,
            'year', 'Discrete',
            'Yanmar marine engine data (interpolated); Sheet 1 Row 43',
            'R43',
            'FC=1.0 at year 2000 (baseline). Pre-2000 >1.0 (less efficient), '
            'post-2004 =0.99 (stable). Row 43.')

    add_row('C', 'FC_LOOKUP_Min', '燃料效率时间系数最小值',
            'ALL', 'ALL', 'ALL', 'ALL', 0.99, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Yanmar data; 2004-2016 stable period',
            'R43',
            'Minimum FC = 0.99 (most efficient era, 2004-2016). Row 43.')

    add_row('C', 'FC_LOOKUP_Max', '燃料效率时间系数最大值',
            'ALL', 'ALL', 'ALL', 'ALL', 1.21, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Yanmar data; 1950-1951 peak',
            'R43',
            'Maximum FC = 1.21 (least efficient era, 1950-1951). Row 43.')

    # ========================================================================
    # D. 辅机功率参数 (Auxiliary Engine Power Ratio) — Sheet 1 Row 44-46
    # ========================================================================
    # Row 44: Overall aux ≈ 38.8% of ghg_lca power
    # Row 45: Detailed ship comparison data (short vs long routes)
    # Row 46: Three-tier classification by GT and age:
    #   - GT>1500 → 0.33-0.40 (large, heavy hydraulics + cold storage)
    #   - 500<GT<=1500 + post-1990 → 0.25-0.33 (medium, transitional)
    #   - GT<=500 or pre-1990 → 0.15-0.25 (small/old, minimal cold storage)

    add_row('D', 'AUX_POWER_RATIO', '辅机/主机功率比 (总体均值)',
            'ALL', 'ALL', 'ALL', 'ALL', 0.388, 0.33, 0.54,
            'ratio', 'Triangular',
            'Sheet 1 Row 44-46',
            'R44',
            'Overall mean: aux = 38.8% of ghg_lca power. '
            'Range: 0.33 (25/75 split, Row 46) to 0.54 (extreme).')

    add_row('D', 'AUX_POWER_RATIO_LARGE', '辅机/主机功率比 (大型船 GT>1500)',
            'ALL', 'ALL', 'ALL', '>=12m', 0.365, 0.33, 0.40,
            'ratio', 'Triangular',
            'Sheet 1 Row 46 — size-mandated high-power category',
            'R46',
            'Large vessels (GT>1500): heavy hydraulics + large cold storage '
            '→ aux ratio forced into 0.33-0.40.')

    add_row('D', 'AUX_POWER_RATIO_MEDIUM',
            '辅机/主机功率比 (中型船 500<GT<=1500, post-1990)',
            'ALL', 'ALL', 'ALL', 'ALL', 0.29, 0.25, 0.33,
            'ratio', 'Triangular',
            'Sheet 1 Row 46 — transitional category',
            'R46',
            'Medium vessels (500<GT<=1500, post-1990): modern equipment '
            '→ aux ratio 0.25-0.33.')

    add_row('D', 'AUX_POWER_RATIO_SMALL',
            '辅机/主机功率比 (小型/老旧船 GT<=500 or pre-1990)',
            'ALL', 'ALL', 'ALL', '<12m', 0.20, 0.15, 0.25,
            'ratio', 'Triangular',
            'Sheet 1 Row 46 — dual-low category',
            'R46',
            'Small/old vessels (GT<=500 or pre-1990): no large cold storage '
            '→ aux ratio 0.15-0.25.')

    # ========================================================================
    # E. 船体材料与建造参数 (Hull Material & Construction) — Sheet 1 Row 70-84
    # ========================================================================

    # ------------------------------------------------------------------
    # E1. Material Ratios — Row 72-73
    # ------------------------------------------------------------------
    # Row 72: Detailed material composition per kg catch (围网船体材料组成比例)
    # Row 73: "船体钢材占LSW 80%、其余20%为其他结构和系统
    #         （10%看作发动机，5%看作铜即电力系统）"
    # Model (ghg_lca.py): STEEL=0.85, ENGINE=0.10, COPPER=0.05
    # Note: 80% of LSW is steel hull; remaining 20% = 10% engine + 5% copper + 5% other
    # The model normalizes to: steel=85%, engine=10%, copper=5% (sum=100%)

    add_row('E', 'MATERIAL_RATIO_STEEL', '船体钢材质量占比',
            'ALL', 'ALL', 'ALL', 'ALL', 0.85, np.nan, np.nan,
            'fraction of GT', 'Normal',
            'Sheet 1 Row 72-73; ghg_lca.py model constants',
            'R72-R73',
            'Steel hull = 85% of GT. Row 73: "船体钢材占LSW 80%". '
            'Row 72: detailed composition confirms ~90% steel for PS hull.')

    add_row('E', 'MATERIAL_RATIO_ENGINE', '发动机铸铁质量占比',
            'ALL', 'ALL', 'ALL', 'ALL', 0.10, np.nan, np.nan,
            'fraction of GT', 'Normal',
            'Sheet 1 Row 73; ghg_lca.py model constants',
            'R73',
            'Engine iron/steel = 10% of GT. Row 73: "10%看作发动机".')

    add_row('E', 'MATERIAL_RATIO_COPPER', '电力系统铜材质量占比',
            'ALL', 'ALL', 'ALL', 'ALL', 0.05, np.nan, np.nan,
            'fraction of GT', 'Normal',
            'Sheet 1 Row 73; ghg_lca.py model constants',
            'R73',
            'Copper = 5% of GT. Row 73: "5%看作铜即电力系统".')

    # ------------------------------------------------------------------
    # E2. Material Emission Factors — Row 68-71
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # E2b. Vessel Construction Emission Factors (cradle-to-gate, ecoinvent LCA)
    # ------------------------------------------------------------------
    # 以下建造碳排放因子来自 ecoinvent v3 cutoff 数据库，
    # 每个过程运行1000次蒙特卡洛模拟提取统计量。
    # 单位: kg CO₂eq / kg vessel (功能单位 = 1 kg 船舶建造)
    #
    # 适用范围说明 (per user instruction):
    #   - 转运船/辅助船 (TS): 统一使用围网钢船因子
    #   - 延绳钓小船 (<12m, 木质): 统一使用围网木船因子
    #   - 延绳钓大船 (>=12m, 钢质): 使用延绳钓钢船专用因子

    # PS steel construction (>=12m) — also applies to TS/aux
    add_row('E', 'EF_BUILD_PS_STEEL', '围网钢船建造碳排放因子 (cradle-to-gate)',
            'ALL', 'PS', 'I', '>=12m',
            2.421, 2.332, 2.528,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Steel',
            '1 kg purse seiner steel construction. '
            'Mean=2.421, SD=0.052, Median=2.415, 95% CI [2.332, 2.528]. '
            'Also applies to: TS/auxiliary vessels (转运船/辅助船统一使用围网钢船因子).')

    # PS wood construction (<12m) — also applies to LL small boats, TS/aux small
    add_row('E', 'EF_BUILD_PS_WOOD', '围网木船建造碳排放因子 (cradle-to-gate)',
            'ALL', 'PS', 'APW', '<12m',
            0.578, 0.513, 0.678,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner, wood | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Wood',
            '1 kg purse seiner wood construction. '
            'Mean=0.578, SD=0.040, Median=0.575, 95% CI [0.513, 0.678]. '
            'Also applies to: LL small boats <12m (延绳钓小船), '
            'TS/aux small boats (转运船/辅助船小船).')

    # LL steel construction (>=12m)
    add_row('E', 'EF_BUILD_LL_STEEL', '延绳钓钢船建造碳排放因子 (cradle-to-gate)',
            'ALL', 'LL', 'I', '>=12m',
            1.956, 1.877, 2.069,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Ecoinvent v3 — market for long liner, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_LL_Steel',
            '1 kg long liner steel construction. '
            'Mean=1.956, SD=0.052, Median=1.949, 95% CI [1.877, 2.069].')

    # LL wood construction (<12m) — same as PS wood
    add_row('E', 'EF_BUILD_LL_WOOD', '延绳钓木船建造碳排放因子 (同围网木船)',
            'ALL', 'LL', 'APW', '<12m',
            0.578, 0.513, 0.678,
            'kg CO₂eq/kg vessel', 'Lognormal',
            '同 EF_BUILD_PS_WOOD — 延绳钓小船建造维护因子使用围网木船因子',
            'Ecoinvent_PS_Wood',
            '延绳钓小船 (<12m, 木质) 建造碳排放: 同围网木船因子 0.578 kg CO₂eq/kg. '
            'Per user instruction: 延绳钓小船的建造维护因子使用围网木船的因子.')

    # TS/aux construction — same as PS steel
    add_row('E', 'EF_BUILD_TS', '转运船/辅助船建造碳排放因子 (同围网钢船)',
            'ALL', 'TP', 'I', 'ALL',
            2.421, 2.332, 2.528,
            'kg CO₂eq/kg vessel', 'Lognormal',
            '同 EF_BUILD_PS_STEEL — 转运船和辅助船统一使用围网钢船因子',
            'Ecoinvent_PS_Steel',
            '转运船/辅助船建造碳排放: 同围网钢船因子 2.421 kg CO₂eq/kg. '
            'Per user instruction: 转运船和辅助船的建造和维护统一使用围网钢船的因子.')

    # ------------------------------------------------------------------
    # E2c. Vessel Maintenance Emission Factors (cradle-to-gate, ecoinvent LCA)
    # ------------------------------------------------------------------
    # 以下维护碳排放因子来自 ecoinvent v3 cutoff 数据库，
    # 每个过程运行1000次蒙特卡洛模拟提取统计量。
    # 单位: kg CO₂eq / kg vessel maintenance (功能单位 = 1 kg 船舶维护)

    # PS steel maintenance (>=12m) — also applies to TS/aux
    add_row('E', 'EF_MAINT_PS_STEEL', '围网钢船维护碳排放因子 (cradle-to-gate)',
            'ALL', 'PS', 'I', '>=12m',
            6.744, 6.627, 6.883,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner maintenance, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Steel_Maint',
            '1 kg purse seiner steel maintenance. '
            'Mean=6.744, SD=0.067, Median=6.740, 95% CI [6.627, 6.883]. '
            'Also applies to: TS/auxiliary vessels (转运船/辅助船统一使用围网钢船因子).')

    # PS wood maintenance (<12m) — also applies to LL small boats, TS/aux small
    add_row('E', 'EF_MAINT_PS_WOOD', '围网木船维护碳排放因子 (cradle-to-gate)',
            'ALL', 'PS', 'APW', '<12m',
            1.289, 1.179, 1.437,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner maintenance, wood | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Wood_Maint',
            '1 kg purse seiner wood maintenance. '
            'Mean=1.289, SD=0.065, Median=1.282, 95% CI [1.179, 1.437]. '
            'Also applies to: LL small boats <12m (延绳钓小船), '
            'TS/aux small boats (转运船/辅助船小船).')

    # LL steel maintenance (>=12m)
    add_row('E', 'EF_MAINT_LL_STEEL', '延绳钓钢船维护碳排放因子 (cradle-to-gate)',
            'ALL', 'LL', 'I', '>=12m',
            4.450, 3.777, 5.376,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Ecoinvent v3 — market for long liner maintenance, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_LL_Steel_Maint',
            '1 kg long liner steel maintenance. '
            'Mean=4.450, SD=0.385, Median=4.417, 95% CI [3.777, 5.376].')

    # LL wood maintenance (<12m) — same as PS wood
    add_row('E', 'EF_MAINT_LL_WOOD', '延绳钓木船维护碳排放因子 (同围网木船)',
            'ALL', 'LL', 'APW', '<12m',
            1.289, 1.179, 1.437,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            '同 EF_MAINT_PS_WOOD — 延绳钓小船建造维护因子使用围网木船因子',
            'Ecoinvent_PS_Wood_Maint',
            '延绳钓小船 (<12m, 木质) 维护碳排放: 同围网木船因子 1.289 kg CO₂eq/kg. '
            'Per user instruction: 延绳钓小船的建造维护因子使用围网木船的因子.')

    # TS/aux maintenance — same as PS steel
    add_row('E', 'EF_MAINT_TS', '转运船/辅助船维护碳排放因子 (同围网钢船)',
            'ALL', 'TP', 'I', 'ALL',
            6.744, 6.627, 6.883,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            '同 EF_MAINT_PS_STEEL — 转运船和辅助船统一使用围网钢船因子',
            'Ecoinvent_PS_Steel_Maint',
            '转运船/辅助船维护碳排放: 同围网钢船因子 6.744 kg CO₂eq/kg. '
            'Per user instruction: 转运船和辅助船的建造和维护统一使用围网钢船的因子.')

    # ------------------------------------------------------------------
    # E3. Lifespan Parameters — Row 78-82
    # ------------------------------------------------------------------
    # Row 78: "25% 用于维修保养"
    # Row 79: "船体钢材更换比例：每 2 年更换 12%"
    # Row 80: "船舶寿命30年；发动机在船舶寿命期内更换一次"
    # Row 81: "船体30年，主机10年；钢材用量增加25%（船体）和50%（主机）用于维修"
    # Row 82: "船体寿命（钢）：30年；船体寿命（木）：40年；发动机更换次数：1次"

    add_row('E', 'LIFESPAN_HULL', '船体寿命 (钢质)',
            'ALL', 'ALL', 'ALL', 'ALL', 30, np.nan, np.nan,
            'years', 'Discrete',
            'Sheet 1 Row 80-82',
            'R80-R82',
            'Steel hull lifespan: 30 years. '
            'Wood hull: 40yr (Row 82, not used in current model).')

    add_row('E', 'LIFESPAN_ENGINE', '发动机寿命 (更换周期)',
            'ALL', 'ALL', 'ALL', 'ALL', 10, np.nan, np.nan,
            'years', 'Discrete',
            'Sheet 1 Row 80-82',
            'R80-R82',
            'Engine lifespan: 10 years (Row 80-81). '
            'Replaced once during 30yr hull life = 2 engines total.')

    add_row('E', 'LIFESPAN_COPPER', '电力系统更新周期',
            'ALL', 'ALL', 'ALL', 'ALL', 8, np.nan, np.nan,
            'years', 'Discrete',
            'ghg_lca.py model constants; Ecoinvent reference',
            '—',
            '⚠ 未在Excel中找到直接来源。当前模型默认值: 8年。'
            'Copper electric system renewal cycle (wiring, switchgear).')

    # ------------------------------------------------------------------
    # E4. Maintenance Parameters — Row 78-81
    # ------------------------------------------------------------------
    add_row('E', 'MAINTENANCE_RATE_STEEL', '船体钢材每2年维护更换比例',
            'ALL', 'ALL', 'ALL', 'ALL', 0.12, np.nan, np.nan,
            'fraction per event', 'Discrete',
            'Sheet 1 Row 79',
            'R79',
            '每2年更换12%船体钢材 (Row 79). '
            'Model: is_steel_maint triggers every 2yr (skipping hull replacement years), '
            'replaces 12% of steel_w.')

    add_row('E', 'MAINTENANCE_INTERVAL_STEEL', '船体钢材维护间隔',
            'ALL', 'ALL', 'ALL', 'ALL', 2, np.nan, np.nan,
            'years', 'Discrete',
            'Sheet 1 Row 79; ghg_lca.py maint_interval=2',
            'R79',
            'Steel maintenance occurs every 2 years (Row 79).')

    add_row('E', 'MAINTENANCE_EXTRA_STEEL_PCT', '建造阶段钢材额外余量 (维修预留)',
            'ALL', 'ALL', 'ALL', 'ALL', 0.25, np.nan, np.nan,
            'fraction of base steel', 'Discrete',
            'Sheet 1 Row 81',
            'R81',
            '建造时钢材用量增加25%用于船体维修预留，50%用于主机维修预留 (Row 81).')

    # ------------------------------------------------------------------
    # E5. Anti-fouling Paint — Row 83-84
    # ------------------------------------------------------------------
    add_row('E', 'ANTIFOUL_PAINT_COATING_RATE', '防污漆平均涂布量',
            'ALL', 'ALL', 'ALL', 'ALL', 0.11, np.nan, np.nan,
            'L/tonne catch', 'Discrete',
            'Sheet 1 Row 83',
            'R83',
            '平均涂布量: 0.11 L/吨渔获 (Row 83). 涂刷频率: 每2年一次.')

    add_row('E', 'ANTIFOUL_PAINT_RELEASE_FRAC', '防污漆海洋释放比例',
            'ALL', 'ALL', 'ALL', 'ALL', 2.0 / 3.0, np.nan, np.nan,
            'fraction', 'Discrete',
            'Sheet 1 Row 83-84',
            'R83-R84',
            '2/3 of antifoul paint released to ocean environment (Row 83). '
            'Row 84: 防污涂料降解率: 2/3释放到海洋环境.')

    # ------------------------------------------------------------------
    # E6. Steel Recycling — Row 76-77
    # ------------------------------------------------------------------
    add_row('E', 'STEEL_RECYCLING_RATE', '报废时钢材回收率',
            'ALL', 'ALL', 'ALL', 'ALL', 0.90, np.nan, np.nan,
            'fraction', 'Discrete',
            'Sheet 1 Row 76',
            'R76',
            '报废时钢材和尼龙可回收，回收率考虑为90% (Row 76).')

    add_row('E', 'STEEL_RECYCLED_CONTENT_RATE', '新船中回收钢材使用率',
            'ALL', 'ALL', 'ALL', 'ALL', 0.50, np.nan, np.nan,
            'fraction', 'Discrete',
            'Sheet 1 Row 77',
            'R77',
            '新船建造中回收钢材使用率50% (Row 77).')

    # ========================================================================
    # F. 渔具材料消耗参数 (Gear Material Consumption) — Sheet 1 Row 51-67
    # ========================================================================

    # ------------------------------------------------------------------
    # F1. Gear Intensity (gear_int) — Row 55-58
    # ------------------------------------------------------------------
    # Row 55: "模型截断" — methodology note
    # Row 56: PS small: ['uniform', 17.9, 9.12] kg/m vessel length
    # Row 57: PS large: ['uniform', 251.0, 54.0] kg/m vessel length
    # Row 58: LL: ['uniform', 0.490, 0.120] kg/hook
    #
    # IMPORTANT: Excel explicitly says "均匀分布" (Uniform distribution).
    # Parameters [a, b] are the range boundaries [min, max] after sorting.
    # Best = (min + max) / 2 — midpoint of uniform range.
    # This is NOT a Normal distribution — there is no std.

    # PS small (<12m): uniform [9.12, 17.9] kg/m → [0.00912, 0.0179] t/m
    gear_int_ps_small_low  = min(17.9, 9.12) / 1000        # 0.00912
    gear_int_ps_small_high = max(17.9, 9.12) / 1000        # 0.01790
    gear_int_ps_small_best = (9.12 + 17.9) / (2 * 1000)    # 0.01351
    add_row('F', 'gear_int_PS', '围网渔具强度系数 (小型船 <12m)',
            'ALL', 'PS', 'ALL', '<12m',
            round(gear_int_ps_small_best, 6),
            round(gear_int_ps_small_low, 6),
            round(gear_int_ps_small_high, 6),
            't gear / m vessel length', 'Uniform',
            'Sheet 1 Row 56; ghg_lca.py mask_ps_small',
            'R56',
            f'Excel: uniform[9.12, 17.9] kg/m. '
            f'Best=(min+max)/2={gear_int_ps_small_best:.5f} t/m. '
            'Model: gear_w = length × gear_int. '
            '小型手工围网(8-12m渔船), 莫桑比克渔业数据.')

    # PS large (>=12m): uniform [54.0, 251.0] kg/m → [0.054, 0.251] t/m
    gear_int_ps_large_low  = min(251.0, 54.0) / 1000        # 0.054
    gear_int_ps_large_high = max(251.0, 54.0) / 1000        # 0.251
    gear_int_ps_large_best = (251.0 + 54.0) / (2 * 1000)    # 0.1525
    add_row('F', 'gear_int_PS', '围网渔具强度系数 (大型船 >=12m)',
            'ALL', 'PS', 'ALL', '>=12m',
            round(gear_int_ps_large_best, 4),
            round(gear_int_ps_large_low, 4),
            round(gear_int_ps_large_high, 4),
            't gear / m vessel length', 'Uniform',
            'Sheet 1 Row 57; ghg_lca.py mask_ps_large',
            'R57',
            f'Excel: uniform[54.0, 251.0] kg/m. '
            f'Best=(min+max)/2={gear_int_ps_large_best:.4f} t/m. '
            'Model: gear_w = length × gear_int. '
            '印度围网渔业(11-24m渔船).')

    # LL: uniform [0.120, 0.490] kg/hook → [0.03333, 0.13611] t/m
    # Conversion: kg/hook ÷ (0.0036 m/hook × 1000 kg/t) = kg/hook / 3.6
    gear_int_ll_low  = min(0.490, 0.120) / (0.0036 * 1000)   # 0.03333
    gear_int_ll_high = max(0.490, 0.120) / (0.0036 * 1000)   # 0.13611
    gear_int_ll_best = (0.490 + 0.120) / (2 * 0.0036 * 1000) # 0.08472
    add_row('F', 'gear_int_LL', '延绳钓渔具强度系数',
            'ALL', 'LL', 'ALL', 'ALL',
            round(gear_int_ll_best, 6),
            round(gear_int_ll_low, 6),
            round(gear_int_ll_high, 6),
            't gear / m vessel length', 'Uniform',
            'Sheet 1 Row 58; ghg_lca.py mask_ll',
            'R58',
            f'Excel: uniform[0.120, 0.490] kg/hook. '
            f'Best=(min+max)/(2×0.0036×1000)={gear_int_ll_best:.5f} t/m. '
            'Model: gear_w = length × gear_int. '
            '1 hook ≈ 0.0036m vessel length. '
            '埃及地中海长鳍金枪鱼延绳钓(4000-4500钩, 14-17m, 70-130HP).')

    # ------------------------------------------------------------------
    # F2. Gear Material Composition — Row 52-54, 59-60
    # ------------------------------------------------------------------
    # Row 52-53: PS net composition (nylon 50%, lead 28%, EVA 20%, Polysteel 2%)
    # Row 54: LL composition (mainline: nylon; hooks: metal/alloy)
    # Row 59: PS detailed: PA6=64.2%, EVA=9.7%, Steel=26.1% (93.2t ±16.2 per vessel)
    # Row 60: Alternative composition: Nylon 66.69%, EVA 27.43%, Polysteel 5.88%

    add_row('F', 'GEAR_MATERIAL_NYLON_PS', '围网尼龙 (PA6) 材料占比',
            'ALL', 'PS', 'ALL', 'ALL', 0.642, np.nan, np.nan,
            'mass fraction', 'Discrete',
            'Sheet 1 Row 59',
            'R59',
            'PA6 (nylon) = 64.2% of PS net weight (Row 59). '
            'Includes netting, ropes, float lines. '
            'Alternative composition (Row 60): 66.69% nylon.')

    add_row('F', 'GEAR_MATERIAL_EVA_PS', '围网EVA浮子占比',
            'ALL', 'PS', 'ALL', 'ALL', 0.097, np.nan, np.nan,
            'mass fraction', 'Discrete',
            'Sheet 1 Row 59',
            'R59',
            'EVA floats = 9.7% of PS net weight (Row 59). '
            'Alternative composition (Row 60): 27.43% EVA.')

    add_row('F', 'GEAR_MATERIAL_STEEL_PS', '围网金属部件 (钢) 占比',
            'ALL', 'PS', 'ALL', 'ALL', 0.261, np.nan, np.nan,
            'mass fraction', 'Discrete',
            'Sheet 1 Row 59',
            'R59',
            'Steel components = 26.1% of PS net weight (Row 59). '
            'Includes chains, rings, wire rope. '
            'Row 52-53 alternative: lead 28%, steel 2%.')

    # LL material
    add_row('F', 'GEAR_MATERIAL_NYLON_LL', '延绳钓主绳尼龙占比',
            'ALL', 'LL', 'ALL', 'ALL', 1.0, np.nan, np.nan,
            'mass fraction (mainline)', 'Discrete',
            'Sheet 1 Row 54',
            'R54',
            'LL mainline: nylon (Row 54). Hooks: metal/alloy. '
            '⚠ 钩子金属材料的具体占比未在Sheet 1中明确给出，需补充.')

    # ------------------------------------------------------------------
    # F3. Gear Emission Factors (材料级, cradle-to-gate) — Row 69
    # ------------------------------------------------------------------
    # ⚠ USER NOTE: Excel Row 69仅标注"尼龙绳生产排放因子"但未给出具体数值.
    # 以下按网具材料组成拆分为3个独立的排放因子, 便于LCA建模.
    # PS网具组成 (Row 59): PA6=64.2%, EVA=9.7%, Steel=26.1%
    # LL网具组成 (Row 54-55): 主绳=尼龙, 钩子=金属/合金
    # 所有值为NaN, 待用户从Ecoinvent等LCA数据库填入.

    add_row('F', 'EMISSION_FACTOR_NYLON_PA6', '尼龙(PA6)碳排放因子 (cradle-to-gate)',
            'ALL', 'ALL', 'ALL', 'ALL', 9.885, 9.807, 9.969,
            'kg CO₂eq/kg nylon', 'Lognormal',
            '自建前景过程 — fishing net production, nylon, 1kg '
            '(1000 MC simulations, Cradle-to-Gate)',
            'SelfBuilt_NylonNet',
            '1 kg 尼龙网衣生产碳排放。系统边界: Cradle-to-Gate。'
            '核心代理: market for nylon 6 | Cutoff, U - RoW + '
            'market for extrusion, plastic film | Cutoff, U - GLO。'
            'Mean=9.885, SD=0.040, Median=9.885, 95% CI [9.807, 9.969]. '
            '同时适用于围网和延绳钓尼龙材料.')

    add_row('F', 'EMISSION_FACTOR_STEEL_GEAR', '渔具用钢/金属件碳排放因子 (cradle-to-gate)',
            'ALL', 'ALL', 'ALL', 'ALL', 3.070, 2.819, 3.374,
            'kg CO₂eq/kg steel hardware', 'Lognormal',
            '自建前景过程 — longline hardware, steel, 1kg '
            '(1000 MC simulations, Cradle-to-Gate)',
            'SelfBuilt_LL_Hardware',
            '1 kg 延绳钓金属渔具 (鱼钩、转环、沉子等五金件) 碳排放。'
            '系统边界: Cradle-to-Gate。'
            '投入: market for steel, low-alloyed | Cutoff, U - GLO + '
            'metal working, average for steel product manufacturing | Cutoff, U - GLO。'
            'Mean=3.070, SD=0.139, Median=3.064, 95% CI [2.819, 3.374].')

    # ------------------------------------------------------------------
    # F4. Gear Intensity Truncation Limits (物理截断) — Row 56
    # ------------------------------------------------------------------
    # Row 56: "模型截断" — 设物理极值防止无限线性外推
    # Kuczenski et al. (2022) Fish. Fish. 23:22-33
    # 延绳钓上限: 1600 kW / 55m LOA / 800 GT
    # 围网双峰: 小集群 1000 kW/50m/750 GT; 大集群 2000-3000 kW/60-80m/1000-2000 GT

    add_row('F', 'GEAR_INT_TRUNC_LL_MAX_KW', '延绳钓gear_int物理截断—最大功率',
            'ALL', 'LL', 'ALL', 'ALL', 1600.0, np.nan, np.nan,
            'kW', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'LL渔船最大功率约1600 kW. 超过此值的vessel在gear_int外推时截断.')

    add_row('F', 'GEAR_INT_TRUNC_LL_MAX_LOA_M', '延绳钓gear_int物理截断—最大船长',
            'ALL', 'LL', 'ALL', 'ALL', 55.0, np.nan, np.nan,
            'm', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'LL渔船最大LOA约55m. 超过此值的vessel在gear_int外推时截断.')

    add_row('F', 'GEAR_INT_TRUNC_LL_MAX_GT', '延绳钓gear_int物理截断—最大总吨位',
            'ALL', 'LL', 'ALL', 'ALL', 800.0, np.nan, np.nan,
            'GT', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'LL渔船最大GT约800. 超过此值的vessel在gear_int外推时截断.')

    add_row('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_KW', '围网(小集群) gear_int物理截断—最大功率',
            'ALL', 'PS', 'ALL', '<12m', 1000.0, np.nan, np.nan,
            'kW', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS小集群(<12m)上限: 1000 kW, 50m LOA, 750 GT.')

    add_row('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_LOA_M', '围网(小集群) gear_int物理截断—最大船长',
            'ALL', 'PS', 'ALL', '<12m', 50.0, np.nan, np.nan,
            'm', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS小集群(<12m)LOA上限约50m.')

    add_row('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_GT', '围网(小集群) gear_int物理截断—最大总吨位',
            'ALL', 'PS', 'ALL', '<12m', 750.0, np.nan, np.nan,
            'GT', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS小集群(<12m)GT上限约750.')

    add_row('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_KW', '围网(大集群) gear_int物理截断—最大功率',
            'ALL', 'PS', 'ALL', '>=12m', 2500.0, 2000.0, 3000.0,
            'kW', 'Triangular',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS大集群(>=12m)上限: 2000-3000 kW, 60-80m LOA, 1000-2000 GT. Best取2500kW.')

    add_row('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_LOA_M', '围网(大集群) gear_int物理截断—最大船长',
            'ALL', 'PS', 'ALL', '>=12m', 70.0, 60.0, 80.0,
            'm', 'Triangular',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS大集群(>=12m)LOA范围60-80m. Best取70m.')

    add_row('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_GT', '围网(大集群) gear_int物理截断—最大总吨位',
            'ALL', 'PS', 'ALL', '>=12m', 1500.0, 1000.0, 2000.0,
            'GT', 'Triangular',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS大集群(>=12m)GT范围1000-2000. Best取1500GT.')

    # ------------------------------------------------------------------
    # F5. Gear Lifespan — Row 61-66
    # ------------------------------------------------------------------
    # Row 61: PS net lifespan 5yr, annual replacement 25%; "1/5 + 25%"
    # Row 62: Company-reported net lifespan: 3.2yr (±0.8, range 2-4yr)
    # Row 63: "5年 更换率25% 20% + 25%"
    # Row 64: "33.3%+(2.3% - 6.6%)"
    # Row 65: "20% + 25%"
    # Row 66: LL update rate: "20% + 25%" (same structure as PS)

    add_row('F', 'LIFESPAN_GEAR_PS', '围网使用寿命',
            'ALL', 'PS', 'ALL', 'ALL', 5, 3, 5,
            'years', 'Triangular',
            'Sheet 1 Row 61-64',
            'R61-R64',
            'PS net lifespan: 5yr (Row 61, Row 63). '
            'Company-reported average: 3.2yr (Row 62). '
            'Annual replacement 25% in non-renewal years (Row 61).')

    add_row('F', 'LIFESPAN_GEAR_LL', '延绳钓使用寿命',
            'ALL', 'LL', 'ALL', 'ALL', 5, 3, 5,
            'years', 'Triangular',
            'Sheet 1 Row 65-66',
            'R65-R66',
            'LL gear lifespan: 5yr (Row 65-66). '
            'Annual replacement 20%+25% in non-renewal years.')

    # ------------------------------------------------------------------
    # F5. Gear Maintenance Rate — Row 61-66
    # ------------------------------------------------------------------
    add_row('F', 'MAINTENANCE_RATE_GEAR_PS', '围网年度维护更换比例',
            'ALL', 'PS', 'ALL', 'ALL', 0.25, 0.20, 0.33,
            'fraction per year', 'Triangular',
            'Sheet 1 Row 61-64',
            'R61-R64',
            'PS: 25% annual gear replacement (in non-renewal years). '
            'Row 61: 1/5 + 25%; Row 63: 20% + 25%.')

    add_row('F', 'MAINTENANCE_RATE_GEAR_LL', '延绳钓年度维护更换比例',
            'ALL', 'LL', 'ALL', 'ALL', 0.25, 0.20, 0.33,
            'fraction per year', 'Triangular',
            'Sheet 1 Row 65-66',
            'R65-R66',
            'LL: 25% annual gear replacement (in non-renewal years). '
            'Row 65-66: 20% + 25%.')

    # ========================================================================
    # G. 延绳钓饵料消耗参数 (Longline Bait Consumption) — Sheet 1 Row 91-94
    # ========================================================================
    # Row 91: Section header
    # Row 92: 每船每航次部署 500-1500 枚钓钩
    # Row 93: 每套钓具总钩数 1,666 - 2,147 枚
    # Row 94: 饵料主要是低值杂鱼 (low-value trash fish)

    add_row('G', 'BAIT_WEIGHT_PER_HOOK_KG', '延绳钓单钩饵料平均重量',
            'ALL', 'LL', 'ALL', 'ALL', 0.1, 0.05, 0.15,
            'kg/hook', 'Triangular',
            'Sheet 1 Row 91-94; ghg_lca.py BAIT_WEIGHT_PER_HOOK_KG',
            'R91-R94',
            'Default: 0.1 kg per hook (low-value trash fish). '
            'Range: 0.05-0.15 kg/hook. '
            'Model: Bait_GHG = Std_Effort × BAIT_WEIGHT × EF_BAIT / 1000.')

    # Bait EF — from ecoinvent LCA (small pelagic fish, fresh)
    add_row('G', 'EMISSION_FACTOR_BAIT', '饵料碳排放因子 (cradle-to-gate)',
            'ALL', 'LL', 'ALL', 'ALL', 1.606, 1.548, 1.670,
            'kg CO₂eq/kg bait', 'Lognormal',
            'Ecoinvent v3 — market for small pelagic fish, fresh | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_Bait',
            '1 kg 小型中上层鱼类 (新鲜) 碳排放。'
            'Mean=1.606, SD=0.033, Median=1.606, 95% CI [1.548, 1.670]. '
            '替代原有遗留值 0.454 kgCO2/kg bait (来源待核实).')

    add_row('G', 'HOOKS_PER_LINE_RANGE_LOW', '每套钓具最低总钩数',
            'ALL', 'LL', 'ALL', 'ALL', 1666, 500, 1666,
            'hooks/line', 'Triangular',
            'Sheet 1 Row 92-93',
            'R92-R93',
            'Row 92: 500-1500 hooks per trip; Row 93: 1666-2147 total hooks per line.')

    add_row('G', 'HOOKS_PER_LINE_RANGE_HIGH', '每套钓具最高总钩数',
            'ALL', 'LL', 'ALL', 'ALL', 2147, 1666, 3000,
            'hooks/line', 'Triangular',
            'Sheet 1 Row 92-93',
            'R92-R93',
            'Upper bound: 2147 hooks (Row 93). '
            'Extended upper bound: 3000 for large industrial LL vessels.')

    # ========================================================================
    # H. 制冷剂参数 (Refrigerant Parameters) — Sheet 1 Row 85-88
    # ========================================================================
    # Row 85: Section header — most vessels have already switched from R22
    # Row 86: R22 GWP = 1810 kg CO2e / kg R22
    # Row 87: Leak rates by vessel type
    # Row 88: Summary: bottom trawl 150 kg/yr, PS 10 kg/yr

    add_row('H', 'R22_GWP', 'R22制冷剂全球增温潜势 (100yr)',
            'ALL', 'ALL', 'ALL', 'ALL', 1810, np.nan, np.nan,
            'kgCO2e/kg R22', 'Discrete',
            'Sheet 1 Row 86',
            'R86',
            'R22 (HCFC) GWP-100 = 1810 (Row 86). '
            'Being phased out under Montreal Protocol.')

    add_row('H', 'R22_LEAK_COASTAL_TRAWL', 'R22年泄漏量 (沿海拖网渔船)',
            'ALL', 'ALL', 'ALL', 'ALL', 150, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87-88',
            'R87-R88',
            'Coastal trawl: 150 kg R22/yr (Row 87-88).')

    add_row('H', 'R22_LEAK_COASTAL_PS', 'R22年泄漏量 (沿海围网渔船)',
            'ALL', 'PS', 'ALL', 'ALL', 10, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87-88',
            'R87-R88',
            'Coastal PS: 10 kg R22/yr (Row 87-88). '
            'Much lower than trawl because PS has less refrigeration demand.')

    add_row('H', 'R22_LEAK_OFFSHORE', 'R22年泄漏量 (近海渔船)',
            'ALL', 'ALL', 'ALL', 'ALL', 200, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87',
            'R87',
            'Offshore vessels: 200 kg R22/yr (Row 87).')

    add_row('H', 'R22_LEAK_DISTANT_PS', 'R22年泄漏量 (远洋围网渔船)',
            'ALL', 'PS', 'ALL', 'ALL', 500, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87',
            'R87',
            'Distant-water PS: 500 kg R22/yr (Row 87). '
            'Tuna PS (Indian Ocean): 751 g/t reference.')

    # ========================================================================
    # I. 努力量标准化参数 (Effort Standardization) — ghg_lca.py + Sheet 1
    # ========================================================================
    # These parameters are used to convert heterogeneous RFMO effort units
    # into a common standard (hooks for LL, sets for PS).

    add_row('I', 'HOOKS_PER_DAY', '延绳钓标准日下钩数 (Effort标准化)',
            'ALL', 'LL', 'ALL', 'ALL', 3000, np.nan, np.nan,
            'hooks/day', 'Triangular',
            'ghg_lca.py HOOKS_PER_DAY constant; Sheet 1 Row 92-93 for range context',
            'R92-R93',
            'Standard LL hooks per day. '
            'Model: Std_Effort(LL) = EffortValue × HOOKS_PER_DAY for days/sets units. '
            '⚠ 该值未在Sheet 1中直接给出，来自模型代码。Row 92-93提供了每套钓具钩数范围 '
            '(1666-2147)，但并非每日下钩数。')

    add_row('I', 'HOURS_PER_SET', '围网标准单网耗时 (Effort标准化)',
            'ALL', 'PS', 'ALL', 'ALL', 12, np.nan, np.nan,
            'hours/set', 'Triangular',
            'ghg_lca.py HOURS_PER_SET constant; '
            'Korican et al. (2023) PS operational profile context',
            'R15',
            'Standard PS hours per set (searching + operation). '
            'Model: Std_Effort(PS) = EffortValue / HOURS_PER_SET for hours units. '
            '⚠ 该值未在Sheet 1中直接给出，来自模型代码。Row 15给出了PS日运行时间(主机4h,辅机15h)'
            '的上下文，但非单网耗时。')

    # ========================================================================
    # J. 历史功率演进参数 (Power Discount / Evolution) — Sheet 1 Row 47-50
    # ========================================================================
    # Row 46 (actually Row 47 in 1-based): "Vessel HP 增长3-6%, GRT增长4%"
    # Row 47 (Row 48): Regional annual power growth rates
    # Row 48 (Row 49): Gear-type power growth rates
    # Row 49 (Row 50): Python preprocessing note

    # Regional power growth rates
    add_row('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (欧洲)',
            'Europe', 'ALL', 'ALL', 'ALL', 0.002, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Europe: 0.2%/yr — lowest growth (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (亚洲)',
            'Asia', 'ALL', 'ALL', 'ALL', 0.012, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Asia: 1.2%/yr — highest growth (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (北美洲)',
            'North America', 'ALL', 'ALL', 'ALL', 0.011, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'North America: 1.1%/yr (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (非洲)',
            'Africa', 'ALL', 'ALL', 'ALL', 0.009, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Africa: 0.9%/yr (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (南美洲)',
            'South America', 'ALL', 'ALL', 'ALL', 0.011, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'South America: 1.1%/yr (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (大洋洲)',
            'Australia & Oceania', 'ALL', 'ALL', 'ALL', 0.017, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Oceania: 1.7%/yr — highest among regions (Row 48).')

    # Gear-type power growth rates (Row 49)
    add_row('J', 'POWER_GROWTH_RATE_LL', '主机功率年均增长率 (延绳钓船队)',
            'ALL', 'LL', 'ALL', 'ALL', 0.010, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 49',
            'R49',
            'LL fleet: 1.0%/yr — 3rd largest contributor (Row 49).')

    add_row('J', 'POWER_GROWTH_RATE_PS', '主机功率年均增长率 (围网船队)',
            'ALL', 'PS', 'ALL', 'ALL', 0.004, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 49',
            'R49',
            'PS fleet: 0.4%/yr — 5th largest contributor (Row 49).')

    # Decadal power growth (Row 47)
    add_row('J', 'POWER_GROWTH_DECADAL_HP', '主机功率十年增长率',
            'ALL', 'ALL', 'ALL', 'ALL', 0.045, 0.03, 0.06,
            'fraction/decade', 'Triangular',
            'Sheet 1 Row 47',
            'R47',
            'Vessel HP grew 3-6% over study period (Row 47). '
            'Best=4.5% (midpoint).')

    # ========================================================================
    # K. GT-LDT 吨位转换参数 — Sheet 1 Row 89-90
    # ========================================================================
    # Row 89: General vessel type LDT/GT ratios
    # Row 90: Fishing vessel LDT/GT = 0.859 (anomalously high)
    # "渔船是异常值，LDT/GT比率高达85.9%"

    add_row('K', 'LDT_GT_RATIO_FISHING', '渔船 GT→LDT 转换系数',
            'ALL', 'ALL', 'ALL', 'ALL', 0.859, np.nan, np.nan,
            'LDT/GT ratio', 'Normal',
            'Sheet 1 Row 90 — MEPC/IMO vessel statistics',
            'R90',
            'Fishing vessel LDT/GT = 85.9% (Row 90). '
            'Much higher than cargo ships (~22-55%). '
            'Means fishing vessels need more structural weight per GT → higher unit GHG.')

    # Reference: general cargo vessels (Row 89)
    add_row('K', 'LDT_GT_RATIO_CARGO_REF', '货船 GT→LDT 转换系数 (参考对比)',
            'ALL', 'ALL', 'ALL', 'ALL', 0.287, 0.22, 0.55,
            'LDT/GT ratio', 'Triangular',
            'Sheet 1 Row 89 — MEPC vessel statistics (various types)',
            'R89',
            'Reference: cargo ships LDT/GT varies 22-55% (Row 89). '
            'Bulk carriers: ~28.7%, Container ships: varies. '
            'Fishing vessels at 85.9% are a clear outlier.')

    # ========================================================================
    # L. EPA Nonroad Engine Reference Data — EPA NR-005d/009d/010f
    # ========================================================================
    # 三份EPA核心技术报告 (可在EPA NEPIS数据库按编号搜索下载):
    #   NR-005d (EPA-420-R-10-016): Median Life, Annual Activity, Load Factor
    #   NR-009d (EPA-420-R-10-018): CI Engine Emission Factors (柴油机)
    #   NR-010f (EPA-420-R-10-019): SI Engine Emission Factors (汽油机)
    # 单位换算: 1 lb/hp-hr ≈ 608.277 g/kWh

    # ------------------------------------------------------------------
    # L1. EPA Load Factors (NR-005d)
    # ------------------------------------------------------------------
    add_row('L', 'LF_EPA_OUTBOARD_GASOLINE', 'EPA船用舷外汽油机默认负荷因子',
            'ALL', 'ALL', 'APW', 'ALL', 0.207, np.nan, np.nan,
            'fraction of MCR', 'Discrete',
            'EPA-420-R-10-016 (NR-005d) — 船用舷外机法定综合工况默认值',
            'EPA_NR005d',
            'EPA对所有常规船用舷外汽油机的基准测试默认负荷因子: 20.7%. '
            '适用于APW小型渔船(<12m, 汽油舷外机).')

    add_row('L', 'LF_EPA_COMMERCIAL_FISHING', 'EPA商业捕捞高负荷因子',
            'ALL', 'ALL', 'I', 'ALL', 0.39, 0.34, 0.44,
            'fraction of MCR', 'Triangular',
            'EPA-420-R-10-016 (NR-005d) — 商业拖网/满载作业',
            'EPA_NR005d',
            '商业捕捞高强度作业(拖网/满载)引擎负荷: 0.34-0.44. '
            'Best取中点0.39. 适用于工业渔船(>=12m).')

    add_row('L', 'LF_EPA_INBOARD_DIESEL', 'EPA船用柴油舷内机默认负荷因子',
            'ALL', 'ALL', 'I', 'ALL', 0.425, 0.40, 0.45,
            'fraction of MCR', 'Triangular',
            'EPA-420-R-10-016 (NR-005d) — 柴油主机持续巡航/重载牵引',
            'EPA_NR005d',
            '柴油舷内机持续巡航/重载牵引默认负荷: 0.40-0.45. '
            'Best取中点0.425. 显著高于汽油舷外机(0.207).')

    # ------------------------------------------------------------------
    # L2. EPA SFR — 汽油机 (NR-010f, Spark-Ignition Outboard)
    # ------------------------------------------------------------------
    add_row('L', 'SFR_GASOLINE_2STROKE', 'EPA传统两冲程汽油舷外机SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000592, 0.000547, 0.000638,
            'tFuel/kWh', 'Triangular',
            'EPA-420-R-10-019 (NR-010f) — 2-Stroke Outboard',
            'EPA_NR010f',
            '传统两冲程: 0.90-1.05 lb/hp-hr = 547-638 g/kWh = 0.000547-0.000638 t/kWh. '
            'Best=592 g/kWh. 油耗极高, >20%未燃燃油直接排放入水.')

    add_row('L', 'SFR_GASOLINE_4STROKE', 'EPA现代四冲程汽油舷外机SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000319, 0.000304, 0.000334,
            'tFuel/kWh', 'Triangular',
            'EPA-420-R-10-019 (NR-010f) — 4-Stroke Outboard',
            'EPA_NR010f',
            '现代四冲程: 0.50-0.55 lb/hp-hr = 304-334 g/kWh = 0.000304-0.000334 t/kWh. '
            'Best=319 g/kWh. 油耗与车用发动机接近, 中大型汽油舷外机主流技术.')

    add_row('L', 'SFR_GASOLINE_DI_2STROKE', 'EPA直喷两冲程汽油舷外机SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000365, 0.000334, 0.000395,
            'tFuel/kWh', 'Triangular',
            'EPA-420-R-10-019 (NR-010f) — DI 2-Stroke Outboard',
            'EPA_NR010f',
            '直喷两冲程: 0.55-0.65 lb/hp-hr = 334-395 g/kWh = 0.000334-0.000395 t/kWh. '
            'Best=365 g/kWh. 缸内直喷改善传统两冲程短路漏油, 油耗介于两者之间.')

    # ------------------------------------------------------------------
    # L3. EPA SFR — 柴油机 (NR-009d, Compression-Ignition Inboard)
    # ------------------------------------------------------------------
    add_row('L', 'SFR_DIESEL_25_50HP', 'EPA小型柴油舷内机(25-50HP / 19-37kW) SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000248, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'EPA-420-R-10-018 (NR-009d) — 25-50 HP (19-37 kW) CI Engine',
            'EPA_NR009d',
            '小型柴油机: ~0.408 lb/hp-hr ≈ 248 g/kWh = 0.000248 t/kWh. '
            '25-50 HP ≈ 19-37 kW. 燃油经济性全面优于同马力四冲程汽油舷外机.')

    add_row('L', 'SFR_DIESEL_100_175HP', 'EPA中型柴油舷内机(100-175HP / 75-130kW) SFR',
            'ALL', 'ALL', 'I', 'ALL', 0.000221, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'EPA-420-R-10-018 (NR-009d) — 100-175 HP (75-130 kW) CI Engine',
            'EPA_NR009d',
            '中型柴油机: ~0.364 lb/hp-hr ≈ 221 g/kWh = 0.000221 t/kWh. '
            '100-175 HP ≈ 75-130 kW. 随排量缸径增加热效率提升, SFR进一步降低.')

    add_row('L', 'SFR_DIESEL_300_600HP', 'EPA大型柴油舷内机(300-600HP / 224-447kW) SFR',
            'ALL', 'ALL', 'I', 'ALL', 0.000210, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'EPA-420-R-10-018 (NR-009d) — 300-600 HP (224-447 kW) CI Engine',
            'EPA_NR009d',
            '大型柴油机: ~0.345 lb/hp-hr ≈ 210 g/kWh = 0.000210 t/kWh. '
            '300-600 HP ≈ 224-447 kW. 中大型近海船只主机典型经济工况. 与Row 37辅机=210 g/kWh一致.')

    # ========================================================================
    # Assemble DataFrame
    # ========================================================================
    prior = pd.DataFrame(rows)

    # Add metadata
    prior.attrs['description'] = (
        '先验参数矩阵 (v7修正版) — 排放模型全部参数的统一长格式矩阵。'
        '覆盖12大类(A-L)，每条记录由(Param_Code, Flag, Gear, Sector, Length_Category)唯一索引。'
        'v4修正: (1)ecoinvent建造/维护EF (PS钢/木, LL钢); '
        '(2)转运船/辅助船使用PS钢船因子; (3)延绳钓小船使用PS木船因子; '
        '(4)填入NaN值: 尼龙PA6=9.885, 渔具钢=3.070, 饵料=1.606 kgCO2/kg. '
        'v5修正: 删除5个不再需要的NaN参数 (STEEL/IRON/COPPER/EVA/GEAR_COMPOSITE). '
        'v6修正: (1)新增柴油/汽油上游WTT EF; (2)更新燃烧CO2 (IMO 2020/EPA 2025); '
        '(3)CH4/N2O按燃料和机型拆分; (4)柴油CH4/N2O改为IMO标准单位g/kWh. '
        'v7修正: T_map_DAS重构为3级数据优先级体系 — '
        'Tier1: Parker(2014)按大洋PS (Atlantic 297/Indian 289/Pacific 244, 缺省277); '
        'Tier2: Jha(2026)印度洋LL (234-256); '
        'Tier3: Anticamara(2011)按大洲兜底 (LL/PS/TP, Flag=ALL, Sector=I).'
    )
    prior.attrs['total_parameters'] = len(prior)
    prior.attrs['sections'] = sorted(prior['Param_Section'].unique())

    # Print summary
    section_names = {
        'A': 'Vessel Classification',
        'B': 'Fishing Activity',
        'C': 'Core Fuel & Emission',
        'D': 'Auxiliary Engine Power',
        'E': 'Hull Material & Construction',
        'F': 'Gear Material',
        'G': 'Longline Bait',
        'H': 'Refrigerant',
        'I': 'Effort Standardization',
        'J': 'Power Discount/Evolution',
        'K': 'GT-LDT Conversion',
        'L': 'EPA Engine Reference Data',
    }
    print(f"  Prior_Matrix: {len(prior)} rows × {len(prior.columns)} cols")
    for sec in sorted(prior['Param_Section'].unique()):
        sec_mask = prior['Param_Section'] == sec
        n_params = sec_mask.sum()
        n_codes = prior.loc[sec_mask, 'Param_Code'].nunique()
        sec_name = section_names.get(sec, sec)
        # Count NaN values in this section
        n_nan_best = prior.loc[sec_mask, 'Value_Best'].isna().sum()
        gap_note = f' [{n_nan_best} 待填]' if n_nan_best > 0 else ''
        print(f"    [{sec}] {sec_name}: {n_params} rows, {n_codes} unique codes{gap_note}")

    return prior


def build_species_cf_matrix(xlsx_path=XLSX_PATH):
    """
    Build the Species_CF_Matrix from Sheet 2 ('资源耗竭影响评估').

    The raw sheet is already well-structured. We:
    1. Read and clean column names
    2. Keep only the core numeric columns
    3. Insert a DEFAULT row for unknown bycatch species

    Returns
    -------
    pd.DataFrame with columns:
        Common_Name, Scientific_Name, CF_median, CF_min, CF_max
    """
    print("\n" + "=" * 70)
    print("  Building Matrix 2: Species_CF_Matrix (物种特征化因子矩阵)")
    print("=" * 70)

    # Read raw sheet
    df_raw = pd.read_excel(xlsx_path, sheet_name='资源耗竭影响评估')

    # Standardize column names
    col_map = {
        '物种 (Common name)': 'Common_Name',
        '学名 (Scientific name)': 'Scientific_Name',
        'CF (中值)': 'CF_median',
        'CF min': 'CF_min',
        'CF max': 'CF_max',
    }
    df = df_raw.rename(columns=col_map)

    # Keep only core columns
    core_cols = ['Common_Name', 'Scientific_Name', 'CF_median', 'CF_min', 'CF_max']
    df = df[core_cols].copy()

    # Clean strings
    for col in ['Common_Name', 'Scientific_Name']:
        df[col] = df[col].apply(safe_str)

    # Ensure numeric CF values
    for col in ['CF_median', 'CF_min', 'CF_max']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Remove any completely empty rows
    df = df.dropna(subset=['Common_Name', 'CF_median'], how='all')
    df = df[df['Common_Name'] != ''].copy()

    # ---- Insert DEFAULT row for unknown bycatch ----
    # Use the geometric mean of all known CF_median values as default
    valid_cf = df['CF_median'].dropna()
    valid_cf = valid_cf[valid_cf > 0]
    if len(valid_cf) > 0:
        default_cf = np.exp(np.log(valid_cf).mean())  # geometric mean
        default_cf_min = df['CF_min'].dropna().min()
        default_cf_max = df['CF_max'].dropna().max()
    else:
        default_cf = 1e-06
        default_cf_min = 1e-07
        default_cf_max = 1e-04

    default_row = pd.DataFrame([{
        'Common_Name': 'DEFAULT',
        'Scientific_Name': 'Unknown bycatch species',
        'CF_median': default_cf,
        'CF_min': default_cf_min,
        'CF_max': default_cf_max,
    }])

    df = pd.concat([df, default_row], ignore_index=True)

    # Add metadata
    df.attrs['description'] = '物种特征化因子矩阵 — 金枪鱼及兼捕物种 CF 值'
    df.attrs['default_row_note'] = (
        f'DEFAULT row CF_median={default_cf:.2e} = geometric mean of all known species; '
        f'used for unknown bycatch in LCA resource depletion assessment'
    )
    df.attrs['source'] = 'Hélias, Langlois & Fréon (2018) Fish and Fisheries 19:950-970'

    print(f"  Species_CF_Matrix: {len(df)} rows × {len(df.columns)} cols")
    print(f"  Species: {df['Common_Name'].tolist()}")
    print(f"  DEFAULT CF_median = {default_cf:.2e} (geometric mean of all known CF)")

    return df


# =============================================================================
# Matrix 3: Scenario_Multiplier_Matrix (情景乘数矩阵)
# =============================================================================

def build_scenario_multiplier_matrix(xlsx_path=XLSX_PATH):
    """
    Build the Scenario_Multiplier_Matrix from Sheet 3 ('情景分析').

    Parse Chinese text descriptions into numeric Fuel_Multiplier and GHG_Multiplier.
    Scenarios with unquantified measures are flagged as 'qualitative_only'.

    Returns
    -------
    pd.DataFrame with columns:
        Scenario_ID, Measure_Category, Measure_Description, Measure_Value_Raw,
        Fuel_Multiplier, GHG_Multiplier, Is_Quantified, Source
    """
    print("\n" + "=" * 70)
    print("  Building Matrix 3: Scenario_Multiplier_Matrix (情景乘数矩阵)")
    print("=" * 70)

    # Read raw sheet
    df_raw = pd.read_excel(xlsx_path, sheet_name='情景分析', header=None)

    # Find the header row (row containing '措施类别')
    header_row = None
    for i, row in df_raw.iterrows():
        if any('措施类别' in safe_str(v) for v in row.values):
            header_row = i
            break

    if header_row is None:
        print("  WARNING: Could not find header row, using row 1 as default")
        header_row = 1

    # Extract data rows (after header)
    # Column mapping (by position): 0=措施类别, 1=具体措施, 2=取值, 3=来源, 4=说明
    data_rows = []
    for i in range(header_row + 1, len(df_raw)):
        row = df_raw.iloc[i]
        category = safe_str(row.iloc[0]) if len(row) > 0 else ''
        measure = safe_str(row.iloc[1]) if len(row) > 1 else ''
        value_text = safe_str(row.iloc[2]) if len(row) > 2 else ''
        source = safe_str(row.iloc[3]) if len(row) > 3 else ''
        note = safe_str(row.iloc[4]) if len(row) > 4 else ''

        # Skip rows that are section headers or empty
        if not measure and not value_text:
            continue
        if category in ('情景分析模型', '措施类别'):
            continue

        data_rows.append({
            'Measure_Category': category,
            'Measure_Description': measure,
            'Measure_Value_Raw': value_text,
            'Source': source,
            'Note': note,
        })

    df = pd.DataFrame(data_rows)

    # ---- Parse numeric multipliers ----
    fuel_mults = []
    ghg_mults = []
    is_quantified = []

    for _, row in df.iterrows():
        text = row['Measure_Value_Raw']
        cat = row['Measure_Category']
        desc = row['Measure_Description']

        # Determine if the parsed value should be treated as fuel or GHG
        # Alternative fuels typically report GHG/carbon reductions, not direct fuel savings
        is_alt_fuel = ('替代燃料' in cat or
                       any(kw in desc for kw in ['甲醇替代', 'LPG替代', 'LNG替代', 'CNG',
                                                 '生物柴油', '生物燃料', '氢-柴油',
                                                 '沼气', '甲醇-柴油', '氢-柴油',
                                                 '电力（LFP', '液化石油气']))
        is_refrigerant = '制冷剂' in cat
        is_gear_change = '更换渔具' in cat
        is_baseline = '基准' in cat or '综合结论' in cat

        # Try to parse fuel savings
        fuel_low, fuel_high, fuel_central = parse_percent_range(text)

        # Try to parse GHG changes
        ghg_mult = parse_ghg_change(text)

        # For alternative fuels, the parsed percentage is typically GHG/carbon reduction,
        # NOT fuel savings. Re-route accordingly.
        if is_alt_fuel and fuel_central is not None and ghg_mult is None:
            # The text describes carbon/GHG reduction → assign to GHG_Multiplier
            ghg_mult = fuel_central
            fuel_central = None

        # If GHG was parsed from a GHG-specific pattern, clear fuel_central
        # to avoid double-counting the same text as both fuel and GHG
        if ghg_mult is not None and fuel_central is not None:
            # Check if the text is primarily about GHG/CO2 (not fuel)
            if re.search(r'(?:GHG|CO₂?|CO2|温室|碳排放?)', text):
                fuel_central = None

        # For refrigerants, the reduction is in GWP impact, not fuel
        if is_refrigerant and fuel_central is not None and ghg_mult is None:
            ghg_mult = fuel_central
            fuel_central = None

        # Determine if this measure is quantified
        quantified = (fuel_central is not None) or (ghg_mult is not None)

        # Round multipliers to 3 decimal places for readability
        if fuel_central is not None:
            fuel_central = round(fuel_central, 3)
        if ghg_mult is not None:
            ghg_mult = round(ghg_mult, 3)

        # Additional checks: text explicitly says "未量化" or contains non-percentage units
        if '未量化' in text or '未量化' in desc:
            quantified = False
        if is_gear_change:
            # Gear change rows often have bycatch mortality rates (0.05 vs 0.25) — not fuel
            quantified = False
            fuel_central = None

        fuel_mults.append(fuel_central)
        ghg_mults.append(ghg_mult)
        is_quantified.append(quantified)

    df['Fuel_Multiplier'] = fuel_mults
    df['GHG_Multiplier'] = ghg_mults
    df['Is_Quantified'] = is_quantified

    # ---- Handle "同上" (same as above) rows ----
    # These are duplicate literature sources citing the same measure.
    # They inherit the multiplier from the nearest non-同上 row above,
    # and are marked as "duplicate reference" in the description.
    same_as_above_refs = {}  # track which primary row each 同上 row references
    for i in range(len(df)):
        if df.loc[i, 'Measure_Description'].strip() == '同上':
            for j in range(i - 1, -1, -1):
                if df.loc[j, 'Measure_Description'].strip() != '同上':
                    df.loc[i, 'Fuel_Multiplier'] = df.loc[j, 'Fuel_Multiplier']
                    df.loc[i, 'GHG_Multiplier'] = df.loc[j, 'GHG_Multiplier']
                    df.loc[i, 'Is_Quantified'] = df.loc[j, 'Is_Quantified']
                    same_as_above_refs[i] = j
                    break

    # ---- Special handling for baseline fuel consumption rows ----
    # These are absolute consumption values (L/kg), not multipliers
    mask_baseline = df['Measure_Category'].str.contains('基准', na=False)
    df.loc[mask_baseline, 'Is_Quantified'] = False

    # ---- Special handling for "综合结论" (summary) rows ----
    # These are global statistics, not scenario measures
    mask_summary = df['Measure_Category'].str.contains('综合结论', na=False)
    df.loc[mask_summary, 'Is_Quantified'] = False

    # ---- Assign Scenario_ID ----
    # S1, S2, ... for quantified; Q1, Q2, ... for qualitative
    # "同上" rows get sub-IDs referencing their primary (e.g., S6a, S6b)
    q_count, s_count = 0, 0
    primary_s_ids = {}  # row index → S number for the primary entry
    scenario_ids = []
    for i in range(len(df)):
        row = df.iloc[i]
        if row['Is_Quantified']:
            if i in same_as_above_refs:
                # Find the S-number assigned to the primary row
                primary_idx = same_as_above_refs[i]
                # Walk back to find the S-number already assigned
                primary_s_num = primary_s_ids.get(primary_idx)
                if primary_s_num is not None:
                    # Count how many 同上 refs point to same primary
                    same_count = sum(1 for v in same_as_above_refs.values() if v == primary_idx)
                    refs_before = sum(1 for k, v in same_as_above_refs.items()
                                     if v == primary_idx and k <= i)
                    letter = chr(ord('a') + refs_before - 1)
                    scenario_ids.append(f'S{primary_s_num}{letter}')
                else:
                    s_count += 1
                    scenario_ids.append(f'S{s_count}')
                    primary_s_ids[i] = s_count
            else:
                s_count += 1
                scenario_ids.append(f'S{s_count}')
                primary_s_ids[i] = s_count
        else:
            if i in same_as_above_refs:
                primary_idx = same_as_above_refs[i]
                primary_q_num = primary_s_ids.get(primary_idx)
                if primary_q_num is not None:
                    refs_before = sum(1 for k, v in same_as_above_refs.items()
                                     if v == primary_idx and k <= i)
                    letter = chr(ord('a') + refs_before - 1)
                    scenario_ids.append(f'Q{primary_q_num}{letter}')
                else:
                    q_count += 1
                    scenario_ids.append(f'Q{q_count}')
                    primary_s_ids[i] = q_count
            else:
                q_count += 1
                scenario_ids.append(f'Q{q_count}')
                primary_s_ids[i] = q_count
    df['Scenario_ID'] = scenario_ids

    # ---- Column comment for multipliers ----
    # Add a note column explaining the multiplier interpretation
    multiplier_notes = []
    for _, row in df.iterrows():
        if row['Is_Quantified'] and pd.notna(row['Fuel_Multiplier']):
            pct = (1 - row['Fuel_Multiplier']) * 100
            multiplier_notes.append(
                f'Fuel multiplier = {row["Fuel_Multiplier"]:.3f} '
                f'(≈ {pct:.0f}% fuel saving relative to baseline)'
            )
        elif row['Is_Quantified'] and pd.notna(row['GHG_Multiplier']):
            pct = (1 - row['GHG_Multiplier']) * 100
            multiplier_notes.append(
                f'GHG multiplier = {row["GHG_Multiplier"]:.3f} '
                f'(≈ {pct:.0f}% GHG reduction relative to baseline)'
            )
        else:
            multiplier_notes.append('Qualitative only — no numeric multiplier')
    df['Multiplier_Note'] = multiplier_notes

    # ---- Select and order columns ----
    cols = [
        'Scenario_ID', 'Measure_Category', 'Measure_Description',
        'Measure_Value_Raw', 'Fuel_Multiplier', 'GHG_Multiplier',
        'Is_Quantified', 'Multiplier_Note', 'Source', 'Note',
    ]
    df = df[cols].copy()

    # Add metadata
    df.attrs['description'] = '情景乘数矩阵 — 减排措施的节油/减排乘数'
    df.attrs['usage'] = (
        'Fuel_Multiplier < 1 = fuel saving; GHG_Multiplier < 1 = GHG reduction. '
        'Q-prefix scenarios are qualitative only (no numeric multiplier).'
    )

    n_quant = df['Is_Quantified'].sum()
    n_qual = (~df['Is_Quantified']).sum()
    print(f"  Scenario_Multiplier_Matrix: {len(df)} rows × {len(df.columns)} cols")
    print(f"  Quantified scenarios: {n_quant} (S-prefix)")
    print(f"  Qualitative scenarios: {n_qual} (Q-prefix)")

    return df


# =============================================================================
# Matrix 4: MonteCarlo_Config_Matrix (蒙特卡洛抽样配置矩阵)
# =============================================================================

def build_montecarlo_config_matrix(xlsx_path=XLSX_PATH):
    """
    Build the MonteCarlo_Config_Matrix from Sheet 4 ('模型参数类型').

    The raw Sheet 4 defines 3 macro-categories of parameters with sampling guidance.
    Wildcard entries (EMISSION_FACTOR_*, MATERIAL_RATIO_*, LIFESPAN_*,
    MAINTENANCE_RATE_*) are expanded into their concrete parameter codes,
    matching the Prior_Matrix for full traceability.

    Returns
    -------
    pd.DataFrame with columns:
        Param_Code, Param_Category, Physical_Meaning,
        Distribution, Arg1, Arg2, Arg3, Clip_Min, Clip_Max,
        Arg1_Meaning, Arg2_Meaning, Arg3_Meaning, Sampling_Strategy_Raw,
        Covered_Prior_Codes
    """
    print("\n" + "=" * 70)
    print("  Building Matrix 4: MonteCarlo_Config_Matrix (蒙特卡洛抽样配置矩阵)")
    print("=" * 70)

    # Parse the raw Sheet 4 to extract category-level metadata
    df_raw = pd.read_excel(xlsx_path, sheet_name='模型参数类型')
    col_map = {
        '参数分类': 'Param_Category',
        '代码中的具体参数': 'Param_Code',
        '核心特征与物理意义': 'Physical_Meaning',
        '蒙特卡洛抽样策略建议': 'Sampling_Strategy_Raw',
    }
    df_raw = df_raw.rename(columns=col_map)

    # Extract category-level info from raw rows
    # Row structure (from Sheet 4):
    #   [1] 一、时间/行为型变量 | T_map (年作业天数) | 与船舶物理规模无关... | 连续概率分布
    #   [3] (Time / Behavior) | H_map (日作业小时) | | 三角分布 或 PERT分布
    #   [5] | HOURS_PER_SET | |
    #   [7] | HOOKS_PER_DAY | |
    #   [8] 二、规模依赖型变量 | gear_int | 受物理定律... | 截断与离散抽样池
    #   [10] (Scale-dependent) | SFR_map | | 物理极值截断...
    #   [12] | BAIT_WEIGHT_PER_HOOK_KG | |
    #   [13] 三、理化与工程常数 | EMISSION_FACTOR_* | 基础工业标准... | 正态/对数正态分布
    #   [15] (Physical & Engineering) | MATERIAL_RATIO_* | | ...
    #   [17] | LIFESPAN_* | |
    #   [19] | MAINTENANCE_RATE_* | |

    cat1_physical = safe_str(df_raw.iloc[1, 2]) if len(df_raw) > 1 else ''
    cat2_physical = safe_str(df_raw.iloc[8, 2]) if len(df_raw) > 8 else ''
    cat3_physical = safe_str(df_raw.iloc[13, 2]) if len(df_raw) > 13 else ''
    cat1_strategy = safe_str(df_raw.iloc[1, 3]) if len(df_raw) > 1 else ''
    cat2_strategy = safe_str(df_raw.iloc[8, 3]) if len(df_raw) > 8 else ''
    cat3_strategy = safe_str(df_raw.iloc[13, 3]) if len(df_raw) > 13 else ''
    cat1_detail = safe_str(df_raw.iloc[3, 3]) if len(df_raw) > 3 else ''  # H_map specific: Triangular/PERT
    cat2_detail = safe_str(df_raw.iloc[10, 3]) if len(df_raw) > 10 else ''  # SFR_map specific: clipping

    # =====================================================================
    # Define ALL concrete parameters with their MC sampling config
    # =====================================================================
    # Format: (Param_Code, Distribution, Physical_Meaning, Sampling_Strategy,
    #          Category_Label, Category_Num, Covered_Prior_Codes)
    #
    # The "Covered_Prior_Codes" field links to Prior_Matrix Param_Code values,
    # enabling full traceability between the two matrices.

    mc_entries = [
        # ---- Category 1: 时间/行为型变量 (Time/Behavior) ----
        # T_map (DAS) — 3-tier data hierarchy
        ('T_map_DAS', 'Triangular',
         '年作业天数（Days at Sea）。数据优先级: Tier1 Parker(2014)按大洋PS, '
         'Tier2 Jha(2026)印度洋LL, Tier3 Anticamara(2011)按大洲兜底。',
         '按 Flag×Gear×Sector 组合查阅文献确定最小值、众数和最大值，使用三角分布独立抽样。'
         'Parker数据适用于1990年后FAD时代围网; Anticamara适用于历史回溯(1950-2010)及非PS船型。',
         '一、时间/行为型变量 (Time/Behavior)', 1,
         'T_map_DAS'),

        # H_map (Daily Engine Hours)
        ('H_map_Hday', 'Triangular',
         '日主机运行小时数。',
         f'查阅文献确定最小值、最可能值和最大值，使用三角分布或PERT分布进行连续抽样。{cat1_detail}',
         '一、时间/行为型变量 (Time/Behavior)', 1,
         'H_map_Hday'),

        # HOURS_PER_SET
        ('HOURS_PER_SET', 'Triangular',
         '围网单网耗时（搜寻+作业小时数）。用于Effort标准化: Std_Effort = EffortValue / HOURS_PER_SET。',
         '查阅文献确定最小/最可能/最大值，使用三角分布连续抽样。该参数直接影响PS Effort标准化分母。',
         '一、时间/行为型变量 (Time/Behavior)', 1,
         'HOURS_PER_SET'),

        # HOOKS_PER_DAY
        ('HOOKS_PER_DAY', 'Triangular',
         '延绳钓标准日下钩数。用于Effort标准化: Std_Effort = EffortValue * HOOKS_PER_DAY。',
         '查阅文献确定最小/最可能/最大值，使用三角分布连续抽样。该参数直接影响LL Effort标准化乘数。',
         '一、时间/行为型变量 (Time/Behavior)', 1,
         'HOOKS_PER_DAY'),

        # LF_move (engine load factor — transit) — added for completeness
        ('LF_move', 'Triangular',
         '航行阶段发动机负荷因子（占MCR比例）。受船舶类型和Sector影响。',
         '按 Gear×Sector 组合设定三角分布参数。Industrial: mode≈0.80; APW: mode≈0.79。',
         '一、时间/行为型变量 (Time/Behavior)', 1,
         'LF_move'),

        # LF_work (engine load factor — fishing)
        ('LF_work', 'Triangular',
         '捕捞作业阶段发动机负荷因子（占MCR比例）。受船舶类型和Sector影响，变动大于LF_move。',
         '按 Gear×Sector 组合设定三角分布参数。I-LL: mode≈0.50; I-PS: mode≈0.65; APW: mode≈0.19。',
         '一、时间/行为型变量 (Time/Behavior)', 1,
         'LF_work'),

        # ---- Category 2: 规模依赖型变量 (Scale-dependent) ----
        # gear_int (Gear intensity factor)
        ('gear_int_PS', 'Truncated',
         '围网渔具强度系数（吨网具/米船长）。受物理定律和空间几何严格限制，随船长呈阶梯变化。',
         f'均匀分布(Uniform)，物理极值截断。PS small (<12m): Uniform[0.00912, 0.0179] t/m; PS large (>=12m): Uniform[0.054, 0.251] t/m。{cat2_strategy}',
         '二、规模依赖型变量 (Scale-dependent)', 2,
         'gear_int_PS'),

        ('gear_int_LL', 'Truncated',
         '延绳钓渔具强度系数（吨网具/米船长）。随船舶长度变化。',
         f'均匀分布(Uniform)，物理极值截断。LL: Uniform[0.03333, 0.13611] t/m (由kg/hook除以3.6转换)。{cat2_strategy}',
         '二、规模依赖型变量 (Scale-dependent)', 2,
         'gear_int_LL'),

        # SFR_map
        ('SFR_map', 'Truncated',
         '特定燃油消耗率（tFuel/kWh）。随船长阶梯变化（<12m vs >=12m），受发动机技术代际影响。',
         f'必须设定物理极值截断(Clipping)，从文献构成的离散池中抽取。{cat2_detail} Industrial: Lognormal(μ=ln(0.00020), σ); APW: Lognormal(μ=ln(0.00035), σ)。',
         '二、规模依赖型变量 (Scale-dependent)', 2,
         'SFR_map'),

        # BAIT_WEIGHT_PER_HOOK_KG
        ('BAIT_WEIGHT_PER_HOOK_KG', 'Triangular',
         '延绳钓单钩饵料平均重量（kg/钩）。受目标鱼种和饵料可获得性影响。',
         f'查阅文献确定最小值、最可能值和最大值，使用三角分布。{cat2_strategy} 默认: mode=0.1 kg/hook。',
         '二、规模依赖型变量 (Scale-dependent)', 2,
         'BAIT_WEIGHT_PER_HOOK_KG'),

        # AUX_POWER_RATIO
        ('AUX_POWER_RATIO', 'Triangular',
         '辅机/主机功率比。随船舶吨位和建造年代呈阶梯变化（0.15-0.40）。',
         '按GT和Builtdate分层设定三角分布: Large(GT>1500)→0.33-0.40; Medium(500-1500, post-1990)→0.25-0.33; Small/Old→0.15-0.25。',
         '二、规模依赖型变量 (Scale-dependent)', 2,
         'AUX_POWER_RATIO | AUX_POWER_RATIO_LARGE | AUX_POWER_RATIO_MEDIUM | AUX_POWER_RATIO_SMALL'),

        # ---- Category 3: 理化与工程常数 (Physical & Engineering Constants) ----
        # These come from Ecoinvent / standard LCA databases.
        # They are stable physical properties, perturbed with Normal or Lognormal.

        # Emission Factors — Upstream (Well-to-Tank, WTT)
        ('EF_WTT_DIESEL', 'Lognormal',
         '柴油上游(WTT)碳排放因子（kg CO₂eq/kg diesel）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(0.369), 95% CI [0.318, 0.441] '
         '(Ecoinvent v3: market for diesel | Cutoff, U - RoW).',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_WTT_DIESEL'),

        ('EF_WTT_GASOLINE', 'Lognormal',
         '汽油上游(WTT)碳排放因子（kg CO₂eq/kg petrol）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(0.535), 95% CI [0.489, 0.595] '
         '(Ecoinvent v3: market for petrol, two-stroke blend | Cutoff, U - GLO).',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_WTT_GASOLINE'),

        # Emission Factors — CO2 from fuel combustion (Tank-to-Wake)
        ('EF_CO2_Diesel', 'Discrete',
         '柴油CO₂燃烧排放因子（tCO₂/tFuel）。IMO 2020化学计量常数，非统计估计。',
         f'离散值，不进行MC扰动。{cat3_strategy} 固定: 3.206 (IMO 2020 Fourth GHG Study, 碳元素质量占比化学计量完全氧化)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_CO2_Diesel'),

        ('EF_CO2_Gasoline', 'Normal',
         '汽油CO₂燃烧排放因子（tCO₂/tFuel）。EPA 2025, 用于小型渔船（APW Sector）。',
         f'查阅EPA获取CV，正态分布扰动。{cat3_strategy} 默认: μ=3.158 (EPA 2025 Table 2: 8.78 kg/gallon ÷ 2.78 kg/gallon)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_CO2_Gasoline'),

        # Emission Factors — CH4 (Methane, by fuel and engine type)
        ('EF_CH4_DIESEL_MSD', 'Lognormal',
         '柴油CH₄排放因子—中速四冲程MSD（g/kWh）。IMO 2020, 渔船主流机型/辅机。',
         f'对数正态分布。{cat3_strategy} 默认: μ=ln(0.010) (IMO 2020 Fourth GHG Study, IMO标准单位 g/kWh)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_CH4_DIESEL_MSD'),

        ('EF_CH4_DIESEL_SSD', 'Lognormal',
         '柴油CH₄排放因子—低速二冲程SSD（g/kWh）。IMO 2020, 大型转运船主机。',
         f'对数正态分布。{cat3_strategy} 默认: μ=ln(0.010) (IMO 2020 Fourth GHG Study, IMO标准单位 g/kWh)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_CH4_DIESEL_SSD'),

        ('EF_CH4_GASOLINE_2STROKE', 'Lognormal',
         '汽油CH₄排放因子—二冲程舷外机（g/kgFuel）。EPA 2025 Table 5, Ships and Boats。',
         f'对数正态分布。{cat3_strategy} 默认: μ=ln(3.76) (EPA 2025: 10.45 g/gallon ÷ 2.78 kg/gallon)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_CH4_GASOLINE_2STROKE'),

        ('EF_CH4_GASOLINE_4STROKE', 'Lognormal',
         '汽油CH₄排放因子—四冲程舷外机（g/kgFuel）。EPA 2025 Table 5, Ships and Boats。',
         f'对数正态分布。{cat3_strategy} 默认: μ=ln(1.50) (EPA 2025: 4.18 g/gallon ÷ 2.78 kg/gallon)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_CH4_GASOLINE_4STROKE'),

        # Emission Factors — N2O (Nitrous Oxide, by fuel and engine type)
        ('EF_N2O_DIESEL_MSD', 'Lognormal',
         '柴油N₂O排放因子—中速四冲程MSD（g/kWh）。IMO 2020, 主力渔船/辅机。',
         f'对数正态分布。{cat3_strategy} 默认: μ=ln(0.030) (IMO 2020 Fourth GHG Study, IMO标准单位 g/kWh)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_N2O_DIESEL_MSD'),

        ('EF_N2O_DIESEL_SSD', 'Lognormal',
         '柴油N₂O排放因子—低速二冲程SSD（g/kWh）。IMO 2020, 大型转运船主机。',
         f'对数正态分布。{cat3_strategy} 默认: μ=ln(0.020) (IMO 2020 Fourth GHG Study, IMO标准单位 g/kWh)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_N2O_DIESEL_SSD'),

        ('EF_N2O_GASOLINE', 'Lognormal',
         '汽油N₂O排放因子（g/kgFuel）。EPA 2025 Table 5, Ships and Boats (二冲程与四冲程统一基准)。',
         f'对数正态分布。{cat3_strategy} 默认: μ=ln(0.04) (EPA 2025: 0.11 g/gallon ÷ 2.78 kg/gallon)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_N2O_GASOLINE'),

        # Vessel Construction EFs (ecoinvent LCA)
        ('EF_BUILD_PS_STEEL', 'Lognormal',
         '围网钢船建造碳排放因子（kg CO₂eq/kg vessel）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(2.421), 95% CI [2.332, 2.528]. '
         '1 kg purse seiner steel construction. 同时适用于转运船/辅助船.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_BUILD_PS_STEEL | EF_BUILD_TS'),

        ('EF_BUILD_PS_WOOD', 'Lognormal',
         '围网木船建造碳排放因子（kg CO₂eq/kg vessel）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(0.578), 95% CI [0.513, 0.678]. '
         '1 kg purse seiner wood construction. 同时适用于LL小船和TS小船.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_BUILD_PS_WOOD | EF_BUILD_LL_WOOD'),

        ('EF_BUILD_LL_STEEL', 'Lognormal',
         '延绳钓钢船建造碳排放因子（kg CO₂eq/kg vessel）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(1.956), 95% CI [1.877, 2.069]. '
         '1 kg long liner steel construction.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_BUILD_LL_STEEL'),

        # Vessel Maintenance EFs (ecoinvent LCA)
        ('EF_MAINT_PS_STEEL', 'Lognormal',
         '围网钢船维护碳排放因子（kg CO₂eq/kg maintenance）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(6.744), 95% CI [6.627, 6.883]. '
         '1 kg purse seiner steel maintenance. 同时适用于转运船/辅助船.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_MAINT_PS_STEEL | EF_MAINT_TS'),

        ('EF_MAINT_PS_WOOD', 'Lognormal',
         '围网木船维护碳排放因子（kg CO₂eq/kg maintenance）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(1.289), 95% CI [1.179, 1.437]. '
         '1 kg purse seiner wood maintenance. 同时适用于LL小船和TS小船.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_MAINT_PS_WOOD | EF_MAINT_LL_WOOD'),

        ('EF_MAINT_LL_STEEL', 'Lognormal',
         '延绳钓钢船维护碳排放因子（kg CO₂eq/kg maintenance）。Ecoinvent v3, 1000 MC。',
         f'对数正态分布。{cat3_strategy} μ=ln(4.450), 95% CI [3.777, 5.376]. '
         '1 kg long liner steel maintenance.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EF_MAINT_LL_STEEL'),

        ('EMISSION_FACTOR_NYLON_PA6', 'Lognormal',
         '尼龙(PA6)碳排放因子（kg CO₂eq/kg nylon）。自建前景过程，Cradle-to-Gate。',
         f'对数正态分布。{cat3_strategy} μ=ln(9.885), 95% CI [9.807, 9.969] (自建LCA过程, 1000 MC). '
         '核心代理: nylon 6 + plastic film extrusion.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EMISSION_FACTOR_NYLON_PA6'),

        ('EMISSION_FACTOR_STEEL_GEAR', 'Lognormal',
         '渔具用钢/金属件碳排放因子（kg CO₂eq/kg steel hardware）。自建前景过程，Cradle-to-Gate。',
         f'对数正态分布。{cat3_strategy} μ=ln(3.070), 95% CI [2.819, 3.374] (自建LCA过程, 1000 MC). '
         '投入: low-alloyed steel + metal working average.',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EMISSION_FACTOR_STEEL_GEAR'),

        ('EMISSION_FACTOR_BAIT', 'Lognormal',
         '饵料碳排放因子（kg CO₂eq/kg bait）。小型中上层鱼类，Cradle-to-Gate。',
         f'对数正态分布。{cat3_strategy} μ=ln(1.606), 95% CI [1.548, 1.670] '
         '(Ecoinvent v3: market for small pelagic fish, fresh, 1000 MC).',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'EMISSION_FACTOR_BAIT'),

        # EPA SFR reference values (for cross-validation)
        ('SFR_GASOLINE_4STROKE', 'Triangular',
         'EPA四冲程汽油舷外机SFR（tFuel/kWh）。用于APW汽油机SFR交叉验证。',
         f'EPA NR-010f报告, 三角分布。默认: mode=0.000319, min=0.000304, max=0.000334。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'SFR_GASOLINE_4STROKE'),

        ('SFR_DIESEL_300_600HP', 'Lognormal',
         'EPA大型柴油舷内机SFR（tFuel/kWh）。300-600HP (224-447kW)，用于Industrial柴油机SFR交叉验证。',
         f'EPA NR-009d报告, 对数正态。默认: μ=0.000210 (≈210 g/kWh, ~0.345 lb/hp-hr)。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'SFR_DIESEL_300_600HP'),

        # Material Ratios
        ('MATERIAL_RATIO_STEEL', 'Normal',
         '船体钢材质量占GT比例。基于船舶设计规范，变异较小。',
         f'查阅Ecoinvent/造船工程文献获取CV，正态分布。{cat3_strategy} 默认: μ=0.85, σ≈0.02。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'MATERIAL_RATIO_STEEL'),

        ('MATERIAL_RATIO_ENGINE', 'Normal',
         '发动机铸铁质量占GT比例。',
         f'正态分布。{cat3_strategy} 默认: μ=0.10, σ≈0.01。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'MATERIAL_RATIO_ENGINE'),

        ('MATERIAL_RATIO_COPPER', 'Normal',
         '电力系统铜材质量占GT比例。',
         f'正态分布。{cat3_strategy} 默认: μ=0.05, σ≈0.01。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'MATERIAL_RATIO_COPPER'),

        # Lifespans
        ('LIFESPAN_HULL', 'Discrete',
         '船体寿命（年）。由船舶设计规范和船级社标准决定。',
         '离散分布或窄三角分布。在LCA中通常取固定值（30年），可通过Bootstrap重抽样船队年龄结构来间接表征变异。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'LIFESPAN_HULL'),

        ('LIFESPAN_ENGINE', 'Discrete',
         '发动机寿命（年）。通常为船体寿命的1/3，10年更换。',
         '离散分布或窄三角分布。默认: 10年。可通过发动机更换记录验证。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'LIFESPAN_ENGINE'),

        ('LIFESPAN_COPPER', 'Discrete',
         '电力系统更新周期（年）。铜缆和配电设备更换频率。',
         '离散分布。默认: 8年。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'LIFESPAN_COPPER'),

        ('LIFESPAN_GEAR_PS', 'Triangular',
         '围网使用寿命（年）。受使用强度和渔场环境（礁石、底质）影响。',
         '三角分布: min=2, mode=5, max=5。Row 60-61: 企业报告平均3.2年，但行业标准取5年。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'LIFESPAN_GEAR_PS'),

        ('LIFESPAN_GEAR_LL', 'Triangular',
         '延绳钓使用寿命（年）。钓具磨损主要由UV降解和物理损耗驱动。',
         '三角分布: min=2, mode=5, max=5。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'LIFESPAN_GEAR_LL'),

        # Maintenance Rates
        ('MAINTENANCE_RATE_STEEL', 'Normal',
         '船体钢材每2年维护更换比例。船舶维修标准作业参数。',
         f'查阅船舶维修工程文献获取CV，正态分布。{cat3_strategy} 默认: μ=0.12。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'MAINTENANCE_RATE_STEEL'),

        ('MAINTENANCE_RATE_GEAR_PS', 'Normal',
         '围网年度维护更换比例（发生于非换代年份）。文献: 20-33%范围。',
         f'正态分布。{cat3_strategy} 默认: μ=0.25（Row 60: 围网寿命5年但每年替换25%）。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'MAINTENANCE_RATE_GEAR_PS'),

        ('MAINTENANCE_RATE_GEAR_LL', 'Normal',
         '延绳钓年度维护更换比例（发生于非换代年份）。文献: 20-33%范围。',
         f'正态分布。{cat3_strategy} 默认: μ=0.25（Row 65: 20%+25%）。',
         '三、理化与工程常数 (Physical & Engineering)', 3,
         'MAINTENANCE_RATE_GEAR_LL'),
    ]

    # Build DataFrame
    rows = []
    for (code, dist, phys, strategy, cat_label, cat_num, covered) in mc_entries:
        rows.append({
            'Param_Code': code,
            'Param_Category': cat_label,
            'Param_Category_Num': cat_num,
            'Physical_Meaning': phys,
            'Distribution': dist,
            'Arg1': np.nan,
            'Arg2': np.nan,
            'Arg3': np.nan,
            'Clip_Min': np.nan,
            'Clip_Max': np.nan,
            'Sampling_Strategy_Raw': strategy,
            'Covered_Prior_Codes': covered,
        })

    df = pd.DataFrame(rows)

    # Add Arg*_Meaning documentation
    arg_docs = {
        'Triangular':  ('Min', 'Mode', 'Max'),
        'PERT':        ('Min', 'Mode', 'Max'),
        'Normal':      ('Mean (μ)', 'Std (σ)', np.nan),
        'Lognormal':   ('Mu (ln-mean)', 'Sigma (ln-std)', np.nan),
        'Uniform':     ('Min', 'Max', np.nan),
        'Continuous':  ('Min', 'Max', np.nan),
        'Discrete':    ('Value_Pool', np.nan, np.nan),
        'Truncated':   ('Min', 'Max', np.nan),
    }

    arg1_doc, arg2_doc, arg3_doc = [], [], []
    for _, row in df.iterrows():
        docs = arg_docs.get(row['Distribution'], ('Arg1', 'Arg2', 'Arg3'))
        arg1_doc.append(docs[0])
        arg2_doc.append(docs[1])
        arg3_doc.append(docs[2])

    df['Arg1_Meaning'] = arg1_doc
    df['Arg2_Meaning'] = arg2_doc
    df['Arg3_Meaning'] = arg3_doc

    # Select and order columns
    cols = [
        'Param_Code', 'Param_Category', 'Param_Category_Num',
        'Physical_Meaning', 'Distribution',
        'Arg1', 'Arg2', 'Arg3',
        'Arg1_Meaning', 'Arg2_Meaning', 'Arg3_Meaning',
        'Clip_Min', 'Clip_Max',
        'Sampling_Strategy_Raw', 'Covered_Prior_Codes',
    ]
    df = df[cols].copy()

    # Add metadata
    df.attrs['description'] = (
        '蒙特卡洛抽样配置矩阵 — 全部 29 个具体参数的分布类型与抽样策略。'
        '由 Sheet 4 的 3 大类宏定义展开为具体参数，与 Prior_Matrix 通过 Covered_Prior_Codes 列联动。'
    )
    df.attrs['usage'] = (
        'Distribution: 推荐概率分布。Arg1/2/3: 分布参数（待填，参见Arg*_Meaning）。'
        'Clip_Min/Max: 物理截断边界。Covered_Prior_Codes: 对应的Prior_Matrix参数代码。'
    )

    # Print summary
    n_cat1 = df[df['Param_Category_Num'] == 1].shape[0]
    n_cat2 = df[df['Param_Category_Num'] == 2].shape[0]
    n_cat3 = df[df['Param_Category_Num'] == 3].shape[0]
    print(f"  MonteCarlo_Config_Matrix: {len(df)} rows × {len(df.columns)} cols")
    print(f"    Category 1 (Time/Behavior):    {n_cat1} params")
    print(f"    Category 2 (Scale-dependent):  {n_cat2} params")
    print(f"    Category 3 (Physical/Engineer):{n_cat3} params")
    print(f"  Distributions: {df['Distribution'].value_counts().to_dict()}")

    return df


# =============================================================================
# Main pipeline
# =============================================================================

def ghg_lca():
    """Run the full data preprocessing pipeline."""
    print("=" * 70)
    print("  MODEL PARAMETERS — DATA PREPROCESSING PIPELINE")
    print(f"  Input: {XLSX_PATH}")
    print("=" * 70)

    # Verify input exists
    if not os.path.exists(XLSX_PATH):
        print(f"\n  ERROR: Input file not found: {XLSX_PATH}")
        print("  Please ensure Model_parameters.xlsx is in the model_parameters/ folder.")
        sys.exit(1)

    # ---- Build all 4 matrices ----
    prior = build_prior_matrix()
    species_cf = build_species_cf_matrix()
    scenario = build_scenario_multiplier_matrix()
    mc_config = build_montecarlo_config_matrix()

    # ---- Save to CSV ----
    print("\n" + "=" * 70)
    print("  Saving output files...")
    print("=" * 70)

    csv_outputs = [
        (prior, OUT_CSV_PRIOR, "Prior_Matrix"),
        (species_cf, OUT_CSV_SPECIES, "Species_CF_Matrix"),
        (scenario, OUT_CSV_SCENARIO, "Scenario_Multiplier_Matrix"),
        (mc_config, OUT_CSV_MC, "MonteCarlo_Config_Matrix"),
    ]

    for df, path, name in csv_outputs:
        try:
            df.to_csv(path, index=False, encoding='utf-8-sig')
            print(f"  [OK] {name} → {path}")
        except PermissionError:
            alt_path = path.replace('.csv', '_NEW.csv')
            df.to_csv(alt_path, index=False, encoding='utf-8-sig')
            print(f"  [OK] {name} → {alt_path} (fallback — original file locked)")

    # ---- Save combined Excel ----
    try:
        with pd.ExcelWriter(OUT_XLSX, engine='openpyxl') as writer:
            prior.to_excel(writer, sheet_name='Prior_Matrix', index=False)
            species_cf.to_excel(writer, sheet_name='Species_CF_Matrix', index=False)
            scenario.to_excel(writer, sheet_name='Scenario_Multiplier_Matrix', index=False)
            mc_config.to_excel(writer, sheet_name='MonteCarlo_Config_Matrix', index=False)
        print(f"  [OK] Combined Excel → {OUT_XLSX}")
    except PermissionError:
        alt_xlsx = OUT_XLSX.replace('.xlsx', '_NEW.xlsx')
        with pd.ExcelWriter(alt_xlsx, engine='openpyxl') as writer:
            prior.to_excel(writer, sheet_name='Prior_Matrix', index=False)
            species_cf.to_excel(writer, sheet_name='Species_CF_Matrix', index=False)
            scenario.to_excel(writer, sheet_name='Scenario_Multiplier_Matrix', index=False)
            mc_config.to_excel(writer, sheet_name='MonteCarlo_Config_Matrix', index=False)
        print(f"  [OK] Combined Excel → {alt_xlsx} (fallback — original file locked)")

    # ---- Summary ----
    print("\n" + "=" * 70)
    print("  PIPELINE COMPLETE — Output Summary")
    print("=" * 70)
    print(f"  Prior_Matrix:                {len(prior)} rows × {len(prior.columns)} cols")
    print(f"  Species_CF_Matrix:           {len(species_cf)} rows × {len(species_cf.columns)} cols")
    print(f"  Scenario_Multiplier_Matrix:  {len(scenario)} rows × {len(scenario.columns)} cols")
    print(f"  MonteCarlo_Config_Matrix:    {len(mc_config)} rows × {len(mc_config.columns)} cols")
    print(f"\n  CSV files saved to: {BASE_DIR}/")
    print(f"  Combined Excel:    {os.path.basename(OUT_XLSX)}")
    print("=" * 70)

    return prior, species_cf, scenario, mc_config


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ghg_lca()
