"""Freeze latest selected MAIN, four public questions, and offline criteria."""
from common import *
import sys
from datetime import datetime, timezone
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (DES/'freeze.json').exists()
pointer_path = ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
p = read(pointer_path); release = read(ROOT/p['manifest_path']); C = ROOT/release['code_root']
assert sha(ROOT/p['manifest_path']) == p['release_manifest_sha256']
assert all(sha(C/n) == h for n,h in release['files'].items())
ids = ['cm-051','cm-022','cm-008','cm-038']
registry = read(ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json')
raw = [next(c for c in registry['cases'] if c['id']==cid and c['collection']=='cm') for cid in ids]
cases = [{'id':c['id'],'question':c['question']} for c in raw]
put(DES/'cases.json',cases)
put(DES/'offline-reference.json',[{k:c.get(k) for k in ('id','question','reference_answer','as_of','targets')} for c in raw])
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(pointer_path),'release':release})
profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
put(DES/'authorization.json',{'user_request':'지금 가장최근메인에서 실험해봐','context':'The four previously successful public CM questions proposed immediately before this instruction: 051,022,008,038.',
    'case_ids':ids,'model':'qwen/qwen3.8-27b','provider':'OpenRouter Parasail FP8','scope':'Exact registered public CM questions and selected public document grant only. Offline reference answers and targets are never product input. Original export metadata unchanged.'})
criteria={'hypothesis':'The latest selected local MAIN can answer four previously successful public CM questions and preserve traceable original-law connections.',
 'success':['Attempt all four questions once, serially, with exact registered wording and native service selection','Separate completed response, core-answer correctness, exact original citations, and actual relationship traversal','Preserve every failed call, model proposal, partial outcome, usage and state; no adaptive whole-case reruns'],
 'failure':'Stop on code/data/ACL/hash/state integrity failure or resource floor. Ordinary provider/model failures remain case outcomes; never reset started-case budgets.',
 'core_criteria':{
  'cm-051':['Explain securities conversion under underwriting regulation6(2) -> capital markets enforcement rule14(1), including CB fraction exclusion','Explain partnership/fund indirect holding by investment ratio and relevant exclusions','Do not automatically import rule14(2) tender-offer denominator or14(3) options outside incorporated paragraph'],
  'cm-022':['State ordinary income/net-asset3:2 and real-estate-heavy2:3 weighting','State80percent net-asset floor','Separate basic method from optional valuation committee alternative'],
  'cm-008':['State innovative-tech issuer AND underwriter condition, not either alone','Connect KOSDAQ rule13(5)1na with implementation rule15(5)','Explain3year lookback,2year post-listing window and specified watch/management/delisting grounds without replacing them with any poor performance'],
  'cm-038':['Distinguish shareholder-meeting report from board/auditor report delegation','Connect external audit act8(4) with decree9(4)','Preserve representative report preparation and written prior reason when internal accounting manager reports']},
 'quality':'Offline agent review against frozen criteria and actual selected originals; no external judge. Whole-answer correctness is separate from core pass. Registered coordinate/version drift reported independently.',
 'graph':'Report actual read/cited documents and explicit selected navigation actions. Distinguish source graph adjacency from actions actually traversed; never invent a continuous chain from a citation list.',
 'limits':{'questions':4,'attempts_per_case':profile['max_model_attempts'],'wall_seconds_per_case':profile['wall_seconds'],'total_product_attempts':4*profile['max_model_attempts'],'concurrency':1,'rss_gib':7,'as_gib':9,'minimum_available_gib':3,'minimum_disk_gib':10},
 'runtime':'Actual service.service.application, no app injection, no session/memory IDs; immutable selected code/data/profile. Only send_once/ModelGateway audit wrapping preserves native values.',
 'selection':'Freeze latest ACTIVE before first dispatch. All four use that one immutable binding. Later independent MAIN promotion is recorded, not silently mixed into this run.',
 'resume':'Completed cases skipped. Started case without final result is interrupted and not replayed. Never-started cases may continue with original frozen code and remaining budget.',
 'model':'Qwen3.8, Parasail FP8, reasoning none, no fallback, ExperimentClient; native bounded gateway owns recovery.',
 'baseline':'Single observed arm. ADR0895 is historical context, not a paired simultaneous control. Known questions, in_sample=true, decision_eligible=false. No MAIN promotion.'}
put(DES/'criteria.json',criteria)
# Preserve the selected release itself, rather than snapshotting unrelated worktree edits.
paths=[str((C/n).relative_to(ROOT)) for n in release['files']]
candidate=ac.snapshot(ADR,'observed',paths,experiment_id='ADR-0979-experiment-v1',arm_id='observed',run_ids=['run-001'])
ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('live.py')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Core-answer pass /4, complete answers /4, exact original source checks and observed law-navigation paths',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,
 arms=[{'id':'observed','role':'candidate','derived_from':['ADR-0974-experiment-v1/candidate'],'changes':'None. Actual selected immutable MAIN, audit wrapping only. Snapshot records byte-identical selected files; no alternate candidate selected.','controls':'Selected code/data/model/profile/search and public document grant; no gold in product input.'}],
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'observed':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
m['design']['execution']=criteria
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'observed','arm_id':'observed','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
m['dataset'].update(name='Four previously successful public CM questions',version='registry-v2-risk_cm / cm / 20261022',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['runs'][0].update(arm_ids=['observed'],purpose='primary',selection_rule='User-requested previously recommended051,022,008,038 in that order; once each, no adaptive reruns.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Unchanged selected retrieval. Post-selection original-read/final-citation accounting only; no retrieval-effect claim.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
f={'frozen_at':datetime.now(timezone.utc).isoformat(),'pointer_sha256':sha(pointer_path),'release_manifest_sha256':p['release_manifest_sha256'],'code_root':release['code_root'],'serving_files':release['files'],
 'files':{str(x.relative_to(ROOT)):sha(x) for x in sorted(DES.glob('*.json'))},
 'scripts':{str(x.relative_to(ROOT)):sha(x) for x in [runner,Path(__file__).with_name('common.py'),Path(__file__),ROOT/'06_TOOLS/EXPERIMENTS/resource_guard.py']},
 'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py'),'candidate_manifest_sha256':sha(candidate/'candidate.json'),'product_model_calls':0}
put(DES/'freeze.json',f)
print('Frozen MAIN',p['generation'],p['release_id'],len(release['files']),'files,4questions, no model calls yet')
