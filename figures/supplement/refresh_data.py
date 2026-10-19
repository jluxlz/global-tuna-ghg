import sys
"""Refresh dependent saved-data panels using current SI numbers; no model rerun."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2]
if __name__=='__main__':
 subprocess.run([sys.executable,str(ROOT/'analysis/si_rebuild_20261012/refresh_supplement.py')],cwd=ROOT,check=True)
