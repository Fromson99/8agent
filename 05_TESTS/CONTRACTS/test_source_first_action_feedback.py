"""Synthetic action-feedback contracts: no external I/O or legal quality claims."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
import pytest
from test_source_first_candidate import session, choice, answer
from test_legal_agent_double_harness import work, seed, PROFILE, WireTransport, generation
from semantic_runtime.legal_agent.source_first_navigation import NavigationKernel
from semantic_runtime.legal_agent.source_first_gateway import SourceFirstGateway
from semantic_runtime.legal_agent.source_first_protocol import DOMAIN, validate_view
from semantic_runtime.legal_agent.source_tools import SourceSession
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.errors import ContractError, ProposalError, DeadlineExceeded
from semantic_runtime.legal_agent.repository import encoded

READ = {'tool':'read','card':'P1','cursor':None}

def navigation(repo, pages=None, text='abcdef'):
    n = NavigationKernel.__new__(NavigationKernel)
    n.repo=repo
    n.cards={'P1':{'card':'P1','source_id':'S','node':'U1',
        'document_name':'모의 규정','heading':'제1조','preview':text,
        'preview_start':0,'preview_end':len(text),'preview_length':len(text),
        'source_chars':len(text),'preview_complete':True,'preview_suppressed':False,
        'citation_eligible':False,'routes':[]}}
    n.by_source={'S':'P1'}; n.allowed={'S'}; n.dismissed=set(); n.rank={'S':0}; n.offset=0
    n.cursors={}; n.read_pages={}; n.read_failures=set(); n.read_binding=repo.context.binding_hash
    raw={'text':text,'source_artifact_sha256':'b'*64}
    source={'document_id':'d','blocks':[{'block_id':'0'}]}
    sources=SimpleNamespace(repo=repo,context=repo.context,scope={'d'},
        store=SimpleNamespace(source=lambda d,b:raw),tools=SimpleNamespace(sources={'S':source}),
        calls=0)
    sources.verify=lambda e:SourceSession.verify(sources,e)
    pages=pages or {None:('OK',0,len(text),None,True)}
    def execute(action):
        repo.reserve_tool(); sources.calls+=1
        status,lo,hi,nxt,complete=pages[action['args']['cursor']]
        ids=[]
        if hi>lo:
            ident='span:'+str(lo)+':'+str(hi)
            seed(repo,text[lo:hi],ident,source_id='S',start=lo,block_text=text)
            ids=[ident]
        return {'status':status,'items':[],'evidence_ids':ids,'next_cursor':nxt,
                'coverage':{'complete':complete},'observation_id':'fixture:'+str(sources.calls)}
    sources.execute=execute
    n.sources=sources; n.references=lambda sid:([],[])
    return n

def running(repo, responses, preread=True):
    s=session(repo); s.nav=navigation(repo)
    if preread:
        s.nav.read('P1',route='server_preread')
    wire=WireTransport(responses)
    s.gateway=SourceFirstGateway(repo,s.context,s.profile,DOMAIN,wire)
    return s,wire

def wire_view(wire,index):
    return json.loads(wire.calls[index]['messages'][1]['content'])['view']

def test_preread_maps_current_evidence_not_citable_preview(work):
    s,wire=running(work,[choice(select=['E1'])])
    s.investigate()
    v=wire_view(wire,0)
    assert v['cards'][0]['read_state']=='COMPLETE'
    assert v['cards'][0]['presented_evidence']==['E1']
    assert not v['cards'][0]['citation_eligible']
    assert s.selected=={'span:0:6'}

def test_duplicate_read_cached_but_counted_and_reported(work):
    s,wire=running(work,[choice(actions=[READ]),choice(select=['E1'])])
    s.investigate()
    v=wire_view(wire,1); receipt=v['last_action_results'][0]
    assert receipt['status']=='ALREADY_READ' and receipt['new_evidence_count']==0
    assert receipt['presented_evidence']==['E1']
    assert v['progress_notice']['code']=='NO_PROGRESS'
    assert s.nav.sources.calls==1 and work.budget()['tool_used']==2
    assert work.db.execute("SELECT COUNT(*) FROM event WHERE kind='SOURCE_FIRST_READ_REUSED'").fetchone()[0]==1

def test_partial_chain_and_cache_never_fabricate_complete(work):
    n=navigation(work,{None:('TRUNCATED',0,3,'next',False),'next':('OK',3,6,None,True)})
    n.read('P1'); assert n.reading('P1')['read_state']=='PARTIAL'
    result=n.read('P1'); assert result['status']=='ALREADY_READ' and result['next_cursor']=='next'
    n.read('P1','next')
    assert n.reading('P1')['read_state']=='COMPLETE' and n.sources.calls==2

def test_final_cursor_and_coverage_flag_without_full_spans_not_complete(work):
    n=navigation(work,{None:('OK',0,3,None,True)})
    n.read('P1')
    assert n.reading('P1')['read_state']=='PARTIAL'

def test_failed_read_not_cached(work):
    n=navigation(work,{None:('ERROR',0,0,None,False)})
    n.read('P1'); n.read('P1')
    assert n.reading('P1')['read_state']=='FAILED' and n.sources.calls==2

def test_cached_read_revalidates_scope_and_generation_binding(work):
    n=navigation(work); n.read('P1'); n.sources.scope.clear()
    with pytest.raises(ContractError): n.read('P1')
    n.sources.scope.add('d')
    n.sources.context=replace(work.context,binding={**work.context.binding,'generation_id':'other'})
    with pytest.raises(ContractError): n.read('P1')

def test_wrong_cursor_rejected(work):
    n=navigation(work); n.cursors['other']='P2'
    with pytest.raises(ProposalError): n.read('P1','other')

def test_recovery_can_select_then_compose_and_review_without_findings(work):
    draft={'paragraphs':[{'text':'합성 원문에 따른 설명','evidence':['E1']}],'limitations':[]}
    review={'checks':[{'claim':'C1','verdict':'SUPPORTED','reason':'합성 대조','evidence':['E1'],'actions':[]}],
            'question':{'status':'RESOLVED','reason':'합성'}}
    s,wire=running(work,[choice(actions=[READ]),choice(actions=[READ]),choice(select=['E1']),draft,review])
    retrieved=s.investigate()
    assert wire_view(wire,2)['progress_notice']['code']=='RECOVERY_REQUIRED'
    selected=s.select(retrieved); assembled=s.assemble()
    result,control=s.answer_and_review({**assembled,'retrieval':retrieved,'selection':selected,'assembly':assembled})
    assert result['answer']['claims'] and control['decision']=='FINAL'
    assert len(wire.calls)==work.budget()['model_reserved']==5
    assert not work.heads('finding')
    # Synthetic evidence has unknown applicability: do not report READY/quality.
    assert control['gate']=='BOUNDED' and not result['answer']['provider_receipt']['quality_certified']

def test_recovery_repeated_read_stops_without_auto_selection(work):
    s,wire=running(work,[choice(actions=[READ])]*3)
    s.investigate()
    assert len(wire.calls)==3 and not s.selected
    assert 'NO_PROGRESS_AFTER_RECOVERY' in s.limitations

def test_empty_draft_uses_same_single_recovery_cap(work):
    s,wire=running(work,[choice(),choice()])
    s.investigate()
    assert len(wire.calls)==2 and not s.selected
    assert 'EMPTY_SELECTION_AFTER_RECOVERY' in s.limitations
    assert s.recovery_used==1
    assert not s.request_recovery('another stage')

def test_recovery_schema_error_does_not_make_extra_physical_call(work):
    s,wire=running(work,[choice(),'{broken'])
    s.investigate()
    assert len(wire.calls)==work.budget()['model_reserved']==2 and not s.selected

def test_finalization_reserve_not_consumed_by_recovery(work):
    s,wire=running(work,[choice()])
    b=work.budget()
    work.db.execute('UPDATE budget SET model_reserved=?',(b['model_limit']-b['finalization_reserve']-1,))
    s.investigate()
    assert len(wire.calls)==1 and not s.selected
    assert work.budget()['model_reserved']==b['model_limit']-b['finalization_reserve']
    assert any(x.startswith('RECOVERY_BUDGET_UNAVAILABLE') for x in s.limitations)

def test_expired_recovery_never_sent(work):
    s,wire=running(work,[])
    s.context=replace(s.context,deadline=0)
    with pytest.raises(DeadlineExceeded): s.request_recovery('expired')
    assert not wire.calls

def test_page_toggle_not_repeated_progress(work):
    s,wire=running(work,[choice(actions=[{'tool':'page','offset':12}]),
                       choice(actions=[{'tool':'page','offset':0}]),
                       choice(actions=[{'tool':'page','offset':12}]),choice()])
    s.investigate()
    assert len(wire.calls)==4 and s.recovery_used==1
    assert 'EMPTY_SELECTION_AFTER_RECOVERY' in s.limitations

def test_context_dropped_spans_not_exposed_as_card_or_receipt_alias(work):
    s=session(work,cap=10500); s.nav=navigation(work,text='x'*6000); s.nav.read('P1')
    s.run_actions([READ])
    v=s.view('investigate')
    assert not v['evidence'] and not v['cards'][0]['presented_evidence']
    assert v['cards'][0]['read_state']=='COMPLETE' and v['cards'][0]['read_evidence_not_present']==1
    assert not v['last_action_results'][0]['presented_evidence']
    assert len(encoded(v)) < s.profile['max_context_chars']

def test_view_validator_rejects_unpresented_alias(work):
    s=session(work); v=s.view('investigate')
    v['cards'][0]['presented_evidence']=['E9']
    with pytest.raises(ContractError): validate_view(v)

@pytest.mark.parametrize('gateway_class',[ModelGateway,SourceFirstGateway])
def test_external_transport_not_blocked_by_export_flag(work,gateway_class):
    wire=WireTransport([choice()]); wire.binding={**wire.binding,'trust_zone':'external'}
    p={**deepcopy(PROFILE),'model_binding':wire.binding}
    gateway=gateway_class(work,work.context,p,DOMAIN,wire)
    assert not work.context.binding['export_allowed']
    if gateway_class is SourceFirstGateway:
        s=session(work); gateway.generate('investigate',s.view('investigate'),'InvestigateDecision')
        assert len(wire.calls)==1
    assert gateway.transport is wire

@pytest.mark.parametrize('gateway_class',[ModelGateway,SourceFirstGateway])
def test_model_binding_still_enforced(work,gateway_class):
    wire=WireTransport([]); wire.binding={**wire.binding,'model':'wrong'}
    with pytest.raises(ContractError): gateway_class(work,work.context,PROFILE,DOMAIN,wire)


def test_real_pipeline_synthetic_generation_to_durable_publication(tmp_path,generation,monkeypatch):
    import importlib.util
    from pathlib import Path
    from semantic_runtime import fulltext
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.contracts import Contracts
    from semantic_runtime.legal_agent.source_first_adapter import SourceFirstAgent
    import semantic_runtime.legal_agent.source_first_session as impl
    root=Path(__file__).resolve().parents[2]
    frozen=Path(impl.__file__).parents[2]
    assert '/revisions/' in str(frozen), 'explicit frozen candidate required'
    spec=importlib.util.spec_from_file_location('wiring_helper',root/'06_TOOLS/EXPERIMENTS/adr_0475/check_cm003.py')
    helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    fulltext.build(generation/'navigation',generation/'fulltext',workers=1)
    nav=json.loads((generation/'navigation/manifest.json').read_text())
    index=fulltext.FulltextIndex(generation/'fulltext',nav)
    monkeypatch.setattr(ServingDocumentAgent,'get_fulltext',lambda self:index)
    contract_root=helper.isolated_contract_root(frozen,tmp_path/'contracts')
    class AdaptiveWire(WireTransport):
        def send_once(self,*,body,ticket):
            self.calls.append(body)
            view=json.loads(body['messages'][1]['content'])['view']
            if view['phase']=='investigate':
                assert any(c['read_state']=='COMPLETE' and c['presented_evidence'] for c in view['cards'])
                value=choice(select=[e['evidence'] for e in view['evidence']])
            elif view['phase']=='compose':
                value={'paragraphs':[{'text':'합성 연결 검사이며 법률 판단이 아닙니다.','evidence':view['selected']}],'limitations':[]}
            else:
                value={'checks':[{'claim':c['claim'],'verdict':'SUPPORTED','reason':'합성 대조',
                                  'evidence':c['evidence'],'actions':[]} for c in view['claims']],
                       'question':{'status':'RESOLVED','reason':'합성'}}
            return {'status_code':200,'body_json':{'model':self.binding['model'],
                    'choices':[{'message':{'content':json.dumps(value,ensure_ascii=False)}}],
                    'usage':{'prompt_tokens':0,'completion_tokens':0,'simulated':True}}}
    wire=AdaptiveWire([])
    wire.binding={**wire.binding,'trust_zone':'external'}
    profile={**deepcopy(PROFILE),'model_binding':wire.binding}
    store=Store(generation)
    pipeline=Pipeline(contract_root,store,implementation='legal-agent-v1',
                      legal_agent_profile=profile,legal_agent_transport=wire)
    pipeline.term_agent=SourceFirstAgent(pipeline,pipeline.term_agent.config,execution_profile=profile,transport=wire)
    try:
        result=pipeline.run('모의승인규정 이사회 승인 예외',['d'],True,
                            execution_context={'runtime':tmp_path/'runtime'})
        Contracts(contract_root).validate_port('runtime.result',result)
        assert result['answer']['claims'] and len(wire.calls)==3
        assert all(set(c['source_ids']) for c in result['answer']['claims'])
        saved=list((tmp_path/'runtime/runs').glob('*.json'))
        assert len(saved)==1 and json.loads(saved[0].read_text())['answer']==result['answer']
    finally:
        store.close()

def test_research_batch_feedback_is_bounded_but_all_actions_are_audited(work):
    s,wire=running(work,[])
    s.run_actions([READ]*9)
    view=s.view('investigate')
    assert len(view['last_action_results'])==8
    assert work.db.execute("SELECT COUNT(*) FROM event WHERE kind='SOURCE_FIRST_ACTION_RESULT'").fetchone()[0]==9

def test_recovery_that_makes_progress_cannot_reset_global_cap(work):
    s,wire=running(work,[choice(actions=[READ]),choice(actions=[READ]),
                       choice(actions=[{'tool':'page','offset':12}]),
                       choice(actions=[{'tool':'page','offset':0}]),
                       choice(actions=[READ])])
    s.investigate()
    assert len(wire.calls)==5 and s.recovery_used==1
    assert any(x.startswith('RECOVERY_EXHAUSTED') for x in s.limitations)
    assert not s.selected

def test_aliases_omitted_from_current_view_cannot_be_selected(work):
    s=session(work,cap=10500); s.nav=navigation(work,text='x'*6000); s.nav.read('P1')
    v=s.view('investigate')
    answer(s,v,choice())
    assert s.ev_alias
    with pytest.raises(ProposalError): s.apply_decision(v,choice(select=list(s.ev_alias)))
    assert not s.selected

