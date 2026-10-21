"""Current C/F/T results, paired technical effects and exact matched accounting."""
from pathlib import Path
import sys,json,math,itertools
import numpy as np
import pandas as pd
import run_hcr as E
H=E.H;O=H/'analysis';O.mkdir(exist_ok=True)
def save(name,data):
    (data if isinstance(data,pd.DataFrame) else pd.DataFrame(data)).to_csv(O/(name+'.csv'),index=False)
def read(key,name):return pd.read_csv(E.OUT/key/(name+'.csv'),dtype={'Technical':str})
def stats(d,groups,value):
    return d.groupby(groups,observed=True)[value].agg(Median='median',P5=lambda x:x.quantile(.05),P95=lambda x:x.quantile(.95),Minimum='min',Maximum='max',N='count').reset_index()
def primary():
    assert (H/'main_Complete.json').exists()
    annual=[];biomass=[];gear=[];period=[];activation=[];organisations=[];geartotals=[]
    for key,p,seed,meta in E.main_jobs():
        a=read(key,'Annual');s=read(key,'Stocks');g=read(key,'Groups');u=read(key,'Effort')
        assert a.Year.tolist()==list(range(2025,2051))
        annual.append(a)
        for org,part in g.groupby('Organization'):
            organisations.append(dict(**meta,Organization=org,GHG_Mt=part.GHG_t.sum()/1e6))
        for gg,part in g.groupby('Gear'):
            geartotals.append(dict(**meta,Gear=gg,GHG_Mt=part.GHG_t.sum()/1e6))
        catch=float(a.Realised_Fleet_Catch_Mt.sum());ghg=float(a.Total_GHG_tCO2e.sum()/1e6)
        tail=s[s.Year==2050]
        period.append(dict(**meta,Key=key,Catch_Mt=catch,GHG_Mt=ghg,Period_CEI=ghg/catch if catch>0 else np.nan,
            GHG_2050_Mt=float(a.loc[a.Year==2050,'Total_GHG_tCO2e'].iloc[0]/1e6),Catch_2050_Mt=float(a.loc[a.Year==2050,'Realised_Fleet_Catch_Mt'].iloc[0]),
            Min_Stock_Bmsy_2050=float(tail.B_Bmsy_Start.min()),Directed_Effort_kW_days=float(u.Realised_kW_days.sum()),
            Years_Any_Stock_Below_Bmsy=int(s[s.B_Bmsy_Start<1].Year.nunique())))
        if meta['Technical']=='000':
            biomass.append(s)
            cg=read(key,'Cells').groupby(['Year','Gear']).Catch_t.sum()
            gu=g[g.Gear.isin(['LL','PS'])].groupby(['Year','Gear'])[['Realised_kW_days','Variable_GHG_t','GHG_t']].sum().reset_index()
            gu['Catch_t']=[cg.get((x.Year,x.Gear),0) for x in gu.itertuples()]
            demand=u.groupby(['Year','Gear']).Required_kW_days.sum()
            capacity=u.groupby(['Year','Gear']).Capacity_kW_days.sum()
            gu['Required_kW_days']=[demand.get((x.Year,x.Gear),0) for x in gu.itertuples()]
            gu['Capacity_kW_days']=[capacity.get((x.Year,x.Gear),0) for x in gu.itertuples()]
            gu['Effort_per_t']=gu.Realised_kW_days/gu.Catch_t.replace(0,np.nan)
            gu['Variable_GHG_per_kW_day']=gu.Variable_GHG_t/gu.Realised_kW_days.replace(0,np.nan)
            for c,v in meta.items():gu[c]=v
            gear.append(gu)
            for stock,ss in s.groupby('Stock'):
                active=ss[ss.HCR_Triggered];closed=ss[ss.HCR_Closed]
                activation.append(dict(**meta,Stock=stock,Triggered_Years=len(active),Closed_Years=len(closed),
                    First_Triggered_Year=int(active.Year.min()) if len(active) else np.nan,Last_Triggered_Year=int(active.Year.max()) if len(active) else np.nan,
                    First_Closure_Year=int(closed.Year.min()) if len(closed) else np.nan,
                    Final_B_Bmsy=float(ss.loc[ss.Year==2050,'B_Bmsy_Start'].iloc[0])))
    a=pd.concat(annual,ignore_index=True);s=pd.concat(biomass,ignore_index=True);g=pd.concat(gear,ignore_index=True);d=pd.DataFrame(period)
    save('HCR_Annual',a);save('HCR_Baseline_Stocks',s);save('HCR_Baseline_Gear',g);save('HCR_Period',d);save('HCR_Threshold_Activation',activation)
    baseperiod=d[d.Technical=='000']
    save('HCR_Baseline_Period_Summary',pd.concat([stats(baseperiod,['Rule'],metric).assign(Metric=metric) for metric in ['Catch_Mt','GHG_Mt','Period_CEI','GHG_2050_Mt','Catch_2050_Mt','Min_Stock_Bmsy_2050','Directed_Effort_kW_days']],ignore_index=True))
    for name,rows,group in [('Organization',organisations,'Organization'),('Gear',geartotals,'Gear')]:
        dd=pd.DataFrame(rows);bb=dd[dd.Technical=='000'][['Future','Rule',group,'GHG_Mt']].rename(columns={'GHG_Mt':'Baseline_GHG_Mt'})
        dd=dd.merge(bb,on=['Future','Rule',group],validate='many_to_one');dd['Reduction_pct']=100*(1-dd.GHG_Mt/dd.Baseline_GHG_Mt)
        save('HCR_'+name+'_Technical_Effects',dd)
    effects=[];shapley=[]
    labels=['Fuel transition','Refrigeration transition','Fleet consolidation']
    for (future,rule),part in d.groupby(['Future','Rule']):
        by=part.set_index('Technical');base=by.loc['000']
        for tech,row in by.iterrows():
            effects.append(dict(Future=future,Rule=rule,Technical=tech,
                Cumulative_Abatement_Mt=base.GHG_Mt-row.GHG_Mt,Cumulative_Reduction_pct=100*(1-row.GHG_Mt/base.GHG_Mt),
                Endpoint_Reduction_pct=100*(1-row.GHG_2050_Mt/base.GHG_2050_Mt),
                Catch_Change_pct=100*(row.Catch_Mt/base.Catch_Mt-1),CEI_Change_pct=100*(row.Period_CEI/base.Period_CEI-1)))
        for metric in ['GHG_Mt','GHG_2050_Mt']:
            total=base[metric]-by.loc['111',metric];terms=[]
            defined=abs(total)>max(1e-6,1e-6*max(abs(base[metric]),abs(by.loc['111',metric])))
            for j,name in enumerate(labels):
                value=0.
                for bits in itertools.product((0,1),repeat=3):
                    if bits[j]:continue
                    k=sum(bits);after=list(bits);after[j]=1
                    weight=math.factorial(k)*math.factorial(2-k)/math.factorial(3)
                    value+=weight*(by.loc[''.join(map(str,bits)),metric]-by.loc[''.join(map(str,after)),metric])
                terms.append(value);shapley.append(dict(Future=future,Rule=rule,Metric=metric,Measure=name,Contribution_Mt=value,
                    Total_Abatement_Mt=total,Share_pct=100*value/total if defined else np.nan,Share_Defined=defined))
            assert abs(sum(terms)-total)<1e-8
    effect=pd.DataFrame(effects);save('HCR_Technical_Effects',effect);save('HCR_Three_Technical_Shapley',shapley)
    save('HCR_Technical_Effect_Summary',stats(effect,['Rule','Technical'],'Cumulative_Reduction_pct'))
    save('HCR_Fuel_Absolute_Effect_Summary',stats(effect[effect.Technical=='100'],['Rule'],'Cumulative_Abatement_Mt'))
    save('HCR_Biomass_2050_Summary',stats(s[s.Year==2050],['Rule','Stock'],'B_Bmsy_Start'))
    # Explicitly paired HCR contrasts, kept separate from technical mitigation.
    pairs=[];period_lmdi=[]
    for future,part in d[d.Technical=='000'].groupby('Future'):
        by=part.set_index('Rule')
        for aa,bb in [('C','F'),('C','T'),('F','T')]:
            x,y=by.loc[aa],by.loc[bb]
            pairs.append(dict(Future=future,Comparison=aa+bb,Base_Rule=aa,Policy_Rule=bb,
                GHG_Change_pct=100*(y.GHG_Mt/x.GHG_Mt-1),Catch_Change_pct=100*(y.Catch_Mt/x.Catch_Mt-1),
                CEI_Change_pct=100*(y.Period_CEI/x.Period_CEI-1),GHG_Difference_Mt=y.GHG_Mt-x.GHG_Mt))
            weight=(y.GHG_Mt+x.GHG_Mt)/2 if np.isclose(y.GHG_Mt,x.GHG_Mt,rtol=1e-10,atol=0) else (y.GHG_Mt-x.GHG_Mt)/(np.log(y.GHG_Mt)-np.log(x.GHG_Mt))
            scale=weight*np.log(y.Catch_Mt/x.Catch_Mt);intensity=weight*np.log(y.Period_CEI/x.Period_CEI)
            residual=scale+intensity-(y.GHG_Mt-x.GHG_Mt);assert abs(residual)<1e-8
            period_lmdi.append(dict(Future=future,Comparison=aa+bb,Catch_Scale_Mt=scale,CEI_Mt=intensity,Delta_GHG_Mt=y.GHG_Mt-x.GHG_Mt,Residual_Mt=residual))
    save('HCR_Unmatched_Rule_Contrasts',pairs)
    save('HCR_Unmatched_Two_Factor_LMDI',period_lmdi)
    report=dict(Primary_Simulations=len(d),Futures=81,HCRs=3,Technical_Subsets_Per_HCR=8,
        Baselines=d[d.Technical=='000'].groupby('Rule')[['Catch_Mt','GHG_Mt','Period_CEI','GHG_2050_Mt']].median().reset_index().to_dict('records'),
        Technical_Medians=effect.groupby(['Rule','Technical'])[['Cumulative_Abatement_Mt','Cumulative_Reduction_pct','Endpoint_Reduction_pct','Catch_Change_pct','CEI_Change_pct']].median().reset_index().to_dict('records'),
        Shapley_Scope='Three technical measures within each HCR; no binary quota-reform measure',
        Biological_Reference='Unchanged fitted inputs; total biomass and start-of-year HCR decisions; realised harvest pulse updates stocks')
    (O/'Primary_Findings.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PRIMARY ANALYSIS COMPLETE',len(d),flush=True)

