"""배치 파이프라인 — 구조 스토어 위의 파생층을 **한 번에, 빠진 것만** 채우는 딸깍.

문서는 두 문으로 들어온다: 수집(manifest)과 업로드(화면·inbox). 어느 문으로
왔든 구조화(①)까지는 그 자리에서 끝나지만, 그 뒤 층(위임·용어·프레임·벡터)은
따로 돌려야 했고, 그래서 "반만 들어간" 문서가 생겼다(2026-08-19 실측: 67문서
중 25문서 벡터 없음, 10문서 프레임 없음, KOFIA 규정 71건 수집만 되고 미투입).
이 모듈은 그 단계들을 **한 줄로 세우고**, 단계마다 "무엇이 빠졌나"를 세어
(라인업) 빠진 것만 돌린다(증분). 진행은 파일(state.json)로 밖에서 보인다.

    단계        무엇                                     누가        증분 단위
    ingest      manifest 미투입 + data/inbox/ 파일 → 스토어  결정론      문서
    structure   result.json·점수·격리 요약 (검사만)          검사        —
    delegation  lsDelegated → delegation.json (법령만)        결정론      전체(원본이 새로울 때)
    terms       정의조항·괄호별칭 → glossary 잠정             결정론      전체(멱등)
    frames      조 → 주체·행위·객체 프레임 (→ 조문 카드)       LLM         조
    embed       구역 벡터                                    임베딩 모델  구역(sha1)
    scopes      scopes.yml 이름 해석 점검 (검사만)             검사        —

규율:
- **덮어쓰지 않는다** — 모든 단계가 기존 모듈의 증분 경로를 부른다(재실행 멱등).
- 모델(LLM·임베딩)이 없으면 그 단계는 **건너뛰고 이유를 남긴다** — 실패가 아니다.
  폐쇄망에서 임베딩 서빙만 있고 LLM 이 없을 수 있다.
- 한 번에 한 실행 — 두 번째 딸깍은 409. 중지는 단계 사이·문서 사이에서 듣는다.
- 상태는 data/pipeline/state.json(현재·마지막 실행) + runs/<id>.jsonl(사건 로그).
  서버가 죽어도 마지막 상태가 남고, 다음 실행은 라인업을 다시 세므로 이어진다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("lawrag.core.batch")

ROOT = Path(__file__).resolve().parent.parent.parent

STAGES = ("ingest", "structure", "delegation", "terms", "frames", "embed", "scopes")
LABELS = {"ingest": "투입", "structure": "구조 점검", "delegation": "위임 간선",
          "terms": "용어 전사", "frames": "프레임", "embed": "벡터", "scopes": "스코프 점검"}
KIND = {"ingest": "결정론", "structure": "검사", "delegation": "결정론", "terms": "결정론",
        "frames": "LLM", "embed": "임베딩", "scopes": "검사"}

# 수집 출처 → 스토어 폴더 라벨. manifest 의 kind 는 item 이 이미 들고 있다.
SOURCE_FOLDER = {"law": "법령·규정", "krx": "상장규정", "kofia": "협회규정"}
INBOX_EXTS = (".xml", ".html", ".htm", ".hwp", ".hwpx", ".docx", ".pdf")


# ------------------------------------------------------------------ 경로
def store_path() -> Path:
    return Path(os.environ.get("STRUCTURE_STORE", ROOT / "data" / "structure"))


def corpus_path() -> Path:
    return Path(os.environ.get("CORPUS_DIR", ROOT / "data" / "corpus"))


def pipeline_dir() -> Path:
    return Path(os.environ.get("PIPELINE_DIR", store_path().parent / "pipeline"))


def inbox_path() -> Path:
    return Path(os.environ.get("PIPELINE_INBOX", store_path().parent / "inbox"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store_docs() -> dict[str, dict]:
    out = {}
    st = store_path()
    if not st.exists():
        return out
    for d in sorted(st.iterdir()):
        mj, rj = d / "meta.json", d / "result.json"
        if mj.exists() and rj.exists():
            try:
                out[d.name] = json.loads(mj.read_text(encoding="utf-8"))
            except Exception:
                continue
    return out


# ------------------------------------------------------------------ ingest
def _manifest_items(source: str) -> list[dict]:
    p = corpus_path() / source / "manifest.json"
    if not p.exists():
        return []
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return m["items"] if isinstance(m, dict) else list(m)


def _body_path(source: str, item: dict) -> Optional[Path]:
    """manifest 항목의 구조화 본문 파일 — law 는 XML, krx/kofia 는 조문 HTML."""
    if source == "law":
        body = item.get("body_file")
        if not body:
            body = next((a["file"] for a in item.get("attachments", [])
                         if a.get("role") == "body"
                         and str(a.get("file", "")).endswith(".xml")), None)
    elif source in ("krx", "kofia"):
        body = item.get("body_html_file")
    else:
        body = item.get("body_file")
    if not body:
        return None
    p = Path(body)
    return p if p.is_absolute() else ROOT / p


def _manifest_sources() -> list[str]:
    """corpus/<source>/manifest.json 이 있는 출처 — 수명주기가 다른 것(해석례류,
    phase_model 선언)은 뺀다. law·krx·kofia 가 앞, 나머지(forms·internal·uploads…)는 뒤."""
    c = corpus_path()
    if not c.is_dir():
        return []
    out = []
    for p in sorted(c.glob("*/manifest.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(m, dict) and m.get("phase_model"):
            continue
        out.append(p.parent.name)
    head = [s for s in ("law", "krx", "kofia") if s in out]
    return head + [s for s in out if s not in head]


def ingest_targets() -> list[dict]:
    """투입 후보 전부 — corpus 의 모든 출처 manifest + inbox. 각각 in_store 표시.
    law 는 XML 문, krx·kofia 는 조문 HTML 문, 그 밖(forms·internal·uploads·…)은
    파일 형식대로 일반 문(내규 폴더·kind=internal 은 내규 문)."""
    out: list[dict] = []
    st = store_path()
    for source in _manifest_sources():
        for it in _manifest_items(source):
            # partial 은 첨부(별표서식)가 덜 온 것이지 본문이 없는 게 아니다 — 본문이
            # 있으면 투입한다. 실패(error 등)만 건너뛴다.
            if it.get("status") not in (None, "ok", "partial"):
                continue
            p = _body_path(source, it)
            if p is None or not p.exists():
                continue
            doc_id = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            via = source if source in ("law", "krx", "kofia") else "file"
            folder = it.get("folder") or SOURCE_FOLDER.get(source) or source
            out.append({"via": via, "source": source,
                        "name": it.get("name") or it.get("label") or p.stem,
                        "path": str(p), "kind": it.get("kind"), "doc_id": doc_id,
                        "in_store": (st / doc_id / "result.json").exists(),
                        "folder": folder, "item": it})
    inbox = inbox_path()
    if inbox.exists():
        for p in sorted(inbox.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in INBOX_EXTS:
                continue
            if "_done" in p.relative_to(inbox).parts:
                continue
            folder = p.relative_to(inbox).parts[0] if len(p.relative_to(inbox).parts) > 1 else ""
            doc_id = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            out.append({"via": "inbox", "name": p.stem, "path": str(p), "kind": None,
                        "doc_id": doc_id, "in_store": (st / doc_id / "result.json").exists(),
                        "folder": folder, "item": None})
    return out


def _ingest_one(t: dict) -> dict:
    from lawrag.core import ingest as ingest_mod
    from lawrag.core import internal_rules
    p = Path(t["path"])
    raw = p.read_bytes()
    st = store_path()
    if t["via"] == "law":
        it = t["item"]
        extra = {k: v for k, v in {
            "kind": it.get("kind"), "enforce": it.get("enforce"), "revised": it.get("revised"),
            "promul_no": it.get("promul_no"), "dept": it.get("dept"),
            "law_serial": it.get("doc_no")}.items() if v}
        r = ingest_mod.ingest_lawxml_bytes(raw, t["name"], st, t["folder"],
                                           extra_meta=extra, manifest_item=it)
        return {"doc_id": r["doc_id"]}
    if t["via"] in ("krx", "kofia"):
        it = t["item"]
        extra = {k: v for k, v in {"kind": it.get("kind"), "enforce": it.get("enforce"),
                                   "revised": it.get("revised"), "dept": it.get("dept")}.items() if v}
        r = ingest_mod.ingest_rulehtml_bytes(raw, t["name"], st, t["folder"],
                                             extra_meta=extra, site=t["via"])
        return {"doc_id": r["doc_id"]}
    # 일반 파일 — manifest(forms·internal·uploads…) 또는 inbox
    it = t.get("item") or {}
    name = it.get("name") or p.stem
    is_internal = (t["folder"] == internal_rules.FOLDER
                   or (it.get("kind") == internal_rules.KIND))
    if is_internal:
        r = internal_rules.ingest_internal_rule(
            raw, p.name, store=st, name=name, folder=internal_rules.FOLDER,
            status=it.get("status_label") or "현행", series=it.get("series") or "",
            version=it.get("version") or "")
    else:
        extra = {k: it.get(k) for k in ("kind", "enforce", "revised", "source") if it.get(k)}
        r = ingest_mod.ingest(raw, p.name, store=st, name=name, folder=t["folder"],
                              extra_meta=extra or None,
                              raw_via="inbox" if t["via"] == "inbox" else "manifest")
    if t["via"] == "inbox":
        # inbox 원본은 raw 등록(ingest 안 ensure)으로 corpus/uploads 에 사본이 남았다 —
        # 처리한 파일은 _done/ 으로 옮겨 다음 실행이 다시 집지 않게 한다.
        done = inbox_path() / "_done" / (t["folder"] or "_")
        done.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(done / p.name))
    return {"doc_id": r["doc_id"]}


# ------------------------------------------------------------------ 라인업 (단계별 세기)
def lineup() -> dict:
    """각 단계의 '빠진 것' — 돌리기 전에 보는 표. 모델을 부르지 않는다."""
    docs = _store_docs()
    out: dict = {"at": _now(), "documents": len(docs), "stages": {}}

    # ingest
    tg = ingest_targets()
    pend = [t for t in tg if not t["in_store"]]
    out["stages"]["ingest"] = {
        "pending": len(pend), "total": len(tg),
        "detail": [{"name": t["name"], "via": t["via"], "folder": t["folder"], "kind": t["kind"]}
                   for t in pend],
        "note": " · ".join(f"{v} {n}" for v, n in sorted(
            {v: sum(1 for t in pend if t["via"] == v) for v in {t["via"] for t in pend}}.items()))
                or "미투입 없음"}

    # structure — 검사
    low = [m for m in docs.values() if not m.get("passed", True) or (m.get("score") or 1) < 0.70]
    by_folder: dict[str, int] = {}
    for m in docs.values():
        by_folder[m.get("folder") or "∅"] = by_folder.get(m.get("folder") or "∅", 0) + 1
    out["stages"]["structure"] = {
        "pending": len(low), "total": len(docs),
        "detail": [{"name": m.get("name"), "score": m.get("score"), "tier": m.get("tier")} for m in low],
        "note": " · ".join(f"{k} {v}" for k, v in sorted(by_folder.items(), key=lambda x: -x[1]))
                + (f" · 격리(0.70 미만) {len(low)}" if low else "")}

    # delegation — 원본(relations)·법령 문서가 delegation.json 보다 새로우면 1
    deleg = store_path().parent / "delegation.json"
    rel = corpus_path() / "law" / "relations"
    newest = 0
    if rel.exists():
        newest = max((p.stat().st_mtime for p in rel.glob("*.xml")), default=0)
    law_newest = max((datetime.fromisoformat(m["at"].replace("Z", "+00:00")).timestamp()
                      for m in docs.values() if m.get("kind") in ("law", "admrul") and m.get("at")),
                     default=0)
    have = deleg.stat().st_mtime if deleg.exists() else 0
    n_edges = 0
    if deleg.exists():
        try:
            n_edges = len(json.loads(deleg.read_text(encoding="utf-8")).get("edges", []))
        except Exception:
            n_edges = 0
    stale = (not deleg.exists()) or newest > have or law_newest > have
    out["stages"]["delegation"] = {
        "pending": 1 if stale else 0, "total": 1,
        "detail": [], "note": f"간선 {n_edges:,}" + (" · 원본·법령이 더 새롭다 → 재생성" if stale else " · 최신")}

    # terms — 용어 출현이 하나도 없는 문서
    gpath = store_path().parent / "glossary.json"
    covered: set = set()
    n_terms = 0
    if gpath.exists():
        try:
            terms = json.loads(gpath.read_text(encoding="utf-8")).get("terms", [])
            n_terms = len(terms)
            for t in terms:
                for o in t.get("occurrences", []):
                    covered.add(o.get("doc_id"))
        except Exception:
            pass
    uncovered = [m for d, m in docs.items() if d not in covered]
    out["stages"]["terms"] = {
        "pending": len(uncovered), "total": len(docs),
        "detail": [{"name": m.get("name")} for m in uncovered],
        "note": f"용어 {n_terms} · 출현 문서 {len(covered)}/{len(docs)} (전사는 멱등 — 전체 재훑기)"}

    # frames — 본칙 조 중 아직 안 뽑힌 조
    try:
        from lawrag.core.rag import frames as frames_mod
        from lawrag.core.rag.index import DocView
        fdir = frames_mod.frames_dir()
        pend_docs = []
        tot_jos = pend_jos = 0
        for d, m in docs.items():
            try:
                res = json.loads((store_path() / d / "result.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            v = DocView.build(d, m, res)
            jos = frames_mod._mainbody_jos(v)
            done: set = set()
            fp = fdir / f"{d}.jsonl"
            if fp.is_file():
                for line in fp.read_text("utf-8").splitlines():
                    try:
                        done.add(json.loads(line)["jo"])
                    except Exception:
                        pass
            n_p = sum(1 for j in jos if j["id"] not in done)
            tot_jos += len(jos)
            pend_jos += n_p
            if n_p:
                pend_docs.append({"name": m.get("name"), "doc_id": d, "jos": len(jos), "pending": n_p})
        out["stages"]["frames"] = {
            "pending": len(pend_docs), "total": len(docs), "units": {"total": tot_jos, "pending": pend_jos},
            "detail": pend_docs,
            "note": f"본칙 조 {tot_jos:,} 중 미추출 {pend_jos:,} (문서 {len(pend_docs)}) · 조당 LLM 1콜"}
    except Exception as exc:                                 # pragma: no cover
        out["stages"]["frames"] = {"pending": 0, "total": len(docs), "detail": [],
                                   "note": f"세지 못함: {exc}"}

    # embed
    try:
        from lawrag.core.terms import embed_sections
        plan = embed_sections.plan()
        out["stages"]["embed"] = {
            "pending": len(plan["docs_pending"]), "total": len(docs),
            "units": {"total": plan["sections"], "fresh": plan["fresh"]},
            "detail": [{"name": x["name"], "doc_id": d, "fresh": x["fresh"]}
                       for d, x in plan["docs_pending"].items()],
            "note": f"구역 {plan['sections']:,} 중 새 임베딩 {plan['fresh']:,} (문서 {len(plan['docs_pending'])})"}
    except Exception as exc:                                 # pragma: no cover
        out["stages"]["embed"] = {"pending": 0, "total": len(docs), "detail": [],
                                  "note": f"세지 못함: {exc}"}

    # scopes
    try:
        from lawrag.core.rag import index as index_mod, scopes as scopes_mod
        rows = scopes_mod.listing(index_mod.current())
        miss = [r for r in rows if r.get("missing")]
        out["stages"]["scopes"] = {
            "pending": len(miss), "total": len(rows),
            "detail": [{"name": r["name"], "missing": r["missing"]} for r in miss],
            "note": f"스코프 {len(rows)}" + (f" · 못 찾은 이름 있는 스코프 {len(miss)}" if miss else " · 전부 해석됨")}
    except Exception as exc:                                 # pragma: no cover
        out["stages"]["scopes"] = {"pending": 0, "total": 0, "detail": [], "note": f"세지 못함: {exc}"}

    # 모델 가용성 — 건너뛸 단계를 미리 알린다
    try:
        from lawrag.core import llm as llm_mod
        llm_mod.load_env()
        out["llm"] = bool(llm_mod.available())
    except Exception:
        out["llm"] = False
    try:
        from lawrag.core import embedding
        out["embedding"] = bool(embedding.available())
    except Exception:
        out["embedding"] = False
    return out


# ------------------------------------------------------------------ 실행기
class Runner:
    """한 번에 하나만 도는 배치 실행기 — 상태는 파일, 진행은 콜백."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._state: dict = {}
        self._last_write = 0.0
        self._log_fh = None

    # ---- 상태 파일
    def _state_path(self) -> Path:
        return pipeline_dir() / "state.json"

    def _write(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_write < 0.5:
            return
        self._last_write = now
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)

    def _event(self, kind: str, **kw) -> None:
        rec = {"ts": _now(), "kind": kind, **kw}
        if self._log_fh is not None:
            self._log_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._log_fh.flush()

    def _stop_file(self) -> Path:
        return pipeline_dir() / "STOP"

    def _stop_requested(self) -> bool:
        return self._stop.is_set() or self._stop_file().exists()

    def status(self) -> dict:
        if self._state and self.is_running():
            return dict(self._state, running=True, owner="this-process")
        p = self._state_path()
        if p.exists():
            try:
                st = json.loads(p.read_text(encoding="utf-8"))
                # 다른 프로세스(CLI)가 돌리는 중이면 상태 파일이 계속 갱신된다 —
                # status=running 이고 파일이 최근(60초)이면 살아 있는 것으로 본다.
                fresh = (time.time() - p.stat().st_mtime) < 60
                running = st.get("status") == "running" and fresh
                if st.get("status") == "running" and not fresh:
                    st["stale"] = True          # 죽은 실행 — 화면이 "끊김"으로 보인다
                return dict(st, running=running, owner="other-process" if running else None)
            except Exception:
                pass
        if self._state:
            return dict(self._state, running=False)
        return {"status": "idle", "running": False}

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def runs(self, limit: int = 20) -> list[dict]:
        d = pipeline_dir() / "runs"
        if not d.exists():
            return []
        out = []
        for p in sorted(d.glob("*.json"), reverse=True)[:limit]:
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out

    def log_tail(self, run_id: str, n: int = 200) -> list[dict]:
        p = pipeline_dir() / "runs" / f"{run_id}.jsonl"
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()[-n:]
        out = []
        for l in lines:
            try:
                out.append(json.loads(l))
            except Exception:
                continue
        return out

    # ---- 시작·중지
    def start(self, stages: Optional[list[str]] = None, opts: Optional[dict] = None) -> dict:
        with self._lock:
            if self.is_running():
                raise RuntimeError("이미 실행 중입니다 — 끝나거나 중지한 뒤 다시 누르세요")
            want = [s for s in (stages or list(STAGES)) if s in STAGES]
            if not want:
                raise ValueError(f"모르는 단계입니다: {stages}")
            want.sort(key=STAGES.index)
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
            self._stop.clear()
            try:
                self._stop_file().unlink(missing_ok=True)
            except Exception:
                pass
            self._state = {
                "run_id": run_id, "status": "running", "started": _now(), "finished": None,
                "requested": want, "opts": opts or {},
                "stages": {s: {"status": "queued" if s in want else "skipped",
                               "done": 0, "total": 0, "current": "", "note": "",
                               "errors": [], "started": None, "finished": None, "result": None,
                               "docs": []}          # 문서 단위 기록 — 화면의 문서별 표
                           for s in STAGES}}
            self._write(force=True)
            (pipeline_dir() / "runs").mkdir(parents=True, exist_ok=True)
            self._log_fh = (pipeline_dir() / "runs" / f"{run_id}.jsonl").open("a", encoding="utf-8")
            self._event("start", stages=want, opts=opts or {})
            self._thread = threading.Thread(target=self._run, args=(want, opts or {}),
                                            name=f"batch-{run_id}", daemon=True)
            self._thread.start()
            return {"run_id": run_id, "stages": want}

    def stop(self) -> dict:
        """중지 요청 — 이 프로세스의 실행이면 이벤트, 다른 프로세스(CLI)면 STOP 파일."""
        self._stop.set()
        try:
            self._stop_file().parent.mkdir(parents=True, exist_ok=True)
            self._stop_file().write_text(_now(), encoding="utf-8")
        except Exception:
            pass
        return {"stopping": bool(self.status().get("running"))}

    # ---- 본체
    def _stage(self, name: str) -> dict:
        return self._state["stages"][name]

    def _doc(self, name: str, **row) -> None:
        """문서 단위 기록 한 줄 — 상태(표)와 사건 로그(jsonl) 둘 다에 남긴다."""
        row = {"ts": _now(), **row}
        docs = self._stage(name)["docs"]
        docs.append(row)
        if len(docs) > 2000:                         # 상태 파일 폭주 방지 — 로그에는 전부 있다
            del docs[: len(docs) - 2000]
        # 사건 기록의 "kind" 는 사건 종류다 — 문서의 kind 는 doc_kind 로 옮겨 적는다
        ev = {("doc_kind" if k == "kind" else k): v for k, v in row.items() if k != "ts"}
        self._event(f"{name}_doc", stage=name, **ev)
        self._write()

    def _progress(self, name: str, done: int, total: int, current: str = "", note: str = "") -> None:
        st = self._stage(name)
        st["done"], st["total"] = done, total
        if current:
            st["current"] = current
        if note:
            st["note"] = note
        self._write()

    def _run(self, want: list[str], opts: dict) -> None:
        try:
            for name in want:
                if self._stop_requested():
                    self._stage(name)["status"] = "stopped"
                    continue
                st = self._stage(name)
                st["status"], st["started"] = "running", _now()
                self._write(force=True)
                self._event("stage_start", stage=name)
                try:
                    res = getattr(self, f"_run_{name}")(opts)
                    st["result"] = res
                    if st["status"] == "running":
                        st["status"] = "stopped" if self._stop_requested() and res.get("stopped") else \
                            ("skipped" if res.get("skipped") else "done")
                    if res.get("note"):
                        st["note"] = res["note"]
                except Exception as exc:
                    st["status"] = "failed"
                    st["errors"].append(f"{type(exc).__name__}: {exc}")
                    log.exception("배치 단계 실패 — %s", name)
                    self._event("stage_error", stage=name, error=str(exc),
                                trace=traceback.format_exc()[-2000:])
                st["finished"] = _now()
                self._write(force=True)
                self._event("stage_end", stage=name, status=st["status"], result=st.get("result"))
            self._state["status"] = "stopped" if self._stop_requested() else (
                "failed" if any(s["status"] == "failed" for s in self._state["stages"].values())
                else "done")
        except Exception as exc:                                   # pragma: no cover
            self._state["status"] = "failed"
            self._state["error"] = f"{type(exc).__name__}: {exc}"
            log.exception("배치 실행 실패")
        finally:
            self._state["finished"] = _now()
            self._write(force=True)
            self._event("end", status=self._state["status"])
            # 실행 요약을 runs/<id>.json 으로 — 이력 목록이 읽는다
            try:
                summ = {k: v for k, v in self._state.items()}
                (pipeline_dir() / "runs" / f"{self._state['run_id']}.json").write_text(
                    json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:
                pass
            if self._log_fh is not None:
                self._log_fh.close()
                self._log_fh = None

    # ---- 단계들
    def _run_ingest(self, opts: dict) -> dict:
        targets = [t for t in ingest_targets() if not t["in_store"]]
        n_ok = n_fail = 0
        fails: list[dict] = []
        self._progress("ingest", 0, len(targets), note=f"미투입 {len(targets)}")
        for i, t in enumerate(targets, 1):
            if self._stop_requested():
                return {"ok": n_ok, "failed": n_fail, "stopped": True, "fails": fails}
            self._progress("ingest", i - 1, len(targets), current=f"{t['via']} · {t['name']}")
            t0 = time.perf_counter()
            try:
                r = _ingest_one(t)
                n_ok += 1
                meta = {}
                try:
                    meta = json.loads((store_path() / r["doc_id"] / "meta.json").read_text(encoding="utf-8"))
                except Exception:
                    pass
                self._doc("ingest", doc=t["name"], doc_id=r.get("doc_id"), via=t["via"],
                          source=t.get("source"), folder=t["folder"], kind=meta.get("kind") or t.get("kind"),
                          ok=True, score=meta.get("score"), tier=meta.get("tier"),
                          structured_by=meta.get("structured_by"), pages=meta.get("pages"),
                          sec=round(time.perf_counter() - t0, 1))
            except Exception as exc:
                n_fail += 1
                err = f"{type(exc).__name__}: {exc}"[:300]
                fails.append({"name": t["name"], "via": t["via"], "error": err})
                self._stage("ingest")["errors"].append(f"{t['name']}: {err}")
                self._doc("ingest", doc=t["name"], doc_id=t.get("doc_id"), via=t["via"],
                          source=t.get("source"), folder=t["folder"], ok=False, error=err,
                          sec=round(time.perf_counter() - t0, 1))
        self._progress("ingest", len(targets), len(targets), current="")
        return {"ok": n_ok, "failed": n_fail, "fails": fails,
                "note": f"투입 {n_ok} · 실패 {n_fail}" if targets else "미투입 없음"}

    def _run_structure(self, opts: dict) -> dict:
        docs = _store_docs()
        low = 0
        for did, m in sorted(docs.items(), key=lambda x: (x[1].get("folder") or "", x[1].get("name") or "")):
            bad = (not m.get("passed", True)) or ((m.get("score") or 1) < 0.70)
            low += bad
            self._doc("structure", doc=m.get("name"), doc_id=did, folder=m.get("folder"),
                      kind=m.get("kind"), score=m.get("score"), tier=m.get("tier"),
                      structured_by=m.get("structured_by"), quarantined=bad)
        lu = lineup()["stages"]["structure"]
        self._progress("structure", lu["total"], lu["total"], note=lu["note"])
        return {"documents": len(docs), "quarantined": low, "note": lu["note"]}

    def _run_delegation(self, opts: dict) -> dict:
        lu = lineup()["stages"]["delegation"]
        if not lu["pending"] and not opts.get("force"):
            self._progress("delegation", 1, 1, note=lu["note"])
            return {"skipped": True, "note": lu["note"] + " — 건너뜀"}
        rel = corpus_path() / "law" / "relations"
        if not rel.exists():
            return {"skipped": True, "note": "corpus/law/relations 없음 — 폐쇄망이면 delegation.json 을 그대로 쓴다"}
        from lawrag.core import lawnet
        self._progress("delegation", 0, 1, current="lsDelegated 전사")
        rc = lawnet.main(["--corpus", str(corpus_path()), "--store", str(store_path())])
        self._progress("delegation", 1, 1, current="")
        after = lineup()["stages"]["delegation"]["note"]
        return {"rc": rc, "note": after}

    def _run_terms(self, opts: dict) -> dict:
        from lawrag.core.terms import transcribe
        self._progress("terms", 0, 2, current="정의조항·괄호별칭 전사")
        rows = transcribe.extract(store_path())
        if self._stop_requested():
            return {"stopped": True}
        self._progress("terms", 1, 2, current=f"등재 {len(rows)}")
        rep = transcribe.register(rows)
        per: dict = {}
        for r in rows:
            per.setdefault(r.get("doc_id"), {"doc": r.get("doc"), "n": 0})["n"] += 1
        for did, x in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
            self._doc("terms", doc=x["doc"], doc_id=did, terms=x["n"])
        self._progress("terms", 2, 2, current="")
        return {"rows": len(rows), "added": len(rep.get("added", [])),
                "updated": len(rep.get("updated", [])), "conflicts": len(rep.get("conflicts", [])),
                "note": f"전사 {len(rows)} · 신규 {len(rep.get('added', []))} · 갱신 {len(rep.get('updated', []))} (잠정 — 승인은 /glossary)"}

    def _run_frames(self, opts: dict) -> dict:
        from lawrag.core import llm as llm_mod
        llm_mod.load_env()
        if not llm_mod.available():
            return {"skipped": True, "note": f"LLM 없음 — 건너뜀 ({llm_mod.MISSING_HINT})"}
        from lawrag.core.llm import LLM
        from lawrag.core.rag import frames as frames_mod
        from lawrag.core.rag.index import DocView
        lu = lineup()["stages"]["frames"]
        pend = lu["detail"]
        total_jos = sum(d["pending"] for d in pend)
        done_jos = 0
        self._progress("frames", 0, total_jos, note=f"문서 {len(pend)} · 조 {total_jos:,}")
        docs = _store_docs()
        stats_all = {"docs": 0, "frames": 0, "errors": 0}
        workers = int(opts.get("workers") or frames_mod.WORKERS)
        for d in pend:
            if self._stop_requested():
                return {"stopped": True, **stats_all}
            did = d["doc_id"]
            try:
                res = json.loads((store_path() / did / "result.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            v = DocView.build(did, docs[did], res)
            self._progress("frames", done_jos, total_jos, current=f"{v.name} ({d['pending']}조)")
            st = frames_mod.extract_doc(v, LLM, workers=workers, only_missing=True)
            done_jos += d["pending"]
            stats_all["docs"] += 1
            stats_all["frames"] += st.get("frames", 0)
            stats_all["errors"] += st.get("errors", 0)
            self._doc("frames", doc=v.name, doc_id=did, **{k: st.get(k) for k in ("jos", "frames", "errors", "sec")})
            self._progress("frames", done_jos, total_jos)
        self._progress("frames", total_jos, total_jos, current="")
        return {**stats_all, "note": f"문서 {stats_all['docs']} · 프레임 {stats_all['frames']:,} · 실패 조 {stats_all['errors']}"}

    def _run_embed(self, opts: dict) -> dict:
        from lawrag.core import embedding
        if not embedding.available():
            return {"skipped": True, "note": "임베딩 모델 없음 — 건너뜀 (EMBED_MODEL 또는 GENOS_EMBED_URL)"}
        from lawrag.core.terms import embed_sections
        plan = embed_sections.plan()
        if not plan["fresh"]:
            self._progress("embed", 0, 0, note="새 구역 없음")
            return {"skipped": True, "note": f"구역 {plan['sections']:,} 전부 최신 — 건너뜀"}
        self._progress("embed", 0, plan["fresh"], current=f"새 구역 {plan['fresh']:,} 임베딩")
        for did, x in sorted(plan["docs_pending"].items(), key=lambda kv: -kv[1]["fresh"]):
            self._doc("embed", doc=x["name"], doc_id=did, fresh=x["fresh"], sections=x["sections"])
        t0 = time.perf_counter()

        def prog(done, total):
            if self._stop_requested():
                raise InterruptedError("중지 요청")
            self._progress("embed", done, total,
                           current=f"{done:,}/{total:,} · {done / max(time.perf_counter() - t0, 1e-6):.1f}구역/s")
            self._event("embed_chunk", done=done, total=total,
                        sec=round(time.perf_counter() - t0, 1))
        try:
            rep = embed_sections.run(store_path(), progress=prog, chunk=int(opts.get("chunk") or 256))
        except InterruptedError:
            return {"stopped": True, "note": "중지 — 벡터 파일은 건드리지 않았다(다음 실행이 이어서)"}
        self._progress("embed", plan["fresh"], plan["fresh"], current="")
        return {**rep, "note": f"구역 {rep['sections']:,} · 새 임베딩 {rep['fresh']:,}"}

    def _run_scopes(self, opts: dict) -> dict:
        lu = lineup()["stages"]["scopes"]
        self._progress("scopes", lu["total"], lu["total"], note=lu["note"])
        return {"scopes": lu["total"], "with_missing": lu["pending"], "detail": lu["detail"],
                "note": lu["note"]}


RUNNER = Runner()
