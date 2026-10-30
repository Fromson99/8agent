"""Actual HTTP/wire and integrity contracts. Synthetic sources and model only."""
import ast
from copy import deepcopy
import inspect,json,sqlite3
from pathlib import Path
import pytest
from conftest import term_glossary
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_assessment as oa, ontology_context as oc
from semantic_runtime.legal_agent import completion_contracts as cc, compact_model_input as minimal
from semantic_runtime.legal_agent import evidence_inventory as inventory
from semantic_runtime.legal_agent.errors import ContractError
from test_ontology_context import inv, bundle, configure, plans, direct_scope, original, connected, definition_source


def prepared(i,gid):
    configure(i,[bundle(i.s)])
    i.s.profile['candidate_navigation'].update(ontology_direct_assessment=True,execution_review=True,
        ontology_context=deepcopy(i.policy['ontology_context']))
    oc.acquire(i,[gid])
    sources,evidence,omitted=inventory.acquired_originals_for(i.s,i.p,100000)
    return sources,cc.evidence_options(sources)


def test_projection_has_current_refs_and_one_original_copy(inv):
    i,gid=inv;sources,options=prepared(i,gid);before=deepcopy(i.p)
    out=oa.project(i.s,i.p,sources,options);card=out['ontology_bundles'][0]
    assert card['status']=='COMPLETE'
    assert all('text' not in p and p['source_refs'] for p in card['payload']['provisions'])
    assert {ref for p in card['payload']['provisions'] for ref in p['source_refs']} <= {o['id'] for o in options}
    assert i.p==before and out['ontology_assessment']['automatic_adoption'] is False


@pytest.mark.parametrize('missing',['source','option','option_piece'])
def test_omission_keeps_knowledge_pending(inv,missing):
    i,gid=inv;sources,options=prepared(i,gid)
    sid=sources[-1]['source_id']
    if missing=='source':sources=sources[:-1];options=[o for o in options if o['source_id']!=sid]
    elif missing=='option':options=[o for o in options if o['source_id']!=sid]
    else:
        option=next(o for o in options if o['source_id']==sid)
        option['end_cp']-=1;option['text']=option['text'][:-1]
    out=oa.project(i.s,i.p,sources,options);card=out['ontology_bundles'][0]
    assert card['status']=='PARTIAL' and not card['payload']['review_notes']
    pending=[p for p in card['payload']['provisions'] if not p['source_refs']]
    assert pending and all('value' not in p and 'note' not in p for p in pending)
    assert all(p['acquisition_status']=='ACQUIRED' and p['delivery_status']=='NOT_SENT' for p in pending)
    assert not any(r['reason']=='SOURCE_NOT_ACQUIRED' for r in card['payload']['unresolved'])
    assert card['payload']['review_notes_status']=='WITHHELD_UNTIL_ALL_ORIGINALS_PRESENTED'


@pytest.mark.parametrize('change',['snapshot','plan','anchor','extent','source','text','option_text','acl'])
def test_binding_corruption_is_rejected(inv,change):
    i,gid=inv;sources,options=prepared(i,gid);row=plans(i)[0]['fragments'][0]
    if change=='snapshot':i.p['ontology_context']['snapshot_sha256']='0'*64
    elif change=='plan':plans(i)[0]['id']='wrong'
    elif change=='anchor':row['anchor']['label']='changed'
    elif change=='extent':row['block_ids']=['unread']
    elif change=='source':row['source_id']='unknown'
    elif change=='text':
        source=next(s for s in sources if s['source_id']==row['source_id'])
        span=next(p for p in source['adopted_spans'] if p['evidence_id'] in row['evidence_ids'])
        span['text']='X'+span['text'][1:]
    elif change=='option_text':
        option=next(o for o in options if o['evidence_id'] in row['evidence_ids'])
        option['text']='X'+option['text'][1:]
    elif change=='acl':i.s.scope=set()
    with pytest.raises(ContractError):oa.project(i.s,i.p,sources,options)


