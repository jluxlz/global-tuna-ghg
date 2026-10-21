"""Raw economic-response sensitivity, independent of any fixed-catch BAU."""
from pathlib import Path
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
d=pd.read_csv(ROOT/'figures/Fig4/Fig4_PanelE_Intensity.csv');d=d[d.Year==2050]
rows=[]
for x in d.itertuples():
 for e in [0,-.1,-.3,-.5,-.7]:
  m=x.Cost_Ratio_vs_MGO**e
  rows.append(dict(WEO=x.WEO,Fuel=x.Fuel,Elasticity=e,Cost_Ratio=x.Cost_Ratio_vs_MGO,
   Raw_Response=m,Physical_Intensity=x.Physical_Intensity_gCO2e_kWh,Adjusted_Intensity=x.Physical_Intensity_gCO2e_kWh*m))
pd.DataFrame(rows).to_csv(HERE/'Extended_Fig6_Current_Price_Sensitivity.csv',index=False)
