"""계보(lineage)를 유지하는 조문 비교.

번호보다 계보가 중요하다. 번호가 밀려도 같은 조문이면 계보를 유지해야 룰과
참조 연결이 끊기지 않는다.

판정 순서
1. 자기 번호를 떼고 인용 번호를 가린 비교값을 만든다 (normalize.compare_text).
2. 2글자 조각(bigram) Jaccard로 후보를 빠르게 거른다.
3. 조문 순서를 유지하는 전역 정렬(가중 LCS)로 대응 쌍을 찾는다.
4. 같은 키에는 가산점 0.05를 준다. 같은 키는 유사도가 낮아도 정렬 후보로 둔다.
5. 정렬에서 빠진 쌍 중 유사도 0.90 이상은 순서를 벗어난 실제 이동으로 회수한다.
6. 같은 키인데 유사도가 낮으면 전면 개정(AMEND)으로 둔다.
7. 남은 항목은 삭제(DELETE) 또는 신설(ADD).

REF_ONLY는 인용 번호만 바뀌었고, 그 변화가 이번 비교의 조문 이동으로 전부
설명될 때만 쓴다. 외부 법령 인용이 바뀌었거나 이동으로 설명되지 않으면 AMEND다.
그룹(조문·전문 / 별표 / 부칙)끼리만 비교한다. 부칙은 공포번호 키로만 맞춘다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .lawgo_parse import KIND_ADDENDUM, KIND_ANNEX, Article
from .normalize import (ARTICLE_REF, bigrams, compact, compare_text, citations,
                        normalize_text, stable_id, strip_own_heading)

SAME, AMEND, MOVE, MOVE_AMEND, REF_ONLY, ADD, DELETE = (
    "SAME", "AMEND", "MOVE", "MOVE_AMEND", "REF_ONLY", "ADD", "DELETE")
RULE_REVIEW = {AMEND: "Y", MOVE_AMEND: "Y", DELETE: "Y", SAME: "N", MOVE: "N", REF_ONLY: "N", ADD: "NA"}

SAME_KEY_BONUS = 0.05
MATCH_MIN = 0.60          # 다른 키끼리 정렬 대응으로 인정하는 최소 유사도
MOVE_RECOVER_MIN = 0.90   # 순서를 벗어난 이동 회수 기준 (합성 데이터 기준, 실문서 재조정 대상)
LOW_SIMILARITY = 0.50     # 같은 키 전면 개정 표시 기준
JACCARD_MIN = 0.30
TOP_CANDIDATES = 8


@dataclass(frozen=True)
class BaseArticle:
    """DB의 현행(열린 구간) 조문 판본."""
    key: str
    kind: str
    title: str
    text: str
    lineage_id: str
    version_id: str
    effective_from: str
    seq: int = 0
    attachment_sha256: str = ""


@dataclass
class Change:
    change_type: str
    old: BaseArticle | None
    new: Article | None
    similarity: float
    reason: str
    lineage_id: str
    effective_from: str = ""
    official_note: str = ""

    @property
    def rule_review(self) -> str:
        return RULE_REVIEW[self.change_type]

    @property
    def kind(self) -> str:
        return (self.new or self.old).kind


@dataclass
class DiffResult:
    changes: list[Change] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {t: 0 for t in (SAME, AMEND, MOVE, MOVE_AMEND, REF_ONLY, ADD, DELETE)}
        for c in self.changes:
            out[c.change_type] += 1
        return out

    def changed(self) -> list[Change]:
        return [c for c in self.changes if c.change_type != SAME]


@dataclass
class _Item:
    index: int
    key: str
    compare: str      # 자기 번호 제거·인용 번호 가림·공백 제거
    body: str         # 자기 번호 제거, 공백 정규화 (인용 내부/외부 판별용)
    flat: str         # body 의 공백 제거
    grams: frozenset
    attachment: str


# 첨부 해시 칸에 파일 sha 대신 별표 내용 지문을 담을 때의 머리 (구조화 경로)
CONTENT_FINGERPRINT = "content:"


def _body(text: str) -> str:
    return normalize_text(strip_own_heading(normalize_text(text)))


def _item(index: int, key: str, text: str, attachment: str) -> _Item:
    compare = compare_text(text)
    body = _body(text)
    return _Item(index, key, compare, body, compact(body), bigrams(compare), attachment or "")


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _ratio(a: str, b: str) -> float:
    if a == b:
        return 1.0
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    if matcher.real_quick_ratio() < 0.3:
        return matcher.real_quick_ratio() * 0.5
    return matcher.ratio()


def _candidates(old: list[_Item], new: list[_Item]) -> dict[tuple[int, int], float]:
    """(old i, new j) → 유사도. 같은 키는 항상, 다른 키는 Jaccard 상위 후보만 계산한다."""
    scores: dict[tuple[int, int], float] = {}
    by_key = {item.key: j for j, item in enumerate(new)}
    for i, o in enumerate(old):
        ranked = sorted(((_jaccard(o.grams, n.grams), j) for j, n in enumerate(new)), reverse=True)
        picks = {j for jac, j in ranked[:TOP_CANDIDATES] if jac >= JACCARD_MIN}
        if o.key in by_key:
            picks.add(by_key[o.key])
        for j in picks:
            scores[(i, j)] = _ratio(o.compare, new[j].compare)
    return scores


def _align(old: list[_Item], new: list[_Item], scores: dict[tuple[int, int], float]) -> list[tuple[int, int]]:
    """순서를 유지하는 가중 정렬. 같은 키 +0.05, 다른 키는 MATCH_MIN 이상만."""
    weight: dict[tuple[int, int], float] = {}
    for (i, j), sim in scores.items():
        same = old[i].key == new[j].key
        if same or sim >= MATCH_MIN:
            weight[(i, j)] = sim + (SAME_KEY_BONUS if same else 0.0)
    n, m = len(old), len(new)
    table = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        row, above = table[i], table[i - 1]
        for j in range(1, m + 1):
            best = above[j] if above[j] >= row[j - 1] else row[j - 1]
            w = weight.get((i - 1, j - 1))
            if w is not None and above[j - 1] + w > best:
                best = above[j - 1] + w
            row[j] = best
    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        w = weight.get((i - 1, j - 1))
        if w is not None and abs(table[i][j] - (table[i - 1][j - 1] + w)) < 1e-9:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif table[i - 1][j] >= table[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def _compact_cites(body: str, key_map: dict[str, str] | None) -> str:
    """인용 토큰을 키 형식으로 맞추고, 내부 인용은 이번 이동 대응표로 바꾼다."""
    cites = citations(body, skip_own_heading=False)
    pieces, last = [], 0
    for cite, match in zip(cites, ARTICLE_REF.finditer(body)):
        key = cite.key
        if key_map is not None and not cite.external:
            key = key_map.get(key, key)
        number, _, branch = key.partition("의")
        pieces.append(body[last:match.start()])
        pieces.append(f"제{number}조" + (f"의{branch}" if branch else ""))
        last = match.end()
    pieces.append(body[last:])
    return "".join(pieces)


def _explained(old_body: str, new_body: str, key_map: dict[str, str]) -> bool:
    return compact(_compact_cites(old_body, key_map)) == compact(_compact_cites(new_body, None))


def _classify(o: BaseArticle, oi: _Item, n: Article, ni: _Item, sim: float,
              key_map: dict[str, str]) -> tuple[str, str]:
    same_key = o.key == n.key
    if oi.attachment.startswith(CONTENT_FINGERPRINT) and oi.attachment == ni.attachment:
        # 구조화 경로 별표: 표 배치만 다르고 글자 구성은 같다 (structured.annex_fingerprint)
        return (SAME, "내용 동일 (표 서식 무시)") if same_key else (MOVE, f"번호 이동 {o.key}→{n.key}, 내용 동일")
    attach_changed = bool(oi.attachment and ni.attachment and oi.attachment != ni.attachment)
    if oi.flat == ni.flat and not attach_changed:
        return (SAME, "내용 동일") if same_key else (MOVE, f"번호 이동 {o.key}→{n.key}, 내용 동일")
    if attach_changed and oi.flat == ni.flat:
        return (AMEND if same_key else MOVE_AMEND), "별표 첨부 파일 sha 변경"
    if oi.compare == ni.compare and not attach_changed:
        if _explained(oi.body, ni.body, key_map):
            if same_key:
                return REF_ONLY, "인용 번호만 변경 (이번 조문 이동으로 설명됨)"
            return MOVE, f"번호 이동 {o.key}→{n.key}, 인용 번호는 이동으로 설명됨"
        reason = "인용 번호 변경이 이번 조문 이동으로 설명되지 않음 (외부 인용 또는 항·호 번호 변경)"
        return (AMEND if same_key else MOVE_AMEND), reason
    if same_key:
        if sim < LOW_SIMILARITY:
            return AMEND, f"같은 번호 전면 개정 (유사도 {sim:.2f}) — 번호 재사용 여부 확인"
        return AMEND, f"내용 개정 (유사도 {sim:.2f})"
    return MOVE_AMEND, f"번호 이동 {o.key}→{n.key}와 내용 개정 (유사도 {sim:.2f})"


def _official_note(o: BaseArticle | None, n: Article | None, change_type: str) -> str:
    if n is None or not n.official_changed:
        return ""
    official = n.official_changed == "Y"
    ours = change_type not in (SAME, MOVE, REF_ONLY)
    if official != ours:
        return f"법제처 조문변경여부={n.official_changed}, 비교 판정={change_type}"
    return ""


def new_lineage(doc_cd: str, version_id: str, key: str) -> str:
    return "L" + stable_id(doc_cd, "lineage", version_id, key, length=23)


def diff_group(base: list[BaseArticle], new: list[Article], *, doc_cd: str, version_id: str,
               keyed_only: bool = False,
               forced: dict[str, str] | None = None) -> list[Change]:
    """한 그룹 비교. forced: 승인 화면 수동 연결 {옛 키: 새 키}."""
    live_new = [a for a in new if not a.deleted]
    deleted_keys = {a.key for a in new if a.deleted}
    old_items = [_item(i, a.key, a.text, a.attachment_sha256) for i, a in enumerate(base)]
    new_items = [_item(j, a.key, a.text, a.attachment_sha256) for j, a in enumerate(live_new)]

    pairs: list[tuple[int, int, float, str]] = []      # (i, j, sim, how)
    used_old: set[int] = set()
    used_new: set[int] = set()
    forced = forced or {}
    old_by_key = {a.key: i for i, a in enumerate(base)}
    new_by_key = {a.key: j for j, a in enumerate(live_new)}
    for old_key, new_key in forced.items():
        i, j = old_by_key.get(old_key), new_by_key.get(new_key)
        if i is None or j is None:
            raise ValueError(f"수동 연결 대상 없음: {old_key}→{new_key}")
        pairs.append((i, j, _ratio(old_items[i].compare, new_items[j].compare), "forced"))
        used_old.add(i)
        used_new.add(j)

    rest_old = [x for x in old_items if x.index not in used_old]
    rest_new = [x for x in new_items if x.index not in used_new]
    if keyed_only:
        by_key = {x.key: x for x in rest_new}
        for o in rest_old:
            n = by_key.get(o.key)
            if n is not None:
                pairs.append((o.index, n.index, _ratio(o.compare, n.compare), "key"))
                used_old.add(o.index)
                used_new.add(n.index)
    else:
        # 같은 키·같은 내용은 확정 대응(anchor)으로 두고, 나머지끼리만 후보 유사도를 계산한다.
        # 600조 규모 법령에서 전 쌍 bigram 계산을 피한다 (대부분 조문은 그대로다).
        new_pos = {x.key: b for b, x in enumerate(rest_new)}
        anchored_old, anchored_new = set(), set()
        scores: dict[tuple[int, int], float] = {}
        for a, o in enumerate(rest_old):
            b = new_pos.get(o.key)
            if b is not None and rest_new[b].flat == o.flat and rest_new[b].attachment == o.attachment:
                scores[(a, b)] = 1.0
                anchored_old.add(a)
                anchored_new.add(b)
        loose_old = [a for a in range(len(rest_old)) if a not in anchored_old]
        loose_new = [b for b in range(len(rest_new)) if b not in anchored_new]
        partial = _candidates([rest_old[a] for a in loose_old], [rest_new[b] for b in loose_new])
        for (x, y), sim in partial.items():
            scores[(loose_old[x], loose_new[y])] = sim
        for a, b in _align(rest_old, rest_new, scores):
            o, n = rest_old[a], rest_new[b]
            pairs.append((o.index, n.index, scores[(a, b)], "aligned"))
            used_old.add(o.index)
            used_new.add(n.index)
        # 순서를 벗어난 이동 회수
        left_old = [x for x in rest_old if x.index not in used_old]
        left_new = [x for x in rest_new if x.index not in used_new]
        if left_old and left_new:
            extra = _candidates(left_old, left_new)
            ranked = sorted(((sim, a, b) for (a, b), sim in extra.items() if sim >= MOVE_RECOVER_MIN),
                            reverse=True)
            for sim, a, b in ranked:
                o, n = left_old[a], left_new[b]
                if o.index in used_old or n.index in used_new:
                    continue
                pairs.append((o.index, n.index, sim, "moved"))
                used_old.add(o.index)
                used_new.add(n.index)

    key_map = {base[i].key: live_new[j].key for i, j, _, _ in pairs if base[i].key != live_new[j].key}
    changes: list[Change] = []
    for i, j, sim, how in pairs:
        o, n = base[i], live_new[j]
        change_type, reason = _classify(o, old_items[i], n, new_items[j], sim, key_map)
        if how == "forced":
            reason = "승인 화면 수동 연결 — " + reason
        elif how == "moved":
            reason = f"순서 밖 이동 회수 (유사도 {sim:.2f}) — " + reason
        changes.append(Change(change_type, o, n, round(sim, 4), reason, o.lineage_id,
                              official_note=_official_note(o, n, change_type)))
    for i, o in enumerate(base):
        if i not in used_old:
            reason = "삭제 표시된 조문" if o.key in deleted_keys else "새 판본에 대응 조문 없음"
            changes.append(Change(DELETE, o, None, 0.0, reason, o.lineage_id))
    for j, n in enumerate(live_new):
        if j not in used_new:
            changes.append(Change(ADD, None, n, 0.0, "신설", new_lineage(doc_cd, version_id, n.key),
                                  official_note=_official_note(None, n, ADD)))
    return changes


def diff_snapshot(base: list[BaseArticle], new: list[Article], *, doc_cd: str, version_id: str,
                  forced: dict[str, str] | None = None) -> DiffResult:
    groups = (
        (lambda k: k not in (KIND_ANNEX, KIND_ADDENDUM), False),
        (lambda k: k == KIND_ANNEX, False),
        (lambda k: k == KIND_ADDENDUM, True),
    )
    result = DiffResult()
    for accept, keyed_only in groups:
        old_part = [a for a in base if accept(a.kind)]
        new_part = [a for a in new if accept(a.kind)]
        keys = {a.key for a in old_part}
        part_forced = {k: v for k, v in (forced or {}).items() if k in keys}
        result.changes.extend(diff_group(old_part, new_part, doc_cd=doc_cd, version_id=version_id,
                                         keyed_only=keyed_only, forced=part_forced))
    # 표시 순서: 새 판본 순서, 삭제는 옛 순서 근처
    result.changes.sort(key=lambda c: (c.new.seq, 0) if c.new else (c.old.seq, 1))
    return result
