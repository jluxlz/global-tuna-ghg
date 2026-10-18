from pathlib import Path
import requests, openpyxl, json, sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
H=Path(__file__).resolve().parent
url='https://assets.publishing.service.gov.uk/media/6722567487df31a87d8c497e/ghg-conversion-factors-2024-full_set__for_advanced_users__v1_1.xlsx'
f=H/'UK_2024_GHG_factors_full.xlsx'
if not f.exists():
    r=requests.get(url,timeout=60);r.raise_for_status();f.write_bytes(r.content)
b=openpyxl.load_workbook(f,data_only=True,read_only=True)
print(b.sheetnames)
out={}
for sn in b.sheetnames:
    if 'propert' in sn.lower() or sn in ['Fuels','WTT- fuels']:
        out[sn]=[list(row) for row in b[sn].iter_rows(values_only=True)]
        print(sn)
        for row in out[sn]:
            if any('diesel' in str(v).lower() or 'petrol' in str(v).lower() or 'density' in str(v).lower() for v in row):print(row[:20])
(H/'UK_Factors_Extract.json').write_text(json.dumps({'source':url,'sheets':out},default=str,indent=2),encoding='utf-8')
