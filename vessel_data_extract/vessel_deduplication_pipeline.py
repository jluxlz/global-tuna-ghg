#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
vessel_deduplication_pipeline.py
=============================================================================
全球远洋金枪鱼船舶资产登记册（Vessel Records）深度清洗与重构脚本

功能：
  1. 池化 5 个 RFMO 的提取船舶数据
  2. 通过三级级联匹配（IMO → Callsign → Name+Flag）识别同一物理船舶
  3. 跨记录填补缺失参数（GT, kW, Length, Builtdate）
  4. 保留信息最饱满且最新的记录作为唯一档案
  5. 对重复原因进行诊断分类（换皮/升级/刷脸）

管线位置：
  extract_and_validate_rfmos.py → vessel_deduplication_pipeline.py → 下游分析

输出：
  - Unified_Vessel_Registry.csv  : 去重后的全局唯一船舶登记册
  - Duplicate_Diagnosis_Report.csv : 每艘船的重复原因诊断报告

=============================================================================
"""

import os
import sys
import re
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

# 抑制 pandas FutureWarning（本项目使用 stable API）
pd.set_option('future.no_silent_downcasting', True)

# =============================================================================
# 全局配置
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent  # vessel_data_extract/
EXTRACTED_DIR = BASE_DIR / "new_extracted_vessel_data"
OUTPUT_DIR = BASE_DIR

# 五个 RFMO 的提取文件映射
RFMO_FILES = {
    "CCSBT": EXTRACTED_DIR / "CCSBT_extracted_new.csv",
    "IATTC": EXTRACTED_DIR / "IATTC_extracted_new.csv",
    "ICCAT": EXTRACTED_DIR / "ICCAT_extracted_new.csv",
    "IOTC":  EXTRACTED_DIR / "IOTC_extracted_new.csv",
    "WCPFC": EXTRACTED_DIR / "WCPFC_extracted_new.csv",
}

# 输出文件
OUTPUT_REGISTRY = OUTPUT_DIR / "Unified_Vessel_Registry.csv"
OUTPUT_DIAGNOSIS = OUTPUT_DIR / "Duplicate_Diagnosis_Report.csv"


# =============================================================================
# 1. 字符串预处理工具
# =============================================================================

def safe_str(val) -> str:
    """将任意值转为安全字符串，处理 NaN/None。"""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", ""):
        return ""
    # 移除 .0 后缀（pandas 将整数读为 float 时产生）
    if s.endswith(".0") and s.count(".") == 1:
        try:
            float(s)
            s = s[:-2]
        except ValueError:
            pass
    return s


def normalize_imo(raw_imo) -> str:
    """
    标准化 IMO 编号。
    IMO 必须是 7 位数字；拒绝占位符 'PENDING', 'NE', '0' 等。

    修复尾零问题：某些 RFMO 将 7 位 IMO 存储为 8 位（末尾多一个 0）。
    例如 9940693（正确）vs 99406930（尾零错误）→ 统一为 9940693。
    策略：仅修复恰好 8 位且末尾为 0 的值；其他长度不作为匹配键。
    （IMO 编号方案永远是 7 位数字，不存在 8 位的正式 IMO）
    """
    s = safe_str(raw_imo).upper().strip()
    # 排除明显的占位符
    if s in ("PENDING", "NE", "N/A", "UNKNOWN", "0", "0.0", ""):
        return ""
    # 提取数字
    digits = re.sub(r'\D', '', s)
    if not digits:
        return ""
    # 修复恰好一位尾零，不截断其他长编号。
    if len(digits) == 8 and digits.endswith('0'):
        digits = digits[:7]
    # IMO 必须为 7 位数字。
    if len(digits) == 7:
        return digits
    return ""


def normalize_callsign(raw_cs) -> str:
    """
    标准化呼号。
    去空格、去特殊标点、统一大写。
    排除占位符 'UNKNOWN', 'NONE', 'PENDING', 'N/A', '(BLANK)'。
    """
    s = safe_str(raw_cs).upper().strip()
    if s in ("UNKNOWN", "NONE", "PENDING", "N/A", "(BLANK)", "(N/A)", ""):
        return ""
    # 移除所有非字母数字字符
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s


def normalize_vesselname(raw_name) -> str:
    """
    标准化船名。
    去前后空格、去除多余内部空格、去除特殊标点、统一大写。
    """
    s = safe_str(raw_name).upper().strip()
    if not s:
        return ""
    # 移除特殊标点（保留字母数字和空格）
    s = re.sub(r'[^A-Z0-9\s]', '', s)
    # 合并多个连续空格为单个空格
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_flag(raw_flag) -> str:
    """
    标准化船籍国。
    去空格、统一大写、标准化常见别称和 ISO3 代码。
    """
    s = safe_str(raw_flag).upper().strip()
    if not s:
        return ""
    # ISO3 代码 → 标准名称 映射
    # 确保跨组织国旗匹配的一致性（某些组织存储 ISO3，某些存储全名）
    iso3_map = {
        "JPN": "JAPAN", "KOR": "SOUTH KOREA", "PRK": "NORTH KOREA",
        "TWN": "TAIWAN", "CHN": "CHINA", "HKG": "HONG KONG",
        "USA": "UNITED STATES", "GBR": "UNITED KINGDOM",
        "FRA": "FRANCE", "ESP": "SPAIN", "PRT": "PORTUGAL",
        "DEU": "GERMANY", "ITA": "ITALY", "NLD": "NETHERLANDS",
        "BEL": "BELGIUM", "SWE": "SWEDEN", "DNK": "DENMARK",
        "FIN": "FINLAND", "NOR": "NORWAY", "ISL": "ICELAND",
        "IRL": "IRELAND", "GRC": "GREECE", "MLT": "MALTA",
        "CYP": "CYPRUS", "HRV": "CROATIA", "POL": "POLAND",
        "UKR": "UKRAINE", "ROU": "ROMANIA", "BGR": "BULGARIA",
        "TUR": "TURKEY", "RUS": "RUSSIAN FEDERATION",
        "AUS": "AUSTRALIA", "NZL": "NEW ZEALAND",
        "CAN": "CANADA", "MEX": "MEXICO",
        "BRA": "BRAZIL", "ARG": "ARGENTINA", "CHL": "CHILE",
        "PER": "PERU", "ECU": "ECUADOR", "COL": "COLOMBIA",
        "VEN": "VENEZUELA", "GUY": "GUYANA", "SUR": "SURINAME",
        "PAN": "PANAMA", "CRI": "COSTA RICA", "SLV": "EL SALVADOR",
        "GTM": "GUATEMALA", "HND": "HONDURAS", "NIC": "NICARAGUA",
        "BLZ": "BELIZE", "CUB": "CUBA", "DOM": "DOMINICAN REPUBLIC",
        "JAM": "JAMAICA", "BHS": "BAHAMAS", "BRB": "BARBADOS",
        "TTO": "TRINIDAD AND TOBAGO", "CUW": "CURACAO",
        "IDN": "INDONESIA", "PHL": "PHILIPPINES", "VNM": "VIETNAM",
        "THA": "THAILAND", "MYS": "MALAYSIA", "SGP": "SINGAPORE",
        "MMR": "MYANMAR", "KHM": "CAMBODIA", "IND": "INDIA",
        "LKA": "SRI LANKA", "BGD": "BANGLADESH", "PAK": "PAKISTAN",
        "ZAF": "SOUTH AFRICA", "NAM": "NAMIBIA", "MOZ": "MOZAMBIQUE",
        "TZA": "TANZANIA", "KEN": "KENYA", "SYC": "SEYCHELLES",
        "MUS": "MAURITIUS", "COM": "COMOROS", "MDG": "MADAGASCAR",
        "SOM": "SOMALIA", "OMN": "OMAN", "YEM": "YEMEN",
        "GHA": "GHANA", "SEN": "SENEGAL", "MRT": "MAURITANIA",
        "MAR": "MOROCCO", "DZA": "ALGERIA", "TUN": "TUNISIA",
        "LBY": "LIBYA", "EGY": "EGYPT", "NGA": "NIGERIA",
        "CIV": "COTE D'IVOIRE", "CPV": "CABO VERDE", "GIN": "GUINEA",
        "GMB": "GAMBIA", "GNB": "GUINEA-BISSAU", "SLE": "SIERRA LEONE",
        "TGO": "TOGO", "BEN": "BENIN", "COG": "CONGO",
        "AGO": "ANGOLA", "ALB": "ALBANIA", "ARE": "UNITED ARAB EMIRATES",
        "LBR": "LIBERIA", "VUT": "VANUATU", "FJI": "FIJI",
        "PNG": "PAPUA NEW GUINEA", "SLB": "SOLOMON ISLANDS",
        "KIR": "KIRIBATI", "TUV": "TUVALU", "NRU": "NAURU",
        "MHL": "MARSHALL ISLANDS", "FSM": "MICRONESIA",
        "COK": "COOK ISLANDS", "WSM": "SAMOA", "TON": "TONGA",
        "PYF": "FRENCH POLYNESIA", "NCL": "NEW CALEDONIA",
    }
    if s in iso3_map:
        return iso3_map[s]
    # 常见别称标准化映射
    alias_map = {
        "KOREA": "SOUTH KOREA",
        "REPUBLIC OF KOREA": "SOUTH KOREA",
        "TAIWAN, FISHING ENTITY OF": "TAIWAN",
        "TAIWAN PROVINCE OF CHINA": "TAIWAN",
        "PEOPLE'S REPUBLIC OF CHINA": "CHINA",
        "UNITED STATES OF AMERICA": "UNITED STATES",
        "UK": "UNITED KINGDOM",
    }
    return alias_map.get(s, s)


def normalize_name_for_matching(raw_name) -> str:
    """
    用于匹配的激进版船名标准化（修复空格/顺序/符号问题）。

    处理逻辑：
      1. 转大写
      2. 将所有非字母数字字符替换为空格（解决 NO.1 vs NO。1 vs NO1 问题）
      3. 按空格分词、排序（解决 DONG WON NO 211 vs NO211 DONGWON 问题）
      4. 重新拼接（去除所有空格 — 解决 DAIKICHI MARU NO 5 vs DAIKICHI MARU NO5 问题）

    返回纯字母数字字符串，仅用于匹配比对，不用于展示。
    """
    s = safe_str(raw_name).upper().strip()
    if not s:
        return ""
    # 将所有非字母数字字符替换为空格
    s = re.sub(r'[^A-Z0-9]', ' ', s)
    # 分词、去空、排序
    tokens = sorted([t for t in s.split() if t])
    # 直接拼接（不加空格），彻底消除空格差异
    return ''.join(tokens)


def normalize_gear_type(vessel_type_val, source_vessel_type_val=None) -> str:
    """
    标准化网具/船舶类型，用于跨组织匹配时的网具一致性校验。

    VesselType 标准化规则：
      - LL   → LONGLINE
      - PS   → PURSE_SEINE
      - TS   → TRANSSHIPMENT
      - SA   → OTHER
      - 空值 → UNKNOWN
    保留 SourceVesselType 的精细分类作为辅助键。
    """
    vt = safe_str(vessel_type_val).upper().strip()
    if vt in ("LL", "LONGLINE"):
        gear = "LONGLINE"
    elif vt in ("PS", "PURSE_SEINE"):
        gear = "PURSE_SEINE"
    elif vt in ("TS", "TRANSSHIPMENT", "CARRIER"):
        gear = "TRANSSHIPMENT"
    elif vt:
        gear = "OTHER"
    else:
        gear = "UNKNOWN"
    return gear


# =============================================================================
# 2. 数据加载与池化
# =============================================================================

def load_data() -> pd.DataFrame:
    """
    加载 5 个 RFMO 的提取船舶数据，添加 Source_RFMO 标签，
    统一列名后池化为单个 DataFrame。
    """
    print("=" * 70)
    print("  阶段一：数据加载与池化")
    print("=" * 70)

    frames = []
    for rfmo_name, filepath in RFMO_FILES.items():
        if not filepath.exists():
            print(f"  [警告] 文件不存在，跳过: {filepath}")
            continue

        df = pd.read_csv(filepath, encoding="utf-8-sig")
        n_rows = len(df)
        df["Source_RFMO"] = rfmo_name
        frames.append(df)
        print(f"  {rfmo_name}: {n_rows} 条记录")

    pooled = pd.concat(frames, ignore_index=True)
    print(f"\n  池化后总记录数: {len(pooled)}")
    return pooled


def preprocess_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    对关键匹配字段进行字符串标准化预处理。
    生成标准化后的辅助列：_imo_key, _cs_key, _name_key, _flag_key, _gear_key。

    重要修复：
      - 当 Flagcode 列存在且有效时，优先使用 Flagcode（当前国旗），
        而非 Flag（某些 RFMO 的 Flag 可能存储了历史国旗如 FlagVesCodePrev）。
        例如 ICCAT: Flag=PRT(旧国旗), Flagcode=JPN(当前国旗) → 应使用 JPN。
    """
    print("\n" + "=" * 70)
    print("  阶段二：字符串标准化预处理")
    print("=" * 70)

    df = df.copy()

    # ---- 国旗修复：当 Flagcode 有效时覆盖 Flag ----
    # ICCAT 的 Flag 列被错误地填充了 FlagVesCodePrev（历史国旗）
    # 而 Flagcode 列存储的是正确的当前国旗 ISO3 代码
    if "Flagcode" in df.columns:
        n_flagcode_valid = df["Flagcode"].apply(
            lambda x: isinstance(x, str) and x.strip() not in ("", "nan", "NaN", "None", "N/A")
        ).sum()
        if n_flagcode_valid > 0:
            flagcode_mask = df["Flagcode"].apply(
                lambda x: isinstance(x, str) and x.strip() not in ("", "nan", "NaN", "None", "N/A")
            )
            n_replaced = flagcode_mask.sum()
            df.loc[flagcode_mask, "Flag"] = df.loc[flagcode_mask, "Flagcode"]
            print(f"  国旗修复: {n_replaced} 条记录使用 Flagcode 覆盖 Flag")
        else:
            print(f"  国旗修复: Flagcode 列全为空，无需修复")
    else:
        print(f"  国旗修复: 无 Flagcode 列，无需修复")

    # ---- 标准化匹配键 ----
    df["_imo_key"] = df["IMO"].apply(normalize_imo)
    df["_cs_key"] = df["Callsign"].apply(normalize_callsign)
    # 展示名（保留空格和原始词序）
    df["_name_display"] = df["Vesselname"].apply(normalize_vesselname)

    # 匹配键 1：分词排序（解决词序问题：DONG WON NO 211 ↔ NO211 DONG WON）
    # 去标点→分词→排序→无空格拼接
    df["_name_key"] = df["Vesselname"].apply(normalize_name_for_matching)

    # 匹配键 2：纯去空格（解决空格问题：GUANG YUAN YU 331 ↔ GUANGYUANYU331）
    # 去所有非字母数字字符（含空格）→ 保留原始顺序
    df["_name_key_nospace"] = df["Vesselname"].apply(
        lambda x: re.sub(r'[^A-Z0-9]', '', safe_str(x).upper())
    )

    # 匹配键 3：字符排序（解决 NO203 vs NO 203、DONGWON vs DONG WON 等
    # 字母数字边界 + 空格 + 词序混合差异）
    # 去所有非字母数字 → 所有字符按字母顺序排序 → 最激进归一化
    df["_name_key_charsort"] = df["Vesselname"].apply(
        lambda x: ''.join(sorted(re.sub(r'[^A-Z0-9]', '', safe_str(x).upper())))
    )

    df["_flag_key"] = df["Flag"].apply(normalize_flag)
    # 网具类型键（跨组织匹配时的硬约束）
    df["_gear_key"] = df.apply(
        lambda r: normalize_gear_type(
            r.get("VesselType", None),
            r.get("SourceVesselType", None)
        ), axis=1
    )

    n_imo_valid = (df["_imo_key"] != "").sum()
    n_cs_valid = (df["_cs_key"] != "").sum()
    n_name1_valid = (df["_name_key"] != "").sum()
    n_name2_valid = (df["_name_key_nospace"] != "").sum()
    n_flag_valid = (df["_flag_key"] != "").sum()

    print(f"  有效 IMO 记录: {n_imo_valid}/{len(df)} ({100*n_imo_valid/len(df):.1f}%)")
    print(f"  有效 Callsign 记录: {n_cs_valid}/{len(df)} ({100*n_cs_valid/len(df):.1f}%)")
    print(f"  有效 Name(分词) 记录: {n_name1_valid}/{len(df)} ({100*n_name1_valid/len(df):.1f}%)")
    print(f"  有效 Name(去空格) 记录: {n_name2_valid}/{len(df)} ({100*n_name2_valid/len(df):.1f}%)")
    print(f"  有效 Flag 记录: {n_flag_valid}/{len(df)} ({100*n_flag_valid/len(df):.1f}%)")

    # 网具分布
    gear_dist = df["_gear_key"].value_counts()
    print(f"  网具类型分布: {gear_dist.to_dict()}")

    return df


