"""Exact frozen-state accounting sensitivity to a common engine-clock factor.

Fuel combustion, upstream fuel and bait are linear in the prescribed base clock.
Scale all main/auxiliary clocks together; retain catches, days, fleet, phase
shares, loads, allocation, materials and leakage. This is not a coupled rerun.
"""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
H=Path(__file__).resolve().parent;R=H.parents[2]
z=np.load(R/'GHG_Calculation/GHG_LCA_Total_Draws.npz')
keep=(z['years']>=1950)&(z['years']<=2025);years=z['years'][keep]
processes=['Fuel_CO2','Fuel_CH4','Fuel_N2O','Fuel_WTT','Build','Maint','Gear_Build','Gear_Maint','Refrig','Bait']
total=z['global_Total'][:,keep]
assert np.allclose(total,sum(z['global_'+k][:,keep] for k in processes),rtol=1e-12,atol=1e-6)
time_scaled=sum(z['global_'+k][:,keep] for k in ['Fuel_CO2','Fuel_CH4','Fuel_N2O','Fuel_WTT','Bait'])
fixed=total-time_scaled
assert fixed.min()>-1e-7
bench=pd.read_csv(R/'figures/supplement/Supplementary_Fig14/Supplementary_Table10_Benchmark.csv')
ll=bench[(bench.Benchmark_ID=='LL23')&(bench.Metric=='Fuel use')].iloc[0]
annual=[];summary=[];benchmark=[]
for factor,industrial,coastal in [(1,24,12),(.75,18,9),(.5,12,6)]:
    scenario=f'{industrial}/{coastal} h'
    draws=(fixed+factor*time_scaled)/1e6
    q=np.quantile(draws,[.05,.5,.95],axis=0)
    for i,y in enumerate(years):annual.append(dict(Scenario=scenario,Clock_factor=factor,Year=int(y),P5_Mt=q[0,i],Median_Mt=q[1,i],P95_Mt=q[2,i]))
    c=np.quantile(draws.sum(axis=1),[.05,.5,.95]);e=q[:,years==2025].ravel()
    reduction=100*(1-(fixed+factor*time_scaled).sum(axis=1)/total.sum(axis=1))
    fuel=float(ll.Model)*factor;lit=float(ll.Literature)
    summary.append(dict(Scenario=scenario,Industrial_h=industrial,Coastal_h=coastal,Clock_factor=factor,
        Cumulative_P5_Mt=c[0],Cumulative_Median_Mt=c[1],Cumulative_P95_Mt=c[2],
        Annual2025_P5_Mt=e[0],Annual2025_Median_Mt=e[1],Annual2025_P95_Mt=e[2],
        Paired_Cumulative_Reduction_Median_pct=float(np.median(reduction)),
        LL2023_Fuel_L_t=fuel,LL2023_Literature_L_t=lit,LL2023_Gap_pct=100*(fuel/lit-1)))
    benchmark.append(dict(Scenario=scenario,Clock_factor=factor,Model_Fuel_L_t=fuel,Literature_Fuel_L_t=lit))
pd.DataFrame(annual).to_csv(H/'Supplementary_Fig15_Annual.csv',index=False)
pd.DataFrame(summary).to_csv(H/'Supplementary_Table11_Engine_Clock.csv',index=False)
pd.DataFrame(benchmark).to_csv(H/'Supplementary_Fig15_LL_Benchmark.csv',index=False)
assert np.isclose(summary[0]['Cumulative_Median_Mt'],813.8,atol=.1)
assert np.isclose(summary[0]['Annual2025_Median_Mt'],26.09,atol=.03)
qc={'method':'Exact linear rescaling of saved paired process draws at frozen vessel states',
    'scaled_processes':['Fuel_CO2','Fuel_CH4','Fuel_N2O','Fuel_WTT','Bait'],
    'unscaled_processes':['Build','Maint','Gear_Build','Gear_Maint','Refrig'],
    'draws':int(total.shape[0]),'years':[int(years.min()),int(years.max())],
    'limitations':'Common main/auxiliary clock factors; no catch, stock, days, allocation or fleet feedback; not observational calibration or a coupled rerun.',
    'inputs':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
       [R/'GHG_Calculation/GHG_LCA_Total_Draws.npz',R/'GHG_Calculation/ghg_lca.py',R/'figures/supplement/Supplementary_Fig14/Supplementary_Table10_Benchmark.csv']}}
(H/'Clock_Sensitivity_QC.json').write_text(json.dumps(qc,indent=2),encoding='utf-8')
print(pd.DataFrame(summary).to_string(index=False))
