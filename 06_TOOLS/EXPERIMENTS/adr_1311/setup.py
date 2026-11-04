from pathlib import Path
import shutil,sys,json,datetime
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent;OLDT=ROOT/'06_TOOLS/EXPERIMENTS/adr_1310'
for n in ['common.py','authorization.py','pinned_imports.py','resource_guard.py','sql_observer.py','profile_observer.py','offline_transport.py']:
 s=(OLDT/n).read_text().replace('ADR-1310-main136-latency-profile','ADR-1311-structure-latency-repair')
 (T/n).write_text(s)
s=(OLDT/'profile_run.py').read_text().replace("assert arm=='profile'","assert arm in ('before','optimized')").replace("ART/('deep' if '--deep-profile' in sys.argv else 'profile')", "ART/'replay'").replace('ADR1310-offline-profile','ADR1311-equivalent-latency-repair')
(T/'replay.py').write_text(s)
sys.path.insert(0,str(T));from common import *
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1310-main136-latency-profile';DES.mkdir(exist_ok=False)
for n in ['baseline.json','baseline-after.json','authorization.json','nearai-only.json','sqlite-source.json','scoring-only-originals.json','source-cell.json']:
 shutil.copyfile(OLD/'artifacts/design'/n,DES/n)
shutil.copytree(OLD/'artifacts/transport',ART/'transport')
c=read(OLD/'artifacts/design/cases.json');c[0]['arms']=['before','optimized'];put(DES/'cases.json',c)
criteria={'hypothesis':'Replace repeated whole-corpus hierarchy scans with parent indexes and bounded successful-resolution reuse, preserve source scopes, and reuse bound original blocks; same protected model inputs/results with less CPU and point SQL.',
'primary_metric':'Same native replay request wall seconds with identical low-overhead observer; before then optimized, one fresh process each, OS cache not cleared.',
'success':['Both arms exactly reproduce all8 original model requests except prior-declared generated view_id/usage and unmodified8 responses; final text/claims/scope/source exactly identical.','Optimized complete replay >=50% faster than fresh before replay, and no full-map per-parent scan.','Target contracts preserve invalid/ambiguous/excluded/cyclic selections, ordering/hash, ACL/stale/store change/failed result/reuse mutation and Oracle request deadlines.','Individual source metadata loads reduced and no content/ACL source loss.'],
'failure':['Any protected input/final answer mismatch, new regression, unexpected network, source/code drift or resource stop.','No claimed Oracle corpus speedup without an actual Oracle timing run.'],
'order':['ontology-369/before','ontology-369/optimized'],'repeats':1,'new_external_calls':0,
'fixed':['Source corpus and generation, original response tape, model/provider/reasoning, final-tables-off ablation, semantic supervisor, schema/prompt, source/ACL/hash checks, budgets'],
'changes':['structure_selection children parent lookup and successful resolution memo','multi_entry prepared immutable coordinates and store binding','query_scope search source IDs by document metadata','storage bounded immutable block memo'],
'failure_contract':'Original ContractError/SelectionError/ValidationError remain owned by existing navigation repair; memo stores only successful records, every lookup retains hash/authorization/source-generation checks. No retry/budget/UNKNOWN behavior changes.',
'limits':read(OLD/'artifacts/design/criteria.json')['limits'],
'followup':'Termination-supervisor semantic changes and live model validation get separate subsequent ADR; source compiler modules/Gold published layouts not modified.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');parent=read(OLD/'실험/manifest.json')
for k in ['design','llm_policy','dataset','retrieval_accounting']:m[k]=parent[k]
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1310-experiment-v1/profile'],'changes':'Completed root-cause diagnosis reference','controls':'Same parent source and code'},*({'id':a,'role':'candidate','derived_from':['baseline'],'changes':'Unchanged frozen parent' if a=='before' else 'Equivalent indexing/reuse and scope SQL repair','controls':'Same tape and protected-input checks'} for a in ('before','optimized'))]
stages=parent['design']['retrieval_stage_plan']['stages_by_arm']['profile'];m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','before','optimized')}
m['design']['code_isolation']['candidates']=[];m['llm_calls']=[]
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261104-structure-latency-v1')
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Exact retrieval/selection semantics retained and original inherited ledger; performance-only implementation.')
m['runs'][0].update(arm_ids=['before','optimized'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='Same original369 tape, fresh before then optimized once after contracts pass.')
m['lineage']['hypothesis_delta']=criteria['hypothesis'];put(ADR/'실험/manifest.json',m)
# Use the original shallow parent snapshot, avoiding recursively nested candidate paths.
orig=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1309-main136-sqlite-latency/artifacts/design/candidate-after.json');code=ROOT/orig['code_root']
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
for arm in ['before','optimized']:
 paths=[str((code/n).relative_to(ROOT)) for n in orig['selected_files']]
 can=ac.snapshot(ADR,arm,paths,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
 put(DES/(arm+'-path.json'),{'candidate':str(can.relative_to(ROOT)),'code_relative':orig['code_root'],'files':orig['selected_files']})
print('Design fixed; isolated before/optimized snapshots prepared.')
