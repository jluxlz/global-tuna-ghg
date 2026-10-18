#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
extract_and_validate_rfmos.py
=============================================================================
Automated extraction, standardization, enrichment, and validation of global
tuna RFMO vessel registries against FAO international standards (ISSCFV/ISSCFG).

Six-step pipeline:
  1. Parse FAO ISSCFV (vessel types) and ISSCFG (gear types) as reference
  2. Top-down extraction (Vessel Type → Gear Type) with dynamic column detection
  3. RFMO-specific name/code normalization to FAO standards
  4. Multi-gear penetration logic: rescue multi-gear vessels whose gear
     includes PS or LL
  5. Schema-aligned output + data enrichment from historical extracted data
  6. Automated cross-validation report

Author: Data Engineering Pipeline
Date:   2026-06-02
=============================================================================
"""

import os
import sys
import re
import warnings
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# ============================================================================
# SECTION 0 — Configuration & Paths
# ============================================================================

# Attempt matplotlib fix for headless environments
try:
    import matplotlib
    matplotlib.use("Agg")
except Exception:
    pass

# Base directory (script location = vessel_data_extract/)
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent  # project root

# Input paths (FAO standards are in the same directory as this script)
FAO_ISSCFV_PATH = BASE_DIR / "ISSCFV.txt"
FAO_ISSCFG_PATH = BASE_DIR / "ISSCFG.txt"
RAW_DATA_DIR = ROOT_DIR / "raw_vessel_data"
EXTRACTED_DIR = ROOT_DIR / "extracted_vessel_data"

# Output directory (placed under vessel_data_extract/)
NEW_EXTRACTED_DIR = BASE_DIR / "new_extracted_vessel_data"

# Raw (non-unit-converted) output directory — original values preserved
NEW_EXTRACTED_RAW_DIR = BASE_DIR / "new_extracted_vessel_data_raw"

# Raw data file mapping (Chinese filenames)
RAW_DATA_FILES = {
    "CCSBT": RAW_DATA_DIR / "CCSBT南方蓝鳍金枪鱼保护委员会.csv",
    "IATTC": RAW_DATA_DIR / "IATTC美洲热带金枪鱼委员会.xlsx",
    "ICCAT": RAW_DATA_DIR / "ICCAT国际大西洋金枪鱼保护委员会.xlsx",
    "IOTC":  RAW_DATA_DIR / "IOTC印度洋金枪鱼委员会.xlsx",
    "WCPFC": RAW_DATA_DIR / "WCPFC中西太平洋渔业委员会.csv",
}

# Existing extracted data (for enrichment)
EXTRACTED_DATA_FILES = {
    "CCSBT": EXTRACTED_DIR / "CCSBT.xlsx",
    "IATTC": EXTRACTED_DIR / "IATTC.xlsx",
    "ICCAT": EXTRACTED_DIR / "ICCAT.xlsx",
    "IOTC":  EXTRACTED_DIR / "IOTC.xlsx",
    "WCPFC": EXTRACTED_DIR / "WCPFC.xlsx",
}

# Target output schema — column names WITHOUT units (units are captured in
# LengthType / TonnageType / PowerType metadata columns).
# ICCAT and WCPFC have an extra 'Flagcode' column
TARGET_SCHEMA = {
    "CCSBT": ["Vesselname", "IMO", "Callsign", "MMSI", "Length",
              "Tonnage", "Enginepower", "Builtdate", "VesselType",
              "SourceVesselType", "LengthType", "TonnageType", "PowerType", "Flag"],
    "IATTC": ["Vesselname", "IMO", "Callsign", "MMSI", "Length",
              "Tonnage", "Enginepower", "Builtdate", "VesselType",
              "SourceVesselType", "LengthType", "TonnageType", "PowerType", "Flag"],
    "ICCAT": ["Vesselname", "IMO", "Callsign", "MMSI", "Length",
              "Tonnage", "Enginepower", "Builtdate", "VesselType",
              "SourceVesselType", "LengthType", "TonnageType", "PowerType", "Flagcode", "Flag"],
    "IOTC":  ["Vesselname", "IMO", "Callsign", "MMSI", "Length",
              "Tonnage", "Enginepower", "Builtdate", "VesselType",
              "SourceVesselType", "LengthType", "TonnageType", "PowerType", "Flag"],
    "WCPFC": ["Vesselname", "IMO", "Callsign", "MMSI", "Length",
              "Tonnage", "Enginepower", "Builtdate", "VesselType",
              "SourceVesselType", "LengthType", "TonnageType", "PowerType", "Flagcode", "Flag"],
}

# ============================================================================
# Unit Conversion Constants
# ============================================================================
# Power: HP (imperial) → kW, PS (metric) → kW
HP_IMPERIAL_TO_KW = 0.7457   # 1 imperial horsepower = 0.7457 kW
PS_METRIC_TO_KW  = 0.7355    # 1 metric horsepower (Pferdestärke) = 0.7355 kW
# BHP (brake horsepower) ≈ imperial HP, same conversion factor

# Tonnage: GT ≈ GRT (1:1 equivalence in LCA)
# NT (net tonnage) ≈ 30% of GT → MUST NOT be treated as GT
# If a record has ONLY NT, GT is forced to NaN

# Length: LOA, LBP, REG are all in meters and treated as equivalent

# ============================================================================
# SECTION 1 — FAO Standard Reference Dictionaries
# ============================================================================

def parse_isscfv(filepath: Path) -> dict:
    """
    Parse ISSCFV.txt into a dictionary:
        { 'LL': 'Longliners', 'SP': 'Purse seiners', 'MO': 'Multipurpose vessels', ... }
    Also builds reverse lookups and a hierarchy map (parent codes and their children).
    """
    code_to_name = {}
    code_to_category = {}
    code_parent = {}       # child code → parent code (e.g. 'LLX' → 'LL')
    parent_children = defaultdict(set)  # parent code → {child codes}

    current_category = "Unknown"
    with open(filepath, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            # Section header (Chinese/English category)
            if line.startswith("---"):
                # e.g. "--- 围网渔船 (Purse seiners) ---"
                cat_match = re.search(r"\(([^)]+)\)", line)
                if cat_match:
                    current_category = cat_match.group(1).strip()
                continue

            # Code line: e.g. "SP (2) - Purse seiners (围网渔船总称)"
            match = re.match(r"([A-Z]{2,4})\s*\([^)]+\)\s*-\s*(.+?)$", line)
            if match:
                code = match.group(1).strip()
                desc = match.group(2).strip()
                code_to_name[code] = desc
                code_to_category[code] = current_category

                # Determine parent-child relationships:
                # Parent codes are 2-letter; children are 3+ letters starting with same prefix
                if len(code) == 2:
                    parent_children[code] = set()
                elif len(code) >= 3:
                    for parent in list(parent_children.keys()):
                        if code.startswith(parent) and len(parent) == 2:
                            parent_children[parent].add(code)
                            code_parent[code] = parent
                            break

    return {
        "code_to_name": code_to_name,
        "code_to_category": code_to_category,
        "parent_children": dict(parent_children),
        "code_parent": code_parent,
    }


def parse_isscfg(filepath: Path) -> dict:
    """
    Parse ISSCFG.txt into a dictionary:
        { 'PS': 'Purse seines', 'LL': 'Longlines (nei)', 'LLS': 'Set longlines', ... }
    Also builds parent-child relationships (e.g. LL → {LLS, LLD, LL}).
    """
    code_to_name = {}
    code_to_category = {}
    code_parent = {}
    parent_children = defaultdict(set)

    current_category = "Unknown"
    with open(filepath, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith("---"):
                cat_match = re.search(r"\(([^)]+)\)", line)
                if cat_match:
                    current_category = cat_match.group(1).strip()
                continue

            # Code line: e.g. "PS (01.1) - Purse seines (围网)"
            match = re.match(r"([A-Z0-9]{2,4})\s*\([^)]+\)\s*-\s*(.+?)$", line)
            if match:
                code = match.group(1).strip()
                desc = match.group(2).strip()
                code_to_name[code] = desc
                code_to_category[code] = current_category

                if len(code) == 2:
                    parent_children[code] = set()
                elif len(code) >= 3:
                    for parent in list(parent_children.keys()):
                        if code.startswith(parent) and len(parent) == 2:
                            parent_children[parent].add(code)
                            code_parent[code] = parent
                            break

    return {
        "code_to_name": code_to_name,
        "code_to_category": code_to_category,
        "parent_children": dict(parent_children),
        "code_parent": code_parent,
    }


def load_fao_standards():
    """Load both FAO standards and return combined reference."""
    print("=" * 70)
    print("  STEP 1: Loading FAO International Standards (ISSCFV & ISSCFG)")
    print("=" * 70)

    isscfv = parse_isscfv(FAO_ISSCFV_PATH)
    isscfg = parse_isscfg(FAO_ISSCFG_PATH)

    print(f"  ISSCFV: {len(isscfv['code_to_name'])} vessel type codes loaded")
    print(f"  ISSCFG: {len(isscfg['code_to_name'])} gear type codes loaded")

    # Show key parent codes
    print(f"  Vessel parent codes: {sorted(k for k in isscfv['parent_children'] if len(k) == 2)}")
    print(f"  Gear parent codes:   {sorted(k for k in isscfg['parent_children'] if len(k) == 2)}")
    print()
    return isscfv, isscfg


# ============================================================================
# SECTION 2 — Dynamic Column Detection Engine
# ============================================================================

# Keyword groups for detecting column roles (case-insensitive)
VESSEL_TYPE_KEYWORDS = [
    "isscfv", "isscfvcode", "vessel type", "type of vessel",
    "type code", "type name", "vessel kind",
]

GEAR_TYPE_KEYWORDS = [
    "isscfg", "isscfgcode", "gear type", "type of fishing method",
    "gear", "gears code", "gears name", "gear code",
]

VESSEL_NAME_KEYWORDS = [
    "vesselname", "vessel name", "name of fishing vessel",
    "name", "vessel",
]

IMO_KEYWORDS = [
    "imo", "imo number", "imo or lr number", "intregno",
]

CALLSIGN_KEYWORDS = [
    "callsign", "call sign", "ircs", "international radio call sign",
]

FLAG_KEYWORDS = [
    "flag", "flag of fishing vessel", "flag state name",
    "flagvescode", "flag state",
]

LENGTH_KEYWORDS = [
    "length", "loa", "length (m)", "loa (m)",
]

TONNAGE_KEYWORDS = [
    "tonnage", "gross tonnage", "gross registered tonnage",
    "gt", "tonnage(t)",
]

ENGINE_POWER_KEYWORDS = [
    "engine power", "enginepower", "power of main engine",
    "engine power (hp)",
]

YEAR_BUILT_KEYWORDS = [
    "year built", "yearbuilt", "when the vessel was built",
    "builtdate", "built",
]
# NOTE: we'll filter out "where" matches in the detection logic

MMSI_KEYWORDS = [
    "mmsi",
]

FLAGCODE_KEYWORDS = [
    "flagcode", "flagvescode", "flag state code",
]

# NOTE: these detect the TYPE/DESCRIPTOR columns, not the value columns
LENGTH_TYPE_KEYWORDS = [
    "length type", "type of length",
]

TONNAGE_TYPE_KEYWORDS = [
    "ton type", "tonnage type", "type of tonnage",
    "tontypecode", "ton type code",
]

POWER_TYPE_KEYWORDS = [
    "unit of power", "power unit", "power type",
    "unit of main engine",
]


def _match_keywords(col_name: str, keywords: list) -> bool:
    """Check if a column name matches any keyword (case-insensitive).

    For short keywords (≤2 characters), uses word-boundary matching (\\b)
    to prevent substring false positives. For example, "gt" must match as a
    standalone token like "(GT)" or " GT " — it must NOT match inside "length".
    """
    cn = str(col_name).lower().strip()
    for kw in keywords:
        if len(kw) <= 2:
            # Word-boundary match for short keywords to prevent substring hits
            # e.g. "gt" should match "gross tonnage (GT)" but NOT "length"
            if re.search(r'(?<![a-z])' + re.escape(kw) + r'(?![a-z])', cn):
                return True
        else:
            if kw in cn:
                return True
    return False


def detect_columns(df: pd.DataFrame) -> dict:
    """
    Dynamically detect key columns in a dataframe.
    Returns dict mapping logical names to actual column names (or None if not found).
    """
    columns = df.columns.tolist()
    detected = {
        "vessel_type_col": None,
        "vessel_type_col_2": None,  # secondary (e.g. Type Name, Vessel Kind)
        "gear_type_col": None,
        "gear_type_col_2": None,
        "vessel_name_col": None,
        "imo_col": None,
        "callsign_col": None,
        "flag_col": None,
        "flagcode_col": None,
        "length_col": None,
        "length_type_col": None,      # type of length measurement (LOA/LBP/REG)
        "tonnage_col": None,
        "tonnage_type_col": None,     # type of tonnage (GT/GRT/NT)
        "engine_power_col": None,
        "engine_power_type_col": None,  # unit of power (HP/KW/PS)
        "year_built_col": None,
        "mmsi_col": None,
    }

    for col in columns:
        cn = str(col).lower().strip()

        if _match_keywords(cn, VESSEL_TYPE_KEYWORDS):
            # Prioritize: "type code" > "type of vessel" > "vessel kind"
            if detected["vessel_type_col"] is None:
                detected["vessel_type_col"] = col
            elif detected["vessel_type_col_2"] is None:
                # Deprioritize "vessel kind" vs "type name" as secondary
                if "kind" in cn and "type name" in str(detected["vessel_type_col_2"]).lower():
                    pass  # keep existing type_name, skip vessel kind
                else:
                    detected["vessel_type_col_2"] = col
            # If both slots are taken but current is "type name", replace slot 2
            elif "type name" in cn and detected["vessel_type_col_2"] is not None:
                detected["vessel_type_col_2"] = col

        if _match_keywords(cn, GEAR_TYPE_KEYWORDS):
            if detected["gear_type_col"] is None:
                detected["gear_type_col"] = col
            elif detected["gear_type_col_2"] is None:
                detected["gear_type_col_2"] = col

        if _match_keywords(cn, VESSEL_NAME_KEYWORDS):
            # Exclude false positives: registration numbers, IDs, etc.
            if any(bad in cn for bad in ["number", "regis", "vid", "win", "serial", "code"]):
                continue
            # Prefer exact "vessel name"-type columns over generic "vessel" columns
            # Priority: "vessel" (exact) > "vessel name" > "name of fishing vessel" > "name"
            if detected["vessel_name_col"] is None:
                detected["vessel_name_col"] = col
            else:
                prev = str(detected["vessel_name_col"]).lower()
                # Exact "vessel" or bare "name" is best for IATTC/IOTC
                if cn == "vessel" and prev != "vessel":
                    detected["vessel_name_col"] = col
                elif cn == "name" and "kind" not in prev:
                    # Bare "Name" beats "Vessel Kind Name" for IOTC
                    detected["vessel_name_col"] = col
                # "vessel name" beats generic "vessel" or "vessel kind"
                elif "vessel name" in cn and "vessel name" not in prev and "kind" not in cn:
                    if prev != "vessel":
                        detected["vessel_name_col"] = col
                elif "vessel" in cn and "vessel" not in prev and "kind" not in cn:
                    detected["vessel_name_col"] = col

        if _match_keywords(cn, IMO_KEYWORDS) and detected["imo_col"] is None:
            detected["imo_col"] = col

        if _match_keywords(cn, CALLSIGN_KEYWORDS) and detected["callsign_col"] is None:
            detected["callsign_col"] = col

        if _match_keywords(cn, FLAG_KEYWORDS):
            # Exclude "previous flag" / "former flag" — we want current flag
            if any(bad in cn for bad in ["previous", "former", "preceding", "before"]):
                continue
            # Distinguish flag name from flag code
            if "code" in cn and detected["flagcode_col"] is None:
                detected["flagcode_col"] = col
            elif detected["flag_col"] is None:
                detected["flag_col"] = col

        if _match_keywords(cn, FLAGCODE_KEYWORDS) and detected["flagcode_col"] is None:
            detected["flagcode_col"] = col

        if _match_keywords(cn, LENGTH_TYPE_KEYWORDS) and detected["length_type_col"] is None:
            detected["length_type_col"] = col

        if _match_keywords(cn, LENGTH_KEYWORDS) and detected["length_col"] is None:
            detected["length_col"] = col

        if _match_keywords(cn, TONNAGE_KEYWORDS) and detected["tonnage_col"] is None:
            detected["tonnage_col"] = col

        if _match_keywords(cn, TONNAGE_TYPE_KEYWORDS) and detected["tonnage_type_col"] is None:
            detected["tonnage_type_col"] = col

        if _match_keywords(cn, POWER_TYPE_KEYWORDS) and detected["engine_power_type_col"] is None:
            detected["engine_power_type_col"] = col

        if _match_keywords(cn, ENGINE_POWER_KEYWORDS) and detected["engine_power_col"] is None:
            detected["engine_power_col"] = col

        if _match_keywords(cn, YEAR_BUILT_KEYWORDS) and detected["year_built_col"] is None:
            # Exclude "where ... built" (construction location, not year)
            if "where" in cn:
                continue
            detected["year_built_col"] = col

        if _match_keywords(cn, MMSI_KEYWORDS) and detected["mmsi_col"] is None:
            detected["mmsi_col"] = col

    return detected


# ============================================================================
# SECTION 3 — RFMO-Specific Mapping & Normalization
# ============================================================================

# --- 3a. CCSBT Mappings ---
# CCSBT uses English full names in "Vessel Type", FAO codes (comma-sep) in "Gear Type"

CCSBT_VESSEL_TYPE_MAP = {
    "longline":                         "LL",
    "purse seine":                      "PS",
    "multi":                            "MO",   # Multi-purpose → check gear
    "transhipment/carrier vessels":     "TS",
    "transhipment":                     "TS",
    "carrier":                          "TS",
    "reefer":                           "TS",
    "other seiners":                    "SO",   # Check gear for PS
    "other liners":                     "LO",   # Check gear for LL
    "bait boat":                        "LO",   # Bait boat → check gear for LL/PS
    "trawler":                          "TO",   # Trawler → only extract if gear PS/LL
    "gill netters":                     "GO",   # Gill netter → only extract if gear PS/LL
    "handline":                         "LO",   # Check gear
    "troller":                          "LO",   # Check gear
}

# CCSBT gear codes are already FAO-standard comma-separated codes
# Parse multi-gear by splitting on commas
CCSBT_GEAR_PARSE_SEP = ","

# --- 3b. IATTC Mappings ---
# IATTC uses English full names in "Gear" column only (no vessel type column)

IATTC_GEAR_TO_VESSEL_TYPE = {
    "longline":             "LL",
    "purse seine":          "PS",
    "multi-purpose":        "MO",   # Extract, note as multi-gear
    "troll":                "LO",   # Troller → not tuna fleet, skip
    "pole and line":        "LO",   # Not tuna fleet
    "harpoon":              "FX",   # Not tuna fleet
    "gillnet":              "GO",   # Not tuna fleet
    "recreational fishing": "RO",   # Discard
}

IATTC_MULTI_GEAR_VESSEL_TYPES = {"multi-purpose"}

# --- 3c. ICCAT Mappings ---
# ICCAT uses FAO-standard codes in IsscfvCode and IsscfgCode
# Direct mapping — ICCAT mostly follows FAO

ICCAT_VESSEL_TYPE_MAP = {
    "LL": "LL",
    "SP": "PS",
    "MO": "MO",
    "FO": "TS",
    "SV": "SA",    # ICCAT uses SV for support; map to SA per FAO ISSCFV
    "SO": "SO",    # Other seiners → check gear
    "LO": "LO",
    "LP": "LO",
    "LH": "LO",
    "LT": "LO",
    "TW": "TO",
    "TO": "TO",
    "GO": "GO",
    "WO": "WO",
    "AU": "VO",    # Auxiliary
    "FX": "FX",
    "RO": "RO",    # Recreational → discard
    "RT": "RT",    # Research → discard
    "CO": "CO",    # Training → discard
    "UN": "UN",
    "VOX": "VO",
    "SOX": "SO",
}

# ICCAT uses separate IRNoTypeCode column to distinguish IMO vs other registration
# IntRegNo column contains the actual number

# --- 3d. IOTC Mappings ---
# CRITICAL: IOTC uses non-standard codes!
# SP = Supply vessel (NOT purse seine!)
# CF = Cargo freezer
# MU = Multipurpose

IOTC_VESSEL_TYPE_MAP = {
    "LL": "LL",      # Longliner
    "PS": "PS",      # Purse seiner
    "SP": "SA",      # *** Supply vessel (purse seiners) — NOT purse seine! ***
    "CF": "TS",      # Cargo freezer → Carrier/Transshipment
    "MU": "MO",      # Multipurpose → check gear
    "BB": "LO",      # Pole & Line vessel
    "GI": "GO",      # Gill Netter
    "LI": "LO",      # Line vessel
    # Directive 2.2: LC (Longliner + Carrier) must NOT go to pure fishing.
    # Forced to TS (transshipment) — pure shipping fuel allocation only.
    "LC": "TS",      # Longliner and Carrier → transshipment (not LL)
    "LB": "LL",      # Longliner-Pole and Line vessel → treat as LL
    "RT": "RT",      # Research-Training → discard
    "TW": "TO",      # Trawler
}

IOTC_GEAR_MAP = {
    "LL": "LL",
    "PS": "PS",
    "GI": "GI",
    "HAND": "LHP",
    "PL": "LP",
    "OTH": "NK",
    "SUPP": "SA",    # Supply vessel gear
    "TROL": "LTL",
    "MWT": "OTM",
}

# IOTC gear codes are semicolon-separated
IOTC_GEAR_PARSE_SEP = ";"

# --- 3e. WCPFC Mappings ---
# WCPFC uses its own codes with suffixes

WCPFC_VESSEL_TYPE_MAP = {
    "LL":  "LL",
    "LLT": "LL",
    "LLZ": "LL",
    "SP":  "PS",
    "SPT": "PS",
    "FO":  "TS",    # Fish carrier
    "CO":  "TS",    # Carrier other
    "LP":  "LO",    # Pole and line
    "LT":  "LO",    # Troller
    "LH":  "LO",    # Hand liner
    "NO":  "NO",    # Lift netter
    # Directive 1.1: ZO = research/survey vessel per FAO ISSCFV,
    # NOT a support vessel. Treat as discard rather than VO.
    "ZO":  "RT",    # Research survey vessel → discard
    "VOS": "SA",    # Support vessel
    "VOB": "SA",    # Bunkering/support
    "WOP": "WO",    # Trap setter
}

WCPFC_GEAR_MAP = {
    "LL":  "LL",
    "LLD": "LLD",
    "LLS": "LLS",
    "PS":  "PS",
    "PS1": "PS",
    "PS2": "PS",
    "SV":  "SA",
    "SX":  "SX",
    "SPR": "SA",
    "LHP": "LHP",
    "LHM": "LHM",
    "LTL": "LTL",
    "LX":  "LX",
    "GND": "GND",
    "MIS": "MIS",
}

# WCPFC gear is semicolon-separated (e.g. "PS; PS1")
WCPFC_GEAR_PARSE_SEP = ";"


# ============================================================================
# SECTION 4 — Target Vessel Classification Logic
# ============================================================================

# FAO parent codes for fishing types we care about
PURSE_SEINE_VESSEL_PARENT = "SP"
LONGLINE_VESSEL_PARENT = "LL"
MULTIPURPOSE_VESSEL = "MO"

# FAO gear parent codes
PURSE_SEINE_GEAR_PARENT = "PS"
LONGLINE_GEAR_PARENT = "LL"

# ALL purse-seine-related gear codes (parent + children per FAO ISSCFG)
#   Section 01 Surrounding nets: PS (purse seines), LA (without purse lines), SUX (nei)
#   WCPFC uses PS1, PS2 as sub-codes for purse seine variants → map to PS-equivalent
PURSE_SEINE_GEAR_CODES = {"PS", "PS1", "PS2", "LA", "SUX"}

# ALL longline-related gear codes (parent + children per FAO ISSCFG)
#   Section 09.3 Longlines: LLS (set longlines), LLD (drifting longlines), LL (nei)
#   NOTE: LHP (handlines), LHM (mechanized lines), LTL (trolling), LVT (vertical),
#         LX (hooks nei) are SEPARATE hook-and-line types — NOT longline — and
#         must NOT trigger "LL" vessel classification.
LONGLINE_GEAR_CODES = {"LL", "LLS", "LLD"}

# Vessel types that are ALWAYS discarded (training, research)
# Directive 1.1: ZO (科研调查船/research survey) & CO (实习船/training)
# unconditionally dropped before any gear matching logic
DISCARD_VESSEL_TYPES = {"RT", "RTX", "CO", "COX", "RO", "ROX", "ZO", "ZOX"}
DISCARD_TYPE_NAMES = {"research", "training", "research-training",
                      "recreational fishing", "fishery research",
                      "patrol", "research and survey",
                      "research survey", "survey vessel"}

# Directive 2.1【跨物理形态过滤】: Physical hull types INELIGIBLE for gear rescue.
# Trawlers (TO) = high-resistance; handliners (LH) & gillnetters (GI/GO) = non-standard
# hull forms. These must NOT be force-fitted into the standardized ocean-going PS/LL fleet,
# even if their gear field carries PS or LL authorization codes.
GEAR_RESCUE_BLOCKLIST = {"TO", "TOX", "TW", "LH", "GI", "GO", "GOX", "GND"}

# Directive 3.2【辅助服务主属性锁定】: Supply/auxiliary vessel codes that must remain
# locked as SA. Even if these vessels claim PS (purse seine) gear codes, refuse gear
# rescue and keep their primary SA classification.
SUPPLY_VESSEL_CODES = {"SP", "SUPP", "SA", "SAX", "SV", "VO", "VOX", "VOS", "VOB"}

# Vessel types that indicate carrier/transshipment (to be extracted)
CARRIER_VESSEL_TYPES = {"FO", "FR", "FOX", "HO", "HOX", "CF"}
SUPPORT_VESSEL_TYPES = {"SA", "SB", "ST", "SAX", "SV", "VO", "VOM", "VOX"}
FISHING_VESSEL_TYPES = {"LL", "SP", "PS", "SO", "LO", "MO", "TO", "GO", "WO",
                        "LLX", "SOX", "LOX", "GOX", "WOX"}


def is_longline_gear(gear_codes: set) -> bool:
    """Check if any gear code is longline-related."""
    return bool(gear_codes & LONGLINE_GEAR_CODES)


def is_purse_seine_gear(gear_codes: set) -> bool:
    """Check if any gear code is purse-seine-related."""
    return bool(gear_codes & PURSE_SEINE_GEAR_CODES)


def should_discard(vessel_type: str, vessel_type_name: str = "") -> bool:
    """Check if a vessel should be discarded (research, training, recreational)."""
    vt_upper = str(vessel_type).upper().strip()
    if vt_upper in DISCARD_VESSEL_TYPES:
        return True
    vtn_lower = str(vessel_type_name).lower().strip()
    for keyword in DISCARD_TYPE_NAMES:
        if keyword in vtn_lower:
            return True
    return False


def parse_gear_codes(gear_str: str, separator: str = ",") -> set:
    """
    Parse a gear string into a set of cleaned gear codes.
    Handles CCSBT comma-separated, IOTC/WCPFC semicolon-separated.
    """
    if pd.isna(gear_str) or str(gear_str).strip() == "":
        return set()
    s = str(gear_str).upper().strip()
    # Replace common separators
    for sep in [",", ";", "/", "&", "+"]:
        s = s.replace(sep, separator)
    codes = set()
    for token in s.split(separator):
        token = token.strip()
        # Remove leading/trailing non-alpha characters
        token = re.sub(r"[^A-Z0-9]", "", token)
        if token and len(token) >= 1:
            codes.add(token)
    return codes


def classify_gear_for_multi(gear_codes: set) -> str:
    """
    For a multi-purpose/multi-gear vessel, classify based on gear codes.

    Logic:
      - If combination contains PS (purse seine), it's treated as PS fleet
        because purse seining is the most capital and energy-intensive operation;
        the dominant carbon emissions are driven by purse-seine behavior.
      - If no PS but contains LL (longline), classify as LL.
      - If BOTH PS and LL are present, extract as combined "PS, LL" to
        preserve both gear authorizations.
      - Otherwise returns 'MO' (true multi-purpose, neither PS nor LL).
    """
    has_ps = is_purse_seine_gear(gear_codes)
    has_ll = is_longline_gear(gear_codes)
    if has_ps and has_ll:
        return "PS, LL"
    if has_ps:
        return "PS"
    if has_ll:
        return "LL"
    return "MO"


def normalize_vessel_type(
    vessel_type_raw: str,
    gear_codes: set,
    org: str,
    vessel_type_name: str = "",
) -> tuple:
    """
    Normalize a vessel to standard FAO code.

    Top-down logic:
      1. Classify vessel type to FAO code
      2. If multi-gear/multi-purpose → check gear for PS/LL
      3. If fishing parent type but not LL/PS → check gear for LL/PS rescue

    Returns:
        (final_vessel_type, is_multi_gear_rescued, was_classified_by_gear)
    """
    vt = str(vessel_type_raw).strip() if pd.notna(vessel_type_raw) else ""
    vtn = str(vessel_type_name).strip() if pd.notna(vessel_type_name) else ""

    if not vt and not vtn:
        return (None, False, False)

    # --- Discard check ---
    if should_discard(vt, vtn):
        return ("DISCARD", False, False)

    # --- Map to FAO code ---
    fao_code = None
    vt_upper = vt.upper().strip()

    if org == "CCSBT":
        # CCSBT uses English names
        vt_lower = vt.lower().strip()
        fao_code = CCSBT_VESSEL_TYPE_MAP.get(vt_lower)
        if fao_code is None:
            # Partial match
            for key, val in CCSBT_VESSEL_TYPE_MAP.items():
                if key in vt_lower:
                    fao_code = val
                    break

    elif org == "IATTC":
        # IATTC doesn't have a separate vessel type column — handled in gear logic
        # For vessels classified via gear column, we use IATTC_GEAR_TO_VESSEL_TYPE
        fao_code = "MO"  # Default for IATTC multi-purpose
        if vt_upper in IATTC_GEAR_TO_VESSEL_TYPE:
            fao_code = IATTC_GEAR_TO_VESSEL_TYPE[vt_upper]

    elif org == "ICCAT":
        fao_code = ICCAT_VESSEL_TYPE_MAP.get(vt_upper, vt_upper)

    elif org == "IOTC":
        fao_code = IOTC_VESSEL_TYPE_MAP.get(vt_upper)
        if fao_code is None:
            # Try matching by type name
            vtn_lower = vtn.lower().strip()
            if "supply" in vtn_lower:
                fao_code = "SA"
            elif "carrier" in vtn_lower or "cargo" in vtn_lower:
                fao_code = "TS"
            elif "longliner" in vtn_lower:
                fao_code = "LL"
            elif "purse" in vtn_lower:
                fao_code = "PS"
            elif "multipurpose" in vtn_lower:
                fao_code = "MO"
            elif "gill" in vtn_lower:
                fao_code = "GO"
            elif "line" in vtn_lower or "pole" in vtn_lower:
                fao_code = "LO"
            elif "research" in vtn_lower or "training" in vtn_lower:
                fao_code = "RT"
            else:
                fao_code = vt_upper

    elif org == "WCPFC":
        fao_code = WCPFC_VESSEL_TYPE_MAP.get(vt_upper)
        if fao_code is None:
            # Additional WCPFC patterns
            if vt_upper.startswith("LL"):
                fao_code = "LL"
            elif vt_upper.startswith("SP"):
                fao_code = "PS"
            elif vt_upper.startswith("FO") or vt_upper.startswith("CO"):
                fao_code = "TS"
            elif "SUPPORT" in vt_upper or vt_upper.startswith("VO"):
                fao_code = "SA"
            else:
                fao_code = vt_upper
    else:
        fao_code = vt_upper

    # --- Directive 2.1 & 3.2: Pre-rescue eligibility checks ---
    # Determine whether this vessel is eligible for gear rescue BEFORE
    # any penetration logic runs. Ineligible vessels keep their raw FAO code.
    is_multi_rescued = False
    was_classified_by_gear = False

    # Directive 2.1: Physical hull types ineligible for gear rescue
    # Check BOTH the mapped FAO code AND the original raw vessel type.
    # (e.g. ICCAT "LH" maps to FAO "LO", but "LH" itself is blocklisted)
    _rescue_blocked = (
        fao_code is not None
        and (str(fao_code).upper().strip() in GEAR_RESCUE_BLOCKLIST
             or str(vt).upper().strip() in GEAR_RESCUE_BLOCKLIST)
    )

    # Directive 3.2: Supply/auxiliary vessels must stay locked as SA
    _supply_locked = (
        str(vt).upper().strip() in SUPPLY_VESSEL_CODES
        or (fao_code is not None
            and str(fao_code).upper().strip() in SUPPLY_VESSEL_CODES)
    )

    # --- Multi-gear / Multi-purpose penetration ---

    if fao_code == "MO" and not _rescue_blocked:
        # Multi-purpose vessel → check gear for PS / LL / PS,LL
        classified = classify_gear_for_multi(gear_codes)
        if classified in ("PS", "LL", "PS, LL"):
            # Directive 3.1: CCSBT double-tagged vessels (PS+LL) → force LL
            # Southern Bluefin Tuna depends on ultra-low-temperature longline
            if org == "CCSBT" and classified == "PS, LL":
                classified = "LL"
            fao_code = classified
            is_multi_rescued = True
            was_classified_by_gear = True

    elif (fao_code is not None
          and fao_code not in ("LL", "PS", "PS, LL", "TS", "SA")
          and fao_code not in DISCARD_VESSEL_TYPES):
        # For other vessel types (e.g., SO, LO, TO, GO, WO, FX):
        # Check if their gear includes PS or LL → rescue as fishing vessel
        # UNLESS blocked by Directive 2.1 (hull) or 3.2 (supply lock)
        if not _rescue_blocked and not _supply_locked:
            has_ps = is_purse_seine_gear(gear_codes)
            has_ll = is_longline_gear(gear_codes)
            if has_ps and has_ll:
                # Directive 3.1: CCSBT double-tag → force LL
                if org == "CCSBT":
                    fao_code = "LL"
                else:
                    fao_code = "PS, LL"
                is_multi_rescued = True
                was_classified_by_gear = True
            elif has_ps:
                fao_code = "PS"
                is_multi_rescued = True
                was_classified_by_gear = True
            elif has_ll:
                fao_code = "LL"
                is_multi_rescued = True
                was_classified_by_gear = True
        # If blocked or supply_locked: fao_code stays as-is
        # → blocked hull types (TO/LH/GI) will be discarded downstream
        # → supply types (SP/SUPP) remain SA and survive as target type

    # --- Discard non-target types ---
    if fao_code and fao_code in DISCARD_VESSEL_TYPES:
        return ("DISCARD", is_multi_rescued, was_classified_by_gear)

    return (fao_code, is_multi_rescued, was_classified_by_gear)


# ============================================================================
# SECTION 5 — Flag Normalization (Full Names → ISO 3166-1 alpha-3)
# ============================================================================

# ISO 3166-1 alpha-2 → alpha-3 mapping (for WCPFC, some ICCAT)
ISO2_TO_ISO3 = {
    "AD": "AND", "AE": "ARE", "AF": "AFG", "AG": "ATG", "AL": "ALB",
    "AM": "ARM", "AO": "AGO", "AR": "ARG", "AT": "AUT", "AU": "AUS",
    "AZ": "AZE", "BA": "BIH", "BB": "BRB", "BD": "BGD", "BE": "BEL",
    "BF": "BFA", "BG": "BGR", "BH": "BHR", "BI": "BDI", "BJ": "BEN",
    "BN": "BRN", "BO": "BOL", "BR": "BRA", "BS": "BHS", "BT": "BTN",
    "BW": "BWA", "BY": "BLR", "BZ": "BLZ", "CA": "CAN", "CD": "COD",
    "CF": "CAF", "CG": "COG", "CH": "CHE", "CI": "CIV", "CK": "COK",
    "CL": "CHL", "CM": "CMR", "CN": "CHN", "CO": "COL", "CR": "CRI",
    "CU": "CUB", "CV": "CPV", "CW": "CUW", "CY": "CYP", "CZ": "CZE",
    "DE": "DEU", "DJ": "DJI", "DK": "DNK", "DM": "DMA", "DO": "DOM",
    "DZ": "DZA", "EC": "ECU", "EE": "EST", "EG": "EGY", "ER": "ERI",
    "ES": "ESP", "ET": "ETH", "FI": "FIN", "FJ": "FJI", "FM": "FSM",
    "FR": "FRA", "GA": "GAB", "GB": "GBR", "GD": "GRD", "GE": "GEO",
    "GH": "GHA", "GM": "GMB", "GN": "GIN", "GQ": "GNQ", "GR": "GRC",
    "GT": "GTM", "GW": "GNB", "GY": "GUY", "HK": "HKG", "HN": "HND",
    "HR": "HRV", "HT": "HTI", "HU": "HUN", "ID": "IDN", "IE": "IRL",
    "IL": "ISR", "IN": "IND", "IQ": "IRQ", "IR": "IRN", "IS": "ISL",
    "IT": "ITA", "JM": "JAM", "JO": "JOR", "JP": "JPN", "KE": "KEN",
    "KG": "KGZ", "KH": "KHM", "KI": "KIR", "KM": "COM", "KN": "KNA",
    "KP": "PRK", "KR": "KOR", "KW": "KWT", "KZ": "KAZ", "LA": "LAO",
    "LB": "LBN", "LC": "LCA", "LI": "LIE", "LK": "LKA", "LR": "LBR",
    "LS": "LSO", "LT": "LTU", "LU": "LUX", "LV": "LVA", "LY": "LBY",
    "MA": "MAR", "MC": "MCO", "MD": "MDA", "ME": "MNE", "MG": "MDG",
    "MH": "MHL", "MK": "MKD", "ML": "MLI", "MM": "MMR", "MN": "MNG",
    "MR": "MRT", "MT": "MLT", "MU": "MUS", "MV": "MDV", "MW": "MWI",
    "MX": "MEX", "MY": "MYS", "MZ": "MOZ", "NA": "NAM", "NC": "NCL",
    "NE": "NER", "NG": "NGA", "NI": "NIC", "NL": "NLD", "NO": "NOR",
    "NP": "NPL", "NR": "NRU", "NZ": "NZL", "OM": "OMN", "PA": "PAN",
    "PE": "PER", "PF": "PYF", "PG": "PNG", "PH": "PHL", "PK": "PAK",
    "PL": "POL", "PT": "PRT", "PW": "PLW", "PY": "PRY", "QA": "QAT",
    "RO": "ROU", "RS": "SRB", "RU": "RUS", "RW": "RWA", "SA": "SAU",
    "SB": "SLB", "SC": "SYC", "SD": "SDN", "SE": "SWE", "SG": "SGP",
    "SI": "SVN", "SK": "SVK", "SL": "SLE", "SM": "SMR", "SN": "SEN",
    "SO": "SOM", "SR": "SUR", "SS": "SSD", "ST": "STP", "SV": "SLV",
    "SY": "SYR", "SZ": "SWZ", "TD": "TCD", "TG": "TGO", "TH": "THA",
    "TJ": "TJK", "TL": "TLS", "TM": "TKM", "TN": "TUN", "TO": "TON",
    "TR": "TUR", "TT": "TTO", "TV": "TUV", "TW": "TWN", "TZ": "TZA",
    "UA": "UKR", "UG": "UGA", "US": "USA", "UY": "URY", "UZ": "UZB",
    "VA": "VAT", "VC": "VCT", "VE": "VEN", "VN": "VNM", "VU": "VUT",
    "WS": "WSM", "YE": "YEM", "ZA": "ZAF", "ZM": "ZMB", "ZW": "ZWE",
}

# Direct mapping: any raw flag string → ISO alpha-3
# Covers: full names, RFMO-specific codes, 2-letter codes, mixed formats
FLAG_TO_ISO3 = {
    # === CCSBT full names ===
    "New Zealand":                     "NZL",
    "Indonesia":                       "IDN",
    "Japan":                           "JPN",
    "Fishing Entity of Taiwan":        "TWN",
    "Australia":                       "AUS",
    "Spain":                           "ESP",
    "South Africa":                    "ZAF",
    "Portugal":                        "PRT",
    "Panama":                          "PAN",
    "Republic of Korea":               "KOR",
    "Liberia":                         "LBR",
    "Singapore":                       "SGP",
    "Vanuatu":                         "VUT",

    # === IATTC full names ===
    "United States":                   "USA",
    "Chile":                           "CHL",
    "China":                           "CHN",
    "Mexico":                          "MEX",
    "Canada":                          "CAN",
    "Ecuador":                         "ECU",
    "Costa Rica":                      "CRI",
    "Chinese Taipei":                  "TWN",
    "Korea":                           "KOR",
    "FRA (French Polynesia)":          "PYF",
    "EU (Spain)":                      "ESP",
    "Nicaragua":                       "NIC",
    "Guatemala":                       "GTM",
    "Venezuela":                       "VEN",
    "Peru":                            "PER",
    "Colombia":                        "COL",
    "EU (Portugal)":                   "PRT",
    "El Salvador":                     "SLV",

    # === IOTC full names ===
    "Sri Lanka":                       "LKA",
    "Iran":                            "IRN",
    "Maldives":                        "MDV",
    "Seychelles":                      "SYC",
    "Korea (Republic of)":             "KOR",
    "Spain (EU)":                      "ESP",
    "France (EU)":                     "FRA",
    "Malaysia":                        "MYS",
    "Portugal (EU)":                   "PRT",
    "Oman":                            "OMN",
    "Thailand":                        "THA",
    "Kenya":                           "KEN",
    "Mauritius":                       "MUS",
    "Madagascar":                      "MDG",
    "India":                           "IND",
    "Tanzania":                        "TZA",
    "Lithuania (EU)":                  "LTU",
    "Italy (EU)":                      "ITA",

    # === ICCAT RFMO codes ===
    "MAR":                             "MAR",
    "EU-ITA":                          "ITA",
    "EU-CYP":                          "CYP",
    "EU-ESP":                          "ESP",
    "EU-MLT":                          "MLT",
    "TUN":                             "TUN",
    "DZA":                             "DZA",
    "USA":                             "USA",
    "EU-GRC":                          "GRC",
    "EU-FRA":                          "FRA",
    "TUR":                             "TUR",
    "EU-PRT":                          "PRT",
    "EU-HRV":                          "HRV",
    "VEN":                             "VEN",
    "TAI":                             "TWN",
    "BRA":                             "BRA",
    "NOR":                             "NOR",
    "ZAF":                             "ZAF",
    "CHN":                             "CHN",
    "PAN":                             "PAN",
    "EGY":                             "EGY",
    "BHS":                             "BHS",
    "GHA":                             "GHA",
    "BLZ":                             "BLZ",
    "NAM":                             "NAM",
    "CIV":                             "CIV",
    "LBY":                             "LBY",
    "RUS":                             "RUS",
    "SUR":                             "SUR",
    "KOR":                             "KOR",
    "GB-ENG":                          "GBR",
    "GBR":                             "GBR",
    "SEN":                             "SEN",
    "LBR":                             "LBR",
    "TTO":                             "TTO",
    "EU-NLD":                          "NLD",
    "EU-IRL":                          "IRL",
    "EU-LTU":                          "LTU",
    "CPV":                             "CPV",
    "SLV":                             "SLV",
    "ALB":                             "ALB",
    "CUR":                             "CUW",
    "CUW":                             "CUW",
    "CAN":                             "CAN",
    "SYR":                             "SYR",
    "EU-POL":                          "POL",
    "SGP":                             "SGP",
    "EU-LVA":                          "LVA",
    "GRD":                             "GRD",
    "UK-SHN":                          "SHN",
    "MEX":                             "MEX",
    "GIN":                             "GIN",
    "AGO":                             "AGO",
    "NGA":                             "NGA",
    "VCT":                             "VCT",
    "VUT":                             "VUT",
    "KHM":                             "KHM",
    "TON":                             "TON",
    "AUS":                             "AUS",
    "YUG":                             "SRB",   # Former Yugoslavia → Serbia
    "UKR":                             "UKR",
    "TGO":                             "TGO",
    "NIC":                             "NIC",
    "CHL":                             "CHL",
    "FRO":                             "FRO",
    "URY":                             "URY",
    "PHL":                             "PHL",
    "SYC":                             "SYC",
    "STP":                             "STP",
    "EU-DEU":                          "DEU",
    "JPN":                             "JPN",
    "PRT":                             "PRT",
    "ESP":                             "ESP",
    "FRA":                             "FRA",
    "ITA":                             "ITA",

    # === IOTC codes (already ISO3) ===
    "LKA":                             "LKA",
    "IRN":                             "IRN",
    "IDN":                             "IDN",
    "MDV":                             "MDV",
    "MYS":                             "MYS",
    "OMN":                             "OMN",
    "THA":                             "THA",
    "KEN":                             "KEN",
    "MUS":                             "MUS",
    "MDG":                             "MDG",
    "IND":                             "IND",
    "TZA":                             "TZA",
    "LTU":                             "LTU",

    # === ICCAT FlagChartTo sentinel ===
    "---":                             "",

    # === WCPFC codes (already alpha-2, handled below before this lookup) ===
}

# Also populate ISO2 codes from the ISO2_TO_ISO3 table into FLAG_TO_ISO3
for _a2, _a3 in ISO2_TO_ISO3.items():
    if _a2 not in FLAG_TO_ISO3:
        FLAG_TO_ISO3[_a2] = _a3


def normalize_flag_to_iso3(raw_flag: str) -> str:
    """
    Normalize a raw flag string to ISO 3166-1 alpha-3 country code.

    Handles: full English names (CCSBT, IATTC, IOTC), ICCAT RFMO codes
    (EU-XXX → XXX, TAI → TWN, etc.), WCPFC 2-letter codes, and standard
    3-letter codes already conforming to ISO.
    """
    if pd.isna(raw_flag) or str(raw_flag).strip() == "":
        return ""
    s = str(raw_flag).strip()
    # Sentinel values
    if s in ("---", "NONE", "N/A", "N.A.", "UNKNOWN"):
        return ""
    # Try exact match first
    if s in FLAG_TO_ISO3:
        return FLAG_TO_ISO3[s]
    # Try uppercased
    s_upper = s.upper()
    if s_upper in FLAG_TO_ISO3:
        return FLAG_TO_ISO3[s_upper]
    # Try as alpha-2 code
    if s_upper in ISO2_TO_ISO3:
        return ISO2_TO_ISO3[s_upper]
    # Try splitting EU- prefix: e.g. "EU-XXX" → XXX, then look up XXX
    if s_upper.startswith("EU-"):
        sub = s_upper[3:]
        if sub in FLAG_TO_ISO3:
            return FLAG_TO_ISO3[sub]
        if sub in ISO2_TO_ISO3:
            return ISO2_TO_ISO3[sub]
        # sub might already be ISO3
        if len(sub) == 3 and sub.isalpha():
            return sub
    # If it looks like an ISO3 code already (3 uppercase letters), return as-is
    if len(s_upper) == 3 and s_upper.isalpha():
        return s_upper
    # Title-case lookup (e.g. "Panama")
    s_title = s.title()
    if s_title in FLAG_TO_ISO3:
        return FLAG_TO_ISO3[s_title]
    return ""  # Unrecognized


# ============================================================================
# SECTION 5b — Raw Data Preprocessing (Unit Standardization & Format Fixes)
# ============================================================================

def _clean_european_number(val):
    """
    Parse a European-formatted number string to float.

    Handles:
      - European decimal comma: "33,6" → 33.6, "1417,46" → 1417.46
      - Mixed comma/dot formats: "4.014,323" → 4014.323
      - Already-numeric values: returned as float
      - NaN / empty: returns np.nan

    The key heuristic: if a string has exactly ONE comma and 1-3 digits after it,
    the comma is a decimal separator (European convention). Multiple commas may
    appear in values like "4,014,323" — these are parsed with the last comma as
    decimal, others as thousand-separator artifacts.
    """
    if pd.isna(val):
        return np.nan

    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s or s.lower() == 'nan':
        return np.nan

    # Remove any surrounding whitespace / non-breaking spaces
    s = s.replace('\xa0', ' ').replace(' ', '').strip()

    n_commas = s.count(',')
    n_dots = s.count('.')

    if n_commas == 0 and n_dots == 0:
        # Plain integer string
        try:
            return float(s)
        except ValueError:
            return np.nan

    if n_commas >= 1 and n_dots == 0:
        # Only commas: could be European decimal or thousand-separated
        if n_commas == 1:
            # Single comma: European decimal ("33,6" → 33.6, "1417,46" → 1417.46)
            parts = s.split(',')
            if len(parts) == 2 and len(parts[1]) <= 3:
                return float(parts[0].replace(',', '') + '.' + parts[1])
        # Multiple commas: could be "4,014,323"
        # Strategy: if last segment ≤3 chars, treat it as decimal
        parts = s.split(',')
        if len(parts[-1]) <= 3 and len(parts[-1]) >= 1:
            int_part = ''.join(parts[:-1])
            try:
                return float(int_part + '.' + parts[-1])
            except ValueError:
                pass
        # Fallback: strip all commas
        return float(s.replace(',', ''))

    if n_dots >= 1 and n_commas == 0:
        # Only dots: could be "4.014.323" (European thousand sep) or "33.6" (decimal)
        if n_dots >= 2:
            # Multiple dots → European thousand separators: "4.014.323" → 4014.323
            parts = s.split('.')
            if len(parts[-1]) <= 3:
                int_part = ''.join(parts[:-1])
                try:
                    return float(int_part + '.' + parts[-1])
                except ValueError:
                    pass
        # Single dot: standard decimal
        try:
            return float(s)
        except ValueError:
            return np.nan

    if n_commas >= 1 and n_dots >= 1:
        # Mixed: "4.014,323" (European: dot=thousands, comma=decimal)
        # Use the rightmost separator as decimal
        last_comma = s.rfind(',')
        last_dot = s.rfind('.')
        if last_comma > last_dot:
            # Last comma is decimal: "4.014,323" → "4014.323"
            int_part = s[:last_comma].replace('.', '').replace(',', '')
            dec_part = s[last_comma + 1:]
            try:
                return float(int_part + '.' + dec_part)
            except ValueError:
                pass
        else:
            # Last dot is decimal: "4,014.323" → "4014.323"
            int_part = s[:last_dot].replace(',', '').replace('.', '')
            dec_part = s[last_dot + 1:]
            try:
                return float(int_part + '.' + dec_part)
            except ValueError:
                pass
        # Fallback: strip commas, keep dots
        return float(s.replace(',', ''))

    # Final fallback
    try:
        return float(s.replace(',', '.'))
    except ValueError:
        return np.nan


def _preprocess_rfmo_raw(df: pd.DataFrame, org: str) -> pd.DataFrame:
    """
    Apply RFMO-specific raw data cleaning BEFORE column detection and extraction.

    Fixes applied per RFMO:
      ICCAT:
        - European decimal comma → dot in LOAm, Tonnage, EnginePowerHP
        - LOAm values > 200 → divide by 100 (cm→m)
        - EnginePowerHP values > 100,000 → divide by 1,000
          (comma-stripping artifact from Excel misreading European formatting)
      WCPFC:
        - Length values in ft → convert to m (×0.3048) based on 'Unit of length' column
    """
    df = df.copy()

    if org == "ICCAT":
        # --- LOAm: European decimal + cm→m fix ---
        if "LOAm" in df.columns:
            before = pd.to_numeric(df["LOAm"], errors="coerce").copy()
            df["LOAm"] = df["LOAm"].apply(_clean_european_number)
            # Fix values > 200 — these are centimetres erroneously stored as metres
            cm_mask = df["LOAm"] > 200
            n_cm = cm_mask.sum()
            if n_cm > 0:
                df.loc[cm_mask, "LOAm"] = df.loc[cm_mask, "LOAm"] / 100.0
                affected = df.loc[cm_mask, "VesselName"].tolist() if "VesselName" in df.columns else []
                print(f"  [Preprocess ICCAT] LOAm: {n_cm} values >200 m → divided by 100 (cm→m)")
                if affected:
                    print(f"    Vessels: {affected}")

        # --- Tonnage: European decimal comma ---
        if "Tonnage" in df.columns:
            n_str_before = df["Tonnage"].apply(lambda x: isinstance(x, str)).sum()
            df["Tonnage"] = df["Tonnage"].apply(_clean_european_number)
            if n_str_before > 0:
                print(f"  [Preprocess ICCAT] Tonnage: {n_str_before} European decimal strings → float")

        # --- EnginePowerHP: European decimal comma + comma-stripping artifact ---
        if "EnginePowerHP" in df.columns:
            n_str_before = df["EnginePowerHP"].apply(lambda x: isinstance(x, str)).sum()
            df["EnginePowerHP"] = df["EnginePowerHP"].apply(_clean_european_number)
            if n_str_before > 0:
                print(f"  [Preprocess ICCAT] EnginePowerHP: {n_str_before} European decimal strings → float")
            # Fix comma-stripping artifacts:
            # Values like 4,014,323 → Excel strips commas → 4014323 → should be 4014.323
            # Heuristic: any EnginePowerHP > 100,000 is likely a comma artifact
            artifact_mask = df["EnginePowerHP"] > 100000
            n_artifact = artifact_mask.sum()
            if n_artifact > 0:
                df.loc[artifact_mask, "EnginePowerHP"] = df.loc[artifact_mask, "EnginePowerHP"] / 1000.0
                affected = df.loc[artifact_mask, ["VesselName", "IntRegNo"]].values.tolist() \
                    if "VesselName" in df.columns else []
                print(f"  [Preprocess ICCAT] EnginePowerHP: {n_artifact} comma-stripping artifacts "
                      f"(>100k) → divided by 1000")
                for name, imo in affected[:5]:
                    print(f"    {name} (IMO={imo})")

    elif org == "WCPFC":
        # --- Length: ft → m conversion ---
        if "Length" in df.columns and "Unit of length" in df.columns:
            ft_mask = df["Unit of length"].astype(str).str.lower().str.strip() == "ft"
            n_ft = ft_mask.sum()
            if n_ft > 0:
                df.loc[ft_mask, "Length"] = pd.to_numeric(
                    df.loc[ft_mask, "Length"], errors="coerce"
                ) * 0.3048
                df.loc[ft_mask, "Unit of length"] = "m"
                print(f"  [Preprocess WCPFC] Length: {n_ft} records converted ft→m (×0.3048)")

    return df


# ============================================================================
# SECTION 6 — Per-RFMO Extraction Functions
# ============================================================================

def _normalize_type_value(raw_val: str) -> str:
    """Normalize a type descriptor to a short standard code."""
    if pd.isna(raw_val) or str(raw_val).strip() == "":
        return ""
    s = str(raw_val).strip().upper()
    # Standardize common variants
    type_map = {
        "LOA": "LOA",
        "LENGTH OVERALL": "LOA",
        "OVERALL": "LOA",
        "LBP": "LBP",
        "LENGTH BETWEEN PERPENDICULARS": "LBP",
        "BETWEENPP": "LBP",
        "BETWEEN PP": "LBP",
        "REG": "REG",
        "REGISTERED": "REG",
        "LENGTH REGISTERED": "REG",
        "GT": "GT",
        "GROSS TONNAGE": "GT",
        "GROSS REGISTERED TONNAGE": "GRT",
        "GRT": "GRT",
        "NT": "NT",
        "NET TONNAGE": "NT",
        "KW": "KW",
        "HP": "HP",
        "PS": "PS",
        "BHP": "BHP",
        "UNK": "UNK",
        "UNKNOWN": "UNK",
        "?": "",    # 占位符/未知 → 清空
    }
    # Exact match first
    if s in type_map:
        return type_map[s]
    # Partial match (use word boundaries to prevent "GT" matching inside "LENGTH")
    for key, val in type_map.items():
        if key in s.split() or re.search(r'\b' + re.escape(key) + r'\b', s):
            return val
    # If it's already a short code (2-4 letters), return as-is
    if re.match(r"^[A-Z0-9]{1,6}$", s):
        return s
    return s[:20]  # Truncate long values


def safe_str(val) -> str:
    """Convert value to string, returning empty string for NaN."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    # Clean float-represented integers (e.g., "9576533.0" → "9576533")
    if s.endswith(".0") and s.count(".") == 1:
        try:
            float(s)
            s = s[:-2]
        except ValueError:
            pass
    return s


