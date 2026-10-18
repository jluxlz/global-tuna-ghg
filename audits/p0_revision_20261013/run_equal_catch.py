"""Tune F quotas by repeated full reruns to match a C-type catch total."""
import itertools,contextlib,io,time,json
from multiprocessing import Pool
import pandas as pd
import run_ensemble as E

def match_one(item):
    i,weo,growth,ret,tc=item
    c=pd.read_csv(E.OUT/f'Matched_F{i+1:02}_0.65/Annual.csv')
    target=float(c.Realised_Fleet_Catch_Mt.sum());cghg=float(c.Total_GHG_tCO2e.sum())
    lo,hi=.15,1.;trials=[]
    for step in range(9):
        fraction=(lo+hi)/2
        p=E.F.make_params(weo=weo,growth=growth,tc=tc,ret=ret,forced=0,quota_type='F')
        p['schaefer_scenario']={s:fraction*(.7 if s=='SBT' else 1.) for s in E.F.MSY_FRAC}
        p['fishery_coupling']=dict(stock_parameters=str(E.ROOT/'scenario/output/schaefer_projection_parameters.csv'),max_operating_days=365)
        meta=dict(Future=f'F{i+1:02}',WEO=weo,Growth=growth,Retirement=ret,TechCreep=tc,Combo='Equal_Catch_F',Max_Days=365,Quota_Fraction=fraction)
        key=f'EqualCatch_F{i+1:02}_trial{step}'
        E.task((key,p,42+i,meta))
        h=pd.read_csv(E.OUT/key/'Annual.csv');catch=float(h.Realised_Fleet_Catch_Mt.sum());ghg=float(h.Total_GHG_tCO2e.sum())
        gap=catch/target-1
        trials.append(dict(Future=f'F{i+1:02}',Trial=step,F_Fraction=fraction,C_Fraction=.65,C_Catch_Mt=target,F_Catch_Mt=catch,
             C_GHG_Mt=cghg/1e6,F_GHG_Mt=ghg/1e6,Relative_Catch_Gap=gap,GHG_Reduction_pct=100*(1-ghg/cghg),
             CEI_Reduction_pct=100*(1-(ghg/catch)/(cghg/target)),Within_1pct=abs(gap)<=.01))
        if abs(gap)<=.01:break
        if gap>0:hi=fraction
        else:lo=fraction
    return trials

def main():
    grid=list(itertools.product(E.F.BAU_WEO,E.F.BAU_GROWTH,E.F.BAU_RETIRE.values(),E.F.BAU_TECH))
    items=[(i,*x) for i,x in enumerate(grid) if x[1]==E.F.BAU_GROWTH[1] and x[2]==2]
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=E.fm.load_baseline_fleet()
    allrows=[];t=time.time()
    with Pool(4,initializer=E.init_worker,initargs=(fleet,pm)) as pool:
        for rows in pool.imap_unordered(match_one,items):
            allrows.extend(rows);print(rows[-1]['Future'],'gap',rows[-1]['Relative_Catch_Gap'],'seconds',round(time.time()-t),flush=True)
    d=pd.DataFrame(allrows);d.to_csv(E.OUT/'Equal_Catch_Trials.csv',index=False)
    final=d.sort_values('Trial').groupby('Future').tail(1)
    final.to_csv(E.OUT/'Equal_Catch_Matched.csv',index=False)
    print(final.to_string(index=False),flush=True)

if __name__=='__main__':main()
