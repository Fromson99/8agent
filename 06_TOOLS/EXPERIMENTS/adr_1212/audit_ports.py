"""Follow-up read-only inventory of failures; no retry or engine substitution."""
from pathlib import Path
import json,sys,hashlib,time,traceback,os,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
freeze=read(D/'audit-freeze.json');assert all(sha(R/p)==h for p,h in freeze['files'].items())
b=read(D/'baseline.json');C=R/b['release']['code_root'];assert all(sha(C/n)==h for n,h in b['release']['files'].items())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert not (O/'port-audit.json').exists()
f=read(D/'freeze.json');sys.path[:0]=[str(C/'02_BACKEND'),str((R/f['entry']).parent)]
from gold_connection import GoldConfig,open_gold_request,VectorReader
from semantic_runtime.oracle_query_fulltext import UnitIndex
from semantic_runtime.initial_vector import Repository,profile,mode
from semantic_runtime.oracle_dp_io import digest
import oracledb
cred=Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json'
assert not cred.stat().st_mode&0o077
result={};start=time.monotonic()
with oracledb.connect(**read(cred)) as c:
    c.call_timeout=60000;cfg=GoldConfig.load(D/'config_b03.json',R);docs=[x['document_id'] for x in read(D/'documents.json')['documents']]
    req,t=open_gold_request(c,cfg,document_ids=docs,channel='cm-r12',seconds=180)
    m=req.records.manifest
    result['release_unchanged']=req.release_id==read(O/'gold-binding.json')['query_release']
    result['selection']={'search_selection':m.get('search_selection'),'selection_proof':m.get('selection_proof')}
    result['metadata_present']=sorted(m.get('metadata',{}));result['assets_present']=sorted(m.get('assets',{}))
    required=['native.unit','native.source','native.surface','native.index_label','native.member','native.coordinate','native.structure_proof','native.definition_summary']
    result['required_navigation_rows']={k:{'present':k in m['tables'],'rows':m['tables'].get(k,{}).get('rows',0)} for k in required}
    result['compiler_bindings']=m.get('navigation_compilers')
    prefix='asset_'+digest('navigation/navigation.sqlite')[:12]+'.'
    result['reference_projection']={k:m['tables'].get(prefix+k) for k in ('reference','reference_payload','reference_body','reference_end','reference_target','reference_candidate')}
    index=UnitIndex(req);found=index.law_groups_page(index,['상장'],limit=5)
    assert found['items'] and all(x.get('document_id') in docs for x in found['items']),found
    result['positive_fulltext']={'term':'상장','returned':len(found['items']),'total':found['total'],'result':found}
    v=VectorReader(req,cfg);head=v.active();envelope=v.metadata(head['VCTR_POST_ID'])
    result['gold_vector']={'head':head,'profile':envelope['manifest']['profile'],'completion':envelope['completion']}
    result['engine_vector_mode']=mode()
    result['engine_vector_tables']={k:getattr(Repository(req.sql),k) for k in ('r','s','a')}
    try:result['engine_vector_head']={'value':Repository(req.sql).active(req.release_id),'passed':True}
    except Exception as e:result['engine_vector_head']={'passed':False,'error_type':type(e).__name__,'error':str(e)}
    try:profile(envelope['manifest']['profile']);result['engine_accepts_gold_vector_profile']=True
    except Exception as e:result['engine_accepts_gold_vector_profile']=False;result['vector_profile_error']=str(e)
    result['vector_interpretation_correction']='The selected engine HAS an initial-vector Retriever in oracle_query_resources (default auto). Factory vector=False alone does not disable it. Its SIDDS legacy tables and legal-vector-profile-v1/GENOS encoder contract do not match the R12 Gold tables and locally pinned BGE-M3 profile; the current adapter does not translate them. Original preflight evidence text was incomplete and is superseded by this port audit.'
    result['sql_calls']=len(t.statements);put(O/'port-audit-sql.json',t.statements)
result.update(model_calls=0,embedding_calls=0,seconds=time.monotonic()-start,code_unchanged=all(sha(C/n)==h for n,h in b['release']['files'].items()),pointer_unchanged=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],free_disk_GiB={str(p):round(shutil.disk_usage(p).free/1024**3,2) for p in (R,Path('/mnt/c'))})
put(O/'port-audit.json',result)
print(json.dumps({k:v for k,v in result.items() if k not in ('reference_projection','positive_fulltext','gold_vector')},ensure_ascii=False,indent=2))
