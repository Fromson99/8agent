"""Exhaustive original-data preservation and declared metadata boundary audit."""
from pathlib import Path
from itertools import zip_longest
from types import SimpleNamespace
import hashlib, json, sqlite3, sys

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0792-risk-committee-team-metadata';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

f=read(D/'freeze.json');b=read(D/'baseline.json');binding=read(D/'data-binding.json')
C=R/f['code_root'];G=R/binding['path'];B=R/b['manifest']['data_path'];did='11478916f48b00e5'
assert all(sha(R/n)==h for n,h in f['files'].items())
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime.fulltext import open_index
from semantic_runtime.team_scope import prepared_catalogue, select_documents
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent.errors import ContractError

checks={};counts={};old=sqlite3.connect(f'file:{B}/store.sqlite?mode=ro',uri=True)
new=sqlite3.connect(f'file:{G}/store.sqlite?mode=ro',uri=True)
schema='SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE \'sqlite_%\' ORDER BY type,name'
checks['same_source_schema']=old.execute(schema).fetchall()==new.execute(schema).fetchall()
changed=[]
for name, in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
    safe='"'+name.replace('"','""')+'"';count=0
    for before,after in zip_longest(old.execute(f'SELECT * FROM {safe} ORDER BY rowid'),new.execute(f'SELECT * FROM {safe} ORDER BY rowid')):
        count+=1;assert before is not None and after is not None
        if before==after:continue
        assert name=='document' and before[0]==after[0]==did and before[:-1]==after[:-1]
        bv,av=json.loads(before[-1]),json.loads(after[-1]);assert bv['document_metadata'].get('team') is None
        assert av['document_metadata'].pop('team')=='risk_team' and av==bv
        changed.append({'table':name,'document_id':did,'field':'document_metadata.team'})
    counts[name]=count
checks['all_source_rows_preserved_except_one_team_field']=len(changed)==1
old.close();new.close()
checks['navigation_and_fulltext_bytes_unchanged']=all(sha(B/n)==sha(G/n) for n in ['navigation/navigation.sqlite','fulltext/units.sqlite'])
checks['parent_manifest_unchanged']=sha(B/'manifest.json')==b['manifest']['data_manifest_sha256']
old_store=Store(B);new_store=Store(G)
try:
    ot=prepared_catalogue(old_store)['teams'];nt=prepared_catalogue(new_store)['teams']
    checks['all_existing_team_memberships_preserved']=all(nt[d]==v for d,v in ot.items() if d!=did)
    checks['only_target_team_corrected']=ot[did]==frozenset() and nt[did]==frozenset({'risk_team'})
    before_scope=select_documents(old_store,'risk_team');after_scope=select_documents(new_store,'risk_team')
    checks['risk_scope_adds_exact_target']=set(after_scope)-set(before_scope)=={did} and not set(before_scope)-set(after_scope)
    index=TermIndex(G/'navigation',new_store);ft=open_index(G/'fulltext',index.manifest)
    checks['native_source_navigation_fulltext_bindings_valid']=True
    t=LocalGemmaTransport(C,R);grant=t.grant
    original=read(R/b['manifest']['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
    checks['authorized_document_scope_unchanged']=grant['public_document_ids']==original['public_document_ids'] and grant['workflow_authorization']['document_ids']==original['workflow_authorization']['document_ids']
    request={'workflow_id':'risk_team_compare_workflow','principal':{'user_id':'jin','team_id':'risk_team'},'document_ids':after_scope}
    bound={'generation_id':binding['generation_id'],'store_sha256':binding['store_sha256'],'generation_manifest_sha256':binding['manifest_sha256']}
    assert did in t.authorize_workflow(request,bound)['scope_document_ids']
    checks['same_model_grant_accepts_corrected_scope']=True
    rejected=[]
    for key in bound:
        try:t.authorize_workflow(request,{**bound,key:'changed'})
        except ContractError:rejected.append(key)
    checks['stale_or_tampered_data_grant_rejected']=len(rejected)==3
    try:t.authorize_workflow({**request,'principal':{'user_id':'jin','team_id':'other_team'}},bound)
    except ContractError:checks['other_team_grant_rejected']=True
    checks['runtime_source_and_search_code_unchanged']=all(f['serving_files'][n]==h for n,h in b['manifest']['files'].items() if n not in ('00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','00_SYSTEM/PIPELINE.json') and not n.startswith('02_BACKEND/ENGINES/'))
finally:old_store.close();new_store.close()
receipt={'status':'complete','checks':checks,'counts':counts,'changed':changed,'risk_scope_before':len(before_scope),'risk_scope_after':len(after_scope),'candidate_code_root':f['code_root'],'model_calls':0}
put(A/'artifacts/run-001/metadata-integrity.json',receipt)
assert all(checks.values()),checks
print(json.dumps(receipt,ensure_ascii=False))
