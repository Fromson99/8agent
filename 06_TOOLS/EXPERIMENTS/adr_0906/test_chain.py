"""Real reader/state contracts for restorable menus and persistent decisions."""
import copy,json
import pytest
from jsonschema import ValidationError
from test_unit_fulltext_adaptive_read import tree,session
from test_selection_tool_contracts_adr0665 import investigation,acquire
from test_law_grouped_navigation import decide,cards,prepared,reader
from semantic_runtime.legal_agent import investigation_chain as chain,law_navigation as ln,unit_relations as rel
from semantic_runtime.legal_agent.errors import ContractError

def execute(inv,data,actions,value):
    inv.validate(value,data,actions);inv.execute(value,data,actions)

def back(inv,fid,reason='과거 검색에서 다른 후보를 선택'):
    data,actions=inv.view();a=next(a for a in actions.values() if a['action']=='RETURN_TO' and a['identity']['frame_id']==fid)
    v=decide(data,'RETURN_TO',a['id']);v['reason']=reason
    execute(inv,data,actions,v)
    return inv.view()

def test_initial_menu_is_immutable_and_has_bound_choices(session):
    inv=investigation(session);data,actions=inv.view();fid=data['chain_frame_id']
    archived=copy.deepcopy(chain.frame(inv.p,fid));data['laws'].clear();actions.clear()
    assert chain.frame(inv.p,fid)==archived

def test_return_search_restores_same_query_candidates_and_retains_read(session):
    inv=investigation(session);initial,_=inv.view();fid=initial['chain_frame_id'];gid=acquire(inv)
    reads=copy.deepcopy(inv.p['selected']);history=copy.deepcopy(chain.context(inv.p)['steps'])
    restored,_=back(inv,fid,'현재 규정이 부족하여 최초 후보를 다시 선택한다')
    assert restored['search_queries']==initial['search_queries']
    assert [l['id'] for l in restored['laws']]==[l['id'] for l in initial['laws']]
    assert inv.p['selected']==reads and inv.p['groups'][gid]['status']=='READ'
    assert restored['investigation_chain']['steps'][:len(history)]==history
    assert restored['return_context']['reason']=='현재 규정이 부족하여 최초 후보를 다시 선택한다'
    assert restored['investigation_chain']['steps'][-1]['action']=='RETURN_TO'

def test_return_read_menu_preserves_original_page_and_later_judgment(session):
    inv=investigation(session);gid=acquire(inv);data,actions=inv.view();fid=data['chain_frame_id'];original=data['sources']
    v=decide(data,'PENDING');v['branch_decisions']=[{'branch_id':gid,'status':'ADOPT','reason':'현재 쟁점의 근거로 채택', 'issue_refs':['Q1'],'basis_refs':[x['id'] for x in data['basis'] if x.get('branch_id')==gid]}]
    execute(inv,data,actions,v)
    later,_=inv.view();v=decide(later,'PENDING');v['reason']='다른 조건 확인';execute(inv,later,inv.view()[1],v)
    restored,_=back(inv,fid,'읽었던 원문의 선택지로 돌아간다')
    assert restored['sources']==original and inv.p['groups'][gid]['status']=='ACTIVE'
    assert any(x['reason']=='다른 조건 확인' for x in restored['investigation_chain']['steps'])
    assert restored['adopted_evidence'][0]['reason']=='현재 쟁점의 근거로 채택'

def test_unknown_return_target_is_rejected(session):
    inv=investigation(session);data,actions=inv.view();v=decide(data,'RETURN_TO','invented')
    with pytest.raises(ValidationError):inv.validate(v,data,actions)
    with pytest.raises(ContractError):inv.restore('unknown','reason')

def test_chain_checkpoint_keeps_every_action_and_menu(session):
    inv=investigation(session);acquire(inv);saved=copy.deepcopy(inv.p)
    other=ln.Investigation(inv.s,inv.question,inv.record,reader,60,saved,None)
    assert chain.state(other.p)==chain.state(inv.p)
    other.view();assert chain.context(other.p)['steps']==chain.context(inv.p)['steps']

def test_ordinary_read_window_does_not_repeat_deferred_other_law_cards(session):
    inv=investigation(session);initial,actions=inv.view();gid=acquire(inv)
    data,_=inv.view();expected={inv.p['groups'][gid]['law_id']}
    assert {l['id'] for l in data['laws']}<=expected
    assert len(json.dumps(data['references'],ensure_ascii=False))<1000
    assert data['investigation_chain']['steps']

def test_choice_reasons_are_preserved_when_current_reason_changes(session):
    inv=investigation(session);acquire(inv);data,actions=inv.view()
    a=decide(data,'PENDING');a['reason']='첫 판단';execute(inv,data,actions,a)
    data,actions=inv.view();a=decide(data,'PENDING');a['reason']='수정 판단';execute(inv,data,actions,a)
    reasons=[s['reason'] for s in chain.context(inv.p)['steps']]
    assert '첫 판단' in reasons and '수정 판단' in reasons

def test_multi_article_read_is_real_original_and_not_auto_adopted(session):
    inv=investigation(session);data,actions=inv.view();a=next(a for a in actions.values() if a['action']=='READ_ARTICLES')
    law=next(l for l in data['laws'] if l['document_id']==a['identity']['document_id'])
    v=decide(data,'READ_ARTICLES',a['id']);v['law_decisions']=[{'law_id':law['id'],'status':'INVESTIGATE','reason':'여러 적중 조문을 함께 조사','issue_refs':['Q1'],'basis_refs':[]}]
    execute(inv,data,actions,v);after,_=inv.view()
    assert after['sources'] and inv.p['selected'] and not inv.active_records()
    assert chain.context(inv.p)['steps'][-1]['action']=='READ_ARTICLES'

