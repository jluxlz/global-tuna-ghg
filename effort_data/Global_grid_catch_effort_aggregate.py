import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# 使用相对于脚本所在目录的路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from flag_utils import normalize_flag_to_iso3

# ==========================================
# NOTE: All RFMO scripts now output ISO3 codes in 'Flag' column.
# Column name is unified to 'Flag' (was Country/FlagName mix).
# This script additionally normalizes any legacy 'Country' columns
# and applies normalize_flag_to_iso3 as a safety net.
# ==========================================

def ensure_flag_iso3(df, rejected=None, source="unknown"):
    """统一 Flag 列：处理 'Country'→'Flag' 重命名 + ISO3 标准化"""
    if 'Flag' not in df.columns:
        if 'Country' in df.columns:
            df.rename(columns={'Country': 'Flag'}, inplace=True)
        elif 'country' in df.columns:
            df.rename(columns={'country': 'Flag'}, inplace=True)
    if 'Flag' in df.columns:
        df['Flag'] = df['Flag'].astype(str).str.strip().apply(normalize_flag_to_iso3)
        if rejected is not None:
            bad = df[df['Flag'].eq('')].copy()
            bad['QC_Source'] = source
            bad['QC_Reason'] = 'unrecognized_flag'
            rejected.append(bad)
        df = df[df['Flag'] != ''].copy()
    return df

