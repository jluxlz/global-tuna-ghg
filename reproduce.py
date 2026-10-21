"""Offline reproduction from supplied accepted vessel and model inputs.

Live registry/query websites are not called. Full model stages may take hours.
Use --refit-stocks to regenerate JABBA fits instead of the frozen fitted inputs.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reproduction_logs'

def verify():
    required=('vessel_data_extract/Unified_Vessel_Registry.csv',
      'PMM_Imputation/After_PMM_Vessels.csv','effort_data/Share5_Lookup_FlagGearYear.csv',
      'effort_data/Grid_Catch_Allocation.csv','model_parameters/Prior_Matrix.csv',
      'model_parameters/Scenario_Fuel_Parameters.xlsx',
      'model_parameters/Scenario_Fuel_Price_Matrix.xlsx',
      'GHG_Calculation/TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv',
      'scenario/output/schaefer_biomass_annual.csv',
      'scenario/output/schaefer_biomass_annual_F.csv',
      'scenario/output/schaefer_projection_parameters.csv')
    missing=[x for x in required if not (ROOT/x).is_file()]
    if missing:raise FileNotFoundError('Restore release data first. Required inputs missing: '+', '.join(missing))
    for x in json.loads((ROOT/'data/frozen_inputs.json').read_text(encoding='utf-8')):
        p=ROOT/x['Path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=x['SHA256']:
            raise RuntimeError('Frozen input differs from release: '+x['Path'])
    print('Frozen input verification passed. No live scraping is required.',flush=True)

def run(label,cmd,cwd=ROOT):
    OUT.mkdir(exist_ok=True)
    with (OUT/(label+'.log')).open('w',encoding='utf-8') as log:
        print('Running',label,'; log:',str(OUT/(label+'.log')),flush=True)
        result=subprocess.run(cmd,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(label+' failed; inspect '+str(OUT/(label+'.log')))

def rscript():
    config_path=ROOT/'reproduction_config.json'
    config=json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    env=config.get('environment',{})
    for key in ('R_HOME','RSCRIPT'):
        if env.get(key):os.environ.setdefault(key,env[key])
    if config.get('path_prefixes'):
        os.environ['PATH']=os.pathsep.join(config['path_prefixes'])+os.pathsep+os.environ['PATH']
    exe=os.environ.get('RSCRIPT') or shutil.which('Rscript')
    if not exe:raise RuntimeError('Install R dependencies and put Rscript on PATH, or set RSCRIPT.')
    return exe

def figures():
    rscript()
    scripts=['figures/Fig1/Fig1_Multi_Dimensional.r','figures/Fig2/Fig2_Spatial_Temporal_CEI.r',
      'figures/Fig3/Fig3_Phase_Decoupling.r','figures/Fig4/Fig4_Coupled_Mechanisms.r',
      'figures/Fig5/plot_fig5.r']
    scripts += [f"figures/Extended_Data/Extended_Fig{n}/{name}" for n,name in {
      3:'Extended_Fig3.r',4:'Extended_Fig4_Decomposition.r',5:'Extended_Fig5_Stock_Structure_Robustness.r',
      6:'Extended_Fig6_Economic_Elasticity_Sensitivity.r',7:'Extended_Fig7_Technology_Creep_Robustness.r',
      8:'Extended_Fig8_Subsidy_Buffer.r',9:'Extended_Fig9_BreakEven_Cutoff.r',
      10:'Extended_Fig10_Shapley_Abatement_Decomposition.r'}.items()]
    for i,script in enumerate(scripts):run('figure_'+str(i+1),[sys.executable,str(ROOT/'analysis/full_chain_20261012/render_single.py'),script])
    run('si_figures',[sys.executable,str(ROOT/'figures/supplement/render_all.py')])

def scenarios(extras):
    hcr=ROOT/'analysis/hcr_revision_20261020'
    run('order_regression',[sys.executable,str(ROOT/'scenario/regression_check_order_dependence.py')])
    shutil.copy2(OUT/'order_regression.log',hcr/'order_guard.log')
    run('execution_context',[sys.executable,str(ROOT/'scenario/regression_check_execution_context.py')])
    os.environ.setdefault('HCR_WORKERS','4')
    run('hcr_pilot',[sys.executable,str(hcr/'run_hcr.py'),'pilot'])
    run('hcr_validation',[sys.executable,str(hcr/'validate.py')])
    run('hcr_primary',[sys.executable,str(hcr/'run_hcr.py'),'main'])
    run('hcr_sensitivities',[sys.executable,str(hcr/'run_hcr.py'),'sensitivity'])
    run('original_cf_comparator',[sys.executable,str(hcr/'run_hcr.py'),'legacy'])
    if extras:
        run('hcr_catch_matching',[sys.executable,str(hcr/'match_hcr.py')])
        for stock in ('BET','YFT'):
            run('regional_'+stock,[sys.executable,str(ROOT/'analysis/p0_revision_20261013/run_regional_ensemble.py'),stock])
        run('regional_summaries',[sys.executable,str(ROOT/'analysis/p0_revision_20261013/analyse_regional.py')])
    run('hcr_summaries',[sys.executable,str(hcr/'analyse_hcr.py')])


def refresh():
    scripts=[
      'figures/Fig2/preprocess_fig2.py','figures/Fig3/preprocess_fig3.py',
      'figures/Fig4/preprocess_fig4.py','figures/Fig5/prepare_hcr_panels.py',
      'figures/Extended_Data/Extended_Fig7/prepare_hcr.py',
      'figures/Extended_Data/Extended_Fig9/prepare_hcr.py',
      'figures/Extended_Data/Extended_Fig10/prepare_hcr.py',
      'figures/supplement/Supplementary_Fig8/prepare_hcr.py',
      'figures/supplement/Supplementary_Fig13/prepare_hcr.py',
      'figures/supplement/Supplementary_Fig16/prepare_hcr.py',
      'figures/supplement/Supplementary_Fig18/prepare_hcr.py',
      'figures/supplement/Supplementary_Fig21/prepare_hcr.py']
    for i,script in enumerate(scripts):run('refresh_'+str(i+1),[sys.executable,str(ROOT/script)])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['verify','historical','stocks','scenarios','refresh','figures','all'])
    p.add_argument('--refit-stocks',action='store_true',help='Run the full configured JABBA chains; default all reuses frozen stock fits.')
    p.add_argument('--extra-experiments',action='store_true',help='Also rerun regional and iterative matched-catch experiments.')
    a=p.parse_args();verify()
    if a.stage in ('historical','all'):run('historical_lca',[sys.executable,'-u',str(ROOT/'GHG_Calculation/ghg_lca.py')],ROOT/'GHG_Calculation')
    if a.stage=='stocks' or (a.stage=='all' and a.refit_stocks):run('jabba_fits',[rscript(),str(ROOT/'scenario/jabba_fit.r')])
    if a.stage in ('scenarios','all'):scenarios(a.extra_experiments)
    if a.stage in ('refresh','all'):refresh()
    if a.stage in ('figures','all'):figures()
    print('Completed',a.stage,flush=True)

if __name__=='__main__':main()
