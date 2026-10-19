"""Fixed-sample sensitivity using actual Fig.3 correction and log OLS.
Rates reported as production decay parameter d; literature q growth r maps
exactly to d=r/(1+r). No GHG, catch, sample or weight changes across rates.
"""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
from scipy.stats import linregress,spearmanr
H=Path(__file__).resolve().parent;R=H.parents[1];O=H/'analysis'
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
PD={'LL':.0186,'PS':.0426};KEY=['Gear','lon','lat','Era']

def rates(gear):
    rs=[.005,.01,.015,.02] if gear=='LL' else [.015,.02,.0435,.0485]
    return [(0.,'Uncorrected')]+[(r/(1+r),'Literature q growth '+str(100*r)+'%') for r in rs]+[(PD[gear],'Adopted')]

def main():
    a=pd.read_csv(R/'figures/Fig3/Fig3_PanelA_Annual_Factors.csv');d=pd.read_csv(R/'figures/Fig3/Fig3_PanelA_Factor_Trends.csv')
    a=a.merge(d[KEY],on=KEY,validate='many_to_one',how='inner')
    fits=[];err=[]
    for key,g in a.groupby(KEY,observed=True):
        bx=100*linregress(g.Year,np.log(g.Standard_Effort/g.Total_Catch)).slope
        by=100*linregress(g.Year,np.log(g.GHG/g.Standard_Effort)).slope
        bc=100*linregress(g.Year,np.log(g.GHG/g.Total_Catch)).slope
        row=dict(zip(KEY,key));row.update(Nominal_X=bx,Nominal_Y=by,Nominal_CEI=bc)
        # Validate all six rates against re-fitted annual factor regressions.
        for rate,label in rates(key[0]):
            es=g.Standard_Effort/(1-rate)**(g.Year-1970)
            rx=100*linregress(g.Year,np.log(es/g.Total_Catch)).slope
            ry=100*linregress(g.Year,np.log(g.GHG/es)).slope
            shift=-100*np.log1p(-rate);err.extend([abs(rx-bx-shift),abs(ry-by+shift),abs(rx+ry-bc)])
        fits.append(row)
    f=pd.DataFrame(fits);d=d.merge(f,on=KEY,validate='one_to_one')
    shift=-100*np.log1p(-d.Gear.map(PD))
    assert np.allclose(d.Nominal_X+shift,d.Effort_log_trend_pct,atol=1e-9)
    assert np.allclose(d.Nominal_Y-shift,d.GHG_Effort_log_trend_pct,atol=1e-9)
    d['Critical_d_effort_pct']=100*np.where(d.Nominal_X<0,1-np.exp(d.Nominal_X/100),0)
    d['Critical_d_per_effort_decline_pct']=100*np.where(d.Nominal_Y>0,1-np.exp(-d.Nominal_Y/100),0)
    d.to_csv(O/'Creep_Fixed_Grid_Fits.csv',index=False)
    rows=[];thresholds=[]
    for (gear,era),g in d.groupby(['Gear','Era']):
        for sp in ['All']+sorted(g.Dominant_Species.unique()):
            v=g if sp=='All' else g[g.Dominant_Species==sp];w=v.Total_GHG.to_numpy();bx=np.average(v.Nominal_X,weights=w);by=np.average(v.Nominal_Y,weights=w)
            thresholds.append(dict(Gear=gear,Era=era,Species=sp,N=len(v),Nominal_X=bx,Nominal_Y=by,Critical_d_pct=100*(1-np.exp(bx/100)) if bx<0 else 0,
                Critical_q_growth_pct=100*(np.exp(-bx/100)-1) if bx<0 else 0))
            for rate,label in rates(gear):
                sh=-100*np.log1p(-rate);x=v.Nominal_X+sh;y=v.Nominal_Y-sh
                masks={'Effort_up':x>0,'Per_effort_down':y<0,'Offset':(x>0)&(y<0),'Effort_outweighs':(x>0)&(y<0)&((x+y)>0)}
                row=dict(Gear=gear,Era=era,Species=sp,d_pct=100*rate,q_growth_pct=100*rate/(1-rate),Rate_Label=label,N=len(v),GHG_weight=w.sum(),
                         X=np.average(x,weights=w),Y=np.average(y,weights=w),CEI=np.average(x+y,weights=w))
                for name,mask in masks.items():row[name+'_count_pct']=100*mask.mean();row[name+'_GHG_pct']=100*w[mask].sum()/w.sum()
                rows.append(row)
    pd.DataFrame(rows).to_csv(O/'Creep_Trends_Fractions.csv',index=False);pd.DataFrame(thresholds).to_csv(O/'Creep_Thresholds.csv',index=False)
    # RFMO weighted grid trends: each eligible 5-degree grid has an explicit
    # dominant RFMO label, based on its positive GHG records in the same era.
    raw=pd.read_csv(R/'GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv',usecols=['Year','Gear','lon','lat','Organization','Standard_Effort','Total_Catch','GHG_emissions_median','SBT_Tonnes'])
    raw=raw[(raw.Year.between(1970,2025))&raw.Gear.isin(PD)&(raw.Standard_Effort>0)&(raw.Total_Catch>0)&(raw.GHG_emissions_median>0)].copy()
    raw['lon']=np.floor(raw.lon/5)*5+2.5;raw['lat']=np.floor(raw.lat/5)*5+2.5
    raw['Era']=np.select([raw.Year<=1990,raw.Year<=2005],['1970-1990','1991-2005'],default='2006-2025')
    tags=raw.groupby(KEY+['Organization']).GHG_emissions_median.sum().reset_index().sort_values('GHG_emissions_median',ascending=False).drop_duplicates(KEY)
    dr=d.merge(tags[KEY+['Organization']],on=KEY,validate='one_to_one')
    rr=[]
    for (gear,era,org),g in dr.groupby(['Gear','Era','Organization']):
        for rate,label in rates(gear):
            sh=-100*np.log1p(-rate);w=g.Total_GHG
            rr.append(dict(Gear=gear,Era=era,Organization=org,Rate_Label=label,d_pct=100*rate,N=len(g),GHG=w.sum(),X=np.average(g.Nominal_X+sh,weights=w),Y=np.average(g.Nominal_Y-sh,weights=w),CEI=np.average(g.Nominal_CEI,weights=w),Attribution='Dominant RFMO per grid-era; descriptive grid trend, not stock-specific'))
    pd.DataFrame(rr).to_csv(O/'Creep_RFMO_Weighted_Trends.csv',index=False)
    # SBT-stock comparison: CCSBT book, LL, SBT-dominant grids fixed over
    # 2009-2022, annual hooks / SBT catch. Reject mixed-stock interpretations.
    sb=raw[(raw.Organization=='CCSBT')&(raw.Gear=='LL')&raw.Year.between(2009,2022)].copy()
    shares=sb.groupby(['lon','lat'])[['SBT_Tonnes','Total_Catch']].sum();eligible=shares[shares.SBT_Tonnes/shares.Total_Catch>=.9].reset_index()[['lon','lat']]
    sb=sb.merge(eligible,on=['lon','lat'],validate='many_to_one')
    annual=sb.groupby('Year')[['Standard_Effort','SBT_Tonnes','Total_Catch','GHG_emissions_median']].sum().reset_index()
    annual['Nominal_hooks_per_t']=annual.Standard_Effort/annual.SBT_Tonnes
    # Official Fig.1 is a raster graphic; extraction is explicitly approximate.
    # Pixel centres chosen by maximum horizontal spread of dark-blue marks,
    # in fixed narrow annual x-windows. Source screenshot retained alongside.
    from PIL import Image
    im=np.array(Image.open(H/'sources/SBT_fig0.png').convert('RGB'));yy,xx=np.indices(im.shape[:2])
    blue=(im[:,:,0]<65)&(im[:,:,1]<65)&(im[:,:,2]<190)
    digit=[]
    for year in range(2009,2023):
        xc=112+(year-1940)*(443-112)/80
        mask=blue&(abs(xx-xc)<=2)&(yy>270)&(yy<410)
        score=mask.sum(axis=1);candidates=np.flatnonzero(score==score.max());y=float(np.median(candidates))
        digit.append(dict(Year=year,TRO_fraction_approx=(417-y)/(417-25),Pixel_x=xc,Pixel_y=y,
            Source='CCSBT 2023 assessment Fig.1, PDF p.9; digitised median, approx +/-0.01 TRO fraction'))
    digit=pd.DataFrame(digit);digit.to_csv(O/'SBT_Official_TRO_Digitised.csv',index=False)
    annual=annual.merge(digit,on='Year',validate='one_to_one');comparisons=[];associations=[]
    for rate,label in rates('LL'):
        v=annual.copy();v['d_pct']=100*rate;v['Rate_Label']=label
        v['Hooks_per_t']=v.Nominal_hooks_per_t/(1-rate)**(v.Year-2009)
        v['Effort_index']=v.Hooks_per_t/v.Hooks_per_t.iloc[0];v['TRO_index']=v.TRO_fraction_approx/v.TRO_fraction_approx.iloc[0]
        slope=100*linregress(v.Year,np.log(v.Hooks_per_t)).slope
        assoc=spearmanr(v.Hooks_per_t,v.TRO_fraction_approx).statistic
        associations.append(dict(Rate_Label=label,d_pct=100*rate,N=len(v),Effort_log_trend_pct=slope,Spearman_rho=assoc,
            SBT_catch_fraction=annual.SBT_Tonnes.sum()/annual.Total_Catch.sum(),Window='2009-2022',Inference='Descriptive association; digitised assessment and temporal dependence preclude causal inference'))
        comparisons.append(v)
    pd.concat(comparisons).to_csv(O/'SBT_Stock_Effort_Comparison.csv',index=False);pd.DataFrame(associations).to_csv(O/'SBT_Associations.csv',index=False)
    qc=dict(Max_OLS_vs_analytic_error=max(err),Fixed_grid_era_N=len(d),Annual_rows=len(a),Sample_weights_unchanged=True,CEI_invariant=True,
        Scope_note='Saved era label is 2006-2025; actual positive observations end in 2024. Display as 2006-2024; no 2025 record was removed or added.',
        Stock_source='https://www.ccsbt.org/system/files/2023-08/ESC28_16_stockAssessment2023.pdf',Digitisation='Median marks extracted from embedded raster, axes calibrated 1940 x112, 2020 x443; TRO0 x y417, TRO1 y25; approximate, not raw model outputs.')
    (O/'Creep_QC.json').write_text(json.dumps(qc,indent=2),encoding='utf-8')
    print(pd.DataFrame(thresholds).query('Species=="All"').to_string(index=False));print(pd.DataFrame(associations).to_string(index=False));print(qc)
if __name__=='__main__':main()
