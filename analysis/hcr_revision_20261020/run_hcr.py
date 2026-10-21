"""Paired C/F/T fleet experiments with complete activity/process accounting.

New outputs are isolated; legacy inventory, fitted stocks and saved scenarios
are read-only. Every checkpoint binds the actual inputs, seed and diagnostics.
"""
from pathlib import Path
import sys,os,json,contextlib,io,hashlib,time,itertools,platform,copy
from multiprocessing import Pool
from functools import lru_cache
import numpy as np
import pandas as pd
from importlib.metadata import version
H=Path(__file__).resolve().parent;R=H.parents[1]
sys.path[:0]=[str(R/'scenario'),str(R/'figures/Fig5'),str(R/'analysis/scientific_validation_20261018')]
import fleet_model as fm
import fig5_run as F
import matched_capture as C
from scenario_seeds import FUTURES,paired_seed,simulation_fingerprint
OUT=H/'ensemble';OUT.mkdir(exist_ok=True)
W={}
GRID_COLUMNS=['Year','Flag','Organization','Gear','lat','Total_Catch','Standard_Effort','GHG_emissions_median']+[s+'_Tonnes' for s in ('SBT','SKJ','BET','YFT','ALB')]

def fingerprint():
    d=simulation_fingerprint();d['scenario/output/schaefer_projection_parameters.csv']=hashlib.sha256((R/'scenario/output/schaefer_projection_parameters.csv').read_bytes()).hexdigest()
    for path in [Path(__file__),Path(C.__file__)]:d[str(path.relative_to(R))]=hashlib.sha256(path.read_bytes()).hexdigest()
    d['Runtime']=dict(Python=platform.python_version(),Platform=platform.platform(),Worker_BLAS_Threads=1,Packages={k:version(k) for k in ('numpy','pandas','scipy','openpyxl')})
    return d

