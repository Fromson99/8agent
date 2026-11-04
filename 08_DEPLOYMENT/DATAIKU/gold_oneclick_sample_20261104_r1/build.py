"""Pack a single notebook/ Python launcher and the existing loader + two data parts."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
NAME='DATAIKU_GOLD_ONECLICK_SAMPLE_20261104_R1.zip'


def main():
    files={p.relative_to(PACKAGE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(PACKAGE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
           and p.suffix!='.pyc' and p.name!='FLOW_MANIFEST.json'}
    assert sum('.part' in n for n in files)==2
    assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in files)
    (PACKAGE/'FLOW_MANIFEST.json').write_text(json.dumps({'version':'gold-oneclick-sample-20261104-r1','files':files},indent=2)+'\n')
    with zipfile.ZipFile(HERE/NAME,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*files,'FLOW_MANIFEST.json']):
            item=zipfile.ZipInfo(name,(2026,11,4,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            z.writestr(item,(PACKAGE/name).read_bytes())
    sha=hashlib.sha256((HERE/NAME).read_bytes()).hexdigest()
    bootstrap=(HERE/'bootstrap_template.py').read_text().replace('DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip',NAME).replace('@@ZIP_SHA@@',sha).replace('gold-zip-flow-code-','gold-oneclick-code-')
    bootstrap+='''
# A prior failed Flow installer is harmless: this launcher uses separate module names.
# If another loader already ran in this kernel, keep its state separate.
for _name in ("oneclick","oneclick_config","oneclick_pipeline","oneclick_db","oneclick_guard",
              "oneclick_storage","oneclick_state","oneclick_panel","run_full","gold_io",
              "fast_loader","fast_insert","vector_stage","jdbc_transport","mesh_embedding"):
    _loaded=sys.modules.get(_name)
    if _loaded is not None and FLOW_PACKAGE.resolve() not in Path(getattr(_loaded,"__file__","")).resolve().parents:
        raise RuntimeError("RESTART_KERNEL_OTHER_LOADER:"+_name)
'''
    code=(HERE/'params_template.py').read_text()+'\n'+bootstrap+'\nfrom oneclick import run\nRESULT = run(PARAMS)\n'
    compile(code,'oneclick-delivered','exec')
    for name in ('DATAIKU_GOLD_ONECLICK_RUN_R1.txt','DATAIKU_GOLD_ONECLICK_RUN_R1.py'):(HERE/name).write_text(code)
    print(json.dumps({'zip':NAME,'bytes':(HERE/NAME).stat().st_size,'sha256':sha,'members':len(files)+1}))


if __name__=='__main__':main()
