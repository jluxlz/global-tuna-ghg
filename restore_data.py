"""Restore the complete scientific data archive, or verify an expanded package."""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,shutil,subprocess,urllib.request,zipfile
ROOT=Path(__file__).resolve().parent

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def download(name,tag,repo,directory):
    directory.mkdir(parents=True,exist_ok=True)
    if shutil.which('gh'):
        subprocess.run(['gh','release','download',tag,'--repo',repo,'--pattern',name,'--dir',str(directory)],check=True)
    else:
        urllib.request.urlretrieve(f'https://github.com/{repo}/releases/download/{tag}/{name}',directory/name)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true');parser.add_argument('--verify',action='store_true')
    parser.add_argument('--figure-data',action='store_true');parser.add_argument('--overwrite',action='store_true')
    parser.add_argument('--assets',type=Path,default=ROOT/'release_downloads');args=parser.parse_args()
    with (ROOT/'data/file_manifest.csv').open(encoding='utf-8',newline='') as stream:rows=list(csv.DictReader(stream))
    if args.figure_data:rows=[x for x in rows if x['Path'].startswith('figures/') and not x['Path'].lower().endswith('.rds')]
    # An expanded complete package already contains the data and needs no download.
    if args.verify and all((ROOT/x['Path']).is_file() and digest(ROOT/x['Path'])==x['SHA256'] for x in rows):
        print('Manifest verified:',len(rows),'files. The complete package is ready; no restoration is needed.');return
    config=json.loads((ROOT/'data/release_config.json').read_text(encoding='utf-8'))
    plain=ROOT/'data/release_files.json'
    if plain.exists():files=json.loads(plain.read_text(encoding='utf-8'))
    else:
        with gzip.open(ROOT/'data/release_files.json.gz','rt',encoding='utf-8') as stream:files=json.load(stream)
    if args.figure_data:files=[x for x in files if x['Path'].startswith('figures/') and not x['Path'].lower().endswith('.rds')]
    assets=json.loads((ROOT/'data/release_assets.json').read_text(encoding='utf-8'))
    needed={x['Asset'] for x in files};args.assets.mkdir(parents=True,exist_ok=True)
    for asset in assets:
        if asset['Asset'] not in needed:continue
        tag=asset.get('Tag',config['Tag']);path=args.assets/asset['Asset']
        if not path.exists() and args.download:download(path.name,tag,config['Repository'],args.assets)
        if not path.exists():raise FileNotFoundError(f'Supply {path.name} in {args.assets}, or use --download.')
        expected=asset.get('SHA256')
        if expected is None:
            # A ZIP cannot contain its own checksum. The expanded bundle uses
            # the checksum sidecar from its own release only if repair is needed.
            checksum=args.assets/asset['Checksum_File']
            if not checksum.exists() and args.download:download(checksum.name,tag,config['Repository'],args.assets)
            if not checksum.exists():raise FileNotFoundError(f'Supply {checksum.name} or use --download to verify this archive.')
            matches=[line.split()[0] for line in checksum.read_text(encoding='utf-8').splitlines() if line.split() and line.split()[-1].lstrip('*')==path.name]
            if len(matches)!=1:raise RuntimeError('Archive checksum entry is missing or ambiguous.')
            expected=matches[0]
        if digest(path)!=expected:raise RuntimeError('Archive checksum mismatch: '+path.name)
    count=0
    for name in sorted(needed):
        with zipfile.ZipFile(args.assets/name) as archive:
            for item in (x for x in files if x['Asset']==name):
                dst=(ROOT/item['Path']).resolve()
                if not dst.is_relative_to(ROOT.resolve()):raise ValueError('Unsafe manifest path')
                if dst.exists():
                    if digest(dst)==item['SHA256']:continue
                    if not args.overwrite:raise FileExistsError('Refusing to overwrite modified file: '+item['Path'])
                dst.parent.mkdir(parents=True,exist_ok=True);temp=dst.with_name(dst.name+'.restoring')
                with archive.open(item['Member']) as src,temp.open('wb') as out:shutil.copyfileobj(src,out)
                if digest(temp)!=item['SHA256']:raise RuntimeError('File checksum mismatch: '+item['Path'])
                temp.replace(dst);count+=1
        print('Restored',name,flush=True)
    if args.verify:
        for row in rows:
            path=ROOT/row['Path']
            if not path.is_file() or digest(path)!=row['SHA256']:raise RuntimeError('Unverified or absent file: '+row['Path'])
        print('Manifest verified:',len(rows),'files')
    print('Restored new files:',count)

if __name__=='__main__':main()
