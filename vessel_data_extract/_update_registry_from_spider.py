#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
_update_registry_from_spider.py
=============================================================================
用 spider 爬取数据更新 Unified_Vessel_Registry.csv 的物理参数。

匹配策略（两级信任体系）：
  IMO 锚点（绝对信任）：
    - 只要 spider 通过 IMO 查到了数据，直接更新 Builtdate、Tonnage、MMSI。
    - IMO 是全球唯一且终身绑定船壳的编号，不存在误匹配风险。

  Callsign 线索（交叉验证）：
    - 当仅通过 Callsign 匹配到 spider 数据时，需通过以下校验：
      1. 船型/作业类型兼容性检查（排除呼号重用错配）
      2. 总吨位容差检查（±20%）
    - 两项均通过 → 更新；任一失败 → 丢弃。

更新范围（spider 可提供的字段）：
  - Builtdate    : 建造年份（海事数据库权威值）
  - Tonnage      : 总吨位 GT
  - MMSI         : 水上移动通信业务标识码
  - VesselType   : 从 spider 的详细船型反推（Fishing Vessel→LL/PS, Cargo→TS）

不更新的字段（spider 无对应数据）：
  - Length, Enginepower（spider 无 LOA 和 kW 数据）
  - Callsign, IMO（这些是匹配键，不从外部覆盖）