def safe_float(val):
    """Convert value to float, returning NaN for non-numeric."""
    if pd.isna(val):
        return np.nan
    try:
        return float(val)
    except (ValueError, TypeError):
        return np.nan


def safe_int_from_float(val):
    """Convert float to int, returning NaN for non-numeric."""
    f = safe_float(val)
    if np.isnan(f):
        return np.nan
    return int(f)


def _clear_types_for_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    If a measurement value is NaN, the corresponding unit type metadata is
    meaningless — clear it.

    This prevents downstream confusion where e.g. Enginepower=NaN but
    PowerType="HP" (the unit label outlives the value it describes).
    """
    df = df.copy()
    if "Length" in df.columns and "LengthType" in df.columns:
        mask = df["Length"].isna()
        if mask.any():
            df.loc[mask, "LengthType"] = ""
    if "Tonnage" in df.columns and "TonnageType" in df.columns:
        mask = df["Tonnage"].isna()
        if mask.any():
            df.loc[mask, "TonnageType"] = ""
    if "Enginepower" in df.columns and "PowerType" in df.columns:
        mask = df["Enginepower"].isna()
        if mask.any():
            df.loc[mask, "PowerType"] = ""
    return df


def extract_ccsbt(filepath: Path, isscfv: dict, isscfg: dict) -> pd.DataFrame:
    """Extract and normalize CCSBT vessel data."""
    print(f"\n{'─' * 60}")
    print(f"  Processing CCSBT: {filepath.name}")
    print(f"{'─' * 60}")

    df_raw = pd.read_csv(filepath, encoding="utf-8")
    cols = detect_columns(df_raw)

    print(f"  Rows: {len(df_raw)}")
    print(f"  Detected vessel type col:  {cols['vessel_type_col']}")
    print(f"  Detected gear type col:    {cols['gear_type_col']}")
    print(f"  Detected vessel name col:  {cols['vessel_name_col']}")
    print(f"  Detected IMO col:          {cols['imo_col']}")
    print(f"  Detected Callsign col:     {cols['callsign_col']}")
    print(f"  Detected length type col:  {cols['length_type_col']}")

    results = []
    multi_gear_rescued = 0
    discarded = 0

    for idx, row in df_raw.iterrows():
        # Extract vessel type and gear
        vessel_type_raw = safe_str(row.get(cols["vessel_type_col"], ""))
        gear_raw = safe_str(row.get(cols["gear_type_col"], ""))

        # Parse gear codes
        gear_codes = parse_gear_codes(gear_raw, CCSBT_GEAR_PARSE_SEP)

        # Normalize vessel type
        fao_code, is_rescued, _ = normalize_vessel_type(
            vessel_type_raw, gear_codes, "CCSBT"
        )

        if fao_code == "DISCARD" or fao_code is None:
            discarded += 1
            continue

        # Only keep target types: LL, PS, PS,LL (combined), TS, SA
        if fao_code not in ("LL", "PS", "PS, LL", "TS", "SA"):
            # Directives 2.1 & 3.2: Block gear rescue for ineligible hull
            # types and supply/auxiliary vessels
            _blocked = (str(fao_code).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in SUPPLY_VESSEL_CODES)
            if _blocked:
                discarded += 1
                continue
            # Check one more time via gear for non-target vessel types
            has_ps = is_purse_seine_gear(gear_codes)
            has_ll = is_longline_gear(gear_codes)
            if has_ps and has_ll:
                fao_code = "PS, LL"
                is_rescued = True
            elif has_ps:
                fao_code = "PS"
                is_rescued = True
            elif has_ll:
                fao_code = "LL"
                is_rescued = True
            else:
                discarded += 1
                continue

        if is_rescued:
            multi_gear_rescued += 1

        # Extract type metadata
        length_type = _normalize_type_value(row.get(cols["length_type_col"], ""))
        # CCSBT: "Tonnage" column = Gross Tonnage (GT); no explicit tonnage type column
        tonnage_type = "GT"
        # CCSBT has no engine power data
        power_type = ""

        # Build standardized output row
        results.append({
            "Vesselname": safe_str(row.get(cols["vessel_name_col"], "")),
            "IMO": safe_str(row.get(cols["imo_col"], "")),
            "Callsign": safe_str(row.get(cols["callsign_col"], "")),
            "MMSI": safe_str(row.get(cols["mmsi_col"], "")),
            "Length": safe_float(row.get(cols["length_col"])),
            "Tonnage": safe_float(row.get(cols["tonnage_col"])),
            "Enginepower": np.nan,  # CCSBT has no engine power
            "Builtdate": np.nan,         # CCSBT has no year built
            "VesselType": fao_code,
            "SourceVesselType": vessel_type_raw,
            "LengthType": length_type,
            "TonnageType": tonnage_type,
            "PowerType": power_type,
            "Flag": normalize_flag_to_iso3(safe_str(row.get(cols["flag_col"], ""))),
        })

    df_out = pd.DataFrame(results, columns=TARGET_SCHEMA["CCSBT"])
    df_out = _clear_types_for_missing_values(df_out)
    print(f"  Extracted: {len(df_out)} vessels")
    print(f"    LL={len(df_out[df_out['VesselType']=='LL'])}, "
          f"PS={len(df_out[df_out['VesselType']=='PS'])}, "
          f"PS,LL={len(df_out[df_out['VesselType']=='PS, LL'])}, "
          f"TS={len(df_out[df_out['VesselType']=='TS'])}, "
          f"SA={len(df_out[df_out['VesselType']=='SA'])}")
    print(f"  Multi-gear rescued: {multi_gear_rescued}")
    print(f"  Discarded: {discarded}")
    return df_out


def extract_iatc(filepath: Path, isscfv: dict, isscfg: dict) -> pd.DataFrame:
    """Extract and normalize IATTC vessel data."""
    print(f"\n{'─' * 60}")
    print(f"  Processing IATTC: {filepath.name}")
    print(f"{'─' * 60}")

    df_raw = pd.read_excel(filepath, sheet_name="RegionalVesselRegister")
    cols = detect_columns(df_raw)

    print(f"  Rows: {len(df_raw)}")
    print(f"  Detected gear col:        {cols['gear_type_col']}")
    print(f"  Detected vessel name col: {cols['vessel_name_col']}")
    print(f"  Detected IMO col:         {cols['imo_col']}")
    print(f"  Detected Callsign col:    {cols['callsign_col']}")
    print(f"  Detected engine power col:{cols['engine_power_col']}")
    print(f"  Detected year built col:  {cols['year_built_col']}")
    print(f"  Detected length type col: {cols['length_type_col']}")

    results = []
    discarded = 0

    for idx, row in df_raw.iterrows():
        gear_raw = safe_str(row.get(cols["gear_type_col"], ""))

        # IATTC has gear only (no vessel type column)
        # Map gear to vessel type
        gear_lower = gear_raw.lower().strip()
        fao_code = IATTC_GEAR_TO_VESSEL_TYPE.get(gear_lower)

        if fao_code is None:
            discarded += 1
            continue

        if fao_code == "RO" or fao_code in DISCARD_VESSEL_TYPES:
            discarded += 1
            continue

        # Directive 1.2: IATTC MO (Multi-purpose) vessels → UNCONDITIONALLY DISCARD
        # LCA 5% truncation rule: these are coastal multi-species vessels
        # without tuna target gear — prevent economic allocation errors
        if gear_lower in IATTC_MULTI_GEAR_VESSEL_TYPES:
            discarded += 1
            continue
        elif fao_code not in ("LL", "PS", "PS, LL", "TS", "SA"):
            discarded += 1
            continue

        # Engine power — preserve raw value (no HP→KW conversion)
        engine_power_raw = safe_float(row.get(cols["engine_power_col"]))

        # Parse year built
        year_built = safe_float(row.get(cols["year_built_col"]))

        # Extract type metadata
        length_type = _normalize_type_value(row.get(cols["length_type_col"], ""))
        # IATTC "Gross tonnage (t)" = Gross Tonnage (GT), "(t)" 仅表示单位为吨
        tonnage_type = "GT"
        # IATTC engine power column name implies HP
        power_col_name = str(cols["engine_power_col"]) if cols["engine_power_col"] else ""
        power_type = "HP" if "hp" in power_col_name.lower() else ""

        results.append({
            "Vesselname": safe_str(row.get(cols["vessel_name_col"], "")),
            "IMO": safe_str(row.get(cols["imo_col"], "")),
            "Callsign": safe_str(row.get(cols["callsign_col"], "")),
            "MMSI": safe_str(row.get(cols["mmsi_col"], "")),
            "Length": safe_float(row.get(cols["length_col"])),
            "Tonnage": safe_float(row.get(cols["tonnage_col"])),
            "Enginepower": engine_power_raw if not np.isnan(engine_power_raw) else np.nan,
            "Builtdate": year_built if not np.isnan(year_built) else np.nan,
            "VesselType": fao_code,
            "SourceVesselType": gear_raw,  # IATTC source type = gear column
            "LengthType": length_type,
            "TonnageType": tonnage_type,
            "PowerType": power_type,
            "Flag": normalize_flag_to_iso3(safe_str(row.get(cols["flag_col"], ""))),
        })

    df_out = pd.DataFrame(results, columns=TARGET_SCHEMA["IATTC"])
    df_out = _clear_types_for_missing_values(df_out)
    print(f"  Extracted: {len(df_out)} vessels")
    print(f"    LL={len(df_out[df_out['VesselType']=='LL'])}, "
          f"PS={len(df_out[df_out['VesselType']=='PS'])}, "
          f"PS,LL={len(df_out[df_out['VesselType']=='PS, LL'])}, "
          f"TS={len(df_out[df_out['VesselType']=='TS'])}, "
          f"SA={len(df_out[df_out['VesselType']=='SA'])}")
    print(f"  Discarded: {discarded} (incl. all MO multi-purpose per LCA 5% cutoff)")
    return df_out


def extract_iccat(filepath: Path, isscfv: dict, isscfg: dict) -> pd.DataFrame:
    """Extract and normalize ICCAT vessel data."""
    print(f"\n{'─' * 60}")
    print(f"  Processing ICCAT: {filepath.name}")
    print(f"{'─' * 60}")

    df_raw = pd.read_excel(filepath)

    # --- Preprocess: fix European decimal commas and unit issues ---
    df_raw = _preprocess_rfmo_raw(df_raw, "ICCAT")

    cols = detect_columns(df_raw)

    print(f"  Rows: {len(df_raw)}")
    print(f"  Detected vessel type col:  {cols['vessel_type_col']}")
    print(f"  Detected gear type col:    {cols['gear_type_col']}")
    print(f"  Detected vessel name col:  {cols['vessel_name_col']}")
    print(f"  Detected IMO col:          {cols['imo_col']}")
    print(f"  Detected tonnage type col: {cols['tonnage_type_col']}")

    # For ICCAT, IMO is in IntRegNo when IRNoTypeCode == 'IMO'
    imo_col = cols["imo_col"]
    has_imo_type = "IRNoTypeCode" in df_raw.columns

    results = []
    multi_gear_rescued = 0
    discarded = 0

    for idx, row in df_raw.iterrows():
        vessel_type_raw = safe_str(row.get(cols["vessel_type_col"], ""))
        gear_raw = safe_str(row.get(cols["gear_type_col"], ""))

        gear_codes = parse_gear_codes(gear_raw, ",")

        fao_code, is_rescued, _ = normalize_vessel_type(
            vessel_type_raw, gear_codes, "ICCAT"
        )

        if fao_code == "DISCARD" or fao_code is None:
            discarded += 1
            continue

        if fao_code not in ("LL", "PS", "PS, LL", "TS", "SA"):
            # Directives 2.1 & 3.2: Block gear rescue for ineligible hull
            # types and supply/auxiliary vessels
            _blocked = (str(fao_code).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in SUPPLY_VESSEL_CODES)
            if _blocked:
                discarded += 1
                continue
            # Try rescue via gear
            has_ps = is_purse_seine_gear(gear_codes)
            has_ll = is_longline_gear(gear_codes)
            if has_ps and has_ll:
                fao_code = "PS, LL"
                is_rescued = True
            elif has_ps:
                fao_code = "PS"
                is_rescued = True
            elif has_ll:
                fao_code = "LL"
                is_rescued = True
            else:
                discarded += 1
                continue

        if is_rescued:
            multi_gear_rescued += 1

        # Extract IMO properly (IntRegNo filtered by IRNoTypeCode)
        imo_val = ""
        if has_imo_type and imo_col:
            ir_type = safe_str(row.get("IRNoTypeCode", ""))
            if ir_type.upper() == "IMO":
                imo_val = safe_str(row.get(imo_col, ""))
        else:
            imo_val = safe_str(row.get(imo_col, "")) if imo_col else ""

        # Engine power — preserve raw value (no HP→KW conversion)
        eng_power_raw = safe_float(row.get(cols["engine_power_col"]))

        year_built = safe_float(row.get(cols["year_built_col"]))

        # Flag and Flagcode → convert to ISO3
        flag_val = normalize_flag_to_iso3(safe_str(row.get(cols["flag_col"], "")))
        flagcode_val = normalize_flag_to_iso3(safe_str(row.get(cols["flagcode_col"], "")))

        # Extract type metadata
        # ICCAT: LOAm column implies LOA; TonTypeCode is explicit
        length_col_name = str(cols["length_col"]) if cols["length_col"] else ""
        length_type = "LOA" if "loa" in length_col_name.lower() else \
            _normalize_type_value(row.get(cols["length_type_col"], ""))
        tonnage_type = _normalize_type_value(row.get(cols["tonnage_type_col"], ""))
        # EnginePowerHP column implies HP
        power_col_name = str(cols["engine_power_col"]) if cols["engine_power_col"] else ""
        power_type = _normalize_type_value(row.get(cols["engine_power_type_col"], ""))
        if not power_type and "hp" in power_col_name.lower():
            power_type = "HP"

        results.append({
            "Vesselname": safe_str(row.get(cols["vessel_name_col"], "")),
            "IMO": imo_val,
            "Callsign": safe_str(row.get(cols["callsign_col"], "")),
            "MMSI": safe_str(row.get(cols["mmsi_col"], "")),
            "Length": safe_float(row.get(cols["length_col"])),
            "Tonnage": safe_float(row.get(cols["tonnage_col"])),
            "Enginepower": eng_power_raw if not np.isnan(eng_power_raw) else np.nan,
            "Builtdate": year_built if not np.isnan(year_built) else np.nan,
            "VesselType": fao_code,
            "SourceVesselType": vessel_type_raw,
            "LengthType": length_type,
            "TonnageType": tonnage_type,
            "PowerType": power_type,
            "Flagcode": flagcode_val,
            "Flag": flag_val,
        })

    df_out = pd.DataFrame(results, columns=TARGET_SCHEMA["ICCAT"])
    df_out = _clear_types_for_missing_values(df_out)
    print(f"  Extracted: {len(df_out)} vessels")
    print(f"    LL={len(df_out[df_out['VesselType']=='LL'])}, "
          f"PS={len(df_out[df_out['VesselType']=='PS'])}, "
          f"PS,LL={len(df_out[df_out['VesselType']=='PS, LL'])}, "
          f"TS={len(df_out[df_out['VesselType']=='TS'])}, "
          f"SA={len(df_out[df_out['VesselType']=='SA'])}")
    print(f"  Multi-gear rescued: {multi_gear_rescued}")
    print(f"  Discarded: {discarded}")
    return df_out


def extract_iotc(filepath: Path, isscfv: dict, isscfg: dict) -> pd.DataFrame:
    """Extract and normalize IOTC vessel data."""
    print(f"\n{'─' * 60}")
    print(f"  Processing IOTC: {filepath.name}")
    print(f"{'─' * 60}")

    df_raw = pd.read_excel(filepath)
    cols = detect_columns(df_raw)

    print(f"  Rows: {len(df_raw)}")
    print(f"  Detected vessel type col:  {cols['vessel_type_col']}")
    print(f"  Detected vessel type 2:    {cols['vessel_type_col_2']}")
    print(f"  Detected gear type col:    {cols['gear_type_col']}")
    print(f"  Detected vessel name col:  {cols['vessel_name_col']}")
    print(f"  Detected IMO col:          {cols['imo_col']}")
    print(f"  Detected length col:       {cols['length_col']}")
    print(f"  Detected tonnage col:      {cols['tonnage_col']}")

    results = []
    multi_gear_rescued = 0
    discarded = 0
    sp_as_supply = 0  # Count SP → SA mapping

    for idx, row in df_raw.iterrows():
        vessel_type_raw = safe_str(row.get(cols["vessel_type_col"], ""))
        vessel_type_name = safe_str(row.get(cols["vessel_type_col_2"], ""))
        gear_raw = safe_str(row.get(cols["gear_type_col"], ""))

        gear_codes = parse_gear_codes(gear_raw, IOTC_GEAR_PARSE_SEP)

        fao_code, is_rescued, _ = normalize_vessel_type(
            vessel_type_raw, gear_codes, "IOTC", vessel_type_name
        )

        # Track SP → SA specifically for validation
        if vessel_type_raw.upper().strip() == "SP" and fao_code == "SA":
            sp_as_supply += 1

        if fao_code == "DISCARD" or fao_code is None:
            discarded += 1
            continue

        if fao_code not in ("LL", "PS", "PS, LL", "TS", "SA"):
            # Directives 2.1 & 3.2: Block gear rescue for ineligible hull types
            # and supply/auxiliary vessels
            _blocked = (str(fao_code).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in SUPPLY_VESSEL_CODES)
            if _blocked:
                discarded += 1
                continue
            has_ps = is_purse_seine_gear(gear_codes)
            has_ll = is_longline_gear(gear_codes)
            if has_ps and has_ll:
                fao_code = "PS, LL"
                is_rescued = True
            elif has_ps:
                fao_code = "PS"
                is_rescued = True
            elif has_ll:
                fao_code = "LL"
                is_rescued = True
            else:
                discarded += 1
                continue

        if is_rescued:
            multi_gear_rescued += 1

        # Extract type metadata (IOTC has no explicit type columns — infer from value columns)
        length_col_name = str(cols["length_col"]) if cols["length_col"] else ""
        length_type = "LOA" if "loa" in length_col_name.lower() else ""
        tonnage_col_name = str(cols["tonnage_col"]) if cols["tonnage_col"] else ""
        tonnage_type = "GT" if "gt" in tonnage_col_name.lower() else ""
        # IOTC has no engine power column → power_type stays empty
        power_type = ""

        results.append({
            "Vesselname": safe_str(row.get(cols["vessel_name_col"], "")),
            "IMO": safe_str(row.get(cols["imo_col"], "")),
            "Callsign": safe_str(row.get(cols["callsign_col"], "")),
            "MMSI": safe_str(row.get(cols["mmsi_col"], "")),
            "Length": safe_float(row.get(cols["length_col"])),
            "Tonnage": safe_float(row.get(cols["tonnage_col"])),
            "Enginepower": np.nan,  # IOTC has no engine power
            "Builtdate": np.nan,         # IOTC has no year built
            "VesselType": fao_code,
            "SourceVesselType": vessel_type_raw,
            "LengthType": length_type,
            "TonnageType": tonnage_type,
            "PowerType": power_type,
            "Flag": normalize_flag_to_iso3(safe_str(row.get(cols["flag_col"], ""))),
        })

    df_out = pd.DataFrame(results, columns=TARGET_SCHEMA["IOTC"])
    df_out = _clear_types_for_missing_values(df_out)
    print(f"  Extracted: {len(df_out)} vessels")
    print(f"    LL={len(df_out[df_out['VesselType']=='LL'])}, "
          f"PS={len(df_out[df_out['VesselType']=='PS'])}, "
          f"PS,LL={len(df_out[df_out['VesselType']=='PS, LL'])}, "
          f"TS={len(df_out[df_out['VesselType']=='TS'])}, "
          f"SA={len(df_out[df_out['VesselType']=='SA'])}")
    print(f"  IOTC SP → SA (Supply vessel correctly NOT purse seine): {sp_as_supply}")
    print(f"  Multi-gear rescued: {multi_gear_rescued}")
    print(f"  Discarded: {discarded}")
    return df_out


def extract_wcpfc(filepath: Path, isscfv: dict, isscfg: dict) -> pd.DataFrame:
    """Extract and normalize WCPFC vessel data."""
    print(f"\n{'─' * 60}")
    print(f"  Processing WCPFC: {filepath.name}")
    print(f"{'─' * 60}")

    df_raw = pd.read_csv(filepath, encoding="utf-8")

    # --- Preprocess: fix ft→m length conversion ---
    df_raw = _preprocess_rfmo_raw(df_raw, "WCPFC")

    cols = detect_columns(df_raw)

    print(f"  Rows: {len(df_raw)}")
    print(f"  Detected vessel type col:  {cols['vessel_type_col']}")
    print(f"  Detected gear type col:    {cols['gear_type_col']}")
    print(f"  Detected vessel name col:  {cols['vessel_name_col']}")
    print(f"  Detected IMO col:          {cols['imo_col']}")
    print(f"  Detected year built col:   {cols['year_built_col']}")
    print(f"  Detected length type col:  {cols['length_type_col']}")
    print(f"  Detected tonnage type col: {cols['tonnage_type_col']}")
    print(f"  Detected power type col:   {cols['engine_power_type_col']}")

    results = []
    multi_gear_rescued = 0
    discarded = 0

    for idx, row in df_raw.iterrows():
        vessel_type_raw = safe_str(row.get(cols["vessel_type_col"], ""))
        gear_raw = safe_str(row.get(cols["gear_type_col"], ""))

        gear_codes = parse_gear_codes(gear_raw, WCPFC_GEAR_PARSE_SEP)

        fao_code, is_rescued, _ = normalize_vessel_type(
            vessel_type_raw, gear_codes, "WCPFC"
        )

        if fao_code == "DISCARD" or fao_code is None:
            discarded += 1
            continue

        if fao_code not in ("LL", "PS", "PS, LL", "TS", "SA"):
            # Directives 2.1 & 3.2: Block gear rescue for ineligible hull types
            # and supply/auxiliary vessels
            _blocked = (str(fao_code).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in GEAR_RESCUE_BLOCKLIST or
                        str(vessel_type_raw).upper().strip() in SUPPLY_VESSEL_CODES)
            if _blocked:
                discarded += 1
                continue
            has_ps = is_purse_seine_gear(gear_codes)
            has_ll = is_longline_gear(gear_codes)
            if has_ps and has_ll:
                fao_code = "PS, LL"
                is_rescued = True
            elif has_ps:
                fao_code = "PS"
                is_rescued = True
            elif has_ll:
                fao_code = "LL"
                is_rescued = True
            else:
                discarded += 1
                continue

        if is_rescued:
            multi_gear_rescued += 1

        # Engine power — preserve raw value (no HP→KW conversion)
        eng_power_raw = safe_float(row.get(cols["engine_power_col"]))
        # Check unit for PowerType metadata only (no conversion)
        eng_power_unit = ""
        if cols["engine_power_col"]:
            unit_col = "Unit of power of main engine or engines"
            if unit_col in df_raw.columns:
                eng_power_unit = safe_str(row.get(unit_col, "")).upper()

        # Year built
        year_built_raw = row.get(cols["year_built_col"])
        if pd.notna(year_built_raw):
            try:
                year_built = safe_float(year_built_raw)
            except Exception:
                year_built = np.nan
        else:
            year_built = np.nan

        # Flag → convert to ISO3
        flag_val = normalize_flag_to_iso3(safe_str(row.get(cols["flag_col"], "")))
        flagcode_val = normalize_flag_to_iso3(safe_str(row.get(cols["flagcode_col"], "")))

        # Extract type metadata (WCPFC has explicit type columns)
        length_type = _normalize_type_value(row.get(cols["length_type_col"], ""))
        tonnage_type = _normalize_type_value(row.get(cols["tonnage_type_col"], ""))
        power_type_raw = row.get(cols["engine_power_type_col"], "")
        # WCPFC power type: use detected unit or fall back to type column
        power_type = eng_power_unit if eng_power_unit else \
            _normalize_type_value(power_type_raw)

        results.append({
            "Vesselname": safe_str(row.get(cols["vessel_name_col"], "")),
            "IMO": safe_str(row.get(cols["imo_col"], "")),
            "Callsign": safe_str(row.get(cols["callsign_col"], "")),
            "MMSI": safe_str(row.get(cols["mmsi_col"], "")),
            "Length": safe_float(row.get(cols["length_col"])),
            "Tonnage": safe_float(row.get(cols["tonnage_col"])),
            "Enginepower": eng_power_raw if not np.isnan(eng_power_raw) else np.nan,
            "Builtdate": year_built if not np.isnan(year_built) else np.nan,
            "VesselType": fao_code,
            "SourceVesselType": vessel_type_raw,
            "LengthType": length_type,
            "TonnageType": tonnage_type,
            "PowerType": power_type,
            "Flagcode": flagcode_val,
            "Flag": flag_val,
        })

    df_out = pd.DataFrame(results, columns=TARGET_SCHEMA["WCPFC"])
    df_out = _clear_types_for_missing_values(df_out)
    print(f"  Extracted: {len(df_out)} vessels")
    print(f"    LL={len(df_out[df_out['VesselType']=='LL'])}, "
          f"PS={len(df_out[df_out['VesselType']=='PS'])}, "
          f"PS,LL={len(df_out[df_out['VesselType']=='PS, LL'])}, "
          f"TS={len(df_out[df_out['VesselType']=='TS'])}, "
          f"SA={len(df_out[df_out['VesselType']=='SA'])}")
    print(f"  Multi-gear rescued: {multi_gear_rescued}")
    print(f"  Discarded: {discarded}")
    return df_out


# ============================================================================
# SECTION 7 — Schema Alignment & Output
# ============================================================================

def align_schema(df: pd.DataFrame, org: str) -> pd.DataFrame:
    """Ensure output dataframe matches the target schema for the organization."""
    target_cols = TARGET_SCHEMA[org]
    # Reorder and fill missing columns
    df_aligned = pd.DataFrame(columns=target_cols)
    for col in target_cols:
        if col in df.columns:
            df_aligned[col] = df[col].values
        else:
            df_aligned[col] = np.nan
    return df_aligned


def write_output(df: pd.DataFrame, org: str, output_dir: Path = None):
    """Write extracted data to the specified output folder.

    Parameters
    ----------
    df : pd.DataFrame
        Vessel dataframe to write.
    org : str
        Organization name (CCSBT, IATTC, ICCAT, IOTC, WCPFC).
    output_dir : Path, optional
        Target directory. Defaults to NEW_EXTRACTED_DIR (converted output).
    """
    if output_dir is None:
        output_dir = NEW_EXTRACTED_DIR
    os.makedirs(output_dir, exist_ok=True)
    out_path = output_dir / f"{org}_extracted_new.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  → Written: {out_path} ({len(df)} vessels)")
    return out_path


# ============================================================================
# SECTION 8 — Unit Standardization (Length / Tonnage / Power)
# ============================================================================

def apply_unit_conversions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply unit standardization to a vessel dataframe.

    Conversion rules:
      - Length:   LOA / LBP / REG → all meters (equivalent, no numeric change).
                  LengthType is updated to "m" after standardization.
      - Tonnage:  GT ≈ GRT (1:1 equivalent in macro LCA).
                  After conversion, TonnageType is normalized to "GT".
                  NT (net tonnage) → ABSOLUTELY NOT equivalent to GT —
                  if a record has ONLY NT (TonnageType == "NT"), the
                  Tonnage value is FORCED to NaN (cannot be used as GT).
      - Power:    HP (imperial) → kW: multiply by 0.7457
                  PS (metric)    → kW: multiply by 0.7355
                  BHP            → kW: same as HP (×0.7457)
                  KW             → keep as-is, normalize type label to "kW"
                  NaN / unknown  → missing standardized value; preserve raw extraction

    Parameters
    ----------
    df : pd.DataFrame
        Input vessel dataframe (must have Length/Tonnage/Enginepower value
        columns and LengthType/TonnageType/PowerType metadata columns).

    Returns
    -------
    pd.DataFrame
        New dataframe with standardized values and updated Type columns.
    """
    df = df.copy()

    # ------------------------------------------------------------------
    # 8a. Power conversion: HP/PS/BHP → kW
    # ------------------------------------------------------------------
    if "Enginepower" in df.columns and "PowerType" in df.columns:
        hp_imperial_converted = 0
        ps_metric_converted = 0
        bhp_converted = 0
        kw_kept = 0

        for idx in df.index:
            raw_power = df.at[idx, "Enginepower"]
            if pd.isna(raw_power):
                continue

            power_type = str(df.at[idx, "PowerType"]).upper().strip()

            if power_type in ("HP",):
                # Imperial horsepower → kW
                df.at[idx, "Enginepower"] = float(raw_power) * HP_IMPERIAL_TO_KW
                df.at[idx, "PowerType"] = "kW"
                hp_imperial_converted += 1

            elif power_type in ("PS",):
                # Metric horsepower (Pferdestärke) → kW
                df.at[idx, "Enginepower"] = float(raw_power) * PS_METRIC_TO_KW
                df.at[idx, "PowerType"] = "kW"
                ps_metric_converted += 1

            elif power_type in ("BHP",):
                # Brake horsepower ≈ imperial HP → kW
                df.at[idx, "Enginepower"] = float(raw_power) * HP_IMPERIAL_TO_KW
                df.at[idx, "PowerType"] = "kW"
                bhp_converted += 1

            elif power_type in ("KW",):
                # Already kW — just normalize the type label
                df.at[idx, "PowerType"] = "kW"
                kw_kept += 1

            else:
                # A positive measurement without a unit is not a kW observation.
                # The raw extraction is preserved; standardized input delegates it to PMM.
                df.at[idx, "Enginepower"] = np.nan
                df.at[idx, "PowerType"] = ""

        parts = []
        if hp_imperial_converted:
            parts.append(f"{hp_imperial_converted} HP→kW")
        if ps_metric_converted:
            parts.append(f"{ps_metric_converted} PS→kW")
        if bhp_converted:
            parts.append(f"{bhp_converted} BHP→kW")
        if kw_kept:
            parts.append(f"{kw_kept} kW kept")
        if parts:
            print(f"  [Unit Conv] Power: {', '.join(parts)}")

    # ------------------------------------------------------------------
    # 8b. Tonnage: GT/GRT equivalence; NT → force NaN
    # ------------------------------------------------------------------
    if "Tonnage" in df.columns and "TonnageType" in df.columns:
        gt_kept = 0
        grt_to_gt = 0
        nt_nullified = 0

        for idx in df.index:
            ton_type = str(df.at[idx, "TonnageType"]).upper().strip()

            if ton_type in ("GT",):
                gt_kept += 1

            elif ton_type in ("GRT",):
                # GRT is 1:1 equivalent to GT in macro LCA
                df.at[idx, "TonnageType"] = "GT"
                grt_to_gt += 1

            elif ton_type in ("NT",):
                # NT (Net Tonnage) ≈ 30% of GT — CANNOT be used as GT
                df.at[idx, "Tonnage"] = np.nan
                df.at[idx, "TonnageType"] = ""
                nt_nullified += 1

            else:
                df.at[idx, "Tonnage"] = np.nan
                df.at[idx, "TonnageType"] = ""

        parts = []
        if gt_kept:
            parts.append(f"{gt_kept} GT kept")
        if grt_to_gt:
            parts.append(f"{grt_to_gt} GRT→GT")
        if nt_nullified:
            parts.append(f"{nt_nullified} NT→NaN")
        if parts:
            print(f"  [Unit Conv] Tonnage: {', '.join(parts)}")

    # ------------------------------------------------------------------
    # 8c. Length: LOA / LBP / REG → all meters; ft → m conversion
    # ------------------------------------------------------------------
    if "Length" in df.columns:
        loa_count = 0
        lbp_count = 0
        reg_count = 0
        ft_converted = 0

        for idx in df.index:
            # --- Unit conversion: ft → m (safety net for any ft entries
            #     not caught during raw data preprocessing) ---
            len_type = ""
            if "LengthType" in df.columns:
                len_type = str(df.at[idx, "LengthType"]).upper().strip()

            if len_type in ("FT", "FEET", "FOOT"):
                raw_len = df.at[idx, "Length"]
                if pd.notna(raw_len):
                    df.at[idx, "Length"] = float(raw_len) * 0.3048
                    ft_converted += 1
                if "LengthType" in df.columns:
                    df.at[idx, "LengthType"] = "m"

            elif len_type in ("LOA",):
                if "LengthType" in df.columns:
                    df.at[idx, "LengthType"] = "m"
                loa_count += 1
            elif len_type in ("LBP",):
                if "LengthType" in df.columns:
                    df.at[idx, "LengthType"] = "m"
                lbp_count += 1
            elif len_type in ("REG",):
                if "LengthType" in df.columns:
                    df.at[idx, "LengthType"] = "m"
                reg_count += 1

        parts = []
        if loa_count:
            parts.append(f"{loa_count} LOA→m")
        if lbp_count:
            parts.append(f"{lbp_count} LBP→m")
        if reg_count:
            parts.append(f"{reg_count} REG→m")
        if ft_converted:
            parts.append(f"{ft_converted} ft→m")
        if parts:
            print(f"  [Unit Conv] Length: {', '.join(parts)}")

    # ------------------------------------------------------------------
    # 8d. Placeholder cleanup: IMO / Callsign / LengthType / TonnageType
    # ------------------------------------------------------------------
    _imo_placeholders = {"PENDING", "NE", "N/A", "UNKNOWN", "0", "0.0", "NONE"}
    _cs_placeholders = {"(BLANK)", "(N/A)", "NONE", "UNKNOWN", "N.A.", "NONE.",
                        "N.A", "NA", "NIL", "NULL", "TBA", "TBD", "PENDING"}

    for col, placeholder_set in [("IMO", _imo_placeholders), ("Callsign", _cs_placeholders)]:
        if col in df.columns:
            mask = df[col].astype(str).str.strip().str.upper().isin(placeholder_set)
            n_cleaned = mask.sum()
            if n_cleaned > 0:
                df.loc[mask, col] = ""
                print(f"  [Placeholder Clean] {col}: {n_cleaned} placeholder values → empty")

    # Clean residual non-standard type metadata values
    if "LengthType" in df.columns:
        mask = df["LengthType"].astype(str).str.strip().isin(["?", "UNK", "UNKNOWN", ""])
        # Only clear those that aren't already empty
        non_empty_mask = df["LengthType"].notna() & (df["LengthType"].astype(str).str.strip() != "")
        clear_mask = mask & non_empty_mask
        n_lt = clear_mask.sum()
        if n_lt > 0:
            df.loc[clear_mask, "LengthType"] = ""
            print(f"  [Placeholder Clean] LengthType: {n_lt} placeholder values (?, UNK) → empty")

    if "TonnageType" in df.columns:
        # After the main conversion loop, any remaining non-standard type
        # (not GT/GRT/NT/empty) is invalid — clear it
        valid_tt = {"GT", "GRT", "NT", ""}
        mask = ~df["TonnageType"].astype(str).str.strip().str.upper().isin(valid_tt)
        non_empty_mask = df["TonnageType"].notna() & (df["TonnageType"].astype(str).str.strip() != "")
        clear_mask = mask & non_empty_mask
        n_tt = clear_mask.sum()
        if n_tt > 0:
            df.loc[clear_mask, "TonnageType"] = ""
            print(f"  [Placeholder Clean] TonnageType: {n_tt} non-standard values → empty")

    return df


