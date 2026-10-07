"""Synthetic clause obligations and native scope/READ regressions; no LLM."""
import pytest
from semantic_runtime.legal_agent.relation_read_policy import classify, validate_decision
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent import unit_relations as rel
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.unit_reading import ensure_context, read
from test_batch_reference_navigation import connected, initial


def reference(tail, **extra):
    mention = '제1조제1항'
    return {'source_text': mention + tail, 'mention_start': 0, 'mention_end': len(mention),
            'mention_text': mention, 'locator': mention, 'reference_role': 'CITES', **extra}


@pytest.mark.parametrize('tail,kind,outgoing,incoming', [
    ('을 준용한다.', 'APPLIES_MUTATIS_MUTANDIS', 'REQUIRED', 'OPTIONAL'),
    ('에 따른 보고서다.', 'CITES', 'OPTIONAL', 'OPTIONAL'),
    (' 단서에서 대통령령으로 정하는 경우란 다음 각 호다.', 'SPECIFIES_DELEGATED_CASES_OF', 'CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    ('에도 불구하고 적용하지 아니한다.', 'EXCLUDES', 'CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    ('의 정의에 따른다.', 'USES_DEFINITION', 'REQUIRED', 'OPTIONAL'),
    ('의 예외로 한다.', 'HAS_EXCEPTION', 'CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    ('으로 본다.', 'DEEMS', 'CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    (' 위반은 과태료를 부과한다.', 'VIOLATION_SANCTIONED_BY', 'CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    (' 시행 이후에 적용한다.', 'TEMPORAL', 'CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
])
def test_direction_and_wording_determine_obligation(tail, kind, outgoing, incoming):
    for direction, obligation in [('OUTGOING', outgoing), ('INCOMING', incoming)]:
        policy = classify(reference(tail), direction, {})
        assert (policy['kind'], policy['obligation']) == (kind, obligation)
        assert not policy['canonical_approval']


def test_legacy_whole_frame_role_is_not_an_applicability_verdict():
    ref = reference('에 따른 보고다. 제2조를 준용한다.', reference_role='APPLIES_MUTATIS_MUTANDIS')
    assert classify(ref, 'INCOMING', {})['kind'] == 'CITES'
    ref = reference('과 제2조를 준용한다.')
    assert classify(ref, 'OUTGOING', {})['kind'] == 'UNKNOWN'


@pytest.mark.parametrize('locator,kind', [('별표 1','ANNEX_STANDARD'),('별지 제1호서식','ANNEX_FORM')])
def test_annex_reference_does_not_force_reverse_read(locator,kind):
    ref = reference('에 따른다.', locator=locator, origins=['raw_explicit_annex_hint'])
    assert classify(ref, 'OUTGOING', {})['kind'] == kind
    assert classify(ref, 'INCOMING', {})['obligation'] == 'OPTIONAL'


def group(obligation='REQUIRED', already=False):
    return {'connections': [{'reading_policy': {'obligation':obligation}, 'already_read':already,
                             'required_block_ids':['1','2']}],
            'read_blocks':set(), 'offers':{'small':({}, {'block_ids':['1']}),
                                         'full':({}, {'block_ids':['1','2']})}}


def test_required_read_cannot_be_skipped_or_truncated():
    for decision in [{'action':'SKIP','scopes':[]}, {'action':'FOLLOW','scopes':['small']}]:
        with pytest.raises(ValueError): validate_decision(decision,group())
    validate_decision({'action':'FOLLOW','scopes':['full']},group())
    validate_decision({'action':'DEFER','scopes':[]},group())


def test_conditional_skip_requires_explicit_inapplicability():
    value={'action':'SKIP','scopes':[]}
    with pytest.raises(ValueError):validate_decision(value,group('CHECK_APPLICABILITY'))
    validate_decision({**value,'applicability':'DOES_NOT_APPLY',
        'applicability_reason':'질문은 지정 주체이며 해당 연결은 신고서 작성 절차만 정한다.'},group('CHECK_APPLICABILITY'))
    validate_decision(value,group(already=True))


@pytest.mark.parametrize('connected', ['① 「모의승인규정」 제1조제1항을 준용한다.'], indirect=True)
def test_native_required_target_scope_and_rejected_skip_are_audited(connected):
    s,_=connected
    src=next(v for v in s.tools.sources.values() if v['document_id']=='detail')
    hit=rel.hit_for(s,src['id'],'1'); state={'count':0,'chars':0}
    own=next(o for o in rel.offer_plan(s,hit)[0] if o['id']=='exact:1')
    selected={'U1':read(s,hit,own,action_state=state)}
    groups,_,_,_=rel.catalog(s,[src['id']],selected,set())
    g=next(g for g in groups if g['target']['document_id']=='d')
    assert g['connections'][0]['reading_policy']['obligation']=='REQUIRED'
    with pytest.raises(ContractError,match='declared endpoint'):
        rel.validate({'decisions':[{'id':'R','action':'FOLLOW','scopes':[next(k for k in g['offers'] if k.startswith('exact:'))],'reason':'불완전'}]}, {'R':g})
    calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        return {'decisions':[{'id':g['id'],'action':'DEFER' if phase.endswith('repair') else 'SKIP',
            'scopes':[],'reason':'추가 확인 필요'} for g in data['groups']], 'needs_more':False}
    result=rel.navigate('준용한 승인 기준',s,selected,invoke,read_state=state,
        seconds_left=lambda:120,max_context_chars=80000)
    assert calls==['source-reference-batch-1','source-reference-choice-repair']
    assert result['pending'] and not any(a['source_id'] != src['id'] for a in result['actions'])


@pytest.mark.parametrize('connected', ['① 「모의승인규정」 제1조제1항 단서에서 대통령령으로 정하는 경우란 다음 각 호를 말한다.'], indirect=True)
def test_native_reverse_proviso_detail_requires_applicability_review(connected):
    s,_=connected;record,sid=initial(s)
    selected={'U1':record['unit_reads'][0]}
    groups,_,_,_=rel.catalog(s,[sid],selected,set())
    g=next(g for g in groups if g['target']['document_id']=='detail')
    assert g['direction']=='INCOMING'
    assert g['connections'][0]['reading_policy']['kind']=='SPECIFIES_DELEGATED_CASES_OF'
    with pytest.raises(ContractError,match='inapplicability'):
        rel.validate({'decisions':[{'id':'R','action':'SKIP','scopes':[],'reason':'역방향'}]}, {'R':g})


def test_ancestor_intro_is_read_once_without_unrelated_siblings(connected):
    s,_=connected;record,sid=initial(s)
    selected={'U1':record['unit_reads'][0]}; state={'count':len(record['actions']),'chars':record['source_chars']}
    ensure_context(s,selected,state);count=state['count'];ensure_context(s,selected,state)
    assert count==state['count']
    blocks={p['block_id'] for r in selected.values() for e in r['evidence'] for p in e['spans']}
    assert blocks=={'0','1','2'} and '3' not in blocks


def test_repeated_closed_scope_reuses_verified_evidence_without_read_actions(connected):
    s,_=connected;record,_=initial(s);r=record['unit_reads'][0]
    state={'count':len(record['actions']),'chars':record['source_chars']};before=dict(state)
    reused=read(s,r['hit'],r['offer'],action_state=state)
    assert reused['complete'] and not reused['actions']
    assert all(state[k]==v for k,v in before.items()) and state['sequence']==record['read_state']['sequence']
    assert reused['text']==r['text'] and reused['evidence_ids']==r['evidence_ids']


def test_article_only_fts_uses_minimal_read_and_defers_reference_acquisition(connected, monkeypatch):
    s,_=connected;s.matcher.unit_fulltext=None
    monkeypatch.setattr(s.repo, 'VERSION', 6)
    record=SourceRecall(s).prepare()
    assert record['unit_read_contract']=='unit-read-v1' and s.batch_reference_navigation
    assert all(a['action']['args']['extent']=='exact' for a in record['actions'])
    assert not any(r.get('kind')=='reference' for rs in record['routes'].values() for r in rs)


@pytest.mark.parametrize('last_obligation,expected_pending', [('OPTIONAL',False),('REQUIRED',True)])
def test_optional_menu_overflow_does_not_force_another_fulltext_pass(connected, monkeypatch, last_obligation, expected_pending):
    import copy
    s,_=connected;record,sid=initial(s);selected={'U1':record['unit_reads'][0]}
    template=rel.catalog(s,[sid],selected,set())[0][0]
    groups=[]
    for i in range(rel.LIMITS['groups_per_batch']+1):
        g=copy.deepcopy(template);g['key']=str(i)
        for c in g['connections']:c['reading_policy']['obligation']='OPTIONAL'
        groups.append(g)
    groups[-1]['connections'][0]['reading_policy']['obligation']=last_obligation
    monkeypatch.setattr(rel,'catalog',lambda *args:(groups,[],[],[]))
    def invoke(system,data,schema,phase,timeout):
        return {'decisions':[{'id':g['id'],
            'action':'DEFER' if any(o['obligation']=='REQUIRED' for o in g['reading_obligations']) else 'SKIP',
            'scopes':[],'reason':'필수 연결은 확인 보류, 선택 인용은 질문과 무관함',
            'applicability':'UNDETERMINED','applicability_reason':'모의 필수 연결은 확인 보류'}
            for g in data['groups']], 'needs_more':False}
    out=rel.navigate('승인 주체',s,selected,invoke,read_state={'count':len(record['actions']),'chars':record['source_chars']},
        seconds_left=lambda:120,max_context_chars=80000)
    assert out['pending']==expected_pending
