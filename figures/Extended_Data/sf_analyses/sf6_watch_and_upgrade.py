# -*- coding: utf-8 -*-
"""
Watcher: when the full-81 SF6 run finishes (EXITCODE in the log and the CSV
updated), automatically
  1) recompute the exact Shapley decomposition,
  2) re-render the supplementary figures,
  3) append the final numbers to Revision_Log.md.
Runs detached; log: Temp/opencode/sf6_watch.log
"""
import os, sys, time, subprocess, io
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission'
PY = r'C:\CONDA\python.exe'
CONDA = r'C:\CONDA\Scripts\conda.exe'
RENV = r'C:\Users\11401\Desktop\r_env\R_4.5.2'
LOG = r'C:\Users\11401\AppData\Local\Temp\opencode\sf6full.log'
CSV = os.path.join(ROOT, 'scenario', 'output', 'fig5', 'SF6_Combos_2050.csv')
SHAP = os.path.join(ROOT, 'scenario', 'output', 'fig5', 'SF6_Shapley_Contributions.csv')
REVL = os.path.join(ROOT, 'manuscript', 'Revision_Log.md')

start_mtime = os.path.getmtime(CSV)
t0 = time.time()
while time.time() - t0 < 6 * 3600:
    done = False
    try:
        done = 'EXITCODE=' in io.open(LOG, encoding='utf-8', errors='ignore').read()
    except Exception:
        pass
    fresh = os.path.getmtime(CSV) > start_mtime + 5
    if done and fresh:
        break
    time.sleep(60)
else:
    print('watcher timeout', flush=True)
    sys.exit(1)

print('SF6 full run detected; upgrading...', flush=True)
subprocess.run([PY, os.path.join(ROOT, 'figures', 'Extended_Data', 'sf_analyses', 'sf6_shapley.py')],
               cwd=os.path.join(ROOT, 'figures', 'Extended_Data', 'sf_analyses'))
subprocess.run([CONDA, 'run', '--no-capture-output', '-p', RENV, 'Rscript', '--vanilla',
                os.path.join(ROOT, 'figures', 'Extended_Data', 'Extended_Fig11', 'Extended_Fig11_Shapley_Abatement_Decomposition.r')],
               cwd=os.path.join(ROOT, 'figures', 'Extended_Data', 'Extended_Fig11'))

# append final numbers to the Revision_Log
import pandas as pd
sh = pd.read_csv(SHAP)
s = sh.groupby('Measure').agg(med=('Shapley_Mt', 'median'), share=('Share_pct', 'median'))
piv = sh.pivot_table(index='Future', columns='Measure', values='Shapley_Mt')
wins = int((piv['Quota reform'] > piv['Fuel transition']).sum())
n = len(piv)
note = ('\n\n---\n**Update (%s) — SF6 full 81-future Shapley**: quota reform median '
        '%.1f Mt (%.1f%% of total abatement) vs fuel transition %.1f Mt (%.1f%%); '
        'quota > fuel in %d/%d futures. Figure and SF6_Shapley_Contributions.csv refreshed.\n'
        % (time.strftime('%Y-%m-%d %H:%M'), s.loc['Quota reform', 'med'],
           s.loc['Quota reform', 'share'], s.loc['Fuel transition', 'med'],
           s.loc['Fuel transition', 'share'], wins, n))
io.open(REVL, 'a', encoding='utf-8').write(note)
print('done; Revision_Log updated', flush=True)
