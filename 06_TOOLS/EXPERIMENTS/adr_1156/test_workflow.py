from copy import deepcopy
import json,sqlite3,io,threading
from types import SimpleNamespace
import pytest
from semantic_runtime.ontology_work import schema
from semantic_runtime.ontology_work.store import LocalFolderStore,DataikuFolderStore
from semantic_runtime.ontology_work.repository import Repository,ddl,TABLES,COLUMNS
from semantic_runtime.ontology_work.workflow import Workflow
from semantic_runtime.legal_agent import ontology_context as oc,ontology_scenarios as sc
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.contracts import digest


def fixture():
    original={'id':'S1','anchor':{'document_id':'d','version':'v1','unit_id':'1','label':'합성 제1조','content_sha256':oc.compiler.content_hash('대상 거래는 10%를 산정한다. 다만 제외 거래는 적용하지 않는다.')},'text':'대상 거래는 10%를 산정한다. 다만 제외 거래는 적용하지 않는다.'}
    work={'version':schema.VERSION,'concept':'합성 산정','originals':[original],
        'judgments':[{'id':'J1','source_ids':['S1'],'judgment':{'finding':'일반 산정과 제외 확인'},'origin':{'run_id':'synthetic'}}],'origin':{'run_id':'synthetic'}}
    proposal={'components':[{'id':'C','text':'대상 거래인지 확인한다.','requires':[],'basis':[{'source':'S1','quote':'대상 거래'}]},
       {'id':'R','text':'10%를 산정한다.','requires':['C'],'basis':[{'source':'S1','quote':'10%를 산정한다.'}]},
       {'id':'X','text':'제외 거래는 적용하지 않는다.','requires':[],'basis':[{'source':'S1','quote':'제외 거래는 적용하지 않는다.'}]}],
       'paths':[{'id':'NORMAL','title':'일반 산정','business_use':'일반 산정 기준','conditions':['C'],'calculations':[],'outcomes':['R'],'notes':[]},
                {'id':'EXCEPTION','title':'제외','business_use':'제외 거래','conditions':['X'],'calculations':[],'outcomes':['X'],'notes':[]}], 'unused_components':{}}
    return work,proposal

def setup(tmp_path):
    path=tmp_path/'ontology.sqlite';repo=Repository(lambda:sqlite3.connect(path,timeout=5));repo.initialize();work,proposal=fixture()
    current={digest(s['anchor']):s['text'] for s in work['originals']}
    w=Workflow(repo,LocalFolderStore(tmp_path/'work'),actor='reviewer',source_reader=lambda a:current.get(digest(a)))
    return w,work,proposal,current

def approve(w,work,p,bid='cb-test'):
    row=w.save(work,p,bundle_id=bid);w.review(bid,row['revision'],row['work_hash'],True,'원문 조건·산정·제외 확인');return row

def publish(w,row):return w.publish(row['bundle_id'],row['revision'],row['work_hash'],w.repo.head(row['bundle_id'])['sequence'])

def test_full_lifecycle(tmp_path):
    w,work,p,current=setup(tmp_path);queued=w.enqueue(work);assert queued['status']=='INPUT'
    assert w.enqueue(work)['reused'];assert not w.repo.lookup(work['originals'][0]['anchor'],{'d'})
    calls=[]
    def generate(prompt,context,shape):calls.append(context);return p,{'id':'mock-model'}
    w.generate=generate;row=w.propose(work,bundle_id=queued['bundle_id'],expected_revision=1)
    assert row['revision']==2 and len(calls)==1
    package=w.preview(row['bundle_id']);assert len(package['paths'])==2
    assert not w.repo.lookup(work['originals'][0]['anchor'],{'d'})
    w.review(row['bundle_id'],2,row['work_hash'],True,'원문 검토')
    assert not w.repo.lookup(work['originals'][0]['anchor'],{'d'})
    receipt=publish(w,row);assert receipt['active']
    rows=w.repo.lookup(work['originals'][0]['anchor'],{'d'});assert len(rows)==1
    catalog=sc.bind_current(rows[0]['context']['scenario_package'],[dict(work['originals'][0],evidence_refs=['E1'])])
    assert len(catalog['paths'])==2 and catalog['runtime_compilation'] is False
    assert publish(w,row)['reused'] and w.repo.head(row['bundle_id'])['sequence']==1

