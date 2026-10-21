from pathlib import Path
import sys,json,importlib.util
import numpy as np
H=Path(__file__).resolve().parent;R=H.parents[1];sys.path.insert(0,str(R/'scenario'))
import price_loader as now
from fuel_price_paths import inverse_carbon_multiplier
assert inverse_carbon_multiplier(100,200)==.5
assert inverse_carbon_multiplier(0,200)==1
assert inverse_carbon_multiplier(None,200)==1
source=H/'before_price_correction/scenario/price_loader.py'
spec=importlib.util.spec_from_file_location('old_price_loader',source);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
old.PRICE_MATRIX_PATH=str(H/'before_price_correction/model_parameters/Scenario_Fuel_Price_Matrix.xlsx')
old.FUEL_PARAMS_PATH=str(R/'model_parameters/Scenario_Fuel_Parameters.xlsx')
regions=['European Union','China','Korea','Advanced','Selected_EMDE','Other_EMDE']
comparisons=0
for scenario in ['STEPS','APS','NZE']:
 for region in regions:
  for year in range(2023,2051):
   for fuel in ['MGO','HFO']:
    a=old.get_fuel_price(fuel,scenario,year,region)[0];b=now.get_fuel_price(fuel,scenario,year,region)[0]
    assert a==b,(fuel,scenario,year,region,a,b)
   for fuel in ['HVO','FAME','LNG_Bio']:
    p=now.get_fuel_price(fuel,scenario,year,region)[0];assert np.isfinite(p) and p>0
    comparisons+=1
  for y0,y1 in [(2023,2030),(2030,2040),(2040,2050)]:
   y=(y0+y1)/2
   for fuel in ['HVO','FAME','LNG_Bio']:
    a=now.get_fuel_price(fuel,scenario,y0,region)[0];b=now.get_fuel_price(fuel,scenario,y1,region)[0];p=now.get_fuel_price(fuel,scenario,y,region)[0]
    assert np.isclose(p,(a+b)/2,rtol=1e-14)
(H/'Price_Interface_QC.json').write_text(json.dumps(dict(Passed=True,Positive_Annual_Alternative_Price_Queries=comparisons,
 Fossil_Price_Queries_Exactly_Unchanged=1008,Region_Fallback_Interpolation_Consistent=True,Inverse_Rule_Boundaries_Passed=True),indent=2),encoding='utf-8')
print('Price interface PASS',comparisons,'positive alternative-fuel queries; all fossil prices unchanged')
