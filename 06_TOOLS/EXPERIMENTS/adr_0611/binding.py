"""Explicit public-source binding, independent of immutable source export flags."""
import hashlib,json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards';D=A/'artifacts/design'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text())
def verify(all_files=False):
 b=read(D/'source-binding.json');policy=read(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json');auth=read(R/'08_DEPLOYMENT/CONFIG/legal-source-export.json');g=read(R/b['generation']/'manifest.json')
 assert auth['enabled'] and sha(R/'08_DEPLOYMENT/CONFIG/legal-source-export.json')==b['source_authorization_sha256']
 assert sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==b['policy_sha256'] and policy['model']==b['model'] and policy['endpoint']==b['destination']
 assert b['public_questions_only'] and not b['private_documents_allowed']
 assert g['export_allowed']==b['source_manifest_export_allowed']==False
 assert g['generation_id']==b['generation_id'] and g['store_sha256']==b['source_store_sha256']
 allowed=set(b['scope_document_ids']);assert any(allowed<=set(x['document_version_ids']) for x in auth['bindings'])
 if all_files:
  assert sha(R/b['generation']/'store.sqlite')==b['source_store_sha256']
  db=sqlite3.connect('file:'+str(R/b['generation']/'store.sqlite')+'?mode=ro',uri=True)
  stored={i:h for i,h in db.execute('SELECT document_id,source_artifact_sha256 FROM document')};db.close()
  for p in b['document_provenance']:
   assert p['document_id'] in allowed and p['status']=='verified'
   assert not p['raw_relative_path'].startswith('internal/')
   assert sha(R/'01_DATA/RAW'/p['raw_relative_path'])==p['raw_sha256']
   assert p['source_artifact_sha256']==stored[p['document_id']]
 return b

def check_payload(data,allowed):
 if isinstance(data,dict):
  for k,v in data.items():
   if k in ('document_id','document_version_id') and isinstance(v,str):assert v in allowed,'source outside public grant'
   if k in ('document_ids','document_version_ids') and isinstance(v,list):assert set(v)<=allowed,'scope outside public grant'
   check_payload(v,allowed)
 elif isinstance(data,list):
  for v in data:check_payload(v,allowed)