def test_disabled_and_no_bundle_keep_old_route(inv):
    i,gid=inv
    assert not oa.ready(i) and oa.project(i.s,i.p,[],[])=={}
    sources,options=prepared(i,gid)
    i.s.profile['candidate_navigation']['ontology_context']={'mode':'A0'}
    assert not oa.ready(i) and oa.project(i.s,i.p,sources,options)=={}


def test_same_material_handoff_cannot_loop_and_resume_keeps_counter(inv):
    from semantic_runtime.legal_agent.law_navigation import Investigation
    i,gid=inv;sources,options=prepared(i,gid)
    i.modern=True;i.question='합성 기준';i.acquired_handoff_result=lambda *args:args
    i.policy['ontology_context']=deepcopy(i.s.profile['candidate_navigation']['ontology_context'])
    i.p['reentry_counters']={'ASSESS_GAP_REENTRY':1}
    before=deepcopy(i.p['read_state'])
    assert Investigation.assessment_handoff(i) is not None
    i.p=deepcopy(i.p)
    assert Investigation.assessment_handoff(i) is not None  # same uncommitted handoff resumes
    i.p['assessment_reviews']=[{'assessment_hash':'next-assessment'}]
    assert Investigation.assessment_handoff(i) is None  # ASSESS consumed this material
    assert len(i.p['assessment_handoffs'])==1 and i.p['read_state']==before
    assert i.p['reentry_counters']=={'ASSESS_GAP_REENTRY':1}


def test_compact_keeps_only_schema_selectable_pending_source_identity():
    schema={'properties':{'source_id':{'enum':['s1']}}}
    view={'source_stage':'memory-assess','read_judgments':{'pending_sources':[{'source_id':'s1','available_evidence_refs':['S1']}],
        'judgments':[{'source_id':'internal-not-selected','id':'J1'}]}}
    out=minimal.project(minimal.bind(view,schema))
    assert out['read_judgments']['pending_sources'][0]['source_id']=='s1'
    assert 'source_id' not in out['read_judgments']['judgments'][0]


def test_compact_preserves_meaning_and_keeps_proofs_only_on_server(inv):
    i,gid=inv;sources,options=prepared(i,gid)
    data=oa.project(i.s,i.p,sources,options);before=deepcopy(data)
    assert data['ontology_assessment']['proofs']
    out=minimal.project(data)
    assert 'ontology_assessment' not in out and out['ontology_bundles']
    assert data==before


def test_truly_unacquired_provision_is_distinct_from_omission(inv):
    i,gid=inv;configure(i,[bundle(i.s)]);direct_scope(i,[('d',None)])
    i.s.profile['candidate_navigation'].update(ontology_direct_assessment=True,execution_review=True,
        ontology_context=deepcopy(i.policy['ontology_context']))
    oc.acquire(i,[gid]);sources,_,_=inventory.acquired_originals_for(i.s,i.p,100000)
    card=oa.project(i.s,i.p,sources,cc.evidence_options(sources))['ontology_bundles'][0]
    assert card['status']=='PARTIAL'
    assert any(p['acquisition_status']=='UNACQUIRED' and p['delivery_status']=='NOT_SENT' for p in card['payload']['provisions'])
    assert any(r['reason']=='OUTSIDE_INVESTIGATION_SCOPE' for r in card['payload']['unresolved'])


def setup_sources(tmp_path,term_glossary,monkeypatch):
    """Reuse only the parent's real tiny-data/app setup, not its decisions."""
    import test_read_judgment_api as parent
    tree=ast.parse(inspect.getsource(parent.test_read_judgment_api_retains_decisions_and_reuses_request))
    fn=tree.body[0];fn.decorator_list=[];fn.name='_setup'
    end=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.ClassDef) and n.name=='Transport')
    fn.body=fn.body[:end]+ast.parse('return root,generation,index,question,target_text,choice_codecs').body
    namespace=dict(vars(parent));exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),parent.__file__,'exec'),namespace)
    return namespace['_setup'](tmp_path,term_glossary,'task_local',monkeypatch)


