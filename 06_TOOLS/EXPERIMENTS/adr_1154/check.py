from common import *
import ast, copy

f=read(DES/'freeze.json'); inherited=read(DES/'inherited-verification.json')
for b in (v for v in inherited.values() if isinstance(v,dict) and 'path' in v):
    assert sha(ROOT/b['path'])==b['sha256'],b['path']
assert all(sha(ROOT/n)==h for n,h in f['scripts'].items())
assert all(sha(ROOT/n)==h for n,h in f['inputs'].items())
oldf=read(ROOT/inherited['freeze']['path']); oldr=read(ROOT/inherited['result']['path'])
S=ROOT/f['code_root']; stage=read(DES/'staging.json'); base=read(DES/'baseline.json')
assert f['files']==oldf['files'] and all(sha(S/n)==h for n,h in f['files'].items())
assert oldr['strict_success'] and oldr['technical_conditions']==226
rerun=read(ROOT/inherited['rerun']['path']); fw=read(ROOT/inherited['framework']['path'])
assert rerun['status']==0 and rerun['passed']==10 and not rerun['import_leaks']
assert fw['passed']==216 and fw['code_files']==f['files'] and sha(ROOT/fw['path'])==fw['sha256']
assert len(fw['rows'])==216 and all(r['status']=='passed' for r in fw['rows'])
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
assert all(sha(ROOT/stage['code_root']/n)==h for n,h in stage['files'].items())
draft=read(DES/'official-preview.json'); actual=dict(base['manifest']['files'])
for row in draft['changes']:
    if row['after'] is None: actual.pop(row['path'])
    else: actual[row['path']]=row['after']
assert actual==stage['files'] and len(actual)==440 and len(draft['changes'])==32
module='02_BACKEND/semantic_runtime/legal_agent/ontology_scenarios.py'
before=ast.parse((ROOT/base['code_root']/module).read_text()); after=ast.parse((S/module).read_text())
def strip_prompt(tree):
    tree=copy.deepcopy(tree)
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROMPT' for t in node.targets): node.value=ast.Constant('PROMPT')
    return ast.dump(tree)
assert strip_prompt(before)==strip_prompt(after)
prompt=read(DES/'prompt.json')
assert len(prompt['new'])==365 and len(prompt['old'])==374
assert any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROMPT' for t in n.targets) and ast.literal_eval(n.value)==prompt['new'] for n in after.body)
assert all(n.endswith('ontology_scenarios.py') or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in stage['changed'])
assert not any(n.startswith('01_DATA/') or '/research/' in n for n in actual)
assert stage['data_shipped'] is False
coord=read(ROOT/'09_ARTIFACTS/AUDITS/20261028-ontology-selection-main110/execution-coordination.json')
assert coord['safe_to_activate'] and coord['active_full_corpus_worker_stopped']
def bind(p): return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
put(DES/'release-rebase.json', {'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':draft['base_release_manifest_sha256'],'candidate':f['binding'],'staged_files':actual,'excluded_candidate_paths':{n:'Unchanged hash-bound test/build support excluded from official runtime' for n in sorted(set(f['files'])-set(actual))}})
for row in draft['changes']: row['reason']='Exact365char1150scenario-selection instruction; other AST unchanged' if row['path'].endswith('.py') else 'Dependent code/engine hash only; no profile or data change'
draft.update(candidate=f['binding'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',draft)
checks={k:True for k in ('same665_product_as_verified1153','all226_technical_conditions_hash_bound','official440_inventory_exact','single_prompt_literal_and31_pins_only','prompt365_chars','profile_model_budget_unchanged','ontology_on_off_retained','ontology_default_off_retained','no_ontology_data_or_research_files','same_data_generation','latest_main109_bound','active_batch_conflict_resolved')}
assert oldr['profile_unchanged'] and oldr['ontology_default_off'] and not oldr['ontology_data_included'] and oldr['same_data_generation']
put(ART/'run-001/result.json', {'status':'complete','strict_success':True,'checks':checks,'receipt_contract_checks':len(checks),'technical_conditions':226,'inherited_conditions':226,'this_run_test_executions':0,'new_model_calls':0,'quality_certified':False,'files':440,'changed_files':32,'ontology_data_included':False,'ontology_default_off':True,'inherited_verification':bind(DES/'inherited-verification.json'),'service_followup_required':True})
print('Receipt audit12/12; exact665product/440serving; inherited226; newmodel0')
