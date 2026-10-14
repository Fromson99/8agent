from pathlib import Path
import json,subprocess,hashlib,xml.etree.ElementTree as E,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0744-focused-rules-final-qualification';D=A/'artifacts/design'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text());f=read(D/'freeze.json')
for p,h in f['serving_files'].items():assert sha(R/p)==h,p
code=R/f['code_root'];names=[str(R/p.relative_to(code)) for p in (code/'05_TESTS/CONTRACTS').glob('test_*.py')]
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py',str(R),*names,str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_entry.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_title_search.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0712/test_compact_input.py'),'--junitxml='+str(A/'artifacts/working-all.xml')]
with (A/'artifacts/working-all.log').open('w') as out:r=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':str(R/'05_TESTS/CONTRACTS')+':'+str(R/'05_TESTS/REGRESSION/core')})
tests=list(E.parse(A/'artifacts/working-all.xml').iter('testcase'));failed=sorted(t.get('name') for t in tests if t.find('failure') is not None or t.find('error') is not None)
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0743-direct-request-provenance/artifacts/run-001/result.json')
assert failed==parent['baseline_all']['failed'],failed
assert len(tests)==parent['candidate_all']['tests']
v={'status':'no-new-regressions','tests':len(tests),'passed':len(tests)-len(failed),'inherited_failures':failed,'new_failures':[],
 'comparison_source':'Selected MAIN52 baseline330 plus45 focused contracts','new104_pass':True,'serving_files_match':len(f['serving_files'])}
(A/'artifacts/working-verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');print(v)
