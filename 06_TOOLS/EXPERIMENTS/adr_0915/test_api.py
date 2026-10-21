from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace as S
import importlib.util,json
import pytest
from semantic_runtime.legal_agent.bounded_source_session import _Gateway,_Protocol,compact_assessment_evidence
from semantic_runtime.legal_agent.navigation_input import NavigationReferences

P=Path(__file__).resolve().parents[1]/'adr_0832/test_delivery.py'
spec=importlib.util.spec_from_file_location('canonical_delivery_fixture',P);prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
tree=prior.tree

@pytest.mark.parametrize('gap',[False,True])
def test_current_compact_api_publishes_and_reuses_verified_original(tmp_path,tree,monkeypatch,gap):
    from test_legal_agent_double_harness import wire
    from test_source_span_norm import proposal
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    class Current(prior.SpanTransport):
        def send_once(self,*,body,ticket):
            view=expand_cards(json.loads(body['messages'][1]['content'])['view'])
            phase=view.get('source_stage',view.get('phase',''))
            if '-read-choice' in phase:
                self.phases.append(phase)
                if view['sources']:
                    return wire({'choice':'FINISH','basis_refs':[s['id'] for s in view['sources']],
                        'issue_refs':[i['id'] for i in view['issues']],'evidence_sufficient':True,'reason':'요청 원문 확인'})
                return wire({'choice':'READ','selections':[{'target':view['read_candidates'][0]['target'],
                    'issue_id':view['issues'][0]['id'],'missing_need':'요청 조문 원문','relation':'DIRECT','source_ref':None}]})
            if phase.startswith('memory-assess'):
                self.phases.append(phase)
                assert all(set(o)=={'id','text'} for o in view['evidence_options'])
                options=view['evidence_options'];ref=next(o['id'] for o in options if '승인 후 보고한다.' in o['text'])
                value=proposal('승인 후 보고한다.','OBLIGATION',[ref],ref)
                if gap:
                    from test_main50_request_repair import GAP
                    value['gaps']=[deepcopy(GAP)]
                value.pop('disposition')
                for row in value['issue_assessments']:row.pop('reason')
                return wire(value)
            return super().send_once(body=body,ticket=ticket)
    import semantic_runtime.app as app_module
    create=app_module.create_app
    def current_create(*args,**kwargs):
        kwargs['memory_identity']=lambda _: {'team_id':'test_team','document_ids':['d']}
        kwargs['legal_agent_transport'].direct_note=False
        kwargs['legal_agent_profile']['candidate_navigation']['answer_first']=True
        return create(*args,**kwargs)
    monkeypatch.setattr(app_module,'create_app',current_create)
    monkeypatch.setattr(prior,'SpanTransport',Current)
    prior.test_compact_assessment_without_navigation_publishes_through_api(tmp_path,tree)
    import sqlite3
    paths=list(tmp_path.rglob('journal.sqlite'))
    events=[]
    for p in paths:
        with sqlite3.connect(p) as db:events.extend(k for k, in db.execute('SELECT kind FROM event'))
    assert 'ACQUIRED_ORIGINALS_TO_ASSESS' in events
    assert 'ASSESSMENT_GAP_REENTRY_PLANNED' not in events
    if gap:assert 'ASSESSMENT_RESEARCH_DEFERRED_TO_USER' in events

@pytest.mark.parametrize('phase',['memory-assess','memory-assess-repair'])
@pytest.mark.parametrize('text',['첫 줄\n둘째 줄 😀 e\u0301','한글 원문.\n'*900])
def test_verified_canonical_delivery_then_compact_wire_restores_exact_sources(phase,text):
    data,acquired=prior.fixture(text)
    data['sources'][0].update(document_name='모의규정',heading='제1조',delivered_context_only=True)
    data.update(input_projection='compact-selection-source-v3',source_stage=phase)
    before=deepcopy(data);evidence=compact_assessment_evidence(data,acquired)
    assert evidence
    schema={'type':'object','properties':{'selected':{'enum':[o['id'] for o in data['evidence_options']]}},'required':['selected'],'additionalProperties':False}
    g=object.__new__(_Gateway);g.protocol=_Protocol(schema);g.compact=True
    g.transport=S(binding={'model':'synthetic'});g.profile={'max_output_tokens':500};g.system='test'
    codec=NavigationReferences(data)
    wire=g.request('assess',data,'assessment',references=codec)
    shown=codec.restore(json.loads(wire['messages'][1]['content'])['view'])
    assert shown['evidence_options']==[{'id':o['id'],'text':o['text']} for o in data['evidence_options']]
    assert shown['sources'][0]['evidence_refs']==data['sources'][0]['evidence_refs']
    assert 'delivered_context_only' not in shown['sources'][0]
    assert data==before and compact_assessment_evidence(data,acquired)==evidence
    reply={'selected':codec.forward[data['evidence_options'][0]['id']]}
    assert codec.decode(reply,g._generation_schema)['selected']==data['evidence_options'][0]['id']

@pytest.mark.parametrize('stage,projection',[('memory-assess','compact-selection-source-v2'),('source-law-navigation-1','compact-selection-source-v3')])
def test_projection_is_not_applied_to_legacy_or_navigation(stage,projection):
    data,_=prior.fixture('정확한 원문');data.update(source_stage=stage,input_projection=projection)
    g=object.__new__(_Gateway);g.protocol=_Protocol({'type':'object','properties':{},'additionalProperties':False})
    g.compact=True;g.transport=S(binding={'model':'synthetic'});g.profile={'max_output_tokens':500};g.system='test'
    codec=NavigationReferences(data);wire=g.request('investigate',data,'schema',references=codec)
    shown=codec.restore(json.loads(wire['messages'][1]['content'])['view'])
    assert shown['evidence_options'][0]['source_id']=='s'
    assert shown['evidence_options'][0]['block_id']=='b'
