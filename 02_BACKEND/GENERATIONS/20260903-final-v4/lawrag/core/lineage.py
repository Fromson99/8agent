"""계보 원장 — 수집→변환→구조화→연결을 문서 단위로 관통하는 파생 뷰.

설계는 docs/LINEAGE.md. 요지 셋:
- 원장은 파생이다. 각 단계의 자기 기록(수집 manifest · 변환 사이드카 ·
  구조화 meta.json · 연결 links.json)을 요청 때마다 조인해 계산할 뿐,
  따로 기록하지 않는다. 파생이면 늦을 수는 있어도 틀리지 않는다.
- 조인 키는 본문 sha256 이다. 구조화 스토어의 doc_id 가 본문 바이트
  sha256 앞 16자리라서(ingest_lawxml·업로드 공통) manifest 의
  body_sha256[:16] 과 결정적으로 이어진다. 이름 매칭은 쓰지 않는다.
- 낙차는 정직하게. 수집됐는데 구조화 안 된 것, 수집 밖 유입(업로드),
  재수집으로 낡은 것을 전부 그대로 드러낸다.

경로는 인자로 받는다 — env 해석은 호출부(라우터)가 한 번만 한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.platform.paths import data_path


def corpus_dir() -> Path:
    """수집 루트 — lawrag/pipeline/collect.py 와 같은 저장소 data/corpus/ 가 기본, CORPUS_DIR 는 테스트용."""
    return Path(os.environ.get("CORPUS_DIR") or data_path("corpus"))


def body_of(item: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """manifest 항목의 본문 (sha256, file, format) — 두 세대 정규화.

    신형은 항목 수준 body_sha256·body_file·body_format, 구형(law 초기분)은
    attachments 안의 role=body 첨부다. 둘 다 없으면 본문 미확보 — 수집이
    partial 로 끝난 항목이 실제로 있다.
    """
    if item.get("body_sha256"):
        return item["body_sha256"], item.get("body_file"), item.get("body_format")
    for a in item.get("attachments", []):
        if a.get("role") == "body" and a.get("sha256"):
            return a["sha256"], a.get("file"), a.get("actual_format")
    return None, None, None


# 형식 → 경로 선언 — 일원화의 자리. 구조화까지 가는 로직은 형식마다 다르다
# (XML 은 태그에서 결정적 이관, hwp 는 md 사이드카를 거치고, PDF·DOCX 는
# 업로드 해석 직행). 그래도 원장이 보는 단계 모델은 하나다:
#     수집 → (변환) → 구조화 → 연결(말뭉치 국면)
# 형식은 여기서 자기 경로만 선언한다 — 변환을 요구하는지, 구조화로 어느
# 길을 타는지. 새 형식이 오면 이 표에 한 줄이 늘 뿐 단계 모델·조인 키·
# 화면은 그대로다. 선언은 형식 단위다 — 문서별 상수는 금지.
ROUTES: dict[str, dict] = {
    "xml":  {"convert": False, "via": "lawxml 결정적 이관 — lawrag/pipeline/ingest_lawxml.py"},
    "html": {"convert": False, "via": "조문 HTML 결정적 이관 — rulehtml (KRX·KOFIA)"},
    "hwp":  {"convert": True,  "via": "md 사이드카(lawrag/core/hwp5_md.py) → 구조화"},
    "pdf":  {"convert": False, "via": "업로드 해석 직행 — POST /v1/structure/documents"},
    "docx": {"convert": False, "via": "업로드 해석 직행 — POST /v1/structure/documents"},
}


def route_of(fmt: Optional[str]) -> tuple[Optional[str], dict]:
    """형식 문자열('hwp5(ole)'·'xml'…) → (계열, 경로 선언).

    미선언 형식은 변환 없음으로 두되 계열 None 으로 그대로 보인다 —
    조용히 아는 척하지 않는다."""
    if fmt:
        for family, route in ROUTES.items():
            if fmt.startswith(family):
                return family, route
    return None, {"convert": False, "via": "경로 미선언 형식"}


def _needs_convert(fmt: Optional[str]) -> bool:
    return route_of(fmt)[1]["convert"]


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _store_metas(store: Path) -> dict[str, dict]:
    """구조화 스토어의 {doc_id: meta}. meta.json 없는 디렉토리는 문서가 아니다."""
    out: dict[str, dict] = {}
    if not store.is_dir():
        return out
    for d in store.iterdir():
        if d.is_dir():
            meta = _read_json(d / "meta.json")
            if meta is not None:
                out[d.name] = meta
    return out


def _edge_counts(links: Optional[dict]) -> tuple[dict[str, int], dict[str, int]]:
    outc: dict[str, int] = {}
    inc: dict[str, int] = {}
    for e in (links or {}).get("links", []):
        outc[e.get("src_doc")] = outc.get(e.get("src_doc"), 0) + 1
        inc[e.get("dst_doc")] = inc.get(e.get("dst_doc"), 0) + 1
    return outc, inc


def _manifest_root(corpus: Path) -> Path:
    """manifest 의 `file`/`body_file` 은 **저장소 뿌리** 상대 경로다. 코퍼스가
    data/corpus/ 에 살면 뿌리는 두 단계 위고, 시험처럼 임의 폴더의 corpus/ 면
    그 부모다."""
    c = corpus.resolve()
    if c.name == "corpus" and c.parent.name == "data":
        return c.parent.parent
    return c.parent


def build(store: Path, links_file: Path, corpus: Optional[Path] = None) -> dict:
    """원장 전체 — 문서별 계보(items) · 고아(extras) · 연결 국면(links)."""
    corpus = corpus or corpus_dir()
    root = _manifest_root(corpus)
    metas = _store_metas(store)
    links = _read_json(links_file)
    out_edges, in_edges = _edge_counts(links)

    items: list[dict] = []
    used: set[str] = set()
    names: dict[str, tuple[str, str]] = {}   # 항목 이름 → (출처, 이름) — 낡음 판정용
    if corpus.is_dir():
        for src_dir in sorted(corpus.iterdir()):
            manifest = _read_json(src_dir / "manifest.json")
            if manifest is None:
                continue
            # 다른 수명주기를 선언한 코퍼스(해석례: 수집→색인→위키)는 이 원장의
            # 단계 모델(수집→변환→구조화→연결) 밖이다 — 낙차로 세지 않는다.
            if manifest.get("phase_model"):
                continue
            source = src_dir.name
            for item in manifest.get("items", []):
                sha, body_file, fmt = body_of(item)
                doc_id = sha[:16] if sha else None
                names[item.get("name", "")] = (source, item.get("name", ""))

                collected = {"done": bool(doc_id) and item.get("status") == "ok",
                             "status": item.get("status")}

                family, route = route_of(fmt)
                need = route["convert"]
                converted: dict = {"required": need}
                if need and body_file:
                    # manifest 의 file 은 저장소 루트 기준 상대경로(data/corpus/…)다.
                    sidecar = root / (body_file + ".md")
                    converted["done"] = sidecar.exists()
                # 별표서식 hwp 첨부의 사이드카는 개수만 병기 — 본문 관문이
                # 아니라 부속물 손실의 기록이다.
                annex = [a for a in item.get("attachments", [])
                         if a.get("role") != "body"
                         and _needs_convert(a.get("actual_format"))]
                if annex:
                    converted["annex_hwp"] = len(annex)
                    converted["annex_md"] = sum(
                        1 for a in annex if a.get("file")
                        and (root / (a["file"] + ".md")).exists())

                meta = metas.get(doc_id) if doc_id else None
                structured: dict = {"done": meta is not None}
                if meta is not None:
                    used.add(doc_id)                       # type: ignore[arg-type]
                    structured.update({"at": meta.get("at"),
                                       "passed": meta.get("passed"),
                                       "score": meta.get("score")})

                if not collected["done"]:
                    nxt: Optional[str] = "수집"
                elif need and not converted.get("done"):
                    nxt = "변환"
                elif not structured["done"]:
                    nxt = "구조화"
                else:
                    nxt = None

                items.append({"source": source, "name": item.get("name"),
                              "kind": item.get("kind"), "doc_id": doc_id,
                              "body_format": fmt, "body_file": body_file,
                              "route": {"family": family, "via": route["via"]},
                              "collected": collected, "converted": converted,
                              "structured": structured,
                              "linked": {"out": out_edges.get(doc_id, 0),
                                         "in": in_edges.get(doc_id, 0)},
                              "next": nxt})

    extras = []
    for doc_id, meta in sorted(metas.items()):
        if doc_id in used:
            continue
        name = meta.get("name") or ""
        stale = name in names
        extras.append({"doc_id": doc_id, "name": name,
                       "source_kind": meta.get("source_kind"),
                       "at": meta.get("at"), "stale": stale,
                       "reason": ("낡음 — 같은 이름의 수집분이 갱신됨 (재구조화 대상)"
                                  if stale else "수집 밖 유입 — 업로드 등")})

    runs = (links or {}).get("runs", [])
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": items, "extras": extras,
            "links": {"present": links is not None,
                      "edges": len((links or {}).get("links", [])),
                      "runs": len(runs),
                      "last_run": runs[-1] if runs else None}}


def summary(ledger: dict) -> dict:
    """출처별 깔때기 — 홈 현황 카드용으로 작다. build() 결과를 접는다."""
    per: dict[str, dict] = {}
    for it in ledger["items"]:
        s = per.setdefault(it["source"], {"items": 0, "collected": 0,
                                          "convert_required": 0, "converted": 0,
                                          "structured": 0})
        s["items"] += 1
        s["collected"] += 1 if it["collected"]["done"] else 0
        if it["converted"]["required"]:
            s["convert_required"] += 1
            s["converted"] += 1 if it["converted"].get("done") else 0
        s["structured"] += 1 if it["structured"]["done"] else 0
    return {"generated_at": ledger["generated_at"],
            "sources": [{"source": k, **v} for k, v in sorted(per.items())],
            "extras": {"total": len(ledger["extras"]),
                       "stale": sum(1 for e in ledger["extras"] if e["stale"])},
            "links": ledger["links"]}
