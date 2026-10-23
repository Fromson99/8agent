from copy import deepcopy
import json
from types import SimpleNamespace as S
import pytest
from conftest import term_glossary
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import connection_scope as cs, unit_relations as rel, decision_projection as dp
from semantic_runtime.legal_agent.errors import ContractError
from test_batch_reference_navigation import connected, initial, decision
from test_read_choice_input_preservation import capture, wire


def inline_fixture(monkeypatch, count):
    scope = cs._scope('모의법 제92조②1호', {'unit_id':'item'},
        [{'source_id':'a','document_id':'d','spans':[{'block_id':'item','start_cp':0,'end_cp':1,'text':'원'}]}])
    groups=[]
    for i in range(count):
        target={'source_id':f't{i}','document_id':'d','document_name':'모의법','heading':f'제{i+1}조','unit_id':str(i)}
        option={'id':f'subtree:{i}','unit_id':str(i),'extent':'subtree','block_ids':[str(i)]}
        connection={'reference_id':f'r{i}','witness':'명시 참조','witness_sha256':f'h{i}',
            'witness_document_id':'d','witness_block_id':'item','witness_chars':5,'witness_truncated':False,
            'endpoint_block_ids':[str(i)],'required_block_ids':[str(i)],'endpoint_scopes':[option['id']],
            'reading_policy':{'obligation':'REQUIRED'},'resolution':'EXACT_STRUCTURE','already_read':False}
        groups.append({'key':f'g{i}','anchor':{'source_id':'a','document_id':'d','document_name':'모의법'},'target':target,'direction':'OUTGOING',
            'connections':[connection],'offers':{option['id']:({'unit_id':str(i),'source_id':f't{i}','document_id':'d'},option)}})
    events=[]
    inv=S(modern=True,policy={'selected_connection_scope':True},question='사용자 질문',
        p={'binding':{'generation':'g'},'issues':[{'id':'Q1'}]},
        s=S(scope=['d'],repo=S(event=lambda *args:events.append(args))),save=lambda:None,
        bind_reference_delivery=lambda **kw:None,read_records=lambda:{},
        closed_reference_decisions=lambda *args:{})
    monkeypatch.setattr(cs,'candidates',lambda inv,data:[(scope,['E1'])])
    monkeypatch.setattr(cs,'current',lambda inv,**kw:{'scope':scope})
    monkeypatch.setattr(rel,'catalog',lambda *args,**kwargs:(deepcopy(groups),[],[],[]))
    monkeypatch.setattr(cs.ur,'unit_label',lambda s,h:'제'+h['unit_id']+'조')
    from semantic_runtime.legal_agent import law_candidates
    monkeypatch.setattr(law_candidates,'token',lambda s,p,v:p+digest(v)[:10])
    data={'sources':[{'id':'E1','text':'원문'}],'references':{}}
    return inv,data,{},groups,scope,events


@pytest.mark.parametrize('count',[0,1,5,6])
def test_explicitly_selected_scope_shows_bounded_connections(monkeypatch,count):
    inv,data,actions,groups,scope,_=inline_fixture(monkeypatch,count)
    cs.offer_choices(inv,data,actions)
    inline=count<=5
    assert len(data['references']['dependency_cards'])==min(count,5)
    assert any(a['action']=='FOLLOW_CONNECTION' for a in actions.values()) is (not inline)
    assert len([a for a in actions.values() if a['action']=='READ_ARTICLES'])==min(count,5)
    assert data['references']['selected_scope_id']==scope['id']
    for a in actions.values():
        if a['action']=='READ_ARTICLES':assert a['identity']['unit_id'] in [str(i) for i in range(count)]


def test_partial_catalog_is_never_called_zero_connections(monkeypatch):
    inv,data,actions,_,_,_=inline_fixture(monkeypatch,0)
    monkeypatch.setattr(rel,'catalog',lambda *a,**k:([],[],[{'kind':'edge_scan_limit'}],[]))
    cs.offer_choices(inv,data,actions)
    preview=data['connection_scope_choices'][0]['connection_preview']
    assert preview['status']=='PARTIAL' and not preview['absence_proven']
    assert any(a['action']=='FOLLOW_CONNECTION' for a in actions.values())


