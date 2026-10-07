"""PDF region-template generation and bbox review for MAIN document ingestion.

No dynamic research imports, external provider fallback, or legal meaning changes.
An unsuccessful visual review raises NeedsReview; never publishes a failed tree.
"""
from __future__ import annotations

import base64
import copy
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import uuid

from . import recipe_visual_loop as loop
from . import recipe_rules

VERSION = "genos-recipe-v37-disclosure-budget-diagnostics"


def accepts_warnings():
    value = os.environ.get('STRUCTURE_RECIPE_ACCEPT_WARNINGS', 'on').strip().lower()
    if value not in {'on','off'}:
        raise ValueError('STRUCTURE_RECIPE_ACCEPT_WARNINGS must be on or off')
    return value == 'on' and os.environ.get('STRUCTURE_RECIPE_PROTOCOL','basic') == 'basic'
_PROGRESS = ContextVar("structure_recipe_progress", default=None)


@contextmanager
def progress_events(emit):
    """Bind this ingestion's progress consumer without a global logging handler."""
    token = _PROGRESS.set(emit)
    try:
        yield
    finally:
        _PROGRESS.reset(token)


class NeedsReview(ValueError):
    repairable = False

    def __init__(self, message, *, diagnostic=None):
        super().__init__(message)
        self.diagnostic = diagnostic


def call_failure(exchange, *, phase, max_tokens, response_path):
    """Public diagnosis uses known categories, never provider text or source content."""
    code = 'existing_llm_call_failed'
    summary = 'LLM 호출 실패'
    action = '상세 응답 파일의 error 항목 확인'
    if exchange.stop_reason == 'max_tokens':
        code = 'OUTPUT_LENGTH_LIMIT'
        summary = f'출력 토큰 한도 초과로 응답 잘림 (max_tokens={max_tokens})'
        action = ('모델 지원 한도 내 STRUCTURE_RECIPE_MAX_TOKENS 조정 후 재실행'
                  if max_tokens < 80000 else
                  '현재 코드의 출력 상한 80000 도달; 요청 분할 또는 출력량 축소 필요')
    elif exchange.stop_reason == 'refusal':
        code, summary = 'MODEL_REFUSAL', '모델이 요청을 거절함'
    elif exchange.error.startswith('JSONDecodeError:'):
        code, summary = 'INVALID_MODEL_JSON', '모델 응답의 JSON 해석 실패'
    diagnostic = {'code': code, 'summary': summary, 'phase': phase,
                  'max_tokens': max_tokens, 'next_action': action,
                  'response_path': str(response_path)}
    output = exchange.usage.get('output_tokens')
    if type(output) is int:
        diagnostic['output_tokens'] = output
    message = (f'{summary}; 단계={phase}; {action}; 상세: {response_path} '
               f'[{code}; existing_llm_call_failed]')
    return NeedsReview(message, diagnostic=diagnostic)


class MeasuredEngine:
    def __init__(self, engine, journal):
        self.engine, self.journal = engine, journal

    def interpret(self, *args, **kwargs):
        with self.journal.step("structure.rebuild"):
            return self.engine.interpret(*args, **kwargs)


def enabled() -> bool:
    """Same switch locally and onsite; explicit off never initializes a provider."""
    mode = os.environ.get("STRUCTURE_RECIPE_VLM", "auto").lower().strip()
    if mode not in {"auto", "on", "off"}:
        raise ValueError("STRUCTURE_RECIPE_VLM must be auto, on or off")
    return mode == "on" or (mode == "auto" and os.environ.get("LLM_BACKEND", "").lower() == "genos")


