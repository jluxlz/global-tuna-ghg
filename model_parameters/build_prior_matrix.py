#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
=============================================================================
build_prior_matrix.py — reconstruction Prior_Matrix.csv (v3.0 Fuel methodology update)
=============================================================================
Core changes:
  1. >=12m fishing vessel: Diesel medium speed machine(MSD/MDO), SFCbase + SFOC Load Formula → Actual SFC
  2. <12m fishing vessel: Gasoline offboard, no auxiliary engine, Direct SFR Check Value(EPA)
  3. transshipment vessel(TP): The oil low speed machine(SSD/HFO)
  4. support vessel(SA): Diesel medium speed machine(MSD/MDO)
  5. Uniform source of load: R22 (Cruise=80%=T_move, Manoeuvring=20%=T_work)
  6. auxiliary engine load: Uniform(0.30, 0.50), independent of phase
  7. CH4/N2O EF: IMO Fourth GHG Study (By engine type)
  8. CO2 EF: By fuel type (HFO=3.114, MDO=3.206, Gasoline=3.158)
  9. Delete Old SFR/LF Data, retain EPA Gasoline-related data

References (Model_parameters.xlsx):
  R22 — Run Load (Cruise 80/30, Manoeuvring 20/50)
  R33 — Engine Class (>=12m→MSD, TP→SSD, SA→MSD, <12m→Gasoline)
  R43 — IMO SFCbase table (by engine type, fuel type, era)
  R45-R49 — IMO GHG EF (CH4, N2O by engine type; CO2 by fuel type)

