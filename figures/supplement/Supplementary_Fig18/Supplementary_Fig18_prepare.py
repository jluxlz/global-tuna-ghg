"""Capacity-constrained whole-chain comparisons; Python exports, R plots."""
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
A=ROOT/'audits/p0_revision_20261013'
d=pd.read_csv(A/'ensemble/All_Annual.csv')
select=d[(d.Max_Days==365)&d.Combo.isin(['0000','1000','0100','1111'])].copy()
names={'0000':'Constrained BAU','1000':'Quota only','0100':'Fuel only','1111':'Combined'}
select['Pathway']=select.Combo.map(names);select['GHG_Mt']=select.Total_GHG_tCO2e/1e6
pressure=pd.read_csv(ROOT/'scenario/output/fig5/BAU_81_Annual.csv');pressure['Pathway']='Fixed-catch stress test'
pd.concat([select[['Year','GHG_Mt','Pathway']],pressure[['Year','GHG_Mt','Pathway']]]).to_csv(HERE/'Supplementary_Fig18_PanelA_Annual.csv',index=False)
r=pd.read_csv(A/'analysis/Paired_Reductions.csv',dtype={'Combo':str})
r=r[r.Combo.isin(names)];r['Pathway']=r.Combo.map(names)
r.to_csv(HERE/'Supplementary_Fig18_PanelB_Reductions.csv',index=False)
period=pd.read_csv(A/'analysis/Period_Catch_GHG_CEI.csv',dtype={'Combo':str})
period=period[(period.Max_Days==365)&period.Combo.isin(['0000','C_type','1000','0100','1111'])]
period['Pathway']=period.Combo.map({**names,'C_type':'C-type quota'})
period.to_csv(HERE/'Supplementary_Fig18_PanelC_Catch_GHG.csv',index=False)
sp=pd.read_csv(A/'analysis/Shapley_Contributions.csv');sp.to_csv(HERE/'Supplementary_Fig18_PanelD_Shapley.csv',index=False)
