"""Current C/F/T and fuel comparisons in the conditional Indian Ocean BET fleet."""
from pathlib import Path
import sys,os,json,hashlib,contextlib,io,time
from multiprocessing import Pool
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[2];H=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'analysis/hcr_revision_20261020'),str(R/'scenario'),str(R/'figures/Fig5')]
import run_hcr as E
CONFIG=R/'analysis/p0_revision_20261013/regional_inputs'
OUT=H/'ensemble';OUT.mkdir(exist_ok=True)
W={}

def init(fleet,pm,signature):
    from threadpoolctl import threadpool_limits
    W['threadpool_guard']=threadpool_limits(limits=1)
    W.update(fleet=fleet,pm=pm,signature=signature)

def job(i,rule,fuel):
    key,p,seed,meta=E.make_job(i,rule,'100' if fuel else '000')
    p['fishery_coupling'].update(stock_parameters=str(CONFIG/'BET_Projection_Parameters.csv'),allocation_file=str(CONFIG/'BET_Catch_Allocation.csv'))
    meta.update(Scope='IOTC_BET_current_HCR',Reference_State_Year=2024,Fuel_Transition=bool(fuel))
    return f'IOTC_BET_F{i+1:02}_{rule}_{int(fuel)}',p,seed,meta

def task(item):
    key,p,seed,meta=item;folder=OUT/key;folder.mkdir(exist_ok=True)
    signature=hashlib.sha256(json.dumps(dict(params=p,seed=seed,inputs=W['signature']),sort_keys=True).encode()).hexdigest()
    mark=folder/'Complete.json'
    if mark.exists():
        saved=json.loads(mark.read_text())
        if saved['Signature']==signature and all(hashlib.sha256((folder/n).read_bytes()).hexdigest()==v for n,v in saved['Outputs'].items()):return key,'reused'
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        hist,last=E.fm.run_scenario_simulation(W['fleet'].copy(),W['pm'],p,start_year=2025,end_year=2050,random_seed=seed)
    stocks=hist.attrs['stock_ledger'];effort=hist.attrs['effort_ledger']
    error=float((stocks.B_Start_Mt+stocks.Growth_Mt-stocks.Realised_Stock_Catch_Mt-stocks.B_End_Mt).abs().max())
    assert error<1e-10
    assert (stocks.Realised_Stock_Catch_Mt<=stocks.Target_Catch_Mt+1e-10).all()
    assert (effort.Realised_kW_days<=effort.Capacity_kW_days+1e-6).all()
    assert np.isfinite(hist.Total_GHG_tCO2e).all()
    positive=hist.Realised_Fleet_Catch_Mt>0
    assert np.allclose(hist.loc[positive,'CEI_tCO2e_per_t']*hist.loc[positive,'Realised_Fleet_Catch_Mt']*1e6,hist.loc[positive,'Total_GHG_tCO2e'],rtol=1e-12)
    outputs={}
    for name,frame in [('Annual',hist),('Stocks',stocks),('Effort',effort)]:
        frame=frame.copy();frame.attrs={}
        for col,value in meta.items():frame[col]=value
        path=folder/(name+'.csv');frame.to_csv(path,index=False)
        outputs[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    mark.write_text(json.dumps(dict(Signature=signature,Parameters=p,Seed=seed,Metadata=meta,Outputs=outputs,Mass_Balance_Error_Mt=error),indent=2),encoding='utf-8')
    return key,'done'

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    mode=sys.argv[1] if len(sys.argv)>1 else 'pilot'
    guard=H/'order_guard.log'
    assert guard.exists() and 'PASS: deterministic' in guard.read_text(encoding='utf-8',errors='replace')
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=E.fm.load_baseline_fleet()
    fleet=fleet[fleet.Organization=='IOTC'].copy()
    weights=json.loads((CONFIG/'BET_Fleet_Weights.json').read_text())
    fleet['Accounting_Weight']=fleet.VesselType.map(weights).fillna(weights['Support'])
    inputs=E.fingerprint()
    for p in [Path(__file__),CONFIG/'BET_Projection_Parameters.csv',CONFIG/'BET_Catch_Allocation.csv',CONFIG/'BET_Fleet_Weights.json']:
        inputs[str(p.relative_to(R))]=hashlib.sha256(p.read_bytes()).hexdigest()
    inputs['Weighted_Fleet_SHA256']=hashlib.sha256(pd.util.hash_pandas_object(fleet,index=True).values.tobytes()).hexdigest()
    signature=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    (H/'Run_Inputs.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
    jobs=[job(i,r,f) for i in (range(81) if mode=='full' else [40]) for r in ['C','F','T'] for f in [False,True]]
    E.configure_spawn_threads();start=time.time()
    print('Regional current HCR:',mode,len(jobs),'runs',flush=True)
    with Pool(int(os.environ.get('REGIONAL_HCR_WORKERS','4')),initializer=init,initargs=(fleet,pm,signature)) as pool:
        for n,result in enumerate(pool.imap_unordered(task,jobs,chunksize=1),1):
            if n%18==0 or n==len(jobs):print(n,'/',len(jobs),'elapsed',round(time.time()-start),'s',flush=True)
    (H/(mode+'_Complete.json')).write_text(json.dumps(dict(Passed=True,Runs=len(jobs),Input_Signature=signature,Seconds=round(time.time()-start)),indent=2),encoding='utf-8')

if __name__=='__main__':main()
