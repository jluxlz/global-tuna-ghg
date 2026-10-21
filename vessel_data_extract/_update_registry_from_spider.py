#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
_update_registry_from_spider.py
=============================================================================
Use spider Crawling Data Update Unified_Vessel_Registry.csv Physical parameters of the. 

Match Policy (Two-tier system of trust) : 
  IMO Dock (Absolutely) : 
    - Just spider Through IMO Got the data, Update Directly Builtdate, Tonnage, MMSI. 
    - IMO Its the only number that binds the hull for life, There is no risk of mismatching. 

  Callsign Threads (Cross Authentication) : 
    - ♪ When only through ♪ Callsign Match spider Data while, The following verification is required: 
      1. Type of ship/Compatibility check for type of operation (Exclude call signs from the wrong match) 
      2. Total tonnage tolerance check (±20%) 
    - Both of them → update; Any Failed → Discard. 

Update Scope (spider Available Fields) : 
  - Builtdate    : year built (Maritime database authoritative values) 
  - Tonnage      : gross tonnage GT
  - MMSI         : Water mobile communications operations identification code
  - VesselType   : From spider The details of the ships reverse thrust (Fishing Vessel→LL/PS, Cargo→TS) 

Do not update field (spider No corresponding data) : 
  - Length, Enginepower (spider none LOA and kW Data) 
  - Callsign, IMO (These are the matching keys, Do Not Cover From External) 
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
# Global Configuration
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
SPIDER_DIR = BASE_DIR.parent / "spider" / "output"
REGISTRY_PATH = BASE_DIR / "Unified_Vessel_Registry.csv"
OUTPUT_PATH = BASE_DIR / "Unified_Vessel_Registry.csv"  # Direct Overwrite

# spider Output file
SPIDER_FILES = [
    "CCSBT_extracted_new_result.xlsx",
    "IATTC_extracted_new_result.xlsx",
    "ICCAT_extracted_new_result.xlsx",
    "IOTC_extracted_new_result.xlsx",
    "WCPFC_extracted_new_result.xlsx",
]

# GT Portfolio threshold (Callsign Use when matching) 
GT_TOLERANCE = 0.20  # ±20%

# =============================================================================
# Ship Compatibility Map
# =============================================================================

