"""Boundary, legacy equivalence and execution-context checks before HCR sweeps."""
from pathlib import Path
import contextlib,io,json,sys,copy
from multiprocessing import get_context
import numpy as np
import pandas as pd
import run_hcr as E
from harvest_control_rules import target_from_rule
W={}
def init(fleet,pm,grid,threads=1):
    from threadpoolctl import threadpool_limits
    W['threadpool_guard']=threadpool_limits(limits=threads)
    import fig5_allocation as fa
    E.fm._BASE3_CACHE=grid;fa._CACHE['grid']=grid
    W.update(fleet=fleet,pm=pm)
def sim(job,end=2050):
    key,p,seed,m=job
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        return E.fm.run_scenario_simulation(W['fleet'],W['pm'],p,start_year=2025,end_year=end,random_seed=seed)[0]
def same_values(a,b):
    for c in a.select_dtypes('number').columns.intersection(b.select_dtypes('number').columns):
        np.testing.assert_allclose(a[c],b[c],rtol=1e-12,atol=1e-7,equal_nan=True,err_msg=c)
def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    assert 'PASS: deterministic' in (E.H/'order_guard.log').read_text(encoding='utf-8',errors='replace')
    cfg=dict(type='T',beta=1,b_trigger_k=.4,b_close_k=.1)
    for b in [0,1,5,10,10.0001,20,39.9999,40,50,100]:
        q,d=target_from_rule(b,.5,100,cfg)
        if b<=10:assert q==0 and d['HCR_Closed']
        if b>=40:assert q==target_from_rule(b,.5,100,{'type':'F'})[0]
        assert 0<=d['HCR_Rate_Multiplier']<=1
    for invalid in [dict(type='X'),dict(type='T',b_close_k=.5,b_trigger_k=.4),dict(type='F',beta=-1)]:
        try:target_from_rule(20,.5,100,invalid)
        except ValueError:pass
        else:raise AssertionError('Invalid rule accepted')
    fleet,pm,grid=E.load_inputs();init(fleet,pm,grid,threads=16);before=fleet.copy(deep=True)
    checks=[]
    for kind in ['C','F']:
        job=E.make_job(40,kind);a=sim(job)
        b=pd.read_csv(E.OUT/job[0]/'Annual.csv');same_values(a,b)
        old=copy.deepcopy(job);p=old[1];p.pop('hcr');p.update(quota_type=kind,schaefer_scenario={s:1. for s in E.F.MSY_FRAC})
        legacy=sim(old);same_values(a,legacy)
        for attr in ['stock_ledger','effort_ledger']:same_values(a.attrs[attr],legacy.attrs[attr])
        checks.append(kind+' explicit HCR equals existing feasible-catch rule; capture unchanged')
        print('PASS',checks[-1],flush=True)
    job=E.make_job(80,'T','111');a=sim(job)
    E.configure_spawn_threads()
    with get_context('spawn').Pool(1,initializer=init,initargs=(fleet,pm,grid)) as pool:b=pool.apply(sim,(job,))
    pd.testing.assert_frame_equal(a,b,check_exact=True)
    for attr in ['stock_ledger','effort_ledger']:pd.testing.assert_frame_equal(a.attrs[attr],b.attrs[attr],check_exact=True)
    checks.append('T-type full technical portfolio bit-identical: serial 16 BLAS threads versus spawned 1 BLAS thread')
    # Repeating after other rules must not change targets or fleet draws.
    pd.testing.assert_frame_equal(a,sim(job),check_exact=True)
    checks.append('T-type policy-order repeat bit-identical')
    # The prior price path produced negative APS HVO prices and missing support
    # vessel activity after 2040. Exercise that exact context, not only NZE.
    for mode in ('inverse_carbon','fixed_2023'):
        aa=sim(E.make_job(27,'C','100',price_assumption=mode))
        assert np.isfinite(aa.Total_GHG_tCO2e).all()
        assert np.isfinite(aa.attrs['effort_ledger'].Realised_kW_days).all()
    checks.append('Previously failing APS/HVO context has finite full-fleet GHG under both positive-price assumptions')
    zero=E.make_job(40,'C',fraction=0);z=sim(zero,end=2026)
    assert (z.Realised_Fleet_Catch_Mt==0).all() and z.CEI_tCO2e_per_t.isna().all()
    assert (z.Total_GHG_tCO2e>0).all(),'Fixed-process emissions must remain at zero catch'
    checks.append('Zero-catch boundary retains fixed GHG and undefined CEI')
    for i in (0,40,80):
        for kind in ('C','F','T'):
            folder=E.OUT/E.make_job(i,kind)[0]
            s=pd.read_csv(folder/'Stocks.csv');a=pd.read_csv(folder/'Annual.csv')
            for stock,g in s.groupby('Stock'):
                assert np.allclose(g.B_Start_Mt.to_numpy()[1:],g.B_End_Mt.to_numpy()[:-1],rtol=0,atol=0)
                r=float(pd.read_csv(E.R/'scenario/output/schaefer_projection_parameters.csv').set_index('Stock').at[stock,'r'])
                for row in g.itertuples():
                    expected,diag=target_from_rule(row.B_Start_Mt,r,row.K_Mt,{'type':kind})
                    assert np.isclose(expected,row.Target_Catch_Mt,rtol=1e-12,atol=1e-12)
    pd.testing.assert_frame_equal(fleet,before,check_exact=True)
    result=dict(Passed=True,Boundary_Checks=True,Checks=checks,Input_Fleet_Unchanged=True,Pilot_Configurations=9,Projection_Years=26,Input_Fingerprint=E.fingerprint())
    (E.H/'Pilot_QC.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
