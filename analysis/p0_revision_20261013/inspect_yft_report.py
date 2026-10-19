from pathlib import Path
import requests, hashlib, json
from pypdf import PdfReader
import io
out=Path(__file__).parent/'sources'/'YFT_current'
url='https://iotc.org/sites/default/files/documents/2024/11/2024_stock_assessment_of_YFTrev2.pdf'
r=requests.get(url,timeout=240);r.raise_for_status()
(out/'Official_2024_Assessment.pdf').write_bytes(r.content)
doc=PdfReader(io.BytesIO(r.content)).pages
text='\n'.join('PAGE '+str(i+1)+'\n'+page.extract_text() for i,page in enumerate(doc))
(out/'Official_2024_Assessment.txt').write_text(text,encoding='utf-8')
print('pages',len(doc),'sha256',hashlib.sha256(r.content).hexdigest())
for i,page in enumerate(doc):
    t=page.extract_text()
    if ('CPUE' in t and 'Table' in t) or 'github' in t:
        print('PAGE',i+1,t[:180].replace('\n',' '))
