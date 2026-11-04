"""Build production notebook package; preserve the original 83-file loading engine."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
NAME='DATAIKU_GOLD_ONECLICK_PROD_20261104_R2.zip'


def main():
    files={p.relative_to(PACKAGE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(PACKAGE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
           and p.suffix!='.pyc' and p.name!='FLOW_MANIFEST.json'}
    assert not any(n.startswith('sample/') or '.part0' in n for n in files)
    assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in files)
    parent=json.loads((HERE/'PARENT_ENGINE_HASHES.json').read_text())
    assert {n[7:]:h for n,h in files.items() if n.startswith('engine/')}==parent['files']
    (PACKAGE/'FLOW_MANIFEST.json').write_text(json.dumps({'version':'gold-oneclick-production-20261104-r2','files':files},indent=2)+'\n')
    with zipfile.ZipFile(HERE/NAME,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*files,'FLOW_MANIFEST.json']):
            item=zipfile.ZipInfo(name,(2026,11,4,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            z.writestr(item,(PACKAGE/name).read_bytes())
    sha=hashlib.sha256((HERE/NAME).read_bytes()).hexdigest()
    bootstrap=(HERE/'bootstrap_template.py').read_text().replace('DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip',NAME).replace('@@ZIP_SHA@@',sha).replace('gold-zip-flow-code-','gold-oneclick-prod-code-')
    bootstrap+='''
# Restart the kernel once if a previous Flow/sample loader was imported.
for _name in ("prod_run","prod_config","prod_pipeline","prod_guard","prod_storage","prod_state","prod_panel",
              "run_full","gold_io","fast_loader","fast_insert","vector_stage","jdbc_transport","mesh_embedding"):
    _loaded=sys.modules.get(_name)
    if _loaded is not None and FLOW_PACKAGE.resolve() not in Path(getattr(_loaded,"__file__","")).resolve().parents:
        raise RuntimeError("RESTART_KERNEL_OTHER_LOADER:"+_name)
'''
    code=(HERE/'params_template.py').read_text()+'\n'+bootstrap+'\nfrom prod_run import run\nRESULT = run(PARAMS)\n'
    compile(code,'production-delivered','exec')
    for name in ('DATAIKU_GOLD_PROD_RUN_R2.txt','DATAIKU_GOLD_PROD_RUN_R2.py'):(HERE/name).write_text(code)
    print(json.dumps({'zip':NAME,'bytes':(HERE/NAME).stat().st_size,'sha256':sha,'members':len(files)+1}))


if __name__=='__main__':main()