@pytest.mark.parametrize('mutation',['hash','quote','cycle','missing','duplicate','judgment_source','unused'])
def test_invalid_draft(tmp_path,mutation):
    w,work,p,_=setup(tmp_path)
    if mutation=='hash':work['originals'][0]['text']+='changed'
    if mutation=='quote':p['components'][0]['basis'][0]['quote']='없는 인용'
    if mutation=='cycle':p['components'][0]['requires']=['R']
    if mutation=='missing':p['components'][0]['requires']=['MISSING']
    if mutation=='duplicate':p['components'].append(deepcopy(p['components'][0]))
    if mutation=='judgment_source':work['judgments'][0]['source_ids']=['unknown']
    if mutation=='unused':p['unused_components']={'C':'unused'}
    with pytest.raises(Exception):w.save(work,p)
    assert not w.repo.list()

def test_stale_revision_and_reapproval(tmp_path):
    w,work,p,_=setup(tmp_path);row=approve(w,work,p);receipt=publish(w,row)
    p['paths'][0]['title']='수정';new=w.save(work,p,bundle_id='cb-test',expected_revision=1)
    assert w.repo.head('cb-test')['publication_id']==receipt['publication_id']
    with pytest.raises(ContractError):w.review('cb-test',1,row['work_hash'],True,'old')
    with pytest.raises(ContractError):publish(w,new)
    with pytest.raises(ContractError):w.save(work,p,bundle_id='cb-test',expected_revision=1)
    w.review('cb-test',2,new['work_hash'],False,'반려');assert w.repo.latest('cb-test')['status']=='REJECTED'
    assert w.repo.head('cb-test')['publication_id']==receipt['publication_id']

def test_source_change_after_approval(tmp_path):
    w,work,p,current=setup(tmp_path);row=approve(w,work,p);current.clear()
    with pytest.raises(ContractError):publish(w,row)
    assert w.repo.head('cb-test')['publication_id'] is None

def test_acl_version_withdraw_and_reconcile(tmp_path):
    w,work,p,_=setup(tmp_path);row=approve(w,work,p);receipt=publish(w,row);a=work['originals'][0]['anchor']
    assert not w.repo.lookup(a,set());assert not w.repo.lookup({**a,'version':'v2'},{'d'})
    w.repo.activate('cb-test',None,1,'reviewer');assert not w.repo.lookup(a,{'d'})
    replay=publish(w,row);assert replay['reused'] and not replay['active']
    with pytest.raises(ContractError):w.repo.activate('cb-test',receipt['publication_id'],1,'reviewer')
    w.repo.activate('cb-test',receipt['publication_id'],2,'reviewer');assert w.repo.lookup(a,{'d'})

def test_atomic_publish_rollback(tmp_path,monkeypatch):
    w,work,p,_=setup(tmp_path);row=approve(w,work,p);event=w.repo.event
    def fail(c,bid,rev,action,*args,**kw):
        if action=='PUBLISHED':raise RuntimeError('injected before commit')
        return event(c,bid,rev,action,*args,**kw)
    monkeypatch.setattr(w.repo,'event',fail)
    with pytest.raises(RuntimeError):publish(w,row)
    assert not w.repo.lookup(work['originals'][0]['anchor'],{'d'})
    with w.repo.session() as c:assert c.execute('SELECT COUNT(*) FROM LGL_ONT_PUB_A').fetchone()[0]==0

class Folder:
    data={}
    def __init__(self):self.data={}
    def upload_stream(self,k,stream):self.data[k]=stream.read()
    def get_download_stream(self,k):return io.BytesIO(self.data[k])

