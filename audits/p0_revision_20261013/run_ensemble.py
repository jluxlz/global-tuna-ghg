"""Full fleet reruns with realised catch/biomass closure and common seeds.

Outputs are isolated from the fixed-catch stress-test production chain.
Resume is keyed by all parameters and SHA256 of model/biological inputs.
"""
from pathlib import Path
import sys,json,contextlib,io,hashlib,time,itertools,os
from multiprocessing import Pool
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'figures/Fig5'));sys.path.insert(0,str(ROOT/'scenario'))
import fleet_model as fm
import fig5_run as F
OUT=Path(__file__).parent/'ensemble';OUT.mkdir(exist_ok=True)
_W={}

def init_worker(fleet,pm):
    _W.update(fleet=fleet,pm=pm)

def digest(params):
    h=hashlib.sha256(json.dumps(params,sort_keys=True).encode())
    for path in [ROOT/'scenario/fleet_model.py',ROOT/'scenario/fishery_coupling.py',Path(params['fishery_coupling']['stock_parameters'])]:
        h.update(path.read_bytes())
    return h.hexdigest()

def task(item):
    key,p,seed,meta=item;signature=digest(p)
    folder=OUT/key;folder.mkdir(exist_ok=True)
    marker=folder/'Complete.json'
    if marker.exists() and json.loads(marker.read_text())['signature']==signature:
        return key,'reused'
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        h,last=fm.run_scenario_simulation(_W['fleet'],_W['pm'],p,start_year=2025,end_year=2050,random_seed=seed)
    stocks=h.attrs['stock_ledger'];effort=h.attrs['effort_ledger']
    error=(stocks.B_Start_Mt+stocks.Growth_Mt-stocks.Realised_Stock_Catch_Mt-stocks.B_End_Mt).abs().max()
    if error>1e-10 or (stocks.Realised_Stock_Catch_Mt>stocks.Target_Catch_Mt+1e-10).any():raise AssertionError('Stock closure failed')
    if (effort.Realised_kW_days>effort.Capacity_kW_days+1e-6).any():raise AssertionError('Physical effort capacity failed')
    if not np.allclose(h.CEI_tCO2e_per_t*h.Realised_Fleet_Catch_Mt*1e6,h.Total_GHG_tCO2e):raise AssertionError('CEI identity failed')
    for col,val in meta.items():h[col]=val;stocks[col]=val;effort[col]=val
    h.to_csv(folder/'Annual.csv',index=False);stocks.to_csv(folder/'Stocks.csv',index=False);effort.to_csv(folder/'Effort.csv',index=False)
    marker.write_text(json.dumps(dict(signature=signature,params=p,seed=seed,meta=meta,mass_balance_error_Mt=float(error)),indent=2),encoding='utf-8')
    return key,'done'

def build_tasks(mode):
    ff=json.loads((ROOT/'scenario/output/fig5/Fig5_Final_Fuel.json').read_text())
    quota=json.loads((ROOT/'scenario/output/fig5/Fig5_Final_Quota.json').read_text())
    futures=list(itertools.product(F.BAU_WEO,F.BAU_GROWTH,F.BAU_RETIRE.values(),F.BAU_TECH))
    tasks=[]
    for i,(weo,growth,ret,tc) in enumerate(futures):
        variants=[(365,''.join(map(str,c))) for c in itertools.product((0,1),repeat=4)]
        variants += [(365,'C_type')]
        if mode=='full':variants += [(280,c) for c in ('0000','1000','0100','1111','C_type')]
        for days,combo in variants:
            p=F.make_params(weo=weo,growth=growth,tc=tc,ret=int(ret),forced=0)
            if combo=='C_type':p.update(schaefer_scenario=dict(F.MSY_FRAC),quota_type='C')
            else:
                q,f,r,c=map(int,combo)
                if q:p.update(schaefer_scenario=dict(F.MSY_FRAC),quota_type=dict(quota))
                if f:p.update(ff[weo])
                if r:p['refrigerant_type']='LN2'
                if c:p['consolidation_type']=2
            p['fishery_coupling']=dict(stock_parameters=str(ROOT/'scenario/output/schaefer_projection_parameters.csv'),max_operating_days=days)
            meta=dict(Future=f'F{i+1:02}',WEO=weo,Growth=growth,Retirement=int(ret),TechCreep=tc,Combo=combo,Max_Days=days)
            tasks.append((f'D{days}_F{i+1:02}_{combo}',p,42+i,meta))
    if mode=='pilot':tasks=tasks[:2]
    return tasks

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'full'
    tasks=build_tasks(mode)
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=fm.load_baseline_fleet()
    workers=int(os.environ.get('P0_WORKERS',12));t=time.time()
    print('START',mode,len(tasks),'simulations',workers,'workers',flush=True)
    with Pool(workers,initializer=init_worker,initargs=(fleet,pm)) as pool:
        for j,(key,status) in enumerate(pool.imap_unordered(task,tasks,chunksize=1),1):
            if j%20==0 or j==len(tasks):print(j,'/',len(tasks),'elapsed seconds',round(time.time()-t),key,status,flush=True)
    frames=[pd.read_csv(OUT/k/'Annual.csv',dtype={'Combo':str}) for k,p,s,m in tasks]
    pd.concat(frames,ignore_index=True).to_csv(OUT/'All_Annual.csv',index=False)
    (OUT/'Ensemble_Complete.json').write_text(json.dumps(dict(mode=mode,simulations=len(tasks),seconds=time.time()-t)),encoding='utf-8')
    print('COMPLETE',flush=True)

if __name__=='__main__':main()