def load_inputs():
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=fm.load_baseline_fleet()
    grid=pd.read_csv(R/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv',usecols=GRID_COLUMNS)
    return fleet,pm,grid

def configure_spawn_threads():
    # Set only after constructing the unchanged parent baseline. New Windows
    # interpreters must see the limit before importing NumPy/MKL, not merely
    # after the numerical libraries have created their initial thread pools.
    for name in ('MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[name]='1'

def init_worker(fleet,pm,grid,signature):
    from threadpoolctl import threadpool_limits
    W['threadpool_guard']=threadpool_limits(limits=1)
    import fig5_allocation as fa
    fm._BASE3_CACHE=grid;fa._CACHE['grid']=grid
    C.init_worker(fleet,pm)
    W.update(fleet=fleet,pm=pm,signature=signature,
        fleet_hash=hashlib.sha256(pd.util.hash_pandas_object(fleet,index=True).values.tobytes()).hexdigest(),
        priors=hashlib.sha256(json.dumps(pm['by_code'],sort_keys=True,default=str).encode()).hexdigest())

def make_job(i,rule,combo='000',fraction=1.,days=365,thresholds=(.4,.1),scope='Main',key=None,price_assumption='inverse_carbon'):
    w,g,ret,tc=FUTURES[i]
    p=F.make_params(weo=w,growth=g,tc=tc,ret=int(ret),forced=0)
    # The explicit HCR branch overrides legacy target definitions only.
    p['hcr']=dict(type=rule,alpha=float(fraction) if rule=='C' else 1.,beta=float(fraction) if rule!='C' else 1.,b_trigger_k=thresholds[0],b_close_k=thresholds[1])
    p['fishery_coupling']=dict(stock_parameters=str(R/'scenario/output/schaefer_projection_parameters.csv'),max_operating_days=days)
    p['alternative_price_assumption']=price_assumption
    fuel,ref,con=map(int,combo)
    if fuel:p.update(json.loads((R/'scenario/output/fig5/Fig5_Final_Fuel.json').read_text())[w])
    if ref:p['refrigerant_type']='LN2'
    if con:p['consolidation_type']=2
    m=dict(Future=f'F{i+1:02}',WEO=w,Growth=g,Retirement=ret,TechCreep=tc,Rule=rule,Technical=combo,Fraction=float(fraction),Max_Days=days,Scope=scope,B_Trigger_K=thresholds[0],B_Closure_K=thresholds[1],Price_Assumption=price_assumption)
    return key or f'{scope}_F{i+1:02}_{rule}_{combo}',p,paired_seed(FUTURES[i]),m

def run_task(job):
    key,p,seed,meta=job;folder=OUT/key;folder.mkdir(exist_ok=True);marker=folder/'Complete.json'
    signature=hashlib.sha256(json.dumps(dict(params=p,seed=seed,inputs=W['signature'],fleet=W['fleet_hash'],priors=W['priors']),sort_keys=True).encode()).hexdigest()
    if marker.exists():
        saved=json.loads(marker.read_text())
        if saved.get('Signature')==signature and saved.get('Outputs') and all((folder/n).is_file() and hashlib.sha256((folder/n).read_bytes()).hexdigest()==v for n,v in saved['Outputs'].items()):return key,'reused'
    C.STATE.update(capture=True,future='',groups=[],cells=[],vessels=[])
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            hist,last=fm.run_scenario_simulation(W['fleet'],W['pm'],p,start_year=2025,end_year=2050,random_seed=seed)
    finally:C.STATE['capture']=False
    stocks=hist.attrs['stock_ledger'];effort=hist.attrs['effort_ledger'];groups=pd.DataFrame(C.STATE['groups']);cells=pd.DataFrame(C.STATE['cells'])
    assert np.isfinite(hist[['Total_GHG_tCO2e','Realised_Fleet_Catch_Mt']]).all().all()
    assert np.isfinite(groups[['GHG_t','Variable_GHG_t','Fixed_GHG_t','Realised_kW_days']]).all().all()
    balance=(stocks.B_Start_Mt+stocks.Growth_Mt-stocks.Realised_Stock_Catch_Mt-stocks.B_End_Mt).abs().max()
    assert balance<1e-10 and (stocks.Realised_Stock_Catch_Mt<=stocks.Target_Catch_Mt+1e-10).all()
    assert (effort.Realised_kW_days<=effort.Capacity_kW_days+1e-6).all()
    assert np.allclose(groups.groupby('Year').GHG_t.sum(),hist.set_index('Year').Total_GHG_tCO2e,rtol=1e-12,atol=1e-7)
    assert np.allclose(cells.groupby('Year').Catch_t.sum(),hist.set_index('Year').Realised_Fleet_Catch_Mt*1e6,rtol=1e-11,atol=1e-6)
    assert np.allclose(cells.groupby('Year').Realised_kW_days.sum(),effort.groupby('Year').Realised_kW_days.sum(),rtol=1e-11,atol=1e-5)
    pos=hist.Realised_Fleet_Catch_Mt>0
    assert np.allclose(hist.loc[pos,'CEI_tCO2e_per_t']*hist.loc[pos,'Realised_Fleet_Catch_Mt']*1e6,hist.loc[pos,'Total_GHG_tCO2e'])
    if 'hcr' in p:
        closed=stocks.HCR_Closed.astype(bool)
        assert (stocks.loc[closed,'Target_Catch_Mt']==0).all() and (stocks.loc[closed,'Realised_Stock_Catch_Mt']==0).all()
    hashes={}
    for name,frame in [('Annual',hist),('Stocks',stocks),('Effort',effort),('Groups',groups),('Cells',cells)]:
        frame=frame.copy()
        for col,val in meta.items():frame[col]=val
        path=folder/(name+'.csv');frame.to_csv(path,index=False);hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    marker.write_text(json.dumps(dict(Signature=signature,Parameters=p,Seed=seed,Metadata=meta,Outputs=hashes,Mass_Balance_Error_Mt=float(balance)),indent=2),encoding='utf-8')
    return key,'done'

def main_jobs():
    combos=['000','100','111','010','001','110','101','011']
    return [make_job(i,rule,combo) for combo in combos for i in range(81) for rule in ('C','F','T')]

def sensitivity_jobs():
    jobs=[]
    for i in range(81):
        for rule in ('C','F','T'):
            for combo in ('000','100','111'):jobs.append(make_job(i,rule,combo,days=280,scope='Days280'))
            jobs.append(make_job(i,rule,fraction=.8,scope='Fraction080'))
        for thresholds,label in [((.5,.2),'Threshold5020'),((.3,.05),'Threshold3005')]:
            jobs.append(make_job(i,'T',thresholds=thresholds,scope=label))
        for rule in ('C','F','T'):
            for combo in ('100','111'):
                jobs.append(make_job(i,rule,combo,scope='FixedPrices',price_assumption='fixed_2023'))
    return jobs

def legacy_jobs():
    rows=json.loads((R/'analysis/scientific_validation_20261018/Saved_Matched_Runs.json').read_text());jobs=[]
    for row in rows:
        p=copy.deepcopy(row['Parameters']);p['fishery_coupling']['stock_parameters']=str(R/'scenario/output/schaefer_projection_parameters.csv')
        m=dict(Future=row['Future'],Rule=row['Rule'],Scope='Original_CF',Original_Folder=row['Folder'])
        jobs.append((f'OriginalCF_{row["Future"]}_{row["Rule"]}',p,row['Seed'],m))
    return jobs

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace');mode=sys.argv[1] if len(sys.argv)>1 else 'main'
    jobs=main_jobs() if mode=='main' else sensitivity_jobs() if mode=='sensitivity' else legacy_jobs() if mode=='legacy' else [make_job(i,r) for i in (0,40,80) for r in ('C','F','T')]
    if mode!='pilot':
        assert 'PASS: deterministic' in (H/'order_guard.log').read_text(encoding='utf-8',errors='replace')
        validation=json.loads((H/'Pilot_QC.json').read_text())
        assert validation['Passed'] and validation.get('Input_Fingerprint')==fingerprint(),'Rerun validation after any model/input/driver change'
    inputs=fingerprint();signature=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    (H/'Run_Inputs.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
    fleet,pm,grid=load_inputs();workers=int(os.environ.get('HCR_WORKERS','16'));start=time.time();status=[]
    configure_spawn_threads()
    print('START',mode,len(jobs),'jobs',workers,'workers',flush=True)
    with Pool(workers,initializer=init_worker,initargs=(fleet,pm,grid,signature)) as pool:
        for j,(key,state) in enumerate(pool.imap_unordered(run_task,jobs,chunksize=1),1):
            status.append(dict(Key=key,Status=state))
            if j%18==0 or j==len(jobs):
                pd.DataFrame(status).to_csv(H/(mode+'_Progress.csv'),index=False)
                print(j,'/',len(jobs),'elapsed',round(time.time()-start),'seconds',key,state,flush=True)
    (H/(mode+'_Complete.json')).write_text(json.dumps(dict(Mode=mode,Jobs=len(jobs),Seconds=time.time()-start,Input_Signature=signature,Fresh=sum(x['Status']=='done' for x in status)),indent=2),encoding='utf-8')
    print('COMPLETE',mode,flush=True)
if __name__=='__main__':main()
