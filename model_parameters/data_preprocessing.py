#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
Data cleansing and matrix re-engineering the pipeline (Data Preprocessing Pipeline)
=============================================================================
Will Model_parameters.xlsx Medium 4 Destructured Sheet Convert to 4 Standardized, 
Machine-readable Relationship Matrix (DataFrame), For downstream LCA Model is called directly. 

Enter:  model_parameters/Model_parameters.xlsx (4 sheets)
Output:  4 One CSV + 1 Merge Excel:
       - model_parameters/Prior_Matrix.csv
       - model_parameters/Species_CF_Matrix.csv
       - model_parameters/Scenario_Multiplier_Matrix.csv
       - model_parameters/MonteCarlo_Config_Matrix.csv
       - model_parameters/Cleaned_Parameter_Matrices.xlsx (4 sheets)

Design principles:
  1. Original Sheet 1 (Dynamic life-cycle models) is"Bibliography", Data embedded in Chinese narrative, 
     Unable to automate the analysis safely → Introduction"Hard Coding + Retroactivity comments"Policy. 
  2. Sheet 2/3/4 Reverse structure → Directly parsing + Text Retrieval. 
  3. Use missing values in all output matrices NaN Tag, Do not use empty string in the calculation core. 
  4. each matrix includes column-level descriptions (via DataFrame.attrs). 

