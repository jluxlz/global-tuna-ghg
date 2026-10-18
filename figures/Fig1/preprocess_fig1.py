"""Aggregate paired LCA draws before calculating Fig1 intervals."""
from pathlib import Path
import json
import hashlib
import sys
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DATA=ROOT/"GHG_Calculation"


def quantiles(x):
    return np.percentile(x,[50,5,95],axis=0)


def main():
    sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    source=DATA/"GHG_LCA_Total_Draws.npz"
    raw=np.load(source,allow_pickle=False)
    years=raw["years"]
    keep=(years>=1950)&(years<=2025)
    years=years[keep]
    cube=raw["total_by_group"][:,:,keep]
    groups=[str(g).rsplit("_",2) for g in raw["groups"]]
    assert cube.shape[0]==len(groups) and np.isfinite(cube).all()
    rows=[]
    for gear in ["LL","PS","TP","SA"]:
        ids=[i for i,g in enumerate(groups) if g[1]==gear]
        samples=cube[ids].sum(axis=0)
        med,lo,hi=quantiles(samples)
        rows.extend(dict(Gear=gear,Year=int(y),GHG_Mt=m/1e6,GHG_Mt_lo=l/1e6,
                         GHG_Mt_hi=h/1e6) for y,m,l,h in zip(years,med,lo,hi))
    pd.DataFrame(rows).to_csv(HERE/"Fig1_Gear_Annual_MC.csv",index=False)
    total=raw["global_Total"][:,keep]
    assert np.allclose(cube.sum(axis=0),total)
    med,lo,hi=quantiles(total.sum(axis=1))
    pd.DataFrame([dict(Start_Year=1950,End_Year=2025,Draws=cube.shape[1],
        GHG_Mt=med/1e6,GHG_Mt_lo=lo/1e6,GHG_Mt_hi=hi/1e6)]).to_csv(
        HERE/"Fig1_Global_Cumulative_MC.csv",index=False)
    grid=pd.read_csv(DATA/"Base_3_Spatial_Grid_Enriched.csv")
    grid=grid[grid.Year.between(1950,2025)&grid.Gear.isin(["LL","PS"])&
              grid.GHG_emissions_median.gt(0)]
    weights=grid.groupby(["Organization","Flag","Gear","Year"]).Effort_Prop.sum()
    coverage=grid.assign(Positive_Catch=grid.Total_Catch.gt(0)).groupby(
        ["Organization","Gear","Positive_Catch"]).agg(
        GHG_t=("GHG_emissions_median","sum"),Catch_t=("Total_Catch","sum"),
        Rows=("Year","size"))
    coverage.to_csv(HERE/"Fig1_Attribution_Coverage.csv")
    flag_gear={}
    for i,(flag,gear,sector) in enumerate(groups):
        flag_gear.setdefault((flag,gear),[]).append(i)
    rows=[]
    annual=[]
    for org in ["WCPFC","IATTC","ICCAT","IOTC","CCSBT"]:
        yearly=np.zeros(cube.shape[1:])
        for (flag,gear),ids in flag_gear.items():
            if gear not in ["LL","PS"]: continue
            w=np.array([weights.get((org,flag,gear,int(y)),0.) for y in years])
            assert (w>=0).all() and (w<=1+1e-8).all()
            yearly+=cube[ids].sum(axis=0)*w
        med,lo,hi=quantiles(yearly)
        annual.extend(dict(Organization=org,Year=int(y),MC_Total=m/1e6,
                           GHG_lo=l/1e6,GHG_hi=h/1e6) for y,m,l,h in zip(years,med,lo,hi))
        med,lo,hi=quantiles(yearly.sum(axis=1))
        rows.append(dict(Organization=org,MC_Total=med/1e6,
                         Total_lo=lo/1e6,Total_hi=hi/1e6))
    pd.DataFrame(rows).to_csv(HERE/"Fig1_Org_Cumulative_MC.csv",index=False)
    pd.DataFrame(annual).to_csv(HERE/"Fig1_Org_Annual_MC.csv",index=False)
    meta=dict(Draws=cube.shape[1],Interval="central 90% (p5-p95)",
              Aggregation="sum paired draws first, then quantile",
              MC_Source_SHA256=hashlib.file_digest(source.open("rb"),"sha256").hexdigest(),
              PanelD_Point="sum effort-allocated fleet-year medians from Base3",
              Grid_Data_First_Year=int(grid.Year.min()),Grid_Data_Last_Year=int(grid.Year.max()),
              PanelD_Coverage="all allocated LL/PS records including zero-catch effort records")
    (HERE/"Fig1_Data_QC.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print("Fig1 paired-draw aggregation PASS")


if __name__=="__main__":main()
