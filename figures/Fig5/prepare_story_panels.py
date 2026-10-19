"""Read saved simulations; export Fig.5 data and relocate old screening panels.

No model rerun, parameter changes or source-table writes.
"""
from pathlib import Path
import sys,json,hashlib,shutil
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OUT=ROOT/'scenario/output/fig5';P0=ROOT/'analysis/p0_revision_20261013'
AUD=ROOT/'analysis/fig5_story_layout_20261013';AUD.mkdir(exist_ok=True)
ARCH=HERE/'_archive_before_story_layout_20261013';ARCH.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'scenario'))
from scenario_seeds import require_seed_protocol
require_seed_protocol(OUT,['BAU_81_Annual.csv','Mitigation_Results_Annual.csv',
    'Fig5_QuotaOnly_Annual.csv','Fig5_Final_Combination_Annual.csv',
    'Heterogeneous_Mitigation_Results.csv'])
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
oldfiles=list(HERE.glob('Fig5_Panel*'))+list(HERE.glob('Fig5_Decision_Chain.*'))+[HERE/'plot_fig5.r',HERE/'Fig5_Caption.md',HERE/'fig5.md']
for p in oldfiles:
    dst=ARCH/p.name
    if p.is_file() and not dst.exists():shutil.copy2(p,dst)
for n in [9,11,16]:
    folder=ROOT/f'figures/supplement/Supplementary_Fig{n}'
    arc=folder/'_archive_before_story_layout_20261013';arc.mkdir(exist_ok=True)
    for p in folder.iterdir():
        if p.is_file() and not p.name.startswith('.render_') and not (arc/p.name).exists():shutil.copy2(p,arc/p.name)
def read(p,**kw):return pd.read_csv(p,**kw)
bau=read(OUT/'BAU_81_Annual.csv')
annual=read(P0/'ensemble/All_Annual.csv',dtype={'Combo':str});annual['Combo']=annual.Combo.str.zfill(4)
con=annual[(annual.Max_Days==365)&(annual.Combo=='0000')].copy()
config=['WEO','Growth','Retirement','TechCreep']
mapping=con[['Future']+config].drop_duplicates()
assert len(mapping)==81 and not mapping.duplicated(config).any()
ret={'Natural':1,'Renewal':2,'Forced':3}
assert set(bau.Retirement.unique())<=set(ret),bau.Retirement.unique()
bau['Retirement']=bau.Retirement.map(ret)
for d in [bau,mapping]:
    d['Growth']=d.Growth.round(8);d['TechCreep']=d.TechCreep.round(8)
bau=bau.merge(mapping,on=config,validate='many_to_one')
assert not bau.duplicated(['Future','Year']).any() and len(bau)==81*26
bau[['BAU_ID','Future']+config].drop_duplicates().to_csv(HERE/'Fig5_Configuration_Map.csv',index=False)
bs=bau[['Future','Year','GHG_Mt']].assign(Baseline='Fixed-catch pressure test')
cs=con[['Future','Year','Total_GHG_tCO2e']].rename(columns={'Total_GHG_tCO2e':'GHG_Mt'}).assign(Baseline='Resource-and-capacity rerun')
cs['GHG_Mt']/=1e6
a=pd.concat([bs,cs],ignore_index=True);a.to_csv(HERE/'Fig5_PanelA_BAU_Annual.csv',index=False)
summ=a.groupby(['Baseline','Year']).GHG_Mt.agg(Median='median',P5=lambda s:s.quantile(.05),P95=lambda s:s.quantile(.95)).reset_index()
summ.to_csv(HERE/'Fig5_PanelA_BAU_Summary.csv',index=False)
fmap=bau[['BAU_ID','Future']].drop_duplicates()
parts=[]
bound={'STEPS':'Low','APS':'Medium','NZE':'High'}
spec=[('Fig5_QuotaOnly_Annual.csv','Quota','GHG_QuotaOnly'),('Mitigation_Results_Annual.csv','Fuel','GHG_Mitigation'),('Fig5_Final_Combination_Annual.csv','Combined','GHG_Final')]
for fn,measure,col in spec:
    d=read(OUT/fn);d=d[d.Year==2050].copy()
    if measure=='Fuel':d=d[(d.Mitigation_Pathway=='Fuel')&(d.Mitigation_Level==d.WEO.map(bound))]
    d=d.merge(fmap,on='BAU_ID',validate='one_to_one');assert len(d)==81
    rows=d[['Future','GHG_BAU',col]].rename(columns={'GHG_BAU':'BAU_GHG_Mt',col:'Policy_GHG_Mt'})
    rows['Reduction_pct']=100*(1-rows.Policy_GHG_Mt/rows.BAU_GHG_Mt)
    rows['Baseline']='Fixed-catch pressure test';rows['Measure']=measure;parts.append(rows)
for code,measure in [('1000','Quota'),('0100','Fuel'),('1111','Combined')]:
    d=annual[(annual.Max_Days==365)&(annual.Combo==code)&(annual.Year==2050)]
    rows=d[['Future','Total_GHG_tCO2e']].merge(con[con.Year==2050][['Future','Total_GHG_tCO2e']],on='Future',validate='one_to_one',suffixes=('_policy','_bau'))
    rows=rows.rename(columns={'Total_GHG_tCO2e_policy':'Policy_GHG_Mt','Total_GHG_tCO2e_bau':'BAU_GHG_Mt'})
    rows[['Policy_GHG_Mt','BAU_GHG_Mt']]/=1e6
    rows['Reduction_pct']=100*(1-rows.Policy_GHG_Mt/rows.BAU_GHG_Mt)
    rows['Baseline']='Resource-and-capacity rerun';rows['Measure']=measure;parts.append(rows)
