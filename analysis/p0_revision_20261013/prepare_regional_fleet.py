"""Build a conditional IOTC BET/YFT fleet component, with explicit weights."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent

def main():
    fits=[];bridge=[]
    for stock,label in [('BET','IOTC_BET'),('YFT','IOTC_YFT_historical')]:
        out=HERE/'regional_fits'/f'{label}_base'
        summary=pd.read_csv(out/'Summary.csv').iloc[0]
        if not bool(summary.QC_Pass):raise ValueError(f'Regional MCMC gate failed: {stock}')
        b=float(summary.B_Terminal_Mt);r=float(summary.r);k=float(summary.K_Mt)
        first=int(summary.Terminal_Year)
        catch=pd.read_csv(HERE/'regional_inputs'/f'{label}_catch.csv').set_index('Year').Catch
        if stock=='YFT':
            updates=pd.read_csv(HERE/'regional_inputs/IOTC_YFT_complete_catch_update.csv').set_index('Year').Catch
            for year in range(first,2024):
                c=float(catch.loc[year]) if year==first else float(updates.loc[year])
                end=b+r*b*(1-b/k)-c
                bridge.append(dict(Stock=stock,Year=year,B_Start_Mt=b,Observed_Catch_Mt=c,B_End_Mt=end,Pass=end>0))
                b=end
                if b<=0:break
            c2024=float(updates.loc[2024]);end=b+r*b*(1-b/k)-c2024
            bridge.append(dict(Stock=stock,Year=2024,B_Start_Mt=b,Observed_Catch_Mt=c2024,B_End_Mt=end,Pass=end>0))
            # The bridge fails, so retain the historical reference state only
            # for an explicitly counterfactual fleet experiment, never promote
            # it as current 2024 stock biomass.
            b=float(summary.B_Terminal_Mt);c2024=float(summary.Catch_Terminal_Mt)
        else:c2024=float(catch.loc[2024])
        fractions=pd.read_csv(HERE/'regional_inputs'/f'{label}_fleet_fraction.csv')
        fraction=float(fractions.iloc[-1].Fleet_Catch_Fraction)
        # YFT's directed fraction is from the historical assessment terminal
        # year; no undocumented reclassification of current IOTC mixed gears.
        fits.append(dict(Stock=stock,r=r,K_Mt=k,B2024_Mt=b,Catch2024_Mt=c2024,
                     Fleet_Catch_Fraction=fraction,Fit_Terminal_Year=first,
                     Reference_State_Year=first,Current_State_Validation=stock=='BET'))
    pd.DataFrame(fits).to_csv(HERE/'regional_inputs/Regional_Projection_Parameters.csv',index=False)
    pd.DataFrame(bridge).to_csv(HERE/'regional_inputs/YFT_Observed_Catch_Bridge_QC.csv',index=False)
    grid=pd.read_csv(ROOT/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv',usecols=['Year','Organization','Gear','SKJ_Tonnes','YFT_Tonnes','BET_Tonnes','ALB_Tonnes','SBT_Tonnes'])
    grid=grid[(grid.Organization=='IOTC')&grid.Year.between(2015,2024)&grid.Gear.isin(['LL','PS'])]
    gear=grid.groupby('Gear')[['SKJ_Tonnes','YFT_Tonnes','BET_Tonnes','ALB_Tonnes','SBT_Tonnes']].sum()
    a=[]
    for stock in ['BET','YFT']:
        for g in ['LL','PS']:
            a.append(dict(Stock=stock,Organization='IOTC',Gear=g,Share=float(gear.at[g,stock+'_Tonnes']/gear[stock+'_Tonnes'].sum())))
    pd.DataFrame(a).to_csv(HERE/'regional_inputs/Regional_Catch_Allocation.csv',index=False)
    weights={g:float((gear.at[g,'BET_Tonnes']+gear.at[g,'YFT_Tonnes'])/gear.loc[g].sum()) for g in gear.index}
    weights['Support']=float(gear[['BET_Tonnes','YFT_Tonnes']].to_numpy().sum()/gear.to_numpy().sum())
    (HERE/'regional_inputs/Regional_Fleet_Weights.json').write_text(json.dumps(weights,indent=2),encoding='utf-8')
    for row in fits:
        stock=row['Stock']
        pd.DataFrame([row]).to_csv(HERE/f'regional_inputs/{stock}_Projection_Parameters.csv',index=False)
        pd.DataFrame(a).query('Stock==@stock').to_csv(HERE/f'regional_inputs/{stock}_Catch_Allocation.csv',index=False)
        individual={g:float(gear.at[g,stock+'_Tonnes']/gear.loc[g].sum()) for g in gear.index}
        individual['Support']=float(gear[stock+'_Tonnes'].sum()/gear.to_numpy().sum())
        (HERE/f'regional_inputs/{stock}_Fleet_Weights.json').write_text(json.dumps(individual,indent=2),encoding='utf-8')
    print(pd.DataFrame(fits).to_string(index=False));print('Accounting weights',weights)

if __name__=='__main__':main()
