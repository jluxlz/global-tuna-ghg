#!/usr/bin/env python
"""
Build fuel price matrix with regional WEO mapping + annual interpolation.
Output: Scenario_Fuel_Price_Matrix.xlsx
"""
import pandas as pd, numpy as np, os

DIR = os.path.dirname(os.path.abspath(__file__))
xls_raw = pd.read_excel(os.path.join(DIR, "Scenario_Fuel_Parameters.xlsx"),
                    sheet_name=None, engine="openpyxl", header=None)

# ---- 0. Parse all sheets ----
# Fuel_Parameters
fp_raw = xls_raw["Fuel_Parameters"]
fp_cols = [str(v).replace('\n',' ').strip() for v in fp_raw.iloc[4].values]
fp = fp_raw.iloc[5:].copy(); fp.columns = fp_cols; fp = fp.reset_index(drop=True)
col_map = {
    "Seq": "Seq", "Fuel Type": "Fuel_Type",
    "LHV (MJ/g)": "LHV_MJ_g", "WtT GHG (gCO2eq/MJ)": "WtT_GHG",
    "Cf_CO2": "CfCO2", "Cf_CH4": "CfCH4", "Cf_N2O": "CfN2O",
    "Current Min": "Price_Cur_Min", "Current Max": "Price_Cur_Max",
    "2050 Min": "Price_2050_Min", "2050 Max": "Price_2050_Max",
}
fp = fp.rename(columns={k:v for k,v in col_map.items() if k in fp.columns})
for c in ["Seq","Price_Cur_Min","Price_Cur_Max","Price_2050_Min","Price_2050_Max","LHV_MJ_g","WtT_GHG","CfCO2","CfCH4","CfN2O"]:
    if c in fp.columns: fp[c] = pd.to_numeric(fp[c], errors="coerce")

# WEO_Fossil_Prices
wfp = xls_raw["WEO_Fossil_Prices"].iloc[4:].copy()
wfp.columns = ["Scenario","Fuel_Region","Unit","2023","2030","2040","2050"]
for c in ["2023","2030","2040","2050"]: wfp[c] = pd.to_numeric(wfp[c], errors="coerce")

# WEO_Carbon_Prices
wcp = xls_raw["WEO_Carbon_Prices"].iloc[4:].copy()
wcp.columns = ["Scenario","WEO_Region","2030","2035","2040","2050"]
for c in ["2030","2035","2040","2050"]: wcp[c] = pd.to_numeric(wcp[c], errors="coerce")

# ---- 1. Regional mapping: all 98 vessel flags → WEO reference regions ----
# Each flag maps to: (crude_proxy, ng_region, carbon_region)
# WEO reference regions available:
#   Crude oil: global only
#   Natural gas: United States, European Union, China, Japan
#   Carbon (STEPS): Canada, Chile & Colombia, China, European Union, Korea
#   Carbon (APS/NZE): Advanced economies*, Selected EMDE**, Other EMDE

