"""Phase-specific LL diagnostics; no calibration or production replacement.

Production medians provide the reference L/t. A separate 500-draw short-window
replay supplies phase response RATIOS, paired within draw. Unverified activity
fractions are transparent scenarios at a fixed recorded-catch denominator.
"""
from pathlib import Path
import sys,json,inspect,contextlib,io,re
import numpy as np
import pandas as pd
H=Path(__file__).resolve().parent;R=H.parents[1];O=H/'analysis';sys.path.insert(0,str(R/'GHG_Calculation'))
import ghg_lca as h
sys.stdout.reconfigure(encoding='utf-8',errors='replace')

def main():
    old=R/'audits/si_order_fuel_diagnosis_20261016'
    base=json.loads((old/'Fuel_Diagnosis_QC.json').read_text());reference=base['Production_FUI_L_t']
    scope=pd.read_csv(R/'figures/supplement/Supplementary_Fig14/Matched_Flag_Gear_Sector_Audit.csv').query('Benchmark_ID=="LL23"')
    with contextlib.redirect_stdout(io.StringIO()):
        pm=h.load_prior_matrix(h.PRIOR_MATRIX_PATH);df,pools=h.run_imputation_pipeline(h.VESSEL_REGISTRY_PATH,pm,write_output=False)
        df=h.impute_builtdate_deterministic(h.convert_gt_to_lsw(df,pm),pools);df['Retire_Year']=9999;df['Is_Ghost']=0
        ghost=pd.read_csv(R/'GHG_Calculation/Ghost_Fleet_Reconstructed.csv');df=h.assign_operational_params(df,pm);ghost=h.assign_operational_params(ghost,pm)
        df=pd.concat([df,ghost],ignore_index=True)
    sw=df[['Flag','VesselType','Sector']].rename(columns={'VesselType':'Gear'}).merge(scope[['Flag','Gear','Sector','Scope_share']],how='left',on=['Flag','Gear','Sector'],validate='many_to_one').Scope_share.fillna(0).to_numpy()
    current=(df.Builtdate<=2023)&(df.Retire_Year>2023)&(sw>0)
    cohort=df.loc[current].copy();cohort['Scope_share']=sw[current];cohort['Age_2023']=2023-cohort.Builtdate
    ids=[]
    for col in ['IMO','MMSI','Callsign']:
        s=cohort[col].astype(str).str.strip().str.upper().str.replace(r'\.0$','',regex=True)
        valid=~s.isin(['','NAN','NONE','0','0.0','UNKNOWN','-'])
        ids.append(dict(Identifier=col,Present=int(valid.sum()),Duplicate_nonblank_rows=int(s[valid].duplicated(keep=False).sum()),Duplicate_values=int(s[valid][s[valid].duplicated()].nunique())))
    pd.DataFrame(ids).to_csv(O/'Fuel_Identifier_QC.csv',index=False)
    # Authorisation periods show permission, never proof of fishing activity.
    raw=pd.read_csv(R/'raw_vessel_data/WCPFC_Vessel_Registry.csv',low_memory=False)
    key='International Radio Call Sign';start='Start of period of validity of authorization';end='End of period of validity of authorization'
    raw['Call_key']=raw[key].astype(str).str.strip().str.upper();raw=raw[~raw.Call_key.isin(['NAN','','NONE'])]
    raw['Auth_start']=pd.to_datetime(raw[start],errors='coerce');raw['Auth_end']=pd.to_datetime(raw[end],errors='coerce')
    raw=raw.sort_values('Auth_start').drop_duplicates('Call_key',keep='last')
    cohort['Call_key']=cohort.Callsign.astype(str).str.strip().str.upper()
    auth=cohort.merge(raw[['Call_key','Auth_start','Auth_end']],on='Call_key',how='left',validate='many_to_one')
    auth['Auth_overlaps_2023']=(auth.Auth_start<=pd.Timestamp('2023-12-31'))&(auth.Auth_end>=pd.Timestamp('2023-01-01'))
    auth[['Vesselname','Flag','Callsign','Builtdate','Length','Enginepower','Scope_share','Auth_start','Auth_end','Auth_overlaps_2023']].to_csv(O/'Fuel_Authorisation_Check.csv',index=False)
    comp=[]
    for name,g in [('All',cohort),*list(cohort.groupby('Flag'))]:
        w=g.Scope_share
        comp.append(dict(Group=name,N=len(g),Scope_weighted_equivalent_vessels=w.sum(),Mean_LOA_m=g.Length.mean(),Mean_Main_kW=g.Enginepower.mean(),
            Scope_weighted_LOA_m=np.average(g.Length,weights=w),Scope_weighted_Main_kW=np.average(g.Enginepower,weights=w),
            Scope_weighted_Aux_kW=np.average(g.Enginepower*g.AUX_Ratio,weights=w),Mean_Tmap_days=g.T_map.mean()))
    pd.DataFrame(comp).to_csv(O/'Fuel_Cohort_Composition.csv',index=False)
    cohort['LOA_class']=pd.cut(cohort.Length,[0,12,24,40,np.inf],labels=['<12','12-24','24-40','>=40'],right=False)
    source=inspect.getsource(h.run_monte_carlo_lca)
    insert='''            if year == 2023:
                volumes=np.vstack([fuel_t_move,fuel_t_work,fuel_t_aux])*(sf*_scope*1000/_rho)[None,:]
                ph=volumes.sum(axis=1);total=ph.sum()
                vals={"Baseline":total,"Transit clock x0.5":total-ph[0]*0.5,"Fishing clock x0.5":total-ph[1]*0.5,"Auxiliary clock x0.5":total-ph[2]*0.5,
                      "Transit clock x0.75":total-ph[0]*0.25,"Fishing clock x0.75":total-ph[1]*0.25,"Auxiliary clock x0.75":total-ph[2]*0.25,
                      "Active fraction 0.75":total*0.75,"Active fraction 0.50":total*0.5,"Active fraction 0.25":total*0.25,
                      "Power x0.75":total*0.75,"Power x1.25":total*1.25,"Days x0.75":total*0.75,"SFC x0.9":total*0.9,"SFC x1.1":total*1.1}
                func=lambda z:0.455*z*z-0.71*z+1.28
                for label,j,lf,base_lf in [("Transit",0,lf_move_m,LF_move),("Fishing",1,lf_work_m,LF_work),("Auxiliary",2,lf_aux_m,np.full(n_ships,0.4))]:
                    for ratio in [0.75,1.25]:
                        # Original SFR is fixed at its assigned phase load.
                        # Apply the SFOC shape to changed operating loads in this
                        # diagnostic, using the original load as response anchor.
                        response=ratio*np.where(~is_gasoline,func(lf*ratio)/func(lf),1.)
                        vals[label+" load x"+str(ratio)]=total-ph[j]+(volumes[j]*response).sum()
                # A joint case is calculated jointly, not summed single effects.
                vals["Transit half + aux half + activity 0.75"]=(total-0.5*ph[0]-0.5*ph[2])*0.75
                for label,value in vals.items():_scenario_draws.append((sim,label,value,total))
                for group,mask in _classes.items():
                    _class_draws.append((sim,group,volumes[:,mask].sum(),ph[0],ph[1],ph[2]))
'''
    assert source.count('            fuel_co2 *= sf')==1
    source=source.replace('            fuel_co2 *= sf',insert+'            fuel_co2 *= sf')
    # is_diesel name is used by the production engine (assert below).
    assert 'is_gasoline =' in source
    classes={str(k):(current.to_numpy() & (df.Length>=lo)&(df.Length<hi)).to_numpy() for k,lo,hi in [('<12',0,12),('12-24',12,24),('24-40',24,40),('>=40',40,np.inf)]}
    rho=df.Sector.map({'I':.830565,'APW':.746269}).to_numpy()
    gl=h.__dict__.copy();gl.update(_scope=sw,_rho=rho,_scenario_draws=[],_class_draws=[],_classes=classes)
    exec(compile(source,'<phase_specific_fuel_diagnostic>','exec'),gl)
    top=pd.read_csv(R/'GHG_Calculation/GSA_Per_Process_Top2.csv');important=set(top.Top1)|set(top.Top2)
    with contextlib.redirect_stdout(io.StringIO()):
        gl['run_monte_carlo_lca'](df,pm,end_year=2025,start_year=2023,n_simulations=500,random_seed=42,
            lookup_data_power=h.init_power_discount_lookup(h.PNAS_POWER_PATH,baseline_year=2015),lookup_data_alpha=h.init_time_profile_lookup(h.PNAS_POWER_PATH,verbose=False),important_params=important)
    draws=pd.DataFrame(gl['_scenario_draws'],columns=['Draw','Case','Fuel_L','Reference_Fuel_L']);draws['Fuel_ratio']=draws.Fuel_L/draws.Reference_Fuel_L
    draws['Diagnostic_FI_L_t']=reference*draws.Fuel_ratio
    draws.to_csv(O/'Fuel_Phase_Sensitivity_Draws.csv',index=False)
    sums=draws.groupby('Case').agg(FI_median=('Diagnostic_FI_L_t','median'),FI_p5=('Diagnostic_FI_L_t',lambda x:x.quantile(.05)),FI_p95=('Diagnostic_FI_L_t',lambda x:x.quantile(.95)),Ratio_median=('Fuel_ratio','median')).reset_index()
    sums['Change_pct']=100*(sums.Ratio_median-1);sums['Status']='Diagnostic assumption; no observed activity validation'
    sums.to_csv(O/'Fuel_Phase_Sensitivity.csv',index=False)
    cl=pd.DataFrame(gl['_class_draws'],columns=['Draw','LOA_class','Fuel_L','Transit_L','Fishing_L','Auxiliary_L'])
    cl['Fuel_share']=cl.Fuel_L/cl[['Transit_L','Fishing_L','Auxiliary_L']].sum(axis=1)
    cl.groupby('LOA_class').agg(Fuel_share=('Fuel_share','median')).reset_index().merge(cohort.groupby('LOA_class',observed=True).agg(N=('Length','size'),Mean_Main_kW=('Enginepower','mean'),Mean_LOA=('Length','mean')).reset_index(),on='LOA_class').to_csv(O/'Fuel_LOA_Class.csv',index=False)
    # Direct upstream catch conservation and allocated process checks.
    keycols=['Year','Flag','Gear','squaretypecode','lat','lon','EffortType','Organization']
    sp=['SKJ_Tonnes','YFT_Tonnes','BET_Tonnes','ALB_Tonnes','SBT_Tonnes']
    b3=pd.read_csv(R/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv',usecols=keycols+sp+['Total_Catch','Effort_Prop','Fuel_CO2_median','GHG_emissions_median'])
    b=b3[(b3.Year==2023)&(b3.Gear=='LL')&b3.Organization.isin(['WCPFC','IATTC'])].copy()
    up=pd.read_csv(R/'effort_data/Grid_Catch_Allocation.csv').rename(columns={'SquareTypeCode':'squaretypecode','Lat':'lat','Lon':'lon'})
    u=up[(up.Year==2023)&(up.Gear=='LL')&up.Organization.isin(['WCPFC','IATTC'])]
    check=b.merge(u[keycols+sp],on=keycols,how='outer',validate='one_to_one',suffixes=('_b','_u'),indicator=True)
    assert (check._merge=='both').all()
    for s in sp:assert np.allclose(check[s+'_b'],check[s+'_u'],rtol=1e-12,atol=1e-9)
    den=[]
    for flag,g in b.groupby('Flag'):
        den.append(dict(Flag=flag,Recorded_four_species_t=g[sp[:4]].sum().sum(),Positive_GHG_four_species_t=g.loc[g.GHG_emissions_median>0,sp[:4]].sum().sum(),
                        SBT_t=g.SBT_Tonnes.sum(),Effort_share=g.Effort_Prop.sum()))
    pd.DataFrame(den).to_csv(O/'Fuel_Catch_Denominator.csv',index=False)
    selected=b[(b.Total_Catch>0)&(b.GHG_emissions_median>0)]
    mc=selected[sp[:4]].sum();survey=pd.Series([38,764,301,1666],index=['SKJ_Tonnes','YFT_Tonnes','BET_Tonnes','ALB_Tonnes']).reindex(mc.index)
    pd.DataFrame(dict(Species=[s.replace('_Tonnes','') for s in mc.index],Model_catch_t=mc.to_numpy(),Model_four_species_share_pct=100*mc.to_numpy()/mc.sum(),
        SurveyA_rounded_catch_t=survey.to_numpy(),SurveyA_four_species_share_pct=100*survey.to_numpy()/survey.sum())).to_csv(O/'Fuel_Species_Composition.csv',index=False)
    coverage=[]
    for org in ['WCPFC','IATTC']:
        ac=pd.read_csv(R/f'effort_data/{org}/{org}_Annual_Catch.csv');gc='GearTypeCode' if 'GearTypeCode' in ac else 'Gear'
        ac=ac[(ac.Year==2023)&(ac[gc]=='LL')];v=b[b.Organization==org]
        coverage.append(dict(Organization=org,Annual_reported_four_species_t=ac[['SKJ','YFT','BET','ALB']].sum().sum(),
            Allocated_grid_four_species_t=v[sp[:4]].sum().sum(),Positive_GHG_grid_catch_t=v.loc[v.GHG_emissions_median>0,sp[:4]].sum().sum()))
    pd.DataFrame(coverage).to_csv(O/'Fuel_Annual_Grid_Catch_Coverage.csv',index=False)
    authq=dict(Matched_current_WCPFC_authorisation_dates=int(auth.Auth_start.notna().sum()),Current_authorisation_overlaps_2023=int(auth.Auth_overlaps_2023.sum()),
       Interpretation='Permission records are current snapshots, not 2023 AIS/VMS or evidence of annual actual fishing. Do not drop unmatched vessels as inactive.')
    qc=dict(Production=base,Identifier_QC=ids,Authorisation=authq,Upstream_catch_row_identity='PASS',Catch_key_duplicates=int(b.duplicated(keycols).sum()),
      Diagnostic_replay_base_fuel_median=float(draws.query('Case=="Baseline"').Fuel_L.median()),
      Independence='2025 ISSF survey is 2023 operator activity; 2012 report uses 2009 activity; later republications of 2009 data are not independent samples.',
      Survey='Pacific LL 14 vessels, mean LOA34.90 m, main1073.51 HP (800.5kW), aux247.71HP (184.7kW); no vessel-level fuel/power cross-tab available. Table5 fishing days1048.29 exceed a calendar year; do not use as per-vessel days.',
      Recalibration='None. Unverified activity/phase factors are sensitivity cases, not fitted corrections.',
      Conclusion='No definite duplicate/catch-allocation bug identified in this diagnostic. Active-status evidence remains absent; production total is a conditional inventory estimate, not externally validated truth.')
    (O/'Fuel_Validation_QC.json').write_text(json.dumps(qc,indent=2),encoding='utf-8')
    print(sums.to_string(index=False));print(pd.DataFrame(comp).query('Group=="All"').to_string(index=False));print(authq)
if __name__=='__main__':main()
