"""Illustrative cost buffering, retaining regional nonlinear responses."""
from pathlib import Path
import sys
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT/'scenario'))
import price_loader as p
cr=pd.read_excel(p.PRICE_MATRIX_PATH,sheet_name='Carbon_Reference');rows=[]
lhv=p.get_fuel_lhv('MGO');cf=p.get_fuel_ef_co2('MGO')
for w in ['STEPS','APS','NZE']:
 for region in sorted(cr[cr.Scenario==w].WEO_Region.dropna().unique()):
  p0,c0=p.get_fuel_price('MGO',w,2023,region);ref=(p0+c0*cf)/1000/lhv
  for y in range(2023,2051):
   price,carbon=p.get_fuel_price('MGO',w,y,region)
   full=((price+carbon*cf)/1000/lhv/ref)**(-.3)
   for name,m in [('Unbuffered',full),('Half carbon cost',((price+.5*carbon*cf)/1000/lhv/ref)**(-.3)),('2023 cost insulation',1.)]:
    rows.append(dict(WEO=w,Region=region,Year=y,Assumption=name,Raw_Response=m,Response_Change_pct=100*(m/full-1)))
pd.DataFrame(rows).to_csv(HERE/'Supplementary_Fig17_Current_Cost_Buffer.csv',index=False)