def _build_flag_map():
    """Build comprehensive Flag→WEO mapping for all 98 vessel flags."""
    m = {}
    # ── NG region assignment ──
    # EU + EFTA + UK
    eu = ["AUT","BEL","BGR","HRV","CYP","CZE","DNK","EST","FIN","FRA","DEU",
          "GRC","HUN","IRL","ITA","LVA","LTU","LUX","MLT","NLD","POL","PRT",
          "ROU","SVK","SVN","ESP","SWE","GBR","NOR","ISL","CHE","FRO","GRL"]
    for f in eu: m[f] = {"ng":"European Union","carbon_steps":"European Union","carbon_aps_nze":"Advanced"}
    # North America
    for f in ["USA","CAN","MEX"]: m[f] = {"ng":"United States","carbon_steps":"Canada","carbon_aps_nze":"Advanced"}
    # Japan + Korea + Taiwan (developed East Asia)
    for f in ["JPN","KOR","TWN"]: m[f] = {"ng":"Japan","carbon_steps":"Korea" if f=="KOR" else "Advanced","carbon_aps_nze":"Advanced"}
    # Australia + New Zealand
    for f in ["AUS","NZL"]: m[f] = {"ng":"United States","carbon_steps":"Canada","carbon_aps_nze":"Advanced"}
    # China → proxy for developing Asia
    for f in ["CHN","HKG","MAC"]: m[f] = {"ng":"China","carbon_steps":"China","carbon_aps_nze":"Selected_EMDE"}
    # Developing Asia (proxy: China for prices, China for carbon)
    dev_asia = ["IDN","PHL","VNM","THA","MYS","SGP","MMR","KHM","LAO","BRN",
                "IND","LKA","BGD","PAK","MDV","NPL","BTN","MNG","PRK"]
    for f in dev_asia: m[f] = {"ng":"China","carbon_steps":"China","carbon_aps_nze":"Selected_EMDE"}
    # Developing Africa (proxy: China/EMDE)
    dev_africa = ["MAR","TUN","DZA","LBY","EGY","MRT","SEN","GMB","GNB","GIN",
                  "SLE","LBR","CIV","GHA","TGO","BEN","NGA","CMR","GAB","COG",
                  "COD","AGO","NAM","ZAF","MOZ","TZA","KEN","SOM","ETH","ERI",
                  "DJI","SDN","SSD","UGA","RWA","BDI","SYC","MUS","COM","MDG",
                  "CPV","STP","GNQ"]
    for f in dev_africa: m[f] = {"ng":"European Union","carbon_steps":"ChileColombia","carbon_aps_nze":"Other_EMDE"}
    # Developing Americas (proxy: Chile & Colombia)
    dev_americas = ["ECU","PAN","CRI","NIC","GTM","HND","SLV","COL","PER","CHL",
                    "VEN","GUY","SUR","BLZ","JAM","DOM","HTI","CUB","BHS","BRB",
                    "TTO","LCA","VCT","GRD","ATG","KNA"]
    for f in dev_americas: m[f] = {"ng":"United States","carbon_steps":"ChileColombia","carbon_aps_nze":"Other_EMDE"}
    # Pacific Islands (proxy: EMDE)
    pacific = ["FJI","PNG","SLB","VUT","WSM","TON","KIR","FSM","MHL","PLW",
               "NRU","TUV","COK","NIU","PYF","NCL"]
    for f in pacific: m[f] = {"ng":"Japan","carbon_steps":"ChileColombia","carbon_aps_nze":"Other_EMDE"}
    # Middle East
    mideast = ["TUR","IRN","IRQ","SAU","ARE","QAT","KWT","BHR","OMN","YEM",
               "JOR","LBN","SYR","ISR","PSE","AZE","ARM","GEO","KAZ","UZB","TKM","KGZ","TJK"]
    for f in mideast: m[f] = {"ng":"European Union","carbon_steps":"ChileColombia","carbon_aps_nze":"Selected_EMDE"}
    # Russia
    for f in ["RUS"]: m[f] = {"ng":"European Union","carbon_steps":"Canada","carbon_aps_nze":"Advanced"}
    # Remaining uncategorized → default to EU/Advanced
    return m

FLAG_REGION_MAP = _build_flag_map()
print(f"  Mapped {len(FLAG_REGION_MAP)} flags to WEO regions")

# WEO reference regions for output
WEO_REF_REGIONS = {
    "EU":     {"ng": "European Union", "carbon_steps": "European Union", "carbon_aps_nze": "Advanced"},
    "US":     {"ng": "United States",  "carbon_steps": "Canada",          "carbon_aps_nze": "Advanced"},
    "China":  {"ng": "China",          "carbon_steps": "China",           "carbon_aps_nze": "Selected_EMDE"},
    "Japan":  {"ng": "Japan",          "carbon_steps": "Korea",           "carbon_aps_nze": "Advanced"},
    "DevAsia":{"ng": "China",          "carbon_steps": "China",           "carbon_aps_nze": "Selected_EMDE"},
    "DevAfr": {"ng": "European Union", "carbon_steps": "ChileColombia",  "carbon_aps_nze": "Other_EMDE"},
    "DevAmer":{"ng": "United States",  "carbon_steps": "ChileColombia",  "carbon_aps_nze": "Other_EMDE"},
    "Pacific":{"ng": "Japan",          "carbon_steps": "ChileColombia",  "carbon_aps_nze": "Other_EMDE"},
}

