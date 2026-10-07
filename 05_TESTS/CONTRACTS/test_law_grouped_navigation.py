"""Synthetic contracts for own-block law directories and model-owned navigation."""
import copy
import json
from contextlib import closing
import pytest
from test_unit_fulltext_adaptive_read import tree, session, hit
from test_batch_reference_navigation import connected
from test_batch_reference_navigation import decision as reference_decision
from semantic_runtime.legal_agent import law_candidates as lc, law_navigation as ln, unit_reading as ur
from semantic_runtime.legal_agent import unit_relations as rel
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.source_selection import select_sources
from semantic_runtime.legal_agent.errors import ProposalError
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_unified_legal_agent import ScriptedTransport, ok


def enable(s, **kw):
    s.profile['candidate_navigation']={**lc.DEFAULT_POLICY,'mode':'law-first-v1',**kw}


def prepared(s):
    enable(s)
    return SourceRecall(s).prepare()


def cards(data):
    return data.get('articles', [card for law in data['laws'] for card in law.get('articles', [])])


def decide(data, action='FINISH', target=None, branch=None):
    law=next((l for l in data['laws'] if branch and l['id']==branch['law_id']), data['laws'][0] if data['laws'] else None)
    value = {'presentation_id':data['presentation_id'],
        'law_decisions':[{'law_id':law['id'],'status':'INVESTIGATE','reason':'적중 원문이 승인 예외 쟁점과 연결됨',
                         'issue_refs':['Q1'],'basis_refs':[data['basis'][0]['id']] if data['basis'] else []}] if law else [],
        'branch_decisions':[], 'next_action':action,'targets':[target] if target else [],'queries':[],
        'issue_refs':['Q1'],'basis_refs':[p['id'] for p in data['basis']], 'reason':'실제 원문과 쟁점 확인',
        'notes':'부모 규정과 예외를 확인한다.','evidence_sufficient':action=='FINISH',
        'sufficiency_reason':'제공된 원문으로 판단 가능' if action=='FINISH' else ''}
    if action == 'FINISH':
        value['basis_refs']=[p['id'] for p in data['basis'] if p.get('branch_id')]
        for row in data['branches']:
            if 'ADOPT' in row['allowed_decisions'] and row['status'] != 'EXCLUDED':
                refs=[b['id'] for b in data['basis'] if b.get('branch_id')==row['id']]
                value['branch_decisions'].append({'branch_id':row['id'],'status':'ADOPT','reason':'확보한 원문을 근거로 채택',
                                                 'issue_refs':['Q1'],'basis_refs':refs})
    return value


def reader(system,data,schema,phase,timeout):
    candidate=next((r for r in cards(data) if r['status']=='CANDIDATE'),None)
    if not any(r['status'] in ('ACTIVE','READ') for r in cards(data)) and candidate:
        return decide(data,'READ_PARENT',candidate['read_parent_action'],candidate)
    continuation=next((r for r in cards(data) if r['status'] in ('ACTIVE','READ') and r.get('read_parent_action')),None)
    if continuation:return decide(data,'READ_PARENT',continuation['read_parent_action'],continuation)
    return decide(data)


def anchor_reader(system,data,schema,phase,timeout):
    # Reference contracts explicitly investigate their anchor law; directory
    # ranking is tested separately and must not silently select the test actor.
    if not any(r['status'] in ('ACTIVE','READ') for r in cards(data)):
        law=next(l for l in data['laws'] if l['document_id']=='d')
        candidate=next(r for r in cards(data) if r['law_id']==law['id'] and r['status']=='CANDIDATE')
        return decide(data,'READ_PARENT',candidate['read_parent_action'],candidate)
    return reader(system,data,schema,phase,timeout)