# =============================================================================
# 4. Union-Find 级联匹配引擎
# =============================================================================

class UnionFind:
    """并查集（Union-Find）数据结构，带路径压缩。"""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        """查找根节点（带路径压缩）。"""
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> bool:
        """合并两个集合（按秩合并）。返回 True 表示真正发生了合并。"""
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        if self.rank[px] < self.rank[py]:
            self.parent[px] = py
        elif self.rank[px] > self.rank[py]:
            self.parent[py] = px
        else:
            self.parent[py] = px
            self.rank[px] += 1
        return True


def build_vessel_graph(df: pd.DataFrame) -> pd.DataFrame:
    """
    使用并查集进行三级级联匹配，将同一物理船舶的所有记录
    归入同一个 Vessel_Cluster_ID。

    匹配优先级：
      第一阶段：IMO 匹配（主键 — 相同 IMO = 同一船舶）
      第二阶段：Callsign 匹配（次键，桥接无 IMO 记录）
      第三阶段：Name + Flag + Gear 匹配（辅助兜底，双键互补）

    安全约束（防误匹配）：
      1. IMO 冲突检测（全阶段）：如果两条记录拥有不同的有效 IMO → 绝不合并
         （例如 WAKABA MARU NO.6: IOTC IMO=9062635, WCPFC IMO=2638368 → 不同船）
         此检查在第二阶段和第三阶段均生效。
      2. 网具类型一致性：Name 匹配时要求 VesselType 一致
         （例如同一船名但在不同组织注册为 LL 和 PS → 不同船）
      3. 双键互补：同时使用分词排序键（解决词序差异）和纯去空格键
         （解决空格有无差异），任一匹配即可链接。
    """
    print("\n" + "=" * 70)
    print("  阶段三：级联匹配（Union-Find）")
    print("=" * 70)

    n = len(df)
    uf = UnionFind(n)
    edges_created = [0, 0, 0, 0, 0]   # [IMO, Callsign, NF-key1, NF-key2, blocked]
    imo_blocked_phase2 = 0
    imo_blocked_phase3 = 0

    # --- 第一阶段：IMO 匹配 ---
    imo_groups = defaultdict(list)
    for i, key in enumerate(df["_imo_key"]):
        if key:
            imo_groups[key].append(i)

    for key, indices in imo_groups.items():
        if len(indices) >= 2:
            root = indices[0]
            for idx in indices[1:]:
                if uf.union(root, idx):
                    edges_created[0] += 1

    print(f"  第一阶段 (IMO): {len(imo_groups)} 个唯一 IMO, {edges_created[0]} 条边")

    # --- 构建集群 IMO 索引（阶段一之后）---
    cluster_imos = defaultdict(set)
    for i in range(n):
        imo = df.at[i, "_imo_key"]
        if imo:
            root = uf.find(i)
            cluster_imos[root].add(imo)

    print(f"  IMO 索引: {sum(1 for v in cluster_imos.values() if v)} 个集群已关联 IMO")

    # --- 第二阶段：Callsign 匹配（带 IMO 冲突检测）---
    cs_groups = defaultdict(list)
    for i, key in enumerate(df["_cs_key"]):
        if key:
            cs_groups[key].append(i)

    cs_edges = 0
    for key, indices in cs_groups.items():
        if len(indices) < 2:
            continue
        # 按有无 IMO 排序：有 IMO 的作为锚点
        indices_with_imo = [(i, bool(df.at[i, "_imo_key"])) for i in indices]
        indices_with_imo.sort(key=lambda x: (x[1], x[0]), reverse=True)
        sorted_indices = [i for i, _ in indices_with_imo]

        anchor = sorted_indices[0]
        for idx in sorted_indices[1:]:
            root_anchor = uf.find(anchor)
            root_idx = uf.find(idx)
            if root_anchor == root_idx:
                continue

            # IMO 冲突检测：两个集群的 IMO 集合不重叠 → 拒绝
            imos_a = cluster_imos[root_anchor]
            imos_b = cluster_imos[root_idx]
            if imos_a and imos_b and not (imos_a & imos_b):
                imo_blocked_phase2 += 1
                continue

            # 安全合并
            if uf.union(anchor, idx):
                cs_edges += 1
                new_root = uf.find(anchor)
                cluster_imos[new_root] = imos_a | imos_b
                if root_anchor != new_root:
                    cluster_imos.pop(root_anchor, None)
                if root_idx != new_root:
                    cluster_imos.pop(root_idx, None)

    edges_created[1] = cs_edges
    print(f"  第二阶段 (Callsign): {len(cs_groups)} 个唯一 Callsign, {cs_edges} 条边")
    if imo_blocked_phase2 > 0:
        print(f"    IMO 冲突阻止: {imo_blocked_phase2} 次")

    # --- 第三阶段：Name + Flag + Gear 匹配（三键互补）---
    # 键 A：分词排序 Name + Flag + Gear（解决词序差异）
    # 键 B：纯去空格 Name + Flag + Gear（解决空格有无差异）
    # 键 C：字符排序 Name + Flag + Gear（解决 NO203↔NO 203、DONGWON↔DONG WON）
    # 任一匹配即可建立连接
    groups_key1 = defaultdict(list)  # token-sort key
    groups_key2 = defaultdict(list)  # nospace key
    groups_key3 = defaultdict(list)  # charsort key

    for i in range(n):
        flag_key = df.at[i, "_flag_key"]
        gear_key = df.at[i, "_gear_key"]
        if not flag_key:
            continue

        name1 = df.at[i, "_name_key"]           # token-sort
        name2 = df.at[i, "_name_key_nospace"]   # space-stripped
        name3 = df.at[i, "_name_key_charsort"]  # char-sorted

        if name1:
            groups_key1[name1 + "|||" + flag_key + "|||" + gear_key].append(i)
        if name2:
            groups_key2[name2 + "|||" + flag_key + "|||" + gear_key].append(i)
        if name3:
            groups_key3[name3 + "|||" + flag_key + "|||" + gear_key].append(i)

    nf_edges = 0

    # 处理三个键组（共享同一套 conflict 检测逻辑）
    # Character sorting destroys vessel numbers: NO 123 and NO 132 become identical.
    for groups, key_label in [(groups_key1, "分词排序"), (groups_key2, "去空格")]:
        for key, indices in groups.items():
            if len(indices) < 2:
                continue

            indices_with_imo = [(i, bool(df.at[i, "_imo_key"])) for i in indices]
            indices_with_imo.sort(key=lambda x: (x[1], x[0]), reverse=True)
            sorted_indices = [i for i, _ in indices_with_imo]

            anchor = sorted_indices[0]
            for idx in sorted_indices[1:]:
                root_anchor = uf.find(anchor)
                root_idx = uf.find(idx)
                if root_anchor == root_idx:
                    continue

                imos_a = cluster_imos[root_anchor]
                imos_b = cluster_imos[root_idx]
                if imos_a and imos_b and not (imos_a & imos_b):
                    imo_blocked_phase3 += 1
                    continue

                if uf.union(anchor, idx):
                    nf_edges += 1
                    new_root = uf.find(anchor)
                    cluster_imos[new_root] = imos_a | imos_b
                    if root_anchor != new_root:
                        cluster_imos.pop(root_anchor, None)
                    if root_idx != new_root:
                        cluster_imos.pop(root_idx, None)

    edges_created[2] = nf_edges
    total_blocked = imo_blocked_phase2 + imo_blocked_phase3

    print(f"  第三阶段 (Name+Flag+Gear 三键):")
    print(f"    分词排序键: {len(groups_key1)} 个唯一组合")
    print(f"    去空格键:   {len(groups_key2)} 个唯一组合")
    print(f"    字符排序键: {len(groups_key3)} 个唯一组合")
    print(f"    有效边数:   {nf_edges}")
    print(f"    IMO 冲突阻止: {imo_blocked_phase3} 次")
    print(f"  总阻止次数: {total_blocked} (Phase2={imo_blocked_phase2}, Phase3={imo_blocked_phase3})")

    # --- 分配 Cluster ID ---
    cluster_map = {}
    cluster_ids = []
    for i in range(n):
        root = uf.find(i)
        if root not in cluster_map:
            cluster_map[root] = len(cluster_map)
        cluster_ids.append(cluster_map[root])

    df["Vessel_Cluster_ID"] = cluster_ids
    n_clusters = len(cluster_map)

    # 统计集群大小分布
    cluster_sizes = df.groupby("Vessel_Cluster_ID").size()
    size_dist = cluster_sizes.value_counts().sort_index()

    print(f"\n  最终集群数: {n_clusters} (从 {n} 条原始记录)")
    print(f"  唯一船舶（集群大小=1）: {(cluster_sizes==1).sum()}")
    print(f"  重复船舶（集群大小≥2）: {(cluster_sizes>=2).sum()}")
    print(f"  集群大小分布: 最大={cluster_sizes.max()}, "
          f"平均={cluster_sizes.mean():.1f}")
    print(f"  集群大小分布详情:")
    for size, count in size_dist.items():
        if count > 0:
            print(f"    大小={size}: {count} 个集群")

    return df