# WEO benchmark years
WEO_YEARS = [2023, 2030, 2035, 2040, 2050]

def interp_annual(data_dict, year):
    """Linear interpolation for any year between WEO benchmarks."""
    yrs = sorted(data_dict.keys())
    vals = [data_dict[y] for y in yrs]
    return float(np.interp(year, yrs, vals))

# ---- 2. Build WEO price indices by commodity+scenario (annual) ----
def build_weo_index(wfp_df, commodity, scen):
    """Return dict {year: price} for a commodity+scenario, annually interpolated."""
    sub = wfp_df[(wfp_df["Fuel_Region"]==commodity)&(wfp_df["Scenario"]==scen)]
    if len(sub)==0: return {}
    raw = {int(yr): sub[str(yr)].values[0] for yr in [2023,2030,2040,2050] if str(yr) in sub.columns}
    # Interpolate missing years
    result = {}
    for y in range(2023, 2051):
        result[y] = interp_annual(raw, y)
    return result

# Pre-build crude oil index (global, not regional)
crude_idx = {scen: build_weo_index(wfp, "Crude oil (IEA)", scen) for scen in ["STEPS","APS","NZE"]}

# Pre-build NG indices by region+scenario
ng_regions = ["United States", "European Union", "China", "Japan"]
ng_idx = {}
for scen in ["STEPS","APS","NZE"]:
    for reg in ng_regions:
        ng_idx[(scen, reg)] = build_weo_index(wfp, f"Natural gas -- {reg}", scen)

# ---- 3. Build annual carbon price lookup ----
def build_carbon_lookup(wcp_df, region, scen):
    """Return dict {year: carbon_price} for region+scenario, annually interpolated."""
    sub = wcp_df[(wcp_df["WEO_Region"]==region)&(wcp_df["Scenario"]==scen)]
    if len(sub)==0:
        # Try cross-scenario: use STEPS data for STEPS, APS for APS, NZE for NZE
        # For APS/NZE "Advanced economies"
        sub2 = wcp_df[(wcp_df["WEO_Region"].str.contains("Advanced economies",na=False))&(wcp_df["Scenario"]==scen)]
        if len(sub2)==0:
            sub2 = wcp_df[(wcp_df["WEO_Region"]=="European Union")&(wcp_df["Scenario"]==scen)]
        sub = sub2
    if len(sub)==0: return {y:0.0 for y in range(2023,2051)}
    raw = {}
    for yr in [2030,2035,2040,2050]:
        if str(yr) in sub.columns:
            raw[yr] = pd.to_numeric(sub[str(yr)].values[0], errors="coerce")
    raw[2023] = 0.0
    return {y: interp_annual(raw, y) for y in range(2023, 2051)}

# Carbon lookup by region
carbon_regions = [
    ("STEPS", "European Union"),
    ("STEPS", "China"),
    ("STEPS", "Korea"),
    ("STEPS", "Canada"),
    ("STEPS", "Chile & Colombia"),
    ("APS", "Advanced economies with net-zero pledges*"),
    ("APS", "Selected EMDE with net-zero pledges**"),
    ("APS", "Other emerging market & developing economies"),
    ("NZE", "Advanced economies with net-zero pledges*"),
    ("NZE", "Selected EMDE with net-zero pledges**"),
    ("NZE", "Selected EMDE without net-zero pledges"),
    ("NZE", "Other emerging market & developing economies"),
]
carbon_lu = {}
for scen, reg in carbon_regions:
    carbon_lu[(scen, reg)] = build_carbon_lookup(wcp, reg, scen)

# ---- 4. Generate price matrix (annual, by region) ----
class_a_crude = [1,2,3,4,5,6,11,21]   # oil-based → global crude index
class_a_ng    = [31]                     # fossil LNG → regional NG index

ALL_YEARS = list(range(2023, 2051))
SCENARIOS = ["STEPS", "APS", "NZE"]

results = []

