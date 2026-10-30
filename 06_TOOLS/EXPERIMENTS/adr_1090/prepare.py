from common import *
from datetime import datetime,timezone
import sys,shutil
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding/artifacts/design/freeze.json')
source=ROOT/old['code_root']
assert all(sha(source/n)==h for n,h in old['files'].items())
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/pointer['manifest_path'])
put(DES/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':base})
matrix={'pages':[[size,count] for size in (4,9,13) for count in range(84)],
 'journal':[[count,spans,reverse] for count in (4,6,12,24,82) for spans in (2,4) for reverse in (False,True)]}
put(DES/'matrix.json',matrix)
criteria={'frozen_at':datetime.now(timezone.utc).isoformat(),'product_changes':0,
 'scope':'Exact ADR1086 rev004 product bytes; prospective finite engineering contracts only, no legal holdout or quality certification.',
 'matrix':bound(DES/'matrix.json'),
 'primary':['Every declared new page boundary preserves all candidates exactly once and binds READ enum to visible rows; all non-read actions remain; all source text, judgment identities, reasons and need content remain unchanged; sorted canonical reconstruction agrees.',
 'Every journal condition matches independently assembled exact evidence, span order and hashes; whole read has at most two SELECTs, single ID uses indexed lookup, corrupt text rejected; request DB only, no corpus queries.',
 'No product change, skipped primary condition, failure, missing source, permission bypass or source drift allowed.'],
 'secondary':'Previously observed pager/wire/judgment/recovery/native API tests rerun as supporting regression, not unseen primary evidence. Prior live partial answer and navigation failures retained.',
 'limits':{'rss_gib':4,'available_gib':3,'disk_gib':20,'swap_gib':0.5,'heavy_workers':1},
 'network':False,'new_model_calls':0,'rollback':'Official rollback to MAIN105 if any source/wire/state regression appears after activation.'}
put(DES/'criteria.json',criteria)
C=ac.snapshot(ADR,'qualified-r1',sorted(old['files']),experiment_id='ADR-1090-experiment-v1',arm_id='qualified',run_ids=['run-001']);S=C/'snapshot'
for name in old['files']:shutil.copyfile(source/name,S/name)
ac.freeze(C);cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding=dict(manifest_path=str((C/'candidate.json').relative_to(ROOT)),manifest_sha256=sha(C/'candidate.json'),revision_id=rev['revision_id'],revision_sha256=rev['revision_sha256'])
freeze={'code_root':str(code.relative_to(ROOT)),'files':old['files'],'candidate':binding,
 'tests':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1090').glob('*.py')}}
put(DES/'freeze.json',freeze)
# Selected release serves this exact 430-file inventory; the official prepare
# independently reconstructs and checks its own serving inventory before apply.
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':pointer['release_manifest_sha256'],
 'candidate':binding,'staged_files':old['files'],'excluded_candidate_paths':{}}
put(DES/'release-rebase.json',rebase)
changes=[]
for name in sorted(set(base['files'])|set(old['files'])):
 if base['files'].get(name)==old['files'].get(name):continue
 reason=('Common compact wire, candidate pages, batch journal reads and exact projection binding' if name.rsplit('/',1)[-1] in ('compact_model_input.py','read_candidate_pages.py','bounded_source_session.py','gateway.py','relations_repository.py','repository.py','law_candidates.py','decision_projection.py') else
 'Exact tested pre-existing working features: judgments, selected connection scope, action chain and structure/annex navigation; retained without rewriting' if '/legal_agent/' in name else
 'Exact tested profile, engine dependency or serving configuration from completed1086; no ontology1088 merge')
 changes.append({'path':name,'before':base['files'].get(name),'after':old['files'].get(name),'reason':reason})
put(DES/'integration.json',{'schema_version':'local-release-integration-v1','base_release_manifest_sha256':pointer['release_manifest_sha256'],'changes':changes,'candidate':binding,'rebase_receipt':bound(DES/'release-rebase.json')})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope'];m['decision_eligible']=True
m['design'].update(hypothesis=criteria['scope'],primary_metric='Prospective finite page/projection and actual SQL invariants; all conditions must pass',success_criteria=criteria['primary'],failure_criteria='Any failed or skipped declared condition, altered source or integrity bypass rejects qualification',criteria_frozen_before_run=True,release_rebase=bound(DES/'release-rebase.json'))
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id=C.name,arm_id='qualified',experiment_id=m['experiment_id'],run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1090/run.py',runner_sha256=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1090/run.py'))])
for a in m['design']['arms']:a.update(changes='No product edit; fixed mathematical/row oracle' if a['id']=='baseline' else 'Exact430files of1086rev004',controls='Same immutable candidate; prior observed tests secondary; new finite matrix primary only')
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['qualified'],'status':'planned','selection_rule':'Complete matrix frozen before first product invocation; new sizes4/9/13 and new SQL conditions;1089failed oracle/412observed pages explicitly excluded from primary','artifact_path':str((ART/'run-001/result.json').relative_to(ROOT)),'sha256':'PENDING'}]
m['dataset'].update(name='Prospective compact presentation and journal finite boundary matrix',version='v1',frozen_source=str((DES/'matrix.json').relative_to(ROOT)),sha256=sha(DES/'matrix.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[]
why='Synthetic presentation and journal contracts, no legal corpus retrieval or golden answer evaluation; prior live evidence is read-only diagnosis.'
m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why
put(ADR/'실험/manifest.json',m)
print(json.dumps({'primary_pages':len(matrix['pages']),'primary_sql':len(matrix['journal']),'files':len(old['files']),'delta':len(changes),'code':freeze['code_root']}))