def test_transient_preview_is_preserved_and_not_retried(monkeypatch):
    inv,data,actions,_,_,events=inline_fixture(monkeypatch,1);calls=[]
    def fail(*a,**kw):calls.append(1);raise TimeoutError('synthetic timeout')
    monkeypatch.setattr(rel,'catalog',fail)
    cs.offer_choices(inv,data,actions);cs.offer_choices(inv,data,actions)
    assert len(calls)==1 and not actions
    preview=data['connection_scope_choices'][0]['connection_preview']
    assert preview['status']=='FAILED' and preview['fallback']=='SEARCH_STRUCTURE' and not preview['absence_proven']
    assert len(events)==1


def test_corrupt_preview_is_fatal_not_fallback(monkeypatch):
    inv,data,actions,_,_,_=inline_fixture(monkeypatch,1)
    def fail(*a,**kw):raise ContractError('reference witness mismatch')
    monkeypatch.setattr(rel,'catalog',fail)
    with pytest.raises(ContractError):cs.offer_choices(inv,data,actions)
    assert not inv.p.get('connection_preview_failures')


def test_scope_aliases_do_not_duplicate_inline_connections(monkeypatch):
    inv,data,actions,groups,scope,_=inline_fixture(monkeypatch,1)
    alias=cs._scope('동일 원문의 다른 선택',{'unit_id':'alias'},scope['members'])
    monkeypatch.setattr(cs,'candidates',lambda *a:[(scope,['E1']),(alias,['E1'])])
    cs.offer_choices(inv,data,actions)
    assert len(data['references']['dependency_cards'])==1
    assert len([a for a in actions.values() if a['action']=='READ_ARTICLES'])==1
    assert len([a for a in actions.values() if a['action']=='FOLLOW_CONNECTION'])==1


def test_already_acquired_target_is_presented_without_another_read(monkeypatch):
    inv,data,actions,groups,_,_=inline_fixture(monkeypatch,1)
    groups[0]['connections'][0]['already_read']=True
    cs.offer_choices(inv,data,actions)
    assert data['references']['dependency_cards'][0]['already_read'] and not actions


def test_source_only_endpoint_is_not_silently_lost(monkeypatch):
    inv,data,actions,groups,_,_=inline_fixture(monkeypatch,1)
    hit,offer=next(iter(groups[0]['offers'].values()))
    offer.update(unit_id=None,extent='exact',reader_target='source')
    cs.offer_choices(inv,data,actions)
    card=data['references']['dependency_cards'][0]
    assert actions[card['read_action']]['identity']['unit_id'] is None
    assert not any(a['action']=='FOLLOW_CONNECTION' for a in actions.values())


def test_non_subtree_endpoint_keeps_scope_menu_without_hiding_inline_link(monkeypatch):
    inv,data,actions,groups,_,_=inline_fixture(monkeypatch,1)
    next(iter(groups[0]['offers'].values()))[1]['extent']='exact'
    cs.offer_choices(inv,data,actions)
    card=data['references']['dependency_cards'][0]
    assert card['requires_scope_menu'] and actions[card['scope_menu_action']]['action']=='FOLLOW_CONNECTION'
    assert not any(a['action']=='READ_ARTICLES' for a in actions.values())


def test_inline_read_rechecks_witness_before_scope_selection(monkeypatch):
    inv,data,actions,groups,_,_=inline_fixture(monkeypatch,1)
    cs.offer_choices(inv,data,actions)
    identity=next(iter(actions.values()))['identity'];accepted=[]
    monkeypatch.setattr(cs,'accept',lambda *a,**k:accepted.append(1))
    cs.validate_inline_read(inv,identity,data,'사용자 질문에 필요한 원문')
    assert accepted==[1]
    groups[0]['connections'][0]['witness_sha256']='changed'
    with pytest.raises(ContractError):cs.validate_inline_read(inv,identity,data,'같은 참조 ID')
    assert accepted==[1]


