from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot'
assert not (ART/'trials').exists() and not (ART/'known-query').exists()
assert '40 passed' in (ART/'contracts-final-targeted.txt').read_text()
ac.freeze(D);assert not ac.validate(D)
cm=read(D/'candidate.json');rev=cm['revisions'][-1]
request=read(ROOT/'90_RUNTIME/manual_queries/special-resolution-20261022/retry/request.json');save(ART/'known-request.json',request)
files={a:{n:sha(ROOT/r/n) for n in s['base_release']['files']} for a,r in s['roots'].items()}
binding={'candidate_id':'candidate','arm_id':'candidate','experiment_id':'ADR-0988-experiment-v1','run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0988/run_case.py','runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_0988/run_case.py')}
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding])
m['design']['call_order']=[['known-special-resolution',a] for a in ('baseline','candidate')]+[[c['id'],a] for i,c in enumerate(read(ART/'cases.json')) for a in (('candidate','baseline') if i%2==0 else ('baseline','candidate'))]
m['dataset'].update(name='In-sample special-resolution and eight synthetic unmet-need decisions',version='expansion-probe-v1',frozen_source=str((ART/'cases.json').relative_to(ROOT)),sha256=sha(ART/'cases.json'),legal_version_checked=True,reference_version_checked=True)
m['dataset']['version_scope']='Same immutable public corpus and synthetic originals; not current legal advice or expert certification.'
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1},{'role':'assessment-and-tool-choice','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Known paired service first; eight synthetic decisions alternating order, no whole-request retry',artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Primary synthetic comparison measures judgment over identical fixed originals/candidate menus, not corpus retrieval; separate known service diagnostic records actual read/claim sets without claiming retrieval recall.',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':'Fixed source and tool-choice probe; no retrieval algorithm/candidate-set modification. Known query is separate in-sample service diagnostic.'})
save(ADR/'실험/manifest.json',m)
save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'cases_sha256':sha(ART/'cases.json'),'gold_sha256':sha(ART/'grading-only.json'),'request_sha256':sha(ART/'known-request.json'),'files':files,'runner_hashes':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')}})
print('Frozen exact MAIN100 and candidate, eight paired probes + known paired native service. No calls yet.')
