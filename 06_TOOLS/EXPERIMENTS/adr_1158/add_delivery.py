from common import *
import sys,ast
D=S/'08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1';D.mkdir(parents=True,exist_ok=True)
(D/'ingest_agent_events.py').write_text('''"""Dataiku Python recipe: existing agent events → S3 work JSON and input queue.
Never approves, publishes, calls GENOS or accesses S3 from GENOS.
"""
import json,os

def ingest(rows,workflow):
    receipts=[]
    for row in rows:
        if row.get('kind')!='ONTOLOGY_WORK_INPUT':continue
        payload=row.get('payload_json',row.get('payload'))
        if isinstance(payload,str):payload=json.loads(payload)
        from semantic_runtime.contracts import digest
        if payload['input_hash']!=digest(payload['input']):raise ValueError('agent work input hash mismatch')
        receipts.append(workflow.enqueue(payload['input']))
    return receipts

def main():
    import dataiku
    from semantic_runtime.ontology_work.configuration import workflow
    variables=dataiku.get_custom_variables()
    config=variables['ontology_connection_config_path']
    os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=config
    actor=dataiku.api_client().get_auth_info(with_secrets=False)['authIdentifier']
    work=workflow(actor=actor)
    dataset=dataiku.Dataset(variables['ontology_agent_event_dataset'])
    # The upstream dataset is the existing authorized agent-event export. Rows are
    # iterated, never loading full logs into a dataframe. Repeat runs deduplicate.
    receipts=ingest(dataset.iter_rows(),work)
    result={'version':'ontology-input-receipts-v1','rows':receipts}
    work.store.put(result)
    return {'queued':len(receipts)}

if __name__=='__main__':print(json.dumps(main(),ensure_ascii=False))
''')
# Runtime DDL comes from one mapping contract; no handwritten shadow layout.
sys.dont_write_bytecode=True;sys.path.insert(0,str(S/'02_BACKEND'))
from semantic_runtime.ontology_work.repository import ddl,TABLES,COLUMNS
(D/'01_CREATE_TABLES.sql').write_text('-- Development SIDDA agent layer. Metadata/DBA approval is separate. No DROP or data migration.\n'+';\n\n'.join(ddl())+';\n')
put(D/'connection.example.json',{'version':'ontology-connection-v1','environment':'dataiku','database':{'kind':'oracle','owner':'SIDDA','dsn_env':'ONTOLOGY_ORACLE_DSN','user_env':'ONTOLOGY_ORACLE_USER','password_env':'ONTOLOGY_ORACLE_PASSWORD'},'source':{'kind':'oracle-silver','owner':'SIDDS','dataset_version':'REPLACE_WITH_PUBLISHED_DATASET_VERSION'},'work_store':{'kind':'dataiku','folder_id':'REPLACE_WITH_ONTOLOGY_WORK_FOLDER'},'operators':{},'model':{'kind':'genos'}})
import csv,io
buf=io.StringIO();writer=csv.writer(buf);writer.writerow(['에이전트번호','개발스키마','테이블명','컬럼순번','물리명','논리명','Oracle타입','NULL','PK','표준용어·도메인·인포타입','메타신청','DBA생성','운영골드후보'])
from semantic_runtime.ontology_work.repository import PK
for key,table in TABLES.items():
 for i,(name,typ,label) in enumerate(COLUMNS[key],1):
  nullable=name in ('RVWR_ID','APRV_HASH_VAL','PUB_ID') and key in ('work','head')
  writer.writerow(['A1(프로젝트 식별자;메타 과제번호 별도)','SIDDA',table,i,name,label,typ,'Y' if nullable else 'N','Y' if name in PK[key].split(',') else 'N','명명 후보·표준사전 대조/신청 필요','미신청','미신청','검토 대상' if key in ('publication','head','anchor') else '에이전트 운영기록'])
(D/'TABLE_COLUMNS.csv').write_text('\ufeff'+buf.getvalue())
for p in D.iterdir():
 n=str(p.relative_to(S));sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
 ac.register_file(CAND,n,upstream_state='absent' if not (ROOT/n).exists() else 'present')
