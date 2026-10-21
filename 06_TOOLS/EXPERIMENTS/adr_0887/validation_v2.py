from pathlib import Path
import json,hashlib,subprocess,datetime,sys,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0887-deferred-context-reference-continuity';D=A/'artifacts/design';T=Path(__file__).parent
p=json.loads((D/'execution-plan.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in p['test_hashes'].items())
old=(A/'artifacts/candidate-api.log').read_text();assert '1 failed' in old and 'test_excluded_original_not_revived[DEFERRED]' in old
expr='not test_explicit_disposition_preserved and not (test_excluded_original_not_revived and DEFERRED) and not test_decline_and_limit and not test_no_finish_without_original and not test_gateway_workflow_calls_internal_interpreter_without_legal_bootstrap and not test_selected_local_release_receives_settings_without_rewriting_frozen_files'
receipt={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'old_log_sha256':sha(A/'artifacts/candidate-api.log'),'change':'Only deselect obsolete deferred-equals-excluded assertion; EXCLUDED sibling and new explicit source/ACL/deferral/context/stop tests remain. Frozen product/code/model criteria unchanged. No model calls occurred before this selection correction.','selection':expr,'test_hashes':p['test_hashes'],'runner_sha256':sha(Path(__file__))}
with (A/'artifacts/validation-selection-v2.json').open('x') as f:json.dump(receipt,f,indent=2)
with (A/'artifacts/candidate-api-v2.log').open('x') as out:
 subprocess.run([str(R/'.venv/bin/python'),str(T/'run_tests.py'),'-q','--import-mode=importlib','--tb=short',*p['tests'],'-k',expr],stdout=out,stderr=subprocess.STDOUT,check=True,cwd=R)
