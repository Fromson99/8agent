from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from test_navigation_delivery_recovery import tree, session, ready, delivery
from conftest import term_glossary
from semantic_runtime.legal_agent import evidence_inventory as inventory, connection_scope as cs
from semantic_runtime.legal_agent.errors import ContractError


def adopted_and_delivered(session):
    inv,data,_=ready(session)
    page=deepcopy(data['sources'][0]);assert len(page['spans'])>1
    accepted=deepcopy(page);accepted['id']+='-prior';accepted['spans']=accepted['spans'][:1]
    inventory.acknowledge(inv.s,inv.p,accepted,data['presentation_id'])
    group=inv.p['groups'][page['branch_id']]
    group.update(status='ACTIVE',issue_decisions={'Q1':{'status':'ADOPT','basis_refs':[accepted['id']]}})
    delivery(inv,data);inventory.reconcile_delivery(inv.s,inv.p,data,'source-law-navigation-2')
    return inv,data,page


@pytest.mark.parametrize('reason',['MODEL_DECISION_UNRESOLVED','INVESTIGATION_BUDGET','NO_PROGRESS'])
def test_prior_adoption_does_not_hide_later_delivered_spans(session,reason):
    inv,data,page=adopted_and_delivered(session);budget=dict(inv.s.repo.budget());prior=deepcopy(inv.p['basis_history'])
    result=inv.bounded_result(reason)
    actual={p['block_id'] for o in result['selected_originals'] for p in o['adopted_spans']}
    assert {p['block_id'] for p in page['spans']} <= actual
    assert inv.p['basis_history']==prior and inv.s.repo.budget()==budget
    assert not result['evidence_sufficient'] and result['answer_coverage']=='UNASSESSED'
    assert inv.bounded_result(reason)['selected_originals']==result['selected_originals']


@pytest.mark.parametrize('mutation',['scope','bytes'])
def test_additional_delivery_is_checked_even_with_prior_adoption(session,mutation):
    inv,data,page=adopted_and_delivered(session)
    if mutation=='scope':inv.s.scope=[]
    else:next(iter(inv.p['delivery_history'].values()))['spans'][-1]['text']+='변조'
    with pytest.raises(ContractError):inv.bounded_result('MODEL_DECISION_UNRESOLVED')


@pytest.mark.parametrize('status,count',[('COMPLETE',5),('PARTIAL',6),('FAILED',0)])
def test_verified_partial_connections_remain_directly_selectable(monkeypatch,status,count):
    from test_selected_connection_scope import fixture
    inv,add=fixture(monkeypatch);page=add('a','s',6,[6]);inv.bind_reference_delivery=lambda **kw:None
    from semantic_runtime.legal_agent import law_candidates
    monkeypatch.setattr(law_candidates,'token',lambda *args:'follow')
    scope=cs.candidates(inv,{'sources':[page]})[0][0]
    cs.accept(inv,scope,{'sources':[page]},'선택한 범위의 연결 확인')
    monkeypatch.setattr(cs,'preview',lambda *a:{'status':status,'connection_count':count,'groups':[{'connections':[{'id':str(i)} for i in range(count)]}],'limits':[],'absence_proven':False})
    def cards(inv,scope,refs,groups,actions):
        result=[]
        for g in groups:
            for c in g['connections']:
                key='read-'+c['id'];actions[key]={'id':key,'action':'READ_ARTICLES','label':key}
                result.append({'read_action':key,'target':{'source_id':'s'},'target_scope':{'block_ids':['6']}})
        return result
    monkeypatch.setattr(cs,'inline_cards',cards)
    actions={};data={'sources':[page],'references':{}}
    cs.offer_choices(inv,data,actions)
    shown=data['references']['dependency_cards']
    assert len(shown)==count
    if status=='PARTIAL':
        assert data['connection_scope_choices'][0]['connections_presented_inline']
        assert any(a['action']=='FOLLOW_CONNECTION' for a in actions.values())
    if status=='FAILED':assert not actions