# Add transport/state/capture and recipe tests before freezing.
p=Path(__file__).parent/'test_database_native.py';s=p.read_text();s=s.replace("    fallback=mode in", "    if mode=='normal':monkeypatch.setenv('GENOS_ONTOLOGY_CAPTURE_ENABLED','on')\n    fallback=mode in",1)
# Persisted journal capture is the real producer for the Dataiku recipe.
s=s.replace("        catalogs=[v for v in t.views",'''        if mode=='normal':
            captured=[];failed=[]
            for dbpath in tmp_path.rglob('*.sqlite'):
                with sqlite3.connect(dbpath) as db:
                    columns=[r[1] for r in db.execute("PRAGMA table_info(event)")]
                    if 'payload_json' not in columns:continue
                    captured.extend(json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='ONTOLOGY_WORK_INPUT'"))
                    failed.extend(json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='ONTOLOGY_WORK_CAPTURE_UNAVAILABLE'"))
            assert captured,failed
            assert all(x['authority']=='CANDIDATE_INPUT_ONLY' and not x['automatic_approval'] for x in captured)
        catalogs=[v for v in t.views''')
p.write_text(s)
p=Path(__file__).parent/'test_workflow.py';s=p.read_text()+'''

def test_unknown_commit_reconciles_and_new_revision_requires_review(tmp_path):
    w,work,p,_=setup(tmp_path);row=approve(w,work,p)
    original=w.repo.connect
    class LoseAck:
        def __init__(self):self.db=original()
        def cursor(self):return self.db.cursor()
        def commit(self):self.db.commit();raise TimeoutError('commit acknowledgement lost')
        def rollback(self):self.db.rollback()
        def close(self):self.db.close()
    w.repo.connect=LoseAck
    with pytest.raises(TimeoutError):publish(w,row)
    w.repo.connect=original
    assert w.repo.head('cb-test')['publication_id']
    receipt=publish(w,row);assert receipt['reused'] and receipt['active']
    assert w.repo.head('cb-test')['sequence']==1


def test_recipe_ingest_deduplicates_and_never_approves(tmp_path):
    import importlib.util,os
    from pathlib import Path
    path=Path(os.environ['QUALIFICATION_CODE_ROOT'])/'08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/ingest_agent_events.py'
    spec=importlib.util.spec_from_file_location('ontology_ingest',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    w,work,p,_=setup(tmp_path)
    row={'kind':'ONTOLOGY_WORK_INPUT','payload_json':json.dumps({'input':work,'input_hash':digest(work)})}
    first=mod.ingest([row],w);second=mod.ingest([row],w)
    assert first[0]['status']=='INPUT' and second[0]['reused']
    assert not w.repo.lookup(work['originals'][0]['anchor'],{'d'})


def test_database_runtime_unavailable_is_persisted_once(tmp_path,monkeypatch):
    from semantic_runtime.ontology_work import runtime
    w,work,p,_=setup(tmp_path)
    source=sqlite3.connect(':memory:');source.execute('CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT)');source.execute("INSERT INTO source_block VALUES ('d','0','1')")
    calls=[];events=[]
    class Broken:
        def lookup(self,*args):calls.append(1);raise TimeoutError('DB down')
    monkeypatch.setattr(runtime,'repository',lambda:Broken())
    session=SimpleNamespace(scope={'d'},tools=SimpleNamespace(sources={'s':{'source_artifact_sha256':'v1'}}),
        store=SimpleNamespace(db=source),matcher=SimpleNamespace(units={('d','1'): {}}),repo=SimpleNamespace(event=lambda *x:events.append(x)))
    inv=SimpleNamespace(policy={'ontology_enabled':True,'ontology_context':{'mode':'DB'}},p={'binding':'binding','selected':{'B1':{'source_id':'s','document_id':'d','offer':{'block_ids':['0']}}}},s=session,save=lambda:None)
    assert not runtime.acquire(inv,['B1'],None)['snapshot']['bundles']
    runtime.acquire(inv,['B1'],None);assert len(calls)==1
    assert next(iter(inv.p['ontology_database']['lookups'].values()))['status']=='UNAVAILABLE'
    assert events[0][0]=='ONTOLOGY_DATABASE_UNAVAILABLE'
''';p.write_text(s)
print('Dataiku recipe, DDL, columns and extra consumer checks prepared')
