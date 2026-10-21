"""External benchmarks only. Read frozen inventory; never fit or mutate models.

Run: C:/CONDA/python figures/supplement/Supplementary_Fig14/benchmark_external.py
R renderer: Supplementary_Fig14.r. All model process values are tonnes CO2e.
Fuel is recovered sector by sector from CO2 / fixed carbon factor, not from CEI.
"""
from pathlib import Path
import json, hashlib, sys
import numpy as np
import pandas as pd
import openpyxl
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
H=Path(__file__).resolve().parent; ROOT=H.parents[2]
AUD=ROOT/'analysis/targeted_revision_20261015'
KEY=['Year','Flag','Gear']
PROC=['Fuel_CO2','Fuel_CH4','Fuel_N2O','Fuel_WTT']
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    # Primary DESNZ Fuel properties, 2024, kg/m3, divided by 1000.
    uk=json.loads((H/'sources/UK_Factors_Extract.json').read_text(encoding='utf-8'))
    prop=uk['sheets']['Fuel properties']
    rho={name:next(r[5]/1000 for r in prop if r[1]==label) for name,label in
         [('I','Diesel (100% mineral diesel)'),('APW','Petrol (100% mineral petrol)')]}
    cf={'I':3.206,'APW':3.158} # verified fixed factors in ghg_lca.py/Prior_Matrix
    b2=pd.read_csv(ROOT/'GHG_Calculation/Base_2_Fleet_GHG.csv')
    assert not b2.duplicated(KEY+['Sector']).any(),'Duplicate fleet-sector interface keys'
    cols=KEY+['Organization','Total_Catch','Effort_Prop','GHG_emissions_median']+[s+'_Tonnes' for s in ['SBT','SKJ','YFT','BET','ALB']]+[p+'_median' for p in PROC]
    b3=pd.read_csv(ROOT/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv',usecols=cols)
    # Denominator and numerator share the same positive-catch/positive-GHG records.
    eligible=b3[(b3.Total_Catch>0)&(b3.GHG_emissions_median>0)].copy()
    settings=[('PS09',2009,'PS',None,None,'Global',368.,'Tyedmers & Parker (2012)',2012,'Tables 4 and 5; activity 2009'),
              ('LL09',2009,'LL',None,None,'Global (ALB)',1069.,'Tyedmers & Parker (2012)',2012,'Tables 4 and 5; all 453 t of sampled LL catch is albacore'),
              ('PS23',2023,'PS',['WCPFC','IATTC','IOTC'],None,'Pacific + Indian',496.3,'Tyedmers & Donovan (2025)',2025,'Tables 4, 10, 12; activity 2023'),
              ('LL23',2023,'LL',['WCPFC','IATTC'],None,'Pacific',1523.3,'Tyedmers & Donovan (2025)',2025,'Tables 4, 10, 12; activity 2023'),
              ('PS23I',2023,'PS',['IOTC'],None,'Indian',522.9,'Tyedmers & Donovan (2025)',2025,'Table 10; Indian sample contains PS only'),
              ('PS03',2003,'PS',None,'ESP','Spanish fleets',436.,'Hospido & Tyedmers (2005)',2005,'Section 3.1; Table 2; activity 2003')]
    rows=[]; sums=[];groups=[]
    for bid,year,gear,orgs,flag,region,lit,author,pub,locator in settings:
        s=eligible[(eligible.Year==year)&(eligible.Gear==gear)].copy()
        if orgs:s=s[s.Organization.isin(orgs)]
        if flag:s=s[s.Flag==flag]
        species={'LL09':['ALB'],'PS03':['SKJ','YFT']}.get(bid,['SKJ','YFT','BET','ALB'])
        s['Matched_Catch']=s[[v+'_Tonnes' for v in species]].sum(axis=1)
        s=s[s.Matched_Catch>0].copy()
        s['Match_Fraction']=s.Matched_Catch/s.Total_Catch
        assert s.Match_Fraction.between(0,1+1e-8).all(),'Matched-species shares outside [0,1]'
        s['Matched_Effort_Prop']=s.Effort_Prop*s.Match_Fraction
        assert len(s)>0,bid
        share=s.groupby(KEY,as_index=False).Matched_Effort_Prop.sum().rename(columns={'Matched_Effort_Prop':'Scope_share'})
        assert share.Scope_share.between(0,1+1e-8).all(),bid
        m=share.merge(b2,on=KEY,how='left',validate='one_to_many')
        assert m.Sector.notna().all()
        assert m.Sector.isin(cf).all()
        # All LL/PS industrial vessels use MDO, coastal LL gasoline, including auxiliaries.
        for p in PROC:m[p+'_scope']=m[p+'_median']*m.Scope_share
        recovered=sum((m.Fuel_CO2_scope/m.Sector.map(cf))*1000/m.Sector.map(rho))
        catch=float(s.Matched_Catch.sum());fui=recovered/catch
        direct=sum(m[p+'_scope'].sum() for p in PROC[:3])/catch
        lifecycle=direct+m.Fuel_WTT_scope.sum()/catch
        cei=(s.GHG_emissions_median*s.Match_Fraction).sum()/catch
        # Cross-file replication is numerical QA, not external validation.
        for p in PROC:
            assert np.isclose(m[p+'_scope'].sum(),(s[p+'_median']*s.Match_Fraction).sum(),rtol=1e-8,atol=1e-7),(bid,p)
        fuel_mass=float(sum(m.Fuel_CO2_scope/m.Sector.map(cf)))
        summary=dict(Benchmark_ID=bid,Activity_year=year,Gear=gear,Region=region,Records=len(s),
             Catch_scope='+'.join(species),Model_catch_t=catch,Model_fuel_L=recovered,Model_FUI_L_t=fui,
             Model_fuel_mass_t=fuel_mass,
             Model_combustion_tCO2e_t=direct,Model_fuel_lifecycle_tCO2e_t=lifecycle,
             Model_full_CEI_tCO2e_t=cei,APW_fuel_CO2_share=m.loc[m.Sector=='APW','Fuel_CO2_scope'].sum()/m.Fuel_CO2_scope.sum())
        sums.append(summary)
        m['Benchmark_ID']=bid;groups.append(m[KEY+['Sector','Scope_share','Benchmark_ID']+[p+'_scope' for p in PROC]])
        def add(metric,unit,model,external,boundary,independent=True,comparison='partial match'):
            rows.append(dict(Benchmark_ID=bid,Study=author,Publication_year=pub,Activity_year=year,
                 Region=region,Gear=gear,Metric=metric,Unit=unit,Model=model,Literature=external,
                 Difference_pct=(model/external-1)*100,Boundary=boundary,Comparison=comparison,
                 Independent_outcome=independent,Locator=locator))
        add('Fuel use','L per t catch',fui,lit,
            'Fishing-vessel fuel; no carriers. Model mass allocation to '+ '+'.join(species)+'; exact survey fleet and targeting coverage differ.'+
            (' Same survey family supplies PS operating-day parameters: not fully independent.' if bid=='PS09' else ''),
            independent=(bid!='PS09'))
        if bid in ['PS23','LL23']:
            v={'PS23':1.3428,'LL23':4.1213}[bid]
            add('Fuel combustion GHG','t CO2e per t catch',direct,v,
                'Model CO2+CH4+N2O only; ISSF Table 12 diesel case. UK Fuels excludes separately tabulated WTT; source prose calls it lifecycle.')
        if bid=='PS03':
            add('Full LCA CEI','t CO2e per t catch',cei,1.8,
                'Context only: literature includes delivery to Galicia, model fishing vessels only; shared background source.',
                False,'boundary mismatch; descriptive gap only')
    pd.DataFrame(rows).to_csv(H/'Supplementary_Table10_Benchmark.csv',index=False)
    pd.DataFrame(sums).to_csv(H/'Model_Matched_Summaries.csv',index=False)
    pd.concat(groups).to_csv(H/'Matched_Flag_Gear_Sector_Audit.csv',index=False)
    # Fleet characteristics are registry cohorts, not verified annual active fleets.
    reg=pd.read_csv(ROOT/'PMM_Imputation/After_PMM_Vessels.csv')
    stats=[]
    for gear in ['LL','PS']:
        subset=reg[(reg.VesselType==gear)&(reg.Builtdate<=2023)]
        for column,unit in [('Length','m'),('Enginepower','kW')]:
            v=pd.to_numeric(subset[column],errors='coerce').dropna()
            for region,lg,kw in [('Pacific',{'PS':63.20,'LL':34.90}[gear],{'PS':3096.72,'LL':1073.51}[gear]*0.745699872)]:
                stats.append(dict(Gear=gear,Model_cohort='Registry vessels built by 2023; all oceans; imputed values included',
                     Metric=column,Unit=unit,N=len(v),Model_mean=v.mean(),Model_median=v.median(),
                     Model_p25=v.quantile(.25),Model_p75=v.quantile(.75),Survey_region=region,
                     Survey_mean=lg if column=='Length' else kw,Survey_N=48 if gear=='PS' else 14,
                     Comparison='Context only: different populations; no annual active-vessel status inferred'))
    pd.DataFrame(stats).to_csv(H/'Fleet_Characteristics_Context.csv',index=False)
    totals=[]
    for year in [2009,2023]:
        for gear in ['LL','PS']:
            t=b2[(b2.Year==year)&(b2.Gear==gear)]
            mass=t.Fuel_CO2_median/t.Sector.map(cf)
            totals.append(dict(Year=year,Gear=gear,Model_fuel_t=mass.sum(),
                Model_fuel_billion_L=(mass*1000/t.Sector.map(rho)).sum()/1e9,
                Scope='Full model five-species-allocated LL/PS fuel; no service vessels',
                External_context='ISSF about 3 billion L across all tuna gears globally; not an identical population',
                Relative_bias='Not calculated: target species, gear and fleet coverage differ'))
    pd.DataFrame(totals).to_csv(H/'Annual_Fuel_Totals_Context.csv',index=False)
    # Every original Excel row is retained and adjudicated; duplicates are not extra evidence.
    paths=sorted((ROOT/'cross_analysis').glob('*.xlsx'));assert len(paths)==1
    wb=openpyxl.load_workbook(paths[0],data_only=True,read_only=True)
    workbook={s.title:[list(row) for row in s.iter_rows(values_only=True)] for s in wb}
    source=workbook['Sheet1'];decisions=[]
    used={2:'PS03: source-checked fuel; full LCA context only',3:'PS09: duplicates 2009 ISSF/Parker data',
          6:'LL09: traced to original 2009 ISSF survey',17:'Duplicate 2009 PS value, not 2023; updated report also gives retrospective 390 L/t',18:'Duplicate LL09, not independent'}
    for n,r in enumerate(source,1):
        if n==1:decision='Header'
        elif n in used:decision=used[n]
        elif n in [4,5]:decision='Not used quantitatively: FAD/FSC values and misplaced mean need original-table verification'
        elif n in [14,15,16]:decision='Context only: full LCA shares calibration/background sources; no independent matched-system residual'
        elif n in [21,22,23,24,25]:decision='Excluded: input-output/hypothetical engineering scenarios, not independent observed LL/PS fleets'
        elif n==27:decision='Excluded from quantitative benchmark: original source and catch/boundary not verified'
        elif n==28:decision='Context only: Atlantic bluefin outside five inventory species; service-vessel boundary differs'
        elif n in [7,8,9,11,12,19,20,26]:decision='Excluded from quantitative benchmark: non-LL/PS gear or non-target species domain'
        else:decision='Blank or separator'
        decisions.append(dict(Excel_row=n,Original_reference=str(r[0] or ''),Decision=decision,Original_cells=json.dumps(r,ensure_ascii=False,default=str)))
    pd.DataFrame(decisions).to_csv(H/'Workbook_Row_Adjudication.csv',index=False,encoding='utf-8-sig')
    inputs=[ROOT/'GHG_Calculation'/f for f in ['Base_2_Fleet_GHG.csv','Base_3_Spatial_Grid_Enriched.csv']]
    qc=dict(Inputs={str(p.relative_to(ROOT)):digest(p) for p in inputs},Densities_kg_L=rho,
            Carbon_factors_tCO2_tfuel=cf,Conservation_checks='PASS sector-recovered allocated process totals',
            Inference='Descriptive external gaps, not statistical validation; central process medians are not paired-draw intervals',
            Important_source_issues=['ISSF 2025 activities=2023; 2009 figures are retrospective, not independent',
             'Table 5 average days 412.46/1048.29/477.78 exceed a calendar year; not used to validate operating days',
             'Table 4 LL fuel/catch differs from Table 10 weighted FUI; retain Table 10, flag internal discrepancy',
             'UK 2024 Fuels and WTT-fuels are distinct: benchmark ISSF Table 12 as-tabulated combustion only',
            'GRT not numerically equated with GT; no tonnage residual calculated',
            '2009 LL survey is albacore only: model numerator AND catch mass-allocated to ALB',
            '2003 Spanish PS is SKJ+YFT only: model numerator AND catch allocated to same species',
            'Do not divide unchanged survey total fuel by a target-only denominator: consistent mass allocation leaves its FUI unchanged'])
    (H/'Benchmark_QC.json').write_text(json.dumps(qc,indent=2),encoding='utf-8')
    print(pd.DataFrame(rows)[['Benchmark_ID','Metric','Model','Literature','Difference_pct']].to_string(index=False))
if __name__=='__main__':main()
