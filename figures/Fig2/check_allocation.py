"""Refit the published Fig. 2 trends under catch allocation on the same sample."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=HERE)
output = parser.parse_args().output.resolve()
output.mkdir(parents=True, exist_ok=True)
source = ROOT / "figures/Fig2/preprocess_fig2.py"
s = source.read_text(encoding="utf-8")
s = s[:s.index("# 6. 3-era CEI means")]
# Keep the original Fig. 2 inclusion rules. Refit on precisely the same
# grid-years and use the baseline cell filters, not the alternative CEI cutoff.
insert = '''
keys = ["Year", "Flag", "Gear"]
assert np.allclose(df_raw["GHG_emissions_median"],
                   (df_raw["Nat_GHG_median"] * df_raw["Effort_Prop"]).fillna(0))
good = df_raw.groupby(keys, sort=False)
assert good["Nat_GHG_median"].nunique().max() == 1
assert good["Nat_Total_Catch"].nunique().max() == 1
total_c = good["Total_Catch"].sum()
assert np.allclose(total_c, good["Nat_Total_Catch"].first())
assert (df_raw["Total_Catch"] >= 0).all()
eligible = df_raw["Nat_Total_Catch"].gt(0) & df_raw["Gear"].isin(["LL","PS"])
df_raw["Catch_GHG"] = np.where(eligible,
    df_raw["Nat_GHG_median"] * df_raw["Total_Catch"] / df_raw["Nat_Total_Catch"], 0)
valid = eligible & df_raw["Nat_GHG_median"].gt(0)
chk = df_raw[valid].groupby(keys).agg(new=("Catch_GHG","sum"), fleet=("Nat_GHG_median","first"))
assert np.allclose(chk.new, chk.fleet)
'''
s = s.replace('df_raw = df_raw[', insert+'\ndf_raw = df_raw[', 1)
s = s.replace('"Total_Catch":           "sum",','"Catch_GHG": "sum",\n    "Total_Catch":           "sum",',1)
ns = {"__file__": str(source)}
exec(compile(s, str(source), "exec"), ns)
baseline = ns["df_slopes"].copy()
published = pd.read_csv(source.parent/"Fig2_PanelBC_Grid_Slopes.csv")
keys = ["Gear","lon","lat"]
assert len(baseline) == len(published) == 1195
b = baseline.merge(published, on=keys, validate="one_to_one")
for k in ("CEI_slope_pct", "CPUE_slope_pct"):
    assert np.allclose(b[k+"_x"],b[k+"_y"]), k
years = ns["df_grid_yr"].copy()
years["Grid_CEI"] = years["Catch_GHG"] / years["Total_Catch"]
out=[]
for key, g in years.groupby(keys):
    if len(g) < 10: continue
    y = g["Grid_CEI"]
    out.append((*key, np.polyfit(g["Year"], y, 1)[0]/y.mean()*100))
pair=baseline.merge(pd.DataFrame(out,columns=keys+["Catch_CEI_slope_pct"]),on=keys,validate="one_to_one")
assert len(pair)==1195
pair.to_csv(output/"Fig2_Allocation_Paired_Grid_Trends.csv",index=False)
rows=[]
for label,g in [("All",pair),*pair.groupby("Dominant_Species")]:
    for method,k in [("Effort","CEI_slope_pct"),("Catch","Catch_CEI_slope_pct")]:
        cp=g["CPUE_slope_pct"]; ce=g[k]
        rows.append(dict(Group=label,Allocation=method,N=len(g),R=cp.corr(ce),
                         Opposing_pct=100*((cp<0)&(ce>0)).mean(),Median_CEI_trend=ce.median()))
summary=pd.DataFrame(rows)
summary.to_csv(output/"Fig2_Allocation_Summary.csv",index=False)
print(summary.to_string(index=False))