b=pd.concat(parts,ignore_index=True);assert len(b)==486
b.to_csv(HERE/'Fig5_PanelB_Paired_Reductions.csv',index=False)
b.groupby(['Baseline','Measure']).Reduction_pct.agg(Median='median',P5=lambda s:s.quantile(.05),P95=lambda s:s.quantile(.95)).reset_index().to_csv(HERE/'Fig5_PanelB_Reduction_Summary.csv',index=False)
c=b[b.Measure.isin(['Quota','Fuel'])].pivot(index=['Baseline','Future'],columns='Measure',values='Reduction_pct').reset_index()
c['Quota_Above_Fuel']=c.Quota>c.Fuel;c.to_csv(HERE/'Fig5_PanelC_Ranking.csv',index=False)
counts=c.groupby('Baseline').Quota_Above_Fuel.sum().to_dict()
assert counts['Resource-and-capacity rerun']==32,counts
assert c.groupby('Baseline').size().eq(81).all()
period=read(P0/'analysis/Period_Catch_GHG_CEI.csv',dtype={'Combo':str});period['Combo']=period.Combo.str.zfill(4)
d=period[(period.Max_Days==365)&period.Combo.isin(['0000','1000'])]
base=d[d.Combo=='0000'].set_index('Future');policy=d[d.Combo=='1000'].set_index('Future')
rows=[]
for metric,col,unit in [('Catch','Cumulative_Fleet_Catch_Mt','Mt catch'),('GHG','Cumulative_GHG_t','t CO2e'),('CEI','Period_CEI','t CO2e / t catch')]:
    for future in base.index:
        v0=base.at[future,col];v1=policy.at[future,col]
        rows.append(dict(Future=future,Metric=metric,BAU_Value=v0,Quota_Value=v1,Unit=unit,Change_pct=100*(v1/v0-1)))
d=pd.DataFrame(rows);d.to_csv(HERE/'Fig5_PanelD_Period_Changes.csv',index=False)
d.groupby('Metric').Change_pct.agg(Median='median',P5=lambda s:s.quantile(.05),P95=lambda s:s.quantile(.95)).reset_index().to_csv(HERE/'Fig5_PanelD_Period_Summary.csv',index=False)
eq=read(P0/'analysis/Equal_Catch_Comparison.csv');assert len(eq)==9 and eq.Within_1pct.all() and eq.Relative_Catch_Gap.abs().max()<=.01
eq=eq.merge(mapping[['Future','WEO','TechCreep']],on='Future',validate='one_to_one')
eq.to_csv(HERE/'Fig5_PanelE_Matched_Catch.csv',index=False)
# Keep relocated figures self-contained, using immutable copies of old panels.
def transfer(oldname,n,newname):
    target=ROOT/f'figures/supplement/Supplementary_Fig{n}'/newname
    if target.exists():return  # current supplied screening checkpoint
    source=ARCH/oldname
    if not source.exists():raise FileNotFoundError(f"Restore supplied screening input: {target}")
    shutil.copy2(source,target)
transfer('Fig5_PanelA_Fuel_Options.csv',9,'Supplementary_Fig9_PanelC_Fuel_Screen.csv')
transfer('Fig5_PanelC_Fuel_Curves.csv',9,'Supplementary_Fig9_PanelD_Transition_Curves.csv')
transfer('Fig5_PanelB_Quota_Species.csv',11,'Supplementary_Fig11_PanelC_Quota_Screen.csv')
# Object effects must follow the current simulations, never an archived panel.
he=read(OUT/'Heterogeneous_Mitigation_Results.csv')
keys=['Gear','Organization','Species']
screen=he.drop_duplicates(['BAU_ID']+keys).groupby(keys).GHG_BAU.sum()
selected=screen[screen>=screen.quantile(.6)].reset_index()[keys]
hc=he.merge(selected,on=keys,validate='many_to_one')
hc=hc[hc.Mitigation_Pathway.isin(['Fuel','Refrigerant','Consolidation'])].copy()
hc['obj']=hc.Organization+' | '+hc.Species+' | '+hc.Gear
hc=hc.groupby(['obj','Gear','Mitigation_Pathway'],as_index=False).Reduction_pct.median().rename(columns={'Reduction_pct':'red'})
hc=hc.sort_values(['obj','Mitigation_Pathway'])
hc.to_csv(ROOT/'figures/supplement/Supplementary_Fig16/Supplementary_Fig16_PanelB_Object_Effects.csv',index=False)
expected={'Resource-and-capacity rerun':[62.5,64.3,91.4]}
for baseline,vals in expected.items():
    got=b[b.Baseline==baseline].groupby('Measure').Reduction_pct.median().reindex(['Quota','Fuel','Combined']).round(1).tolist();assert got==vals,(got,vals)
assert d.groupby('Metric').Change_pct.median().reindex(['Catch','GHG','CEI']).round(1).tolist()==[189.3,-51.2,-82.5]
assert round(eq.GHG_Reduction_pct.median(),1)==19.4
sources=[OUT/fn for fn in ['BAU_81_Annual.csv']+[v[0] for v in spec]]+[P0/'ensemble/All_Annual.csv',P0/'analysis/Period_Catch_GHG_CEI.csv',P0/'analysis/Equal_Catch_Comparison.csv']
(AUD/'Data_QC.json').write_text(json.dumps(dict(Configuration_Map_N=81,Ranking_Counts=counts,Matched_N=9,Max_Catch_Gap=float(eq.Relative_Catch_Gap.abs().max()),Sources={str(p.relative_to(ROOT)):digest(p) for p in sources}),indent=2),encoding='utf-8')
print('Panel data verified: 81 paired futures per baseline; nine matched-catch cases.')
