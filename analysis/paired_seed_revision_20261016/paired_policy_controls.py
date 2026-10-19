"""Policy-order regression plus ID-aligned physical-fleet comparison."""
from pathlib import Path
import sys,json,contextlib,io,hashlib
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'figures/Fig5'))
import fig5_run as F
from scenario_seeds import FUTURES,paired_seed
H=Path(__file__).parent
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
with contextlib.redirect_stdout(io.StringIO()):fleet,pm=F.fleet_model.load_baseline_fleet()
F._init_worker(fleet,pm)
future=FUTURES[40];w,g,r,t=future
base=F.make_params(weo=w,growth=g,tc=t,ret=r,forced=0)
seed=paired_seed(future)
h0,f0=F._sim(base,seed)
hr,fr=F._sim({**base,'refrigerant_type':'LN2'},seed)
cols=['Flag','VesselType','Organization','LOA','Power_kW','Tonnage_GT','Built_Year','Effective_Hull_Year','Engine_Vintage']
a=f0.set_index('Vessel_ID')[cols].sort_index();b=fr.set_index('Vessel_ID')[cols].sort_index()
assert a.index.equals(b.index)
string_cols=['Flag','VesselType','Organization']
assert a[string_cols].equals(b[string_cols])
numeric=[c for c in cols if c not in string_cols]
diff=(a[numeric]-b[numeric]).abs().max()
assert np.allclose(a[numeric],b[numeric],rtol=1e-12,atol=1e-8)
fuel=json.loads((Path(F.OUT)/'Fig5_Final_Fuel.json').read_text())[w]
F._sim({**base,**fuel},seed)
F._sim({**base,'consolidation_type':2},seed)
h1,f1=F._sim(base,seed)
assert h0.equals(h1),'Policy order contaminated subsequent baseline'
assert f0.equals(f1),'Policy order contaminated subsequent fleet'
res=dict(Future='F41',Seed=seed,baseline_after_ref_fuel_consolidation_bit_identical=True,
    refrigeration_same_vessel_ids_and_physical_attributes=True,
    physical_attribute_max_abs_differences=diff.to_dict(),
    note='Raw ordered hashes differ because the model sorts fleets by GHG/power. Physical comparisons align by vessel ID and use a numeric tolerance.')
(H/'Policy_Control_QC.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
print(json.dumps(res,indent=2))
