from pathlib import Path
import sys
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
A=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'
p=pd.read_csv(A/'HCR_Period.csv',dtype={'Technical':str});b=p[p.Technical=='000']
b.to_csv(HERE/'Extended_Fig7_HCR_PanelA_Baselines.csv',index=False)
e=pd.read_csv(A/'HCR_Technical_Effects.csv',dtype={'Technical':str})
e=e[e.Technical=='100'].merge(b[['Future','Rule','TechCreep','WEO']],on=['Future','Rule'],validate='one_to_one')
e.to_csv(HERE/'Extended_Fig7_HCR_PanelB_Fuel.csv',index=False)