def build_global_tables(output_dir=None, iccat_path=None, iotc_path=None, iattc_path=None):
    output_dir = Path(output_dir or SCRIPT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    rejected = []
    # ==========================================
    # 1. 汇总年度纯捕获量 (Annual Catch)
    # ==========================================
    annual_dfs = []

    # (1) CCSBT
    df_ccsbt_a = pd.read_csv(os.path.join(SCRIPT_DIR, 'CCSBT', 'CCSBT_Annual_Catch.csv'))
    # 宽表转长表（年份 -> 各国家捕获量，列名已是 ISO3）
    df_ccsbt_a_melt = df_ccsbt_a.melt(id_vars=['Year'], var_name='Flag', value_name='SBT')
    df_ccsbt_a_melt['Organization'] = 'CCSBT'
    df_ccsbt_a_melt['GearTypeCode'] = 'Unknown' # 宏观年度汇总不带渔具
    df_ccsbt_a_melt = ensure_flag_iso3(df_ccsbt_a_melt, rejected, "df_ccsbt_a_melt")
    annual_dfs.append(df_ccsbt_a_melt)

    # (2) IATTC
    df_iattc_a = pd.read_csv(os.path.join(SCRIPT_DIR, 'IATTC', 'IATTC_Annual_Catch.csv'))
    df_iattc_a.rename(columns={'Gear': 'GearTypeCode'}, inplace=True)
    df_iattc_a = ensure_flag_iso3(df_iattc_a, rejected, "df_iattc_a")
    df_iattc_a['Organization'] = 'IATTC'
    annual_dfs.append(df_iattc_a)

    # (3) ICCAT
    df_iccat_a = pd.read_csv(os.path.join(SCRIPT_DIR, 'ICCAT', 'ICCAT_Annual_Catch.csv'))
    df_iccat_a.rename(columns={'YearC': 'Year', 'GearCode': 'GearTypeCode'}, inplace=True)
    df_iccat_a = ensure_flag_iso3(df_iccat_a, rejected, "df_iccat_a")
    df_iccat_a['Organization'] = 'ICCAT'
    annual_dfs.append(df_iccat_a)

    # (4) IOTC
    df_iotc_a = pd.read_csv(os.path.join(SCRIPT_DIR, 'IOTC', 'IOTC_Annual_Catch.csv'))
    df_iotc_a = ensure_flag_iso3(df_iotc_a, rejected, "df_iotc_a")
    df_iotc_a['Organization'] = 'IOTC'
    annual_dfs.append(df_iotc_a)

    # (5) WCPFC
    df_wcpfc_a = pd.read_csv(os.path.join(SCRIPT_DIR, 'WCPFC', 'WCPFC_Annual_Catch.csv'))
    df_wcpfc_a = ensure_flag_iso3(df_wcpfc_a, rejected, "df_wcpfc_a")
    df_wcpfc_a['Organization'] = 'WCPFC'
    annual_dfs.append(df_wcpfc_a)

    # 纵向合并所有年度表
    global_annual = pd.concat(annual_dfs, ignore_index=True)

    # 统一目标物种的列（不存在则补0）
    species_cols = ['SKJ', 'BET', 'YFT', 'SBT', 'ALB']
    for sp in species_cols:
        if sp not in global_annual.columns:
            global_annual[sp] = 0.0
        else:
            global_annual[sp] = global_annual[sp].fillna(0.0)

    # 规范列顺序
    annual_cols = ['Organization', 'Year', 'Flag', 'GearTypeCode'] + species_cols
    global_annual = global_annual[annual_cols]
    global_annual.to_csv(output_dir / 'Global_Annual_Catch.csv', index=False, encoding='utf-8-sig')
    print(f"  Global_Annual_Catch.csv: {len(global_annual)} rows")


    # ==========================================
    # 2. 汇总网格捕捞与努力量 (Grid Catch Effort)
    # ==========================================
    grid_dfs = []

    # (1) CCSBT
    df_ccsbt_g = pd.read_csv(os.path.join(SCRIPT_DIR, 'CCSBT', 'CCSBT_Grid_Catch_Effort.csv'))
    df_ccsbt_g.rename(columns={'Gear': 'GearTypeCode', 'Latitude': 'Lat', 'Longitude': 'Lon', 'Effort_Type': 'EffortType', 'Effort': 'EffortValue'}, inplace=True)
    df_ccsbt_g = ensure_flag_iso3(df_ccsbt_g, rejected, "df_ccsbt_g")
    df_ccsbt_g['Organization'] = 'CCSBT'
    df_ccsbt_g['SBT'] = 0.0 # 若努力量表中无捕获数据用0填补
    grid_dfs.append(df_ccsbt_g)

    # (2) IATTC
    df_iattc_g = pd.read_csv(iattc_path or os.path.join(SCRIPT_DIR, 'IATTC', 'IATTC_Grid_Catch_Effort.csv'))
    df_iattc_g.rename(columns={'Effort': 'EffortValue'}, inplace=True)
    df_iattc_g = ensure_flag_iso3(df_iattc_g, rejected, "df_iattc_g")
    df_iattc_g['Organization'] = 'IATTC'
    grid_dfs.append(df_iattc_g)

    # (3) ICCAT
    df_iccat_g = pd.read_csv(iccat_path or os.path.join(SCRIPT_DIR, 'ICCAT', 'ICCAT_Grid_Catch_Effort.csv'))
    df_iccat_g.rename(columns={'YearC': 'Year', 'GearCode': 'GearTypeCode', 'Eff1Type': 'EffortType', 'Eff1': 'EffortValue'}, inplace=True)
    df_iccat_g = ensure_flag_iso3(df_iccat_g, rejected, "df_iccat_g")
    df_iccat_g['Organization'] = 'ICCAT'
    # Keep tonnes and fish counts in separate columns; unknown units cannot become tonnes.
    units = df_iccat_g['CatchUnit'].astype(str).str.strip().str.lower()
    for sp in ['BFT', 'YFT', 'BET', 'SKJ', 'ALB']:
        if sp not in df_iccat_g:
            continue
        values = pd.to_numeric(df_iccat_g[sp], errors='coerce').fillna(0)
        df_iccat_g[sp + 'n'] = pd.to_numeric(df_iccat_g.get(sp+'n', pd.Series(0.0, index=df_iccat_g.index)), errors='coerce').fillna(0) + values.where(units.isin(['nr', 'n', 'no']), 0.0)
        df_iccat_g[sp] = values.where(units.isin(['t', 'mt', 'kg']), 0.0)
        df_iccat_g.loc[units.eq('kg'), sp] /= 1000.0
    unknown = df_iccat_g.loc[~units.isin(['t', 'mt', 'kg', 'nr', 'n', 'no'])].copy()
    unknown.to_csv(output_dir / 'ICCAT_Unknown_Catch_Units.csv', index=False, encoding='utf-8-sig')
    grid_dfs.append(df_iccat_g)

    # (4) IOTC
    df_iotc_g = pd.read_csv(iotc_path or os.path.join(SCRIPT_DIR, 'IOTC', 'IOTC_Grid_Catch_Effort.csv'))
    df_iotc_g.rename(columns={'EFFORT': 'EffortValue'}, inplace=True)
    df_iotc_g = ensure_flag_iso3(df_iotc_g, rejected, "df_iotc_g")
    df_iotc_g['Organization'] = 'IOTC'
    grid_dfs.append(df_iotc_g)

    # (5) WCPFC
    df_wcpfc_g = pd.read_csv(os.path.join(SCRIPT_DIR, 'WCPFC', 'WCPFC_Grid_Catch_Effort.csv'))
    df_wcpfc_g = ensure_flag_iso3(df_wcpfc_g, rejected, "df_wcpfc_g")
    df_wcpfc_g['Organization'] = 'WCPFC'
    grid_dfs.append(df_wcpfc_g)

    # 纵向合并所有网格表
    global_grid = pd.concat(grid_dfs, ignore_index=True)

    # 统一重量(吨)和数量(尾)的列名，填补空缺为 0
    species_weight = ['SKJ', 'BET', 'YFT', 'SBT', 'ALB']
    species_num = ['SKJn', 'BETn', 'YFTn', 'SBTn', 'ALBn']

    for col in species_weight + species_num:
        if col not in global_grid.columns:
            global_grid[col] = 0.0
        else:
            global_grid[col] = global_grid[col].fillna(0.0)

    # 对空缺的努力量填0或Unknown
    global_grid['EffortValue'] = global_grid['EffortValue'].fillna(0.0)
    global_grid['EffortType'] = global_grid['EffortType'].fillna('Unknown')

    # 规范列顺序
    grid_cols = ['Organization', 'Year', 'Flag', 'GearTypeCode', 'SquareTypeCode', 'Lat', 'Lon', 'EffortType', 'EffortValue'] + species_weight + species_num
    global_grid = global_grid[grid_cols]

    global_grid.to_csv(output_dir / 'Global_Grid_Catch_Effort.csv', index=False, encoding='utf-8-sig')

    print("大一统处理完成！")
    if rejected:
        pd.concat(rejected, ignore_index=True).to_csv(output_dir / "Global_Flag_Rejections.csv", index=False, encoding="utf-8-sig")
    return global_annual, global_grid


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=SCRIPT_DIR)
    parser.add_argument("--iccat-path")
    args = parser.parse_args()
    build_global_tables(args.output_dir, args.iccat_path)
