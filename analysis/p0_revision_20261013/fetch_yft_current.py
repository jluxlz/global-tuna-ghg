from pathlib import Path
import requests,json,hashlib,zipfile
out=Path(__file__).parent/'sources'; out.mkdir(exist_ok=True)
urls=[('YFT_current.zip','https://iotc.org/sites/default/files/documents/2024/10/IOTC-2024-WPTT26AS-DATA1_-_YFT_Stock_assessment_inputs_Rev1.zip'),('YFT_main_tree.json','https://api.github.com/repos/Fundacion-AZTI/IOTC_YFT_2024_Assessment/git/trees/main?recursive=1')]
for name,url in urls:
    r=requests.get(url,timeout=240);r.raise_for_status();(out/name).write_bytes(r.content)
    print(name,len(r.content),hashlib.sha256(r.content).hexdigest())
    if name.endswith('.zip'):
        with zipfile.ZipFile(out/name) as z:
            for m in z.infolist():
                if not (out/'YFT_current'/m.filename).resolve().is_relative_to((out/'YFT_current').resolve()): raise ValueError('archive traversal')
            z.extractall(out/'YFT_current')
        print('\n'.join(x.filename for x in z.infolist()))
    else:
        print('\n'.join(x['path']+' '+str(x.get('size')) for x in r.json()['tree'] if x['type']=='blob' and any(k in x['path'].lower() for k in ['cpue','data.ss','report.sso','.rdata','.rds'])))
