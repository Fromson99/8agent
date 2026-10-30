"""Selective three-way composition of completed parents, before any tests."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
A=ROOT/'04_EXPERIMENTS/ADR/ADR-1088-ontology-a1-compact-integration';ART=A/'artifacts'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text())
parents={}
for p in m['lineage']['parents']:
 assert sha(ROOT/p['manifest_path'])==p['manifest_sha256']
 v=json.loads((ROOT/p['manifest_path']).read_text());assert v['results']['by_arm'][p['arm_id']]['status']=='complete'
 binding=v['design']['code_isolation']['candidates'][0]
 cm=json.loads((ROOT/binding['manifest_path']).read_text());r=next(r for r in cm['revisions'] if r['revision_id']==binding['revision_id'])
 assert r['revision_sha256']==binding['revision_sha256']
 code=(ROOT/binding['manifest_path']).parent/'revisions'/binding['revision_id']/'snapshot'
 assert all(sha(ROOT/x['frozen_path'])==x['snapshot_sha256'] for x in r['files'])
 parents[p['experiment_id']]={'code':code,'revision':r,'binding':binding}
ontology=parents['ADR-1087-experiment-v1']['code'];common=parents['ADR-1086-experiment-v1']['code']
common_base=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1085/compact-r1/revisions/rev-001/snapshot'
criteria={'hypothesis':'Common compact input/paging/batched journal code can be selectively combined with the ontology-only repair without losing task-local judgments, delivery, source or selection contracts.',
 'primary_metric':'Combined A1/A2 real HTTP synthetic delivery; common wire tamper/paging/SQL and ontology regressions; rollback index recovery.',
 'success_criteria':['All combined ontology/API tests and inherited common contracts pass on identical frozen code; original texts and selectable refs exact.',
  'Only common1086 changed hunks adopted, preserve1079/1087 task-local/action-minimal/review state; conflict resolutions explicit before test.',
  'Current A1 uses compact wire and20candidate paging. Synthetic output selects existing allowed actions; hidden/stale choices rejected. No assertion about real LLM appropriateness.',
  'Index flag set only after autocommit creation; first create in transaction rolled back or committed is rechecked, no false delivery or new model call.',
  'No MAIN/GENOS changes and no live model/corpus loading; exact merge/code/run/pin receipts retained.'],
 'failure_contract':'Existing retry owners/budgets preserved. Invalid source/hash/state/choice fails. Index DDL failure propagates before marking receipt; no new automatic retry. First index rollback cannot authorize a nonindexed cache hit.',
 'models':{'calls':0,'output_cap':None},'resources':{'max_rss_gib':1,'min_available_gib':3},
 'parents':{k:{'code_root':str(v['code'].relative_to(ROOT)),'binding':v['binding']} for k,v in parents.items()},
 'common_base':str(common_base.relative_to(ROOT))}
assert not (ART/'criteria.json').exists();put(ART/'criteria.json',criteria)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update({k:criteria[k] for k in ('hypothesis','primary_metric','success_criteria','failure_contract')},criteria_frozen_before_run=True,failure_criteria='Any original/choice/state regression fails; no live model until separately planned.')
m['design']['criteria_record']={'path':str((ART/'criteria.json').relative_to(ROOT)),'sha256':sha(ART/'criteria.json')}
m['integration'].update(result_arm='integrated',rationale=criteria['hypothesis'],common_invariants='Exact original/source/ACL/state and A1/A2 semantics; same schema decoder and successful delivery proof.',no_conflict_reason=None)
m['integration']['parent_contributions']=[{'parent_ref':'ADR-1087-experiment-v1/optimized','adopted':'Full frozen ontology/task-local base with four ontology product changes','excluded':'Known transaction-ready-flag issue fixed; no legal-quality claim'}, {'parent_ref':'ADR-1086-experiment-v1/compact','adopted':'Only eight changed product modules and two profile settings, applied as three-way hunks','excluded':'Independent base snapshot and profile values; live quality/latency not transferred'}]
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Synthetic combined ontology/common API contracts',version='v1',frozen_source=str((ART/'criteria.json').relative_to(ROOT)),sha256=sha(ART/'criteria.json'))
reason='No retrieval selection measurement; synthetic source/choice identity preservation only. No real corpus, question or gold.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
for arm in m['design']['arms']:arm.update(changes='Completed parents, selective combined candidate plus rollback cache repair',controls='Same existing semantic/source/selection contracts and budgets; models0')
put(A/'실험/manifest.json',m)
files={str((ROOT/r['frozen_path']).relative_to(ontology)) for r in parents['ADR-1087-experiment-v1']['revision']['files']}
integration=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding/artifacts/integration.json').read_text())
delta=[r['path'] for r in integration['files'] if '/ENGINES/' not in r['path'] and r['path']!='00_SYSTEM/PIPELINE.json']
files.update(delta);existing=[n for n in files if (ROOT/n).is_file()]
C=ac.snapshot(A,'a1-combined-r1',sorted(existing),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n in files:
 source=ontology/n if (ontology/n).is_file() else common/n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p)
 if n not in existing:ac.register_file(C,n,upstream_state='absent')
merges=[]
for n in delta:
 ours=S/n
 if not (ontology/n).exists():status='new-common-file';ours.write_bytes((common/n).read_bytes());rc=0
 else:
  r=subprocess.run(['git','merge-file','-p',str(ours),str(common_base/n),str(common/n)],text=True,capture_output=True)
  assert r.returncode>=0,(n,r.stderr)
  ours.write_text(r.stdout);rc=r.returncode;status='conflict' if rc else 'merged'
 merges.append({'path':n,'status':status,'conflicts':rc,'common_base_sha256':sha(common_base/n) if (common_base/n).exists() else None,'common_sha256':sha(common/n),'ontology_sha256':sha(ontology/n) if (ontology/n).exists() else None})
# This flag is only a performance hint, and must not outlive rolled-back DDL.
p=S/'02_BACKEND/semantic_runtime/legal_agent/ontology_io.py';s=p.read_text();old='        repo._ontology_delivery_index_ready = True';assert old in s
p.write_text(s.replace(old,"        repo._ontology_delivery_index_ready = not repo.db.in_transaction"))
put(ART/'merge-initial.json',{'files':merges,'unresolved':[r['path'] for r in merges if r['conflicts']]})
print(json.dumps({'candidate':str(S.relative_to(ROOT)),'conflicts':[r['path'] for r in merges if r['conflicts']]}))
