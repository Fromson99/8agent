"""Exclude only unrelated legacy schemas that invalidate an existing cache compiler."""
from common import *
import sys,copy,shutil,gzip,ast
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-0966-law-name-bound-holdout';PA=P/'artifacts'
pm=read(P/'실험/manifest.json');old=read(PA/'stage.json');base=read(ROOT/old['base_pointer']['manifest_path'])
assert pm['reservation']['status']=='completed' and read(PA/'analysis.json')['strict_success']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==old['base_pointer']
C=ART/'code';shutil.copytree(ROOT/old['roots']['candidate'],C)
target='02_BACKEND/semantic_runtime/full_glossary.py';before=(C/target).read_bytes();original=(ROOT/old['base_pointer']['manifest_path']).parent/'code'/target
def nodes(raw):
    tree=ast.parse(raw);return [ast.dump(n,include_attributes=False) for n in tree.body if not (isinstance(n,ast.FunctionDef) and n.name=='decision_schema') and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PLAN_SCHEMA' for t in n.targets))]
assert nodes(before)==nodes(original.read_bytes()),'Changes beyond the two legacy schemas must not be excluded'
assert all(sha(ROOT/n)==h for n,h in old['files']['candidate'].items()),'working drift'
with gzip.open(ART/'preserved-full_glossary.py.gz','wb') as out:out.write(before)
shutil.copyfile(original,C/target)
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
    v=read(p)
    if 'files' in v:
        for n in v['files']:v['files'][n]=sha(C/n)
        save(p,v)
def pins(v):
    if isinstance(v,dict):
        if v.get('manifest') and 'sha256' in v and (C/v['manifest']).is_file():v['sha256']=sha(C/v['manifest'])
        for x in v.values():pins(x)
    elif isinstance(v,list):
        for x in v:pins(x)
p=C/'00_SYSTEM/PIPELINE.json';v=read(p);pins(v);save(p,v)
files={n:sha(C/n) for n in old['files']['candidate']};changed=[n for n,h in files.items() if h!=old['files']['candidate'][n]]
assert all(n==target or n.startswith('02_BACKEND/ENGINES/') or n=='00_SYSTEM/PIPELINE.json' for n in changed)
law_paths={n:h for n,h in files.items() if n.startswith('02_BACKEND/semantic_runtime/legal_agent/')}
assert all(old['files']['candidate'][n]==h for n,h in law_paths.items())
seal={'base_pointer':old['base_pointer'],'roots':{'candidate':str(C.relative_to(ROOT)),'baseline':old['roots']['candidate']},'files':{'candidate':files,'baseline':old['files']['candidate']},'working_baseline':old['files']['candidate']}
save(ART/'stage.json',seal)
delta={'changed_from_model_trial':changed,'functional_file':target,'legacy_only_schema_nodes':['PLAN_SCHEMA','decision_schema'],
 'all_other_ast_nodes_identical':True,'all_legal_agent_bytes_identical':True,'legal_agent_files':law_paths,
 'preserved_unapplied_change':{'path':str((ART/'preserved-full_glossary.py.gz').relative_to(ROOT)),'sha256':sha(ART/'preserved-full_glossary.py.gz'),'original_sha256':hashlib.sha256(before).hexdigest(),'restore':'gzip -dc to a review copy; do not overwrite selected compiler without a new compatible cache generation'},
 'reason':'Keep immutable active-cache compiler exact. The two excluded legacy full-glossary schemas are not invoked by v6/v8 law-navigation. Current RAG text-length changes elsewhere are preserved.'}
save(ART/'integration-delta.json',delta)
paths=[n for n,h in files.items() if base['files'].get(n)!=h]
candidate=ac.snapshot(ADR,'integrated',paths,experiment_id='ADR-0967-experiment-v1',arm_id='integrated',run_ids=['run-001'])
for n in paths:shutil.copyfile(C/n,candidate/'snapshot'/n)
ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('run_contracts.py')
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']='Preserve exact active-cache compiler; legal-agent source investigation bytes and parent model outcomes unchanged.'
m['design'].update(hypothesis='Removing only unrelated incompatible legacy schemas allows real-data source reading while retaining measured law-name recovery.',primary_metric='All applicable260 contracts, native candidate/working/active consumers and exact code/data/model selection. Inherit model source-navigation8/8 and retry4/4 on identical legal-agent code.',success_criteria='All260 applicable contracts pass; only the seven pre-recorded failures may be excluded. Native service HEALTH and real law-name candidate, same-article retry and original read pass. All418 serving files match evaluated/working/selected; code/cache/source/ACL/state checks must hold. Every legal-agent module must equal ADR0966 model trial. Actual activated service failure rolls back. No new model quality estimate.',failure_criteria='Any new contract failure, cache/source/ACL/state/hash failure or byte drift blocks cutover. Do not weaken cache integrity or mutate original generation.',criteria_frozen_before_run=True,
 code_isolation={**pm['design']['code_isolation'],'candidates':[{'candidate_id':'integrated','arm_id':'integrated','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}]},
 allowed_existing_failures=pm['design']['allowed_existing_failures'],test_bindings=pm['design']['test_bindings'],budget=pm['design']['budget'],
 inherited_model_outcomes={'path':str((PA/'analysis.json').relative_to(ROOT)),'sha256':sha(PA/'analysis.json')},
 limits='Parent integration failed on cache compiler binding; only its valid source-model outcomes are inherited. This ADR must newly qualify final integrated code against real data.')
m['design']['arms'][0].update(changes='Completed ADR0966 model8/8, retry4/4; failed production cache binding retained',controls='No new baseline model calls')
m['design']['arms'][1].update(changes='Restore exact MAIN97 full_glossary compiler bytes; preserve all current law-name and other RAG text-length work',controls='Unchanged data/model/search-selection; all legal-agent source identical to parent')
m['design']['script_bindings']={str(p.relative_to(ROOT)):sha(p) for p in runner.parent.glob('*.py')}
m['llm_policy']=copy.deepcopy(pm['llm_policy']);m['llm_policy']['llm_calls']=[]
m['dataset']={'name':'Deterministic integration and real public original reading; parent synthetic model outcomes inherited','version':'law-name-integration-v1','frozen_source':str((ART/'stage.json').relative_to(ROOT)),'sha256':sha(ART/'stage.json'),'legal_version_checked':True,'reference_version_checked':True,'version_scope':'Original selected local data unchanged; no legal-answer evaluation'}
reason='No new retrieval-effect comparison: unchanged legal-agent modules inherit parent exact source-navigation outcomes; this run qualifies cache compatibility, contracts and real service wiring.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['runs'][0].update(purpose='audit',status='planned',selection_rule=m['design']['success_criteria'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'model_calls':0})
text=(ADR/'README.md').read_text().replace('decision_eligible: false','decision_eligible: true');(ADR/'README.md').write_text(text)
print('Frozen418; legacy compiler restored only in candidate; legal-agent identical; working untouched')
