"""Synthetic scope, retry, source and state contracts; no generated legal answers."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
qs=pytest.importorskip('semantic_runtime.legal_agent.query_scope')
from semantic_runtime.legal_agent import memory_methods as mm, corrected_memory as memory
from semantic_runtime.legal_agent import unit_reading as ur, law_candidates as lc
from semantic_runtime.legal_agent.errors import ContractError
from test_memory_runtime_v2 import Fake, Wire, command
from test_unit_fulltext_adaptive_read import session,hit
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime import unit_fulltext
import sqlite3,json


@pytest.fixture
def tree(tmp_path,term_glossary):
    texts=['제1조 승인 규칙','① 다음 각 호의 승인 기준을 적용한다.',
        '1. 승인 원칙은 다음 목과 같다.','가. 긴급 승인 예외는 허용한다.',
        '2. 일반 승인 예외는 허용하지 않는다.','② 승인 후 보고한다.']
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',texts),('other','다른규정',['별도 원문'])])
    nodes=[('0',None,'kr_article','제1조',0,6,'제1조'),
        ('1','0','circled','①',1,5,'제1조제1항'),
        ('2','1','dot_number:1','1.',2,4,'제1조제1항제1호'),
        ('3','2','hangul_dot','가.',3,4,'제1조제1항제1호가목'),
        ('4','1','dot_number:1','2.',4,5,'제1조제1항제2호'),
        ('5','0','circled','②',5,6,'제1조제2항')]
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='d'")
        for uid,parent,family,surface,lo,hi,locator in nodes:
            coordinate=find_coordinates(locator)[0].coordinate
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',uid,parent,json.dumps({
                'family':family,'surface':surface,'title':'','span':[lo,hi],
                'legal_coordinate':coordinate.as_dict(),'coordinate_scope':'body',
                'coordinate_key':'body:'+coordinate.canonical_surface()},ensure_ascii=False)))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    gen=tmp_path/'built/generation';idx=tmp_path/'unit-index'
    unit_fulltext.build(gen,gen/'navigation',idx,workers=1)
    return gen,unit_fulltext.UnitFulltextIndex(idx,json.loads((gen/'navigation/manifest.json').read_text()))


def change(document=None,structure=None,operation='REPLACE',quote=None):
    return {'operation':operation,'targets':[] if operation in ('KEEP','CLEAR') else [{'document':document,'structure':structure,'selection':None}],
        'user_quote':quote if quote is not None else ' '.join(x for x in (document,structure) if x)}


def metadata():
    matcher = S(documents={'a':'가상심사규정','b':'가상심사규정 시행세칙','c':'다른규정'},
        document_context={},document_aliases={'a':['가상규정']},stored_coordinates={},units={
            ('a','ch'):{'surface':'제2장','title':'심사','parent':None,'span':[0,3]},
            ('a','1'):{'surface':'제10조','title':'승인','parent':'ch','span':[0,2]},
            ('a','2'):{'surface':'제11조','title':'보고','parent':None,'span':[3,4]}})
    # Match persisted source metadata: a bare coordinate selects a bound body
    # branch, never an unresolved title or an addendum with the same surface.
    from lawrag.core.legal_coordinate import parse_label
    for key, node in matcher.units.items():
        coordinate = parse_label(node['surface'])
        assert coordinate is not None
        node.update(coordinate_scope='body', coordinate_key='body:'+coordinate.canonical_surface())
        matcher.stored_coordinates[key] = coordinate
    return matcher


@pytest.mark.parametrize('count',[0,1,160,161,1000])
def test_authorized_replan_never_serializes_inventory(count):
    ctx={'goals':[{'id':'g'}],'knowledge':[],'allowed_documents':[{'id':str(i)} for i in range(count)]}
    value=mm.normalize(command('RESEARCH_REPLAN',target='g',document_scope_mode='AUTHORIZED'),ctx)
    from jsonschema import validate
    validate(value,memory.COMMAND)
    assert value['document_ids'] is None


def test_followup_scope_keep_replace_add_clear_and_no_cross_document_inheritance():
    m=metadata();scope=qs.resolve(change('가상규정','제2장'),None,m,['a','b','c'],'가상규정 제2장')
    kept=qs.resolve(change(operation='KEEP'),scope,m,['a','b','c'],'아니 승인 예외를 다시 찾아')
    assert kept==scope
    replaced=qs.resolve(change('다른규정'),scope,m,['a','b','c'],'다른규정')
    assert replaced['targets'][0]['document_id']=='c' and replaced['targets'][0]['unit_id'] is None
    added=qs.resolve(change('다른규정',operation='ADD'),scope,m,['a','b','c'],'다른규정')
    assert {r['document_id'] for r in added['targets']}=={'a','c'}
    assert qs.resolve(change(operation='CLEAR',quote='전체에서 찾아'),added,m,['a','b','c'],'전체에서 찾아') is None


@pytest.mark.parametrize('requested,authorized',[
    (change('가상심사'),['a','b']), (change('없는규정'),['a','b']),
    (change('다른규정'),['a','b']), (change('가상규정','제99장'),['a','b'])])
def test_missing_ambiguous_denied_scope_never_becomes_global(requested,authorized):
    with pytest.raises(qs.UnresolvedScope):qs.resolve(requested,None,metadata(),authorized,requested['user_quote'])


def test_scope_hash_metadata_and_acl_are_rechecked():
    m=metadata();scope=qs.resolve(change('가상규정'),None,m,['a'],'가상규정')
    s=S(matcher=m,scope=['a']);qs.attach(s,scope)
    bad=deepcopy(scope);bad['targets'][0]['document_id']='c'
    with pytest.raises(ContractError,match='hash'):qs.attach(s,bad)
    s.scope=[]
    with pytest.raises(ContractError,match='authorization'):qs.attach(s,scope)
    s.scope=['a'];m.document_context['a']={'version':'changed'}
    with pytest.raises(ContractError,match='metadata'):qs.attach(s,scope)


def test_whole_named_document_cannot_silently_clear_the_document_boundary():
    m=metadata();scope=qs.resolve(change('가상규정','제2장'),None,m,['a','b'],'가상규정 제2장')
    quote='제2장만 보지 말고 가상심사규정 전부를 대상으로 찾아'
    with pytest.raises(qs.UnresolvedScope,match='특정 문서'):
        qs.resolve(change(operation='CLEAR',quote=quote),scope,m,['a','b'],quote)
    with pytest.raises(qs.UnresolvedScope,match='특정 문서'):
        qs.resolve(change(operation='CLEAR',quote='전부를 대상으로 찾아'),scope,m,['a','b'],quote)
    wider=qs.resolve(change('가상심사규정',quote=quote),scope,m,['a','b'],quote)
    assert wider['targets'][0]['document_id']=='a' and wider['targets'][0]['unit_id'] is None
    assert scope['targets'][0]['unit_id']=='ch'


def test_fulltext_filters_before_paging_and_reads_cannot_expand_to_siblings(session):
    native,idx=session;s=native.sources
    scope=qs.resolve(change('모의승인규정','①'),None,s.matcher,['d'],'모의승인규정 ①')
    qs.attach(s,scope)
    params=qs.fulltext(s)
    page=idx.hit_page(s.matcher.unit_fulltext_db,['승인'],hit(native)['source_id'],lc.allowed(s),limit=30,**params)
    assert {r['unit_id'] for r in page['items']} <= {'1','2','3','4'}
    choices=ur.offers(s,hit(native))
    assert choices and all(set(o['block_ids']) <= {'1','2','3','4'} for o in choices)
    outside=next(o for o in ur._offer_plan(s,hit(native))[0] if o['id']=='subtree:0')
    with pytest.raises(ContractError,match='unoffered'):ur.read(s,hit(native),outside,action_state=ur.read_state(s))
    assert qs.documents(s)==['d'] and not qs.direct(s,'d','5')
    page=qs.document_structure(s,'d')
    assert [r['unit_id'] for r in page['children']]==['1']


def test_verified_read_grant_does_not_expand_search(session):
    native,idx=session;s=native.sources
    scope=qs.resolve(change('모의승인규정','①'),None,s.matcher,['d'],'모의승인규정 ①');qs.attach(s,scope)
    before=qs.fulltext(s);sid=hit(native)['source_id']
    assert not ur.offers(s,hit(native,'5'))
    qs.grant(s,sid,['5'],witness={'kind':'synthetic_validated_edge'})
    assert ur.offers(s,hit(native,'5'))
    assert qs.fulltext(s)==before and not qs.direct(s,'d','5')
    assert not qs.action_allowed(s,'SEARCH_BODY',{'document_id':'d','unit_id':'5'})
    with pytest.raises(ContractError):qs.grant(s,sid,['999'],witness={})


def test_metadata_page_never_returns_sibling_outside_scope(session):
    native,_=session;s=native.sources
    scope=qs.resolve(change('모의승인규정','①'),None,s.matcher,['d'],'모의승인규정 ①');qs.attach(s,scope)
    for offset in range(4):
        page=qs.catalogue(s,document_id='d',queries=['승인'],offset=offset,limit=1)
        assert all(qs.direct(s,r['document_id'],r.get('unit_id')) for r in page['items'])


def test_failed_first_question_can_change_query_keep_scope_and_restore(tmp_path):
    m=metadata()
    class Scoped(Fake):
        def scope_state(self,state,c,utterance,*,dialogue=(),**kw):
            if c.get('search_scope_change'):
                state={**state,'search_scope':qs.resolve(c['search_scope_change'],state.get('search_scope'),m,state['document_ids'],utterance)}
            return state
    f=Scoped();w=Wire();repo=memory.Memory(tmp_path/'state.sqlite',f,w)
    principal={'user_id':'u','team_id':'risk_team','document_ids':['a','b']}
    def send(number,c,question):
        w.command=c
        return repo.execute({'question':question,'request_id':str(number),'session_id':'s'},principal)
    f.fails='SELECT'
    with pytest.raises(memory.MemoryError):send(1,command('CASE_START',task='승인 요건',search_scope_change=change('가상규정','제2장')),'가상규정 제2장')
    row=repo.context('s',principal,'')['goals'][0];gid=row['id'];before=deepcopy(row['state'])
    assert before['search_scope']['targets'][0]['unit_id']=='ch'
    f.fails=None
    result=send(2,command('RESEARCH_REPLAN',target=gid,queries=['승인 예외'],document_scope_mode='AUTHORIZED'),'못 찾은 승인 예외로 수정')
    assert result['goal_id']==gid and result['state']['search_scope']==before['search_scope']
    assert result['executed'][0]=='PLAN'
    duplicate=repo.execute({'question':'못 찾은 승인 예외로 수정','request_id':'2','session_id':'s'},principal)
    assert duplicate==result
    initial=repo.events(gid)[0]['id']
    replaced=send(3,command('RESEARCH_REPLAN',target=gid,search_scope_change=change('가상심사규정 시행세칙')),'가상심사규정 시행세칙')
    assert replaced['state']['search_scope']['targets'][0]['document_id']=='b'
    restored=send(4,command('STATE_RESTORE',target=gid,restore_event=initial,restore_fields=['search_scope']),'원래 범위로 복원')
    assert restored['state']['search_scope']==before['search_scope']
    prior=repo.goal(gid,'s')
    unresolved=send(5,command('RESEARCH_REPLAN',target=gid,search_scope_change=change('없는규정')),'없는규정')
    assert unresolved['status']=='CLARIFY' and repo.goal(gid,'s')==prior
    repo.close()

from test_batch_reference_navigation import connected,initial
from semantic_runtime.legal_agent import unit_relations as relations

def test_actual_reference_catalogue_grants_read_only_after_original_acquisition(connected):
    s,idx=connected
    scope=qs.resolve(change('모의승인규정'),None,s.matcher,s.scope,'모의승인규정');qs.attach(s,scope)
    detail=next(v for v in s.tools.sources.values() if v['document_id']=='detail')
    assert not ur.offers(s,relations.hit_for(s,detail['id'],'1'))
    rec,sid=initial(s)
    groups,*_=relations.catalog(s,[sid],{'U1':rec['unit_reads'][0]},set())
    group=next(g for g in groups if g['target']['document_id']=='detail')
    assert group['offers'] and qs.permitted_blocks(s,detail['id'])
    assert qs.documents(s)==['d'] and detail['id'] not in qs.search_sources(s)
    assert not qs.action_allowed(s,'OPEN_LAW',{'document_id':'detail'})
    assert not any(g['target']['document_id']=='foreign' for g in groups)
    h,offer=next(pair for pair in group['offers'].values() if pair[1]['extent']=='exact')
    read=ur.read(s,relations.hit_for(s,detail['id'],offer['unit_id']),offer,action_state=ur.read_state(s))
    assert read['complete'] and read['evidence_ids']
    assert qs.documents(s)==['d']

    checkpoint={'selected':{'direct':rec['unit_reads'][0],'linked':read},'contexts':{},
        'scope_read_grants':deepcopy(s.scope_read_grants),'direct_scope_hash':scope['hash']}
    qs.attach(s,scope)
    qs.restore_grants(s,checkpoint)
    assert set(offer['block_ids']) <= qs.permitted_blocks(s,detail['id'])
    assert qs.documents(s)==['d']
    corrupt=deepcopy(checkpoint);corrupt['scope_read_grants'][detail['id']]['999']={'reference_id':'absent'}
    qs.attach(s,scope)
    # 2026-11-08: a grant no current original witnesses is dropped (narrower reading), not a request failure
    # (MAIN176 S4 HTTP 500). The verified grants are restored as before.
    qs.restore_grants(s,corrupt)
    assert set(offer['block_ids']) <= qs.permitted_blocks(s,detail['id']) and '999' not in qs.permitted_blocks(s,detail['id'])
