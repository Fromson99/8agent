from pathlib import Path
import sys,json,hashlib
ROOT=Path('/home/jin/8-AGENT')
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector'
DES=ADR/'artifacts/design';DES.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path'])
assert active['generation']==118
criteria={'scope':'All 1547 documents and every logical row of the selected nine SQLite assets, original tokenizer postings and navigation references; R12 B03 physical schema. B05 is naming compatibility only.',
 'success':['13 tables / 60 columns / 13 PK / 11 nonunique ordinary indexes, exact R12 types',
 'Complete source and query row counts and SHA chains agree before publication and activation',
 'Document/unit/parent/block and reference links preserved; ACL rejects widening; stale HEAD CAS rejected',
 'Local real BGE-M3 vectors carry exact input/source/profile hashes, finite normalized 1024 dimensions and full text coverage; partial vector publication never active',
 'Independent explicit parameter connection uses GOLD tables; current selected MAIN118 bytes and active pointer unchanged'],
 'failure':'Any missing row, source/hash/permission violation, implicit embedding truncation, resource guard or Oracle capacity shortfall prevents complete/active status. Preserve partial evidence and report blockers.',
 'stages':['read-only inventory and deterministic capacity bound','Oracle stratified capacity pilot','full migration only if the native Oracle capacity admits it','real embedding pilot and measured full-build budget','independent source/search/vector contracts'],
 'capacity_rule':'Do not attempt a full import if a conservative payload/index lower bound already exceeds Oracle Free 12GB. No deletion of existing owners, no sharding to evade product limits. Keep a reusable full importer and report the target requirement.',
 'resources':{'heavy_processes':1,'minimum_wsl_free_GiB':80,'minimum_c_free_GiB':80,'maximum_new_disk_GiB':40,'minimum_available_RAM_GiB':3,'maximum_worker_RSS_GiB':5.5,'maximum_process_swap_increase_MiB':128,'cpu_threads':4,'pilot_embedding_seconds':600},
 'embedding':{'model':'BAAI/bge-m3','local_only':True,'dimensions':1024,'metric':'COSINE','normalization':'l2','max_tokens':512,'max_characters':800,'overlap':100,'no_truncation':True,'cache_reuse':'Only exact input hash/profile bindings; legacy truncated cache is not complete coverage.'},
 'evaluation':'Data integrity/integration feasibility only, no answer generation or legal-quality benchmark; retrieval ranking accuracy not certified.',
 'external_model_calls':0,'main_wiring':'unchanged','genos_deployment':False}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
m=read(ADR/'실험/manifest.json');h='R12 gold can preserve the selected corpus and support independently parameterized original, lexical and native vector reads, subject to measured local database capacity.'
m['lineage']['hypothesis_delta']=h
m['design'].update(hypothesis=h,primary_metric='Complete migration integrity and native GOLD contract checks',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'artifact_path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')},execution=criteria)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Read-only selected corpus and existing projection contract','controls':'Selected MAIN118 and same immutable nine source databases'},{'id':'gold-b03','role':'candidate','derived_from':['baseline'],'changes':'Independent full importer, resource-aware publication and local embedding runner','controls':'Same source versions, JSON hash contract, tokenizer and ACL'}]
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Selected MAIN118 full corpus',version=active['release_id'],frozen_source=str((DES/'baseline.json').relative_to(ROOT)),sha256=sha(DES/'baseline.json'))
m['runs'][0].update(selection_rule='Whole corpus; deterministic first 128 rows per nonvirtual asset table for sizing; first source spans for local embedding throughput, no golden answer selection',artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='Migration and SQL contract feasibility, no paired candidate retrieval or answer benchmark'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No retrieval-quality or answer-quality claim; native exact search is an integration contract only'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=['08_DEPLOYMENT/LOCAL/gold_connection_r12/'+p for p in ['gold_connection.py','config_b03.json','config_b05.json']]
C=ac.snapshot(ADR,'gold-b03',paths,experiment_id=m['experiment_id'],arm_id='gold-b03',run_ids=['run-001'])
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str((C/'snapshot').relative_to(ROOT))})
print(C/'snapshot')
