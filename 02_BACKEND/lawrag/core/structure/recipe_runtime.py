"""PDF region-template generation and bbox review for MAIN document ingestion.

No dynamic research imports, external provider fallback, or legal meaning changes.
An unsuccessful visual review raises NeedsReview; never publishes a failed tree.
"""
from __future__ import annotations

import base64
import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid

from . import recipe_visual_loop as loop
from . import recipe_rules

VERSION = "genos-recipe-v22-main-regions"
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
    pass


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
    profile = os.environ.get("GENOS_LLM_PROFILE", "qwen").upper()
    names = ["GENOS_BASE_URL", "GENOS_LLM_URL", "GENOS_GATEWAY_API_PREFIX", "GENOS_LLM_API_PREFIX",
             "GENOS_LLM_MODEL", f"GENOS_{profile}_MODEL", "GENOS_LLM_SERVING_ID", f"GENOS_{profile}_SERVING_ID",
             "GENOS_LLM_JSON_MODE", "GENOS_LLM_TEMPERATURE", "STRUCTURE_RECIPE_MAX_PAGES",
             "STRUCTURE_RECIPE_MAX_CHARS", "STRUCTURE_RECIPE_MAX_TOKENS",
             "STRUCTURE_RECIPE_REVIEW_MODE", "STRUCTURE_RECIPE_MAX_DOCUMENT_PAGES",
             "STRUCTURE_RECIPE_MAX_CALLS", "STRUCTURE_RECIPE_MAX_RULE_ROUNDS", "STRUCTURE_RECIPE_MAX_CORRECTIONS"]
    return {"enabled": True, "version": VERSION,
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
    def __init__(self, journal, images, *, request=None, max_calls=9):
        from semantic_runtime import genos
        self.target, self.model = genos.from_env("llm")
        if not self.model:
            raise ValueError("Set GENOS_QWEN_MODEL or GENOS_LLM_MODEL explicitly for visual structure")
        if not 1 <= self.target.max_retries <= 3:
            raise ValueError("GENOS_LLM_MAX_RETRIES must be 1..3 for visual structure")
        if not math.isfinite(self.target.read_timeout) or not 0 < self.target.read_timeout <= 300:
            raise ValueError("GENOS_LLM_TIMEOUT must be >0 and <=300")
        self.request = request or genos.request_json
        self.journal, self.images = journal, images
        self.calls = 0
        self.max_calls = max_calls
        self.max_tokens = integer("STRUCTURE_RECIPE_MAX_TOKENS", 4096, 256, 16384)
        self.json_mode = os.environ.get("GENOS_LLM_JSON_MODE", "prompt")
        if self.json_mode not in {"prompt", "json_object", "json_schema"}:
            raise ValueError("Unsupported GENOS_LLM_JSON_MODE")
        self.temperature = float(os.environ.get("GENOS_LLM_TEMPERATURE", "0"))
        if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Invalid GENOS_LLM_TEMPERATURE")
        journal.event("provider.configured", backend="genos", model=self.model,
                      json_mode=self.json_mode, max_attempts=self.target.max_retries,
                      timeout=self.target.read_timeout)

    def __call__(self, phase, system, data, schema, vision):
        import jsonschema
        from semantic_runtime.genos import ServingError
        # Initial assembly + three reviews; one induction + assembly + three reviews.
        if self.calls >= self.max_calls:
            raise NeedsReview("model_call_budget_exhausted")
        self.calls += 1
        if vision and not self.images:
            raise NeedsReview("visual_review_requires_images")
        serialized = json.dumps(data, ensure_ascii=False)
        if len(serialized) > integer("STRUCTURE_RECIPE_MAX_CHARS", 160000, 1000, 500000):
            raise NeedsReview("document_context_budget_exceeded")
        content = [{"type": "text", "text": serialized}]
        if vision:
            content.extend({"type": "image_url", "image_url": {"url": uri}} for uri in self.images)
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": system + "\nReturn only JSON matching this schema:\n" + json.dumps(schema)},
            {"role": "user", "content": content}],
            "max_tokens": self.max_tokens, "temperature": self.temperature, "stream": False}
        if self.json_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        elif self.json_mode == "json_schema":
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "structure_recipe", "strict": True, "schema": schema}}
        self.journal.save(f"call-{self.calls}-{phase}-input.json", {
            "system": system, "data": data, "schema": schema, "model": self.model,
            "image_count": len(self.images) if vision else 0,
            "payload_sha256": loop.digest(payload), "images_omitted": True})
        # No silent schema-mode or image-to-text fallback. Every retry has same images.
        with self.journal.step(phase):
            for attempt in range(1, self.target.max_retries + 1):
                started = time.monotonic()
                self.journal.event("model.request", phase=phase, call=self.calls, attempt=attempt,
                                   model=self.model, image_count=len(self.images) if vision else 0)
                try:
                    with self.journal.obs.context(run_id=self.journal.run_id, document=self.journal.document, phase=phase):
                        body = self.request(replace(self.target, max_retries=1), "/chat/completions", payload)
                    break
                except ServingError as exc:
                    transient = "request failed after" in str(exc)
                    self.journal.event("model.error", phase=phase, attempt=attempt, transient=transient,
                                       error_type=type(exc).__name__, seconds=round(time.monotonic()-started, 3))
                    if not transient or attempt == self.target.max_retries:
                        raise
                    self.journal.event("model.retry", phase=phase, next_attempt=attempt+1, delay_seconds=2*attempt)
                    time.sleep(2 * attempt)
            self.journal.save(f"call-{self.calls}-{phase}-response.json", body)
            choice = body["choices"][0]
            usage = body.get("usage") or {}
            self.journal.event("model.response", phase=phase, call=self.calls,
                               model=body.get("model", self.model), finish_reason=choice.get("finish_reason"),
                               seconds=round(time.monotonic()-started, 3),
                               input_count=usage.get("prompt_tokens"), output_count=usage.get("completion_tokens"))
            if choice.get("finish_reason") not in {"stop", "end_turn"}:
                raise NeedsReview("incomplete_model_response")
            text = choice["message"]["content"]
            if not isinstance(text, str):
                raise NeedsReview("non_text_model_response")
            text = text.strip()
            if text.startswith("```json\n") and text.endswith("```"):
                text = text[8:-3].strip()
            value = json.loads(text)
            jsonschema.validate(value, schema)
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


