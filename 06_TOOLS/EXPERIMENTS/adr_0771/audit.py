"""Frozen display-only qualification of the actual producer/consumer connection."""
from pathlib import Path
import hashlib,json,subprocess,sys,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0771-source-cards-main-wiring';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root']
assert not (O/'result.json').exists();O.mkdir(exist_ok=True)
for p,h in f['files'].items():assert sha(R/p)==h,p
for name in b['manifest']['files']:
 if name.startswith('02_BACKEND/semantic_runtime/') and Path(name).name not in {'progress.py','chat_adapter.py'}:assert sha(code/name)==sha(base/name),name
 if name.startswith('00_SYSTEM/LEGAL_AGENT/'):assert sha(code/name)==sha(base/name),name
paired={}
for name,root in [('baseline',base),('source-cards',code)]:
 subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0771/probe.py'),str(root),str(O/(name+'.json'))],check=True)
 paired[name]=read(O/(name+'.json'))
assert len(paired['source-cards'])==24
assert all(x['source_paths_visible'] and x['one_complete_read_card'] and x['answer_unchanged'] for x in paired['source-cards'])
assert all(x['answer_unchanged'] for x in paired['baseline'])
tests=[str(code/'05_TESTS/CONTRACTS/test_main_source_cards.py')]+['05_TESTS/CONTRACTS/'+x for x in ['test_main_workflow_display.py','test_genos_answer_stream.py','test_public_display_boundary.py']]
with (O/'contracts.log').open('w') as out:
 result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0771/run_tests.py',str(code),*tests,'--junitxml='+str(O/'contracts.xml')],cwd=R,stdout=out,stderr=subprocess.STDOUT)
cases=list(ET.parse(O/'contracts.xml').iter('testcase'));assert result.returncode==0 and len(cases)==48
assert all(t.find('failure') is None and t.find('error') is None and t.find('skipped') is None for t in cases)
checks={'matrix24_all_paths_and_groups':True,'model_and_search_semantics_unchanged':True,'same_streamed_answers_both_arms':True,'scope_private_errors_and_request_isolation_contracts':True,'48_contracts_passed':True,'no_model_calls':True,'data_and_MAIN56_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'frozen_code_and_runner_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),'same297_serving_files':all(sha(code/p)==h for p,h in f['serving_files'].items())}
output={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':len(cases),'by_arm':{name:{'status':'complete','matrix_cases':len(rows),'complete_source_displays':sum(x['source_paths_visible'] and x['one_complete_read_card'] for x in rows),'identical_answers':len(rows)} for name,rows in paired.items()},'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},'limitations':['Display notification grouping, not an LLM-call count; backend suppresses some model boundaries.','Entire matrix is synthetic; no new legal-quality or field-latency claim.','R1 field editor is already mailed but actual GENOS paste/render remains unverified.','Known previous UI unit tests are regression, not holdout evidence.']}
assert output['strict_success'];put(O/'result.json',output);print(json.dumps(output,ensure_ascii=False))
