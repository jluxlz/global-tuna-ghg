"""Quantify paired-seed variation without assigning probabilities to futures."""
from pathlib import Path
import sys,json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'figures/Fig5'))
import fig5_paired_rerun as D
H=Path(__file__).parent
rows=[];objects=[];struct=[]
for i in D.PILOT_FUTURES:
    for replicate in range(5):
        b=D.read_checkpoint(i,'0000',replicate).set_index('Year')
        bo=D.read_checkpoint(i,'0000',replicate,kind='Objects').set_index(['Organization','Species','Gear']).GHG_tCO2e
        bm=json.loads((D.OUT/f'F{i+1:02d}_0000_R{replicate}/Complete.json').read_text(encoding='utf-8'))
        for combo,name in [('0100','Fuel'),('0010','Refrigeration'),('0001','Consolidation'),('1000','Quota'),('1111','Combined')]:
            p=D.read_checkpoint(i,combo,replicate).set_index('Year')
            po=D.read_checkpoint(i,combo,replicate,kind='Objects').set_index(['Organization','Species','Gear']).GHG_tCO2e
            pm=json.loads((D.OUT/f'F{i+1:02d}_{combo}_R{replicate}/Complete.json').read_text(encoding='utf-8'))
            assert bm['seed']==pm['seed']
            rows.append(dict(Future=bm['future'],Replicate=replicate,Seed=bm['seed'],Measure=name,
                BAU_2050_Mt=b.at[2050,'GHG_tCO2e']/1e6,Policy_2050_Mt=p.at[2050,'GHG_tCO2e']/1e6,
                Endpoint_Reduction_pct=100*(1-p.at[2050,'GHG_tCO2e']/b.at[2050,'GHG_tCO2e']),
                Cumulative_Reduction_pct=100*(1-p.GHG_tCO2e.sum()/b.GHG_tCO2e.sum())))
            struct.append(dict(Future=bm['future'],Replicate=replicate,Measure=name,
                Retirement=bm['configuration'][2],
                Ordered_Final_Table_Hash_Identical=bm['final_structure_sha256']==pm['final_structure_sha256'],
                Max_Vessel_Count_Diff=int((b.N_Vessels-p.N_Vessels).abs().max()),
                Max_Power_Diff_kW=float((b.Total_Power_kW-p.Total_Power_kW).abs().max())))
            for (o,s,g),v in bo.items():
                objects.append(dict(Future=bm['future'],Replicate=replicate,Seed=bm['seed'],
                    Organization=o,Species=s,Gear=g,Measure=name,Reduction_pct=100*(1-po.loc[(o,s,g)]/v)))
df=pd.DataFrame(rows);obj=pd.DataFrame(objects);sd=pd.DataFrame(struct)
df.to_csv(H/'Pilot_Paired_Reductions.csv',index=False)
obj.to_csv(H/'Pilot_Object_Reductions.csv',index=False)
sd.to_csv(H/'Pilot_Fleet_Structure_Check.csv',index=False)
summary=df.groupby(['Future','Measure']).Endpoint_Reduction_pct.agg(Median='median',Minimum='min',Maximum='max').reset_index()
summary['Range_pp']=summary.Maximum-summary.Minimum
summary.to_csv(H/'Pilot_PerFuture_Summary.csv',index=False)
piv=df.pivot(index=['Future','Replicate'],columns='Measure',values='Endpoint_Reduction_pct')
rank=(piv.Quota>piv.Fuel).groupby('Future').agg(Quota_Wins='sum',Replicates='count')
rank.to_csv(H/'Pilot_Rank_Stability.csv')
ref=sd[sd.Measure=='Refrigeration']
ordinary=ref[ref.Retirement.isin([1,2])]
assert ordinary.Max_Vessel_Count_Diff.eq(0).all() and (ordinary.Max_Power_Diff_kW<1e-6).all()
out=dict(Futures=list(rank.index),Replicates_per_future=5,
    Quota_Fuel_Rank=rank.to_dict(orient='index'),
    Max_Endpoint_Range_pp=summary.groupby('Measure').Range_pp.max().to_dict(),
    Refrigeration_natural_and_renewal_capacity_identical=bool(ordinary.Max_Vessel_Count_Diff.eq(0).all() and (ordinary.Max_Power_Diff_kW<1e-6).all()),
    Refrigeration_forced_retirement_max_vessel_count_diff=int(ref.Max_Vessel_Count_Diff.max()),
    Refrigeration_forced_retirement_max_power_diff_kW=float(ref.Max_Power_Diff_kW.max()),
    Object_signs={m:dict(N=len(g),Negative=int((g.Reduction_pct<0).sum()),Min=float(g.Reduction_pct.min()),Max=float(g.Reduction_pct.max())) for m,g in obj.groupby('Measure')})
(H/'Pilot_QC.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
