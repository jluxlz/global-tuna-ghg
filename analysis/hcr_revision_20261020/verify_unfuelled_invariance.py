"""Verify that the price correction changed no no-transition HCR trajectories."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import run_hcr as E
H=E.H;archive=H/'_archive_pre_positive_prices_20261020/ensemble';checks=[]
for key,p,seed,m in E.main_jobs():
 if m['Technical']!='000':continue
 for table in ['Annual','Stocks','Effort','Groups','Cells']:
  a=pd.read_csv(archive/key/(table+'.csv'));b=pd.read_csv(E.OUT/key/(table+'.csv'))
  cols=list(a.select_dtypes('number').columns.intersection(b.select_dtypes('number').columns))
  assert len(a)==len(b)
  np.testing.assert_array_equal(a[cols].to_numpy(),b[cols].to_numpy())
 checks.append(key)
for future in ['F13','F14','F15','F40','F41','F42','F67','F68','F69']:
 for rule in ['C','F']:
  for table in ['Annual','Stocks','Effort','Groups','Cells']:
   a=pd.read_csv(archive/('OriginalCF_'+future+'_'+rule)/(table+'.csv'))
   b=pd.read_csv(E.OUT/('OriginalCF_'+future+'_'+rule)/(table+'.csv'))
   cols=list(a.select_dtypes('number').columns.intersection(b.select_dtypes('number').columns))
   np.testing.assert_array_equal(a[cols].to_numpy(),b[cols].to_numpy())
(H/'Unfuelled_Invariance_QC.json').write_text(json.dumps(dict(Passed=True,No_Transition_HCRs=len(checks),Original_CF_Runs=18,Tables_Per_Run=5,Numeric_Values_Bit_Identical_After_CSV_Read=True),indent=2),encoding='utf-8')
print('No-transition trajectories and all original matched C/F process states unchanged.')
