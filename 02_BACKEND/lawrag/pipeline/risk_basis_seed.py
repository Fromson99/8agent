"""Four reviewed risk-rule links, resolved inside the existing RAG selection.

No discovery model, latest-filename heuristic, ingestion, or indexing.
R3 uses resolve/binding with risk_basis_staging for the existing JSON review queue.
The original plan helpers below are retained for historical R1 contracts only.
"""
from copy import deepcopy
import json
import re
import sqlite3

from semantic_runtime.basis_links.contracts import require, digest, principal
from semantic_runtime.basis_links.repository import Repository, DDL
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.resolver import snapshot, targets
from semantic_runtime.team_scope import select_documents

SCHEMA = "risk-basis-append-v1"
POLICY = "risk-photo-0954-reviewed-locations-v1"


def normalized(value):
    import unicodedata
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def binding(store):
    store.check_unchanged()
    store.selection.require_latest()
    value = {
        "generation_id": store.manifest["generation_id"],
        "source_manifest_hash": digest(store.manifest),
        "selection_fingerprint": store.selection.fingerprint,
        "native_latest_verified": store.selection.native_latest_verified,
    }
    if getattr(store, "is_oracle_query", False):
        request = store.oracle_request
        value.update(backend="oracle", query_release_id=request.release_id,
                     dataset_version=request.snapshot.dataset_version,
                     source_release_id=request.snapshot.release_id,
                     query_channel=getattr(store, "_risk_seed_channel", None),
                     query_pointer_revision=request.pointer_revision)
    else:
        value["backend"] = "sqlite"
    return value


def inventory(store, who):
    """The Store already masks excluded versions; team scope narrows it again."""
    principal(who)
    pinned = binding(store)
    allowed = set(select_documents(store, who["team_id"]))
    if who.get("document_ids"):
        allowed &= set(who["document_ids"])
    source = SourcePort(store)
    records = []
    for did in sorted(allowed):
        item = source.catalogue[did]
        name = normalized(item["name"])
        if "위험관리기준시행세칙" in name or "금융투자업규정" in name:
            records.append({"document_id": did, "name": item["name"],
                            "side": item["category"],
                            "source_hash": source.document_hash(did),
                            "latest_mark": deepcopy(store.selection.latest.get(did))})
    return {"schema": SCHEMA, "binding": pinned, "documents": records,
            "allowed_document_ids": sorted(allowed),
            "excluded_count": len(store.selection.excluded),
            "selection_rule": "RAG Store visibility + require_latest + existing team scope"}


def _one(values, label):
    require(len(values) == 1, "RISK_SEED_AMBIGUOUS" if values else "RISK_SEED_MISSING",
            f"{label}: RAG 필터 안에서 유일한 대상이 필요합니다. 발견 {len(values)}개.", 409)
    return values[0]