Output: model_parameters/Prior_Matrix.csv
=============================================================================
"""

import os
import sys
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, "Prior_Matrix.csv")

rows = []

def add(section, code, name_en, flag="ALL", gear="ALL", sector="ALL",
        len_cat="ALL", v_best=None, v_low=None, v_high=None,
        unit="", dist="Discrete", source="", s1_row="", note=""):
    """Add a row to the Prior_Matrix."""
    rows.append({
        'Param_Section':    section,
        'Param_Code':       code,
        'Param_Name_EN':    name_en,
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
# SECTION A: Standard Classification of Ships (Vessel Classification)
# ===========================================================================

add('A', 'LENGTH_THRESHOLD_SECTOR_M', 'Sector classification vessel-length threshold (EU standard)',
    'ALL', 'ALL', 'ALL', 'ALL', 12.0, None, None, 'm', 'Discrete',
    'Council Regulation (EC) No 1198/2006 of 27 July 2006 on the European Fisheries Fund, Article 26',
    'R4',
    'I (Industrial): >=12m; APW (Artisanal): <12m. '
    'Harmonization by EU standards. For Sector binary classification and engine type/Fuel type determination. ')

add('A', 'LENGTH_THRESHOLD_SFR_M', 'SFR/EF stepwise vessel-length threshold (common EU standard)',
    'ALL', 'ALL', 'ALL', 'ALL', 12.0, None, None, 'm', 'Discrete',
    'Council Regulation (EC) No 1198/2006; Greer et al. (2019) Mar. Policy 107:103382',
    'R4-R5',
    '<12m: Gasoline offboard, no auxiliary engine, Direct SFR; >=12m: Diesels+auxiliary engine, SFCbase+SFOC Formula. '
    'Uniformly used EU 12m standard. ')

# ===========================================================================
# SECTION B: Parameters for ship operations (Fishing Activity Parameters)
# T_map (annual days at sea) and H_map (Day running hours)
# attention: LF (load factor) Moved to Section C3, Put it together with the fuel parameters
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
add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS Atlantic',
    'Atlantic', 'PS', 'I', 'ALL', 297.0, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    'Tier 1 — Atlantic purse seine: 297 days/year. n=9, avg LOA=70.6m. '
    'Applicable to ICCAT Water, 1990 After FAD Times.')

add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS Indian',
    'Indian', 'PS', 'I', 'ALL', 289.0, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    'Tier 1 — Indian Ocean purse seine: 289 days/year. n=9, avg LOA=81.7m. '
    'Applicable to IOTC Water, 1990 After FAD Times.')

add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS Pacific',
    'Pacific', 'PS', 'I', 'ALL', 244.0, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    'Tier 1 — Pacific purse seine: 244 days/year. n=75, avg LOA=68.9m. '
    'Applicable to WCPFC+IATTC Water, 1990 After FAD Times.')

parker_mean = round((297 + 289 + 244) / 3, 1)  # 276.7
add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 1: Parker PS default mean',
    'ALL', 'PS', 'I', 'ALL', parker_mean, None, None, 'days/year', 'Triangular',
    parker_citation, 'R11',
    f'Tier 1 — Default for unmaped tissue: mean(Atlantic 297, Indian 289, Pacific 244) '
    f'= {parker_mean} days/year.')

# ─── T_map: Tier 2 — Jha LL Indian Ocean ───
add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 2: Jha LL Indian Ocean',
    'Asia', 'LL', 'APW', '<12m', 245.0, 234.0, 256.0, 'days/year', 'Triangular',
    jha_citation, 'R15',
    'Tier 2 — mechanised longline fisheries in the Indian Ocean: 234-256 days/year. '
    '16-20m mechanized longline-cum-gillnet vessels, SE Arabian Sea.')

# ─── T_map: Tier 3 — Anticamara LL/PS by Continent ───
ll_das = {
    'Africa': 274, 'Asia': 334, 'Australia & Oceania': 334,
    'Europe': 304, 'North America': 304, 'South America': 304,
}
for region, das in ll_das.items():
    add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 3: Anticamara LL',
        region, 'LL', 'ALL', 'ALL', das, None, None,
        'days/year', 'Triangular', anticamara_citation, 'R7',
        f'Tier 3 — LL {region}: {das} days/year (Anticamara et al. 2011).')

ps_das = {
    'Africa': 159, 'Asia': 195, 'Australia & Oceania': 195,
    'Europe': 177, 'North America': 177, 'South America': 177,
}
for region, das in ps_das.items():
    add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Tier 3: Anticamara PS',
        region, 'PS', 'ALL', 'ALL', das, None, None,
        'days/year', 'Triangular', anticamara_citation, 'R8',
        f'Tier 3 — PS {region}: {das} days/year (Anticamara et al. 2011).')

# PS China expert override
add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — China PS expert',
    'Asia', 'PS', 'I', 'ALL', 200.0, None, None, 'days/year', 'Triangular',
    'Expert consultation (expert consultation with Bin Xie) — China PS fleet.', 'R9',
    'China-specific PS DAS=200, Higher than average for Asia region(195).')

# Transport vessel
add('B', 'T_map_DAS', 'annual days at sea (Days at Sea) — Transport vessel',
    'ALL', 'TP', 'I', 'ALL', 180.0, None, None, 'days/year', 'Triangular',
    'Inferred from R10: "Transport 15 days per month" → 15×12=180 days/year.',
    'R10',
    'transshipment vessel/Refrigerated transport vessels: 15 days/month × 12 = 180 days/year.')

# ─── T_map: ALL-region fallbacks ───
for gear, gear_label in [('LL', 'Longline'), ('PS', 'Purse Seine')]:
    gear_vals = []
    for r in rows:
        if r['Param_Code'] == 'T_map_DAS' and r['Gear'] == gear and r['Flag'] != 'ALL':
            gear_vals.append(r['Value_Best'])
    if gear_vals:
        mean_das = round(np.mean(gear_vals), 1)
        add('B', 'T_map_DAS', 'annual days at sea (Days at Sea)',
            'ALL', gear, 'ALL', 'ALL', mean_das, None, None,
            'days/year', 'Triangular', anticamara_citation, 'R7-R11',
            f'ALL-region fallback: mean of {len(gear_vals)} regional values = {mean_das} days/year.')

# ─── H_map: Daily Engine Hours ───
add('B', 'H_map_Hday', 'daily main engine operating hours (Daily Engine Hours) — Industrial',
    'ALL', 'ALL', 'I', 'ALL', 24.0, None, None, 'h/day', 'Triangular',
    'Greer et al. (2019) Mar. Policy 107:103382; Korican et al. (2023) Ocean Eng. 286:115734',
    'R18,R20',
    'Industrial: 24h continuous deep-sea operation.')

add('B', 'H_map_Hday', 'daily main engine operating hours (Daily Engine Hours) — APW',
    'ALL', 'ALL', 'APW', 'ALL', 12.0, 4.0, 12.0, 'h/day', 'Triangular',
    'Greer et al. (2019) smallscale=4h; PNAS alpha-analysis: observed median ~9h/day → 12h',
    'R19,R21',
    'APW: coastal daytime operation. Conservative 12h As the best estimate, 4h As the lower limit.')

# PS-specific engine hours
add('B', 'H_map_Main_PS', 'PS daily main engine operating hours',
    'ALL', 'PS', 'I', 'ALL', 4.0, None, None, 'h/day', 'Triangular',
    'Korican et al. (2023) Ocean Eng. 286:115734', 'R17',
    'PS ghg_lca engine: ~4h/day (short high-power bursts for setting/hauling).')

add('B', 'H_map_Aux_PS', 'PS daily auxiliary engine operating hours',
    'ALL', 'PS', 'I', 'ALL', 15.0, None, None, 'h/day', 'Triangular',
    'Korican et al. (2023) Ocean Eng. 286:115734', 'R17',
    'PS auxiliary engine: ~15h/day (hydraulic pumps, refrigeration, lighting).')

# ===========================================================================
# SECTION C0: Engine type and fuel type mapping (Engine & Fuel Type Mapping)
# Source: R33 (Engine Class) + author-specified assumption
# ===========================================================================

# --- Engine Type ---
add('C', 'ENGINE_TYPE_FISHING_GE12M', '>=12m fishing-vessel engine type',
    'ALL', 'ALL', 'I', '>=12m', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); author-specified assumption — The diesel machine on the fishing boat is considered medium speed(MSD)',
    'R33',
    'MSD (Medium-Speed Diesel, A four-speed diesel engine). '
    'Applicable to>=12m of LL/PS/SA fishing-vessel main and auxiliary engines. '
    'Basis R33: most distant-water fishing vessels use medium-speed four-stroke diesel engines.')

add('C', 'ENGINE_TYPE_TP', 'transshipment-vessel engine type',
    'ALL', 'TP', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); author-specified assumption — The freighter heavy fuel engine is considered a slow speeder(SSD)',
    'R33',
    'SSD (Slow-Speed Diesel, low-speed two-stroke diesel engine). '
    'For trans-shipment vessels/Refrigerated transport vessels(TP)main engine.')

add('C', 'ENGINE_TYPE_SA', 'support-vessel engine type',
    'ALL', 'SA', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); author-specified assumption — Auxiliary diesel engines are considered medium speed(MSD)',
    'R33',
    'MSD (Medium-Speed Diesel, A four-speed diesel engine). Auxiliary ships are of the same type as fishing vessels.')

add('C', 'ENGINE_TYPE_FISHING_LT12M', '<12m fishing-vessel engine type',
    'ALL', 'ALL', 'APW', '<12m', None, None, None, 'categorical', 'Discrete',
    'EMEP/EEA Guidebook 2019 (R33); author-specified assumption — <12m Use of an off-board engine for petrol',
    'R33',
    'Gasoline_Outboard (Gasoline offboard). <12m Gasoline machines for small fishing vessels, no auxiliary engine.')

# --- Fuel Type ---
add('C', 'FUEL_TYPE_FISHING_GE12M', '>=12m fishing-vessel fuel type',
    'ALL', 'ALL', 'I', '>=12m', None, None, None, 'categorical', 'Discrete',
    'IMO (2020) Fourth IMO GHG Study; author-specified assumption',
    'R43',
    'MDO (Marine Diesel Oil, marine diesel oil). >=12m Use of light diesel for fishing vessels.')

add('C', 'FUEL_TYPE_TP', 'transshipment-vessel fuel type',
    'ALL', 'TP', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'IMO (2020) Fourth IMO GHG Study; author-specified assumption — Use of heavy oil on trans-shipment vessels(HFO)',
    'R43',
    'HFO (Heavy Fuel Oil, Heavy fuel oil). transshipment vessel/Heavy oil used by refrigeration transport vessels.')

add('C', 'FUEL_TYPE_SA', 'support-vessel fuel type',
    'ALL', 'SA', 'I', 'ALL', None, None, None, 'categorical', 'Discrete',
    'IMO (2020) Fourth IMO GHG Study; author-specified assumption',
    'R43',
    'MDO (Marine Diesel Oil, marine diesel oil). Auxiliary ships are of the same type as fishing vessels, Use of light diesel.')

add('C', 'FUEL_TYPE_FISHING_LT12M', '<12m fishing-vessel fuel type',
    'ALL', 'ALL', 'APW', '<12m', None, None, None, 'categorical', 'Discrete',
    'U.S. EPA (2025); author-specified assumption',
    'R33',
    'Gasoline (petrol). <12m small fishing vessels use petrol outboard engines.')

# ===========================================================================
# SECTION C1: SFCbase Baseline fuel consumption rate (IMO Fourth GHG Study Table 4)
# Source: R43
# SFC_actual = SFC_base × (0.455×L² − 0.71×L + 1.28)  [It only applies to>=12m Diesels]
# ===========================================================================

imo_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO. Table 4 — '
    'Proposed Specific Fuel Consumption (SFC; g/kWh) values.'
)

sfcbase_data = [
    # (Engine_Type, Fuel_Type, Era, Value_g_kWh, Era_Label)
    # SSD — Slow-Speed Diesel (transshipment vessel TP)
    ('SSD', 'HFO', 'Before 1983', 205, 'SSD_HFO_PRE1983'),
    ('SSD', 'HFO', '1984-2000',  185, 'SSD_HFO_1984_2000'),
    ('SSD', 'HFO', '2001+',      175, 'SSD_HFO_2001PLUS'),
    ('SSD', 'MDO', 'Before 1983', 190, 'SSD_MDO_PRE1983'),
    ('SSD', 'MDO', '1984-2000',  175, 'SSD_MDO_1984_2000'),
    ('SSD', 'MDO', '2001+',      165, 'SSD_MDO_2001PLUS'),
    # MSD — Medium-Speed Diesel (>=12m fishing vessel LL/PS/SA)
    ('MSD', 'HFO', 'Before 1983', 215, 'MSD_HFO_PRE1983'),
    ('MSD', 'HFO', '1984-2000',  195, 'MSD_HFO_1984_2000'),
    ('MSD', 'HFO', '2001+',      185, 'MSD_HFO_2001PLUS'),
    ('MSD', 'MDO', 'Before 1983', 200, 'MSD_MDO_PRE1983'),
    ('MSD', 'MDO', '1984-2000',  185, 'MSD_MDO_1984_2000'),
    ('MSD', 'MDO', '2001+',      175, 'MSD_MDO_2001PLUS'),
    # HSD — High-Speed Diesel (Stand-by/References)
    ('HSD', 'HFO', 'Before 1983', 225, 'HSD_HFO_PRE1983'),
    ('HSD', 'HFO', '1984-2000',  205, 'HSD_HFO_1984_2000'),
    ('HSD', 'HFO', '2001+',      195, 'HSD_HFO_2001PLUS'),
    ('HSD', 'MDO', 'Before 1983', 210, 'HSD_MDO_PRE1983'),
    ('HSD', 'MDO', '1984-2000',  190, 'HSD_MDO_1984_2000'),
    ('HSD', 'MDO', '2001+',      185, 'HSD_MDO_2001PLUS'),
    # MeOH (methanol) — alternative fuel, Only 2001+Its worth it
    ('SSD', 'MeOH', '2001+',     350, 'SSD_MEOH_2001PLUS'),
    ('MSD', 'MeOH', '2001+',     370, 'MSD_MEOH_2001PLUS'),
    # Auxiliary Engine (auxiliary engine) — auxiliary engines are usually medium-speed four-stroke diesel generators,
    # SFCbase Introduction MSD Values corresponding to fuel type (IMO Table 4 Practice)
    ('AUX', 'HFO', 'Before 1983', 215, 'AUX_HFO_PRE1983'),
    ('AUX', 'HFO', '1984-2000',  195, 'AUX_HFO_1984_2000'),
    ('AUX', 'HFO', '2001+',      185, 'AUX_HFO_2001PLUS'),
    ('AUX', 'MDO', 'Before 1983', 200, 'AUX_MDO_PRE1983'),
    ('AUX', 'MDO', '1984-2000',  185, 'AUX_MDO_1984_2000'),
    ('AUX', 'MDO', '2001+',      175, 'AUX_MDO_2001PLUS'),
]

# Tag N/A of SFCbase (MeOH Yes 1983 Ive been working on this for years 1984-2000 Not applicable for the period)
sfcbase_na_entries = {
    'SSD_MEOH_PRE1983', 'SSD_MEOH_1984_2000',
    'MSD_MEOH_PRE1983', 'MSD_MEOH_1984_2000',
}

for eng, fuel, era, val, code_suffix in sfcbase_data:
    code = f'SFC_BASE_{code_suffix}'
    name = f'SFC baseline value — {eng} {fuel} ({era})'
    note = (f'IMO Table 4: {eng} engine, {fuel} fuel, {era}. '
            f'SFCbase = {val} g/kWh. '
            f'For SFC_actual = SFCbase × SFOC_load_formula(LF). '
            f'It only applies to>=12m Diesels. The gas outlet does not use this formula.')
    add('C', code, name,
        'ALL', 'ALL', 'ALL', 'ALL', float(val), None, None,
        'g/kWh', 'Discrete', imo_citation, 'R43', note)

# SFCbase era boundary (For Model Query)
add('C', 'SFC_BASE_ERA_BOUNDARY_1', 'SFCbase era boundary 1 (Pre-1983 end)',
    'ALL', 'ALL', 'ALL', 'ALL', 1983.0, None, None, 'year', 'Discrete',
    imo_citation, 'R43',
    'Builtdate < 1984 → SFCbase = "Before 1983" column. '
    'Border Year 1983 is Pre-1983 Last year of the period.')

add('C', 'SFC_BASE_ERA_BOUNDARY_2', 'SFCbase era boundary 2 (1984-2000 end)',
    'ALL', 'ALL', 'ALL', 'ALL', 2000.0, None, None, 'year', 'Discrete',
    imo_citation, 'R43',
    '1984 <= Builtdate <= 2000 → SFCbase = "1984-2000" column. '
    '2001+ → SFCbase = "2001+" column.')

# ===========================================================================
# SECTION C2: SFOC Factor for load correction formula (Jalkanen et al. 2012)
# Source: R34
# SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28)
# ===========================================================================

jalkanen_citation = (
    'Jalkanen, J.-P., Johansson, L., Kukkonen, J., Brink, A., Kalli, J., & Stipa, T. (2012). '
    'Extension of an assessment model of ship traffic exhaust emissions for particulate matter '
    'and carbon monoxide. Atmos. Chem. Phys. 12:2641-2659. DOI:10.5194/acp-12-2641-2012'
)

add('C', 'SFOC_LOAD_COEFF_A', 'SFOC-quadratic load coefficient (L²)',
    'ALL', 'ALL', 'I', '>=12m', 0.455, None, None, 'dimensionless', 'Discrete',
    jalkanen_citation, 'R34',
    'SFOC_actual = SFOC_base × (0.455×L² − 0.71×L + 1.28). '
    'It only applies to>=12m four-stroke diesel main and auxiliary engines. L=Engine load factor(LF, Quantified power ratio). '
    'Example:: L=0.80→factor=1.003, L=0.20→factor=1.156, L=0.50→factor=1.039.')

add('C', 'SFOC_LOAD_COEFF_B', 'SFOC-linear load coefficient (L)',
    'ALL', 'ALL', 'I', '>=12m', -0.71, None, None, 'dimensionless', 'Discrete',
    jalkanen_citation, 'R34',
    'A single item factor. The parabolic formula is L≈0.78 Min. value in the vicinity(Most economics).')

add('C', 'SFOC_LOAD_COEFF_C', 'SFOC-load-equation constant',
    'ALL', 'ALL', 'I', '>=12m', 1.28, None, None, 'dimensionless', 'Discrete',
    jalkanen_citation, 'R34',
    'Constant items. L=0(Rust)Hour SFOC as the base value 1.28 Multiply; L=1(Full load)Hour≈1.025 Multiply.')

add('C', 'SFOC_LOAD_APPLICABILITY', 'SFOC-load-equation applicability',
    'ALL', 'ALL', 'I', '>=12m', 1.0, None, None, 'binary flag', 'Discrete',
    jalkanen_citation + '; It only applies to>=12m Diesels(main engine+auxiliary engine)',
    'R34',
    '1=Application(>=12m Diesels, this equation applies to main and auxiliary engines). '
    '0=Not applicable(<12m Gasoline offboard, Use EPA Direct SFR Value). '
    'It is recommended that the load of the backup be fixed in the efficient areas(30%-50%), Use same SFOC Formula calculation actual SFC.')

# ===========================================================================
# SECTION C3: Engine running load factor (Load Factors)
# Source: R22 (EMEP/EEA Guidebook 2019) + R23 (EPA Gasoline offboard)
#
# Logic:
#   >=12m Diesels:
#     LF_move  = 0.80 (Cruise/MCR≥65%, EMEP/EEA)
#     LF_work  = 0.20 (Manoeuvring/MCR<20%, EMEP/EEA)
#     LF_aux   = Uniform(0.30, 0.50) (auxiliary engines are not separated by phase, common load range)
#   <12m Gasoline offboard:
#     LF_move  = 0.80 (EPA Cruise load)
#     LF_work  = 0.201 (EPA mean load over the marine outboard engine certification cycle)
#     no auxiliary engine
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

# --- >=12m Industrial (diesel MSD/MDO) ---
add('C', 'LF_MAIN_MOVE', 'main engine transit load factor (T_move — Cruise)',
    'ALL', 'ALL', 'I', '>=12m', 0.80, None, None, 'fraction of MCR', 'Discrete',
    emep_citation,
    'R22',
    '>=12m diesel main engine T_move (Cruise): MCR≥65%, Typical load 80% (EMEP/EEA R22). '
    'Corresponds to R22 "Cruise: Main=80%".')

add('C', 'LF_MAIN_WORK', 'main engine fishing load factor (T_work — Manoeuvring)',
    'ALL', 'ALL', 'I', '>=12m', 0.20, None, None, 'fraction of MCR', 'Discrete',
    emep_citation,
    'R22',
    '>=12m diesel main engine T_work (Manoeuvring): MCR<20% (EMEP/EEA R22). '
    'Corresponds to R22 "Manoeuvring: Main=20%". '
    'T_work ♪ And the fishing ♪/Lets go/Get off the net/Fishing operations such as the start-up of nets.')

add('C', 'LF_AUX', 'auxiliary engine operating load factor (independent of phase, common load range)',
    'ALL', 'ALL', 'I', '>=12m', 0.40, 0.30, 0.50, 'fraction of MCR', 'Uniform',
    emep_citation,
    'R22',
    '>=12m common auxiliary engine load: Uniform(0.30, 0.50), Best Midpoint 0.40. '
    'Corresponds to R22 "Cruise: Aux=30%, Manoeuvring: Aux=50%". '
    'auxiliary engines are not separated by T_move/T_work Phase, Unified fixed load running. '
    'Use SFOC Formula calculation actual SFC Hour, Replace with LF Value.')

# --- <12m APW (Gasoline offboard) ---
add('C', 'LF_MAIN_MOVE_GASOLINE', 'petrol outboard engine transit load factor (T_move)',
    'ALL', 'ALL', 'APW', '<12m', 0.80, None, None, 'fraction of MCR', 'Discrete',
    'author-specified assumption — petrol outboard engine transit load set to 0.8',
    'R22-R23',
    '<12m Gasoline offboard T_move: 0.80 (Same as a diesel cruise).')

add('C', 'LF_MAIN_WORK_GASOLINE', 'petrol outboard engine fishing load factor (T_work)',
    'ALL', 'ALL', 'APW', '<12m', 0.201, None, None, 'fraction of MCR', 'Discrete',
    epa_lf_citation + '; author-specified assumption — Gasoline operating load used 0.201',
    'R23',
    '<12m Gasoline offboard T_work: EPA mean load over the marine outboard engine certification test cycle=20.7%≈0.201. '
    'EPA-420-R-10-016 (NR-005d): Default for SQE.')

# --- auxiliary engine applicability indicator ---
add('C', 'HAS_AUX_ENGINE', 'whether an auxiliary engine is present',
    'ALL', 'ALL', 'I', '>=12m', 1.0, None, None, 'binary flag', 'Discrete',
    'author-specified assumption — >=12m auxiliary engine present, <12m no auxiliary engine',
    'R22',
    '1=auxiliary engine present(>=12m Diesel boats). auxiliary engines generate electricity/Hydraulic/Refrigeration, etc.')

add('C', 'HAS_AUX_ENGINE', 'whether an auxiliary engine is present (<12m no auxiliary engine)',
    'ALL', 'ALL', 'APW', '<12m', 0.0, None, None, 'binary flag', 'Discrete',
    'author-specified assumption — <12m petrol-powered vessels have no auxiliary engine',
    'R22-R23',
    '0=no auxiliary engine(<12m Gasoline offboard). main engines directly power all equipment on small fishing vessels, no separate auxiliary engine.')

# ===========================================================================
# SECTION C4: CO₂ combustion emission factor (by Fuel Type)
# Source: R49 (IMO 2020)
# ===========================================================================

imo_ef_citation = (
    'International Maritime Organization. (2020). '
    'Fourth IMO GHG Study 2020. London, UK: IMO.'
)

add('C', 'EF_CO2_HFO', 'heavy fuel oil(HFO)CO₂combustion emission factor',
    'ALL', 'ALL', 'I', 'ALL', 3.114, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    'Heavy fuel oil(HFO)Incendiary CO₂emission factor: 3.114 kg CO₂/g fuel = 3.114 tCO2/tFuel. '
    'For trans-shipment vessels(TP)main engine.')

add('C', 'EF_CO2_MDO', 'marine diesel oil(MDO)CO₂combustion emission factor',
    'ALL', 'ALL', 'I', '>=12m', 3.206, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    'Light diesel for boat(MDO)Incendiary CO₂emission factor: 3.206 kg CO₂/g fuel = 3.206 tCO2/tFuel. '
    'Applicable to>=12m fishing vessel(LL/PS/SA)main and auxiliary engines.')

add('C', 'EF_CO2_Gasoline', 'petrol CO₂combustion emission factor',
    'ALL', 'ALL', 'APW', '<12m', 3.158, None, None, 'tCO2/tFuel', 'Discrete',
    'U.S. EPA (2025). Emission Factors for Greenhouse Gas Inventories. '
    'Table 2: Mobile Combustion CO2, Motor Gasoline.',
    'EPA_2025',
    'Cars/Gasoline burning from ships CO₂emission factor. '
    '8.78 kg/gallon ÷ 2.78 kg/gallon = 3.158 kg CO₂/kg petrol. '
    'Applicable to<12m Gasoline offboard.')

# LNG & Methanol CO2 EF (R49 — Stand-by/Scene analysis)
add('C', 'EF_CO2_LNG', 'liquefied natural gas(LNG)CO₂combustion emission factor',
    'ALL', 'ALL', 'ALL', 'ALL', 2.750, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    'LNG Incendiary CO₂emission factor: 2.750 kg CO₂/g fuel = 2.750 tCO2/tFuel. '
    'Low-carbon fossil fuels. For scenario analysis.')

add('C', 'EF_CO2_Methanol', 'methanol(MeOH)CO₂combustion emission factor',
    'ALL', 'ALL', 'ALL', 'ALL', 1.375, None, None, 'tCO2/tFuel', 'Discrete',
    imo_ef_citation + ' — Table: CO2 emission factors by fuel type',
    'R49',
    'Methanol burning CO₂emission factor: 1.375 kg CO₂/g fuel = 1.375 tCO2/tFuel. '
    'alternative fuel. For scenario analysis.')

# ===========================================================================
# SECTION C5: CH₄ emission factor (by Engine Type, IMO 2020)
# Source: R47 (IMO Table 56 — LNG CH4 EF) + R48 (IMO Table 58 — HFO/MDO/MeOH CH4 EF)
# CH4 Emission calculations: P × LF_avg × hours × EF_CH4(g/kWh) / 1e6 × GWP_CH4
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

add('C', 'EF_CH4_SSD', 'diesel CH₄emission factor—low-speed two-stroke(SSD)',
    'ALL', 'ALL', 'I', 'ALL', 0.010, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'SSD (Slow-Speed Diesel) CH4 EF: 0.010 g/kWh (IMO Table 58). '
    'For trans-shipment vessels(TP)main engine. ♪ All the engines of the generation and the Tier Use this value uniformly.')

add('C', 'EF_CH4_MSD', 'diesel CH₄emission factor—medium-speed four-stroke(MSD)',
    'ALL', 'ALL', 'I', 'ALL', 0.010, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'MSD (Medium-Speed Diesel) CH4 EF: 0.010 g/kWh (IMO Table 58). '
    'Applicable to>=12m fishing vessel(LL/PS/SA)main and auxiliary engines. ♪ All the engines of the generation and the Tier Use this value uniformly.')

add('C', 'EF_CH4_AUX', 'auxiliary engine CH₄emission factor',
    'ALL', 'ALL', 'I', 'ALL', 0.010, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'Auxiliary Engine CH4 EF: 0.010 g/kWh (IMO Table 58). '
    'For all>=12m fishing-vessel auxiliary engines.')

# EPA petrol CH4 (retain)
add('C', 'EF_CH4_GASOLINE_2STROKE', 'petrol CH₄emission factor—two-stroke outboard engine',
    'ALL', 'ALL', 'APW', '<12m', 3.76, None, None, 'g/kgFuel', 'Lognormal',
    'U.S. EPA (2025). Table 5: Mobile Combustion CH4 and N2O for '
    'Non-Road Vehicles, Ships and Boats.',
    'EPA_2025',
    'methane emission factor for conventional two-stroke petrol outboard engines. '
    '10.45 g/gallon ÷ 2.78 kg/gallon = 3.76 g CH₄/kg petrol.')

add('C', 'EF_CH4_GASOLINE_4STROKE', 'petrol CH₄emission factor—four-stroke outboard engine',
    'ALL', 'ALL', 'APW', '<12m', 1.50, None, None, 'g/kgFuel', 'Lognormal',
    'U.S. EPA (2025). Table 5: Mobile Combustion CH4 and N2O for '
    'Non-Road Vehicles, Ships and Boats.',
    'EPA_2025',
    'methane emission factor for modern four-stroke petrol outboard engines. '
    '4.18 g/gallon ÷ 2.78 kg/gallon = 1.50 g CH₄/kg petrol.')

# --- CH4: MeOH (R48 Table 58) ---
add('C', 'EF_CH4_SSD_MEOH', 'diesel CH₄emission factor—SSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.001, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'SSD Methanol CH4 EF: 0.001 g/kWh (IMO Table 58, MeOH column). For scenario analysis.')

add('C', 'EF_CH4_MSD_MEOH', 'diesel CH₄emission factor—MSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.001, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'MSD Methanol CH4 EF: 0.001 g/kWh (IMO Table 58, MeOH column). For scenario analysis.')

# --- CH4: Boiler & Gas Turbine (R48 Table 58, HFO/MDO) ---
add('C', 'EF_CH4_BOILER', 'CH₄emission factor—Boiler/Steam Turbine (HFO/MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.002, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'Boiler and Steam Turbine CH4 EF: 0.002 g/kWh (IMO Table 58).')

add('C', 'EF_CH4_GAS_TURBINE', 'CH₄emission factor—Gas Turbine (HFO/MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.002, None, None, 'g/kWh', 'Discrete',
    imo_ch4_citation,
    'R48',
    'Gas Turbine CH4 EF: 0.002 g/kWh (IMO Table 58).')

# --- CH4: LNG (R47 Table 56) ---
add('C', 'EF_CH4_LNG_OTTO_SS', 'CH₄emission factor—LNG Otto-SS',
    'ALL', 'ALL', 'ALL', 'ALL', 2.5, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Otto-SS (♪ The low-speed sparks set on fire ♪) CH4 EF: 2.5 g/kWh (IMO Table 56). For scenario analysis.')

add('C', 'EF_CH4_LNG_OTTO_MS', 'CH₄emission factor—LNG Otto-MS',
    'ALL', 'ALL', 'ALL', 'ALL', 5.5, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Otto-MS (Medium speed sparks lit) CH4 EF: 5.5 g/kWh (IMO Table 56). For scenario analysis.')

add('C', 'EF_CH4_LNG_DIESEL', 'CH₄emission factor—LNG-Diesel (dual fuel)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.2, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG-Diesel (dual-fuel diesel engine) CH4 EF: 0.2 g/kWh (IMO Table 56). For scenario analysis.')

add('C', 'EF_CH4_LNG_LBSI', 'CH₄emission factor—LNG LBSI',
    'ALL', 'ALL', 'ALL', 'ALL', 4.1, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG LBSI (Lean-Burn Spark Ignition) CH4 EF: 4.1 g/kWh (IMO Table 56).')

add('C', 'EF_CH4_LNG_AUX', 'CH₄emission factor—LNG Auxiliary Engine',
    'ALL', 'ALL', 'ALL', 'ALL', 5.5, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Auxiliary Engine CH4 EF: 5.5 g/kWh (IMO Table 56). For scenario analysis.')

add('C', 'EF_CH4_LNG_BOILER', 'CH₄emission factor—LNG Boiler/Steam Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.04, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Boiler/Steam Turbine CH4 EF: 0.04 g/kWh (IMO Table 56).')

add('C', 'EF_CH4_LNG_GAS_TURBINE', 'CH₄emission factor—LNG Gas Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.06, None, None, 'g/kWh', 'Discrete',
    imo_ch4_lng_citation,
    'R47',
    'LNG Gas Turbine CH4 EF: 0.06 g/kWh (IMO Table 56).')

# ===========================================================================
# SECTION C6: N₂O emission factor (by Engine Type, IMO 2020)
# Source: R45 (IMO Table 60 — LNG N2O EF) + R46 (IMO Table 59 — HFO/MDO/MeOH N2O EF)
# N2O Emission calculations: P × LF_avg × hours × EF_N2O(g/kWh) / 1e6 × GWP_N2O
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

add('C', 'EF_N2O_SSD_MDO', 'diesel N₂O emission factor—SSD/MDO',
    'ALL', 'ALL', 'I', 'ALL', 0.030, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'SSD MDO N2O EF: 0.030 g/kWh (IMO Table 59: SS row, MDO column). '
    'For trans-shipment vessels(TP)auxiliary engine(If used MDO).')

add('C', 'EF_N2O_SSD_HFO', 'diesel N₂O emission factor—SSD/HFO',
    'ALL', 'ALL', 'I', 'ALL', 0.031, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'SSD HFO N2O EF: 0.031 g/kWh (IMO Table 59: SS row, HFO column). '
    'For trans-shipment vessels(TP)main engine(Use HFO).')

add('C', 'EF_N2O_MSD_MDO', 'diesel N₂O emission factor—MSD/MDO',
    'ALL', 'ALL', 'I', 'ALL', 0.030, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'MSD MDO N2O EF: 0.030 g/kWh (IMO Table 59: MS row, MDO column). '
    'Applicable to>=12m fishing vessel(LL/PS/SA)main and auxiliary engines.')

add('C', 'EF_N2O_AUX_MDO', 'auxiliary engine N₂O emission factor—Aux/MDO',
    'ALL', 'ALL', 'I', 'ALL', 0.036, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Auxiliary Engine MDO N2O EF: 0.036 g/kWh (IMO Table 59: Aux row, MDO column). '
    'For all>=12m fishing-vessel auxiliary engines.')

# EPA petrol N2O (retain)
add('C', 'EF_N2O_GASOLINE', 'petrol N₂O emission factor',
    'ALL', 'ALL', 'APW', '<12m', 0.04, None, None, 'g/kgFuel', 'Lognormal',
    'U.S. EPA (2025). Table 5: Mobile Combustion CH4 and N2O for '
    'Non-Road Vehicles, Ships and Boats.',
    'EPA_2025',
    'Gasoline N₂O emission factor (Two-strike and four-stroke do not differ significantly, EPA Harmonization of benchmarks) . '
    '0.11 g/gallon ÷ 2.78 kg/gallon = 0.04 g N₂O/kg petrol.')

# --- N2O: MeOH (R46 Table 59) ---
add('C', 'EF_N2O_SSD_MEOH', 'N₂O emission factor—SSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.003, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'SSD Methanol N2O EF: 0.003 g/kWh (IMO Table 59, MeOH column). For scenario analysis.')

add('C', 'EF_N2O_MSD_MEOH', 'N₂O emission factor—MSD/MeOH',
    'ALL', 'ALL', 'ALL', 'ALL', 0.003, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'MSD Methanol N2O EF: 0.003 g/kWh (IMO Table 59, MeOH column). For scenario analysis.')

# --- N2O: Boiler & Gas Turbine (R46 Table 59, HFO/MDO) ---
add('C', 'EF_N2O_BOILER_HFO', 'N₂O emission factor—Boiler/Steam Turbine (HFO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.040, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Boiler/Steam Turbine HFO N2O EF: 0.040 g/kWh (IMO Table 59).')

add('C', 'EF_N2O_BOILER_MDO', 'N₂O emission factor—Boiler/Steam Turbine (MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.049, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Boiler/Steam Turbine MDO N2O EF: 0.049 g/kWh (IMO Table 59).')

add('C', 'EF_N2O_GAS_TURBINE_HFO', 'N₂O emission factor—Gas Turbine (HFO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.040, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Gas Turbine HFO N2O EF: 0.040 g/kWh (IMO Table 59).')

add('C', 'EF_N2O_GAS_TURBINE_MDO', 'N₂O emission factor—Gas Turbine (MDO)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.049, None, None, 'g/kWh', 'Discrete',
    imo_n2o_citation,
    'R46',
    'Gas Turbine MDO N2O EF: 0.049 g/kWh (IMO Table 59).')

# --- N2O: LNG (R45 Table 60) ---
add('C', 'EF_N2O_LNG_OTTO_SS', 'N₂O emission factor—LNG Otto-SS',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Otto-SS N2O EF: 0.020 g/kWh (IMO Table 60). For scenario analysis.')

add('C', 'EF_N2O_LNG_OTTO_MS', 'N₂O emission factor—LNG Otto-MS',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Otto-MS N2O EF: 0.020 g/kWh (IMO Table 60). For scenario analysis.')

add('C', 'EF_N2O_LNG_DIESEL', 'N₂O emission factor—LNG-Diesel (dual fuel)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.030, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG-Diesel N2O EF: 0.030 g/kWh (IMO Table 60). For scenario analysis.')

add('C', 'EF_N2O_LNG_LBSI', 'N₂O emission factor—LNG LBSI',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG LBSI N2O EF: 0.020 g/kWh (IMO Table 60).')

add('C', 'EF_N2O_LNG_AUX', 'N₂O emission factor—LNG Auxiliary Engine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Auxiliary Engine N2O EF: 0.020 g/kWh (IMO Table 60). For scenario analysis.')

add('C', 'EF_N2O_LNG_BOILER', 'N₂O emission factor—LNG Boiler/Steam Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Boiler/Steam Turbine N2O EF: 0.020 g/kWh (IMO Table 60).')

add('C', 'EF_N2O_LNG_GAS_TURBINE', 'N₂O emission factor—LNG Gas Turbine',
    'ALL', 'ALL', 'ALL', 'ALL', 0.020, None, None, 'g/kWh', 'Discrete',
    imo_n2o_lng_citation,
    'R45',
    'LNG Gas Turbine N2O EF: 0.020 g/kWh (IMO Table 60).')

# ===========================================================================
# SECTION C7: Upstream emission factors (Well-to-Tank, WTT)
# ===========================================================================

add('C', 'EF_WTT_DIESEL', 'upstream diesel(WTT)carbon emission factor',
    'ALL', 'ALL', 'ALL', 'ALL', 0.369, 0.318, 0.441,
    'kg CO2eq/kg diesel', 'Lognormal',
    'Ecoinvent v3 — market for diesel | diesel | Cutoff, U - RoW (1000 MC simulations)',
    'Ecoinvent_Diesel_WTT',
    '1 kg Upstream diesel production and transport carbon emissions (Cradle-to-Tank). '
    'Mean=0.369, SD=0.031, Median=0.366, 95% CI [0.318, 0.441].')

add('C', 'EF_WTT_GASOLINE', 'upstream petrol(WTT)carbon emission factor',
    'ALL', 'ALL', 'APW', 'ALL', 0.535, 0.489, 0.595,
    'kg CO2eq/kg petrol', 'Lognormal',
    'Ecoinvent v3 — market for petrol, two-stroke blend | petrol, two-stroke blend | '
    'Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_Gasoline_WTT',
    '1 kg Upstream production and transport of carbon emissions from gasoline (Cradle-to-Tank). '
    'Mean=0.535, SD=0.029, Median=0.532, 95% CI [0.489, 0.595].')

add('C', 'EF_WTT_HFO', 'upstream heavy fuel oil(WTT)carbon emission factor',
    'ALL', 'ALL', 'ALL', 'ALL', 0.252, 0.211, 0.309,
    'kg CO2eq/kg HFO', 'Lognormal',
    'Ecoinvent v3 — market for heavy fuel oil | heavy fuel oil | Cutoff, U - RoW '
    '(1000 MC simulations)',
    'Ecoinvent_HFO_WTT',
    '1 kg Upstream production and transport of carbon emissions from heavy oil (Cradle-to-Tank). '
    'Mean=0.252, SD=0.026, Median=0.250, 95% CI [0.211, 0.309].')

# ===========================================================================
# SECTION C8: GWP (Global warming potential)
# ===========================================================================

add('C', 'GWP_CH4_100yr', 'methane 100 year global warming potential',
    'ALL', 'ALL', 'ALL', 'ALL', 28.5, 27.0, 30.0,
    'kgCO2e/kgCH4', 'Uniform',
    'IPCC AR5/AR6',
    'R50',
    'CH4 GWP-100: IPCC range 27-30, midpoint 28.5 (R50).')

add('C', 'GWP_N2O_100yr', 'nitrous oxide 100 year global warming potential',
    'ALL', 'ALL', 'ALL', 'ALL', 273.0, None, None,
    'kgCO2e/kgN2O', 'Discrete',
    'IPCC AR6',
    'R50',
    'N2O GWP-100: 273 (IPCC AR6, R50).')

# ===========================================================================
# SECTION C9: FC_LOOKUP Fuel efficiency time factor
# ===========================================================================

add('C', 'FC_LOOKUP_Baseline_Year', 'fuel-efficiency time-factor baseline year',
    'ALL', 'ALL', 'ALL', 'ALL', 2000.0, None, None, 'year', 'Discrete',
    'Yanmar marine engine data (interpolated); Greer et al. (2019)',
    'R55',
    'FC=1.0 at year 2000 (baseline). Pre-2000 >1.0 (less efficient), '
    'post-2004 =0.99 (stable).')

add('C', 'FC_LOOKUP_Min', 'minimum fuel-efficiency time factor',
    'ALL', 'ALL', 'ALL', 'ALL', 0.99, None, None, 'dimensionless', 'Discrete',
    'Yanmar data; 2004-2016 stable period',
    'R55',
    'Minimum FC = 0.99 (most efficient era, 2004-2016).')

add('C', 'FC_LOOKUP_Max', 'maximum fuel-efficiency time factor',
    'ALL', 'ALL', 'ALL', 'ALL', 1.21, None, None, 'dimensionless', 'Discrete',
    'Yanmar data; 1950-1951 peak',
    'R55',
    'Maximum FC = 1.21 (least efficient era, 1950-1951).')

# ===========================================================================
# SECTION C10: alternative fuel SFR (Scene analysis)
# ===========================================================================

add('C', 'SFR_Methanol_Diesel_80', 'methanol-diesel blend (80%energy substitution) SFR',
    'ALL', 'ALL', 'ALL', 'ALL', 0.000439, None, None, 'tFuel/kWh', 'Lognormal',
    'Sjeric et al. (2026) Ocean Eng. 345:123864',
    'R39',
    '438.58 g/kWh = 0.000439 t/kWh. Used in scenario S4, S14.')

add('C', 'SFR_H2_Diesel_80', 'hydrogen-diesel blend (80%energy substitution) SFR',
    'ALL', 'ALL', 'ALL', 'ALL', 0.000112, None, None, 'tFuel/kWh', 'Lognormal',
    'Sjeric et al. (2026) Ocean Eng. 345:123864',
    'R40',
    '112.32 g/kWh = 0.000112 t/kWh. Used in scenario S14.')

# ===========================================================================
# SECTION L: EPA Gasoline offboard SFR Data (retain)
# Gasoline exteriors are not used SFOC Formula, Directly use below SFR Value
# ===========================================================================

epa_sfr_citation = (
    'U.S. EPA. Exhaust Emission Factors for Nonroad Engine Modeling — '
    'Spark-Ignition. EPA-420-R-10-019 (NR-010f).'
)

add('L', 'SFR_GASOLINE_2STROKE', 'EPA conventional two-stroke petrol outboard engine SFR',
    'ALL', 'ALL', 'APW', '<12m', 0.000592, 0.000547, 0.000638,
    'tFuel/kWh', 'Triangular',
    epa_sfr_citation,
    'EPA_NR010f',
    'The traditional two-stroke: 0.90-1.05 lb/hp-hr = 547-638 g/kWh. Best=592 g/kWh. '
    'Applicable to<12m conventional two-stroke petrol outboard engines. This value is used directly as SFR, No, Im not SFOC Load Fix.')

add('L', 'SFR_GASOLINE_4STROKE', 'EPA modern four-stroke petrol outboard engine SFR',
    'ALL', 'ALL', 'APW', '<12m', 0.000319, 0.000304, 0.000334,
    'tFuel/kWh', 'Triangular',
    epa_sfr_citation,
    'EPA_NR010f',
    'Modern Four-Four: 0.50-0.55 lb/hp-hr = 304-334 g/kWh. Best=319 g/kWh. '
    'Applicable to<12m modern four-stroke petrol outboard engine. This value is used directly as SFR, No, Im not SFOC Load Fix.')

add('L', 'SFR_GASOLINE_DI_2STROKE', 'EPA direct-injection two-stroke petrol outboard engine SFR',
    'ALL', 'ALL', 'APW', '<12m', 0.000365, 0.000334, 0.000395,
    'tFuel/kWh', 'Triangular',
    epa_sfr_citation,
    'EPA_NR010f',
    'Two straight ahead: 0.55-0.65 lb/hp-hr = 334-395 g/kWh. Best=365 g/kWh. '
    'Applicable to<12m direct-injection two-stroke petrol outboard engine. This value is used directly as SFR, No, Im not SFOC Load Fix.')

# EPA Default load factor for the petrol outboard (Reservation as a reference)
add('L', 'LF_EPA_OUTBOARD_GASOLINE', 'EPA default marine petrol outboard engine load factor (combined operating cycle)',
    'ALL', 'ALL', 'APW', '<12m', 0.207, None, None, 'fraction of MCR', 'Discrete',
    epa_lf_citation,
    'EPA_NR005d',
    'EPA Default load factors for baseline testing of all conventional off-board petrol machines: 20.7%. '
    'Actual modelling T_work Introduction 0.201 (EPA Authentication cycle average load), T_move Introduction 0.8. '
    'Keep this parameter as a reference.')

# ===========================================================================
# SECTION D: auxiliary engine power ratio (Auxiliary Engine Power Ratio)
# Source: R56 — 2010 Global fleet of ships for the year (2010 world fleet) Column
# Uniformly adopted EMEP/EEA Guidebook 2019 of 2010 Global fleet data for the year
# ===========================================================================

add('D', 'AUX_POWER_RATIO_FISHING', 'auxiliary engine/main engine power ratio — fishing vessel (Fishing)',
    'ALL', 'ALL', 'I', '>=12m', 0.39, None, None, 'ratio', 'Discrete',
    'De Lauretis, R., Ntziachristos, L., & Trozzi, C. (2021). '
    'EMEP/EEA air pollutant emission inventory guidebook 2019. '
    'Table: 2010 world fleet auxiliary-to-ghg_lca power ratio.',
    'R56',
    'fishing vessel (Fishing) auxiliary engine/main engine power ratio: 0.39 (2010 Global fleet of ships for the year). '
    'Applicable to>=12m of LL/PS Fishing vessels.')

add('D', 'AUX_POWER_RATIO_TP', 'auxiliary engine/main engine power ratio — transshipment vessel (General Cargo)',
    'ALL', 'TP', 'I', 'ALL', 0.23, None, None, 'ratio', 'Discrete',
    'De Lauretis, R., Ntziachristos, L., & Trozzi, C. (2021). '
    'EMEP/EEA air pollutant emission inventory guidebook 2019. '
    'Table: 2010 world fleet auxiliary-to-ghg_lca power ratio.',
    'R56',
    'transshipment vessel(TP) auxiliary engine/main engine power ratio: 0.23 (Misc cargo ships General Cargo, 2010 Global fleet of ships for the year).')

add('D', 'AUX_POWER_RATIO_SA', 'auxiliary engine/main engine power ratio — support vessel (Other)',
    'ALL', 'SA', 'I', 'ALL', 0.35, None, None, 'ratio', 'Discrete',
    'De Lauretis, R., Ntziachristos, L., & Trozzi, C. (2021). '
    'EMEP/EEA air pollutant emission inventory guidebook 2019. '
    'Table: 2010 world fleet auxiliary-to-ghg_lca power ratio.',
    'R56',
    'support vessel(SA) auxiliary engine/main engine power ratio: 0.35 (Other Other, 2010 Global fleet of ships for the year).')

# ===========================================================================
# SECTION E: Parameters for the construction and maintenance of the hull (Hull Construction & Maintenance)
# Only keep construction/maintenance EF and life expectancy parameters; material share/Anti-fouling paint/Unused parameters for models such as recovery have been removed
# ===========================================================================

# construction EF
add('E', 'EF_BUILD_PS_STEEL', 'construction emission factor for steel purse-seine vessels (cradle-to-gate)',
    'ALL', 'PS', 'I', '>=12m', 2.421, 2.332, 2.528,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner, steel | Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_PS_Steel',
    '1 kg purse seiner steel construction. Mean=2.421, 95% CI [2.332, 2.528].')

add('E', 'EF_BUILD_PS_WOOD', 'construction emission factor for wooden purse-seine vessels (cradle-to-gate)',
    'ALL', 'PS', 'APW', '<12m', 0.578, 0.513, 0.678,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner, wood | Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_PS_Wood',
    '1 kg purse seiner wood construction. Mean=0.578, 95% CI [0.513, 0.678].')

add('E', 'EF_BUILD_LL_STEEL', 'construction emission factor for steel longline vessels (cradle-to-gate)',
    'ALL', 'LL', 'I', '>=12m', 1.956, 1.877, 2.069,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Ecoinvent v3 — market for long liner, steel | Cutoff, U - GLO (1000 MC simulations)',
    'Ecoinvent_LL_Steel',
    '1 kg long liner steel construction. Mean=1.956, 95% CI [1.877, 2.069].')

add('E', 'EF_BUILD_LL_WOOD', 'construction emission factor for wooden longline vessels (same as wooden purse-seine vessels)',
    'ALL', 'LL', 'APW', '<12m', 0.578, 0.513, 0.678,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Same EF_BUILD_PS_WOOD',
    'Ecoinvent_PS_Wood',
    'small longline vessels (<12m, wood) Construction of carbon emissions: same factor as wooden purse-seine vessels 0.578 kg CO2eq/kg.')

add('E', 'EF_BUILD_TS', 'transshipment vessel/support-vessel construction emission factor (same as steel purse-seine vessels)',
    'ALL', 'TP', 'I', 'ALL', 2.421, 2.332, 2.528,
    'kg CO2eq/kg vessel', 'Lognormal',
    'Same EF_BUILD_PS_STEEL',
    'Ecoinvent_PS_Steel',
    'transshipment vessel/Carbon emissions from construction of support vessels: same factor as steel purse-seine vessels 2.421 kg CO2eq/kg.')

# maintenance EF
add('E', 'EF_MAINT_PS_STEEL', 'maintenance emission factor for steel purse-seine vessels (cradle-to-gate)',
    'ALL', 'PS', 'I', '>=12m', 6.744, 6.627, 6.883,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner maintenance, steel | Cutoff, U - GLO',
    'Ecoinvent_PS_Steel_Maint',
    '1 kg purse seiner steel maintenance. Mean=6.744, 95% CI [6.627, 6.883].')

add('E', 'EF_MAINT_PS_WOOD', 'maintenance emission factor for wooden purse-seine vessels (cradle-to-gate)',
    'ALL', 'PS', 'APW', '<12m', 1.289, 1.179, 1.437,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Ecoinvent v3 — market for purse seiner maintenance, wood | Cutoff, U - GLO',
    'Ecoinvent_PS_Wood_Maint',
    '1 kg purse seiner wood maintenance. Mean=1.289, 95% CI [1.179, 1.437].')

add('E', 'EF_MAINT_LL_STEEL', 'maintenance emission factor for steel longline vessels (cradle-to-gate)',
    'ALL', 'LL', 'I', '>=12m', 4.450, 3.777, 5.376,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Ecoinvent v3 — market for long liner maintenance, steel | Cutoff, U - GLO',
    'Ecoinvent_LL_Steel_Maint',
    '1 kg long liner steel maintenance. Mean=4.450, 95% CI [3.777, 5.376].')

add('E', 'EF_MAINT_LL_WOOD', 'maintenance emission factor for wooden longline vessels (same as wooden purse-seine vessels)',
    'ALL', 'LL', 'APW', '<12m', 1.289, 1.179, 1.437,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Same EF_MAINT_PS_WOOD',
    'Ecoinvent_PS_Wood_Maint',
    'small longline vessels (<12m, wood) Maintenance of carbon emissions: same factor as wooden purse-seine vessels 1.289 kg CO2eq/kg.')

add('E', 'EF_MAINT_TS', 'transshipment vessel/support-vessel maintenance emission factor (same as steel purse-seine vessels)',
    'ALL', 'TP', 'I', 'ALL', 6.744, 6.627, 6.883,
    'kg CO2eq/kg maintenance', 'Lognormal',
    'Same EF_MAINT_PS_STEEL',
    'Ecoinvent_PS_Steel_Maint',
    'transshipment vessel/Auxiliary ships maintain carbon emissions: same factor as steel purse-seine vessels 6.744 kg CO2eq/kg.')

# Life parameters
add('E', 'LIFESPAN_HULL', 'hull service life (steel)',
    'ALL', 'ALL', 'ALL', 'ALL', 30.0, None, None, 'years', 'Discrete',
    'SUPERPROP (2012); Hospido & Tyedmers (2005); Ceballos-Santos et al. (2023)',
    'R93-R95',
    'Steel hull lifespan: 30 years. Wood hull: 40yr (not used in current model).')

add('E', 'LIFESPAN_ENGINE', 'engine service life (replacement interval)',
    'ALL', 'ALL', 'ALL', 'ALL', 10.0, None, None, 'years', 'Discrete',
    'SUPERPROP (2012); Hospido & Tyedmers (2005)',
    'R93-R94',
    'Engine lifespan: 10 years. Replaced once during 30yr hull life = 2 engines total.')

# ===========================================================================
# SECTION F: Parameters for the consumption of gear material (Gear Material Consumption)
# ===========================================================================

# gear_int
gear_int_ps_small_low  = min(17.9, 9.12) / 1000       # 0.00912
gear_int_ps_small_high = max(17.9, 9.12) / 1000       # 0.01790
gear_int_ps_small_best = (9.12 + 17.9) / (2 * 1000)   # 0.01351

add('F', 'gear_int_PS', 'purse-seine gear mass per unit vessel length (small vessels <12m)',
    'ALL', 'PS', 'ALL', '<12m',
    round(gear_int_ps_small_best, 6), round(gear_int_ps_small_low, 6),
    round(gear_int_ps_small_high, 6),
    't gear / m vessel length', 'Uniform',
    'Rosario (2011) — Mozambique artisanal purse seine; GRO Centre',
    'R69',
    f'Uniform[9.12, 17.9] kg/m. Best={gear_int_ps_small_best:.5f} t/m. '
    'small artisanal purse-seine fisheries(8-12m fishing vessel), Mozambique fisheries data.')

gear_int_ps_large_low  = min(251.0, 54.0) / 1000       # 0.054
gear_int_ps_large_high = max(251.0, 54.0) / 1000       # 0.251
gear_int_ps_large_best = (251.0 + 54.0) / (2 * 1000)   # 0.1525

add('F', 'gear_int_PS', 'purse-seine gear mass per unit vessel length (large vessels >=12m)',
    'ALL', 'PS', 'ALL', '>=12m',
    round(gear_int_ps_large_best, 4), round(gear_int_ps_large_low, 4),
    round(gear_int_ps_large_high, 4),
    't gear / m vessel length', 'Uniform',
    'Meenakumari (2016) — Purse seining in India. Indian J. Fish. 63(3)',
    'R70',
    f'Uniform[54.0, 251.0] kg/m. Best={gear_int_ps_large_best:.4f} t/m. '
    'Indian purse-seine fisheries(11-24m fishing vessel).')

gear_int_ll_low  = min(0.490, 0.120) / (0.0036 * 1000)    # 0.03333
gear_int_ll_high = max(0.490, 0.120) / (0.0036 * 1000)    # 0.13611
gear_int_ll_best = (0.490 + 0.120) / (2 * 0.0036 * 1000)  # 0.08472

add('F', 'gear_int_LL', 'longline gear mass per unit vessel length',
    'ALL', 'LL', 'ALL', 'ALL',
    round(gear_int_ll_best, 6), round(gear_int_ll_low, 6),
    round(gear_int_ll_high, 6),
    't gear / m vessel length', 'Uniform',
    'Gabr & Elhaweet (2012) — Pelagic Longline Fishery for Albacore off Egypt. '
    'Turkish J. Fish. Aquat. Sci. 12:735-741',
    'R71',
    f'Uniform[0.120, 0.490] kg/hook. Best={gear_int_ll_best:.5f} t/m. '
    '1 hook ≈ 0.0036m vessel length. Longline longlines for longfin tuna in the Egyptian Mediterranean.')

# Composition of network materials — PS: nylon(PA6+EVA) 73.9% + steel 26.1%; LL: Same PS Percentage
# Source: Andrés et al. (2022) — PA6=64.2%, EVA=9.7%, Steel=26.1%
# author-specified assumption: Float(EVA)Jimbi is integrated into the nylon, longline uses the same nylon/steel scale
nylon_ps = round(0.642 + 0.097, 3)  # 0.739 (PA6 + EVA merged)
steel_ps = 0.261

add('F', 'GEAR_MATERIAL_NYLON_PS', 'purse-seine nylon (PA6+EVA) material share',
    'ALL', 'PS', 'ALL', 'ALL', nylon_ps, None, None, 'mass fraction', 'Discrete',
    'Andrés et al. (2022) Front. Sustain. 3:929902',
    'R72',
    f'PA6 (64.2%) + EVA Float (9.7%) = {nylon_ps} (Merge into nylon). '
    'Includes netting, ropes, float lines, EVA floats.')

add('F', 'GEAR_MATERIAL_STEEL_PS', 'purse-seine metal components (steel) share',
    'ALL', 'PS', 'ALL', 'ALL', steel_ps, None, None, 'mass fraction', 'Discrete',
    'Andrés et al. (2022) Front. Sustain. 3:929902',
    'R72',
    f'Steel components = {steel_ps} of PS net weight. Includes chains, rings, wire rope.')

add('F', 'GEAR_MATERIAL_NYLON_LL', 'nylon share of longline gear materials (same as purse seine)',
    'ALL', 'LL', 'ALL', 'ALL', nylon_ps, None, None, 'mass fraction', 'Discrete',
    'Same GEAR_MATERIAL_NYLON_PS — Andrés et al. (2022)',
    'R72',
    f'LL nylon = {nylon_ps} (same as purse seine PA6+EVA Merge value). The main rope+A strap+The floats are all nylons.')

add('F', 'GEAR_MATERIAL_STEEL_LL', 'longline metal components (steel) share (same as purse seine)',
    'ALL', 'LL', 'ALL', 'ALL', steel_ps, None, None, 'mass fraction', 'Discrete',
    'Same GEAR_MATERIAL_STEEL_PS — Andrés et al. (2022)',
    'R72',
    f'LL steel hardware = {steel_ps} (same steel share as purse seine). hooks, Ring, Suzuko waits for the hardware.')

# fishing gear EF
add('F', 'EMISSION_FACTOR_NYLON_PA6', 'nylon(PA6)carbon emission factor (cradle-to-gate)',
    'ALL', 'ALL', 'ALL', 'ALL', 9.885, 9.807, 9.969,
    'kg CO2eq/kg nylon', 'Lognormal',
    'Self-building foreground process — fishing net production, nylon, 1kg (1000 MC simulations)',
    'SelfBuilt_NylonNet',
    'Mean=9.885, 95% CI [9.807, 9.969].')

add('F', 'EMISSION_FACTOR_STEEL_GEAR', 'gear steel/metal-component emission factor (cradle-to-gate)',
    'ALL', 'ALL', 'ALL', 'ALL', 3.070, 2.819, 3.374,
    'kg CO2eq/kg steel hardware', 'Lognormal',
    'Self-building foreground process — longline hardware, steel, 1kg (1000 MC simulations)',
    'SelfBuilt_LL_Hardware',
    'Mean=3.070, 95% CI [2.819, 3.374].')

# Interruption of devices
add('F', 'GEAR_INT_TRUNC_LL_MAX_KW', 'longline gear_int physical truncation—maximum power',
    'ALL', 'LL', 'ALL', 'ALL', 1600.0, None, None, 'kW', 'Discrete',
    'Kuczenski et al. (2022) Fish. Fish. 23:22-33',
    'R68', 'LL Maximum power margin for fishing vessels 1600 kW.')

add('F', 'GEAR_INT_TRUNC_LL_MAX_LOA_M', 'longline gear_int physical truncation—maximum vessel length',
    'ALL', 'LL', 'ALL', 'ALL', 55.0, None, None, 'm', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'LL Maximum number of fishing boats LOA NYO 55m.')

add('F', 'GEAR_INT_TRUNC_LL_MAX_GT', 'longline gear_int physical truncation—maximum gross tonnage',
    'ALL', 'LL', 'ALL', 'ALL', 800.0, None, None, 'GT', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'LL Maximum number of fishing boats GT NYO 800.')

add('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_KW', 'purse seine(small-vessel group) gear_int physical truncation—maximum power',
    'ALL', 'PS', 'ALL', '<12m', 1000.0, None, None, 'kW', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'PS Small cluster ceiling: 1000 kW, 50m LOA, 750 GT.')

add('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_LOA_M', 'purse seine(small-vessel group) gear_int physical truncation—maximum vessel length',
    'ALL', 'PS', 'ALL', '<12m', 50.0, None, None, 'm', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'PS small-vessel group LOA Maximum Treaty 50m.')

add('F', 'GEAR_INT_TRUNC_PS_SMALL_MAX_GT', 'purse seine(small-vessel group) gear_int physical truncation—maximum gross tonnage',
    'ALL', 'PS', 'ALL', '<12m', 750.0, None, None, 'GT', 'Discrete',
    'Kuczenski et al. (2022)',
    'R68', 'PS small-vessel group GT Maximum Treaty 750.')

add('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_KW', 'purse seine(large-vessel group) gear_int physical truncation—maximum power',
    'ALL', 'PS', 'ALL', '>=12m', 2500.0, 2000.0, 3000.0, 'kW', 'Triangular',
    'Kuczenski et al. (2022)',
    'R68', 'PS Large cluster cap: 2000-3000 kW, 60-80m LOA, 1000-2000 GT.')

add('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_LOA_M', 'purse seine(large-vessel group) gear_int physical truncation—maximum vessel length',
    'ALL', 'PS', 'ALL', '>=12m', 70.0, 60.0, 80.0, 'm', 'Triangular',
    'Kuczenski et al. (2022)',
    'R68', 'PS large-vessel group LOA Scope 60-80m.')

add('F', 'GEAR_INT_TRUNC_PS_LARGE_MAX_GT', 'purse seine(large-vessel group) gear_int physical truncation—maximum gross tonnage',
    'ALL', 'PS', 'ALL', '>=12m', 1500.0, 1000.0, 2000.0, 'GT', 'Triangular',
    'Kuczenski et al. (2022)',
    'R68', 'PS large-vessel group GT Scope 1000-2000.')

# Life of devices/maintenance
add('F', 'LIFESPAN_GEAR_PS', 'purse-seine service life',
    'ALL', 'PS', 'ALL', 'ALL', 5.0, 3.0, 5.0, 'years', 'Triangular',
    'Vazquez-Rowe et al. (2010) Fish. Res. 106(3):517-527; Andrés et al. (2022)',
    'R74-R76',
    'PS net lifespan: 5yr. Annual replacement 25% in non-renewal years.')

add('F', 'LIFESPAN_GEAR_LL', 'longline service life',
    'ALL', 'LL', 'ALL', 'ALL', 5.0, 3.0, 5.0, 'years', 'Triangular',
    'Ceballos-Santos et al. (2023); Kuczenski et al. (2022)',
    'R79-R80',
    'LL gear lifespan: 5yr.')

add('F', 'MAINTENANCE_RATE_GEAR_PS', 'annual purse-seine maintenance replacement fraction',
    'ALL', 'PS', 'ALL', 'ALL', 0.25, 0.20, 0.33, 'fraction per year', 'Triangular',
    'Vazquez-Rowe et al. (2010); Ceballos-Santos et al. (2023)',
    'R74-R76',
    'PS: 25% annual gear replacement (in non-renewal years).')

add('F', 'MAINTENANCE_RATE_GEAR_LL', 'annual longline maintenance replacement fraction',
    'ALL', 'LL', 'ALL', 'ALL', 0.25, 0.20, 0.33, 'fraction per year', 'Triangular',
    'Ceballos-Santos et al. (2023); Kuczenski et al. (2022)',
    'R79-R80',
    'LL: 25% annual gear replacement (in non-renewal years).')

# ===========================================================================
# SECTION G: Literary consumption parameters (Bait Consumption)
# ===========================================================================

add('G', 'BAIT_WEIGHT_PER_HOOK_KG', 'mean bait mass per longline hook',
    'ALL', 'LL', 'ALL', 'ALL', 0.10, 0.05, 0.15, 'kg/hook', 'Triangular',
    'Jha et al. (2026); ghg_lca.py BAIT_WEIGHT_PER_HOOK_KG',
    'R107',
    'Default: 0.1 kg per hook (low-value trash fish). Range: 0.05-0.15 kg/hook.')

add('G', 'EMISSION_FACTOR_BAIT', 'bait emission factor (cradle-to-gate)',
    'ALL', 'LL', 'ALL', 'ALL', 1.606, 1.548, 1.670,
    'kg CO2eq/kg bait', 'Lognormal',
    'Ecoinvent v3 — market for small pelagic fish, fresh | Cutoff, U - GLO '
    '(1000 MC simulations)',
    'Ecoinvent_Bait',
    'Mean=1.606, 95% CI [1.548, 1.670].')

add('G', 'HOOKS_PER_LINE_RANGE_LOW', 'minimum hooks per longline set',
    'ALL', 'LL', 'ALL', 'ALL', 1666.0, 500.0, 1666.0, 'hooks/line', 'Triangular',
    'Jha et al. (2026)',
    'R105-R106',
    '500-1500 hooks per trip; 1666-2147 total hooks per line.')

add('G', 'HOOKS_PER_LINE_RANGE_HIGH', 'maximum hooks per longline set',
    'ALL', 'LL', 'ALL', 'ALL', 2147.0, 1666.0, 3000.0, 'hooks/line', 'Triangular',
    'Jha et al. (2026)',
    'R106',
    'Upper bound: 2147 hooks. Extended upper bound: 3000 for large industrial LL.')

# ===========================================================================
# SECTION H: Refrigerant parameters (Refrigerant)
# ===========================================================================

add('H', 'R22_GWP', 'R22 refrigerant global warming potential (100yr)',
    'ALL', 'ALL', 'ALL', 'ALL', 1810.0, None, None, 'kgCO2e/kg R22', 'Discrete',
    'IPCC (2007)',
    'R99',
    'R22 (HCFC) GWP-100 = 1810.')

add('H', 'R22_LEAK_COASTAL_TRAWL', 'R22 annual leakage (coastal trawlers)',
    'ALL', 'ALL', 'ALL', 'ALL', 150.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011); Vazquez-Rowe et al. (2010)',
    'R100-R101',
    'Coastal trawl: 150 kg R22/yr.')

add('H', 'R22_LEAK_COASTAL_PS', 'R22 annual leakage (coastal purse-seine vessels)',
    'ALL', 'PS', 'ALL', 'ALL', 10.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011); Vazquez-Rowe et al. (2010)',
    'R100-R101',
    'Coastal PS: 10 kg R22/yr.')

add('H', 'R22_LEAK_OFFSHORE', 'R22 annual leakage (offshore fishing vessels)',
    'ALL', 'ALL', 'ALL', 'ALL', 200.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011)',
    'R100',
    'Offshore vessels: 200 kg R22/yr.')

add('H', 'R22_LEAK_DISTANT_PS', 'R22 annual leakage (offshore purse-seine vessels)',
    'ALL', 'PS', 'ALL', 'ALL', 500.0, None, None, 'kg R22/year/vessel', 'Triangular',
    'Iribarren et al. (2011)',
    'R100',
    'Distant-water PS: 500 kg R22/yr. Tuna PS (Indian Ocean): 751 g/t reference.')

# ===========================================================================
# SECTION I: Efforts to standardize parameters (Effort Standardization)
# ===========================================================================

add('I', 'HOOKS_PER_DAY', 'standard longline hooks per day (Effort standardisation)',
    'ALL', 'LL', 'ALL', 'ALL', 3000.0, None, None, 'hooks/day', 'Triangular',
    'ghg_lca.py HOOKS_PER_DAY constant; Jha et al. (2026)',
    'R105-R106',
    'Standard LL hooks per day. Model: Std_Effort(LL) = EffortValue × HOOKS_PER_DAY.')

add('I', 'HOURS_PER_SET', 'standard purse-seine hours per set (Effort standardisation)',
    'ALL', 'PS', 'ALL', 'ALL', 12.0, None, None, 'hours/set', 'Triangular',
    'ghg_lca.py HOURS_PER_SET constant; Korican et al. (2023)',
    'R17',
    'Standard PS hours per set (searching + operation).')

# ===========================================================================
# SECTION J: Power growth parameters (Power Growth Rate)
# ===========================================================================

add('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Europe)',
    'Europe', 'ALL', 'ALL', 'ALL', 0.002, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Europe: 0.2%/yr — lowest growth.')

add('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Asia)',
    'Asia', 'ALL', 'ALL', 'ALL', 0.012, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Asia: 1.2%/yr — highest growth.')

add('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (North America)',
    'North America', 'ALL', 'ALL', 'ALL', 0.011, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'North America: 1.1%/yr.')

add('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Africa)',
    'Africa', 'ALL', 'ALL', 'ALL', 0.009, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Africa: 0.9%/yr.')

add('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (South America)',
    'South America', 'ALL', 'ALL', 'ALL', 0.011, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'South America: 1.1%/yr.')

add('J', 'POWER_GROWTH_RATE', 'annual main engine power growth rate (Oceania)',
    'Australia & Oceania', 'ALL', 'ALL', 'ALL', 0.017, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R61', 'Oceania: 1.7%/yr — highest among regions.')

add('J', 'POWER_GROWTH_RATE_LL', 'annual main engine power growth rate (longline fleet)',
    'ALL', 'LL', 'ALL', 'ALL', 0.01, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R62', 'LL fleet: 1.0%/yr.')

add('J', 'POWER_GROWTH_RATE_PS', 'annual main engine power growth rate (purse-seine fleet)',
    'ALL', 'PS', 'ALL', 'ALL', 0.004, None, None, 'fraction/year', 'Normal',
    'Anticamara et al. (2011)',
    'R62', 'PS fleet: 0.4%/yr.')

add('J', 'POWER_GROWTH_DECADAL_HP', 'decadal main engine power growth rate',
    'ALL', 'ALL', 'ALL', 'ALL', 0.045, 0.03, 0.06, 'fraction/decade', 'Triangular',
    'SPC (2016) WCPFC-SC12-2016/MI-WP-08',
    'R60', 'Vessel HP grew 3-6% over study period. Best=4.5%.')

# ===========================================================================
# SECTION K: GT-LDT Tonn conversion (GT→LDT Conversion)
# ===========================================================================

add('K', 'LDT_GT_RATIO_FISHING', 'fishing vessel GT→LDT conversion factor',
    'ALL', 'ALL', 'ALL', 'ALL', 0.859, None, None, 'LDT/GT ratio', 'Discrete',
    'European Commission (2025) KOM(2025)0052 SWD — 61 Actual statistics on dismantling vessels',
    'R103',
    'Fishing vessel LDT/GT = 85.9%. 61 Statistical results of a genuinely decapitated fishing vessel: '
    'Total GT=138,757 / Total LDT=119,231 = 0.859.')

add('K', 'LDT_GT_RATIO_CARGO_REF', 'cargo vessels GT→LDT conversion factor (reference comparison)',
    'ALL', 'ALL', 'ALL', 'ALL', 0.287, 0.22, 0.55, 'LDT/GT ratio', 'Triangular',
    'Mikelis (2008) WMU J. Marit. Affairs 7:227-239',
    'R102',
    'Reference: cargo ships LDT/GT varies 22-55%. '
    'transshipment vessel(TP)Introduction cargo ratio 0.287 No, I dont fishing ratio 0.859.')

# ===========================================================================
# FINAL: Build DataFrame & Export
# ===========================================================================

df = pd.DataFrame(rows)

# Ensure column order
columns = [
    'Param_Section', 'Param_Code', 'Param_Name_EN', 'Flag', 'Gear', 'Sector',
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
