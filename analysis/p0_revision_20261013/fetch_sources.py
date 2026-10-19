"""Preserve primary assessment inputs; no production files are overwritten."""
from pathlib import Path
import hashlib, json, zipfile
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / 'sources'
OUT.mkdir(parents=True, exist_ok=True)
url = 'https://iotc.org/sites/default/files/documents/2025/10/IOTC-2025-WPTT27-DATA07_SABET.zip'
r = requests.get(url, timeout=180)
r.raise_for_status()
p = OUT / 'IOTC-2025-WPTT27-DATA07_SABET.zip'
p.write_bytes(r.content)
with zipfile.ZipFile(p) as z:
    for member in z.infolist():
        dest = (OUT / 'BET' / member.filename).resolve()
        if not dest.is_relative_to((OUT / 'BET').resolve()):
            raise ValueError('Unsafe archive path')
    z.extractall(OUT / 'BET')
api = 'https://api.github.com/repos/Fundacion-AZTI/IOTC_YFT_2024_Assessment/git/trees/reproducible?recursive=1'
r = requests.get(api, timeout=120)
r.raise_for_status()
(OUT / 'YFT_repository_tree.json').write_text(r.text, encoding='utf-8')
manifest = {'BET': {'url': url, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()},
            'YFT_tree': {'url': api, 'sha256': hashlib.sha256(r.content).hexdigest()}}
(OUT / 'Source_Manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
for x in r.json()['tree']:
    if x['type'] == 'blob' and any(t in x['path'].lower() for t in ['catch','cpue','.dat','.rds','.rdata','report.sso']):
        print(x['path'], x.get('size'))
print('BET files:', [str(x.relative_to(OUT)) for x in (OUT/'BET').rglob('*') if x.is_file()])