def test_grouped_index_cursor_binding_and_acl(tree):
    _,idx=tree
    with closing(idx.connect()) as db:
        page=idx.law_groups_page(db,['승인','원문'],limit=1)
        assert page['total']==2 and len(page['items'])==1 and page['next_cursor']
        second=idx.law_groups_page(db,['승인','원문'],cursor=page['next_cursor'],limit=1)
        assert second['items'][0]['document_id']!=page['items'][0]['document_id']
        with pytest.raises(ValueError,match='cursor'):
            idx.law_groups_page(db,['승인'],cursor=page['next_cursor'])
        with pytest.raises(ValueError,match='scope'):
            idx.law_groups_page(db,['승인'],{'invalid'})
        assert idx.law_groups_page(db,['승인'],set())['total']==0
        sid=idx.article_groups_page(db,['승인'],'d')['items'][0]['source_id']
        hits=idx.hit_page(db,['승인'],sid,limit=1)
        assert hits['total']>=5 and hits['next_cursor'] and 'score' not in hits['items'][0]
        with pytest.raises(ValueError,match='cursor'):
            idx.article_groups_page(db,['승인'],'d',cursor=hits['next_cursor'])


def test_leaf_parent_and_unmatched_siblings_are_read(session):
    native,_=session;s=native.sources;enable(s)
    rec=SourceRecall(s).prepare()
    # Use one exact leaf entry to ensure its immediate parent is the default.
    rec['unit_reads']=ur.acquire_batch(s,[hit(native)],rec['read_state'])
    rec['unit_hits']=[hit(native)]
    seen=[]
    def invoke(*args):
        seen.append(copy.deepcopy(args[1]));return reader(*args)
    out=select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120)
    assert out['status']=='complete' and out['law_navigation']['law_decisions'][0]['reason']
    assert any(r['offer']['id']=='subtree:2' for r in out['read_scopes'])
    assert '승인 원칙' in out['selected_originals'][0]['text']
    assert cards(seen[0])[0]['parent']['siblings']
    assert not any('score' in json.dumps(v,ensure_ascii=False) for v in seen)


def test_unresolved_connections_allow_complete_and_are_recorded(connected):
    s,_=connected;rec=prepared(s)
    out=select_sources('긴급 승인 예외',rec,reader,session=s,remaining_seconds=120)
    assert out['status']=='complete' and out['completed_with_unresolved_connections']
    assert out['reference_navigation']['pending'] and out['completion_limitations']
    assert out['diagnostics']['blockers']==[] and out['diagnostics']['observations']
    assert out['reference_navigation']['actions']==[]


def test_finish_before_parent_pages_is_repaired(session):
    native,_=session;s=native.sources;rec=prepared(s)
    inv=ln.Investigation(s,'긴급 승인 예외',rec,reader,120,None,None)
    data,actions=inv.view();branch=cards(data)[0]
    value=decide(data,'READ_PARENT',branch['read_parent_action'],branch)
    inv.validate(value,data,actions);inv.execute(value,data,actions)
    data,actions=inv.view()
    if len(inv.p['groups'][branch['id']]['page_plan'])>1:
        with pytest.raises(ProposalError,match='unpresented'):
            inv.validate(decide(data),data,actions)


def test_cross_law_selection_and_exclusion_keep_only_chosen_branch(connected):
    s,_=connected;rec=prepared(s);seen=[];switched=False
    def invoke(system,data,schema,phase,timeout):
        nonlocal switched
        seen.append(copy.deepcopy(data))
        active=next((r for r in cards(data) if r['status'] in ('ACTIVE','READ')),None)
        if active and not switched:
            point=next(p for p in data['return_points'] if p['number']==1)
            d=decide(data,'RETURN_TO',point['return_action'],active)
            d['reason']='읽은 법령이 부족하여 최초 검색 후보로 돌아가 다른 법령을 조사'
            refs=[b['id'] for b in data['basis'] if b.get('branch_id')==active['id']]
            d['branch_decisions']=[{'branch_id':active['id'],'status':'EXCLUDE','reason':'읽은 규정은 현재 세칙의 절차 쟁점과 다름',
                                   'issue_refs':['Q1'],'basis_refs':refs}]
            switched=True;return d
        return reader(system,data,schema,phase,timeout)
    out=select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120)
    assert out['status']=='complete' and len(out['final_ids'])==1
    assert any(b['status']=='EXCLUDED' for b in out['law_navigation']['branches'])
    assert len(out['law_navigation']['law_decisions'])==2


