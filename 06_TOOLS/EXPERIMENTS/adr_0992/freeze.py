"""Freeze implementation, shared sources, fixed cases and execution harness before calls."""
from common import *
import sys,ast,xml.etree.ElementTree as E
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot';B=ROOT/s['roots']['baseline']
assert not (ART/'design-freeze.json').exists()
tests=E.parse(ART/'contracts.xml').getroot()
failures=[c for c in tests.iter('testcase') if c.find('failure') is not None or c.find('error') is not None]
assert len(failures)==2 and all(c.get('name').startswith('test_native_api_uses_streaming_compose_and_preserves_publication') for c in failures)
fixed=E.parse(ART/'contracts-fixture-corrected.xml').getroot()
assert sum(int(n.get('tests','0')) for n in fixed.iter('testsuite'))==2
assert all(not int(n.get('failures','0')) and not int(n.get('errors','0')) for n in fixed.iter('testsuite'))
ac.freeze(D);assert not ac.validate(D)
cm=read(D/'candidate.json');rev=cm['revisions'][-1]
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0992/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))}])
m['dataset'].update(name='Known native request and five fixed synthetic adequacy decisions',version='compact-prompts-v1',frozen_source=str((ART/'cases.json').relative_to(ROOT)),sha256=sha(ART/'cases.json'),legal_version_checked=True,reference_version_checked=True,version_scope='Same immutable public native corpus; synthetic assessment sources separately marked; not legal answer certification')
m['runs'][0].update(arm_ids=['baseline','candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['design']['failure_recovery']['experiment_dispatch']='Provider/transport failure, process crash, or resource pressure stops later cases. Native bounded or semantic failure is preserved and fixed independent paired probes continue. No retry of any case.'
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1},{'role':'assessment-probe','class':'product','model':'qwen/qwen3.8-27b','repeats':10}]
reason='No retrieval implementation change or new recall comparison. Native actual source reads retained; fixed-evidence decisions isolate assessment behavior.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
save(ADR/'실험/manifest.json',m)
files={'baseline':s['baseline_files'],'candidate':{n:sha(C/n) for n in s['baseline_files']}}
files['candidate'].update({str(p.relative_to(C)):sha(p) for p in (C/'05_TESTS/CONTRACTS').glob('*.py')})
save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'request_sha256':sha(ART/'known-request.json'),'cases_sha256':sha(ART/'cases.json'),'grading_sha256':sha(ART/'grading-only.json'),'files':files,'working_files':s['working_files'],'runner_hashes':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py') if p.name!='finish.py'},'contract_sha256':sha(ART/'contracts.xml'),'fixture_correction_sha256':sha(ART/'contracts-fixture-corrected.xml')})
print('Frozen419productfiles+5fixtures; native8 + ten paired one-call probes; global18 maximum, no provider retry.')
