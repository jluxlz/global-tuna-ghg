"""Historical coverage and ghost-capacity audit; data only, no plotting."""
from pathlib import Path
import pandas as pd,numpy as np,json,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
g=pd.read_csv(ROOT/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv')
b=pd.read_csv(ROOT/'GHG_Calculation/Base_2_Fleet_GHG.csv')
pos=g[g.Total_Catch>0].copy()
pos['Coverage']=np.where(pos.GHG_emissions_median>0,'Allocated GHG','No allocated GHG')
catch=pos.groupby(['Year','Coverage']).Total_Catch.sum().div(1e6).reset_index(name='Catch_Mt')
catch.to_csv(HERE/'Supplementary_Fig4_PanelA_Catch_Coverage.csv',index=False)
fleet=b.groupby('Year').Nat_GHG_median.sum()
placed=g.groupby('Year').GHG_emissions_median.sum()
coverage=pd.DataFrame({'Fleet_GHG_t':fleet,'Grid_GHG_t':placed}).fillna(0)
coverage['Allocated_pct']=coverage.Grid_GHG_t/coverage.Fleet_GHG_t*100
assert coverage.Allocated_pct.between(0,100.000001).all()
coverage.reset_index().to_csv(HERE/'Supplementary_Fig4_PanelB_GHG_Coverage.csv',index=False)
qc=pd.read_csv(ROOT/'GHG_Calculation/Ghost_Fleet_Capacity_QC.csv')
ghost=qc.groupby('Year')[['Gap_kW','Ghost_kW','Unfilled_kW']].sum().reset_index()
assert np.allclose(ghost.Gap_kW,ghost.Ghost_kW+ghost.Unfilled_kW,rtol=1e-10,atol=1e-7)
ghost.to_csv(HERE/'Supplementary_Fig4_PanelC_Ghost_Capacity.csv',index=False)
summary=dict(Positive_catch_rows=len(pos),Catch_without_GHG_rows=int((pos.GHG_emissions_median<=0).sum()),
 Catch_without_GHG_Mt=float(pos.loc[pos.GHG_emissions_median<=0,'Total_Catch'].sum()/1e6),
 First_Grid_Year=int(g.Year.min()),Last_Grid_Year=int(g.Year.max()),
 Unique_Catch_Keys=not g.duplicated(['Year','Flag','Gear','squaretypecode','lat','lon','EffortType','Organization']).any(),
 Max_Unfilled_kW=float(ghost.Unfilled_kW.abs().max()),Ghost_From_2017_kW=float(ghost.loc[ghost.Year>=2017,'Ghost_kW'].sum()))
(HERE/'Supplementary_Fig4_QC.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(summary)
