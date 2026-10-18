from pathlib import Path
import requests,sys,io,hashlib,json
from pypdf import PdfReader
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
out=Path(__file__).parent/'sources/YFT_current'
files={'CPUE_2024':'https://iotc.org/sites/default/files/documents/2024/06/IOTC-2024-WPTT26DP-14_-_Yellowfin_Joint_longline_index.pdf',
       'CPUE_2025':'https://iotc.org/sites/default/files/documents/2025/11/IOTC-2025-SC28-12E-Yellowfin_CPUE.pdf',
       'Assessment_2025_revision':'https://iotc.org/sites/default/files/documents/2025/11/IOTC-2025-SC28-13E-Yellowfin_Assessment.pdf'}
manifest=[]
for name,url in files.items():
    r=requests.get(url,timeout=180);r.raise_for_status();(out/(name+'.pdf')).write_bytes(r.content)
    pages=PdfReader(io.BytesIO(r.content)).pages
    text='\n'.join('PAGE '+str(i+1)+'\n'+p.extract_text() for i,p in enumerate(pages))
    (out/(name+'.txt')).write_text(text,encoding='utf-8')
    manifest.append(dict(name=name,url=url,sha256=hashlib.sha256(r.content).hexdigest(),pages=len(pages)))
    print(name,len(pages),'pages',flush=True)
(out/'cpue_papers_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