def test_resume_accepted_read_uses_saved_decision(session,monkeypatch):
    native,_=session;s=native.sources;rec=prepared(s);saved=[];calls=[];original=ur.read
    def invoke(*args):calls.append(args[3]);return reader(*args)
    def fail(*args,**kw):raise RuntimeError('interrupted tool')
    monkeypatch.setattr(ur,'read',fail)
    with pytest.raises(RuntimeError,match='interrupted'):
        select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120,on_checkpoint=lambda p:saved.append(copy.deepcopy(p)))
    checkpoint=saved[-1];assert checkpoint['accepted']
    monkeypatch.setattr(ur,'read',original)
    out=select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120,checkpoint=checkpoint)
    assert out['status']=='complete' and calls.count('source-law-navigation-1')==1


def test_search_replaces_expression_and_keeps_read_branches(session):
    native,_=session;s=native.sources;rec=prepared(s);saved=[]
    def research(system,data,schema,phase,timeout):
        action=next(a for a in data['actions'] if a['action']=='RESEARCH')
        value=decide(data,'RESEARCH',action['id']);value['queries']=['보고'];return value
    out=select_sources('긴급 승인 예외',rec,research,session=s,remaining_seconds=120,on_checkpoint=lambda p:saved.append(copy.deepcopy(p)))
    assert out['needs_fulltext'] and out['status']=='pending'
    s.law_search_queries=['보고'];new=SourceRecall(s).prepare()
    assert new['law_navigation']['queries']==['보고']
    inv=ln.Investigation(s,'긴급 승인 예외',new,reader,120,saved[-1],None)
    assert len(inv.p['query_history'])==2
    data,actions=inv.view();value=research(None,data,None,None,None);value['queries']=rec['law_navigation']['queries']
    with pytest.raises(ProposalError,match='unchanged'):inv.validate(value,data,actions)


class LawTransport(ScriptedTransport):
    def send_once(self, *, body, ticket):
        view=json.loads(body['messages'][1]['content'])['view']
        phase=view.get('source_stage',view['phase'])
        if phase.startswith('source-law-navigation-'):
            self.phases.append(phase)
            if getattr(self,'interrupt_phase',None)==phase:raise RuntimeError('synthetic interrupted selection')
            searches=getattr(self,'searches',[])
            if searches:
                action=next(a for a in view['actions'] if a['action']=='RESEARCH')
                value=decide(view,'RESEARCH',action['id']);value['queries']=[searches.pop(0)]
                return wire(value)
            return wire(reader(None,view,None,phase,120))
        return super().send_once(body=body,ticket=ticket)


@pytest.fixture
def law_api(tmp_path,tree):
    gen,idx=tree;t=LawTransport()
    principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'max_model_attempts':80,
            'max_read_chars':40,'candidate_navigation':{'mode':'law-first-v1'}},
        legal_agent_transport=t,memory_identity=lambda req:principal)
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as client:
        n=0
        def send(**kwargs):
            nonlocal n
            n+=1
            return client.post('/v1/rag/ask',json={'question':'긴급 승인 예외','session_id':'law','request_id':'r'+str(n),**kwargs})
        yield send,t,client


def test_native_v6_api_has_law_selection_reasons_and_actual_parent_body(law_api):
    send,t,_=law_api
    out=ok(send())
    meta=out['assembly']['term_agent']
    assert meta['law_navigation']['law_decisions'][0]['reason']
    stage=next(s for s in meta['judgment_view']['stages'] if s['stage']=='SELECT')
    assert stage['laws'][0]['selection']['reason'] and stage['laws'][0]['branches']
    assert out['answer']['claims'] and out['executed']==['INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE']
    assert not any(p.startswith('source-unit-') for p in t.phases)


def test_native_v6_multiple_research_rounds_keep_investigation(law_api):
    send,t,_=law_api;t.searches=['보고','원칙']
    out=ok(send())
    nav=out['assembly']['term_agent']['law_navigation']
    assert nav['laws'] and out['answer']['claims']
    assert {'source-law-navigation-1','source-law-navigation-2','source-law-navigation-3'}<=set(t.phases)


