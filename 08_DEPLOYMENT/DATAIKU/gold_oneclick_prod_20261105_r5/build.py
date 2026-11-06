"""Build the notebook pair from the R5 source and check its delta against the R4 ZIP."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
NAME='DATAIKU_GOLD_ONECLICK_PROD_20261105_R5.zip'


def main():
    previous = HERE.parent/'gold_oneclick_prod_20261105_r4/DATAIKU_GOLD_ONECLICK_PROD_20261105_R4.zip'
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == '6a9ec341321c6b2301498b7fb0b6c7d6e7fbae939f65a197413d050815106fab'
    with zipfile.ZipFile(previous) as archive:
        baseline = json.loads(archive.read('FLOW_MANIFEST.json'))['files']
    files={p.relative_to(PACKAGE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(PACKAGE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
           and p.suffix!='.pyc' and p.name!='FLOW_MANIFEST.json'}
    assert not any(n.startswith('sample/') or '.part0' in n for n in files)
    assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in files)
    assert files.keys() == baseline.keys()
    assert {name for name in files if files[name] != baseline[name]} == {
        'registration_current.json', 'prod_run.py'}
    (PACKAGE/'FLOW_MANIFEST.json').write_text(json.dumps({'version':'gold-oneclick-production-20261105-r5','files':files},indent=2)+'\n')
    with zipfile.ZipFile(HERE/NAME,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*files,'FLOW_MANIFEST.json']):
            item=zipfile.ZipInfo(name,(2026,11,5,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
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
    for name in ('DATAIKU_GOLD_PROD_RUN_R5.txt','DATAIKU_GOLD_PROD_RUN_R5.py'):(HERE/name).write_text(code)
    print(json.dumps({'zip':NAME,'bytes':(HERE/NAME).stat().st_size,'sha256':sha,'members':len(files)+1}))


if __name__=='__main__':main()
