from copy import deepcopy
from types import SimpleNamespace as S
import json
import pytest
from semantic_runtime.legal_agent import request_repair as rr, completion_execution as ce, completion_v6 as v6, law_navigation as ln, decision_projection as dp
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.output_contract import DecisionConflict, diagnostics
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from test_main50_request_repair import tree, session, modern
from test_focused_input_modality import v6_proposal
from test_investigation_completion_adr0678 import decision
from test_batch_reference_navigation import connected, initial


def recovery_fixture(actions=None):
    events=[];saved=[]
    p={'binding':{'generation':'immutable','scope':['d']},'state_version':7,'turn':3,'no_progress':2,'used_calls':9}
    data={'presentation_id':'P','state_version':7,'sources':[{'id':'E','text':'정확한 원문'}]}
    actions={'T':{'action':'READ_ARTICLES','identity':{'document_id':'d','source_id':'s'}}} if actions is None else actions
    inv=S(modern=True,p=p,view=lambda:(deepcopy(data),deepcopy(actions)),save=lambda:saved.append(deepcopy(p)),
          s=S(repo=S(event=lambda k,v:events.append((k,v)),budget=lambda:{'model_limit':40,'model_reserved':9,'finalization_reserve':3})))
    return inv,events,saved


def test_one_recovery_survives_interruption_and_does_not_reset_counters():
    inv,events,saved=recovery_fixture();first=rr.no_progress_recovery(inv)
    assert len(events)==1 and saved and inv.p['no_progress']==2 and inv.p['used_calls']==9
    resumed=deepcopy(inv.p);inv.p=resumed;inv.view=lambda:pytest.fail('resume must reuse immutable presentation')
    assert rr.no_progress_recovery(inv)==first and len(events)==1
    rr.finish_no_progress_recovery(inv.p,'unrelated');assert rr.no_progress_recovery(inv)==first
    rr.finish_no_progress_recovery(inv.p,first[2]);assert rr.no_progress_recovery(inv) is None
    new=rr.new_epoch(inv.p,reason='ASSESS_GAP_REENTRY');inv.p=new
    assert rr.no_progress_recovery(inv) is None and new['no_progress']==2


@pytest.mark.parametrize('tamper',['binding','revision','epoch','source_text','target'])
def test_recovery_snapshot_fails_closed(tamper):
    inv,_,_=recovery_fixture();rr.no_progress_recovery(inv)
    if tamper=='binding':inv.p['binding']['scope']=[]
    if tamper=='revision':inv.p['state_version']+=1
    if tamper=='epoch':inv.p['investigation_epoch']=1
    if tamper=='source_text':inv.p['no_progress_recovery']['snapshot'][0]['sources'][0]['text']='변조'
    if tamper=='target':inv.p['no_progress_recovery']['snapshot'][1]['T']['identity']['document_id']='private'
    with pytest.raises(ContractError,match='snapshot'):rr.no_progress_recovery(inv)


@pytest.mark.parametrize('mode',['no_actions','only_finish','legacy'])
def test_recovery_needs_an_existing_investigation_route(mode):
    inv,e,_=recovery_fixture({} if mode=='no_actions' else {'T':{'action':'FINISH'}})
    if mode=='legacy':inv.modern=False
    assert rr.no_progress_recovery(inv) is None and not e and 'no_progress_recovery' not in inv.p


def test_native_acquired_content_is_progress_before_presentation(connected):
    session,_=connected;record,sid=initial(session);r=record['unit_reads'][0]
    p={'selected':{},'basis_history':{},'groups':{},'laws':{}}
    assert rr.record_progress(p) is False
    p['selected']['G']=r;before=deepcopy(r)
    assert rr.record_progress(p) and not rr.record_progress(p)
    assert not p['basis_history'] and p['selected']['G']==before
    p['selected']['duplicate']=deepcopy(r)
    assert not rr.record_progress(p)
    p['previews']=[{'text':'새로운 검색 미리보기'}]
    assert not rr.record_progress(p)


