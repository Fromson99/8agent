from pathlib import Path
import json,subprocess,hashlib,xml.etree.ElementTree as E,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');contracts=read(A/'artifacts/contract-result.json')
for p,h in f['serving_files'].items():assert sha(R/p)==h,p
files=contracts['suite_files']+[str(R/'05_TESTS/CONTRACTS/test_bounded_wiki_recall.py')]
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py',str(R),*files,'--junitxml='+str(A/'artifacts/working-all.xml')]
with (A/'artifacts/working-all.log').open('w') as log:
 r=subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':str(R/'05_TESTS/CONTRACTS')+':'+str(R/'05_TESTS/REGRESSION/core')})
tests=list(E.parse(A/'artifacts/working-all.xml').iter('testcase'))
failed=sorted(t.get('classname','')+'::'+t.get('name','') for t in tests if t.find('failure') is not None or t.find('error') is not None)
assert failed==contracts['baseline_all']['failed'],failed
assert len(tests)==contracts['candidate_all']['tests']+contracts['new_contracts']['tests']
v={'status':'no-new-regressions','tests':len(tests),'passed':len(tests)-len(failed),'inherited_failures':failed,'new_failures':[],'new_contracts_pass':True,'serving_files_match':len(f['serving_files'])}
(A/'artifacts/working-verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print(v)
