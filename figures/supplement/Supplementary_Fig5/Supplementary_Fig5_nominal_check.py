"""Analytically undo the historical effort correction on saved Fig.3 slopes.
No new annual trend regressions, stock fits or future simulations are performed.
"""
from pathlib import Path
import numpy as np
import pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parents[2]
d=pd.read_csv(ROOT/'figures/Fig3/Fig3_PanelA_Factor_Trends.csv')
d['Shift']=-100*np.log(1-d.Gear.map({'LL':.0186,'PS':.0426}))
d['Nominal_effort']=d.Effort_log_trend_pct-d.Shift
d['Nominal_GHG_effort']=d.GHG_Effort_log_trend_pct+d.Shift
assert np.allclose(d.Nominal_effort+d.Nominal_GHG_effort,d.CEI_log_trend_pct,atol=1e-10)
out=[]
for (gear,era),g in d.groupby(['Gear','Era'],observed=True):
 for label,a,b in [('Nominal','Nominal_effort','Nominal_GHG_effort'),('Technology-adjusted','Effort_log_trend_pct','GHG_Effort_log_trend_pct')]:
  out.append(dict(Gear=gear,Era=era.replace('2006-2025','2006-2024'),Basis=label,
    Effort_trend=np.average(g[a],weights=g.Total_GHG),GHG_effort_trend=np.average(g[b],weights=g.Total_GHG),
    CEI_trend=np.average(g.CEI_log_trend_pct,weights=g.Total_GHG),N=len(g)))
pd.DataFrame(out).to_csv(H/'Supplementary_Fig5_PanelB_Creep_Comparison.csv',index=False)
d.to_csv(H/'Supplementary_Fig5_Nominal_Corrected_Grid_Data.csv',index=False)