def policy_identity():
    """Cache identity without keys. Structural models now affect PDF parsing outputs."""
    active = enabled()
    if not active:
        return {"enabled": False, "version": VERSION}
    names = ["GENOS_BASE_URL", "GENOS_LLM_URL", "GENOS_GATEWAY_API_PREFIX", "GENOS_LLM_API_PREFIX",
             "GENOS_LLM_MODEL", "GENOS_LLM_SERVING_ID",
             "GENOS_LLM_JSON_MODE", "GENOS_LLM_TEMPERATURE", "STRUCTURE_RECIPE_MAX_PAGES",
             "STRUCTURE_RECIPE_MAX_CHARS", "STRUCTURE_RECIPE_MAX_TOKENS",
             "STRUCTURE_RECIPE_REVIEW_MODE", "STRUCTURE_RECIPE_MAX_DOCUMENT_PAGES",
             "STRUCTURE_RECIPE_MAX_CALLS", "STRUCTURE_RECIPE_MAX_RULE_ROUNDS", "STRUCTURE_RECIPE_MAX_CORRECTIONS",
             "STRUCTURE_RECIPE_PROTOCOL", "STRUCTURE_RECIPE_REVIEW_MAX_CHARS",
             "STRUCTURE_RECIPE_ACCEPT_WARNINGS", "STRUCTURE_RECIPE_REVIEW_MAX_TOKENS"]
    return {"enabled": True, "version": VERSION,
            "llm_code_sha256": sha(Path(__file__).parents[1] / "llm.py"),
            "settings_sha256": loop.digest({name: os.environ.get(name) for name in names})}


