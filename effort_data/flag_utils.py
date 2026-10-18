"""
Shared Flag → ISO3 Normalization Module
========================================
Single source of truth for converting raw RFMO flag strings to ISO 3166-1 alpha-3
codes. Used by all effort_data/ extraction scripts and aggregation pipelines.

Covers all 5 RFMOs:
  - CCSBT: 2-letter codes (AU, JP, KR, TW, ZA, etc.)
  - IATTC: 3-letter ISO + full names (JPN, KOR, "United States", etc.)
  - ICCAT: RFMO-specific codes + non-English names + garbled encodings
  - IOTC:  3-letter ISO + full names (LKA, SYC, "Spain (EU)", etc.)
  - WCPFC: 2-letter ISO (JP, TW, KR, US, CN, etc.)

Eliminates: pycountry dependency, 5+ copies of ALLOWED_COUNTRIES, 5+ variants
of get_country_name(), ICCAT's 90-entry flag_mapping, and the downstream
{'Korea':'South Korea', ...} patch in every GHG script.
"""

import pandas as pd

# ============================================================================
# ISO 3166-1 alpha-2 → alpha-3 mapping (for WCPFC, CCSBT, some ICCAT)
# ============================================================================
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

# ============================================================================
# Direct mapping: any raw flag string → ISO alpha-3
# Covers: full English names, RFMO-specific codes, non-English names,
#         2-letter codes, garbled encodings, historical entities
# ============================================================================
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
    "European Union":                  "EU",    # Not a sovereign state, keep as-is for filtering

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
    "Comoros":                         "COM",

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

    # === ICCAT non-English names (from flag_mapping) ===
    "Algerie":                         "DZA",
    "Maroc":                           "MAR",
    "Tunisie":                         "TUN",
    "Türkiye":                         "TUR",
    "T\u7bd3\u9e7frkiye":                       "TUR",   # Garbled encoding variant
    "Côte d'Ivoire":                   "CIV",
    "C?te d'Ivoire":                   "CIV",   # Garbled encoding variant
    "Cabo Verde":                      "CPV",
    "Guinea Ecuatorial":               "GNQ",
    "S Tomé e Príncipe":              "STP",
    "Guinée Rep":                      "GIN",
    "Guin\u7bd3\u5a04e Rep":                    "GIN",   # Garbled encoding variant
    "Curaçao":                         "CUW",
    "Cura?ao":                         "CUW",   # Garbled encoding variant

    # === ICCAT RFMO-specific full names ===
    "Korea Rep":                       "KOR",
    "China PR":                        "CHN",
    "Chinese Taipei":                  "TWN",
    "Russian Federation":              "RUS",
    "Great Britain":                   "GBR",
    "EU-France":                       "FRA",
    "EU-Greece":                       "GRC",
    "EU-Italy":                        "ITA",
    "EU-Malta":                        "MLT",
    "EU-Portugal":                     "PRT",
    "EU-España":                       "ESP",
    "EU-Espa?a":                       "ESP",   # Garbled encoding variant
    "EU-Bulgaria":                     "BGR",
    "EU-Germany":                      "DEU",
    "EU-Sweden":                       "SWE",
    "EU-Cyprus":                       "CYP",
    "EU-Rumania":                      "ROU",
    "EU-Poland":                       "POL",
    "EU-Ireland":                      "IRL",
    "EU-Netherlands":                  "NLD",
    "EU-Estonia":                      "EST",
    "EU-Latvia":                       "LVA",
    "EU-Lithuania":                    "LTU",
    "EU-Denmark":                      "DNK",
    "EU-Croatia":                      "HRV",

    # === ICCAT UK/FR territories ===
    "UK-Sta Helena":                   "SHN",
    "UK-Bermuda":                      "BMU",
    "UK-Turks and Caicos":             "TCA",
    "UK-British Virgin Islands":       "VGB",
    "FR-St Pierre et Miquelon":        "SPM",

    # === ICCAT additional full names ===
    "St Vincent and Grenadines":       "VCT",
    "Sta Lucia":                       "LCA",
    "Saint Kitts and Nevis":           "KNA",
    "Falklands":                       "FLK",
    "Gibraltar":                       "GIB",
    "Faroe Islands":                   "FRO",
    "Cayman Islands":                  "CYM",
    "Dominican Republic":              "DOM",
    "Equatorial Guinea":               "GNQ",
    "Sao Tome and Principe":           "STP",
    "St. Pierre and Miquelon":         "SPM",
    "Turks and Caicos Islands":        "TCA",
    "British Virgin Islands":          "VGB",
    "St. Vincent and the Grenadines":  "VCT",
    "Serbia and Montenegro":           "SCG",

    # === ICCAT non-country / sentinel (map to empty for filtering) ===
    "NEI (MED)":                       "",
    "NEI (Flag related)":              "",
    "NEI (combined)":                  "",
    "NEI (ETRO)":                      "",
    "NEI (BIL)":                       "",
    "NEI (inflated)":                  "",
    "NEI":                             "",
    "Mixed flags (FR+ES)":             "",
    "Mixed flags (EU tropical)":       "",
    "Mixed flags":                     "",
    "ICCAT (RMA)":                     "",
    "ICCAT":                           "",

    # === Historical entities ===
    "USSR":                            "SUN",
    "Soviet Union":                    "SUN",
    "Yugoslavia Fed":                  "YUG",
    "Yugoslavia":                      "YUG",
    "Germany Democratic Rep":          "DDR",
    "East Germany":                    "DDR",

    # === Country name variants (commonly seen across RFMOs) ===
    "South Korea":                     "KOR",
    "Korea, Republic of":              "KOR",
    "Taiwan":                          "TWN",
    "Taiwan, Fishing Entity of":       "TWN",
    "Ivory Coast":                     "CIV",
    "Cape Verde":                      "CPV",
    "Micronesia":                      "FSM",
    "Syria":                           "SYR",
    "Tanzania":                        "TZA",
    "United Kingdom":                  "GBR",
    "United States of America":        "USA",
    "Russia":                          "RUS",
    "Turkey":                          "TUR",
    "Morocco":                         "MAR",
    "Tunisia":                         "TUN",
    "Algeria":                         "DZA",
    "Guinea":                          "GIN",
    "Guinea-Bissau":                   "GNB",
    "Equatorial Guinea":              "GNQ",
    "Curacao":                         "CUW",
    "Albania":                         "ALB",
    "Angola":                          "AGO",
    "Argentina":                       "ARG",
    "Aruba":                           "ABW",
    "Barbados":                        "BRB",
    "Belize":                          "BLZ",
    "Benin":                           "BEN",
    "Brazil":                          "BRA",
    "Cambodia":                        "KHM",
    "Cameroon":                        "CMR",
    "Colombia":                        "COL",
    "Congo":                           "COG",
    "Costa Rica":                      "CRI",
    "Cuba":                            "CUB",
    "Dominica":                        "DMA",
    "Egypt":                           "EGY",
    "El Salvador":                     "SLV",
    "Fiji":                            "FJI",
    "France":                          "FRA",
    "French Polynesia":                "PYF",
    "Gabon":                           "GAB",
    "Gambia":                          "GMB",
    "Georgia":                         "GEO",
    "Ghana":                           "GHA",
    "Greece":                          "GRC",
    "Grenada":                         "GRD",
    "Guatemala":                       "GTM",
    "Guyana":                          "GUY",
    "Honduras":                        "HND",
    "Iceland":                         "ISL",
    "Israel":                          "ISR",
    "Italy":                           "ITA",
    "Jamaica":                         "JAM",
    "Kiribati":                        "KIR",
    "Lebanon":                         "LBN",
    "Libya":                           "LBY",
    "Malta":                           "MLT",
    "Marshall Islands":                "MHL",
    "Mauritania":                      "MRT",
    "Mauritius":                       "MUS",
    "Mexico":                          "MEX",
    "Namibia":                         "NAM",
    "Nauru":                           "NRU",
    "New Caledonia":                   "NCL",
    "Nicaragua":                       "NIC",
    "Nigeria":                         "NGA",
    "Norway":                          "NOR",
    "Palestine":                       "PSE",
    "Papua New Guinea":                "PNG",
    "Peru":                            "PER",
    "Philippines":                     "PHL",
    "Poland":                          "POL",
    "Portugal":                        "PRT",
    "Puerto Rico":                     "PRI",
    "Romania":                         "ROU",
    "Senegal":                         "SEN",
    "Sierra Leone":                    "SLE",
    "Singapore":                       "SGP",
    "Solomon Islands":                 "SLB",
    "Suriname":                        "SUR",
    "Sweden":                          "SWE",
    "Thailand":                        "THA",
    "Togo":                            "TGO",
    "Tonga":                           "TON",
    "Trinidad and Tobago":             "TTO",
    "Ukraine":                         "UKR",
    "Uruguay":                         "URY",
    "Vanuatu":                         "VUT",
    "Venezuela":                       "VEN",
    "St. Helena":                      "SHN",
    "St. Lucia":                       "LCA",
    "St. Kitts and Nevis":             "KNA",
    "St. Vincent and the Grenadines":  "VCT",
    "Falkland Islands":                "FLK",
    "Cook Islands":                    "COK",
    "Maldives":                        "MDV",
    "Sri Lanka":                       "LKA",
    "Seychelles":                      "SYC",
    "Madagascar":                      "MDG",
    "Oman":                            "OMN",

    # === ICCAT FlagChartTo sentinel ===
    "---":                             "",
}

