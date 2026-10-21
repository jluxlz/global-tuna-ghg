"""Export the complete 243 no-transition HCR runs without waiting for technologies."""
import pandas as pd
import run_hcr as E
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def stats(d,keys,col):
 return d.groupby(keys,observed=True)[col].agg(Median='median',P5=lambda x:x.quantile(.05),P95=lambda x:x.quantile(.95),N='count').reset_index()
rows=[];gears=[]
for key,p,seed,meta in E.main_jobs():
 if meta['Technical']!='000':continue
 assert (E.OUT/key/'Complete.json').is_file(),key
 s=pd.read_csv(E.OUT/key/'Stocks.csv');rows.append(s)
 g=pd.read_csv(E.OUT/key/'Groups.csv');u=pd.read_csv(E.OUT/key/'Effort.csv')
 c=pd.read_csv(E.OUT/key/'Cells.csv').groupby(['Year','Gear']).Catch_t.sum()
 z=g[g.Gear.isin(['LL','PS'])].groupby(['Year','Gear']).Realised_kW_days.sum().reset_index()
 z['Catch_t']=[c.get((x.Year,x.Gear),0) for x in z.itertuples()]
 demand=u.groupby(['Year','Gear']).Required_kW_days.sum()
 z['Required_kW_days']=[demand.get((x.Year,x.Gear),0) for x in z.itertuples()]
 z['Effort_per_t']=z.Realised_kW_days/z.Catch_t.replace(0,float('nan'))
 for k,v in meta.items():z[k]=v
 gears.append(z)
s=pd.concat(rows);g=pd.concat(gears)
F=R/'figures/Fig4'
s.to_csv(F/'Fig4_PanelA_HCR_Biomass.csv',index=False)
stats(s,['Rule','Stock','Year'],'B_Bmsy_Start').to_csv(F/'Fig4_PanelA_HCR_Summary.csv',index=False)
g.to_csv(F/'Fig4_PanelC_HCR_Effort.csv',index=False)
long=g.melt(id_vars=['Future','Rule','Year','Gear'],value_vars=['Realised_kW_days','Effort_per_t','Required_kW_days','Catch_t'],var_name='Metric',value_name='Value')
stats(long,['Rule','Year','Gear','Metric'],'Value').to_csv(F/'Fig4_PanelC_HCR_Summary.csv',index=False)
print('Complete 243-run baseline Fig4 inputs exported.')
