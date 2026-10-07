"""Read-only verification of actual DB bindings, public scope and split bundle recovery."""
from pathlib import Path
import json,hashlib,gzip,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0524-gemma-fp8-scoped-retrieval'
def read(p):return json.loads(p.read_text())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
f=read(A/'artifacts/frozen-design.json');index=read(A/'artifacts/run-001/results.json');scope=set(read(A/'product-cases.json')['public_scope_document_ids']);rows=[]
for cid,arms in index['cases'].items():
 for arm,ref in arms.items():
  p=R/ref['path'];r=read(p);expected=read(R/f['generations'][arm]/'navigation/manifest.json')['index_sha256'];actual=r.get('binding',{}).get('index_sha256')
  j=sqlite3.connect('file:'+str(p.parent/'journal.sqlite')+'?mode=ro',uri=True)
  docs={d[0] for d in j.execute('SELECT DISTINCT document_id FROM evidence_unit')}
  if actual is None:
   binding=json.loads(j.execute('SELECT binding_json FROM run').fetchone()[0]);actual=binding['index_sha256']
  j.close();assert docs<=scope;assert actual==expected
  restored=None;b=r.get('result',{}).get('assembly',{}).get('term_agent',{}).get('source_bundle')
  if b:
   b=json.loads(json.dumps(b));rb=b.get('reference_bundle') or {}
   if rb.get('graph_artifact'):
    with gzip.open(p.parent/rb.pop('graph_artifact'),'rt') as z:rb['graph']=json.load(z)
   bh=b.pop('bundle_hash');restored=digest(b)==bh;assert restored
  rows.append({'case_id':cid,'arm':arm,'actual_navigation_sha256':actual,'expected_navigation_sha256':expected,'public_evidence_documents':len(docs),'outside_public_scope':0,'split_bundle_reconstruction_valid':restored,'hard_deadline':r.get('error',{}).get('type')=='HardDeadlineExceeded' if r.get('error') else False})
out={'status':'PASS','actual_public_evidence_and_DB_bindings_verified':True,'semantic_relationship_correctness_certified':False,'case_rows':rows,'active_unchanged':hashlib.sha256((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()).hexdigest()==f['file_hashes']['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']}
(A/'artifacts/output-binding-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('Output binding audit PASS',len(rows))
