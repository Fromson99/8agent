from conftest import term_glossary
from copy import deepcopy
import json, sqlite3, pytest
from jsonschema import Draft202012Validator
from fastapi.testclient import TestClient
from test_request_entry_branch_contract import proposal, response_wire, scoped_tree
from semantic_runtime.legal_agent import request_entry as entry
from test_model_structure_selection import matcher, choose, single, scope_change
from semantic_runtime.legal_agent import wire_schema as ws
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.output_contract import OutputContractError
import gzip


def test_ambiguous_child_rejected_without_guessing_ancestor():
    m=matcher();coord=m.stored_coordinates[('d','p')]
    m.units[('d','p2')]={**m.units[('d','p')], 'span':[20,21]}
    m.stored_coordinates[('d','p2')]=coord
    selection=choose([single(2)],unit='항',root=True)
    c={'search_scope_change':scope_change(selection)};before=deepcopy(c)
    with pytest.raises(OutputContractError) as e:
        entry.validate_initial_selection(c,m,['d'],c['search_scope_change']['user_quote'])
    assert e.value.issues[0]['code']=='ENTRY_STRUCTURE_AMBIGUOUS_ENDPOINT'
    assert c==before


def test_no_permission_or_integrity_failure_becomes_repair(monkeypatch):
    from semantic_runtime.legal_agent import query_scope
    def fail(*args,**kw):raise ContractError('source binding changed')
    monkeypatch.setattr(query_scope,'resolve',fail)
    with pytest.raises(ContractError):
        entry.validate_initial_selection({'search_scope_change':scope_change(choose())},matcher(),['d'],'x')


def test_absent_document_retains_original_resolution_boundary():
    c={'search_scope_change':scope_change(choose())}
    c['search_scope_change']['targets'][0]['document']='없는규정'
    entry.validate_initial_selection(c,matcher(),['d'],c['search_scope_change']['user_quote'])


def test_saved_navigation_wire_order_preserves_all_constraints():
    from pathlib import Path
    root=Path('/home/jin/8-AGENT')
    p=root/'04_EXPERIMENTS/ADR/ADR-1351-integration-oneclick-provider-matrix/artifacts/public-live/B03-17-parasail/raw/call-002/request.json.gz'
    schema=json.load(gzip.open(p,'rt'))['response_format']['json_schema']['schema']
    projected,count=ws.discriminator_first(schema)
    assert count>0 and projected==schema  # dict equality ignores order; constraints identical
    assert list(projected['anyOf'][0]['properties'])[0]=='choice'
    assert ws.discriminator_first(projected)[1]==0
    # Construct a complete witness, then independently reject wrong target,
    # missing progress, extra fields, and wrong action/field combinations.
    def sample(s):
        if '$ref' in s:return sample(schema['$defs'][s['$ref'].split('/')[-1]])
        if 'const' in s:return s['const']
        if 'enum' in s:return s['enum'][0]
        if 'anyOf' in s:return sample(s['anyOf'][0])
        t=s.get('type');t=t[0] if isinstance(t,list) else t
        if t=='object':return {k:sample(s['properties'][k]) for k in s.get('required',[])}
        if t=='array':return [sample(s['items']) for _ in range(s.get('minItems',0))]
        if t=='string':return 'x'*max(1,s.get('minLength',0)) if s.get('maxLength',1)>0 else ''
        if t=='boolean':return False
        if t=='integer':return s.get('minimum',0)
        return None
    good=sample(schema);a=Draft202012Validator(schema);b=Draft202012Validator(projected)
    assert a.is_valid(good) and b.is_valid(good)
    variants=[]
    for key in good:
        v=deepcopy(good);del v[key];variants.append(v)
    v=deepcopy(good);v['selections'][0]['target']='OUTSIDE';variants.append(v)
    v=deepcopy(good);v['extra']='not allowed';variants.append(v)
    v=deepcopy(good);v['choice']='LOCATE';variants.append(v)
    assert all(not a.is_valid(v) and not b.is_valid(v) for v in variants)
    # Literal data called properties/anyOf must never be visited.
    literal={'const':{'properties':{'z':{'const':1},'a':{}},'anyOf':[1,2]}}
    assert ws.discriminator_first(literal)==(literal,0)


