"""Exact accounting decomposition of saved, reproduced matched-catch runs.

The species allocation uses the model's effort-demand partitions, only for
activity-scalable LL/PS fuel and bait. It is an accounting allocation, not a
claim that the species-specific physical fuel use was observed.
"""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
H=Path(__file__).resolve().parent;O=H/'analysis';O.mkdir(exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8',errors='replace')

def lmean(a,b):
    equal=np.isclose(a,b,rtol=1e-10,atol=0)
    out=np.empty(len(a));out[equal]=(a[equal]+b[equal])/2
    out[~equal]=(a[~equal]-b[~equal])/(np.log(a[~equal])-np.log(b[~equal]))
    return out

def main():
    totals=[];terms=[];annuals=[];species=[];standard=[];bio=[];procs=[];gears=[];closures=[]
    for future in ['F13','F14','F15','F40','F41','F42','F67','F68','F69']:
        runs={}
        for rule in ['C','F']:
            folder=H/'matched_capture'/(future+'_'+rule)
            assert (folder/'Complete.json').exists(),folder
            runs[rule]={n:pd.read_csv(folder/(n+'.csv')) for n in ['Annual','Stocks','Effort','Groups','Cells']}
            a=runs[rule]['Annual'].copy();a['Future']=future;a['Rule']=rule;annuals.append(a)
            g=runs[rule]['Groups'].copy();g['Future']=future;g['Rule']=rule;gears.append(g)
            for col in ['GHG_Fuel_CO2','GHG_Fuel_CH4','GHG_Fuel_N2O','GHG_Fuel_WtT','GHG_Build','GHG_Refrig','Diag_Maint','Diag_Gear','Diag_Bait']:
                procs.append(dict(Future=future,Rule=rule,Process=col,GHG_Mt=g[col].sum()/1e6))
        # Collapse effort-scalable emissions over gears before species-year LMDI.
        # Hooks and sets are not mixed: U is common physical kW-days.
        cell={k:v['Cells'].groupby(['Stock','Year'])[['Catch_t','Realised_kW_days','Variable_GHG_t']].sum() for k,v in runs.items()}
        tc={k:d.Catch_t.sum() for k,d in cell.items()}
        sc={k:d.groupby('Stock').Catch_t.sum() for k,d in cell.items()}
        x=cell['C'].join(cell['F'],lsuffix='_C',rsuffix='_F')
        valid=(x>0).all(axis=1)
        v=x.loc[valid].copy();factors={}
        for k in ['C','F']:
            s=v.index.get_level_values('Stock').map(sc[k]).to_numpy()
            c=v['Catch_t_'+k].to_numpy();u=v['Realised_kW_days_'+k].to_numpy();g=v['Variable_GHG_t_'+k].to_numpy()
            factors[k]=np.column_stack([np.full(len(v),tc[k]),s/tc[k],c/s,u/c,g/u])
            assert np.allclose(np.prod(factors[k],axis=1),g,rtol=1e-12)
        w=lmean(v.Variable_GHG_t_F.to_numpy(),v.Variable_GHG_t_C.to_numpy())
        contribution=np.sum(w[:,None]*np.log(factors['F']/factors['C']),axis=0)/1e6
        labels=['Cumulative catch scale','Species composition','Within-species catch timing','Effort per catch','GHG per effort']
        values=dict(zip(labels,contribution))
        values['Structural-zero cells']=(x.loc[~valid,'Variable_GHG_t_F'].sum()-x.loc[~valid,'Variable_GHG_t_C'].sum())/1e6
        for gearset,label in [(['LL','PS'],'LL/PS materials, gear and leakage'),(['TP','SA'],'Support vessels')]:
            gg={k:d['Groups'].loc[d['Groups'].Gear.isin(gearset)] for k,d in runs.items()}
            col='Fixed_GHG_t' if gearset==['LL','PS'] else 'GHG_t'
            values[label]=(gg['F'][col].sum()-gg['C'][col].sum())/1e6
        orig={k:d['Annual'].Total_GHG_tCO2e.sum()/1e6 for k,d in runs.items()}
        delta=orig['F']-orig['C'];error=sum(values.values())-delta
        assert abs(error)<1e-8,(future,error)
        closures.append(dict(Future=future,Whole_fleet_delta_Mt=delta,Decomposed_delta_Mt=sum(values.values()),Residual_Mt=error,
            Positive_common_cells=int(valid.sum()),Structural_zero_cells=int((~valid).sum()),Variable_scope_fraction_C=cell['C'].Variable_GHG_t.sum()/1e6/orig['C']))
        for label,val in values.items():terms.append(dict(Future=future,Term=label,Delta_Mt=val,Percent_C_total=100*val/orig['C'],Share_net_difference_pct=100*val/delta))
        row=dict(Future=future,GHG_C_Mt=orig['C'],GHG_F_Mt=orig['F'],Catch_C_Mt=tc['C']/1e6,Catch_F_Mt=tc['F']/1e6,
                 Reduction_pct=100*(1-orig['F']/orig['C']),Catch_difference_pct=100*(tc['F']/tc['C']-1))
        # Common species weights, then common species-year weights. These are
        # static accounting comparisons, with each run's existing intensities.
        ss={k:d.groupby('Stock')[['Catch_t','Variable_GHG_t']].sum() for k,d in cell.items()}
        cw=(ss['C'].Catch_t/tc['C']+ss['F'].Catch_t/tc['F'])/2
        cei={k:ss[k].Variable_GHG_t/ss[k].Catch_t for k in ss}
        sp_std={k:float((cw*cei[k]).sum()) for k in ss}
        aw=(cell['C'].Catch_t/tc['C']+cell['F'].Catch_t/tc['F'])/2
        common=(cell['C'].Catch_t>0)&(cell['F'].Catch_t>0)
        aw_common=aw.loc[common]/aw.loc[common].sum()
        at_std={k:float((aw_common*(cell[k].Variable_GHG_t/cell[k].Catch_t).loc[common]).sum()) for k in cell}
        row.update(Variable_GHG_reduction_pct=100*(1-cell['F'].Variable_GHG_t.sum()/cell['C'].Variable_GHG_t.sum()),
                   Species_standardised_intensity_reduction_pct=100*(1-sp_std['F']/sp_std['C']),
                   Species_year_standardised_intensity_reduction_pct=100*(1-at_std['F']/at_std['C']),
                   Common_cell_Catch_C_fraction=cell['C'].loc[common].Catch_t.sum()/tc['C'],
                   Common_cell_Catch_F_fraction=cell['F'].loc[common].Catch_t.sum()/tc['F'])
        totals.append(row)
        for stock in ss['C'].index:
            species.append(dict(Future=future,Stock=stock,**{f'{q}_{k}':float(ss[k].loc[stock,q]) for k in ss for q in ['Catch_t','Variable_GHG_t']},
                                Catch_share_C=float(ss['C'].loc[stock,'Catch_t']/tc['C']),Catch_share_F=float(ss['F'].loc[stock,'Catch_t']/tc['F'])))
        for k in runs:
            b=runs[k]['Stocks'].merge(cell[k].reset_index(),on=['Stock','Year'],validate='one_to_one')
            b['Effort_per_t']=b.Realised_kW_days/b.Catch_t.replace(0,np.nan)
            b['Required_effort_per_t']=runs[k]['Cells'].groupby(['Stock','Year']).Required_kW_days.sum().reindex(pd.MultiIndex.from_frame(b[['Stock','Year']])).to_numpy()/b.Catch_t.replace(0,np.nan)
            b['Future']=future;b['Rule']=k;bio.append(b)
    for name,rows in [('Matched_Mechanism_Summary',totals),('Matched_LMDI_Terms',terms),('Matched_Annual',pd.concat(annuals)),('Matched_Species',species),
                       ('Matched_Stock_Effort',pd.concat(bio)),('Matched_Processes',procs),('Matched_Gear_Annual',pd.concat(gears)),('Matched_Closure',closures)]:
        (rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows)).to_csv(O/(name+'.csv'),index=False)
    t=pd.DataFrame(totals);z=pd.DataFrame(terms);a=pd.concat(annuals)
    yearly=a.pivot(index=['Future','Year'],columns='Rule',values='Total_GHG_tCO2e');yearly['Saving_Mt']=(yearly.C-yearly.F)/1e6
    yearly=yearly.reset_index();yearly['Period']=pd.cut(yearly.Year,[2024,2034,2044,2050],labels=['2025-2034','2035-2044','2045-2050'])
    periods=yearly.groupby(['Future','Period'],observed=True).Saving_Mt.sum().reset_index();periods['Share_pct']=100*periods.Saving_Mt/periods.Future.map(yearly.groupby('Future').Saving_Mt.sum())
    periods.to_csv(O/'Matched_Savings_Period.csv',index=False)
    gp=pd.concat(gears).groupby(['Future','Rule','Gear']).agg(GHG_t=('GHG_t','sum'),Effort=('Realised_kW_days','sum')).reset_index()
    gp=gp.pivot(index=['Future','Gear'],columns='Rule',values=['GHG_t','Effort'])
    gp['Delta_Mt']=(gp.GHG_t.F-gp.GHG_t.C)/1e6;gp=gp.reset_index();gp.columns=['_'.join(c).strip('_') for c in gp.columns]
    gp['Net_saving_share_pct']=100*gp.Delta_Mt/gp.Future.map(gp.groupby('Future').Delta_Mt.sum())
    gp.to_csv(O/'Matched_Gear_Period.csv',index=False)
    bm=pd.concat(bio);stats=[]
    for (future,stock),v in bm.groupby(['Future','Stock']):
        v=v.pivot(index='Year',columns='Rule',values=['B_Start_Mt','Effort_per_t','Catch_t','Realised_kW_days'])
        stats.append(dict(Future=future,Stock=stock,Mean_B_ratio_F_C=(v.B_Start_Mt.F/v.B_Start_Mt.C).mean(),
            Cum_effort_ratio_F_C=v.Realised_kW_days.F.sum()/v.Realised_kW_days.C.sum(),Cum_catch_ratio_F_C=v.Catch_t.F.sum()/v.Catch_t.C.sum(),
            Period_effort_C=v.Realised_kW_days.C.sum()/v.Catch_t.C.sum(),Period_effort_F=v.Realised_kW_days.F.sum()/v.Catch_t.F.sum()))
    pd.DataFrame(stats).to_csv(O/'Matched_Stock_Mechanism.csv',index=False)
    aa=a.pivot(index=['Future','Year'],columns='Rule',values=['N_Vessels','Total_Power_kW','Mean_Age','Mean_LOA'])
    for col in ['N_Vessels','Total_Power_kW','Mean_Age','Mean_LOA']:assert np.allclose(aa[col].C,aa[col].F,rtol=1e-12)
    print(t.to_string(index=False));print(z.groupby('Term').Delta_Mt.agg(['min','median','max']).to_string());print(periods.groupby('Period',observed=True).Share_pct.median())

if __name__=='__main__':main()