# spider Detailed Type of Ship → Is it compatible with our register of fishing vessels?
# True  = Compatibility (It could be our fishing boat/Refrigerated transport vessels) 
# False = Incompatible (Its clearly other types of ships, The call signs been re-used) 
SHIP_TYPE_COMPATIBLE = {
    # --- Compatibility: Fishing vessels and fisheries-related ---
    "Fishing Vessel": True,
    "Fish Carrier": True,
    "Fish Factory Ship": True,
    "Fishery Support Vessel": True,
    "Fishery Research Vessel": True,
    "Fishery Patrol Vessel": True,
    "Fish Farm Support Vessel": True,

    # --- Compatibility: Refrigerated transport vessels (Tuna trans-shipment vessels)  ---
    "Refrigerated Cargo Ship": True,

    # --- Compatibility: General-purpose freighter (Its probably a small, mixed fishing boat)  ---
    # Non Autocompatibility, We need to make further judgements

    # --- Incompatible: Apparently not a fishing boat ---
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
    Inspection spider Is the boat crawling with our web set?/Compatibility of ship types. 

    spider_ship_type: Detailed types of ships in the maritime database (Like "Fishing Vessel") 
    our_gear_type: In our register VesselType (LL/PS/TS/SA/OTHER) 

    Back True For Compatibility, You can trust it spider Data. 
    """
    if not spider_ship_type or pd.isna(spider_ship_type):
        return True  # No ship-type information → Not ruled out (Conservative Release, Dependencies GT I dont think so) 

    st = str(spider_ship_type).strip()

    # Accurate matching of known types
    if st in SHIP_TYPE_COMPATIBLE:
        return SHIP_TYPE_COMPATIBLE[st]

    # Unknown type → Fuzzy Match (Conservative Release) 
    # Organisation "Fish" → Compatibility
    if "FISH" in st.upper():
        return True
    # Organisation "Cargo/Passenger/General" → Im not sure, Free but Mark
    # Contains apparently incompatible terms → Reject
    incompatible_keywords = [
        "TANKER", "BULK", "CONTAINER", "PASSENGER", "CRUISE",
        "YACHT", "DRILL", "FPSO", "FRIGATE", "DESTROYER",
        "SUBMARINE", "AIRCRAFT", "CORVETTE", "MINE",
        "TROOP", "LANDING CRAFT", "DREDGER", "HOPPER",
    ]
    for kw in incompatible_keywords:
        if kw in st.upper():
            return False

    # Default release (Mark as manual review) 
    return None  # None = Im not sure, Yes GT I dont think so


def map_ship_type_to_gear(spider_ship_type: str) -> str:
    """
    From spider The details of the ship are pushing us backwards VesselType. 

    Fishing Vessel → Keep the original VesselType No change (LL or PS Depends on other information) 
    Refrigerated Cargo Ship / Fish Carrier → TS (Transshipment)
    """
    if not spider_ship_type or pd.isna(spider_ship_type):
        return None

    st = str(spider_ship_type).strip().upper()

    if "REFRIGERATED" in st or "FISH CARRIER" in st or "FISH FACTORY" in st:
        return "TS"

    # Fishing Vessel → Do not change the original type
    return None


# =============================================================================
# Tool Functions
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
    """Safe turn float, Failed to return NaN. """
    if pd.isna(val) or val is None:
        return np.nan
    try:
        return float(val)
    except (ValueError, TypeError):
        return np.nan


# =============================================================================
# Main Update Logic
# =============================================================================

def load_spider_data() -> pd.DataFrame:
    """Load and pool all spider Output, Remove the required field. """
    print("=" * 70)
    print("  Load Spider Crawling Data")
    print("=" * 70)

    all_rows = []
    for fname in SPIDER_FILES:
        fpath = SPIDER_DIR / fname
        if not fpath.exists():
            print(f"  [Skip] File does not exist: {fname}")
            continue

        df = pd.read_excel(fpath)
        # Index to Columns (0-based) :
        # 0=Query Identification, 1=Original Line Number, 2=Name of ship(Enter), 3=IMO(Enter), 4=Call sign(Enter),
        # 5=MMSI, 6=Built_Date, 7=gross tonnage, 8=Detailed type of ship, 9=Name of ship(Fetch),
        # 10=Registration of ships, 11=Original year of construction, 12=Original total tons, 13=Matching of determinations,
        # 14=Wrong message, 15=Query note, 16=Manual query

        for _, row in df.iterrows():
            query_notes = safe_str(row.iloc[15])  # Query note
            imo_input = safe_imo(row.iloc[3])       # IMO(Enter)
            cs_input = safe_cs(row.iloc[4])         # Call sign(Enter)

            # Find out how to query: From query_notes First paragraph (" | " Before) Identification. 
            #   IMO:      *Query(IMO)Success*       → An anchor trust
            #   Callsign: *Query(CallSign)Success*   → Cross Authentication
            #   ShipName: *Query(ShipName)Success*   → Cross Authentication(Minimum)
            #   Its not working   → Skip
            # Notes: Can not get folder: %s: %s "(IMO)", Because Callsign of query_notes
            #     The second half contains "Query successful(IMO:|Call:xxx)" Itll match (IMO). 
            first_segment = query_notes.split("|")[0].strip() if "|" in query_notes else query_notes
            if "(IMO)" in first_segment:
                match_type = "IMO"
            elif "(CallSign)" in first_segment:
                match_type = "Callsign"
            elif "(ShipName)" in first_segment:
                match_type = "ShipName"
            else:
                # Query failed or failed → Skip
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
    print(f"  Always crawling records: {len(spider)}")
    print(f"    IMO Query successful: {(spider['match_type']=='IMO').sum()}")
    print(f"    Callsign Query successful: {(spider['match_type']=='Callsign').sum()}")
    print(f"    ShipName Query successful: {(spider['match_type']=='ShipName').sum()}")

    # Sort by Match: IMO > Callsign > ShipName
    # Same IMO/Callsign Only data from the most reliable sources are kept
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
    Use spider Data update registry. 

    Back: (Updated registry, Change Log DataFrame)
    """
    print("\n" + "=" * 70)
    print("  Update to Execute Parameter (IMO Dock + Callsign Cross Authentication) ")
    print("=" * 70)

    # ---- Build Spider Query Index ----
    # IMO Index: Reservation only IMO Query for successful data (Absolute trust anchor) 
    imo_index = {}
    for _, row in spider.iterrows():
        imo = row["imo_input"]
        if imo and row["match_type"] == "IMO" and imo not in imo_index:
            imo_index[imo] = row

    # Callsign Index: Organisation Callsign and ShipName Matching data (Cross-check required) 
    # ShipName Match here indexed by the name of the ship
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

    print(f"  IMO Index: {len(imo_index)} One IMO (Dock)")
    print(f"  Callsign Index: {len(cs_index)} One Callsign (Cross Authentication)")
    print(f"  ShipName Index: {len(name_index)} Its the only name of the ship (Cross Authentication)")

    # ---- Line-by-line processing of registries ----
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

        # --- First level: IMO Base point match ---
        if reg_imo and reg_imo in imo_index:
            spider_row = imo_index[reg_imo]
            match_method = "IMO_anchor"

        # --- Second level: Callsign Cross-check Match ---
        if spider_row is None and reg_cs and reg_cs in cs_index:
            candidates = cs_index[reg_cs]

            # Sort multiple candidates by matching type and quality, Try one by one
            for cand in candidates:
                spider_gt = safe_float(cand["tonnage_scraped"])
                spider_type = cand["ship_type_scraped"]

                # Verify 1: Compatibility of ship types
                type_ok = is_ship_type_compatible(spider_type, reg_vesseltype)

                # Verify 2: GT Portability
                gt_ok = True
                if (not np.isnan(reg_gt)) and (not np.isnan(spider_gt)) and reg_gt > 0:
                    ratio = spider_gt / reg_gt
                    gt_ok = (1 - GT_TOLERANCE) <= ratio <= (1 + GT_TOLERANCE)

                if type_ok == False:
                    # Clear incompatibility between the ships pattern
                    if not gt_ok:
                        updated_count["Callsign_rejected_both"] += 1
                        change_log.append({
                            "Vesselname": reg_name, "IMO": reg_imo, "Callsign": reg_cs,
                            "Flag": reg_flag,
                            "match_method": "Callsign_REJECTED",
                            "field": "ALL",
                            "old_value": f"GT={reg_gt}, Builtdate={reg_bd}",
                            "new_value": f"GT={spider_gt}, Builtdate={safe_float(cand['builtdate_scraped'])}",
                            "reason": f"Non-compatible ship({spider_type} vs {reg_vesseltype}) + GT Its a bad look"
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
                        "reason": f"Non-compatible ship: spider={spider_type}, registry={reg_vesseltype}"
                    })
                    continue

                if not gt_ok and type_ok != True:
                    # GT Its so bad and the ships not sure → Reject
                    updated_count["Callsign_rejected_gt"] += 1
                    change_log.append({
                        "Vesselname": reg_name, "IMO": reg_imo, "Callsign": reg_cs,
                        "Flag": reg_flag,
                        "match_method": "Callsign_REJECTED",
                        "field": "ALL",
                        "old_value": f"GT={reg_gt}, Builtdate={reg_bd}",
                        "new_value": f"GT={spider_gt}, Builtdate={safe_float(cand['builtdate_scraped'])}",
                        "reason": f"GT Its a bad look: {reg_gt}→{spider_gt} ({(spider_gt/reg_gt-1)*100:+.0f}%)"
                    })
                    continue

                if not gt_ok:
                    # Ship type compatible, but GT Its a bad look → Reject
                    updated_count["Callsign_rejected_gt"] += 1
                    change_log.append({
                        "Vesselname": reg_name, "IMO": reg_imo, "Callsign": reg_cs,
                        "Flag": reg_flag,
                        "match_method": "Callsign_REJECTED",
                        "field": "ALL",
                        "old_value": f"GT={reg_gt}, Builtdate={reg_bd}",
                        "new_value": f"GT={spider_gt}, Builtdate={safe_float(cand['builtdate_scraped'])}",
                        "reason": f"GT Its a bad look: {reg_gt}→{spider_gt} ({(spider_gt/reg_gt-1)*100:+.0f}%)"
                    })
                    continue

                # Through！Use this candidate
                spider_row = cand
                match_method = "Callsign_validated"
                if type_ok is None:
                    validation_notes = f"The ships not sure(spider={spider_type}, reg={reg_vesseltype}), GT The margin passed"
                break

            # If all the candidates fail,
            if spider_row is None:
                pass  # change_log Its in the record

        # --- Level III: ShipName Cross-check Match (Minimum Trust)  ---
        if spider_row is None and reg_name:
            reg_name_upper = reg_name.upper()
            # Lets get to the exact match, Try to blur the match again
            candidates = name_index.get(reg_name_upper, [])
            if not candidates:
                # Try matching with standardized ship names (Go to non-letter numbers) 
                reg_name_norm = re.sub(r'[^A-Z0-9]', '', reg_name_upper)
                for name_key, cands in name_index.items():
                    if re.sub(r'[^A-Z0-9]', '', name_key) == reg_name_norm:
                        candidates = cands
                        break

            for cand in candidates:
                spider_gt = safe_float(cand["tonnage_scraped"])
                spider_type = cand["ship_type_scraped"]

                # Verify 1: Compatibility of ship types (It has to be clearly compatible) 
                type_ok = is_ship_type_compatible(spider_type, reg_vesseltype)
                if type_ok == False:
                    continue  # The name of the ship matches + Non-compatible ship → Skip to see the next candidate

                # Verify 2: GT Portability (We have to go) 
                gt_ok = True
                if (not np.isnan(reg_gt)) and (not np.isnan(spider_gt)) and reg_gt > 0:
                    ratio = spider_gt / reg_gt
                    gt_ok = (1 - GT_TOLERANCE) <= ratio <= (1 + GT_TOLERANCE)
                if not gt_ok:
                    continue

                # Verify 3: Flag Coherence (ShipName Matching with the flag) 
                spider_flag = cand.get("flag_scraped", "")
                if spider_flag and reg_flag:
                    sf_norm = spider_flag.upper().strip()
                    rf_norm = reg_flag.upper().strip()
                    # Simple check: The flag code is consistent or contains each other
                    if sf_norm != rf_norm and sf_norm not in rf_norm and rf_norm not in sf_norm:
                        continue

                # All through
                spider_row = cand
                match_method = "ShipName_validated"
                validation_notes = "ShipName Cross-check through(Type of ship+GT+Flag)"
                break

        if spider_row is None:
            continue  # No match, Skip this ship

        # ---- Execute Update ----
        spider_bd = safe_float(spider_row["builtdate_scraped"])
        spider_gt = safe_float(spider_row["tonnage_scraped"])
        spider_mmsi = safe_float(spider_row["mmsi"])
        spider_type = spider_row["ship_type_scraped"]
        spider_flag = spider_row["flag_scraped"]

        changes_this_row = []

        # --- update Builtdate ---
        if not np.isnan(spider_bd) and spider_bd > 1900:
            old_bd = registry.at[idx, "Builtdate"]
            if np.isnan(safe_float(old_bd)) or abs(safe_float(old_bd) - spider_bd) > 0.1:
                registry.at[idx, "Builtdate"] = spider_bd
                changes_this_row.append(f"Builtdate: {old_bd} → {int(spider_bd)}")

        # --- update Tonnage (GT) ---
        if not np.isnan(spider_gt) and spider_gt > 0:
            old_gt = safe_float(registry.at[idx, "Tonnage"])
            if np.isnan(old_gt) or abs(old_gt - spider_gt) / max(old_gt, spider_gt) > 0.01:
                registry.at[idx, "Tonnage"] = spider_gt
                registry.at[idx, "TonnageType"] = "GT"
                changes_this_row.append(f"Tonnage: {old_gt} → {spider_gt}")

        # --- update MMSI (Filling gaps or apparent differences)  ---
        if not np.isnan(spider_mmsi) and spider_mmsi > 0:
            old_mmsi = safe_float(registry.at[idx, "MMSI"])
            if np.isnan(old_mmsi) or old_mmsi == 0:
                registry.at[idx, "MMSI"] = spider_mmsi
                changes_this_row.append(f"MMSI: Empty → {int(spider_mmsi)}")

        # --- update VesselType (Just think of it spider Clear instruction as TS/Transport vessels)  ---
        new_gear = map_ship_type_to_gear(spider_type)
        if new_gear and registry.at[idx, "VesselType"] != new_gear:
            old_type = registry.at[idx, "VesselType"]
            registry.at[idx, "VesselType"] = new_gear
            changes_this_row.append(f"VesselType: {old_type} → {new_gear}")

        # --- update Flag (If only the register had no flag and spider present)  ---
        if spider_flag:
            old_flag = safe_str(registry.at[idx, "Flag"])
            if not old_flag or old_flag in ("", "nan"):
                registry.at[idx, "Flag"] = spider_flag
                changes_this_row.append(f"Flag: Empty → {spider_flag}")

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
                    "IMO Dock Update" if match_method == "IMO_anchor" else "Callsign Cross-check through"
                ),
            })

    print(f"\n  Updated statistics:")
    print(f"    IMO Update of anchors: {updated_count['IMO_anchor']} One")
    print(f"    Callsign Authentication through: {updated_count['Callsign_validated']} One")
    print(f"    ShipName Authentication through: {updated_count['ShipName_validated']} One")
    print(f"    Callsign Reject(Non-compatible ship): {updated_count['Callsign_rejected_ship_type']} One")
    print(f"    Callsign Reject(GT Its a bad look): {updated_count['Callsign_rejected_gt']} One")
    print(f"    Callsign Reject(Double failure): {updated_count['Callsign_rejected_both']} One")
    print(f"    Total update: {len(change_log)} Item")

    change_df = pd.DataFrame(change_log) if change_log else pd.DataFrame()
    return registry, change_df


