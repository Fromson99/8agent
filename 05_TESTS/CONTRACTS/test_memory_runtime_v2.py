import copy
import importlib.util
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import corrected_memory as m, memory_methods, memory_identity, memory_rag

class Fake:
    binding={'generation':'SYNTHETIC'}
    def __init__(self):self.reenter=False;self.fails=None
    def catalogue(self,ids):return [{'id':d,'name':d} for d in ids]
    def verify(self,read):assert read['binding']==self.binding
    @contextmanager
    def open(self,*args):yield self
    def schema(self,stage):return {'type':'object'}
    def stage(self,stage,state,parts,*args):
        if stage==self.fails:raise m.MemoryError('injected failure')
        if stage=='READ':return {'binding':self.binding,'originals':[{'source_id':s,'text':'모의 원문'} for s in ('cited','adopted','read')]}
        if stage=='INTENT':return {'purpose':state['task'],'concepts':['보고 의무']}
        if stage=='SELECT':
            if self.reenter:
                self.reenter=False
                raise m.Reenter('RECALL','need additional originals',{'needs_fulltext':True,'final_ids':['cited']})
            return {'final_ids':['cited','adopted']}
        if stage=='ASSESS':return {'claims':[{'text':'조건부 판단','source_id':'cited','quote':'모의 원문'}],'limitations':[]}
        if stage=='COMPOSE':return {'text':'현재 판단',**parts['ASSESS']['payload']}
        return {'stage':stage}
class Wire:
    def __call__(self,system,data,schema,phase):
        if phase.startswith('memory-resolve-related'):return related_all(schema)
        if phase.startswith('memory-resolve'):return copy.deepcopy(self.command)
        if phase.endswith('check'):return {'valid':True,'reason':'synthetic contract response'}
        raise AssertionError(phase)
def related_all(schema):
    """Scripted related-question step: every earlier question judged related (the pre-selection behavior)."""
    return {'reason':'모의 선택',**{k:{'related':'YES','why':'모의: 이전 질문 전체'} for k in schema['properties'] if k!='reason'}}
def is_related(schema):
    import re
    props=set(schema.get('properties',{})) if isinstance(schema,dict) else set()
    return 'reason' in props and len(props)>1 and all(k=='reason' or re.fullmatch(r'q\d+',k) for k in props)
def fit(value,schema):
    """A scripted full command answered in the shape of the requested resolver step.

    The resolver asks method/target/reason first and the remaining fields second; a scripted
    provider returns only the requested properties, defaulting a missing one from its rule.
    """
    if is_related(schema):return related_all(schema)
    if not isinstance(value,dict) or not isinstance(schema,dict) or 'anyOf' in schema or 'properties' not in schema:return value
    defs=schema.get('$defs',{})
    def rule(r):
        while isinstance(r,dict) and '$ref' in r:r=defs[r['$ref'].split('/')[-1]]
        return r if isinstance(r,dict) else {}
    def default(r):
        r=rule(r)
        if 'const' in r:return r['const']
        if r.get('enum'):return r['enum'][0]
        if r.get('type')=='array':return []
        if r.get('type')=='object':return {k:default(v) for k,v in r.get('properties',{}).items()}
        if r.get('anyOf'):return default(r['anyOf'][0])
        return None
    return {k:(copy.deepcopy(value[k]) if k in value else default(r)) for k,r in schema['properties'].items()}
def command(method,**kw):
    value={'method_id':method,'document_scope_mode':'KEEP','target':None,'knowledge_id':None,'stage':'NONE','task':None,'source_category':'KEEP','document_ids':None,'facts':None,'queries':None,'restore_event':None,'restore_fields':[],'format':'prose','reason':'모의 계약',
           'search_scope_change':{'operation':'KEEP','targets':[],'user_quote':''},
           # Code that executes a pending (clarified) request expects the field; older code rejects it.
           **({'pending_request':None} if 'pending_request' in m.COMMAND['properties'] else {}),**kw}
    # Scripted current-model proposals use the current wire contract. Tests of
    # persisted legacy commands build those deliberately without these fields.
    value=copy.deepcopy(value)
    for target in value['search_scope_change']['targets']:target.setdefault('selection',None)
    return value
@pytest.fixture
def memory(tmp_path):
    f=Fake();w=Wire();mem=m.Memory(tmp_path/'memory.sqlite',f,w);n=0
    principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
    def send(c,session='s',**extra):
        nonlocal n
        n+=1;w.command=c
        return mem.execute({'question':'모의 요청','session_id':session,'request_id':'r'+str(n),**extra},principal)
    yield mem,f,w,send,principal
    mem.close()
