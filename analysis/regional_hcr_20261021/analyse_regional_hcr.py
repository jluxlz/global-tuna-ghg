"""Summarize paired regional experiments without pooling accounting scopes."""
from pathlib import Path
import json,hashlib,copy
import numpy as np
import pandas as pd
H=Path(__file__).resolve().parent;R=H.parents[1];A=H/'analysis';A.mkdir(exist_ok=True)
assert json.loads((H/'full_Complete.json').read_text())['Runs']==486
annual=[];stocks=[];effort=[];files=0;pairchecks=0
for i in range(1,82):
 for fuel in (0,1):
  marks=[]
  for rule in ['C','F','T']:
   folder=H/'ensemble'/f'IOTC_BET_F{i:02}_{rule}_{fuel}'
   mark=json.loads((folder/'Complete.json').read_text());marks.append(mark)
   for name,digest in mark['Outputs'].items():
    assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest;files+=1
   annual.append(pd.read_csv(folder/'Annual.csv',dtype={'Technical':str}))
   stocks.append(pd.read_csv(folder/'Stocks.csv',dtype={'Technical':str}))
   effort.append(pd.read_csv(folder/'Effort.csv',dtype={'Technical':str}))
  pars=[copy.deepcopy(x['Parameters']) for x in marks]
  for p in pars:p.pop('hcr')
  assert pars[0]==pars[1]==pars[2] and len({m['Seed'] for m in marks})==1
  pairchecks+=1
d=pd.concat(annual,ignore_index=True);s=pd.concat(stocks,ignore_index=True);e=pd.concat(effort,ignore_index=True)
assert not d.duplicated(['Future','Rule','Fuel_Transition','Year']).any()
g=d.groupby(['Future','Rule','Fuel_Transition'],as_index=False).agg(Catch_Mt=('Realised_Fleet_Catch_Mt','sum'),GHG_t=('Total_GHG_tCO2e','sum'))
g['GHG_Mt']=g.GHG_t/1e6;g['CEI']=g.GHG_Mt/g.Catch_Mt
end=d[d.Year==2050][['Future','Rule','Fuel_Transition','Total_GHG_tCO2e']].rename(columns={'Total_GHG_tCO2e':'GHG_2050_t'})
g=g.merge(end,on=['Future','Rule','Fuel_Transition'])
effects=[]
for _,z in g[g.Fuel_Transition==False].groupby('Future'):
 z=z.set_index('Rule')
 for base,policy in [('C','F'),('C','T'),('F','T')]:
  out=dict(Future=z.iloc[0].Future,Comparison=base+policy)
  for col in ['Catch_Mt','GHG_Mt','CEI','GHG_2050_t']:out[col+'_Change_pct']=100*(z.at[policy,col]/z.at[base,col]-1)
  effects.append(out)
effects=pd.DataFrame(effects)
fuel=g[g.Fuel_Transition].merge(g[~g.Fuel_Transition],on=['Future','Rule'],suffixes=('_Fuel','_Base'))
fuel['Reduction_pct']=100*(1-fuel.GHG_Mt_Fuel/fuel.GHG_Mt_Base)
fuel['Abatement_Mt']=fuel.GHG_Mt_Base-fuel.GHG_Mt_Fuel
fuel['Catch_Change_pct']=100*(fuel.Catch_Mt_Fuel/fuel.Catch_Mt_Base-1)
fuel.groupby('Rule').Catch_Change_pct.agg(['min','median','max']).to_csv(A/'Fuel_Catch_Response.csv')
trigger=s.groupby(['Future','Rule','Fuel_Transition'],as_index=False).agg(Triggered_Years=('HCR_Triggered','sum'),Closed_Years=('HCR_Closed','sum'),Min_B_Bmsy=('B_Bmsy_Start','min'))
global_stocks=pd.read_csv(R/'analysis/hcr_revision_20261020/analysis/HCR_Baseline_Stocks.csv')
global_stocks=global_stocks[global_stocks.Stock=='BET'].copy();global_stocks['Stock_Source']='Pooled global BET'
regional=s[~s.Fuel_Transition].copy();regional['Stock_Source']='Indian Ocean BET'
context=pd.concat([global_stocks,regional],ignore_index=True)
context=context[['Future','Rule','Year','B_Bmsy_Start','HCR_Triggered','HCR_Closed','Stock_Source']]
no_trigger=not s[s.Rule=='T'].HCR_Triggered.any()
max_diff=0.
if no_trigger:
 for _,z in d[d.Rule.isin(['F','T'])].groupby(['Future','Fuel_Transition']):
  a=z[z.Rule=='F'].sort_values('Year');b=z[z.Rule=='T'].sort_values('Year')
  for col in ['Total_GHG_tCO2e','Realised_Fleet_Catch_Mt','N_Vessels','Total_Power_kW']:
   diff=float(np.max(np.abs(a[col].to_numpy()-b[col].to_numpy())));max_diff=max(max_diff,diff)
   np.testing.assert_allclose(a[col],b[col],rtol=1e-12,atol=1e-7)
for name,frame in [('Annual',d),('Stocks',s),('Effort',e),('Period',g),('Paired_Rule_Effects',effects),('Fuel_Effects',fuel),('Threshold_Activation',trigger),('Stock_Context',context)]:frame.to_csv(A/(name+'.csv'),index=False)
summary=dict(Conditional_Regional_Fleet=True,Primary_Regional_Stock='IOTC BET',Runs=486,Period_Medians=g[~g.Fuel_Transition].groupby('Rule')[['Catch_Mt','GHG_Mt','CEI']].median().to_dict(),Paired_Rule_Medians=effects.groupby('Comparison').median(numeric_only=True).to_dict(),Fuel_Reduction_Medians=fuel.groupby('Rule').Reduction_pct.median().to_dict(),Regional_T_Triggered_Any=not no_trigger,Max_F_T_Absolute_Difference_When_Untriggered=max_diff,Initial_B_Bmsy=context[context.Year==2025].groupby('Stock_Source').B_Bmsy_Start.median().to_dict())
(A/'Summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
(H/'QC.json').write_text(json.dumps(dict(Passed=True,Runs=486,Output_Files_Verified=files,Paired_Design_Checks=pairchecks,No_Regional_Threshold_Activation=no_trigger,Current_BET_Reference=2024,YFT_Not_Used_As_Current_State=True),indent=2),encoding='utf-8')
print(json.dumps(summary),flush=True)
