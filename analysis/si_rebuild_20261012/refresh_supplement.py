"""Compatibility entrypoint for the current figure-data bridges."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
subprocess.run([sys.executable,str(ROOT/'reproduce.py'),'refresh'],cwd=ROOT,check=True)
