"""Prepare two independent Indian Ocean surplus-production data sets.

BET: official 2025 assessment inputs, all 15 catch fisheries, 1975-2024.
YFT: historical official-author SS3 input 1950-2020, all 21 fisheries.
The YFT 2024 raised-catch file is retained separately; the public reproducible
SS3 data file is not mislabelled as the updated 2024 assessment.
No second technology-creep correction is applied to standardised indices.
"""
from pathlib import Path
import pandas as pd
import numpy as np
root=Path(__file__).resolve().parents[2]
out=Path(__file__).parent/'regional_inputs';out.mkdir(exist_ok=True)
sources=Path(__file__).parent/'sources'

def save(stock,catch,cpue,baseyear,quarterbase,llps):
    catch=catch[catch.qtr>0].copy()
    catch['Year']=baseyear+(catch.qtr-quarterbase)//4
    cpue=cpue[cpue.qtr>0].copy();cpue['Year']=baseyear+(cpue.qtr-quarterbase)//4
    assert not catch.duplicated(['qtr','fleet']).any()
    assert not cpue.duplicated(['qtr','fleet']).any()
    assert (catch.Catch>=0).all() and (cpue.Index>0).all()
    annual=catch.groupby('Year').Catch.sum().rename('Catch').reset_index()
    annual.Catch/=1e6
    annual.to_csv(out/f'{stock}_catch.csv',index=False)
    catch.to_csv(out/f'{stock}_catch_quarterly.csv',index=False)
    grouped=cpue.groupby(['Year','fleet']).agg(Index=('Index',lambda v:np.exp(np.log(v).mean())),SE=('SE','max')).reset_index()
    # Quarter-level uncertainty is retained conservatively (not divided by
    # sqrt(n)); within-year covariance is unavailable.
    for value,suffix in [('Index','cpue'),('SE','se')]:
        wide=grouped.pivot(index='Year',columns='fleet',values=value).reindex(annual.Year)
        wide.columns=[f'LL_{int(c)}' for c in wide.columns];wide.index.name='Year'
        wide.reset_index().to_csv(out/f'{stock}_{suffix}.csv',index=False)
    directed=catch[catch.fleet.isin(llps)].groupby('Year').Catch.sum()/catch.groupby('Year').Catch.sum()
    directed.rename('Fleet_Catch_Fraction').reset_index().to_csv(out/f'{stock}_fleet_fraction.csv',index=False)
    print(stock,int(annual.Year.min()),int(annual.Year.max()),'catch Mt',annual.Catch.sum(),'last',annual.Catch.iloc[-1],'CPUE series',cpue.fleet.nunique())

bet=pd.read_csv(sources/'BET/SS3catch.csv').rename(columns={'YearQtr':'qtr','ModelFleet':'fleet'})
idx=pd.read_csv(sources/'BET/SS3CPUE_all.csv').rename(columns={'cpue':'Index','cv':'SE'})
idx=idx[idx.fleet.between(16,22)]
save('IOTC_BET',bet,idx,1975,193,list(range(1,12)))

# Read only the explicitly delimited catch and CPUE sections in SS3 data.
lines=(sources/'YFT/data.ss').read_text().splitlines()
def read_block(start_marker,columns):
    start=next(i for i,l in enumerate(lines) if l.startswith(start_marker))+1
    rows=[]
    for l in lines[start:]:
        content=l.split('#')[0].strip()
        if not content:continue
        tokens=content.split()
        if len(tokens)!=len(columns):break
        values=[float(x) for x in tokens]
        if values[0]==-999 and rows:break
        if values[0]>0:rows.append(values)
    return pd.DataFrame(rows,columns=columns)
yft=read_block('#_year\tseason\tfleet\tcatch\tcatch_se',['qtr','season','fleet','Catch','SE'])
idx=read_block('#_CPUE_data',['qtr','season','fleet','Index','SE'])
assert yft.qtr.min()==13 and yft.qtr.max()==296
assert set(idx.fleet)=={22.,23.,24.,25.}
save('IOTC_YFT_historical',yft,idx,1950,13,[3,6,7,8,10,11,13,16,17,19,20])
# All-fishery catch updates, used for a labelled 2021-2024 forward bridge.
rc=pd.read_csv(root/'effort_data/IOTC/source_data/IOTC-DATASETS-2026-02-23-RC-SCI-1950-2024.csv')
rc=rc[rc.SPECIES_CODE=='YFT']
rc.groupby('YEAR').CATCH.sum().rename_axis('Year').div(1e6).rename('Catch').reset_index().to_csv(out/'IOTC_YFT_complete_catch_update.csv',index=False)
