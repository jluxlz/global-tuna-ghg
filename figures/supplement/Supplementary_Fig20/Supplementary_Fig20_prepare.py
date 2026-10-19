from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
A=ROOT/'analysis/p0_revision_20261013'
trajectories=[];qc=[]
for label,stock in [('IOTC_BET','BET'),('IOTC_YFT_historical','YFT')]:
    folder=A/'regional_fits'/f'{label}_base'
    t=pd.read_csv(folder/'Fitted_Trajectory.csv');t['Stock']=stock;trajectories.append(t)
    q=pd.read_csv(folder/'Rank_Diagnostics.csv');q['Stock']=stock;qc.append(q)
pd.concat(trajectories).to_csv(HERE/'Supplementary_Fig20_PanelA_Regional_Fits.csv',index=False)
pd.concat(qc).to_csv(HERE/'Supplementary_Fig20_PanelB_Regional_QC.csv',index=False)
pd.read_csv(A/'analysis/Regional_Paired_Comparisons.csv',dtype={'Combo':str}).to_csv(HERE/'Supplementary_Fig20_PanelC_Policies.csv',index=False)
pd.read_csv(A/'regional_inputs/YFT_Observed_Catch_Bridge_QC.csv').to_csv(HERE/'Supplementary_Fig20_PanelD_Bridge.csv',index=False)
