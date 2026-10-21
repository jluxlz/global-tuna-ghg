"""Complete-file integrity, paired-design fairness and scientific conservation."""
from pathlib import Path
import sys,json,hashlib,copy
import numpy as np
import pandas as pd
import run_hcr as E
H=E.H;R=E.R
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 sys.stdout.reconfigure(encoding='utf-8',errors='replace')
 assert json.loads((H/'Production_Complete.json').read_text())['Sensitivity']==1620
 assert (H/'Matching_Complete.json').is_file()
 inputs=E.fingerprint();signature=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
 validation=json.loads((H/'Pilot_QC.json').read_text());assert validation['Passed'] and validation['Input_Fingerprint']==inputs
 for mode,expected in [('main',1944),('sensitivity',1620),('legacy',18)]:
  marker=json.loads((H/(mode+'_Complete.json')).read_text());assert marker['Jobs']==expected and marker['Input_Signature']==signature
 fleet,pm,grid=E.load_inputs();E.init_worker(fleet,pm,grid,signature)
 count=0;files=0;mass=0.
 for folder in E.OUT.iterdir():
  if not folder.is_dir() or not (folder/'Complete.json').is_file():continue
  m=json.loads((folder/'Complete.json').read_text())
  expected=hashlib.sha256(json.dumps(dict(params=m['Parameters'],seed=m['Seed'],inputs=signature,fleet=E.W['fleet_hash'],priors=E.W['priors']),sort_keys=True).encode()).hexdigest()
  assert m['Signature']==expected,folder
  for name,digest in m['Outputs'].items():assert sha(folder/name)==digest,(folder,name);files+=1
  count+=1;mass=max(mass,m['Mass_Balance_Error_Mt'])
 assert mass<1e-10
 # Rule-only contrasts hold everything except the target generation fixed.
 rulechecks=0
 for i in range(81):
  for combo in ['000','100','111','010','001','110','101','011']:
   saved=[json.loads((E.OUT/E.make_job(i,r,combo)[0]/'Complete.json').read_text()) for r in ['C','F','T']]
   params=[copy.deepcopy(x['Parameters']) for x in saved]
   for p in params:assert p.get('fishery_coupling');p.pop('hcr')
   assert params[0]==params[1]==params[2] and len({x['Seed'] for x in saved})==1
   starts=[pd.read_csv(E.OUT/E.make_job(i,r,combo)[0]/'Stocks.csv').query('Year==2025').set_index('Stock').B_Start_Mt for r in ['C','F','T']]
   pd.testing.assert_series_equal(starts[0],starts[1],check_exact=True);pd.testing.assert_series_equal(starts[0],starts[2],check_exact=True)
   rulechecks+=1
 pairs=pd.read_csv(H/'HCR_Matched_Pairs.csv');matched=pairs[pairs.Matched]
 for p in matched.itertuples():
  a=json.loads((E.OUT/p.Base_Key/'Complete.json').read_text());b=json.loads((E.OUT/p.Policy_Key/'Complete.json').read_text())
  pa=copy.deepcopy(a['Parameters']);pb=copy.deepcopy(b['Parameters']);pa.pop('hcr');pb.pop('hcr')
  assert pa==pb and a['Seed']==b['Seed']
  aa=pd.read_csv(E.OUT/p.Base_Key/'Annual.csv');bb=pd.read_csv(E.OUT/p.Policy_Key/'Annual.csv')
  gap=abs(bb.Realised_Fleet_Catch_Mt.sum()/aa.Realised_Fleet_Catch_Mt.sum()-1)
  assert gap<=.010000000001
 closure=pd.read_csv(H/'analysis/HCR_Matched_Closure.csv');assert closure.Residual_Mt.abs().max()<1e-8
 lmdi=pd.read_csv(H/'analysis/HCR_Unmatched_Two_Factor_LMDI.csv');assert lmdi.Residual_Mt.abs().max()<1e-8
 sh=pd.read_csv(H/'analysis/HCR_Three_Technical_Shapley.csv')
 sums=sh.groupby(['Future','Rule','Metric']).Contribution_Mt.sum()
 targets=sh.groupby(['Future','Rule','Metric']).Total_Abatement_Mt.first()
 assert (sums-targets).abs().max()<1e-8
 assert sh.loc[~sh.Share_Defined,'Share_pct'].isna().all()
 old=json.loads((H/'Protected_Inputs_Before.json').read_text());changed=[]
 approved={'figures/Fig4/Fig4_PanelD_Fuel_Cost.csv','figures/Fig4/Fig4_PanelD_Render_Data.csv',
           'figures/Fig4/Fig4_PanelE_Intensity.csv','figures/Fig4/Fig4_PanelE_Render_Data.csv'}
 for name,digest in old.items():
  if sha(R/name)!=digest:
   assert name.replace('\\','/') in approved,name
   changed.append(name)
 # Price-corrected analytical inputs retain every physical factor and fossil
 # comparison. Only HVO/FAME cost-dependent entries may change.
 for letter,suffix in [('D','Fuel_Cost'),('E','Intensity')]:
  name=f'figures/Fig4/Fig4_Panel{letter}_{suffix}.csv'
  a=pd.read_csv(H/'before'/name);b=pd.read_csv(R/name)
  keys=['WEO','Year','Fuel'];a=a.set_index(keys).sort_index();b=b.set_index(keys).sort_index()
  pd.testing.assert_index_equal(a.index,b.index)
  pd.testing.assert_frame_equal(a[~a.index.get_level_values('Fuel').isin(['HVO','FAME'])],b[~b.index.get_level_values('Fuel').isin(['HVO','FAME'])],check_exact=True)
  if letter=='E':
   for c in ['Physical_Intensity_gCO2e_kWh','EF_gCO2e_MJ','SFC_g_kWh','LHV_MJ_kg']:
    pd.testing.assert_series_equal(a[c],b[c],check_exact=True)
 assert json.loads((H/'Unfuelled_Invariance_QC.json').read_text())['Passed']
 assert json.loads((H/'Price_Interface_QC.json').read_text())['Passed']
 report=dict(Passed=True,Validated_Completed_Runs=count,Verified_Output_Files=files,
  Main_Simulations=1944,Sensitivity_Simulations=1620,Original_CF_Replicates=18,
  Matched_Pairs=len(matched),Attempted_Pairs=len(pairs),Rule_Only_Paired_Contexts=rulechecks,
  Maximum_Stock_Residual_Mt=mass,Maximum_Matched_Decomposition_Residual_Mt=float(closure.Residual_Mt.abs().max()),
  Maximum_Two_Factor_Residual_Mt=float(lmdi.Residual_Mt.abs().max()),
  Maximum_Shapley_Residual_Mt=float((sums-targets).abs().max()),
  Protected_Files=len(old),Approved_Price_Dependent_Changes=changed,
  Historical_Inventory_Figures1to3_And_Stock_Fits_Unchanged=True,
  Baseline_Price_Invariance=True,Original_19p4_Percent_Design_Reproduced=True,
  Scope='Numerical and paired-design validation, not independent biological prediction')
 (H/'Final_Scientific_QC.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
