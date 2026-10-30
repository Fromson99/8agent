import ast
import importlib.util
import json
from pathlib import Path
import re
import zipfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_pod_20261028_r4'
SERVICE='GENOS_DATAIKU_COMPUTE_20261028_R5'
PACKAGE='DATAIKU_COMPUTE_RECIPES_20261028_R5.zip'
OLD_CODE='8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685'
spec=importlib.util.spec_from_file_location('r4build',BASE/'build.py');r4=importlib.util.module_from_spec(spec);spec.loader.exec_module(r4)
sha,edit,writezip=r4.sha,r4.edit,r4.writezip


def main():
    with zipfile.ZipFile(BASE/'GENOS_DATAIKU_COMPUTE_20261028_R4.zip') as z:original={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json'])==OLD_CODE
    pins=json.loads(original['CODE_PINS.json']);assert all(sha(original[n])==h for n,h in pins['files'].items())
    payload=dict(original)
    service=original['service.py'].decode().replace('import review_audit','import review_audit\nimport sample_worker\nimport probe_runtime')
    service=edit(service,"    if op == 'HEALTH':", "    if op in {'HEALTH','PROBE_HEALTH'}:")
    service=edit(service,"'preprocessor':parser_config.inspect(ROOT)", "'probe_purpose':sample_worker.PURPOSE,\n                'preprocessor':probe_runtime.inspect(ROOT) if op=='PROBE_HEALTH' else parser_config.inspect(ROOT)")
    service=edit(service,"            parser = parser_config.require(ROOT)", "            purpose=data.get('purpose','pipeline')\n            if purpose not in {'pipeline',sample_worker.PURPOSE}:raise ValueError('COMPUTE_PURPOSE')\n            parser = (probe_runtime if purpose==sample_worker.PURPOSE else parser_config).require(ROOT)")
    service=edit(service,"if h['archives'] != archives or h['deadline']", "if h['purpose'] != purpose or h['archives'] != archives or h['deadline']")
    service=edit(service,"h = dict(id=ident, token=token, folder=folder, archives=archives, deadline=deadline,", "h = dict(id=ident, token=token, folder=folder, archives=archives, deadline=deadline, purpose=purpose,")
    service=edit(service,"                parser_config.require(ROOT, h['parser_config_sha256'])", "                (probe_runtime if h['purpose']==sample_worker.PURPOSE else parser_config).require(ROOT, h['parser_config_sha256'])")
    service=edit(service,"        with (folder/'compute.log').open('ab',buffering=0) as output:", "        if h['purpose']==sample_worker.PURPOSE:\n            command=[sys.executable,'-B',str(ROOT/'sample_worker.py'),str(folder),json.dumps(h['archives'],sort_keys=True),h['parser_config_sha256']]\n        with (folder/'compute.log').open('ab',buffering=0) as output:")
    service=edit(service,"h['child']=child;h['phase']='NATIVE_PIPELINE'", "h['child']=child;h['phase']='DOCUMENT_PROBE' if h['purpose']==sample_worker.PURPOSE else 'NATIVE_PIPELINE'")
    service=edit(service,"            review_audit.export(folder)", "            if h['purpose']==sample_worker.PURPOSE:sample_worker.export_partial(folder)\n            else:review_audit.export(folder)")
    payload['service.py']=service.encode()
    for n in ('sample_worker.py','probe_runtime.py'):payload[n]=(HERE/n).read_bytes()
    payload['CODE_PINS.json']=(json.dumps({**pins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}},sort_keys=True,indent=2)+'\n').encode()
    code=sha(payload['CODE_PINS.json']);writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    (HERE/'service.py').write_bytes(payload['service.py'])
    with zipfile.ZipFile(BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R4.zip') as z:client={n:z.read(n) for n in z.namelist()}
    for n in ('selection.py','probe_client.py'):client[n]=(HERE/n).read_bytes()
    client['COMPUTE_CODE_SHA256.txt']=(code+'\n').encode()
    upgrade=client['checkpoint_upgrade.py'].decode().replace('PREVIOUS_CODES = {',"PREVIOUS_CODES = {'"+OLD_CODE+"', ")
    upgrade=upgrade.replace("if previous_code == '8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1':", "if previous_code in {'8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1','"+OLD_CODE+"'}:")
    client['checkpoint_upgrade.py']=upgrade.encode()
    client['updater.py']=client['updater.py'].replace(b'pod-r4-before.json',b'document-probe-r5-before.json')
    ref=json.loads(client['REFERENCE.json']);ref['prior_compute_bootstraps'].append((BASE/'bootstrap.txt').read_text());client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in client.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    writezip(HERE/PACKAGE,client)
    oldboot=(BASE/'bootstrap.txt').read_text()
    boot=oldboot.replace('DATAIKU_COMPUTE_RECIPES_20261028_R4.zip',PACKAGE).replace(sha((BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R4.zip').read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    boot=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),boot);(HERE/'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL','CONTROL'):
        s=(BASE/f'DATAIKU_POD_{kind}_20261028_R4.txt').read_text().replace(oldboot,boot).replace(repr(oldboot),repr(boot)).replace('pipeline_pod_r4_updater','pipeline_probe_r5_updater').replace('POD_R4_FLOW_READY','PROBE_R5_FLOW_READY')
        s=s.replace('PROBE_R5_FLOW_READY: GENOS 환경변수/리비전 적용 뒤 00 → 02 → 03','PROBE_R5_FLOW_READY: 클라이언트 갱신 완료. 네 문서 확인은 DATAIKU_FOUR_FORMAT_TEST.txt 실행')
        (HERE/f'DATAIKU_R5_{kind}.txt').write_text(s);ast.parse(s)
    notebook="# LEGAL_RAG Python 노트북에서 전체 셀 실행. YAML/문서 경로 입력 없음.\nRUN_NAME = 'doc_formats_20261028_r1'\nACTION = 'run'  # run / status / cancel; 재실행은 같은 RUN_NAME 사용\n"+boot+'''\nwork,root=verified_package()
sys.path[:0]=[str(root),str(root/'client'),str(root/'client/02_BACKEND')]
cached=sys.modules.get('controller')
if cached is not None and getattr(cached,'EXPECTED',None)!=(root/'COMPUTE_CODE_SHA256.txt').read_text().strip():
    raise RuntimeError('NOTEBOOK_KERNEL_RESTART_REQUIRED: 이전 파이프라인 모듈이 로드되어 있습니다. 새 커널에서 실행하세요.')
import probe_client
result=probe_client.run(dataiku,work,RUN_NAME,ACTION)
'''
    (HERE/'DATAIKU_FOUR_FORMAT_TEST.txt').write_text(notebook);ast.parse(notebook)
    for n,b in payload.items():
        if n.endswith('.py'):compile(b,n,'exec')
    (HERE/'BUILD.json').write_text(json.dumps({'baseline_code_sha256':OLD_CODE,'code_sha256':code,'service_files':len(payload),
        'unchanged_baseline_files':sum(payload.get(n)==b for n,b in original.items()),'changed_files':[n for n,b in payload.items() if original.get(n)!=b],
        'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in (SERVICE+'.zip',PACKAGE)}},indent=2)+'\n')
    print('BUILT',code,len(payload))

if __name__=='__main__':main()