# =============================================================================
# Main entrance
# =============================================================================

def main():
    print("=" * 70)
    print("  Spider Data → Unified_Vessel_Registry Parameter Update")
    print("  IMO Dock (Absolutely) + Callsign Cross Authentication")
    print("=" * 70)

    # ---- Load Register ----
    print(f"\n Load Register: {REGISTRY_PATH}")
    registry = pd.read_csv(REGISTRY_PATH, encoding="utf-8-sig")
    print(f"  Current number of ships: {len(registry)}")

    # Recording statistics before updating
    old_bd_count = registry["Builtdate"].notna().sum()
    old_gt_count = registry["Tonnage"].notna().sum()
    old_mmsi_count = registry["MMSI"].notna().sum()

    # ---- Load spider Data ----
    spider = load_spider_data()

    # ---- Execute Update ----
    registry, change_log = update_registry(registry, spider)

    # ---- Updated statistics ----
    new_bd_count = registry["Builtdate"].notna().sum()
    new_gt_count = registry["Tonnage"].notna().sum()
    new_mmsi_count = registry["MMSI"].notna().sum()

    print(f"\n  Changes in data integrity:")
    print(f"    Builtdate: {old_bd_count} → {new_bd_count} (+{new_bd_count-old_bd_count})")
    print(f"    Tonnage:   {old_gt_count} → {new_gt_count} (+{new_gt_count-old_gt_count})")
    print(f"    MMSI:      {old_mmsi_count} → {new_mmsi_count} (+{new_mmsi_count-old_mmsi_count})")

    # ---- Output ----
    print("\n" + "=" * 70)
    print("  Save Results")
    print("=" * 70)

    # Keep an updated registry
    registry.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"  Register updated: {OUTPUT_PATH}")

    # Save Change Log
    log_path = BASE_DIR / "Registry_Update_Log.csv"
    if len(change_log) > 0:
        change_log.to_csv(log_path, index=False, encoding="utf-8-sig")
        print(f"  Change Log: {log_path} ({len(change_log)} Article change)")

        # Print Changes Summary
        print(f"\n  Change Field Distribution:")
        field_counts = change_log["field"].value_counts()
        for field, count in field_counts.items():
            print(f"    {field}: {count}")

    print("\n  Completed. ")
    return registry, change_log


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    registry, change_log = main()
