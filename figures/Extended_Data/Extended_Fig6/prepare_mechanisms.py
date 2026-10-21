"""Retain matched whole-fleet contributions and period species mechanisms."""
from pathlib import Path
import pandas as pd
H=Path(__file__).resolve().parent;R=H.parents[2];A=R/'analysis/hcr_revision_20261020/analysis'
pd.read_csv(A/'HCR_Matched_LMDI_Terms.csv').to_csv(H/'Extended_Fig6_PanelA_Contributions.csv',index=False)
d=pd.read_csv(A/'HCR_Matched_Stock_Effort.csv')
g=d.groupby(['Future','Comparison','Pair_Member','Stock']).agg(Catch_t=('Catch_t','sum'),Effort=('Realised_kW_days','sum'),Biomass=('B_Start_Mt','mean')).reset_index()
g['Effort_per_t']=g.Effort/g.Catch_t
p=g.pivot(index=['Future','Comparison','Stock'],columns='Pair_Member',values=['Biomass','Effort_per_t','Catch_t'])
ratios=pd.DataFrame({k+'_Ratio':p[k]['Policy']/p[k]['Base'] for k in ['Biomass','Effort_per_t','Catch_t']}).reset_index()
ratios.rename(columns={'Effort_per_t_Ratio':'Effort_Ratio'}).to_csv(H/'Extended_Fig6_PanelB_Biomass.csv',index=False)
ratios.rename(columns={'Effort_per_t_Ratio':'Effort_Ratio'}).to_csv(H/'Extended_Fig6_PanelC_Effort.csv',index=False)