for _, row in fp.iterrows():
    seq = row["Seq"]
    cur_min = row["Price_Cur_Min"]
    cur_max = row["Price_Cur_Max"]
    if pd.isna(cur_min) and pd.isna(cur_max): continue

    if seq in class_a_crude:
        # Crude oil: global price, but carbon tax varies by region
        for scen in SCENARIOS:
            base_2023 = crude_idx[scen][2023]
            for yr in ALL_YEARS:
                factor = crude_idx[scen][yr] / base_2023 if base_2023 > 0 else 1.0
                p_min = cur_min * factor if pd.notna(cur_min) else None
                p_max = cur_max * factor if pd.notna(cur_max) else None
                # Output by WEO reference region (different carbon tax per region)
                for ref_name in WEO_REF_REGIONS:
                    results.append({"Seq":seq,"Fuel":row["Fuel_Type"],"Scenario":scen,"Year":yr,
                        "WEO_Region":ref_name,"Price_Min":p_min,"Price_Max":p_max,"Method":"Crude"})

    elif seq in class_a_ng:
        # LNG: regional NG price, regional carbon tax
        for scen in SCENARIOS:
            for ref_name, ref_cfg in WEO_REF_REGIONS.items():
                ng_reg = ref_cfg["ng"]
                base_2023 = ng_idx.get((scen, ng_reg), {}).get(2023, 1.0)
                for yr in ALL_YEARS:
                    ng_price = ng_idx.get((scen, ng_reg), {}).get(yr, 1.0)
                    factor = ng_price / base_2023 if base_2023 > 0 else 1.0
                    p_min = cur_min * factor if pd.notna(cur_min) else None
                    p_max = cur_max * factor if pd.notna(cur_max) else None
                    results.append({"Seq":seq,"Fuel":row["Fuel_Type"],"Scenario":scen,"Year":yr,
                        "WEO_Region":ref_name,"Price_Min":p_min,"Price_Max":p_max,"Method":f"LNG_{ng_reg}"})

    else:
        # Class B: green/bio — production cost path (no fossil price dependency)
        p_min_2050 = row.get("Price_2050_Min")
        p_max_2050 = row.get("Price_2050_Max")
        if pd.notna(p_min_2050):
            cagr_min = (p_min_2050/cur_min)**(1/27)-1 if cur_min>0 else 0
            cagr_max = (p_max_2050/cur_max)**(1/27)-1 if cur_max>0 else 0
        else:
            p_min_2050 = cur_min*0.85 if pd.notna(cur_min) else None
            p_max_2050 = cur_max*0.85 if pd.notna(cur_max) else None
            cagr_min = 0.85**(1/27)-1 if pd.notna(cur_min) else 0
            cagr_max = 0.85**(1/27)-1 if pd.notna(cur_max) else 0

        for scen in SCENARIOS:
            for yr in ALL_YEARS:
                t = yr-2023
                if yr==2023: mult=1.0
                else:
                    c_aps  = carbon_lu.get(("APS","Advanced economies with net-zero pledges*"),{}).get(yr,0)
                    c_scen = carbon_lu.get((scen,"Advanced economies with net-zero pledges*"),{}).get(yr,0)
                    mult = c_scen/c_aps if c_aps>0 else 1.0
                p_min = cur_min*(1+cagr_min)**t*mult if pd.notna(cur_min) else None
                p_max = cur_max*(1+cagr_max)**t*mult if pd.notna(cur_max) else None
                # Green fuels: same production cost globally (no fossil regional variance)
                results.append({"Seq":seq,"Fuel":row["Fuel_Type"],"Scenario":scen,"Year":yr,
                    "WEO_Region":"Global","Price_Min":p_min,"Price_Max":p_max,"Method":f"ClassB"})

# ---- 5. Effective cost with region-specific carbon tax ----
df_r = pd.DataFrame(results)

