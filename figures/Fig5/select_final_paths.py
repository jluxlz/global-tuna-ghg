"""Rebuild final choices from the current proxy data using the documented screen."""
from pathlib import Path
import sys,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import fig5_run as f
OUT=ROOT/"scenario/output/fig5"


def main():
    sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    fo=pd.read_csv(OUT/"Fig5_Fuel_Options.csv")
    assert not fo.duplicated(["WEO","FuelOption","Intensity"]).any()
    fuel,choices={},[]
    for weo,level in f.WEO_FUEL_LEVEL.items():
        sub=fo[(fo.WEO==weo)&(fo.Intensity==level)]
        # Proxy emission reduction is the fuel screening objective. Economic
        # response is already included in the intensity, not added a second time.
        best=sub.sort_values(["Reduction_2050","FuelOption"],ascending=[False,True]).iloc[0]
        nodes=f.FUEL_LEVELS_V16[level]
        fuel[weo]=dict(biofuel_type=best.BioFuel if pd.notna(best.BioFuel) else "HVO",
                       newfuel_type=best.DevFuel if pd.notna(best.DevFuel) else "MGO",
                       biofuel_nodes=dict(zip([2030,2040,2050],nodes["bio"] if pd.notna(best.BioFuel) else [0.,0.,0.])),
                       newfuel_nodes=dict(zip([2030,2040,2050],nodes["renewal"] if pd.notna(best.DevFuel) else [0.,0.,0.])))
        choices.append(dict(WEO=weo,FuelOption=best.FuelOption,Intensity=level,
                            Reduction_2050=float(best.Reduction_2050)))
    quota=pd.read_csv(OUT/"Fig5_Quota_Recommendation.csv")
    # The regime rank is invariant to the common tech-creep multiplier;
    # verify that invariant instead of silently choosing one facet.
    assert quota.groupby("Species").BestQuota.nunique().eq(1).all()
    assert quota.Sustainable.all(), "No feasible quota regime for one or more species"
    qs=quota.groupby("Species").BestQuota.first().to_dict()
    assert set(qs)=={"SKJ","BET","YFT","ALB","SBT"}
    (OUT/"Fig5_Final_Fuel.json").write_text(json.dumps(fuel,indent=2),encoding="utf-8")
    (OUT/"Fig5_Final_Quota.json").write_text(json.dumps(qs,indent=2),encoding="utf-8")
    pd.DataFrame(choices).to_csv(HERE/"Fig5_Final_Selection.csv",index=False)
    print("Fresh final choices:",choices,qs)


if __name__=="__main__":main()
