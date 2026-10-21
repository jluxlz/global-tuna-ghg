"""Export figure-specific C/F/T panel tables from completed, conserved simulations.

No model fitting, emission rescaling or matched-catch selection takes place here.
An alternative validated analysis directory may be supplied as the sole argument.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
SOURCE=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'

def read(name):
    return pd.read_csv(SOURCE/(name+'.csv'),dtype={'Technical':str})

def write(name,data,folder=HERE):
    data.to_csv(folder/(name+'.csv'),index=False)

def summary(d,keys,value):
    return d.groupby(keys,observed=True)[value].agg(Median='median',P5=lambda x:x.quantile(.05),P95=lambda x:x.quantile(.95),Minimum='min',Maximum='max',N='count').reset_index()

def primary():
    a=read('HCR_Annual');a=a[a.Technical=='000'].copy()
    a['GHG_Mt']=a.Total_GHG_tCO2e/1e6
    write('Fig5_HCR_PanelA_Annual',a)
    write('Fig5_HCR_PanelA_Summary',summary(a,['Rule','Year'],'GHG_Mt'))
    b=read('HCR_Period');b=b[b.Technical=='000']
    write('Fig5_HCR_PanelB_Period',b)
    write('Fig5_HCR_PanelB_Summary',read('HCR_Baseline_Period_Summary'))
    c=read('HCR_Technical_Effects')
    write('Fig5_HCR_PanelC_Fuel',c[c.Technical=='100'])
    write('Fig5_HCR_PanelD_Technical',c[c.Technical.isin(['100','010','001','111'])])
    write('Fig5_HCR_Three_Technical_Shapley',read('HCR_Three_Technical_Shapley'))
    s=read('HCR_Baseline_Stocks')
    write('Fig4_PanelA_HCR_Biomass',s,ROOT/'figures/Fig4')
    write('Fig4_PanelA_HCR_Summary',summary(s,['Rule','Stock','Year'],'B_Bmsy_Start'),ROOT/'figures/Fig4')
    g=read('HCR_Baseline_Gear')
    write('Fig4_PanelC_HCR_Effort',g,ROOT/'figures/Fig4')
    z=g.melt(id_vars=['Future','Rule','Year','Gear'],value_vars=['Realised_kW_days','Effort_per_t','Required_kW_days','Catch_t'],var_name='Metric',value_name='Value')
    write('Fig4_PanelC_HCR_Summary',summary(z,['Rule','Year','Gear','Metric'],'Value'),ROOT/'figures/Fig4')

def matched():
    write('Fig5_HCR_PanelE_Matched',read('HCR_Matched_Mechanism_Summary'))
    write('Fig5_HCR_PanelE_Summary',read('HCR_Matched_Summary'))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    primary();matched()
    print('C/F/T panel inputs exported from '+str(SOURCE))
