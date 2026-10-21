"""Copy verified current regional C/F/T comparisons into this figure folder."""
from pathlib import Path
import json,shutil
H=Path(__file__).resolve().parent;R=H.parents[2];A=R/'analysis/regional_hcr_20261021/analysis'
assert json.loads((A.parent/'QC.json').read_text())['Passed']
for src,dst in [('Stock_Context','PanelA_Stocks'),('Paired_Rule_Effects','PanelB_Quota'),('Fuel_Effects','PanelC_Fuel'),('Threshold_Activation','Threshold_Activation')]:
    shutil.copy2(A/(src+'.csv'),H/('Extended_Fig9_'+dst+'.csv'))
