"""Freeze scope before implementing the user-authorized navigation repair."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/ptr['manifest_path'])
assert ptr['generation']==149
assert sha(ROOT/ptr['manifest_path'])==ptr['release_manifest_sha256']
assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
put(DES/'baseline.json',{'pointer':ptr,'release':release,'gold_binding':read(gold/'binding.json'),
 'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.json','.py','.yaml')},
 'working_files':{n:sha(ROOT/n) for n in release['files']}})
criteria={'authorization':'전체 구현하고 메인에 반영해',
 'hypothesis':'A single explicit dispatch contract, scope-aware lossless tool menus, action-specific guidance and repair aliases remove mechanically induced navigation conflicts while retaining goals, evidence, authorization and bounded recovery.',
 'success':['Every accepted action is the action actually executed; new source needs never silently replace a selected action.',
 'All originally executable navigation paths remain reachable through the compact menu; visible choices and schema agree, stale or hidden targets remain rejected.',
 'Normal and repair prompts use the same public action names, target mapping and eligibility conditions.',
 'Original evidence, required goals, unresolved scope and budgets survive failure, handoff, resume and duplicate requests.',
 'Relevant contract and actual API tests pass with no new failures against MAIN149; prepared and selected service plus Gold engine checks pass.'],
 'failure':['New permission, source/hash, state, budget or evidence regression; unrecorded action replacement; hidden unreachable required source; new contract failures.'],
 'limits':['Structural and native API contracts are not general legal quality certification. Live model verification is a separately frozen follow-up after implementation. No GENOS field deployment or source DB mutation.'],
 'planned_scope':['request entry and memory transition audit','source action/goal dispatch','tool menu and descriptions','schema and repair names','finish and scope gates','review/repair owners','assessment/ontology consumption and publication'],
 'resource_limits':{'minimum_available_GiB':4,'maximum_swap_growth_MiB':128,'heavy_processes':1}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Executable choice, scope, recovery and selected consumer contract correctness',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Navigation and downstream synthetic contracts, source-bound prior failure fixtures',version='coherent-navigation-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['retrieval_accounting']['changed']=False
m['retrieval_accounting']['not_applicable_reason']='Contract implementation; original retrieval set retained and every offered route remains reachable. Live selection effect is reserved for a follow-up.'
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No live retrieval or legal-answer effect comparison in this implementation ADR')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Frozen deterministic contract matrix and actual native API then prepared and selected service checks',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
for a in m['design']['arms']:a.update(changes='Selected MAIN149' if a['id']=='baseline' else 'Coherent navigation dispatch, compact menus and repair contract',controls='Same source generation, model policy, authorization and final evidence verification')
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',list(release['files']),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in release['files']:shutil.copyfile(ROOT/release['code_root']/n,can/'snapshot'/n)
put(DES/'mutable-candidate.json',{'path':str(can.relative_to(ROOT)),'files':list(release['files'])})
print(can/'snapshot')
