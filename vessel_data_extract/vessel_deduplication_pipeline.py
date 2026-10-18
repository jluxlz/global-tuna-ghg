#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Harmonise and deduplicate vessel records from five RFMO registries.

The pipeline links records using IMO identifiers, callsigns, then vessel name
and flag. It fills missing physical parameters across linked records and
records changes in identity, vessel characteristics and annual registration.
The output contains one selected record per vessel cluster, together with a
duplicate-diagnosis report. Conflicting characteristics are resolved by the
selection rules implemented below; these are reconstruction assumptions.

Inputs: standardised outputs of extract_and_validate_rfmos.py.
Outputs: Unified_Vessel_Registry.csv and Duplicate_Diagnosis_Report.csv.
"""

import os
import sys
import re
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

# Depress pandas FutureWarning (Use for this item stable API) 
pd.set_option('future.no_silent_downcasting', True)

# =============================================================================
# Global Configuration
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent  # vessel_data_extract/
EXTRACTED_DIR = BASE_DIR / "new_extracted_vessel_data"
OUTPUT_DIR = BASE_DIR

# Five RFMO Map of extraction file
RFMO_FILES = {
    "CCSBT": EXTRACTED_DIR / "CCSBT_extracted_new.csv",
    "IATTC": EXTRACTED_DIR / "IATTC_extracted_new.csv",
    "ICCAT": EXTRACTED_DIR / "ICCAT_extracted_new.csv",
    "IOTC":  EXTRACTED_DIR / "IOTC_extracted_new.csv",
    "WCPFC": EXTRACTED_DIR / "WCPFC_extracted_new.csv",
}

# Output file
OUTPUT_REGISTRY = OUTPUT_DIR / "Unified_Vessel_Registry.csv"
OUTPUT_DIAGNOSIS = OUTPUT_DIR / "Duplicate_Diagnosis_Report.csv"


# =============================================================================
# 1. String pre-processing tool
# =============================================================================

def safe_str(val) -> str:
    """Convert any value to a secure string, Processing NaN/None. """
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", ""):
        return ""
    # Remove .0 Suffix (pandas Read Integer as float Its timed out) 
    if s.endswith(".0") and s.count(".") == 1:
        try:
            float(s)
            s = s[:-2]
        except ValueError:
            pass
    return s


def normalize_imo(raw_imo) -> str:
    """
    standardisation IMO Numbering. 
    IMO It must be 7 Digits; Reject placeholder 'PENDING', 'NE', '0' Wait. 

    Fixing the zero problem: Some RFMO Will 7 bits IMO Store As 8 bits (One more at the end 0) . 
    For example 9940693 (Correct) vs 99406930 (End zero error) → Uniform to 9940693. 
    Policy: Just fix it just in time 8 and at the end of 0 value of the; Other length does not match. 
     (IMO Numbering always is 7 Digits, Cannot initialise Evolutions mail component 8 _Other Organiser IMO) 
    """
    s = safe_str(raw_imo).upper().strip()
    # Exclude clear placeholders
    if s in ("PENDING", "NE", "N/A", "UNKNOWN", "0", "0.0", ""):
        return ""
    # Numbers to extract
    digits = re.sub(r'\D', '', s)
    if not digits:
        return ""
    # Its just a little bit of a fix, Do not cut off other long numbers. 
    if len(digits) == 8 and digits.endswith('0'):
        digits = digits[:7]
    # IMO Yes, I have to 7 Digits. 
    if len(digits) == 7:
        return digits
    return ""


def normalize_callsign(raw_cs) -> str:
    """
    Standard call sign. 
    Go to space, Go to the special point, Uniform uppercase. 
    Exclude placeholders 'UNKNOWN', 'NONE', 'PENDING', 'N/A', '(BLANK)'. 
    """
    s = safe_str(raw_cs).upper().strip()
    if s in ("UNKNOWN", "NONE", "PENDING", "N/A", "(BLANK)", "(N/A)", ""):
        return ""
    # Remove all non-letter numeric characters
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s


def normalize_vesselname(raw_name) -> str:
    """
    Standardized ship name. 
    Go to the front and back spaces, Remove excess internal spaces, Remove Special Point, Uniform uppercase. 
    """
    s = safe_str(raw_name).upper().strip()
    if not s:
        return ""
    # Remove Special Punctuation (Keep Alphabetical numerals and spaces) 
    s = re.sub(r'[^A-Z0-9\s]', '', s)
    # Merge multiple consecutive spaces into individual spaces
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_flag(raw_flag) -> str:
    """
    Standardized country of origin. 
    Go to space, Uniform uppercase, Standardized common aliases ISO3 Code. 
    """
    s = safe_str(raw_flag).upper().strip()
    if not s:
        return ""
    # ISO3 Code → Standard name Map
    # Ensure consistency in cross-organizational flag matching (Some Organizations Store ISO3, Some Storage Full Name) 
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
    # Common aliases for standardized mapping
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
    Standardized radical versions of ship names for matching (Fix Space/Order/Symbol problem) . 

    Deal with logic: 
      1. Revert Capitalcase
      2. Replace all non-letter number characters with spaces (Solve NO.1 vs NO. 1 vs NO1 Problem) 
      3. Words by Space, Sort (Solve DONG WON NO 211 vs NO211 DONGWON Problem) 
      4. Reassemble (Remove all spaces — Solve DAIKICHI MARU NO 5 vs DAIKICHI MARU NO5 Problem) 

    Returns Pure Letter Number String, For matching only, Not for presentation. 
    """
    s = safe_str(raw_name).upper().strip()
    if not s:
        return ""
    # Replace all non-letter number characters with spaces
    s = re.sub(r'[^A-Z0-9]', ' ', s)
    # Words, Go empty, Sort
    tokens = sorted([t for t in s.split() if t])
    # Stretching Directly (No spaces) , Elimination of spatial differences
    return ''.join(tokens)


