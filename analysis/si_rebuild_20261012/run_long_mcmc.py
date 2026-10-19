"""Parallel independent stock refits; safe hashes; no promotion without diagnostics."""
from pathlib import Path
import os,sys,subprocess,json,hashlib,concurrent.futures,time
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
label=sys.argv[1] if len(sys.argv)>1 else 'sampling_60000'
ni=int(sys.argv[2]) if len(sys.argv)>2 else 60000
nb=int(sys.argv[3]) if len(sys.argv)>3 else 20000
nt=int(sys.argv[4]) if len(sys.argv)>4 else 5
seed=int(sys.argv[5]) if len(sys.argv)>5 else 123
prior_mode='range' if '--range' in sys.argv else 'lnorm'
sampler='B0' if '--b0' in sys.argv else 'qK' if '--qk' in sys.argv else 'centred'
stocks=[s for s in sys.argv[6:] if s not in ['--range','--qk','--b0']] or ['SKJ','ALB','YFT','BET','SBT']
OUT=HERE/'mcmc_refits'/label;OUT.mkdir(parents=True,exist_ok=True)
worker=OUT/'worker_source.r'
if not worker.exists():worker.write_bytes((ROOT/'scenario/jabba_refit_stock.r').read_bytes())
hash_file=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
production=[ROOT/'scenario/output'/n for n in ['schaefer_biomass_annual.csv','schaefer_biomass_annual_F.csv']]
before={str(p):hash_file(p) for p in production}
RENV=Path('C:/Users/11401/Desktop/r_env/R_4.5.2')
env=os.environ.copy();env.update(R_HOME=str(RENV/'lib/R'),R_PROFILE_USER=str(ROOT/'analysis/full_chain_20261012/r_runtime_profile.R'),
 PATH=str(RENV/'lib/R/bin/x64')+os.pathsep+str(RENV/'Library/bin')+os.pathsep+env['PATH'])
def fit(stock):
    logpath=OUT/(stock+'.log');start=time.time()
    if (OUT/(stock+'_Complete.txt')).exists():
        old_log=logpath.read_text(encoding='utf-8',errors='replace')
        if f'REFIT_COMPLETE {stock}' in old_log and not any(e in old_log for e in ['Error:','Error in','Execution halted']):return dict(Stock=stock,Existing=True)
        raise RuntimeError(stock+' has an interrupted prior run; use a new isolated label')
    with logpath.open('w',encoding='utf-8') as log:
        result=subprocess.run([str(RENV/'lib/R/bin/x64/Rscript.exe'),'--no-site-file',str(worker),stock,str(OUT),str(ni),str(nb),str(nt),str(seed),prior_mode,sampler],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    text=logpath.read_text(encoding='utf-8',errors='replace')
    complete=(OUT/(stock+'_Complete.txt')).exists() and f'REFIT_COMPLETE {stock}' in text and not any(e in text for e in ['Error in','Execution halted'])
    if not complete:raise RuntimeError(stock+' incomplete: '+str(logpath))
    if result.returncode not in [0,3221225477]:raise RuntimeError(f'{stock} exit {result.returncode}')
    print(stock,'complete',round(time.time()-start),'seconds',flush=True)
    return dict(Stock=stock,Exit_Code=result.returncode,Seconds=time.time()-start)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=list(pool.map(fit,stocks))
assert before=={str(p):hash_file(p) for p in production}
(OUT/'Run_Manifest.json').write_text(json.dumps(dict(Label=label,ni=ni,nb=nb,nt=nt,nc=4,Seed=seed,K_Prior_Interpretation=prior_mode,Sampler=sampler,Prior_Data_Changed=prior_mode=='range',Worker_SHA256=hash_file(worker),Production_Hashes=before,Results=results),indent=2),encoding='utf-8')
print('All refits complete; production inputs unchanged')
