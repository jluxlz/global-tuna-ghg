"""Recover archival tables and analytically undo effort correction; no stock refits."""
from pathlib import Path
import json,sys
import pandas as pd
import numpy as np
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
H=Path(__file__).resolve().parent; R=H.parents[1]
books=json.loads((H/'Workbook_Values.json').read_text(encoding='utf-8'))
book=next(v for k,v in books.items() if k.endswith('JABBA_TechCreep_Sensitivity.xlsx'))
for label in ['Sensitivity','Final_Config','Notes']:
    rows=book[label+'_cached'];d=pd.DataFrame(rows[1:],columns=rows[0]);d['Evidence_version']='2026-09-20 archive, not current production validation'
    d.to_csv(H/('Archived_Creep_'+label+'.csv'),index=False,encoding='utf-8-sig')
f=R/'figures/Fig3/Fig3_PanelA_Factor_Trends.csv';d=pd.read_csv(f)
d['Slope_shift_pct_yr']=-100*np.log(1-d.Gear.map({'LL':.0186,'PS':.0426}))
d['Nominal_effort_trend']=d.Effort_log_trend_pct-d.Slope_shift_pct_yr
d['Nominal_GHG_effort_trend']=d.GHG_Effort_log_trend_pct+d.Slope_shift_pct_yr
assert np.allclose(d.Nominal_effort_trend+d.Nominal_GHG_effort_trend,d.CEI_log_trend_pct,atol=1e-10)
d.to_csv(H/'Nominal_Corrected_Grid_Trends.csv',index=False)
out=[]
for keys,s in d.groupby(['Gear','Era'],observed=True):
    for basis,a,b in [('Nominal','Nominal_effort_trend','Nominal_GHG_effort_trend'),('Technology-adjusted','Effort_log_trend_pct','GHG_Effort_log_trend_pct')]:
        out.append(dict(Gear=keys[0],Era=keys[1].replace('2006-2025','2006-2024'),Basis=basis,
            Effort_trend=np.average(s[a],weights=s.Total_GHG),GHG_effort_trend=np.average(s[b],weights=s.Total_GHG),
            CEI_trend=np.average(s.CEI_log_trend_pct,weights=s.Total_GHG),N=len(s)))
o=pd.DataFrame(out);o.to_csv(H/'Nominal_Corrected_Weighted_Trends.csv',index=False)
o.to_csv(R/'figures/supplement/Supplementary_Fig11/Supplementary_Fig11_PanelB_Creep_Comparison.csv',index=False)
print(o.to_string(index=False))