def normalize_gear_type(vessel_type_val, source_vessel_type_val=None) -> str:
    """
    Standardized web tools/Type of ship, Consistency check for cross-organizational matching. 

    VesselType Standardized rules: 
      - LL   → LONGLINE
      - PS   → PURSE_SEINE
      - TS   → TRANSSHIPMENT
      - SA   → OTHER
      - Empty value → UNKNOWN
    retain SourceVesselType _Other Organiser. 
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
# 2. Data Load and Pooling
# =============================================================================

def load_data() -> pd.DataFrame:
    """
    Load 5 One RFMO RESOURCES FOR THE RESOURCE OF THE RESOURCES OF THE RESOURCES OF THE, Add Source_RFMO Label, 
    Unanimously singled out for listing DataFrame. 
    """
    print("=" * 70)
    print("  Phase I: Data Load and Pooling")
    print("=" * 70)

    frames = []
    for rfmo_name, filepath in RFMO_FILES.items():
        if not filepath.exists():
            print(f"  [This function is EXPERIMENTAL] File does not exist, Skip: {filepath}")
            continue

        df = pd.read_csv(filepath, encoding="utf-8-sig")
        n_rows = len(df)
        df["Source_RFMO"] = rfmo_name
        frames.append(df)
        print(f"  {rfmo_name}: {n_rows} Records")

    pooled = pd.concat(frames, ignore_index=True)
    print(f"\n  Total records after pool: {len(pooled)}")
    return pooled


def preprocess_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardized string pre-processing for key matching fields. 
    Generate standardized support columns: _imo_key, _cs_key, _name_key, _flag_key, _gear_key. 

    Important repairs: 
      - When Flagcode Columns exist and are valid, Priority Use Flagcode (Current Flag) , 
        No, I dont Flag (Some RFMO of Flag It might be a historical flag FlagVesCodePrev) . 
        For example ICCAT: Flag=PRT(Old flag), Flagcode=JPN(Current Flag) → It should be used JPN. 
    """
    print("\n" + "=" * 70)
    print("  Phase II: Standard pre-processing of strings")
    print("=" * 70)

    df = df.copy()

    # ---- Flag restoration: When Flagcode Overwrite when valid Flag ----
    # ICCAT of Flag The columns were wrongly filled FlagVesCodePrev (History flag) 
    # And Flagcode Columns store the correct current flag ISO3 Code
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
            print(f"  Flag restoration: {n_replaced} Use of log Flagcode Overwrite Flag")
        else:
            print(f"  Flag restoration: Flagcode Columns are empty, No need to repair")
    else:
        print(f"  Flag restoration: none Flagcode Column, No need to repair")

    # ---- Standard Matching Keys ----
    df["_imo_key"] = df["IMO"].apply(normalize_imo)
    df["_cs_key"] = df["Callsign"].apply(normalize_callsign)
    # Synchronising folder (Keep Spaces and Original Words Order) 
    df["_name_display"] = df["Vesselname"].apply(normalize_vesselname)

    # Match Key 1: Sorting Words (Solve verbity problems: DONG WON NO 211 ↔ NO211 DONG WON) 
    # Go to the mark→Words→Sort→No Space Collapse
    df["_name_key"] = df["Vesselname"].apply(normalize_name_for_matching)

    # Match Key 2: Just go to space (Solve the problem of spaces: GUANG YUAN YU 331 ↔ GUANGYUANYU331) 
    # Go to all non-letter numerical characters (Space) → Retain original order
    df["_name_key_nospace"] = df["Vesselname"].apply(
        lambda x: re.sub(r'[^A-Z0-9]', '', safe_str(x).upper())
    )

    # Match Key 3: Character Sorting (Solve NO203 vs NO 203, DONGWON vs DONG WON Wait
    # Alphabetic Boundaries + Space + The word sequence mix difference) 
    # Go to all non-letter numbers → All characters in alphabetical order → The most radical of them all
    df["_name_key_charsort"] = df["Vesselname"].apply(
        lambda x: ''.join(sorted(re.sub(r'[^A-Z0-9]', '', safe_str(x).upper())))
    )

    df["_flag_key"] = df["Flag"].apply(normalize_flag)
    # Type of Network Key (Hard constraints on cross-organizational matching) 
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

    print(f"  Validity IMO Records: {n_imo_valid}/{len(df)} ({100*n_imo_valid/len(df):.1f}%)")
    print(f"  Validity Callsign Records: {n_cs_valid}/{len(df)} ({100*n_cs_valid/len(df):.1f}%)")
    print(f"  Validity Name(Words) Records: {n_name1_valid}/{len(df)} ({100*n_name1_valid/len(df):.1f}%)")
    print(f"  Validity Name(Go to space) Records: {n_name2_valid}/{len(df)} ({100*n_name2_valid/len(df):.1f}%)")
    print(f"  Validity Flag Records: {n_flag_valid}/{len(df)} ({100*n_flag_valid/len(df):.1f}%)")

    # Network distribution
    gear_dist = df["_gear_key"].value_counts()
    print(f"  Distribution of Network Type: {gear_dist.to_dict()}")

    return df