Author: Claude Code Auxiliary Build
Date: 2026-06-18
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
    "fuel savings 35–61%"    → (0.65, 0.39, 0.52)  # reduction → multiplier = 1-pct
    "GHG emission reduction 22%"     → (1-0.22, 1-0.22, 0.78)
    "Carbon emissions are only diesel fuel 50%"  → (0.50, 0.50, 0.50)  # direct fraction, NOT reduction
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
        r'\d+\s*(?:ton|\u5428|t)\s*(?:CO|C)', r'\u6b21\u4f5c\u4e1a',
    ]
    for pat in unit_patterns:
        if re.search(pat, text):
            return None, None, None

    # ---- Detect "direct fraction" pattern: "is/is/only...of X%" ----
    # "Carbon emissions are only diesel fuel 50.24%" → multiplier = 0.5024 (direct, NOT 1-pct)
    direct_frac_match = re.search(
        r'(?:\u4ec5\u4e3a|\u4ec5\u4e3a|\u4e3a|\u662f)\s*(?:\S+\s*\u7684)?\s*(\d+\.?\d*)\s*%', text
    )
    if direct_frac_match:
        val = float(direct_frac_match.group(1)) / 100.0
        return val, val, val

    # ---- Detect saving/reduction language ----
    is_saving = any(kw in text for kw in [
        '\u8282\u7701', '\u51cf\u5c11', '\u964d\u4f4e', '\u4e0b\u964d', '\u8282\u7ea6', '\u51cf\u6392', 'saving', 'reduce'
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

    # Try single number with saving keywords but no % (e.g., "reduction 40")
    if is_saving:
        single_no_pct = re.search(
            r'(?:\u8282\u7701|\u51cf\u5c11|\u964d\u4f4e|\u4e0b\u964d|\u8282\u7ea6|\u51cf\u6392)\s*(\d+\.?\d*)', text
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
    "GHG emission reduction 22%"     → 0.78
    "GHG emission reduction >30%"    → 0.70
    "CO₂emission factor 0.9 tonnes"  → 0.9 (direct factor, not multiplier)

    Returns
    -------
    float or None
    """
    text = safe_str(text)
    if not text:
        return None

    # Pattern: GHG/CO2 reduction/decrease/decrease X% (with optional > or ~)
    pct_match = re.search(
        r'(?:GHG|CO₂?|CO2|\u6e29\u5ba4|\u78b3\u6392\u653e?)\s*(?:\u6392\u653e)?\s*'
        r'(?:\u51cf\u5c11|\u964d\u4f4e|\u4e0b\u964d|\u51cf\u6392)\s*[>~]?\s*(\d+\.?\d*)\s*%',
        text
    )
    if pct_match:
        reduction = float(pct_match.group(1)) / 100.0
        return round(1.0 - reduction, 3)

    # Pattern: direct CO2 emission factor
    ef_match = re.search(
        r'(?:CO₂?|CO2)\s*(?:\u6392\u653e\u56e0\u5b50)?\s*[：:]\s*(\d+\.?\d*)', text
    )
    if ef_match:
        return float(ef_match.group(1))

    return None


def normalize_distribution_name(text: str) -> str:
    """
    Map Chinese distribution descriptions to standard English names.

    Examples
    --------
    "Triangular distribution" → "Triangular"
    "Normal distribution" → "Normal"
    "logarithmic normal distribution" → "Lognormal"
    "Continuous Probability Distribution" → "Continuous" (generic)
    """
    text = safe_str(text).lower()
    if '\u4e09\u89d2' in text or 'triangular' in text:
        return 'Triangular'
    if 'pert' in text:
        return 'PERT'
    if '\u5bf9\u6570\u6b63\u6001' in text or 'lognormal' in text or 'log normal' in text:
        return 'Lognormal'
    if '\u6b63\u6001' in text or 'normal' in text:
        return 'Normal'
    if '\u5747\u5300' in text or 'uniform' in text:
        return 'Uniform'
    if '\u622a\u65ad' in text or 'truncat' in text:
        return 'Truncated'
    if '\u79bb\u6563' in text or 'discrete' in text:
        return 'Discrete'
    if '\u8fde\u7eed' in text or 'continuous' in text:
        return 'Continuous'
    return 'Continuous'


# =============================================================================
# Matrix 1: Prior_Matrix (Pre-demonstration Array — Full list of parameters of the emission model)
# =============================================================================
#
# Design description:
#   Prior_Matrix Its an emission model"Parameters master table", In long format (long format) Organization. 
#   Each record represents a combination of parameters in a given dimension (Flag × Gear × Sector × LengthCategory)
#   Take value from below. All parameters in total table, Downstream model press Param_Code + Width Keys Direct Index. 
#
#   Parameters Source: Model_parameters.xlsx → Sheet 1「Dynamic life-cycle models」(108 rows)
#   The Sheet Its a notebook, Arguments embedded in the Chinese narrative, Its gonna be extracted manually. 
#
#   Parameter Overwrite 8 Category:
#     A. Standard Classification of Ships            (Vessel Classification)
#     B. Parameters for ship operations        (Fishing Activity Parameters)
#     C. Core fuel and emission parameters      (Core Fuel & Emission Parameters)
#     D. auxiliary engine power parameters            (Auxiliary Engine Power)
#     E. Ship-body material and construction parameters      (Hull Material & Construction)
#     F. Parameters for the consumption of gear material        (Gear Material Consumption)
#     G. longline bait consumption parameters      (Longline Bait Consumption)
#     H. Refrigerant parameters              (Refrigerant Parameters)
#     I. Efforts to standardize parameters        (Effort Standardization)
#     J. Historical Power Evolution Parameters        (Power Discount / Historical Evolution)
#     K. GT-LDT Tonn Conversion Parameters     (Gross Tonnage → Light Displacement Tonnage)
#
#   LONG-FORMAT Column Definitions:
#     Param_Section    — Large class of parameters (A-L)
#     Param_Code       — Variable name in model code (e.g., T_map, SFR_map)
#     Param_Name_EN    — parameter name in English
#     Flag             — Application of flag States/Regional (ALL = Globally available)
#     Gear             — Type of gear applicable: LL/PS/TP/ALL
#     Sector           — Applicable authority: I (Industrial) / APW (Artisanal) / ALL
#     Length_Category  — vessel-length class: <12m / >=12m / ALL
#     Value_Best       — Best estimate (median/mode/mean)
#     Value_Low        — Parameter Lower Limits
#     Value_High       — Parameter Maximum
#     Unit             — Physics Unit
#     Distribution     — Recommended Monte Carlo distribution type
#     Source_Citation  — Documentation sources (Author, Year, Periodicals)
#     Sheet1_Row       — Original Sheet 1 Line Numbers
#     Note             — Note (Extract Logic, Assumptions, Relationship with model)
#
#   SCALAR Uniform use of parameters: Flag=ALL, Gear=ALL, Sector=ALL, Length_Category=ALL
#   GEAR-SPECIFIC parameter:   Flag=ALL, Gear=LL|PS|TP, Sector=ALL
#   SECTOR-SPECIFIC parameter: Flag=ALL, Gear=ALL, Sector=I|APW
#   REGION-SPECIFIC parameter: Flag=Africa|Asia|..., Gear=LL|PS, Sector=I|APW
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
    print("  Building Matrix 1: Prior_Matrix (Pre-demonstration Array — v2 Revised)")
    print("  Fixes: Sheet1_Row 'R' prefix + Bastos LF corrected + EFs gapped")
    print("=" * 70)

    rows = []

    def add_row(section, code, name_en, flag, gear, sector, len_cat,
                v_best, v_low, v_high, unit, dist, source, s1_row, note):
        rows.append({
            'Param_Section':    section,
            'Param_Code':       code,
            'Param_Name_EN':    name_en,
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
    # A. Standard Classification of Ships (Vessel Classification) — Sheet 1 Row 4-5
    # ========================================================================
    # Row 4: "Classification criteria for artisanal and industrial fisheries — vessel length 12m" (EU definition)
    # Row 5: Keep as model comment line (Original Greer 16m Threshold abandoned, Uniformly used EU 12m standard) 
    # Model usage:
    #   - 12m: common vessel-length threshold, For Sector, SFR_map, EF_fuel_map Waiting for all staircase functions
    #   - EU standard: Council Regulation (EC) No 1198/2006, Article 26

    add_row(
        'A', 'LENGTH_THRESHOLD_SECTOR_M', 'Sector classification vessel-length threshold (EU standard)',
        'ALL', 'ALL', 'ALL', 'ALL',
        12.0, np.nan, np.nan, 'm', 'Discrete',
        'Council Regulation (EC) No 1198/2006 of 27 July 2006 on the European Fisheries Fund, Article 26',
        'R4',
        'I (Industrial): >=12m; APW (Artisanal): <12m. Harmonization by EU standards. For Sector binary classification. '
    )
    add_row(
        'A', 'LENGTH_THRESHOLD_SFR_M', 'SFR/EF stepwise vessel-length threshold (common EU standard)',
        'ALL', 'ALL', 'ALL', 'ALL',
        12.0, np.nan, np.nan, 'm', 'Discrete',
        'Council Regulation (EC) No 1198/2006; Greer et al. (2019) Mar. Policy 107:103382',
        'R4-R5',
        '<12m vs >=12m. Uniformly used EU 12m standard. Original Row 5 (Greer 16m)Abandoned, All ladder functions are aligned by pressing 12m Division. '
    )

    # ========================================================================
    # B. Parameters for ship operations (Fishing Activity Parameters) — Sheet 1 Row 6-28
    # ========================================================================

    # ------------------------------------------------------------------
    # B1. DAS — Days at Sea (T_map) — Row 6-13
    # ------------------------------------------------------------------
    # Data Priority System (Data Hierarchy):
    #   Tier 1 (Highest): Parker et al. (2014) — modern tuna purse-seine fleet, By Ocean,
    #                  Response 1990 After FAD Real high-intensity work under strategy
    #   Tier 2 (Sub): Jha et al. (2026) — Indian Ocean/mechanised longline fisheries in the Arabian Sea, Recent regional amendments
    #   Tier 3 (Take the bottom): Anticamara et al. (2011) — Macro-historical baseline (1950-2010),
    #                  Applicable to non-principal ship type(TP), Historical retroactivity, Missing data range
    #
    # Geographical Map (Geographic Mapping):
    #   Pacific  → Asia/Oceania (Theta) or Americas (Tung Tai!)
    #   Indian   → Asia or Africa
    #   Atlantic → Europe/Americas or Africa
    # RFMO Corresponds to: IATTC+WCPFC→Pacific, IOTC→Indian, ICCAT→Atlantic
    #
    # For full literature reference see entries Source_Citation Fields.
    #
    # Row 6: Table header — Gear × Region
    # Row 7: Longline DAS table (Anticamara et al. 2011)
    # Row 8: Purse Seine DAS table (Anticamara et al. 2011)
    # Row 9: PS China = 200 (expert: expert consultation with Bin Xie)
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
    # Data: 93 purse-seine vessels (And thats the only way to make a living/Yellowfin tuna catches 28%), By ocean layer.

    parker_citation = (
        'Parker RWR, Vázquez-Rowe I, Tyedmers PH. (2014). '
        'Fuel performance and carbon footprint of the global purse seine tuna fleet. '
        'J. Clean. Prod. 103:517-524. DOI:10.1016/j.jclepro.2014.05.017'
    )

    # Atlantic PS: 297 days (n=9 vessels, avg LOA=70.6m)
    add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS Atlantic',
            'Atlantic', 'PS', 'I', 'ALL', 297, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            'Tier 1 — Atlantic purse seine (Parker et al. 2014): 297 days/year. '
            'n=9 vessels, avg LOA=70.6m. Applicable to ICCAT Water, 1990 After FAD Times. '
            'RFMO: ICCAT → Atlantic.')

    # Indian PS: 289 days (n=9 vessels, avg LOA=81.7m)
    add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS Indian',
            'Indian', 'PS', 'I', 'ALL', 289, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            'Tier 1 — Indian Ocean purse seine (Parker et al. 2014): 289 days/year. '
            'n=9 vessels, avg LOA=81.7m. Applicable to IOTC Water, 1990 After FAD Times. '
            'RFMO: IOTC → Indian.')

    # Pacific PS: 244 days (n=75 vessels, avg LOA=68.9m)
    add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS Pacific',
            'Pacific', 'PS', 'I', 'ALL', 244, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            'Tier 1 — Pacific purse seine (Parker et al. 2014): 244 days/year. '
            'n=75 vessels, avg LOA=68.9m. Applicable to WCPFC+IATTC Water, 1990 After FAD Times. '
            'RFMO: WCPFC+IATTC → Pacific.')

    # PS fallback for unmapped RFMOs: mean of 3 oceans
    parker_mean = round((297 + 289 + 244) / 3, 1)  # = 276.7 ≈ 277
    add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS default mean',
            'ALL', 'PS', 'I', 'ALL', parker_mean, np.nan, np.nan,
            'days/year', 'Triangular', parker_citation,
            'R11',
            f'Tier 1 — Default for unmaped tissue: mean(Atlantic 297, Indian 289, Pacific 244) '
            f'= {parker_mean} days/year. '
            'For those that cannot be clearly divided into three oceans RFMO (Like CCSBT Trans-ocean waters) or missing database RFMO Trailers . '
            'Parker et al. (2014) Global weighted average=253 days (Smaller ships), '
            f'Average of arithmetic in three oceans={parker_mean} days (large commercial purse-seine vessels only).')

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
    add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 2: Jha LL Indian Ocean',
            'Asia', 'LL', 'APW', '<12m', 245, 234, 256,
            'days/year', 'Triangular', jha_citation,
            'R13',
            'Tier 2 — mechanised longline fisheries in the Indian Ocean (Jha et al. 2026): '
            '234-256 days/year, Best=245 (midpoint). '
            '16-20m mechanized longline-cum-gillnet vessels, SE Arabian Sea. '
            'Provide up-to-date area time slices, More reflective of current fishing efforts than historical baselines. '
            'Geographical Map: Indian Ocean → Asia (South Asia/Arabian Sea coast).')

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
        add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 3: Anticamara LL',
                region, 'LL', 'ALL', 'ALL', das, np.nan, np.nan,
                'days/year', 'Triangular', anticamara_citation,
                'R7',
                f'Tier 3 — LL {region} (Anticamara et al. 2011): {das} days/year. '
                'Macro-historical baseline (1950-2010), Flag=ALL, Sector=ALL. '
                'For longline fleet historical retroactivity for lack of high-precision data.')

    # Purse Seine DAS by continent (Row 8) — Tier 3 fallback
    ps_das = {
        'Africa': 159, 'Asia': 195, 'Australia & Oceania': 195,
        'Europe': 177, 'North America': 177, 'South America': 177,
    }
    for region, das in ps_das.items():
        add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 3: Anticamara PS',
                region, 'PS', 'ALL', 'ALL', das, np.nan, np.nan,
                'days/year', 'Triangular', anticamara_citation,
                'R8',
                f'Tier 3 — PS {region} (Anticamara et al. 2011): {das} days/year. '
                'Macro-historical baseline (1950-2010), Flag=ALL, Sector=ALL. '
                'Applicable to 1990 A year ago(none FAD)historical reconstruction of purse-seine fleets or missing Parker Area of data.')

    # PS China expert consultation (Row 9) — specific override
    add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — China PS expert',
            'Asia', 'PS', 'I', 'ALL', 200, np.nan, np.nan,
            'days/year', 'Triangular',
            'Expert consultation (expert consultation with Bin Xie) — China PS fleet. '
            'Overrides Anticamara Asia PS (195 days) for Chinese-flagged vessels.',
            'R9',
            'China-specific PS DAS=200, Higher than average for Asia region(195). '
            'applies to Chinese-flagged purse-seine vessels, Overwrite Anticamara Asia PS Entry.')

    # Transport vessel (Row 10) — Anticamara inferred
    add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Transport vessel',
            'ALL', 'TP', 'I', 'ALL', 180, np.nan, np.nan,
            'days/year', 'Triangular',
            'Inferred from Sheet 1 Row 10: "Transport 15 days per month" '
            '→ 15×12=180 days/year. '
            'Reference: Anticamara et al. (2011) for non-fishing vessel DAS baseline.',
            'R10',
            'Transport/refrigerated carrier vessel (transshipment vessel/Refrigerated transport vessels). '
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
            add_row('B', 'T_map_DAS', 'annual days at sea (Days at Sea)',
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
    # Row 17: "Long trip to the sea (Trip duration) | 6h"
    # Row 18: "24h(Industrial)"
    # Row 19: "6h(Smallscale)"
    #
    # Current model (ghg_lca.py) uses: H_map = {'LL': 6, 'PS': 24, 'TS': 24}
    # This is a simplified approach. The Prior_Matrix records provide a more
    # nuanced Sector-aware parameterization for future model refinement.

    # Industrial: 24h continuous deep-sea operation
    add_row('B', 'H_map_Hday', 'daily main engine operating hours (Daily Engine Hours)',
            'ALL', 'ALL', 'I', 'ALL', 24.0, np.nan, np.nan,
            'h/day', 'Triangular',
            'Greer et al. (2019) Mar. Policy 107:103382; '
            'Korican et al. (2023) Ocean Eng. 286:115734',
            'R16,R18',
            'Industrial: 24h continuous deep-sea operation (Row 16, Row 18).')

    # APW: 12h coastal daytime (based on PNAS α-analysis, median ~9h → 12h)
    add_row('B', 'H_map_Hday', 'daily main engine operating hours (Daily Engine Hours)',
            'ALL', 'ALL', 'APW', 'ALL', 12.0, 4.0, 12.0,
            'h/day', 'Triangular',
            'Greer et al. (2019) smallscale=4h (Row 16, Row 19); '
            'PNAS α-analysis: observed median ~9h/day → 12h (half of Industrial)',
            'R16,R19',
            'APW: coastal daytime operation. Sheet 1 says 4-6h (Row 16, 19), '
            'but PNAS empirical data shows median ~9h. '
            'Conservative 12h As the best estimate, 4h As the lower limit.')

    # PS-specific: ghg_lca engine vs auxiliary (Row 15, Korican et al. 2023)
    add_row('B', 'H_map_Main_PS', 'PS daily main engine operating hours',
            'ALL', 'PS', 'I', 'ALL', 4.0, np.nan, np.nan,
            'h/day', 'Triangular',
            'Korican et al. (2023) Ocean Eng. 286:115734',
            'R15',
            'PS ghg_lca engine: ~4h/day (short high-power bursts for setting/hauling).')
    add_row('B', 'H_map_Aux_PS', 'PS daily auxiliary engine operating hours',
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
    add_row('B', 'LF_move', 'Engine load factor during the cruise phase (Transit Load Factor)',
            'ALL', 'LL', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) JGR 112:D12305 — cruise MCR≥65%, typical load 80%',
            'R22-R23',
            'LL Industrial transit: 80% MCR cruise (Eyring et al. 2005, Row 22-23).')

    add_row('B', 'LF_work', 'Engine load factors for the fishing operations phase (Fishing Load Factor)',
            'ALL', 'LL', 'I', 'ALL', 0.50, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Perčić et al. (2020) — general marine auxiliary engines, Aux=0.5',
            'R27',
            'LL Industrial fishing: Aux=0.5 (Perčić et al. 2020, Row 27). '
            'Fishing phase uses auxiliary engines at ~50% load for hauling gear. '
            'NOTE: Bastos et al. (2021) is SMALL-SCALE (see APW entries below).')

    # --- Industrial Purse Seine ---
    add_row('B', 'LF_move', 'Engine load factor during the cruise phase (Transit Load Factor)',
            'ALL', 'PS', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) JGR 112:D12305 — cruise MCR≥65%, typical load 80%',
            'R22-R23',
            'PS Industrial transit: 80% MCR cruise (same as LL).')

    add_row('B', 'LF_work', 'Engine load factors for the fishing operations phase (Fishing Load Factor)',
            'ALL', 'PS', 'I', 'ALL', 0.65, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) JGR 112:D12305 — non-cargo ships, load 65-75%',
            'R24',
            'PS Industrial fishing: 65% MCR (Eyring non-cargo 65-75%, Row 24). '
            'Higher than LL because PS uses hydraulics during setting/hauling.')

    # --- Industrial Transport ---
    add_row('B', 'LF_move', 'Engine load factor during the cruise phase (Transit Load Factor)',
            'ALL', 'TP', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) — general vessel cruise parameters',
            'R22-R23',
            'Transport vessel transit: 80% MCR cruise.')

    add_row('B', 'LF_work', 'Engine load factors for the fishing operations phase (Fishing Load Factor)',
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

    add_row('B', 'LF_move', 'Engine load factor during the cruise phase (Transit Load Factor)',
            'ALL', 'ALL', 'APW', 'ALL', 0.79, 0.73, 0.80,
            'fraction of MCR', 'Triangular',
            'Kim et al. (2023) JMSE 11:1488 — coastal small fishing vessels',
            'R28',
            'APW transit: Coastal vessels 79% load (Row 28). '
            'Range 73-80% covers coastal-to-offshore variation.')

    add_row('B', 'LF_work', 'Engine load factors for the fishing operations phase (Fishing Load Factor)',
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
    add_row('B', 'LF_move', 'Engine load factor during the cruise phase (Transit Load Factor)',
            'ALL', 'ALL', 'I', 'ALL', 0.80, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Eyring et al. (2005) + Perčić et al. (2020) — general marine engines',
            'R22-R23,R27',
            'General Industrial fallback: 80% MCR cruise.')

    add_row('B', 'LF_work', 'Engine load factors for the fishing operations phase (Fishing Load Factor)',
            'ALL', 'ALL', 'I', 'ALL', 0.50, np.nan, np.nan,
            'fraction of MCR', 'Triangular',
            'Perčić et al. (2020) — general marine auxiliary engines, Aux=0.5',
            'R27',
            'General Industrial fallback: 50% aux load.')

    # ========================================================================
    # C. Core fuel and emission parameters (Core Fuel & Emission) — Sheet 1 Row 30-43
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
    add_row('C', 'SFR_map', 'Specific fuel consumption rate (Specific Fuel Consumption Rate)',
            'ALL', 'ALL', 'I', '>=12m', 0.000200, 0.000155, 0.000250,
            'tFuel/kWh', 'Lognormal',
            sfr_source_main,
            'R31,R36',
            'Industrial ghg_lca engine diesel: 200 g/kWh = 0.00020 t/kWh. '
            'Range 155-250 g/kWh from literature. '
            'Row 31: 0.00020 tFuel/kWh; Row 36: ghg_lca=215 g/kWh.')

    # Smallscale SFR (<12m, gasoline/diesel mix)
    add_row('C', 'SFR_map', 'Specific fuel consumption rate (Specific Fuel Consumption Rate)',
            'ALL', 'ALL', 'APW', '<12m', 0.000350, 0.000250, 0.000450,
            'tFuel/kWh', 'Lognormal',
            'Winther (2007) Danish navigation emissions; Greer et al. (2019)',
            'R32',
            'Smallscale: 350 g/kWh. Higher SFR due to less efficient small engines. '
            'Range 250-450 g/kWh. Row 32: 0.00035 tFuel/kWh.')

    # Main vs Aux diesel SFR (for detailed fuel modeling)
    add_row('C', 'SFR_Main_Diesel', 'specific diesel consumption of main engines',
            'ALL', 'ALL', 'I', 'ALL', 0.000215, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sustainable Ships (2022)',
            'R36',
            'Main engine diesel: 215 g/kWh (Row 36).')

    add_row('C', 'SFR_Aux_Diesel', 'specific diesel consumption of auxiliary engines',
            'ALL', 'ALL', 'I', 'ALL', 0.000210, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sustainable Ships (2022)',
            'R37',
            'Auxiliary engine diesel: 210 g/kWh (Row 37).')

    # Alternative fuel SFR (for scenario modeling — S4, S14)
    add_row('C', 'SFR_Methanol_Diesel_80', 'methanol-diesel blend (80%energy substitution) SFR',
            'ALL', 'ALL', 'ALL', 'ALL', 0.000439, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sheet 1 Row 34',
            'R34',
            '438.58 g/kWh = 0.000439 t/kWh. Used in scenario S4, S14.')

    add_row('C', 'SFR_H2_Diesel_80', 'hydrogen-diesel blend (80%energy substitution) SFR',
            'ALL', 'ALL', 'ALL', 'ALL', 0.000112, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'Sheet 1 Row 35',
            'R35',
            '112.32 g/kWh = 0.000112 t/kWh. Used in scenario S14.')

    # ------------------------------------------------------------------
    # C1b. SFOC-Load Conversion Formula (Diesel load-Oil consumption) — Row 30
    # ------------------------------------------------------------------
    # Row 30: SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28)
    #   L = Engine load factor (Load Factor, fraction of rated power)
    #   Conditions of application: ≥12m, four-stroke diesel main engine
    #   Source: Jalkanen et al. (2012) ACP 12:2641-2659
    #   Example calculation:
    #     L=0.80 (Cruise): factor = 0.455×0.64 − 0.71×0.80 + 1.28 = 1.003
    #     L=0.50 (LL fishing operation): factor = 0.455×0.25 − 0.71×0.50 + 1.28 = 1.039
    #     L=0.19 (APW fishing operation): factor = 0.455×0.0361 − 0.71×0.19 + 1.28 = 1.162

    add_row('C', 'SFOC_LOAD_COEFF_A', 'SFOC-quadratic load coefficient (L²)',
            'ALL', 'ALL', 'ALL', '>=12m', 0.455, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Jalkanen et al. (2012) Atmos. Chem. Phys. 12:2641-2659',
            'R30',
            'SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28). '
            'It only applies to≥12m four-stroke diesel main engine. L=Engine load factor(LF, Quantified power ratio).')

    add_row('C', 'SFOC_LOAD_COEFF_B', 'SFOC-linear load coefficient (L)',
            'ALL', 'ALL', 'ALL', '>=12m', -0.71, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Jalkanen et al. (2012) Atmos. Chem. Phys. 12:2641-2659',
            'R30',
            'A single item factor. The parabolic formula is L=0.78 Min. value in the vicinity(Most economics).')

    add_row('C', 'SFOC_LOAD_COEFF_C', 'SFOC-load-equation constant',
            'ALL', 'ALL', 'ALL', '>=12m', 1.28, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Jalkanen et al. (2012) Atmos. Chem. Phys. 12:2641-2659',
            'R30',
            'Constant items. L=0(Rust)Hour SFOC as the base value 1.28 Multiply; L=1(Full load)Hour≈1.025 Multiply.')

    add_row('C', 'SFOC_LOAD_APPLICABILITY', 'SFOC-load-equation applicability',
            'ALL', 'ALL', 'I', '>=12m', 1.0, np.nan, np.nan,
            'binary flag', 'Discrete',
            'Jalkanen et al. (2012); It only applies to≥12m four-stroke diesel main engine',
            'R30',
            '1=Application. auxiliary engines use a fixed efficient load(75%)+Fixed SFR(220 g/kWh), This formula is not applicable. ')

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
    # Upstream production of fuel/Indirect carbon emission factors for transport processes. 
    # Source: ecoinvent v3 cutoff Database, 1000 The Monte Carlo simulation. 
    # Units: kg CO₂eq / kg fuel (Functional units = 1 kg Fuel supply)

    add_row('C', 'EF_WTT_DIESEL', 'upstream diesel(WTT)carbon emission factor',
            'ALL', 'ALL', 'ALL', 'ALL', 0.369, 0.318, 0.441,
            'kg CO₂eq/kg diesel', 'Lognormal',
            'Ecoinvent v3 — market for diesel | diesel | Cutoff, U - RoW '
            '(1000 MC simulations)',
            'Ecoinvent_Diesel_WTT',
            '1 kg Upstream diesel production and transport carbon emissions (Cradle-to-Tank). '
            'Process: market for diesel | Cutoff, U - RoW. '
            'Mean=0.369, SD=0.031, Median=0.366, 95% CI [0.318, 0.441]. '
            'This and the burner(EF_CO2_Diesel)Add complete Well-to-Wake emissions. ')

    add_row('C', 'EF_WTT_GASOLINE', 'upstream petrol(WTT)carbon emission factor',
            'ALL', 'ALL', 'APW', 'ALL', 0.535, 0.489, 0.595,
            'kg CO₂eq/kg petrol', 'Lognormal',
            'Ecoinvent v3 — market for petrol, two-stroke blend | '
            'petrol, two-stroke blend | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_Gasoline_WTT',
            '1 kg Upstream production and transport of carbon emissions from gasoline (Cradle-to-Tank). '
            'Process: market for petrol, two-stroke blend | Cutoff, U - GLO. '
            'Mean=0.535, SD=0.029, Median=0.532, 95% CI [0.489, 0.595]. '
            'This and the burner(EF_CO2_Gasoline)Add complete Well-to-Wake emissions. ')

    # ------------------------------------------------------------------
    # C2b. Combustion (Tank-to-Wake, TTW) — CO₂ Emission Factors
    # ------------------------------------------------------------------
    # Direct fuel combustion CO₂emission factor. 

    # CO2 from diesel — IMO (2020) Fourth GHG Study
    add_row('C', 'EF_CO2_Diesel', 'diesel CO₂combustion emission factor',
            'ALL', 'ALL', 'I', 'ALL', 3.206, 3.206, 3.206,
            'tCO2/tFuel', 'Discrete',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            'Light diesel for boat(MDO)Incendiary CO₂emission factor. '
            'Based on carbon mass ratio(~87.44%)dimensionless conversion factor from the stoichiometric complete-oxidation equation(CF). '
            '3.206 kg CO₂/kg diesel = 3206 g/kgFuel. '
            'Original value [u]: 3.17 (Korican 2023), Update As IMO Official value [v].')

    # CO2 from gasoline — EPA (2025)
    add_row('C', 'EF_CO2_Gasoline', 'petrol CO₂combustion emission factor',
            'ALL', 'ALL', 'APW', 'ALL', 3.158, np.nan, np.nan,
            'tCO2/tFuel', 'Normal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Climate Leadership. Washington, DC.',
            'EPA_2025',
            'Cars/Gasoline burning from ships CO₂emission factor. '
            'Original: 8.78 kg/gallon ÷ 2.78 kg/gallon = 3.158 kg CO₂/kg petrol. '
            'Source: EPA Table 2 Mobile Combustion CO2, Motor Gasoline. '
            'Original value [u]: 3.01, Update As EPA Official value [v].')

    # ------------------------------------------------------------------
    # C2c. Combustion — CH₄ (Methane) Emission Factors
    # ------------------------------------------------------------------
    # methane emissions vary by engine stroke technology and fuel type, specified by fuel and engine type. 

    # Diesel CH4 — IMO (2020) Fourth GHG Study (g/kWh, IMO Standard Unit)
    add_row('C', 'EF_CH4_DIESEL_MSD', 'diesel CH₄emission factor—medium-speed four-stroke(MSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.010, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            'medium-speed diesel engine (Medium-Speed Diesel, MSD) methane slip factor. '
            'most distant-water fishing vessels use medium-speed four-stroke diesel engines, applies to primary fishing vessels and auxiliary engines. '
            '0.010 g/kWh (IMO Standard Unit).')

    add_row('C', 'EF_CH4_DIESEL_SSD', 'diesel CH₄emission factor—low-speed two-stroke(SSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.010, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            'low-speed diesel engine (Slow-Speed Diesel, SSD) methane slip factor. '
            'applies to main engines of large transshipment vessels. '
            '0.010 g/kWh (IMO Standard Unit).')

    # Gasoline CH4 — EPA (2025) Table 5, Ships and Boats
    add_row('C', 'EF_CH4_GASOLINE_2STROKE', 'petrol CH₄emission factor—two-stroke outboard engine',
            'ALL', 'ALL', 'APW', 'ALL', 3.76, np.nan, np.nan,
            'g/kgFuel', 'Lognormal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Table 5: Mobile Combustion CH4 and N2O for Non-Road Vehicles, Ships and Boats.',
            'EPA_2025',
            'methane emission factor for conventional two-stroke petrol outboard engines. '
            'Original: 10.45 g/gallon ÷ 2.78 kg/gallon = 3.76 g CH₄/kg petrol. '
            'two-stroke engine scavenging releases unburned hydrocarbons(Ham CH₄)The escape is significantly higher.')

    add_row('C', 'EF_CH4_GASOLINE_4STROKE', 'petrol CH₄emission factor—four-stroke outboard engine',
            'ALL', 'ALL', 'APW', 'ALL', 1.50, np.nan, np.nan,
            'g/kgFuel', 'Lognormal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Table 5: Mobile Combustion CH4 and N2O for Non-Road Vehicles, Ships and Boats.',
            'EPA_2025',
            'methane emission factor for modern four-stroke petrol outboard engines. '
            'Original: 4.18 g/gallon ÷ 2.78 kg/gallon = 1.50 g CH₄/kg petrol. '
            'Its more perfect, CH₄The emissions are about two-stroke 40%.')

    # ------------------------------------------------------------------
    # C2d. Combustion — N₂O (Nitrous Oxide) Emission Factors
    # ------------------------------------------------------------------

    add_row('C', 'EF_N2O_DIESEL_MSD', 'diesel N₂O emission factor—medium-speed four-stroke(MSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.030, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            'medium-speed diesel engine (MSD) N₂O emission factor. '
            'applies to primary fishing vessels and auxiliary engines. '
            '0.030 g/kWh (IMO Standard Unit). '
            'Original Universal Value: 0.14 g/kgFuel (Korican 2023).')

    add_row('C', 'EF_N2O_DIESEL_SSD', 'diesel N₂O emission factor—low-speed two-stroke(SSD)',
            'ALL', 'ALL', 'I', 'ALL', 0.020, np.nan, np.nan,
            'g/kWh', 'Lognormal',
            'IMO (2020) Fourth IMO GHG Study 2020. London, UK: IMO.',
            'IMO_2020',
            'low-speed diesel engine (SSD) N₂O emission factor. '
            'applies to main engines of large transshipment vessels. '
            '0.020 g/kWh (IMO Standard Unit).')

    add_row('C', 'EF_N2O_GASOLINE', 'petrol N₂O emission factor',
            'ALL', 'ALL', 'APW', 'ALL', 0.04, np.nan, np.nan,
            'g/kgFuel', 'Lognormal',
            'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
            'Table 5: Mobile Combustion CH4 and N2O for Non-Road Vehicles, Ships and Boats.',
            'EPA_2025',
            'Gasoline N₂O emission factor (Two-strike and four-stroke do not differ significantly, EPA Harmonization of benchmarks) . '
            'Original: 0.11 g/gallon ÷ 2.78 kg/gallon = 0.04 g N₂O/kg petrol.')

    # ------------------------------------------------------------------
    # C3. GWP — Global Warming Potential — Row 39
    # ------------------------------------------------------------------
    add_row('C', 'GWP_CH4_100yr', 'methane 100 year global warming potential',
            'ALL', 'ALL', 'ALL', 'ALL', 28.5, 27.0, 30.0,
            'kgCO2e/kgCH4', 'Uniform',
            'IPCC AR5/AR6; Sheet 1 Row 39',
            'R39',
            'CH4 GWP-100: IPCC range 27-30, midpoint 28.5 (Row 39).')

    add_row('C', 'GWP_N2O_100yr', 'nitrous oxide 100 year global warming potential',
            'ALL', 'ALL', 'ALL', 'ALL', 273.0, np.nan, np.nan,
            'kgCO2e/kgN2O', 'Discrete',
            'IPCC AR6; Sheet 1 Row 39',
            'R39',
            'N2O GWP-100: 273 (IPCC AR6, Row 39).')

    # ------------------------------------------------------------------
    # C4. FC_LOOKUP — Fuel Coefficient time series — Row 43
    # ------------------------------------------------------------------
    add_row('C', 'FC_LOOKUP_Baseline_Year', 'fuel-efficiency time-factor baseline year',
            'ALL', 'ALL', 'ALL', 'ALL', 2000, np.nan, np.nan,
            'year', 'Discrete',
            'Yanmar marine engine data (interpolated); Sheet 1 Row 43',
            'R43',
            'FC=1.0 at year 2000 (baseline). Pre-2000 >1.0 (less efficient), '
            'post-2004 =0.99 (stable). Row 43.')

    add_row('C', 'FC_LOOKUP_Min', 'minimum fuel-efficiency time factor',
            'ALL', 'ALL', 'ALL', 'ALL', 0.99, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Yanmar data; 2004-2016 stable period',
            'R43',
            'Minimum FC = 0.99 (most efficient era, 2004-2016). Row 43.')

    add_row('C', 'FC_LOOKUP_Max', 'maximum fuel-efficiency time factor',
            'ALL', 'ALL', 'ALL', 'ALL', 1.21, np.nan, np.nan,
            'dimensionless', 'Discrete',
            'Yanmar data; 1950-1951 peak',
            'R43',
            'Maximum FC = 1.21 (least efficient era, 1950-1951). Row 43.')

    # ========================================================================
    # D. auxiliary engine power parameters (Auxiliary Engine Power Ratio) — Sheet 1 Row 44-46
    # ========================================================================
    # Row 44: Overall aux ≈ 38.8% of ghg_lca power
    # Row 45: Detailed ship comparison data (short vs long routes)
    # Row 46: Three-tier classification by GT and age:
    #   - GT>1500 → 0.33-0.40 (large, heavy hydraulics + cold storage)
    #   - 500<GT<=1500 + post-1990 → 0.25-0.33 (medium, transitional)
    #   - GT<=500 or pre-1990 → 0.15-0.25 (small/old, minimal cold storage)

    add_row('D', 'AUX_POWER_RATIO', 'auxiliary engine/main engine power ratio (Overall average)',
            'ALL', 'ALL', 'ALL', 'ALL', 0.388, 0.33, 0.54,
            'ratio', 'Triangular',
            'Sheet 1 Row 44-46',
            'R44',
            'Overall mean: aux = 38.8% of ghg_lca power. '
            'Range: 0.33 (25/75 split, Row 46) to 0.54 (extreme).')

    add_row('D', 'AUX_POWER_RATIO_LARGE', 'auxiliary engine/main engine power ratio (large vessels GT>1500)',
            'ALL', 'ALL', 'ALL', '>=12m', 0.365, 0.33, 0.40,
            'ratio', 'Triangular',
            'Sheet 1 Row 46 — size-mandated high-power category',
            'R46',
            'Large vessels (GT>1500): heavy hydraulics + large cold storage '
            '→ aux ratio forced into 0.33-0.40.')

    add_row('D', 'AUX_POWER_RATIO_MEDIUM',
            'auxiliary engine/main engine power ratio (Medium-sized boats 500<GT<=1500, post-1990)',
            'ALL', 'ALL', 'ALL', 'ALL', 0.29, 0.25, 0.33,
            'ratio', 'Triangular',
            'Sheet 1 Row 46 — transitional category',
            'R46',
            'Medium vessels (500<GT<=1500, post-1990): modern equipment '
            '→ aux ratio 0.25-0.33.')

    add_row('D', 'AUX_POWER_RATIO_SMALL',
            'auxiliary engine/main engine power ratio (Small/Old boat GT<=500 or pre-1990)',
            'ALL', 'ALL', 'ALL', '<12m', 0.20, 0.15, 0.25,
            'ratio', 'Triangular',
            'Sheet 1 Row 46 — dual-low category',
            'R46',
            'Small/old vessels (GT<=500 or pre-1990): no large cold storage '
            '→ aux ratio 0.15-0.25.')

    # ========================================================================
    # E. Ship-body material and construction parameters (Hull Material & Construction) — Sheet 1 Row 70-84
    # ========================================================================

    # ------------------------------------------------------------------
    # E1. Material Ratios — Row 72-73
    # ------------------------------------------------------------------
    # Row 72: Detailed material composition per kg catch (material shares of purse-seine vessel hulls)
    # Row 73: "Ship Body Steel LSW 80%, The rest 20%for other structures and systems
    #          (10%Seen as an engine, 5%Its considered a copper or an electrical system) "
    # Model (ghg_lca.py): STEEL=0.85, ENGINE=0.10, COPPER=0.05
    # Note: 80% of LSW is steel hull; remaining 20% = 10% engine + 5% copper + 5% other
    # The model normalizes to: steel=85%, engine=10%, copper=5% (sum=100%)

    add_row('E', 'MATERIAL_RATIO_STEEL', 'hull steel mass fraction',
            'ALL', 'ALL', 'ALL', 'ALL', 0.85, np.nan, np.nan,
            'fraction of GT', 'Normal',
            'Sheet 1 Row 72-73; ghg_lca.py model constants',
            'R72-R73',
            'Steel hull = 85% of GT. Row 73: "Ship Body Steel LSW 80%". '
            'Row 72: detailed composition confirms ~90% steel for PS hull.')

    add_row('E', 'MATERIAL_RATIO_ENGINE', 'Quality share of engine irons',
            'ALL', 'ALL', 'ALL', 'ALL', 0.10, np.nan, np.nan,
            'fraction of GT', 'Normal',
            'Sheet 1 Row 73; ghg_lca.py model constants',
            'R73',
            'Engine iron/steel = 10% of GT. Row 73: "10%Seen as an engine".')

    add_row('E', 'MATERIAL_RATIO_COPPER', 'Proportion of copper quality in electrical systems',
            'ALL', 'ALL', 'ALL', 'ALL', 0.05, np.nan, np.nan,
            'fraction of GT', 'Normal',
            'Sheet 1 Row 73; ghg_lca.py model constants',
            'R73',
            'Copper = 5% of GT. Row 73: "5%Its considered a copper or an electrical system".')

    # ------------------------------------------------------------------
    # E2. Material Emission Factors — Row 68-71
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # E2b. Vessel Construction Emission Factors (cradle-to-gate, ecoinvent LCA)
    # ------------------------------------------------------------------
    # The following carbon emission factors are derived from ecoinvent v3 cutoff Database, 
    # Every process runs 1000 Monte Carlo Simulation of Statistics. 
    # Units: kg CO₂eq / kg vessel (Functional units = 1 kg Ship construction)
    #
    # Description of the scope of application (per user instruction):
    #   - transshipment vessel/support vessel (TS): use the steel purse-seine vessel factor
    #   - small longline vessels (<12m, wood): use the wooden purse-seine vessel factor
    #   - large longline vessels (>=12m, steel): use the factor for steel longline vessels

    # PS steel construction (>=12m) — also applies to TS/aux
    add_row('E', 'EF_BUILD_PS_STEEL', 'construction emission factor for steel purse-seine vessels (cradle-to-gate)',
            'ALL', 'PS', 'I', '>=12m',
            2.421, 2.332, 2.528,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Steel',
            '1 kg purse seiner steel construction. '
            'Mean=2.421, SD=0.052, Median=2.415, 95% CI [2.332, 2.528]. '
            'Also applies to: TS/auxiliary vessels (transshipment vessel/Auxiliary ships use the purse seine steel factor uniformly).')

    # PS wood construction (<12m) — also applies to LL small boats, TS/aux small
    add_row('E', 'EF_BUILD_PS_WOOD', 'construction emission factor for wooden purse-seine vessels (cradle-to-gate)',
            'ALL', 'PS', 'APW', '<12m',
            0.578, 0.513, 0.678,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner, wood | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Wood',
            '1 kg purse seiner wood construction. '
            'Mean=0.578, SD=0.040, Median=0.575, 95% CI [0.513, 0.678]. '
            'Also applies to: LL small boats <12m (small longline vessels), '
            'TS/aux small boats (transshipment vessel/Auxiliary ship).')

    # LL steel construction (>=12m)
    add_row('E', 'EF_BUILD_LL_STEEL', 'construction emission factor for steel longline vessels (cradle-to-gate)',
            'ALL', 'LL', 'I', '>=12m',
            1.956, 1.877, 2.069,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Ecoinvent v3 — market for long liner, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_LL_Steel',
            '1 kg long liner steel construction. '
            'Mean=1.956, SD=0.052, Median=1.949, 95% CI [1.877, 2.069].')

    # LL wood construction (<12m) — same as PS wood
    add_row('E', 'EF_BUILD_LL_WOOD', 'construction emission factor for wooden longline vessels (same as wooden purse-seine vessels)',
            'ALL', 'LL', 'APW', '<12m',
            0.578, 0.513, 0.678,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Same EF_BUILD_PS_WOOD — Longline boat construction and maintenance factor for purse seine boat',
            'Ecoinvent_PS_Wood',
            'small longline vessels (<12m, wood) Construction of carbon emissions: same factor as wooden purse-seine vessels 0.578 kg CO₂eq/kg. '
            'Per user instruction: Factors for the construction of longline boats and the maintenance factor for the use of purse-seine boats.')

    # TS/aux construction — same as PS steel
    add_row('E', 'EF_BUILD_TS', 'transshipment vessel/support-vessel construction emission factor (same as steel purse-seine vessels)',
            'ALL', 'TP', 'I', 'ALL',
            2.421, 2.332, 2.528,
            'kg CO₂eq/kg vessel', 'Lognormal',
            'Same EF_BUILD_PS_STEEL — Harmonizing the use of the purse-seine steel factor for trans-shipment vessels and ancillary vessels',
            'Ecoinvent_PS_Steel',
            'transshipment vessel/Carbon emissions from construction of support vessels: same factor as steel purse-seine vessels 2.421 kg CO₂eq/kg. '
            'Per user instruction: Factors for the construction and maintenance of trans-shipment and auxiliary vessels for the uniform use of seine steel vessels.')

    # ------------------------------------------------------------------
    # E2c. Vessel Maintenance Emission Factors (cradle-to-gate, ecoinvent LCA)
    # ------------------------------------------------------------------
    # The following maintenance of carbon emission factors is derived from ecoinvent v3 cutoff Database, 
    # Every process runs 1000 Monte Carlo Simulation of Statistics. 
    # Units: kg CO₂eq / kg vessel maintenance (Functional units = 1 kg Ship maintenance)

    # PS steel maintenance (>=12m) — also applies to TS/aux
    add_row('E', 'EF_MAINT_PS_STEEL', 'maintenance emission factor for steel purse-seine vessels (cradle-to-gate)',
            'ALL', 'PS', 'I', '>=12m',
            6.744, 6.627, 6.883,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner maintenance, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Steel_Maint',
            '1 kg purse seiner steel maintenance. '
            'Mean=6.744, SD=0.067, Median=6.740, 95% CI [6.627, 6.883]. '
            'Also applies to: TS/auxiliary vessels (transshipment vessel/Auxiliary ships use the purse seine steel factor uniformly).')

    # PS wood maintenance (<12m) — also applies to LL small boats, TS/aux small
    add_row('E', 'EF_MAINT_PS_WOOD', 'maintenance emission factor for wooden purse-seine vessels (cradle-to-gate)',
            'ALL', 'PS', 'APW', '<12m',
            1.289, 1.179, 1.437,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Ecoinvent v3 — market for purse seiner maintenance, wood | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_PS_Wood_Maint',
            '1 kg purse seiner wood maintenance. '
            'Mean=1.289, SD=0.065, Median=1.282, 95% CI [1.179, 1.437]. '
            'Also applies to: LL small boats <12m (small longline vessels), '
            'TS/aux small boats (transshipment vessel/Auxiliary ship).')

    # LL steel maintenance (>=12m)
    add_row('E', 'EF_MAINT_LL_STEEL', 'maintenance emission factor for steel longline vessels (cradle-to-gate)',
            'ALL', 'LL', 'I', '>=12m',
            4.450, 3.777, 5.376,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Ecoinvent v3 — market for long liner maintenance, steel | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_LL_Steel_Maint',
            '1 kg long liner steel maintenance. '
            'Mean=4.450, SD=0.385, Median=4.417, 95% CI [3.777, 5.376].')

    # LL wood maintenance (<12m) — same as PS wood
    add_row('E', 'EF_MAINT_LL_WOOD', 'maintenance emission factor for wooden longline vessels (same as wooden purse-seine vessels)',
            'ALL', 'LL', 'APW', '<12m',
            1.289, 1.179, 1.437,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Same EF_MAINT_PS_WOOD — Longline boat construction and maintenance factor for purse seine boat',
            'Ecoinvent_PS_Wood_Maint',
            'small longline vessels (<12m, wood) Maintenance of carbon emissions: same factor as wooden purse-seine vessels 1.289 kg CO₂eq/kg. '
            'Per user instruction: Factors for the construction of longline boats and the maintenance factor for the use of purse-seine boats.')

    # TS/aux maintenance — same as PS steel
    add_row('E', 'EF_MAINT_TS', 'transshipment vessel/support-vessel maintenance emission factor (same as steel purse-seine vessels)',
            'ALL', 'TP', 'I', 'ALL',
            6.744, 6.627, 6.883,
            'kg CO₂eq/kg maintenance', 'Lognormal',
            'Same EF_MAINT_PS_STEEL — Harmonizing the use of the purse-seine steel factor for trans-shipment vessels and ancillary vessels',
            'Ecoinvent_PS_Steel_Maint',
            'transshipment vessel/Auxiliary ships maintain carbon emissions: same factor as steel purse-seine vessels 6.744 kg CO₂eq/kg. '
            'Per user instruction: Factors for the construction and maintenance of trans-shipment and auxiliary vessels for the uniform use of seine steel vessels.')

    # ------------------------------------------------------------------
    # E3. Lifespan Parameters — Row 78-82
    # ------------------------------------------------------------------
    # Row 78: "25% For repairs and maintenance"
    # Row 79: "Ship Body Steel Replacement Ratio: Every 2 Yearly replacement 12%"
    # Row 80: "Life of ships 30 years; Engines are replaced once in the lifetime of the ship"
    # Row 81: "hull 30 years, main engine 10 years; Increased use of steel 25% (hull) and 50% (main engine) For maintenance"
    # Row 82: "hull service life (steel) : 30 years; hull service life (Wood) : 40 years; Engine replacements: 1 Number of times"

    add_row('E', 'LIFESPAN_HULL', 'hull service life (steel)',
            'ALL', 'ALL', 'ALL', 'ALL', 30, np.nan, np.nan,
            'years', 'Discrete',
            'Sheet 1 Row 80-82',
            'R80-R82',
            'Steel hull lifespan: 30 years. '
            'Wood hull: 40yr (Row 82, not used in current model).')

    add_row('E', 'LIFESPAN_ENGINE', 'engine service life (replacement interval)',
            'ALL', 'ALL', 'ALL', 'ALL', 10, np.nan, np.nan,
            'years', 'Discrete',
            'Sheet 1 Row 80-82',
            'R80-R82',
            'Engine lifespan: 10 years (Row 80-81). '
            'Replaced once during 30yr hull life = 2 engines total.')

    add_row('E', 'LIFESPAN_COPPER', 'Electricity system update cycle',
            'ALL', 'ALL', 'ALL', 'ALL', 8, np.nan, np.nan,
            'years', 'Discrete',
            'ghg_lca.py model constants; Ecoinvent reference',
            '—',
            '⚠ Not yet Excel direct source found in. Current model default: 8 years. '
            'Copper electric system renewal cycle (wiring, switchgear).')

    # ------------------------------------------------------------------
    # E4. Maintenance Parameters — Row 78-81
    # ------------------------------------------------------------------
    add_row('E', 'MAINTENANCE_RATE_STEEL', 'Shipwork steel every 2 Annual replacement rate for maintenance',
            'ALL', 'ALL', 'ALL', 'ALL', 0.12, np.nan, np.nan,
            'fraction per event', 'Discrete',
            'Sheet 1 Row 79',
            'R79',
            'Every 2 Yearly replacement 12%Ship Body Steel (Row 79). '
            'Model: is_steel_maint triggers every 2yr (skipping hull replacement years), '
            'replaces 12% of steel_w.')

    add_row('E', 'MAINTENANCE_INTERVAL_STEEL', 'Maintenance interval for hull steel',
            'ALL', 'ALL', 'ALL', 'ALL', 2, np.nan, np.nan,
            'years', 'Discrete',
            'Sheet 1 Row 79; ghg_lca.py maint_interval=2',
            'R79',
            'Steel maintenance occurs every 2 years (Row 79).')

    add_row('E', 'MAINTENANCE_EXTRA_STEEL_PCT', 'Additional surplus of steel in the construction phase (Maintenance provision)',
            'ALL', 'ALL', 'ALL', 'ALL', 0.25, np.nan, np.nan,
            'fraction of base steel', 'Discrete',
            'Sheet 1 Row 81',
            'R81',
            'Increased use of steel for construction 25%For hull maintenance, 50%allowance for main engine maintenance (Row 81).')

    # ------------------------------------------------------------------
    # E5. Anti-fouling Paint — Row 83-84
    # ------------------------------------------------------------------
    add_row('E', 'ANTIFOUL_PAINT_COATING_RATE', 'The average amount of paint is covered in anti-fouling paint',
            'ALL', 'ALL', 'ALL', 'ALL', 0.11, np.nan, np.nan,
            'L/tonne catch', 'Discrete',
            'Sheet 1 Row 83',
            'R83',
            'Average clothing volume: 0.11 L/Ton catch (Row 83). Cursor Frequency: Every 2 Annual.')

    add_row('E', 'ANTIFOUL_PAINT_RELEASE_FRAC', 'Proportion of marine releases of anti-fouling paints',
            'ALL', 'ALL', 'ALL', 'ALL', 2.0 / 3.0, np.nan, np.nan,
            'fraction', 'Discrete',
            'Sheet 1 Row 83-84',
            'R83-R84',
            '2/3 of antifoul paint released to ocean environment (Row 83). '
            'Row 84: Degradation rate of anti-fouling paints: 2/3 Release to the marine environment.')

    # ------------------------------------------------------------------
    # E6. Steel Recycling — Row 76-77
    # ------------------------------------------------------------------
    add_row('E', 'STEEL_RECYCLING_RATE', 'Recovery rate for steel at end of life',
            'ALL', 'ALL', 'ALL', 'ALL', 0.90, np.nan, np.nan,
            'fraction', 'Discrete',
            'Sheet 1 Row 76',
            'R76',
            'Steel and nylon are recoverable at end of life, The recovery rate is taken into account 90% (Row 76).')

    add_row('E', 'STEEL_RECYCLED_CONTENT_RATE', 'Use of recovered steel in new ships',
            'ALL', 'ALL', 'ALL', 'ALL', 0.50, np.nan, np.nan,
            'fraction', 'Discrete',
            'Sheet 1 Row 77',
            'R77',
            'Use of recycled steel in the construction of new ships 50% (Row 77).')

    # ========================================================================
    # F. Parameters for the consumption of gear material (Gear Material Consumption) — Sheet 1 Row 51-67
    # ========================================================================

    # ------------------------------------------------------------------
    # F1. Gear Intensity (gear_int) — Row 55-58
    # ------------------------------------------------------------------
    # Row 55: "Model Interruption" — methodology note
    # Row 56: PS small: ['uniform', 17.9, 9.12] kg/m vessel length
    # Row 57: PS large: ['uniform', 251.0, 54.0] kg/m vessel length
    # Row 58: LL: ['uniform', 0.490, 0.120] kg/hook
    #
    # IMPORTANT: Excel explicitly says "even distribution" (Uniform distribution).
    # Parameters [a, b] are the range boundaries [min, max] after sorting.
    # Best = (min + max) / 2 — midpoint of uniform range.
    # This is NOT a Normal distribution — there is no std.

    # PS small (<12m): uniform [9.12, 17.9] kg/m → [0.00912, 0.0179] t/m
    gear_int_ps_small_low  = min(17.9, 9.12) / 1000        # 0.00912
    gear_int_ps_small_high = max(17.9, 9.12) / 1000        # 0.01790
    gear_int_ps_small_best = (9.12 + 17.9) / (2 * 1000)    # 0.01351
    add_row('F', 'gear_int_PS', 'purse-seine gear mass per unit vessel length (small vessels <12m)',
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
            'small artisanal purse-seine fisheries(8-12m fishing vessel), Mozambique fisheries data.')

    # PS large (>=12m): uniform [54.0, 251.0] kg/m → [0.054, 0.251] t/m
    gear_int_ps_large_low  = min(251.0, 54.0) / 1000        # 0.054
    gear_int_ps_large_high = max(251.0, 54.0) / 1000        # 0.251
    gear_int_ps_large_best = (251.0 + 54.0) / (2 * 1000)    # 0.1525
    add_row('F', 'gear_int_PS', 'purse-seine gear mass per unit vessel length (large vessels >=12m)',
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
            'Indian purse-seine fisheries(11-24m fishing vessel).')

    # LL: uniform [0.120, 0.490] kg/hook → [0.03333, 0.13611] t/m
    # Conversion: kg/hook ÷ (0.0036 m/hook × 1000 kg/t) = kg/hook / 3.6
    gear_int_ll_low  = min(0.490, 0.120) / (0.0036 * 1000)   # 0.03333
    gear_int_ll_high = max(0.490, 0.120) / (0.0036 * 1000)   # 0.13611
    gear_int_ll_best = (0.490 + 0.120) / (2 * 0.0036 * 1000) # 0.08472
    add_row('F', 'gear_int_LL', 'longline gear mass per unit vessel length',
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
            'Longline longlines for longfin tuna in the Egyptian Mediterranean(4000-4500 hooks, 14-17m, 70-130HP).')

    # ------------------------------------------------------------------
    # F2. Gear Material Composition — Row 52-54, 59-60
    # ------------------------------------------------------------------
    # Row 52-53: PS net composition (nylon 50%, lead 28%, EVA 20%, Polysteel 2%)
    # Row 54: LL composition (mainline: nylon; hooks: metal/alloy)
    # Row 59: PS detailed: PA6=64.2%, EVA=9.7%, Steel=26.1% (93.2t ±16.2 per vessel)
    # Row 60: Alternative composition: Nylon 66.69%, EVA 27.43%, Polysteel 5.88%

    add_row('F', 'GEAR_MATERIAL_NYLON_PS', 'purse-seine nylon (PA6) material share',
            'ALL', 'PS', 'ALL', 'ALL', 0.642, np.nan, np.nan,
            'mass fraction', 'Discrete',
            'Sheet 1 Row 59',
            'R59',
            'PA6 (nylon) = 64.2% of PS net weight (Row 59). '
            'Includes netting, ropes, float lines. '
            'Alternative composition (Row 60): 66.69% nylon.')

    add_row('F', 'GEAR_MATERIAL_EVA_PS', 'purse seine EVA Float ratio',
            'ALL', 'PS', 'ALL', 'ALL', 0.097, np.nan, np.nan,
            'mass fraction', 'Discrete',
            'Sheet 1 Row 59',
            'R59',
            'EVA floats = 9.7% of PS net weight (Row 59). '
            'Alternative composition (Row 60): 27.43% EVA.')

    add_row('F', 'GEAR_MATERIAL_STEEL_PS', 'purse-seine metal components (steel) share',
            'ALL', 'PS', 'ALL', 'ALL', 0.261, np.nan, np.nan,
            'mass fraction', 'Discrete',
            'Sheet 1 Row 59',
            'R59',
            'Steel components = 26.1% of PS net weight (Row 59). '
            'Includes chains, rings, wire rope. '
            'Row 52-53 alternative: lead 28%, steel 2%.')

    # LL material
    add_row('F', 'GEAR_MATERIAL_NYLON_LL', 'nylon share of the longline mainline',
            'ALL', 'LL', 'ALL', 'ALL', 1.0, np.nan, np.nan,
            'mass fraction (mainline)', 'Discrete',
            'Sheet 1 Row 54',
            'R54',
            'LL mainline: nylon (Row 54). Hooks: metal/alloy. '
            '⚠ Specific percentage of metal material in hooks is missing Sheet 1 Its clearly given, Additional requirements.')

    # ------------------------------------------------------------------
    # F3. Gear Emission Factors (Material level, cradle-to-gate) — Row 69
    # ------------------------------------------------------------------
    # ⚠ USER NOTE: Excel Row 69 Mark only"Nilonline production emission factors"No specific values given.
    # The following is broken down by web-based material: 3 A stand-alone emission factor, Easy LCA Model.
    # PS Network composition (Row 59): PA6=64.2%, EVA=9.7%, Steel=26.1%
    # LL Network composition (Row 54-55): The main rope=nylon, The hook=Metal/Alloys
    # All Values NaN, To-Use From Ecoinvent Wait LCA Database Filling.

    add_row('F', 'EMISSION_FACTOR_NYLON_PA6', 'nylon(PA6)carbon emission factor (cradle-to-gate)',
            'ALL', 'ALL', 'ALL', 'ALL', 9.885, 9.807, 9.969,
            'kg CO₂eq/kg nylon', 'Lognormal',
            'Self-building foreground process — fishing net production, nylon, 1kg '
            '(1000 MC simulations, Cradle-to-Gate)',
            'SelfBuilt_NylonNet',
            '1 kg Nilon netcoats produce carbon emissions. system boundary: Cradle-to-Gate. '
            'Core Agent: market for nylon 6 | Cutoff, U - RoW + '
            'market for extrusion, plastic film | Cutoff, U - GLO。'
            'Mean=9.885, SD=0.040, Median=9.885, 95% CI [9.807, 9.969]. '
            'It applies to both the purse seine and longline nylon materials.')

    add_row('F', 'EMISSION_FACTOR_STEEL_GEAR', 'gear steel/metal-component emission factor (cradle-to-gate)',
            'ALL', 'ALL', 'ALL', 'ALL', 3.070, 2.819, 3.374,
            'kg CO₂eq/kg steel hardware', 'Lognormal',
            'Self-building foreground process — longline hardware, steel, 1kg '
            '(1000 MC simulations, Cradle-to-Gate)',
            'SelfBuilt_LL_Hardware',
            '1 kg longline metal gear (hooks, Ring, Suzuko waits for the hardware) carbon emissions. '
            'system boundary: Cradle-to-Gate. '
            'Input: market for steel, low-alloyed | Cutoff, U - GLO + '
            'metal working, average for steel product manufacturing | Cutoff, U - GLO。'
            'Mean=3.070, SD=0.139, Median=3.064, 95% CI [2.819, 3.374].')

    # ------------------------------------------------------------------
    # F4. Gear Intensity Truncation Limits (physical truncation) — Row 56
    # ------------------------------------------------------------------
    # Row 56: "Model Interruption" — Set the physical poles to prevent unlimited linear extrapolation
    # Kuczenski et al. (2022) Fish. Fish. 23:22-33
    # longline upper bound: 1600 kW / 55m LOA / 800 GT
    # bimodal purse-seine distribution: small-vessel group 1000 kW/50m/750 GT; large-vessel group 2000-3000 kW/60-80m/1000-2000 GT

    add_row('F', 'GEAR_INT_TRUNC_LL_MAX_KW', 'longline gear_int physical truncation—maximum power',
            'ALL', 'LL', 'ALL', 'ALL', 1600.0, np.nan, np.nan,
            'kW', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'LL Maximum power margin for fishing vessels 1600 kW. above this value vessel Yes gear_int Intercept when extrapolating.')

    add_row('F', 'GEAR_INT_TRUNC_LL_MAX_LOA_M', 'longline gear_int physical truncation—maximum vessel length',
            'ALL', 'LL', 'ALL', 'ALL', 55.0, np.nan, np.nan,
            'm', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'LL Maximum number of fishing boats LOA NYO 55m. above this value vessel Yes gear_int Intercept when extrapolating.')

    add_row('F', 'GEAR_INT_TRUNC_LL_MAX_GT', 'longline gear_int physical truncation—maximum gross tonnage',
            'ALL', 'LL', 'ALL', 'ALL', 800.0, np.nan, np.nan,
            'GT', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'LL Maximum number of fishing boats GT NYO 800. above this value vessel Yes gear_int Intercept when extrapolating.')

    add_row('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_KW', 'purse seine(small-vessel group) gear_int physical truncation—maximum power',
            'ALL', 'PS', 'ALL', '<12m', 1000.0, np.nan, np.nan,
            'kW', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS small-vessel group(<12m)upper bound: 1000 kW, 50m LOA, 750 GT.')

    add_row('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_LOA_M', 'purse seine(small-vessel group) gear_int physical truncation—maximum vessel length',
            'ALL', 'PS', 'ALL', '<12m', 50.0, np.nan, np.nan,
            'm', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS small-vessel group(<12m)LOA Maximum Treaty 50m.')

    add_row('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_GT', 'purse seine(small-vessel group) gear_int physical truncation—maximum gross tonnage',
            'ALL', 'PS', 'ALL', '<12m', 750.0, np.nan, np.nan,
            'GT', 'Discrete',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS small-vessel group(<12m)GT Maximum Treaty 750.')

    add_row('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_KW', 'purse seine(large-vessel group) gear_int physical truncation—maximum power',
            'ALL', 'PS', 'ALL', '>=12m', 2500.0, 2000.0, 3000.0,
            'kW', 'Triangular',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS large-vessel group(>=12m)upper bound: 2000-3000 kW, 60-80m LOA, 1000-2000 GT. Best Remove 2500kW.')

    add_row('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_LOA_M', 'purse seine(large-vessel group) gear_int physical truncation—maximum vessel length',
            'ALL', 'PS', 'ALL', '>=12m', 70.0, 60.0, 80.0,
            'm', 'Triangular',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS large-vessel group(>=12m)LOA Scope 60-80m. Best Remove 70m.')

    add_row('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_GT', 'purse seine(large-vessel group) gear_int physical truncation—maximum gross tonnage',
            'ALL', 'PS', 'ALL', '>=12m', 1500.0, 1000.0, 2000.0,
            'GT', 'Triangular',
            'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
            'R56',
            'PS large-vessel group(>=12m)GT Scope 1000-2000. Best Remove 1500GT.')

    # ------------------------------------------------------------------
    # F5. Gear Lifespan — Row 61-66
    # ------------------------------------------------------------------
    # Row 61: PS net lifespan 5yr, annual replacement 25%; "1/5 + 25%"
    # Row 62: Company-reported net lifespan: 3.2yr (±0.8, range 2-4yr)
    # Row 63: "5 years Replacement rate 25% 20% + 25%"
    # Row 64: "33.3%+(2.3% - 6.6%)"
    # Row 65: "20% + 25%"
    # Row 66: LL update rate: "20% + 25%" (same structure as PS)

    add_row('F', 'LIFESPAN_GEAR_PS', 'purse-seine service life',
            'ALL', 'PS', 'ALL', 'ALL', 5, 3, 5,
            'years', 'Triangular',
            'Sheet 1 Row 61-64',
            'R61-R64',
            'PS net lifespan: 5yr (Row 61, Row 63). '
            'Company-reported average: 3.2yr (Row 62). '
            'Annual replacement 25% in non-renewal years (Row 61).')

    add_row('F', 'LIFESPAN_GEAR_LL', 'longline service life',
            'ALL', 'LL', 'ALL', 'ALL', 5, 3, 5,
            'years', 'Triangular',
            'Sheet 1 Row 65-66',
            'R65-R66',
            'LL gear lifespan: 5yr (Row 65-66). '
            'Annual replacement 20%+25% in non-renewal years.')

    # ------------------------------------------------------------------
    # F5. Gear Maintenance Rate — Row 61-66
    # ------------------------------------------------------------------
    add_row('F', 'MAINTENANCE_RATE_GEAR_PS', 'annual purse-seine maintenance replacement fraction',
            'ALL', 'PS', 'ALL', 'ALL', 0.25, 0.20, 0.33,
            'fraction per year', 'Triangular',
            'Sheet 1 Row 61-64',
            'R61-R64',
            'PS: 25% annual gear replacement (in non-renewal years). '
            'Row 61: 1/5 + 25%; Row 63: 20% + 25%.')

    add_row('F', 'MAINTENANCE_RATE_GEAR_LL', 'annual longline maintenance replacement fraction',
            'ALL', 'LL', 'ALL', 'ALL', 0.25, 0.20, 0.33,
            'fraction per year', 'Triangular',
            'Sheet 1 Row 65-66',
            'R65-R66',
            'LL: 25% annual gear replacement (in non-renewal years). '
            'Row 65-66: 20% + 25%.')

    # ========================================================================
    # G. longline bait consumption parameters (Longline Bait Consumption) — Sheet 1 Row 91-94
    # ========================================================================
    # Row 91: Section header
    # Row 92: Every ship is deployed on every voyage 500-1500 A fishing hook
    # Row 93: Number of hooks per gear set 1,666 - 2,147 Min
    # Row 94: The bait is mainly for low-value fish (low-value trash fish)

    add_row('G', 'BAIT_WEIGHT_PER_HOOK_KG', 'mean bait mass per longline hook',
            'ALL', 'LL', 'ALL', 'ALL', 0.1, 0.05, 0.15,
            'kg/hook', 'Triangular',
            'Sheet 1 Row 91-94; ghg_lca.py BAIT_WEIGHT_PER_HOOK_KG',
            'R91-R94',
            'Default: 0.1 kg per hook (low-value trash fish). '
            'Range: 0.05-0.15 kg/hook. '
            'Model: Bait_GHG = Std_Effort × BAIT_WEIGHT × EF_BAIT / 1000.')

    # Bait EF — from ecoinvent LCA (small pelagic fish, fresh)
    add_row('G', 'EMISSION_FACTOR_BAIT', 'bait emission factor (cradle-to-gate)',
            'ALL', 'LL', 'ALL', 'ALL', 1.606, 1.548, 1.670,
            'kg CO₂eq/kg bait', 'Lognormal',
            'Ecoinvent v3 — market for small pelagic fish, fresh | Cutoff, U - GLO '
            '(1000 MC simulations)',
            'Ecoinvent_Bait',
            '1 kg Small pelagic fish (Fresh) carbon emissions. '
            'Mean=1.606, SD=0.033, Median=1.606, 95% CI [1.548, 1.670]. '
            'Replace existing legacy value 0.454 kgCO2/kg bait (Source to be verified).')

    add_row('G', 'HOOKS_PER_LINE_RANGE_LOW', 'minimum hooks per longline set',
            'ALL', 'LL', 'ALL', 'ALL', 1666, 500, 1666,
            'hooks/line', 'Triangular',
            'Sheet 1 Row 92-93',
            'R92-R93',
            'Row 92: 500-1500 hooks per trip; Row 93: 1666-2147 total hooks per line.')

    add_row('G', 'HOOKS_PER_LINE_RANGE_HIGH', 'maximum hooks per longline set',
            'ALL', 'LL', 'ALL', 'ALL', 2147, 1666, 3000,
            'hooks/line', 'Triangular',
            'Sheet 1 Row 92-93',
            'R92-R93',
            'Upper bound: 2147 hooks (Row 93). '
            'Extended upper bound: 3000 for large industrial LL vessels.')

    # ========================================================================
    # H. Refrigerant parameters (Refrigerant Parameters) — Sheet 1 Row 85-88
    # ========================================================================
    # Row 85: Section header — most vessels have already switched from R22
    # Row 86: R22 GWP = 1810 kg CO2e / kg R22
    # Row 87: Leak rates by vessel type
    # Row 88: Summary: bottom trawl 150 kg/yr, PS 10 kg/yr

    add_row('H', 'R22_GWP', 'R22 refrigerant global warming potential (100yr)',
            'ALL', 'ALL', 'ALL', 'ALL', 1810, np.nan, np.nan,
            'kgCO2e/kg R22', 'Discrete',
            'Sheet 1 Row 86',
            'R86',
            'R22 (HCFC) GWP-100 = 1810 (Row 86). '
            'Being phased out under Montreal Protocol.')

    add_row('H', 'R22_LEAK_COASTAL_TRAWL', 'R22 annual leakage (coastal trawlers)',
            'ALL', 'ALL', 'ALL', 'ALL', 150, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87-88',
            'R87-R88',
            'Coastal trawl: 150 kg R22/yr (Row 87-88).')

    add_row('H', 'R22_LEAK_COASTAL_PS', 'R22 annual leakage (coastal purse-seine vessels)',
            'ALL', 'PS', 'ALL', 'ALL', 10, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87-88',
            'R87-R88',
            'Coastal PS: 10 kg R22/yr (Row 87-88). '
            'Much lower than trawl because PS has less refrigeration demand.')

    add_row('H', 'R22_LEAK_OFFSHORE', 'R22 annual leakage (offshore fishing vessels)',
            'ALL', 'ALL', 'ALL', 'ALL', 200, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87',
            'R87',
            'Offshore vessels: 200 kg R22/yr (Row 87).')

    add_row('H', 'R22_LEAK_DISTANT_PS', 'R22 annual leakage (offshore purse-seine vessels)',
            'ALL', 'PS', 'ALL', 'ALL', 500, np.nan, np.nan,
            'kg R22/year/vessel', 'Triangular',
            'Sheet 1 Row 87',
            'R87',
            'Distant-water PS: 500 kg R22/yr (Row 87). '
            'Tuna PS (Indian Ocean): 751 g/t reference.')

    # ========================================================================
    # I. Efforts to standardize parameters (Effort Standardization) — ghg_lca.py + Sheet 1
    # ========================================================================
    # These parameters are used to convert heterogeneous RFMO effort units
    # into a common standard (hooks for LL, sets for PS).

    add_row('I', 'HOOKS_PER_DAY', 'standard longline hooks per day (Effort standardisation)',
            'ALL', 'LL', 'ALL', 'ALL', 3000, np.nan, np.nan,
            'hooks/day', 'Triangular',
            'ghg_lca.py HOOKS_PER_DAY constant; Sheet 1 Row 92-93 for range context',
            'R92-R93',
            'Standard LL hooks per day. '
            'Model: Std_Effort(LL) = EffortValue × HOOKS_PER_DAY for days/sets units. '
            '⚠ The value is not there Sheet 1 , and give it to me, From model code. Row 92-93 It provides the range of hooks for each set of fishing gear '
            '(1666-2147), But not every day. ')

    add_row('I', 'HOURS_PER_SET', 'standard purse-seine hours per set (Effort standardisation)',
            'ALL', 'PS', 'ALL', 'ALL', 12, np.nan, np.nan,
            'hours/set', 'Triangular',
            'ghg_lca.py HOURS_PER_SET constant; '
            'Korican et al. (2023) PS operational profile context',
            'R15',
            'Standard PS hours per set (searching + operation). '
            'Model: Std_Effort(PS) = EffortValue / HOURS_PER_SET for hours units. '
            '⚠ The value is not there Sheet 1 , and give it to me, From model code. Row 15 Yes PS Run-time(main engine 4h,auxiliary engine 15h)'
            'Context, But its a time-consuming, non-separated network. ')

    # ========================================================================
    # J. Historical Power Evolution Parameters (Power Discount / Evolution) — Sheet 1 Row 47-50
    # ========================================================================
    # Row 46 (actually Row 47 in 1-based): "Vessel HP Growth 3-6%, GRT Growth 4%"
    # Row 47 (Row 48): Regional annual power growth rates
    # Row 48 (Row 49): Gear-type power growth rates
    # Row 49 (Row 50): Python preprocessing note

    # Regional power growth rates
    add_row('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Europe)',
            'Europe', 'ALL', 'ALL', 'ALL', 0.002, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Europe: 0.2%/yr — lowest growth (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Asia)',
            'Asia', 'ALL', 'ALL', 'ALL', 0.012, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Asia: 1.2%/yr — highest growth (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (North America)',
            'North America', 'ALL', 'ALL', 'ALL', 0.011, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'North America: 1.1%/yr (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Africa)',
            'Africa', 'ALL', 'ALL', 'ALL', 0.009, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Africa: 0.9%/yr (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (South America)',
            'South America', 'ALL', 'ALL', 'ALL', 0.011, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'South America: 1.1%/yr (Row 48).')

    add_row('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Oceania)',
            'Australia & Oceania', 'ALL', 'ALL', 'ALL', 0.017, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 48',
            'R48',
            'Oceania: 1.7%/yr — highest among regions (Row 48).')

    # Gear-type power growth rates (Row 49)
    add_row('J', 'POWER_GROWTH_RATE_LL', 'annual main engine power growth rate (longline fleet)',
            'ALL', 'LL', 'ALL', 'ALL', 0.010, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 49',
            'R49',
            'LL fleet: 1.0%/yr — 3rd largest contributor (Row 49).')

    add_row('J', 'POWER_GROWTH_RATE_PS', 'annual main engine power growth rate (purse-seine fleet)',
            'ALL', 'PS', 'ALL', 'ALL', 0.004, np.nan, np.nan,
            'fraction/year', 'Normal',
            'Sheet 1 Row 49',
            'R49',
            'PS fleet: 0.4%/yr — 5th largest contributor (Row 49).')

    # Decadal power growth (Row 47)
    add_row('J', 'POWER_GROWTH_DECADAL_HP', 'decadal main engine power growth rate',
            'ALL', 'ALL', 'ALL', 'ALL', 0.045, 0.03, 0.06,
            'fraction/decade', 'Triangular',
            'Sheet 1 Row 47',
            'R47',
            'Vessel HP grew 3-6% over study period (Row 47). '
            'Best=4.5% (midpoint).')

    # ========================================================================
    # K. GT-LDT Tonn Conversion Parameters — Sheet 1 Row 89-90
    # ========================================================================
    # Row 89: General vessel type LDT/GT ratios
    # Row 90: Fishing vessel LDT/GT = 0.859 (anomalously high)
    # "The fishing boat is abnormal, LDT/GT High ratio 85.9%"

    add_row('K', 'LDT_GT_RATIO_FISHING', 'fishing vessel GT→LDT conversion factor',
            'ALL', 'ALL', 'ALL', 'ALL', 0.859, np.nan, np.nan,
            'LDT/GT ratio', 'Normal',
            'Sheet 1 Row 90 — MEPC/IMO vessel statistics',
            'R90',
            'Fishing vessel LDT/GT = 85.9% (Row 90). '
            'Much higher than cargo ships (~22-55%). '
            'Means fishing vessels need more structural weight per GT → higher unit GHG.')

    # Reference: general cargo vessels (Row 89)
    add_row('K', 'LDT_GT_RATIO_CARGO_REF', 'cargo vessels GT→LDT conversion factor (reference comparison)',
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
    # Three EPA Core technical reports (Its possible EPA NEPIS Database Search Download by Number):
    #   NR-005d (EPA-420-R-10-016): Median Life, Annual Activity, Load Factor
    #   NR-009d (EPA-420-R-10-018): CI Engine Emission Factors (Diesels)
    #   NR-010f (EPA-420-R-10-019): SI Engine Emission Factors (Gasoline)
    # Conversion in units: 1 lb/hp-hr ≈ 608.277 g/kWh

    # ------------------------------------------------------------------
    # L1. EPA Load Factors (NR-005d)
    # ------------------------------------------------------------------
    add_row('L', 'LF_EPA_OUTBOARD_GASOLINE', 'EPA default marine petrol outboard engine load factor',
            'ALL', 'ALL', 'APW', 'ALL', 0.207, np.nan, np.nan,
            'fraction of MCR', 'Discrete',
            'EPA-420-R-10-016 (NR-005d) — Default for SQE',
            'EPA_NR005d',
            'EPA Default load factors for baseline testing of all conventional off-board petrol machines: 20.7%. '
            'Applicable to APW Small fishing vessels(<12m, Gasoline offboard).')

    add_row('L', 'LF_EPA_COMMERCIAL_FISHING', 'EPA Commercial catch high load factor',
            'ALL', 'ALL', 'I', 'ALL', 0.39, 0.34, 0.44,
            'fraction of MCR', 'Triangular',
            'EPA-420-R-10-016 (NR-005d) — Commercial trawling/Full load job',
            'EPA_NR005d',
            'High-intensity commercial fishing operations(Trawl/Full)Engine load: 0.34-0.44. '
            'Best Midpoint 0.39. Applicable to industrial fishing vessels(>=12m).')

    add_row('L', 'LF_EPA_INBOARD_DIESEL', 'EPA Default load factor for diesel cargo',
            'ALL', 'ALL', 'I', 'ALL', 0.425, 0.40, 0.45,
            'fraction of MCR', 'Triangular',
            'EPA-420-R-10-016 (NR-005d) — continuous cruising of diesel main engines/Load Towed',
            'EPA_NR005d',
            'The diesel cargo is on a continuous cruise/Reload towed default load: 0.40-0.45. '
            'Best Midpoint 0.425. Its significantly higher than the gas outboard(0.207).')

    # ------------------------------------------------------------------
    # L2. EPA SFR — Gasoline (NR-010f, Spark-Ignition Outboard)
    # ------------------------------------------------------------------
    add_row('L', 'SFR_GASOLINE_2STROKE', 'EPA conventional two-stroke petrol outboard engine SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000592, 0.000547, 0.000638,
            'tFuel/kWh', 'Triangular',
            'EPA-420-R-10-019 (NR-010f) — 2-Stroke Outboard',
            'EPA_NR010f',
            'The traditional two-stroke: 0.90-1.05 lb/hp-hr = 547-638 g/kWh = 0.000547-0.000638 t/kWh. '
            'Best=592 g/kWh. The fuel is very high, >20%Unburned fuel is directly released into water.')

    add_row('L', 'SFR_GASOLINE_4STROKE', 'EPA modern four-stroke petrol outboard engine SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000319, 0.000304, 0.000334,
            'tFuel/kWh', 'Triangular',
            'EPA-420-R-10-019 (NR-010f) — 4-Stroke Outboard',
            'EPA_NR010f',
            'Modern Four-Four: 0.50-0.55 lb/hp-hr = 304-334 g/kWh = 0.000304-0.000334 t/kWh. '
            'Best=319 g/kWh. Fuel consumption is close to vehicle engines, Main technology for medium-sized and large-scale petrol offboards.')

    add_row('L', 'SFR_GASOLINE_DI_2STROKE', 'EPA direct-injection two-stroke petrol outboard engine SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000365, 0.000334, 0.000395,
            'tFuel/kWh', 'Triangular',
            'EPA-420-R-10-019 (NR-010f) — DI 2-Stroke Outboard',
            'EPA_NR010f',
            'Two straight ahead: 0.55-0.65 lb/hp-hr = 334-395 g/kWh = 0.000334-0.000395 t/kWh. '
            'Best=365 g/kWh. direct injection reduces short-circuit fuel losses in conventional two-stroke engines, The oil is in between.')

    # ------------------------------------------------------------------
    # L3. EPA SFR — Diesels (NR-009d, Compression-Ignition Inboard)
    # ------------------------------------------------------------------
    add_row('L', 'SFR_DIESEL_25_50HP', 'EPA small diesel inboard engine(25-50HP / 19-37kW) SFR',
            'ALL', 'ALL', 'APW', 'ALL', 0.000248, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'EPA-420-R-10-018 (NR-009d) — 25-50 HP (19-37 kW) CI Engine',
            'EPA_NR009d',
            'Small diesel machine: ~0.408 lb/hp-hr ≈ 248 g/kWh = 0.000248 t/kWh. '
            '25-50 HP ≈ 19-37 kW. fuel economy exceeds that of four-stroke petrol outboard engines with the same power.')

    add_row('L', 'SFR_DIESEL_100_175HP', 'EPA Inner diesel engine, medium(100-175HP / 75-130kW) SFR',
            'ALL', 'ALL', 'I', 'ALL', 0.000221, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'EPA-420-R-10-018 (NR-009d) — 100-175 HP (75-130 kW) CI Engine',
            'EPA_NR009d',
            'Fuel, medium: ~0.364 lb/hp-hr ≈ 221 g/kWh = 0.000221 t/kWh. '
            '100-175 HP ≈ 75-130 kW. Heat efficiency increases with the volume cylinders, SFR Further down.')

    add_row('L', 'SFR_DIESEL_300_600HP', 'EPA large diesel inboard engine(300-600HP / 224-447kW) SFR',
            'ALL', 'ALL', 'I', 'ALL', 0.000210, np.nan, np.nan,
            'tFuel/kWh', 'Lognormal',
            'EPA-420-R-10-018 (NR-009d) — 300-600 HP (224-447 kW) CI Engine',
            'EPA_NR009d',
            'Large diesel machine: ~0.345 lb/hp-hr ≈ 210 g/kWh = 0.000210 t/kWh. '
            '300-600 HP ≈ 224-447 kW. typical efficient operating conditions of main engines on medium and large offshore vessels. and Row 37 auxiliary engine=210 g/kWh Unanimously.')

    # ========================================================================
    # Assemble DataFrame
    # ========================================================================
    prior = pd.DataFrame(rows)

    # Add metadata
    prior.attrs['description'] = (
        'Pre-demonstration Array (v7 Revised) — A single long format matrix for all parameters of the emission model. '
        'Overwrite 12 Category(A-L), ♪ Every record by ♪(Param_Code, Flag, Gear, Sector, Length_Category)Unique Index. '
        'v4 Amendments: (1)ecoinvent construction/maintenance EF (PS steel/Wood, LL steel); '
        '(2)transshipment vessel/Use of an auxiliary ship PS Steel ship factor; (3)small longline vessels use PS Woodboat factors; '
        '(4)Enter NaN Value: nylon PA6=9.885, Fishing steel=3.070, bait=1.606 kgCO2/kg. '
        'v5 Amendments: remove 5 One no longer needed NaN parameter (STEEL/IRON/COPPER/EVA/GEAR_COMPOSITE). '
        'v6 Amendments: (1)Additional diesel fuel/upstream petrol WTT EF; (2)Update burning CO2 (IMO 2020/EPA 2025); '
        '(3)CH4/N2O Split by fuel and machine type; (4)diesel CH4/N2O should read IMO Standard Unit g/kWh. '
        'v7 Amendments: T_map_DAS Reconfigure 3 Data Priority System — '
        'Tier1: Parker(2014)By Ocean PS (Atlantic 297/Indian 289/Pacific 244, default 277); '
        'Tier2: Jha(2026)Indian Ocean LL (234-256); '
        'Tier3: Anticamara(2011)By continent (LL/PS/TP, Flag=ALL, Sector=I).'
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
        gap_note = f' [{n_nan_best} To be filled in]' if n_nan_best > 0 else ''
        print(f"    [{sec}] {sec_name}: {n_params} rows, {n_codes} unique codes{gap_note}")

    return prior


def build_species_cf_matrix(xlsx_path=XLSX_PATH):
    """
    Build the Species_CF_Matrix from Sheet 2 ('resource depletion impact assessment').

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
    print("  Building Matrix 2: Species_CF_Matrix (Species characterization factor matrix)")
    print("=" * 70)

    # Read raw sheet
    df_raw = pd.read_excel(xlsx_path, sheet_name='\u8d44\u6e90\u8017\u7aed\u5f71\u54cd\u8bc4\u4f30')

    # Standardize column names
    col_map = {
        '\u7269\u79cd (Common name)': 'Common_Name',
        '\u5b66\u540d (Scientific name)': 'Scientific_Name',
        'CF (\u4e2d\u503c)': 'CF_median',
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
    df.attrs['description'] = 'Species characterization factor matrix — Tuna and by-catch species CF Value'
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
# Matrix 3: Scenario_Multiplier_Matrix (Scenario Multiplier Matrix)
# =============================================================================

def build_scenario_multiplier_matrix(xlsx_path=XLSX_PATH):
    """
    Build the Scenario_Multiplier_Matrix from Sheet 3 ('scenario analysis').

    Parse Chinese text descriptions into numeric Fuel_Multiplier and GHG_Multiplier.
    Scenarios with unquantified measures are flagged as 'qualitative_only'.

    Returns
    -------
    pd.DataFrame with columns:
        Scenario_ID, Measure_Category, Measure_Description, Measure_Value_Raw,
        Fuel_Multiplier, GHG_Multiplier, Is_Quantified, Source
    """
    print("\n" + "=" * 70)
    print("  Building Matrix 3: Scenario_Multiplier_Matrix (Scenario Multiplier Matrix)")
    print("=" * 70)

    # Read raw sheet
    df_raw = pd.read_excel(xlsx_path, sheet_name='\u60c5\u666f\u5206\u6790', header=None)

    # Find the header row (row containing 'measure category')
    header_row = None
    for i, row in df_raw.iterrows():
        if any('\u63aa\u65bd\u7c7b\u522b' in safe_str(v) for v in row.values):
            header_row = i
            break

    if header_row is None:
        print("  WARNING: Could not find header row, using row 1 as default")
        header_row = 1

    # Extract data rows (after header)
    # Column mapping (by position): 0=measure category, 1=Specific measures, 2=Value, 3=Source, 4=Annotations
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
        if category in ('\u60c5\u666f\u5206\u6790\u6a21\u578b', '\u63aa\u65bd\u7c7b\u522b'):
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
        is_alt_fuel = ('\u66ff\u4ee3\u71c3\u6599' in cat or
                       any(kw in desc for kw in ['\u7532\u9187\u66ff\u4ee3', 'LPG\u66ff\u4ee3', 'LNG\u66ff\u4ee3', 'CNG',
                                                 '\u751f\u7269\u67f4\u6cb9', '\u751f\u7269\u71c3\u6599', '\u6c22-\u67f4\u6cb9',
                                                 '\u6cbc\u6c14', '\u7532\u9187-\u67f4\u6cb9', '\u6c22-\u67f4\u6cb9',
                                                 '\u7535\u529b（LFP', '\u6db2\u5316\u77f3\u6cb9\u6c14']))
        is_refrigerant = '\u5236\u51b7\u5242' in cat
        is_gear_change = '\u66f4\u6362\u6e14\u5177' in cat
        is_baseline = '\u57fa\u51c6' in cat or '\u7efc\u5408\u7ed3\u8bba' in cat

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
            if re.search(r'(?:GHG|CO₂?|CO2|\u6e29\u5ba4|\u78b3\u6392\u653e?)', text):
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

        # Additional checks: text explicitly says "not quantified" or contains non-percentage units
        if '\u672a\u91cf\u5316' in text or '\u672a\u91cf\u5316' in desc:
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

    # ---- Handle "same as above" (same as above) rows ----
    # These are duplicate literature sources citing the same measure.
    # They inherit the multiplier from the nearest non-same as above row above,
    # and are marked as "duplicate reference" in the description.
    same_as_above_refs = {}  # track which primary row each same as above row references
    for i in range(len(df)):
        if df.loc[i, 'Measure_Description'].strip() == '\u540c\u4e0a':
            for j in range(i - 1, -1, -1):
                if df.loc[j, 'Measure_Description'].strip() != '\u540c\u4e0a':
                    df.loc[i, 'Fuel_Multiplier'] = df.loc[j, 'Fuel_Multiplier']
                    df.loc[i, 'GHG_Multiplier'] = df.loc[j, 'GHG_Multiplier']
                    df.loc[i, 'Is_Quantified'] = df.loc[j, 'Is_Quantified']
                    same_as_above_refs[i] = j
                    break

    # ---- Special handling for baseline fuel consumption rows ----
    # These are absolute consumption values (L/kg), not multipliers
    mask_baseline = df['Measure_Category'].str.contains('\u57fa\u51c6', na=False)
    df.loc[mask_baseline, 'Is_Quantified'] = False

    # ---- Special handling for "Consolidated conclusions" (summary) rows ----
    # These are global statistics, not scenario measures
    mask_summary = df['Measure_Category'].str.contains('\u7efc\u5408\u7ed3\u8bba', na=False)
    df.loc[mask_summary, 'Is_Quantified'] = False

    # ---- Assign Scenario_ID ----
    # S1, S2, ... for quantified; Q1, Q2, ... for qualitative
    # "same as above" rows get sub-IDs referencing their primary (e.g., S6a, S6b)
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
                    # Count how many same as above refs point to same primary
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
    df.attrs['description'] = 'Scenario Multiplier Matrix — Oil saving for emission reduction measures/Emission reduction multiplier'
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
# Matrix 4: MonteCarlo_Config_Matrix (Monte Carlo Sample Configuration Matrix)
# =============================================================================

def build_montecarlo_config_matrix(xlsx_path=XLSX_PATH):
    """
    Build the MonteCarlo_Config_Matrix from Sheet 4 ('model parameter type').

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
    print("  Building Matrix 4: MonteCarlo_Config_Matrix (Monte Carlo Sample Configuration Matrix)")
    print("=" * 70)

    # Parse the raw Sheet 4 to extract category-level metadata
    df_raw = pd.read_excel(xlsx_path, sheet_name='\u6a21\u578b\u53c2\u6570\u7c7b\u578b')
    col_map = {
        '\u53c2\u6570\u5206\u7c7b': 'Param_Category',
        '\u4ee3\u7801\u4e2d\u7684\u5177\u4f53\u53c2\u6570': 'Param_Code',
        '\u6838\u5fc3\u7279\u5f81\u4e0e\u7269\u7406\u610f\u4e49': 'Physical_Meaning',
        '\u8499\u7279\u5361\u6d1b\u62bd\u6837\u7b56\u7565\u5efa\u8bae': 'Sampling_Strategy_Raw',
    }
    df_raw = df_raw.rename(columns=col_map)

    # Extract category-level info from raw rows
    # Row structure (from Sheet 4):
    #   [1] One, Time/Behavior Variables | T_map (Annual days of operation) | Its not about the physical size of the ship... | Continuous Probability Distribution
    #   [3] (Time / Behavior) | H_map (Daily working hours) | | Triangular distribution or PERT Distribution
    #   [5] | HOURS_PER_SET | |
    #   [7] | HOOKS_PER_DAY | |
    #   [8] Two, Size Dependent Variable | gear_int | By the laws of physics... | Interrupt and separate sampling pools
    #   [10] (Scale-dependent) | SFR_map | | Physical polar cut-off...
    #   [12] | BAIT_WEIGHT_PER_HOOK_KG | |
    #   [13] III, Science and Engineering Constant | EMISSION_FACTOR_* | Basic industry standards... | normal/logarithmic normal distribution
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
        # ---- Category 1: Time/Behavior Variables (Time/Behavior) ----
        # T_map (DAS) — 3-tier data hierarchy
        ('T_map_DAS', 'Triangular',
         'Annual days of operation (Days at Sea) . Data Priority: Tier1 Parker(2014)By Ocean PS, '
         'Tier2 Jha(2026)Indian Ocean LL, Tier3 Anticamara(2011)By continent. ',
         'Press Flag×Gear×Sector A combination of reference literature to determine minimum values, Mass and Max, Independent sampling using triangulation. '
         'Parker Data applicable 1990 After FAD purse-seine fisheries in this era; Anticamara For historical retrospection(1950-2010)and non-governmental organizations PS Type of ship. ',
         'One, Time/Behavior Variables (Time/Behavior)', 1,
         'T_map_DAS'),

        # H_map (Daily Engine Hours)
        ('H_map_Hday', 'Triangular',
         'daily main engine operating hours. ',
         f'Check the literature to determine the minimum value, Most likely and maximum, Use triangular distribution or PERT Distribution for continuous sampling. {cat1_detail}',
         'One, Time/Behavior Variables (Time/Behavior)', 1,
         'H_map_Hday'),

        # HOURS_PER_SET
        ('HOURS_PER_SET', 'Triangular',
         'purse-seine hours per set (Search+Hours of operation) . For Effort standardisation: Std_Effort = EffortValue / HOURS_PER_SET. ',
         'Check the literature to determine the minimum/Most likely/maximum, Continuous sampling using triangular distribution. Direct impact of this parameter PS Effort Standard denominator. ',
         'One, Time/Behavior Variables (Time/Behavior)', 1,
         'HOURS_PER_SET'),

        # HOOKS_PER_DAY
        ('HOOKS_PER_DAY', 'Triangular',
         'standard longline hooks per day. For Effort standardisation: Std_Effort = EffortValue * HOOKS_PER_DAY. ',
         'Check the literature to determine the minimum/Most likely/maximum, Continuous sampling using triangular distribution. Direct impact of this parameter LL Effort Standardized multipliers. ',
         'One, Time/Behavior Variables (Time/Behavior)', 1,
         'HOOKS_PER_DAY'),

        # LF_move (engine load factor — transit) — added for completeness
        ('LF_move', 'Triangular',
         'Engine load factor during the cruise phase (Jim MCR Percentage) . by type of ship and Sector Impact. ',
         'Press Gear×Sector Group set trigonometric distribution parameters. Industrial: mode≈0.80; APW: mode≈0.79. ',
         'One, Time/Behavior Variables (Time/Behavior)', 1,
         'LF_move'),

        # LF_work (engine load factor — fishing)
        ('LF_work', 'Triangular',
         'Engine load factors for the fishing operations phase (Jim MCR Percentage) . by type of ship and Sector Impact, Change greater than LF_move. ',
         'Press Gear×Sector Group set trigonometric distribution parameters. I-LL: mode≈0.50; I-PS: mode≈0.65; APW: mode≈0.19. ',
         'One, Time/Behavior Variables (Time/Behavior)', 1,
         'LF_work'),

        # ---- Category 2: Size Dependent Variable (Scale-dependent) ----
        # gear_int (Gear intensity factor)
        ('gear_int_PS', 'Truncated',
         'purse-seine gear mass per unit vessel length (tonnes of fishing gear/metres of vessel length) . Very limited by the laws of physics and space geometry, varies stepwise with vessel length. ',
         f'even distribution(Uniform), Physical polar cut-off. PS small (<12m): Uniform[0.00912, 0.0179] t/m; PS large (>=12m): Uniform[0.054, 0.251] t/m. {cat2_strategy}',
         'Two, Size Dependent Variable (Scale-dependent)', 2,
         'gear_int_PS'),

        ('gear_int_LL', 'Truncated',
         'longline gear mass per unit vessel length (tonnes of fishing gear/metres of vessel length) . Changes as long as ship. ',
         f'even distribution(Uniform), Physical polar cut-off. LL: Uniform[0.03333, 0.13611] t/m (by kg/hook divide by 3.6 Convert). {cat2_strategy}',
         'Two, Size Dependent Variable (Scale-dependent)', 2,
         'gear_int_LL'),

        # SFR_map
        ('SFR_map', 'Truncated',
         'Specific fuel consumption rate (tFuel/kWh) . varies stepwise with vessel length (<12m vs >=12m) , Intergenerational effects of engine technology. ',
         f'A physical polar cut must be set(Clipping), Draw from the discrete pool of literature. {cat2_detail} Industrial: Lognormal(μ=ln(0.00020), σ); APW: Lognormal(μ=ln(0.00035), σ)。',
         'Two, Size Dependent Variable (Scale-dependent)', 2,
         'SFR_map'),

        # BAIT_WEIGHT_PER_HOOK_KG
        ('BAIT_WEIGHT_PER_HOOK_KG', 'Triangular',
         'mean bait mass per longline hook (kg/hooks) . Subject to availability of target species and bait. ',
         f'Check the literature to determine the minimum value, Most likely and maximum, Use Triangular Distribution. {cat2_strategy} default: mode=0.1 kg/hook. ',
         'Two, Size Dependent Variable (Scale-dependent)', 2,
         'BAIT_WEIGHT_PER_HOOK_KG'),

        # AUX_POWER_RATIO
        ('AUX_POWER_RATIO', 'Triangular',
         'auxiliary engine/main engine power ratio. Step by tonnage and age of construction (0.15-0.40) . ',
         'Press GT and Builtdate Layer Set Triangular Distribution: Large(GT>1500)→0.33-0.40; Medium(500-1500, post-1990)→0.25-0.33; Small/Old→0.15-0.25. ',
         'Two, Size Dependent Variable (Scale-dependent)', 2,
         'AUX_POWER_RATIO | AUX_POWER_RATIO_LARGE | AUX_POWER_RATIO_MEDIUM | AUX_POWER_RATIO_SMALL'),

        # ---- Category 3: Science and Engineering Constant (Physical & Engineering Constants) ----
        # These come from Ecoinvent / standard LCA databases.
        # They are stable physical properties, perturbed with Normal or Lognormal.

        # Emission Factors — Upstream (Well-to-Tank, WTT)
        ('EF_WTT_DIESEL', 'Lognormal',
         'upstream diesel(WTT)carbon emission factor (kg CO₂eq/kg diesel) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(0.369), 95% CI [0.318, 0.441] '
         '(Ecoinvent v3: market for diesel | Cutoff, U - RoW).',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_WTT_DIESEL'),

        ('EF_WTT_GASOLINE', 'Lognormal',
         'upstream petrol(WTT)carbon emission factor (kg CO₂eq/kg petrol) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(0.535), 95% CI [0.489, 0.595] '
         '(Ecoinvent v3: market for petrol, two-stroke blend | Cutoff, U - GLO).',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_WTT_GASOLINE'),

        # Emission Factors — CO2 from fuel combustion (Tank-to-Wake)
        ('EF_CO2_Diesel', 'Discrete',
         'diesel CO₂combustion emission factor (tCO₂/tFuel) . IMO 2020 Chemical measures constant, Non-statistical estimates. ',
         f'Dispersal value, Not in progress MC Disturbing. {cat3_strategy} Fixed: 3.206 (IMO 2020 Fourth GHG Study, stoichiometric complete oxidation based on the carbon mass fraction). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_CO2_Diesel'),

        ('EF_CO2_Gasoline', 'Normal',
         'petrol CO₂combustion emission factor (tCO₂/tFuel) . EPA 2025, For small fishing vessels (APW Sector) . ',
         f'Access EPA Fetch CV, Normal Distribution Disruption. {cat3_strategy} default: μ=3.158 (EPA 2025 Table 2: 8.78 kg/gallon ÷ 2.78 kg/gallon). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_CO2_Gasoline'),

        # Emission Factors — CH4 (Methane, by fuel and engine type)
        ('EF_CH4_DIESEL_MSD', 'Lognormal',
         'diesel CH₄emission factor—medium-speed four-stroke MSD (g/kWh) . IMO 2020, Mainstream type of fishing vessel/auxiliary engine. ',
         f'logarithmic normal distribution. {cat3_strategy} default: μ=ln(0.010) (IMO 2020 Fourth GHG Study, IMO Standard Unit g/kWh). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_CH4_DIESEL_MSD'),

        ('EF_CH4_DIESEL_SSD', 'Lognormal',
         'diesel CH₄emission factor—low-speed two-stroke SSD (g/kWh) . IMO 2020, main engines of large transshipment vessels. ',
         f'logarithmic normal distribution. {cat3_strategy} default: μ=ln(0.010) (IMO 2020 Fourth GHG Study, IMO Standard Unit g/kWh). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_CH4_DIESEL_SSD'),

        ('EF_CH4_GASOLINE_2STROKE', 'Lognormal',
         'petrol CH₄emission factor—two-stroke outboard engine (g/kgFuel) . EPA 2025 Table 5, Ships and Boats. ',
         f'logarithmic normal distribution. {cat3_strategy} default: μ=ln(3.76) (EPA 2025: 10.45 g/gallon ÷ 2.78 kg/gallon). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_CH4_GASOLINE_2STROKE'),

        ('EF_CH4_GASOLINE_4STROKE', 'Lognormal',
         'petrol CH₄emission factor—four-stroke outboard engine (g/kgFuel) . EPA 2025 Table 5, Ships and Boats. ',
         f'logarithmic normal distribution. {cat3_strategy} default: μ=ln(1.50) (EPA 2025: 4.18 g/gallon ÷ 2.78 kg/gallon). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_CH4_GASOLINE_4STROKE'),

        # Emission Factors — N2O (Nitrous Oxide, by fuel and engine type)
        ('EF_N2O_DIESEL_MSD', 'Lognormal',
         'diesel N₂O emission factor—medium-speed four-stroke MSD (g/kWh) . IMO 2020, Main fishing vessels/auxiliary engine. ',
         f'logarithmic normal distribution. {cat3_strategy} default: μ=ln(0.030) (IMO 2020 Fourth GHG Study, IMO Standard Unit g/kWh). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_N2O_DIESEL_MSD'),

        ('EF_N2O_DIESEL_SSD', 'Lognormal',
         'diesel N₂O emission factor—low-speed two-stroke SSD (g/kWh) . IMO 2020, main engines of large transshipment vessels. ',
         f'logarithmic normal distribution. {cat3_strategy} default: μ=ln(0.020) (IMO 2020 Fourth GHG Study, IMO Standard Unit g/kWh). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_N2O_DIESEL_SSD'),

        ('EF_N2O_GASOLINE', 'Lognormal',
         'petrol N₂O emission factor (g/kgFuel) . EPA 2025 Table 5, Ships and Boats (Two-stroke and four-stroke alignment). ',
         f'logarithmic normal distribution. {cat3_strategy} default: μ=ln(0.04) (EPA 2025: 0.11 g/gallon ÷ 2.78 kg/gallon). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_N2O_GASOLINE'),

        # Vessel Construction EFs (ecoinvent LCA)
        ('EF_BUILD_PS_STEEL', 'Lognormal',
         'construction emission factor for steel purse-seine vessels (kg CO₂eq/kg vessel) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(2.421), 95% CI [2.332, 2.528]. '
         '1 kg purse seiner steel construction. Its also applicable to transshipment ships/support vessel.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_BUILD_PS_STEEL | EF_BUILD_TS'),

        ('EF_BUILD_PS_WOOD', 'Lognormal',
         'construction emission factor for wooden purse-seine vessels (kg CO₂eq/kg vessel) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(0.578), 95% CI [0.513, 0.678]. '
         '1 kg purse seiner wood construction. Its also applicable LL ♪ The boat and the TS The boat.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_BUILD_PS_WOOD | EF_BUILD_LL_WOOD'),

        ('EF_BUILD_LL_STEEL', 'Lognormal',
         'construction emission factor for steel longline vessels (kg CO₂eq/kg vessel) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(1.956), 95% CI [1.877, 2.069]. '
         '1 kg long liner steel construction.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_BUILD_LL_STEEL'),

        # Vessel Maintenance EFs (ecoinvent LCA)
        ('EF_MAINT_PS_STEEL', 'Lognormal',
         'maintenance emission factor for steel purse-seine vessels (kg CO₂eq/kg maintenance) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(6.744), 95% CI [6.627, 6.883]. '
         '1 kg purse seiner steel maintenance. Its also applicable to transshipment ships/support vessel.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_MAINT_PS_STEEL | EF_MAINT_TS'),

        ('EF_MAINT_PS_WOOD', 'Lognormal',
         'maintenance emission factor for wooden purse-seine vessels (kg CO₂eq/kg maintenance) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(1.289), 95% CI [1.179, 1.437]. '
         '1 kg purse seiner wood maintenance. Its also applicable LL ♪ The boat and the TS The boat.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_MAINT_PS_WOOD | EF_MAINT_LL_WOOD'),

        ('EF_MAINT_LL_STEEL', 'Lognormal',
         'maintenance emission factor for steel longline vessels (kg CO₂eq/kg maintenance) . Ecoinvent v3, 1000 MC. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(4.450), 95% CI [3.777, 5.376]. '
         '1 kg long liner steel maintenance.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EF_MAINT_LL_STEEL'),

        ('EMISSION_FACTOR_NYLON_PA6', 'Lognormal',
         'nylon(PA6)carbon emission factor (kg CO₂eq/kg nylon) . Self-building foreground process, Cradle-to-Gate. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(9.885), 95% CI [9.807, 9.969] (Self-created LCA Process, 1000 MC). '
         'Core Agent: nylon 6 + plastic film extrusion.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EMISSION_FACTOR_NYLON_PA6'),

        ('EMISSION_FACTOR_STEEL_GEAR', 'Lognormal',
         'gear steel/metal-component emission factor (kg CO₂eq/kg steel hardware) . Self-building foreground process, Cradle-to-Gate. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(3.070), 95% CI [2.819, 3.374] (Self-created LCA Process, 1000 MC). '
         'Input: low-alloyed steel + metal working average.',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EMISSION_FACTOR_STEEL_GEAR'),

        ('EMISSION_FACTOR_BAIT', 'Lognormal',
         'bait emission factor (kg CO₂eq/kg bait) . Small pelagic fish, Cradle-to-Gate. ',
         f'logarithmic normal distribution. {cat3_strategy} μ=ln(1.606), 95% CI [1.548, 1.670] '
         '(Ecoinvent v3: market for small pelagic fish, fresh, 1000 MC).',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'EMISSION_FACTOR_BAIT'),

        # EPA SFR reference values (for cross-validation)
        ('SFR_GASOLINE_4STROKE', 'Triangular',
         'EPA The four-legged gas outboard SFR (tFuel/kWh) . For APW Gasoline SFR Cross Authentication. ',
         f'EPA NR-010f Report, Triangular distribution. default: mode=0.000319, min=0.000304, max=0.000334. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'SFR_GASOLINE_4STROKE'),

        ('SFR_DIESEL_300_600HP', 'Lognormal',
         'EPA large diesel inboard engine SFR (tFuel/kWh) . 300-600HP (224-447kW), For Industrial Diesels SFR Cross Authentication. ',
         f'EPA NR-009d Report, lognormal. default: μ=0.000210 (≈210 g/kWh, ~0.345 lb/hp-hr). ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'SFR_DIESEL_300_600HP'),

        # Material Ratios
        ('MATERIAL_RATIO_STEEL', 'Normal',
         'Body steel quality GT Percentage. Ship-based design codes, Less Variation. ',
         f'Access Ecoinvent/Access to documentation on shipbuilding CV, Normal distribution. {cat3_strategy} default: μ=0.85, σ≈0.02. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'MATERIAL_RATIO_STEEL'),

        ('MATERIAL_RATIO_ENGINE', 'Normal',
         'Engine casting iron mass GT Percentage. ',
         f'Normal distribution. {cat3_strategy} default: μ=0.10, σ≈0.01. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'MATERIAL_RATIO_ENGINE'),

        ('MATERIAL_RATIO_COPPER', 'Normal',
         'Copper Quality of Electricity System GT Percentage. ',
         f'Normal distribution. {cat3_strategy} default: μ=0.05, σ≈0.01. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'MATERIAL_RATIO_COPPER'),

        # Lifespans
        ('LIFESPAN_HULL', 'Discrete',
         'hull service life (years) . Its determined by the ship design code and the standards of the class societies. ',
         'Dispersal distribution or narrow triangle distribution. Yes LCA . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  (30 years) , Through Bootstrap The age structure of the re-sampled fleet indirectly indicates a variation in the behaviour of the ship. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'LIFESPAN_HULL'),

        ('LIFESPAN_ENGINE', 'Discrete',
         'engine service life (years) . Its usually a hull life 1/3, 10 Yearly replacement. ',
         'Dispersal distribution or narrow triangle distribution. default: 10 years. It can be verified by engine replacement records. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'LIFESPAN_ENGINE'),

        ('LIFESPAN_COPPER', 'Discrete',
         'Electricity system update cycle (years) . Frequency of replacement of copper cables and electrical distribution equipment. ',
         'Dispersal distribution. default: 8 years. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'LIFESPAN_COPPER'),

        ('LIFESPAN_GEAR_PS', 'Triangular',
         'purse-seine service life (years) . Intensity of use and fishery environment (Rocks, Substrate) Impact. ',
         'Triangular distribution: min=2, mode=5, max=5. Row 60-61: Average of corporate reporting 3.2 years, But industry standards 5 years. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'LIFESPAN_GEAR_PS'),

        ('LIFESPAN_GEAR_LL', 'Triangular',
         'longline service life (years) . The gear is mostly worn out UV Degradation and physical wear and tear drivers. ',
         'Triangular distribution: min=2, mode=5, max=5. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'LIFESPAN_GEAR_LL'),

        # Maintenance Rates
        ('MAINTENANCE_RATE_STEEL', 'Normal',
         'Shipwork steel every 2 Annual replacement rate for maintenance. Standard operating parameters for ship maintenance. ',
         f'Access to documentation of ship repair works CV, Normal distribution. {cat3_strategy} default: μ=0.12. ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'MAINTENANCE_RATE_STEEL'),

        ('MAINTENANCE_RATE_GEAR_PS', 'Normal',
         'annual purse-seine maintenance replacement fraction (In a non-generational year) . Documentation: 20-33%Scope. ',
         f'Normal distribution. {cat3_strategy} default: μ=0.25 (Row 60: purse-seine service life 5 Year but replacement per year 25%) . ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
         'MAINTENANCE_RATE_GEAR_PS'),

        ('MAINTENANCE_RATE_GEAR_LL', 'Normal',
         'annual longline maintenance replacement fraction (In a non-generational year) . Documentation: 20-33%Scope. ',
         f'Normal distribution. {cat3_strategy} default: μ=0.25 (Row 65: 20%+25%) . ',
         'III, Science and Engineering Constant (Physical & Engineering)', 3,
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
        'Monte Carlo Sample Configuration Matrix — All 29 Distribution type for specific parameters and sampling strategy. '
        'by Sheet 4 of 3 Large macro definitions expanded as specific parameters, and Prior_Matrix Through Covered_Prior_Codes LIBERATION. '
    )
    df.attrs['usage'] = (
        'Distribution: Recommended Probability Distribution. Arg1/2/3: Distribution Parameters (To be filled in, See Arg*_Meaning) . '
        'Clip_Min/Max: Physical cut the boundary. Covered_Prior_Codes: Corresponding Prior_Matrix Parameter Code. '
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
