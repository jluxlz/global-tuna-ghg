from pathlib import Path
import sys,shutil
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
A=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'
names={'A_Matching':'HCR_Matched_Mechanism_Summary','B_Emissions':'HCR_Matched_Mechanism_Summary',
 'C_Decomposition':'HCR_Matched_LMDI_Terms','D_Weights':'HCR_Matched_Mechanism_Summary',
 'E_Stock_Effort':'HCR_Matched_Stock_Effort','F_Annual':'HCR_Matched_Annual',
 'Closure':'HCR_Matched_Closure'}
for panel,src in names.items():shutil.copy2(A/(src+'.csv'),HERE/('Extended_Fig6_Panel'+panel+'.csv'))
for src in ['HCR_Matched_Pairs','Common_Catch_Triples','Catch_Attainable_Ranges','Catch_Matching_All_Candidates']:
 shutil.copy2(A.parent/(src+'.csv'),HERE/(src+'.csv'))
shutil.copy2(A.parent/'Catch_Matching_Protocol.json',HERE/'Catch_Matching_Protocol.json')
