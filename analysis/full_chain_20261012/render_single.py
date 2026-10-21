"""Render and validate one R figure without touching running model checkpoints."""
from pathlib import Path
import sys,os,subprocess,csv,json,hashlib,shutil
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RENV=Path(os.environ.get("R_ENV", ""))
config_path=ROOT/'reproduction_config.json'
config=json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
for key,value in config.get('environment',{}).items():os.environ.setdefault(key,value)
if config.get('path_prefixes'):os.environ['PATH']=os.pathsep.join(config['path_prefixes'])+os.pathsep+os.environ['PATH']
RSCRIPT=os.environ.get("RSCRIPT") or shutil.which("Rscript")
if not RSCRIPT: raise RuntimeError("Rscript is not on PATH; set RSCRIPT to its executable.")


def main():
    sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    script=(ROOT/sys.argv[1]).resolve()
    assert script.is_relative_to(ROOT) and script.suffix.lower()==".r"
    tag=script.stem
    manifest=HERE/(tag+"_graphics.tsv")
    if manifest.exists():manifest.unlink()
    env=os.environ.copy()
    env.update(R_PROFILE_USER=str(HERE/"r_runtime_profile.R"), FIGURE_ARTIFACT_MANIFEST=str(manifest))
    (HERE/"logs").mkdir(exist_ok=True)
    logpath=HERE/"logs"/(tag+"_manual_render.log")
    with logpath.open("w",encoding="utf-8") as log:
        result=subprocess.run([RSCRIPT,"--no-site-file",str(script)],
                               cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    log=logpath.read_text(encoding="utf-8",errors="replace")
    if result.returncode and not (result.returncode==3221225477 and manifest.exists()
                                  and not any(x in log for x in ["Error in","Error:","Execution halted"])):
        raise RuntimeError(f"Render failed: {result.returncode}, {logpath}")
    rows=[]
    with manifest.open(encoding="utf-8") as f:
        for row in csv.DictReader(f,delimiter="\t"):
            source=Path(row["Temporary"]);target=Path(row["Target"])
            assert source.is_relative_to(ROOT) and target.is_relative_to(ROOT)
            assert target.stem not in ["Fig1","Fig2","Fig3","Fig4","Fig5"]
            assert source.stat().st_size>100
            if target.suffix.lower()==".pdf":assert source.read_bytes().startswith(b"%PDF-")
            else:
                with Image.open(source) as image:image.verify()
            source.replace(target)
            rows.append(dict(Path=str(target.relative_to(ROOT)),Bytes=target.stat().st_size))
    (HERE/(tag+"_Render_QC.json")).write_text(json.dumps(dict(Source_SHA256=
        hashlib.file_digest(script.open("rb"),"sha256").hexdigest(),Exit_Code=result.returncode,
        Outputs=rows),indent=2),encoding="utf-8")
    print("Render QA PASS",script.name,len(rows),"artifacts")


if __name__=="__main__":main()
