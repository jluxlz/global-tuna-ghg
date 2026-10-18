from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
A=ROOT/'audits/p0_revision_20261013/analysis'
for name,source in [('A_LMDI','Catch_CEI_LMDI.csv'),('B_Catch_CEI','Period_Catch_GHG_CEI.csv'),('C_Matched','Equal_Catch_Comparison.csv'),('D_Closest','Equal_Catch_Comparison.csv')]:
    pd.read_csv(A/source,dtype={'Combo':str}).to_csv(HERE/f'Supplementary_Fig19_Panel{name}.csv',index=False)
