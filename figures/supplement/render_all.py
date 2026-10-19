"""Render the current SI figures in manuscript order, without running models.

python figures/supplement/render_all.py         # figures 1-20
python figures/supplement/render_all.py 3 14 15  # selected figures
"""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def main():
 sys.stdout.reconfigure(encoding='utf-8',errors='replace')
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('figures',nargs='*',type=int)
 selected=parser.parse_args().figures or list(range(1,21))
 if any(n not in range(1,21) for n in selected):parser.error('Figure numbers must be between 1 and 20.')
 completed=[]
 for n in selected:
  prefix='validation_20261018/' if n in (5,15,19) else ''
  script=f'figures/supplement/{prefix}Supplementary_Fig{n}/Supplementary_Fig{n}.r'
  subprocess.run([sys.executable,str(ROOT/'analysis/full_chain_20261012/render_single.py'),script],cwd=ROOT,check=True)
  completed.append(n)
  (HERE/'Render_Status.json').write_text(json.dumps(dict(Requested=selected,Completed=completed),indent=2),encoding='utf-8')
 print('SI render complete:',', '.join(map(str,completed)))
if __name__=='__main__':main()
