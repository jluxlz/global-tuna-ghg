"""Representative HCR shape and observed model threshold activation."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
source=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'figures/Fig4/Fig4_PanelA_HCR_Biomass.csv'
s=pd.read_csv(source)
assert len(s[['Future','Rule']].drop_duplicates())==243
x=np.linspace(0,2,501);g=np.clip((x-.2)/.6,0,1)
curves=pd.concat([pd.DataFrame({'B_Bmsy':x,'Rule':r,'Target_MSY':q}) for r,q in [('C',np.ones(len(x))),('F',x),('T',x*g)]],ignore_index=True)
curves.to_csv(HERE/'Supplementary_Fig12_PanelA_HCR_Shapes.csv',index=False)
t=s[s.Rule=='T'].copy()
t.groupby(['Stock','Year'])[['HCR_Triggered','HCR_Closed']].mean().reset_index().to_csv(HERE/'Supplementary_Fig12_PanelB_Activation.csv',index=False)
t.to_csv(HERE/'Supplementary_Fig12_Threshold_States.csv',index=False)
s[s.Year==2050].to_csv(HERE/'Supplementary_Fig12_PanelC_Stock_Endpoints.csv',index=False)
