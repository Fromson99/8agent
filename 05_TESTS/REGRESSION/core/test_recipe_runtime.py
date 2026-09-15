"""Ordinary synthetic wiring contracts; no network or quality evaluation."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lawrag.core.structure import recipe_runtime as runtime
from lawrag.core.structure import recipe_visual_loop as loop
from lawrag.core.structure.model import Block, Candidate
from semantic_runtime import genos

RECIPE = {"tag": "test_recipe", "version": 1, "levels": [["heading"], ["number"]]}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "genos")
    monkeypatch.setenv("STRUCTURE_RECIPE_VLM", "on")
    monkeypatch.setenv("GENOS_LLM_PROFILE", "qwen")
    monkeypatch.setenv("GENOS_BASE_URL", "https://test.invalid")
    monkeypatch.setenv("GENOS_QWEN_SERVING_ID", "123")
    monkeypatch.setenv("GENOS_QWEN_MODEL", "test-qwen-vl")
    monkeypatch.setenv("GENOS_QWEN_KEY", "TEST-SECRET-NEVER-LOG")
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


def response(value, finish="stop"):
    return {"model": "test-qwen-vl", "choices": [{"finish_reason": finish,
            "message": {"content": json.dumps(value)}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3}}


def test_switch_and_policy(monkeypatch):
    assert runtime.enabled()
    before = runtime.policy_identity()
    monkeypatch.setenv("GENOS_QWEN_KEY", "NEW-SECRET")
    assert runtime.policy_identity() == before
    monkeypatch.setenv("GENOS_QWEN_MODEL", "other")
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


def test_multimodal_payload_retry_and_safe_logs(tmp_path, monkeypatch):
    received = []
    def request(target, path, payload):
        received.append(payload)
        assert target.root == "https://test.invalid/api/gateway/rep/serving/123"
        assert path == "/chat/completions"
        assert target.max_retries == 1
        if len(received) == 1:
            raise genos.ServingError("GENOS request failed after 1 attempts: HTTP 429")
        return response(RECIPE)
    monkeypatch.setattr(runtime.time, "sleep", lambda _: None)
    journal = runtime.Journal(tmp_path, "law/test.pdf")
    calls = runtime.GenosCalls(journal, ["data:image/png;base64,aGVsbG8="], request=request)
    assert calls("test", "test", {}, loop.recipe_schema({"heading": {}, "number": {}}), True) == RECIPE
    assert received[0] == received[1]
    assert received[1]["messages"][1]["content"][1]["type"] == "image_url"
    text = (journal.directory / "events.jsonl").read_text()
    assert "model.retry" in text and "input_count" in text
    assert "TEST-SECRET-NEVER-LOG" not in text and "data:image" not in text


@pytest.mark.parametrize("finish", ["length", "content_filter", None])
def test_incomplete_output_holds(tmp_path, finish):
    calls = runtime.GenosCalls(runtime.Journal(tmp_path, "x"), [], request=lambda *a: response(RECIPE, finish))
    with pytest.raises(runtime.NeedsReview, match="incomplete"):
        calls("assemble", "x", {}, loop.recipe_schema({"heading": {}, "number": {}}), False)


def test_no_auth_retry(tmp_path):
    count = []
    def request(*a):
        count.append(1)
        raise genos.ServingError("GENOS HTTP 401")
    calls = runtime.GenosCalls(runtime.Journal(tmp_path, "x"), [], request=request)
    with pytest.raises(genos.ServingError):
        calls("assemble", "x", {}, {}, False)
    assert count == [1]


def test_closed_schema_and_no_text_only_review(tmp_path):
    calls = runtime.GenosCalls(runtime.Journal(tmp_path, "x"), [], request=lambda *a: response(RECIPE))
    with pytest.raises(runtime.NeedsReview, match="requires_images"):
        calls("review", "x", {}, {}, True)


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


def test_exhausted_transient_budget(tmp_path, monkeypatch):
    attempts = []
    def request(*a):
        attempts.append(1)
        raise genos.ServingError("GENOS request failed after 1 attempts: HTTP 503")
    monkeypatch.setattr(runtime.time, "sleep", lambda _: None)
    calls = runtime.GenosCalls(runtime.Journal(tmp_path, "x"), [], request=request)
    with pytest.raises(genos.ServingError):
        calls("assemble", "x", {}, {}, False)
    assert len(attempts) == 2


def test_invalid_json_not_retried(tmp_path):
    attempts = []
    def request(*a):
        attempts.append(1)
        body = response(RECIPE)
        body["choices"][0]["message"]["content"] = "not JSON"
        return body
    calls = runtime.GenosCalls(runtime.Journal(tmp_path, "x"), [], request=request)
    with pytest.raises(json.JSONDecodeError):
        calls("assemble", "x", {}, {}, False)
    assert len(attempts) == 1




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

def regional_provider(monkeypatch, verdict='approve', invalid_parent=False):
    seen=[]
    def request(target,path,payload):
        data=json.loads(payload['messages'][1]['content'][0]['text']);seen.append(data)
        if 'outline' in data:
            value={'regions':[{'start_block':0,'template_id':'body','label':'body','reason':'continuous format'}]}
        elif 'region_instances' in data:
            value={'families':{f:{'parent_family':'missing' if invalid_parent else '$document','heading_position':'line_start','sequence':'consecutive','reset_scope':'document','rationale':'synthetic source'} for f in data['catalog']}}
        else:
            value={'verdict':verdict,'reviewed_state_id':data['reviewed_state_id'],'issues':[] if verdict=='approve' else [{'blocks':[data['source_blocks'][0]['idx']],'reason':'source requires review'}],'template_changes':[]}
        return response(value)
    monkeypatch.setattr(genos,'request_json',request)
    return seen

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
    assert len([d for d in seen if 'region_instances' in d])==3
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
    before=runtime.policy_identity();monkeypatch.setenv('GENOS_QWEN_MODEL','stronger-model');assert runtime.policy_identity()!=before
