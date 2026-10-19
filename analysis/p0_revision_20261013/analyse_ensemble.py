from pathlib import Path
import json,itertools,math
import pandas as pd
import numpy as np

HERE=Path(__file__).parent;ROOT=HERE.parents[1];OUT=HERE/'analysis';OUT.mkdir(exist_ok=True)

def logarithmic_mean(a,b):
    if a<=0 or b<=0:raise ValueError('LMDI requires positive period totals; zero cases need explicit limiting treatment')
    return a if np.isclose(a,b,rtol=1e-12) else (a-b)/np.log(a/b)

def main():
    d=pd.read_csv(HERE/'ensemble/All_Annual.csv',dtype={'Combo':str})
    d['Combo']=d.Combo.str.zfill(4)
    d.to_csv(HERE/'ensemble/All_Annual.csv',index=False)
    keys=['Max_Days','Future','WEO','Growth','Retirement','TechCreep','Combo']
    if d.duplicated(keys+['Year']).any():raise AssertionError('Duplicate future/combo/year')
    if not (d.groupby(keys).size()==26).all():raise AssertionError('Incomplete simulation window')
    period=d.groupby(keys).agg(Cumulative_GHG_t=('Total_GHG_tCO2e','sum'),Cumulative_Fleet_Catch_Mt=('Realised_Fleet_Catch_Mt','sum'),
             Cumulative_Stock_Catch_Mt=('Realised_Stock_Catch_Mt','sum'),Cumulative_Target_Mt=('Target_Catch_Mt','sum')).reset_index()
    period['Period_CEI']=period.Cumulative_GHG_t/(period.Cumulative_Fleet_Catch_Mt*1e6)
    endpoint=d[d.Year==2050][keys+['Total_GHG_tCO2e','Realised_Fleet_Catch_Mt','CEI_tCO2e_per_t']]
    period=period.merge(endpoint,on=keys,validate='one_to_one')
    period.to_csv(OUT/'Period_Catch_GHG_CEI.csv',index=False)
    base=period[period.Combo=='0000'].set_index(['Max_Days','Future'])
    rows=[];decomposition=[]
    for x in period.itertuples():
        b=base.loc[x.Max_Days,x.Future];g0=b.Cumulative_GHG_t;g1=x.Cumulative_GHG_t
        c0=b.Cumulative_Fleet_Catch_Mt;c1=x.Cumulative_Fleet_Catch_Mt
        lm=logarithmic_mean(g1,g0)
        catch_term=lm*np.log(c1/c0);intensity_term=lm*np.log(x.Period_CEI/b.Period_CEI)
        residual=(g1-g0)-catch_term-intensity_term
        if abs(residual)>max(abs(g1),abs(g0))*1e-10:raise AssertionError('LMDI closure failed')
        decomposition.append(dict(Max_Days=x.Max_Days,Future=x.Future,Combo=x.Combo,
             Delta_GHG_Mt=(g1-g0)/1e6,Catch_Effect_Mt=catch_term/1e6,CEI_Effect_Mt=intensity_term/1e6,
             Catch_Ratio=c1/c0,CEI_Ratio=x.Period_CEI/b.Period_CEI,Residual_t=residual))
        rows.append(dict(Max_Days=x.Max_Days,Future=x.Future,Combo=x.Combo,
             Reduction_2050_pct=100*(1-x.Total_GHG_tCO2e/b.Total_GHG_tCO2e),
             Reduction_Cumulative_pct=100*(1-g1/g0),Catch_Change_pct=100*(c1/c0-1),
             CEI_Change_pct=100*(x.Period_CEI/b.Period_CEI-1)))
    reductions=pd.DataFrame(rows);reductions.to_csv(OUT/'Paired_Reductions.csv',index=False)
    pd.DataFrame(decomposition).to_csv(OUT/'Catch_CEI_LMDI.csv',index=False)
    shap=[]
    for future,g in period[period.Max_Days==365].groupby('Future'):
        gm=g[g.Combo!='C_type'].set_index('Combo')
        if len(gm)!=16:raise AssertionError('Shapley requires all 16 combinations')
        for lever in range(4):
            for metric in ['Total_GHG_tCO2e','Cumulative_GHG_t']:
                contribution=0.
                for combo in itertools.product((0,1),repeat=4):
                    if combo[lever]:continue
                    code=''.join(map(str,combo));n=sum(combo)
                    on=list(combo);on[lever]=1;on=''.join(map(str,on))
                    weight=math.factorial(n)*math.factorial(3-n)/math.factorial(4)
                    contribution+=weight*(gm.at[code,metric]-gm.at[on,metric])
                total=gm.at['0000',metric]-gm.at['1111',metric]
                shap.append(dict(Future=future,Lever=['Quota','Fuel','Refrigerant','Consolidation'][lever],Metric=metric,
                     Contribution_Mt=contribution/1e6,Total_Abatement_Mt=total/1e6,Share_pct=100*contribution/total if total!=0 else np.nan))
    shp=pd.DataFrame(shap)
    for (future,metric),g in shp.groupby(['Future','Metric']):
        if not np.isclose(g.Contribution_Mt.sum(),g.Total_Abatement_Mt.iloc[0],rtol=1e-10):raise AssertionError('Shapley efficiency failed')
    shp.to_csv(OUT/'Shapley_Contributions.csv',index=False)
    summary=reductions.groupby(['Max_Days','Combo']).agg(Endpoint_Median=('Reduction_2050_pct','median'),Endpoint_p5=('Reduction_2050_pct',lambda x:x.quantile(.05)),
            Endpoint_p95=('Reduction_2050_pct',lambda x:x.quantile(.95)),Cumulative_Median=('Reduction_Cumulative_pct','median'),
            Catch_Change_Median=('Catch_Change_pct','median'),CEI_Change_Median=('CEI_Change_pct','median')).reset_index()
    summary.to_csv(OUT/'Reduction_Summary.csv',index=False)
    count=[]
    for days,g in reductions.groupby('Max_Days'):
        wide=g.pivot(index='Future',columns='Combo',values='Reduction_2050_pct')
        count.append(dict(Max_Days=int(days),Quota_Above_Fuel=int((wide['1000']>wide['0100']).sum()),N=len(wide)))
    (OUT/'Ordering.json').write_text(json.dumps(count,indent=2),encoding='utf-8')
    pressure=pd.read_csv(ROOT/'scenario/output/fig5/BAU_81_Annual.csv')
    pressure['Future']=pressure.BAU_ID.str.replace('BAU_','F',regex=False).str.replace(r'F0(\d\d)$',r'F\1',regex=True)
    old=pressure[pressure.Year==2050].GHG_Mt
    constrained=d[(d.Max_Days==365)&(d.Combo=='0000')&(d.Year==2050)].Total_GHG_tCO2e/1e6
    (OUT/'BAU_Comparison.json').write_text(json.dumps(dict(Pressure_2050_median_Mt=float(old.median()),Constrained_2050_median_Mt=float(constrained.median()),
         Constrained_2050_p5_Mt=float(constrained.quantile(.05)),Constrained_2050_p95_Mt=float(constrained.quantile(.95))),indent=2),encoding='utf-8')
    matched=HERE/'ensemble/Matched_Catch_Annual.csv'
    if matched.exists():
        m=pd.read_csv(matched).groupby(['Future','Quota_Fraction']).agg(Catch_Mt=('Realised_Fleet_Catch_Mt','sum'),GHG_Mt=('Total_GHG_tCO2e',lambda x:x.sum()/1e6)).reset_index()
        f=period[(period.Max_Days==365)&(period.Combo=='1000')][['Future','Cumulative_Fleet_Catch_Mt','Cumulative_GHG_t']]
        m=m.merge(f,on='Future',validate='many_to_one');m['Relative_Catch_Gap']=m.Catch_Mt/m.Cumulative_Fleet_Catch_Mt-1
        m['F_vs_C_GHG_Reduction_pct']=100*(1-m.Cumulative_GHG_t/1e6/m.GHG_Mt)
        m.to_csv(OUT/'Matched_Catch_All_Comparisons.csv',index=False)
        best=m.loc[m.groupby('Future').Relative_Catch_Gap.apply(lambda x:x.abs().idxmin())].copy()
        best['Within_5pct_Catch']=best.Relative_Catch_Gap.abs()<=.05
        best.to_csv(OUT/'Matched_Catch_Closest.csv',index=False)
    equal=HERE/'ensemble/Equal_Catch_Matched.csv'
    if equal.exists():
        pd.read_csv(equal).to_csv(OUT/'Equal_Catch_Comparison.csv',index=False)
    print(summary.to_string(index=False));print('ORDERING',count)

if __name__=='__main__':main()
