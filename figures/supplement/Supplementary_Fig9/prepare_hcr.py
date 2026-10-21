from pathlib import Path
import sys,json
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
H=ROOT/'analysis/hcr_revision_20261020'
for name in ['main_Complete.json','sensitivity_Complete.json']:assert (H/name).is_file()
counts=[('Primary: 81 futures x 3 HCRs x 8 subsets',1944),('280-day bound: 81 x 3 HCRs x 3 subsets',729),('80% harvest fractions: 81 x 3 HCRs',243),('Two alternative T-type thresholds: 81 x 2',162),('Fixed alternative-fuel prices: 81 x 3 HCRs x 2 subsets',486)]
pd.DataFrame(counts,columns=['Stage','Runs']).to_csv(HERE/'Supplementary_Fig9_PanelB_Run_Counts.csv',index=False)
