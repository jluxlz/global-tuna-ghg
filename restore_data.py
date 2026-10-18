"""Download and restore versioned release data with SHA-256 verification.

Run from a clone: python restore_data.py --download
For figure data only: python restore_data.py --download --figure-data
Large diagnostic objects and raw tables are stored in release ZIP assets. The
ordinary Git tree plus these assets reconstructs the paths in file_manifest.csv.
Private repository access requires gh authentication as an authorised reader.
"""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,shutil,subprocess,urllib.request,zipfile
ROOT=Path(__file__).resolve().parent

def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--download',action='store_true');p.add_argument('--figure-data',action='store_true');p.add_argument('--verify',action='store_true');p.add_argument('--overwrite',action='store_true');p.add_argument('--assets',type=Path,default=ROOT/'release_downloads');a=p.parse_args()
 config=json.loads((ROOT/'data/release_config.json').read_text(encoding='utf-8'))
 index=ROOT/'data/release_files.json'
 if index.exists():files=json.loads(index.read_text(encoding='utf-8'))
 else:
  with gzip.open(ROOT/'data/release_files.json.gz','rt',encoding='utf-8') as f:files=json.load(f)
 assets=json.loads((ROOT/'data/release_assets.json').read_text(encoding='utf-8'))
 if a.figure_data:files=[x for x in files if x['Path'].startswith('figures/') and not x['Path'].lower().endswith('.rds')]
 needed={x['Asset'] for x in files};a.assets.mkdir(exist_ok=True,parents=True)
 for x in assets:
  if x['Asset'] not in needed:continue
  path=a.assets/x['Asset']
  if not path.exists() and a.download:
   print('Downloading',path.name,flush=True)
   if shutil.which('gh'):
    subprocess.run(['gh','release','download',config['Tag'],'--repo',config['Repository'],'--pattern',path.name,'--dir',str(a.assets)],check=True)
   else:
    if config.get('Private'):raise RuntimeError('Install and authenticate gh to download private release data.')
    url=f"https://github.com/{config['Repository']}/releases/download/{config['Tag']}/{path.name}"
    urllib.request.urlretrieve(url,path)
  if not path.exists():raise FileNotFoundError(f'{path}: supply this release asset or use --download')
  if digest(path)!=x['SHA256']:raise RuntimeError(f'Asset checksum mismatch: {path.name}')
 byasset={k:[] for k in needed}
 for x in files:byasset[x['Asset']].append(x)
 count=0
 for asset,items in byasset.items():
  with zipfile.ZipFile(a.assets/asset) as z:
   for x in items:
    dst=(ROOT/x['Path']).resolve()
    if not dst.is_relative_to(ROOT.resolve()):raise ValueError('Unsafe manifest path')
    if dst.exists():
     if digest(dst)==x['SHA256']:continue
     if not a.overwrite:raise FileExistsError(f'Refusing to overwrite modified file: {x["Path"]}')
    dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_name(dst.name+'.restoring')
    with z.open(x['Member']) as src,tmp.open('wb') as out:shutil.copyfileobj(src,out)
    if digest(tmp)!=x['SHA256']:raise RuntimeError(f'File checksum mismatch: {x["Path"]}')
    tmp.replace(dst);count+=1
  print('Restored',asset,flush=True)
 if a.verify:
  with (ROOT/'data/file_manifest.csv').open(encoding='utf-8',newline='') as f:
   rows=list(csv.DictReader(f))
  if a.figure_data:rows=[x for x in rows if x['Path'].startswith('figures/') and not x['Path'].lower().endswith('.rds')]
  for x in rows:
   path=ROOT/x['Path']
   if not path.exists() or digest(path)!=x['SHA256']:raise RuntimeError(f'Unverified or absent file: {x["Path"]}')
  print('Manifest verified:',len(rows),'files')
 print('Restored new files:',count)

if __name__=='__main__':main()
