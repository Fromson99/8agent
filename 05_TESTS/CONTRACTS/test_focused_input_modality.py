"""Synthetic source, scope and durable-consumer boundaries; no quality certification."""
from copy import deepcopy
from types import SimpleNamespace as S
import json
import pytest
from jsonschema import Draft202012Validator, ValidationError
from semantic_runtime.legal_agent import completion_v6 as v6, completion_v5 as v5, completion_contracts as cc
from semantic_runtime.legal_agent import investigation_scope as scope, law_navigation as ln
from semantic_runtime.legal_agent.navigation_input import NavigationReferences, compact_cards, expand_cards, AUDIT_FIELDS
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_main50_request_repair import tree, session, modern, proposal, ModernTransport, GAP
from test_investigation_completion_adr0678 import decision, apply
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_unified_legal_agent import ok


def strip_audit(v):
    if isinstance(v,dict):return {k:strip_audit(x) for k,x in v.items() if k not in AUDIT_FIELDS}
    if isinstance(v,list):return [strip_audit(x) for x in v]
    return v


def test_aliases_preserve_original_text_and_structured_identity_and_collisions():
    ident='T'+'a'*32
    view={'ids':[ident,'T1'],'sources':[{'id':ident,'source_id':'article:d:1','text':ident}],
          'request_quote':ident,'text_hash':'b'*64}
    codec=NavigationReferences(view);encoded=codec.view(view)
    assert encoded['ids']==['T2','T1'] and encoded['sources'][0]['text']==ident
    assert codec.restore(encoded)==view and NavigationReferences(view).receipt(view)==codec.receipt(view)
    schema=cc.obj({'target':{'enum':[ident]},'source_quote':{'const':ident}})
    wire_schema=codec.schema(schema)
    assert codec.decode({'target':'T2','source_quote':ident},wire_schema)=={'target':ident,'source_quote':ident}
    for bad in ['T1',ident,'T3']:
        with pytest.raises(ProposalError):codec.decode({'target':bad,'source_quote':ident},wire_schema)


def test_cards_roundtrip_all_sources_choices_and_multilingual_coordinates():
    rows=[{'id':'B'+str(i),'article':'제9-35조 ①','preview':'聯結 10.0%','read_action':'T'+str(i),'span_hash':'a'*64} for i in range(8)]
    original={'articles':rows,'laws':[{'id':'L1','articles':deepcopy(rows)}],
       'actions':[{'id':'T'+str(i),'action':'READ_ARTICLES','label':'원문 확인'} for i in range(8)],
       'sources':[{'source_id':'article:1','text':'① 허가를 받아야 한다.\n② 갈음할 수 있다.','start_cp':0,'end_cp':38}]}
    saved=deepcopy(original);after=compact_cards(original)
    assert expand_cards(after)==strip_audit(original) and original==saved
    assert after['sources']==original['sources']
    assert len(json.dumps(after,ensure_ascii=False))<len(json.dumps(original,ensure_ascii=False))


def purpose(view,target,relation='DIRECT'):
    return {'target':target,'issue_id':'Q1','request_quote':view['issues'][0].get('request_quote',view['investigation_scope']['request']),
        'missing_need':'승인 기준 원문 확보','relation':relation,'source_quote':''}


def focused(native):
    i=modern(native);i.s.profile['candidate_navigation']['completion_policy_version']=cc.V6
    i.p['issues'][0]['request_quote']='승인 기준'
    return i


def test_scope_is_connected_and_requires_exact_need_for_every_target(session):
    native,_=session;i=focused(native);d,a=i.view()
    target=d['articles'][0]['read_parent_action'];v=decision(d,'READ_PARENT',target)
    with pytest.raises(ValidationError):i.validate(v,d,a)
    v['exploration']=[purpose(d,target)];i.validate(v,d,a)
    bad=deepcopy(v);bad['exploration'][0]['request_quote']='별도 업무 조사'
    with pytest.raises(ProposalError,match='request quote'):i.validate(bad,d,a)
    bad=deepcopy(v);bad['exploration']*=2
    with pytest.raises(ProposalError,match='every selected target'):i.validate(bad,d,a)
    bad=deepcopy(v);bad['exploration'][0]['missing_need']=' '
    with pytest.raises(ProposalError,match='unmet'):i.validate(bad,d,a)
    apply(i,v,d,a)
    d,a=i.view();i.validate(decision(d,'FINISH'),d,a)