def start(send):return send(command('CASE_START',task='보고 위임',facts=[]))
def test_no_automatic_knowledge_and_precise_source_edges(memory):
    db,f,w,send,p=memory;first=start(send)
    assert db.db.execute('SELECT count(*) FROM knowledge').fetchone()[0]==0
    kid=send(command('EXPERIENCE_CONFIRM',target=first['goal_id']))['knowledge_id']
    edges=list(db.db.execute('SELECT * FROM ontology_edge WHERE knowledge=?',(kid,)))
    assert sum(e['relation']=='READ_SOURCE' for e in edges)==3
    assert sum(e['relation']=='ADOPTED_SOURCE' for e in edges)==2
    assert sum(e['relation']=='CITED_SOURCE' for e in edges)==1
    supported=[e for e in edges if e['relation']=='SUPPORTED_BY']
    assert len(supported)==1 and supported[0]['source'].endswith(':CLAIM:0')
    assert db.export_wiki(p)['pages'][0]['source_ids']==['cited']
def test_recorrection_to_initial_and_preserved_presentation(memory):
    db,f,w,send,p=memory;first=start(send);gid=first['goal_id'];initial=db.events(gid)[0]['id']
    for value in ('A','B','C'):
        send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':value}]))
    result=send(command('STATE_RESTORE',target=gid,restore_event=initial,restore_fields=['facts']))
    assert result['state']['facts']==[]
    kid=send(command('EXPERIENCE_CONFIRM',target=gid))['knowledge_id']
    before=db.goal(gid,'s');history=send(command('HISTORY_EXPLAIN',target=gid))
    assert db.goal(gid,'s')==before
    assert history['history'][-1]['restore_event']==initial
    table=send(command('ANSWER_PRESENT',target=gid,format='table'))
    assert table['executed']==['COMPOSE']
    assert db.checked_knowledge(kid,p)
    send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'D'}]))
    assert not db.candidates(p,'보고')
    assert db.db.execute('SELECT status FROM knowledge WHERE id=?',(kid,)).fetchone()[0]=='RETIRED'
def test_additional_search_is_durable_and_supersedes_upstream(memory):
    db,f,w,send,p=memory;f.reenter=True;out=start(send)
    assert out['executed']==['INTENT','PLAN','RECALL','READ','RECALL','READ','SELECT','ASSESS','COMPOSE']
    assert db.db.execute("SELECT count(*) FROM event WHERE kind='RAG_REENTRY'").fetchone()[0]==1
    assert db.db.execute("SELECT count(*) FROM node WHERE stage='READ'").fetchone()[0]==2
    assert db.parts(out['goal_id'])['READ']['supersedes'] is not None
    assert db.route(out['goal_id'])['payload']['nodes']['READ']==db.parts(out['goal_id'])['READ']['id']
def test_failed_correction_retires_stale_knowledge_and_recovers(memory):
    db,f,w,send,p=memory;gid=start(send)['goal_id'];send(command('EXPERIENCE_CONFIRM',target=gid));f.fails='SELECT'
    with pytest.raises(m.MemoryError):send(command('RESEARCH_REENTER',target=gid,stage='SELECT'))
    assert db.goal(gid,'s')['status']=='PENDING' and db.route(gid) is None and db.candidates(p,'보고')==[]
    f.fails=None;out=send(command('RESEARCH_REENTER',target=gid,stage='COMPOSE'))
    assert out['executed']==['SELECT','ASSESS','COMPOSE']
def test_reuse_rebinds_nodes_and_isolation(memory):
    db,f,w,send,p=memory;first=start(send);gid=first['goal_id'];kid=send(command('EXPERIENCE_CONFIRM',target=gid))['knowledge_id']
    out=send(command('EXPERIENCE_REUSE',knowledge_id=kid,document_scope_mode='AUTHORIZED',**{**first['state'],'document_ids':None}),session='new')
    assert out['status']=='REUSED' and out['executed']==['COMPOSE']
    assert {db.db.execute('SELECT goal FROM node WHERE id=?',(n,)).fetchone()[0] for n in db.route(out['goal_id'])['payload']['nodes'].values()}=={out['goal_id']}
    assert db.candidates({**p,'user_id':'other'},'보고')==[]
    with pytest.raises(m.MemoryError):db.identity('s',{**p,'user_id':'other'})