def integer(name, default, low, high):
    value = int(os.environ.get(name, str(default)))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class Journal:
    def __init__(self, root, document):
        from semantic_runtime import observability as obs
        self.obs = obs
        self.logger = obs.get_logger("structure.recipe")
        self.run_id = uuid.uuid4().hex
        self.directory = Path(root) / self.run_id
        self.directory.mkdir(parents=True, mode=0o700)
        self.document = document
        self.emit = _PROGRESS.get()
        self.lock = threading.Lock()

    def event(self, name, **fields):
        # Only metadata supplied by this module: never arbitrary provider objects.
        row = {"ts": datetime.now(timezone.utc).isoformat(), "event": name,
               "run_id": self.run_id, "document": self.document, **fields}
        def clean(value):
            if isinstance(value, str):
                return re.sub(r"data:image/[^,\s]+,[A-Za-z0-9+/=]+", "[IMAGE OMITTED]", self.obs._redact_secrets(value))
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [clean(v) for v in value]
            return value
        level = (logging.ERROR if name in {"stage.error", "run.needs_review"} else
                 logging.WARNING if name in {"model.error", "model.retry"} else
                 logging.DEBUG if name in {"artifact.saved", "page.rendered", "stage.wait", "stage.start", "stage.end"} else logging.INFO)
        safe_row = clean({**row, "level": logging.getLevelName(level)})
        encoded = json.dumps(safe_row, ensure_ascii=False)
        with self.lock:
            fd = os.open(self.directory / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
        self.obs.event(self.logger, name, level=level,
                       **{k: v for k, v in safe_row.items() if k not in {"ts", "event", "level"}})
        if self.emit and (name.startswith("recipe.") or name in {
                "model.request", "model.response", "model.retry", "run.complete", "run.needs_review"}):
            self.emit("[STRUCTURE VLM] " + encoded)

    def save(self, name, value):
        atomic(self.directory / name, value)
        self.event("artifact.saved", artifact=name, sha256=sha(self.directory / name))

    @contextmanager
    def step(self, phase):
        started = time.monotonic()
        stopped = threading.Event()
        self.event("stage.start", phase=phase)

        def heartbeat():
            while not stopped.wait(10):
                self.event("stage.wait", phase=phase, seconds=round(time.monotonic() - started, 3))

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            yield
        except Exception as exc:
            self.event("stage.error", phase=phase, error_type=type(exc).__name__)
            raise
        finally:
            stopped.set()
            thread.join()
            self.event("stage.end", phase=phase, seconds=round(time.monotonic() - started, 3))


class GenosCalls:
    """Structure adapter over the existing product LLM, including its VLM path."""

    def __init__(self, journal, images, *, max_calls=9):
        from lawrag.core import llm
        # Check before constructing a client: internal PDFs must stay on GENOS.
        if llm.backend() != "genos":
            raise NeedsReview("visual_structure_requires_genos_backend")
        self.journal, self.images = journal, images
        self.protocol = os.environ.get('STRUCTURE_RECIPE_PROTOCOL', 'basic').strip().lower()
        if self.protocol not in {'basic', 'compact', 'legacy'}:
            raise ValueError('STRUCTURE_RECIPE_PROTOCOL must be basic, compact or legacy')
        self.calls = 0
        self.max_calls = max_calls
        self.max_tokens = integer("STRUCTURE_RECIPE_MAX_TOKENS", 80000, 256, 80000)
        self.client = llm.LLM()
        self.model = self.client.model
        if not self.model:
            raise NeedsReview("existing_llm_model_discovery_failed; see LLM /v1/models log")
        journal.event("provider.configured", backend="genos", model=self.model,
                      caller="lawrag.core.llm.LLM.structured", protocol=self.protocol)

    def __call__(self, phase, system, data, schema, vision):
        if self.protocol == 'compact':
            from .recipe_compact import route
            return route(self._request, self.journal, phase, system, data, schema, vision)
        return self._request(phase, system, data, schema, vision)

    def _request(self, phase, system, data, schema, vision):
        import jsonschema
        from .recipe_output import COMPACT, ResponseError
        system += COMPACT
        if self.calls >= self.max_calls:
            raise NeedsReview("model_call_budget_exhausted", diagnostic={
                'code': 'model_call_budget_exhausted', 'phase': phase,
                'calls': self.calls, 'max_calls': self.max_calls,
                'summary': '문서별 모델 호출 횟수 상한 도달 (입력 토큰 한도와 별개)',
                'next_action': 'review-budget.json의 검수 창 수와 호출 상한을 확인하세요.'})
        if vision and not self.images:
            raise NeedsReview("visual_review_requires_images")
        if vision and any(not isinstance(uri, str) or not uri.startswith("data:image/")
                          or not uri.partition(",")[2] for uri in self.images):
            raise NeedsReview("invalid_visual_image")
        serialized = json.dumps(data, ensure_ascii=False)
        limit = integer("STRUCTURE_RECIPE_MAX_CHARS", 160000, 1000, 500000)
        if self.protocol == 'basic':
            limit = min(limit, integer('STRUCTURE_RECIPE_REVIEW_MAX_CHARS', 24000, 1000, 100000))
        if len(serialized) > limit:
            raise NeedsReview("document_context_budget_exceeded")
        self.calls += 1
        max_tokens = self.max_tokens
        if self.protocol == 'basic' and accepts_warnings():
            max_tokens = min(max_tokens, integer('STRUCTURE_RECIPE_REVIEW_MAX_TOKENS',80000,256,80000))
        self.journal.save(f"call-{self.calls}-{phase}-input.json", {
            "system": system, "data": data, "schema": schema, "model": self.model,
            "image_count": len(self.images) if vision else 0, "max_tokens":max_tokens,
            "enable_thinking": False,
            "caller": "lawrag.core.llm.LLM.structured", "images_omitted": True})
        with self.journal.step(phase):
            self.journal.event("model.request", phase=phase, call=self.calls, attempt=1,
                               model=self.model, image_count=len(self.images) if vision else 0)
            with self.journal.obs.context(run_id=self.journal.run_id, document=self.journal.document, phase=phase):
                value = self.client.structured(
                    kind="structure_recipe_" + phase, system=system, user=serialized,
                    schema=schema, max_tokens=max_tokens,
                    images=list(self.images) if vision else None, enable_thinking=False)
            exchange = self.client.log[-1]
            self.journal.save(f"call-{self.calls}-{phase}-response.json", exchange.dump())
            self.journal.save(f"call-{self.calls}-{phase}-provider-response.json",
                              getattr(exchange, 'provider_response', []))
            self.journal.event("model.response", phase=phase, call=self.calls,
                               model=exchange.model, finish_reason=exchange.stop_reason,
                               seconds=exchange.dur_ms / 1000,
                               input_count=exchange.usage.get("input_tokens"),
                               output_count=exchange.usage.get("output_tokens"),
                               failed=bool(exchange.error))
            if value is None or exchange.error:
                failure = call_failure(exchange, phase=phase, max_tokens=max_tokens,
                                       response_path=self.journal.directory / f"call-{self.calls}-{phase}-response.json")
                if (failure.diagnostic['code'] == 'INVALID_MODEL_JSON'
                        and exchange.stop_reason == 'end_turn'):
                    raise ResponseError('Return a complete valid JSON object matching the response schema.',
                                        exchange.raw_response, diagnostic=failure.diagnostic) from failure
                raise failure
            if exchange.stop_reason != "end_turn":
                raise NeedsReview("incomplete_model_response")
            if vision and exchange.images != len(self.images):
                raise NeedsReview("visual_image_count_mismatch")
            # Regional review owns normalization, schema validation and bounded
            # clarification, so malformed reviews can reach that recovery loop.
            if not phase.startswith('window-review-'):
                try:
                    jsonschema.validate(value, schema)
                except jsonschema.ValidationError as exc:
                    raise ResponseError('Model response violates the response schema', value) from exc
            self.journal.save(f"call-{self.calls}-{phase}.json", value)
            return value


@contextmanager
def tag_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def tags_read(path):
    if not path.exists():
        return {"schema_version": "document-recipe-tags-v2", "documents": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "document-recipe-tags-v2" or not isinstance(value.get("documents"), dict):
        raise NeedsReview("invalid_tag_registry")
    return value


def revise_pdf(engine, blocks, pdf, *, store, document, hints=None, source_evidence=None):
    """Return actual rebuilt Result + audit metadata. Native PDFs only, caller guards."""
    journal = Journal(Path(store).parent / "structure-recipe-runs", document)
    engine = MeasuredEngine(engine, journal)
    tags_path = Path(os.environ.get("STRUCTURE_RECIPE_TAGS", str(Path(store).parent / "structure-recipes.json")))
    try:
        with journal.step("baseline"):
            baseline = engine.interpret(copy.deepcopy(blocks), doc=document, llm=None, ledger=None, **(hints or {}))
            catalog = {}
            for node in baseline.nodes():
                examples = catalog.setdefault(node.family, {"source_examples": []})["source_examples"]
                if len(examples) < 3:
                    examples.append({"block": node.block_idx, "surface": node.surface})
            anchors = loop.inventory(baseline)
            binding = {"source_sha256": sha(pdf), "blocks_sha256": loop.digest(recipe_rules.block_records(blocks)),
                       "catalog_sha256": loop.digest(catalog), "runtime": VERSION,
                       "policy": policy_identity(),
                       "code_sha256": loop.digest({str(p.relative_to(Path(__file__).parent)): sha(p)
                                                   for p in Path(__file__).parent.rglob("*.py")})}
            from . import recipe_basic
            binding['structure_resources_sha256'] = recipe_basic.resources_identity()
            if source_evidence:
                binding['source_evidence'] = source_evidence
                journal.save('source-evidence.json', source_evidence)
            journal.save("binding.json", binding)
            journal.save("blocks.json", recipe_rules.block_records(blocks))
            journal.save("catalog.json", catalog)
            journal.save("baseline.json", loop.tree_record(baseline))
        call = GenosCalls(journal, [], max_calls=integer("STRUCTURE_RECIPE_MAX_CALLS",64,1,256))
        # Bind cached approvals to the actual model, including IDs discovered
        # from /models. Replacing a model behind the same profile invalidates reuse.
        binding['resolved_model'] = call.model
        journal.save('binding.json', binding)
        with tag_lock(tags_path):
            previous = tags_read(tags_path)["documents"].get(document)
        if previous and previous.get("binding") == binding and previous.get("status") in {"visual_approved", "visual_sampled"}:
            if loop.digest(previous["recipe"]) != previous.get("recipe_sha256"):
                raise NeedsReview("tag_digest_mismatch")
            if loop.digest(previous.get("coverage")) != previous.get("coverage_sha256"):
                raise NeedsReview("coverage_digest_mismatch")
            expected_status = "visual_approved" if previous["coverage"]["visual_scope"] == "full" else "visual_sampled"
            if previous["status"] != expected_status:
                raise NeedsReview("visual_scope_status_mismatch")
            saved_rules = previous.get("rules", [])
            if loop.digest(saved_rules) != previous.get("rules_sha256"):
                raise NeedsReview("rule_digest_mismatch")
            if saved_rules:
                engine = recipe_rules.RuleEngine(engine, saved_rules, blocks,
                    protected=[n.block_idx for n in baseline.nodes()], catalog=catalog)
                catalog = engine.extend_catalog(catalog, blocks)
            with journal.step("tag.reuse"):
                result = loop.build(engine, blocks, previous["recipe"], catalog, anchors)
                if loop.digest(loop.tree_record(result)) != previous.get("tree_sha256"):
                    raise NeedsReview("tag_replay_changed")
            journal.event("run.complete", reused=True, model_calls=0)
            return result, {"status": previous["status"], "coverage": previous["coverage"], "reused": True, "model_calls": 0,
                            "tag": previous["recipe"]["tag"], "run_id": journal.run_id,
                            "backend": previous["backend"], "model": previous["model"],
                            "process": "region-templates", "runtime": VERSION,
                            "region_count": len(previous["recipe"]["regions"]),
                            "template_count": len(previous["recipe"]["templates"])}
        mode = os.environ.get("STRUCTURE_RECIPE_REVIEW_MODE", "adaptive")
        if mode not in {"adaptive", "full"}:
            raise ValueError("STRUCTURE_RECIPE_REVIEW_MODE must be adaptive or full")
        # Chunk transport lacks local rectangles/tables. Inspect every original
        # page before accepting a grammar; approval is about hierarchy, not cells.
        if source_evidence or getattr(call, 'protocol', None) == 'basic':
            mode = 'full'
        max_pages = integer("STRUCTURE_RECIPE_MAX_PAGES", 1 if getattr(call,'protocol',None)=='basic' and accepts_warnings() else 6, 1, 20)
        import fitz
        from . import recipe_pages
        with fitz.open(pdf) as pages:
            if not 1 <= len(pages) <= integer("STRUCTURE_RECIPE_MAX_DOCUMENT_PAGES", 2000, 1, 10000):
                raise NeedsReview("document_page_budget_exceeded")
            inventory = recipe_pages.inventory(pages, blocks)
            journal.save("page-inventory.json", inventory)
            if any("missing_text_or_ocr" in p["risks"] for p in inventory):
                raise NeedsReview("source_blocks_missing_ocr_required")
            def render(selected):
                images = []
                with journal.step("render.window"):
                    for number in selected:
                        page = pages[number-1]
                        scale = min(1.5, 1600/max(page.rect.width,page.rect.height))
                        png = page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes("png")
                        images.append("data:image/png;base64,"+base64.b64encode(png).decode())
                        journal.event("page.rendered",page=number,image_bytes=len(png))
                return images
            checkpoint = journal.directory.parent / 'checkpoints' / (loop.digest([document,binding])+'.json')
            with tag_lock(checkpoint):
                result, recipe, rules, coverage = recipe_pages.run(
                    engine, blocks, pages, baseline, catalog, anchors, call, journal,
                    width=max_pages, render=render, full_review=mode == "full",
                    checkpoint=checkpoint, checkpoint_binding=binding,
                    max_corrections=integer("STRUCTURE_RECIPE_MAX_CORRECTIONS",2 if accepts_warnings() else 6,1,12),
                    basic_hints=hints)
            if source_evidence:
                coverage['source_evidence'] = source_evidence
                coverage['approval_scope'] = 'structure-template; missing parser coordinates and cells remain unavailable'
                journal.save('coverage.json', coverage)
            return save_result(result,recipe,rules,coverage,call,binding,pdf,blocks,journal,tags_path,document,previous)
    except Exception as exc:
        # Keep short machine reasons, never dump schema instances/source into progress.
        cause, seen = exc, set()
        diagnostic = None
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            diagnostic = getattr(cause, 'diagnostic', None)
            if diagnostic:
                break
            cause = cause.__cause__
        reason = str(cause if diagnostic else exc)
        if diagnostic and diagnostic.get('artifact'):
            diagnostic = copy.deepcopy(diagnostic)
            diagnostic['response_path'] = str(journal.directory / diagnostic['artifact'])
            reason = (f"{diagnostic['summary']}; 단계={diagnostic['phase']}; "
                      f"시도={diagnostic['attempts']}; {diagnostic['next_action']}; "
                      f"상세: {diagnostic['response_path']} [review_pending: {diagnostic['code']}]")
        if not diagnostic and not isinstance(exc, NeedsReview) and not (isinstance(exc, ValueError) and
                re.fullmatch(r"[A-Za-z][A-Za-z0-9_ .:-]{0,159}", reason)):
            reason = "configuration_or_step_failure"
        journal.event("run.needs_review", error_type=type(exc).__name__,
                      reason=reason)
        message = (reason if diagnostic else
                   f"구조 검수 보류: {reason}; 상세: {journal.directory / 'events.jsonl'}")
        raise NeedsReview(message, diagnostic=diagnostic) from exc


def save_result(result, recipe, rules, coverage, call, binding, pdf, blocks, journal, tags_path, document, previous):
    if sha(pdf) != binding["source_sha256"] or loop.digest(recipe_rules.block_records(blocks)) != binding["blocks_sha256"]:
        raise NeedsReview("source_changed")
    status = ("accepted_with_warnings" if coverage.get('review_warnings') else
              "visual_approved" if coverage["visual_scope"] == "full" else "visual_sampled")
    row = {"binding":binding,"rules":rules,"rules_sha256":loop.digest(rules),
           "recipe":recipe,"recipe_sha256":loop.digest(recipe),
           "tree_sha256":loop.digest(loop.tree_record(result)),"status":status,"run_id":journal.run_id,
           "backend":"genos","model":call.model,"coverage":coverage,"coverage_sha256":loop.digest(coverage)}
    with journal.step("tag.save"), tag_lock(tags_path):
        registry = tags_read(tags_path)
        if registry["documents"].get(document) != previous: raise NeedsReview("concurrent_tag_change")
        journal.save("tag.change.json",{"before":previous,"after":row})
        registry["documents"][document] = row
        atomic(tags_path,registry)
    journal.event("run.complete",reused=False,model_calls=call.calls,tag=recipe["tag"],
                  status=status, warning_count=len(coverage.get("review_warnings",[])),
                  visual_scope=coverage["visual_scope"],reviewed_pages=len(coverage["visually_reviewed_pages"]),
                  total_pages=coverage["total_pages"])
    return result,{"status":status,"reused":False,"model_calls":call.calls,"tag":recipe["tag"],
                   "run_id":journal.run_id,"backend":"genos","model":call.model,"coverage":coverage,
                   "process":"region-templates","runtime":VERSION,
                   "region_count":len(recipe["regions"]),"template_count":len(recipe["templates"])}
