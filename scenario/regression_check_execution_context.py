"""Guard serial/spawn equivalence of fuel initialization and fleet sampling."""
from pathlib import Path
import contextlib, io, json, sys
from multiprocessing import get_context
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scenario'),str(ROOT/'figures/Fig5')]
import fleet_model as fm
import fig5_run as F
W={}
def init(fleet,pm): W.update(fleet=fleet,pm=pm)
def simulate(job):
    i,combo,coupled=job
    from scenario_seeds import FUTURES,paired_seed
    w,g,r,t=FUTURES[i]
    p=F.make_params(weo=w,growth=g,tc=t,ret=r,forced=0)
    if combo=='1111':
        p.update(json.loads((Path(F.OUT)/'Fig5_Final_Fuel.json').read_text())[w])
        p.update(quota_type=json.loads((Path(F.OUT)/'Fig5_Final_Quota.json').read_text()),
                 schaefer_scenario=dict(F.MSY_FRAC),refrigerant_type='LN2',consolidation_type=2)
    if coupled:p['fishery_coupling']=dict(stock_parameters=str(ROOT/'scenario/output/schaefer_projection_parameters.csv'),max_operating_days=365)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        return fm.run_scenario_simulation(W['fleet'],W['pm'],p,start_year=2025,end_year=2050,random_seed=paired_seed(FUTURES[i]))[0]
def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=fm.load_baseline_fleet()
    init(fleet,pm)
    jobs=[(80,'1111',True),(80,'0000',True),(40,'1111',True),(80,'1111',False)]
    before=fleet.copy(deep=True)
    serial=[simulate(j) for j in jobs]
    with get_context('spawn').Pool(1,initializer=init,initargs=(fleet,pm)) as pool:
        spawned=pool.map(simulate,jobs)
    for j,a,b in zip(jobs,serial,spawned):
        pd.testing.assert_frame_equal(a,b,check_exact=True)
        for key in ['stock_ledger','effort_ledger']:
            if key in a.attrs:pd.testing.assert_frame_equal(a.attrs[key],b.attrs[key],check_exact=True)
        print('PASS serial/spawn bit-identical:',j,flush=True)
    # Deliberately perturb a process-local property to ensure entry points
    # restore workbook values before evaluating the scenario.
    fm.FUEL_DATABASE['NH3_Green']=(np.nextafter(18.6,0),0.,0.,0.)
    pd.testing.assert_frame_equal(serial[0],simulate(jobs[0]),check_exact=True)
    pd.testing.assert_frame_equal(before,fleet,check_exact=True)
    print('PASS: execution-context equivalence and input fleet preservation',flush=True)
if __name__=='__main__':main()
