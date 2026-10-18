from pathlib import Path
import shutil,json
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
files=['scenario/jabba_fit.r','figures/Extended_Data/Extended_Fig5/Extended_Fig5_build_diagnostics.r','figures/Extended_Data/Extended_Fig5/Extended_Fig5_JABBA_Diagnostics.r']
for rel in files:
    source=ROOT/rel;dest=HERE/'_archive_before_edit'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():shutil.copy2(source,dest)
lib=ROOT/'scenario/r_lib';lib.mkdir(exist_ok=True)
for p in (HERE/'R_lib').iterdir():
    if p.is_dir() and not (lib/p.name).exists():shutil.copytree(p,lib/p.name)
shutil.copy2(HERE/'Diagnostic_Package_Manifest.json',lib/'Package_Manifest.json')
ignore=ROOT/'.gitignore'
old=ignore.read_text(encoding='utf-8') if ignore.exists() else ''
if 'scenario/r_lib/' not in old:
    with ignore.open('a',encoding='utf-8') as f:f.write('\n# Task-local CRAN MCMC diagnostics binaries\nscenario/r_lib/\n')
