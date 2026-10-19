"""Refresh dependent panel bridges without replacing approved R figure styles."""
from pathlib import Path
import pandas as pd, json, shutil, subprocess
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;OUT=ROOT/'figures/supplement'
def save(d,n,label):d.to_csv(OUT/f'Supplementary_Fig{n}'/f'Supplementary_Fig{n}_{label}.csv',index=False)
bau=pd.read_csv(ROOT/'scenario/output/fig5/BAU_81_Annual.csv')
save(bau.groupby('Year').GHG_Mt.quantile([.05,.25,.5,.75,.95]).unstack().reset_index().rename(columns={.05:'p5',.25:'p25',.5:'Median',.75:'p75',.95:'p95'}),13,'PanelB_Scenarios')
save(pd.read_csv(ROOT/'figures/Fig4/Fig4_PanelE_Intensity.csv'),9,'PanelA_Fuel_Intensity')
fuel=json.loads((ROOT/'scenario/output/fig5/Fig5_Final_Fuel.json').read_text())
nodes=[dict(WEO=w,Fuel=x['biofuel_type'] if key=='biofuel_nodes' else x['newfuel_type'],Path='Drop-in blend' if key=='biofuel_nodes' else 'Newbuild fuel',Year=int(y),Share=s) for w,x in fuel.items() for key in ['biofuel_nodes','newfuel_nodes'] for y,s in x[key].items()]
save(pd.DataFrame(nodes),9,'PanelB_Adoption')
cf=pd.read_csv(ROOT/'scenario/output/schaefer_biomass_annual_F.csv');qrows=[]
# Fractions are the prescribed precautionary SBT setting used by the fleet model.
for s in ['SKJ','YFT','BET','ALB','SBT']:
    fraction=.7 if s=='SBT' else 1.;sc=f'MSY_{round(100*fraction)}'
    t=cf[(cf.Stock==s)&(cf.Scenario==sc)&(cf.Year==2050)].iloc[0]
    qrows.append(dict(Species=s,Fraction_FMSY=fraction,Biomass_K_2050=t.Biomass_Mt/t.K_Mt,Quota_Ratio_2050=t.quota_ratio))
save(pd.DataFrame(qrows),11,'PanelA_Choices')
shutil.copy2(ROOT/'scenario/output/fig5/Fig5_Quota_Species_Meco.csv',OUT/'Supplementary_Fig11/Quota_Screen_Source.csv')
save(pd.read_csv(ROOT/'figures/Fig5/Fig5_PanelD_Org_Summary.csv'),16,'PanelA_Organizations')
ed=ROOT/'figures/Extended_Data/Extended_Fig5'
shutil.copy2(ed/'Extended_Fig5_PanelB_CPUE_Fits.csv',OUT/'Supplementary_Fig6/Supplementary_Fig6_PanelA_Fits.csv')
shutil.copy2(ed/'Extended_Fig5_MCMC_Traces.csv',OUT/'Supplementary_Fig7/Supplementary_Fig7_PanelA_Traces.csv')
shutil.copy2(ed/'Extended_Fig5_Diagnostic_Summary.csv',OUT/'tables/JABBA_Production_Diagnostic_Summary.csv')
shutil.copy2(ROOT/'scenario/jabba_sampler_config.csv',OUT/'tables/JABBA_Sampling_Configuration.csv')
shutil.copy2(HERE/'Independent_Seed_Summary.csv',OUT/'tables/JABBA_Independent_Seed_Summary.csv')
for n in [13,9,11,16,6,7]:
    subprocess.run(['C:/CONDA/python',str(ROOT/'analysis/full_chain_20261012/render_single.py'),f'figures/supplement/Supplementary_Fig{n}/Supplementary_Fig{n}.r'],cwd=ROOT,check=True)
print('Dependent supplemental panels refreshed')
