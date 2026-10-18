"""Read-only diagnosis. Saved production estimates stay authoritative.

Replay 500 draws over 2023-25 solely to expose engine contributions. Shortening
the simulation window changes the RNG consumption, so this is explicitly a
diagnostic replay, not a replacement of the preserved historical Monte Carlo.
"""
from pathlib import Path
import sys,inspect,json,hashlib
import pandas as pd
import numpy as np
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
H=Path(__file__).resolve().parent;R=H.parents[1]
sys.path.insert(0,str(R/'GHG_Calculation'))
import ghg_lca as h

def main():
 inputs=[R/'GHG_Calculation'/x for x in ['ghg_lca.py','Base_2_Fleet_GHG.csv','Ghost_Fleet_Reconstructed.csv']]
 inputs += [R/'model_parameters/Prior_Matrix.csv']
 hashes={str(p.relative_to(R)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in inputs}
 pm=h.load_prior_matrix(h.PRIOR_MATRIX_PATH)
 df,pools=h.run_imputation_pipeline(h.VESSEL_REGISTRY_PATH,pm,write_output=False)
 df=h.impute_builtdate_deterministic(h.convert_gt_to_lsw(df,pm),pools)
 df['Retire_Year']=9999;df['Is_Ghost']=0
 ghost=pd.read_csv(R/'GHG_Calculation/Ghost_Fleet_Reconstructed.csv')
 df=h.assign_operational_params(df,pm)
 ghost=h.assign_operational_params(ghost,pm)
 df=pd.concat([df,ghost],ignore_index=True)
 alpha_lookup=h.init_time_profile_lookup(h.PNAS_POWER_PATH,verbose=False)
 alpha23=h.query_alpha_work_vectorized(df.Flag.to_numpy(),df.VesselType.to_numpy(),df.Length.to_numpy(),np.full(len(df),2023),alpha_lookup,sectors=df.Sector.to_numpy())
 alpha_first=h.query_alpha_work_vectorized(df.Flag.to_numpy(),df.VesselType.to_numpy(),df.Length.to_numpy(),np.full(len(df),int(df.Builtdate.min())),alpha_lookup)
 scope=pd.read_csv(R/'figures/supplement/Supplementary_Fig14/Matched_Flag_Gear_Sector_Audit.csv')
 scope=scope[scope.Benchmark_ID=='LL23'].copy()
 cf={'I':3.206,'APW':3.158};rho={'I':.830565,'APW':.746269}
 scope['Production_Fuel_L']=scope.Fuel_CO2_scope/scope.Sector.map(cf)*1000/scope.Sector.map(rho)
 b3=pd.read_csv(R/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv',usecols=['Year','Flag','Gear','Organization','Total_Catch','GHG_emissions_median','SKJ_Tonnes','YFT_Tonnes','BET_Tonnes','ALB_Tonnes'])
 s=b3[(b3.Year==2023)&(b3.Gear=='LL')&b3.Organization.isin(['WCPFC','IATTC'])&(b3.Total_Catch>0)&(b3.GHG_emissions_median>0)].copy()
 s['Matched_Catch_t']=s[['SKJ_Tonnes','YFT_Tonnes','BET_Tonnes','ALB_Tonnes']].sum(axis=1)
 catches=s.groupby('Flag',as_index=False).Matched_Catch_t.sum()
 flags=scope.groupby('Flag',as_index=False).Production_Fuel_L.sum().merge(catches,on='Flag',validate='one_to_one')
 flags['Production_FUI_L_t']=flags.Production_Fuel_L/flags.Matched_Catch_t
 flags['Fuel_share_pct']=100*flags.Production_Fuel_L/flags.Production_Fuel_L.sum()
 flags['Catch_share_pct']=100*flags.Matched_Catch_t/flags.Matched_Catch_t.sum()
 flags.sort_values('Production_Fuel_L',ascending=False).to_csv(H/'LL23_Flag_Attribution.csv',index=False)
 w=df[['Flag','VesselType','Sector']].rename(columns={'VesselType':'Gear'}).merge(scope[['Flag','Gear','Sector','Scope_share']],how='left',on=['Flag','Gear','Sector'],validate='many_to_one').Scope_share.fillna(0).to_numpy()
 current=(df.Builtdate<=2023)&(df.Retire_Year>2023)&(w>0)
 cohort=df.loc[current,['Flag','VesselType','Sector','Builtdate','Length','Enginepower','T_map','H_main','H_aux','AUX_Ratio','Is_Ghost']].copy()
 cohort['Age_2023']=2023-cohort.Builtdate
 cohort['Scope_share']=w[current]
 cohort['Alpha_production']=alpha_first[current];cohort['Alpha_2023']=alpha23[current]
 cohort.to_csv(H/'LL23_Model_Eligible_Cohort.csv',index=False)
 # Instrument an in-memory copy; production source is not edited or executed as a CLI.
 source=inspect.getsource(h.run_monte_carlo_lca)
 insert='''            if year == 2023:
                aw = np.clip(_alpha23 * mul["Alpha"], 0., 1.)
                base = np.vstack([fuel_t_move, fuel_t_work, fuel_t_aux])
                alt_alpha = (P_main * lf_move_m * sfc_m_move * (1-aw) * total_days * H_main_day + P_main * lf_work_m * sfc_m_work * aw * total_days * H_main_day + P_aux * lf_aux_m * sfc_a * hours_aux) * fc_array * active_mask
                volumes = base * (sf * _scope * 1000 / _rho)[None,:]
                cap_factor = np.minimum(1., 365. / total_days)
                _diag.append(np.r_[volumes.sum(axis=1), (alt_alpha * sf * _scope * 1000 / _rho).sum(), volumes[:, _age30].sum(), volumes[:, _ghostmask].sum(), (volumes * cap_factor[None,:]).sum(), volumes[:, total_days > 365.].sum(), mul["T_map"]])
'''
 needle='            fuel_co2 *= sf'
 assert source.count(needle)==1
 source=source.replace(needle,insert+needle)
 g=h.__dict__.copy();g.update(_alpha23=alpha23,_scope=w,_rho=df.Sector.map(rho).to_numpy(),_diag=[],_age30=(2023-df.Builtdate.to_numpy()>30),_ghostmask=df.Is_Ghost.fillna(0).to_numpy()==1)
 exec(compile(source,'<read_only_fuel_diagnostic>','exec'),g)
 top=pd.read_csv(R/'GHG_Calculation/GSA_Per_Process_Top2.csv')
 important=set(top.Top1)|set(top.Top2)
 g['run_monte_carlo_lca'](df,pm,end_year=2025,start_year=2023,n_simulations=500,random_seed=42,lookup_data_power=h.init_power_discount_lookup(h.PNAS_POWER_PATH,baseline_year=2015),lookup_data_alpha=alpha_lookup,important_params=important)
 draws=pd.DataFrame(g['_diag'],columns=['Main_transit_L','Main_fishing_L','Auxiliary_L','Annual_alpha_L','Age_over30_L','Ghost_L','Days_capped365_L','Fuel_on_over365_days_L','Days_multiplier'])
 draws['Total_L']=draws[['Main_transit_L','Main_fishing_L','Auxiliary_L']].sum(axis=1)
 for c in ['Main_transit','Main_fishing','Auxiliary']:draws[c+'_share_pct']=draws[c+'_L']/draws.Total_L*100
 draws['Annual_alpha_change_pct']=(draws.Annual_alpha_L/draws.Total_L-1)*100
 draws['Age_over30_share_pct']=draws.Age_over30_L/draws.Total_L*100
 draws['Days_cap_change_pct']=(draws.Days_capped365_L/draws.Total_L-1)*100
 draws.to_csv(H/'LL23_Diagnostic_Draws.csv',index=False)
 summary=dict(Production_fuel_L=float(flags.Production_Fuel_L.sum()),Production_catch_t=float(flags.Matched_Catch_t.sum()),Production_FUI_L_t=float(flags.Production_Fuel_L.sum()/flags.Matched_Catch_t.sum()),Eligible_registry_vessels=int(current.sum()),Ghost_eligible=int(cohort.Is_Ghost.sum()),Age_over30_eligible=int((cohort.Age_2023>30).sum()),Alpha_changed_vessels=int((abs(cohort.Alpha_production-cohort.Alpha_2023)>1e-10).sum()),Diagnostic_medians=draws.median().to_dict(),Draws_with_days_over365=int((draws.Fuel_on_over365_days_L>0).sum()),Mean_days_cap_effect_pct=float(draws.Days_cap_change_pct.mean()),Max_days_cap_effect_pct=float(draws.Days_cap_change_pct.min()),Cohort_days=sorted(cohort.T_map.unique().tolist()),Industrial_alpha_range=[float(cohort.loc[cohort.Sector=='I','Alpha_production'].min()),float(cohort.loc[cohort.Sector=='I','Alpha_production'].max())],Diagnostic_note='500-draw shortened-window replay; RNG stream differs from preserved historical run. Component ratios diagnose equations, not observed causal shares of the survey gap.',Frozen_inputs=hashes)
 for p in inputs:assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==hashes[str(p.relative_to(R))]
 (H/'Fuel_Diagnosis_QC.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
