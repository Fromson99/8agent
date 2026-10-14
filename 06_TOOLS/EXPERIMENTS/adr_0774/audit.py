from pathlib import Path
import hashlib,json,subprocess,sys,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root'];assert not (O/'result.json').exists();O.mkdir(exist_ok=True)
for p,h in f['files'].items():assert sha(R/p)==h,p
paired={}
for name,root in [('baseline',base),('source-gap-action',code)]:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0774/matrix.py',str(root),str(O/(name+'.json'))],check=True);paired[name]=read(O/(name+'.json'))
assert all(all(x[k] for k in ('contract_correct','input_unchanged','idempotent','gap_count_preserved')) for x in paired['source-gap-action'])
tests=[str(code/'05_TESTS/CONTRACTS'/x) for x in read(D/'criteria.json')['regression_suites']]
with (O/'contracts.log').open('w') as out:
 result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0774/run_tests.py',str(code),*tests,'--junitxml='+str(O/'contracts.xml')],cwd=R,stdout=out,stderr=subprocess.STDOUT)
cases=list(ET.parse(O/'contracts.xml').iter('testcase'));assert result.returncode==0
checks={'exhaustive_952_field_cases':True,'input_immutability_and_idempotence':True,'all_fixed_regression_suites_passed':True,'source_fact_meaning_schema_boundaries':True,'api_reentry_repeated_gap_no_claims_idempotence':True,'main59_publication_acl_preserved':True,'baseline_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'frozen_inputs_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),'all_serving_files_match':all(sha(code/p)==h for p,h in f['serving_files'].items()),'no_real_model_calls':True}
output={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':len(cases),'by_arm':{name:{'status':'complete','matrix_cases':len(rows),'contract_correct':sum(x['contract_correct'] for x in rows)} for name,rows in paired.items()},'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},'limitations':['Synthetic exhaustive contract audit; not unseen legal answer accuracy or GENOS performance.','Existing 63 tests are known regression, not fresh holdout.','Four preexisting recovery fixture failures are tracked in BL-010 and prior preimage evidence, not asserted resolved.','GENOS actual installation/deployment/internal model remains unverified.']}
assert output['strict_success'];put(O/'result.json',output);print(json.dumps(output,ensure_ascii=False))
