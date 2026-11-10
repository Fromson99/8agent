"""떨어진 폴더 → 비교 → 자동 반영 → Gold(개발계 실버) 전환 · 되돌리기 · 정리 — Dataiku 실행기.

새 DB 표 없이 기존 표와 Dataiku 관리 폴더(JSON)만 쓴다. GENOS 구조화·Agent·적재는 이미 설치된
R6(GENOS → ORDS → SIDDA.LGL_PIPE_RESULT_A → Dataiku 03 적재) 함수를 그대로 부른다.

동작 (ACTION)
  check    쓰기 권한 확인 (DELETE·UPDATE·INSERT를 WHERE 1=0으로 — 행은 안 바뀜)
  status   지금 채널이 가리키는 세대·문서 수·지난 원문 ZIP 일치·업데이트 기록
  decide   떨어진 파일 → (해시가 지금 Gold에 있으면 변경 없음) → 바뀐 파일만 작은 R6 실행으로 구조화
           → Gold에서 읽은 지금 판본과 조문 비교 → APPROVED / HOLD / WAIT_EFFECTIVE / NO_CHANGE, 대비표
           → 비교용 Agent 결과 삭제
  publish  승인 문서만 바꿔 넣은 전체 원문 ZIP → R6 실행(구조화·Agent·03 적재) → 새 세대(아직 서빙 안 함)
           → 적재 건수 확인 뒤 Agent 결과 삭제
  activate 벡터 게시 행 + 채널 교체(한 블록) → 업데이트 기록(diff JSON + 옛 파일, 최근 3개)
           → Gold 옛 세대 정리(지금 + 이전 2개만 남김, 묶음 삭제)
  rollback 가장 최근 업데이트를 되돌림 — 이전 세대가 남아 있으면 채널만, 없으면 옛 파일로 다시 만들어 게시
  cleanup  남은 Agent 결과·옛 세대 정리를 이어서 (끊긴 정리 재개)
  run      decide → (승인 있으면) publish → activate 를 차례로
"""
from __future__ import annotations

import datetime
import gzip
import io
import json
import re
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import history
from .corpus import (DOCUMENTS, SOURCES, LazyZip, Replacement, assemble_files, file_sha256, identify,
                     inventory, sha256, verify_base, write_zip, write_zip_file)
from .daily import header_for, Incoming
from .decide import APPROVED, HOLD, NO_CHANGE, WAIT_EFFECTIVE, compare
from .lawgo_parse import ParseError
from .release_ops import (Names, ReleaseError, agent_cleanup, channel, documents, generation,
                          privilege_check, prune, prune_plan, releases, structure, switch)
from .structured import from_structure, header_from_name, header_from_xml

TERMINAL = {NO_CHANGE, HOLD, "PUBLISHED"}


class Stop(RuntimeError):
    """사용자에게 보일 멈춤 사유 (코드: 설명)."""


def kst_today() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%Y%m%d")


def run_id() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%Y%m%d-%H%M%S")


# ------------------------------------------------------------------ 구조화 결과 읽기

