"""Independently rerun fixed-quota fractions; never rescale GHG outputs."""
import sys,itertools,contextlib,io,json,time
from pathlib import Path
from multiprocessing import Pool
import pandas as pd
import run_ensemble as E

def main():
    futures=list(itertools.product(E.F.BAU_WEO,E.F.BAU_GROWTH,E.F.BAU_RETIRE.values(),E.F.BAU_TECH))
    tasks=[]
    # Nine prespecified WEO x technology contrasts at central fleet growth,
    # renewal retirement. The comparison is conditional, not an 81-future rank.
    for i,(weo,growth,ret,tc) in enumerate(futures):
        if growth!=E.F.BAU_GROWTH[1] or ret!=2:continue
        for fraction in [.35,.5,.65,.8,.9,1.,1.1,1.25]:
            p=E.F.make_params(weo=weo,growth=growth,tc=tc,ret=ret,forced=0,quota_type='C')
            p['schaefer_scenario']={s:fraction*(.7 if s=='SBT' else 1.) for s in E.F.MSY_FRAC}
            p['fishery_coupling']=dict(stock_parameters=str(E.ROOT/'scenario/output/schaefer_projection_parameters.csv'),max_operating_days=365)
            meta=dict(Future=f'F{i+1:02}',WEO=weo,Growth=growth,Retirement=int(ret),TechCreep=tc,Combo='Matched_C',Max_Days=365,Quota_Fraction=fraction)
            tasks.append((f'Matched_F{i+1:02}_{fraction}',p,42+i,meta))
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=E.fm.load_baseline_fleet()
    t=time.time();print('MATCHED_CATCH_RERUNS',len(tasks),flush=True)
    with Pool(3,initializer=E.init_worker,initargs=(fleet,pm)) as pool:
        for j,(key,status) in enumerate(pool.imap_unordered(E.task,tasks),1):
            if j%12==0:print(j,'/',len(tasks),'seconds',round(time.time()-t),flush=True)
    pd.concat([pd.read_csv(E.OUT/k/'Annual.csv') for k,p,s,m in tasks],ignore_index=True).to_csv(E.OUT/'Matched_Catch_Annual.csv',index=False)
    print('MATCHED_COMPLETE',flush=True)

if __name__=='__main__':main()