@pytest.mark.parametrize('defect',[None,'generation','span','context_limit','resume'])
def test_reference_decision_keeps_background_originals_without_expanding_roots(connected,defect):
    s,_=connected;rec,sid=initial(s)
    src=next(v for v in s.tools.sources.values() if v['document_id']=='detail')
    hit=rel.hit_for(s,src['id'],'2')
    from semantic_runtime.legal_agent import unit_reading as ur
    extra=ur.read(s,hit,next(o for o in ur.offers(s,hit) if o['id']=='subtree:2'),action_state={'count':0,'chars':0})
    selected={'a':rec['unit_reads'][0]}
    spans=[p for e in rec['unit_reads'][0]['evidence'] for p in e['spans']]
    # Use the actually read parent range so the incoming connection is in scope.
    h=rel.hit_for(s,sid,'0');parent=ur.read(s,h,next(o for o in ur.offers(s,h) if o['id']=='subtree:0'),action_state={'count':0,'chars':0})
    selected['parent']=parent;spans=[p for e in parent['evidence'] for p in e['spans']]
    extra=deepcopy(extra)
    if defect=='generation':extra['evidence'][0]['generation_id']='other'
    if defect=='span':extra['evidence'][0]['spans'][0]['text']='변조'
    seen=[]
    def invoke(system,data,schema,phase,timeout):
        seen.append(deepcopy(data))
        assert data['question']=='긴급 승인 예외'
        assert any('책임자 확인' in x['text'] for x in data['sources'])
        assert {g['anchor']['source_id'] for g in data['groups']}=={sid}
        return decision(data)
    with cs.bound(s,{'members':[{'source_id':sid,'spans':spans}]}):
        state={};read_state={'count':0,'chars':0}
        args=dict(read_state=read_state,seconds_left=lambda:120,
            max_context_chars=1 if defect=='context_limit' else 80000,
            max_model_batches=1,context_reads={'extra':extra},state=state)
        if defect in ('generation','span'):
            with pytest.raises(ContractError):rel.navigate('긴급 승인 예외',s,selected,invoke,**args)
            assert not seen
            return
        result=rel.navigate('긴급 승인 예외',s,selected,invoke,**args)
        if defect=='context_limit':
            assert not seen and result['pending']
            assert any(x['kind']=='reference_context_limit' for x in result['limits'])
        else:
            assert len(seen)==1
            if defect=='resume':
                before=deepcopy(read_state)
                rel.navigate('긴급 승인 예외',s,selected,invoke,**args)
                assert len(seen)==1 and read_state==before
    assert 'extra' not in selected


def test_scoped_catalog_knows_acquired_targets_without_using_them_as_roots(connected):
    s,_=connected;rec,sid=initial(s)
    from semantic_runtime.legal_agent import unit_reading as ur
    reads={}
    for did in ['d','detail']:
        src=next(v for v in s.tools.sources.values() if v['document_id']==did)
        h=rel.hit_for(s,src['id'],'0')
        reads[did]=ur.read(s,h,next(o for o in ur.offers(s,h) if o['id']=='subtree:0'),action_state={'count':0,'chars':0})
    spans=[p for e in reads['d']['evidence'] for p in e['spans']]
    with cs.bound(s,{'members':[{'source_id':sid,'spans':spans}]}):
        groups,_,_,_=rel.catalog(s,[sid],reads,set())
    assert groups and all(c['already_read'] for g in groups for c in g['connections'])
    assert {g['anchor']['source_id'] for g in groups}=={sid}


def test_navigation_wire_reports_omitted_originals(monkeypatch):
    expected={'included':['E1'],'omitted_by_context_budget':['E2'],'character_limit':100,'automatic_adoption':False}
    def setup(data,actions):data['retained_original_context']=expected
    assert wire(capture(monkeypatch,setup))['retained_original_context']==expected


