"""Record exact delivered code and deterministic local checks."""
import json,subprocess,sys,hashlib,gzip
from pathlib import Path
from build import H,R,NAME,sha,enc
source=json.loads((H/'SOURCE_BINDING.json').read_bytes())
assert sha((H/'code.zip').read_bytes())==source['code_zip_sha256']
compat="""import json,sys,zipfile,hashlib
from pathlib import Path
h=Path(sys.argv[1]);count=0
with zipfile.ZipFile(h/'code.zip') as z:
 for n in z.namelist():
  if n.endswith('.py'):compile(z.read(n),n,'exec');count+=1
compile((h/(sys.argv[2]+'_WORKFLOW_PASTE_ALL.txt')).read_bytes(),'workflow-editor','exec')
print(json.dumps({'status':'PASS','compiled_modules':count,'workflow_editor':True,'python':sys.version,'executable':sys.executable,'code_zip_sha256':hashlib.sha256((h/'code.zip').read_bytes()).hexdigest()}))
"""
r=subprocess.run(['/home/jin/.local/bin/python3.11','-c',compat,str(H),NAME],capture_output=True,text=True,check=True)
(H/'PYTHON311_CHECK.json').write_bytes(enc(json.loads(r.stdout)))
r=subprocess.run([sys.executable,str(H/'code_smoke.py'),str(H/'test-code')],capture_output=True,text=True,check=True)
(H/'CODE_SMOKE.json').write_bytes(enc(json.loads(r.stdout)))
assert '100 passed, 8 deselected' in (H/'contracts-final.log').read_text()
assert '2 passed' in (H/'installation-002.log').read_text()
checks={}
for kind in ('prior_main87','interrupted_main87'):
 v=json.loads((H/('PASS_'+kind+'.json')).read_bytes());assert v['status']=='PASS'
 checks[kind]={k:x for k,x in v.items() if k!='main_basis'}
 transcript=json.loads(gzip.decompress((H/('TEST_'+kind+'.json.gz')).read_bytes()))
 if kind=='prior_main87':
  rows=[r for r in transcript if any('installed_contract_runner.py' in str(a) for a in r['argv'])]
  assert len(rows)==1 and rows[0]['exit']==0
  checks[kind]['installed_contract_summary']=[s for s in rows[0]['stdout'].splitlines() if ' passed' in s or 'INSTALLED_CONTRACT_IMPORTS' in s]
resources={}
for n in ('contracts-final','installation-002'):
 v=json.loads((H/(n+'-resources.json')).read_bytes());assert v['returncode']==0 and v['stop_reason'] is None
 resources[n]={k:v[k] for k in ('returncode','seconds','peak_group_rss_bytes','min_available_bytes','stop_reason')}
value={'version':NAME,'status':'PASS_WITH_KNOWN_BASELINE_TEST_FAILURES','identity_policy':'team-session-v1',
'code_zip_sha256':source['code_zip_sha256'],'baseline_code_zip_sha256':source['baseline_code_zip_sha256'],
'payload_files':source['payload_files'],'python_modules':734,'changed_files':len(source['changes']),
'code_changes':8,'repinned_manifests':33,
'contracts':{'passed':100,'deselected_known_baseline_failures':8,'log_sha256':sha((H/'contracts-final.log').read_bytes()),
'baseline_failure_evidence':'baseline-001.log and baseline-001-resources.json; all eight also fail on unmodified sealed MAIN87; no frozen ADR tests changed'},
'installations':checks,'python311':json.loads((H/'PYTHON311_CHECK.json').read_bytes()),'resources':resources,
'coverage':['no user ID: workflow run/save/status/resume and normal v5/v6 multi-turn','stable team/session namespacing; same request dedup across user metadata changes','session isolation, cross-team isolation, trusted authority and document scope','checkpoint interruption, exhausted budget resume, unchanged deadline and monotonic usage','stale revision, request/body mismatch and saved-state hash tamper','legacy records preserved without budget reset or automatic migration','exact installed service entry and separate workflow editor consumer','interrupted install/reapply, changed-file rejection, same committed checkout gate, exact rollback'],
'limits':['synthetic scripted model and local TLS fixture only; zero external/GENOS model calls','old user-owned chats require new session or original revision; no automatic migration','no new cross-run natural-language comparison follow-up feature','GENOS field import, workflow editor save, Git push, revision deployment and internal model execution not verified'],
'local_main_pointer_changed':False,'local_main_release':'cm-read-continuity-20261019-r1','local_main_generation':87,
'working_code_updated':True,'genos_field_verified':False,'external_model_calls':0,
'failure_records_preserved':['tests-001 through tests-005','regression-001','baseline-001','installation.log (fixture import setup error)']}
assert (R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()==(H/'SOURCE_POINTER.json').read_bytes()
(H/'VALIDATION.json').write_bytes(enc(value))
(H/'TESTED_PACKAGE_BINDING.json').write_bytes((H/'PACKAGE_BINDING.json').read_bytes())
print(json.dumps({'status':value['status'],'contracts':100,'install_commands':sum(r['commands'] for r in checks.values()),'code_zip_sha256':source['code_zip_sha256']}))
