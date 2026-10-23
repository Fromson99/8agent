from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1034-read-judgment-live-question'
pm=read(parent/'실험/manifest.json');pf=read(parent/'artifacts/design-freeze.json');ps=read(parent/'artifacts/stage.json')
assert pm['results']['status']=='complete' and pm['reservation']['status']=='completed'
files=pf['files']['candidate'];assert all(sha(ROOT/n)==h for n,h in files.items())
m=read(ADR/'실험/manifest.json');d=m['design']
d.update(hypothesis='Operation-specific KEEP/WITHDRAW delta output with host-retained findings removes the observed normal-read blocker; a durable correction budget keyed to the request and actual original/judgment revisions prevents reset across presentation/menu/ASSESS reentry changes.',
 primary_metric='Deterministic exact-failure recovery and retained retry limits; actual97 source acquisition, judgment continuity/final review, calls/tokens/latency.',
 success_criteria='Contract tests accept KEEP delta and exact unchanged legacy repetition without extra model call, reject changed findings/unknown IDs/bad source or stale state, retain needs/conflicts/history and final review. Same-original/same-judgment read-choice failures permit at most2 model proposals total across changed presentation/schema and restart; unknown reservation is not replayed; new original or explicit judgment revision is distinct. Actual unchanged known question reads97 without KEEP rejection, returns answer/explicit limited answer, retains all prior judgments and needs, and executes no duplicate equivalent directory or unsupported coordinate. Zero hash/ACL violations;14 physical calls/1800s.163 reach and semantic choices are observed, not forced or legal gold.',
 failure_criteria='Required contract/API failure, unsafe normalization or silent state loss, retry reset with unchanged original/judgment state, KEEP contract blocking97 acquisition, no97 acquisition, unaccounted final judgment/need or source/hash/ACL failure. Provider429/transport ends once with no rerun; a blocked provider run does not establish model quality. Unexercised semantic conflicts remain unverified live.',
 criteria_frozen_before_run=True,
 sampling='One exposed known-query candidate live run, exact same65 public documents/request/data/model/budgets as1034. Parent failure outputs are regression fixtures only, not product prompts. No fresh baseline model call, no gold or target injected, no judge. Historical1034 is unpaired context.',
 retrieval_stage_plan=deepcopy(pm['design']['retrieval_stage_plan']),
 budgets={'per_arm_calls':14,'total_calls':14,'wall_seconds':1800,'rss_limit_gib':6,'minimum_available_gib':4},
 failure_recovery={'classification':'JSON/schema, operation conflict, original/hash/ACL/revision failures; provider terminal errors distinct.',
 'owner':'Existing bounded_decision remains the only correction owner. Optional durable cross-presentation correction scope shares that owner; gateway schema repair remains0.',
 'normalization':'KEEP/WITHDRAW restore existing finding/use/issue fields only from the exact bound prior head. Exact duplicate finding allowed with audit; changed finding, nonempty new needs/conflicts, changed use/issue refs rejected. Entire canonical review/action/source proof revalidated before commit.',
 'limits':'At most initial+one correction for the same request, original material and judgment revision, independent of presentation/tool-menu/schema aliases/ASSESS text.14calls/1800s; provider/transport retry0. RSS6GiB/available4GiB.',
 'state':'Existing append-only journal holds shared budget reservation/rejection/acceptance and exact raw response; persisted counts/unknown reservations survive restart. Judgment original history, needs/conflicts and final receipts preserved.',
 'terminal':'Existing bounded stop/limited verified-source answer or pending failure. No fabricated source/need closure; no semantic uncertainty stop added.',
 'checks':'Exact1034 failed proposals, delta/legacy/changed KEEP, withdrawal/history, omitted needs, ACL/hash/stale, initial+repair success/failure, altered presentation/schema and process restart, unknown reservation, distinct new material, unchanged common consumers, actual API and live service.'},
 working_integration='Only verified deterministic fixes selectively copied back to existing working code after candidate checks and live observation. Semantic answer failures recorded separately; integrity failures prevent integration. No MAIN102/GENOS cutover.',
 historical_comparison={'parent':'ADR-1034-experiment-v1/candidate','calls':9,'input_tokens':285765,'seconds':309.847,'paired':False,'parent_record_limitation':'Original final validator has known-query/public-capital-gains label mismatch; raw calls/source audit and separate corrected ledger retained. New experiment uses known-query consistently.'})
d['arms'][0].update(changes='Completed parent1034 exact511 working files; no fresh baseline calls.',controls='Historical failed run and unchanged source/model conditions; not a paired comparison.')
d['arms'][1].update(changes='KEEP/WITHDRAW delta schema and audited prior-state reconstruction; retained read-choice correction scope across reentry.',controls='Same source selection policy, model, public question, data,14calls/1800s; no automatic connection traversal.')
m['lineage']['hypothesis_delta']=d['hypothesis'];m['llm_policy']=deepcopy(pm['llm_policy'])
m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
m['runs'][0].update(arm_ids=['candidate'],selection_rule=d['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',d)
cd=ac.snapshot(ADR,'candidate',sorted(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);c=cd/'snapshot'
shutil.copyfile(parent/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str(c.relative_to(ROOT))},'root':str(c.relative_to(ROOT)),
 'candidate_dirs':{'candidate':str(cd.relative_to(ROOT))},'candidate_dir':str(cd.relative_to(ROOT)),
 'working_before':files,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],
 'parent':str(parent.relative_to(ROOT)),'same_parent_files':len(files)})
save(ART/'graph-before.json',{'validation_errors':read(ROOT/'04_EXPERIMENTS/ADR/EXPERIMENT_GRAPH.json')['validation_errors']})
print('Prepared',len(files),'parent/working files in isolated candidate')
