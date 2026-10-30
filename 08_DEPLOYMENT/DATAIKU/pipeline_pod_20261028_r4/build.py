"""Reproducible R4 from sealed R3 plus pinned GENOS source; no ambient RAG files."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=HERE.parent/'pipeline_preprocessor_20261027_r3'
SERVICE='GENOS_DATAIKU_COMPUTE_20261028_R4'
PACKAGE='DATAIKU_COMPUTE_RECIPES_20261028_R4.zip'
OLD_CODE='8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1'
UPSTREAM='aa610c3db24aaa02c65e953279f1a60d014babaf'
UPROOT=Path('/tmp/agent8-pod-parser-upstream-20261028')
spec=importlib.util.spec_from_file_location('r3builder',BASE/'build.py')
prev=importlib.util.module_from_spec(spec);spec.loader.exec_module(prev)
sha,edit,writezip=prev.sha,prev.edit,prev.writezip


def build():
    with zipfile.ZipFile(BASE/'GENOS_DATAIKU_COMPUTE_20261027_R3.zip') as z:
        original={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json'])==OLD_CODE
    pins=json.loads(original['CODE_PINS.json'])
    assert all(sha(original[n])==h for n,h in pins['files'].items())
    payload=dict(original)
    changed=['02_BACKEND/lawrag/core/genos_preprocessor.py','02_BACKEND/lawrag/core/genos_pod.py','02_BACKEND/lawrag/pipeline/raw_preprocess.py']
    for n in changed:payload[n]=(ROOT/n).read_bytes()
    paths=subprocess.check_output(['git','-C',str(UPROOT),'ls-tree','-r','--name-only',UPSTREAM],text=True).splitlines()
    selected=[n for n in paths if n.startswith('genon/') and Path(n).suffix in {'.py','.yaml','.yml','.json','.md','.txt'}
              and not any(p in {'tests','sample_files','examples','evaluation','gitbook_doc','docs'} for p in Path(n).parts)]
    # Site-owned YAML is mandatory. Do not distribute upstream sample credentials.
    selected=[n for n in selected if n!='genon/preprocessor/resource/parser_processor_config.yaml']
    vendor={n:subprocess.check_output(['git','-C',str(UPROOT),'show',UPSTREAM+':'+n]) for n in selected}
    for n,b in vendor.items():payload['pod_vendor/'+n]=b
    payload['POD_VENDOR_SOURCE.json']=(json.dumps({'repository':'https://github.com/genonai/doc_parser_code_serving','revision':UPSTREAM,
        'files':{n:sha(b) for n,b in vendor.items()}},indent=2,sort_keys=True)+'\n').encode()
    for n,source in [('pod_parser.py','preprocessor.py'),('prepare_pod_config.py','prepare_config.py')]:
        payload[n]=(ROOT/'08_DEPLOYMENT/GENOS/preprocessor'/source).read_bytes()
    payload['parser_config.py']=(HERE/'parser_config.py').read_bytes()
    worker=original['worker.py'].decode()
    worker=edit(worker,"'--pdf-conversion', 'off'","'--pdf-conversion', 'on'")
    worker=edit(worker,"    env.setdefault('GENOS_PDF_PARSER', 'preprocessor')", "    env['GENOS_PREPROCESSOR_TRANSPORT'] = 'pod'\n    env['GENOS_PDF_PARSER'] = 'preprocessor'")
    worker=edit(worker,"env.setdefault('GENOS_PREPROCESSOR_RESPONSE_MODE', 'auto')","env['GENOS_PREPROCESSOR_RESPONSE_MODE'] = 'docling'")
    worker=worker.replace('PREPROCESSOR_CONFIG_OK: remote connectivity not yet checked','POD_RUNTIME_CONFIG_OK: document/model execution not yet checked')
    payload['worker.py']=worker.encode()
    audit=original['review_audit.py'].decode()
    audit=edit(audit,"    return paths, {'reserved_model_calls':", "    paths.update(derivatives(workspace))\n    return paths, {'reserved_model_calls':")
    audit+='''

def derivatives(workspace):
    """Return original-to-PDF mapping and exact derived bytes to Dataiku."""
    data=Path(workspace)/'01_DATA'
    catalog=data/'CATALOG/RAW_DERIVATIVES.json'
    if not catalog.is_file():return {}
    paths={'audit/derivatives/RAW_DERIVATIVES.json':catalog}
    for name,item in t.read(catalog)['files'].items():
        if item.get('kind')!='native_rendered_pdf':continue
        path=t.checked(data,name)
        if t.sha(path)!=item['sha256']:raise ValueError('DERIVED_PDF_HASH_CHANGED')
        if t.sha(t.checked(data,item['origin']))!=item['origin_sha256']:raise ValueError('DERIVED_PDF_ORIGIN_CHANGED')
        paths['audit/derivatives/'+name]=path
    return paths
'''
    payload['review_audit.py']=audit.encode()
    # Optional offline runtime artifact is outside application CODE_PINS (not imported).
    wheel='packages/genon_docling-2.41.0+genon.0-py3-none-any.whl'
    runtime={wheel:subprocess.check_output(['git','-C',str(UPROOT),'show',UPSTREAM+':'+wheel]),
             'upstream-pyproject.toml':subprocess.check_output(['git','-C',str(UPROOT),'show',UPSTREAM+':genon/preprocessor/pyproject.toml'])}
    writezip(HERE/'GENOS_POD_RUNTIME_20261028_R4.zip',runtime)
    payload['CODE_PINS.json']=(json.dumps({**pins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}},indent=2,sort_keys=True)+'\n').encode()
    code_sha=sha(payload['CODE_PINS.json'])
    writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    for n in ('worker.py','review_audit.py'):(HERE/n).write_bytes(payload[n])
    with zipfile.ZipFile(BASE/'DATAIKU_COMPUTE_RECIPES_20261027_R3.zip') as z:client={n:z.read(n) for n in z.namelist()}
    client['COMPUTE_CODE_SHA256.txt']=(code_sha+'\n').encode()
    controller=client['controller.py'].decode().replace(r"PREPROCESSOR_[A-Z_]{1,60}",r"(?:PREPROCESSOR|POD)_[A-Z_]{1,60}")
    client['controller.py']=controller.encode()
    upgrade=client['checkpoint_upgrade.py'].decode()
    upgrade=edit(upgrade,"    phase = old.get('phase')", "    phase = old.get('phase')")
    upgrade=upgrade.replace("PREVIOUS_CODES = {PREVIOUS_CODE, ", "PREVIOUS_CODES = {'"+OLD_CODE+"', PREVIOUS_CODE, ")
    upgrade=edit(upgrade,"    # Check the snapshot again", "    proof = None\n    if previous_code == '"+OLD_CODE+"':\n        from upgrade_review import require_zero_review\n        proof = require_zero_review(store,old)\n    # Check the snapshot again")
    upgrade=edit(upgrade,"'reason': 'PDF_PREPROCESSOR_RESTORED'", "'zero_review_proof': proof, 'prior_audit_blob': old.get('audit_blob'), 'reason': 'SAME_POD_PARSER_AND_CONVERSION'")
    client['checkpoint_upgrade.py']=upgrade.encode()
    client['upgrade_review.py']=(HERE/'upgrade_review.py').read_bytes()
    updater=client['updater.py'].decode().replace('preprocessor-r3-before.json','pod-r4-before.json')
    client['updater.py']=updater.encode()
    ref=json.loads(client['REFERENCE.json']);ref['prior_compute_bootstraps'].append((BASE/'bootstrap.txt').read_text())
    client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in client.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    writezip(HERE/PACKAGE,client)
    oldboot=(BASE/'bootstrap.txt').read_text()
    boot=oldboot.replace('DATAIKU_COMPUTE_RECIPES_20261027_R3.zip',PACKAGE).replace(sha((BASE/'DATAIKU_COMPUTE_RECIPES_20261027_R3.zip').read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    import re
    boot=re.sub(r'PACKAGE_BYTES = \d+', 'PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),boot)
    (HERE/'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL','CONTROL'):
        s=(BASE/f'DATAIKU_PREPROCESSOR_{kind}_20261027_R3.txt').read_text()
        s=s.replace(oldboot,boot).replace(repr(oldboot),repr(boot)).replace('pipeline_preprocessor_r3_updater','pipeline_pod_r4_updater').replace('PREPROCESSOR_R3_FLOW_READY','POD_R4_FLOW_READY')
        (HERE/f'DATAIKU_POD_{kind}_20261028_R4.txt').write_text(s);ast.parse(s)
    for n,b in payload.items():
        if n.endswith('.py'):compile(b,n,'exec')
    result={'baseline_code_sha256':OLD_CODE,'code_sha256':code_sha,'upstream_revision':UPSTREAM,
            'service_changed':[n for n,b in payload.items() if b!=original.get(n)],
            'service_files':len(payload),'baseline_files_unchanged':sum(payload.get(n)==b for n,b in original.items()),
            'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in (SERVICE+'.zip',PACKAGE,'GENOS_POD_RUNTIME_20261028_R4.zip')}}
    (HERE/'BUILD.json').write_text(json.dumps(result,indent=2)+'\n')
    print('BUILT',len(payload),'files',code_sha)

if __name__=='__main__':build()