@pytest.mark.parametrize('mode',['A1','A2'])
@pytest.mark.parametrize('need_more',[False,True])
def test_actual_http_direct_answer_or_gap_reentry_and_duplicate(tmp_path,term_glossary,monkeypatch,mode,need_more):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    from test_action_choice_ontology_adr1066 import single_provision_snapshot
    from test_legal_agent_double_harness import wire
    from test_source_span_norm import proposal
    from test_main50_request_repair import GAP
    from test_unified_scope_semantic_authority import wire as entry
    root,generation,index,question,target_text,codecs=setup_sources(tmp_path,term_glossary,monkeypatch)
    snapshot,_=single_provision_snapshot(tmp_path/'raw.sqlite');b=snapshot['bundles'][0]
    if not need_more:
        second=deepcopy(b['provisions'][0])
        with sqlite3.connect(tmp_path/'raw.sqlite') as db:
            text=db.execute("SELECT text FROM source_block WHERE document_id='d' AND block_id='1'").fetchone()[0]
        second['anchor'].update(unit_id='1',label='합성 제2조',content_sha256=oc.compiler.content_hash(text))
        second.update(role='REQUIREMENT',note='승인 요건의 원문')
        b['provisions'].append(second)
        b['relations']=[{'from':'합성 제1조','to':'합성 제2조','type':'DELEGATES_TO','target_status':'CONFIRMED'}]
    stage=[''];project=minimal.project
    def capture(view,schema=None):
        stage[0]=view.get('source_stage','');return project(view,schema)
    monkeypatch.setattr(minimal,'project',capture)
    class Transport:
        binding={'provider':'fixture','model':'synthetic-contract','adapter_version':'fixture-v1','endpoint_identity':'no-network','trust_zone':'internal','max_input_bytes':500000}
        def __init__(self):self.calls=[];self.views=[];self.choices=[];self.assessed=False;self.opened=False
        def validate_model(self):return {'verified':True,'synthetic':True}
        def send_once(self,*,body,ticket):
            raw=json.loads(body['messages'][1]['content'])['view'];view=expand_cards(raw)
            phase=view.get('source_stage',view.get('phase',stage[0]));self.calls.append(phase);self.views.append((phase,deepcopy(view)))
            if isinstance(view.get('tool_options'),dict):view['tool_options']=[dict(o,choice=k) for k,rows in view['tool_options'].items() for o in rows]
            if phase=='request-entry':
                value=entry(question);value['intent']['issues'][0]['request_quote']=question
                value['command']['queries']=['모의승인규정 제1조'];value['search']['mode']='STRUCTURE';return wire(value)
            if '-read-choice' in phase:
                if not self.opened:
                    option=next(o for o in view['tool_options'] if o['choice']=='OPEN_TASK' and '목차' in o['label'])
                    value={'choice':'OPEN_TASK','target':option['target'],'issue_id':'Q1','missing_need':'적용 기준 원문의 목차 확인','relation':'DIRECT','source_ref':None};self.opened=True
                else:
                    assert not self.assessed or need_more, 'complete bundle must never navigate after ASSESS'
                    wanted='제2조' if self.assessed else '제1조'
                    candidates=[c for c in view.get('read_candidates',[]) if c.get('coordinate')==wanted]
                    if candidates:
                        value={'choice':'READ','selections':[{'target':candidates[0]['target'],'issue_id':'Q1','missing_need':'필요한 적용 기준 원문 확인','relation':'DIRECT','source_ref':None}]}
                    else:
                        links=[c for c in view.get('references',{}).get('dependency_cards',[]) if c.get('read_action') and wanted in c['target']['heading']]
                        follows=[o for o in view['tool_options'] if o['choice']=='FOLLOW_CONNECTION']
                        locations=[o for o in view['tool_options'] if o['choice']=='LOCATE']
                        source_ref=next((s['id'] for s in view.get('sources',[])),None)
                        if links:
                            value={'choice':'READ','selections':[{'target':links[0]['read_action'],'issue_id':'Q1','missing_need':'부족한 적용 기준 원문 확인','relation':'DEPENDENCY','source_ref':source_ref}]}
                        elif follows:
                            value={'choice':'FOLLOW_CONNECTION','target':follows[0]['target'],'issue_id':'Q1','missing_need':'부족한 적용 기준의 명시 연결 확인','relation':'DEPENDENCY','source_ref':source_ref}
                        elif locations:
                            value={'choice':'LOCATE','target':locations[0]['target'],'issue_id':'Q1','missing_need':'부족한 적용 기준 위치 확인','relation':'DIRECT','source_ref':None,'structure_filter':{'coordinate':wanted,'title':'','coordinate_scope':'body'}}
                        else:
                            option=next(o for o in view['tool_options'] if o['choice']=='OPEN_TASK' and '목차' in o['label'])
                            value={'choice':'OPEN_TASK','target':option['target'],'issue_id':'Q1','missing_need':'부족한 적용 기준 위치 조사','relation':'DIRECT','source_ref':None}
                ctx=view.get('read_judgments',{});rows=[]
                by_id={r['id']:r for r in ctx.get('current_originals',[])}
                for jid in ctx.get('required',[]):
                    row=by_id[jid];rows.append({'judgment_id':jid,'operation':'SET','use':'SUPPORT','finding':'현재 원문 범위 확인','reason':'부족한 적용 기준을 조사한다.','issue_refs':['Q1'],'basis_refs':row['source_refs'],'missing':[],'conflicts_with':[]})
                value['read_review']={'judgments':rows,'need_updates':[],'conflict_updates':[]}
                for action in value.get('selections',[value]):action['judgment_refs']=[r['judgment_id'] for r in rows] or [r['id'] for r in ctx.get('judgments',[])]
                self.choices.append(value['choice'])
                return wire(codecs[-1][1].project(value))
            if phase=='memory-assess':
                self.assessed=True
                card=view['ontology_bundles'][0];assert card['mode']==mode
                options=view['evidence_options'];known={o['id'] for o in options}
                assert all(ref in known for p in card['payload']['provisions'] for ref in p.get('source_refs',[]))
                found=next((o for o in options if target_text in o['text']),None)
                if found:
                    value=proposal(target_text,'OBLIGATION',[found['id']],found['id']);value.pop('disposition')
                else:
                    assert need_more
                    loc=next((o['target'] for o in view.get('locator_options',[]) if '제2조' in json.dumps(o,ensure_ascii=False)),'')
                    value={'claims':[],'issue_assessments':[{'issue_id':'Q1','status':'INSUFFICIENT','reason':'제2조 적용 기준 원문 필요'}],
                           'gaps':[{**GAP,'reason':'적용 기준을 정하는 제2조 원문이 필요하다.','missing_target':loc}]}
                ctx=view['read_judgments'];used=set(value['claims'][0]['evidence_refs']) if value['claims'] else set()
                value['read_judgment_review']={
                    'judgments':[{'id':h['id'],'disposition':'USE' if used.intersection(h.get('available_evidence_refs',[])) else 'NOT_USED',
                        'claim_refs':['C1'] if used.intersection(h.get('available_evidence_refs',[])) else [],
                        'basis_refs':list(used.intersection(h.get('available_evidence_refs',[]))),'reason':'현재 원문과 답변 근거의 범위를 대조했다.'} for h in ctx.get('judgments',[])],
                    'needs':[{'id':n['id'],'status':'NOT_NEEDED','reason':'현재 원문과 부족 항목에 반영','material':False,'basis_refs':[]} for n in ctx.get('needs',[])],
                    'conflicts':[],
                    'pending_sources':[{'source_id':p['source_id'],'disposition':'REVIEWED','reason':'제시된 원문으로 적용 범위와 부족을 판단했다.','basis_refs':p['available_evidence_refs']} for p in ctx.get('pending_sources',[])]}
                return wire(value)
            raise AssertionError('unexpected phase '+phase)
    transport=Transport();profile=json.loads((root/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile['candidate_navigation'].update(minimal_input=True,minimal_action_choices=True,execution_review=True,task_local_navigation=True,read_judgment=True,
        selected_connection_scope=True,small_connection_context=True,answer_first=False,answer_progress_control=False,ontology_direct_assessment=True,
        ontology_context={'mode':mode,'snapshot':snapshot,'snapshot_sha256':digest(snapshot)})
    profile.update(model_binding=transport.binding,answer_presentation='structured')
    app=create_app(tmp_path,generation,contracts_root=root,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,
                   memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=index
    try:
        with TestClient(app) as api:
            request={'question':question,'session_id':'direct','request_id':'r1'}
            response=api.post('/v1/rag/ask',json=request);assert response.status_code==200,response.text
            result=response.json();assert target_text in result['answer']['text']
            assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
            count=len(transport.calls);again=api.post('/v1/rag/ask',json=request)
            assert again.status_code==200 and again.json()['answer']==result['answer'] and len(transport.calls)==count
        first=transport.calls.index('memory-assess')
        assert transport.choices[:2]==['OPEN_TASK','READ'] and first==3
        assert transport.calls.count('memory-assess')==(2 if need_more else 1)
        assert 'FINISH' not in transport.choices
        assert ('FOLLOW_CONNECTION' in transport.choices)==need_more
        journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        with sqlite3.connect(journal) as db:
            events=[(k,json.loads(p)) for k,p in db.execute('SELECT kind,payload_json FROM event ORDER BY seq')]
            assert sum(k=='ACQUIRED_ORIGINALS_TO_ASSESS' and p.get('reason')=='ONTOLOGY_DIRECT_ASSESSMENT' for k,p in events)==(2 if need_more else 1)
            assert sum(k=='CASE_STAGE_REENTRY' and p['from_stage']=='ASSESS' for k,p in events)==int(need_more)
            assert any(k=='COMPOSITION_RENDERED' and not p['model_call'] for k,p in events)
            views=[json.loads(p) for p, in db.execute('SELECT body_json FROM model_view')]
            assess=[v for v in views if v.get('source_stage')=='memory-assess']
            assert len(assess[0]['read_judgments']['pending_sources'])==(1 if need_more else 2)
            assert not assess[0]['read_judgments']['judgments']
        from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
        from semantic_runtime.legal_agent.unified_publication import validate_saved
        repo=UnifiedRepository(journal)
        try:validate_saved(repo,result)
        finally:repo.close()
        print('DIRECT_HTTP',mode,'gap',need_more,'calls',transport.calls)
    finally:app.state.pipeline.store.close()


def test_typed_pending_ids_survive_wire_and_independent_repository_projection():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences,expand_cards
    sid='article:'+'a'*24
    schema={'properties':{'source_id':{'enum':[sid]}}}
    canonical=minimal.bind({'source_stage':'memory-assess','read_judgments':{'pending_sources':[
        {'source_id':sid,'available_evidence_refs':['S'+'b'*28]}]}},schema)
    refs=NavigationReferences(canonical);mapped=refs.view(canonical)
    wire=expand_cards(minimal.project(mapped,refs.schema(schema)))
    assert wire==expand_cards(minimal.project(mapped))
    row=wire['read_judgments']['pending_sources'][0]
    assert row['source_id']==refs.forward[sid]
    assert row['source_id'] in refs.schema(schema)['properties']['source_id']['enum']
    assert refs.restore(mapped)==canonical
