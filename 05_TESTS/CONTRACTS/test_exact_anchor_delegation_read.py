"""Independent synthetic delegated cases: raw text, bounded coverage and consumers."""
import json
import sqlite3
import pytest
from test_batch_reference_navigation import connected, initial, decision, rel
from test_unit_fulltext_adaptive_read import unit_fts, SourceRecall
from test_document_release import source
from test_bounded_source_main import settings
from test_legal_agent_v5 import app_for
from test_unified_legal_agent import ScriptedTransport
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.legal_agent.source_selection import select_sources
from semantic_runtime.legal_agent.unit_reading import read as unit_read, offers
dep = pytest.importorskip('semantic_runtime.legal_agent.unit_dependencies')


@pytest.fixture
def delegated(tmp_path, term_glossary):
    records = [
        ('rule','모의투자규정', ['제1조 투자 구분','① 다음 각 호의 기준을 적용한다.',
            '1. 제3자배정 투자자는 일반 기준을 따른다. 다만, 세칙으로 정하는 경우는 제외한다.',
            '2. 전문투자자는 별도 기준을 따른다. 다만, 세칙으로 정하는 경우는 제외한다.',
            '3. 다른 주주는 일반 기준을 따른다. 다만, 세칙으로 정하는 경우는 제외한다.']),
        ('detail','모의투자규정 시행세칙', ['제2조 투자 예외',
            '① 규정 제1조제1항제1호 단서에서 "세칙으로 정하는 경우"란 다음 각 호의 어느 하나에 해당하는 경우를 말한다.',
            '1. 전문투자자가 취득한 경우', '2. 종업원이 취득한 경우',
            '② 규정 제1조제1항제2호 단서에서 "세칙으로 정하는 경우"란 다음 각 호의 어느 하나에 해당하는 경우를 말한다.',
            '1. 정해진 자격을 갖춘 법인인 경우',
            '③ 규정 제1조제1항제3호 단서에서 "세칙으로 정하는 경우"란 다음 각 호의 어느 하나에 해당하는 경우를 말한다.',
            '1. 무관한 예외 조건']),
        ('other','무관한규정', ['제3조 다른 주주',
            '① 「모의투자규정」 제1조제1항제3호에 따른 무관한 설명']),
        ('cross','모의다른상장규정',['제4조 다른 상장',
            '① 「모의투자규정 시행세칙」 제2조제1항 단서에서 "세칙으로 정하는 경우"란 다음 각 호의 어느 하나에 해당하는 경우를 말한다.',
            '1. 다른 상장 유형에만 적용하는 조건'])]
    raw = source(tmp_path/'raw.sqlite',records)
    trees = {
        'rule':[('0',None,'kr_article','제1조',[1],0,5),('1','0','circled','①',[1],1,5),
                ('2','1','dot_number:1','1.',[1],2,3),('3','1','dot_number:1','2.',[2],3,4),
                ('4','1','dot_number:1','3.',[3],4,5)],
        'detail':[('0',None,'kr_article','제2조',[2],0,8),('1','0','circled','①',[1],1,4),
            ('2','1','dot_number:1','1.',[1],2,3),('3','1','dot_number:1','2.',[2],3,4),
            ('4','0','circled','②',[2],4,6),('5','4','dot_number:1','1.',[1],5,6),
            ('6','0','circled','③',[3],6,8),('7','6','dot_number:1','1.',[1],7,8)],
        'other':[('0',None,'kr_article','제3조',[3],0,2),('1','0','circled','①',[1],1,2)],
        'cross':[('0',None,'kr_article','제4조',[4],0,3),('1','0','circled','①',[1],1,3),
                 ('2','1','dot_number:1','1.',[1],2,3)]}
    with sqlite3.connect(raw) as db:
        for did,nodes in trees.items():
            db.execute('UPDATE document SET json=? WHERE document_id=?',
                (json.dumps({'ladder':{'rungs':[{'families':['kr_article']},
                    {'families':['circled']},{'families':['dot_number:1']}]}}),did))
            db.execute('DELETE FROM source_unit WHERE document_id=?',(did,))
            for uid,parent,family,surface,ordinal,lo,hi in nodes:
                db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',(did,uid,parent,
                    json.dumps({'family':family,'surface':surface,'ordinal':ordinal,'title':'',
                        'parent':parent,'span':[lo,hi]},ensure_ascii=False)))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    gen=tmp_path/'built/generation'
    unit_fts.build(gen,gen/'navigation',tmp_path/'index',workers=1)
    index=unit_fts.UnitFulltextIndex(tmp_path/'index',json.loads((gen/'navigation/manifest.json').read_text()))
    app=app_for(tmp_path,gen,ScriptedTransport(),{**settings(),'page_size':1,'max_read_chars':80})
    p=app.state.pipeline;p.term_agent.unit_fulltext=index
    question='제1호와 제2호 중 어떤 기준인가? (모의투자규정 제1조)'
    request={'question':question,'document_ids':['rule','detail','other','cross'],'use_llm':False}
    try:
        with p.term_agent.open_session(request,query=p.plan(question,request['document_ids']),runtime=tmp_path/'runtime') as session:
            s=session.sources
            src=next(v for v in s.tools.sources.values() if v['document_id']=='rule')
            hit=rel.hit_for(s,src['id'],'0');recall=SourceRecall(s)
            recall.discover=lambda:([src['id']],{'discovery_mode':'structure','routes':{},'unit_hits':[hit]})
            yield s,recall.prepare(),question
    finally:p.store.close()


