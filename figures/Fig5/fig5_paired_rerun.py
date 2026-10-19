"""Checkpointed, paired-seed replacement for legacy pressure-test simulations.

All 16 policy subsets share a seed within each of the 81 futures. A five-future,
five-seed diagnostic tests residual fleet-sampling variability. This driver
does not change biological, economic or fleet algorithms. Run after the
mandatory order-dependence regression. Production CSVs are promoted only
after every checkpoint and cross-interface check succeeds.
"""
from pathlib import Path
import contextlib
import hashlib
import io
import itertools
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scenario"))
import fig5_run as F
from scenario_seeds import FUTURES, PROTOCOL, paired_seed, record_seed_protocol

AUD = ROOT / "analysis/paired_seed_revision_20261016"
OUT = AUD / "ensemble"
W = {}
PILOT_FUTURES = (8, 31, 40, 54, 73)
PILOT_COMBOS = ("0000", "0100", "0010", "0001", "1000", "1111")


def init_worker(fleet, pm, signature):
    W.update(fleet=fleet, pm=pm, signature=signature)


def run_task(item):
    i, combo, replicate, params = item
    seed = paired_seed(FUTURES[i], replicate)
    coupled = params.get("fishery_coupling") is not None
    key = ("Feasible_" if coupled else "") + f"F{i+1:02d}_{combo}_R{replicate}"
    folder = OUT / key
    folder.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256(("checkpoint-v2" + W["signature"] + json.dumps(
        dict(params=params, seed=seed), sort_keys=True)).encode())
    if coupled:
        hasher.update((ROOT/"scenario/fishery_coupling.py").read_bytes())
        hasher.update(Path(params["fishery_coupling"]["stock_parameters"]).read_bytes())
    sig=hasher.hexdigest()
    marker = folder / "Complete.json"
    if marker.exists():
        old = json.loads(marker.read_text())
        if old["signature"] == sig and all(
            hashlib.sha256((folder / fn).read_bytes()).hexdigest() == h
            for fn, h in old["outputs"].items()):
            return key, "reused"
    start = time.time()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        hist, final, ra, sa, rg, sg, teff = F.fleet_model.run_scenario_simulation(
            W["fleet"], W["pm"], params, start_year=2025, end_year=2050,
            random_seed=seed, return_econ_agg=True)
    annual = rg.groupby("Year", as_index=False).GHG_tCO2e.sum()
    # The RFMO aggregate used by the legacy figure must conserve the full fleet.
    assert np.allclose(annual.GHG_tCO2e, hist.Total_GHG_tCO2e, rtol=1e-10)
    assert len(annual) == 26 and np.isfinite(annual.GHG_tCO2e).all()
    assert (annual.GHG_tCO2e >= 0).all()
    annual=annual.merge(hist[["Year","N_Vessels","Total_Power_kW","Meco","M_econ"]],
                        on="Year",validate="one_to_one")
    if coupled:
        annual=annual.merge(hist[["Year","Realised_Fleet_Catch_Mt","CEI_tCO2e_per_t"]],
                            on="Year",validate="one_to_one")
        stock=hist.attrs["stock_ledger"];effort=hist.attrs["effort_ledger"]
        assert (stock.B_Start_Mt+stock.Growth_Mt-stock.Realised_Stock_Catch_Mt-stock.B_End_Mt).abs().max()<1e-10
        assert (effort.Realised_kW_days<=effort.Capacity_kW_days+1e-6).all()
    annual.to_csv(folder / "Annual.csv", index=False)
    objects = sg.groupby(["Organization", "Species", "Gear"], as_index=False).GHG_tCO2e.sum()
    objects.to_csv(folder / "Objects.csv", index=False)
    marker.write_text(json.dumps(dict(protocol=PROTOCOL, signature=sig,
        future=f"F{i+1:02d}", combo=combo, replicate=replicate, seed=seed,
        configuration=list(FUTURES[i]), params=params, seconds=time.time()-start,
        final_structure_sha256=hashlib.sha256(pd.util.hash_pandas_object(
            final[["Vessel_ID","Flag","VesselType","Organization","LOA","Power_kW",
                   "Tonnage_GT","Built_Year","Effective_Hull_Year","Engine_Vintage"]],
            index=True).values.tobytes()).hexdigest(),
        outputs={fn:hashlib.sha256((folder/fn).read_bytes()).hexdigest()
                 for fn in ("Annual.csv", "Objects.csv")}), indent=2), encoding="utf-8")
    return key, "done"


def params_for(i, combo, ff, qs):
    w, g, r, t = FUTURES[i]
    p = F.make_params(weo=w, growth=g, tc=t, ret=r, forced=0)
    q, fuel, ref, cs = map(int, combo)
    if q:
        p.update(quota_type=dict(qs), schaefer_scenario=dict(F.MSY_FRAC))
    if fuel:
        p.update(ff[w])
    if ref:
        p["refrigerant_type"] = "LN2"
    if cs:
        p["consolidation_type"] = 2
    return p