def test_path_repair_reaches_originals_and_reuses_answer(tmp_path, scoped_tree):
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    from test_assessment_source_reply import EmptyAssessment
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT
    from test_model_structure_selection import choose, single

    question = '모의승인규정 제1조 1항에서 2호는 빼고 전부 설명해'
    selected = choose(exclude=[single(2)], article=1, dash=None, paragraph=1)
    good = proposal()
    good['command']['queries'] = ['승인']
    good['intent']['issues'][0]['request_quote'] = question
    good['search'].update(mode='STRUCTURE')
    good['search']['scope_decision'].update(user_quote=question, targets=[
        {'document': '모의승인규정', 'structure': None, 'selection': selected}])
    bad = deepcopy(good)
    bad['search']['scope_decision']['targets'][0]['selection']['groups'][0]['parent_path'][0]['n'] = 99

    class Transport(EmptyAssessment):
        def send_once(self, *, body, ticket):
            view = json.loads(body['messages'][1]['content'])['view']
            phase = view.get('source_stage', view['phase'])
            if phase.startswith('request-entry'):
                self.phases.append(phase)
                if phase == 'request-entry':
                    return response_wire(bad)
                assert view['rejected_decision'] == bad
                assert view['question'] == question
                return response_wire(good)
            return super().send_once(body=body, ticket=ticket)

    generation, index = scoped_tree
    transport = Transport('repaired')
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'request_entry_policy': 'fused-title-v1', 'candidate_navigation': {
            'mode': 'law-first-v1', 'investigation_control': True, 'completion_contract': True,
            'completion_policy_version': 'investigation-completion-v8', 'compact_input': True,
            'structure_first': True, 'selectable_search': True, 'answer_first': True, 'assessment_reentry_limit': 0}}
    runtime = tmp_path/'runtime'
    body = {'question': question, 'session_id': 's', 'request_id': 'r'}
    answer = None
    for _ in range(2):
        application = create_app(tmp_path, generation, contracts_root=ROOT, provider=object(),
            implementation='legal-agent-unified-v6', legal_agent_profile=profile,
            legal_agent_transport=transport, runtime_root=runtime,
            memory_identity=lambda _: {'user_id': 'synthetic', 'team_id': 'risk_team', 'document_ids': ['d']})
        application.state.pipeline.term_agent.unit_fulltext = index
        with TestClient(application) as api:
            response = api.post('/v1/rag/ask', json=body)
            assert response.status_code == 200, response.text
            result = response.json()
            assert '긴급 승인 예외는 허용한다' in result['answer']['text']
            assert '일반 승인 예외는 허용하지 않는다' not in result['answer']['text']
            if answer is None:
                answer, calls = result['answer'], len(transport.phases)
            assert result['answer'] == answer and len(transport.phases) == calls
    assert transport.phases[:2] == ['request-entry', 'request-entry-repair']
    with sqlite3.connect(selected_store(runtime)) as db:
        state = json.loads(db.execute('SELECT state FROM goal WHERE id=?', (result['question_id'],)).fetchone()[0])
        assert [r['unit_id'] for r in state['search_scope']['targets']] == ['2']
        assert state['search_scope']['selections'][0]['excluded_unit_ids'] == ['4']

from types import SimpleNamespace as S
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.corrected_memory import Memory
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,BINDING
from test_structure_first_search import structured_generation
@pytest.mark.parametrize('always_missing',[False,True])
def test_missing_path_repairs_once_with_durable_budget(tmp_path,structured_generation,always_missing):
    question='모의승인규정 원문을 확인해 줘'
    profile={**settings(),'request_entry_policy':'fused-title-v1','candidate_navigation':{
        'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
        'completion_policy_version':'investigation-completion-v8'}}
    app=create_app(tmp_path,structured_generation,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile=profile,
        legal_agent_transport=S(binding=BINDING,validate_model=lambda:{'verified':True,'synthetic':True}))
    p=app.state.pipeline;calls=[]
    value={'routing':{'mode':'CASE','answer':'','reason':'원문 조사'},
        'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
            'queries':['모의승인규정'],'format':'prose','reason':'요청한 문서 확인',
            'search_scope_change':{'operation':'REPLACE','targets':[{'document':'모의승인규정','structure':None,'selection':None}],'user_quote':question}},
        'intent':{'purpose':'모의승인규정 원문 확인','concepts':['승인'],
            'issues':[{'id':'Q1','question':'모의승인규정 원문 확인','subject':'승인','kind':'OTHER','request_quote':question}]},
        'context_quotes':[],'search':{'mode':'STRUCTURE','title_hint_ids':[],'reason':'문서 원문 조사'}}
    scope=value['command'].pop('search_scope_change')
    value['search'].pop('title_hint_ids')
    value['search']['scope_decision']={'mode':'NAMED_SCOPE', 'targets':scope['targets'],
        'user_quote':scope['user_quote'], 'reason':'요청에 명시된 문서 전체'}
    def invoke(system,data,schema,phase,*args):
        calls.append(phase);out=deepcopy(value)
        if always_missing or len(calls)==1:out['search']['scope_decision']['targets'][0]['selection']={'coordinate_scope':'body','groups':[{'parent_path':[],'unit':'조','include':[{'kind':'SINGLE','value':{'n':99}}],'exclude':[]}]}
        return out
    request={'question':question,'document_ids':['d'],'use_llm':False}
    with p.term_agent.open_session(request,query=p.plan(question,['d']),runtime=tmp_path/'native') as native:
        executor=S(binding={'synthetic':'required-scope'},model=S(ensure=lambda:native,pipeline=p),shortcut_flags={})
        context={'utterance':question,'goals':[],'knowledge':[],'wiki_links':{},'allowed_documents':[{'id':'d','name':'모의승인규정'}]}
        for attempt in range(2 if always_missing else 1):
            repo=Memory(tmp_path/'entry.sqlite',executor,invoke)
            repo._entry_body={**request,'session_id':'s','request_id':'same-request'}
            repo._entry_principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
            try:
                if always_missing:
                    with pytest.raises(OutputContractError) as caught:entry.run(repo,context)
                    assert caught.value.repairable is False
                    assert all(row['repairable'] is False for row in caught.value.issues)
                else:
                    entry.run(repo,context)
                    assert executor.request_entry['command']['search_scope_change']['operation']=='REPLACE'
                assert calls==['request-entry','request-entry-repair']
            finally:repo.close()
    p.store.close()