# =============================================================================
# 4. Union-Find Cascade matching engine
# =============================================================================

class UnionFind:
    """♪ And check the collection ♪ (Union-Find) Data structure, Compression with Path. """

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        """Find Roots (Compression with Path) . """
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> bool:
        """Merge two sets (Merge with Thread) . Back True That the merger really happened. """
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
    Use and search for a three-tier calibration match, ♪ Put all the records of the same physical ship ♪
    ♪ Become the same ♪ Vessel_Cluster_ID. 

    Match Priority: 
      Phase I: IMO Match (Main Key — Same IMO = Same ship) 
      Phase II: Callsign Match (Minor key, The bridges open IMO Records) 
      Phase III: Name + Flag + Gear Match (Auxiliary Pocket, Double Key Complementation) 

    Security Constraint (Prejudice Match) : 
      1. IMO Conflict detection (Full phase) : If two records have different validitys, IMO → Never merge
          (For example WAKABA MARU NO.6: IOTC IMO=9062635, WCPFC IMO=2638368 → Different ships) 
         This inspection takes effect in both phase II and phase III. 
      2. Network type consistency: Name Require when matching VesselType Unanimously
          (For example, the same name but registered in different organizations LL and PS → Different ships) 
      3. Double Key Complementation: Use the word sorting key at the same time (Resolve the word-order difference) ♪ And the empty spaces ♪
          (Resolve any differences in spaces) , Any match is linked. 
    """
    print("\n" + "=" * 70)
    print("  Phase III: Cascade Matches (Union-Find) ")
    print("=" * 70)

    n = len(df)
    uf = UnionFind(n)
    edges_created = [0, 0, 0, 0, 0]   # [IMO, Callsign, NF-key1, NF-key2, blocked]
    imo_blocked_phase2 = 0
    imo_blocked_phase3 = 0

    # --- Phase I: IMO Match ---
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

    print(f"  Phase I (IMO): {len(imo_groups)} One IMO, {edges_created[0]} The side")

    # --- Form Clusters IMO Index (After phase one) ---
    cluster_imos = defaultdict(set)
    for i in range(n):
        imo = df.at[i, "_imo_key"]
        if imo:
            root = uf.find(i)
            cluster_imos[root].add(imo)

    print(f"  IMO Index: {sum(1 for v in cluster_imos.values() if v)} The clusters are connected IMO")

    # --- Phase II: Callsign Match (Take it IMO Conflict detection) ---
    cs_groups = defaultdict(list)
    for i, key in enumerate(df["_cs_key"]):
        if key:
            cs_groups[key].append(i)

    cs_edges = 0
    for key, indices in cs_groups.items():
        if len(indices) < 2:
            continue
        # Yes, sir IMO Sort: present IMO as anchor point
        indices_with_imo = [(i, bool(df.at[i, "_imo_key"])) for i in indices]
        indices_with_imo.sort(key=lambda x: (x[1], x[0]), reverse=True)
        sorted_indices = [i for i, _ in indices_with_imo]

        anchor = sorted_indices[0]
        for idx in sorted_indices[1:]:
            root_anchor = uf.find(anchor)
            root_idx = uf.find(idx)
            if root_anchor == root_idx:
                continue

            # IMO Conflict detection: Two clusters IMO The collection does not overlap → Reject
            imos_a = cluster_imos[root_anchor]
            imos_b = cluster_imos[root_idx]
            if imos_a and imos_b and not (imos_a & imos_b):
                imo_blocked_phase2 += 1
                continue

            # Secure Merge
            if uf.union(anchor, idx):
                cs_edges += 1
                new_root = uf.find(anchor)
                cluster_imos[new_root] = imos_a | imos_b
                if root_anchor != new_root:
                    cluster_imos.pop(root_anchor, None)
                if root_idx != new_root:
                    cluster_imos.pop(root_idx, None)

    edges_created[1] = cs_edges
    print(f"  Phase II (Callsign): {len(cs_groups)} One Callsign, {cs_edges} The side")
    if imo_blocked_phase2 > 0:
        print(f"    IMO Conflict prevention: {imo_blocked_phase2} Number of times")

    # --- Phase III: Name + Flag + Gear Match (Three-key complementarity) ---
    # Neutrons A: Sorting Words Name + Flag + Gear (Resolve the word-order difference) 
    # Neutrons B: Just go to space Name + Flag + Gear (Resolve any differences in spaces) 
    # Neutrons C: Character Sorting Name + Flag + Gear (Solve NO203↔NO 203, DONGWON↔DONG WON) 
    # Any match creates a connection
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

    # Handle three key groups (Share the same set conflict Test logic) 
    # Character sorting destroys vessel numbers: NO 123 and NO 132 become identical.
    for groups, key_label in [(groups_key1, "Sorting Words"), (groups_key2, "Go to space")]:
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

    print(f"  Phase III (Name+Flag+Gear Three):")
    print(f"    Word Sorting Keys: {len(groups_key1)} A single combination")
    print(f"    Space button:   {len(groups_key2)} A single combination")
    print(f"    Character Sort Keys: {len(groups_key3)} A single combination")
    print(f"    Number of valid edges:   {nf_edges}")
    print(f"    IMO Conflict prevention: {imo_blocked_phase3} Number of times")
    print(f"  Total number of stops: {total_blocked} (Phase2={imo_blocked_phase2}, Phase3={imo_blocked_phase3})")

    # --- Allocation Cluster ID ---
    cluster_map = {}
    cluster_ids = []
    for i in range(n):
        root = uf.find(i)
        if root not in cluster_map:
            cluster_map[root] = len(cluster_map)
        cluster_ids.append(cluster_map[root])

    df["Vessel_Cluster_ID"] = cluster_ids
    n_clusters = len(cluster_map)

    # Distribution of statistical clusters
    cluster_sizes = df.groupby("Vessel_Cluster_ID").size()
    size_dist = cluster_sizes.value_counts().sort_index()

    print(f"\n  Number of final clusters: {n_clusters} (From {n} Original record)")
    print(f"  The only ship (Cluster Size=1) : {(cluster_sizes==1).sum()}")
    print(f"  Repeat ship (Cluster Size≥2) : {(cluster_sizes>=2).sum()}")
    print(f"  Cluster size distribution: Max={cluster_sizes.max()}, "
          f"Average={cluster_sizes.mean():.1f}")
    print(f"  Details of cluster size distribution:")
    for size, count in size_dist.items():
        if count > 0:
            print(f"    Size={size}: {count} Clusters")

    return df


# =============================================================================
# 5. Cross-filling and braining
# =============================================================================

def impute_and_deduplicate(df: pd.DataFrame, diagnosis: pd.DataFrame = None) -> pd.DataFrame:
    """Resolve duplicate records within each Vessel_Cluster_ID.

    Type C denotes repeated annual registration: retain the most informative
    record when physical characteristics agree. Type B denotes conflicting or
    updated characteristics: use the cluster maxima for GT, kW and length, as
    specified by the reconstruction rule. These maxima are assumed proxies
    for installed capacity, not independently verified vessel measurements.
    Type A denotes identity changes: retain vessel-name history, keep the flag
    of the selected base record, and store previous flags in Flag_History.
    Combined A+B clusters apply both identity and characteristic rules.
    """
    print("\n" + "=" * 70)
    print("  Phase V: Cross-filling and braining")
    print("=" * 70)

    # ---- Construct diagnostic type search table ----
    diag_lookup: dict = {}
    if diagnosis is not None and len(diagnosis) > 0:
        for _, row in diagnosis.iterrows():
            diag_lookup[row["Vessel_Cluster_ID"]] = {
                "type_a": bool(row.get("Type_A_ReFlag", False)),
                "type_b": bool(row.get("Type_B_Modification", False)),
                "type_c": bool(row.get("Type_C_Renewal", False)),
            }

    # ---- Ensure numeric column type ----
    numeric_cols = ["Length", "Tonnage", "Enginepower", "Builtdate"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---- by cluster + Builtdate Sort (The latest is in front of us) ----
    df = df.sort_values(["Vessel_Cluster_ID", "Builtdate"],
                        ascending=[True, False]).reset_index(drop=True)

    # ---- Cross-line Fill: Fill missing values with other records in the same cluster ----
    # Priority to state-of-the-art values (ffill Top down = From New to Old) , And then fill it back with the old values
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
    # The flag is crossed
    df["Flag"] = df.groupby("Vessel_Cluster_ID")["Flag"].transform(
        lambda x: x.mask(x == "nan").ffill().bfill()
    )

    # ---- Calculate information saturation ----
    for col in numeric_cols:
        df[f"_has_{col}"] = (~df[col].isna()).astype(int)
    df["_completeness_score"] = (
        df["_has_Length"] + df["_has_Tonnage"] +
        df["_has_Enginepower"] + df["_has_Builtdate"]
    )

    # ---- Cluster-by-cluster treatment: Generate final records according to diagnostic type ----
    results = []
    clusters_without_diag = 0

    for cid, grp in df.groupby("Vessel_Cluster_ID"):
        diag = diag_lookup.get(cid, None)
        if diag is None:
            clusters_without_diag += 1
            diag = {"type_a": False, "type_b": False, "type_c": False}

        # Select Base Record: The most full information, Same time Builtdate Latest
        best_idx = grp["_completeness_score"].idxmax()
        record = grp.loc[best_idx].to_dict()

        # --- Type B Processing: Conservative principle for maximum value ---
        if diag["type_b"]:
            for col in ["Length", "Tonnage", "Enginepower"]:
                max_val = grp[col].max()
                if pd.notna(max_val):
                    record[col] = max_val
                    unit_col = units.get(col)
                    if unit_col in grp:
                        record[unit_col] = grp.loc[grp[col].idxmax(), unit_col]

        # --- Type A Processing: Merge ship name + Save a new flag history ---
        if diag["type_a"]:
            # Merge the flag: Collect all the different flags (ISO3 Format, deduplication, Go empty) 
            flags = grp["Flag"].dropna()
            flags = flags[flags != ""].unique()
            if len(flags) > 1:
                record["Flag_History"] = "; ".join(sorted(flags))
                # A flag lookup requires one country; keep the selected registry record.
                record["Flag"] = grp.loc[best_idx, "Flag"]
            elif len(flags) == 1:
                record["Flag"] = flags[0]

            # Merge ship name: Only if the three matches are different (A real name change) Only when you merge it
            # If the character sortes the same key → Space only/Word order/Numerical glue format difference, Do Not Merge
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
                # Its actually the same name (Format Differences Only) → Show name for the most fully documented message
                record["Vesselname"] = grp.loc[best_idx, "_name_display"]
                if pd.isna(record["Vesselname"]) or record["Vesselname"] == "":
                    record["Vesselname"] = names[0]

        # --- Organization of marking sources (More RFMO Registration) ---
        source_rfmos = sorted(grp["Source_RFMO"].unique())
        record["Authorized_Oceans"] = "; ".join(source_rfmos)

        results.append(record)

    unified = pd.DataFrame(results)

    # ---- Clear placeholder values ----
    # Some RFMO ♪ In nothing ♪ IMO/Fill placeholder on call sign instead of leaving empty, 
    # These placeholders have been correctly ignored during the matching phase, But its left in the output field, Need to be emptied
    _imo_placeholders = {"PENDING", "NE", "N/A", "UNKNOWN", "0", "0.0"}
    _cs_placeholders = {"(BLANK)", "(N/A)", "NONE", "UNKNOWN", "N.A.", "NONE.",
                        "N.A", "NA", "NIL", "NULL", "TBA", "TBD", "PENDING"}

    for col, placeholder_set in [("IMO", _imo_placeholders), ("Callsign", _cs_placeholders)]:
        if col in unified.columns:
            mask = unified[col].astype(str).str.strip().str.upper().isin(placeholder_set)
            n_cleaned = mask.sum()
            if n_cleaned > 0:
                unified.loc[mask, col] = ""
                print(f"  Placeholders cleanup: {col} Fields Empty {n_cleaned} Placeholder value")

    # ---- Cleanup of auxiliary and non-output columns ----
    drop_cols = [c for c in unified.columns
                 if c.startswith("_has_") or c.startswith("_completeness")]
    unified = unified.drop(columns=drop_cols + [
        "_imo_key", "_cs_key", "_name_key",
        "_name_key_nospace", "_name_key_charsort", "_name_display",
        "_flag_key", "_gear_key", "Source_RFMO",
        "Vessel_Cluster_ID",
    ], errors="ignore")

    # ---- Keep only basic fields (To restate the result has been updated to the field) ----
    extraction_cols = [
        "Vesselname", "IMO", "Callsign", "MMSI",
        "Length", "Tonnage", "Enginepower", "Builtdate",
        "VesselType", "SourceVesselType",
        "LengthType", "TonnageType", "PowerType",
        "Flagcode", "Flag", "Flag_History", "Authorized_Oceans",
    ]
    unified = unified[[c for c in extraction_cols if c in unified.columns]]

    # ---- Statistical Output ----
    n_type_b = sum(1 for r in results if diag_lookup.get(r["Vessel_Cluster_ID"], {}).get("type_b"))
    n_type_a = sum(1 for r in results if diag_lookup.get(r["Vessel_Cluster_ID"], {}).get("type_a"))
    n_type_c = sum(1 for r in results if diag_lookup.get(r["Vessel_Cluster_ID"], {}).get("type_c"))

    print(f"  The only number of ships that are smart enough to get back to the ship: {len(unified)}")
    print(f"  Log compression ratio: {len(df)} → {len(unified)} "
          f"({100*(1-len(unified)/len(df)):.1f}% Compression)")
    print(f"  of which:")
    print(f"    Type A (Change your skin-Merge ship name): {n_type_a}")
    print(f"    Type B (Upgrade-Maximum value): {n_type_b}")
    print(f"    Type C (Fuse your face-Remove Direct): {n_type_c}")
    if clusters_without_diag > 0:
        print(f"    No diagnostic information cluster (Single-record ships) : {clusters_without_diag}")

    return unified


# =============================================================================
# 6. Diagnosis and classification of causes of repetition
# =============================================================================

def diagnose_and_classify_duplicates(df_clustered: pd.DataFrame) -> pd.DataFrame:
    """
    Duplicate records for each occurrence (Cluster Size ≥2) of Vessel_Cluster_ID Diagnostic classification. 

    Classification rules: 
      Variation A (Change your skin) : Flag or Vesselname Differences within clusters
      Variation B (Upgrade) : kW Change >5% or GT Change
      Variation C (Fuse your face) : All physical parameters in the cluster (Flag, kW, GT, Length) Unanimously, 
                      Annual administrative renewal only

    attention: A and B We can live together (The same ship is reflagging and upgrading) 
    """
    print("\n" + "=" * 70)
    print("  Phase IV: Diagnosis and classification of causes of repetition")
    print("=" * 70)

    # Analysis of duplicate clusters only
    cluster_counts = df_clustered.groupby("Vessel_Cluster_ID").size()
    multi_record_clusters = cluster_counts[cluster_counts >= 2].index
    df_multi = df_clustered[df_clustered["Vessel_Cluster_ID"].isin(multi_record_clusters)].copy()

    if len(df_multi) == 0:
        print("  No duplicates, Skip the diagnosis. ")
        return pd.DataFrame(columns=["Vessel_Cluster_ID", "Type_A_ReFlag",
                                      "Type_B_Modification", "Type_C_Renewal",
                                      "Record_Count", "Notes"])

    # Ensure value columns
    for col in ["Enginepower", "Tonnage", "Length", "Builtdate"]:
        df_multi[col] = pd.to_numeric(df_multi[col], errors="coerce")

    # --- Aggregation of each cluster ---
    diag_parts = []

    for cid, grp in df_multi.groupby("Vessel_Cluster_ID"):
        n_records = len(grp)

        # Collection of Valid Values
        flags = set(grp["_flag_key"].dropna().replace({"": np.nan}).dropna().unique())
        # Synchronising folder (Keep Spaces and Original Words Order) 
        names_display = set(grp["_name_display"].dropna().replace({"": np.nan}).dropna().unique())
        # Three matches: Sorting Words, Just go to space, Character Sorting
        names_match = set(grp["_name_key"].dropna().replace({"": np.nan}).dropna().unique())
        names_nospace = set(grp["_name_key_nospace"].dropna().replace({"": np.nan}).dropna().unique())
        names_charsort = set(grp["_name_key_charsort"].dropna().replace({"": np.nan}).dropna().unique())
        # A real name change = All three keys are different. 
        # If the character sortes the same key → Space only/Word order/Numerical glue format difference
        #    (Like DONG WON NO 203 ↔ NO203 DONGWON → Character set is identical) 
        # If the word sorting key is the same → Space differences only
        # If you go to the space button, its the same → Only word-order differences

        kw_vals = grp["Enginepower"].dropna()
        gt_vals = grp["Tonnage"].dropna()
        len_vals = grp["Length"].dropna()

        # --- Variation A: Change your skin ---
        # A real name change = Theres a difference between the two matches
        # If the word sorting key is the same → Only word-order differences (Like DONG WON NO 211 ↔ NO211 DONG WON) 
        # If you go to the space button, its the same   → Space differences only (Like GUANG YUAN YU 331 ↔ GUANGYUANYU331) 
        # The difference between the two keys is the real change of name (Like CHOKYU MARU NO.21 ↔ CHOKYU MARU) 
        name_changed = (len(names_match) > 1) and (len(names_nospace) > 1) and (len(names_charsort) > 1)
        type_a = False
        a_details = []
        if len(flags) > 1:
            type_a = True
            a_details.append(f"Flag Change: {sorted(flags)}")
        if name_changed:
            type_a = True
            a_details.append(f"Change of name of ship: {sorted(names_display)}")

        # --- Variation B: Upgrade ---
        type_b = False
        b_details = []
        if len(kw_vals) >= 2:
            kw_range = (kw_vals.min(), kw_vals.max())
            if kw_vals.max() > 0:
                kw_pct = (kw_vals.max() - kw_vals.min()) / kw_vals.max()
                if kw_pct > 0.05:
                    type_b = True
                    b_details.append(f"kW Change: {kw_range[0]:.1f}→{kw_range[1]:.1f} "
                                     f"({100*kw_pct:.1f}%)")

        if len(gt_vals) >= 2:
            gt_range = (gt_vals.min(), gt_vals.max())
            if gt_vals.max() != gt_vals.min():
                type_b = True
                b_details.append(f"GT Change: {gt_range[0]:.1f}→{gt_range[1]:.1f}")

        # --- Variation C: Fuse your face ---
        # ♪ Neither is it ♪ A Not really B Hour, Deciding that C
        type_c = (not type_a) and (not type_b)

        # --- Combining diagnostic records ---
        details = []
        if type_a:
            details.append(f"[A-Change your skin] {'; '.join(a_details)}")
        if type_b:
            details.append(f"[B-Upgrade] {'; '.join(b_details)}")
        if type_c:
            details.append(f"[C-Fuse your face] Parameters are consistent, Annual renewal only")

        # Access to representative IMO And the name of the ship
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

    # --- Output statistics ---
    n_total_dup = len(diagnosis)
    n_type_a = diagnosis["Type_A_ReFlag"].sum()
    n_type_b = diagnosis["Type_B_Modification"].sum()
    n_type_c = diagnosis["Type_C_Renewal"].sum()
    n_a_and_b = ((diagnosis["Type_A_ReFlag"]) & (diagnosis["Type_B_Modification"])).sum()

    print(f"  Total number of repeat clusters: {n_total_dup}")
    print(f"  Total records involved: {diagnosis['Record_Count'].sum()}")
    print(f"")
    print(f"  Variation A (Change your skin - Re-flagging/Change of name): {n_type_a} ({100*n_type_a/n_total_dup:.1f}%)")
    print(f"  Variation B (Upgrade - power/Tonne change): {n_type_b} ({100*n_type_b/n_total_dup:.1f}%)")
    print(f"  Variation C (Fuse your face - Pure annual renewal): {n_type_c} ({100*n_type_c/n_total_dup:.1f}%)")
    print(f"  of which A+B Coexistence: {n_a_and_b} ({100*n_a_and_b/n_total_dup:.1f}%)")

    # Cluster size distribution
    size_dist = diagnosis["Record_Count"].value_counts().sort_index()
    print(f"\n  Repeat Cluster Size Distribution:")
    for size, count in size_dist.items():
        print(f"    Size={size}: {count} Clusters ({100*count/n_total_dup:.1f}%)")

    return diagnosis


# =============================================================================
# 7. Main entrance
# =============================================================================

def main():
    print("=" * 70)
    print("  Global tuna ship asset register — Deep Purge and Restructure")
    print("  Vessel Deduplication Pipeline")
    print("=" * 70)

    # ---- Phase I: Loading data ----
    df = load_data()

    # ---- Phase II: String pre-processing ----
    df = preprocess_strings(df)

    # ---- Phase III: Cascade Matches (Union-Find) ----
    df = build_vessel_graph(df)

    # ---- Phase IV: Diagnosis of repeated causes (Diagnosis before filling, Retain original differences) ----
    diagnosis = diagnose_and_classify_duplicates(df)

    # ---- Phase V: Cross-filling and braining (Disaggregated strategy according to type of diagnosis) ----
    unified = impute_and_deduplicate(df, diagnosis)

    # ---- Phase VI: Output of outcome documents ----
    print("\n" + "=" * 70)
    print("  Phase VI: Output of outcome documents")
    print("=" * 70)

    # Uniform registry (Only those that are consistent with the extraction documents are retained 15 Basic Fields) 
    unified.to_csv(OUTPUT_REGISTRY, index=False, encoding="utf-8-sig")
    print(f"  Harmonization of the Register of Ships: {OUTPUT_REGISTRY}")
    print(f"    Total {len(unified)} The only ship")
    print(f"    Fields: {list(unified.columns)}")

    # Diagnosis report (Separate Files, Not merged into the Register) 
    if len(diagnosis) > 0:
        diagnosis.to_csv(OUTPUT_DIAGNOSIS, index=False, encoding="utf-8-sig")
        print(f"  Duplicate diagnostic reports: {OUTPUT_DIAGNOSIS}")
        print(f"    Total {len(diagnosis)} Repeat clusters")

    # ---- Final summary ----
    print("\n" + "=" * 70)
    print("  Were done with the pipe — Summary")
    print("=" * 70)
    print(f"  Original records: {len(df)}")
    print(f"  The only ship: {len(unified)}")
    print(f"  Compression Rate: {100*(1-len(unified)/len(df)):.1f}%")
    print()

    return unified, diagnosis


if __name__ == "__main__":
    # Windows Console Encoded
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    unified, diagnosis = main()
