from pathlib import Path
import requests, hashlib, json
out=Path(__file__).parent/'sources'/'YFT';out.mkdir(parents=True,exist_ok=True)
paths=['models/base/4A_io/data.ss','models/base/4A_io/Report.sso','code/ss3_data_inputs/CPUE/2_CPUE-4A_io.R','code/ss3_data_inputs/CE/2_CE-4A_io.R']
manifest=[]
for path in paths:
    url='https://raw.githubusercontent.com/Fundacion-AZTI/IOTC_YFT_2024_Assessment/reproducible/'+path
    r=requests.get(url,timeout=180);r.raise_for_status()
    p=out/Path(path).name;p.write_bytes(r.content)
    manifest.append(dict(url=url,file=p.name,sha256=hashlib.sha256(r.content).hexdigest()))
    print(p.name,len(r.content))
(out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
