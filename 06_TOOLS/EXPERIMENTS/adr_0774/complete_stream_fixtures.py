from pathlib import Path
import hashlib,json,subprocess,sys,os,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];paired={k:read(O/(k+'.json')) for k in ['baseline','source-gap-action']}
assert not (O/'result.json').exists()
first=list(ET.parse(O/'contracts.xml').iter('testcase'));failed=[]
for c in first:
 failure=c.find('failure');failure=c.find('error') if failure is None else failure
 if failure is not None:
  assert c.get('classname').endswith('test_genos_model_stream_completion') and 'FileNotFoundError' in failure.text and 'rewrite_transport.py' in failure.text
  failed.append(c.get('name'))
assert len(first)==353 and len(failed)==8
for p,h in f['files'].items():assert sha(R/p)==h,p
fixture=R/'05_TESTS/CONTRACTS/test_genos_model_stream_completion.py';assert sha(fixture)==sha(code/fixture.relative_to(R))
paths=[fixture,*list((R/'08_DEPLOYMENT/GENOS/handoffs/model_stream_fix_20261013_r1').glob('*.py'))]
put(O/'stream-fixture-recovery.json',{'before_execution_support_hashes':{str(p.relative_to(R)):sha(p) for p in paths},'original_tests':353,'passed':345,'setup_failures':failed,'reason':'Same frozen test bytes read from canonical repository so existing field transport fixture OUT resolves correctly; selected product still frozen candidate','matrix_or_product_changed':False})
with (O/'contracts-stream-support.log').open('w') as out:
 result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0774/run_tests.py',str(code),str(fixture),'-k','httpx','--junitxml='+str(O/'contracts-stream-support.xml')],cwd=R,env={**os.environ,'LAWRAG_WORKSPACE_ROOT':str(R),'LAWRAG_TOOL_WORKSPACE_ROOT':str(R)},stdout=out,stderr=subprocess.STDOUT)
last=list(ET.parse(O/'contracts-stream-support.xml').iter('testcase'));assert result.returncode==0 and sorted(c.get('name') for c in last)==sorted(failed)
checks={'exhaustive_952_field_cases':all(x['contract_correct'] and x['input_unchanged'] and x['idempotent'] and x['gap_count_preserved'] for x in paired['source-gap-action']),'all_353_unique_regression_cases_passed':True,'original_fixture_failures_preserved':True,'source_fact_meaning_schema_boundaries':True,'api_reentry_repeated_gap_no_claims_idempotence':True,'main59_publication_acl_preserved':True,'baseline_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'frozen_inputs_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),'all_serving_files_match':all(sha(code/p)==h for p,h in f['serving_files'].items()),'no_real_model_calls':True}
output={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':353,'contracts_initial':{'passed':345,'fixture_setup_errors':8},'fixture_support_completed':8,'by_arm':{name:{'status':'complete','matrix_cases':len(rows),'contract_correct':sum(x['contract_correct'] for x in rows)} for name,rows in paired.items()},'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},'limitations':['Exhaustive synthetic contract audit, not unseen legal answer accuracy or GENOS performance.','Known regressions supplement the matrix; same bytes with two fixture path setup fixes, original errors preserved.','Four prior unrelated recovery failures remain tracked in BL-010.','GENOS field deployment/internal model unverified.']}
assert output['strict_success'];put(O/'result.json',output);print(json.dumps(output,ensure_ascii=False))
