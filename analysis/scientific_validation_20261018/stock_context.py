"""Independent assessment context, with native metric definitions kept apart.

The YFT file is an archived author model ending 2020, NOT the adopted 2025
assessment ensemble. SBT uses a digitised official median with stated precision.
No JABBA refits or cross-ocean biological attribution are made.
"""
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.stats import spearmanr,linregress
H=Path(__file__).resolve().parent;R=H.parents[1];O=H/'analysis'

def main():
    lines=(R/'analysis/p0_revision_20261013/sources/YFT/Report.sso').read_text().splitlines()
    start=next(i for i,x in enumerate(lines) if x.startswith('TIME_SERIES report:'))
    header=lines[start+1].split();rows=[]
    for line in lines[start+2:]:
        x=line.split()
        if len(x)<8 or not x[0].isdigit():break
        if x[2]=='TIME' and 13<=int(x[1])<=296:rows.append([int(x[0]),int(x[1]),float(x[6])])
    t=pd.DataFrame(rows,columns=['Area','Quarter','SpawnBio'])
    assert set(t.Area)=={1,2,3,4}
    t=t.groupby('Quarter').SpawnBio.sum().reset_index();t['Year']=1950+(t.Quarter-13)//4
    yearly=t.groupby('Year').SpawnBio.mean().reset_index();assert yearly.Year.max()==2020
    yearly.to_csv(O/'YFT_Archived_Assessment_Spawning_Index.csv',index=False)
    raw=pd.read_csv(R/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv',usecols=['Year','Organization','Gear','lat','lon','Total_Catch','YFT_Tonnes','Standard_Effort','GHG_emissions_median'])
    raw=raw[(raw.Organization=='IOTC')&raw.Gear.isin(['LL','PS'])&raw.Year.between(1970,2020)&(raw.Total_Catch>0)&(raw.Standard_Effort>0)&(raw.GHG_emissions_median>0)].copy()
    raw['lon']=np.floor(raw.lon/5)*5+2.5;raw['lat']=np.floor(raw.lat/5)*5+2.5
    # Membership is selected once for the complete historical comparison.
    g=raw.groupby(['Gear','lon','lat'])[['YFT_Tonnes','Total_Catch']].sum();g=g[g.YFT_Tonnes/g.Total_Catch>=.5].reset_index()[['Gear','lon','lat']]
    raw=raw.merge(g,on=['Gear','lon','lat'],validate='many_to_one')
    annual=raw.groupby(['Gear','Year'])[['YFT_Tonnes','Total_Catch','Standard_Effort']].sum().reset_index().merge(yearly,on='Year',validate='many_to_one')
    out=[];summ=[]
    for gear in ['LL','PS']:
        x=annual[annual.Gear==gear].copy()
        for first,last in [(1970,2020),(2006,2020)]:
            v=x[x.Year.between(first,last)].copy()
            for d,label in [(0.,'Uncorrected'),(.0186 if gear=='LL' else .0426,'Adopted')]:
                z=v.copy();z['Effort_per_t']=z.Standard_Effort/(1-d)**(z.Year-first)/z.YFT_Tonnes
                z['Effort_index']=z.Effort_per_t/z.Effort_per_t.iloc[0];z['Stock_index']=z.SpawnBio/z.SpawnBio.iloc[0]
                z['Rate_Label']=label;z['d_pct']=100*d;z['Window']=str(first)+'-'+str(last);z['Stock']='IOTC YFT (archived model)'
                out.append(z)
                summ.append(dict(Stock='IOTC YFT archived 4A_io',Gear=gear,Window=z.Window.iloc[0],Rate_Label=label,N=len(z),
                                 Effort_log_trend_pct=100*linregress(z.Year,np.log(z.Effort_per_t)).slope,
                                 Stock_log_trend_pct=100*linregress(z.Year,np.log(z.SpawnBio)).slope,
                                 Spearman_rho=spearmanr(z.Effort_per_t,z.SpawnBio).statistic,
                                 YFT_catch_fraction=z.YFT_Tonnes.sum()/z.Total_Catch.sum()))
    pd.concat(out).to_csv(O/'YFT_Stock_Effort_Comparison.csv',index=False);pd.DataFrame(summ).to_csv(O/'YFT_Associations.csv',index=False)
    print(pd.DataFrame(summ).to_string(index=False))
if __name__=='__main__':main()
