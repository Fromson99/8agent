"""떨어진 폴더 → 구조화 결과로 증분 비교 → 자동 반영 → 전체 세대 조립 → 활성화.

입력 하나(Incoming)는 떨어진 파일 바이트와 그 파일의 GENOS 구조화 결과(result.json)다.
형식(법령 XML·행정규칙 XML·내규 docx 등)과 관계없이 구조화 결과로 비교한다.

1. decide: 문서마다 구조화 결과 → DocumentSnapshot → ingest(비교·게이트) → auto_apply.
   승인된 문서는 숨김 조문을 준비하고(prepare_index) Gold 게시를 기다린다(GOLD PENDING).
   보류 문서·변경 없음 문서는 이번 Gold 세대에 넣지 않는다 (지난 파일 유지).
2. replacements: 승인된 문서만 전체 원문 ZIP 교체 목록으로 (corpus.assemble 입력).
3. (밖에서) 새 전체 원문 ZIP으로 R6 → Gold 게시.
4. finish: 게시된 Gold 세대에 승인 문서를 연결(link_gold)하고, 한 트랜잭션에서 모두 활성화 +
   조회 채널 교체(activate_many).

같은 파일을 다시 넣으면 같은 작업이라 다시 처리하지 않는다 (적재작업ID = 문서코드+원문 해시).
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .corpus import Replacement, doc_name
from .lawgo_parse import ParseError
from .preview import render_html
from .service import AUTO_USER, ChannelSwitch, IncrementService
from .structured import Header, from_result, header_from_name, header_from_xml


@dataclass(frozen=True)
class Incoming:
    file_name: str
    data: bytes
    result: dict                   # GENOS 구조화 result.json (nodes·blocks)
    source: str = ""               # 지난 원문에 없는 새 문서일 때 출처 경로 (law / internal/<팀>)


def header_for(item: Incoming) -> Header:
    sha = hashlib.sha256(item.data).hexdigest()
    head = item.data[:4000].lstrip()
    if head.startswith(b"<"):
        try:
            tag = ET.fromstring(item.data).tag
        except ET.ParseError:
            tag = ""
        if tag in ("법령", "AdmRulService"):
            return header_from_xml(item.data, source_sha256=sha)
    return header_from_name(doc_name(item.file_name), filename=item.file_name, source_sha256=sha)


def decide(service: IncrementService, incoming: list[Incoming], *, hold_on_strong: bool = True) -> dict:
    entries = []
    for item in incoming:
        entry = {"file": item.file_name, "sha256": hashlib.sha256(item.data).hexdigest()}
        try:
            header = header_for(item)
            snapshot = from_result(item.result, header)
        except ParseError as exc:
            entries.append({**entry, "decision": "FAILED", "step": "STRUCTURE", "error": str(exc)})
            continue
        entry.update(doc_cd=snapshot.doc_cd, name=snapshot.name, load_id="")
        result = service.ingest(snapshot, source_name=item.file_name)
        entry.update(load_id=result.load_id, counts=result.gate.get("counts"), reused=result.reused)
        if result.state == "NO_CHANGE":
            entries.append({**entry, "decision": "NO_CHANGE"})
            continue
        if result.reused and result.state not in ("PREVIEW", "BLOCKED", "BLOCKED_PENDING"):
            entries.append({**entry, "decision": "ALREADY", "state": result.state})
            continue
        verdict = service.auto_apply(result.load_id, hold_on_strong=hold_on_strong)
        preview = service.preview(result.load_id)
        entry["preview_html"] = render_html(preview, service.job(result.load_id)["PRVW_HASH_VALU"] or "")
        if verdict["decision"] == "APPROVED":
            service.prepare_index(result.load_id, external=("GOLD",))
            entries.append({**entry, "decision": "APPROVED", "source": item.source,
                            "acknowledged": verdict.get("acknowledged", [])})
        else:
            entries.append({**entry, "decision": verdict["decision"], "reasons": verdict.get("reasons", []),
                            "state": verdict["state"]})
    summary = {}
    for e in entries:
        summary[e["decision"]] = summary.get(e["decision"], 0) + 1
    return {"entries": entries, "summary": summary,
            "publish_needed": any(e["decision"] == "APPROVED" for e in entries)}


def replacements(report: dict, incoming: list[Incoming]) -> list[Replacement]:
    by_file = {(i.file_name, hashlib.sha256(i.data).hexdigest()): i for i in incoming}
    out = []
    for e in report["entries"]:
        if e["decision"] != "APPROVED":
            continue
        item = by_file[(e["file"], e["sha256"])]
        out.append(Replacement(doc_cd=e["doc_cd"], file_name=item.file_name, data=item.data,
                               header=header_for(item), load_id=e["load_id"], source=item.source))
    return out


def finish(service: IncrementService, report: dict, *, dtls_hash: str, verifier=None,
           channel: ChannelSwitch | None = None, user: str = AUTO_USER) -> dict:
    """새 Gold 세대(dtls_hash)에 승인 문서를 연결하고 한 번에 활성화한다."""
    approved = [e for e in report["entries"] if e["decision"] == "APPROVED"]
    if not approved:
        return {"state": "NOTHING_TO_ACTIVATE"}
    linked = []
    for e in approved:
        out = service.link_gold(e["load_id"], dtls_hash=dtls_hash, verifier=verifier)
        linked.append({"load_id": e["load_id"], "doc_cd": e["doc_cd"], **out})
    failed = [x for x in linked if not x["ok"]]
    if failed:
        return {"state": "GOLD_NOT_READY", "linked": linked}
    activated = service.activate_many([e["load_id"] for e in approved], channel=channel, user=user)
    return {"state": "ACTIVATED", "linked": linked, "activated": activated}
