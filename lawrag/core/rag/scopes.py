"""질의 스코프 — "이 문서들만 대상으로 답하라" 의 정의(yml)와 해석.

과제 1(2026-08-19): 사용자가 RAG 가 답해야 하는 **외규 문서 묶음**을 정의하면
그 질의는 그 문서들만 대상으로 돈다. 묶음의 정의는 코드도 폴더도 아니고
**yml 한 장**이다 — 폴더는 1:1 관리 라벨이라 한 문서가 여러 묶음에 들 수 없고,
코드에 박으면 사용자가 못 고친다.

    data/rag/scopes.yml  (env RAG_SCOPES_FILE)

    scopes:
      - name: 자본시장-기본
        description: 자본시장법 3종
        documents:                    # 파일명(확장자·' 본문' 꼬리 있어도 됨) · 표시 이름 · doc_id
          - 자본시장과 금융투자업에 관한 법률
          - 자본시장과 금융투자업에 관한 법률 시행령 본문.xml
          - 금융투자업규정
        kinds: [law]                  # 선택 — 태그(kind)로 묶는다, documents 와 합집합
        scope_kinds: [외규]           # 선택 — 내규·외규·서식 축으로 묶는다
        include_old: false            # 선택 — 구판(status=구판)까지 넣나 (기본 false)

내장 스코프(yml 에 없어도 쓴다): `외규` · `내규` · `서식` — scope_kind 축 그대로.

해석 규칙:
- 이름 대조는 **정규형**으로 — 확장자·' 본문' 꼬리·공백을 지우고 대소문자를 접는다.
  사용자는 파일명을 적고, 스토어는 표시 이름을 들고 있어서 둘이 한 글자씩 다르다.
- 못 찾은 이름은 **조용히 버리지 않는다** — missing 으로 돌려주고 API 가 보여 준다.
  "자본시장법이 스코프에 있는 줄 알았는데 오타라 빠져 있었다" 가 가장 나쁜 실패다.
- 구판(내규 status=구판)은 include_old 를 켜지 않는 한 스코프에 안 든다 — 신구
  대비는 구판을 **명시**해서 연다.
- 파일은 mtime 으로 다시 읽는다 — 서버 재시작 없이 yml 을 고치면 다음 질의부터 반영.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import Index, store_path

log = logging.getLogger("lawrag.core.rag.scopes")

BUILTIN = ("외규", "내규", "서식")


def scopes_path() -> Path:
    return Path(os.environ.get("RAG_SCOPES_FILE",
                               store_path().parent / "rag" / "scopes.yml"))


# ------------------------------------------------------------------ 이름 정규형
_EXT = re.compile(r"\.(pdf|xml|html?|docx?|hwpx?|md|txt|yml|yaml)$", re.I)
_BODY_TAIL = re.compile(r"\s*본문$")


def canon(name: str) -> str:
    """파일명·표시 이름을 같은 꼴로 — 확장자·' 본문' 꼬리·공백 제거, 대소문자 접기.
    괄호·점은 남긴다(서식 이름 `(2024.12.31)` 은 뜻을 가른다)."""
    s = (name or "").strip()
    s = _EXT.sub("", s)
    s = _BODY_TAIL.sub("", s)
    return re.sub(r"\s+", "", s).casefold()


# ------------------------------------------------------------------ 읽기
_cache: dict = {}


def load(path: Optional[Path] = None) -> dict:
    """yml → {"scopes": [...]} — 없으면 빈 목록. mtime 캐시."""
    p = path or scopes_path()
    if not p.exists():
        return {"scopes": []}
    sig = p.stat().st_mtime_ns
    if _cache.get("sig") == sig and _cache.get("path") == str(p):
        return _cache["data"]
    import yaml
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:               # 깨진 yml — 스코프가 전부 사라지는 게 아니라 보인다
        log.warning("scopes.yml 읽기 실패 — %s", exc)
        data = {"scopes": [], "error": str(exc)}
    if isinstance(data, list):             # 꼭대기에 바로 목록을 적어도 받는다
        data = {"scopes": data}
    data.setdefault("scopes", [])
    _cache.update(sig=sig, path=str(p), data=data)
    return data


def save(data: dict, path: Optional[Path] = None) -> Path:
    """yml 을 쓴다(업로드 API 가 부른다). 유효성은 resolve 가 본다 — 여기서는
    모양만 지킨다(scopes 목록)."""
    import yaml
    p = path or scopes_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {"scopes": list(data.get("scopes") or [])}
    p.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")
    _cache.clear()
    return p


def definitions(path: Optional[Path] = None) -> list[dict]:
    """yml 의 스코프 정의 목록 — 이름이 없는 항목은 버린다."""
    out = []
    for row in load(path).get("scopes") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        out.append(row)
    return out


# ------------------------------------------------------------------ 해석
@dataclass
class Resolved:
    name: str
    doc_ids: frozenset
    missing: list = field(default_factory=list)      # yml 에 적혔지만 스토어에 없는 이름
    description: str = ""
    builtin: bool = False

    @property
    def empty(self) -> bool:
        return not self.doc_ids


def _name_map(index: Index) -> dict[str, str]:
    m: dict[str, str] = {}
    for did, v in index.docs.items():
        m.setdefault(canon(v.name), did)
        m.setdefault(did, did)
    return m


def resolve_names(index: Index, names: list) -> tuple[set, list]:
    """파일명·표시 이름·doc_id 목록 → (doc_id 집합, 못 찾은 이름)."""
    nm = _name_map(index)
    found: set = set()
    missing: list = []
    for raw in names or []:
        key = str(raw or "").strip()
        if not key:
            continue
        did = nm.get(key) or nm.get(canon(key))
        if did:
            found.add(did)
        else:
            missing.append(key)
    return found, missing


def _by_tags(index: Index, kinds: list, scope_kinds: list) -> set:
    ks = {str(k).strip() for k in kinds or [] if str(k).strip()}
    sks = {str(k).strip() for k in scope_kinds or [] if str(k).strip()}
    if not ks and not sks:
        return set()
    return {d for d, v in index.docs.items()
            if (v.kind in ks) or (v.scope_kind in sks)}


def resolve_def(index: Index, row: dict) -> Resolved:
    ids, missing = resolve_names(index, row.get("documents") or [])
    ids |= _by_tags(index, row.get("kinds") or [], row.get("scope_kinds") or [])
    if not row.get("include_old"):
        ids = {d for d in ids if index.docs[d].is_current}
    return Resolved(name=str(row.get("name")), doc_ids=frozenset(ids),
                    missing=missing, description=str(row.get("description") or ""))


def resolve(index: Index, name: str) -> Optional[Resolved]:
    """스코프 이름 → 해석. yml 정의가 내장 이름보다 먼저다(사용자가 '외규'를
    직접 정의하면 그게 이긴다). 모르는 이름이면 None."""
    key = (name or "").strip()
    if not key:
        return None
    for row in definitions():
        if str(row.get("name")).strip() == key:
            return resolve_def(index, row)
    if key in BUILTIN:
        ids = frozenset(d for d, v in index.docs.items()
                        if v.scope_kind == key and v.is_current)
        return Resolved(name=key, doc_ids=ids, builtin=True,
                        description={"외규": "법령·행정규칙·거래소/협회 규정 전부",
                                     "내규": "사내 규정·지침·세칙 (현행)",
                                     "서식": "상장 서식·표준정관"}[key])
    return None


def listing(index: Index) -> list[dict]:
    """화면·API 용 목록 — yml 정의(해석 결과 포함) + 내장."""
    out = []
    seen: set = set()
    for row in definitions():
        r = resolve_def(index, row)
        seen.add(r.name)
        out.append({"name": r.name, "description": r.description,
                    "documents": sorted(index.docs[d].name for d in r.doc_ids),
                    "count": len(r.doc_ids), "missing": r.missing,
                    "builtin": False})
    for b in BUILTIN:
        if b in seen:
            continue
        r = resolve(index, b)
        out.append({"name": b, "description": r.description,
                    "documents": sorted(index.docs[d].name for d in r.doc_ids),
                    "count": len(r.doc_ids), "missing": [], "builtin": True})
    return out


def apply(index: Index, scope: str = "", documents: Optional[list] = None
          ) -> tuple[Index, dict]:
    """질의 한 건에 스코프를 씌운다 — (스코프 색인, 경위).

    scope(이름)와 documents(즉석 파일명 목록)는 합집합이다. 둘 다 없으면 기본
    스코프(구판 제외)만 건다. 이름을 모르거나 해석 결과가 비면 **예외** —
    "스코프가 비어 전체를 뒤졌다" 는 조용한 실패가 과제 1 의 정반대다."""
    info: dict = {"scope": scope or "", "documents": list(documents or []),
                  "doc_ids": [], "missing": [], "names": []}
    if not scope and not documents:
        sub = index.scoped(None)
        info["default"] = True
        info["doc_ids"] = sorted(sub.scope) if sub.scope is not None else []
        return sub, info
    ids: set = set()
    if scope:
        r = resolve(index, scope)
        if r is None:
            raise ValueError(f"모르는 스코프입니다: {scope} "
                             f"(scopes.yml 정의 또는 {'/'.join(BUILTIN)})")
        ids |= set(r.doc_ids)
        info["missing"] += r.missing
        info["description"] = r.description
    if documents:
        found, missing = resolve_names(index, list(documents))
        ids |= {d for d in found if index.docs[d].is_current}
        info["missing"] += missing
    if not ids:
        raise ValueError(
            "스코프가 비었습니다 — 이름이 스토어의 문서와 하나도 맞지 않습니다: "
            + ", ".join(info["missing"][:5]))
    label = scope or f"즉석({len(ids)}문서)"
    sub = index.scoped(ids, name=label)
    info["doc_ids"] = sorted(ids)
    info["names"] = sorted(index.docs[d].name for d in ids)
    return sub, info
