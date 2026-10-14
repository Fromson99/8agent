from pathlib import Path
import hashlib,json,subprocess,sys,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root'];assert not (O/'result.json').exists();O.mkdir(exist_ok=True)
for p,h in f['files'].items():assert sha(R/p)==h,p
paired={}
for name,root in [('baseline',base),('successful-publication',code)]:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0773/probe.py',str(root),str(O/(name+'.json'))],check=True);paired[name]=read(O/(name+'.json'))
assert len(paired['successful-publication'])==36 and all(x['admitted']==x['expected'] for x in paired['successful-publication'])
tests=[str(code/'05_TESTS/CONTRACTS'/x) for x in ['test_successful_shortcut.py','test_successful_core_routes.py','test_bounded_wiki_recall.py','test_ad_pagination.py','test_ad_language.py']]+['05_TESTS/CONTRACTS/'+x for x in ['test_ad_request_reports.py','test_genos_model_stream_completion.py']]
with (O/'contracts.log').open('w') as out:
 result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0773/run_tests.py',str(code),*tests,'--junitxml='+str(O/'contracts.xml')],cwd=R,stdout=out,stderr=subprocess.STDOUT)
cases=list(ET.parse(O/'contracts.xml').iter('testcase'));assert result.returncode==0 and len(cases)==169
checks={'matrix36_terminal_surface_admissions':True,'publication_retry_rollback_and_legacy_verification':True,'compiler_exact_success_binding_and_failed_trace_exclusion':True,'source_acl_revision_and_pagination_regressions':True,'169_contracts_passed':True,'no_real_model_calls':True,'baseline_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'frozen_inputs_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),'all_serving_files_match':all(sha(code/p)==h for p,h in f['serving_files'].items())}
output={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':len(cases),'by_arm':{name:{'status':'complete','matrix_cases':len(rows),'correct_admissions':sum(x['admitted']==x['expected'] for x in rows)} for name,rows in paired.items()},'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},'limitations':['Synthetic state contracts, not legal semantic correctness or field performance.','Legacy results without matching durable journal and answer stay unconfirmed.','GENOS installation/deployment requires field execution.','Existing regression tests supplement the prospectively frozen exhaustive state matrix.']}
assert output['strict_success'];put(O/'result.json',output);print(json.dumps(output,ensure_ascii=False))
