"""Behavioral contracts: explicit gaps, scoped references and independent roots."""
import json
import sqlite3
from types import SimpleNamespace
import pytest
from test_provision_references import SCHEMA, article, frame, build
from semantic_runtime.term_references import compile_references
from semantic_runtime.reference_exploration import ReferenceNavigator

def db_new():
    db=sqlite3.connect(':memory:');db.executescript(SCHEMA)
    return db

def add(db,sid,number,text):
    article(db,sid,'d','모의규정',f'제{number}조',f'u{number}',[(str(number*100),f'제{number}조 '+text)],[])

def navigator(db):
    compile_references(db)
    sources={sid:json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')}
    return ReferenceNavigator(db,sources,{'d'},'fixture-binding')

def roots(nav,*sids):
    return [nav.root(s,query='원질문',reason='독립 검색에서 선택') for s in sids]

def test_missing_provision_is_inspection_only():
    r=build()[('k5','제4조제9항')]
    assert not r['target_source_ids'] and not r['targets']
    assert r['inspection_targets'][0]['source_id']=='k4'
    assert r['coordinate_status']=='ARTICLE_ONLY'

def test_gap_does_not_recurse_or_open_reverse():
    db=db_new();add(db,'a',1,'제2조제9항에 따른다.');add(db,'b',2,'제3조를 준용한다.');add(db,'c',3,'끝')
    nav=navigator(db);w=nav.walk(roots(nav,'a'))
    assert w['source_ids']==['a'] and len(w['gaps'])==1
    assert w['gaps'][0]['targets'][0]['source_id']=='b'
    assert list(nav.neighbors(nav.extent('b'),'incoming'))==[]

def test_no_similar_name_reference():
    db=db_new();add(db,'a',1,'모의규정과 비슷한 용어를 검토한다.');add(db,'b',2,'모의규정과 비슷한 용어다.')
    nav=navigator(db)
    assert nav.walk(roots(nav,'a'))['source_ids']==['a']

def test_recursive_reverse_and_forward_and_independent_new_root():
    db=db_new()
    add(db,'a',1,'제2조를 준용한다.');add(db,'b',2,'종료')
    add(db,'c',3,'제1조 및 제4조를 준용한다.');add(db,'d',4,'종료')
    add(db,'e',5,'제3조를 준용한다.');add(db,'f',6,'제2조를 준용한다.')
    nav=navigator(db);w=nav.walk(roots(nav,'a'))
    assert set(w['source_ids'])=={'a','b','c','d','e','f'}
    assert set(nav.walk(roots(nav,'a','b'))['source_ids'])=={'a','b','c','d','e','f'}
    assert all(e['witness']['span_hash'] for e in w['edges'])

def test_item10_never_leaks_to_item39_and_deepest_reverse_extent():
    db=db_new();frame(db,'d',[['kr_article'],['circled'],['dot'],['hangul_dot']])
    add(db,'a',1,'제2조제1항제10호에 따른다.')
    article(db,'b','d','모의규정','제2조','u2',
        [('200','제2조'),('201','① 정의'),('210','10. 제3조에 따른다.'),('239','39. 제4조에 따른다.')],
        [('u21','u2',[1],'①',['201'],'circled'),('u210','u21',[10],'10.',['210'],'dot'),('u239','u21',[39],'39.',['239'],'dot')])
    add(db,'c',3,'종료');add(db,'d',4,'종료')
    nav=navigator(db);w=nav.walk(roots(nav,'a'))
    assert set(w['source_ids'])=={'a','b','c'}
    assert any(s['extent']['block_ids']==['210'] for s in w['states'] if s['extent']['source_id']=='b')
    incoming=list(nav.neighbors(nav.extent('c'),'incoming'))
    assert incoming[0]['targets'][0]['block_ids']==['210']

def test_title_inside_supplement_is_not_main_body_reference():
    db=db_new();add(db,'a',1,'목적');add(db,'b',2,'기준')
    article(db,'supp','d','모의규정','부칙','us',
        [('900','부칙'),('901','제1조(시행일) 제2조를 적용한다.')],
        [('us1','us',[1],'제1조',['901'],'kr_article')])
    nav=navigator(db)
    refs=list(nav.neighbors(nav.extent('supp'),'outgoing'))
    assert len(refs)==1 and refs[0]['targets'][0]['source_id']=='b'

def test_body_block_start_is_still_a_citation():
    db=db_new();add(db,'b',2,'목적')
    article(db,'a','d','모의규정','제1조','u1',[('100','제1조'),('101','제2조를 준용한다.')],[])
    nav=navigator(db)
    assert len(list(nav.neighbors(nav.extent('a'),'outgoing')))==1

def test_cycle_shared_owner_and_budget_pending():
    db=db_new();add(db,'a',1,'제2조를 준용한다.');add(db,'b',2,'제1조를 준용한다.')
    nav=navigator(db);rs=roots(nav,'a','b');w=nav.walk(rs)
    assert w['status']=='COMPLETE' and len(w['states'])<=6
    assert len(w['owners']['b'])==2
    assert nav.walk(rs[1:])['owners']['b']==[rs[1]['root_id']]
    partial=nav.walk(rs,max_states=1)
    assert partial['status']=='PARTIAL' and partial['pending']

def test_witness_tampering_rejected():
    db=db_new();add(db,'a',1,'제2조에 따른다.');add(db,'b',2,'기준');nav=navigator(db)
    row=json.loads(db.execute('SELECT json FROM reference').fetchone()[0]);row['source_text_sha256']='wrong'
    db.execute('UPDATE reference SET json=?',(json.dumps(row),))
    with pytest.raises(ValueError,match='witness'):nav.walk(roots(nav,'a'))

from conftest import term_glossary
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session
from test_tool_exploration_v3 import read, tool

def test_workflow_read_and_new_search_receipts(tmp_path,generation):
    with session(tmp_path,generation) as s:
        result=read(s)
        assert result['status'] in ('OK','PARTIAL')
        assert result['exploration_origin']['route_class']=='SEARCH_ROOT'
        assert result['exploration_origin']['read_reason']
        discovered=s.work.db.execute("SELECT count(*) FROM event WHERE kind='SEARCH_ROOTS_DISCOVERED'").fetchone()[0]
        assert discovered>=1
        bad=s.sources.execute(tool('read',target=s.sources.root,extent='self',cursor=None),'bad')
        assert bad['status']=='NOT_EXECUTED'
        assert not [r for r in s.sources.action_summaries() if r['status']=='ERROR']

def test_linked_full_article_read_keeps_scope_and_all_family_direction():
    from semantic_runtime.legal_agent.workflow_relation_cards import RelationCards
    from semantic_runtime.legal_agent.workflow_relations_tools import RelationsTools
    db=db_new();frame(db,'d',[['kr_article'],['circled'],['dot']])
    article(db,'a','d','모의규정','제1조','u1',
        [('100','제1조'),('101','① 정의'),('110','10. 제2조를 준용한다.'),('139','39. 제3조를 준용한다.')],
        [('u11','u1',[1],'①',['101'],'circled'),('u110','u11',[10],'10.',['110'],'dot'),('u139','u11',[39],'39.',['139'],'dot')])
    add(db,'b',2,'종료');add(db,'c',3,'종료');nav=navigator(db)
    source=nav.sources['a'];e={'source_id':'a','spans':[{'block_id':b['block_id'],'start_cp':0,'end_cp':len(b['text'])} for b in source['blocks']]}
    origin={'route_class':'DB_REFERENCE','target_extent':nav.extent('a',['110'])}
    fake=SimpleNamespace(repo=SimpleNamespace(evidence=lambda _:e),tools=SimpleNamespace(db=db,sources=nav.sources),
        scope={'d'},context=SimpleNamespace(binding_hash=nav.binding),read_origin=lambda _:origin)
    cards=RelationCards(fake)
    notices=list(cards.references('E1'))
    assert len(notices)==1 and notices[0]['targets'][0]['source_id']=='b'
    assert notices[0]['targets'][0]['exploration_origin']['target_extent']['source_id']=='b'
    calls=[]
    fake.relation_page=lambda anchor,family,offset,direction='both':(calls.append(direction) or [],None,{'scan_status':'COMPLETE'})
    fake.follow_reference=lambda args,offset:RelationsTools.follow_reference(fake,args,offset)
    RelationsTools.follow_relations(fake,{'target':'E1','family':'all'},0)
    assert calls==['both']
