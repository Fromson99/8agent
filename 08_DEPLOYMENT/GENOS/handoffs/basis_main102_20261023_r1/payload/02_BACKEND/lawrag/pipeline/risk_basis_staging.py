"""User-fixed risk links join the discovery job's JSON review queue."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path

from semantic_runtime.basis_links.contracts import digest, require, principal
from semantic_runtime.basis_links.integration import selection
from semantic_runtime.basis_links.service import Service
from . import basis_batch_artifacts as artifacts
from .basis_batch_candidates import JsonRepository, tool_binding
from . import risk_basis_seed as fixed

METHOD = "USER_FIXED_RISK_V1"


class PreparedRepository(JsonRepository):
    """Service transactions are prepared in memory; the outer JSON commit is atomic."""
    def __init__(self, value):
        self.data = deepcopy(value)
        self.in_transaction = False

    @contextmanager
    def transaction(self):
        require(not self.in_transaction, "RISK_STAGE_TRANSACTION", "중첩 준비 트랜잭션입니다.")
        before = deepcopy(self.data)
        self.in_transaction = True
        try:
            yield
        except BaseException:
            self.data = before
            raise
        finally:
            self.in_transaction = False


def key(value):
    return digest({side: sorted(digest(selection(e)) for e in value[side])
                   for side in ("internal", "external")})


def plan_context(job, generation, runtime):
    job = artifacts.plain(job)
    plan = artifacts.signed(artifacts.read_json(job / "PLAN.json"), "plan_sha256")
    require(plan.get("schema_version") == "basis-batch-v1",
            "RISK_STAGE_PLAN", "기존 검토 배치 PLAN.json이 필요합니다.")
    expected = {"kind": "json-candidates-v1", "path": str(job / "CANDIDATES.json"),
                "tool": tool_binding(), "publication": "manual-review-only"}
    require(plan.get("candidate_storage") == expected, "RISK_STAGE_JOB",
            "같은 stage-plan 작업의 JSON 검토함이 필요합니다. 직접 SQLite 배치는 지원하지 않습니다.", 409)
    require(Path(plan["binding"]["generation_path"]).resolve() == Path(generation).resolve()
            and Path(plan["binding"]["runtime"]).resolve() == Path(runtime).resolve(),
            "RISK_STAGE_CONTEXT", "검토 배치의 원문·runtime이 현재 설정과 다릅니다.", 409)
    require(plan["binding"]["principal"]["team_id"] == "risk_team",
            "RISK_STAGE_TEAM", "위험관리팀 검토 배치가 필요합니다.", 403)
    return plan


def stage(job, generation, runtime, operator, *, inspect=False, config=None,
          context_check=lambda: None, hook=None):
    job = artifacts.plain(job)
    plan = plan_context(job, generation, runtime)
    pin = {k: plan["binding"][k] for k in
           ("generation_id", "manifest_sha256", "store_sha256", "selection_sha256")}
    who = {**plan["binding"]["principal"], "user_id": operator, "basis_review": True}
    principal(who, review=True)
    with artifacts.source(generation, pin, who, config) as (sources, scoped):
        require(scoped["document_ids"], "RISK_STAGE_TEAM", "현재 접근 가능한 문서가 없습니다.", 403)
        selected = fixed.resolve(sources.store, scoped)
        metadata = json.loads(sources.store.db.execute(
            "SELECT json FROM document WHERE document_id=?", (selected["internal_document_id"],)).fetchone()[0])
        require(metadata.get("document_metadata", {}).get("is_latest") is True,
                "RISK_STAGE_LATEST", "최종 내규 표시가 필요합니다.", 409)
        scoped = selected["principal"]
        operation = digest([METHOD, fixed.POLICY, plan["plan_sha256"], pin, operator])
        receipt_id = "risk-fixed:" + operation
        path = job / "CANDIDATES.json"
        if inspect:
            context_check()
            return {"status": "INSPECTED", "candidate_file": str(path), "resolved": selected,
                    "published_to_sqlite": False}
        repo = JsonRepository(path, writable=True)
        with repo.transaction():
            saved = repo.receipt(receipt_id, operation)
            if saved:
                for item in saved["actions"]:
                    current = repo.head(item["link_id"])
                    require(current and digest(current) == item["head_hash"], "RISK_STAGE_CHANGED",
                            "저장 이후 변경된 확정 연결입니다. 자동 복원하지 않습니다.", 409)
                result = {**saved, "status": "STAGED_REUSED"}
            else:
                staged = PreparedRepository(repo.data)
                service = Service(staged, sources)
                views = service.list(scoped, selected["internal_document_id"])["items"]
                actions = []
                for mapping in selected["links"]:
                    matches = [v for v in views if v["link"]["kind"] == "BASIS"
                               and v["link"].get("perspective", "CURRENT_BASIS") == "CURRENT_BASIS"
                               and key(v["binding"] or v["link"]) == key(mapping)]
                    require(len(matches) <= 1, "RISK_STAGE_DUPLICATES",
                            "동일한 후보가 여러 개입니다: " + mapping["key"], 409)
                    request = receipt_id + ":" + mapping["key"]
                    if matches:
                        row = matches[0]
                        require(row["binding"] and row["binding"]["status"] == "current",
                                "RISK_STAGE_BINDING", "후보의 현재 원문 결속이 필요합니다.", 409)
                        require(row["link"]["status"] in ("PROPOSED", "APPROVED"),
                                "RISK_STAGE_REVIEW_CONFLICT", "반려·취소된 연결은 자동 복구하지 않습니다.", 409)
                        for side in ("internal", "external"):
                            for end in row["binding"][side]:
                                sources.verify(end, scoped)
                        action = "reuse" if row["link"]["status"] == "APPROVED" else "approve_candidate"
                    else:
                        row = service.propose(scoped, {
                            "request_id": request, "internal": mapping["internal"], "external": mapping["external"],
                            "kind": "BASIS", "reason": "사용자가 지정한 위험관리기준시행세칙의 확정 연결; SQLite 이관은 HTML 검토 후 별도 실행",
                            "provenance": {"type": "USER_SELECTION", "method": METHOD, "policy": fixed.POLICY,
                                           "plan_sha256": plan["plan_sha256"], "mapping": mapping["key"],
                                           "explicit_reference_visible": mapping["explicit_reference"],
                                           "legal_quality_certified": False}})
                        action = "create"
                    ident = row["link"]["link_id"]
                    if action != "reuse":
                        reviewed = service.review(scoped, {"request_id": request + ":confirm", "action": "approve",
                            "reason": "사용자 지정 4건의 연결 확인. JSON 보관이며 운영 이관 승인과 별개.",
                            "items": [{"link_id": ident, "revision": row["link"]["revision"],
                                       "view_hash": row["view_hash"]}]})
                        require(reviewed["status"] == "completed", "RISK_STAGE_REVIEW", "확정 연결 준비 실패", 409)
                    actions.append({"mapping": mapping["key"], "action": action, "link_id": ident,
                                    "head_hash": digest(staged.head(ident))})
                    if hook:
                        hook("prepared:" + mapping["key"])
                result = {"status": "STAGED", "operation_id": operation, "plan_sha256": plan["plan_sha256"],
                          "candidate_file": str(path), "internal_document_id": selected["internal_document_id"],
                          "actions": actions, "published_to_sqlite": False, "model_calls": 0}
                repo.data = staged.data
                repo.save_receipt(receipt_id, operation, result)
            context_check()
            require(plan_context(job, generation, runtime) == plan, "RISK_STAGE_CHANGED",
                    "저장 직전에 검토 계획 또는 도구가 바뀌었습니다.", 409)
            require(fixed.resolve(sources.store, scoped)["links"] == selected["links"],
                    "RISK_STAGE_SOURCE", "저장 직전에 선택 원문이 바뀌었습니다.", 409)
            if hook:
                hook("before_commit")
        if hook:
            hook("after_commit")
        artifacts.atomic(job / ("RISK_FIXED_" + operation[:16] + ".json"), result)
        return result