# Map WEO reference region → carbon lookup key
def _get_carbon_price(woe_region, scen, yr):
    """Look up carbon price for a WEO reference region."""
    if woe_region == "Global":  # green fuels: default to Advanced economies
        key = ("APS", "Advanced economies with net-zero pledges*") if scen=="APS" else \
              ("NZE", "Advanced economies with net-zero pledges*") if scen=="NZE" else \
              ("STEPS", "European Union")
        return carbon_lu.get(key, {}).get(yr, 0)
    cfg = WEO_REF_REGIONS.get(woe_region, {})
    if scen == "STEPS":
        reg = cfg.get("carbon_steps", "European Union")
    else:
        tag = cfg.get("carbon_aps_nze", "Advanced")
        reg = f"Advanced economies with net-zero pledges*" if tag=="Advanced" else \
              f"Selected EMDE with net-zero pledges**" if tag=="Selected_EMDE" else \
              "Other emerging market & developing economies"
    key = (scen, reg)
    # Try exact match, then fallback
    cp = carbon_lu.get(key, {}).get(yr)
    if cp is None:
        # Fallback: use EU/Advanced
        fb = ("STEPS","European Union") if scen=="STEPS" else (scen,"Advanced economies with net-zero pledges*")
        cp = carbon_lu.get(fb, {}).get(yr, 0)
    return cp if cp is not None else 0

df_r["Carbon_USDtCO2"] = df_r.apply(
    lambda r: _get_carbon_price(r["WEO_Region"], r["Scenario"], r["Year"]), axis=1)

# Total EF
ef_cols = ["Seq"]+[c for c in ["WtT_GHG","CfCO2","CfCH4","CfN2O"] if c in fp.columns]
fp_lite = fp[ef_cols].copy()
fp_lite = fp_lite.rename(columns={"WtT_GHG":"WtT_GHG_gCO2eq_MJ","CfCO2":"CfCO2_g_g"})
fp_lite["Total_EF_gCO2_MJ"] = (fp_lite["WtT_GHG_gCO2eq_MJ"].fillna(0) +
    fp_lite["CfCO2_g_g"].fillna(0)/fp["LHV_MJ_g"].fillna(1)*1e3)
fp_lite["Total_EF_gCO2_MJ"] = np.where(fp_lite["CfCO2_g_g"].fillna(1)==0, 0, fp_lite["Total_EF_gCO2_MJ"])
df_r = df_r.merge(fp_lite[["Seq","Total_EF_gCO2_MJ"]], on="Seq", how="left")

df_r["Carbon_Tax_USDMWh"] = (df_r["Total_EF_gCO2_MJ"].fillna(0)*3.6*df_r["Carbon_USDtCO2"].fillna(0)/1e6)
df_r["Eff_Min"] = df_r["Price_Min"].fillna(0)+df_r["Carbon_Tax_USDMWh"]
df_r["Eff_Max"] = df_r["Price_Max"].fillna(0)+df_r["Carbon_Tax_USDMWh"]

# ---- 6. Output ----
out_path = os.path.join(DIR, "Scenario_Fuel_Price_Matrix.xlsx")
with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
    # Pivoted matrix
    pivot = df_r.pivot_table(index=["Seq","Fuel","Scenario","WEO_Region"], columns="Year",
        values=["Price_Min","Price_Max","Eff_Min","Eff_Max"], aggfunc="first")
    pivot.columns = [f"{v}_{y}" for v,y in pivot.columns]
    pivot = pivot.reset_index().sort_values(["Seq","Scenario","WEO_Region"])
    pivot.to_excel(writer, sheet_name="Price_Matrix", index=False)

    # Long format for LCA
    df_r.to_excel(writer, sheet_name="Price_Long", index=False)

    # Flag → Region mapping
    frm_rows = []
    for flag, cfg in FLAG_REGION_MAP.items():
        frm_rows.append({"Flag":flag,"NG_Region":cfg["ng"],
            "Carbon_STEPS":cfg["carbon_steps"],"Carbon_APS_NZE":cfg["carbon_aps_nze"]})
    pd.DataFrame(frm_rows).to_excel(writer, sheet_name="Flag_Region_Map", index=False)

    # Regional carbon price reference
    cp_rows = []
    for (scen,reg),lu in carbon_lu.items():
        for yr,cp in lu.items():
            if yr in [2023,2030,2035,2040,2050]:
                cp_rows.append({"Scenario":scen,"WEO_Region":reg,"Year":yr,"Carbon_USDtCO2":round(cp,1)})
    pd.DataFrame(cp_rows).to_excel(writer, sheet_name="Carbon_Reference", index=False)

print(f"Done: {out_path}")
print(f"Rows: {len(df_r):,} (annual 2023-2050, with regional mapping)")
print(f"NG regions: {ng_regions}")
print(f"Carbon regions: {len(carbon_lu)} lookup tables")