def build_tasks():
    ff = json.loads((Path(F.OUT)/"Fig5_Final_Fuel.json").read_text())
    qs = json.loads((Path(F.OUT)/"Fig5_Final_Quota.json").read_text())
    combos = ["".join(map(str,c)) for c in itertools.product((0,1), repeat=4)]
    tasks = [(i,c,0,params_for(i,c,ff,qs)) for i in range(81) for c in combos]
    tasks += [(i,c,r,params_for(i,c,ff,qs)) for i in PILOT_FUTURES
              for r in range(1,5) for c in PILOT_COMBOS]
    # The close feasible-catch quota/fuel medians warrant a separate stochastic
    # spot-check. Original production files remain untouched.
    for i in PILOT_FUTURES:
        for replicate in range(5):
            for c in ("0000","1000","0100","1111"):
                p=params_for(i,c,ff,qs)
                p["fishery_coupling"]=dict(stock_parameters=str(
                    ROOT/"scenario/output/schaefer_projection_parameters.csv"),max_operating_days=365)
                tasks.append((i,c,replicate,p))
    return tasks


def read_checkpoint(i, combo, replicate=0, kind="Annual"):
    return pd.read_csv(OUT/f"F{i+1:02d}_{combo}_R{replicate}"/f"{kind}.csv")


