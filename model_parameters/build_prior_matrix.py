#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
build_prior_matrix.py — 重构 Prior_Matrix.csv (v3.0 燃油方法论更新)
=============================================================================
核心变化:
  1. >=12m 渔船: 柴油中速机(MSD/MDO), SFCbase + SFOC负荷公式 → 实际SFC
  2. <12m 渔船: 汽油舷外机, 无辅机, 直接SFR查值(EPA)
  3. 转运船(TP): 重油低速机(SSD/HFO)
  4. 辅助船(SA): 柴油中速机(MSD/MDO)
  5. 负荷统一来源: R22 (Cruise=80%=T_move, Manoeuvring=20%=T_work)
  6. 辅机负荷: Uniform(0.30, 0.50), 不分phase
  7. CH4/N2O EF: IMO Fourth GHG Study (按发动机类型)
  8. CO2 EF: 按燃料类型 (HFO=3.114, MDO=3.206, Gasoline=3.158)
  9. 删除旧SFR/LF数据, 保留EPA汽油相关数据

参考来源 (Model_parameters.xlsx):
  R22 — 运行负荷 (Cruise 80/30, Manoeuvring 20/50)
  R33 — 引擎分类 (>=12m→MSD, TP→SSD, SA→MSD, <12m→Gasoline)
  R43 — IMO SFCbase table (by engine type, fuel type, era)
  R45-R49 — IMO GHG EF (CH4, N2O by engine type; CO2 by fuel type)

