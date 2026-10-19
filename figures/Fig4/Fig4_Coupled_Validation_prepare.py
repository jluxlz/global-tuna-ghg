"""Alternative Fig4 panel preview from actual coupled stock/catch ledgers."""
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent
E=ROOT/'analysis/p0_revision_20261013/ensemble'
rows=[]
for f in range(1,82):
    for combo,label in [('0000','Constrained BAU'),('C_type','C-type quota'),('1000','F-type quota')]:
        d=pd.read_csv(E/f'D365_F{f:02}_{combo}/Stocks.csv',dtype={'Combo':str})
        d['Pathway']=label;d['B_K']=d.B_End_Mt/d.K_Mt;rows.append(d)
pd.concat(rows).to_csv(HERE/'Fig4_Coupled_Validation_PanelA_Stocks.csv',index=False)
