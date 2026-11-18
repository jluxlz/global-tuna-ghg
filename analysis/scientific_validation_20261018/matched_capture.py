"""Capture process and stock-allocation diagnostics for the current HCR simulations."""
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
