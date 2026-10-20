"""Reproduce only 18 selected runs to expose previously unsaved process states.

Production source files and outputs are never edited. In-memory instrumentation
adds diagnostic columns after original calculations, then checks saved histories.
"""
from pathlib import Path
import sys,json,contextlib,io,inspect,hashlib,time,copy
from multiprocessing import Pool
import numpy as np
import pandas as pd
H=Path(__file__).resolve().parent;R=H.parents[1]
sys.path.insert(0,str(R/'figures/Fig5'));sys.path.insert(0,str(R/'scenario'))
import fleet_model as fm
OUT=H/'matched_capture';STATE={};ORIGINAL_PIPELINE=fm.process_fleet_dynamics_pipeline
PROCS=['GHG_Fuel_CO2','GHG_Fuel_CH4','GHG_Fuel_N2O','GHG_Fuel_WtT','GHG_Build','GHG_Refrig','Diag_Maint','Diag_Gear','Diag_Bait']

def capture_pipeline(*args,**kwargs):
    out=ORIGINAL_PIPELINE(*args,**kwargs)
    if not STATE.get('capture'):return out
    df=out[0];year=kwargs['current_year'];params=args[3];couple=params['_fishery_state']
    econ=out[4];df=df.copy()
    weight=df.get('Accounting_Weight',pd.Series(1.,index=df.index))
    for p in PROCS:df[p]=df[p]*weight
    assert np.allclose(df[PROCS].sum(axis=1),df.GHG_Emissions,rtol=1e-11,atol=1e-8),'Process closure'
    df['Variable_GHG']=df[['GHG_Fuel_CO2','GHG_Fuel_CH4','GHG_Fuel_N2O','GHG_Fuel_WtT','Diag_Bait']].sum(axis=1)
    df['Fixed_GHG']=df[['GHG_Build','GHG_Refrig','Diag_Maint','Diag_Gear']].sum(axis=1)
    df['Weighted_Power']=df.Power_kW*weight
    df['Actual_kW_days']=df.Power_kW*econ.loc[df.index,'Operating_Days']*weight
    df['Fuel_t']=df.Diag_Fuel_t*weight
    for (org,gear),g in df.groupby(['Organization','VesselType']):
        entry=dict(Year=year,Organization=org,Gear=gear,N_Vessels=len(g),Active_N=int((g.Actual_kW_days>0).sum()),
                   Power_kW=g.Weighted_Power.sum(),Realised_kW_days=g.Actual_kW_days.sum(),GHG_t=g.GHG_Emissions.sum(),
                   Variable_GHG_t=g.Variable_GHG.sum(),Fixed_GHG_t=g.Fixed_GHG.sum(),Fuel_t=g.Fuel_t.sum(),Mean_Age=g.Age.mean(),Mean_LOA=g.LOA.mean())
        entry.update({p:float(g[p].sum()) for p in PROCS});STATE['groups'].append(entry)
        if gear in ('LL','PS'):
            total_d=couple.demand.get((org,gear),0.)
            for stock in couple.stocks.index:
                ds=couple.demand_s.get((stock,org,gear),0.);share=ds/total_d if total_d>0 else 0.
                STATE['cells'].append(dict(Year=year,Organization=org,Gear=gear,Stock=stock,
                    Catch_t=couple.catch_sg.get((stock,org,gear),0.)*1e6,Required_kW_days=ds,
                    Realised_kW_days=entry['Realised_kW_days']*share,Variable_GHG_t=entry['Variable_GHG_t']*share,
                    Allocation_Share=share))
    if STATE['future']=='F41' and year in (2025,2035,2050):
        keep=['Organization','VesselType','Power_kW','LOA','Age','GHG_Emissions','Actual_kW_days','Variable_GHG','Fixed_GHG']
        v=df[keep].copy();v['Year']=year;STATE['vessels'].append(v)
    return out

def init_worker(fleet,pm):
    STATE.update(fleet=fleet,pm=pm,capture=False)
    source=inspect.getsource(fm.compute_fleet_ghg)
    needle='    df["Fuel_Label"] = sfc_label'
    assert source.count(needle)==1
    insert='''    _diag_sf = _sf if _fac else np.ones(n)
    df["Diag_Maint"] = maint * _diag_sf
    df["Diag_Gear"] = gear * _diag_sf
    df["Diag_Bait"] = bait * _diag_sf
    df["Diag_Fuel_t"] = fuel_total_t * _diag_sf
'''
    exec(compile(source.replace(needle,insert+needle),'<isolated_process_capture>','exec'),fm.__dict__)
    fm.process_fleet_dynamics_pipeline=capture_pipeline

