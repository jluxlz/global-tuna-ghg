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
    guard=ROOT/'analysis/paired_seed_revision_20261016/order_regression_final.log'
    guard.parent.mkdir(exist_ok=True)
    run('order_regression',[sys.executable,str(ROOT/'scenario/regression_check_order_dependence.py')])
    shutil.copy2(OUT/'order_regression.log',guard)
    # Both four-measure factorial drivers use common within-future seeds.
    run('fixed_target',[sys.executable,str(ROOT/'figures/Fig5/fig5_paired_rerun.py'),'full'])
    run('feasible_catch',[sys.executable,str(ROOT/'analysis/p0_revision_20261013/run_ensemble.py'),'full'])
    if extras:
        run('fixed_quota_matching',[sys.executable,str(ROOT/'analysis/p0_revision_20261013/run_matched_catch.py')])
        run('adjusted_rate_matching',[sys.executable,str(ROOT/'analysis/p0_revision_20261013/run_equal_catch.py')])
        for stock in ('BET','YFT'):run('regional_'+stock,[sys.executable,str(ROOT/'analysis/p0_revision_20261013/run_regional_ensemble.py'),stock])
    run('feasible_summary',[sys.executable,str(ROOT/'analysis/p0_revision_20261013/analyse_ensemble.py')])
    run('fixed_shapley',[sys.executable,str(ROOT/'figures/Extended_Data/Extended_Fig10/Extended_Fig10_shapley.py')])

def refresh():
    run('fig2_bridge',[sys.executable,str(ROOT/'figures/Fig2/preprocess_fig2.py')])
    run('fig3_bridge',[sys.executable,str(ROOT/'figures/Fig3/preprocess_fig3.py')])
    run('fig4_bridge',[sys.executable,str(ROOT/'figures/Fig4/preprocess_fig4.py')])
    run('fig5_bridge',[sys.executable,str(ROOT/'figures/Fig5/prepare_story_panels.py')])

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
