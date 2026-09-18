import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest

from semantic_runtime import navigation_loop as n

@pytest.fixture
def session():
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE occurrence(term_id,source_id)');db.execute('CREATE TABLE reference(id,json)');db.execute('CREATE TABLE reference_end(source_id,reference_id)')
    terms={k:{'id':k,'label':k} for k in 'ABCD'}
    edges={k:[] for k in terms}
    for x,y in zip('ABC','BCD'):
        e={'id':x+y,'source':x,'target':y,'code':'related'};edges[x].append(e);edges[y].append(e)
    sources={f's{i:02}':{'id':f's{i:02}','document_id':'doc','document_name':'가상법','unit_id':str(i),'heading':f'제{i}조','text':f'원문{i} 조건과 예외입니다.','text_sha256':str(i),'source_artifact_sha256':'artifact','blocks':[]} for i in range(12)}
    for sid in sources:db.execute('insert into occurrence values (?,?)',('A',sid))
    db.execute('insert into occurrence values (?,?)',('D','s11'))
    t=SimpleNamespace(terms=terms,edges=edges,db=db,sources=sources,validate_scope=lambda scope:scope)
    units={('doc',str(i)):{'parent':None,'family':'kr_article','surface':f'제{i}조','title':'제목'} for i in range(12)}
    m=SimpleNamespace(sources=sources,documents={'doc':'가상법'},units=units,starts=lambda q,s:{'documents':[],'terms':[{'id':'A','question_spans':[]}],'structures':[{'id':'structure:doc:0','question_spans':[],'kind':'LOCATOR','document_id':'doc','family':'kr_article'}]},_unit_sources=lambda d,u:[f's{int(u):02}'])
    g=SimpleNamespace(connections=SimpleNamespace(_definitions=lambda s,node,end:[{'text':'정의'}]))
    v=n.NavigationSession(m,t,g,'질문',['doc']);v.issues={'Q1':'조건'}
    yield v
    db.close()

def test_metadata_does_not_read(session):
    assert not session.read_segments
    r=session.listing(['A']);assert r['total']==12 and r['next_offset']==8
    assert all('text' not in x for x in r['items'])
    assert not session.delivered

def test_page_past_eight_and_intersection(session):
    r=session.listing(['A'],offset=8);assert len(r['items'])==4
    session.graph('A',3,0)
    assert session.listing(['A','D'],match='all')['items'][0]['id']=='s11'

def test_three_hops_actual_edges(session):
    r=session.graph('A',3,0);assert r['items'][-1]['path']==['AB','BC','CD']
    assert 'D' in session.known_terms

def test_open_definition_no_source_search(session):
    assert session.definitions('A',0)['source_search_executed'] is False
    assert not session.known_sources and not session.read_segments

def test_cannot_adopt_unread_or_undelivered(session):
    session.listing(['A']);s=session.read('s00')
    with pytest.raises(ValueError):session.judge(s['id'],'adopted','Q1',s['text'],'claim')
    session.context();session.delivered.update(session.active);assert s['id'] in session.delivered
    with pytest.raises(ValueError):session.judge(s['id'],'adopted','Q1','捏造','claim')

def test_exclude_reopen_revise(session):
    session.listing(['A']);s=session.read('s00');session.context();session.delivered.update(session.active)
    session.judge(s['id'],'excluded','Q1');assert not session.active
    session.read('s00');session.context();session.delivered.update(session.active);session.judge(s['id'],'adopted','Q1',s['text'],'조건 확인')
    assert len(session.judgments)==1 and next(iter(session.judgments.values()))['status']=='adopted'

def test_read_more_than_eight_over_time(session):
    session.listing(['A']);session.listing(['A'],offset=8)
    for i in range(12):
        s=session.read(f's{i:02}');session.context();session.delivered.update(session.active);session.judge(s['id'],'deferred','Q1')
    assert len(session.delivered)==12 and not session.active

def test_active_capacity_independent(session):
    session.listing(['A']);session.listing(['A'],offset=8)
    for i in range(6):session.read(f's{i:02}')
    with pytest.raises(ValueError):session.read('s06')
    session.context();session.delivered.update(session.active);session.judge(next(iter(session.active)),'excluded','Q1');session.read('s06')