输出: model_parameters/Prior_Matrix.csv
=============================================================================
"""

import os
import sys
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, "Prior_Matrix.csv")

rows = []

def add(section, code, name_cn, flag="ALL", gear="ALL", sector="ALL",
        len_cat="ALL", v_best=None, v_low=None, v_high=None,
        unit="", dist="Discrete", source="", s1_row="", note=""):
    """Add a row to the Prior_Matrix."""
    rows.append({
        'Param_Section':    section,
        'Param_Code':       code,
        'Param_Name_CN':    name_cn,
        'Flag':             flag,
        'Gear':             gear,
        'Sector':           sector,
        'Length_Category':  len_cat,
        'Value_Best':       v_best if v_best is not None else np.nan,
        'Value_Low':        v_low if v_low is not None else np.nan,
        'Value_High':       v_high if v_high is not None else np.nan,
        'Unit':             unit,
        'Distribution':     dist,
        'Source_Citation':  source,
        'Sheet1_Row':       s1_row,
        'Note':             note,
    })

# ===========================================================================
# SECTION A: 船舶分类标准 (Vessel Classification)
# ===========================================================================

add('A', 'LENGTH_THRESHOLD_SECTOR_M', 'Sector划分船长阈值 (EU标准)',
    'ALL', 'ALL', 'ALL', 'ALL', 12.0, None, None, 'm', 'Discrete',
    'Council Regulation (EC) No 1198/2006 of 27 July 2006 on the European Fisheries Fund, Article 26',
    'R4',
    'I (Industrial): >=12m; APW (Artisanal): <12m. '
    '按欧盟标准统一划分。用于Sector二元分类和发动机类型/燃料类型判定。')

add('A', 'LENGTH_THRESHOLD_SFR_M', 'SFR/EF阶梯分界船长阈值 (统一EU标准)',
    'ALL', 'ALL', 'ALL', 'ALL', 12.0, None, None, 'm', 'Discrete',
    'Council Regulation (EC) No 1198/2006; Greer et al. (2019) Mar. Policy 107:103382',
    'R4-R5',
    '<12m: 汽油舷外机, 无辅机, 直接SFR; >=12m: 柴油机+辅机, SFCbase+SFOC公式. '
    '统一使用EU 12m标准。')

# ===========================================================================
# SECTION B: 船舶作业活动参数 (Fishing Activity Parameters)
# T_map (年出海天数) 和 H_map (日运行小时)
# 注意: LF (负荷因子) 已移至 Section C3, 与燃油计算参数放在一起
# ===========================================================================

parker_citation = (
    'Parker RWR, Vazquez-Rowe I, Tyedmers PH. (2014). '
    'Fuel performance and carbon footprint of the global purse seine tuna fleet. '
    'J. Clean. Prod. 103:517-524. DOI:10.1016/j.jclepro.2014.05.017'
)

jha_citation = (
    'Jha PN, VS Y, MV B, Edwin L. (2026). '
    'Environmental burden of fishing: Assessment of fuel consumption and the '
    'carbon footprint by mechanized fishing vessels operating in the '
    'southeastern Arabian Sea. '
    'Thalassas: Int. J. Mar. Sci. 42:18. DOI:10.1007/s41208-025-01026-8'
)

anticamara_citation = (
    'Anticamara JA, Watson R, Gelchu A, Pauly D. (2011). '
    'Global fishing effort (1950-2010): Trends, gaps, and implications. '
    'Fish. Res. 107(1-3):131-136. DOI:10.1016/j.fishres.2010.10.016'
)

# ─── T_map: Tier 1 — Parker PS by Ocean (post-1990, FAD era) ───
add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS Atlantic',
    'Atlantic', 'PS', 'I', 'ALL', 297.0, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    'Tier 1 — 大西洋围网: 297 days/year. n=9, avg LOA=70.6m. '
    '适用于ICCAT水域, 1990年后FAD时代.')

add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS Indian',
    'Indian', 'PS', 'I', 'ALL', 289.0, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    'Tier 1 — 印度洋围网: 289 days/year. n=9, avg LOA=81.7m. '
    '适用于IOTC水域, 1990年后FAD时代.')

add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS Pacific',
    'Pacific', 'PS', 'I', 'ALL', 244.0, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    'Tier 1 — 太平洋围网: 244 days/year. n=75, avg LOA=68.9m. '
    '适用于WCPFC+IATTC水域, 1990年后FAD时代.')

parker_mean = round((297 + 289 + 244) / 3, 1)  # 276.7
add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 1: Parker PS 缺省均值',
    'ALL', 'PS', 'I', 'ALL', parker_mean, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    f'Tier 1 — 未映射组织默认值: mean(Atlantic 297, Indian 289, Pacific 244) '
    f'= {parker_mean} days/year.')

# ─── T_map: Tier 2 — Jha LL Indian Ocean ───
add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 2: Jha LL Indian Ocean',
    'Asia', 'LL', 'APW', '<12m', 245.0, 234.0, 256.0, 'days/year', 'Triangular',
    jha_citation, 'R15',
    'Tier 2 — 印度洋机械化延绳钓: 234-256 days/year. '
    '16-20m mechanized longline-cum-gillnet vessels, SE Arabian Sea.')

# ─── T_map: Tier 3 — Anticamara LL/PS by Continent ───
ll_das = {
    'Africa': 274, 'Asia': 334, 'Australia & Oceania': 334,
    'Europe': 304, 'North America': 304, 'South America': 304,
}
for region, das in ll_das.items():
    add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 3: Anticamara LL',
        region, 'LL', 'ALL', 'ALL', das, None, None,
        'days/year', 'Triangular', anticamara_citation, 'R7',
        f'Tier 3 — LL {region}: {das} days/year (Anticamara et al. 2011).')

ps_das = {
    'Africa': 159, 'Asia': 195, 'Australia & Oceania': 195,
    'Europe': 177, 'North America': 177, 'South America': 177,
}
for region, das in ps_das.items():
    add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Tier 3: Anticamara PS',
        region, 'PS', 'ALL', 'ALL', das, None, None,
        'days/year', 'Triangular', anticamara_citation, 'R8',
        f'Tier 3 — PS {region}: {das} days/year (Anticamara et al. 2011).')

# PS China expert override
add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — China PS expert',
    'Asia', 'PS', 'I', 'ALL', 200.0, None, None, 'days/year', 'Triangular',
    'Expert consultation (谢斌老师咨询) — China PS fleet.', 'R9',
    'China-specific PS DAS=200, 高于亚洲区域均值(195).')

# Transport vessel
add('B', 'T_map_DAS', '年出海天数 (Days at Sea) — Transport vessel',
    'ALL', 'TP', 'I', 'ALL', 180.0, None, None, 'days/year', 'Triangular',
    'Inferred from R10: "Transport 15 days per month" → 15×12=180 days/year.',
    'R10',
    '转运船/冷藏运输船: 15 days/month × 12 = 180 days/year.')

# ─── T_map: ALL-region fallbacks ───
for gear, gear_label in [('LL', 'Longline'), ('PS', 'Purse Seine')]:
    gear_vals = []
    for r in rows:
        if r['Param_Code'] == 'T_map_DAS' and r['Gear'] == gear and r['Flag'] != 'ALL':
            gear_vals.append(r['Value_Best'])
    if gear_vals:
        mean_das = round(np.mean(gear_vals), 1)
        add('B', 'T_map_DAS', '年出海天数 (Days at Sea)',
            'ALL', gear, 'ALL', 'ALL', mean_das, None, None,
            'days/year', 'Triangular', anticamara_citation, 'R7-R11',
            f'ALL-region fallback: mean of {len(gear_vals)} regional values = {mean_das} days/year.')

# ─── H_map: Daily Engine Hours ───
add('B', 'H_map_Hday', '日主机运行小时数 (Daily Engine Hours) — Industrial',
    'ALL', 'ALL', 'I', 'ALL', 24.0, None, None, 'h/day', 'Triangular',
    'Greer et al. (2019) Mar. Policy 107:103382; Korican et al. (2023) Ocean Eng. 286:115734',
    'R18,R20',
    'Industrial: 24h continuous deep-sea operation.')

add('B', 'H_map_Hday', '日主机运行小时数 (Daily Engine Hours) — APW',
    'ALL', 'ALL', 'APW', 'ALL', 12.0, 4.0, 12.0, 'h/day', 'Triangular',
    'Greer et al. (2019) smallscale=4h; PNAS alpha-analysis: observed median ~9h/day → 12h',
    'R19,R21',
    'APW: coastal daytime operation. 保守取12h作为最佳估计, 4h作为下限.')

# PS-specific engine hours
add('B', 'H_map_Main_PS', 'PS主机日运行小时数',
    'ALL', 'PS', 'I', 'ALL', 4.0, None, None, 'h/day', 'Triangular',
    'Korican et al. (2023) Ocean Eng. 286:115734', 'R17',
    'PS ghg_lca engine: ~4h/day (short high-power bursts for setting/hauling).')

add('B', 'H_map_Aux_PS', 'PS辅机日运行小时数',
    'ALL', 'PS', 'I', 'ALL', 15.0, None, None, 'h/day', 'Triangular',
    'Korican et al. (2023) Ocean Eng. 286:115734', 'R17',
    'PS auxiliary engine: ~15h/day (hydraulic pumps, refrigeration, lighting).')

# ===========================================================================
# SECTION C0: 发动机类型与燃料类型映射 (Engine & Fuel Type Mapping)
# 来源: R33 (引擎分类) + 用户指令
# ===========================================================================

# --- Engine Type ---
add('C', 'ENGINE_TYPE_FISHING_GE12M', '>=12m捕捞船发动机类型',
    'ALL', 'ALL', 'I', '>=12m', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); 用户指令 — 渔船柴油机视作中速机(MSD)',
    'R33',
    'MSD (Medium-Speed Diesel, 中速四冲程柴油机). '
    '适用于>=12m的LL/PS/SA渔船主机和辅机. '
    '依据R33: 远洋渔船绝大多数采用中速四冲程柴油机.')

add('C', 'ENGINE_TYPE_TP', '转运船发动机类型',
    'ALL', 'TP', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); 用户指令 — 转运船重油发动机视作慢速机(SSD)',
    'R33',
    'SSD (Slow-Speed Diesel, 低速二冲程柴油机). '
    '适用于转运船/冷藏运输船(TP)主机.')

add('C', 'ENGINE_TYPE_SA', '辅助船发动机类型',
    'ALL', 'SA', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); 用户指令 — 辅助船柴油发动机视作中速机(MSD)',
    'R33',
    'MSD (Medium-Speed Diesel, 中速四冲程柴油机). 辅助船与捕捞船同型.')

add('C', 'ENGINE_TYPE_FISHING_LT12M', '<12m捕捞船发动机类型',
    'ALL', 'ALL', 'APW', '<12m', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); 用户指令 — <12m使用汽油舷外机',
    'R33',
    'Gasoline_Outboard (汽油舷外机). <12m小型渔船使用汽油机, 无辅机.')

# --- Fuel Type ---
add('C', 'FUEL_TYPE_FISHING_GE12M', '>=12m捕捞船燃料类型',
    'ALL', 'ALL', 'I', '>=12m', None, None, None, 'categorical', 'Discrete',
    'IMO (2020) Fourth IMO GHG Study; 用户指令',
    'R43',
    'MDO (Marine Diesel Oil, 船用柴油). >=12m渔船使用轻柴油.')

add('C', 'FUEL_TYPE_TP', '转运船燃料类型',
    'ALL', 'TP', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'IMO (2020) Fourth IMO GHG Study; 用户指令 — 转运船使用重油(HFO)',
    'R43',
    'HFO (Heavy Fuel Oil, 重质燃料油). 转运船/冷藏运输船使用重油.')

add('C', 'FUEL_TYPE_SA', '辅助船燃料类型',
    'ALL', 'SA', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'IMO (2020) Fourth IMO GHG Study; 用户指令',
    'R43',
    'MDO (Marine Diesel Oil, 船用柴油). 辅助船与捕捞船同型, 使用轻柴油.')

add('C', 'FUEL_TYPE_FISHING_LT12M', '<12m捕捞船燃料类型',
    'ALL', 'ALL', 'APW', '<12m', None, None, None, 'categorical', 'Discrete',
    'U.S. EPA (2025); 用户指令',
    'R33',
    'Gasoline (汽油). <12m小型渔船使用汽油舷外机.')

# ===========================================================================
# SECTION C1: SFCbase 基准油耗率 (IMO Fourth GHG Study Table 4)
# 来源: R43
# SFC_actual = SFC_base × (0.455×L² − 0.71×L + 1.28)  [仅适用于>=12m柴油机]
# ===========================================================================

imo_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO. Table 4 — '
    'Proposed Specific Fuel Consumption (SFC; g/kWh) values.'
)

sfcbase_data = [
    # (Engine_Type, Fuel_Type, Era, Value_g_kWh, Era_Label)
    # SSD — Slow-Speed Diesel (转运船 TP)
    ('SSD', 'HFO', 'Before 1983', 205, 'SSD_HFO_PRE1983'),
    ('SSD', 'HFO', '1984-2000',  185, 'SSD_HFO_1984_2000'),
    ('SSD', 'HFO', '2001+',      175, 'SSD_HFO_2001PLUS'),
    ('SSD', 'MDO', 'Before 1983', 190, 'SSD_MDO_PRE1983'),
    ('SSD', 'MDO', '1984-2000',  175, 'SSD_MDO_1984_2000'),
    ('SSD', 'MDO', '2001+',      165, 'SSD_MDO_2001PLUS'),
    # MSD — Medium-Speed Diesel (>=12m 渔船 LL/PS/SA)
    ('MSD', 'HFO', 'Before 1983', 215, 'MSD_HFO_PRE1983'),
    ('MSD', 'HFO', '1984-2000',  195, 'MSD_HFO_1984_2000'),
    ('MSD', 'HFO', '2001+',      185, 'MSD_HFO_2001PLUS'),
    ('MSD', 'MDO', 'Before 1983', 200, 'MSD_MDO_PRE1983'),
    ('MSD', 'MDO', '1984-2000',  185, 'MSD_MDO_1984_2000'),
    ('MSD', 'MDO', '2001+',      175, 'MSD_MDO_2001PLUS'),
    # HSD — High-Speed Diesel (备用/参考)
    ('HSD', 'HFO', 'Before 1983', 225, 'HSD_HFO_PRE1983'),
    ('HSD', 'HFO', '1984-2000',  205, 'HSD_HFO_1984_2000'),
    ('HSD', 'HFO', '2001+',      195, 'HSD_HFO_2001PLUS'),
    ('HSD', 'MDO', 'Before 1983', 210, 'HSD_MDO_PRE1983'),
    ('HSD', 'MDO', '1984-2000',  190, 'HSD_MDO_1984_2000'),
    ('HSD', 'MDO', '2001+',      185, 'HSD_MDO_2001PLUS'),
    # MeOH (甲醇) — 替代燃料, 仅2001+有值
    ('SSD', 'MeOH', '2001+',     350, 'SSD_MEOH_2001PLUS'),
    ('MSD', 'MeOH', '2001+',     370, 'MSD_MEOH_2001PLUS'),
    # Auxiliary Engine (辅机) — 辅机通常为中速四冲程柴油发电机组,
    # SFCbase采用MSD对应燃料类型的值 (IMO Table 4惯例)
    ('AUX', 'HFO', 'Before 1983', 215, 'AUX_HFO_PRE1983'),
    ('AUX', 'HFO', '1984-2000',  195, 'AUX_HFO_1984_2000'),
    ('AUX', 'HFO', '2001+',      185, 'AUX_HFO_2001PLUS'),
    ('AUX', 'MDO', 'Before 1983', 200, 'AUX_MDO_PRE1983'),
    ('AUX', 'MDO', '1984-2000',  185, 'AUX_MDO_1984_2000'),
    ('AUX', 'MDO', '2001+',      175, 'AUX_MDO_2001PLUS'),
]

# 标记N/A的SFCbase (MeOH在1983年前和1984-2000期间不适用)
sfcbase_na_entries = {
    'SSD_MEOH_PRE1983', 'SSD_MEOH_1984_2000',
    'MSD_MEOH_PRE1983', 'MSD_MEOH_1984_2000',
}

for eng, fuel, era, val, code_suffix in sfcbase_data:
    code = f'SFC_BASE_{code_suffix}'
    name = f'SFC基准值 — {eng} {fuel} ({era})'
    note = (f'IMO Table 4: {eng} engine, {fuel} fuel, {era}. '
            f'SFCbase = {val} g/kWh. '
            f'用于SFC_actual = SFCbase × SFOC_load_formula(LF). '
            f'仅适用于>=12m柴油机. 汽油舷外机不使用此公式.')
    add('C', code, name,
        'ALL', 'ALL', 'ALL', 'ALL', float(val), None, None,
        'g/kWh', 'Discrete', imo_citation, 'R43', note)

# SFCbase 年份分段边界 (用于模型查询)
add('C', 'SFC_BASE_ERA_BOUNDARY_1', 'SFCbase年份分段边界1 (Pre-1983截止)',
    'ALL', 'ALL', 'ALL', 'ALL', 1983.0, None, None, 'year', 'Discrete',
    imo_citation, 'R43',
    'Builtdate < 1984 → SFCbase = "Before 1983" column. '
    '边界年1983为Pre-1983时段的最后一年.')

add('C', 'SFC_BASE_ERA_BOUNDARY_2', 'SFCbase年份分段边界2 (1984-2000截止)',
    'ALL', 'ALL', 'ALL', 'ALL', 2000.0, None, None, 'year', 'Discrete',
    imo_citation, 'R43',
    '1984 <= Builtdate <= 2000 → SFCbase = "1984-2000" column. '
    '2001+ → SFCbase = "2001+" column.')

# ===========================================================================
# SECTION C2: SFOC 负荷修正公式系数 (Jalkanen et al. 2012)
# 来源: R34
# SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28)
# ===========================================================================

jalkanen_citation = (
    'Jalkanen, J.-P., Johansson, L., Kukkonen, J., Brink, A., Kalli, J., & Stipa, T. (2012). '
    'Extension of an assessment model of ship traffic exhaust emissions for particulate matter '
    'and carbon monoxide. Atmos. Chem. Phys. 12:2641-2659. DOI:10.5194/acp-12-2641-2012'
)

add('C', 'SFOC_LOAD_COEFF_A', 'SFOC-负荷二次项系数 (L²)',
    'ALL', 'ALL', 'I', '>=12m', 0.455, None, None, 'dimensionless', 'Discrete',
    jalkanen_citation, 'R34',
    'SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28). '
    '仅适用于>=12m四冲程柴油主机和辅机。L=发动机负荷因子(LF, 额定功率比例). '
    '示例: L=0.80→factor=1.003, L=0.20→factor=1.156, L=0.50→factor=1.039.')

add('C', 'SFOC_LOAD_COEFF_B', 'SFOC-负荷一次项系数 (L)',
    'ALL', 'ALL', 'I', '>=12m', -0.71, None, None, 'dimensionless', 'Discrete',
    jalkanen_citation, 'R34',
    '一次项系数。抛物线公式在L≈0.78附近取最小值(最经济工况).')

add('C', 'SFOC_LOAD_COEFF_C', 'SFOC-负荷常数项系数',
    'ALL', 'ALL', 'I', '>=12m', 1.28, None, None, 'dimensionless', 'Discrete',
    jalkanen_citation, 'R34',
    '常数项。L=0(怠速)时SFOC为基准值的1.28倍; L=1(全负荷)时≈1.025倍.')

add('C', 'SFOC_LOAD_APPLICABILITY', 'SFOC-负荷公式适用范围',
    'ALL', 'ALL', 'I', '>=12m', 1.0, None, None, 'binary flag', 'Discrete',
    jalkanen_citation + '; 仅适用于>=12m柴油机(主机+辅机)',
    'R34',
    '1=适用(>=12m柴油机, 主机和辅机均适用此公式). '
    '0=不适用(<12m汽油舷外机, 使用EPA直接SFR值). '
    '辅机负荷建议固定在高效区间(30%-50%), 使用同一SFOC公式计算实际SFC.')

# ===========================================================================
# SECTION C3: 发动机运行负荷因子 (Load Factors)
# 来源: R22 (EMEP/EEA Guidebook 2019) + R23 (EPA 汽油舷外机)
#
# 逻辑:
#   >=12m 柴油机:
#     LF_move  = 0.80 (Cruise/MCR≥65%, EMEP/EEA)
#     LF_work  = 0.20 (Manoeuvring/MCR<20%, EMEP/EEA)
#     LF_aux   = Uniform(0.30, 0.50) (辅机不分phase, 统一负荷区间)
#   <12m 汽油舷外机:
#     LF_move  = 0.80 (EPA巡航负荷)
#     LF_work  = 0.201 (EPA船用舷外机认证循环平均负荷)
#     无辅机
# ===========================================================================

emep_citation = (
    'De Lauretis, R., Ntziachristos, L., & Trozzi, C. (2021). '
    '1.A.3.d.i, 1.A.3.d.ii, 1.A.4.c.iii Navigation (shipping) (Update Dec. 2021). '
    'In European Environment Agency (Ed.), EMEP/EEA air pollutant emission inventory guidebook 2019. '
    'Copenhagen, Denmark: European Environment Agency.'
)

epa_lf_citation = (
    'U.S. EPA. Median Life, Annual Activity, and Load Factor Values for '
    'Nonroad Engine Emissions Modeling. EPA-420-R-10-016 (NR-005d).'
)

# --- >=12m Industrial (柴油 MSD/MDO) ---
add('C', 'LF_MAIN_MOVE', '主机航行阶段负荷因子 (T_move — Cruise)',
    'ALL', 'ALL', 'I', '>=12m', 0.80, None, None, 'fraction of MCR', 'Discrete',
    emep_citation,
    'R22',
    '>=12m柴油主机 T_move (Cruise): MCR≥65%, 典型负荷80% (EMEP/EEA R22). '
    '对应R22 "Cruise: Main=80%".')

add('C', 'LF_MAIN_WORK', '主机作业阶段负荷因子 (T_work — Manoeuvring)',
    'ALL', 'ALL', 'I', '>=12m', 0.20, None, None, 'fraction of MCR', 'Discrete',
    emep_citation,
    'R22',
    '>=12m柴油主机 T_work (Manoeuvring): MCR<20% (EMEP/EEA R22). '
    '对应R22 "Manoeuvring: Main=20%". '
    'T_work含放钓/收钓/下网/起网等捕捞作业.')

add('C', 'LF_AUX', '辅机运行负荷因子 (不分phase, 统一负荷区间)',
    'ALL', 'ALL', 'I', '>=12m', 0.40, 0.30, 0.50, 'fraction of MCR', 'Uniform',
    emep_citation,
    'R22',
    '>=12m辅机统一负荷: Uniform(0.30, 0.50), Best取中点0.40. '
    '对应R22 "Cruise: Aux=30%, Manoeuvring: Aux=50%". '
    '辅机不分T_move/T_work阶段, 统一固定负荷运行. '
    '使用SFOC公式计算实际SFC时, 代入此LF值.')

# --- <12m APW (汽油舷外机) ---
add('C', 'LF_MAIN_MOVE_GASOLINE', '汽油舷外机航行阶段负荷因子 (T_move)',
    'ALL', 'ALL', 'APW', '<12m', 0.80, None, None, 'fraction of MCR', 'Discrete',
    '用户指令 — 汽油舷外机航行阶段负荷采用0.8',
    'R22-R23',
    '<12m汽油舷外机 T_move: 0.80 (与柴油机巡航负荷相同).')

add('C', 'LF_MAIN_WORK_GASOLINE', '汽油舷外机作业阶段负荷因子 (T_work)',
    'ALL', 'ALL', 'APW', '<12m', 0.201, None, None, 'fraction of MCR', 'Discrete',
    epa_lf_citation + '; 用户指令 — 汽油机运行负荷采用0.201',
    'R23',
    '<12m汽油舷外机 T_work: EPA船用舷外机认证测试循环平均负荷=20.7%≈0.201. '
    'EPA-420-R-10-016 (NR-005d): 船用舷外机法定综合工况默认值.')

# --- 辅机适用性标记 ---
add('C', 'HAS_AUX_ENGINE', '是否有辅机',
    'ALL', 'ALL', 'I', '>=12m', 1.0, None, None, 'binary flag', 'Discrete',
    '用户指令 — >=12m有辅机, <12m无辅机',
    'R22',
    '1=有辅机(>=12m柴油船). 辅机用于发电/液压/制冷等.')

add('C', 'HAS_AUX_ENGINE', '是否有辅机 (<12m无辅机)',
    'ALL', 'ALL', 'APW', '<12m', 0.0, None, None, 'binary flag', 'Discrete',
    '用户指令 — <12m汽油船无辅机',
    'R22-R23',
    '0=无辅机(<12m汽油舷外机). 小型渔船主机直接驱动所有设备, 无独立辅机.')

# ===========================================================================
# SECTION C4: CO₂ 燃烧排放因子 (by Fuel Type)
# 来源: R49 (IMO 2020)
# ===========================================================================

imo_ef_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO.'
)

add('C', 'EF_CO2_HFO', '重油(HFO)CO₂燃烧排放因子',
    'ALL', 'ALL', 'I', 'ALL', 3.114, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    '重质燃料油(HFO)燃烧CO₂排放因子: 3.114 kg CO₂/g fuel = 3.114 tCO2/tFuel. '
    '适用于转运船(TP)主机.')

add('C', 'EF_CO2_MDO', '船用柴油(MDO)CO₂燃烧排放因子',
    'ALL', 'ALL', 'I', '>=12m', 3.206, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    '船用轻柴油(MDO)燃烧CO₂排放因子: 3.206 kg CO₂/g fuel = 3.206 tCO2/tFuel. '
    '适用于>=12m渔船(LL/PS/SA)主机和辅机.')

add('C', 'EF_CO2_Gasoline', '汽油CO₂燃烧排放因子',
    'ALL', 'ALL', 'APW', '<12m', 3.158, None, None, 'tCO2/tFuel', 'Discrete',
    'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
    'Table 2: Mobile Combustion CO2, Motor Gasoline.',
    'EPA_2025',
    '车用/船用汽油燃烧CO₂排放因子. '
    '8.78 kg/gallon ÷ 2.78 kg/gallon = 3.158 kg CO₂/kg 汽油. '
    '适用于<12m汽油舷外机.')

# LNG & Methanol CO2 EF (R49 — 备用/场景分析)
add('C', 'EF_CO2_LNG', '液化天然气(LNG)CO₂燃烧排放因子',
    'ALL', 'ALL', 'ALL', 'ALL', 2.750, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    'LNG燃烧CO₂排放因子: 2.750 kg CO₂/g fuel = 2.750 tCO2/tFuel. '
    '低碳化石燃料. 用于场景分析.')

add('C', 'EF_CO2_Methanol', '甲醇(MeOH)CO₂燃烧排放因子',
    'ALL', 'ALL', 'ALL', 'ALL', 1.375, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    '甲醇燃烧CO₂排放因子: 1.375 kg CO₂/g fuel = 1.375 tCO2/tFuel. '
    '替代燃料. 用于场景分析.')

# ===========================================================================
# SECTION C5: CH₄ 排放因子 (by Engine Type, IMO 2020)
# 来源: R47 (IMO Table 56 — LNG CH4 EF) + R48 (IMO Table 58 — HFO/MDO/MeOH CH4 EF)
# CH4排放计算: P × LF_avg × hours × EF_CH4(g/kWh) / 1e6 × GWP_CH4
# ===========================================================================

imo_ch4_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO. '
    'Table 58 — Energy-based emissions factors for CH4 for different engine types '
    '(HFO, LSHFO & MDO).'
)

imo_ch4_lng_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO. '
    'Table 56 — Energy-based emissions factors for CH4 for different engine types '
    '(LNG).'
)

add('C', 'EF_CH4_SSD', '柴油CH₄排放因子—低速二冲程(SSD)',
    'ALL', 'ALL', 'I', 'ALL', 0.010, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'SSD (Slow-Speed Diesel) CH4 EF: 0.010 g/kWh (IMO Table 58). '
    '适用于转运船(TP)主机. 所有发动机世代和Tier统一使用此值.')

add('C', 'EF_CH4_MSD', '柴油CH₄排放因子—中速四冲程(MSD)',
    'ALL', 'ALL', 'I', 'ALL', 0.010, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'MSD (Medium-Speed Diesel) CH4 EF: 0.010 g/kWh (IMO Table 58). '
    '适用于>=12m渔船(LL/PS/SA)主机和辅机. 所有发动机世代和Tier统一使用此值.')

add('C', 'EF_CH4_AUX', '辅机CH₄排放因子',
    'ALL', 'ALL', 'I', 'ALL', 0.010, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'Auxiliary Engine CH4 EF: 0.010 g/kWh (IMO Table 58). '
    '适用于所有>=12m渔船辅机.')

# EPA 汽油 CH4 (保留)
add('C', 'EF_CH4_GASOLINE_2STROKE', '汽油CH₄排放因子—二冲程舷外机',
    'ALL', 'ALL', 'APW', '<12m', 3.76, None, None, 'g/kgFuel', 'Lognormal',
    'U.S. EPA (2025). Table 5: Mobile Combustion CH4 and N2O for '
    'Non-Road Vehicles, Ships and Boats.',
    'EPA_2025',
    '老式二冲程汽油舷外机甲烷排放因子. '
    '10.45 g/gallon ÷ 2.78 kg/gallon = 3.76 g CH₄/kg 汽油.')

add('C', 'EF_CH4_GASOLINE_4STROKE', '汽油CH₄排放因子—四冲程舷外机',
    'ALL', 'ALL', 'APW', '<12m', 1.50, None, None, 'g/kgFuel', 'Lognormal',
    'U.S. EPA (2025). Table 5: Mobile Combustion CH4 and N2O for '
    'Non-Road Vehicles, Ships and Boats.',
    'EPA_2025',
    '现代四冲程汽油舷外机甲烷排放因子. '
    '4.18 g/gallon ÷ 2.78 kg/gallon = 1.50 g CH₄/kg 汽油.')

# --- CH4: MeOH (R48 Table 58) ---
add('C', 'EF_CH4_SSD_MEOH', '柴油CH₄排放因子—SSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.001, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'SSD Methanol CH4 EF: 0.001 g/kWh (IMO Table 58, MeOH column). 用于场景分析.')

add('C', 'EF_CH4_MSD_MEOH', '柴油CH₄排放因子—MSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.001, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'MSD Methanol CH4 EF: 0.001 g/kWh (IMO Table 58, MeOH column). 用于场景分析.')

# --- CH4: Boiler & Gas Turbine (R48 Table 58, HFO/MDO) ---
add('C', 'EF_CH4_BOILER', 'CH₄排放因子—Boiler/Steam Turbine (HFO/MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.002, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'Boiler and Steam Turbine CH4 EF: 0.002 g/kWh (IMO Table 58).')

add('C', 'EF_CH4_GAS_TURBINE', 'CH₄排放因子—Gas Turbine (HFO/MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.002, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'Gas Turbine CH4 EF: 0.002 g/kWh (IMO Table 58).')

# --- CH4: LNG (R47 Table 56) ---
add('C', 'EF_CH4_LNG_OTTO_SS', 'CH₄排放因子—LNG Otto-SS',
    'ALL', 'ALL', 'ALL', 'ALL', 2.5, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Otto-SS (低速火花点火) CH4 EF: 2.5 g/kWh (IMO Table 56). 用于场景分析.')

add('C', 'EF_CH4_LNG_OTTO_MS', 'CH₄排放因子—LNG Otto-MS',
    'ALL', 'ALL', 'ALL', 'ALL', 5.5, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Otto-MS (中速火花点火) CH4 EF: 5.5 g/kWh (IMO Table 56). 用于场景分析.')

add('C', 'EF_CH4_LNG_DIESEL', 'CH₄排放因子—LNG-Diesel (双燃料)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.2, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG-Diesel (双燃料柴油机) CH4 EF: 0.2 g/kWh (IMO Table 56). 用于场景分析.')

add('C', 'EF_CH4_LNG_LBSI', 'CH₄排放因子—LNG LBSI',
    'ALL', 'ALL', 'ALL', 'ALL', 4.1, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG LBSI (Lean-Burn Spark Ignition) CH4 EF: 4.1 g/kWh (IMO Table 56).')

add('C', 'EF_CH4_LNG_AUX', 'CH₄排放因子—LNG Auxiliary Engine',
    'ALL', 'ALL', 'ALL', 'ALL', 5.5, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Auxiliary Engine CH4 EF: 5.5 g/kWh (IMO Table 56). 用于场景分析.')

add('C', 'EF_CH4_LNG_BOILER', 'CH₄排放因子—LNG Boiler/Steam Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.04, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Boiler/Steam Turbine CH4 EF: 0.04 g/kWh (IMO Table 56).')

add('C', 'EF_CH4_LNG_GAS_TURBINE', 'CH₄排放因子—LNG Gas Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.06, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Gas Turbine CH4 EF: 0.06 g/kWh (IMO Table 56).')

# ===========================================================================
# SECTION C6: N₂O 排放因子 (by Engine Type, IMO 2020)
# 来源: R45 (IMO Table 60 — LNG N2O EF) + R46 (IMO Table 59 — HFO/MDO/MeOH N2O EF)
# N2O排放计算: P × LF_avg × hours × EF_N2O(g/kWh) / 1e6 × GWP_N2O
# ===========================================================================

imo_n2o_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO. '
    'Table 59 — Energy-based emissions factors for N2O for different engine types '
    '(HFO, LSHFO & MDO).'
)

imo_n2o_lng_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO. '
    'Table 60 — Energy-based emissions factors for N2O for different engine types '
    '(LNG).')

add('C', 'EF_N2O_SSD_MDO', '柴油N₂O排放因子—SSD/MDO',
    'ALL', 'ALL', 'I', 'ALL', 0.030, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'SSD MDO N2O EF: 0.030 g/kWh (IMO Table 59: SS row, MDO column). '
    '适用于转运船(TP)辅机(如使用MDO).')

add('C', 'EF_N2O_SSD_HFO', '柴油N₂O排放因子—SSD/HFO',
    'ALL', 'ALL', 'I', 'ALL', 0.031, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'SSD HFO N2O EF: 0.031 g/kWh (IMO Table 59: SS row, HFO column). '
    '适用于转运船(TP)主机(使用HFO).')

add('C', 'EF_N2O_MSD_MDO', '柴油N₂O排放因子—MSD/MDO',
    'ALL', 'ALL', 'I', 'ALL', 0.030, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'MSD MDO N2O EF: 0.030 g/kWh (IMO Table 59: MS row, MDO column). '
    '适用于>=12m渔船(LL/PS/SA)主机和辅机.')

add('C', 'EF_N2O_AUX_MDO', '辅机N₂O排放因子—Aux/MDO',
    'ALL', 'ALL', 'I', 'ALL', 0.036, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Auxiliary Engine MDO N2O EF: 0.036 g/kWh (IMO Table 59: Aux row, MDO column). '
    '适用于所有>=12m渔船辅机.')

# EPA 汽油 N2O (保留)
add('C', 'EF_N2O_GASOLINE', '汽油N₂O排放因子',
    'ALL', 'ALL', 'APW', '<12m', 0.04, None, None, 'g/kgFuel', 'Lognormal',
    'U.S. EPA (2025). Table 5: Mobile Combustion CH4 and N2O for '
    'Non-Road Vehicles, Ships and Boats.',
    'EPA_2025',
    '汽油机N₂O排放因子（二冲程与四冲程无显著差异, EPA统一基准）. '
    '0.11 g/gallon ÷ 2.78 kg/gallon = 0.04 g N₂O/kg 汽油.')

# --- N2O: MeOH (R46 Table 59) ---
add('C', 'EF_N2O_SSD_MEOH', 'N₂O排放因子—SSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.003, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'SSD Methanol N2O EF: 0.003 g/kWh (IMO Table 59, MeOH column). 用于场景分析.')

add('C', 'EF_N2O_MSD_MEOH', 'N₂O排放因子—MSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.003, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'MSD Methanol N2O EF: 0.003 g/kWh (IMO Table 59, MeOH column). 用于场景分析.')

# --- N2O: Boiler & Gas Turbine (R46 Table 59, HFO/MDO) ---
add('C', 'EF_N2O_BOILER_HFO', 'N₂O排放因子—Boiler/Steam Turbine (HFO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.040, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Boiler/Steam Turbine HFO N2O EF: 0.040 g/kWh (IMO Table 59).')

add('C', 'EF_N2O_BOILER_MDO', 'N₂O排放因子—Boiler/Steam Turbine (MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.049, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Boiler/Steam Turbine MDO N2O EF: 0.049 g/kWh (IMO Table 59).')

add('C', 'EF_N2O_GAS_TURBINE_HFO', 'N₂O排放因子—Gas Turbine (HFO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.040, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Gas Turbine HFO N2O EF: 0.040 g/kWh (IMO Table 59).')

add('C', 'EF_N2O_GAS_TURBINE_MDO', 'N₂O排放因子—Gas Turbine (MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.049, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Gas Turbine MDO N2O EF: 0.049 g/kWh (IMO Table 59).')

# --- N2O: LNG (R45 Table 60) ---
add('C', 'EF_N2O_LNG_OTTO_SS', 'N₂O排放因子—LNG Otto-SS',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Otto-SS N2O EF: 0.020 g/kWh (IMO Table 60). 用于场景分析.')

add('C', 'EF_N2O_LNG_OTTO_MS', 'N₂O排放因子—LNG Otto-MS',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Otto-MS N2O EF: 0.020 g/kWh (IMO Table 60). 用于场景分析.')

add('C', 'EF_N2O_LNG_DIESEL', 'N₂O排放因子—LNG-Diesel (双燃料)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.030, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG-Diesel N2O EF: 0.030 g/kWh (IMO Table 60). 用于场景分析.')

add('C', 'EF_N2O_LNG_LBSI', 'N₂O排放因子—LNG LBSI',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG LBSI N2O EF: 0.020 g/kWh (IMO Table 60).')

add('C', 'EF_N2O_LNG_AUX', 'N₂O排放因子—LNG Auxiliary Engine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Auxiliary Engine N2O EF: 0.020 g/kWh (IMO Table 60). 用于场景分析.')

add('C', 'EF_N2O_LNG_BOILER', 'N₂O排放因子—LNG Boiler/Steam Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Boiler/Steam Turbine N2O EF: 0.020 g/kWh (IMO Table 60).')

add('C', 'EF_N2O_LNG_GAS_TURBINE', 'N₂O排放因子—LNG Gas Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Gas Turbine N2O EF: 0.020 g/kWh (IMO Table 60).')

# ===========================================================================
# SECTION C7: 上游排放因子 (Well-to-Tank, WTT)
# ===========================================================================

add('C', 'EF_WTT_DIESEL', '柴油上游(WTT)碳排放因子',
    'ALL', 'ALL', 'ALL', 'ALL', 0.369, 0.318, 0.441,
    'kg CO2eq/kg diesel', 'Lognormal',
    'Ecoinvent v3 — market for diesel | diesel | Cutoff, U - RoW (1000 MC simulations)',
    'Ecoinvent_Diesel_WTT',
    '1 kg 柴油上游生产与运输碳排放 (Cradle-to-Tank). '
    'Mean=0.369, SD=0.031, Median=0.366, 95% CI [0.318, 0.441].')

add('C', 'EF_WTT_GASOLINE', '汽油上游(WTT)碳排放因子',
    'ALL', 'ALL', 'APW', 'ALL', 0.535, 0.489, 0.595,
    'kg CO2eq/kg petrol', 'Lognormal',
    'Ecoinvent v3 — market for petrol, two-stroke blend | petrol, two-stroke blend | '
    'Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_Gasoline_WTT',
    '1 kg 汽油上游生产与运输碳排放 (Cradle-to-Tank). '
    'Mean=0.535, SD=0.029, Median=0.532, 95% CI [0.489, 0.595].')

add('C', 'EF_WTT_HFO', '重油上游(WTT)碳排放因子',
    'ALL', 'ALL', 'ALL', 'ALL', 0.252, 0.211, 0.309,
    'kg CO2eq/kg HFO', 'Lognormal',
    'Ecoinvent v3 — market for heavy fuel oil | heavy fuel oil | Cutoff, U - RoW '
    '(1000 MC simulations)',
    'Ecoinvent_HFO_WTT',
    '1 kg 重油上游生产与运输碳排放 (Cradle-to-Tank). '
    'Mean=0.252, SD=0.026, Median=0.250, 95% CI [0.211, 0.309].')

# ===========================================================================
# SECTION C8: GWP (全球增温潜势)
# ===========================================================================

add('C', 'GWP_CH4_100yr', '甲烷 100年全球增温潜势',
    'ALL', 'ALL', 'ALL', 'ALL', 28.5, 27.0, 30.0,
    'kgCO2e/kgCH4', 'Uniform',
    'IPCC AR5/AR6',
    'R50',
    'CH4 GWP-100: IPCC range 27-30, midpoint 28.5 (R50).')

add('C', 'GWP_N2O_100yr', '氧化亚氮 100年全球增温潜势',
    'ALL', 'ALL', 'ALL', 'ALL', 273.0, None, None,
    'kgCO2e/kgN2O', 'Discrete',
    'IPCC AR6',
    'R50',
    'N2O GWP-100: 273 (IPCC AR6, R50).')

# ===========================================================================
# SECTION C9: FC_LOOKUP 燃料效率时间系数
# ===========================================================================

add('C', 'FC_LOOKUP_Baseline_Year', '燃料效率时间系数基准年份',
    'ALL', 'ALL', 'ALL', 'ALL', 2000.0, None, None, 'year', 'Discrete',
    'Yanmar marine engine data (interpolated); Greer et al. (2019)',
    'R55',
    'FC=1.0 at year 2000 (baseline). Pre-2000 >1.0 (less efficient), '
    'post-2004 =0.99 (stable).')

add('C', 'FC_LOOKUP_Min', '燃料效率时间系数最小值',
    'ALL', 'ALL', 'ALL', 'ALL', 0.99, None, None, 'dimensionless', 'Discrete',
    'Yanmar data; 2004-2016 stable period',
    'R55',
    'Minimum FC = 0.99 (most efficient era, 2004-2016).')

add('C', 'FC_LOOKUP_Max', '燃料效率时间系数最大值',
    'ALL', 'ALL', 'ALL', 'ALL', 1.21, None, None, 'dimensionless', 'Discrete',
    'Yanmar data; 1950-1951 peak',
    'R55',
    'Maximum FC = 1.21 (least efficient era, 1950-1951).')

# ===========================================================================
# SECTION C10: 替代燃料 SFR (场景分析用)
# ===========================================================================

add('C', 'SFR_Methanol_Diesel_80', '甲醇-柴油混合 (80%能量替代) SFR',
    'ALL', 'ALL', 'ALL', 'ALL', 0.000439, None, None, 'tFuel/kWh', 'Lognormal',
    'Sjeric et al. (2026) Ocean Eng. 345:123864',
    'R39',
    '438.58 g/kWh = 0.000439 t/kWh. Used in scenario S4, S14.')

add('C', 'SFR_H2_Diesel_80', '氢-柴油混合 (80%能量替代) SFR',
    'ALL', 'ALL', 'ALL', 'ALL', 0.000112, None, None, 'tFuel/kWh', 'Lognormal',
    'Sjeric et al. (2026) Ocean Eng. 345:123864',
    'R40',
    '112.32 g/kWh = 0.000112 t/kWh. Used in scenario S14.')

# ===========================================================================
# SECTION L: EPA汽油舷外机 SFR数据 (保留)
# 汽油舷外机不使用SFOC公式, 直接使用以下SFR值
# ===========================================================================

epa_sfr_citation = (
    'U.S. EPA. Exhaust Emission Factors for Nonroad Engine Modeling — '
    'Spark-Ignition. EPA-420-R-10-019 (NR-010f).'
)

add('L', 'SFR_GASOLINE_2STROKE', 'EPA传统两冲程汽油舷外机SFR',
    'ALL', 'ALL', 'APW', '<12m', 0.000592, 0.000547, 0.000638,
    'tFuel/kWh', 'Triangular',
    epa_sfr_citation,
    'EPA_NR010f',
    '传统两冲程: 0.90-1.05 lb/hp-hr = 547-638 g/kWh. Best=592 g/kWh. '
    '适用于<12m老式二冲程汽油舷外机. 此值直接用作SFR, 不经过SFOC负荷修正.')

add('L', 'SFR_GASOLINE_4STROKE', 'EPA现代四冲程汽油舷外机SFR',
    'ALL', 'ALL', 'APW', '<12m', 0.000319, 0.000304, 0.000334,
    'tFuel/kWh', 'Triangular',
    epa_sfr_citation,
    'EPA_NR010f',
    '现代四冲程: 0.50-0.55 lb/hp-hr = 304-334 g/kWh. Best=319 g/kWh. '
    '适用于<12m现代四冲程汽油舷外机. 此值直接用作SFR, 不经过SFOC负荷修正.')

add('L', 'SFR_GASOLINE_DI_2STROKE', 'EPA直喷两冲程汽油舷外机SFR',
    'ALL', 'ALL', 'APW', '<12m', 0.000365, 0.000334, 0.000395,
    'tFuel/kWh', 'Triangular',
    epa_sfr_citation,
    'EPA_NR010f',
    '直喷两冲程: 0.55-0.65 lb/hp-hr = 334-395 g/kWh. Best=365 g/kWh. '
    '适用于<12m直喷两冲程汽油舷外机. 此值直接用作SFR, 不经过SFOC负荷修正.')

# EPA汽油舷外机默认负荷因子 (保留作为参考)
add('L', 'LF_EPA_OUTBOARD_GASOLINE', 'EPA船用舷外汽油机默认负荷因子 (综合工况)',
    'ALL', 'ALL', 'APW', '<12m', 0.207, None, None, 'fraction of MCR', 'Discrete',
    epa_lf_citation,
    'EPA_NR005d',
    'EPA对所有常规船用舷外汽油机的基准测试默认负荷因子: 20.7%. '
    '实际建模时T_work采用0.201 (EPA认证循环平均负荷), T_move采用0.8. '
    '保留此参数作为参考值.')

# ===========================================================================
# SECTION D: 辅机功率比 (Auxiliary Engine Power Ratio)
# 来源: R56 — 2010年全球船队 (2010 world fleet) 列
# 统一采用EMEP/EEA Guidebook 2019的2010年全球船队数据
# ===========================================================================

add('D', 'AUX_POWER_RATIO_FISHING', '辅机/主机功率比 — 渔船 (Fishing)',
    'ALL', 'ALL', 'I', '>=12m', 0.39, None, None, 'ratio', 'Discrete',
    'De Lauretis, R., Ntziachristos, L., & Trozzi, C. (2021). '
    'EMEP/EEA air pollutant emission inventory guidebook 2019. '
    'Table: 2010 world fleet auxiliary-to-ghg_lca power ratio.',
    'R56',
    '渔船 (Fishing) 辅机/主机功率比: 0.39 (2010年全球船队). '
    '适用于>=12m的LL/PS捕捞船.')

add('D', 'AUX_POWER_RATIO_TP', '辅机/主机功率比 — 转运船 (General Cargo)',
    'ALL', 'TP', 'I', 'ALL', 0.23, None, None, 'ratio', 'Discrete',
    'De Lauretis, R., Ntziachristos, L., & Trozzi, C. (2021). '
    'EMEP/EEA air pollutant emission inventory guidebook 2019. '
    'Table: 2010 world fleet auxiliary-to-ghg_lca power ratio.',
    'R56',
    '转运船(TP) 辅机/主机功率比: 0.23 (件杂货船 General Cargo, 2010年全球船队).')

add('D', 'AUX_POWER_RATIO_SA', '辅机/主机功率比 — 辅助船 (Other)',
    'ALL', 'SA', 'I', 'ALL', 0.35, None, None, 'ratio', 'Discrete',
    'De Lauretis, R., Ntziachristos, L., & Trozzi, C. (2021). '
    'EMEP/EEA air pollutant emission inventory guidebook 2019. '
    'Table: 2010 world fleet auxiliary-to-ghg_lca power ratio.',
    'R56',
    '辅助船(SA) 辅机/主机功率比: 0.35 (其他 Other, 2010年全球船队).')

# ===========================================================================
# SECTION E: 船体建造与维护参数 (Hull Construction & Maintenance)
# 仅保留建造/维护EF和寿命参数; 材料占比/防污漆/回收等模型未使用参数已移除
# ===========================================================================

# 建造EF
add('E', 'EF_BUILD_PS_STEEL', '围网钢船建造碳排放因子 (cradle-to-gate)',
    'ALL', 'PS', 'I', '>=12m', 2.421, 2.332, 2.528,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner, steel | Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_PS_Steel',
    '1 kg purse seiner steel construction. Mean=2.421, 95% CI [2.332, 2.528].')

add('E', 'EF_BUILD_PS_WOOD', '围网木船建造碳排放因子 (cradle-to-gate)',
    'ALL', 'PS', 'APW', '<12m', 0.578, 0.513, 0.678,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner, wood | Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_PS_Wood',
    '1 kg purse seiner wood construction. Mean=0.578, 95% CI [0.513, 0.678].')

add('E', 'EF_BUILD_LL_STEEL', '延绳钓钢船建造碳排放因子 (cradle-to-gate)',
    'ALL', 'LL', 'I', '>=12m', 1.956, 1.877, 2.069,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Ecoinvent v3 — market for long liner, steel | Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_LL_Steel',
    '1 kg long liner steel construction. Mean=1.956, 95% CI [1.877, 2.069].')

add('E', 'EF_BUILD_LL_WOOD', '延绳钓木船建造碳排放因子 (同围网木船)',
    'ALL', 'LL', 'APW', '<12m', 0.578, 0.513, 0.678,
    'kg CO2eq/kg vessel', 'Lognormal',
    '同 EF_BUILD_PS_WOOD',
    'Ecoinvent_PS_Wood',
    '延绳钓小船 (<12m, 木质) 建造碳排放: 同围网木船因子 0.578 kg CO2eq/kg.')

add('E', 'EF_BUILD_TS', '转运船/辅助船建造碳排放因子 (同围网钢船)',
    'ALL', 'TP', 'I', 'ALL', 2.421, 2.332, 2.528,
    'kg CO2eq/kg vessel', 'Lognormal',
    '同 EF_BUILD_PS_STEEL',
    'Ecoinvent_PS_Steel',
    '转运船/辅助船建造碳排放: 同围网钢船因子 2.421 kg CO2eq/kg.')

# 维护EF
add('E', 'EF_MAINT_PS_STEEL', '围网钢船维护碳排放因子 (cradle-to-gate)',
    'ALL', 'PS', 'I', '>=12m', 6.744, 6.627, 6.883,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner maintenance, steel | Cutoff, U - GLO',
    'Ecoinvent_PS_Steel_Maint',
    '1 kg purse seiner steel maintenance. Mean=6.744, 95% CI [6.627, 6.883].')

add('E', 'EF_MAINT_PS_WOOD', '围网木船维护碳排放因子 (cradle-to-gate)',
    'ALL', 'PS', 'APW', '<12m', 1.289, 1.179, 1.437,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner maintenance, wood | Cutoff, U - GLO',
    'Ecoinvent_PS_Wood_Maint',
    '1 kg purse seiner wood maintenance. Mean=1.289, 95% CI [1.179, 1.437].')

add('E', 'EF_MAINT_LL_STEEL', '延绳钓钢船维护碳排放因子 (cradle-to-gate)',
    'ALL', 'LL', 'I', '>=12m', 4.450, 3.777, 5.376,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Ecoinvent v3 — market for long liner maintenance, steel | Cutoff, U - GLO',
    'Ecoinvent_LL_Steel_Maint',
    '1 kg long liner steel maintenance. Mean=4.450, 95% CI [3.777, 5.376].')

add('E', 'EF_MAINT_LL_WOOD', '延绳钓木船维护碳排放因子 (同围网木船)',
    'ALL', 'LL', 'APW', '<12m', 1.289, 1.179, 1.437,
    'kg CO2eq/kg maintenance', 'Lognormal',
    '同 EF_MAINT_PS_WOOD',
    'Ecoinvent_PS_Wood_Maint',
    '延绳钓小船 (<12m, 木质) 维护碳排放: 同围网木船因子 1.289 kg CO2eq/kg.')

add('E', 'EF_MAINT_TS', '转运船/辅助船维护碳排放因子 (同围网钢船)',
    'ALL', 'TP', 'I', 'ALL', 6.744, 6.627, 6.883,
    'kg CO2eq/kg maintenance', 'Lognormal',
    '同 EF_MAINT_PS_STEEL',
    'Ecoinvent_PS_Steel_Maint',
    '转运船/辅助船维护碳排放: 同围网钢船因子 6.744 kg CO2eq/kg.')

# 寿命参数
add('E', 'LIFESPAN_HULL', '船体寿命 (钢质)',
    'ALL', 'ALL', 'ALL', 'ALL', 30.0, None, None, 'years', 'Discrete',
    'SUPERPROP (2012); Hospido & Tyedmers (2005); Ceballos-Santos et al. (2023)',
    'R93-R95',
    'Steel hull lifespan: 30 years. Wood hull: 40yr (not used in current model).')

add('E', 'LIFESPAN_ENGINE', '发动机寿命 (更换周期)',
    'ALL', 'ALL', 'ALL', 'ALL', 10.0, None, None, 'years', 'Discrete',
    'SUPERPROP (2012); Hospido & Tyedmers (2005)',
    'R93-R94',
    'Engine lifespan: 10 years. Replaced once during 30yr hull life = 2 engines total.')

# ===========================================================================
# SECTION F: 渔具材料消耗参数 (Gear Material Consumption)
# ===========================================================================

# gear_int
gear_int_ps_small_low  = min(17.9, 9.12) / 1000       # 0.00912
gear_int_ps_small_high = max(17.9, 9.12) / 1000       # 0.01790
gear_int_ps_small_best = (9.12 + 17.9) / (2 * 1000)   # 0.01351

add('F', 'gear_int_PS', '围网渔具强度系数 (小型船 <12m)',
    'ALL', 'PS', 'ALL', '<12m',
    round(gear_int_ps_small_best, 6), round(gear_int_ps_small_low, 6),
    round(gear_int_ps_small_high, 6),
    't gear / m vessel length', 'Uniform',
    'Rosario (2011) — Mozambique artisanal purse seine; GRO Centre',
    'R69',
    f'Uniform[9.12, 17.9] kg/m. Best={gear_int_ps_small_best:.5f} t/m. '
    '小型手工围网(8-12m渔船), 莫桑比克渔业数据.')

gear_int_ps_large_low  = min(251.0, 54.0) / 1000       # 0.054
gear_int_ps_large_high = max(251.0, 54.0) / 1000       # 0.251
gear_int_ps_large_best = (251.0 + 54.0) / (2 * 1000)   # 0.1525

add('F', 'gear_int_PS', '围网渔具强度系数 (大型船 >=12m)',
    'ALL', 'PS', 'ALL', '>=12m',
    round(gear_int_ps_large_best, 4), round(gear_int_ps_large_low, 4),
    round(gear_int_ps_large_high, 4),
    't gear / m vessel length', 'Uniform',
    'Meenakumari (2016) — Purse seining in India. Indian J. Fish. 63(3)',
    'R70',
    f'Uniform[54.0, 251.0] kg/m. Best={gear_int_ps_large_best:.4f} t/m. '
    '印度围网渔业(11-24m渔船).')

gear_int_ll_low  = min(0.490, 0.120) / (0.0036 * 1000)    # 0.03333
gear_int_ll_high = max(0.490, 0.120) / (0.0036 * 1000)    # 0.13611
gear_int_ll_best = (0.490 + 0.120) / (2 * 0.0036 * 1000)  # 0.08472

add('F', 'gear_int_LL', '延绳钓渔具强度系数',
    'ALL', 'LL', 'ALL', 'ALL',
    round(gear_int_ll_best, 6), round(gear_int_ll_low, 6),
    round(gear_int_ll_high, 6),
    't gear / m vessel length', 'Uniform',
    'Gabr & Elhaweet (2012) — Pelagic Longline Fishery for Albacore off Egypt. '
    'Turkish J. Fish. Aquat. Sci. 12:735-741',
    'R71',
    f'Uniform[0.120, 0.490] kg/hook. Best={gear_int_ll_best:.5f} t/m. '
    '1 hook ≈ 0.0036m vessel length. 埃及地中海长鳍金枪鱼延绳钓.')

# 网具材料组成 — PS: 尼龙(PA6+EVA) 73.9% + 钢 26.1%; LL: 同PS比例
# 来源: Andrés et al. (2022) — PA6=64.2%, EVA=9.7%, Steel=26.1%
# 用户指令: 浮子(EVA)占比并入尼龙, 延绳钓采用相同尼龙/钢比例
nylon_ps = round(0.642 + 0.097, 3)  # 0.739 (PA6 + EVA merged)
steel_ps = 0.261

add('F', 'GEAR_MATERIAL_NYLON_PS', '围网尼龙 (PA6+EVA) 材料占比',
    'ALL', 'PS', 'ALL', 'ALL', nylon_ps, None, None, 'mass fraction', 'Discrete',
    'Andrés et al. (2022) Front. Sustain. 3:929902',
    'R72',
    f'PA6 (64.2%) + EVA浮子 (9.7%) = {nylon_ps} (合并为尼龙). '
    'Includes netting, ropes, float lines, EVA floats.')

add('F', 'GEAR_MATERIAL_STEEL_PS', '围网金属部件 (钢) 占比',
    'ALL', 'PS', 'ALL', 'ALL', steel_ps, None, None, 'mass fraction', 'Discrete',
    'Andrés et al. (2022) Front. Sustain. 3:929902',
    'R72',
    f'Steel components = {steel_ps} of PS net weight. Includes chains, rings, wire rope.')

add('F', 'GEAR_MATERIAL_NYLON_LL', '延绳钓尼龙材料占比 (同围网)',
    'ALL', 'LL', 'ALL', 'ALL', nylon_ps, None, None, 'mass fraction', 'Discrete',
    '同 GEAR_MATERIAL_NYLON_PS — Andrés et al. (2022)',
    'R72',
    f'LL nylon = {nylon_ps} (同围网PA6+EVA合并值). 主绳+支绳+浮子绳均为尼龙.')

add('F', 'GEAR_MATERIAL_STEEL_LL', '延绳钓金属部件 (钢) 占比 (同围网)',
    'ALL', 'LL', 'ALL', 'ALL', steel_ps, None, None, 'mass fraction', 'Discrete',
    '同 GEAR_MATERIAL_STEEL_PS — Andrés et al. (2022)',
    'R72',
    f'LL steel hardware = {steel_ps} (同围网钢占比). 鱼钩、转环、沉子等五金件.')

# 网具EF
add('F', 'EMISSION_FACTOR_NYLON_PA6', '尼龙(PA6)碳排放因子 (cradle-to-gate)',
    'ALL', 'ALL', 'ALL', 'ALL', 9.885, 9.807, 9.969,
    'kg CO2eq/kg nylon', 'Lognormal',
    '自建前景过程 — fishing net production, nylon, 1kg (1000 MC simulations)',
    'SelfBuilt_NylonNet',
    'Mean=9.885, 95% CI [9.807, 9.969].')

add('F', 'EMISSION_FACTOR_STEEL_GEAR', '渔具用钢/金属件碳排放因子 (cradle-to-gate)',
    'ALL', 'ALL', 'ALL', 'ALL', 3.070, 2.819, 3.374,
    'kg CO2eq/kg steel hardware', 'Lognormal',
    '自建前景过程 — longline hardware, steel, 1kg (1000 MC simulations)',
    'SelfBuilt_LL_Hardware',
    'Mean=3.070, 95% CI [2.819, 3.374].')

# 网具截断
add('F', 'GEAR_INT_TRUNC_LL_MAX_KW', '延绳钓gear_int物理截断—最大功率',
    'ALL', 'LL', 'ALL', 'ALL', 1600.0, None, None, 'kW', 'Discrete',
    'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
    'R68', 'LL渔船最大功率约1600 kW.')

add('F', 'GEAR_INT_TRUNC_LL_MAX_LOA_M', '延绳钓gear_int物理截断—最大船长',
    'ALL', 'LL', 'ALL', 'ALL', 55.0, None, None, 'm', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'LL渔船最大LOA约55m.')

add('F', 'GEAR_INT_TRUNC_LL_MAX_GT', '延绳钓gear_int物理截断—最大总吨位',
    'ALL', 'LL', 'ALL', 'ALL', 800.0, None, None, 'GT', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'LL渔船最大GT约800.')

add('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_KW', '围网(小集群) gear_int物理截断—最大功率',
    'ALL', 'PS', 'ALL', '<12m', 1000.0, None, None, 'kW', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'PS小集群上限: 1000 kW, 50m LOA, 750 GT.')

add('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_LOA_M', '围网(小集群) gear_int物理截断—最大船长',
    'ALL', 'PS', 'ALL', '<12m', 50.0, None, None, 'm', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'PS小集群LOA上限约50m.')

add('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_GT', '围网(小集群) gear_int物理截断—最大总吨位',
    'ALL', 'PS', 'ALL', '<12m', 750.0, None, None, 'GT', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'PS小集群GT上限约750.')

add('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_KW', '围网(大集群) gear_int物理截断—最大功率',
    'ALL', 'PS', 'ALL', '>=12m', 2500.0, 2000.0, 3000.0, 'kW', 'Triangular',
    'Kuczenski et al. (2022)',
    'R68', 'PS大集群上限: 2000-3000 kW, 60-80m LOA, 1000-2000 GT.')

add('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_LOA_M', '围网(大集群) gear_int物理截断—最大船长',
    'ALL', 'PS', 'ALL', '>=12m', 70.0, 60.0, 80.0, 'm', 'Triangular',
    'Kuczenski et al. (2022)',
    'R68', 'PS大集群LOA范围60-80m.')

add('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_GT', '围网(大集群) gear_int物理截断—最大总吨位',
    'ALL', 'PS', 'ALL', '>=12m', 1500.0, 1000.0, 2000.0, 'GT', 'Triangular',
    'Kuczenski et al. (2022)',
    'R68', 'PS大集群GT范围1000-2000.')

# 网具寿命/维护
add('F', 'LIFESPAN_GEAR_PS', '围网使用寿命',
    'ALL', 'PS', 'ALL', 'ALL', 5.0, 3.0, 5.0, 'years', 'Triangular',
    'Vazquez-Rowe et al. (2010) Fish. Res. 106(3):517-527; Andrés et al. (2022)',
    'R74-R76',
    'PS net lifespan: 5yr. Annual replacement 25% in non-renewal years.')

add('F', 'LIFESPAN_GEAR_LL', '延绳钓使用寿命',
    'ALL', 'LL', 'ALL', 'ALL', 5.0, 3.0, 5.0, 'years', 'Triangular',
    'Ceballos-Santos et al. (2023); Kuczenski et al. (2022)',
    'R79-R80',
    'LL gear lifespan: 5yr.')

add('F', 'MAINTENANCE_RATE_GEAR_PS', '围网年度维护更换比例',
    'ALL', 'PS', 'ALL', 'ALL', 0.25, 0.20, 0.33, 'fraction per year', 'Triangular',
    'Vazquez-Rowe et al. (2010); Ceballos-Santos et al. (2023)',
    'R74-R76',
    'PS: 25% annual gear replacement (in non-renewal years).')

add('F', 'MAINTENANCE_RATE_GEAR_LL', '延绳钓年度维护更换比例',
    'ALL', 'LL', 'ALL', 'ALL', 0.25, 0.20, 0.33, 'fraction per year', 'Triangular',
    'Ceballos-Santos et al. (2023); Kuczenski et al. (2022)',
    'R79-R80',
    'LL: 25% annual gear replacement (in non-renewal years).')

# ===========================================================================
# SECTION G: 饵料消耗参数 (Bait Consumption)
# ===========================================================================

add('G', 'BAIT_WEIGHT_PER_HOOK_KG', '延绳钓单钩饵料平均重量',
    'ALL', 'LL', 'ALL', 'ALL', 0.10, 0.05, 0.15, 'kg/hook', 'Triangular',
    'Jha et al. (2026); ghg_lca.py BAIT_WEIGHT_PER_HOOK_KG',
    'R107',
    'Default: 0.1 kg per hook (low-value trash fish). Range: 0.05-0.15 kg/hook.')

add('G', 'EMISSION_FACTOR_BAIT', '饵料碳排放因子 (cradle-to-gate)',
    'ALL', 'LL', 'ALL', 'ALL', 1.606, 1.548, 1.670,
    'kg CO2eq/kg bait', 'Lognormal',
    'Ecoinvent v3 — market for small pelagic fish, fresh | Cutoff, U - GLO '
    '(1000 MC simulations)',
    'Ecoinvent_Bait',
    'Mean=1.606, 95% CI [1.548, 1.670].')

add('G', 'HOOKS_PER_LINE_RANGE_LOW', '每套钓具最低总钩数',
    'ALL', 'LL', 'ALL', 'ALL', 1666.0, 500.0, 1666.0, 'hooks/line', 'Triangular',
    'Jha et al. (2026)',
    'R105-R106',
    '500-1500 hooks per trip; 1666-2147 total hooks per line.')

add('G', 'HOOKS_PER_LINE_RANGE_HIGH', '每套钓具最高总钩数',
    'ALL', 'LL', 'ALL', 'ALL', 2147.0, 1666.0, 3000.0, 'hooks/line', 'Triangular',
    'Jha et al. (2026)',
    'R106',
    'Upper bound: 2147 hooks. Extended upper bound: 3000 for large industrial LL.')

# ===========================================================================
# SECTION H: 制冷剂参数 (Refrigerant)
# ===========================================================================

add('H', 'R22_GWP', 'R22制冷剂全球增温潜势 (100yr)',
    'ALL', 'ALL', 'ALL', 'ALL', 1810.0, None, None, 'kgCO2e/kg R22', 'Discrete',
    'IPCC (2007)',
    'R99',
    'R22 (HCFC) GWP-100 = 1810.')

add('H', 'R22_LEAK_COASTAL_TRAWL', 'R22年泄漏量 (沿海拖网渔船)',
    'ALL', 'ALL', 'ALL', 'ALL', 150.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011); Vazquez-Rowe et al. (2010)',
    'R100-R101',
    'Coastal trawl: 150 kg R22/yr.')

add('H', 'R22_LEAK_COASTAL_PS', 'R22年泄漏量 (沿海围网渔船)',
    'ALL', 'PS', 'ALL', 'ALL', 10.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011); Vazquez-Rowe et al. (2010)',
    'R100-R101',
    'Coastal PS: 10 kg R22/yr.')

add('H', 'R22_LEAK_OFFSHORE', 'R22年泄漏量 (近海渔船)',
    'ALL', 'ALL', 'ALL', 'ALL', 200.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011)',
    'R100',
    'Offshore vessels: 200 kg R22/yr.')

add('H', 'R22_LEAK_DISTANT_PS', 'R22年泄漏量 (远洋围网渔船)',
    'ALL', 'PS', 'ALL', 'ALL', 500.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011)',
    'R100',
    'Distant-water PS: 500 kg R22/yr. Tuna PS (Indian Ocean): 751 g/t reference.')

# ===========================================================================
# SECTION I: 努力量标准化参数 (Effort Standardization)
# ===========================================================================

add('I', 'HOOKS_PER_DAY', '延绳钓标准日下钩数 (Effort标准化)',
    'ALL', 'LL', 'ALL', 'ALL', 3000.0, None, None, 'hooks/day', 'Triangular',
    'ghg_lca.py HOOKS_PER_DAY constant; Jha et al. (2026)',
    'R105-R106',
    'Standard LL hooks per day. Model: Std_Effort(LL) = EffortValue × HOOKS_PER_DAY.')

add('I', 'HOURS_PER_SET', '围网标准单网耗时 (Effort标准化)',
    'ALL', 'PS', 'ALL', 'ALL', 12.0, None, None, 'hours/set', 'Triangular',
    'ghg_lca.py HOURS_PER_SET constant; Korican et al. (2023)',
    'R17',
    'Standard PS hours per set (searching + operation).')

# ===========================================================================
# SECTION J: 功率增长参数 (Power Growth Rate)
# ===========================================================================

add('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (欧洲)',
    'Europe', 'ALL', 'ALL', 'ALL', 0.002, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Europe: 0.2%/yr — lowest growth.')

add('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (亚洲)',
    'Asia', 'ALL', 'ALL', 'ALL', 0.012, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Asia: 1.2%/yr — highest growth.')

add('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (北美洲)',
    'North America', 'ALL', 'ALL', 'ALL', 0.011, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'North America: 1.1%/yr.')

add('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (非洲)',
    'Africa', 'ALL', 'ALL', 'ALL', 0.009, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Africa: 0.9%/yr.')

add('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (南美洲)',
    'South America', 'ALL', 'ALL', 'ALL', 0.011, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'South America: 1.1%/yr.')

add('J', 'POWER_GROWTH_RATE', '主机功率年均增长率 (大洋洲)',
    'Australia & Oceania', 'ALL', 'ALL', 'ALL', 0.017, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Oceania: 1.7%/yr — highest among regions.')

add('J', 'POWER_GROWTH_RATE_LL', '主机功率年均增长率 (延绳钓船队)',
    'ALL', 'LL', 'ALL', 'ALL', 0.01, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R62', 'LL fleet: 1.0%/yr.')

add('J', 'POWER_GROWTH_RATE_PS', '主机功率年均增长率 (围网船队)',
    'ALL', 'PS', 'ALL', 'ALL', 0.004, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R62', 'PS fleet: 0.4%/yr.')

add('J', 'POWER_GROWTH_DECADAL_HP', '主机功率十年增长率',
    'ALL', 'ALL', 'ALL', 'ALL', 0.045, 0.03, 0.06, 'fraction/decade', 'Triangular',
    'SPC (2016) WCPFC-SC12-2016/MI-WP-08',
    'R60', 'Vessel HP grew 3-6% over study period. Best=4.5%.')

# ===========================================================================
# SECTION K: GT-LDT 吨位转换 (GT→LDT Conversion)
# ===========================================================================

add('K', 'LDT_GT_RATIO_FISHING', '渔船 GT→LDT 转换系数',
    'ALL', 'ALL', 'ALL', 'ALL', 0.859, None, None, 'LDT/GT ratio', 'Discrete',
    'European Commission (2025) KOM(2025)0052 SWD — 61艘拆解渔船实际统计',
    'R103',
    'Fishing vessel LDT/GT = 85.9%. 61艘真实被拆解捕捞渔船统计结果: '
    'Total GT=138,757 / Total LDT=119,231 = 0.859.')

add('K', 'LDT_GT_RATIO_CARGO_REF', '货船 GT→LDT 转换系数 (参考对比)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.287, 0.22, 0.55, 'LDT/GT ratio', 'Triangular',
    'Mikelis (2008) WMU J. Marit. Affairs 7:227-239',
    'R102',
    'Reference: cargo ships LDT/GT varies 22-55%. '
    '转运船(TP)采用cargo ratio 0.287而非fishing ratio 0.859.')

# ===========================================================================
# FINAL: Build DataFrame & Export
# ===========================================================================

df = pd.DataFrame(rows)

# Ensure column order
columns = [
    'Param_Section', 'Param_Code', 'Param_Name_CN', 'Flag', 'Gear', 'Sector',
    'Length_Category', 'Value_Best', 'Value_Low', 'Value_High', 'Unit',
    'Distribution', 'Source_Citation', 'Sheet1_Row', 'Note'
]
df = df[columns]

# Write CSV
df.to_csv(OUT_PATH, index=False, encoding='utf-8-sig')
print(f"\nPrior_Matrix written to: {OUT_PATH}")
print(f"Total rows: {len(df)}")
print(f"\nSection breakdown:")
for section in sorted(df['Param_Section'].unique()):
    count = len(df[df['Param_Section'] == section])
    print(f"  Section {section}: {count} rows")
print("\nDone!")
