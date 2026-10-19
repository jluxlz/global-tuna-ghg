# -*- coding: utf-8 -*-
"""
SF6 (step 2): exact Shapley decomposition over {quota, fuel, refrigerant,
consolidation} from the 16-combo x 9-future endpoint table.
Outputs: SF6_Shapley_Contributions.csv (+ summary print)
"""
from pathlib import Path
import os, sys, itertools, math
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import numpy as np, pandas as pd

OUT = str(Path(__file__).resolve().parents[3] / 'scenario/output/fig5')
d = pd.read_csv(os.path.join(OUT, 'SF6_Combos_2050.csv'))
d['Combo'] = d['Combo'].astype(str).str.zfill(4)
MEAS = ['q', 'f', 'r', 'c']
NAMES = {'q': 'Quota reform', 'f': 'Fuel transition', 'r': 'LN2 refrigerant', 'c': 'Consolidation'}

rows = []
for fut, g in d.groupby('Future'):
    vals = {tuple(k): v for k, v in zip(g.Combo.apply(lambda s: tuple(int(x) for x in s)), g.GHG_2050_Mt)}
    E = lambda S: vals[tuple(1 if m in S else 0 for m in MEAS)]
    base = E(set())
    full = E(set(MEAS))
    total = base - full
    for m in MEAS:
        others = [x for x in MEAS if x != m]
        phi = 0.0
        for k in range(len(others) + 1):
            for S in itertools.combinations(others, k):
                w = math.factorial(k) * math.factorial(len(MEAS) - k - 1) / math.factorial(len(MEAS))
                phi += w * (E(set(S)) - E(set(S) | {m}))
        rows.append({'Future': fut, 'Measure': NAMES[m], 'Shapley_Mt': phi,
                     'BAU_Mt': base, 'Final_Mt': full, 'Total_abatement_Mt': total,
                     'Share_pct': 100 * phi / total if total > 0 else np.nan})
sh = pd.DataFrame(rows)
sh.to_csv(os.path.join(OUT, 'SF6_Shapley_Contributions.csv'), index=False)

print('== Shapley contributions (Mt CO2e, 2050; 9 stratified futures) ==')
s = sh.groupby('Measure').Shapley_Mt.agg(['median', lambda x: x.quantile(.05), lambda x: x.quantile(.95)]).round(1)
s.columns = ['median', 'p5', 'p95']
print(s.sort_values('median', ascending=False).to_string())
print()
print('== Share of total abatement (%) ==')
s2 = sh.groupby('Measure').Share_pct.agg(['median', lambda x: x.quantile(.05), lambda x: x.quantile(.95)]).round(1)
s2.columns = ['median', 'p5', 'p95']
print(s2.sort_values('median', ascending=False).to_string())
print()
piv = sh.pivot_table(index='Future', columns='Measure', values='Shapley_Mt')
piv['Quota_wins'] = piv['Quota reform'] > piv['Fuel transition']
print('quota > fuel in every future:', bool(piv.Quota_wins.all()))
print()
print('total abatement median: %.1f Mt (BAU %.1f -> final %.1f)' % (
    sh.groupby('Future').Total_abatement_Mt.first().median(),
    sh.groupby('Future').BAU_Mt.first().median(),
    sh.groupby('Future').Final_Mt.first().median()))