def test_dependency_needs_actual_delivered_clause_and_selected_issue():
    d={'completion_contract':cc.V6,'issues':[{'id':'Q1','request_quote':'기준과 예외'}],
       'investigation_scope':{'request':'배경 설명. 기준과 예외'},'sources':[{'text':'제2조의 예외에 따른다.'}]}
    v={'targets':['T1'],'issue_refs':['Q1'],'exploration':[purpose(d,'T1','DEPENDENCY')]}
    with pytest.raises(ProposalError,match='original clause'):scope.validate(v,d)
    v['exploration'][0]['source_quote']='제2조의 예외에 따른다.';scope.validate(v,d)
    v['issue_refs']=[]
    with pytest.raises(ProposalError,match='issue_refs'):scope.validate(v,d)


@pytest.mark.parametrize('text,kind',[
 ('보고하여야 한다.','OBLIGATION'),('허가를 받아야 한다.','OBLIGATION'),
 ('신고를 갈음할 수 있다.','PERMISSION'),('신청할 수 있으며','PERMISSION'),
 ('양도하여서는 아니 된다.','PROHIBITION'),('이를 할 수 없다.','PROHIBITION'),
 ('신고한다.','UNSPECIFIED'),('해야 하는 것은 아니다.','UNSPECIFIED'),
 ('허가를 받아야 한다. 다만 신고로 갈음할 수 있다.','UNSPECIFIED')])
def test_explicit_source_modality_does_not_guess_mixed_or_unmarked_text(text,kind):
    assert v6.source_modality(text)=='UNSPECIFIED'


def v6_proposal(ids=('S1',),quote='신고를 갈음할 수 있다.',kind='PERMISSION'):
    out=proposal(ids);c=out['claims'][0];c['content_contract']='source-modality-v1'
    c.update(conclusion=quote,details=[{'text':quote,'evidence_refs':list(ids)}])
    c['rule']['norms']=[{'kind':kind,'text':quote,'source_quote':quote,'evidence_refs':list(ids)}]
    del c['rule']['obligations'];c['rule'].update(condition_tree=None,exceptions=[])
    return out


def test_model_modal_judgment_is_preserved_and_wrong_selected_span_is_rejected():
    p=v6_proposal();o=[{'id':'S1','source_id':'s','text':'신고를 갈음할 수 있다.'}]
    v6.verify_modalities(p,o)
    bad=deepcopy(p);bad['claims'][0]['rule']['norms'][0]['kind']='OBLIGATION'
    v6.verify_modalities(bad,o)  # Semantic interpretation remains the model's judgment.
    bad=deepcopy(p);bad['claims'][0]['rule']['norms'][0]['text']='신고를 갈음하여야 한다.'
    v6.verify_modalities(bad,o)
    bad=deepcopy(p);bad['claims'][0]['rule']['norms'][0]['source_quote']='신고를 생략할 수 있다.'
    with pytest.raises(ProposalError,match='exact clause'):v6.verify_modalities(bad,o)


def test_v6_content_composes_once_and_tampered_durable_content_fails():
    p=v6_proposal();o=[{'id':'S1','source_id':'s','text':'신고를 갈음할 수 있다.'}];issues=[{'id':'Q1','question':'신고 대체'}]
    out,model=v6.prepare(p,v6.assessment_schema(issues,[],o,[]),issues,o,[])
    a=v6.materialize(out,o,issues,model);rendered=cc.compose(a,cc.default_plan(a))
    cc.verify_composition(a,rendered);v5.verify_content(rendered['claims'][0])
    assert rendered['text'].count('신고를 갈음할 수 있다.')==1 and '허용:' in rendered['text'] and '의무:' not in rendered['text']
    bad=deepcopy(rendered['claims'][0]);bad['text']=bad['text'].replace('허용:','의무:')
    with pytest.raises(ContractError):v5.verify_content(bad)
    bad=deepcopy(rendered['claims'][0]);bad['answer_content']['rule']['norms'][0]['kind']='OBLIGATION'
    with pytest.raises(ContractError):v5.verify_content(bad)
    c=deepcopy(p['claims'][0]);c['rule']['condition_tree']={'mode':'LEAF','text':c['conclusion'],'evidence_refs':['S1']}
    assert v6.render_content(c).count(c['conclusion'])==1 and '허용:' in v6.render_content(c)


def test_v5_historical_content_renderer_unchanged():
    c=proposal()['claims'][0];before=v5.compile_claim(c)
    assert '의무: 승인 후 보고한다.' in before['text']
    v5.verify_content(before)