# Populate ISO2 codes from the ISO2_TO_ISO3 table into FLAG_TO_ISO3
for _a2, _a3 in ISO2_TO_ISO3.items():
    if _a2 not in FLAG_TO_ISO3:
        FLAG_TO_ISO3[_a2] = _a3

# ============================================================================
# Whitelist: ISO3 codes for countries retained in the analysis
# Converted from the original 77-name ALLOWED_COUNTRIES list.
# "Korea" and "South Korea" both map to KOR (single entry).
# ============================================================================
ALLOWED_ISO3 = frozenset({
    "ALB", "DZA", "AGO", "AUS", "BLZ", "BRA", "CAN",
    "CPV", "CHL", "CHN", "COL", "COK", "CRI",
    "HRV", "CYP", "ECU", "EGY", "SLV", "FJI", "FRA",
    "PYF", "GHA", "GRC", "GRD", "GTM", "GIN",
    "IND", "IDN", "IRN", "ITA", "CIV", "JPN", "KEN",
    "KIR", "KOR", "LBR", "LBY", "LTU", "MDG", "MYS",
    "MDV", "MLT", "MHL", "MUS", "MEX", "FSM",
    "MAR", "NAM", "NRU", "NZL", "NIC", "NOR", "OMN",
    "PAN", "PNG", "PER", "PHL", "PRT", "SEN",
    "SYC", "SGP", "ZAF", "ESP", "LKA",
    "SUR", "SYR", "TWN", "TZA", "THA", "TON",
    "TTO", "TUN", "TUR", "USA", "VUT", "VEN",
    # 2026-09 additions: countries present in the vessel registry but
    # missing from the original 77-name list
    "SLB", "TUV", "NCL", "GBR", "CUW", "BHS", "RUS",
})