def run_selection(s,record,question,observations):
    def invoke(system,data,schema,phase,timeout):
        observations.append((phase,data))
        if phase=='source-unit-triage':
            return {'issues':['투자 구분'],'choices':[{'id':data['units'][0]['id'],
                'scope':'subtree:0','reason':'질문 규정의 원문을 확인한다'}],'needs_search':False}
        if phase.startswith('source-reference-batch'):return decision(data)
        return {'issues':[],'choices':[],'needs_search':False}
    return select_sources(question,record,invoke,remaining_seconds=120,session=s)


def test_required_delegated_conditions_are_read_despite_skip_and_reach_review(delegated):
    s,record,question=delegated;seen=[]
    out=run_selection(s,record,question,seen)
    assert out['status']=='complete'
    original=next(v for v in out['selected_originals'] if v['document_id']=='detail')
    assert '전문투자자가 취득한 경우' in original['text']
    assert '정해진 자격을 갖춘 법인인 경우' in original['text']
    assert '무관한 예외 조건' not in original['text']
    assert '제2조 투자 예외' not in original['text']
    scopes={r['scope'] for r in out['reference_navigation']['required_reads']
            if r['status']=='READ' and r['kind']=='EXPLICIT_DELEGATED_CASES'}
    assert scopes=={'subtree:1','subtree:4'}
    review=next(data for phase,data in seen if phase=='source-unit-review')
    assert any('전문투자자가 취득한 경우' in row['text'] for row in review['sources'])
    assert {e['source_id'] for e in out['selected_evidence']}==set(out['final_ids'])


def test_question_unit_focus_excludes_other_paragraphs_and_other_sources(delegated):
    s,record,question=delegated
    row=record['unit_reads'][0];state={'count':len(record['actions']),'chars':record['source_chars']}
    hit=rel.hit_for(s,row['source_id'],'0')
    chosen=unit_read(s,hit,next(o for o in offers(s,hit) if o['id']=='subtree:0'),action_state=state)
    selected={'U1':chosen};focus,receipts,unresolved=dep.focus_for(question,s,selected)
    assert focus[row['source_id']]=={'2','3'} and not unresolved
    groups,_,_,_=rel.catalog(s,[row['source_id']],selected,set(),focus)
    assert len(groups)==1 and groups[0]['target']['document_id']=='detail'
    assert len(groups[0]['connections'])==2
    assert {c['witness_unit_id'] for c in groups[0]['connections']}=={'1','4'}


def test_required_character_budget_cannot_be_overridden_by_needs_search_false(delegated,monkeypatch):
    s,record,question=delegated
    monkeypatch.setitem(dep.LIMITS,'chars',1)
    out=run_selection(s,record,question,[])
    assert out['status']=='pending' and out['needs_fulltext']
    assert any(r['status']=='UNRESOLVED' and r['reason']=='required_read_budget'
               for r in out['reference_navigation']['required_reads'])


def test_missing_question_coordinate_remains_unresolved(delegated):
    s,record,_=delegated
    out=run_selection(s,record,'제9호의 기준은 무엇인가? (모의투자규정 제1조)',[])
    assert out['status']=='pending'
    assert out['reference_navigation']['focus_unresolved'][0]['reason']=='ambiguous_or_missing_question_unit'


def test_local_next_items_are_completed_without_relation_model_call(delegated):
    s,record,_=delegated;row=record['unit_reads'][0]
    hit=rel.hit_for(s,row['source_id'],'1');state={'count':len(record['actions']),'chars':record['source_chars']}
    own=unit_read(s,hit,next(o for o in offers(s,hit) if o['id']=='exact:1'),action_state=state)
    selected={'U1':own};focus={row['source_id']:{'1'}};receipts=[]
    assert not dep.complete_local_lists(s,selected,focus,rel.hit_for,state,receipts)
    assert any('제3자배정 투자자는' in r['text'] for r in selected.values())
    assert any(r['kind']=='LOCAL_ENUMERATION' and r['scope']=='subtree:1' for r in receipts)


def test_ordinary_reference_is_still_optional(connected):
    s,_=connected;record,sid=initial(s)
    calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if phase.startswith('source-reference-batch'):return decision(data)
        return {'issues':[],'needs_search':False,'choices':([{'id':data['units'][0]['id'],
            'scope':'exact:2','reason':'선택한 원칙을 확인'}] if phase.endswith('triage') else [])}
    out=select_sources('원칙',record,invoke,remaining_seconds=120,session=s)
    assert out['final_ids']==[sid]
    assert not any(r.get('kind')=='EXPLICIT_DELEGATED_CASES' for r in out['reference_navigation']['required_reads'])
    assert any(p.startswith('source-reference-batch') for p in calls)


def test_inaccessible_required_detail_keeps_coverage_unresolved(delegated):
    s,record,question=delegated
    s.scope=['rule','other']
    out=run_selection(s,record,question,[])
    assert out['status']=='pending' and out['needs_fulltext']
    assert not any(v['document_id']=='detail' for v in out['selected_originals'])
    assert out['reference_navigation']['unresolved_delegations']


def test_reverse_role_on_defining_anchor_stays_optional_and_unread(delegated):
    s,record,question=delegated;seen=[]
    out=run_selection(s,record,question,seen)
    assert out['status']=='complete'
    assert not any(v['document_id']=='cross' for v in out['selected_originals'])
    assert not any(s.tools.sources[r['source_id']]['document_id']=='cross'
                   for r in out['reference_navigation']['required_reads'])
    cards=[g for phase,data in seen if phase.startswith('source-reference-batch') for g in data['groups']]
    cross=next(g for g in cards if g['target']['document_id']=='cross')
    assert cross['connections'][0]['reference_role']=='SPECIFIES_DELEGATED_CASES_OF'
    assert cross['direction']=='INCOMING'