def test_failed_choice_delivery_is_retained_on_the_next_view_without_adoption(session):
    from semantic_runtime.legal_agent import decision_projection as dp
    inv,data,page=adopted_and_delivered(session)
    next_view={'sources':[],'basis':[]}
    prior=deepcopy(inv.p['basis_history'])
    dp.retain_requested(inv,next_view)
    assert page['id'] in [p['id'] for p in next_view['sources']]
    assert inv.p['basis_history']==prior
    context=inventory.originals_for(inv.s,inv.p,context_refs=dp.requested_refs(inv.p))
    assert {p['block_id'] for p in page['spans']} <= {p['block_id'] for s in context for p in s['adopted_spans']}


def test_reference_menu_pages_whole_sources_and_keeps_anchor_bytes():
    from semantic_runtime.legal_agent import unit_relations as rel
    groups={str(i):{'anchor':{'source_id':'anchor'},'target':{'source_id':str(i)},'direction':'OUTGOING','connections':[]} for i in range(3)}
    data={'groups':[{'id':str(i),'text':'x'*400} for i in range(3)],'omitted_groups':0,
          'all_group_summaries':[], 'sources':[{'source_id':'anchor','text':'필수 원문'}, {'source_id':'other','text':'a'*6000}]}
    before=deepcopy(data)
    shown,offered=rel.fit_context(data,groups,1200)
    import json
    assert len(json.dumps(shown,ensure_ascii=False))<=1200
    assert shown['sources']==[data['sources'][0]] and shown['original_context_omissions']['still_acquired']
    assert shown['omitted_groups']==3-len(offered) and len(offered)>=1
    assert data==before and len(groups)==3


def test_oversized_anchor_is_never_silently_truncated():
    from semantic_runtime.legal_agent import unit_relations as rel
    g={'x':{'anchor':{'source_id':'anchor'},'target':{},'connections':[]}}
    d={'groups':[{'id':'x'}],'sources':[{'source_id':'anchor','text':'원문'*4000}], 'omitted_groups':0}
    shown,offered=rel.fit_context(d,g,1000)
    assert shown==d and offered==g


@pytest.mark.parametrize('changed', [False, True])
def test_same_oversized_menu_is_not_reoffered_but_new_originals_can_reopen_it(monkeypatch,changed):
    from test_selected_connection_scope import fixture
    from semantic_runtime.legal_agent import law_candidates
    inv,add=fixture(monkeypatch);page=add('a','s',6,[6]);inv.bind_reference_delivery=lambda **kw:None
    monkeypatch.setattr(law_candidates,'token',lambda *args:'follow')
    scope=cs.candidates(inv,{'sources':[page]})[0][0]
    cs.accept(inv,scope,{'sources':[page]},'선택한 범위의 연결 확인')
    inv.p['connection_context_blocks']={scope['id']:{'acquired_signature':cs.acquired_signature(inv),
        'reason':'reference_context_limit','absence_proven':False,'fallback':'SEARCH_STRUCTURE'}}
    if changed:add('b','other',10,[10])
    monkeypatch.setattr(cs,'preview',lambda *a:{'status':'PARTIAL','connection_count':6,
        'groups':[],'limits':[],'absence_proven':False})
    data={'sources':[page],'references':{}};actions={}
    cs.offer_choices(inv,data,actions)
    assert ('follow' in actions) is changed
    assert bool(data['connection_scope_choices'][0]['menu_unavailable']) is (not changed)
    assert not data['connection_scope_choices'][0]['connection_preview']['absence_proven']



def test_directory_overflow_never_hides_the_late_targets():
    from semantic_runtime.legal_agent import unit_relations as rel
    groups={str(i):{'anchor':{'source_id':'a'},'target':{'source_id':str(i)}} for i in range(12)}
    data={'groups':[{'id':str(i),'text':'인용문'*100} for i in range(12)],
          'sources':[{'source_id':'a','text':'선택 원문'}], 'omitted_groups':0,
          'connection_directory':{'listed_groups':12,'catalog_complete':False}}
    shown,offered=rel.fit_context(data,groups,1000)
    assert list(offered)==list(groups) and shown==data