# =============================================================================
# 5. 跨行填补与智能去重
# =============================================================================

def impute_and_deduplicate(df: pd.DataFrame, diagnosis: pd.DataFrame = None) -> pd.DataFrame:
    """
    对每个 Vessel_Cluster_ID 集群进行智能去重，根据重复类型分别处理：

      Type C（刷脸 — 纯年度续期）：
        参数完全一致，直接删除重复记录，保留信息最饱满的一条。

      Type B（升级 — 功率/吨位变更）：
        保守原则：GT、kW、Length 取集群内最大值（Max）。

        保守原则（Conservative Principle）背景与理据：
        在远洋渔业中，船东为了规避某些管委会的高额吨位税、或者是为了
        逃避严格的"马力/努力量双控"政策，经常会存在"低报（Under-
        reporting）"现象。但他们绝不会闲着没事去"高报"。因此，几个冲突
        数据中的最高值，往往最接近这艘船真实的物理装机容量。

        出于 LCA 碳排放核算的"保守原则（宁可高估不低估）"，取最大值是
        最无懈可击的做法。高估碳排放不会导致"假阴性"（错误地认为某渔业
        是低碳的），而低估则可能掩盖真正的高排放环节。

        物理逻辑：功率增大或吨位增加代表船舶进行了动力升级或结构改造，
        更新后的值是船舶的当前实际状态。即便没有物理改造，低报数据中
        的最高值也是最接近真实值的估计。

      Type A（换皮 — 改名/换旗）：
        合并船名为 "名称A; 名称B" 格式，保留换名历史轨迹。
        Flag 保留所选基础记录的单一旗国；Flag_History 保存换旗记录。

      Type A+B（换皮+升级共存）：
        同时应用 A 和 B 的处理逻辑。
    """
    print("\n" + "=" * 70)
    print("  阶段五：跨行填补与智能去重")
    print("=" * 70)

    # ---- 构建诊断类型查找表 ----
    diag_lookup: dict = {}
    if diagnosis is not None and len(diagnosis) > 0:
        for _, row in diagnosis.iterrows():
            diag_lookup[row["Vessel_Cluster_ID"]] = {
                "type_a": bool(row.get("Type_A_ReFlag", False)),
                "type_b": bool(row.get("Type_B_Modification", False)),
                "type_c": bool(row.get("Type_C_Renewal", False)),
            }

    # ---- 确保数值列类型 ----
    numeric_cols = ["Length", "Tonnage", "Enginepower", "Builtdate"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---- 按集群 + Builtdate 排序（最新在前）----
    df = df.sort_values(["Vessel_Cluster_ID", "Builtdate"],
                        ascending=[True, False]).reset_index(drop=True)

    # ---- 跨行填补：同一集群内用其他记录填补缺失值 ----
    # 优先使用最新记录的值（ffill 从上往下 = 从新到旧），再用旧值回填
    units = {"Length": "LengthType", "Tonnage": "TonnageType", "Enginepower": "PowerType"}
    for col in numeric_cols:
        # Move a measurement with the metadata of the record that supplied it.
        unit_col = units.get(col)
        original = df[col].where(df[col] > 0)
        source_index = pd.Series(np.where(original.notna(), df.index, np.nan), index=df.index)
        source_index = source_index.groupby(df["Vessel_Cluster_ID"]).transform(lambda x: x.ffill().bfill())
        df[col] = original.groupby(df["Vessel_Cluster_ID"]).transform(lambda x: x.ffill().bfill())
        if unit_col and unit_col in df:
            metadata = df[unit_col].copy()
            valid = source_index.notna()
            df.loc[valid, unit_col] = metadata.loc[source_index[valid].astype(int)].to_numpy()
    # 国旗也进行跨行填补
    df["Flag"] = df.groupby("Vessel_Cluster_ID")["Flag"].transform(
        lambda x: x.mask(x == "nan").ffill().bfill()
    )

    # ---- 计算信息饱满度 ----
    for col in numeric_cols:
        df[f"_has_{col}"] = (~df[col].isna()).astype(int)
    df["_completeness_score"] = (
        df["_has_Length"] + df["_has_Tonnage"] +
        df["_has_Enginepower"] + df["_has_Builtdate"]
    )

    # ---- 逐集群处理：根据诊断类型生成最终记录 ----
    results = []
    clusters_without_diag = 0

    for cid, grp in df.groupby("Vessel_Cluster_ID"):
        diag = diag_lookup.get(cid, None)
        if diag is None:
            clusters_without_diag += 1
            diag = {"type_a": False, "type_b": False, "type_c": False}

        # 选择基础记录：信息最饱满，同分时取 Builtdate 最新
        best_idx = grp["_completeness_score"].idxmax()
        record = grp.loc[best_idx].to_dict()

        # --- Type B 处理：保守原则取最大值 ---
        if diag["type_b"]:
            for col in ["Length", "Tonnage", "Enginepower"]:
                max_val = grp[col].max()
                if pd.notna(max_val):
                    record[col] = max_val
                    unit_col = units.get(col)
                    if unit_col in grp:
                        record[unit_col] = grp.loc[grp[col].idxmax(), unit_col]

        # --- Type A 处理：合并船名 + 另存换旗历史 ---
        if diag["type_a"]:
            # 合并国旗：收集所有不同的国旗（ISO3格式，去重、去空）
            flags = grp["Flag"].dropna()
            flags = flags[flags != ""].unique()
            if len(flags) > 1:
                record["Flag_History"] = "; ".join(sorted(flags))
                # A flag lookup requires one country; keep the selected registry record.
                record["Flag"] = grp.loc[best_idx, "Flag"]
            elif len(flags) == 1:
                record["Flag"] = flags[0]

            # 合并船名：只有当三个匹配键都不同（真正的改名）时才合并
            # 若字符排序键一致 → 仅属空格/词序/数字粘连格式差异，不合并
            names = grp["_name_display"].dropna()
            names = names[names != ""].unique()
            name_keys_charsort = grp["_name_key_charsort"].dropna()
            name_keys_charsort = name_keys_charsort[name_keys_charsort != ""].unique()

            real_name_change = (
                len(name_keys_charsort) > 1
                if len(name_keys_charsort) > 0
                else len(names) > 1
            )

            if real_name_change and len(names) > 1:
                record["Vesselname"] = "; ".join(sorted(names))
            elif len(names) >= 1:
                # 名字实际上相同（仅格式差异）→ 取信息最饱满记录的展示名
                record["Vesselname"] = grp.loc[best_idx, "_name_display"]
                if pd.isna(record["Vesselname"]) or record["Vesselname"] == "":
                    record["Vesselname"] = names[0]

        # --- 标记来源组织（多RFMO注册）---
        source_rfmos = sorted(grp["Source_RFMO"].unique())
        record["Authorized_Oceans"] = "; ".join(source_rfmos)

        results.append(record)

    unified = pd.DataFrame(results)

    # ---- 清理占位符值 ----
    # 某些 RFMO 在无 IMO/呼号时填入占位符而非留空，
    # 这些占位符在匹配阶段已被正确忽略，但会残留在输出字段中，需统一清空
    _imo_placeholders = {"PENDING", "NE", "N/A", "UNKNOWN", "0", "0.0"}
    _cs_placeholders = {"(BLANK)", "(N/A)", "NONE", "UNKNOWN", "N.A.", "NONE.",
                        "N.A", "NA", "NIL", "NULL", "TBA", "TBD", "PENDING"}

    for col, placeholder_set in [("IMO", _imo_placeholders), ("Callsign", _cs_placeholders)]:
        if col in unified.columns:
            mask = unified[col].astype(str).str.strip().str.upper().isin(placeholder_set)
            n_cleaned = mask.sum()
            if n_cleaned > 0:
                unified.loc[mask, col] = ""
                print(f"  占位符清理: {col} 字段清空 {n_cleaned} 个占位符值")

    # ---- 清理辅助列及非输出列 ----
    drop_cols = [c for c in unified.columns
                 if c.startswith("_has_") or c.startswith("_completeness")]
    unified = unified.drop(columns=drop_cols + [
        "_imo_key", "_cs_key", "_name_key",
        "_name_key_nospace", "_name_key_charsort", "_name_display",
        "_flag_key", "_gear_key", "Source_RFMO",
        "Vessel_Cluster_ID",
    ], errors="ignore")

    # ---- 只保留基础字段（去重结果已更新到字段内）----
    extraction_cols = [
        "Vesselname", "IMO", "Callsign", "MMSI",
        "Length", "Tonnage", "Enginepower", "Builtdate",
        "VesselType", "SourceVesselType",
        "LengthType", "TonnageType", "PowerType",
        "Flagcode", "Flag", "Flag_History", "Authorized_Oceans",
    ]
    unified = unified[[c for c in extraction_cols if c in unified.columns]]

    # ---- 统计输出 ----
    n_type_b = sum(1 for r in results if diag_lookup.get(r["Vessel_Cluster_ID"], {}).get("type_b"))
    n_type_a = sum(1 for r in results if diag_lookup.get(r["Vessel_Cluster_ID"], {}).get("type_a"))
    n_type_c = sum(1 for r in results if diag_lookup.get(r["Vessel_Cluster_ID"], {}).get("type_c"))

    print(f"  智能去重后唯一船舶数: {len(unified)}")
    print(f"  记录压缩比: {len(df)} → {len(unified)} "
          f"({100*(1-len(unified)/len(df)):.1f}% 压缩)")
    print(f"  其中:")
    print(f"    Type A (换皮-合并船名): {n_type_a}")
    print(f"    Type B (升级-取最大值): {n_type_b}")
    print(f"    Type C (刷脸-直接删除): {n_type_c}")
    if clusters_without_diag > 0:
        print(f"    无诊断信息集群（单记录船舶）: {clusters_without_diag}")

    return unified


# =============================================================================
# 6. 重复原因诊断与分类
# =============================================================================

def diagnose_and_classify_duplicates(df_clustered: pd.DataFrame) -> pd.DataFrame:
    """
    对每个存在重复记录（集群大小 ≥2）的 Vessel_Cluster_ID 进行诊断分类。

    分类规则：
      变异 A（换皮）：Flag 或 Vesselname 在集群内存在差异
      变异 B（升级）：kW 变化 >5% 或 GT 发生变化
      变异 C（刷脸）：集群内所有物理参数 (Flag, kW, GT, Length) 一致，
                      仅是年度行政续期

    注意：A 和 B 可以共存（同一艘船既换旗又升级）
    """
    print("\n" + "=" * 70)
    print("  阶段四：重复原因诊断与分类")
    print("=" * 70)

    # 仅分析有重复的集群
    cluster_counts = df_clustered.groupby("Vessel_Cluster_ID").size()
    multi_record_clusters = cluster_counts[cluster_counts >= 2].index
    df_multi = df_clustered[df_clustered["Vessel_Cluster_ID"].isin(multi_record_clusters)].copy()

    if len(df_multi) == 0:
        print("  无重复记录，跳过诊断。")
        return pd.DataFrame(columns=["Vessel_Cluster_ID", "Type_A_ReFlag",
                                      "Type_B_Modification", "Type_C_Renewal",
                                      "Record_Count", "Notes"])

    # 确保数值列
    for col in ["Enginepower", "Tonnage", "Length", "Builtdate"]:
        df_multi[col] = pd.to_numeric(df_multi[col], errors="coerce")

    # --- 对每个集群进行聚合诊断 ---
    diag_parts = []

    for cid, grp in df_multi.groupby("Vessel_Cluster_ID"):
        n_records = len(grp)

        # 提取有效值集合
        flags = set(grp["_flag_key"].dropna().replace({"": np.nan}).dropna().unique())
        # 展示名（保留空格和原始词序）
        names_display = set(grp["_name_display"].dropna().replace({"": np.nan}).dropna().unique())
        # 三个匹配键：分词排序、纯去空格、字符排序
        names_match = set(grp["_name_key"].dropna().replace({"": np.nan}).dropna().unique())
        names_nospace = set(grp["_name_key_nospace"].dropna().replace({"": np.nan}).dropna().unique())
        names_charsort = set(grp["_name_key_charsort"].dropna().replace({"": np.nan}).dropna().unique())
        # 真正的改名 = 三个键都不同。
        # 若字符排序键一致 → 仅属空格/词序/数字粘连格式差异
        #   （如 DONG WON NO 203 ↔ NO203 DONGWON → 字符集完全相同）
        # 若分词排序键一致 → 仅属空格差异
        # 若去空格键一致 → 仅属词序差异

        kw_vals = grp["Enginepower"].dropna()
        gt_vals = grp["Tonnage"].dropna()
        len_vals = grp["Length"].dropna()

        # --- 变异 A：换皮 ---
        # 真正的改名 = 两个匹配键都存在差异
        # 若分词排序键一致 → 仅词序差异（如 DONG WON NO 211 ↔ NO211 DONG WON）
        # 若去空格键一致   → 仅空格差异（如 GUANG YUAN YU 331 ↔ GUANGYUANYU331）
        # 两个键都不同才是真改名（如 CHOKYU MARU NO.21 ↔ CHOKYU MARU）
        name_changed = (len(names_match) > 1) and (len(names_nospace) > 1) and (len(names_charsort) > 1)
        type_a = False
        a_details = []
        if len(flags) > 1:
            type_a = True
            a_details.append(f"Flag变更: {sorted(flags)}")
        if name_changed:
            type_a = True
            a_details.append(f"船名变更: {sorted(names_display)}")

        # --- 变异 B：升级 ---
        type_b = False
        b_details = []
        if len(kw_vals) >= 2:
            kw_range = (kw_vals.min(), kw_vals.max())
            if kw_vals.max() > 0:
                kw_pct = (kw_vals.max() - kw_vals.min()) / kw_vals.max()
                if kw_pct > 0.05:
                    type_b = True
                    b_details.append(f"kW变化: {kw_range[0]:.1f}→{kw_range[1]:.1f} "
                                     f"({100*kw_pct:.1f}%)")

        if len(gt_vals) >= 2:
            gt_range = (gt_vals.min(), gt_vals.max())
            if gt_vals.max() != gt_vals.min():
                type_b = True
                b_details.append(f"GT变化: {gt_range[0]:.1f}→{gt_range[1]:.1f}")

        # --- 变异 C：刷脸 ---
        # 当既不是 A 也不是 B 时，判定为 C
        type_c = (not type_a) and (not type_b)

        # --- 组装诊断记录 ---
        details = []
        if type_a:
            details.append(f"[A-换皮] {'; '.join(a_details)}")
        if type_b:
            details.append(f"[B-升级] {'; '.join(b_details)}")
        if type_c:
            details.append(f"[C-刷脸] 参数一致，仅年度续期")

        # 获取代表性的 IMO 和船名
        imo_vals = grp["_imo_key"].dropna().replace({"": np.nan}).dropna().unique()
        name_display_vals = grp["_name_display"].dropna().replace({"": np.nan}).dropna().unique()
        rfmo_list = "; ".join(sorted(grp["Source_RFMO"].unique()))

        diag_parts.append({
            "Vessel_Cluster_ID": cid,
            "Record_Count": n_records,
            "IMO": "; ".join(imo_vals) if len(imo_vals) > 0 else "",
            "Vesselname": "; ".join(name_display_vals) if len(name_display_vals) > 0 else "",
            "Type_A_ReFlag": type_a,
            "Type_B_Modification": type_b,
            "Type_C_Renewal": type_c,
            "Unique_Flags": "; ".join(sorted(flags)) if flags else "",
            "Unique_Names": "; ".join(sorted(names_display)) if names_display else "",
            "Authorized_Oceans": rfmo_list,
            "Notes": "; ".join(details),
        })

    diagnosis = pd.DataFrame(diag_parts)

    # --- 输出统计 ---
    n_total_dup = len(diagnosis)
    n_type_a = diagnosis["Type_A_ReFlag"].sum()
    n_type_b = diagnosis["Type_B_Modification"].sum()
    n_type_c = diagnosis["Type_C_Renewal"].sum()
    n_a_and_b = ((diagnosis["Type_A_ReFlag"]) & (diagnosis["Type_B_Modification"])).sum()

    print(f"  重复集群总数: {n_total_dup}")
    print(f"  涉及记录总数: {diagnosis['Record_Count'].sum()}")
    print(f"")
    print(f"  变异 A (换皮 - 换旗/改名): {n_type_a} ({100*n_type_a/n_total_dup:.1f}%)")
    print(f"  变异 B (升级 - 功率/吨位变更): {n_type_b} ({100*n_type_b/n_total_dup:.1f}%)")
    print(f"  变异 C (刷脸 - 纯年度续期): {n_type_c} ({100*n_type_c/n_total_dup:.1f}%)")
    print(f"  其中 A+B 共存: {n_a_and_b} ({100*n_a_and_b/n_total_dup:.1f}%)")

    # 集群大小分布
    size_dist = diagnosis["Record_Count"].value_counts().sort_index()
    print(f"\n  重复集群大小分布:")
    for size, count in size_dist.items():
        print(f"    大小={size}: {count} 个集群 ({100*count/n_total_dup:.1f}%)")

    return diagnosis


# =============================================================================
# 7. 主入口
# =============================================================================

def main():
    print("=" * 70)
    print("  全球金枪鱼船舶资产登记册 — 深度清洗与重构")
    print("  Vessel Deduplication Pipeline")
    print("=" * 70)

    # ---- 阶段一：加载数据 ----
    df = load_data()

    # ---- 阶段二：字符串预处理 ----
    df = preprocess_strings(df)

    # ---- 阶段三：级联匹配（Union-Find）----
    df = build_vessel_graph(df)

    # ---- 阶段四：重复原因诊断（在填补前诊断，保留原始差异）----
    diagnosis = diagnose_and_classify_duplicates(df)

    # ---- 阶段五：跨行填补与智能去重（根据诊断类型分策略处理）----
    unified = impute_and_deduplicate(df, diagnosis)

    # ---- 阶段六：输出结果文件 ----
    print("\n" + "=" * 70)
    print("  阶段六：输出结果文件")
    print("=" * 70)

    # 统一登记册（仅保留与提取文件一致的15个基础字段）
    unified.to_csv(OUTPUT_REGISTRY, index=False, encoding="utf-8-sig")
    print(f"  统一船舶登记册: {OUTPUT_REGISTRY}")
    print(f"    共 {len(unified)} 艘唯一船舶")
    print(f"    字段: {list(unified.columns)}")

    # 诊断报告（单独文件，不合并到登记册）
    if len(diagnosis) > 0:
        diagnosis.to_csv(OUTPUT_DIAGNOSIS, index=False, encoding="utf-8-sig")
        print(f"  重复诊断报告: {OUTPUT_DIAGNOSIS}")
        print(f"    共 {len(diagnosis)} 个重复集群")

    # ---- 最终摘要 ----
    print("\n" + "=" * 70)
    print("  管线执行完毕 — 摘要")
    print("=" * 70)
    print(f"  原始记录: {len(df)}")
    print(f"  唯一船舶: {len(unified)}")
    print(f"  压缩率: {100*(1-len(unified)/len(df)):.1f}%")
    print()

    return unified, diagnosis


if __name__ == "__main__":
    # Windows 控制台编码修复
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    unified, diagnosis = main()
