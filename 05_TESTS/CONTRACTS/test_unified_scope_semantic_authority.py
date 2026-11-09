"""Native boundaries for the MAIN semantic audit; synthetic originals only."""
from conftest import term_glossary
from copy import deepcopy
from types import SimpleNamespace as S
import sqlite3
import pytest
from jsonschema import validate, ValidationError
from semantic_runtime.legal_agent import request_entry as entry, query_scope as qs
from semantic_runtime.legal_agent import completion_v8 as v8, completion_execution as ce
from semantic_runtime.legal_agent import law_title_hints as titles, law_name_recovery as names
from semantic_runtime.legal_agent import structure_query as sq, relation_read_policy as relations
from semantic_runtime.legal_agent.corrected_memory import MemoryError
from semantic_runtime.navigation_match import SurfaceIndex, MorphIndex
from semantic_runtime import fulltext, term_morph
from test_source_span_norm import proposal
from test_main50_request_repair import GAP
from test_unit_fulltext_adaptive_read import tree, session
from test_followup_structure_lookup import investigation, apply, structured_generation

# The request-entry search field asks_definition exists from the definition-priority change on; older
# code rejects it, so scripted entries carry it only when the loaded schema has it.
from semantic_runtime.legal_agent import request_entry as _asks_entry
import json as _asks_json
ASKS_DEFINITION = {'asks_definition': True} if 'asks_definition' in _asks_json.dumps(_asks_entry.schema(model=True)) else {}


def wire(question='모의승인규정에서 승인 요건을 알려줘',named=True):
    return {'routing':{'mode':'CASE','answer':'','reason':'새 질문'},
        'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
            'queries':['모의승인규정 승인 요건'],'format':'prose','reason':'요청 범위 조사'},
        'intent':{'purpose':'승인 요건 설명','concepts':['승인'],
            'issues':[{'id':'Q1','question':'승인 요건','subject':'승인','kind':'OTHER'}]},
        'context_quotes':[], 'search':{**ASKS_DEFINITION, 'mode':'FULLTEXT','reason':'본문의 요건 확인',
            'scope_decision':{'mode':'NAMED_SCOPE' if named else 'AUTHORIZED_SCOPE',
                'targets':[{'document':'모의승인규정','structure':None,'selection':None}] if named else [],
                'user_quote':question if named else '',
                'reason':'이 규정에서 확인하라는 명시 요청' if named else '검색 법령을 지정하지 않은 일반 요청'}}}


def test_single_scope_wire_has_no_independent_title_or_keep_decision():
    schema=entry.schema(model=True)
    command=schema['properties']['command']['anyOf'][0]
    search=schema['properties']['search']['anyOf'][0]
    assert 'search_scope_change' not in command['properties']
    assert 'title_hint_ids' not in search['properties']
    raw=wire();validate(raw,schema)
    hints={'candidates':[{'hint_id':'T1','title':'모의승인규정','matched_label':None}]}
    decoded=entry.decode_scope(raw,hints)
    assert decoded['command']['search_scope_change']['operation']=='REPLACE'
    assert decoded['search']['title_hint_ids']==['T1']
    assert 'scope_decision' in raw['search']
    validate(decoded,entry.schema())


@pytest.mark.parametrize('mode,targets,quote',[
    ('NAMED_SCOPE',[],''),('AUTHORIZED_SCOPE',[{'document':'상법','structure':None,'selection':None}],''),
    ('AUTHORIZED_SCOPE',[],'상법')])
def test_scope_conflicts_rejected_without_guessing(mode,targets,quote):
    raw=wire();raw['search']['scope_decision'].update(mode=mode,targets=targets,user_quote=quote)
    with pytest.raises(MemoryError):entry.decode_scope(raw,{'candidates':[]})


def test_title_clue_count_does_not_discard_allowed_candidates():
    m=S(documents={str(i):'모의승인규정'+str(i) for i in range(11)},
        document_context={},document_aliases={str(i):['승인규정'] for i in range(11)})
    result=titles.hints('승인규정에서 기준 확인',m,list(m.documents))
    assert len(result['candidates'])==11 and result['omitted_candidates']==0
    rows,total=names.candidates(m,list(m.documents),'승인규정')
    assert len(rows)==total==11
    assert len(titles.hints('승인규정',m,['0'])['candidates'])==1


def test_nested_terms_preserve_boundaries():
    index=SurfaceIndex();index.add('주주','short');index.add('주주총회','long')
    assert {v for h in index.match('주주총회',include_nested=True) for v in h['values']}=={'short','long'}
    assert [h['values'] for h in index.match('주주총회')]==[['long']]
    assert not index.match('가주주총회',include_nested=True)
    morph=MorphIndex();morph.add('주주','short');morph.add('주주 총회','long')
    assert 'short' in {v for h in morph.match('주주 총회') for v in h['values']}


def test_all_query_terms_reach_fts(monkeypatch):
    terms=['token'+str(i) for i in range(70)]
    monkeypatch.setattr(term_morph,'tokenize',lambda text:[S(form=t,tag='NNG') for t in terms])
    assert fulltext.question_terms('query')==terms
    db=sqlite3.connect(':memory:');db.execute('CREATE VIRTUAL TABLE f USING fts5(text)')
    db.execute('INSERT INTO f VALUES (?)',(terms[-1],))
    assert db.execute('SELECT count(*) FROM f WHERE f MATCH ?',(fulltext.expression(terms),)).fetchone()[0]==1
    db.close()