def test_duplicate_id_and_revision_conflict(memory):
    db,f,w,send,p=memory;first=start(send)
    body={'question':'모의 요청','session_id':'s','request_id':'r1'}
    assert db.execute(body,p)==first
    with pytest.raises(m.Conflict):db.execute({**body,'question':'changed'},p)
    with pytest.raises(m.Conflict):send(command('ANSWER_PRESENT',target=first['goal_id']),expected_revision=99)
def test_legacy_database_is_not_silently_migrated(tmp_path):
    path=tmp_path/'legacy.sqlite';db=sqlite3.connect(path);db.execute('CREATE TABLE knowledge(id TEXT)');db.close()
    with pytest.raises(m.MemoryError,match='explicit migration'):m.Memory(path,Fake(),Wire())
@pytest.mark.parametrize('field,value',[('facts',[{'name':'x','value':'hidden'}]),('queries',['hidden']),('task','hidden')])
def test_read_only_methods_cannot_hide_mutations(memory,field,value):
    db,f,w,send,p=memory;gid=start(send)['goal_id'];before=db.goal(gid,'s')
    out=send(command('HISTORY_EXPLAIN',target=gid,**{field:value}))
    assert out['status']=='CLARIFY' and db.goal(gid,'s')==before

def session_body():
    return {'memory':True,'question':'public','user_id':'u','team_id':'risk_team','session_id':'s','request_id':'r'}

def test_unsigned_session_and_envelope_normalization():
    body=session_body()
    expected=memory_identity.validate_session(body)
    assert expected['user_id'].startswith('session:') and expected['team_id']=='risk_team'
    normalized={k:v for k,v in {'API_TYPE':'LEGAL_AGENT','channel':'genos-chat',**body}.items() if k not in ('API_TYPE','channel')}
    assert memory_identity.validate_session(normalized)==expected
    assert memory_identity.validate_session({k:v for k,v in body.items() if k!='user_id'})==expected

@pytest.mark.parametrize('field,value',[('team_id',None),('session_id','anonymous'),('request_id',''),('expected_revision',0)])
def test_unsigned_session_rejects_invalid_selectors(field,value):
    with pytest.raises(m.MemoryError):memory_identity.validate_session({**session_body(),field:value})

@pytest.mark.parametrize('key',['','obsolete-key'])
def test_signing_environment_has_no_runtime_dependency(monkeypatch,key):
    monkeypatch.setenv('GENOS_MEMORY_SIGNING_KEY',key)
    value=memory_identity.validate_session(session_body())
    assert value['team_id']=='risk_team' and value['user_id'].startswith('session:')

def test_native_selection_consumes_fallback(monkeypatch):
    source=S(force_fulltext_recall=False,profile={})
    native=memory_rag.NativeExecution(S(verify=lambda x:None,question=lambda x:'Q'),S(sources=source,work=S(event=lambda *x:None)),{}, {})
    monkeypatch.setattr(memory_rag,'select_sources',lambda *a,**k:{'final_ids':[], 'needs_fulltext':True})
    parts={'PLAN':{'payload':{'law_names':[],'queries':['Q']}},'READ':{'payload':{'record':{'discovery_mode':'structure'}}}}
    with pytest.raises(m.Reenter) as caught:native.stage('SELECT',{'facts':[]},parts,'Q','prose')
    assert caught.value.stage=='RECALL' and source.force_fulltext_recall
    with pytest.raises(m.MemoryError,match='remains unresolved'):native.stage('SELECT',{'facts':[]},parts,'Q','prose')

def test_model_calls_share_native_budget_and_cleanup():
    from semantic_runtime.legal_agent.memory_binding import RuntimeModel
    opened=[];closed=[];calls=[]
    @contextmanager
    def open_session(*args,**kwargs):
        opened.append(1)
        try:
            yield S(work=S(event=lambda *x:None),sources=S(source=S()),context=S(remaining=lambda:99),profile={'max_output_tokens':6400},
                    structured=lambda *x:calls.append(x) or {'ok':True})
        finally:closed.append(1)
    p=S(plan=lambda *a:{},term_agent=S(open_session=open_session))
    model=RuntimeModel(p,'runtime',{'question':'Q','request_id':'r','session_id':'s'}, {'document_ids':['d']})
    model.invoke('system',{}, {},'command');model.invoke('system',{}, {},'assess');model.close();model.close()
    assert len(opened)==len(closed)==1 and len(calls)==2
