from pathlib import Path
import json,hashlib,subprocess,sys,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0892-verified-assessment-wire';D=A/'artifacts/design';mode=sys.argv[1];assert mode in ('candidate','working')
p=json.loads((D/'execution-plan.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in p['test_hashes'].items())
args=[str(R/'.venv/bin/python'),str(Path(__file__).with_name('run_tests.py')),'-q','--import-mode=importlib','--tb=short',*p['tests']]
if True:args+=['-k','not test_compact_assessment_without_navigation_publishes_through_api and not test_native_search_candidates_survive_focus_window and not (test_excluded_original_not_revived and DEFERRED) and not test_explicit_disposition_preserved and not test_recorded_navigation_boundary and not test_bounded_reviews_and_reserve and not test_decline_and_limit and not test_no_finish_without_original and not test_gateway_workflow_calls_internal_interpreter_without_legal_bootstrap and not test_selected_local_release_receives_settings_without_rewriting_frozen_files']
env=dict(os.environ)
if mode=='working':env['TASK_TEST_CODE_ROOT']=str(R)
with (A/('artifacts/'+mode+'-api.log')).open('x') as log:subprocess.run(args,env=env,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
