"""준비가 끝난 1급 후보의 **마지막 승인만** LLM에게 맡긴다.

이 모듈은 원문·골든을 읽지 않는다. 입력은 이미 조립된 Concept/Relation/Assertion
후보와 source 좌표뿐이다. LLM은 닫힌 item key별 승인·기각·보류만 반환하며 새 ID,
label, role, source를 만들거나 고칠 수 없다. 최종 active 발행은 다시 코드 검증을
통과해야 한다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .builder import section_id
from .store import GraphStore
from .tier1 import Tier1Registry, concept_id
from .uncertainty import review_state


SYSTEM = (
    "너는 1급 지식 후보의 최종 승인자다. 앞 단계가 Concept, Relation, Assertion, "
    "role, source 좌표, query cue를 이미 만들었다. 새 항목·ID·표면형·role·source를 "
    "만들거나 수정하지 말고 주어진 item_key마다 approve/reject/defer 중 하나만 "
    "판정한다.\n"
    "승인 기준: (1) Concept label이 재사용 가능한 도메인 개념이고 type이 맞다. "
    "(2) alias는 같은 뜻이다. (3) Relation은 표시된 src_label과 dst_label 사이에 "
    "type(IS_A 등)이 정확히 성립하고 evidence 좌표가 있다. (4) Assertion의 "
    "PREDICATE는 행위이고 role/role_labels/raw_slots 묶음이 하나의 명확한 명제를 "
    "이룬다. (5) query cue가 해당 명제를 여는 표현으로 적절하다. (6) 근거가 "
    "부족하거나 넓은 말 하나가 여러 뜻이면 defer. "
    "confidence=high인 approve만 실제 1급으로 발행된다."
)


def _key(kind: str, item_id: str) -> str:
    return f"{kind}:{item_id}"


def _candidate_payload(blob: dict, *, retry_deferred: bool = False,
                       force_all: bool = False) -> tuple[list[dict], list[str]]:
    """기존 승인 흔적은 가리고, 후보 자체만 닫힌 메뉴로 만든다."""
    items = []
    for kind, rows in (("concept", blob.get("concepts") or []),
                       ("relation", blob.get("relations") or []),
                       ("assertion", blob.get("assertions") or [])):
        for row in rows:
            if not force_all and row.get("candidate_status") in ("approved", "rejected"):
                continue
            if not force_all and row.get("candidate_status") == "deferred" and not retry_deferred:
                continue
            clean = {k: copy.deepcopy(v) for k, v in row.items()
                     if k not in ("status", "approved_by", "candidate_status", "approval")}
            item_key = _key(kind, str(row.get("id") or ""))
            items.append({"item_key": item_key, "kind": kind, "candidate": clean})
    return items, [x["item_key"] for x in items]


def _schema(keys: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "item_key": {"type": "string", "enum": keys},
                "decision": {"type": "string", "enum": ["approve", "reject", "defer"]},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "reason": {"type": "string"},
            },
            "required": ["item_key", "decision", "confidence", "reason"],
            "additionalProperties": False,
        }}},
        "required": ["decisions"], "additionalProperties": False,
    }


def _source_exists(store: GraphStore, row: dict) -> bool:
    source = row.get("source") or {}
    return bool(source.get("doc_id") and source.get("node") is not None
                and store.get_node(section_id(str(source["doc_id"]), source["node"])))


def approve(llm, candidate_path: str | Path, graph_path: str | Path,
            output_path: str | Path, audit_path: str | Path, *, batch_size: int = 50,
            workers: int = 1, retry_deferred: bool = False,
            force_all: bool = False, progress=None) -> dict:
    """candidates 원장 → 승인 판정 → 검증을 통과한 항목만 canonical에 발행.

    ``force_all``은 사용자가 명시적으로 전수 승인을 지시한 운영 모드다. 이전
    reject/defer를 포함한 모든 후보를 approve/high로 다시 기록하지만 source 실재,
    의존 Concept, IS_A 비순환, 최종 Tier1 스키마 검증은 우회하지 않는다.
    """
    candidate_path, graph_path = Path(candidate_path), Path(graph_path)
    output_path, audit_path = Path(output_path), Path(audit_path)
    candidate_bytes = candidate_path.read_bytes()
    blob = json.loads(candidate_bytes.decode("utf-8"))
    items, keys = _candidate_payload(blob, retry_deferred=retry_deferred,
                                     force_all=force_all)
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size는 1..100")
    if workers < 1 or workers > 16:
        raise ValueError("workers는 1..16")
    candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()

    # 수만 건 심사는 중간 결과를 잃으면 재호출 비용이 크다. 후보 파일 해시와
    # 후보 key가 같은 실행만 재개하고, 완료 배치는 JSONL 한 줄로 즉시 남긴다.
    # key 기준이라 재개할 때 batch_size를 50→100으로 바꿔도 이미 받은 판정을
    # 그대로 살리고 나머지만 다시 묶는다.
    checkpoint = audit_path.with_name(f".{audit_path.name}.checkpoint.jsonl")
    checkpoint_meta = {"candidate_sha256": candidate_sha, "version": 2}
    key_set = set(keys)
    resumed: list[dict] = []
    completed: dict[int, list[dict]] = {}
    if checkpoint.is_file() and not force_all:
        try:
            lines = checkpoint.read_text(encoding="utf-8").splitlines()
            meta = json.loads(lines[0]) if lines else {}
            # version 1(batch 번호 체크포인트)도 후보 해시만 같으면 key별로 이관한다.
            if meta.get("candidate_sha256") == candidate_sha:
                for line in lines[1:]:
                    row = json.loads(line)
                    resumed.extend(d for d in (row.get("decisions") or [])
                                   if d.get("item_key") in key_set)
        except (OSError, ValueError, json.JSONDecodeError):
            resumed = []
    if not resumed and not force_all:
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(checkpoint_meta, ensure_ascii=False) + "\n",
                              encoding="utf-8")

    resumed_keys = {d.get("item_key") for d in resumed}
    remaining = [item for item in items if item["item_key"] not in resumed_keys]
    batches = ([] if force_all else
               [remaining[i:i + batch_size]
                for i in range(0, len(remaining), batch_size)])

    def review(pos: int, batch: list[dict]) -> tuple[int, list[dict], bool]:
        batch_keys = [x["item_key"] for x in batch]
        out = None
        # 일시적 rate limit/연결 실패는 None으로 돌아온다. 누락을 곧바로 보류로
        # 굳히지 않고 짧은 지수 backoff 뒤 재시도한다.
        for attempt in range(5):
            out = llm.structured(
                "domain_graph.tier1_approval", SYSTEM,
                "[승인 후보 — 원문/골든 없음]\n" + json.dumps(batch, ensure_ascii=False),
                # 100건 배치에서 각 사유가 길어지면 18k를 실제로 소진했다. 잘린
                # JSON은 판정이 아니므로 후보당 300토큰까지 허용한다.
                _schema(batch_keys), max_tokens=max(2000, len(batch_keys) * 300),
                effort="low")
            if out is not None:
                rows = out.get("decisions") or []
                returned = [d.get("item_key") for d in rows]
                # JSON Schema는 item_key의 enum은 막지만 "각 key를 정확히 한 번"은
                # 표현하지 못한다. 누락·중복 응답은 완료가 아니며 같은 닫힌 메뉴를
                # 다시 심사한다.
                if len(rows) == len(batch_keys) and len(set(returned)) == len(batch_keys) \
                        and set(returned) == set(batch_keys):
                    return pos, rows, True
                out = None
            if attempt < 4:
                time.sleep(min(16, 2 ** attempt))
        return pos, [], False

    lock = threading.Lock()
    decided = len(resumed)
    if progress and resumed:
        progress(0, len(batches), 0, decided)

    pending = list(enumerate(batches, 1))
    failed: list[int] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(review, pos, batch): (pos, batch)
                   for pos, batch in pending}
        for future in as_completed(futures):
            pos, batch = futures[future]
            done_pos, rows, complete = future.result()
            with lock:
                if not complete:
                    failed.append(done_pos)
                    continue
                completed[done_pos] = rows
                with checkpoint.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"batch": done_pos, "decisions": rows},
                                       ensure_ascii=False) + "\n")
                decided += len(rows)
                if progress:
                    progress(len(completed), len(batches), len(batch), decided)

    if failed:
        raise RuntimeError(
            f"승인 배치 {len(failed)}개가 5회에도 정확한 전수 판정을 반환하지 않음; "
            "체크포인트에서 재실행 필요")

    if force_all:
        fresh = [{
            "item_key": item["item_key"], "decision": "approve",
            "confidence": "high", "reason": "사용자 명시 전수 승인",
        } for item in items]
    else:
        fresh = [*resumed, *(row for pos in range(1, len(batches) + 1)
                             for row in completed.get(pos, []))]

    # 중복·누락·메뉴 밖 판정은 승인으로 간주하지 않는다.
    decisions = {}
    review_keys = set(keys)
    if not force_all:
        for kind, rows in (("concept", blob.get("concepts") or []),
                           ("relation", blob.get("relations") or []),
                           ("assertion", blob.get("assertions") or [])):
            for row in rows:
                prior = row.get("approval") or {}
                k = _key(kind, str(row.get("id") or ""))
                status = row.get("candidate_status")
                if status in ("approved", "rejected") or \
                        (status == "deferred" and k not in review_keys):
                    decisions[k] = {
                        "item_key": k,
                        "decision": prior.get("decision") or (
                            "approve" if status == "approved" else
                            "reject" if status == "rejected" else "defer"),
                        "confidence": prior.get("confidence") or "high",
                        "reason": prior.get("reason") or "이전 확정 판정",
                    }
    duplicate = set()
    for row in fresh:
        k = row.get("item_key")
        if k not in keys:
            continue
        if k in decisions:
            duplicate.add(k)
        decisions[k] = row
    for k in duplicate:
        decisions.pop(k, None)

    ledger = copy.deepcopy(blob)
    canonical = {"schema_version": int(blob.get("schema_version") or 1),
                 "concepts": [], "relations": [], "assertions": []}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    model = "user-force-all" if force_all else str(getattr(llm, "model", "unknown"))
    approver = "user:force-all" if force_all else f"llm:{model}"
    published_review_state = review_state(approved_by=approver)
    approved_concepts = set()
    reasons = {}

    def record(row: dict, key: str, decision: dict, published: bool,
               validation: str = "") -> None:
        raw = decision.get("decision")
        row.pop("approved_by", None)
        row.pop("status", None)
        row["candidate_status"] = (
            "approved" if published else "rejected" if raw == "reject" else "deferred")
        row["review_state"] = published_review_state if published else (
            "rejected" if raw == "reject" else "unreviewed")
        row["approval"] = {
            "decision": raw or "defer",
            "confidence": decision.get("confidence") or "low",
            "reason": decision.get("reason") or "판정 누락 — 보류",
            "validation": validation,
            "by": approver, "at": now,
        }
        reasons[key] = row["approval"]["reason"]

    for row in ledger.get("concepts") or []:
        k = _key("concept", str(row.get("id") or ""))
        d = decisions.get(k) or {}
        published = d.get("decision") == "approve" and d.get("confidence") == "high"
        record(row, k, d, published,
               "통과" if published else "approve/high 아님")
        if published:
            approved_concepts.add(concept_id(row["id"]))
            active_row = {key: copy.deepcopy(value) for key, value in row.items()
                          if key not in ("candidate_status", "approval")}
            active_row.update(status="active", approved_by=approver,
                              review_state=published_review_state,
                              evidence_type=active_row.get("evidence_type") or
                              str((active_row.get("candidate_basis") or {}).get(
                                  "source") or "candidate_pipeline"))
            canonical["concepts"].append(active_row)

    with GraphStore(graph_path, readonly=True) as store:
        is_a_graph: dict[str, set[str]] = {}

        def creates_is_a_cycle(src: str, dst: str) -> bool:
            """src→dst를 더했을 때 dst에서 src로 돌아오는가."""
            if src == dst:
                return True
            todo, seen = [dst], set()
            while todo:
                cur = todo.pop()
                if cur == src:
                    return True
                if cur in seen:
                    continue
                seen.add(cur)
                todo.extend(is_a_graph.get(cur, ()))
            return False

        for row in ledger.get("relations") or []:
            k = _key("relation", str(row.get("id") or ""))
            d = decisions.get(k) or {}
            deps = {concept_id(row.get("src")), concept_id(row.get("dst"))}
            llm_ok = d.get("decision") == "approve" and d.get("confidence") == "high"
            published = llm_ok and deps <= approved_concepts
            cyclic = (published and row.get("type") == "IS_A" and
                      creates_is_a_cycle(concept_id(row.get("src")),
                                         concept_id(row.get("dst"))))
            if cyclic:
                published = False
            validation = ("통과" if published else "IS_A 순환" if cyclic else
                          "의존 Concept 미승인" if llm_ok else "approve/high 아님")
            record(row, k, d, published, validation)
            if published:
                if row.get("type") == "IS_A":
                    is_a_graph.setdefault(concept_id(row.get("src")), set()).add(
                        concept_id(row.get("dst")))
                active_row = {key: copy.deepcopy(value) for key, value in row.items()
                              if key not in ("candidate_status", "approval")}
                active_row.update(status="active", approved_by=approver,
                                  review_state=published_review_state,
                                  evidence_type=active_row.get("evidence_type") or
                                  str((active_row.get("candidate_basis") or {}).get(
                                      "source") or "candidate_pipeline"))
                canonical["relations"].append(active_row)
        for row in ledger.get("assertions") or []:
            k = _key("assertion", str(row.get("id") or ""))
            d = decisions.get(k) or {}
            deps = {concept_id(cid) for values in (row.get("roles") or {}).values()
                    for cid in (values if isinstance(values, list) else [values])}
            source_ok = _source_exists(store, row)
            llm_ok = d.get("decision") == "approve" and d.get("confidence") == "high"
            published = llm_ok and deps <= approved_concepts and source_ok
            validation = "통과" if published else (
                "source 좌표 없음" if llm_ok and not source_ok else
                "의존 Concept 미승인" if llm_ok else "approve/high 아님")
            record(row, k, d, published, validation)
            if published:
                active_row = {key: copy.deepcopy(value) for key, value in row.items()
                              if key not in ("candidate_status", "approval")}
                active_row.update(status="active", approved_by=approver,
                                  review_state=published_review_state,
                                  evidence_type=active_row.get("evidence_type") or
                                  str((active_row.get("candidate_basis") or {}).get(
                                      "source") or "candidate_pipeline"))
                canonical["assertions"].append(active_row)

    # 임시 파일을 엄격 검증한 뒤에만 canonical을 원자적으로 바꾼다.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(f".{output_path.name}.approving")
    tmp.write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        registry = Tier1Registry.load(tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(output_path)

    # canonical 발행이 성공한 뒤 후보 원장에 판정 이력을 남긴다.
    candidate_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    audit = {
        "at": now, "model": model, "candidate": str(candidate_path),
        "candidate_sha256": candidate_sha,
        "output": str(output_path), "decisions": fresh,
        "reasons": reasons,
        "published": {"concepts": len(registry.active_concepts),
                      "relations": len(registry.active_relations),
                      "assertions": len(registry.active_assertions)},
        "input_policy": ("user-authorized force-all; structural validation retained"
                         if force_all else
                         "prebuilt candidates only; no source text; no golden"),
        "force_all": force_all,
        "batches": len(batches), "resumed_decisions": len(resumed),
        "reviewed_now": len(keys),
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    if not force_all:
        checkpoint.unlink(missing_ok=True)
    return audit