def test_reference_step_returns_to_law_menu_and_explains_target_law(connected):
    s,_=connected;rec=prepared(s);followed=False;reference_calls=[]
    def invoke(system,data,schema,phase,timeout):
        nonlocal followed
        if phase.startswith('source-reference-'):
            reference_calls.append(phase);d=reference_decision(data)
            group=next(g for g in data['groups'] if g['target']['document_id']=='detail')
            next(c for c in d['decisions'] if c['id']==group['id']).update(action='FOLLOW',scopes=['subtree:1'],applicability='APPLIES',applicability_reason='질문의 예외 기준을 확인')
            return d
        if not followed and any(r['status'] in ('ACTIVE','READ') for r in cards(data)):
            followed=True
            action=next(a for a in data['actions'] if a['action']=='FOLLOW_CONNECTION')
            return decide(data,'FOLLOW_CONNECTION',action['id'])
        return anchor_reader(system,data,schema,phase,timeout)
    out=select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120)
    assert out['status']=='complete' and len(out['final_ids'])==2 and len(reference_calls)==1
    target=next(l for l in out['law_navigation']['laws'] if l['document_id']=='detail')
    reason=next(r for r in out['law_navigation']['law_decisions'] if r['law_id']==target['id'])
    assert reason['reason'] and out['reference_navigation']['actions']


def test_candidate_page_can_move_to_a_law_outside_initial_page(connected):
    s,_=connected;rec=prepared(s);initial_law=rec['law_navigation']['law_page']['items'][0]['document_id'];s.profile['candidate_navigation']['law_page_size']=1
    rec=SourceRecall(s).prepare();moved=False
    def invoke(system,data,schema,phase,timeout):
        nonlocal moved
        if not moved:
            moved=True;action=next(a for a in data['actions'] if a['action']=='NEXT_LAWS')
            return decide(data,'NEXT_LAWS',action['id'])
        candidate=next((r for r in cards(data) if r['status']=='CANDIDATE'),None)
        if not candidate and not data['sources']:
            law=data['laws'][0];return decide(data,'OPEN_LAW',law['open_action'])
        return reader(system,data,schema,phase,timeout)
    out=select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120)
    assert out['status']=='complete' and out['selected_originals'][0]['document_id']!=initial_law
    assert out['law_navigation']['law_total']==2


def test_finish_cannot_use_only_previews(session):
    native,_=session;s=native.sources;rec=prepared(s)
    inv=ln.Investigation(s,'긴급 승인 예외',rec,reader,120,None,None)
    data,actions=inv.view()
    from jsonschema import ValidationError
    with pytest.raises((ProposalError, ValidationError)):
        inv.validate(decide(data),data,actions)


def test_workflow_renders_law_names_and_selection_reasons(law_api):
    from test_genos_chat_flow import workflow
    send,_,_=law_api;out=ok(send());html=workflow()._judgment_html(out)
    assert '모의승인규정' in html and '법령별 조사' in html and '적중 원문이 승인 예외' in html


def test_native_v6_resume_selection_continues_same_case(law_api):
    send,t,client=law_api;t.interrupt_phase='source-law-navigation-2'
    failed=send(request_id='resume');assert failed.status_code==502
    t.interrupt_phase=None
    out=ok(send(request_id='resume'))
    assert out['answer']['claims'] and t.phases.count('source-law-navigation-1')==1


def test_unresolved_required_target_does_not_block_completion(connected,monkeypatch):
    s,_=connected;rec=prepared(s);catalog=rel.catalog
    def unresolved(*args,**kwargs):
        groups,statuses,limits,missing=catalog(*args,**kwargs)
        return groups,statuses,limits,missing+[{'reference_id':'synthetic-required',
            'reason':'MISSING_TARGET','reading_policy':{'obligation':'REQUIRED'}}]
    monkeypatch.setattr(rel,'catalog',unresolved)
    out=select_sources('긴급 승인 예외',rec,reader,session=s,remaining_seconds=120)
    assert out['status']=='complete' and out['completed_with_unresolved_connections']
    assert out['reference_navigation']['unresolved'][-1]['reading_policy']['obligation']=='REQUIRED'