def lmean(a,b):
    equal=np.isclose(a,b,rtol=1e-10,atol=0);out=np.empty(len(a));out[equal]=(a[equal]+b[equal])/2
    out[~equal]=(a[~equal]-b[~equal])/(np.log(a[~equal])-np.log(b[~equal]));return out

def matched():
    assert (H/'Matching_Complete.json').exists()
    pairs=pd.read_csv(H/'HCR_Matched_Pairs.csv');terms=[];summaries=[];bio=[];yearly=[];closures=[]
    for pair in pairs[pairs.Matched].itertuples():
        runs={k:{n:read(key,n) for n in ['Annual','Groups','Cells','Stocks']} for k,key in [('Base',pair.Base_Key),('Policy',pair.Policy_Key)]}
        cells={k:d['Cells'].groupby(['Stock','Year'])[['Catch_t','Realised_kW_days','Variable_GHG_t']].sum() for k,d in runs.items()}
        totalcatch={k:d.Catch_t.sum() for k,d in cells.items()};speciescatch={k:d.groupby('Stock').Catch_t.sum() for k,d in cells.items()}
        x=cells['Base'].join(cells['Policy'],lsuffix='_Base',rsuffix='_Policy',how='outer').fillna(0)
        valid=(x>0).all(axis=1);v=x[valid];factors={}
        for k in runs:
            species=v.index.get_level_values('Stock').map(speciescatch[k]).to_numpy()
            c=v['Catch_t_'+k].to_numpy();u=v['Realised_kW_days_'+k].to_numpy();g=v['Variable_GHG_t_'+k].to_numpy()
            factors[k]=np.column_stack([np.full(len(v),totalcatch[k]),species/totalcatch[k],c/species,u/c,g/u])
            assert np.allclose(np.prod(factors[k],axis=1),g,rtol=1e-12)
        w=lmean(v.Variable_GHG_t_Policy.to_numpy(),v.Variable_GHG_t_Base.to_numpy())
        values=dict(zip(['Cumulative catch scale','Species composition','Within-species catch timing','Effort per catch','GHG per effort'],np.sum(w[:,None]*np.log(factors['Policy']/factors['Base']),axis=0)/1e6))
        values['Structural-zero cells']=(x.loc[~valid,'Variable_GHG_t_Policy'].sum()-x.loc[~valid,'Variable_GHG_t_Base'].sum())/1e6
        for gears,label,column in [(['LL','PS'],'LL/PS fixed processes','Fixed_GHG_t'),(['TP','SA'],'Support vessels','GHG_t')]:
            values[label]=(runs['Policy']['Groups'].query('Gear in @gears')[column].sum()-runs['Base']['Groups'].query('Gear in @gears')[column].sum())/1e6
        totals={k:d['Annual'].Total_GHG_tCO2e.sum()/1e6 for k,d in runs.items()};delta=totals['Policy']-totals['Base']
        error=sum(values.values())-delta;assert abs(error)<1e-8,(pair.Future,pair.Comparison,error)
        defined=abs(delta)>max(1e-6,1e-6*max(totals.values()))
        for term,value in values.items():terms.append(dict(Future=pair.Future,Comparison=pair.Comparison,Term=term,Delta_Mt=value,
            Percent_Base_GHG=100*value/totals['Base'],Share_Net_Difference_pct=100*value/delta if defined else np.nan,Net_Share_Defined=defined))
        closures.append(dict(Future=pair.Future,Comparison=pair.Comparison,Net_Difference_Mt=delta,Sum_Contributions_Mt=sum(values.values()),Residual_Mt=error,Positive_Common_Cells=int(valid.sum()),Structural_Zero_Cells=int((~valid).sum())))
        row=dict(Future=pair.Future,Comparison=pair.Comparison,Base_Rule=pair.Base_Rule,Policy_Rule=pair.Policy_Rule,Matching_Design=pair.Matching_Design,
            Base_Catch_Mt=totalcatch['Base']/1e6,Policy_Catch_Mt=totalcatch['Policy']/1e6,Catch_Gap_pct=100*(totalcatch['Policy']/totalcatch['Base']-1),
            Base_GHG_Mt=totals['Base'],Policy_GHG_Mt=totals['Policy'],Whole_Fleet_GHG_Reduction_pct=100*(1-totals['Policy']/totals['Base']),Net_Difference_Mt=delta,Net_Share_Defined=defined)
        aggregate={k:d.groupby('Stock')[['Catch_t','Variable_GHG_t']].sum() for k,d in cells.items()}
        commonstocks=aggregate['Base'].index.intersection(aggregate['Policy'].index)
        positive=[s for s in commonstocks if all(aggregate[k].at[s,'Catch_t']>0 for k in aggregate)]
        speciesweights=sum(aggregate[k].loc[positive,'Catch_t']/totalcatch[k] for k in aggregate)/2;speciesweights/=speciesweights.sum()
        speciesI={k:float((speciesweights*(aggregate[k].Variable_GHG_t/aggregate[k].Catch_t).loc[positive]).sum()) for k in aggregate}
        common=(x.Catch_t_Base>0)&(x.Catch_t_Policy>0)
        annualweights=(x.Catch_t_Base/totalcatch['Base']+x.Catch_t_Policy/totalcatch['Policy'])/2
        annualweights=annualweights[common]/annualweights[common].sum()
        commonI={k:float((annualweights*(x['Variable_GHG_t_'+k]/x['Catch_t_'+k]).loc[common]).sum()) for k in aggregate}
        row.update(Variable_GHG_Reduction_pct=100*(1-cells['Policy'].Variable_GHG_t.sum()/cells['Base'].Variable_GHG_t.sum()),
            Common_Species_Intensity_Reduction_pct=100*(1-speciesI['Policy']/speciesI['Base']),
            Common_Species_Year_Intensity_Reduction_pct=100*(1-commonI['Policy']/commonI['Base']),
            Common_Cell_Base_Catch_Fraction=x.loc[common,'Catch_t_Base'].sum()/totalcatch['Base'],
            Common_Cell_Policy_Catch_Fraction=x.loc[common,'Catch_t_Policy'].sum()/totalcatch['Policy'])
        assert abs(row['Catch_Gap_pct'])<=1.0000001
        summaries.append(row)
        for k,d in runs.items():
            a=d['Annual'].copy();a['Pair_Member']=k;a['Comparison']=pair.Comparison;yearly.append(a)
            b=d['Stocks'].merge(cells[k].reset_index(),on=['Stock','Year'],validate='one_to_one')
            b['Effort_per_t']=b.Realised_kW_days/b.Catch_t.replace(0,np.nan);b['Variable_CEI']=b.Variable_GHG_t/b.Catch_t.replace(0,np.nan)
            b['Pair_Member']=k;b['Comparison']=pair.Comparison;bio.append(b)
    save('HCR_Matched_Mechanism_Summary',summaries);save('HCR_Matched_LMDI_Terms',terms);save('HCR_Matched_Closure',closures)
    save('HCR_Matched_Stock_Effort',pd.concat(bio,ignore_index=True));save('HCR_Matched_Annual',pd.concat(yearly,ignore_index=True))
    t=pd.DataFrame(summaries);save('HCR_Matched_Summary',t.groupby('Comparison').agg(N=('Future','count'),Median_GHG_Reduction_pct=('Whole_Fleet_GHG_Reduction_pct','median'),
        Minimum_GHG_Reduction_pct=('Whole_Fleet_GHG_Reduction_pct','min'),Maximum_GHG_Reduction_pct=('Whole_Fleet_GHG_Reduction_pct','max'),
        Max_Absolute_Catch_Gap_pct=('Catch_Gap_pct',lambda x:x.abs().max()),Median_Common_Species_Year_Intensity_Reduction_pct=('Common_Species_Year_Intensity_Reduction_pct','median')).reset_index())
    print('MATCHED ACCOUNTING COMPLETE',len(t),flush=True)

