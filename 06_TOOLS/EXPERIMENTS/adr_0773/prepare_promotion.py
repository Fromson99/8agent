from pathlib import Path
import hashlib,json,sys,xml.etree.ElementTree as ET,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:');f=read(D/'freeze.json')
for row in read(A/'artifacts/working-install-receipt.json')['files']:assert sha(R/row['path'])==row['after'],row['path']
cases=list(ET.parse(A/'artifacts/working-required.xml').iter('testcase'));assert len(cases)==169 and all(t.find('failure') is None and t.find('error') is None for t in cases)
q={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'successful-publication','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
a={'authorized_by':'user','authorization_text':'코드 수정해서 메인에 반영하고 그리고 삼성메일로 쏴줘','quality_gate_override':False,'qualification':q,'rollback_pipeline':bound(A/'artifacts/working-backup/00_SYSTEM/PIPELINE.json')}
v={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_required_tests':bound(A/'artifacts/working-required.xml'),'limitations':read(A/'artifacts/run-001/result.json')['limitations'],'working_concurrent_preserved':read(A/'artifacts/working-install-receipt.json')['preserved_concurrent']}
sys.path.insert(0,str(R/f['code_root']/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,a,v);put(A/'artifacts/main-authorization.json',a);put(A/'artifacts/main-validation.json',v)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(R/f['code_root']),'--generation',read(D/'baseline.json')['manifest']['data_path'],'--release-id','successful-shortcut-20261013-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as out:subprocess.run(cmd,check=True,stdout=out,stderr=subprocess.STDOUT)