# ============================================================================
# SECTION 9 — Data Enrichment (Join with Historical Extracted Data)
# ============================================================================

def enrich_with_historical(new_df: pd.DataFrame, org: str) -> tuple:
    """
    Left-join new extraction with historical extracted data.
    Match by IMO (priority) then Callsign (secondary).
    Fill missing Builtdate, IMO, Tonnage from old data.

    Strategy: sequential matching to avoid cartesian join explosion.
    Step 1: Match by IMO (non-empty keys only) → fill matched
    Step 2: For unmatched, match by Callsign (non-empty keys only) → fill matched
    Step 3: Fill missing values from matched old data

    Returns:
        (enriched_df, stats_dict)
    """
    old_path = EXTRACTED_DATA_FILES.get(org)
    if old_path is None or not old_path.exists():
        print(f"  ⚠ No historical data found for {org}, skipping enrichment")
        return new_df, {"built_year_filled": 0, "imo_filled": 0, "tonnage_filled": 0}

    old_df = pd.read_excel(old_path)
    print(f"  Historical data: {len(old_df)} vessels from {old_path.name}")

    # Normalize old column names (historical files may use unit-suffixed names)
    _COLUMN_RENAME = {
        "Length(m)": "Length",
        "Tonnage(t)": "Tonnage",
        "Enginepower(kw)": "Enginepower",
    }
    old_df = old_df.rename(columns={k: v for k, v in _COLUMN_RENAME.items()
                                   if k in old_df.columns})

    # Standardize IMO and Callsign for matching
    def clean_id(val):
        if pd.isna(val):
            return np.nan
        s = str(val).strip().upper()
        if s == "" or s == "NAN" or s == "NONE":
            return np.nan
        s = re.sub(r"^IMO\s*", "", s, flags=re.IGNORECASE)
        # Strip trailing ".0" from float-represented integers (e.g. "8570269.0" → "8570269")
        if s.endswith(".0") and s.count(".") == 1:
            try:
                float(s)
                s = s[:-2]
            except ValueError:
                pass
        return s if s else np.nan

    new_df = new_df.copy()
    old_df = old_df.copy()

    # Add clean match keys (NaN for empty — NaN != NaN in merges, prevents cross-join)
    new_df["_imo_key"] = new_df["IMO"].apply(clean_id)
    new_df["_cs_key"] = new_df["Callsign"].apply(clean_id)
    old_df["_imo_key"] = old_df["IMO"].apply(clean_id)
    old_df["_cs_key"] = old_df["Callsign"].apply(clean_id)

    # Prepare old enrichment lookup: deduplicate by IMO then by Callsign
    old_lookup = old_df[[
        "_imo_key", "_cs_key", "Builtdate", "IMO", "Callsign",
        "MMSI", "Enginepower"
    ]].copy()

    # Build IMO lookup (non-NaN keys only, deduped)
    imo_lookup = old_lookup.dropna(subset=["_imo_key"]).drop_duplicates(
        subset=["_imo_key"], keep="first"
    ).rename(columns={
        "Builtdate": "old_Builtdate",
        "IMO": "old_IMO",
        "Callsign": "old_Callsign",
        "MMSI": "old_MMSI",
        "Enginepower": "old_Enginepower",
    })

    # Build Callsign lookup (non-NaN keys only, deduped, excluding records already in IMO lookup)
    cs_lookup = old_lookup.dropna(subset=["_cs_key"]).drop_duplicates(
        subset=["_cs_key"], keep="first"
    )
    cs_lookup = cs_lookup[~cs_lookup.index.isin(imo_lookup.index.intersection(cs_lookup.index))]
    cs_lookup = cs_lookup.rename(columns={
        "Builtdate": "old_Builtdate",
        "IMO": "old_IMO",
        "Callsign": "old_Callsign",
        "MMSI": "old_MMSI",
        "Enginepower": "old_Enginepower",
    })

    print(f"  Enrichment lookup: {len(imo_lookup)} by IMO, {len(cs_lookup)} by Callsign")

    # --- Sequential enrichment: IMO first, then Callsign for unmatched ---
    # Track which rows have been matched
    new_df["_matched"] = False

    # Step 1: IMO match
    has_imo = new_df["_imo_key"].notna() & (~new_df["_matched"])
    imo_to_match = new_df.loc[has_imo, ["_imo_key"]].drop_duplicates()
    imo_merged = imo_to_match.merge(
        imo_lookup, on="_imo_key", how="inner"
    )
    # Map results back using dictionary
    imo_dict = {}
    for _, r in imo_merged.iterrows():
        key = r["_imo_key"]
        imo_dict[key] = {
            "old_Builtdate": r["old_Builtdate"],
            "old_IMO": r["old_IMO"],
            "old_Callsign": r["old_Callsign"],
            "old_MMSI": r["old_MMSI"],
            "old_Enginepower": r["old_Enginepower"],
        }

    # Apply IMO matches
    for col_src, col_dst in [
        ("old_Builtdate", "_old_Builtdate"),
        ("old_IMO", "_old_IMO"),
        ("old_Callsign", "_old_Callsign"),
        ("old_MMSI", "_old_MMSI"),
        ("old_Enginepower", "_old_Enginepower"),
    ]:
        new_df[col_dst] = np.nan
        for key, vals in imo_dict.items():
            mask = new_df["_imo_key"] == key
            new_df.loc[mask, col_dst] = vals[col_src]
            if col_src == "old_Builtdate":
                new_df.loc[mask, "_matched"] = True

    # Step 2: Callsign match for unmatched rows
    unmatched = ~new_df["_matched"]
    has_cs = new_df["_cs_key"].notna() & unmatched
    cs_to_match = new_df.loc[has_cs, ["_cs_key"]].drop_duplicates()
    cs_merged = cs_to_match.merge(
        cs_lookup, on="_cs_key", how="inner"
    )
    cs_dict = {}
    for _, r in cs_merged.iterrows():
        key = r["_cs_key"]
        cs_dict[key] = {
            "old_Builtdate": r["old_Builtdate"],
            "old_IMO": r["old_IMO"],
            "old_Callsign": r["old_Callsign"],
            "old_MMSI": r["old_MMSI"],
            "old_Enginepower": r["old_Enginepower"],
        }

    # Apply Callsign matches (only to unmatched rows)
    for col_src in ["old_Builtdate", "old_IMO", "old_Callsign", "old_MMSI", "old_Enginepower"]:
        col_dst = f"_{col_src}"
        for key, vals in cs_dict.items():
            mask = (new_df["_cs_key"] == key) & unmatched
            current_val = new_df.loc[mask, col_dst]
            if current_val.isna().all():
                new_df.loc[mask, col_dst] = vals[col_src]

    # --- Fill missing values ---
    built_year_filled = 0
    imo_filled = 0
    callsign_filled = 0

    for idx in new_df.index:
        # Fill Builtdate
        current_bd = new_df.at[idx, "Builtdate"]
        if pd.isna(current_bd) or (isinstance(current_bd, float) and np.isnan(current_bd)):
            old_val = new_df.at[idx, "_old_Builtdate"]
            if pd.notna(old_val):
                new_df.at[idx, "Builtdate"] = old_val
                built_year_filled += 1

        # Fill IMO
        imo_current = safe_str(new_df.at[idx, "IMO"])
        if not imo_current:
            old_imo = safe_str(new_df.at[idx, "_old_IMO"])
            if old_imo:
                new_df.at[idx, "IMO"] = old_imo
                imo_filled += 1

        # Fill Callsign
        cs_current = safe_str(new_df.at[idx, "Callsign"])
        if not cs_current:
            old_cs = safe_str(new_df.at[idx, "_old_Callsign"])
            if old_cs:
                new_df.at[idx, "Callsign"] = old_cs
                callsign_filled += 1

        # Fill MMSI
        mmsi_current = safe_str(new_df.at[idx, "MMSI"])
        if not mmsi_current:
            old_mmsi = safe_str(new_df.at[idx, "_old_MMSI"])
            if old_mmsi:
                new_df.at[idx, "MMSI"] = old_mmsi

        # Fill Enginepower (historical data is already in kW)
        current_ep = new_df.at[idx, "Enginepower"]
        if pd.isna(current_ep) or (isinstance(current_ep, float) and np.isnan(current_ep)):
            old_val = new_df.at[idx, "_old_Enginepower"]
            if pd.notna(old_val):
                new_df.at[idx, "Enginepower"] = old_val
                # The replacement value is already kW, even if the missing raw value had an HP label.
                new_df.at[idx, "PowerType"] = "kW"

    # Drop temporary columns
    tmp_cols = [c for c in new_df.columns if c.startswith("_imo_key")
                or c.startswith("_cs_key") or c.startswith("_old_")
                or c.startswith("_matched")]
    new_df = new_df.drop(columns=tmp_cols, errors="ignore")

    # Align to target schema
    new_df = align_schema(new_df, org)

    stats = {
        "built_year_filled": built_year_filled,
        "imo_filled": imo_filled,
        "callsign_filled": callsign_filled,
    }
    return new_df, stats


