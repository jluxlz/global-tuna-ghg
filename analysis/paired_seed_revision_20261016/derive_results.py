"""Trace manuscript/SI statistics to exact saved paired comparisons."""
from pathlib import Path
import sys,json,hashlib
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2];H=Path(__file__).parent
P=ROOT/'scenario/output/fig5'

def stats(x):
    return dict(Median=float(x.median()),P5=float(x.quantile(.05)),P95=float(x.quantile(.95)),
                Minimum=float(x.min()),Maximum=float(x.max()))

def extract(folder):
    bau=pd.read_csv(folder/'BAU_81_Annual.csv');q=pd.read_csv(folder/'Fig5_QuotaOnly_Annual.csv')
    m=pd.read_csv(folder/'Mitigation_Results_Annual.csv');f=pd.read_csv(folder/'Fig5_Final_Combination_Annual.csv')
    bound={'STEPS':'Low','APS':'Medium','NZE':'High'}
    s={};reductions={}
    for label,df,col in [('Quota',q,'GHG_QuotaOnly'),('Combined',f,'GHG_Final')]+[
            (label,m[(m.Mitigation_Pathway==path)&((m.Mitigation_Level.isna())|(m.Mitigation_Level==m.WEO.map(bound)))],'GHG_Mitigation')
            for label,path in [('Fuel','Fuel'),('Refrigeration','Refrigerant'),('Consolidation','Consolidation')]]:
        d=df[df.Year==2050].set_index('BAU_ID')
        assert len(d)==81
        red=100*(1-d[col]/d.GHG_BAU)
        reductions[label]=red
        s[label]=stats(red)
    sh=pd.read_csv(folder/'SF6_Shapley_Contributions.csv')
    assert len(sh)==324 and not sh.duplicated(['Future','Measure']).any()
    closure=sh.groupby('Future').agg(Total=('Total_abatement_Mt','first'),Sum=('Shapley_Mt','sum'))
    assert np.allclose(closure.Total,closure.Sum,rtol=1e-12,atol=1e-9)
    pv=sh.pivot(index='Future',columns='Measure',values='Shapley_Mt')
    s.update(Quota_Above_Fuel=int((reductions['Quota']>reductions['Fuel']).sum()),
        Shapley_Quota_Above_Fuel=int((pv['Quota reform']>pv['Fuel transition']).sum()),
        BAU_2050=stats(bau[bau.Year==2050].GHG_Mt),Final_2050=stats(f[f.Year==2050].GHG_Final),
        Shapley_Shares={name:stats(g.Share_pct) for name,g in sh.groupby('Measure')},
        Shapley_Mt={name:stats(g.Shapley_Mt) for name,g in sh.groupby('Measure')})
    return s

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    old=extract(H/'before/production_fig5');new=extract(P)
    # Cross-analysis identity: Shapley no-measure and full-measure endpoints
    # now use exactly the same simulations as the plotted pressure-test arms.
    c=pd.read_csv(P/'SF6_Combos_2050.csv',dtype={'Combo':str});c.Combo=c.Combo.str.zfill(4)
    a=pd.read_csv(P/'BAU_81_Annual.csv');f=pd.read_csv(P/'Fig5_Final_Combination_Annual.csv')
    for combo,table,col in [('0000',a,'GHG_Mt'),('1111',f,'GHG_Final')]:
        x=c[c.Combo==combo].set_index('Future').GHG_2050_Mt.sort_index()
        y=table[table.Year==2050].set_index('BAU_ID')[col].sort_index()
        assert np.array_equal(x.to_numpy(),y.to_numpy())
    panel=ROOT/'figures/Extended_Data/Extended_Fig7'
    he=pd.read_csv(P/'Heterogeneous_Mitigation_Results.csv')
    err=(he.Reduction_pct-100*(1-he.GHG_Mitigation/he.GHG_BAU)).abs().max()
    assert err<=.0005000001
    org=pd.read_csv(panel/'Extended_Fig7_PanelA_Organizations.csv').set_index('Organization')
    b=pd.read_csv(panel/'Extended_Fig7_PanelB_Object_Effects.csv')
    new['Object_Organization_Medians']=org.to_dict(orient='index')
    new['Displayed_Objects']={name:dict(Minimum=float(g.red.min()),Maximum=float(g.red.max()),Negative_N=int((g.red<0).sum())) for name,g in b.groupby('Mitigation_Pathway')}
    new['Object_Selected_Rows']=b.to_dict(orient='records')
    new['Object_Reduction_Rounding_Max_Error']=float(err)
    # Every production row must carry an auditable future-paired run record.
    records=[]
    for p in (H/'ensemble').glob('*/Complete.json'):
        d=json.loads(p.read_text(encoding='utf-8'))
        records.append(dict(Run=p.parent.name,Future=d['future'],Combo=d['combo'],
            Replicate=d['replicate'],Seed=d['seed'],Input_Signature=d['signature']))
    seeds=pd.DataFrame(records);seeds.to_csv(H/'Paired_Seed_Manifest.csv',index=False)
    legacy=seeds[(seeds.Replicate==0)&~seeds.Run.str.startswith('Feasible_')]
    assert len(legacy)==1296 and legacy.groupby('Future').Seed.nunique().eq(1).all()
    assert seeds.groupby(['Future','Replicate']).Seed.nunique().eq(1).all()
    (H/'Results_Before_After.json').write_text(json.dumps(dict(Before=old,After=new),indent=2),encoding='utf-8')
    rows=[]
    for metric in ['Quota','Fuel','Combined','Refrigeration','Consolidation']:
        rows.append(dict(Statistic=metric+'_median_2050_reduction_pct',Before=old[metric]['Median'],After=new[metric]['Median']))
    for metric in ['Quota_Above_Fuel','Shapley_Quota_Above_Fuel']:
        rows.append(dict(Statistic=metric,Before=old[metric],After=new[metric]))
    for m in ['Quota reform','Fuel transition']:
        rows.append(dict(Statistic='Shapley_share_'+m,Before=old['Shapley_Shares'][m]['Median'],After=new['Shapley_Shares'][m]['Median']))
    pd.DataFrame(rows).to_csv(H/'Headline_Changes.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':main()
