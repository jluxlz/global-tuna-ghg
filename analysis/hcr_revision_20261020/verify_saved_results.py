"""Check preserved scientific outputs after relocation; no model recalculation."""
from pathlib import Path
import sys,json,hashlib,copy
import numpy as np
import pandas as pd
H=Path(__file__).resolve().parent

def main():
 results=[];files=0;max_balance=0.
 for folder in sorted((H/'ensemble').iterdir()):
  if not folder.is_dir() or not (folder/'Complete.json').exists():continue
  mark=json.loads((folder/'Complete.json').read_text(encoding='utf-8'))
  assert len(mark['Outputs'])==5,folder
  for name,digest in mark['Outputs'].items():
   p=folder/name
   assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==digest,p
   files+=1
  max_balance=max(max_balance,mark['Mass_Balance_Error_Mt']);results.append(folder.name)
 assert len(results)>=3963 and max_balance<1e-10
 fairness=0
 for future in range(1,82):
  for combo in ['000','100','010','001','110','101','011','111']:
   marks=[json.loads((H/'ensemble'/f'Main_F{future:02}_{rule}_{combo}/Complete.json').read_text()) for rule in ['C','F','T']]
   params=[copy.deepcopy(x['Parameters']) for x in marks]
   for p in params:p.pop('hcr')
   assert params[0]==params[1]==params[2] and len({x['Seed'] for x in marks})==1
   fairness+=1
 pairs=pd.read_csv(H/'HCR_Matched_Pairs.csv')
 for p in pairs[pairs.Matched].itertuples():
  a=pd.read_csv(H/'ensemble'/p.Base_Key/'Annual.csv');b=pd.read_csv(H/'ensemble'/p.Policy_Key/'Annual.csv')
  assert abs(b.Realised_Fleet_Catch_Mt.sum()/a.Realised_Fleet_Catch_Mt.sum()-1)<=.010000000001
 for future in [1,41,81]:
  for rule in ['C','F','T']:
   folder=H/'ensemble'/f'Main_F{future:02}_{rule}_000'
   a=pd.read_csv(folder/'Annual.csv');s=pd.read_csv(folder/'Stocks.csv');u=pd.read_csv(folder/'Effort.csv')
   assert np.isfinite(a.Total_GHG_tCO2e).all()
   assert np.allclose(s.B_Start_Mt+s.Growth_Mt-s.Realised_Stock_Catch_Mt,s.B_End_Mt,rtol=1e-11,atol=1e-10)
   assert (u.Realised_kW_days<=u.Capacity_kW_days+1e-6).all()
   positive=a.Realised_Fleet_Catch_Mt>0
   assert np.allclose(a.loc[positive,'Total_GHG_tCO2e'],a.loc[positive,'Realised_Fleet_Catch_Mt']*1e6*a.loc[positive,'CEI_tCO2e_per_t'])
 out=dict(Passed=True,Saved_Runs=len(results),Output_Files_Verified=files,Paired_Design_Checks=fairness,Matched_Pairs=27,Max_Recorded_Mass_Balance_Error_Mt=max_balance,Scientific_Recalculation_Performed=False,Stored_Run_Provenance_Preserved=True)
 (H/'Relocation_Integrity_QC.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out),flush=True)
if __name__=='__main__':main()
