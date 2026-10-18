#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
fix_spider_output.py
=============================================================================
Fix spider output Excel files: correct the "original" build date and tonnage
columns (which were read from buggy extraction CSVs), and re-evaluate the
comparison judgment.

The extraction bug (gt keyword matching "length") caused Tonnage=Length
in IATTC and WCPFC extraction outputs. The spider read these wrong values as
"original" data. After fixing the extraction, this script corrects the spider
output files without requiring re-running the spider (no web scraping needed).

Fix logic:
  1. Read corrected extraction CSV → get correct old values
  2. Read spider output Excel → update original value columns
  3. Match by IMO (priority) → Callsign → Vesselname
  4. Re-evaluate comparison judgment for each row
=============================================================================
"""

import os
import sys
import re
from pathlib import Path

import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

BASE_DIR = Path(__file__).resolve().parent  # spider/
ROOT_DIR = BASE_DIR.parent
OUTPUT_FOLDER = BASE_DIR / "output"
EXTRACTED_DIR = ROOT_DIR / "vessel_data_extract" / "new_extracted_vessel_data"

# Mapping: spider output filename → extraction CSV filename
FILE_MAPPING = {
    "CCSBT_extracted_new_result.xlsx": "CCSBT_extracted_new.csv",
    "IATTC_extracted_new_result.xlsx": "IATTC_extracted_new.csv",
    "ICCAT_extracted_new_result.xlsx": "ICCAT_extracted_new.csv",
    "IOTC_extracted_new_result.xlsx":  "IOTC_extracted_new.csv",
    "WCPFC_extracted_new_result.xlsx": "WCPFC_extracted_new.csv",
}

# Column positions in spider output Excel
COL_IMO_INPUT = 4       # IMO Encoding(Enter)
COL_CALLSIGN_INPUT = 5  # Call sign(Enter)
COL_SHIPNAME_INPUT = 3  # Name of ship(Enter)
COL_NEW_BUILD_DATE = 7  # Built_Date (Crawl) 
COL_NEW_TONNAGE = 8     # gross tonnage (Crawl) 
COL_OLD_BUILD_DATE = 12 # Original year of construction
COL_OLD_TONNAGE = 13    # Original total tons
COL_JUDGMENT = 14       # Data match determination


def safe_str(val) -> str:
    """Convert value to clean string, handling NaN."""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none"):
        return ""
    if s.endswith(".0") and s.count(".") == 1:
        try:
            float(s)
            s = s[:-2]
        except ValueError:
            pass
    return s


def normalize_for_compare(val) -> str:
    """Normalize value for comparison: strip spaces, commas, lowercase."""
    s = safe_str(val)
    if not s:
        return ""
    s = s.replace(",", "").replace("，", "")
    s = s.strip()
    return s


def compare_and_judge(new_val: str, old_val: str, field_name: str) -> tuple:
    """Compare old vs new value for a single field."""
    new_norm = normalize_for_compare(new_val)
    old_norm = normalize_for_compare(old_val)

    if not old_norm and not new_norm:
        return ("both_empty", "")
    if not old_norm and new_norm:
        return ("filled", f"{field_name}original value missing, filled")
    if old_norm and not new_norm:
        return ("new_empty", f"{field_name}Crawl as Empty(Old value:{old_val})")
    if old_norm == new_norm:
        return ("match", "")
    else:
        return ("updated", f"{field_name}(Old value:{old_val}->New value:{new_val})")


def build_comparison_judgment(new_build_date: str, new_gross_tonnage: str,
                               old_build_date: str, old_gross_tonnage: str) -> str:
    """Build comprehensive comparison judgment text."""
    bd_status, bd_msg = compare_and_judge(new_build_date, old_build_date, "year built")
    gt_status, gt_msg = compare_and_judge(new_gross_tonnage, old_gross_tonnage, "gross tonnage")

    all_statuses = [bd_status, gt_status]

    if all(s in ("match", "both_empty") for s in all_statuses) and "match" in all_statuses:
        return "identical"

    if all(s == "both_empty" for s in all_statuses):
        return "original value missing, Crawling data is empty"

    changes = []
    if bd_msg:
        changes.append(bd_msg)
    if gt_msg:
        changes.append(gt_msg)

    if not changes:
        return "identical"

    has_filled = "filled" in all_statuses
    has_updated = "updated" in all_statuses
    has_new_empty = "new_empty" in all_statuses

    if has_updated and has_filled:
        prefix = "data updated+Supplementary: "
    elif has_updated:
        prefix = "data updated: "
    elif has_filled and not has_updated:
        prefix = "original value missing, filled: "
    elif has_new_empty:
        prefix = "attention-Crawling data missing: "
    else:
        prefix = ""

    return prefix + "; ".join(changes)


def apply_judgment_style(cell, judgment_text: str):
    """Apply color-coded style to judgment cell."""
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    if "identical" in judgment_text:
        cell.font = Font(color="006100")
        cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    elif "data updated" in judgment_text:
        cell.font = Font(color="9C5700", bold=True)
        cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    elif "original value missing, filled" in judgment_text:
        cell.font = Font(color="0066CC")
        cell.fill = PatternFill(start_color="DAEEF3", end_color="DAEEF3", fill_type="solid")
    elif "attention" in judgment_text:
        cell.font = Font(color="9C0006")
        cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")


def build_extraction_lookup(extraction_csv_path: str) -> dict:
    """Build lookup dictionaries from corrected extraction CSV."""
    df = pd.read_csv(extraction_csv_path, encoding="utf-8-sig")
    print(f"  Loaded {len(df)} vessels from {Path(extraction_csv_path).name}")

    imo_lookup = {}
    cs_lookup = {}
    name_lookup = {}

    for _, row in df.iterrows():
        imo = safe_str(row.get("IMO", ""))
        cs = safe_str(row.get("Callsign", ""))
        name = safe_str(row.get("Vesselname", ""))
        build_date = safe_str(row.get("Builtdate", ""))
        tonnage = safe_str(row.get("Tonnage", ""))

        entry = {"build_date": build_date, "tonnage": tonnage}

        if imo:
            imo_lookup[imo.upper()] = entry
        if cs:
            cs_lookup[cs.upper()] = entry
        if name:
            name_lookup[name.upper()] = entry

    print(f"  IMO keys: {len(imo_lookup)}, Callsign keys: {len(cs_lookup)}, Name keys: {len(name_lookup)}")
    return imo_lookup, cs_lookup, name_lookup


def fix_spider_output(spider_xlsx_name: str, extraction_csv_name: str):
    """Fix a single spider output Excel file."""
    spider_path = OUTPUT_FOLDER / spider_xlsx_name
    extraction_path = EXTRACTED_DIR / extraction_csv_name

    if not spider_path.exists():
        print(f"\n  SKIP {spider_xlsx_name}: file not found")
        return 0

    print(f"\n{'='*60}")
    print(f"  Fixing: {spider_xlsx_name}")
    print(f"  Source: {extraction_csv_name}")
    print(f"{'='*60}")

    # Build lookup from corrected extraction data
    imo_lookup, cs_lookup, name_lookup = build_extraction_lookup(str(extraction_path))

    # Open spider output Excel
    wb = openpyxl.load_workbook(str(spider_path))
    sheet = wb.active

    fixed_count = 0
    unchecked_count = 0
    total_rows = sheet.max_row - 1  # exclude header

    for row_num in range(2, sheet.max_row + 1):
        imo = safe_str(sheet.cell(row=row_num, column=COL_IMO_INPUT).value)
        cs = safe_str(sheet.cell(row=row_num, column=COL_CALLSIGN_INPUT).value)
        ship_name = safe_str(sheet.cell(row=row_num, column=COL_SHIPNAME_INPUT).value)

        old_build_date_current = safe_str(sheet.cell(row=row_num, column=COL_OLD_BUILD_DATE).value)
        old_tonnage_current = safe_str(sheet.cell(row=row_num, column=COL_OLD_TONNAGE).value)

        # Find correct values from extraction
        correct_entry = None
        match_type = ""

        # Priority: IMO > Callsign > Vesselname
        if imo and imo.upper() in imo_lookup:
            correct_entry = imo_lookup[imo.upper()]
            match_type = "IMO"
        elif cs and cs.upper() in cs_lookup:
            correct_entry = cs_lookup[cs.upper()]
            match_type = "Callsign"
        elif ship_name and ship_name.upper() in name_lookup:
            correct_entry = name_lookup[ship_name.upper()]
            match_type = "Vesselname"

        if correct_entry is None:
            unchecked_count += 1
            continue

        correct_build_date = correct_entry["build_date"]
        correct_tonnage = correct_entry["tonnage"]

        # Check if update is needed
        bd_changed = (normalize_for_compare(old_build_date_current) !=
                      normalize_for_compare(correct_build_date))
        ton_changed = (normalize_for_compare(old_tonnage_current) !=
                       normalize_for_compare(correct_tonnage))

        if not bd_changed and not ton_changed:
            continue  # Already correct

        # Update the original values
        if bd_changed:
            sheet.cell(row=row_num, column=COL_OLD_BUILD_DATE).value = (
                int(float(correct_build_date)) if correct_build_date.replace('.', '').isdigit()
                else correct_build_date
            )
        if ton_changed:
            sheet.cell(row=row_num, column=COL_OLD_TONNAGE).value = (
                float(correct_tonnage) if correct_tonnage else correct_tonnage
            )

        # Re-evaluate judgment
        new_build_date = safe_str(sheet.cell(row=row_num, column=COL_NEW_BUILD_DATE).value)
        new_tonnage = safe_str(sheet.cell(row=row_num, column=COL_NEW_TONNAGE).value)

        judgment = build_comparison_judgment(
            new_build_date, new_tonnage,
            correct_build_date, correct_tonnage
        )

        judgment_cell = sheet.cell(row=row_num, column=COL_JUDGMENT)
        judgment_cell.value = judgment
        apply_judgment_style(judgment_cell, judgment)

        fixed_count += 1

    wb.save(str(spider_path))
    wb.close()

    print(f"  Results: {fixed_count} rows fixed, {total_rows - fixed_count - unchecked_count} already correct, "
          f"{unchecked_count} unmatched")
    return fixed_count


def main():
    print("=" * 70)
    print("  SPIDER OUTPUT FIXER — Correct Original Values & Judgment")
    print("=" * 70)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    total_fixed = 0
    for spider_name, extraction_name in FILE_MAPPING.items():
        fixed = fix_spider_output(spider_name, extraction_name)
        total_fixed += fixed

    print(f"\n{'='*70}")
    print(f"  TOTAL FIXED: {total_fixed} rows across all spider output files")
    print(f"  Done. Spider output files have been updated with correct original values.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