def test_scope_and_ids(session):
    with pytest.raises(ValueError):session.listing(['A'],document_id='private')
    with pytest.raises(ValueError):session.read('s11')
    with pytest.raises(ValueError):session.graph('D',2,0)
    with pytest.raises(ValueError):session.listing([],structure_id='structure:private:1')

def test_sufficient_requires_coverage(session):
    with pytest.raises(ValueError):session.execute('STOP',{'status':'sufficient','unresolved':[]})
    session.listing(['A']);s=session.read('s00');session.context();session.delivered.update(session.active);session.judge(s['id'],'adopted','Q1',s['text'],'확인')
    assert session.execute('STOP',{'status':'sufficient','unresolved':[]})['status']=='sufficient'

def test_references_require_read(session):
    with pytest.raises(ValueError):session.references('s00')
    session.listing(['A']);session.read('s00');session.context();session.delivered.update(session.active)
    assert session.references('s00')['total']==0

def test_budget_reports_incomplete(session):
    session.limits['max_calls']=1
    class Provider:
        def call(self,*args):return {'issues':[],'actions':[{'tool':'LIST','args':json.dumps({'term_ids':['A']}),'reason':'조건 확인'}]},{}
    r=session.run(Provider());assert r['status']=='STOP' and r['calls']==1
    assert not r['adopted'] and r['stop']['unresolved']

def test_context_memory_and_rejection(session):
    class Provider:
        def __init__(self):self.i=0
        def call(self,role,system,data,schema):
            self.i+=1
            if self.i==1:a={'tool':'LIST','args':json.dumps({'term_ids':['A']}),'reason':'첫 탐색'}
            else:
                assert data['history_summary'][0]['reason']=='첫 탐색'
                a={'tool':'STOP','args':json.dumps({'status':'incomplete','unresolved':['근거 부족']}),'reason':'종료'}
            return {'issues':[],'actions':[a]},{}
    r=session.run(Provider());assert r['calls']==2 and len(r['trace'])==2


def test_compact_schema_and_local_id_guard(session):
    schema=session.response_schema()['properties']['actions']['items']['properties']
    assert schema['args']['type']=='string'
    session.listing(['A'])
    with pytest.raises(ValueError):session.read('doc')