def test_all_document_headings_remain_paged_candidates():
    from test_structure_first_search import matcher
    m=matcher()
    expected=sq.catalogue(m,['law'],document_id='law',limit=100)
    got=sq.catalogue(m,['law'],document_id='law',queries=['아무관련어도없음'],limit=1)
    assert got['total']==expected['total']==2
    seen=[]
    while True:
        seen.extend(r['unit_id'] for r in got['items'])
        if got['next_offset'] is None:break
        got=sq.catalogue(m,['law'],document_id='law',queries=['아무관련어도없음'],limit=1,offset=got['next_offset'])
    assert set(seen)=={r['unit_id'] for r in expected['items']}


@pytest.mark.parametrize('kind',['MISSING_SOURCE','MISSING_SCOPE','WRONG_SUBJECT','UNREAD_SAVED','UNRESOLVED_REFERENCE'])
def test_materiality_and_issue_reason_are_preserved(kind):
    raw=proposal();raw['gaps']=[{**deepcopy(GAP),'kind':kind,'material':False}]
    raw['issue_assessments'][0]['reason']='확보한 원문으로 요청의 기준을 설명할 수 있고 부수 내용만 미확인'
    options=[{'id':'S1','source_id':'s','text':'신고할 수 있다.'}];issues=[{'id':'Q1','question':'신고'}]
    schema=v8.assessment_schema(issues,[],options,[])
    wire_schema,decode=ce.assessment_projection(schema)
    compact=deepcopy(raw);compact.pop('disposition')
    accepted,audit=v8.prepare(decode(compact),schema,issues,options,[])
    assert accepted['gaps'][0]['material'] is False
    assert accepted['issue_assessments'][0]['reason']==raw['issue_assessments'][0]['reason']
    assert audit['gaps']==raw['gaps'] and accepted['disposition']=='ANSWER'


def test_same_norm_across_issues_is_not_a_retry_trigger():
    raw=proposal();second=deepcopy(raw['claims'][0]);second.update(claim_id='C2',issue_refs=['Q2'])
    raw['claims'].append(second)
    raw['issue_assessments'].append({'issue_id':'Q2','status':'COVERED','reason':'같은 규정이 이 요구에도 적용'})
    options=[{'id':'S1','source_id':'s','text':'신고할 수 있다.'}]
    issues=[{'id':i,'question':'신고'} for i in ('Q1','Q2')]
    accepted,_=v8.prepare(raw,v8.assessment_schema(issues,[],options,[]),issues,options,[])
    assert len(accepted['claims'])==2
    bad=deepcopy(raw);bad['claims'][1]['rule']['norms'][0]['source_ref']='hidden'
    with pytest.raises(ValidationError):v8.prepare(bad,v8.assessment_schema(issues,[],options,[]),issues,options,[])


def test_relation_necessity_is_not_inferred_from_words():
    text='제2조를 준용한다.'
    policy=relations.classify({'source_text':text,'mention_start':0,'mention_end':3,'mention_text':'제2조'},'OUTGOING',{})
    assert policy['kind']=='APPLIES_MUTATIS_MUTANDIS' and policy['obligation']=='OPTIONAL'
    relations.validate_decision({'action':'SKIP','applicability':'UNDETERMINED','applicability_reason':'현재 질문의 직접 요건에는 필요 없고 적용 여부는 미확인'},
        {'connections':[{'reading_policy':policy}]})


def test_failed_sibling_and_range_have_independent_name_clues():
    from test_structure_first_search import matcher
    m=matcher();m.document_context={};m.document_aliases={'law':['자본시장법']}
    page=names.attach(sq.catalogue(m,['law'],queries=['자본시장법 제6조','자본시장규칙 제99조']),m,['law'])
    assert page['law_name_recoveries'][0]['original_queries']==['자본시장규칙 제99조']
    page=names.attach(sq.catalogue(m,['law'],queries=['자본시장규칙 제6조부터 제9조']),m,['law'])
    recovery=page['law_name_recoveries'][0]
    assert recovery['requires_structure_decision'] and recovery['structure_filter'] is None
    assert recovery['original_queries']==['자본시장규칙 제6조부터 제9조']


def test_body_search_can_leave_article_cursor_but_not_user_scope(session):
    native,_=session;inv=investigation(native);inv.policy['structure_first']=True
    scope=qs.resolve({'operation':'REPLACE','targets':[{'document':'모의승인규정','structure':None}],
        'user_quote':'모의승인규정'},None,inv.s.matcher,inv.s.scope,'모의승인규정')
    qs.attach(inv.s,scope)
    inv.p['structure_location']={'document_id':'d','unit_id':'0','offset':0}
    data,actions=inv.view()
    targets=[a['identity'] for a in actions.values() if a['action']=='SEARCH_BODY']
    assert {'document_id':'d','unit_id':None} in targets
    assert qs.active(inv.s)==scope
    assert all(a['document_id']=='d' for a in targets)