@pytest.mark.parametrize('window',['read','structure'])
def test_native_search_candidates_survive_focus_window(session,window):
    native,_=session;i=modern(native);i.p['window']='search'
    d,a=i.view();before={r['source_id'] for law in d['laws'] for r in law.get('article_matches',[])}
    assert before
    i.p['window']=window;d,a=i.view()
    after={r['source_id'] for law in d['laws'] for r in law.get('article_matches',[])}
    assert after and after<=before
    assert any(x['action']=='READ_ARTICLES' for x in a.values())
    assert all(x['identity'].get('document_id') in i.s.scope for x in a.values() if x['action']=='READ_ARTICLES')


def test_native_navigation_run_uses_recovery_once(session,monkeypatch):
    native,_=session;i=modern(native);i.p['no_progress']=2;calls=[]
    from semantic_runtime.basis_links import resolver
    from semantic_runtime.legal_agent import comparison_research,source_investigation,definition_entry
    for module,name in [(resolver,'acquire'),(comparison_research,'acquire'),(source_investigation,'acquire_preferred'),(definition_entry,'acquire_initial')]:
        monkeypatch.setattr(module,name,lambda inv:None)
    def choose(data,actions,phase):
        calls.append(phase);return decision(data,'FINISH')
    i.request_decision=choose
    result=i.run()
    assert len(calls)==1 and i.p['no_progress_recovery']['status']=='COMPLETED'
    assert result['next_action']=='DONE' and result['status']=='complete'


@pytest.mark.parametrize('actual,source,opposite',[
    ('OBLIGATION','보고하여야 한다.','보고할 수 있다.'),
    ('PERMISSION','보고할 수 있다.','보고하여야 한다.'),
    ('PROHIBITION','보고하여서는 아니 된다.','보고할 수 있다.')])
def test_modality_repair_identifies_actual_claim_and_norm_without_rewriting(actual,source,opposite):
    value=v6_proposal(quote=source,kind=actual);value['claims']*=2;value=deepcopy(value)
    value['claims'][1]=deepcopy(value['claims'][1]);value['claims'][1]['claim_id']='C2'
    value['claims'][1]['rule']['norms'][0]['text']=opposite
    before=deepcopy(value)
    with pytest.raises(DecisionConflict) as error:v6.verify_modalities(value,[{'id':'S1','text':source}])
    detail=diagnostics(error.value);issue=detail['issues'][0]
    assert issue['path']=='/claims/1/rule/norms/0/text'
    assert issue['expected_constraint']['source_modality']==actual
    assert issue['expected_constraint']['source_quote']==source and value==before
    value['claims'][1]['rule']['norms'][0]['text']=source
    v6.verify_modalities(value,[{'id':'S1','text':source}])


def test_uncertain_modality_stays_model_judgment():
    text='보고하여야 한다. 다만 서면 제출로 갈음할 수 있다.'
    value=v6_proposal(quote=text,kind='PERMISSION')
    value['claims'][0]['rule']['norms'][0]['text']='서면 제출로 갈음할 수 있다.'
    v6.verify_modalities(value,[{'id':'S1','text':text}])


def test_assessment_view_preserves_every_original_and_identity_without_audit_duplication():
    sources=[{'source_id':'article:one','document_name':'모의규정','heading':'제8조','evidence_refs':['S1','S2'],'article_complete':True,'read_scopes':[], 'delivered_context_only':True,'document_id':'private-id'}]
    options=[{'id':'S1','source_id':'article:one','text':'① 보통주식은 그 주식의 수.\n','text_hash':'a'*64,'block_id':'1','start_cp':0,'end_cp':18},
             {'id':'S2','source_id':'article:one','text':'② 전환증권은 금액/가격. e\u0301 😀','text_hash':'b'*64,'block_id':'2','start_cp':0,'end_cp':25}]
    original=deepcopy((sources,options));headers,rows=ce.assessment_original_view(sources,options)
    assert rows==[{'id':o['id'],'text':o['text']} for o in options]
    assert headers[0]['evidence_refs']==[o['id'] for o in rows]
    assert 'delivered_context_only' not in headers[0] and (sources,options)==original
    assert len(json.dumps([headers,rows]))<len(json.dumps(original))
    view={'sources':headers,'evidence_options':rows};codec=NavigationReferences(view)
    assert codec.restore(codec.view(view))==view
