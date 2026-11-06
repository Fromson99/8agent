from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(exist_ok=False)
def candidate(number):
    folder=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number}-*'))
    assert read(folder/'실험/manifest.json')['reservation']['status']=='completed'
    return read(folder/'artifacts/design/candidate-repaired.json')
o,c=candidate(1376),candidate(1369)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==142
base=read(ROOT/ptr['manifest_path']);assert sha(ROOT/ptr['manifest_path'])==ptr['release_manifest_sha256']
for f in (o,c,{'selected_files':base['files'],'code_root':base['code_root']}):
    assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['selected_files'].items())
assert o['selected_files'].keys()==c['selected_files'].keys()==base['files'].keys()
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
b={'pointer':ptr,'release':base,'working_files':{n:sha(ROOT/n) for n in base['files']},
   'gold_binding':read(gold/'binding.json'),'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.json','.py','.yaml')}}
assert b['gold_binding']['engine_root']==base['code_root'] and b['gold_binding']['engine_files']==base['files']
put(DES/'baseline.json',b)
criteria={'scope':'User-directed local MAIN143. Join completed1376 ontology authoring with completed1369 answer consumer which actually used the approved package in1374. Exclude unrelated newer work. No production knowledge publication or GENOS field changes.',
 'required':['Regenerate engine hashes and native metadata; exact executable639 plans vs active MAIN142','Prepared service files equal candidate528; relevant prepared ontology, final review and 434 native contracts pass','Actual selected fresh-process MAIN and Gold entry checks; version/rollback/original data confirmed.'],
 'failure':'Do not activate on failed prepared checks. Preserve before state; use official rollback if selected-entry validation fails. Known limitations: one explicit adopted case; general ON/OFF still unresolved.',
 'rollback':ptr['manifest_path'],'parents':{'ontology':o['pin'],'consumer':c['pin']},'limits':{'model_calls':0,'heavy_workers':1}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Exact tested local service selection and retained source/data/Gold compatibility',success_criteria=criteria['required'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for arm in m['design']['arms']:
    arm.update(changes='Exact active142 reference' if arm['id']=='baseline' else 'Current user-authorized integration of two completed arms',controls='Same original data, Gold configuration, source review, default settings and physical provider policy')
m['integration'].update(result_arm='integrated',rationale=criteria['scope'],common_invariants='Exact original scope, ACL, immutable records, frozen source and engine validation',conflicts=[],no_conflict_reason=None,rollback_ref='ADR-1336-experiment-v1/integrated')
for row in m['integration']['parent_contributions']:
    row.update(adopted='All ontology_work products from completed1376' if '1376' in row['parent_ref'] else 'All answer-consumer paths from completed1369',excluded='No unverified working-only changes or deployment to field')
for n in base['files']:
    if o['selected_files'][n]!=c['selected_files'][n] and not ('/ENGINES/' in n or n in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py')):
        m['integration']['conflicts'].append({'surface':n,'resolution':'Take exact 1376 authoring bytes' if '/ontology_work/' in n else 'Take exact 1369 answer-consumer bytes','reason':'Select tested producer and tested consumer independently as in1374'})
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Pinned legal-agent final-review, real-wire authoring and native assembly contracts',version='local-main143-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Prepared frozen code then fresh actual MAIN selection and Gold connector import checks',artifact_path=str((ART/'result.json').relative_to(ROOT)))
for y in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):y['not_applicable_reason']='Local integration and active code binding only; live RAG experiment will be separate'
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'integrated',list(base['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
sources={}
for n in base['files']:
    f=o if n.startswith('02_BACKEND/semantic_runtime/ontology_work/') else c
    if ('/ENGINES/' not in n and n not in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py') and f['selected_files'][n]!=base['files'][n]):
        assert '/ontology_work/' in n or '/legal_agent/' in n,n
        sources[n]=1376 if f is o else 1369
    shutil.copyfile(ROOT/f['code_root']/n,can/'snapshot'/n)
put(DES/'source-set.json',sources);put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(base['files']),'product_files':list(sources)})
print('verified products',len(sources))
