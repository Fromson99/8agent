from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1134-scenario-sufficiency-search-return';ART=ADR/'artifacts';D=Path(__file__).parent;OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1133-scenario-selection-receipt'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(OLD/'artifacts/freeze.json');source=ROOT/f['code_root'];oldm=read(OLD/'실험/manifest.json')
criteria={'hypothesis':'Explicit multi-route scope and sufficiency decisions can use one bounded reselection, then native original investigation when unavailable or insufficient, without legal text rewriting or unbounded retry.', 'primary':['All synthetic contracts pass','Native HTTP insufficient/no-match leads to existing SELECT and actual additional original read','After fallback use ordinary assessment, no repeated scenario loop','Normal/conditional chosen body unchanged and duplicate request reuses result','Shorter system prompt than1133; multi-select enabled without comparison-only wording'], 'run':'Synthetic local contracts and native HTTP only; no new model or quality/latency comparison; historical1133 provenance only.', 'failure':'Any integrity failure, lost prior claims/gaps, repeated selector loop, failed HTTP recovery or final body drift', 'failure_contract':{'owner':'output.bounded_decision owns shape repair; scenario runtime owns at most1 insufficiency reselection; existing completion tail owns SELECT reentry', 'budget':'At most2 choices with at most1 shape repair each, same request model/deadline. Reserve ordinary search/finalization. Missing catalog skips selector. Repeated insufficiency goes to ordinary search.', 'state':'Existing DecisionJournal preserves raw accepted/rejected choices per round; existing ASSESS_GAP_REENTRY persists originals/gaps/counters; request same input does not invoke again.', 'meaning':'No rule-generated path or legal rewrite. CONDITIONAL preserves missing user facts; coverage shortage is original investigation. Transport/authority/hash failures remain failures.', 'publication':'Keep selected immutable text while sufficient; ordinary retrieval/assessment owns later legal answer after fallback. Missing paths do not prove source absence.'}, 'limits':{'max_rss_gib':4,'min_available_gib':3,'min_disk_gib':20,'heavy_processes':1,'new_model_calls':0}}
put(ART/'criteria.json',criteria)
for name in ['composition.json','parent.json']:shutil.copyfile(OLD/'artifacts'/name,ART/name)
put(ART/'parent-binding.json',{'parent':'ADR-1133-experiment-v1/scenario','freeze_sha256':sha(OLD/'artifacts/freeze.json'),'selected_pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria='All fixed contracts pass; no live model quality certification',failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for a in m['design']['arms']:a.update(changes='Historical parent, not rerun' if a['id']=='baseline' else 'Short multi-route sufficiency contract, bounded reselection and native SELECT reentry',controls='Same scenario package compiler and original/source contracts as1133')
m['runs'][0].update(arm_ids=['scenario'],selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'scenario-r1',present,experiment_id=m['experiment_id'],arm_id='scenario',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(source/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for name in ['common.py','check.py','test_direct.py','test_projection.py','test_semantics.py','test_scenarios.py','test_scenario_native.py']:
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1133'/name).read_text().replace('ADR-1133-scenario-selection-receipt','ADR-1134-scenario-sufficiency-search-return').replace('adr_1133','adr_1134').replace('ADR1133','ADR1134');(D/name).write_text(s)
print(S)
