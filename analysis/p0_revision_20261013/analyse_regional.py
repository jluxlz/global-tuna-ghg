from pathlib import Path
import pandas as pd
import numpy as np
HERE=Path(__file__).parent;OUT=HERE/'analysis'

def main():
    annual=[];stocks=[];comparisons=[]
    for stock in ['BET','YFT']:
        d=pd.read_csv(HERE/'ensemble'/f'Regional_{stock}_All_Annual.csv',dtype={'Combo':str})
        d.Combo=d.Combo.map(lambda x:x.zfill(4) if x.isdecimal() else x);annual.append(d)
        s=pd.read_csv(HERE/'ensemble'/f'Regional_{stock}_All_Stocks.csv',dtype={'Combo':str});s.Combo=s.Combo.map(lambda x:x.zfill(4) if x.isdecimal() else x);stocks.append(s)
        period=d.groupby(['Future','Combo','Reference_State_Year']).agg(Catch_Mt=('Realised_Fleet_Catch_Mt','sum'),GHG_Mt=('Total_GHG_tCO2e',lambda x:x.sum()/1e6)).reset_index()
        period['CEI']=period.GHG_Mt/period.Catch_Mt
        end=d[d.Year==2050][['Future','Combo','Total_GHG_tCO2e']];period=period.merge(end,on=['Future','Combo'],validate='one_to_one')
        base=period[period.Combo=='0000'].set_index('Future')
        for x in period.itertuples():
            b=base.loc[x.Future]
            g0,g1=b.GHG_Mt,x.GHG_Mt
            lm=g0 if np.isclose(g0,g1,rtol=1e-12) else (g1-g0)/np.log(g1/g0)
            comparisons.append(dict(Stock=stock,Future=x.Future,Combo=x.Combo,Reference_State_Year=x.Reference_State_Year,
                 Cumulative_Catch_Mt=x.Catch_Mt,Cumulative_GHG_Mt=g1,Period_CEI=x.CEI,
                 Endpoint_Reduction_pct=100*(1-x.Total_GHG_tCO2e/b.Total_GHG_tCO2e),Cumulative_Reduction_pct=100*(1-g1/g0),
                 Catch_Change_pct=100*(x.Catch_Mt/b.Catch_Mt-1),CEI_Change_pct=100*(x.CEI/b.CEI-1),
                 Catch_Effect_Mt=lm*np.log(x.Catch_Mt/b.Catch_Mt),CEI_Effect_Mt=lm*np.log(x.CEI/b.CEI)))
    pd.concat(annual).to_csv(OUT/'Regional_Annual.csv',index=False);pd.concat(stocks).to_csv(OUT/'Regional_Stocks.csv',index=False)
    c=pd.DataFrame(comparisons);c.to_csv(OUT/'Regional_Paired_Comparisons.csv',index=False)
    summary=c.groupby(['Stock','Reference_State_Year','Combo']).agg(Endpoint_Median=('Endpoint_Reduction_pct','median'),Endpoint_p5=('Endpoint_Reduction_pct',lambda x:x.quantile(.05)),
            Endpoint_p95=('Endpoint_Reduction_pct',lambda x:x.quantile(.95)),Cumulative_Median=('Cumulative_Reduction_pct','median'),
            Catch_Change_Median=('Catch_Change_pct','median'),CEI_Change_Median=('CEI_Change_pct','median')).reset_index()
    summary.to_csv(OUT/'Regional_Reduction_Summary.csv',index=False);print(summary.to_string(index=False))

if __name__=='__main__':main()