# ============================================================================
# Core functions
# ============================================================================

def normalize_flag_to_iso3(raw_flag: str) -> str:
    """
    Normalize a raw flag string to ISO 3166-1 alpha-3 country code.

    Handles: full English names (CCSBT, IATTC, IOTC), ICCAT RFMO codes
    (EU-XXX -> XXX, TAI -> TWN, etc.), ICCAT non-English names (Algerie,
    Maroc, etc.), WCPFC/CCSBT 2-letter codes, standard 3-letter codes,
    garbled encodings, and historical entities.

    Returns "" for unrecognized or non-country entries (NEI, Mixed flags, etc.).
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
    # Try splitting EU- / UK- / FR- prefix: e.g. "EU-XXX" -> XXX
    for prefix in ("EU-", "UK-", "FR-"):
        if s_upper.startswith(prefix):
            sub = s_upper[len(prefix):]
            if sub in FLAG_TO_ISO3:
                return FLAG_TO_ISO3[sub]
            if sub in ISO2_TO_ISO3:
                return ISO2_TO_ISO3[sub]
            # sub might already be ISO3
            if len(sub) == 3 and sub.isalpha():
                return sub
    # EU/UK/FR ligature without hyphen: e.g. "EUESP" -> ESP, "EUFRA" -> FRA
    # French overseas fleets (Mayotte / Reunion) are attributed to France
    for prefix in ("EU", "UK", "FR"):
        if s_upper.startswith(prefix) and len(s_upper) == 5:
            sub = s_upper[len(prefix):]
            if sub in ("MYT", "REU"):
                return "FRA"
            if sub in FLAG_TO_ISO3:
                return FLAG_TO_ISO3[sub]
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


def is_allowed_iso3(iso3_code: str) -> bool:
    """
    Check if an ISO3 code is in the analysis whitelist.
    Simple exact-match lookup — no fuzzy matching needed since ISO3 codes
    are unambiguous.
    """
    if not iso3_code or pd.isna(iso3_code):
        return False
    return str(iso3_code).strip().upper() in ALLOWED_ISO3