def test_scoped_heading_miss_preserves_document_and_acl():
    from semantic_runtime.legal_agent import structure_query as sq
    matcher=S(stored_coordinates={('d','1'):object()},document_names=S(match=lambda _:[]),title_keys=set(),structures=S(match=lambda _:[]))
    assert sq.resolve('존재하지 않는 제목',matcher,['d'],document_id='d')['failure']['code']=='UNRESOLVED_HEADING'
    assert sq.resolve('없는 문서',matcher,['d'])['failure']['code']=='MISSING_DOCUMENT'
    assert sq.resolve('제1조',matcher,['d'],document_id='private')['failure']['code']=='OUTSIDE_SCOPE'


class FocusedTransport(ModernTransport):
    def __init__(self,reentry=False,reject_once=False):
        super().__init__();self.reentry=reentry;self.reject_once=reject_once;self.projected=[]
    def send_once(self,*,body,ticket):
        v=expand_cards(json.loads(body['messages'][1]['content'])['view']);phase=v.get('source_stage',v['phase'])
        if v.get('input_projection')=='compact-selection-source-v3':self.projected.append(phase)
        if phase.startswith('source-law-navigation-'):
            self.phases.append(phase)
            if self.reject_once:
                self.reject_once=False
                return wire({'unoffered':'T999999'})
            if v['sources'] or v.get('assessment_gaps'):
                out=decision(v,'FINISH')
                if v.get('assessment_gaps'):
                    out['branch_decisions']=[];g=v['assessment_gaps'][0]
                    out['gap_resolutions']=[{'gap_id':g['gap_id'],'status':'RESOLVED','reason':'이미 채택한 원문',
                       'basis_refs':[b['id'] for b in v['basis'] if b.get('branch_id')],'action_refs':[]}]
                return wire(out)
            target=next((c['read_action'] for law in v['laws'] for c in law.get('article_matches',[]) if c.get('read_action')),None)
            if target:out=decision(v,'READ_ARTICLES',target)
            else:
                card=next(c for law in v['laws'] for c in law.get('articles',[]) if c.get('read_parent_action'))
                out=decision(v,'READ_PARENT',card['read_parent_action'])
            out['exploration']=[purpose(v,out['targets'][0])]
            return wire(out)
        if phase.startswith('memory-assess'):
            self.phases.append(phase);out=v6_proposal([o['id'] for o in v['evidence_options']],quote='승인 후 보고한다.',kind='UNSPECIFIED')
            if self.reentry and not v['gap_history']:out['gaps']=[deepcopy(GAP)]
            return wire(out)
        return super().send_once(body=body,ticket=ticket)


