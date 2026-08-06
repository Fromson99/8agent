"""데이터 모델 (SPEC §2).

    Block           Docling 요소 하나를 해석기 관점으로 감싼 것
    Candidate       구조 가설 후보 하나
    Ladder          유도된 레벨 사다리
    ScopeStack      DP 상태
    Node            트리 마디
    StructureResult 산출물 전체
    Fingerprint     재현 판정 키

`Candidate` 에 `level` 이 **처음부터 있지 않다**는 것이 요점이다. 레벨은 용어집이
아니라 문서가 유도한다(SPEC §0, §6) — 제안자는 레벨 의미를 담지 않고, S2 가 배정하며,
배정받지 못한 후보(`unassigned`)는 S3 이 문맥으로 앉힌다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

Ordinal = tuple[int, ...]


@dataclass
class Block:
    """Docling 요소 하나. 해석기는 이 형태만 안다 — 파서 교체에 열려 있다.

    `bbox` 는 해석에 쓰이지 않는다 — 판별은 텍스트와 offset 으로만 한다. 다만
    결과를 **원본 PDF 위에 되돌려 보여 주려면** 좌표가 있어야 하므로 실어 나른다.

    `kind` 가 `text` 가 아닌 블록은 **구조 후보를 내지 않는다**(S0 이 건너뛴다).
    그래도 블록 리스트에는 남는다 — 표를 아예 빼 버리면 `idx` 가 원본 요소 순서와
    어긋나 `Node.span` 으로 표를 되찾을 길이 없어지고, 화면에서 표가 통째로
    사라진다. 자리를 지키게 두고 발화만 막는다.
    """
    idx: int                       # 읽기 순서
    text: str
    page: int = 1
    is_heading: bool = False
    element_index: int = 0         # 원본 요소 index (출처 되돌리기용)
    bbox: Optional[list[float]] = None
    bbox_origin: str = "BOTTOMLEFT"
    kind: str = "text"             # text | table | figure
    # 타이포그래피 (`core.typography`). 마커 없는 제목을 보려면 이 축이 있어야 한다.
    # `size_ratio` 는 본문 대비 배율이라 문서마다 임계를 다시 잡지 않아도 된다.
    size_ratio: Optional[float] = None
    bold: bool = False
    gap_before: Optional[float] = None

    @property
    def proposes(self) -> bool:
        """구조 후보를 낼 수 있는 블록인가."""
        return self.kind == "text"

    @staticmethod
    def page_widths(blocks) -> dict[int, float]:
        """페이지 폭 추정 — 그 쪽 **본문** 블록들의 오른쪽 끝 최댓값.

        PDF 를 다시 열지 않고 얻는다. 들여쓰기 비교는 **같은 쪽 안의 상대 위치**만
        보면 되므로 이 근사로 충분하다.

        표·그림은 세지 않는다. 이 값은 마커의 왼쪽 x 를 나누는 분모이고(§indent),
        표가 본문보다 넓게 그려지는 문서에서는 분모만 커져 모든 계열의 들여쓰기가
        함께 얕아진다 — 비교에 보탬이 없으면서 임계값(MIN_GAP)만 흔든다.
        """
        out: dict[int, float] = {}
        for b in blocks:
            if b.bbox and b.proposes:
                out[b.page] = max(out.get(b.page, 0.0), float(b.bbox[2]))
        return {k: v for k, v in out.items() if v > 0}

    @classmethod
    def from_elements(cls, elements) -> list["Block"]:
        """`core.parse_adapter.Element` 리스트 → 블록.

        표와 그림도 블록이 된다. 구조 후보는 여전히 내지 않지만(`kind != "text"`),
        **읽기 순서의 자리를 차지한다** — 그래야 `Node.span` 이 표를 덮고, 검수
        화면이 "이 구역에 표가 있다" 를 말할 수 있다.
        """
        out: list[Block] = []
        for e in elements:
            if getattr(e, "table", None) is not None:
                kind, text = "table", e.table.text()
            elif getattr(e, "is_picture", False):
                kind, text = "figure", getattr(e, "text", "") or ""
            elif getattr(e, "text", ""):
                kind, text = "text", e.text
            else:
                continue
            out.append(cls(idx=len(out), text=text.strip(), page=e.page,
                           is_heading=e.is_heading, element_index=e.index,
                           bbox=getattr(e, "bbox", None),
                           bbox_origin=getattr(e, "bbox_origin", "BOTTOMLEFT"),
                           kind=kind,
                           size_ratio=getattr(e, "size_ratio", None),
                           bold=getattr(e, "bold", False),
                           gap_before=getattr(e, "gap_before", None)))
        return out

    def dump(self) -> dict:
        d = {"idx": self.idx, "page": self.page, "text": self.text,
             "is_heading": self.is_heading, "element_index": self.element_index}
        if self.kind != "text":
            d["kind"] = self.kind
        if self.size_ratio is not None:
            d["size_ratio"] = self.size_ratio
            d["bold"] = self.bold
            d["gap_before"] = self.gap_before
        if self.bbox:
            d["bbox"] = self.bbox
            d["bbox_origin"] = self.bbox_origin
        return d


@dataclass
class Candidate:
    """구조 가설 후보 하나 (SPEC §2).

    `family` 는 **마커 계열**이다(dot_number, circled, kr_jang …). 도메인이 아니다.
    `depth` 는 자기계열 depth — 점번호 `1.1.1` 처럼 표면이 스스로 깊이를 말할 때만 있다.
    """
    id: str
    family: str
    depth: Optional[int] = None        # 자기계열 depth (없으면 None)
    surface: str = ""
    ordinal: Optional[Ordinal] = None
    doc: str = ""
    block_idx: int = 0
    offset: int = 0                    # 블록 안에서 마커가 시작한 위치
    end: int = 0                       # 마커가 끝난 위치
    page: int = 1
    element_index: int = 0
    text: str = ""                     # 블록 전문
    construction: str = "full"         # full | fragment (§5.1)
    in_paren: bool = False
    is_heading: bool = False
    # 블록의 좌표. 판별에는 안 쓰이고 **들여쓰기 증거**(S3)와 검수 화면만 쓴다.
    bbox: Optional[list[float]] = None

    guards: dict[str, float] = field(default_factory=dict)
    s: float = 0.0

    # --- S2 산출 (계열 정합) ------------------------------------------------
    # 자기 계열 안에서 구조로 인정됐는가. 사다리 없이 판정된다 — 서수 비교는
    # **같은 계열 안에서만** 일어나므로 레벨을 몰라도 된다.
    survives: bool = True
    family_note: str = ""
    chain: Optional[int] = None        # 속한 연속 단위 번호 (계열 안에서)
    # S5b 배치가 이미 판정한 후보. 다시 잔여로 올리지 않는다 — 그러면 두 번째 콜이
    # 같은 질문을 반복하고 목록이 영영 수렴하지 않는다.
    llm_verdict: str = ""

    # --- S3 산출 (사다리) ---------------------------------------------------
    level: Optional[int] = None        # 배정된 레벨. None = 미배정
    unassigned: bool = False
    assign_note: str = ""

    # --- S3 산출 ---------------------------------------------------------
    activated: bool = False
    activated_level: Optional[int] = None
    decision_note: str = ""
    # 최선(활성)과 차선(기각=0)의 점수 차. 작을수록 DP 가 못 가른 것이다.
    decision_margin: float = float("inf")
    transition_gain: float = 0.0       # 실제로 고른 전이의 점수

    # --- 제목 (S4 뒤) --------------------------------------------------------
    # `제7조` 는 좌표, `금융소비자의 기본적 권리` 는 이름이다.
    title: str = ""
    title_reason: str = ""

    @property
    def family_key(self) -> str:
        """사다리에 등재되는 키. 자기계열 depth 가 있으면 깊이까지가 한 계열이다."""
        return f"{self.family}:{self.depth}" if self.depth is not None else self.family

    @property
    def tail(self) -> str:
        return self.text[self.end:]

    def dump(self) -> dict:
        d = {"id": self.id, "family": self.family_key, "surface": self.surface,
             "block": self.block_idx, "offset": self.offset, "page": self.page,
             "s": round(self.s, 3), "guards": {k: round(v, 3) for k, v in self.guards.items()},
             "survives": self.survives, "level": self.level,
             "unassigned": self.unassigned, "activated": self.activated}
        if not self.survives:
            d["family_note"] = self.family_note
        if self.ordinal:
            d["ordinal"] = list(self.ordinal)
        if self.activated_level is not None:
            d["activated_level"] = self.activated_level
        if self.decision_note:
            d["decision"] = self.decision_note
        if self.title:
            d["title"] = self.title
        if self.assign_note:
            d["assign_note"] = self.assign_note
        return d


@dataclass
class Rung:
    """사다리 한 칸."""
    level: int
    families: list[str] = field(default_factory=list)
    reg_score: float = 0.0
    evidence: str = ""

    def dump(self) -> dict:
        return {"level": self.level, "families": sorted(self.families),
                "reg_score": round(self.reg_score, 3), "evidence": self.evidence}


@dataclass
class Ladder:
    """레벨 사다리 (SPEC §2). `[L0, L1, L2 …]`."""
    rungs: list[Rung] = field(default_factory=list)
    unregistered: list[str] = field(default_factory=list)   # 문지기에 걸린 계열
    # 순환 때문에 증거가 아니라 **임의 규칙으로** 층이 정해진 계열. 비어 있어야 정상이다.
    cycle_broken: list[str] = field(default_factory=list)
    unordered_pairs: list[str] = field(default_factory=list)
    n_pairs: int = 0                                        # 비교한 계열 쌍의 총수
    root: Optional[str] = None                              # 좌표 최상위로 접은 계열
    flattened: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(self.rungs)

    def level_of(self, family_key: str) -> Optional[int]:
        for r in self.rungs:
            if family_key in r.families:
                return r.level
        return None

    def dump(self) -> dict:
        return {"depth": self.depth, "rungs": [r.dump() for r in self.rungs],
                "unregistered": sorted(self.unregistered),
                "cycle_broken": sorted(self.cycle_broken),
                "unordered_pairs": sorted(self.unordered_pairs), "n_pairs": self.n_pairs,
                "root": self.root, "flattened": sorted(self.flattened),
                "notes": self.notes}


@dataclass(frozen=True)
class ScopeStack:
    """DP 상태 (SPEC §2). 레벨별 마지막 활성 서수. `None` 이면 그 레벨은 닫혀 있다.

    불변으로 둔다 — DP 는 상태를 키로 병합하므로 해시가 되어야 한다.
    """
    last: tuple[Optional[Ordinal], ...]

    @classmethod
    def empty(cls, depth: int) -> "ScopeStack":
        return cls(tuple([None] * depth))

    def open_levels(self) -> list[int]:
        return [i for i, v in enumerate(self.last) if v is not None]

    def activate(self, level: int, ordinal: Optional[Ordinal]) -> "ScopeStack":
        """해당 레벨을 갱신하고 **하위 레벨 스코프를 닫는다**(SPEC §4 S3)."""
        nxt = list(self.last)
        nxt[level] = ordinal if ordinal is not None else ()
        for deeper in range(level + 1, len(nxt)):
            nxt[deeper] = None
        return ScopeStack(tuple(nxt))


@dataclass
class Node:
    """트리 마디 (SPEC §2)."""
    level: int
    ordinal: Optional[Ordinal]
    family: str
    surface: str
    block_idx: int
    page: int
    element_index: int
    candidate_id: str
    title: str = ""                    # 구역의 이름 (좌표와 별개)
    title_reason: str = ""
    activation_reason: str = ""
    children: list["Node"] = field(default_factory=list)
    span: tuple[int, int] = (0, 0)     # 이 마디가 덮는 블록 범위
    # 이 마디에 딸린 표·그림. **자식 마디가 아니라 잎**이다 — 구역을 열지 않으므로
    # 트리의 마디가 될 수 없지만, 어느 구역의 것인지는 말해야 한다.
    attachments: list[dict] = field(default_factory=list)

    def dump(self) -> dict:
        d = {"level": self.level, "family": self.family, "surface": self.surface,
             "title": self.title, "title_reason": self.title_reason,
             "ordinal": list(self.ordinal) if self.ordinal else None,
             "block": self.block_idx, "page": self.page, "span": list(self.span),
             "candidate": self.candidate_id, "reason": self.activation_reason,
             "children": [c.dump() for c in self.children]}
        if self.attachments:
            d["attachments"] = self.attachments
        return d

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Fingerprint:
    """재현 판정 키 (SPEC §2, §7) — 발화 family 집합 + 유도된 중첩순서."""
    families: list[str] = field(default_factory=list)
    order: list[list[str]] = field(default_factory=list)   # 레벨별 family

    def key(self) -> str:
        return "|".join(">".join(sorted(lv)) for lv in self.order) or "(빈 사다리)"

    def dump(self) -> dict:
        return {"key": self.key(), "families": sorted(self.families), "order": self.order}


@dataclass
class StructureResult:
    """산출물 전체 (SPEC §2)."""
    doc: str
    tree: list[Node] = field(default_factory=list)       # 최상위 마디들
    ladder: Ladder = field(default_factory=Ladder)
    candidates: list[Candidate] = field(default_factory=list)
    fitness_score: float = 0.0
    fitness_passed: bool = False
    tier: str = "cold"                                   # hot | warm | cold
    audit_log: list[str] = field(default_factory=list)
    fingerprint: Fingerprint = field(default_factory=Fingerprint)
    residual: list[str] = field(default_factory=list)    # LLM 배치로 갈 애매 후보
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    applied: dict[str, Any] = field(default_factory=dict)   # 이 문서에 준 힌트

    def activated(self) -> list[Candidate]:
        return [c for c in self.candidates if c.activated]

    def nodes(self) -> list[Node]:
        out: list[Node] = []
        for root in self.tree:
            out.extend(root.walk())
        return out

    def dump(self) -> dict:
        return {
            "doc": self.doc,
            "fitness": {"score": round(self.fitness_score, 3),
                        "passed": self.fitness_passed, "tier": self.tier},
            "fingerprint": self.fingerprint.dump(),
            "ladder": self.ladder.dump(),
            "tree": [n.dump() for n in self.tree],
            "candidates": [c.dump() for c in self.candidates],
            "residual": self.residual,
            "audit_log": self.audit_log,
            "applied": self.applied,
            "stats": self.stats,
            "warnings": self.warnings,
        }
