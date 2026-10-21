from pathlib import Path
import sys
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
A=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'
d=pd.read_csv(A/'HCR_Annual.csv',dtype={'Technical':str});d=d[d.Technical=='000'].copy();d['GHG_Mt']=d.Total_GHG_tCO2e/1e6
s=d.groupby(['Rule','Year']).GHG_Mt.agg(Median='median',p5=lambda x:x.quantile(.05),p25=lambda x:x.quantile(.25),p75=lambda x:x.quantile(.75),p95=lambda x:x.quantile(.95)).reset_index()
s.to_csv(HERE/'Supplementary_Fig13_PanelB_Scenarios.csv',index=False)
