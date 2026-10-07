"""Native pre-SQL eligibility, action scope separation and projection guards."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parent))
import run

@pytest.fixture
def native(tmp_path):
    frozen=run.verify();mods=run.modules(frozen);assets=run.ADR/'artifacts/native-contracts'
    cat=run.read(assets/'source-catalogue.json')
    return mods,assets,cat,tmp_path

def actions(*pairs):
    return [{'query':q,'concept_refs':refs,'reason':'기존 판단 근거','expected_information':'이번 행동에서 확인할 정보'} for q,refs in pairs]

def scopes(native,aa,documents=None):
    m,a,cat,_=native;g=m['graph'].Graph(a/'ontology.sqlite')
    try:return m['scope'].ActionScopes(g,m['graph'],cat,documents or ['mock-regulation:v1','mock-performance:v1'],aa)
    finally:g.close()

def c_nodes(cat):return {s for s,c in cat.items() if c['document_id']=='mock-performance:v1'}

def test_mixed_action_has_two_distinct_scopes(native):
    _,_,cat,_=native
    aa=actions(('적용규정 확인',['purpose:applicable']),('업무 실적 확인',['purpose:performance']))
    ss=scopes(native,aa);c=c_nodes(cat)
    assert not c&set(ss.for_query('적용규정 확인')['allowed_node_ids'])
    assert c<=set(ss.for_query('업무 실적 확인')['allowed_node_ids'])
    assert c<=ss.allowed_union  # a legitimate second action preserves needed C

@pytest.mark.parametrize('aa',[[],actions(('미확정',[])),actions(('충돌',['purpose:applicable']),('충돌',['purpose:performance']))])
def test_unknown_or_conflicting_action_does_not_prune(native,aa):
    ss=scopes(native,aa);assert c_nodes(native[2])<=ss.allowed_union
    assert not ss.for_query('충돌')['excluded_node_ids']

def test_stale_version_reverts_before_search(native):
    aa=actions(('특례 적용',['purpose:applicable']))
    ss=scopes(native,aa,['mock-regulation:v1','mock-performance:v1','mock-drift:v2'])
    p=ss.for_query('특례 적용');assert 'version changed' in p['fallback_reason']
    assert not p['excluded_node_ids']
    assert c_nodes(native[2])<=set(p['allowed_node_ids'])

def test_plan_contract_requires_valid_contexts_and_query_alignment(native):
    m= native[0]['plan'];names=['모의규정'];ids=['purpose:applicable','purpose:performance','purpose:inventory']
    value={'mode':'SEARCH','reason':'적용 확인','answer':'','law_names':[],
           'queries':['인수 적용'],'browse_view':'documents','document_category':'all','title_query':'',
           'inspect_documents':False,'search_actions':actions(('인수 적용',['purpose:applicable']))}
    assert m.validate_action_catalogue(value,names,ids)==value
    bad=deepcopy(value);bad['search_actions'][0]['concept_refs']=['unknown:concept']
    with pytest.raises(Exception):m.validate_action_catalogue(bad,names,ids)
    bad=deepcopy(value);bad['search_actions'][0]['query']='다른 검색'
    with pytest.raises(ValueError):m.validate_action_catalogue(bad,names,ids)

@pytest.mark.parametrize('limit',[None,1,4,16])
def test_pre_sql_scope_retains_native_bm25_order_and_ties(native,limit):
    from semantic_runtime.fulltext import question_terms
    m,a,cat,out=native;case=run.read(run.DESIGN/'cases.json')['cases'][0]
    with run.session(out,a/'fixture/built/generation',case,False) as s:
        ss=scopes(native,actions(('인수 적용',['purpose:applicable'])))
        allowed=set(ss.for_query('인수 적용')['allowed_node_ids'])
        proj=run.read(a/'fts-projection.json')['source_rowids'];rows=[proj[sid] for sid in allowed]
        index=s.sources.matcher.fulltext;db=s.sources.matcher.fulltext_db;terms=question_terms('외국인 인수 적용')
        baseline=index.rank(db,terms,allowed,limit)
        candidate=m['fts'].FulltextIndex.rank(index,db,terms,allowed,limit,eligible_rowids=rows)
        assert baseline==candidate
        assert not c_nodes(cat)&set(candidate)

@pytest.mark.parametrize('ancestor',[False,True])
def test_native_read_c_cannot_bypass_single_action_scope(native,ancestor):
    m,a,cat,out=native;case=run.read(run.DESIGN/'cases.json')['cases'][0]
    with run.session(out,a/'fixture/built/generation',case,False) as s:
        ss=scopes(native,actions(('適用',['purpose:applicable'])));ss.install(s.sources,cat)
        sid=next(iter(c_nodes(cat)));c=cat[sid]
        target=s.sources.handle('D' if ancestor else 'P',{'document_id':c['document_id']} if ancestor else
            {'document_id':c['document_id'],'unit_id':c['unit_id'],'source_id':sid})
        proposal={'tool':'read','args':{'target':target,'extent':'article','cursor':None},'question_refs':['Q1'],
                  'reason':'native read guard','expected_information':'원문'}
        with pytest.raises(m['graph'].AccessDenied):s.sources.execute(proposal,'blocked',actor='SYSTEM_POLICY')
        assert not s.sources.repo.evidence()

def test_alternative_query_backend_can_consume_same_scope(native):
    ss=scopes(native,actions(('개념 검색',['purpose:applicable'])))
    # An alternate backend consumes generic node eligibility, no fulltext naming.
    alternate=lambda eligible:list(sorted(set(eligible)&set(native[2])))
    assert not set(alternate(ss.for_query('개념 검색')['allowed_node_ids']))&c_nodes(native[2])

def test_empty_sql_scope_returns_no_rows(native):
    from semantic_runtime.fulltext import question_terms
    m,a,_,out=native;case=run.read(run.DESIGN/'cases.json')['cases'][0]
    with run.session(out,a/'fixture/built/generation',case,False) as s:
        assert m['fts'].FulltextIndex.rank(s.sources.matcher.fulltext,s.sources.matcher.fulltext_db,
            question_terms('외국인'),set(),eligible_rowids=[])==[]
