"""근거 발췌로 가는 얇은 통로 — 런타임이 코퍼스를 만나는 **유일한** 자리 (AGENT6 §2).

    from agents.agent6.src import basis
    text = basis.load_excerpt("KSB/제19조/제3항")      # 발췌 하나
    text = basis.load_excerpt("KOFIA-R#고령투자자")     # 용어 앵커도 같은 함수
    ctx  = basis.resolve(items)                        # {좌표: 발췌} 일괄
    막힘 = basis.blocked_items(items)                  # {항목id: 사유}

## 얇아야 하는 이유

런타임 LLM 은 금소법을 읽지 않는다. 컴파일 타임에 물질화된 발췌만 읽는다(§0 원칙 1).
그래서 이 파일에는 **검색이 없다.** 좌표를 받아 파일 하나를 여는 것이 전부다.
"이 발화에 관련된 조문 찾기"라는 열린 문제를 런타임에 풀지 않겠다는 결정이 여기에
코드로 굳어 있다 — 여기에 유사도 검색을 추가하는 순간 그 결정이 무너진다.

## 용어 앵커 해소(`resolve_term`)가 여기 있어도 되는 이유

`resolve_term()` 은 **컴파일 국면 함수**다 — 코퍼스 빌드(`corpus_build`)만 부르고,
런타임 경로(`load_excerpt`·`resolve`·`blocked_items`)는 부르지 않는다. 좌표 규약을 아는
곳이 한 군데여야 쓰는 쪽(빌드)과 읽는 쪽(런타임)이 갈리지 않으므로 같은 파일에 둔다.
해소는 유사도 검색이 아니라 **doc.json 안의 정확 매칭**이다: 용어가 구역 제목이면 그
구역, 아니면 그 용어의 fact 가 걸린 구역. 어느 쪽도 아니면 MISSING 이고, 여러 곳이면
추측하지 않고 AMBIGUOUS 다(agent1 의 `LookupResult.status` 와 같은 철학).

## 좌표 표기 (§5)

    KSB/제19조/제3항        section 좌표 — 번호를 이미 아는 문서
    KOFIA-R#고령투자자       용어 앵커   — 문서 안의 낱말로 위치를 가리킨다
    KSB/제21조#단정적 판단    용어 + 범위 — 그 구역 **안에서** 용어를 찾는다

용어 앵커를 권하는 이유는 개정 내성이다. 조 번호가 밀려도 용어는 남는다 — manifest 는
"무엇을 물었나(asked)"와 "어디로 해소됐나(resolved)"를 둘 다 남기고, 개정 후에는
resolved 만 바뀐다.

## 차단이 기본인 이유

발췌가 없는 항목을 그냥 판정하면, LLM 은 근거 없이 그럴듯한 답을 낸다. 그것은 틀린
판정보다 나쁘다 — 무엇을 근거로 틀렸는지조차 남지 않아 고칠 수가 없다. 그래서
`blocked_items()` 는 미해소 basis 를 가진 항목을 **기본으로 차단**하고, 완화는 호출자가
좌표를 하나씩 이름 대어(`allow_missing=["CASE"]`) 명시할 때만 허용한다. 통째로 푸는
스위치는 두지 않는다.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Optional

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.glossary import normalize as _normalize                # noqa: E402

DEFAULT_CORPUS = ROOT / "agents/agent6/corpus"

RESOLVED = "RESOLVED"
AMBIGUOUS = "AMBIGUOUS"      # 여러 구역에 걸린다 — 추측하지 않는다
MISSING = "MISSING"

# 용어 앵커를 좌표에서 가르는 문자. schema.COORD_SEPARATORS 와 같은 약속이다.
TERM_SEP = "#"


class BasisError(Exception):
    """근거 통로의 실패. 전부 시끄럽다 — 근거가 없는데 있는 척하지 않는다."""


class ManifestMissing(BasisError):
    """manifest 가 없다 — 코퍼스를 아직 빌드하지 않았다."""


class ExcerptMissing(BasisError):
    """좌표에 해당하는 발췌 파일이 없다."""


class AmbiguousTerm(BasisError):
    """용어 앵커가 여러 구역에 걸려 발췌를 만들지 못했다.

    `ExcerptMissing` 의 하위가 **아니다.** 둘은 다른 사실이고 부르는 쪽의 대응도 다르다 —
    없음은 "수집 대기"지만 모호함은 "스펙에 section 을 적어라"다. 하나로 뭉치면 그 구별이
    사라져 영영 고쳐지지 않는다.
    """

    def __init__(self, message: str, candidates: Iterable[str] = ()):
        super().__init__(message)
        self.candidates = tuple(candidates)


# --- 좌표 ↔ 파일 -------------------------------------------------------------

class Coord(NamedTuple):
    """좌표 하나를 뜯어 놓은 것. `doc, section, term = split_coord(...)` 로도 쓴다."""
    doc: str
    section: Optional[str]
    term: Optional[str]

    def asked(self) -> str:
        """원래 표기로 되돌린다 — manifest·리포트의 키다."""
        base = f"{self.doc}/{self.section}" if self.section else self.doc
        return f"{base}{TERM_SEP}{self.term}" if self.term else base


def split_coord(coord: str) -> Coord:
    """"KSB/제19조#단정적 판단" → ("KSB", "제19조", "단정적 판단").

    section 도 term 도 없는 좌표(코퍼스 ID 만)는 형태로는 통과시킨다 — 그것이 근거가
    될 수 없다는 판단은 `excerpt_path()` 와 체크리스트 스키마가 한다.
    """
    text = str(coord)
    head, sep, term = text.partition(TERM_SEP)
    doc, _, section = head.partition("/")
    if not doc:
        raise BasisError(f"좌표 '{coord}' 에 코퍼스 ID 가 없습니다")
    if sep and not term.strip():
        raise BasisError(f"좌표 '{coord}' 의 '{TERM_SEP}' 뒤가 비어 있습니다 — 용어를 적으세요")
    if term and ("/" in term or "\\" in term):
        raise BasisError(f"좌표 '{coord}' 의 용어 '{term}' 에 경로 구분자가 있습니다 — "
                         f"용어는 원문에 나오는 낱말 그대로 적습니다")
    return Coord(doc, section or None, term.strip() or None)


def excerpt_path(coord: str, *, corpus_dir: str | Path | None = None) -> Path:
    """좌표 → 발췌 파일 경로.

    규약(§5): `excerpts/{ID}/{section_path 의 / 를 _ 로}[#용어].txt`
    **물은 좌표**로 이름을 짓는다(해소된 좌표가 아니라). 그래야 개정으로 조 번호가
    밀려도 런타임이 같은 파일을 계속 찾는다 — 용어 앵커를 두는 이유가 그것이다.
    """
    doc, section, term = split_coord(coord)
    tail = section.replace("/", "_") if section else ""
    if term:
        tail += TERM_SEP + term
    if not tail:
        raise BasisError(
            f"좌표 '{coord}' 에 section 도 용어도 없습니다 — 코퍼스 ID 만으로는 발췌를 "
            f"특정할 수 없습니다. 체크리스트에서 용어 앵커(term)나 조문 좌표(section)를 "
            f"확정하세요")
    base = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS
    return base / "excerpts" / doc / (tail + ".txt")


def load_manifest(manifest: Any = None) -> dict[str, Any]:
    """dict 를 주면 그대로, 경로를 주면 읽고, 아무것도 안 주면 기본 위치에서 읽는다."""
    if isinstance(manifest, Mapping):
        return dict(manifest)
    p = Path(manifest) if manifest else (DEFAULT_CORPUS / "manifest.json")
    if not p.exists():
        raise ManifestMissing(
            f"코퍼스 manifest 가 없습니다: {p}. "
            f"python -m agents.agent6.src.corpus_build 로 먼저 빌드하세요")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BasisError(f"{p}: manifest 를 읽지 못했습니다 — {exc}") from exc


def _basis_index(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["coord"]: r for r in manifest.get("basis", [])}


# ===========================================================================
# 용어 앵커 해소 — **컴파일 국면**. 코퍼스 빌드만 부른다.
# ===========================================================================
#
# 용어집은 판정 도구가 아니라 **문서 안의 좌표를 잡는 앵커**다. agent1 이
# `lookup(계약서, "별지1/신탁계약 세부내역", 신탁보수)` 로 값을 찾듯, 여기서는 용어로
# 근거 조문의 자리를 찾는다.
#
# 두 경로가 있고 **제목이 먼저**다.
#
#   1. 제목 앵커 — 구역 marker 의 `title`(regex 마커가 잡은 조 제목) 또는 `term`
#      (term_marker 로 열린 구역)에 그 용어가 들어 있는 구역. 용어가 곧 그 구역의
#      이름이므로 가장 강한 신호다. 금소법은 이 경로만 쓴다 — `조` 마커가 제목 줄
#      "제19조(설명의무)" 를 통째로 먹어 조 제목은 fact 가 되지 못하기 때문이다
#      (statute.glossary.yaml 주석의 실측 참조).
#   2. 본문 앵커 — 그 용어의 fact 가 걸린 구역. 제목에 없는 개념어("숙려기간")가 이쪽이다.
#
# 후보가 여럿이면 **하나가 나머지 전부의 조상일 때만** 접는다. 발췌는 자손을 포함하므로
# (corpus_build.render_excerpt) 조상 하나를 고르는 것은 추측이 아니라 포함관계다.
# 그래도 여럿이면 AMBIGUOUS — 고르지 않고 후보를 전부 보고한다.

@dataclass
class Anchor:
    """용어 앵커 해소 결과. status 가 전부다 — 조용히 하나를 고르지 않는다."""
    status: str                      # RESOLVED | AMBIGUOUS | MISSING
    term: str                        # 물은 용어(표면형 그대로)
    canonical: str                   # 용어집이 아는 정규 용어명 (미등록이면 물은 그대로)
    section_id: Optional[str] = None
    via: str = ""                    # "제목" | "본문"
    candidates: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    def dump(self) -> dict[str, Any]:
        d: dict[str, Any] = {"status": self.status, "term": self.term, "via": self.via}
        if self.canonical != self.term:
            d["canonical"] = self.canonical
        if self.section_id:
            d["section_id"] = self.section_id
        if self.candidates:
            d["candidates"] = self.candidates
        if self.reason:
            d["reason"] = self.reason
        if self.warnings:
            d["warnings"] = self.warnings
        return d


class _Sec(NamedTuple):
    section_id: str
    title: str                       # marker.title 또는 marker.term
    children: tuple[str, ...]


def _read_doc(doc: Any) -> tuple[list[_Sec], list[tuple[str, str]]]:
    """`core.structurize.Document` 든 그것을 덤프한 doc.json 이든 같은 모양으로 읽는다.

    빌드는 Document 를, 재현·검증은 디스크의 doc.json 을 넘긴다. 두 경로가 다른 코드를
    타면 "빌드에서는 되는데 검증에서는 안 된다"가 생긴다.
    """
    if isinstance(doc, Mapping):
        raw_secs = doc.get("sections") or []
        raw_facts = doc.get("facts") or []
        secs = [_Sec(s["section_id"],
                     str((s.get("marker") or {}).get("title")
                         or (s.get("marker") or {}).get("term") or ""),
                     tuple(s.get("children") or []))
                for s in raw_secs]
        facts = [(f["term"], f["section_id"]) for f in raw_facts]
        return secs, facts
    secs = [_Sec(s.section_id,
                 str(s.marker.get("title") or s.marker.get("term") or ""),
                 tuple(s.children))
            for s in getattr(doc, "sections", [])]
    facts = [(f.term, f.section_id) for f in getattr(doc, "facts", [])]
    return secs, facts


def _descendants(secs: list[_Sec], root: str) -> set[str]:
    """children 링크로 자손을 모은다. path 접두사로 세지 않는 이유는 path 가 유일하지
    않기 때문이다 — 같은 제목이 반복되면 코어가 section_id 에만 '#2' 를 붙인다."""
    by_id = {s.section_id: s for s in secs}
    out: set[str] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        for child in by_id.get(cur, _Sec("", "", ())).children:
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def subtree_ids(doc: Any, section_ids: Iterable[str]) -> set[str]:
    """주어진 구역들과 그 자손 전부의 section_id — 용어 앵커의 범위 좁히기에 쓴다."""
    secs, _ = _read_doc(doc)
    out: set[str] = set()
    for sid in section_ids:
        out.add(sid)
        out |= _descendants(secs, sid)
    return out


def _collapse_to_ancestor(secs: list[_Sec], cands: list[str]) -> Optional[str]:
    """후보 중 하나가 나머지 전부의 조상이면 그것. 아니면 None."""
    for c in cands:
        kin = _descendants(secs, c)
        if all(o == c or o in kin for o in cands):
            return c
    return None


def resolve_term(doc: Any, term: str, *, scope: Optional[Iterable[str]] = None,
                 glossary: Any = None) -> Anchor:
    """용어 하나를 코퍼스 doc.json 안의 section 좌표로 해소한다.

        basis.resolve_term(doc, "설명의무")                    → KSB 제19조
        basis.resolve_term(doc, "고령투자자", scope=Ⅳ의 자손들)  → Ⅳ/Ⅳ-2/11.

    `glossary` 를 주면 별칭까지 함께 찾는다("청약철회" 로 물어도 조 제목 "청약의 철회"
    를 찾는다). 용어집에 없는 용어도 표면형 그대로 찾아 보되 경고를 남긴다 — 원문에
    실제로 나오는지 세어 보고 용어집에 등록하는 것이 규율이다.
    """
    surfaces = [term]
    canonical = term
    warnings: list[str] = []
    if glossary is not None:
        name = glossary.lookup(term)
        if name:
            canonical, surfaces = name, glossary.surfaces_of(name)
        else:
            # 등록되지 않은 용어는 **제목 앵커로만** 잡힌다. structurize 가 fact 를
            # 만드는 대상이 용어집의 fact 용어뿐이기 때문이다 — 본문에 백 번 나와도
            # 용어집에 없으면 fact 가 하나도 없다. 이 사실을 말해 주지 않으면
            # "원문에 있는데 왜 못 찾느냐"로 시간을 버린다.
            warnings.append(
                f"용어 '{term}' 이 용어집(doc_type {getattr(glossary, 'doc_type', '?')})에 "
                f"없습니다 — 구역 제목으로만 찾았습니다. 본문 앵커가 필요하면 원문 등장 "
                f"횟수를 세어 용어집에 fact 용어로 등록하고 코퍼스를 다시 빌드하세요")
    keys = [k for k in (_normalize(s) for s in surfaces) if k]
    if not keys:
        return Anchor(MISSING, term, canonical, reason="용어가 비어 있습니다",
                      warnings=warnings)

    secs, facts = _read_doc(doc)
    allowed = set(scope) if scope is not None else None
    in_scope = [s for s in secs if allowed is None or s.section_id in allowed]
    if allowed is not None and not in_scope:
        return Anchor(MISSING, term, canonical, warnings=warnings,
                      reason="좁히려는 section 좌표가 이 코퍼스에 없습니다")

    titled = [s for s in in_scope if any(k in _normalize(s.title) for k in keys)]
    if titled:
        return _decide(secs, titled, "제목", term, canonical, warnings,
                       {s.section_id: s.title for s in titled})

    hits: dict[str, int] = {}
    for f_term, sid in facts:
        if _normalize(f_term) in keys and (allowed is None or sid in allowed):
            hits[sid] = hits.get(sid, 0) + 1
    if hits:
        order = {s.section_id: i for i, s in enumerate(secs)}
        found = [s for s in in_scope if s.section_id in hits]
        found.sort(key=lambda s: order[s.section_id])
        return _decide(secs, found, "본문", term, canonical, warnings,
                       {s.section_id: s.title for s in found}, hits)

    scoped = " (좁힌 범위 안)" if allowed is not None else ""
    unregistered = (glossary is not None and glossary.lookup(term) is None)
    fix = ("이 용어는 용어집에 없어 fact 가 만들어지지 않았습니다 — 본문에 나오더라도 "
           "제목 앵커로만 찾습니다. 용어집에 fact 용어로 등록하고 코퍼스를 다시 빌드하세요"
           if unregistered else
           "원문에 실제로 나오는 낱말인지 확인하거나 section 좌표로 인용하세요")
    return Anchor(MISSING, term, canonical, warnings=warnings,
                  reason=f"용어 '{term}' 이 이 코퍼스의 구역 제목에도 fact 에도 없습니다{scoped} — {fix}")


def _decide(secs: list[_Sec], cands: list[_Sec], via: str, term: str, canonical: str,
            warnings: list[str], titles: Mapping[str, str],
            hits: Optional[Mapping[str, int]] = None) -> Anchor:
    ids = [s.section_id for s in cands]
    rows = [{"section_id": i, "title": titles.get(i, ""),
             **({"facts": hits[i]} if hits and i in hits else {})} for i in ids]
    if len(ids) == 1:
        return Anchor(RESOLVED, term, canonical, ids[0], via, rows, warnings=warnings)
    folded = _collapse_to_ancestor(secs, ids)
    if folded:
        note = (f"{len(ids)}개 구역에 걸렸으나 '{folded}' 가 나머지의 조상이라 "
                f"그 구역으로 접었습니다 (발췌는 자손을 포함합니다)")
        return Anchor(RESOLVED, term, canonical, folded, via, rows,
                      reason=note, warnings=warnings)
    return Anchor(AMBIGUOUS, term, canonical, None, via, rows, warnings=warnings,
                  reason=f"용어 '{term}' 이 {len(ids)}개 구역의 {via}에 걸립니다 "
                         f"({', '.join(ids[:6])}{' …' if len(ids) > 6 else ''}) — "
                         f"추측하지 않습니다. basis 에 section 을 함께 적어 좁히세요 "
                         f"(예: {{ doc: …, term: {term}, section: {ids[0].split('/')[0]} }})")


# --- 발췌 읽기 ---------------------------------------------------------------

@dataclass
class Ref:
    """발췌 하나 — **무엇을 물었나(query)** 와 **어디로 해소됐나(coordinate)** 를 함께 든다.

    용어 앵커는 좌표가 두 개다. 리포트에 해소된 좌표만 남기면 "왜 하필 그 조문인가"가
    사라지고, 물은 것만 남기면 "정말 그 자리로 갔는가"를 확인할 수 없다. 둘 다 든다.
    """
    query: str
    coordinate: str
    text: str
    header: dict[str, str] = field(default_factory=dict)

    @property
    def moved(self) -> bool:
        return bool(self.coordinate) and self.coordinate != self.query


def _split_header(raw: str) -> tuple[dict[str, str], str]:
    """발췌 파일을 (머리글 dict, 본문) 으로. 머리글은 첫 `#` 주석 블록이다."""
    head: dict[str, str] = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or not lines[i].strip()):
        if lines[i].startswith("#"):
            body = lines[i].lstrip("#").strip()
            if ":" in body:
                k, _, v = body.partition(":")
                head[k.strip()] = v.strip()
        i += 1
    return head, "\n".join(lines[i:]).strip()


def _explain_absence(coord: str, path: Path, manifest: Any,
                     corpus_dir: str | Path | None) -> None:
    """발췌가 없을 때 **왜** 없는지까지 말하고 예외를 던진다. 반드시 던진다.

    "없음"과 "모호함"은 다른 사실이고 고치는 방법도 다르다. manifest 를 읽을 수 있으면
    그 구별까지 전한다 — 읽을 수 없으면 없음으로 본다(빌드 전이라는 뜻이다).
    """
    src = manifest
    if src is None and corpus_dir is not None:
        src = Path(corpus_dir) / "manifest.json"
    row: dict[str, Any] = {}
    try:
        row = _basis_index(load_manifest(src)).get(coord) or {}
    except BasisError:
        pass
    if row.get("status") == AMBIGUOUS:
        cands = [c.get("section_id", "") for c in (row.get("anchor") or {}).get("candidates", [])]
        raise AmbiguousTerm(row.get("reason") or
                            f"좌표 '{coord}' 의 용어가 여러 구역에 걸려 발췌를 만들지 못했습니다",
                            cands)
    reason = f" ({row['reason']})" if row.get("reason") else ""
    raise ExcerptMissing(
        f"좌표 '{coord}' 의 발췌가 없습니다: {path}{reason}. "
        f"코퍼스 빌드에서 이 좌표가 미해소였거나, 원문이 아직 없습니다")


def load_ref(coord: str, *, corpus_dir: str | Path | None = None,
             manifest: Any = None) -> Ref:
    """좌표 하나를 발췌 + 해소 좌표로. 용어 앵커도 section 좌표도 같은 입구다.

    해소 좌표는 **발췌 파일의 머리글**에서 읽는다(manifest 를 다시 뒤지지 않는다) —
    발췌와 그 출처가 같은 파일에 있어야 둘이 어긋나지 않는다.
    """
    p = excerpt_path(coord, corpus_dir=corpus_dir)
    if not p.exists():
        _explain_absence(coord, p, manifest, corpus_dir)
    head, body = _split_header(p.read_text(encoding="utf-8"))
    section_id = head.get("section_id") or ""
    resolved = f"{split_coord(coord).doc}/{section_id}" if section_id else coord
    return Ref(query=coord, coordinate=resolved, text=body, header=head)


def load_excerpt(coord: str, *, corpus_dir: str | Path | None = None,
                 with_header: bool = False) -> str:
    """좌표 하나의 발췌문. 머리글(`#` 주석)은 기본으로 걷어낸다.

    머리글에는 판본·수집일·verification 이 들어 있다. 사람이 발췌를 열어 봤을 때 어느
    판본인지 알 수 있어야 하므로 파일에는 남기고, 프롬프트에는 넣지 않는다.
    """
    p = excerpt_path(coord, corpus_dir=corpus_dir)
    if not p.exists():
        _explain_absence(coord, p, None, corpus_dir)
    raw = p.read_text(encoding="utf-8")
    return raw if with_header else _split_header(raw)[1]


def excerpt_header(coord: str, *, corpus_dir: str | Path | None = None) -> dict[str, str]:
    """발췌 머리글의 key: value — 판본 추적용(리포트에 근거 판본을 적을 때 쓴다)."""
    return _split_header(load_excerpt(coord, corpus_dir=corpus_dir,
                                      with_header=True))[0]


def coords_of(items: Iterable[Any]) -> dict[str, list[str]]:
    """항목들이 요구하는 좌표 → 요구한 항목 id. 꺼진 항목은 세지 않는다."""
    out: dict[str, list[str]] = {}
    for item in items:
        if not getattr(item, "enabled", True):
            continue
        for coord in item.basis_refs():
            out.setdefault(coord, []).append(item.id)
    return out


def resolve(items: Iterable[Any], manifest: Any = None, *,
            corpus_dir: str | Path | None = None) -> dict[str, str]:
    """항목들이 요구하는 좌표의 발췌를 한 번에 싣는다. 반환: {좌표: 발췌문}.

    해소되지 않은 좌표(MISSING·AMBIGUOUS)는 **여기서는 조용히 빠진다** — 그 처리는
    `blocked_items()` 의 몫이고, 이 함수는 "실을 수 있는 것을 싣는" 일만 한다.
    그러나 manifest 가 RESOLVED 라고 한 좌표의 파일이 없으면 예외다. manifest 와 디스크가
    어긋난 채로 도는 것은 조용한 실패의 전형이다(누군가 발췌를 지웠거나 빌드가 반쪽이다).
    """
    man = load_manifest(manifest)
    index = _basis_index(man)
    out: dict[str, str] = {}
    unknown: list[str] = []
    for coord in coords_of(items):
        row = index.get(coord)
        if row is None:
            unknown.append(coord)
            continue
        if row["status"] != RESOLVED:
            continue
        out[coord] = load_excerpt(coord, corpus_dir=corpus_dir)
    if unknown:
        raise BasisError(
            f"manifest 가 모르는 좌표가 있습니다: {', '.join(sorted(unknown))}. "
            f"체크리스트가 바뀐 뒤 코퍼스를 다시 빌드하지 않았습니다 "
            f"(python -m agents.agent6.src.corpus_build)")
    return out


# --- 차단 -------------------------------------------------------------------

def blocked_items(items: Iterable[Any], manifest: Any = None, *,
                  allow_missing: Iterable[str] = ()) -> dict[str, str]:
    """미해소 basis 를 가진 항목 → 차단 사유. **기본은 차단이다.**

    `allow_missing` 은 호출자가 "이 근거는 없어도 판정하겠다"고 명시적으로 이름 대는
    자리다. 좌표("CASE/2023-046")로도, 코퍼스 ID("CASE")로도 받는다. 전부 푸는 값은
    받지 않는다 — 그런 스위치가 있으면 결국 켜진 채로 운영에 나간다.

    호출자가 이 함수를 부르지 않아도 리포트는 나온다. 그래서 manifest 에도 결과를
    박아 둔다(corpus_build) — 차단을 잊는 것 자체가 조용한 실패이기 때문이다.
    """
    man = load_manifest(manifest)
    index = _basis_index(man)
    allow = {str(a) for a in allow_missing}
    blocked: dict[str, str] = {}

    for item in items:
        if not getattr(item, "enabled", True):
            continue
        reasons: list[str] = []
        for coord in item.basis_refs():
            doc = split_coord(coord).doc
            if coord in allow or doc in allow:
                continue
            row = index.get(coord)
            if row is None:
                reasons.append(f"{coord}(manifest 에 없음 — 코퍼스 재빌드 필요)")
            elif row["status"] != RESOLVED:
                reasons.append(f"{coord}({_short(row.get('reason'))})")
        if reasons:
            blocked[item.id] = "미해소 basis: " + ", ".join(reasons)
    return blocked


def activatable(items: Iterable[Any], manifest: Any = None, *,
                allow_missing: Iterable[str] = ()) -> list[Any]:
    """차단되지 않은 항목만. 런타임의 활성 항목 집합은 여기서 시작한다."""
    blocked = blocked_items(items, manifest, allow_missing=allow_missing)
    return [i for i in items if getattr(i, "enabled", True) and i.id not in blocked]


def _short(reason: Optional[str], limit: int = 60) -> str:
    text = " ".join((reason or "사유 미기재").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"
