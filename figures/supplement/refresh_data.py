"""Refresh the current scientific panel inputs through the main workflow."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
if __name__=='__main__':subprocess.run([sys.executable,str(ROOT/'reproduce.py'),'refresh'],cwd=ROOT,check=True)