def test_v6_default_profile_and_derived_unit_index_boot_without_manual_injection(tmp_path,tree):
    from lawrag.pipeline.fulltext_stage import derive
    from semantic_runtime.unit_fulltext import UnitFulltextIndex
    gen,_=tree;out=tmp_path/'own-block-generation';derive(gen,out,workers=1)
    app=create_app(tmp_path/'app',out,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6')
    p=app.state.pipeline
    try:
        assert isinstance(p.term_agent.unit_fulltext,UnitFulltextIndex)
        assert p.term_agent.profile['candidate_navigation']['mode']=='law-first-v1'
        request={'question':'긴급 승인 예외','document_ids':['d'],'use_llm':False}
        with p.term_agent.open_session(request,query=p.plan(request['question'],['d']),runtime=tmp_path/'native') as s:
            rec=SourceRecall(s.sources).prepare()
            assert rec['law_navigation']['law_page']['total']==1
    finally:p.store.close()


def test_native_api_returns_complete_with_unresolved_connection_warning(tmp_path,connected):
    s,idx=connected;t=LawTransport()
    app=create_app(tmp_path/'app',s.store.path,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'candidate_navigation':{'mode':'law-first-v1'}},legal_agent_transport=t,
        memory_identity=lambda req:{'user_id':'u','team_id':'risk_team','document_ids':['d','detail']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as client:
        out=ok(client.post('/v1/rag/ask',json={'question':'긴급 승인 예외','session_id':'law','request_id':'warning'}))
    meta=out['assembly']['term_agent']
    assert out['status']=='READY' and meta['completed_with_unresolved_connections']
    assert out['answer']['unresolved'] and '미해결 또는 미열람' in out['answer']['text']


def test_reference_read_interruption_resumes_without_repeated_reference_model(connected,monkeypatch):
    s,_=connected;rec=prepared(s);saved=[];calls=[];followed=False;original=rel.read;fail=True
    def invoke(system,data,schema,phase,timeout):
        nonlocal followed
        calls.append(phase)
        if phase.startswith('source-reference-'):
            d=reference_decision(data);g=next(g for g in data['groups'] if g['target']['document_id']=='detail')
            next(c for c in d['decisions'] if c['id']==g['id']).update(action='FOLLOW',scopes=['subtree:1'],applicability='APPLIES',applicability_reason='질문의 예외 기준을 확인')
            return d
        if not followed and any(g['status'] in ('ACTIVE','READ') for g in cards(data)):
            followed=True;a=next(a for a in data['actions'] if a['action']=='FOLLOW_CONNECTION')
            return decide(data,'FOLLOW_CONNECTION',a['id'])
        return anchor_reader(system,data,schema,phase,timeout)
    def interrupted(*args,**kwargs):
        nonlocal fail
        r=original(*args,**kwargs)
        if fail:fail=False;raise RuntimeError('reference READ interrupted after acquisition')
        return r
    monkeypatch.setattr(rel,'read',interrupted)
    with pytest.raises(RuntimeError,match='reference READ interrupted'):
        select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120,on_checkpoint=lambda p:saved.append(copy.deepcopy(p)))
    out=select_sources('긴급 승인 예외',rec,invoke,session=s,remaining_seconds=120,checkpoint=saved[-1])
    assert out['status']=='complete' and len(out['final_ids'])==2
    assert len([phase for phase in calls if phase.startswith('source-reference-')])==1


def test_exact_requested_unit_is_kept_even_when_its_article_already_has_fts_hit(session,monkeypatch):
    from semantic_runtime.legal_agent import structure_query
    native,_=session;s=native.sources;enable(s)
    sid=hit(native)['source_id']
    # This fixture has a structural tree, but no persisted coordinate mapping.
    # Supply the resolver's closed output and test the recall adapter's contract.
    monkeypatch.setattr(structure_query,'resolve',lambda *args:{'status':'MATCH','source_ids':[sid],
        'pairs':[{'document_id':'d','unit_id':'4','coordinate':'제1조제1항제2호'}],'reason':'EXACT_DOCUMENT_COORDINATE'})
    selected,receipt=SourceRecall(s).discover()
    assert receipt['structure_query']['status']=='MATCH'
    assert any(h['unit_id']=='4' and h.get('entry_reason')=='exact_structure' for h in receipt['unit_hits'])
