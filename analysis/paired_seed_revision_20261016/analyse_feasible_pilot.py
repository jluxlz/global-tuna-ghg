"""Repeated-seed diagnostic of the feasible-catch comparison, not a forecast CI."""
from pathlib import Path
import sys,json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'figures/Fig5'))
import fig5_paired_rerun as D
H=Path(__file__).parent
rows=[];max_error=0.
original=pd.read_csv(ROOT/'analysis/p0_revision_20261013/ensemble/All_Annual.csv',dtype={'Combo':str})
original.Combo=original.Combo.str.zfill(4)
for i in D.PILOT_FUTURES:
    future=f'F{i+1:02d}'
    for replicate in range(5):
        folder=D.OUT/f'Feasible_{future}_0000_R{replicate}'
        base=pd.read_csv(folder/'Annual.csv').set_index('Year')
        bm=json.loads((folder/'Complete.json').read_text(encoding='utf-8'))
        if replicate==0:
            oldbase=original[(original.Max_Days==365)&(original.Future==future)&(original.Combo=='0000')].set_index('Year')
            error=float((base.GHG_tCO2e-oldbase.Total_GHG_tCO2e).abs().max())
            max_error=max(error,max_error)
            assert np.allclose(base.GHG_tCO2e,oldbase.Total_GHG_tCO2e,rtol=1e-12,atol=1e-6)
        for c,name in [('1000','Quota'),('0100','Fuel'),('1111','Combined')]:
            folder=D.OUT/f'Feasible_{future}_{c}_R{replicate}'
            d=pd.read_csv(folder/'Annual.csv').set_index('Year')
            m=json.loads((folder/'Complete.json').read_text(encoding='utf-8'));assert m['seed']==bm['seed']
            if replicate==0:
                old=original[(original.Max_Days==365)&(original.Future==future)&(original.Combo==c)].set_index('Year')
                error=float((d.GHG_tCO2e-old.Total_GHG_tCO2e).abs().max());max_error=max(error,max_error)
                assert np.allclose(d.GHG_tCO2e,old.Total_GHG_tCO2e,rtol=1e-12,atol=1e-6)
            rows.append(dict(Future=future,Replicate=replicate,Seed=m['seed'],Measure=name,
                BAU_2050_Mt=float(base.at[2050,'GHG_tCO2e']/1e6),
                Policy_2050_Mt=float(d.at[2050,'GHG_tCO2e']/1e6),
                Endpoint_Reduction_pct=100*(1-d.at[2050,'GHG_tCO2e']/base.at[2050,'GHG_tCO2e']),
                Cumulative_Reduction_pct=100*(1-d.GHG_tCO2e.sum()/base.GHG_tCO2e.sum())))
df=pd.DataFrame(rows);df.to_csv(H/'Feasible_Pilot_Paired_Reductions.csv',index=False)
summary=df.groupby(['Future','Measure']).Endpoint_Reduction_pct.agg(Median='median',Minimum='min',Maximum='max').reset_index()
summary['Range_pp']=summary.Maximum-summary.Minimum
summary.to_csv(H/'Feasible_Pilot_PerFuture_Summary.csv',index=False)
p=df.pivot(index=['Future','Replicate'],columns='Measure',values='Endpoint_Reduction_pct')
rank=(p.Quota>p.Fuel).groupby('Future').agg(Quota_Wins='sum',Replicates='count')
rank.to_csv(H/'Feasible_Pilot_Rank_Stability.csv')
largest=summary[summary.Measure=='Combined'].sort_values('Range_pp',ascending=False).iloc[0].Future
lc=df[(df.Future==largest)&(df.Measure=='Combined')]
out=dict(Futures=list(rank.index),Replicates_per_future=5,
    Primary_seed_reproduction_max_abs_error_tCO2e=max_error,
    Quota_Fuel_Rank=rank.to_dict(orient='index'),
    Max_Endpoint_Range_pp=summary.groupby('Measure').Range_pp.max().to_dict(),
    Median_WithinFuture_Range_pp=summary.groupby('Measure').Range_pp.median().to_dict(),
    Largest_Combined_Range_Future=largest,
    Largest_Combined_Range_Absolute_Mt=dict(BAU_Minimum=float(lc.BAU_2050_Mt.min()),
        BAU_Maximum=float(lc.BAU_2050_Mt.max()),Policy_Minimum=float(lc.Policy_2050_Mt.min()),
        Policy_Maximum=float(lc.Policy_2050_Mt.max())),
    note='Five selected futures; replicated-seed ranges are not 81-future uncertainty intervals or forecast probabilities.')
(H/'Feasible_Pilot_QC.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