def test_title_and_locator_same_unit_preserved():
    p=Path(n.__file__).with_name('navigation_match.py')
    spec=importlib.util.spec_from_file_location('match432',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    db=sqlite3.connect(':memory:');db.execute('create table label(key,source,node_id)')
    matcher=m.ReverseMatcher.__new__(m.ReverseMatcher)
    matcher.tools=SimpleNamespace(validate_scope=lambda x:x,terms={})
    matcher.glossary=SimpleNamespace(dbs={'lookup':db});matcher.documents={'doc':'가상법'}
    matcher.document_context={}
    matcher.document_names=m.SurfaceIndex();matcher.document_names.add('가상법','doc')
    matcher.structures=m.SurfaceIndex();matcher.body=m.SurfaceIndex()
    for text,kind in [('적용범위','TITLE'),('제26조','LOCATOR')]:
        matcher.structures.add(text,{'document_id':'doc','unit_id':'282','kind':kind,'family':'kr_article'})
    result=matcher.starts('적용범위 가상법 제26조',['doc'])
    assert result['structures'][0]['kind']=='LOCATOR'
    assert len(result['structures'][0]['question_spans'])==2
    db.close()


def test_unique_structure_read_is_explicit_choice(session):
    s=session.read('structure:doc:0')
    assert s['source_id']=='s00' and s['selected_structure_id']=='structure:doc:0'
    assert not session.delivered

def test_multiple_structure_sources_require_selection(session):
    session.m._unit_sources=lambda d,u:['s00','s01']
    result=session.read('structure:doc:0')
    assert result['status']=='CHOOSE_SOURCE' and not session.read_segments

def test_wire_alias_roundtrip_and_original_text(session):
    session.listing(['A']);s=session.read('s00');session.context()
    data=session.wire({'source_id':'s00','segment_id':s['id'],'text':'s00','quote':'A1'})
    assert data['source_id'].startswith('A') and data['segment_id'].startswith('E')
    assert data['text']=='s00' and data['quote']=='A1'
    assert session.wire(data,decode=True)['source_id']=='s00'
    action={'args':json.dumps({'source_id':data['source_id']})}
    assert json.loads(session.wire(action,decode=True)['args'])['source_id']=='s00'


def test_graph_read_exclude_reopen_adopt_loop(session):
    class ScriptedProvider:
        def __init__(self):self.turn=0;self.source=None;self.segment=None
        def call(self,role,system,data,schema):
            self.turn+=1
            if self.turn==1:
                tool,args='GRAPH',{'term_id':data['initial']['terms']['items'][0]['id'],'hops':3}
            elif self.turn==2:
                target=data['last_results'][0]['result']['items'][-1]['to']['id']
                tool,args='LIST',{'term_ids':[target]}
            elif self.turn==3:
                self.source=data['last_results'][0]['result']['items'][0]['id']
                tool,args='READ',{'source_id':self.source}
            elif self.turn==4:
                self.segment=data['active_segments'][0]
                tool,args='JUDGE',{'segment_id':self.segment['id'],'status':'excluded','issue_id':'Q1','quote':'','claim':''}
            elif self.turn==5:
                assert not data['active_segments']
                assert data['judgments'][0]['status']=='excluded'
                assert any(h['tool']=='GRAPH' for h in data['history_summary'])
                tool,args='READ',{'source_id':self.source}
            else:
                segment=data['active_segments'][0]
                actions=[{'tool':'JUDGE','args':json.dumps({'segment_id':segment['id'],'status':'adopted','issue_id':'Q1','quote':segment['text'],'claim':'재검토한 원문에 조건과 예외가 있다.'}),'reason':'동일 원문 재검토 후 판단 수정'},
                         {'tool':'STOP','args':json.dumps({'status':'sufficient','unresolved':[]}),'reason':'질문 항목에 원문 근거 확보'}]
                return {'issues':[],'actions':actions},{}
            return {'issues':[],'actions':[{'tool':tool,'args':json.dumps(args),'reason':'조건 확인을 위한 경로 선택·재검토'}]},{}
    result=session.run(ScriptedProvider())
    assert result['status']=='FINISH' and result['calls']==6 and result['failure'] is None
    assert result['read_source_ids']==['s11']
    assert len(result['adopted'])==1
    assert [r['result']['status'] for r in result['trace'] if r['tool']=='JUDGE']==['excluded','adopted']
    assert all(r['status']=='OK' for r in result['trace'])

def test_wire_decodes_only_id_fields_so_issue_ids_survive(session):
    session.listing(['A']);session.context();session.wire({})
    alias=session.aliases['s00']
    out=session.wire({'issues':[{'id':alias,'text':'보관 기간'}],
                      'actions':[{'tool':'JUDGE','args':json.dumps({'segment_id':'E9','issue_id':alias,'status':'excluded','quote':'','claim':''}),'reason':'r'}]},decode=True)
    assert out['issues'][0]['id']==alias
    assert json.loads(out['actions'][0]['args'])['issue_id']==alias
    assert json.loads(session.wire({'args':json.dumps({'term_ids':[session.aliases['A']],'source_id':alias})},decode=True)['args'])=={'term_ids':['A'],'source_id':'s00'}

def test_alias_shaped_issue_id_is_rejected_without_ending_session(session):
    class Provider:
        def __init__(self):self.rounds=0
        def call(self,*args):
            self.rounds+=1
            if self.rounds==1:return {'issues':[{'id':'A7','text':'보관 기간'}],'actions':[{'tool':'HISTORY','args':'{}','reason':'이력 확인'}]},{}
            return {'issues':[],'actions':[{'tool':'STOP','args':json.dumps({'status':'incomplete','unresolved':['근거 없음']}),'reason':'종료'}]},{}
    state=session.run(Provider())
    assert state['failure'] is None and 'A7' not in state['issues']
    rejected=[x for x in state['trace'] if x['tool']=='ISSUES']
    assert rejected and rejected[0]['status']=='REJECTED' and 'Q1-style' in rejected[0]['error']