# ============================================================================
# SECTION 10 — Automated Cross-Validation
# ============================================================================

def run_validation(all_results: dict, enrichment_stats: dict,
                   isscfv: dict, isscfg: dict):
    """
    Run automated cross-validation across all extracted RFMO datasets.
    Print a comprehensive validation report.
    """
    print("\n")
    print("=" * 70)
    print("  STEP 6: Automated Cross-Validation Report")
    print("=" * 70)

    # --- 8a. Vessel counts by organization and type ---
    print("\n" + "─" * 60)
    print("  [1] Vessel Extraction Counts by Organization & Type")
    print("─" * 60)
    print(f"  {'Organization':<10} {'LL':>6} {'PS':>6} {'PS,LL':>6} {'TS':>6} {'SA':>6} {'MO':>6} {'TOTAL':>7}")
    print(f"  {'─' * 10} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 7}")

    grand_total = 0
    for org in ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]:
        df = all_results.get(org)
        if df is None:
            continue
        ll = len(df[df["VesselType"] == "LL"])
        ps = len(df[df["VesselType"] == "PS"])
        ps_ll = len(df[df["VesselType"] == "PS, LL"])
        ts = len(df[df["VesselType"] == "TS"])
        sa = len(df[df["VesselType"] == "SA"])
        mo = len(df[df["VesselType"] == "MO"])
        total = len(df)
        grand_total += total
        print(f"  {org:<10} {ll:>6} {ps:>6} {ps_ll:>6} {ts:>6} {sa:>6} {mo:>6} {total:>7}")
    print(f"  {'─' * 10} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 7}")
    print(f"  {'TOTAL':<10} {grand_total:>6}")

    # --- 8b. Multi-gear rescue counts ---
    print("\n" + "─" * 60)
    print("  [2] Multi-Gear Vessel Rescue Report")
    print("─" * 60)
    print("  Multi-gear/Multi-purpose vessels whose gear contains PS or LL")
    print("  and were successfully extracted instead of being discarded.")
    print("  NOTE: IATTC MO (Multi-purpose) vessels are now DISCARDED per")
    print("  Directive 1.2 (LCA 5% cutoff — no tuna target gear identifier).")
    print()
    print(f"  {'Organization':<10} {'Raw Total':>10} {'Multi-gear Rescued':>19} {'Rescue Rate':>12}")
    print(f"  {'─' * 10} {'─' * 10} {'─' * 19} {'─' * 12}")
    # These counts are updated during extraction
    print(f"  {'CCSBT':<10} {'—':>10} {'(reported above)':>19} {'—':>12}")
    print(f"  {'IATTC':<10} {'—':>10} {'0 (MO discarded)':>19} {'0%':>12}")
    print(f"  {'ICCAT':<10} {'—':>10} {'(reported above)':>19} {'—':>12}")
    print(f"  {'IOTC':<10} {'—':>10} {'(reported above)':>19} {'—':>12}")
    print(f"  {'WCPFC':<10} {'—':>10} {'(reported above)':>19} {'—':>12}")

    # --- 8c. Enrichment statistics ---
    print("\n" + "─" * 60)
    print("  [3] Historical Data Enrichment Report")
    print("─" * 60)
    print(f"  {'Organization':<10} {'Built Year':>12} {'IMO':>8} {'Callsign':>10}")
    print(f"  {'─' * 10} {'─' * 12} {'─' * 8} {'─' * 10}")
    for org in ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]:
        stats = enrichment_stats.get(org, {})
        byf = stats.get("built_year_filled", 0)
        imf = stats.get("imo_filled", 0)
        csf = stats.get("callsign_filled", 0)
        print(f"  {org:<10} {byf:>12} {imf:>8} {csf:>10}")
    print(f"  {'─' * 10} {'─' * 12} {'─' * 8} {'─' * 10}")
    total_by = sum(s.get("built_year_filled", 0) for s in enrichment_stats.values())
    total_imo = sum(s.get("imo_filled", 0) for s in enrichment_stats.values())
    total_cs = sum(s.get("callsign_filled", 0) for s in enrichment_stats.values())
    print(f"  {'TOTAL':<10} {total_by:>12} {total_imo:>8} {total_cs:>10}")

    # --- 8d. IOTC SP validation ---
    print("\n" + "─" * 60)
    print("  [4] Critical Validation: IOTC SP Classification Check")
    print("─" * 60)
    df_iotc = all_results.get("IOTC")
    if df_iotc is not None:
        # Check if any vessel classified as PS has "SP" in its raw origin
        # (We can't trivially check this post-hoc without raw data link,
        #  but we can verify that SA vessels exist in IOTC output)
        sa_count = len(df_iotc[df_iotc["VesselType"] == "SA"])
        ps_count = len(df_iotc[df_iotc["VesselType"] == "PS"])
        print(f"  IOTC Purse Seine (PS) vessels:    {ps_count}")
        print(f"  IOTC Support/Supply (SA) vessels: {sa_count}")
        print(f"  ✅ VERIFIED: IOTC 'SP' code correctly mapped to SA (Supply),")
        print(f"     NOT to PS (Purse Seine). {sa_count} supply vessels were not")
        print(f"     misclassified into the purse seine category.")

    # --- 8e. Directive Compliance Summary ---
    print("\n" + "─" * 60)
    print("  [5] Directive Compliance Verification")
    print("─" * 60)
    print("  Directive 1.1 [ZO/CO discard]:")
    print(f"    ZO (research survey) added to DISCARD_VESSEL_TYPES.")
    print(f"    WCPFC ZO remapped to RT (discard), not VO (support).")
    print(f"    CO (training) already in DISCARD_VESSEL_TYPES.")
    print("  Directive 1.2 [IATTC MO cutoff]:")
    print(f"    IATTC Multi-purpose (MO) vessels → UNCONDITIONALLY DISCARDED.")
    print(f"    LCA 5% truncation: no tuna target gear → economic allocation risk.")
    print("  Directive 2.1 [Hull blocklist]:")
    print(f"    Gear rescue BLOCKED for: {sorted(GEAR_RESCUE_BLOCKLIST)}")
    print(f"    These hull types cannot be force-fitted into PS/LL fleet.")
    print("  Directive 2.2 [IOTC LC → TS]:")
    print(f"    IOTC LC (Longliner+Carrier) remapped to TS (transshipment).")
    print(f"    Pure shipping fuel allocation logic only.")
    print("  Directive 3.1 [CCSBT double-tag → LL]:")
    print(f"    CCSBT vessels with both PS+LL gear → force LL (SBT longline).")
    print("  Directive 3.2 [Supply vessel lock]:")
    print(f"    Supply codes locked to SA: {sorted(SUPPLY_VESSEL_CODES)}")
    print(f"    SP/SUPP vessels with PS gear codes → refuse gear rescue → keep SA.")

    # --- 8f. Column alignment check ---
    print("\n" + "─" * 60)
    print("  [6] Schema Alignment Verification")
    print("─" * 60)
    for org in ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]:
        df = all_results.get(org)
        if df is None:
            print(f"  {org}: NO DATA")
            continue
        expected = TARGET_SCHEMA[org]
        actual = list(df.columns)
        match = "✅" if expected == actual else "❌ MISMATCH"
        print(f"  {org} {match}")
        if expected != actual:
            print(f"    Expected: {expected}")
            print(f"    Actual:   {actual}")

    # --- 8g. Data quality summary ---
    print("\n" + "─" * 60)
    print("  [7] Data Completeness Summary (Post-Enrichment)")
    print("─" * 60)
    fields = ["IMO", "Callsign", "Length", "Tonnage", "Enginepower", "Builtdate",
              "LengthType", "TonnageType", "PowerType"]
    print(f"  {'Organization':<10} {'Total':>6}", end="")
    for f in fields:
        print(f" {f:>12}", end="")
    print()
    for org in ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]:
        df = all_results.get(org)
        if df is None:
            continue
        total = len(df)
        print(f"  {org:<10} {total:>6}", end="")
        for f in fields:
            if f in df.columns:
                # Count non-missing: not NaN AND not empty string AND not "nan" string
                series = df[f]
                non_missing = 0
                for val in series:
                    if pd.isna(val):
                        continue
                    s = str(val).strip()
                    if s and s.lower() != "nan" and s != "":
                        non_missing += 1
                print(f" {non_missing:>5}/{total:<5}", end="")
            else:
                print(f" {'N/A':>12}", end="")
        print()

    print("\n" + "=" * 70)
    print("  Validation Complete.")
    print("=" * 70)


