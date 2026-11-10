"""증분 처리 단계 실행과 상태 전이.

DETECTED → PARSED → DIFFED → PREVIEW → APPROVED → INDEXING → ACTIVATED (→ ROLLED_BACK)
예외: NO_CHANGE(조문 변화 없음, 종료) · REJECTED · BLOCKED · BLOCKED_PENDING · FAILED

자동 반영(auto_apply): 사람 승인 대신 게이트로 판단한다. BLOCKED·BLOCKED_PENDING과 강한 경고
(조문 수 급감·대량 삭제·변경률 50% 초과·별표 소실·시행일 못 읽음)는 보류(PREVIEW 유지),
그 밖에는 승인자 AUTO로 승인한다. 잘못 들어간 판본은 rollback으로 되돌린다.

반영 순서 (색인 준비 후 활성화)
1. 승인된 변경으로 새 조문 행을 숨김(OPEN_YN=N)으로 만든다. 참조 행도 함께.
2. 외부 색인(Gold 세대 게시·벡터)은 IDX_WORK에 PENDING으로 두고, 확인되면 READY.
3. 전부 READY면 한 트랜잭션에서: 작업 상태 CAS → 문서 활성 판본 CAS(기준 판본이 그대로일 때만)
   → 옛 판본·옛 조문 구간 닫기 → 새 조문 공개 → 재검토 대상 등록 → (선택) Gold 조회 채널 포인터 CAS.
4. 실패하면 전부 롤백. 기존 현행본은 그대로이고 같은 명령을 다시 실행하면 된다.

멱등성: 적재작업ID = 문서코드+원천 sha. 같은 파일을 다시 넣으면 기존 작업을 돌려준다.
조문판본ID = 판본ID+조문키라 재시도해도 같은 행이 된다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .addenda import schedule_for
from .diff import (ADD, AMEND, DELETE, MOVE, MOVE_AMEND, REF_ONLY, SAME, BaseArticle, Change,
                   diff_snapshot)
from .gate import assign_effective, day_before, evaluate, today_kst
from .lawgo_parse import KIND_ANNEX, Article, DocumentSnapshot
from .normalize import citations, compare_hash, normalize_text, stable_id, text_hash
from .preview import build_preview, preview_hash
from .schema import TABLE, qualified

TERMINAL = {"ACTIVATED", "NO_CHANGE", "REJECTED", "ROLLED_BACK"}
AUTO_USER = "AUTO"
ALLOWED = {
    "PREVIEW": {"APPROVED", "REJECTED", "PREVIEW"},
    "BLOCKED": {"PREVIEW", "REJECTED"},
    "BLOCKED_PENDING": {"PREVIEW", "REJECTED"},
    "APPROVED": {"INDEXING", "FAILED"},
    "INDEXING": {"INDEXING", "ACTIVATED", "FAILED"},
    "FAILED": {"INDEXING"},
    "ACTIVATED": {"ROLLED_BACK"},
}
NEW_ROW_TYPES = (ADD, AMEND, MOVE, MOVE_AMEND, REF_ONLY)
CLOSE_TYPES = (AMEND, MOVE, MOVE_AMEND, REF_ONLY, DELETE)
IMPACT_TYPES = (AMEND, MOVE_AMEND, DELETE)


class IncrementError(RuntimeError):
    pass


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass
class ChannelSwitch:
    """활성화 트랜잭션에서 Gold 조회 채널 포인터를 바꾼다 (SRCH_CHNL: 채널명·게시해시·변경번호)."""
    table: str
    channel: str
    old_post: str
    new_post: str
    expected_no: int
    name_column: str = "RFRN_CHNL_NAME"
    post_column: str = "RFRN_POST_HASH_VALU"
    number_column: str = "CHAN_NO"

    def sql(self) -> tuple[str, dict]:
        return (f"UPDATE {self.table} SET {self.post_column}=:new_post, "
                f"{self.number_column}={self.number_column}+1 "
                f"WHERE {self.name_column}=:channel AND {self.post_column}=:old_post "
                f"AND {self.number_column}=:expected_no",
                {"new_post": self.new_post, "channel": self.channel, "old_post": self.old_post,
                 "expected_no": self.expected_no})


@dataclass
class IngestResult:
    load_id: str
    state: str
    doc_cd: str
    gate: dict = field(default_factory=dict)
    preview_hash: str = ""
    reused: bool = False


class IncrementService:
    def __init__(self, db, *, owner: str | None = None, today: str | None = None):
        self.db = db
        self.owner = owner
        self.today = today

    # ---------------------------------------------------------------- 공통
    def t(self, key: str) -> str:
        return qualified(TABLE[key], self.owner)

    def create_schema(self) -> None:
        from .schema import ddl
        with self.db.transaction() as tx:
            for statement in ddl(self.db.dialect, self.owner):
                tx.execute(statement)

    def job(self, load_id: str) -> dict | None:
        rows = self.db.query(f"SELECT * FROM {self.t('LOAD_WORK')} WHERE LOAD_WORK_ID=:id", {"id": load_id})
        return rows[0] if rows else None

    def _require(self, load_id: str) -> dict:
        job = self.job(load_id)
        if job is None:
            raise IncrementError(f"적재작업 없음: {load_id}")
        return job

    def _hist_seq(self, load_id: str) -> int:
        rows = self.db.query(f"SELECT MAX(HIST_SEQ) AS N FROM {self.t('LOAD_HIST')} WHERE LOAD_WORK_ID=:id",
                             {"id": load_id})
        return int(rows[0]["N"] or 0) if rows else 0

    def _hist(self, tx, load_id: str, seq: int, before: str | None, after: str, detail: dict) -> None:
        tx.execute(f"INSERT INTO {self.t('LOAD_HIST')} (LOAD_WORK_ID, HIST_SEQ, BFR_STTS_CD, AFTR_STTS_CD, "
                   f"HIST_CTNT, RGSN_ASTM) VALUES (:id, :seq, :before, :after, :detail, {{now}})",
                   {"id": load_id, "seq": seq, "before": before, "after": after, "detail": _json(detail)})

    def _transition(self, tx, job: dict, after: str, extra: str = "", binds: dict | None = None) -> None:
        before = job["PRCS_STTS_CD"]
        if after not in ALLOWED.get(before, set()):
            raise IncrementError(f"허용되지 않는 상태 전이 {before}→{after}")
        sets = "PRCS_STTS_CD=:after, STTS_CHG_NO=STTS_CHG_NO+1, CHG_ASTM={now}" + (", " + extra if extra else "")
        tx.execute(f"UPDATE {self.t('LOAD_WORK')} SET {sets} WHERE LOAD_WORK_ID=:id AND PRCS_STTS_CD=:before "
                   f"AND STTS_CHG_NO=:rev",
                   {"after": after, "id": job["LOAD_WORK_ID"], "before": before,
                    "rev": int(job["STTS_CHG_NO"]), **(binds or {})}, expect=1)

    # ---------------------------------------------------------------- 조회
    def document(self, doc_cd: str) -> dict | None:
        rows = self.db.query(f"SELECT * FROM {self.t('RGLT_DOC')} WHERE RGLT_DOC_CD=:d", {"d": doc_cd})
        return rows[0] if rows else None

    def version(self, ver_id: str | None) -> dict | None:
        if not ver_id:
            return None
        rows = self.db.query(f"SELECT * FROM {self.t('RGLT_VER')} WHERE RGLT_VER_ID=:v", {"v": ver_id})
        return rows[0] if rows else None

    def current_articles(self, doc_cd: str) -> list[BaseArticle]:
        rows = self.db.query(
            f"SELECT ARTC_VER_ID, ARTC_KEY_VALU, ARTC_SE_CD, ARTC_TITLE_NAME, ARTC_CTNT, LNG_ID, "
            f"ENFC_STRT_DT, ARTC_SEQ, ATCH_HASH_VALU FROM {self.t('ARTC_VER')} "
            f"WHERE RGLT_DOC_CD=:d AND OPEN_YN='Y' AND ENFC_END_DT IS NULL ORDER BY ARTC_SEQ",
            {"d": doc_cd})
        return [BaseArticle(r["ARTC_KEY_VALU"], r["ARTC_SE_CD"], r["ARTC_TITLE_NAME"] or "",
                            r["ARTC_CTNT"] or "", r["LNG_ID"], r["ARTC_VER_ID"], r["ENFC_STRT_DT"],
                            int(r["ARTC_SEQ"] or 0), r["ATCH_HASH_VALU"] or "") for r in rows]

    def articles_as_of(self, doc_cd: str, as_of: str) -> list[dict]:
        """조회 시점 필터: 시작 <= 기준일 AND (종료 없음 OR 종료 >= 기준일). 기준일은 KST YYYYMMDD."""
        return self.db.query(
            f"SELECT ARTC_KEY_VALU, LNG_ID, ARTC_TITLE_NAME, ARTC_CTNT, ENFC_STRT_DT, ENFC_END_DT, "
            f"RGLT_VER_ID FROM {self.t('ARTC_VER')} WHERE RGLT_DOC_CD=:d AND OPEN_YN='Y' "
            f"AND ENFC_STRT_DT <= :as_of AND (ENFC_END_DT IS NULL OR ENFC_END_DT >= :as_of) "
            f"ORDER BY ARTC_SEQ", {"d": doc_cd, "as_of": as_of})

    def changes(self, load_id: str) -> list[dict]:
        return self.db.query(f"SELECT * FROM {self.t('ARTC_CMPR')} WHERE LOAD_WORK_ID=:id ORDER BY CMPR_SEQ",
                             {"id": load_id})

    # ---------------------------------------------------------------- 1. 적재·비교
    def ingest(self, snapshot: DocumentSnapshot, *, source_name: str = "",
               forced: dict[str, str] | None = None) -> IngestResult:
        load_id = "W" + stable_id(snapshot.doc_cd, "load", snapshot.source_sha256, length=31)
        existing = self.job(load_id)
        if existing is not None and not forced:
            return IngestResult(load_id, existing["PRCS_STTS_CD"], snapshot.doc_cd,
                                json.loads(existing["GATE_RSLT_CTNT"] or "{}"),
                                existing["PRVW_HASH_VALU"] or "", reused=True)
        if forced and (existing is None or existing["PRCS_STTS_CD"] not in ("PREVIEW", "BLOCKED", "BLOCKED_PENDING")):
            raise IncrementError("수동 연결은 승인 전(PREVIEW/BLOCKED) 작업에만 쓸 수 있다")
        version_id = "V" + stable_id(snapshot.doc_cd, "ver", snapshot.source_sha256, length=31)
        document = self.document(snapshot.doc_cd)
        base_version = self.version(document["ACTV_VER_ID"]) if document else None
        base = self.current_articles(snapshot.doc_cd)

        diff = diff_snapshot(base, snapshot.articles, doc_cd=snapshot.doc_cd, version_id=version_id,
                             forced=forced)
        schedule = schedule_for(snapshot)
        effective = assign_effective(diff, snapshot, schedule)
        gate = evaluate(diff, snapshot, schedule,
                        base_effective=base_version["ENFC_STRT_DT"] if base_version else "",
                        base_count=len(base), today=self.today or today_kst())
        if gate.no_change:
            state = "NO_CHANGE"
        elif gate.stop:
            state = gate.stop
        else:
            state = "PREVIEW"
        rows = self._cmpr_rows(load_id, version_id, diff.changed())
        gate_dict = {**gate.as_dict(), "effective": effective, "schedule": schedule.__dict__,
                     "doc_name": snapshot.name, "promulgation_no": snapshot.promulgation_no}
        preview = build_preview(snapshot.doc_cd, snapshot.name, snapshot.source_sha256, effective,
                                gate_dict, rows, {a.version_id: a for a in base})
        digest = preview_hash(preview) if state != "NO_CHANGE" else ""

        with self.db.transaction() as tx:
            if document is None:
                tx.execute(f"INSERT INTO {self.t('RGLT_DOC')} (RGLT_DOC_CD, SRC_SE_CD, OFCL_ID, RGLT_DOC_NAME, "
                           f"ALIAS_CTNT, ACTV_VER_ID, RGSN_ASTM, CHG_ASTM) VALUES (:d, :kind, :ofcl, :name, "
                           f"'[]', NULL, {{now}}, {{now}})",
                           {"d": snapshot.doc_cd, "kind": snapshot.source_kind,
                            "ofcl": snapshot.official_id, "name": snapshot.name})
            if existing is None:
                tx.execute(f"INSERT INTO {self.t('LOAD_WORK')} (LOAD_WORK_ID, RGLT_DOC_CD, SRC_SE_CD, "
                           f"SRC_HASH_VALU, SRC_FILE_NAME, BASE_VER_ID, NEW_VER_ID, PRCS_STTS_CD, STTS_CHG_NO, "
                           f"PRVW_HASH_VALU, GATE_RSLT_CTNT, RGSN_ASTM, CHG_ASTM) VALUES (:id, :d, :kind, :sha, "
                           f":file, :base, :ver, :state, 1, :preview, :gate, {{now}}, {{now}})",
                           {"id": load_id, "d": snapshot.doc_cd, "kind": snapshot.source_kind,
                            "sha": snapshot.source_sha256, "file": source_name[:600],
                            "base": base_version["RGLT_VER_ID"] if base_version else None,
                            "ver": version_id if state != "NO_CHANGE" else None, "state": state,
                            "preview": digest or None, "gate": _json(gate_dict)})
                seq = 0
                for before, after in ((None, "DETECTED"), ("DETECTED", "PARSED"), ("PARSED", "DIFFED"),
                                      ("DIFFED", state)):
                    seq += 1
                    self._hist(tx, load_id, seq, before, after,
                               {"articles": len(snapshot.articles), "counts": gate.counts} if after == state else {})
            else:                                   # 수동 연결로 재비교 (PREVIEW 유지)
                tx.execute(f"DELETE FROM {self.t('ARTC_CMPR')} WHERE LOAD_WORK_ID=:id", {"id": load_id})
                tx.execute(f"UPDATE {self.t('LOAD_WORK')} SET PRCS_STTS_CD=:state, STTS_CHG_NO=STTS_CHG_NO+1, "
                           f"PRVW_HASH_VALU=:preview, GATE_RSLT_CTNT=:gate, CHG_ASTM={{now}} "
                           f"WHERE LOAD_WORK_ID=:id AND STTS_CHG_NO=:rev",
                           {"state": state, "preview": digest or None, "gate": _json({**gate_dict, "forced": forced}),
                            "id": load_id, "rev": int(existing["STTS_CHG_NO"])}, expect=1)
                self._hist(tx, load_id, self._hist_seq(load_id) + 1, existing["PRCS_STTS_CD"], state,
                           {"forced": forced, "counts": gate.counts})
            for row in rows:
                tx.execute(f"INSERT INTO {self.t('ARTC_CMPR')} (LOAD_WORK_ID, CMPR_SEQ, CHG_TYPE_CD, "
                           f"OLD_ARTC_VER_ID, OLD_ARTC_KEY_VALU, NEW_ARTC_KEY_VALU, NEW_ARTC_VER_ID, LNG_ID, "
                           f"SMLR_RATE, JDGM_RSN_CTNT, ENFC_STRT_DT, RULE_RVW_YN, CMPR_ADDN_IFMN_CTNT, RGSN_ASTM) "
                           f"VALUES (:LOAD_WORK_ID, :CMPR_SEQ, :CHG_TYPE_CD, :OLD_ARTC_VER_ID, :OLD_ARTC_KEY_VALU, "
                           f":NEW_ARTC_KEY_VALU, :NEW_ARTC_VER_ID, :LNG_ID, :SMLR_RATE, :JDGM_RSN_CTNT, "
                           f":ENFC_STRT_DT, :RULE_RVW_YN, :CMPR_ADDN_IFMN_CTNT, {{now}})", row)
            if state != "NO_CHANGE" and (existing is None):
                tx.execute(f"INSERT INTO {self.t('RGLT_VER')} (RGLT_VER_ID, RGLT_DOC_CD, LOAD_WORK_ID, BASE_VER_ID, "
                           f"SRC_HASH_VALU, RGLT_DOC_ID, DTLS_HASH_VALU, PRMG_DT, PRMG_NO, ENFC_STRT_DT, "
                           f"ENFC_END_DT, VER_STTS_CD, VER_ADDN_IFMN_CTNT, RGSN_ASTM) VALUES (:v, :d, :id, :base, "
                           f":sha, :gold, NULL, :pd, :pn, :eff, NULL, 'CANDIDATE', :meta, {{now}})",
                           {"v": version_id, "d": snapshot.doc_cd, "id": load_id,
                            "base": base_version["RGLT_VER_ID"] if base_version else None,
                            "sha": snapshot.source_sha256, "gold": snapshot.source_sha256[:16],
                            "pd": snapshot.promulgated or None, "pn": snapshot.promulgation_no or None,
                            "eff": effective, "meta": _json({"name": snapshot.name,
                                                             "revision_kind": snapshot.revision_kind,
                                                             "meta": snapshot.meta,
                                                             "addendum": schedule.source_key})})
        return IngestResult(load_id, state, snapshot.doc_cd, gate_dict, digest)

    def _cmpr_rows(self, load_id: str, version_id: str, changes: list[Change]) -> list[dict]:
        return comparison_rows(load_id, version_id, changes)

    def preview(self, load_id: str) -> dict:
        job = self._require(load_id)
        gate = json.loads(job["GATE_RSLT_CTNT"] or "{}")
        rows = self.changes(load_id)
        olds = {}
        ids = [r["OLD_ARTC_VER_ID"] for r in rows if r["OLD_ARTC_VER_ID"]]
        for start in range(0, len(ids), 200):
            part = ids[start:start + 200]
            names = {f"o{i}": v for i, v in enumerate(part)}
            for r in self.db.query(
                    f"SELECT ARTC_VER_ID, ARTC_KEY_VALU, ARTC_SE_CD, ARTC_TITLE_NAME, ARTC_CTNT, LNG_ID, "
                    f"ENFC_STRT_DT, ARTC_SEQ, ATCH_HASH_VALU FROM {self.t('ARTC_VER')} "
                    f"WHERE ARTC_VER_ID IN ({', '.join(':' + n for n in names)})", names):
                olds[r["ARTC_VER_ID"]] = BaseArticle(r["ARTC_KEY_VALU"], r["ARTC_SE_CD"], r["ARTC_TITLE_NAME"] or "",
                                                     r["ARTC_CTNT"] or "", r["LNG_ID"], r["ARTC_VER_ID"],
                                                     r["ENFC_STRT_DT"], int(r["ARTC_SEQ"] or 0),
                                                     r["ATCH_HASH_VALU"] or "")
        return build_preview(job["RGLT_DOC_CD"], gate.get("doc_name", ""), job["SRC_HASH_VALU"],
                             gate.get("effective", ""), {k: v for k, v in gate.items() if k != "forced"},
                             rows, olds)

    # ---------------------------------------------------------------- 2. 승인
    def approve(self, load_id: str, *, user: str, preview_digest: str, acknowledge: bool = False) -> dict:
        job = self._require(load_id)
        if job["PRCS_STTS_CD"] != "PREVIEW":
            raise IncrementError(f"PREVIEW 상태만 승인 가능 (현재 {job['PRCS_STTS_CD']})")
        if preview_digest != job["PRVW_HASH_VALU"]:
            raise IncrementError("승인한 대비표 해시가 현재 비교 결과와 다르다 — 대비표를 다시 확인")
        gate = json.loads(job["GATE_RSLT_CTNT"] or "{}")
        strong = [w for w in gate.get("warnings", []) if w.get("strong")]
        if strong and not acknowledge:
            raise IncrementError("강한 경고 확인 필요: " + "; ".join(w["message"] for w in strong))
        document = self.document(job["RGLT_DOC_CD"])
        if (document or {}).get("ACTV_VER_ID") != job["BASE_VER_ID"]:
            raise IncrementError("비교 기준 판본이 그 사이 바뀌었다 — 같은 파일로 다시 적재")
        with self.db.transaction() as tx:
            self._transition(tx, job, "APPROVED", "APRV_USER_ID=:user, APRV_ASTM={now}", {"user": user})
            self._hist(tx, load_id, self._hist_seq(load_id) + 1, "PREVIEW", "APPROVED",
                       {"user": user, "acknowledged": [w["code"] for w in strong]})
        return self._require(load_id)

    def auto_apply(self, load_id: str, *, hold_on_strong: bool = True) -> dict:
        """사람 승인 대신 게이트 결과로 승인하거나 보류한다. 보류는 상태를 바꾸지 않고 이력만 남긴다."""
        job = self._require(load_id)
        state = job["PRCS_STTS_CD"]
        gate = json.loads(job["GATE_RSLT_CTNT"] or "{}")
        strong = [w for w in gate.get("warnings", []) if w.get("strong")]
        if state in ("BLOCKED", "BLOCKED_PENDING"):
            reasons = [gate.get("stop_reason") or state]
        elif state == "PREVIEW" and strong and hold_on_strong:
            reasons = [f"{w['code']}: {w['message']}" for w in strong]
        elif state == "PREVIEW":
            self.approve(load_id, user=AUTO_USER, preview_digest=job["PRVW_HASH_VALU"], acknowledge=True)
            return {"load_id": load_id, "decision": "APPROVED", "state": "APPROVED",
                    "acknowledged": [w["code"] for w in strong]}
        else:
            return {"load_id": load_id, "decision": "SKIPPED", "state": state}
        with self.db.transaction() as tx:
            self._hist(tx, load_id, self._hist_seq(load_id) + 1, state, state,
                       {"user": AUTO_USER, "hold": reasons})
        return {"load_id": load_id, "decision": "HOLD", "state": state, "reasons": reasons}

    def reject(self, load_id: str, *, user: str, reason: str) -> dict:
        job = self._require(load_id)
        with self.db.transaction() as tx:
            self._transition(tx, job, "REJECTED", "APRV_USER_ID=:user, ERR_CTNT=:reason",
                             {"user": user, "reason": reason[:1300]})
            if job["NEW_VER_ID"]:
                tx.execute(f"UPDATE {self.t('RGLT_VER')} SET VER_STTS_CD='REJECTED' "
                           f"WHERE RGLT_VER_ID=:v AND VER_STTS_CD='CANDIDATE'", {"v": job["NEW_VER_ID"]})
            self._hist(tx, load_id, self._hist_seq(load_id) + 1, job["PRCS_STTS_CD"], "REJECTED",
                       {"user": user, "reason": reason})
        return self._require(load_id)

    def unblock(self, load_id: str, *, user: str, reason: str) -> dict:
        """BLOCKED·BLOCKED_PENDING을 사람이 판단해 대비표 검토로 넘긴다 (승인은 별도)."""
        job = self._require(load_id)
        if job["PRCS_STTS_CD"] not in ("BLOCKED", "BLOCKED_PENDING"):
            raise IncrementError("멈춘 작업이 아니다")
        with self.db.transaction() as tx:
            self._transition(tx, job, "PREVIEW")
            self._hist(tx, load_id, self._hist_seq(load_id) + 1, job["PRCS_STTS_CD"], "PREVIEW",
                       {"user": user, "reason": reason, "unblocked": True})
        return self._require(load_id)

    # ---------------------------------------------------------------- 3. 색인 준비 (숨김)
    def prepare_index(self, load_id: str, *, external: tuple[str, ...] = ("GOLD",)) -> dict:
        job = self._require(load_id)
        if job["PRCS_STTS_CD"] not in ("APPROVED", "INDEXING", "FAILED"):
            raise IncrementError(f"승인된 작업만 색인 준비 (현재 {job['PRCS_STTS_CD']})")
        if job["PRCS_STTS_CD"] == "FAILED" and job["FAIL_STEP_NAME"] not in ("INDEXING", "ACTIVATION"):
            raise IncrementError("색인·활성화 단계 실패만 재시도할 수 있다")
        doc_cd, ver_id = job["RGLT_DOC_CD"], job["NEW_VER_ID"]
        rows = self.changes(load_id)
        base = self.current_articles(doc_cd)
        lineage_by_key = {a.key: a.lineage_id for a in base}
        for r in rows:
            if r["CHG_TYPE_CD"] in CLOSE_TYPES and r["OLD_ARTC_KEY_VALU"] in lineage_by_key:
                lineage_by_key.pop(r["OLD_ARTC_KEY_VALU"], None)
        for r in rows:
            if r["CHG_TYPE_CD"] in NEW_ROW_TYPES:
                lineage_by_key[r["NEW_ARTC_KEY_VALU"]] = r["LNG_ID"]
        names = {normalize_text(d["RGLT_DOC_NAME"]).replace(" ", ""): d["RGLT_DOC_CD"]
                 for d in self.db.query(f"SELECT RGLT_DOC_CD, RGLT_DOC_NAME FROM {self.t('RGLT_DOC')}")}
        new_rows, ref_rows, idx_rows = [], [], []
        for r in rows:
            if r["CHG_TYPE_CD"] not in NEW_ROW_TYPES:
                continue
            payload = json.loads(r["CMPR_ADDN_IFMN_CTNT"])
            new_rows.append({
                "id": r["NEW_ARTC_VER_ID"], "d": doc_cd, "v": ver_id, "key": r["NEW_ARTC_KEY_VALU"],
                "lng": r["LNG_ID"], "seq": int(payload["seq"]), "kind": payload["kind"],
                "title": (payload["title"] or "")[:600], "text": payload["text"],
                "h": text_hash(payload["text"]), "c": compare_hash(payload["text"]),
                "atch": payload.get("attachment_sha256") or None, "eff": r["ENFC_STRT_DT"],
                "chg": r["CHG_TYPE_CD"], "meta": _json(payload.get("official") or {})})
            cites = _resolve_citations(payload["text"], doc_cd, lineage_by_key, names)
            for n, cite in enumerate(cites, 1):
                ref_rows.append({"a": r["NEW_ARTC_VER_ID"], "n": n, "d": doc_cd, "lng": r["LNG_ID"], **cite})
            idx_rows.append(("REF", r["NEW_ARTC_KEY_VALU"], len(cites), len(cites)))
        external_targets = self._external_targets(rows, doc_cd)
        with self.db.transaction() as tx:
            self._transition(tx, job, "INDEXING", "FAIL_STEP_NAME=NULL, ERR_CTNT=NULL")
            tx.execute(f"DELETE FROM {self.t('ARTC_RFRN')} WHERE ARTC_VER_ID IN (SELECT ARTC_VER_ID FROM "
                       f"{self.t('ARTC_VER')} WHERE RGLT_VER_ID=:v AND OPEN_YN='N')", {"v": ver_id})
            tx.execute(f"DELETE FROM {self.t('ARTC_VER')} WHERE RGLT_VER_ID=:v AND OPEN_YN='N'", {"v": ver_id})
            tx.execute(f"DELETE FROM {self.t('IDX_WORK')} WHERE LOAD_WORK_ID=:id", {"id": load_id})
            for row in new_rows:
                tx.execute(f"INSERT INTO {self.t('ARTC_VER')} (ARTC_VER_ID, RGLT_DOC_CD, RGLT_VER_ID, ARTC_KEY_VALU, "
                           f"LNG_ID, ARTC_SEQ, ARTC_SE_CD, ARTC_TITLE_NAME, ARTC_CTNT, CTNT_HASH_VALU, "
                           f"CMPR_HASH_VALU, ATCH_HASH_VALU, ENFC_STRT_DT, ENFC_END_DT, CHG_TYPE_CD, STRC_UNIT_ID, "
                           f"OPEN_YN, ARTC_ADDN_IFMN_CTNT, RGSN_ASTM) VALUES (:id, :d, :v, :key, :lng, :seq, :kind, "
                           f":title, :text, :h, :c, :atch, :eff, NULL, :chg, NULL, 'N', :meta, {{now}})", row)
            for row in ref_rows:
                tx.execute(f"INSERT INTO {self.t('ARTC_RFRN')} (ARTC_VER_ID, RFRN_SEQ, RGLT_DOC_CD, LNG_ID, "
                           f"TAGT_RGLT_DOC_CD, TAGT_ARTC_KEY_VALU, TAGT_LNG_ID, EXTR_YN, RFRN_TEXT_CTNT, RGSN_ASTM) "
                           f"VALUES (:a, :n, :d, :lng, :tdoc, :tkey, :tlng, :ext, :text, {{now}})", row)
            for kind, key, expected, result in idx_rows:
                self._idx_insert(tx, load_id, kind, key, "READY", expected, result, None)
            for kind in external:
                self._idx_insert(tx, load_id, kind, "*", "PENDING", None, None, None)
            self._hist(tx, load_id, self._hist_seq(load_id) + 1, job["PRCS_STTS_CD"], "INDEXING",
                       {"hidden_rows": len(new_rows), "references": len(ref_rows), "external": list(external),
                        "impact_candidates": len(external_targets)})
        hidden = self.db.query(f"SELECT COUNT(*) AS N FROM {self.t('ARTC_VER')} WHERE RGLT_VER_ID=:v "
                               f"AND OPEN_YN='N'", {"v": ver_id})[0]["N"]
        if int(hidden) != len(new_rows):
            self.fail(load_id, "INDEXING", f"숨김 조문 수 불일치 {hidden}/{len(new_rows)}")
            raise IncrementError("숨김 조문 수 불일치")
        return {"hidden_rows": len(new_rows), "references": len(ref_rows),
                "pending": list(external), "state": "INDEXING"}

    def _idx_insert(self, tx, load_id, kind, key, status, expected, result, ref) -> None:
        tx.execute(f"INSERT INTO {self.t('IDX_WORK')} (LOAD_WORK_ID, IDX_KIND_CD, ARTC_KEY_VALU, IDX_STTS_CD, "
                   f"EXPC_CNT, RSLT_CNT, RSLT_REF_VALU, ERR_CTNT, RGSN_ASTM, CHG_ASTM) VALUES (:id, :kind, :key, "
                   f":status, :expected, :result, :ref, NULL, {{now}}, {{now}})",
                   {"id": load_id, "kind": kind, "key": key, "status": status, "expected": expected,
                    "result": result, "ref": ref})

    def mark_index(self, load_id: str, kind: str, *, status: str, count: int | None = None,
                   ref: str | None = None, error: str | None = None, key: str = "*") -> None:
        if status not in ("READY", "FAILED", "PENDING"):
            raise IncrementError("status는 READY/FAILED/PENDING")
        job = self._require(load_id)
        if job["PRCS_STTS_CD"] != "INDEXING":
            raise IncrementError("INDEXING 상태가 아니다")
        with self.db.transaction() as tx:
            tx.execute(f"UPDATE {self.t('IDX_WORK')} SET IDX_STTS_CD=:status, RSLT_CNT=:count, RSLT_REF_VALU=:ref, "
                       f"ERR_CTNT=:error, CHG_ASTM={{now}} WHERE LOAD_WORK_ID=:id AND IDX_KIND_CD=:kind "
                       f"AND ARTC_KEY_VALU=:key",
                       {"status": status, "count": count, "ref": ref, "error": error, "id": load_id,
                        "kind": kind, "key": key}, expect=1)

    def link_gold(self, load_id: str, *, dtls_hash: str, rglt_doc_id: str | None = None,
                  verifier=None) -> dict:
        """새 판본이 숨김 상태로 게시된 Gold 세대를 연결하고, verifier가 있으면 건수를 확인한다."""
        job = self._require(load_id)
        ver = self.version(job["NEW_VER_ID"])
        doc_id = rglt_doc_id or ver["RGLT_DOC_ID"]
        counts = verifier.counts(dtls_hash, doc_id) if verifier is not None else None
        ok = counts is None or (counts.get("DOC_VER") == 1 and counts.get("DOC_UNIT", 0) > 0)
        with self.db.transaction() as tx:
            tx.execute(f"UPDATE {self.t('RGLT_VER')} SET DTLS_HASH_VALU=:dtls, RGLT_DOC_ID=:doc "
                       f"WHERE RGLT_VER_ID=:v AND VER_STTS_CD='CANDIDATE'",
                       {"dtls": dtls_hash, "doc": doc_id, "v": ver["RGLT_VER_ID"]}, expect=1)
        self.mark_index(load_id, "GOLD", status="READY" if ok else "FAILED",
                        count=(counts or {}).get("DOC_UNIT"), ref=f"{dtls_hash}/{doc_id}",
                        error=None if ok else f"Gold 건수 불일치 {counts}")
        return {"ok": ok, "counts": counts}

    def fail(self, load_id: str, step: str, error: str) -> None:
        job = self._require(load_id)
        with self.db.transaction() as tx:
            self._transition(tx, job, "FAILED", "FAIL_STEP_NAME=:step, ERR_CTNT=:err",
                             {"step": step, "err": error[:1300]})
            self._hist(tx, load_id, self._hist_seq(load_id) + 1, job["PRCS_STTS_CD"], "FAILED",
                       {"step": step, "error": error})

    # ---------------------------------------------------------------- 4. 활성화 (한 트랜잭션)
    def _external_targets(self, rows: list[dict], doc_cd: str) -> list[dict]:
        """바뀐 계보를 인용하는 현행 조문(같은 문서 포함)과 연결 문서 — 1단계만."""
        lineages = sorted({r["LNG_ID"] for r in rows if r["CHG_TYPE_CD"] in IMPACT_TYPES + (MOVE,)})
        out: list[dict] = []
        for start in range(0, len(lineages), 200):
            part = {f"l{i}": v for i, v in enumerate(lineages[start:start + 200])}
            if not part:
                continue
            out.extend(self.db.query(
                f"SELECT r.TAGT_LNG_ID, r.RGLT_DOC_CD, r.LNG_ID, a.ARTC_KEY_VALU FROM {self.t('ARTC_RFRN')} r "
                f"JOIN {self.t('ARTC_VER')} a ON a.ARTC_VER_ID=r.ARTC_VER_ID "
                f"WHERE a.OPEN_YN='Y' AND a.ENFC_END_DT IS NULL "
                f"AND r.TAGT_LNG_ID IN ({', '.join(':' + k for k in part)})", part))
        return out

    def _activation_plan(self, load_id: str) -> dict:
        job = self._require(load_id)
        if job["PRCS_STTS_CD"] != "INDEXING":
            raise IncrementError(f"INDEXING 상태만 활성화 (현재 {job['PRCS_STTS_CD']})")
        pending = self.db.query(f"SELECT IDX_KIND_CD, ARTC_KEY_VALU, IDX_STTS_CD FROM {self.t('IDX_WORK')} "
                                f"WHERE LOAD_WORK_ID=:id AND IDX_STTS_CD<>'READY'", {"id": load_id})
        if pending:
            raise IncrementError(f"색인 준비 미완료: {[(p['IDX_KIND_CD'], p['ARTC_KEY_VALU'], p['IDX_STTS_CD']) for p in pending][:5]}")
        doc_cd, ver_id = job["RGLT_DOC_CD"], job["NEW_VER_ID"]
        rows = self.changes(load_id)
        gate = json.loads(job["GATE_RSLT_CTNT"] or "{}")
        citing = self._external_targets(rows, doc_cd)
        links = self.db.query(f"SELECT TAGT_RGLT_DOC_CD, LINK_KIND_CD FROM {self.t('DOC_LINK')} "
                              f"WHERE RGLT_DOC_CD=:d", {"d": doc_cd})
        name = gate.get("doc_name") or ""
        document = self.document(doc_cd)
        aliases = json.loads(document.get("ALIAS_CTNT") or "[]") if document else []
        if document and name and name != document["RGLT_DOC_NAME"] and document["RGLT_DOC_NAME"] not in aliases:
            aliases.append(document["RGLT_DOC_NAME"])
        return {"job": job, "doc_cd": doc_cd, "ver_id": ver_id, "base_id": job["BASE_VER_ID"], "rows": rows,
                "new_count": sum(1 for r in rows if r["CHG_TYPE_CD"] in NEW_ROW_TYPES),
                "effective": gate.get("effective") or self.version(ver_id)["ENFC_STRT_DT"],
                "reviews": _reviews(load_id, rows, citing, links, doc_cd),
                "name": name or document["RGLT_DOC_NAME"], "aliases": aliases}

    def _apply_activation(self, tx, plan: dict, user: str, channel_name: str | None) -> None:
        job, doc_cd, ver_id, base_id = plan["job"], plan["doc_cd"], plan["ver_id"], plan["base_id"]
        rows, effective = plan["rows"], plan["effective"]
        load_id = job["LOAD_WORK_ID"]
        self._transition(tx, job, "ACTIVATED")
        tx.execute(f"UPDATE {self.t('RGLT_DOC')} SET ACTV_VER_ID=:new, RGLT_DOC_NAME=:name, "
                   f"ALIAS_CTNT=:aliases, CHG_ASTM={{now}} WHERE RGLT_DOC_CD=:d AND "
                   f"(ACTV_VER_ID=:base OR (ACTV_VER_ID IS NULL AND :base IS NULL))",
                   {"new": ver_id, "name": plan["name"], "aliases": _json(plan["aliases"]),
                    "d": doc_cd, "base": base_id}, expect=1)
        if base_id:
            tx.execute(f"UPDATE {self.t('RGLT_VER')} SET VER_STTS_CD='SUPERSEDED', ENFC_END_DT=:end, "
                       f"SPSD_ASTM={{now}} WHERE RGLT_VER_ID=:base AND VER_STTS_CD='ACTIVE'",
                       {"end": day_before(effective), "base": base_id}, expect=1)
        tx.execute(f"UPDATE {self.t('RGLT_VER')} SET VER_STTS_CD='ACTIVE', ACTV_ASTM={{now}} "
                   f"WHERE RGLT_VER_ID=:v AND VER_STTS_CD='CANDIDATE'", {"v": ver_id}, expect=1)
        for r in rows:
            if r["CHG_TYPE_CD"] in CLOSE_TYPES:
                tx.execute(f"UPDATE {self.t('ARTC_VER')} SET ENFC_END_DT=:end, SPSD_ASTM={{now}} "
                           f"WHERE ARTC_VER_ID=:old AND ENFC_END_DT IS NULL AND OPEN_YN='Y'",
                           {"end": day_before(r["ENFC_STRT_DT"] or effective),
                            "old": r["OLD_ARTC_VER_ID"]}, expect=1)
        tx.execute(f"UPDATE {self.t('ARTC_VER')} SET OPEN_YN='Y' WHERE RGLT_VER_ID=:v AND OPEN_YN='N'",
                   {"v": ver_id}, expect=plan["new_count"])
        for review in plan["reviews"]:
            tx.execute(f"INSERT INTO {self.t('RVW_TRGT')} (RVW_TRGT_ID, LOAD_WORK_ID, RVW_KIND_CD, SRC_LNG_ID, "
                       f"TAGT_RGLT_DOC_CD, TAGT_LNG_ID, TAGT_ARTC_KEY_VALU, RVW_RSN_CTNT, RVW_STTS_CD, "
                       f"PRCS_USER_ID, RGSN_ASTM, PRCS_ASTM) VALUES (:id, :load, :kind, :src, :tdoc, :tlng, "
                       f":tkey, :reason, 'OPEN', NULL, {{now}}, NULL)", review)
        self._hist(tx, load_id, self._hist_seq(load_id) + 1, "INDEXING", "ACTIVATED",
                   {"user": user, "new_rows": plan["new_count"],
                    "closed": sum(1 for r in rows if r["CHG_TYPE_CD"] in CLOSE_TYPES),
                    "reviews": len(plan["reviews"]), "channel": channel_name})

    def _invalidate(self, plan: dict) -> dict:
        return {"doc_cd": plan["doc_cd"], "rglt_doc_ids": [self.version(plan["ver_id"])["RGLT_DOC_ID"]] +
                ([self.version(plan["base_id"])["RGLT_DOC_ID"]] if plan["base_id"] else [])}

    def activate(self, load_id: str, *, channel: ChannelSwitch | None = None,
                 user: str = "") -> dict:
        return self.activate_many([load_id], channel=channel, user=user)["results"][0]

    def activate_many(self, load_ids: list[str], *, channel: ChannelSwitch | None = None,
                      user: str = "") -> dict:
        """여러 문서를 한 트랜잭션에서 활성화하고 조회 채널은 한 번만 바꾼다.
        새 Gold 세대 하나에 여러 문서의 새 판본이 들어가므로, 하나라도 어긋나면 전부 롤백한다."""
        if not load_ids or len(set(load_ids)) != len(load_ids):
            raise IncrementError("활성화할 작업 목록이 비었거나 중복")
        plans = [self._activation_plan(i) for i in load_ids]
        if len({p["doc_cd"] for p in plans}) != len(plans):
            raise IncrementError("한 번에 같은 문서의 판본 둘을 활성화할 수 없다")
        try:
            with self.db.transaction() as tx:
                for plan in plans:
                    self._apply_activation(tx, plan, user, channel.channel if channel else None)
                if channel is not None:
                    sql, binds = channel.sql()
                    tx.execute(sql, binds, expect=1)
        except Exception as exc:          # Dataiku 경로는 Oracle 오류가 실행기 예외로 온다
            for load_id in load_ids:
                self._note_error(load_id, f"활성화 롤백: {type(exc).__name__}: {exc}")
            raise IncrementError(f"활성화 롤백 — 기존 현행본 유지: {exc}") from exc
        results = [{"load_id": p["job"]["LOAD_WORK_ID"], "state": "ACTIVATED", "new_rows": p["new_count"],
                    "reviews": len(p["reviews"]), "invalidate": self._invalidate(p)} for p in plans]
        return {"state": "ACTIVATED", "results": results, "channel": channel.channel if channel else None}

    # ---------------------------------------------------------------- 5. 되돌리기 (한 트랜잭션)
    def rollback(self, load_id: str, *, user: str, reason: str,
                 channel: ChannelSwitch | None = None) -> dict:
        """활성화한 판본을 닫고 기준 판본을 다시 연다. 이 판본이 아직 현행일 때만 (뒤 판본이 있으면 거절).
        새 조문 행은 지우지 않고 숨긴다(OPEN_YN=N). 같은 원문 파일은 같은 작업이라 다시 넣으려면
        수정한 파일이 필요하다."""
        job = self._require(load_id)
        if job["PRCS_STTS_CD"] != "ACTIVATED":
            raise IncrementError(f"ACTIVATED 상태만 되돌린다 (현재 {job['PRCS_STTS_CD']})")
        doc_cd, ver_id, base_id = job["RGLT_DOC_CD"], job["NEW_VER_ID"], job["BASE_VER_ID"]
        document = self.document(doc_cd)
        if (document or {}).get("ACTV_VER_ID") != ver_id:
            raise IncrementError("이 판본 뒤에 다른 판본이 활성화됐다 — 최신 판본부터 되돌린다")
        rows = self.changes(load_id)
        new_count = sum(1 for r in rows if r["CHG_TYPE_CD"] in NEW_ROW_TYPES)
        closed = [r for r in rows if r["CHG_TYPE_CD"] in CLOSE_TYPES and r["OLD_ARTC_VER_ID"]]
        try:
            with self.db.transaction() as tx:
                self._transition(tx, job, "ROLLED_BACK", "ERR_CTNT=:reason", {"reason": reason[:1300]})
                tx.execute(f"UPDATE {self.t('RGLT_DOC')} SET ACTV_VER_ID=:base, CHG_ASTM={{now}} "
                           f"WHERE RGLT_DOC_CD=:d AND ACTV_VER_ID=:new",
                           {"base": base_id, "d": doc_cd, "new": ver_id}, expect=1)
                tx.execute(f"UPDATE {self.t('RGLT_VER')} SET VER_STTS_CD='ROLLED_BACK', SPSD_ASTM={{now}} "
                           f"WHERE RGLT_VER_ID=:v AND VER_STTS_CD='ACTIVE'", {"v": ver_id}, expect=1)
                if base_id:
                    tx.execute(f"UPDATE {self.t('RGLT_VER')} SET VER_STTS_CD='ACTIVE', ENFC_END_DT=NULL, "
                               f"SPSD_ASTM=NULL WHERE RGLT_VER_ID=:base AND VER_STTS_CD='SUPERSEDED'",
                               {"base": base_id}, expect=1)
                tx.execute(f"UPDATE {self.t('ARTC_VER')} SET OPEN_YN='N' WHERE RGLT_VER_ID=:v AND OPEN_YN='Y'",
                           {"v": ver_id}, expect=new_count)
                for r in closed:
                    tx.execute(f"UPDATE {self.t('ARTC_VER')} SET ENFC_END_DT=NULL, SPSD_ASTM=NULL "
                               f"WHERE ARTC_VER_ID=:old AND ENFC_END_DT IS NOT NULL AND OPEN_YN='Y'",
                               {"old": r["OLD_ARTC_VER_ID"]}, expect=1)
                tx.execute(f"UPDATE {self.t('RVW_TRGT')} SET RVW_STTS_CD='DISMISSED', PRCS_USER_ID=:user, "
                           f"PRCS_ASTM={{now}} WHERE LOAD_WORK_ID=:id AND RVW_STTS_CD='OPEN'",
                           {"user": user, "id": load_id})
                if channel is not None:
                    sql, binds = channel.sql()
                    tx.execute(sql, binds, expect=1)
                self._hist(tx, load_id, self._hist_seq(load_id) + 1, "ACTIVATED", "ROLLED_BACK",
                           {"user": user, "reason": reason, "hidden_rows": new_count, "reopened": len(closed),
                            "channel": channel.channel if channel else None})
        except IncrementError:
            raise
        except Exception as exc:
            raise IncrementError(f"되돌리기 롤백 — 현재 판본 유지: {exc}") from exc
        return {"state": "ROLLED_BACK", "active_version": base_id, "hidden_rows": new_count,
                "reopened": len(closed),
                "invalidate": {"doc_cd": doc_cd, "rglt_doc_ids": [self.version(ver_id)["RGLT_DOC_ID"]] +
                               ([self.version(base_id)["RGLT_DOC_ID"]] if base_id else [])}}

    def _note_error(self, load_id: str, message: str) -> None:
        with self.db.transaction() as tx:
            tx.execute(f"UPDATE {self.t('LOAD_WORK')} SET ERR_CTNT=:err, CHG_ASTM={{now}} WHERE LOAD_WORK_ID=:id",
                       {"err": message[:1300], "id": load_id})


def comparison_rows(load_id: str, version_id: str, changes: list[Change]) -> list[dict]:
    """조문 변경 목록 → 대비표 행 (증분 표 ARTC_CMPR 행과 같은 모양)."""
    rows = []
    for seq, change in enumerate(changes, 1):
        new = change.new
        payload = None
        if new is not None:
            payload = {"kind": new.kind, "title": new.title, "text": new.text, "seq": new.seq,
                       "attachment_sha256": new.attachment_sha256,
                       "official": {"changed": new.official_changed, "effective": new.official_effective,
                                    "moved": list(new.official_moved)},
                       "official_note": change.official_note}
        rows.append({
            "LOAD_WORK_ID": load_id, "CMPR_SEQ": seq, "CHG_TYPE_CD": change.change_type,
            "OLD_ARTC_VER_ID": change.old.version_id if change.old else None,
            "OLD_ARTC_KEY_VALU": change.old.key if change.old else None,
            "NEW_ARTC_KEY_VALU": new.key if new else None,
            "NEW_ARTC_VER_ID": ("A" + stable_id(version_id, new.key, length=31)) if new else None,
            "LNG_ID": change.lineage_id, "SMLR_RATE": round(float(change.similarity), 4),
            "JDGM_RSN_CTNT": change.reason[:1300], "ENFC_STRT_DT": change.effective_from or None,
            "RULE_RVW_YN": change.rule_review,
            "CMPR_ADDN_IFMN_CTNT": _json(payload) if payload is not None else None,
        })
    return rows


def _resolve_citations(text: str, doc_cd: str, lineage_by_key: dict[str, str],
                       names: dict[str, str]) -> list[dict]:
    out = []
    body = normalize_text(text)
    for cite in citations(body):
        target_doc, target_lineage = None, None
        if not cite.external:
            target_doc = doc_cd
            target_lineage = lineage_by_key.get(cite.key)
        else:
            position = body.find(cite.text)
            opening = body.rfind("「", 0, position)
            closing = body.find("」", opening)
            if opening != -1 and 0 < closing < position:
                name = body[opening + 1:closing].replace(" ", "")
                target_doc = names.get(name)
        out.append({"tdoc": target_doc, "tkey": cite.key, "tlng": target_lineage,
                    "ext": "Y" if cite.external else "N", "text": cite.text[:600]})
    return out


def _reviews(load_id: str, rows: list[dict], citing: list[dict], links: list[dict], doc_cd: str) -> list[dict]:
    out: dict[str, dict] = {}

    def add(kind, src, tdoc, tlng, tkey, reason):
        rid = "R" + stable_id(load_id, kind, src or "", tdoc or "", tlng or "", tkey or "", length=31)
        out[rid] = {"id": rid, "load": load_id, "kind": kind, "src": src, "tdoc": tdoc, "tlng": tlng,
                    "tkey": tkey, "reason": reason[:1300]}

    changed = {r["LNG_ID"]: r for r in rows}
    for r in rows:
        if r["RULE_RVW_YN"] == "Y":
            add("RULE", r["LNG_ID"], doc_cd, r["LNG_ID"], r["NEW_ARTC_KEY_VALU"] or r["OLD_ARTC_KEY_VALU"],
                f"{r['CHG_TYPE_CD']} — 이 계보에 연결된 조건·판단·실행 룰 재검토")
    for c in citing:
        r = changed.get(c["TAGT_LNG_ID"])
        if r is None:
            continue
        if r["CHG_TYPE_CD"] == MOVE and c["RGLT_DOC_CD"] == doc_cd:
            continue                      # 같은 문서의 번호 이동은 이번 비교가 REF_ONLY로 처리
        add("CITING_ARTICLE", r["LNG_ID"], c["RGLT_DOC_CD"], c["LNG_ID"], c["ARTC_KEY_VALU"],
            f"인용 대상 {r['OLD_ARTC_KEY_VALU'] or ''}→{r['NEW_ARTC_KEY_VALU'] or ''} {r['CHG_TYPE_CD']}")
    if any(r["CHG_TYPE_CD"] in IMPACT_TYPES + (ADD,) for r in rows):
        for link in links:
            add("LINKED_DOC", None, link["TAGT_RGLT_DOC_CD"], None, None,
                f"{link['LINK_KIND_CD']} 연결 문서 — {doc_cd} 개정에 따른 상충·위임 점검")
    return list(out.values())