def sensitivity():
    assert (H/'sensitivity_Complete.json').exists();rows=[]
    for key,p,seed,m in E.sensitivity_jobs():
        a=read(key,'Annual');s=read(key,'Stocks');catch=a.Realised_Fleet_Catch_Mt.sum();ghg=a.Total_GHG_tCO2e.sum()/1e6
        rows.append(dict(**m,GHG_Mt=ghg,Catch_Mt=catch,Period_CEI=ghg/catch if catch>0 else np.nan,
            GHG_2050_Mt=a.iloc[-1].Total_GHG_tCO2e/1e6,Minimum_Stock_Bmsy2050=s.loc[s.Year==2050,'B_Bmsy_Start'].min()))
    d=pd.DataFrame(rows);save('HCR_Sensitivity_Period',d)
    save('HCR_Sensitivity_Summary',d.groupby(['Scope','Rule','Technical'])[['GHG_Mt','Catch_Mt','Period_CEI','Minimum_Stock_Bmsy2050']].median().reset_index())
    print('SENSITIVITY ANALYSIS COMPLETE',len(d),flush=True)

def original_cf():
    assert (H/'Original_CF_Reproduction.json').exists();rows=[]
    for future in ['F13','F14','F15','F40','F41','F42','F67','F68','F69']:
        runs={k:read('OriginalCF_'+future+'_'+k,'Annual') for k in ['C','F']}
        g={k:v.Total_GHG_tCO2e.sum()/1e6 for k,v in runs.items()};c={k:v.Realised_Fleet_Catch_Mt.sum() for k,v in runs.items()}
        rows.append(dict(Future=future,Reduction_pct=100*(1-g['F']/g['C']),Catch_Gap_pct=100*(c['F']/c['C']-1),C_GHG_Mt=g['C'],F_GHG_Mt=g['F'],C_Catch_Mt=c['C'],F_Catch_Mt=c['F']))
    save('Original_CF_Reverified',rows)
    d=pd.DataFrame(rows);assert round(d.Reduction_pct.median(),1)==19.4
    print('ORIGINAL CF REVERIFIED',d.Reduction_pct.median(),flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    mode=sys.argv[1] if len(sys.argv)>1 else 'all'
    if mode in ['all','primary']:primary()
    if mode in ['all','matched']:matched()
    if mode in ['all','sensitivity']:sensitivity()
    if mode in ['all','original']:original_cf()