def test_retained_body_and_current_presentation_flag_agree(monkeypatch):
    page={'id':'E1','branch_id':'G1','source_id':'s','page':1,'total_pages':1,
          'text':'이미 확보한 시행령 원문','spans':[{'text':'이미 확보한 시행령 원문'}]}
    state={'selected':{'G1':{}},'groups':{'G1':{'status':'READ','page_plan':[[]]}},
        'basis_history':{'E1':{**page,'accepted':True}}}
    inv=S(p=state,s=S(profile={'max_read_chars':100,'max_context_chars':1000}),render_page=lambda *a:deepcopy(page))
    monkeypatch.setattr(cs.inventory,'check_page',lambda *a,**k:None)
    # This fixture isolates retention; exact coverage is tested with source
    # bindings in test_navigation_scope_memory and test_navigation_execution_context.
    monkeypatch.setattr(cs.inventory,'presentation_receipt',lambda s,g,r,pages,**kw:
        {'currently_presented':bool(pages),'presented_complete':bool(pages),'missing_spans':[]})
    data={'sources':[],'basis':[],'saved_inventory':[{'material_id':'G1','currently_presented':False}]}
    dp.retain_requested(inv,data)
    assert data['sources'][0]['text']==page['text'] and data['saved_inventory'][0]['currently_presented']


def test_budget_omitted_active_original_still_has_saved_text_view(monkeypatch):
    page={'id':'E1','branch_id':'G1','source_id':'s','page':1,'total_pages':1,
          'text':'확보한 원문은 사라지지 않는다.','spans':[{'text':'확보한 원문은 사라지지 않는다.'}]}
    state={'selected':{'G1':{}},'groups':{'G1':{'status':'ACTIVE','page_plan':[[]]}},
        'basis_history':{'E1':{**page,'accepted':True}}}
    inv=S(p=state,s=S(profile={'max_read_chars':1,'max_context_chars':2}),render_page=lambda *a:deepcopy(page))
    monkeypatch.setattr(cs.inventory,'check_page',lambda *a,**k:None)
    monkeypatch.setattr(cs.inventory,'presentation_receipt',lambda s,g,r,pages,**kw:
        {'currently_presented':bool(pages),'presented_complete':bool(pages),'missing_spans':[]})
    from semantic_runtime.legal_agent import law_candidates
    monkeypatch.setattr(law_candidates,'token',lambda *a:'VIEW1')
    data={'sources':[],'basis':[],'saved_inventory':[{'material_id':'G1','status':'ACTIVE'}]};actions={}
    dp.retain_requested(inv,data,actions)
    assert not data['sources'] and not data['saved_inventory'][0]['currently_presented']
    assert data['retained_original_context']['omitted_by_context_budget']==['E1']
    assert actions[data['saved_inventory'][0]['view_action']]['action']=='VIEW_SAVED_SOURCE'


def test_completed_follow_history_precedes_recent_skips_under_limit(monkeypatch):
    inv,_,_,groups,_,_=inline_fixture(monkeypatch,3)
    inv.s.context=S(query={'generation_id':'g'})
    binding=digest({'question':inv.question,'scope':['d'],'generation':'g'})
    inv.p.update(action_chain={'steps':[],'frames':{}},reference_states={'one':{'binding':binding,'decisions':{}}})
    for i,g in enumerate(groups):
        g['anchor']['document_id']='d'
        d={'id':str(i),'action':'FOLLOW' if i==0 else 'SKIP','scopes':[],
            'reason':'검토한 이유','applicability':'APPLIES' if i==0 else 'DOES_NOT_APPLY','applicability_reason':'원문 대조'}
        key=rel.group_signature(inv.question,g)
        inv.p['reference_states']['one']['decisions'][key]=d
        inv.p['action_chain']['frames'][str(i)]={'kind':'REFERENCE','offered':{str(i):g}}
        inv.p['action_chain']['steps'].append({'status':'APPLIED','from_frame':str(i),'reference_decisions':[d]})
    # Closure validity is independently covered by the reference continuity suite.
    monkeypatch.setattr(rel,'closed_decision',lambda q,g,d,b:d[rel.group_signature(q,g)])
    result=dp.previous_reference_decisions(inv,limit=1)
    assert result['items'][0]['decision']['action']=='FOLLOW' and result['omitted']==2
