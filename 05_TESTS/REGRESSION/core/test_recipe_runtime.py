"""Ordinary synthetic wiring contracts; no network or quality evaluation."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lawrag.core.structure import recipe_runtime as runtime
from lawrag.core.structure import recipe_visual_loop as loop
from lawrag.core.structure.model import Block, Candidate
from semantic_runtime import genos
from lawrag.core import llm
import requests

RECIPE = {"tag": "test_recipe", "version": 1, "levels": [["heading"], ["number"]]}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    # Preserve the previous protocol's regression suite; compact has its own
    # real-adapter/HTTP-mock integration cases in test_recipe_compact.py.
    monkeypatch.setenv('STRUCTURE_RECIPE_PROTOCOL','legacy')
    monkeypatch.setenv('STRUCTURE_RECIPE_ACCEPT_WARNINGS','off')
    monkeypatch.setenv("LLM_BACKEND", "genos")
    monkeypatch.setenv("STRUCTURE_RECIPE_VLM", "on")
    monkeypatch.setenv("GENOS_BASE_URL", "https://test.invalid")
    monkeypatch.setenv("GENOS_LLM_SERVING_ID", "123")
    monkeypatch.setenv("GENOS_LLM_MODEL", "test-qwen-vl")
    monkeypatch.setenv("GENOS_LLM_KEY", "TEST-SECRET-NEVER-LOG")
    monkeypatch.setenv("GENOS_GATEWAY_API_PREFIX", "none")
    monkeypatch.setenv("GENOS_LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("GENOS_LLM_TIMEOUT", "30")
    monkeypatch.setenv("GENOS_LLM_JSON_MODE", "prompt")
    monkeypatch.setenv("GENOS_LLM_TEMPERATURE", "0")
    monkeypatch.delenv("GENOS_LLM_URL", raising=False)
    monkeypatch.delenv("STRUCTURE_RECIPE_TAGS", raising=False)
    def no_network(*a, **k):
        raise AssertionError("Live network forbidden in wiring contracts")
    monkeypatch.setattr(genos, "request_json", no_network)
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(llm, "load_env", lambda: None)


def response(value, finish="stop"):
    if "verdict" in value:value={**value,"opinion_decisions":value.get("opinion_decisions",[])}
    return {"model": "test-qwen-vl", "choices": [{"finish_reason": finish,
            "message": {"content": json.dumps(value)}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3}}


def test_switch_and_policy(monkeypatch):
    assert runtime.enabled()
    before = runtime.policy_identity()
    monkeypatch.setenv("GENOS_LLM_KEY", "NEW-SECRET")
    assert runtime.policy_identity() == before
    monkeypatch.setenv("GENOS_LLM_MODEL", "other")
    assert runtime.policy_identity() != before
    monkeypatch.setenv("STRUCTURE_RECIPE_VLM", "off")
    assert not runtime.enabled()
    monkeypatch.setenv("STRUCTURE_RECIPE_VLM", "auto")
    assert runtime.enabled()
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    assert not runtime.enabled()


def test_numeric_token_setting_does_not_corrupt_json_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTURE_RECIPE_MAX_TOKENS", "4096")
    journal = runtime.Journal(tmp_path, "test.pdf")
    journal.event("test", output_count=4096, nested=[{"secret": "TEST-SECRET-NEVER-LOG"}], image="data:image/png;base64,aGVsbG8=")
    value = json.loads((journal.directory / "events.jsonl").read_text())
    assert value["output_count"] == 4096
    assert value["nested"][0]["secret"] == "[REDACTED]"
    assert value["image"] == "[IMAGE OMITTED]"


def install_transport(monkeypatch, callback, models=None):
    """Mock only HTTP; exercise the unchanged production LLM streaming path."""
    class Reply:
        def __init__(self, body, status=200):
            self.body, self.status_code = body, status
            self.headers = {}
            self.text = "synthetic"
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError("HTTP " + str(self.status_code))
        def json(self):
            return self.body
        def iter_lines(self):
            choice = self.body['choices'][0]
            yield ('data: ' + json.dumps({
                'model': self.body.get('model', 'test-qwen-vl'),
                'choices': [{'delta': {'content': choice['message']['content']},
                             'finish_reason': choice['finish_reason']}],
                'usage': self.body.get('usage', {})})).encode()
            yield b'data: [DONE]'
    sessions=[]
    class Session:
        def __init__(self):
            self.headers={}; self.trust_env=True; self.calls=[]; sessions.append(self)
        def get(self, url, **kwargs):
            self.calls.append(('GET', url, kwargs))
            return Reply({'data':[{'id': i} for i in (models() if callable(models) else models or ['test-qwen-vl'])]})
        def post(self, url, **kwargs):
            self.calls.append(('POST', url, kwargs))
            body=callback(self, url, kwargs['json'])
            return Reply(body) if isinstance(body, dict) else Reply({}, body)
    monkeypatch.setattr(requests, 'Session', Session)
    return sessions


def test_existing_llm_generic_auth_path_stream_and_images(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_LLM_SERVING_ID','456')
    monkeypatch.setenv('GENOS_LLM_KEY','PROFILE-SECRET')
    monkeypatch.delenv('GENOS_LLM_MODEL',raising=False)
    sessions=install_transport(monkeypatch,lambda *a: {**response(RECIPE),'model':'site-vision-model'},models=['site-vision-model'])
    journal=runtime.Journal(tmp_path,'profile')
    provider=runtime.GenosCalls(journal,['data:image/png;base64,aGVsbG8='])
    from lawrag.core import llm as current_llm
    assert isinstance(provider.client,current_llm.LLM)
    assert provider.model=='site-vision-model'
    provider('review','test',{'full_text':'whole document'},loop.recipe_schema({'heading':{},'number':{}}),True)
    session=sessions[0]
    assert session.trust_env is False
    post=next(row[2]["json"] for row in session.calls if row[0]=="POST")
    assert post["chat_template_kwargs"]=={"enable_thinking":False}
    assert list(journal.directory.glob("call-*-provider-response.json"))
    assert session.headers['Authorization']=='Bearer PROFILE-SECRET'
    assert [r[1] for r in session.calls]==[
        'https://test.invalid/api/gateway/rep/serving/456/v1/models',
        'https://test.invalid/api/gateway/rep/serving/456/v1/chat/completions']
    body=session.calls[-1][2]['json']
    assert body['model']=='site-vision-model' and body['stream'] is True
    assert body['messages'][1]['content'][0]['type']=='image_url'
    assert json.loads(body['messages'][1]['content'][1]['text'])=={'full_text':'whole document'}
    text=''.join(p.read_text() for p in journal.directory.glob('*.json*'))
    assert 'PROFILE-SECRET' not in text and 'data:image' not in text


@pytest.mark.parametrize('finish',['length','content_filter'])
def test_incomplete_output_holds(tmp_path,monkeypatch,finish):
    install_transport(monkeypatch,lambda *a: response(RECIPE,finish))
    calls=runtime.GenosCalls(runtime.Journal(tmp_path,'x'),[])
    with pytest.raises(runtime.NeedsReview,match='existing_llm_call_failed'):
        calls('assemble','x',{}, {},False)


@pytest.mark.parametrize('status',[401,503])
def test_existing_llm_failure_not_retried_by_adapter(tmp_path,monkeypatch,status):
    sessions=install_transport(monkeypatch,lambda *a: status)
    calls=runtime.GenosCalls(runtime.Journal(tmp_path,'x'),[])
    with pytest.raises(runtime.NeedsReview,match='existing_llm_call_failed'):
        calls('assemble','x',{}, {},False)
    assert len(sessions[0].calls)==1


def test_explicit_profile_model_does_not_need_discovery(tmp_path,monkeypatch):
    sessions=install_transport(monkeypatch,lambda *a: response(RECIPE))
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'explicit'),[])
    assert provider.model=='test-qwen-vl' and not sessions[0].calls


def test_genos_documented_first_model_and_user_header(tmp_path,monkeypatch):
    # GENOS v1.8.6 LLM API: GET /v1/models, data[0].id,
    # Authorization Bearer and optional x-genos-user-id.
    monkeypatch.delenv('GENOS_LLM_MODEL',raising=False)
    monkeypatch.setenv('GENOS_USER_ID','653')
    sessions=install_transport(monkeypatch,lambda *a: response(RECIPE),models=['first','second'])
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'documented'),[])
    assert provider.model=='first'
    assert sessions[0].headers['x-genos-user-id']=='653'
    assert sessions[0].headers['Authorization']=='Bearer TEST-SECRET-NEVER-LOG'
    assert sessions[0].calls[0][1].endswith('/v1/models')


def test_existing_direct_serving_endpoint_is_preserved(tmp_path,monkeypatch):
    monkeypatch.setenv('GENOS_LLM_URL','https://configured.invalid/api/gateway/rep/serving/789')
    sessions=install_transport(monkeypatch,lambda *a: response(RECIPE))
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'direct'),['data:image/jpeg;base64,aGVsbG8='])
    provider('review','test',{}, {},True)
    assert sessions[0].calls[0][1]=='https://configured.invalid/api/gateway/rep/serving/789/v1/chat/completions'
    body=sessions[0].calls[0][2]['json']
    assert body['messages'][1]['content'][0]['image_url']['url']=='data:image/jpeg;base64,aGVsbG8='


def test_real_progress_consumer_allows_model_request_and_response(tmp_path,monkeypatch):
    from io import StringIO
    from lawrag.pipeline.genos_progress import Progress
    sessions=install_transport(monkeypatch,lambda *a: response(RECIPE))
    progress=Progress(tmp_path/'progress',StringIO())
    try:
        progress.document(1,1,'synthetic.pdf','구조화')
        with runtime.progress_events(progress.emit):
            journal=runtime.Journal(tmp_path/'calls','synthetic.pdf')
            provider=runtime.GenosCalls(journal,['data:image/png;base64,aGVsbG8='])
            assert provider('detect-format-regions','test',{}, {},True)==RECIPE
        assert len(sessions[0].calls)==1
        events=[json.loads(line) for line in (journal.directory/'events.jsonl').read_text().splitlines()]
        request=next(row for row in events if row['event']=='model.request')
        assert request['attempt']==1
        log=(tmp_path/'progress'/'progress.log').read_text()
        assert '시도 1' in log and '응답 대기' in log
        assert '입력/출력 5/3' in progress.state['detail']
    finally:
        progress.close()


def test_closed_schema_and_no_text_only_review(tmp_path,monkeypatch):
    sessions=install_transport(monkeypatch,lambda *a: response(RECIPE))
    calls=runtime.GenosCalls(runtime.Journal(tmp_path,'x'),[])
    with pytest.raises(runtime.NeedsReview,match='requires_images'):
        calls('review','x',{}, {},True)
    calls.images=['malformed-image']
    with pytest.raises(runtime.NeedsReview,match='invalid_visual_image'):
        calls('review','x',{}, {},True)
    assert not sessions[0].calls


def test_external_backend_rejected_before_client(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_BACKEND','anthropic')
    monkeypatch.setattr(llm,'LLM',lambda: pytest.fail('must not construct external client'))
    with pytest.raises(runtime.NeedsReview,match='requires_genos_backend'):
        runtime.GenosCalls(runtime.Journal(tmp_path,'x'),[])


def test_configured_json_mode_rejection_stops_without_hidden_retry(tmp_path,monkeypatch):
    monkeypatch.setenv('GENOS_LLM_JSON_MODE','json_schema')
    received=[]
    def reply(session,url,payload):
        received.append(payload)
        return 400 if len(received)==1 else response(RECIPE)
    install_transport(monkeypatch,reply)
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'schema'),['data:image/png;base64,aGVsbG8='])
    with pytest.raises(runtime.NeedsReview):provider('review','test',{}, {},True)
    assert len(received)==provider.calls==1
    assert received[0]['messages'][1]['content'][0]['image_url']['url']=='data:image/png;base64,aGVsbG8='
    assert 'response_format' in received[0]
    assert provider.client.log[-1].output_contract['category']=='REQUEST_SCHEMA_UNSUPPORTED'
    assert provider.client.log[-1].physical_calls==1


def test_schema_and_call_budget_still_enforced(tmp_path,monkeypatch):
    import jsonschema
    from lawrag.core.structure.recipe_output import ResponseError
    sessions=install_transport(monkeypatch,lambda *a: response({'wrong':True}))
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'schema'),[],max_calls=1)
    with pytest.raises(ResponseError) as failure:
        provider('assemble','test',{},loop.recipe_schema({'heading':{},'number':{}}),False)
    assert failure.value.__cause__.category=='OUTPUT_SHAPE_INVALID'
    assert failure.value.response=={'wrong':True}
    with pytest.raises(runtime.NeedsReview,match='model_call_budget'):
        provider('assemble','test',{}, {},False)
    assert len(sessions[0].calls)==1


def fixture_tree():
    nodes = []
    for i, family in enumerate(("heading", "number")):
        value = {"family": family, "block_idx": i, "span": [i, 2]}
        nodes.append(SimpleNamespace(family=family, block_idx=i, surface=family,
                     span=(i, 2), ordinal=None if i == 0 else (1,), candidate_id=f"c{i}", children=[], dump=lambda v=value: v))
    return SimpleNamespace(nodes=lambda: nodes, tree=nodes, ladder=SimpleNamespace(dump=lambda: [["heading"], ["number"]]),
                           fitness_passed=True, fitness_score=1, warnings=[],
                           candidates=[Candidate(id=f"c{i}",family=family,surface=family,ordinal=None if i==0 else (1,),block_idx=i,offset=0,end=len(family),text=family) for i,family in enumerate(("heading","number"))], stats={})


def fixture_pdf(tmp_path):
    import fitz
    path = tmp_path / "test.pdf"
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(path)
    return path






def test_native_pdf_ingest_dispatch(tmp_path, monkeypatch):
    from lawrag.core import ingest
    from lawrag.core.structure import viewer
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"test")
    monkeypatch.setattr(ingest, "parse_cached", lambda *a: SimpleNamespace(elements=[], images=[], warnings=[], parser="fake"))
    calls = []
    def revise(*a, **kw):
        calls.append(kw)
        return fixture_tree(), {"status": "visual_approved", "tag": "test", "model_calls": 2}
    monkeypatch.setattr(runtime, "revise_pdf", revise)
    monkeypatch.setattr(viewer, "payload", lambda *a, **kw: {})
    data = ingest.interpret_doc(pdf, store=tmp_path / "store", recipe_document="law/test.pdf")
    assert data["recipe_review"]["status"] == "visual_approved"
    assert calls[0]["document"] == "law/test.pdf"
    assert ingest.structured_by(data, "pdf") == "recipe-vlm:test"


def test_explicit_format_keeps_precedence(tmp_path, monkeypatch):
    from lawrag.core import ingest
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"test")
    monkeypatch.setattr(ingest, "parse_cached", lambda *a: None)
    monkeypatch.setattr(ingest, "_interpret_with_format", lambda *a: {"bound": True})
    monkeypatch.setattr(runtime, "revise_pdf", lambda *a, **k: pytest.fail("must preserve manual format"))
    result = ingest.interpret_doc(pdf, store=tmp_path, doc_id="test", binding_of=lambda *a: "manual")
    assert result["bound"]


def test_invalid_json_handed_to_owner_without_adapter_retry(tmp_path,monkeypatch):
    from lawrag.core.structure.recipe_output import ResponseError
    body=response(RECIPE);body['choices'][0]['message']['content']='not JSON'
    sessions=install_transport(monkeypatch,lambda *a: body)
    calls=runtime.GenosCalls(runtime.Journal(tmp_path,'x'),[])
    with pytest.raises(ResponseError) as failure:
        calls('assemble','x',{}, {},False)
    assert failure.value.response=='not JSON'
    assert failure.value.diagnostic['code']=='INVALID_MODEL_JSON'
    assert len(sessions[0].calls)==1


def test_off_dispatch_uses_legacy_engine(tmp_path, monkeypatch):
    from lawrag.core import ingest
    from lawrag.core.structure import pipeline, viewer, fingerprint
    monkeypatch.setenv("STRUCTURE_RECIPE_VLM", "off")
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"test")
    monkeypatch.setattr(ingest, "parse_cached", lambda *a: SimpleNamespace(elements=[], images=[], warnings=[], parser="fake"))
    monkeypatch.setattr(runtime, "revise_pdf", lambda *a, **k: pytest.fail("rollback must not invoke new runtime"))
    seen = []
    def interpret(*a, **k):
        seen.append(k)
        return SimpleNamespace(stats={})
    monkeypatch.setattr(pipeline, "interpret", interpret)
    monkeypatch.setattr(fingerprint.Ledger, "load", lambda *a: SimpleNamespace(save=lambda: None))
    monkeypatch.setattr(viewer, "payload", lambda *a, **k: {})
    result = ingest.interpret_doc(pdf, store=tmp_path)
    assert len(seen) == 1 and "recipe_review" not in result

# Missing-marker induction uses real structure engine + synthetic blocks and model replies.
from copy import deepcopy
from lawrag.core.structure import pipeline, recipe_rules
from lawrag.core.structure.model import Block

RULES = [{"id": "auto_headword", "match": {"bold": True, "max_chars": 40}, "examples": [0, 2]}]


def glossary_blocks(numbered=False):
    blocks = [Block(0, "경제용어가", bold=True, size_ratio=1.3),
              Block(1, "어떤 상태를 뜻하는 정의 문장이다.", size_ratio=1),
              Block(2, "경제용어나", bold=True, size_ratio=1.3),
              Block(3, "다른 상태를 뜻하는 정의 문장이다.", size_ratio=1)]
    if numbered:
        blocks.append(Block(4, "1. 세부 사항", size_ratio=1))
    return blocks












def test_rule_overlap_and_dropped_anchors_rejected():
    blocks = glossary_blocks()
    with pytest.raises(ValueError, match="overlap"):
        recipe_rules.validate(RULES, blocks, protected=[0])
    duplicate = deepcopy(RULES[0]); duplicate["id"] = "auto_other"
    with pytest.raises(ValueError, match="overlap"):
        recipe_rules.validate(RULES + [duplicate], blocks)
    empty = SimpleNamespace(interpret=lambda *a, **k: SimpleNamespace(nodes=lambda: [], candidates=[]))
    with pytest.raises(ValueError, match="dropped"):
        recipe_rules.RuleEngine(empty, RULES, blocks).interpret(blocks)



# The default runtime now uses region detection and family grammars. The former
# per-instance/generated-rule protocol is covered only by its low-level unit tests.
def regional_document(tmp_path, count=2):
    import fitz
    pdf=tmp_path/'source.pdf';blocks=[]
    with fitz.open() as doc:
        for i in range(count):
            page=doc.new_page();page.insert_text((50,50),'Synthetic article')
            blocks.append(Block(i,f'제{i+1}조(제목) 본문',page=i+1,bbox=[50,40,400,65],bbox_origin='TOPLEFT'))
        doc.save(pdf)
    return pdf,blocks

def regional_provider(monkeypatch, verdict='approve', invalid_parent=False, fail_phase=None, noop=False,
                      bad_stage=None, bad_kind='schema'):
    seen=[]
    injected=False
    def request(target,path,payload):
        nonlocal injected
        content=payload['messages'][1]['content']
        data=json.loads(content if isinstance(content,str) else next(b['text'] for b in content if b['type']=='text'));seen.append(data)
        stage=('detect' if 'outline' in data else 'template' if 'region_instances' in data
               else 'adjudicate' if 'reviewed_state_id' in data else 'opinions')
        if stage==bad_stage and not injected:
            injected=True
            if bad_kind=='http':return 401
            bad=response({'wrong':True})
            if bad_kind=='json':bad['choices'][0]['message']['content']='{"invalid":'
            return bad
        if ((fail_phase == 'detect' and 'outline' in data) or
                (fail_phase == 'review' and 'recipe' in data and 'reviewed_state_id' not in data)):
            return response({'private': 'PRIVATE-MODEL-OUTPUT'}, 'length')
        if 'recipe' in data and 'reviewed_state_id' not in data:return response({'opinions':[],'summary':'No visual defects observed'})
        if 'outline' in data:
            value={'regions':[{'start_block':0,'template_id':'body','label':'body','reason':'continuous format'}]}
        elif 'region_instances' in data:
            value={'families':{f:{'parent_family':'missing' if invalid_parent else '$document','heading_position':'line_start','sequence':'consecutive','reset_scope':'document','rationale':'synthetic source'} for f in data['catalog']}}
        else:
            value={'verdict':verdict,'reviewed_state_id':data['reviewed_state_id'],'issues':[] if verdict=='approve' else [{'blocks':[data['source_blocks'][0]['idx']],'reason':'source requires review'}],'template_changes':[]}
            if noop:
                tid=next(iter(data['recipe']['templates']))
                family=next(iter(data['recipe']['templates'][tid]['heading_rules']))
                rule=deepcopy(data['recipe']['templates'][tid]['heading_rules'][family])
                rule['rationale']='Another explanation without executable changes'
                value.update(verdict='revise',issues=[],template_changes=[{'template_id':tid,'family':family,'rule':rule}])
        return response(value)
    install_transport(monkeypatch,request)
    return seen


@pytest.mark.parametrize('stage,key', [('detect','invalid_plan'),('template','invalid_template'),
                                     ('opinions','invalid_opinions'),('adjudicate','invalid_review')])
@pytest.mark.parametrize('kind', ['json','schema'])
def test_invalid_answers_reach_owning_repair_loop(tmp_path,monkeypatch,stage,key,kind):
    pdf,blocks=regional_document(tmp_path)
    seen=regional_provider(monkeypatch,bad_stage=stage,bad_kind=kind)
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='source')
    repairs=[data for data in seen if key in data]
    assert len(repairs)==1
    correction=repairs[0]
    assert correction[key]==('{"invalid":' if kind=='json' else {'wrong':True})
    error=correction['repair_feedback']['error']
    assert error['code']==('INVALID_MODEL_JSON' if kind=='json' else 'INVALID_RESPONSE_SCHEMA')
    if kind=='schema':assert error['constraint']=='additionalProperties' and error['actual']=={'wrong':True}
    else:assert error['line']==1 and error['column']==12 and error['message']=='Expecting value'
    assert correction['repair_feedback']['remaining_attempts']==1
    assert correction['source_blocks'] and 'TEST-SECRET-NEVER-LOG' not in json.dumps(correction)
    assert len(tree.nodes())==2 and meta['status']=='visual_approved'


@pytest.mark.parametrize('stage', ['detect','template','opinions','adjudicate'])
def test_http_failure_is_not_repackaged_as_model_repair(tmp_path,monkeypatch,stage):
    pdf,blocks=regional_document(tmp_path)
    seen=regional_provider(monkeypatch,bad_stage=stage,bad_kind='http')
    with pytest.raises(runtime.NeedsReview) as failure:
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='source')
    assert failure.value.diagnostic['code']=='existing_llm_call_failed'
    assert len(seen)=={'detect':1,'template':2,'opinions':3,'adjudicate':4}[stage]
    assert not any('repair_feedback' in data for data in seen)
    assert not (tmp_path/'structure-recipes.json').exists()


def test_noop_review_cause_and_exact_pending_path_survive_runtime(tmp_path,monkeypatch):
    pdf,blocks=regional_document(tmp_path)
    regional_provider(monkeypatch,noop=True)
    with pytest.raises(runtime.NeedsReview) as failure:
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='source')
    diagnostic=failure.value.diagnostic
    assert diagnostic['code']=='NO_EXECUTABLE_CHANGE'
    assert '실행 규칙이 현재와 동일함' in str(failure.value)
    pending=Path(diagnostic['response_path'])
    assert pending.is_file() and str(pending) in str(failure.value)
    assert json.loads(pending.read_text())['rule_comparison'][0]['changed_fields']==[]
    assert not (tmp_path/'structure-recipes.json').exists()


@pytest.mark.parametrize('max_tokens,phase', [(4096, 'detect'), (80000, 'detect'), (80000, 'review')])
def test_output_limit_reaches_error_summary_console_and_status(tmp_path, monkeypatch, max_tokens, phase):
    from io import StringIO
    from lawrag.pipeline import genos_build, genos_status
    from lawrag.pipeline.genos_progress import Progress

    monkeypatch.setenv('STRUCTURE_RECIPE_MAX_TOKENS', str(max_tokens))
    pdf, blocks = regional_document(tmp_path)
    regional_provider(monkeypatch, fail_phase=phase)
    def ingest(*args):
        runtime.revise_pdf(pipeline, blocks, pdf, store=tmp_path/'store', document='synthetic')
    monkeypatch.setattr(genos_build, '_ingest_files', ingest)
    row = {'document_id': 'synthetic', 'path': str(pdf), 'relative': 'synthetic.pdf', 'source': 'internal'}
    class Terminal(StringIO):
        def isatty(self):
            return True
    terminal = Terminal()
    progress = Progress(tmp_path/'logs', terminal)
    ledger = genos_status.Ledger(tmp_path/'logs').start([row], 'structure')
    try:
        progress.document(1, 1, row['relative'], '구조화')
        with pytest.raises(ValueError) as failure:
            with runtime.progress_events(progress.emit):
                genos_build.ingest_files({'files': [row]}, tmp_path, progress.emit)
        progress.error(failure.value)
        ledger.update('synthetic', 'structure', 'FAILED', error=str(failure.value))
        ledger.finish()
        reports = genos_status.export_report(tmp_path/'logs')
        entry = json.loads((tmp_path/'structure-errors.json').read_text())[0]
        diagnosis = entry['diagnostic']
        assert diagnosis['code'] == 'OUTPUT_LENGTH_LIMIT'
        assert diagnosis['max_tokens'] == max_tokens
        assert diagnosis['output_tokens'] == 3
        response_path = Path(diagnosis['response_path'])
        assert json.loads(response_path.read_text())['stop_reason'] == 'max_tokens'
        assert '출력 토큰 한도 초과' in str(failure.value)
        assert f'max_tokens={max_tokens}' in str(failure.value)
        if max_tokens == 80000:
            assert '요청 분할 또는 출력량 축소' in diagnosis['next_action']
        assert str(response_path) in terminal.getvalue().split('실패 원인: ')[-1]
        assert 'max_tokens=' + str(max_tokens) in terminal.getvalue()
        current = json.loads((tmp_path/'logs/current.json').read_text())
        assert '출력 토큰 한도' in current['detail']
        assert current['status'] == 'FAILED'
        for path in reports.values():
            if Path(path).suffix in {'.html', '.csv'}:
                report = Path(path).read_text()
                assert f'max_tokens={max_tokens}' in report
                assert str(response_path) in report
        summary = (tmp_path/'structure-errors.json').read_text() + terminal.getvalue()
        assert 'PRIVATE-MODEL-OUTPUT' not in summary
        assert 'TEST-SECRET-NEVER-LOG' not in summary
        assert 'LLM 호출 전 구조화 실패' not in summary
        assert not (tmp_path/'structure-recipes.json').exists()
    finally:
        progress.close()
        ledger.close()

def test_region_tag_reuses_same_model_source_and_exact_tree(tmp_path,monkeypatch):
    pdf,blocks=regional_document(tmp_path);seen=regional_provider(monkeypatch)
    kw=dict(store=tmp_path/'store',document='source')
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,**kw)
    assert meta['process']=='region-templates' and meta['region_count']==meta['template_count']==1
    count=len(seen);again,cached=runtime.revise_pdf(pipeline,blocks,pdf,**kw)
    assert cached['reused'] and cached['model_calls']==0 and len(seen)==count
    assert cached['model']==meta['model'] and cached['backend']=='genos'
    assert loop.tree_record(tree)==loop.tree_record(again)
    tags=tmp_path/'structure-recipes.json';value=json.loads(tags.read_text());value['documents']['source']['recipe']['version']=2;runtime.atomic(tags,value)
    with pytest.raises(runtime.NeedsReview):runtime.revise_pdf(pipeline,blocks,pdf,**kw)
    assert len(seen)==count

@pytest.mark.parametrize('verdict',['hold','missing_rules','source_error'])
def test_region_hold_never_publishes_or_runs_individual_rule_generation(tmp_path,monkeypatch,verdict):
    pdf,blocks=regional_document(tmp_path);seen=regional_provider(monkeypatch,verdict)
    with pytest.raises(runtime.NeedsReview):runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='held')
    assert not (tmp_path/'structure-recipes.json').exists()
    assert any('recipe' in d for d in seen) and not any('protected_anchors' in d for d in seen)

def test_invalid_region_family_parent_is_bounded_and_not_published(tmp_path,monkeypatch):
    pdf,blocks=regional_document(tmp_path);seen=regional_provider(monkeypatch,invalid_parent=True)
    with pytest.raises(runtime.NeedsReview):runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='bad')
    assert len([d for d in seen if 'region_instances' in d])==2
    assert not (tmp_path/'structure-recipes.json').exists()

def test_document_page_budget_before_provider(tmp_path,monkeypatch):
    pdf,blocks=regional_document(tmp_path);seen=regional_provider(monkeypatch)
    monkeypatch.setenv('STRUCTURE_RECIPE_MAX_DOCUMENT_PAGES','1')
    with pytest.raises(runtime.NeedsReview) as error:runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='big')
    assert 'document_page_budget_exceeded' in str(error.value.__cause__) and not seen

def test_region_font_and_model_settings_invalidate_cache(tmp_path,monkeypatch):
    pdf,blocks=regional_document(tmp_path);seen=regional_provider(monkeypatch);kw=dict(store=tmp_path/'store',document='font')
    runtime.revise_pdf(pipeline,blocks,pdf,**kw);count=len(seen)
    blocks[0].font_name='ChangedFont';_,meta=runtime.revise_pdf(pipeline,blocks,pdf,**kw)
    assert not meta['reused'] and len(seen)>count
    before=runtime.policy_identity();monkeypatch.setenv('GENOS_LLM_MODEL','stronger-model');assert runtime.policy_identity()!=before