def test_content_stores(tmp_path):
    f=Folder()
    for store in (LocalFolderStore(tmp_path),DataikuFolderStore(f)):
        key=store.put({'한글':['내용']});assert store.put({'한글':['내용']})==key
        assert store.get(key)=={'한글':['내용']}
        with pytest.raises(ContractError):store.get('../../escape')
    key=next(iter(f.data));f.data[key]=b'{}'
    with pytest.raises(ContractError):DataikuFolderStore(f).get(key.split('/')[-1][:-5])

@pytest.mark.parametrize('kind',['repair','twice_invalid','transport'])
def test_generation_bounded(tmp_path,kind):
    w,work,p,_=setup(tmp_path);calls=[]
    def generate(*args):
        calls.append(1)
        if kind=='transport':raise TimeoutError('unknown outcome')
        if len(calls)==1 or kind=='twice_invalid':return {},{'id':'model'}
        return p,{'id':'model'}
    w.generate=generate
    if kind=='repair':assert w.propose(work)['status']=='DRAFT'
    else:
        with pytest.raises(Exception):w.propose(work)
    assert len(calls)==(1 if kind=='transport' else 2)
    assert len(list((tmp_path/'work/objects').glob('*.json')))>=2

def test_multiple_bundle_catalog(tmp_path):
    from semantic_runtime.legal_agent.ontology_scenario_runtime import catalog_from
    w,work,p,_=setup(tmp_path);cards=[]
    for bid in ['cb-one','cb-two']:
        row=approve(w,work,p,bid);publish(w,row)
    for row in w.repo.lookup(work['originals'][0]['anchor'],{'d'}):
        cards.append({'payload':{'scenario_catalog':sc.bind_current(row['context']['scenario_package'],[dict(work['originals'][0],evidence_refs=['E1'])])}})
    c=catalog_from({'ontology_bundles':cards});assert len(c['paths'])==4
    assert len({x['id'] for x in c['paths']})==4
    assert {x['body'] for x in c['paths']}=={x['body'] for x in cards[0]['payload']['scenario_catalog']['paths']}

def test_schema_shipped_and_db_mode():
    assert oc.compiler._validator().schema['$id']=='ontology-bundle-v0.schema.json'
    assert oc.configuration({'mode':'DB'})=={'mode':'DB'}
    assert not oc.enabled({'ontology_enabled':False,'ontology_context':{'mode':'DB'}})
    for t in TABLES.values():assert len(t.encode())<=30
    for cols in COLUMNS.values():assert all(len(c[0].encode())<=30 for c in cols)
    assert all('SIDDA.' in stmt for stmt in ddl())

def test_operator_source_and_env_config(tmp_path,monkeypatch):
    from semantic_runtime.ontology_work.configuration import workflow
    w,work,p,_=setup(tmp_path)
    raw=tmp_path/'source.sqlite'
    with sqlite3.connect(raw) as db:
        db.execute('CREATE TABLE document(document_id TEXT,source_artifact_sha256 TEXT)');db.execute("INSERT INTO document VALUES ('d','v1')")
        db.execute('CREATE TABLE source_block(document_id TEXT,unit_id TEXT,block_id TEXT,text TEXT)');db.execute('INSERT INTO source_block VALUES (?,?,?,?)',('d','1','1',work['originals'][0]['text']))
    cfg={'version':'ontology-connection-v1','environment':'local','database':{'kind':'sqlite-local','path':str(tmp_path/'ontology.sqlite')},'source':{'kind':'sqlite-local','path':str(raw)},'work_store':{'kind':'local','path':str(tmp_path/'work')},'operators':{'reviewer':{'document_ids':['d']}}}
    path=tmp_path/'settings.json';path.write_text(json.dumps(cfg));monkeypatch.setenv('GENOS_RAG_ONTOLOGY_CONFIG',str(path))
    with pytest.raises(ContractError):workflow(actor='stranger')
    assert workflow(actor='reviewer').save(work,p)['status']=='DRAFT'
