"""Extract the preserved official SBT plot; no invented numeric trajectory."""
from pathlib import Path
import sys,json,hashlib
from pypdf import PdfReader
H=Path(__file__).resolve().parent;R=H.parents[1]
p=R/'analysis/manuscript_extended_20261012/verified_references/CCSBT_SBT_2023.pdf'
page=PdfReader(p).pages[8]
for i,im in enumerate(page.images):im.image.save(H/f'sources/SBT_fig{i}.png')
sources=[dict(Source='CCSBT official 2023 assessment, Fig.1, PDF page9',URL='https://www.ccsbt.org/system/files/2023-08/ESC28_16_stockAssessment2023.pdf',
    File=str(p.relative_to(R)),SHA256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),Use='Approximate digitisation of median TRO; precision +/-0.01 fraction, not posterior interval'),
 dict(Source='Archived author YFT model, reproducible branch 4A_io, through2020',URL='https://raw.githubusercontent.com/Fundacion-AZTI/IOTC_YFT_2024_Assessment/reproducible/models/base/4A_io/Report.sso',
    File='analysis/p0_revision_20261013/sources/YFT/Report.sso',Use='Native spawning-output history only; not current official assessment ensemble'),
 dict(Source='Hoyle2024, IOTC-2024-WPTT26(DP)-16rev3',URL='https://iotc.org/sites/default/files/documents/2024/07/IOTC-2024-WPTT26DP-16rev3_-_Effort_creep.pdf',Use='Index-specific catchability scenarios, not exact adopted rates')]
(H/'sources/Source_Manifest.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
print('Preserved official raster and source provenance prepared.')