def read_generation_store(path: Path, wanted_sha: set[str]) -> dict[str, dict]:
    """GENOS 결과 generation/store.sqlite → {원문 sha: {name, nodes, blocks}}."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        block_table = "source_block" if "source_block" in tables else "block_payload"
        out = {}
        for doc_id, name, sha in db.execute("SELECT document_id, name, source_artifact_sha256 FROM document"):
            if sha not in wanted_sha:
                continue
            nodes = [json.loads(j) for (j,) in db.execute(
                "SELECT json FROM source_unit WHERE document_id=?", (doc_id,))]
            blocks = []
            for idx, unit, text, j in db.execute(
                    f"SELECT block_id, unit_id, text, json FROM {block_table} WHERE document_id=?", (doc_id,)):
                meta = json.loads(j) if j else {}
                blocks.append({**meta, "idx": int(idx), "text": text or "",
                               "node": int(unit) if unit not in (None, "") else meta.get("node"),
                               "kind": meta.get("kind", "text")})
            out[sha] = {"doc_id": doc_id, "name": name, "nodes": nodes,
                        "blocks": sorted(blocks, key=lambda b: b["idx"])}
        return out
    finally:
        db.close()


# ------------------------------------------------------------------ R6 호출 (Dataiku 안)

class R6Runner:
    """설치된 R6의 submit / wait_ready / load 를 증분 전용 trial 이름과 입력 ZIP으로 부른다."""

    def __init__(self, cfg: dict, overrides: dict):
        self.cfg = {**cfg, **overrides}

    def _ctx(self, trial: str, zip_name: str, zip_sha: str):
        import dataiku
        cfg = {**self.cfg, "DATA_ZIP_NAME": zip_name, "DATA_ZIP_SHA256": zip_sha}
        project = dataiku.api_client().get_default_project().project_key
        if cfg["project"] != project:
            raise Stop("FLOW_PROJECT_MISMATCH: R6 설치 프로젝트와 다른 프로젝트")
        ids = dict(cfg["folders"], input=cfg["INPUT_FOLDER_ID"], support=cfg["SUPPORT_FOLDER_ID"])
        folders = {k: dataiku.Folder(v) for k, v in ids.items() if v}
        paths = Path(cfg["WORK_DIR"]) / "agent-layer-zip-r6" / project / cfg["ENVIRONMENT"] / trial
        paths.mkdir(parents=True, exist_ok=True, mode=0o700)
        return cfg, paths, folders

    def step(self, op: str, trial: str, zip_name: str, zip_sha: str):
        import dataiku
        import flow_runtime as fr
        import transport as t
        cfg, paths, folders = self._ctx(trial, zip_name, zip_sha)
        fn = {"submit": fr.submit, "wait": fr.wait_ready, "load": fr.load}[op]
        with t.lock(paths / "flow.lock"):
            return fn(cfg, paths, folders, dataiku.get_custom_variables(), trial)

    def restore_generation(self, trial: str, zip_name: str, zip_sha: str, dest: Path) -> tuple[Path, str]:
        import agent_stage as stage
        import flow_runtime as fr
        import transport as t
        cfg, _, folders = self._ctx(trial, zip_name, zip_sha)
        record = fr.read(folders["wait"], trial + "/ready.json")
        intent = record["intent"]
        fr.validate_intent(intent, cfg, trial)
        query = fr.layer_query(cfg["AGENT_CONNECTION"])
        stage.restore(query, intent["job"], intent["binding"], record["result"], dest / "result.zip")
        t.unpack(dest / "result.zip", dest / "restored", prefixes=("generation/",))
        return dest / "restored/generation", intent["job"]

    def job(self, trial: str, zip_name: str, zip_sha: str) -> str:
        import flow_runtime as fr
        _, _, folders = self._ctx(trial, zip_name, zip_sha)
        return fr.read(folders["wait"], trial + "/ready.json")["intent"]["job"]

    def report(self, trial: str, zip_name: str, zip_sha: str) -> dict:
        import flow_runtime as fr
        _, _, folders = self._ctx(trial, zip_name, zip_sha)
        return fr.read(folders["load"], trial + "/report.json")


# ------------------------------------------------------------------ 실행기

@dataclass
class Params:
    channel: str                          # 서빙 채널 (개발계 DP_QUERY_CHANNEL 값, 운영 main)
    base_zip_name: str = ""               # 첫 실행: 지금 세대를 만든 원문 ZIP (R6 입력 폴더)
    base_prefix: str = ""                 # 또는 입력 폴더의 낱개 원문 파일 접두 (그 아래 external/… 경로)
    hold_on_strong: bool = True
    retry_hold: bool = False
    prune_batch: int = 50000
    keep: int = history.KEEP
    today: str = ""
    agent_table: str = "SIDDA.LGL_PIPE_RESULT_A"
    extra: dict = field(default_factory=dict)


class Flow:
    def __init__(self, *, store: history.Store, drop: history.Store, inputs: history.Store, db, agent_db,
                 names: Names, r6, params: Params, log=print):
        self.store, self.drop, self.inputs = store, drop, inputs
        self.db, self.agent_db, self.n, self.r6, self.p, self.log = db, agent_db, names, r6, params, log
        self._tmp = tempfile.TemporaryDirectory(prefix="increment-")
        self.work = Path(self._tmp.name)

    def _open_zip(self, name: str, expect_sha: str = "") -> tuple[LazyZip, str]:
        local = self.work / (uuid.uuid4().hex + ".zip")
        if not self.inputs.download(name, local):
            raise Stop(f"ZIP_MISSING: 입력 폴더에 {name} 없음")
        digest = file_sha256(local)
        if expect_sha and digest != expect_sha:
            raise Stop(f"ZIP_CHANGED: {name} 해시가 기록과 다름")
        return LazyZip(local), digest

    def _put_zip(self, name: str, files) -> str:
        local = self.work / (uuid.uuid4().hex + ".zip")
        digest = write_zip_file(files, local)
        self.inputs.upload_file(name, local)
        local.unlink()
        return digest

    # ---------------------------------------------------------------- 공통
    def _current(self) -> dict:
        if self.p.channel.startswith("g19_"):
            raise Stop("SERVING_CHANNEL_IS_LOADER_CHANNEL: 서빙 채널이 적재기가 세대마다 만드는 g19_ 이름이다. "
                       "main 채널 행을 추가하고(INCREMENT_MAIN_CHANNEL SQL) 서빙 DP_QUERY_CHANNEL을 main으로 바꾼 뒤 "
                       "CHANNEL='main'으로 실행")
        ch = channel(self.db, self.n, self.p.channel)
        gen = generation(self.db, self.n, ch["query_id"])
        docs = documents(self.db, self.n, gen.dataset_version)
        return {"channel": ch, "generation": gen.as_dict(), "documents": docs}

    def _corpus(self, cur: dict) -> tuple[dict, dict[str, bytes]]:
        st = history.state(self.store)
        corpus = st.get("corpus") or {}
        if st.get("current_query") != cur["channel"]["query_id"] or not corpus.get("name"):
            if self.p.base_zip_name:
                corpus = {"name": self.p.base_zip_name}
            elif self.p.base_prefix:
                corpus = {"name": self._zip_from_prefix(self.p.base_prefix)}
            else:
                raise Stop("BASE_ZIP_REQUIRED: 첫 실행은 지금 세대를 만든 원문 ZIP 이름(BASE_DATA_ZIP_NAME) 또는 "
                           "입력 폴더의 원문 파일 접두(BASE_DOCUMENT_PREFIX)가 필요")
        files, digest = self._open_zip(corpus["name"], corpus.get("sha256", ""))
        check = verify_base(files, {d["doc_id"] for d in cur["documents"]})
        if not check["ok"]:
            raise Stop("BASE_ZIP_NOT_CURRENT_GENERATION: 원문 ZIP 문서와 지금 세대 문서가 다름 " +
                       json.dumps({k: check[k] for k in ("zip_documents", "current_documents", "missing_count",
                                                          "extra_count", "missing_in_zip", "not_in_current")},
                                  ensure_ascii=False)[:1500])
        return {"name": corpus["name"], "sha256": digest}, files

    def _zip_from_prefix(self, prefix: str) -> str:
        """입력 폴더의 낱개 원문 파일(R6 LOOSE 입력과 같은 배치) → 기준 원문 ZIP 한 개."""
        prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        members = {}
        for path in self.inputs.list(prefix):
            rel = path[len(prefix):]
            parts = PurePosixPath(rel).parts
            if parts and parts[0] in SOURCES and (PurePosixPath(rel).suffix.lower() in DOCUMENTS
                                                  or rel.endswith(".genos.json")):
                members[rel] = path
        if not members:
            raise Stop(f"BASE_PREFIX_EMPTY: {prefix} 아래 출처 경로(external/…·internal/…) 원문 파일 없음")

        class _Lazy(dict):
            def __getitem__(inner, key):
                return self.inputs.get(members[key])
        local = self.work / (uuid.uuid4().hex + ".zip")
        digest = write_zip_file(_Lazy({k: None for k in members}), local)
        final = f"INCREMENT_BASE_{digest[:12]}.zip"
        if final not in self.inputs.list(final):
            self.inputs.upload_file(final, local)
        local.unlink()
        return final

    @staticmethod
    def _header(file_name: str, data: bytes):
        return header_for(Incoming(file_name, data, {}))

    def _cleanup_job(self, trial: str, job: str) -> None:
        st = history.state(self.store)
        st.setdefault("jobs", {})[trial] = {"job": job, "agent_cleaned": False}
        history.save_state(self.store, st)
        rounds = agent_cleanup(self.agent_db, job, table=self.p.agent_table)
        st = history.state(self.store)
        st["jobs"][trial] = {"job": job, "agent_cleaned": True, "rounds": rounds}
        history.save_state(self.store, st)

    # ---------------------------------------------------------------- check
    def check(self) -> dict:
        return privilege_check(self.db, self.n, agent_table=self.p.agent_table, agent_db=self.agent_db)

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        cur = self._current()
        st = history.state(self.store)
        out = {"channel": cur["channel"], "generation": {k: v for k, v in cur["generation"].items() if k != "documents"},
               "documents": len(cur["documents"]), "state": {k: st.get(k) for k in ("current_query", "corpus", "seq")},
               "updates": [{k: u.get(k) for k in ("seq", "run", "status", "at")} for u in history.updates(self.store)],
               "pending_agent_cleanup": [k for k, v in (st.get("jobs") or {}).items() if not v.get("agent_cleaned")]}
        try:
            corpus, _ = self._corpus(cur)
            out["base_zip"] = {"ok": True, **corpus}
        except Stop as exc:
            out["base_zip"] = {"ok": False, "reason": str(exc)}
        return out

    # ---------------------------------------------------------------- decide
    def decide(self, run: str) -> dict:
        today = self.p.today or kst_today()
        cur = self._current()
        corpus, files = self._corpus(cur)
        current_ids = {d["doc_id"] for d in cur["documents"]}
        inv = inventory(files)
        st = history.state(self.store)
        entries, pending = [], []
        for path in self.drop.list():
            if PurePosixPath(path).suffix.lower() not in DOCUMENTS:
                continue
            data = self.drop.get(path)
            digest = sha256(data)
            entry = {"path": path, "file": PurePosixPath(path).name, "sha256": digest}
            prior = (st.get("files") or {}).get(digest)
            if prior and (prior["decision"] in TERMINAL - {HOLD} or (prior["decision"] == HOLD and not self.p.retry_hold)):
                entries.append({**entry, "decision": "ALREADY", "previous": prior})
                continue
            if digest[:16] in current_ids:
                entries.append({**entry, "decision": NO_CHANGE, "reasons": ["같은 파일이 이미 지금 세대에 있음"]})
                continue
            doc_cd = identify(entry["file"], data)
            members = [r for r in inv if r["doc_cd"] == doc_cd]
            entry.update(doc_cd=doc_cd, members=[r["member"] for r in members])
            if members:
                target = members[0]["member"]
                source = ""
            else:
                parts = PurePosixPath(path).parts
                if len(parts) < 3 or parts[0] not in SOURCES:
                    entries.append({**entry, "decision": HOLD, "reasons": [
                        "지난 원문에 없는 새 문서 — 출처 경로 폴더에 넣어야 함 (예: external/financial_team/law/<문서명>/파일)"]})
                    continue
                law = doc_cd.split(":")[0] in ("LAW", "ADMRUL")
                source = "/".join(parts[:-2] if law and len(parts) > 3 else parts[:-1])
                target = path
            entry.update(target=target, source=source)
            pending.append((entry, data))
        dup = {}
        for entry, _ in pending:
            dup.setdefault(entry["doc_cd"], []).append(entry)
        for doc_cd, group in dup.items():
            if len(group) > 1:
                for e in group:
                    e["decision"], e["reasons"] = HOLD, [f"같은 문서 파일이 {len(group)}개 떨어짐 — 하나만 남겨야 함"]
        work = [(e, d) for e, d in pending if "decision" not in e]
        entries += [e for e, _ in pending if "decision" in e]

        missing = [(e, d) for e, d in work if self.store.get(f"structured/{e['sha256']}.json.gz") is None]
        if missing:
            zip_bytes = write_zip({e["target"]: d for e, d in missing})
            name, digest = f"INCREMENT_{run}_CMP.zip", sha256(zip_bytes)
            self.inputs.put(name, zip_bytes)
            trial = f"inc-{run}-cmp"
            self.log(f"비교용 구조화: 파일 {len(missing)}개 → R6 {trial}")
            self.r6.step("submit", trial, name, digest)
            self.r6.step("wait", trial, name, digest)
            with tempfile.TemporaryDirectory(prefix="increment-cmp-") as tmp:
                generation_dir, job = self.r6.restore_generation(trial, name, digest, Path(tmp))
                found = read_generation_store(generation_dir / "store.sqlite", {e["sha256"] for e, _ in missing})
            for sha, value in found.items():
                self.store.put_gz_json(f"structured/{sha}.json.gz", value)
            self._cleanup_job(trial, job)
            self.inputs.delete(name)

        for entry, data in work:
            value = self.store.get_gz_json(f"structured/{entry['sha256']}.json.gz")
            if value is None:
                entries.append({**entry, "decision": "FAILED", "reasons": ["GENOS 구조화 결과 없음 (변환 실패 또는 제외)"]})
                continue
            try:
                new = from_structure(value["nodes"], value["blocks"], self._header(entry["file"], data))
                old = None
                if entry["members"]:
                    member = entry["members"][0]
                    old_ids = {sha256(files[m])[:16] for m in entry["members"]}
                    if len(old_ids) > 1:
                        entry.setdefault("warnings", []).append(f"팀 폴더마다 지난 판본이 다름 {sorted(old_ids)}")
                    nodes, blocks = structure(self.db, self.n, cur["generation"]["dataset_version"],
                                              sha256(files[member])[:16])
                    old = from_structure(nodes, blocks, self._header(PurePosixPath(member).name, files[member]))
            except (ParseError, ReleaseError) as exc:
                entries.append({**entry, "decision": "FAILED", "reasons": [f"비교 입력 만들기 실패: {exc}"]})
                continue
            result = compare(old, new, today=today, hold_on_strong=self.p.hold_on_strong)
            html = result.pop("preview_html")
            if html:
                self.store.put(f"runs/{run}/previews/{entry['sha256'][:16]}.html", html.encode("utf-8"))
            entries.append({**entry, **result, "warnings": entry.get("warnings", []) + result["warnings"]})

        st = history.state(self.store)
        for e in entries:
            if e["decision"] != "ALREADY":
                st.setdefault("files", {})[e["sha256"]] = {"decision": e["decision"], "run": run,
                                                           "doc_cd": e.get("doc_cd"), "path": e["path"]}
        history.save_state(self.store, st)
        summary = {}
        for e in entries:
            summary[e["decision"]] = summary.get(e["decision"], 0) + 1
        record = {"run": run, "today": today, "channel": cur["channel"],
                  "generation": {k: v for k, v in cur["generation"].items() if k != "documents"},
                  "corpus": corpus, "summary": summary, "entries": entries}
        self.store.put_json(f"runs/{run}/decide.json", record)
        return {"run": run, "summary": summary, "approved": [e["file"] for e in entries if e["decision"] == APPROVED]}

    # ---------------------------------------------------------------- publish
    def publish(self, run: str) -> dict:
        dec = self.store.get_json(f"runs/{run}/decide.json")
        if dec is None:
            raise Stop(f"DECIDE_FIRST: {run} 판단 기록 없음")
        approved = [e for e in dec["entries"] if e["decision"] == APPROVED]
        if not approved:
            return {"run": run, "state": "NOTHING_TO_PUBLISH"}
        cur = self._current()
        if cur["channel"]["query_id"] != dec["channel"]["query_id"]:
            raise Stop("CHANNEL_MOVED: 판단 뒤 서빙 세대가 바뀜 — decide부터 다시")
        corpus, files = self._corpus(cur)
        if corpus["sha256"] != dec["corpus"]["sha256"]:
            raise Stop("BASE_ZIP_CHANGED_SINCE_DECIDE")
        reps = []
        for e in approved:
            data = self.drop.get(e["path"])
            if data is None or sha256(data) != e["sha256"]:
                raise Stop(f"DROP_FILE_CHANGED: {e['path']}")
            reps.append(Replacement(doc_cd=e["doc_cd"], file_name=e["file"], data=data,
                                    header=self._header(e["file"], data), source=e.get("source", "")))
        out_files, asm = assemble_files(files, reps, as_of=dec["today"], base_sha256=corpus["sha256"])
        name = f"INCREMENT_{run}_FULL.zip"
        digest = self._put_zip(name, out_files)
        trial = f"inc-{run}-pub"
        self.log(f"전체 원문 {asm.members}개 파일(교체 {len(asm.replaced)}·추가 {len(asm.added)}) → R6 {trial}")
        for op in ("submit", "wait", "load"):
            self.r6.step(op, trial, name, digest)
        report = self.r6.report(trial, name, digest)
        if not report.get("checks") or report.get("status") not in ("DEV_LOADED", "PROD_LOADED"):
            raise Stop(f"LOAD_NOT_VERIFIED: {report.get('status')}")
        job = self.r6.job(trial, name, digest)
        self._cleanup_job(trial, job)
        record = {"run": run, "trial": trial, "job": job, "zip": {"name": name, "sha256": digest},
                  "assembly": asm.as_dict(), "report": report}
        self.store.put_json(f"runs/{run}/publish.json", record)
        return {"run": run, "state": "PUBLISHED_NOT_ACTIVE", "query_release_id": report["query_release_id"],
                "counts": report.get("counts")}

    # ---------------------------------------------------------------- activate
    def activate(self, run: str) -> dict:
        dec = self.store.get_json(f"runs/{run}/decide.json")
        pub = self.store.get_json(f"runs/{run}/publish.json")
        if pub is None:
            raise Stop(f"PUBLISH_FIRST: {run} 게시 기록 없음")
        if pub.get("activated"):
            return {"run": run, "state": "ALREADY_ACTIVE"}
        cur = self._current()
        _, base_files = self._corpus(cur)
        new_query = pub["report"]["query_release_id"]
        vector = (pub["report"].get("vector") or {}).get("publication_id") or ""
        moved = switch(self.db, self.n, channel_name=self.p.channel, expected_query=dec["channel"]["query_id"],
                       new_query=new_query, vector_post_id=vector)
        olds = {r["old_member"]: base_files[r["old_member"]] for r in pub["assembly"]["replaced"]}
        docs = [{k: e.get(k) for k in ("file", "path", "doc_cd", "name", "decision", "effective", "promulgation_no",
                                       "counts", "changes", "warnings", "old_sha256", "new_sha256")}
                for e in dec["entries"] if e["decision"] == APPROVED]
        record = history.write_update(self.store, {
            "run": run, "at": run_id(), "channel_before": moved["before"], "channel_after": moved["after"],
            "base_corpus": dec["corpus"], "new_corpus": pub["zip"], "documents": docs,
            "replaced": pub["assembly"]["replaced"], "added": pub["assembly"]["added"],
            "publish_trial": pub["trial"]}, olds)
        st = history.state(self.store)
        st["current_query"], st["corpus"] = new_query, pub["zip"]
        for e in dec["entries"]:
            if e["decision"] == APPROVED:
                st["files"][e["sha256"]] = {**st["files"].get(e["sha256"], {}), "decision": "PUBLISHED",
                                             "update": record["seq"]}
        history.save_state(self.store, st)
        pub["activated"] = record["seq"]
        self.store.put_json(f"runs/{run}/publish.json", pub)
        pruned = self.cleanup()
        return {"run": run, "state": "ACTIVE", "update": record["seq"], "channel": moved["after"],
                "prune": pruned}

    # ---------------------------------------------------------------- rollback
    def rollback(self, run: str) -> dict:
        active = [u for u in history.updates(self.store) if u.get("status") == "ACTIVE"]
        if not active:
            raise Stop("NOTHING_TO_ROLLBACK: 되돌릴 업데이트 기록 없음 (최근 3개까지만 보관)")
        u = active[-1]
        cur = channel(self.db, self.n, self.p.channel)
        if cur["query_id"] != u["channel_after"]["query_id"]:
            raise Stop("CHANNEL_NOT_AT_LATEST_UPDATE: 서빙 세대가 마지막 업데이트와 다름")
        target = u["channel_before"]["query_id"]
        current_corpus = history.state(self.store)["corpus"]
        files, _ = self._open_zip(current_corpus["name"], current_corpus.get("sha256", ""))
        files = files.copy()
        olds = history.old_files(self.store, u["seq"], u["old_files"])
        for r in u["replaced"]:
            if r["member"] != r["old_member"]:
                files.pop(r["member"], None)
            files[r["old_member"]] = olds[r["old_member"]]
        for a in u["added"]:
            files.pop(a["member"], None)
        rebuilt = self.work / (uuid.uuid4().hex + ".zip")
        rebuilt_sha = write_zip_file(files, rebuilt)
        try:
            gen = generation(self.db, self.n, target)
            if not gen.vector_post_id:
                raise ReleaseError("이전 세대 벡터 게시 없음")
            method = "CHANNEL"
        except ReleaseError:
            gen, method = None, "REBUILD"
        if method == "CHANNEL":
            moved = switch(self.db, self.n, channel_name=self.p.channel, expected_query=cur["query_id"],
                           new_query=target, vector_post_id=gen.vector_post_id)
            new_query = target
        else:
            name, digest = f"INCREMENT_{run}_ROLLBACK.zip", rebuilt_sha
            self.inputs.upload_file(name, rebuilt)
            trial = f"inc-{run}-rb"
            for op in ("submit", "wait", "load"):
                self.r6.step(op, trial, name, digest)
            report = self.r6.report(trial, name, digest)
            if not report.get("checks"):
                raise Stop("ROLLBACK_LOAD_NOT_VERIFIED")
            self._cleanup_job(trial, self.r6.job(trial, name, digest))
            new_query = report["query_release_id"]
            moved = switch(self.db, self.n, channel_name=self.p.channel, expected_query=cur["query_id"],
                           new_query=new_query, vector_post_id=report["vector"]["publication_id"])
        name = u["base_corpus"]["name"] if method == "CHANNEL" else f"INCREMENT_{run}_ROLLBACK.zip"
        if method == "CHANNEL" and (u["base_corpus"].get("sha256") != rebuilt_sha or name not in self.inputs.list(name)):
            name = f"INCREMENT_{run}_ROLLBACK.zip"
            self.inputs.upload_file(name, rebuilt)
        history.mark(self.store, u["seq"], "ROLLED_BACK", rolled_back_by=run, method=method)
        st = history.state(self.store)
        st["current_query"], st["corpus"] = new_query, {"name": name, "sha256": rebuilt_sha}
        for d in u["documents"]:
            if d.get("new_sha256") in st["files"]:
                st["files"][d["new_sha256"]]["decision"] = "ROLLED_BACK"
        history.save_state(self.store, st)
        return {"run": run, "rolled_back_update": u["seq"], "method": method, "channel": moved["after"]}

    # ---------------------------------------------------------------- cleanup
    def cleanup(self, max_batches: int | None = None) -> dict:
        st = history.state(self.store)
        for trial, job in (st.get("jobs") or {}).items():
            if not job.get("agent_cleaned"):
                self._cleanup_job(trial, job["job"])
        cur = channel(self.db, self.n, self.p.channel)
        keep = history.keep_queries(self.store, cur["query_id"], self.p.keep)
        if cur["query_id"] not in keep:
            keep = [cur["query_id"]] + keep[: self.p.keep - 1]
        plan = prune_plan(releases(self.db, self.n), keep)
        self.store.put_json("prune/last-plan.json", plan)
        done = prune(self.db, self.n, plan, batch=self.p.prune_batch, max_batches=max_batches)
        self.store.put_json("prune/last-result.json", done)
        return {"keep": keep, "removed": [r["query_id"][:16] for r in plan["remove"]],
                "protected": [q[:16] for q in plan["protected"]], "complete": done["complete"]}

    # ---------------------------------------------------------------- run
    def run(self, run: str) -> dict:
        out = {"decide": self.decide(run)}
        if out["decide"]["approved"]:
            out["publish"] = self.publish(run)
            out["activate"] = self.activate(run)
        else:
            out["cleanup"] = self.cleanup()
        return out


def r6_cfg_from_recipe(project, recipe_name: str) -> dict:
    """설치된 R6 레시피 코드의 run('...', {cfg}) 에서 설정을 읽는다 (같은 GENOS·Agent·대상)."""
    import ast
    code = project.get_recipe(recipe_name).get_settings().get_code()
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "run" and len(node.args) == 2:
            return ast.literal_eval(node.args[1])
    raise Stop(f"R6_CFG_NOT_FOUND: {recipe_name} 코드에서 설정을 찾지 못함")
