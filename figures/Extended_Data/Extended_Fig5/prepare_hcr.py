from pathlib import Path
import sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
A=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'
g=pd.read_csv(A/'HCR_Baseline_Gear.csv')
g['Demand_Fulfilled']=g.Realised_kW_days/g.Required_kW_days.replace(0,np.nan)
g['Capacity_Used']=g.Realised_kW_days/g.Capacity_kW_days.replace(0,np.nan)
g.to_csv(HERE/'Extended_Fig5_HCR_PanelA_Effort.csv',index=False)
s=pd.read_csv(A/'HCR_Baseline_Stocks.csv');s['Target_Fulfilled']=s.Realised_Stock_Catch_Mt/s.Target_Catch_Mt.replace(0,np.nan)
s.to_csv(HERE/'Extended_Fig5_HCR_PanelB_Catches.csv',index=False)