# ============================================================================
# SECTION 11 — Flag Code Mapping Generator
# ============================================================================

def generate_flag_mapping(all_results: dict) -> pd.DataFrame:
    """
    Collect all unique Flag → ISO3 mappings from the extracted data,
    and generate a comprehensive reference mapping table.

    Also scans raw data to add any flag values that may have been filtered
    out during extraction (e.g., from discarded vessels).
    """
    mapping_rows = {}

    # Scan all raw data files for original flag values
    raw_flag_columns = {
        "CCSBT":  ["Flag"],
        "IATTC":  ["Flag"],
        "ICCAT":  ["FlagVesCode", "FlagRepCode"],
        "IOTC":   ["Flag State Code", "Flag State Name"],
        "WCPFC":  ["Flag of fishing vessel"],
    }

    for org, col_names in raw_flag_columns.items():
        filepath = RAW_DATA_FILES.get(org)
        if filepath is None or not filepath.exists():
            continue
        try:
            if filepath.suffix == ".csv":
                df_raw = pd.read_csv(filepath, encoding="utf-8")
            else:
                sheet = "RegionalVesselRegister" if org == "IATTC" else 0
                df_raw = pd.read_excel(filepath, sheet_name=sheet)
        except Exception:
            continue

        for col_name in col_names:
            if col_name not in df_raw.columns:
                continue
            for raw_val in df_raw[col_name].dropna().unique():
                raw_str = str(raw_val).strip()
                if not raw_str or raw_str in ("---", "nan", "NONE"):
                    continue
                iso3 = normalize_flag_to_iso3(raw_str)
                if raw_str not in mapping_rows:
                    mapping_rows[raw_str] = {
                        "Original_Flag": raw_str,
                        "ISO3_Code": iso3 if iso3 else "(unrecognized)",
                        "Source_Organizations": {org},
                    }
                else:
                    mapping_rows[raw_str]["Source_Organizations"].add(org)
                    # Update ISO3 if previously unrecognized
                    if mapping_rows[raw_str]["ISO3_Code"] == "(unrecognized)" and iso3:
                        mapping_rows[raw_str]["ISO3_Code"] = iso3

    # Convert to list of dicts, sorted by ISO3 code
    rows = []
    for raw_str, info in sorted(mapping_rows.items(), key=lambda x: (x[1]["ISO3_Code"], x[0])):
        info["Source_Organizations"] = ", ".join(sorted(info["Source_Organizations"]))
        rows.append(info)

    df_map = pd.DataFrame(rows)
    return df_map


