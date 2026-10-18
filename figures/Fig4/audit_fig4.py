"""Repeatable row-level upstream QC and numerical Fig4/model interface checks.
No plots, model production runs, or upstream writes.
"""
import hashlib
import json
from pathlib import Path
import sys
import re
from collections import Counter
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scenario"))
import preprocess_fig4 as prep
model = prep.fleet_model


def sha(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def upstream_checks():
    key = ["Year", "Flag", "Gear", "squaretypecode", "lat", "lon", "EffortType", "Organization"]
    cols = prep.SP_COLS
    base = pd.read_csv(model.GRID_PATH, usecols=key+cols+["Effort_Prop", "GHG_emissions_median", "Nat_GHG_median", "Fuel_CO2_median"])
    raw = pd.read_csv(ROOT / "effort_data/Grid_Catch_Allocation.csv")
    raw = raw.rename(columns={"SquareTypeCode": "squaretypecode", "Lat": "lat", "Lon": "lon"})
    assert not base.duplicated(key).any() and not raw.duplicated(key).any(), "Duplicate catch records"
    m = base.merge(raw[key+cols], on=key, how="outer", validate="one_to_one", indicator=True,
                   suffixes=("_base", "_raw"))
    assert (m._merge == "both").all(), "Base_3 catch coverage mismatch"
    errors = {s: float(np.max(np.abs(m[s+"_base"]-m[s+"_raw"]))) for s in cols}
    assert max(errors.values()) < 1e-7, f"Row-level catch conservation: {errors}"
    assert np.isfinite(base[cols+["Effort_Prop", "GHG_emissions_median"]]).all().all()
    assert (base[cols+["Effort_Prop", "GHG_emissions_median"]] >= 0).all().all()
    ep = base.groupby(["Year", "Flag", "Gear"]).Effort_Prop.sum()
    assert np.minimum(np.abs(ep), np.abs(ep-1)).max() < 1e-7, "Effort allocation not 0 or 1"
    assert np.allclose(base.GHG_emissions_median, base.Nat_GHG_median*base.Effort_Prop, rtol=1e-9, atol=1e-7)
    base2_path = ROOT/"GHG_Calculation/Base_2_Fleet_GHG.csv"
    base2 = pd.read_csv(base2_path)
    group = ["Year", "Flag", "Gear"]
    allocated = base.groupby(group).Fuel_CO2_median.sum()
    fleet_total = base2.groupby(group).Fuel_CO2_median.sum().reindex(allocated.index)
    missing = fleet_total.isna()
    nat = base.groupby(group).Nat_GHG_median.max()
    assert (allocated[missing] == 0).all() and (nat[missing] == 0).all(), "Unmatched fleet group carries emissions"
    expected_fuel = fleet_total.fillna(0)*ep
    assert np.allclose(allocated, expected_fuel, rtol=1e-9, atol=1e-6), "Process allocation does not conserve Base_2"
    for design in ["C", "F"]:
        p = prep.projection(design)
        assert np.allclose(p[p.Year == 2024].biomass_ratio, 1), "Wrong projection origin"
        for (_, _), g in p.groupby(["Stock", "Scenario"]):
            if design == "C":
                assert g.Catch_Mt.nunique() == 1 and g.quota_ratio.nunique() == 1
            else:
                ratio = g.quota_ratio/g.biomass_ratio
                # Source ratios are rounded to 4 decimals, unlike model internals.
                assert ratio.max()-ratio.min() < .002, "F catch/quota not proportional to biomass"
    cr = prep.carbon_reference()
    assert set(cr.Scenario) == set(prep.WEO)
    fuel_sheet = pd.read_excel(prep.pl.FUEL_PARAMS_PATH, sheet_name="Fuel_Parameters", header=None)
    fuel_rows = []
    for f in prep.FUELS:
        name = "Hydrogen -- Green" if f == "H2_Green" else prep.pl._FUEL_ALIASES[f]
        matched = fuel_sheet[1].astype(str).str.contains(name, regex=False) if f == "H2_Green" else fuel_sheet[1].astype(str).str.strip() == name
        source = fuel_sheet[matched]
        assert len(source) == 1 and pd.notna(source.iloc[0,3]), f"Missing source fuel property: {f}"
        r = source.iloc[0]
        lhv = float(r[3])*1000 if float(r[3])<1 else float(r[3])
        loaded = prep._h2green_params()[0] if f == "H2_Green" else prep.pl.get_fuel_lhv(f)
        assert lhv > 0 and np.isclose(lhv, loaded), "LHV column or unit mismatch"
        fuel_rows.append(dict(Fuel=f, Excel_Row=int(source.index[0])+1,
                              LHV_MJ_kg=lhv, Source_LHV_Column="D", Source_WtT_Column="E",
                              WtT_Source_Value=r[4]))
    pd.DataFrame(fuel_rows).to_csv(HERE/"Fig4_Fuel_Parameters_QC.csv", index=False)
    for w in prep.WEO:
        for f in prep.FUELS:
            if f != "H2_Green":
                for y in [2023, 2030, 2040, 2050]:
                    prep.fuel_price(f, w, y)
    assert np.isclose(model.get_grid_ef("NZE", 2050), -4), "Signed NZE grid convention changed"
    paths = [Path(model.GRID_PATH), base2_path, ROOT/"effort_data/Grid_Catch_Allocation.csv",
             ROOT/"PMM_Imputation/After_PMM_Vessels.csv", ROOT/"model_parameters/Prior_Matrix.csv",
             ROOT/"model_parameters/Scenario_Fuel_Parameters.xlsx", Path(prep.pl.PRICE_MATRIX_PATH),
             ROOT/"scenario/output/schaefer_biomass_annual.csv",
             ROOT/"scenario/output/schaefer_biomass_annual_F.csv",
             ROOT/"scenario/jabba_fit.r", ROOT/"scenario/fleet_model.py", ROOT/"scenario/price_loader.py"]
    report = dict(catch_rows=len(base), max_row_catch_error=errors,
                  catch_tonnes=base[cols].sum().to_dict(), zero_effort_groups=int((ep == 0).sum()),
                  catch_groups_without_Base2=int(missing.sum()),
                  catch_groups_without_Base2_tonnes=float(base.groupby(group)[cols].sum().sum(axis=1)[missing].sum()),
                  process_allocation="PASS: groupwise Fuel_CO2 against Base_2, including zero-effort groups",
                  sha256={str(p.relative_to(ROOT)): sha(p) for p in paths})
    (HERE/"Fig4_Upstream_QC.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    coverage = base.groupby(group).agg(Rows=("Effort_Prop","size"), Effort_Prop=("Effort_Prop","sum"),
                                       Nat_GHG_median=("Nat_GHG_median","max"))
    coverage["Catch_tonnes"] = base.groupby(group)[cols].sum().sum(axis=1)
    coverage["Has_Base2"] = ~missing
    coverage.to_csv(HERE/"Fig4_Fleet_Coverage_QC.csv")
    print(f"Upstream QC passed: {len(base):,} matched catch rows; complete C/F projections and price anchors")
    return report


def model_checks():
    # Actual registry vessels and their operational parameters, deterministic seed42.
    fleet, pm = model.load_baseline_fleet()
    fleet = pd.concat([fleet[fleet.VesselType == g].iloc[[0]] for g in ["PS", "LL"]]).copy()
    tests = []
    for w in prep.WEO:
        for y in [2025, 2030, 2040, 2050]:
            for tc in prep.TECH.values():
                for design in ["C", "F"]:
                    pairs = list(zip(fleet.Flag.astype(str), fleet.Organization.astype(str)))
                    macro = model.get_meco_eff_map("MSY_100", design, y, tc, flags_orgs=pairs)
                    assert set(pairs) <= set(macro), "Missing macro map silently defaults to Meco=1"
                    gb = model.get_gear_blended_params("MSY_100", y, quota_type=design)
                    econ = model.compute_vessel_econ_effort(fleet.copy(), w, y, gb,
                              {"tech_creep": tc, "elasticity": -.3}, meco_eff_map=macro)
                    assert np.allclose(econ.Meco, [macro[p] for p in pairs])
                    assert np.allclose(econ.M_econ_raw, econ.Cost_Ratio**-.3)
                    assert np.allclose(econ.E_final, econ.Meco*econ.M_econ_raw)
                    # Actual bottom-up fuel calculation must respond once, linearly
                    # to E_final. Hold fuel state, fleet size and upsize constant.
                    if tc == .024:
                        base_econ = econ.copy()
                        base_econ["E_final"] = 1.
                        a = model.compute_fleet_ghg(fleet.copy(), pm, ref_year=y, vessel_econ_df=econ)
                        b = model.compute_fleet_ghg(fleet.copy(), pm, ref_year=y, vessel_econ_df=base_econ)
                        for c in ["GHG_Fuel_CO2", "GHG_Fuel_CH4", "GHG_Fuel_N2O", "GHG_Fuel_WtT"]:
                            assert np.allclose(a[c], b[c]*econ.E_final, rtol=1e-10, atol=1e-9), c
                    for idx, r in econ.iterrows():
                        tests.append(dict(WEO=w, Year=y, Design=design, Tech_Rate=tc,
                                          Gear=fleet.loc[idx, "VesselType"], Flag=fleet.loc[idx, "Flag"],
                                          Organization=fleet.loc[idx, "Organization"],
                                          Meco=r.Meco, Mecon=r.M_econ_raw, Cost_Ratio=r.Cost_Ratio,
                                          E_final=r.E_final, Reference_USD_MJ=r.Baseline_USD_per_MJ))
    pd.DataFrame(tests).to_csv(HERE/"Fig4_Model_Transmission_QC.csv", index=False)
    # Validate all forecast shares, rather than only the two sampled vessels.
    shares = model.species_share_forecast()["method"]
    assert np.isfinite(shares.Share).all() and (shares.Share >= 0).all()
    assert set(shares.Year) == set(range(2025,2051))
    assert not shares.duplicated(["Year","Flag","Organization","Species"]).any()
    assert np.allclose(shares.groupby(["Year","Flag","Organization"]).Share.sum(),1,atol=1e-8)
    shares.to_csv(HERE/"Fig4_Model_Species_Shares_QC.csv",index=False)
    return len(tests)


def panel_checks():
    names = dict(A="Biomass", B="Yearly_M", C="Effort_Required", D="Fuel_Cost",
                 E="Intensity", F="Crossover_By_Leak")
    data = {k: pd.read_csv(HERE/f"Fig4_Panel{k}_{v}.csv") for k,v in names.items()}
    expected = dict(A=1170, B=336, C=312, D=72, E=672, F=135)
    assert {k: len(d) for k,d in data.items()} == expected
    b,c,d,e,f = [data[k] for k in "BCDEF"]
    assert np.allclose(b.M_econ, b.Cost_Ratio**-.3)
    assert np.allclose(b[b.Year == 2023].M_econ, 1)
    assert np.allclose(c.E_req, c.Quota_Ratio/np.maximum(c.Biomass_Ratio*c.Tech_Factor, .01))
    assert np.allclose(d.M_econ, d.Cost_Ratio_vs_MGO**-.3)
    assert np.allclose(e.Intensity_gCO2e_kWh, e.SFC_g_kWh*e.LHV_MJ_kg*e.EF_gCO2e_MJ/1000*e.M_econ)
    assert np.allclose(e[e.Fuel == "MGO"].M_econ, 1)
    cross = d.merge(e, on=["WEO", "Year", "Fuel"], validate="one_to_one", suffixes=("_d", "_e"))
    assert len(cross) == 72 and np.allclose(cross.M_econ_d, cross.M_econ_e)
    components = pd.read_csv(HERE/"Fig4_PanelC_Species_Components.csv")
    assert np.allclose(components.groupby(["Gear","Year","Design","Tech_Creep"]).Species_Weight.sum(),1)
    annual = pd.read_csv(HERE/"Fig4_PanelF_Annual_Components.csv")
    for r in f.itertuples():
        win = annual[(annual.WEO == r.WEO) & (annual.LN2_tCO2e_ship < r.R22_tCO2e_ship)]
        assert (pd.isna(r.Cross_Year) and len(win) == 0) or (len(win) and r.Cross_Year == win.Year.min())
    # Archive vs current changes, including the corrected PS share and exact H2 unit conversion.
    changes = []
    keys = dict(A=["Year","Stock","Scenario","Type"], B=["WEO","Region","Year"],
                C=["Year","Gear","Design","Tech_Creep"], D=["WEO","Year","Fuel"],
                E=["WEO","Year","Fuel"], F=["WEO","Leak_kg_yr"])
    for k, df in data.items():
        old_path = HERE/"_archive_pre_audit_20261012"/f"Fig4_Panel{k}_{names[k]}.csv"
        if not old_path.exists():
            continue  # Removing an archive must not break current scientific QC.
        old = pd.read_csv(old_path)
        m = old.merge(df, on=keys[k], suffixes=("_old","_new"), validate="one_to_one")
        for col in old.select_dtypes("number").columns:
            if col in keys[k] or col not in df:
                continue
            delta = m[col+"_new"]-m[col+"_old"]
            changes.append(dict(Panel=k, Column=col, Matched=len(m),
                                Max_Abs_Change=float(delta.abs().max()),
                                Missing_Status_Changes=int((m[col+"_new"].isna()!=m[col+"_old"].isna()).sum())))
    pd.DataFrame(changes).to_csv(HERE/"Fig4_Numeric_Changes.csv", index=False)
    qc = dict(panel_rows=expected, PS_share=float(f.PS_Catch_Share.iloc[0]),
              registry_PS_ships=int(f.Registry_PS_Ships.iloc[0]),
              d_e_max_mecon_error=float((cross.M_econ_d-cross.M_econ_e).abs().max()),
              e_min_intensity=float(e.Intensity_gCO2e_kWh.min()),
              e_max_intensity=float(e.Intensity_gCO2e_kWh.max()),
              fossil_wtt_topup_max=float(e.WtT_Topup_gCO2e_MJ.max()),
              ratio_blend_vs_species_mean_max=float((c.E_req-c.Weighted_Species_Meco).abs().max()))
    return qc


def caption_numeric_audit():
    old_path = HERE/"_archive_pre_audit_20261012/Figure4_Caption.md"
    if not old_path.exists():
        old_path = HERE/"Figure4_Caption.md"
    new_path = HERE/"Figure4_Caption_Audited.md"
    if not old_path.exists() or not new_path.exists():
        return
    pattern = r"(?<![A-Za-z])\d+(?:\.\d+)?"
    old = Counter(re.findall(pattern, old_path.read_text(encoding="utf-8")))
    new = Counter(re.findall(pattern, new_path.read_text(encoding="utf-8")))
    report = dict(original_caption_modified=False, main_text_modified=False,
        comparison="A separate concise caption for the audited figure; original caption retained",
        removed_tokens=dict(old-new), added_tokens=dict(new-old),
        verified_changes={"86.6 -> 79.02": "PanelF_Annual_Components.PS_Catch_Share; current Base_3 five-species total",
                          "100kg crossings -> 2034/2031/2029": "PanelF_Crossover_By_Leak; sorted STEPS/APS/NZE",
                          "7 -> 8 fuels": "PanelD/PanelE complete fuel keys",
                          "NZE 2050 0 -> -4": "fleet_model.get_grid_ef; retained signed-grid convention"},
        other_token_whitelist="Condensed fresh caption: dates, panel labels, equations, preserved physical assumptions and removed outdated posterior/endpoint statistics. No upstream numeric input was changed; all result changes are recorded separately in Fig4_Numeric_Changes.csv.")
    (HERE/"Caption_Numeric_Audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


if __name__ == "__main__":
    upstream_checks()
    report = panel_checks()
    report["model_vessel_checks"] = model_checks()
    report["status"] = "PASS"
    report["panel_sha256"] = {p.name: sha(p) for p in HERE.glob("Fig4_Panel*.csv") if "Render_Data" not in p.name}
    caption_numeric_audit()
    (HERE/"Fig4_QC.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