def resolve(store, who):
    report = inventory(store, who)
    docs = report["documents"]

    def exact_document(title, side):
        def matches(row):
            # Match a real title/path component; never invent a newest date.
            parts = row["name"].replace("/", ">").split(">")
            return row["side"] == side and any(
                normalized(re.sub(r"\.(pdf|docx?|hwpx?|txt)$", "", p.strip(), flags=re.I)) == normalized(title)
                or normalized(re.sub(r"\(\d{8}\)(?:\.(pdf|docx?|hwpx?|txt))?$", "", p.strip(), flags=re.I)) == normalized(title)
                for p in parts)
        return _one([d for d in docs if matches(d) and
                     (side == "internal" or normalized(d["name"].split(">")[-1]) == normalized(title))],
                    title)

    internal = exact_document("위험관리기준시행세칙", "internal")
    regulation = exact_document("금융투자업규정", "external")
    annex = _one([d for d in docs if d["side"] == "external"
                  and "금융투자업규정시행세칙" in normalized(d["name"])
                  and re.search(r"\[별표\s*10\]", d["name"])
                  and "계량항목산정기준" in normalized(d["name"])], "시행세칙 별표10 계량항목 산정기준")
    chosen = {d["document_id"] for d in (internal, regulation, annex)}
    scoped = {**who, "document_ids": sorted(chosen)}
    source = SourcePort(store)

    def units(did):
        return [(str(r["unit_id"]), json.loads(r["json"]))
                for r in store.db.execute("SELECT unit_id,json FROM source_unit WHERE document_id=?", (did,))]

    cache = {did: units(did) for did in chosen}

    def coordinate(doc, key, anchor):
        did = doc["document_id"]
        uid, _ = _one([(u, r) for u, r in cache[did] if r.get("coordinate_key") == "body:" + key], key)
        end = source.endpoint({"document_id": did, "unit_id": uid}, scoped, doc["side"])
        text = normalized(" ".join(s["text"] for s in end["spans"]))
        require(all(normalized(x) in text for x in anchor), "RISK_SEED_CONTENT_CHANGED",
                key + ": 검토한 내용의 확인 문구가 없습니다. 새 의미 연결은 추정하지 않습니다.", 409)
        return end

    def annex_unit(label, anchor):
        did = annex["document_id"]
        uid, _ = _one([(u, r) for u, r in cache[did]
                       if normalized(r.get("title", "")) == normalized(label)
                       or normalized(r.get("surface", "") + r.get("title", "")) == normalized(label)], label)
        end = source.endpoint({"document_id": did, "unit_id": uid}, scoped, "external")
        text = normalized(" ".join(s["text"] for s in end["spans"]))
        require(all(normalized(x) in text for x in anchor), "RISK_SEED_CONTENT_CHANGED", label, 409)
        return end

    i1 = coordinate(internal, "제6-4조제1항", ["단기유동성지표", "유동성비율"])
    i2 = coordinate(internal, "제6-4조제2항", ["금융투자업규정시행세칙", "별표10", "산정"])
    i3 = coordinate(internal, "제1-4조제1항제3호", ["레버리지비율", "금융투자업규정", "제3-6조"])
    i4 = coordinate(internal, "제2-1조제1항제3호", ["레버리지비율", "1,000%"])
    e1 = coordinate(regulation, "제3-24조의4제2항", ["3개월", "1개월", "100분의100"])
    e2 = coordinate(regulation, "제3-6조제4호", ["레버리지비율", "자기자본", "총자산"])
    e3 = coordinate(regulation, "제3-24조의4제1항", ["레버리지비율", "제외"])
    e4 = coordinate(regulation, "제3-26조제7항", ["900%", "보고"])
    a1 = annex_unit("유동성비율(3개월)", ["3개월", "유동성자산"])
    a2 = annex_unit("조정유동성비율(3개월)", ["채무보증"])
    a3 = annex_unit("유동성비율 산정 원칙", ["만기", "자산"])
    links = []
    for label, left, right, explicit in (
        ("liquidity-maintenance", i1, [e1], False),
        ("liquidity-explicit-annex", i2, [a1, a2, a3], True),
        ("leverage-explicit-definition", i3, [e2], True),
        ("leverage-maintenance-reporting", i4, [e2, e3, e4], False),
    ):
        links.append({"key": label, "internal": [left], "external": right,
                      "explicit_reference": explicit})
    return {"inventory": report, "principal": scoped, "links": links,
            "internal_document_id": internal["document_id"]}


def memory_repository():
    # Only four link histories are staged. This is not a source/index mirror.
    repo = object.__new__(Repository)
    repo.db = sqlite3.connect(":memory:", isolation_level=None)
    repo.db.row_factory = sqlite3.Row
    repo.db.executescript(DDL)
    return repo


def rows(repository):
    from semantic_runtime.basis_links.oracle import TABLES
    return {table: [dict(r) for r in repository.db.execute("SELECT * FROM " + table)]
            for table in TABLES}


def endpoint_key(link):
    return digest({side: sorted(e["endpoint_hash"] for e in link[side])
                   for side in ("internal", "external")})


