from pathlib import Path
import sys,shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
A=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/hcr_revision_20261020/analysis'
shutil.copy2(A/'HCR_Three_Technical_Shapley.csv',HERE/'Extended_Fig8_HCR_Shapley.csv')
shutil.copy2(A/'HCR_Period.csv',HERE/'Extended_Fig8_HCR_Period.csv')
