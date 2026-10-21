from pathlib import Path
import sys
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
A=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'
for label,name in [('A_Organizations','Organization'),('B_Gears','Gear')]:
 d=pd.read_csv(A/('HCR_'+name+'_Technical_Effects.csv'),dtype={'Technical':str})
 d=d[d.Technical.isin(['100','010','001','111'])]
 d.to_csv(HERE/('Supplementary_Fig16_HCR_Panel'+label+'.csv'),index=False)
