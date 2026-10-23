from pathlib import Path
import sys, json, hashlib, shutil
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1031-small-connections-parent-context'
ART=ADR/'artifacts'
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='Complete selected-scope directories with at most two distinct endpoints can deliver those originals without another model choice. Include only delivered own text of structural ancestors through the article; never their sibling subtrees. No recursive automatic reads.',
 primary_metric='Deterministic boundary/source/consumer contracts, not model answer quality.',
 success_criteria='One and two endpoints auto-read once; three remain selectable; ancestor own wording/links present, siblings absent; incomplete scan/failure/budget preserve originals and unresolved state; source/hash/ACL/resume enforced; actual API and existing regressions pass.',
 failure_criteria='Extra model decision for auto-read, automatic third target or recursive expansion, sibling contamination, repeated I/O after completion/failure, erased failure/evidence/budget, source/hash/ACL bypass.',
 criteria_frozen_before_run=True,
 failure_recovery={'owner':'Existing reader and request_repair; deterministic companion acquisition records partial failures through the existing definition_context failure recorder.', 'budget':'At most two unique endpoints per explicit selected-scope directory, 12000 new characters including parent introductions, existing shared tool/deadline/read budget. No model calls. Sequential tests, address space3GiB, minimum available RAM4GiB.', 'state':'Bound hashed directory/auto-read receipts; verified original body checkpoint before ancestor reads; retry does not reset failed/completed targets; incomplete catalogs retain menu; no applicability or sufficiency claims.'},
 working_integration='Integrate passing contract-tested code selectively with the new flag enabled in working profile; selected MAIN102 and GENOS unchanged. No model-effect or generalization claim.')
for a in m['design']['arms']:
 a.update(changes='Existing complete ADR1030, historical context only' if a['id']=='baseline' else m['design']['hypothesis'],controls='Working tree existing paths/pins, synthetic fixtures, same canonical source/ACL/budgets.')
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['llm_policy']['llm_calls']=[]
reason='Structural implementation audit with deterministic synthetic API/contract fixtures only; no corpus/model retrieval-effect comparison or scored question runs.'
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['runs'][0].update(arm_ids=['candidate'],selection_rule=reason,artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1030-first-required-read-before-stop/artifacts/design-freeze.json'
names=set(read(prior)['files']['candidate'])
assert all((ROOT/n).is_file() for n in names)
d=ac.snapshot(ADR,'candidate',sorted(names),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
save(ART/'stage.json',{'candidate_dir':str(d.relative_to(ROOT)),'root':str((d/'snapshot').relative_to(ROOT)),
 'working_before':{n:sha(ROOT/n) for n in sorted(names)},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
for name in ('common.py','run_contracts.py','repin.py'):
 text=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1030'/name).read_text().replace('ADR-1030-first-required-read-before-stop','ADR-1031-small-connections-parent-context')
 text=text.replace("read(ART/'stage.json')['roots'][arm]","read(ART/'stage.json')['root']").replace("read(ART/'stage.json')['roots']['candidate']","read(ART/'stage.json')['root']")
 if name=='repin.py': text=text.replace("('answer_progress.py', 'decision_projection.py')","('connection_scope.py', 'law_navigation.py', 'definition_context.py')")
 (Path(__file__).parent/name).write_text(text)
print(d/'snapshot')
