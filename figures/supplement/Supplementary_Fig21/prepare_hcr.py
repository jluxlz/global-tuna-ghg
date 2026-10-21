from pathlib import Path
import sys
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
A=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'
base=pd.read_csv(A/'HCR_Period.csv',dtype={'Technical':str})
base['Minimum_Stock_Bmsy2050']=base.Min_Stock_Bmsy_2050
sens=pd.read_csv(A/'HCR_Sensitivity_Period.csv',dtype={'Technical':str})
allruns=pd.concat([base,sens],ignore_index=True)
days=allruns[allruns.Scope.isin(['Main','Days280'])&allruns.Technical.isin(['000','100','111'])].copy()
days[days.Technical=='000'].to_csv(HERE/'Supplementary_Fig21_HCR_PanelA_Catch_GHG.csv',index=False)
bb=days[days.Technical=='000'][['Future','Rule','Max_Days','GHG_Mt']].rename(columns={'GHG_Mt':'Reference_GHG_Mt'})
compare=pd.concat([days[days.Technical!='000'],sens[sens.Scope=='FixedPrices']],ignore_index=True)
effects=compare.merge(bb,on=['Future','Rule','Max_Days'],validate='many_to_one')
effects['Reduction_pct']=100*(1-effects.GHG_Mt/effects.Reference_GHG_Mt)
effects['Condition']=effects.apply(lambda r:'Fixed prices / 365 d' if r.Scope=='FixedPrices' else 'Inverse prices / '+str(r.Max_Days)+' d',axis=1)
effects.to_csv(HERE/'Supplementary_Fig21_HCR_PanelB_Day_Effects.csv',index=False)
frac=sens[sens.Scope=='Fraction080'];ref=base[base.Technical=='000']
f=frac.merge(ref[['Future','Rule','Catch_Mt','GHG_Mt','Period_CEI']],on=['Future','Rule'],suffixes=('','_Reference'),validate='one_to_one')
for c in ['Catch_Mt','GHG_Mt','Period_CEI']:f[c+'_Change_pct']=100*(f[c]/f[c+'_Reference']-1)
f.to_csv(HERE/'Supplementary_Fig21_HCR_PanelC_Fraction_Effects.csv',index=False)
t=allruns[(allruns.Rule=='T')&(allruns.Technical=='000')&(allruns.Max_Days==365)&(allruns.Fraction==1)].copy()
t['Threshold']=t.B_Trigger_K.astype(str)+' / '+t.B_Closure_K.astype(str)
t.to_csv(HERE/'Supplementary_Fig21_HCR_PanelD_Thresholds.csv',index=False)