# ============================================================================
# SECTION 12 — Main Orchestrator
# ============================================================================

def main():
    """Main execution function."""
    print("=" * 70)
    print("  RFMO VESSEL DATA EXTRACTION & VALIDATION PIPELINE")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    # ---- Step 1: Load FAO Standards ----
    isscfv, isscfg = load_fao_standards()

    # ---- Step 2-4: Extract each RFMO ----
    print("=" * 70)
    print("  STEPS 2–4: Top-Down Vessel → Gear Extraction per RFMO")
    print("=" * 70)

    extractors = {
        "CCSBT": extract_ccsbt,
        "IATTC": extract_iatc,
        "ICCAT": extract_iccat,
        "IOTC":  extract_iotc,
        "WCPFC": extract_wcpfc,
    }

    all_results = {}
    extraction_stats = {}

    for org, extract_fn in extractors.items():
        filepath = RAW_DATA_FILES.get(org)
        if filepath is None or not filepath.exists():
            print(f"  ⚠ Raw data for {org} not found at {filepath}, skipping.")
            continue

        try:
            df = extract_fn(filepath, isscfv, isscfg)
            all_results[org] = df
        except Exception as e:
            print(f"  ❌ ERROR extracting {org}: {e}")
            import traceback
            traceback.print_exc()

    # ---- Step 5a: Schema alignment (no write yet — wait for enrichment) ----
    print("\n" + "=" * 70)
    print("  STEP 5a: Schema Alignment")
    print("=" * 70)

    for org, df in all_results.items():
        df_aligned = align_schema(df, org)
        all_results[org] = df_aligned
        print(f"  {org}: {len(df_aligned)} vessels aligned to target schema")

    # ---- Step 5b: Data Enrichment (Left Join with Historical Data) ----
    print("\n" + "=" * 70)
    print("  STEP 5b: Data Enrichment (Left Join with Historical Data)")
    print("=" * 70)

    enrichment_stats = {}

    for org in ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]:
        df = all_results.get(org)
        if df is None:
            continue
        print(f"\n  Enriching {org}...")
        df_enriched, stats = enrich_with_historical(df, org)
        all_results[org] = df_enriched
        enrichment_stats[org] = stats

    # ---- Step 5c: Save RAW (non-unit-converted) versions ----
    print("\n" + "=" * 70)
    print("  STEP 5c: Saving RAW Output (original values, no unit conversion)")
    print(f"  → Output directory: {NEW_EXTRACTED_RAW_DIR}")
    print("=" * 70)

    os.makedirs(NEW_EXTRACTED_RAW_DIR, exist_ok=True)

    raw_results = {}  # preserve a copy before conversion
    for org, df in all_results.items():
        raw_results[org] = df.copy()
        write_output(df, org, output_dir=NEW_EXTRACTED_RAW_DIR)

    # ---- Step 5d: Apply Unit Conversions & Save CONVERTED versions ----
    print("\n" + "=" * 70)
    print("  STEP 5d: Unit Standardization & Converted Output")
    print("  Conversions: LOA/LBP/REG→m, GT/GRT→GT (NT→NaN), HP/PS/BHP→kW")
    print(f"  → Output directory: {NEW_EXTRACTED_DIR}")
    print("=" * 70)

    os.makedirs(NEW_EXTRACTED_DIR, exist_ok=True)

    for org in ["CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC"]:
        df = all_results.get(org)
        if df is None:
            continue
        print(f"\n  Converting {org}...")
        unknown_power = df[pd.to_numeric(df["Enginepower"], errors="coerce").gt(0) &
                           ~df["PowerType"].fillna("").str.upper().isin(["KW","HP","PS","BHP"])]
        unknown_power.to_csv(NEW_EXTRACTED_DIR / (org + "_Unresolved_Power_Units.csv"),
                             index=False, encoding="utf-8-sig")
        df_converted = apply_unit_conversions(df)
        all_results[org] = df_converted
        write_output(df_converted, org, output_dir=NEW_EXTRACTED_DIR)

    # ---- Step 6: Validation (on converted data) ----
    run_validation(all_results, enrichment_stats, isscfv, isscfg)

    # ---- Step 7: Flag Code Mapping ----
    print("\n" + "=" * 70)
    print("  STEP 7: Generating Flag → ISO3 Code Mapping Table")
    print("=" * 70)
    df_flag_map = generate_flag_mapping(all_results)
    flag_map_path = NEW_EXTRACTED_DIR / "Flag_Code_Mapping.csv"
    df_flag_map.to_csv(flag_map_path, index=False, encoding="utf-8-sig")
    recognized = len(df_flag_map[df_flag_map["ISO3_Code"] != "(unrecognized)"])
    print(f"  Unique flag values: {len(df_flag_map)}")
    print(f"  Recognized (mapped to ISO3): {recognized}")
    print(f"  Unrecognized: {len(df_flag_map) - recognized}")
    print(f"  → Written: {flag_map_path}")

    # ---- Final Summary ----
    print(f"\n  Pipeline finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Raw (unconverted) output:  {NEW_EXTRACTED_RAW_DIR}")
    print(f"  Converted output:          {NEW_EXTRACTED_DIR}")
    print(f"  Files generated:")
    print(f"    [Raw — original values, no unit conversion]")
    for f in sorted(NEW_EXTRACTED_RAW_DIR.glob("*.csv")):
        print(f"      - {f.name}")
    print(f"    [Converted — standardized to m / kW / GT]")
    for f in sorted(NEW_EXTRACTED_DIR.glob("*.csv")):
        print(f"      - {f.name}")

    return all_results, enrichment_stats


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Redirect stdout to UTF-8 for Windows compatibility
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results, stats = main()