def test_reference_frame_restores_original_choices_and_current_history(session):
    inv=investigation(session);acquire(inv)
    offered={'g':{'key':'k','anchor':{'source_id':next(iter(inv.p['selected'].values()))['source_id']},'target':{'source_id':'x'}}}
    data={'question':inv.question,'groups':[{'id':'g','target':'x','read_options':['choice']}],'sources':[]}
    out=inv.reference_menu(data,offered);fid=out['chain_frame_id']
    d={'decisions':[{'id':'g','action':'DEFER','scopes':[],'reason':'현재 원문만으로 연결 적용 미확인','applicability':'UNCERTAIN','applicability_reason':'추가 확인 필요'}],'needs_more':False}
    inv.reference_decision(out,d);inv.restore(fid,'이전에 보류한 연결을 다시 판단한다')
    archived=chain.frame(inv.p,fid)
    assert archived['data']['groups']==data['groups']
    assert chain.context(inv.p)['steps'][-1]['reference_decisions']==d['decisions']
    assert inv.p['revisit']['reason']=='이전에 보류한 연결을 다시 판단한다'

def test_search_after_return_keeps_current_adoption_without_reset(session):
    inv=investigation(session);initial,_=inv.view();gid=acquire(inv);inv.p['groups'][gid]['status']='ACTIVE'
    restored,_=back(inv,initial['chain_frame_id'],'최초 검색을 다시 조사')
    assert inv.active_records() and restored['adopted_evidence']
    assert restored['articles'][0]['status']=='ACTIVE'

from test_batch_reference_navigation import connected,decision as reference_choice
from semantic_runtime.legal_agent import law_candidates as lc,unit_reading as ur

def test_two_real_articles_read_in_one_action_with_separate_evidence(connected):
    s,_=connected;inv=ln.Investigation(s,'긴급 승인 예외',prepared(s),reader,60,None,None)
    data,actions=inv.view();choices=list(a for a in actions.values() if a['action']=='READ_ARTICLES')[:2]
    assert len(choices)==2
    value=decide(data,'READ_ARTICLES',choices[0]['id']);value['targets']=[a['id'] for a in choices]
    dids={a['identity']['document_id'] for a in choices}
    value['law_decisions']=[{'law_id':l['id'],'status':'INVESTIGATE','reason':'원칙과 세칙을 함께 조사','issue_refs':['Q1'],'basis_refs':[]} for l in data['laws'] if l['document_id'] in dids]
    execute(inv,data,actions,value);after,_=inv.view()
    assert len(inv.p['selected'])==2 and len({r['source_id'] for r in inv.p['selected'].values()})==2
    assert len(after['sources'])==2 and not inv.active_records()

def test_real_reference_return_reuses_closed_skip(connected):
    s,_=connected;menus=[]
    def invoke(system,data,schema,phase,timeout):
        assert phase.startswith('source-reference-');menus.append(copy.deepcopy(data));return reference_choice(data)
    inv=ln.Investigation(s,'긴급 승인 예외',prepared(s),invoke,60,None,None)
    data,actions=inv.view();card=next(c for c in cards(data) if s.tools.sources[inv.p['groups'][c['id']]['source_id']]['document_id']=='d')
    value=decide(data,'READ_PARENT',card['read_parent_action'],card);execute(inv,data,actions,value)
    data,actions=inv.view();action=next(a for a in actions.values() if a['action']=='FOLLOW_CONNECTION')
    execute(inv,data,actions,decide(data,'FOLLOW_CONNECTION',action['id']))
    assert menus
    fid=menus[0]['chain_frame_id'];original=copy.deepcopy(chain.frame(inv.p,fid)['data']['groups'])
    back(inv,fid,'접속 관계를 다시 검토해야 하므로 이전 선택지로 복귀')
    assert len(menus)==1
    assert chain.frame(inv.p,fid)['data']['groups']==original
    assert any(step['action']=='RETURN_TO' for step in chain.context(inv.p)['steps'])
    assert any(step['reference_decisions'] for step in chain.context(inv.p)['steps'])

def test_repeated_same_choice_is_two_actions_but_interrupted_resume_is_one(session):
    inv=investigation(session);data,actions=inv.view();v=decide(data,'PENDING')
    execute(inv,data,actions,v);execute(inv,data,actions,v)
    assert len(chain.context(inv.p)['steps'])==2
    row=chain.begin(inv.p,data,v,actions);row['status']='INTERRUPTED'
    again=chain.begin(inv.p,data,v,actions)
    assert again['id']==row['id'] and len(chain.context(inv.p)['steps'])==3

def test_historical_query_stays_restored_on_checkpoint_resume_with_newer_read_record(session):
    inv=investigation(session);initial,_=inv.view();fid=initial['chain_frame_id'];acquire(inv)
    # A different RECALL record may be the enclosing native stage checkpoint.
    newer=copy.deepcopy(inv.record);newer['law_navigation']['query_fingerprint']='different-newer-query'
    inv.restore(fid,'이전 검색을 다시 선택');saved=copy.deepcopy(inv.p)
    resumed=ln.Investigation(inv.s,inv.question,newer,reader,60,saved,None)
    data,_=resumed.view()
    assert data['search_queries']==initial['search_queries'] and data['return_context']['frame_id']==fid
    assert data['investigation_chain']['steps']==chain.context(inv.p)['steps']

from test_law_grouped_navigation import law_api

def test_native_api_exposes_chain_and_preserves_it_for_answer(law_api):
    send,transport,_=law_api;out=send();assert out.status_code==200
    meta=out.json()['assembly']['term_agent'];steps=meta['investigation_chain']['steps']
    assert steps and all(s['reason'] for s in steps)
    assert steps[-1]['action']=='FINISH' and meta['return_points']