def promote():
    annual_rows, het_rows, quota_rows, final_rows, bau_rows, endpoint_rows = [], [], [], [], [], []
    for i, (w,g,r,t) in enumerate(FUTURES):
        bid = f"BAU_{i+1:03d}"
        meta = dict(BAU_ID=bid,WEO=w,Growth=g,
                    Retirement={1:"Natural",2:"Renewal",3:"Forced"}[r],TechCreep=t)
        base = read_checkpoint(i,"0000").set_index("Year").GHG_tCO2e / 1e6
        bobj = read_checkpoint(i,"0000",kind="Objects").set_index(["Organization","Species","Gear"]).GHG_tCO2e / 1e6
        for y, v in base.items():
            bau_rows.append(dict(**meta,Year=int(y),GHG_Mt=v))
        for bits in itertools.product((0,1),repeat=4):
            combo = "".join(map(str,bits))
            ghg = read_checkpoint(i,combo).set_index("Year").GHG_tCO2e / 1e6
            endpoint_rows.append(dict(Future=f"F{i+1:02d}",WEO=w,Growth=g,
                Retirement=meta["Retirement"],TechCreep=t,Combo=combo,GHG_2050_Mt=ghg[2050]))
            if combo in ("1000","1111"):
                for y in base.index:
                    col = "GHG_QuotaOnly" if combo=="1000" else "GHG_Final"
                    row = dict(**meta,Year=int(y),GHG_BAU=base[y],Reduction_pct=round(100*(1-ghg[y]/base[y]),3))
                    row[col] = ghg[y]
                    (quota_rows if combo=="1000" else final_rows).append(row)
            if bits[0] or combo=="0000":
                continue
            name = "+".join(n for n,bit in zip(("Fuel","Refrigerant","Consolidation"),bits[1:]) if bit)
            level = F.WEO_FUEL_LEVEL[w] if name.startswith("Fuel") else ""
            for y in base.index:
                annual_rows.append(dict(**meta,Year=int(y),Mitigation_Pathway=name,
                    Mitigation_Level=level,GHG_BAU=base[y],GHG_Mitigation=ghg[y],
                    GHG_Reduction_pct=round(100*(1-ghg[y]/base[y]),3)))
            obj = read_checkpoint(i,combo,kind="Objects").set_index(["Organization","Species","Gear"]).GHG_tCO2e / 1e6
            if set(bobj.index) != set(obj.index):
                raise AssertionError("Policy changed object support; zero/missing treatment requires review")
            for (org,sp,gear),v in bobj.items():
                vm = obj.loc[(org,sp,gear)]
                het_rows.append(dict(**meta,Organization=org,Species=sp,Gear=gear,
                    Mitigation_Pathway=name,Mitigation_Level=level,GHG_BAU=v,
                    GHG_Mitigation=vm,Reduction_pct=round(100*(1-vm/v),3)))
    # Original BAU seed block is retained; catch hidden model/input drift here.
    old = pd.read_csv(ROOT/"data/reference/BAU_81_Annual.csv").sort_values(["BAU_ID","Year"])
    bau = pd.DataFrame(bau_rows).sort_values(["BAU_ID","Year"])
    max_diff = float(np.max(np.abs(old.GHG_Mt.to_numpy()-bau.GHG_Mt.to_numpy())))
    if max_diff > 1e-9:
        raise AssertionError(f"Paired rerun unexpectedly changed baseline by {max_diff} Mt")
    tables = {"BAU_81_Annual.csv":bau,"Mitigation_Results_Annual.csv":pd.DataFrame(annual_rows),
        "Heterogeneous_Mitigation_Results.csv":pd.DataFrame(het_rows),
        "Fig5_QuotaOnly_Annual.csv":pd.DataFrame(quota_rows),
        "Fig5_Final_Combination_Annual.csv":pd.DataFrame(final_rows),
        "SF6_Combos_2050.csv":pd.DataFrame(endpoint_rows)}
    opts=[]
    for (o,s,g),d in tables["Heterogeneous_Mitigation_Results.csv"].groupby(["Organization","Species","Gear"]):
        best=d.groupby("Mitigation_Pathway").Reduction_pct.mean().idxmax()
        opts.append(dict(Gear=g,Organization=o,Species=s,Optimal_Pathway=best,
            Optimal_Reduction=round(d[d.Mitigation_Pathway==best].Reduction_pct.mean(),3),
            N_BAU_Optimal=81,P_BAU_Optimal=1.0))
    tables["Optimal_Mitigation_By_Object.csv"]=pd.DataFrame(opts)
    stage=AUD/"verified_outputs";stage.mkdir(exist_ok=True)
    for fn,d in tables.items():
        d.to_csv(stage/fn,index=False)
    # Validate the complete factorial and consistent baselines before promotion.
    assert len(tables["SF6_Combos_2050.csv"])==1296
    assert len(tables["Mitigation_Results_Annual.csv"])==81*7*26
    assert not tables["Heterogeneous_Mitigation_Results.csv"].duplicated(
        ["BAU_ID","Organization","Species","Gear","Mitigation_Pathway"]).any()
    import shutil
    for fn in tables:
        shutil.copy2(stage/fn,Path(F.OUT)/fn)
    record_seed_protocol(F.OUT,list(tables))
    (AUD/"Promotion_QC.json").write_text(json.dumps(dict(
        protocol=PROTOCOL,baseline_max_difference_Mt=max_diff,
        rows={fn:len(d) for fn,d in tables.items()}),indent=2),encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    mode=sys.argv[1] if len(sys.argv)>1 else "full"
    if mode=="promote":
        promote();return
    guard=(AUD/"order_regression_final.log").read_text(encoding="utf-8",errors="replace")
    if "PASS: deterministic" not in guard or "FAIL:" in guard:
        raise RuntimeError("Order-dependence regression must pass before production")
    tasks=build_tasks()
    if mode=="pilot":
        tasks=[x for x in tasks if x[0] in PILOT_FUTURES and x[1] in PILOT_COMBOS
               and "fishery_coupling" not in x[3]]
    with contextlib.redirect_stdout(io.StringIO()):
        fleet,pm=F.fleet_model.load_baseline_fleet()
    signature=hashlib.sha256(pd.util.hash_pandas_object(fleet,index=True).values.tobytes()+
        json.dumps(pm,sort_keys=True,default=str).encode())
    paths=[ROOT/p for p in ("scenario/fleet_model.py","scenario/price_loader.py",
        "PMM_Imputation/After_PMM_Vessels.csv","effort_data/Share5_Lookup_FlagGearYear.csv",
        "GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv","model_parameters/Prior_Matrix.csv",
        "scenario/scenario_seeds.py","GHG_Calculation/ghg_lca.py",
        "scenario/output/schaefer_biomass_annual.csv","scenario/output/schaefer_biomass_annual_F.csv",
        "model_parameters/Scenario_Fuel_Parameters.xlsx","model_parameters/Scenario_Fuel_Price_Matrix.xlsx",
        "scenario/output/fig5/Fig5_Final_Fuel.json","scenario/output/fig5/Fig5_Final_Quota.json")]
    for p in paths:signature.update(p.read_bytes())
    signature=signature.hexdigest()
    workers=int(os.environ.get("PAIRED_WORKERS","18"));start=time.time()
    print("START",mode,len(tasks),"simulations",workers,"workers",flush=True)
    with Pool(workers,initializer=init_worker,initargs=(fleet,pm,signature)) as pool:
        for j,(key,status) in enumerate(pool.imap_unordered(run_task,tasks,chunksize=1),1):
            if j%10==0 or j==len(tasks):
                print(j,"/",len(tasks),"elapsed",round(time.time()-start),key,status,flush=True)
    (AUD/f"{mode}_Complete.json").write_text(json.dumps(dict(simulations=len(tasks),
        seconds=time.time()-start,input_signature=signature),indent=2),encoding="utf-8")
    if mode=="full":promote()
    print("COMPLETE",flush=True)


if __name__=="__main__":main()
