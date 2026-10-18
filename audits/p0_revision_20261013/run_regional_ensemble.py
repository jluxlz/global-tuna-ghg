"""Regional conditional component: full 81 futures, five policy comparisons."""
import sys,itertools,contextlib,io,json,time
from multiprocessing import Pool
import pandas as pd
import run_ensemble as E

def main():
    futures=list(itertools.product(E.F.BAU_WEO,E.F.BAU_GROWTH,E.F.BAU_RETIRE.values(),E.F.BAU_TECH))
    ff=json.loads((E.ROOT/'scenario/output/fig5/Fig5_Final_Fuel.json').read_text())
    config=E.OUT.parent/'regional_inputs'
    stock=sys.argv[1] if len(sys.argv)>1 else 'BET'
    weights=json.loads((config/f'{stock}_Fleet_Weights.json').read_text())
    tasks=[]
    for i,(weo,growth,ret,tc) in enumerate(futures):
        for combo in ['0000','1000','0100','1111','C_type','F80']:
            p=E.F.make_params(weo=weo,growth=growth,tc=tc,ret=int(ret),forced=0)
            if combo in ('1000','1111','C_type'):
                p.update(schaefer_scenario={stock:'MSY_100'},quota_type='C' if combo=='C_type' else 'F')
            if combo=='F80':p.update(schaefer_scenario={stock:'MSY_80'},quota_type='F')
            if combo in ('0100','1111'):p.update(ff[weo])
            if combo=='1111':p.update(refrigerant_type='LN2',consolidation_type=2)
            p['fishery_coupling']=dict(stock_parameters=str(config/f'{stock}_Projection_Parameters.csv'),
               allocation_file=str(config/f'{stock}_Catch_Allocation.csv'),max_operating_days=365)
            meta=dict(Future=f'F{i+1:02}',WEO=weo,Growth=growth,Retirement=int(ret),TechCreep=tc,Combo=combo,Max_Days=365,Scope=f'IOTC_{stock}',Reference_State_Year=2024 if stock=='BET' else 2020)
            tasks.append((f'Regional_{stock}_F{i+1:02}_{combo}',p,42+i,meta))
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=E.fm.load_baseline_fleet()
    fleet=fleet[fleet.Organization=='IOTC'].copy()
    fleet['Accounting_Weight']=fleet.VesselType.map(weights).fillna(weights['Support'])
    print('REGIONAL',len(tasks),'simulations; conditional fleet weights',weights,flush=True)
    with Pool(2,initializer=E.init_worker,initargs=(fleet,pm)) as pool:
        for j,(key,status) in enumerate(pool.imap_unordered(E.task,tasks),1):
            if j%25==0:print(j,'/',len(tasks),flush=True)
    pd.concat([pd.read_csv(E.OUT/k/'Annual.csv',dtype={'Combo':str}) for k,p,s,m in tasks],ignore_index=True).to_csv(E.OUT/f'Regional_{stock}_All_Annual.csv',index=False)
    pd.concat([pd.read_csv(E.OUT/k/'Stocks.csv',dtype={'Combo':str}) for k,p,s,m in tasks],ignore_index=True).to_csv(E.OUT/f'Regional_{stock}_All_Stocks.csv',index=False)
    print('REGIONAL_COMPLETE',flush=True)

if __name__=='__main__':main()