@pytest.mark.parametrize('reentry,reject_once',[(False,False),(True,False),(False,True)])
def test_full_native_v6_publication_alias_repair_and_same_request_reuse(tmp_path,tree,reentry,reject_once):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen,idx=tree;t=FocusedTransport(reentry,reject_once)
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
       'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
          'completion_policy_version':cc.V6,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
       legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:{'user_id':'u','team_id':'t','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'v6','request_id':'r1'}
        result=ok(api.post('/v1/rag/ask',json=body));calls=len(t.phases)
        assert result['assembly']['term_agent']['completion_contract']==cc.V6
        assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
        assert result['answer']['text'].count('승인 후 보고한다.')==1
        assert len(result['assembly']['term_agent']['case']['judgment_refs'])==7
        again=ok(api.post('/v1/rag/ask',json=body))
        assert again['answer']==result['answer'] and len(t.phases)==calls
        assert t.projected and not any('compose' in p for p in t.phases)
        if reentry:assert t.phases.count('memory-assess')==2


def test_card_columns_match_canonical_persisted_json_order():
    view={'actions':[{'id':'T'+str(i),'action':'READ_ARTICLES','label':'원문 확인'} for i in range(8)]}
    persisted=json.loads(json.dumps(view,sort_keys=True))
    assert compact_cards(view)==compact_cards(persisted)


@pytest.mark.parametrize('quote,kind',[
    ('기재하지 않을 수 있다.','PERMISSION'),
    ('미리 이사회 의결을 거쳐야 한다.','OBLIGATION'),
    ('지정한 절차에 따라야 한다.','OBLIGATION'),
    ('보고서를 내야 한다.','OBLIGATION')])
def test_additional_explicit_endings_preserve_selected_clause(quote,kind):
    assert v6.source_modality(quote)=='UNSPECIFIED'
    v6.verify_modalities(v6_proposal(quote=quote,kind=kind),[{'id':'S1','text':quote}])


def test_uncertain_legal_effect_may_remain_unspecified_without_modal_reversal():
    quote='시장 여건에 따라 이익이 감소할 수 있다.'
    p=v6_proposal(quote=quote,kind='UNSPECIFIED')
    v6.verify_modalities(p,[{'id':'S1','text':quote}])
    assert '규정:' in v6.render_content(p['claims'][0])
    p['claims'][0]['rule']['norms'][0]['text']='이익이 감소하여야 한다.'
    v6.verify_modalities(p,[{'id':'S1','text':quote}])


@pytest.mark.parametrize('version', [cc.V5, cc.V7])
@pytest.mark.parametrize('fresh_content', [True, False])
def test_completed_recall_refreshes_only_new_content_before_stop(session, version, fresh_content):
    from copy import deepcopy
    from test_main50_request_repair import modern
    from semantic_runtime.legal_agent import law_navigation as ln, request_repair as rr
    native, _ = session
    seed = modern(native)
    seed.s.profile['candidate_navigation']['completion_policy_version'] = version
    seed = ln.Investigation(seed.s, seed.question, seed.record, None, 120, None, None)
    state = deepcopy(seed.p)
    if fresh_content:
        # Previous completed catalogue had no candidates; the requested recall
        # now returns the fixture's authorized source. No invented source/ID.
        state['laws'] = {}; state['groups'] = {}; state['structure_page']['items'] = []
        state['request_progress'] = []
        rr.record_progress(state)
    prior = set(state['request_progress'])
    limit = seed.s.profile['max_no_progress']
    state.update(awaiting_search=True, no_progress=limit)
    state['catalogue']['query_fingerprint'] = 'previous-query'
    saved = []
    budget = deepcopy(seed.s.repo.budget())
    resumed = ln.Investigation(seed.s, seed.question, seed.record, None, 120, state,
        lambda value: saved.append(deepcopy(value)))
    assert resumed.p['no_progress'] == (0 if fresh_content else limit)
    assert prior <= set(resumed.p['request_progress'])
    assert resumed.p['read_state'] == state['read_state']
    assert seed.s.repo.budget() == budget
    assert saved and saved[-1]['no_progress'] == resumed.p['no_progress']
    assert 'awaiting_search' not in saved[-1]
    def reached(*args):
        raise RuntimeError('next native decision reached')
    resumed.invoke = reached
    if fresh_content:
        with pytest.raises(RuntimeError, match='next native decision reached'):
            resumed.run()
        # Even another query fingerprint cannot credit identical content again.
        again = deepcopy(saved[-1]); again.update(awaiting_search=True, no_progress=limit)
        again['catalogue']['query_fingerprint'] = 'another-query'
        repeated = ln.Investigation(seed.s, seed.question, seed.record, reached, 120, again, None)
        assert repeated.p['no_progress'] == limit
        assert repeated.p['request_progress'] == saved[-1]['request_progress']
        repeated.run()
        assert repeated.p['stop_reason'] == 'NO_PROGRESS'
    else:
        resumed.run()
        assert resumed.p['stop_reason'] == 'NO_PROGRESS'



def test_direct_annotation_cannot_replace_request_or_dependency_evidence():
    d={'completion_contract':cc.V7,'issues':[{'id':'Q1','request_quote':'기준과 예외'}],
       'investigation_scope':{'request':'배경 설명. 기준과 예외'},'sources':[]}
    v={'targets':['T1'],'issue_refs':['Q1'],'exploration':[purpose(d,'T1','DIRECT')]}
    v['exploration'][0]['source_quote']='미열람 미확인 메모'
    scope.validate(v,d)
    v['exploration'][0]['relation']='DEPENDENCY'
    with pytest.raises(ProposalError,match='original clause'):scope.validate(v,d)
    v['exploration'][0].update(relation='DIRECT',request_quote='배경 설명')
    with pytest.raises(ProposalError,match='explicit issue'):scope.validate(v,d)



@pytest.mark.parametrize('quote,kind', [('해당 금액을 수입에 산입한다.','OBLIGATION'),('위 규정을 준용한다.','PERMISSION')])
def test_unmarked_clause_is_not_proof_of_contextual_modality_error(quote,kind):
    p=v6_proposal(quote=quote,kind=kind)
    options=[{'id':'S1','source_id':'s','text':quote}]
    assert v6.source_modality(quote)=='UNSPECIFIED'
    v6.verify_modalities(p,options)
    # Acceptance is not a certification of legal classification.
    assert p['claims'][0]['rule']['norms'][0]['kind']==kind


def test_unmarked_clause_still_requires_exact_selected_original():
    p=v6_proposal(quote='해당 금액을 수입에 산입한다.',kind='OBLIGATION')
    with pytest.raises(ProposalError,match='exact clause'):
        v6.verify_modalities(p,[{'id':'S1','source_id':'s','text':'서로 다른 원문이다.'}])


@pytest.mark.parametrize('annotation', ['', '모델이 바꾼 인용', '다른 미확인 문장'])
def test_dependency_selects_delivered_identity_without_rewriting(annotation):
    from semantic_runtime.legal_agent import investigation_scope as scope
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    from jsonschema import validate
    ident='E'+'a'*24
    view={'completion_contract':cc.V8,'issues':[{'id':'Q1','request_quote':'예외를 설명해 주세요'}],
          'sources':[{'id':ident,'text':'제2조의 예외에 따른다.'}],
          'basis':[{'id':'V-retained','source_id':'old-source'}]}
    scope.annotate(view,'예외를 설명해 주세요')
    row={'target':'T1','issue_id':'Q1','request_quote':'예외를 설명해 주세요',
         'missing_need':'제2조 예외 원문','relation':'DEPENDENCY','source_ref':ident,'source_quote':annotation}
    schema=scope.schema(view,{'T1'});validate([row],schema)
    codec=NavigationReferences(view);wire=codec.schema(schema)
    decoded=codec.decode(codec.view([row]),wire)
    assert decoded==[row]
    value={'targets':['T1'],'issue_refs':['Q1'],'exploration':decoded}
    before=deepcopy(view);scope.validate(value,view);assert view==before


@pytest.mark.parametrize('ref',['E-unread','V-retained'])
def test_dependency_rejects_unread_identity_even_with_valid_looking_quote(ref):
    from semantic_runtime.legal_agent import investigation_scope as scope
    view={'completion_contract':cc.V8,'issues':[{'id':'Q1','request_quote':'예외 확인'}],
          'sources':[{'id':'E-current','text':'제2조 예외.'}], 'basis':[{'id':'V-retained'}]}
    scope.annotate(view,'예외 확인')
    row={'target':'T1','issue_id':'Q1','request_quote':'예외 확인','missing_need':'제2조',
         'relation':'DEPENDENCY','source_ref':ref,'source_quote':'제2조 예외.'}
    with pytest.raises(ProposalError):scope.validate({'targets':['T1'],'issue_refs':['Q1'],'exploration':[row]},view)


def test_dependency_identity_requires_nonempty_current_original():
    from semantic_runtime.legal_agent import investigation_scope as scope
    view={'completion_contract':cc.V8,'issues':[{'id':'Q1','request_quote':'예외 확인'}],
          'sources':[{'id':'E-current','text':''}]}
    scope.annotate(view,'예외 확인')
    row={'target':'T1','issue_id':'Q1','request_quote':'예외 확인','missing_need':'제2조',
         'relation':'DEPENDENCY','source_ref':'E-current','source_quote':''}
    assert scope.schema(view,{'T1'})['items']['properties']['source_ref']['enum']==[None]
    with pytest.raises(ProposalError):scope.validate({'targets':['T1'],'issue_refs':['Q1'],'exploration':[row]},view)


def test_scope_identity_schema_only_offers_current_delivered_sources():
    from semantic_runtime.legal_agent import investigation_scope as scope
    view={'completion_contract':cc.V8,'issues':[{'id':'Q1'}],
          'sources':[{'id':'E-current','text':'원문'},{'id':'E-empty','text':''}],
          'basis':[{'id':'V-retained'}]}
    assert scope.schema(view,{'T1'})['items']['properties']['source_ref']['enum']==[None,'E-current']


def test_older_scope_contract_keeps_exact_quote_language():
    from semantic_runtime.legal_agent import investigation_scope as scope
    view={'completion_contract':cc.V7,'issues':[{'id':'Q1'}],'sources':[{'id':'E-current','text':'원문'}]}
    assert 'source_ref' not in scope.schema(view,{'T1'})['items']['properties']


@pytest.mark.parametrize('explicit,entry,expected,origin',[
    (None,{'mode':'STRUCTURE'},['자본시장법 금융 업무 재산 검사'],'accepted_request_queries'),
    (['자본시장법 신규 탐색'],{'mode':'FULLTEXT'},['자본시장법 신규 탐색'],'selected_search_queries')])
def test_selected_query_does_not_reinsert_excluded_raw_coordinate(explicit,entry,expected,origin):
    from semantic_runtime.legal_agent.law_candidates import search_queries
    s=S(context=S(request={'question':'업무 검사, 제310조는 제외'}),entry_search=entry,law_search_queries=explicit)
    queries,actual=search_queries(s,{'queries':['자본시장법 금융 업무 재산 검사']})
    assert queries==expected and actual==origin and all('310' not in q for q in queries)


def test_no_entry_preserves_selected_query_without_raw_expansion():
    from semantic_runtime.legal_agent.law_candidates import search_queries
    s=S(context=S(request={'question':'제310조 검사'}))
    queries,origin=search_queries(s,{'queries':['검사'],'law_names':[]})
    assert origin=='request_query_fallback' and queries==['검사']


def title_matcher():
    from test_structure_first_search import matcher
    m=matcher()
    m.units[('law','제6조')].update(title='선임',span=[0,10])
    m.structures.add('선임',{'document_id':'law','unit_id':'제6조','kind':'TITLE'})
    m.units[('law','제6조의2')].update(title='회사의 업무, 재산상태의 검사',span=[20,30])
    return m


def test_metadata_title_variant_ranks_before_short_literal_and_pages_without_loss():
    from semantic_runtime.legal_agent.structure_query import catalogue
    m=title_matcher();kw={'queries':['자본시장법 회사 업무 재산상태 검사 선임'],'limit':1}
    first=catalogue(m,['law','decree'],**kw)
    assert first['items'][0]['unit_id']=='제6조의2'
    assert first['navigation_hint_only'] and not first['citation_eligible']
    assert not first['items'][0]['content_read']
    second=catalogue(m,['law','decree'],offset=first['next_offset'],**kw)
    assert second['items'][0]['unit_id']=='제6조'


def test_metadata_title_overlap_preserves_exact_coordinate_and_scope():
    from semantic_runtime.legal_agent.structure_query import catalogue
    m=title_matcher()
    got=catalogue(m,['law','decree'],queries=['자본시장법 제6조 회사 업무 재산상태 검사'])
    assert [r['unit_id'] for r in got['items']]==['제6조']
    assert catalogue(m,['decree'],queries=['자본시장법 회사 업무 재산상태 검사'])['items']==[]
    assert catalogue(m,['law','decree'],queries=['회사 업무 재산상태 검사'])['items']==[]


def test_metadata_title_candidates_keep_ambiguous_originals_non_executable():
    from semantic_runtime.legal_agent.structure_query import catalogue
    m=title_matcher();m._unit_sources=lambda did,uid:['a','b']
    row=next(r for r in catalogue(m,['law'],queries=['자본시장법 회사 업무 재산상태 검사'])['items'] if r['kind']=='structure')
    assert not row['source_binding_unique'] and row['source_id'] is None


def test_selected_fulltext_route_receipt_is_acyclic_and_no_raw_reinsertion(session):
    from semantic_runtime.legal_agent.source_recall import SourceRecall
    i=modern(session[0]);s=i.s
    s.entry_search={'mode':'FULLTEXT'}
    s.recall_query_plan={'queries':['승인 기준'], 'law_names':[]}
    s.context.request['question']='승인 기준; 제310조는 제외'
    selected,rec=SourceRecall(s).discover()
    assert rec['law_navigation']['route_queries']==['승인 기준']
    assert rec['law_navigation']['query_origin']=='accepted_request_queries'
    json.dumps(rec,ensure_ascii=False)


def test_heading_hints_skip_nullable_and_unresolved_metadata():
    from semantic_runtime.legal_agent.structure_query import catalogue
    m=title_matcher()
    m.stored_coordinates[('law','heading-only')]=None
    m.units[('law','heading-only')]={'title':'회사 업무 재산상태 검사','coordinate_scope':'body'}
    got=catalogue(m,['law'],queries=['자본시장법 회사 업무 재산상태 검사'])
    rows=[r for r in got['items'] if r['kind']=='structure']
    assert rows[0]['unit_id']=='제6조의2'
    assert not any(r['unit_id']=='heading-only' for r in rows)
