"""Row-level conservation and physical interface checks on real pilot runs."""
from pathlib import Path
import numpy as np
import pandas as pd
out=Path(__file__).parent
results=[]
for case in ['BAU','C','F']:
    h=pd.read_csv(out/f'pilot_{case}_annual.csv')
    b=pd.read_csv(out/f'pilot_{case}_stocks.csv')
    e=pd.read_csv(out/f'pilot_{case}_effort.csv')
    assert not b.duplicated(['Year','Stock']).any()
    assert not e.duplicated(['Year','Organization','Gear']).any()
    balance=(b.B_Start_Mt+b.Growth_Mt-b.Realised_Stock_Catch_Mt-b.B_End_Mt).abs().max()
    assert balance<1e-10
    assert (b.B_End_Mt>=0).all()
    assert (b.Realised_Stock_Catch_Mt<=b.Target_Catch_Mt+1e-10).all()
    assert (e.Realised_kW_days<=e.Capacity_kW_days+1e-6).all()
    assert (e.Realised_kW_days<=e.Required_kW_days+1e-6).all()
    assert np.allclose(h.CEI_tCO2e_per_t*h.Realised_Fleet_Catch_Mt*1e6,h.Total_GHG_tCO2e)
    for _,group in b.groupby('Stock'):
        assert np.allclose(group.B_End_Mt.iloc[:-1],group.B_Start_Mt.iloc[1:])
    assert np.allclose(b.groupby('Year').Realised_Fleet_Catch_Mt.sum(),h.Realised_Fleet_Catch_Mt)
    results.append(dict(Case=case,Mass_balance_error_Mt=balance,Years=len(h),Stock_rows=len(b),Status='PASS'))
pd.DataFrame(results).to_csv(out/'Coupling_Pilot_QC.csv',index=False)
print('PASS: exact stock transitions, catch conservation, quota and physical capacity ceilings, GHG=C*CEI')