def task(item):
    future=item['Future'];rule=item['Rule'];folder=OUT/(future+'_'+rule);folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'Complete.json'
    # Saved parameter records retain the author's original paths. Always bind
    # this global-stock diagnostic to the provided local frozen stock table.
    params=copy.deepcopy(item['Parameters'])
    params['fishery_coupling']['stock_parameters']=str(R/'scenario/output/schaefer_projection_parameters.csv')
    from scenario_seeds import simulation_fingerprint
    fingerprint=dict(inputs=simulation_fingerprint(),params=params,seed=item['Seed'],
                     capture_source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     stocks=hashlib.sha256(Path(params['fishery_coupling']['stock_parameters']).read_bytes()).hexdigest())
    signature=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
    if marker.exists():
        saved=json.loads(marker.read_text())
        if saved.get('signature')==signature and saved.get('outputs') and all(
            (folder/name).is_file() and hashlib.sha256((folder/name).read_bytes()).hexdigest()==value
            for name,value in saved['outputs'].items()):return future,rule,'reused'
    STATE.update(capture=True,future=future,groups=[],cells=[],vessels=[])
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        hist,last=fm.run_scenario_simulation(STATE['fleet'],STATE['pm'],params,start_year=2025,end_year=2050,random_seed=item['Seed'])
    STATE['capture']=False
    original=R/item['Folder'];old=pd.read_csv(original/'Annual.csv');errors={}
    for c in ['Total_GHG_tCO2e','Realised_Fleet_Catch_Mt','N_Vessels','Total_Power_kW']:
        assert np.allclose(hist[c],old[c],rtol=1e-12,atol=1e-7),(future,rule,c,float(np.max(np.abs(hist[c]-old[c]))))
        errors[c]=float(np.max(np.abs(hist[c]-old[c])))
    groups=pd.DataFrame(STATE['groups']);cells=pd.DataFrame(STATE['cells'])
    annual=groups.groupby('Year').GHG_t.sum()
    assert np.allclose(annual,hist.set_index('Year').Total_GHG_tCO2e,rtol=1e-12)
    assert np.allclose(cells.groupby('Year').Catch_t.sum(),hist.set_index('Year').Realised_Fleet_Catch_Mt*1e6,rtol=1e-11)
    for name,data in [('Annual',hist),('Stocks',hist.attrs['stock_ledger']),('Effort',hist.attrs['effort_ledger']),('Groups',groups),('Cells',cells)]:
        data.to_csv(folder/(name+'.csv'),index=False)
    if STATE['vessels']:pd.concat(STATE['vessels'],ignore_index=True).to_csv(folder/'Central_Vessel_States.csv',index=False)
    names=['Annual.csv','Stocks.csv','Effort.csv','Groups.csv','Cells.csv']
    if STATE['vessels']:names.append('Central_Vessel_States.csv')
    hashes={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in names}
    marker.write_text(json.dumps(dict(original=str(original.relative_to(R)),seed=item['Seed'],params=params,signature=signature,outputs=hashes,reproduction_max_errors=errors,
        boundary='Species allocation applies only to LL/PS activity-scalable fuel and bait, by actual effort partitions. Vessel materials, gear and leakage stay unallocated; support vessels separately reported.'),indent=2),encoding='utf-8')
    return future,rule,errors['Total_GHG_tCO2e']

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace');OUT.mkdir(exist_ok=True)
    runs=json.loads((H/'Saved_Matched_Runs.json').read_text(encoding='utf-8'))
    # Saved outputs are inspected before any rerun.
    records=[]
    for row in runs:
        a=pd.read_csv(R/row['Folder']/'Annual.csv');a['Rule']=row['Rule'];a['Future']=row['Future'];records.append(a)
    old=pd.concat(records,ignore_index=True);old.to_csv(H/'analysis/Matched_Saved_Annual.csv',index=False)
    if len(sys.argv)>1 and sys.argv[1]=='saved':
        print(old.groupby(['Future','Rule'])[['Total_GHG_tCO2e','Realised_Fleet_Catch_Mt']].sum().to_string());return
    if len(sys.argv)>1 and sys.argv[1]=='pilot':runs=[x for x in runs if x['Future']=='F41']
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=fm.load_baseline_fleet()
    t=time.time()
    with Pool(4,initializer=init_worker,initargs=(fleet,pm)) as pool:
        for result in pool.imap_unordered(task,runs):print(result,'seconds',round(time.time()-t),flush=True)
    print('MATCHED_CAPTURE_COMPLETE',len(runs),flush=True)
if __name__=='__main__':main()
