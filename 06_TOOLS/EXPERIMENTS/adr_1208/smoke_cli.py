"""Exercise the delivered folder exactly as an operator would invoke it."""
from pathlib import Path
import json,subprocess,time,os,hashlib,math
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector/artifacts';OUT=A/'operator-cli';OUT.mkdir(exist_ok=True)
scope={d['document_id'] for d in json.loads((R/'08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/documents.json').read_text())['documents']}
sample=json.loads((A/'run-001/checks-result.json').read_text())['details']['reference_navigation_samples'][0]
commands=[('documents',['documents']),('source',['source','3521c3aaa5a735fd','0']),('search',['search','이사회']),('reference-targets',['reference-targets',sample['document_id'],sample['reference_id']]),('vector-search',['vector-search','상장주선인의 의무 인수와 보유 기간'])]
results=[]
for name,args in commands:
    start=time.monotonic();out=OUT/(name+'.json');err=OUT/(name+'.stderr.log')
    with out.open('w') as stdout,err.open('w') as stderr:
        result=subprocess.run([str(R/'.venv/bin/python'),str(R/'08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py'),*args],cwd=R,stdout=stdout,stderr=stderr,timeout=180,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'4','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4'})
    if result.returncode:raise RuntimeError('OPERATOR_CLI_FAILED:'+name)
    value=json.loads(out.read_text())
    if name=='documents':assert {x['document_id'] for x in value}==scope
    elif name=='source':assert value['text']=='제1편 총 칙'
    elif name=='search':assert len(value['result']['items'])==10 and sum(x['unit_count'] for x in value['result']['items'])==107
    elif name=='reference-targets':assert value['reference']['id']==sample['reference_id']
    elif name=='vector-search':assert len(value['result'])==20 and all(x['DOC_ID'] in scope and math.isfinite(x['DISTANCE']) for x in value['result'])
    results.append({'name':name,'seconds':time.monotonic()-start,'exit_code':0,'stdout_json_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'pass':True})
    (A/'run-001/operator-cli-checks.json').write_text(json.dumps({'status':'RUNNING','commands':results},ensure_ascii=False,indent=2)+'\n')
(A/'run-001/operator-cli-checks.json').write_text(json.dumps({'status':'PASS','commands':results},ensure_ascii=False,indent=2)+'\n')
print('OPERATOR CLI PASS',len(results))