def revise_pdf(engine, blocks, pdf, *, store, document, hints=None):
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
            journal.save("binding.json", binding)
            journal.save("blocks.json", recipe_rules.block_records(blocks))
            journal.save("catalog.json", catalog)
            journal.save("baseline.json", loop.tree_record(baseline))
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
        max_pages = integer("STRUCTURE_RECIPE_MAX_PAGES", 6, 1, 20)
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
            call = GenosCalls(journal, [], max_calls=integer("STRUCTURE_RECIPE_MAX_CALLS",64,1,256))
            result, recipe, rules, coverage = recipe_pages.run(
                engine, blocks, pages, baseline, catalog, anchors, call, journal,
                width=max_pages, render=render, full_review=mode == "full",
                max_corrections=integer("STRUCTURE_RECIPE_MAX_CORRECTIONS",6,1,12))
            return save_result(result,recipe,rules,coverage,call,binding,pdf,blocks,journal,tags_path,document,previous)
    except Exception as exc:
        # Keep short machine reasons, never dump schema instances/source into progress.
        reason = str(exc)
        if not isinstance(exc, NeedsReview) and not (isinstance(exc, ValueError) and
                re.fullmatch(r"[A-Za-z][A-Za-z0-9_ .:-]{0,159}", reason)):
            reason = "configuration_or_step_failure"
        journal.event("run.needs_review", error_type=type(exc).__name__,
                      reason=reason)
        raise NeedsReview(f"구조 검수 보류: {journal.run_id}; structure-recipe-runs 로그 확인") from exc


def save_result(result, recipe, rules, coverage, call, binding, pdf, blocks, journal, tags_path, document, previous):
    if sha(pdf) != binding["source_sha256"] or loop.digest(recipe_rules.block_records(blocks)) != binding["blocks_sha256"]:
        raise NeedsReview("source_changed")
    status = "visual_approved" if coverage["visual_scope"] == "full" else "visual_sampled"
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
                  visual_scope=coverage["visual_scope"],reviewed_pages=len(coverage["visually_reviewed_pages"]),
                  total_pages=coverage["total_pages"])
    return result,{"status":status,"reused":False,"model_calls":call.calls,"tag":recipe["tag"],
                   "run_id":journal.run_id,"backend":"genos","model":call.model,"coverage":coverage,
                   "process":"region-templates","runtime":VERSION,
                   "region_count":len(recipe["regions"]),"template_count":len(recipe["templates"])}