=============================================================================
"""

import os
import sys
import re
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

# =============================================================================
# 全局配置
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
SPIDER_DIR = BASE_DIR.parent / "spider" / "output"
REGISTRY_PATH = BASE_DIR / "Unified_Vessel_Registry.csv"
OUTPUT_PATH = BASE_DIR / "Unified_Vessel_Registry.csv"  # 直接覆盖

# spider 输出文件
SPIDER_FILES = [
    "CCSBT_extracted_new_result.xlsx",
    "IATTC_extracted_new_result.xlsx",
    "ICCAT_extracted_new_result.xlsx",
    "IOTC_extracted_new_result.xlsx",
    "WCPFC_extracted_new_result.xlsx",
]

# GT 容差阈值（Callsign 匹配时使用）
GT_TOLERANCE = 0.20  # ±20%

# =============================================================================
# 船型兼容性映射
# =============================================================================

# spider 详细船型 → 是否兼容我们的渔船登记册
# True  = 兼容（可能是我们的渔船/冷藏运输船）
# False = 不兼容（明显是其他类型的船，呼号被重用了）
SHIP_TYPE_COMPATIBLE = {
    # --- 兼容：渔船及渔业相关 ---
    "Fishing Vessel": True,
    "Fish Carrier": True,
    "Fish Factory Ship": True,
    "Fishery Support Vessel": True,
    "Fishery Research Vessel": True,
    "Fishery Patrol Vessel": True,
    "Fish Farm Support Vessel": True,

    # --- 兼容：冷藏运输船（金枪鱼转运船） ---
    "Refrigerated Cargo Ship": True,

    # --- 兼容：通用货船（可能是小型兼业渔船） ---
    # 不自动兼容，需进一步判断

    # --- 不兼容：明显不是渔船 ---
    "Tug": False,
    "Yacht": False,
    "Yacht (Sailing)": False,
    "Sailing Vessel": False,
    "Bulk Carrier": False,
    "Bulk Carrier, Laker Only": False,
    "Bulk Carrier, Self-discharging": False,
    "Bulk Carrier, Self-discharging, Laker": False,
    "Products Tanker": False,
    "Products Tank Barge, non propelled": False,
    "Chemical/Products Tanker": False,
    "Chemical/Products Tanker, Inland Waterways": False,
    "Chemical Tanker": False,
    "Chemical Tanker, Inland Waterways": False,
    "Crude Oil Tanker": False,
    "Crude/Oil Products Tanker": False,
    "LPG Tanker": False,
    "Asphalt/Bitumen Tanker": False,
    "Bunkering Tanker (Oil)": False,
    "Tanker (unspecified)": False,
    "Water Tanker": False,
    "Wine Tanker": False,
    "Container Ship (Fully Cellular)": False,
    "General Cargo Ship": False,
    "General Cargo Ship (Open Hatch)": False,
    "General Cargo, Inland Waterways": False,
    "General Cargo/Passenger Ship": False,
    "Ro-Ro Cargo Ship": False,
    "Vehicles Carrier": False,
    "Livestock Carrier": False,
    "Cement Carrier": False,
    "Aggregates Carrier": False,
    "Wood Chips Carrier": False,
    "Deck Cargo Ship": False,
    "Deck Cargo Pontoon, non propelled": False,
    "Palletised Cargo Ship": False,
    "Passenger Ship": False,
    "Passenger/Cruise": False,
    "Passenger/Ro-Ro Ship (Vehicles)": False,
    "Passenger/Ro-Ro Ship (Vehicles), Inland Waterways": False,
    "Passenger/Landing Craft": False,
    "Cruise Ship, Inland Waterways": False,
    "Training Ship": False,
    "Training Ship, Stationary": False,
    "Sail Training Ship": False,
    "Platform Supply Ship": False,
    "Standby Safety Vessel": False,
    "Crew/Supply Vessel": False,
    "Supply Tender": False,
    "Offshore Tug/Supply Ship": False,
    "Offshore Support Vessel": False,
    "Anchor Handling Tug Supply": False,
    "Utility Vessel": False,
    "Search & Rescue Vessel": False,
    "Salvage Ship": False,
    "Pollution Control Vessel": False,
    "Patrol Vessel": False,
    "Landing Craft": False,
    "Tank Landing Craft": False,
    "Hopper, Motor": False,
    "Trailing Suction Hopper Dredger": False,
    "Suction Hopper Dredger": False,
    "Grab Dredger": False,
    "Pusher Tug": False,
    "Articulated Pusher Tug": False,
    "Research Survey Vessel": False,
    "Drilling Rig, semi submersible": False,
    "Drilling Rig, jack up": False,
    "FPSO, Oil": False,
    "Frigate": False,
    "Destroyer": False,
    "Corvette": False,
    "Minehunter": False,
    "Submarine": False,
    "Submarine Salvage Vessel": False,
    "Aircraft Carrier": False,
    "Attack Vessel, Naval": False,
    "Troopship": False,
    "Logistics Vessel (Naval Ro-Ro Cargo)": False,
    "Commissioning Service Operation Vessel": False,
    "Work/Repair Vessel": False,
}


def is_ship_type_compatible(spider_ship_type: str, our_gear_type: str) -> bool:
    """
    检查 spider 爬取的船型是否与我们的网具/船舶类型兼容。

    spider_ship_type: 海事数据库中的详细船舶类型（如 "Fishing Vessel"）
    our_gear_type: 我们登记册中的 VesselType（LL/PS/TS/SA/OTHER）

    返回 True 表示兼容，可以信任 spider 数据。
    """
    if not spider_ship_type or pd.isna(spider_ship_type):
        return True  # 无船型信息 → 不排除（保守放行，依赖 GT 容差兜底）

    st = str(spider_ship_type).strip()

    # 精确匹配已知类型
    if st in SHIP_TYPE_COMPATIBLE:
        return SHIP_TYPE_COMPATIBLE[st]

    # 未知类型 → 模糊匹配（保守放行）
    # 包含 "Fish" → 兼容
    if "FISH" in st.upper():
        return True
    # 包含 "Cargo/Passenger/General" → 不确定，放行但标记
    # 包含明显不兼容词汇 → 拒绝
    incompatible_keywords = [
        "TANKER", "BULK", "CONTAINER", "PASSENGER", "CRUISE",
        "YACHT", "DRILL", "FPSO", "FRIGATE", "DESTROYER",
        "SUBMARINE", "AIRCRAFT", "CORVETTE", "MINE",
        "TROOP", "LANDING CRAFT", "DREDGER", "HOPPER",
    ]
    for kw in incompatible_keywords:
        if kw in st.upper():
            return False

    # 默认放行（标记为需人工审查）
    return None  # None = 不确定，需要 GT 容差兜底


def map_ship_type_to_gear(spider_ship_type: str) -> str:
    """
    从 spider 的详细船型反推我们的 VesselType。

    Fishing Vessel → 保持原 VesselType 不变（LL 或 PS 由其他信息决定）
    Refrigerated Cargo Ship / Fish Carrier → TS (Transshipment)
    """
    if not spider_ship_type or pd.isna(spider_ship_type):
        return None

    st = str(spider_ship_type).strip().upper()

    if "REFRIGERATED" in st or "FISH CARRIER" in st or "FISH FACTORY" in st:
        return "TS"

    # Fishing Vessel → 不改变原类型
    return None


# =============================================================================
# 工具函数
# =============================================================================

def safe_str(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", ""):
        return ""
    if s.endswith(".0") and s.count(".") == 1:
        try:
            float(s)
            s = s[:-2]
        except ValueError:
            pass
    return s


def safe_imo(val) -> str:
    s = safe_str(val).upper()
    if s in ("PENDING", "NE", "N/A", "UNKNOWN", "0", "0.0"):
        return ""
    digits = re.sub(r'\D', '', s)
    if len(digits) == 8 and digits.endswith('0'):
        digits = digits[:7]
    if len(digits) == 7:
        return digits
    return ""


def safe_cs(val) -> str:
    s = safe_str(val).upper()
    if s in ("UNKNOWN", "NONE", "PENDING", "N/A", "(BLANK)", "(N/A)", ""):
        return ""
    return re.sub(r'[^A-Z0-9]', '', s)


def safe_float(val) -> float:
    """安全转 float，失败返回 NaN。"""
    if pd.isna(val) or val is None:
        return np.nan
    try:
        return float(val)
    except (ValueError, TypeError):
        return np.nan


# =============================================================================
# 主更新逻辑
# =============================================================================

def load_spider_data() -> pd.DataFrame:
    """加载并池化所有 spider 输出，提取需要的字段。"""
    print("=" * 70)
    print("  加载 Spider 爬取数据")
    print("=" * 70)

    all_rows = []
    for fname in SPIDER_FILES:
        fpath = SPIDER_DIR / fname
        if not fpath.exists():
            print(f"  [跳过] 文件不存在: {fname}")
            continue

        df = pd.read_excel(fpath)
        # 列索引（0-based）:
        # 0=查询标识, 1=原始行号, 2=船名(输入), 3=IMO(输入), 4=呼号(输入),
        # 5=MMSI, 6=建造日期, 7=总吨, 8=详细船舶类型, 9=船名(抓取),
        # 10=注册船籍, 11=原建造年份, 12=原总吨数, 13=比对判定,
        # 14=报错信息, 15=查询说明, 16=是否人工查询

        for _, row in df.iterrows():
            query_notes = safe_str(row.iloc[15])  # 查询说明
            imo_input = safe_imo(row.iloc[3])       # IMO(输入)
            cs_input = safe_cs(row.iloc[4])         # 呼号(输入)

            # 判断查询方式：从 query_notes 的第一个段（" | " 之前）识别。
            #   IMO:      *查询(IMO)成功*       → 锚点信任
            #   Callsign: *查询(CallSign)成功*   → 交叉验证
            #   ShipName: *查询(ShipName)成功*   → 交叉验证(最低)
            #   均无结果   → 跳过
            # 注：不能在全文中搜索 "(IMO)"，因为 Callsign 的 query_notes
            #     后半段含 "查询成功(IMO:|Call:xxx)" 也会匹配到 (IMO)。
            first_segment = query_notes.split("|")[0].strip() if "|" in query_notes else query_notes
            if "(IMO)" in first_segment:
                match_type = "IMO"
            elif "(CallSign)" in first_segment:
                match_type = "Callsign"
            elif "(ShipName)" in first_segment:
                match_type = "ShipName"
            else:
                # 查询失败或未成功 → 跳过
                continue

            entry = {
                "spider_rfmo": fname.split("_")[0],
                "match_type": match_type,
                "imo_input": imo_input,
                "cs_input": cs_input,
                "shipname_input": safe_str(row.iloc[2]),
                "mmsi": safe_float(row.iloc[5]),
                "builtdate_scraped": safe_float(row.iloc[6]),
                "tonnage_scraped": safe_float(row.iloc[7]),
                "ship_type_scraped": safe_str(row.iloc[8]),
                "shipname_scraped": safe_str(row.iloc[9]),
                "flag_scraped": safe_str(row.iloc[10]),
                "builtdate_original": safe_float(row.iloc[11]),
                "tonnage_original": safe_float(row.iloc[12]),
                "judgment": safe_str(row.iloc[13]),
            }
            all_rows.append(entry)

    spider = pd.DataFrame(all_rows)
    print(f"  总爬取记录: {len(spider)}")
    print(f"    IMO 查询成功: {(spider['match_type']=='IMO').sum()}")
    print(f"    Callsign 查询成功: {(spider['match_type']=='Callsign').sum()}")
    print(f"    ShipName 查询成功: {(spider['match_type']=='ShipName').sum()}")

    # 按匹配方式排序: IMO > Callsign > ShipName
    # 同一 IMO/Callsign 只保留最可靠来源的数据
    match_order = {"IMO": 0, "Callsign": 1, "ShipName": 2}
    spider["_match_rank"] = spider["match_type"].map(match_order).fillna(3)
    spider = spider.sort_values(
        ["_match_rank", "builtdate_scraped", "tonnage_scraped"],
        ascending=[True, False, False]
    )
    spider = spider.drop(columns=["_match_rank"])

    return spider


def update_registry(registry: pd.DataFrame, spider: pd.DataFrame) -> tuple:
    """
    用 spider 数据更新登记册。

    返回: (更新后的 registry, 变更日志 DataFrame)
    """
    print("\n" + "=" * 70)
    print("  执行参数更新（IMO 锚点 + Callsign 交叉验证）")
    print("=" * 70)

    # ---- 构建 Spider 查询索引 ----
    # IMO 索引：仅保留通过 IMO 查询成功的数据（绝对信任锚点）
    imo_index = {}
    for _, row in spider.iterrows():
        imo = row["imo_input"]
        if imo and row["match_type"] == "IMO" and imo not in imo_index:
            imo_index[imo] = row

    # Callsign 索引：包含 Callsign 和 ShipName 匹配的数据（需交叉验证）
    # ShipName 匹配在这里通过船名输入进行索引
    cs_index = defaultdict(list)
    name_index = defaultdict(list)
    for _, row in spider.iterrows():
        cs = row["cs_input"]
        name = row["shipname_input"]
        if row["match_type"] in ("Callsign", "ShipName"):
            if cs:
                cs_index[cs].append(row)
            if name:
                name_index[name.upper()].append(row)

    print(f"  IMO 索引: {len(imo_index)} 个唯一 IMO (锚点)")
    print(f"  Callsign 索引: {len(cs_index)} 个唯一 Callsign (交叉验证)")
    print(f"  ShipName 索引: {len(name_index)} 个唯一船名 (交叉验证)")

    # ---- 逐行处理登记册 ----
    change_log = []
    updated_count = {"IMO_anchor": 0, "Callsign_validated": 0, "ShipName_validated": 0,
                     "Callsign_rejected_ship_type": 0, "Callsign_rejected_gt": 0,
                     "Callsign_rejected_both": 0}

    for idx in range(len(registry)):
        reg_imo = safe_imo(registry.at[idx, "IMO"])
        reg_cs = safe_cs(registry.at[idx, "Callsign"])
        reg_gt = safe_float(registry.at[idx, "Tonnage"])
        reg_bd = safe_float(registry.at[idx, "Builtdate"])
        reg_mmsi = safe_float(registry.at[idx, "MMSI"])
        reg_vesseltype = safe_str(registry.at[idx, "VesselType"])
        reg_name = safe_str(registry.at[idx, "Vesselname"])
        reg_flag = safe_str(registry.at[idx, "Flag"])

        spider_row = None
        match_method = None
        validation_notes = ""

        # --- 第一级：IMO 锚点匹配 ---
        if reg_imo and reg_imo in imo_index:
            spider_row = imo_index[reg_imo]
            match_method = "IMO_anchor"

        # --- 第二级：Callsign 交叉验证匹配 ---
        if spider_row is None and reg_cs and reg_cs in cs_index:
            candidates = cs_index[reg_cs]

            # 对多个候选按匹配类型和质量排序，逐个尝试
            for cand in candidates:
                spider_gt = safe_float(cand["tonnage_scraped"])
                spider_type = cand["ship_type_scraped"]

                # 校验 1: 船型兼容性
                type_ok = is_ship_type_compatible(spider_type, reg_vesseltype)

                # 校验 2: GT 容差
                gt_ok = True
                if (not np.isnan(reg_gt)) and (not np.isnan(spider_gt)) and reg_gt > 0:
                    ratio = spider_gt / reg_gt
                    gt_ok = (1 - GT_TOLERANCE) <= ratio <= (1 + GT_TOLERANCE)

                if type_ok == False:
                    # 船型明确不兼容
                    if not gt_ok:
                        updated_count["Callsign_rejected_both"] += 1
                        change_log.append({
                            "Vesselname": reg_name, "IMO": reg_imo, "Callsign": reg_cs,
                            "Flag": reg_flag,
                            "match_method": "Callsign_REJECTED",
                            "field": "ALL",
                            "old_value": f"GT={reg_gt}, Builtdate={reg_bd}",
                            "new_value": f"GT={spider_gt}, Builtdate={safe_float(cand['builtdate_scraped'])}",
                            "reason": f"船型不兼容({spider_type} vs {reg_vesseltype}) + GT超容差"
                        })
                        continue
                    updated_count["Callsign_rejected_ship_type"] += 1
                    change_log.append({
                        "Vesselname": reg_name, "IMO": reg_imo, "Callsign": reg_cs,
                        "Flag": reg_flag,
                        "match_method": "Callsign_REJECTED",
                        "field": "ALL",
                        "old_value": f"GT={reg_gt}, Builtdate={reg_bd}",
                        "new_value": f"GT={spider_gt}, Builtdate={safe_float(cand['builtdate_scraped'])}",
                        "reason": f"船型不兼容: spider={spider_type}, registry={reg_vesseltype}"
                    })
                    continue

                if not gt_ok and type_ok != True:
                    # GT 超容差且船型不确定 → 拒绝
                    updated_count["Callsign_rejected_gt"] += 1
                    change_log.append({
                        "Vesselname": reg_name, "IMO": reg_imo, "Callsign": reg_cs,
                        "Flag": reg_flag,
                        "match_method": "Callsign_REJECTED",
                        "field": "ALL",
                        "old_value": f"GT={reg_gt}, Builtdate={reg_bd}",
                        "new_value": f"GT={spider_gt}, Builtdate={safe_float(cand['builtdate_scraped'])}",
                        "reason": f"GT超容差: {reg_gt}→{spider_gt} ({(spider_gt/reg_gt-1)*100:+.0f}%)"
                    })
                    continue

                if not gt_ok:
                    # 船型兼容但 GT 超容差 → 拒绝
                    updated_count["Callsign_rejected_gt"] += 1
                    change_log.append({
                        "Vesselname": reg_name, "IMO": reg_imo, "Callsign": reg_cs,
                        "Flag": reg_flag,
                        "match_method": "Callsign_REJECTED",
                        "field": "ALL",
                        "old_value": f"GT={reg_gt}, Builtdate={reg_bd}",
                        "new_value": f"GT={spider_gt}, Builtdate={safe_float(cand['builtdate_scraped'])}",
                        "reason": f"GT超容差: {reg_gt}→{spider_gt} ({(spider_gt/reg_gt-1)*100:+.0f}%)"
                    })
                    continue

                # 通过！使用此候选
                spider_row = cand
                match_method = "Callsign_validated"
                if type_ok is None:
                    validation_notes = f"船型不确定(spider={spider_type}, reg={reg_vesseltype}), GT容差通过"
                break

            # 如果所有候选都失败
            if spider_row is None:
                pass  # change_log 已在上面记录

        # --- 第三级：ShipName 交叉验证匹配（最低信任度） ---
        if spider_row is None and reg_name:
            reg_name_upper = reg_name.upper()
            # 先精确匹配，再尝试模糊匹配
            candidates = name_index.get(reg_name_upper, [])
            if not candidates:
                # 尝试用标准化船名匹配（去非字母数字）
                reg_name_norm = re.sub(r'[^A-Z0-9]', '', reg_name_upper)
                for name_key, cands in name_index.items():
                    if re.sub(r'[^A-Z0-9]', '', name_key) == reg_name_norm:
                        candidates = cands
                        break

            for cand in candidates:
                spider_gt = safe_float(cand["tonnage_scraped"])
                spider_type = cand["ship_type_scraped"]

                # 校验 1: 船型兼容性（必须明确兼容）
                type_ok = is_ship_type_compatible(spider_type, reg_vesseltype)
                if type_ok == False:
                    continue  # 船名匹配 + 船型不兼容 → 先跳过看下一个候选

                # 校验 2: GT 容差（必须通过）
                gt_ok = True
                if (not np.isnan(reg_gt)) and (not np.isnan(spider_gt)) and reg_gt > 0:
                    ratio = spider_gt / reg_gt
                    gt_ok = (1 - GT_TOLERANCE) <= ratio <= (1 + GT_TOLERANCE)
                if not gt_ok:
                    continue

                # 校验 3: Flag 一致性（ShipName 匹配要求同国旗）
                spider_flag = cand.get("flag_scraped", "")
                if spider_flag and reg_flag:
                    sf_norm = spider_flag.upper().strip()
                    rf_norm = reg_flag.upper().strip()
                    # 简单检查：国旗代码一致或互相包含
                    if sf_norm != rf_norm and sf_norm not in rf_norm and rf_norm not in sf_norm:
                        continue

                # 全部通过
                spider_row = cand
                match_method = "ShipName_validated"
                validation_notes = "ShipName交叉验证通过(船型+GT+国旗)"
                break

        if spider_row is None:
            continue  # 无匹配，跳过此船

        # ---- 执行更新 ----
        spider_bd = safe_float(spider_row["builtdate_scraped"])
        spider_gt = safe_float(spider_row["tonnage_scraped"])
        spider_mmsi = safe_float(spider_row["mmsi"])
        spider_type = spider_row["ship_type_scraped"]
        spider_flag = spider_row["flag_scraped"]

        changes_this_row = []

        # --- 更新 Builtdate ---
        if not np.isnan(spider_bd) and spider_bd > 1900:
            old_bd = registry.at[idx, "Builtdate"]
            if np.isnan(safe_float(old_bd)) or abs(safe_float(old_bd) - spider_bd) > 0.1:
                registry.at[idx, "Builtdate"] = spider_bd
                changes_this_row.append(f"Builtdate: {old_bd} → {int(spider_bd)}")

        # --- 更新 Tonnage (GT) ---
        if not np.isnan(spider_gt) and spider_gt > 0:
            old_gt = safe_float(registry.at[idx, "Tonnage"])
            if np.isnan(old_gt) or abs(old_gt - spider_gt) / max(old_gt, spider_gt) > 0.01:
                registry.at[idx, "Tonnage"] = spider_gt
                registry.at[idx, "TonnageType"] = "GT"
                changes_this_row.append(f"Tonnage: {old_gt} → {spider_gt}")

        # --- 更新 MMSI（仅填补缺失或明显不同） ---
        if not np.isnan(spider_mmsi) and spider_mmsi > 0:
            old_mmsi = safe_float(registry.at[idx, "MMSI"])
            if np.isnan(old_mmsi) or old_mmsi == 0:
                registry.at[idx, "MMSI"] = spider_mmsi
                changes_this_row.append(f"MMSI: 空 → {int(spider_mmsi)}")

        # --- 更新 VesselType（仅当 spider 明确指示为 TS/运输船） ---
        new_gear = map_ship_type_to_gear(spider_type)
        if new_gear and registry.at[idx, "VesselType"] != new_gear:
            old_type = registry.at[idx, "VesselType"]
            registry.at[idx, "VesselType"] = new_gear
            changes_this_row.append(f"VesselType: {old_type} → {new_gear}")

        # --- 更新 Flag（仅当登记册无国旗且 spider 有） ---
        if spider_flag:
            old_flag = safe_str(registry.at[idx, "Flag"])
            if not old_flag or old_flag in ("", "nan"):
                registry.at[idx, "Flag"] = spider_flag
                changes_this_row.append(f"Flag: 空 → {spider_flag}")

        if changes_this_row:
            updated_count[match_method] += 1
            change_log.append({
                "Vesselname": reg_name,
                "IMO": reg_imo,
                "Callsign": reg_cs,
                "Flag": reg_flag,
                "match_method": match_method,
                "field": "; ".join([c.split(":")[0] for c in changes_this_row]),
                "old_value": "; ".join([c.split(": ")[1].split(" → ")[0] for c in changes_this_row]),
                "new_value": "; ".join([c.split(" → ")[1] for c in changes_this_row]),
                "reason": validation_notes if validation_notes else (
                    "IMO锚点直接更新" if match_method == "IMO_anchor" else "Callsign交叉验证通过"
                ),
            })

    print(f"\n  更新统计:")
    print(f"    IMO 锚点更新: {updated_count['IMO_anchor']} 艘")
    print(f"    Callsign 验证通过: {updated_count['Callsign_validated']} 艘")
    print(f"    ShipName 验证通过: {updated_count['ShipName_validated']} 艘")
    print(f"    Callsign 拒绝(船型不兼容): {updated_count['Callsign_rejected_ship_type']} 艘")
    print(f"    Callsign 拒绝(GT超容差): {updated_count['Callsign_rejected_gt']} 艘")
    print(f"    Callsign 拒绝(双重失败): {updated_count['Callsign_rejected_both']} 艘")
    print(f"    总更新: {len(change_log)} 项")

    change_df = pd.DataFrame(change_log) if change_log else pd.DataFrame()
    return registry, change_df


# =============================================================================
# 主入口
# =============================================================================

def main():
    print("=" * 70)
    print("  Spider 数据 → Unified_Vessel_Registry 参数更新")
    print("  IMO 锚点（绝对信任）+ Callsign 交叉验证")
    print("=" * 70)

    # ---- 加载登记册 ----
    print(f"\n加载登记册: {REGISTRY_PATH}")
    registry = pd.read_csv(REGISTRY_PATH, encoding="utf-8-sig")
    print(f"  当前船舶数: {len(registry)}")

    # 记录更新前的统计
    old_bd_count = registry["Builtdate"].notna().sum()
    old_gt_count = registry["Tonnage"].notna().sum()
    old_mmsi_count = registry["MMSI"].notna().sum()

    # ---- 加载 spider 数据 ----
    spider = load_spider_data()

    # ---- 执行更新 ----
    registry, change_log = update_registry(registry, spider)

    # ---- 更新后统计 ----
    new_bd_count = registry["Builtdate"].notna().sum()
    new_gt_count = registry["Tonnage"].notna().sum()
    new_mmsi_count = registry["MMSI"].notna().sum()

    print(f"\n  数据完整性变化:")
    print(f"    Builtdate: {old_bd_count} → {new_bd_count} (+{new_bd_count-old_bd_count})")
    print(f"    Tonnage:   {old_gt_count} → {new_gt_count} (+{new_gt_count-old_gt_count})")
    print(f"    MMSI:      {old_mmsi_count} → {new_mmsi_count} (+{new_mmsi_count-old_mmsi_count})")

    # ---- 输出 ----
    print("\n" + "=" * 70)
    print("  保存结果")
    print("=" * 70)

    # 保存更新后的登记册
    registry.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"  登记册已更新: {OUTPUT_PATH}")

    # 保存变更日志
    log_path = BASE_DIR / "Registry_Update_Log.csv"
    if len(change_log) > 0:
        change_log.to_csv(log_path, index=False, encoding="utf-8-sig")
        print(f"  变更日志: {log_path} ({len(change_log)} 条变更)")

        # 打印变更摘要
        print(f"\n  变更字段分布:")
        field_counts = change_log["field"].value_counts()
        for field, count in field_counts.items():
            print(f"    {field}: {count}")

    print("\n  完成。")
    return registry, change_log


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    registry, change_log = main()