def plan(store, who, *, batch_id, existing=()):
    """Build append-only lifecycle rows using the existing proposal/review code."""
    principal(who, review=True)
    require(isinstance(batch_id, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", batch_id),
            "RISK_SEED_BATCH", "안정적인 batch_id가 필요합니다.")
    selected = resolve(store, who)
    scoped = selected["principal"]
    source = SourcePort(store)
    repo = memory_repository()
    reuse, reuse_pins, added = [], [], []
    # One fixed mapping set per team/source selection, even if two operators
    # use different batch labels. The Oracle receipt serializes their commits.
    operation = digest([POLICY, scoped["team_id"], selected["inventory"]["binding"]])
    try:
        service = Service(repo, source)
        for row in selected["links"]:
            matches = [v for v in existing if endpoint_key(v) == endpoint_key(row)]
            if matches:
                old = _one(matches, row["key"] + " 기존 연결")
                require(old["status"] == "APPROVED" and old["kind"] == "BASIS",
                        "RISK_SEED_EXISTING_REVIEW", "기존 반려·취소·후보 관계는 자동 변경하지 않습니다.", 409)
                reuse.append(old["link_id"])
                reuse_pins.append({"link_id": old["link_id"], "revision": old["revision"],
                                   "team_id": old["team_id"], "payload_hash": digest(old)})
                continue
            request = operation + ":" + row["key"]
            proposal = service.propose(scoped, {
                "request_id": request, "internal": row["internal"], "external": row["external"],
                "kind": "BASIS", "reason": "사용자가 지정하고 로컬 ADR0954에서 회수 경로를 확인한 조항 연결. 적용성·일치·충돌의 법률 정답을 승인하는 것은 아님.",
                "provenance": {"type": "USER_SELECTION", "policy": POLICY, "batch_id": batch_id,
                               "explicit_reference_visible": row["explicit_reference"],
                               "legal_quality_certified": False}})
            receipt = service.review(scoped, {
                "request_id": request + ":approve", "action": "approve",
                "reason": "사용자 지시: 선택된 위험관리기준시행세칙의 기존 검토 연결만 추가",
                "items": [{"link_id": proposal["link"]["link_id"], "revision": 1,
                           "view_hash": proposal["view_hash"]}]})
            require(receipt["status"] == "completed", "RISK_SEED_STAGE", "연결 revision 조립 실패", 409)
            added.append(proposal["link"]["link_id"])
        added_rows = rows(repo)
        graph = snapshot(service, scoped, [selected["internal_document_id"]])
        verified = targets(service, scoped, graph)
        # A separate rollback advances only newly created heads to REVOKED.
        for link in service.list(scoped)["items"]:
            service.review(scoped, {
                "request_id": operation + ":revoke:" + link["link"]["link_id"],
                "action": "revoke", "reason": "이 증분 배치의 신규 연결만 취소; 이력 보존",
                "items": [{"link_id": link["link"]["link_id"], "revision": link["link"]["revision"],
                           "view_hash": link["view_hash"]}]})
        after = rows(repo)
        rollback = {}
        for table, values in after.items():
            rollback[table] = [v for v in values if v not in added_rows[table]]
        result = {"schema": SCHEMA, "policy": POLICY, "batch_id": batch_id,
                  "operation_id": operation, "source_binding": selected["inventory"]["binding"],
                  "principal": scoped, "internal_document_id": selected["internal_document_id"],
                  "resolved": selected["links"], "new_link_ids": added,
                  "reused_link_ids": reuse, "reused_link_pins": reuse_pins,
                  "rows": added_rows, "rollback_rows": rollback,
                  "resolver_endpoint_count": len(verified), "source_guards": [],
                  "legal_quality_certified": False, "index_rebuild": False}
        result["plan_hash"] = digest(result)
        return result
    finally:
        repo.close()


def check_plan(value, store, who):
    require(value.get("schema") == SCHEMA and value.get("policy") == POLICY,
            "RISK_SEED_PLAN", "지원하는 연결 계획이 아닙니다.")
    require(digest({k: v for k, v in value.items() if k != "plan_hash"}) == value.get("plan_hash"),
            "RISK_SEED_PLAN_HASH", "계획 내용이 변경됐습니다.", 409)
    principal(who, review=True)
    require(all(who[k] == value["principal"][k] for k in ("team_id", "user_id")),
            "RISK_SEED_PRINCIPAL", "계획과 실행 주체가 다릅니다.", 403)
    require(binding(store) == value["source_binding"], "RISK_SEED_SELECTION_CHANGED",
            "RAG 판본 필터 또는 선택 데이터가 변경됐습니다. 새 계획이 필요합니다.", 409)
    current = resolve(store, who)
    require(current["links"] == value["resolved"], "RISK_SEED_SOURCE_CHANGED",
            "선택 문서 또는 조항 원문이 변경됐습니다.", 409)
    return current
