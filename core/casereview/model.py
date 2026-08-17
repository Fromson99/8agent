"""검토의 다섯 타입 — 사실·쟁점·규범·포섭·결론 (docs/REVIEW.md §다섯 타입).

**도메인 무관**이다. 사실·쟁점·규범·포섭·결론은 규칙 기반 검토 일반의 형태라
사내 규정 준수·계약 검토·감사에 그대로 간다. 법률 특수성(관문 질문·규제축·
조항호 논리 표지·위임 간선)은 플러그인으로 빠진다.

설계 규율 둘:

1. **필드는 최종 크기, 구현은 지금 크기.** `Optional` 로 둔 칸(시점·증거·
   리스크·버전)은 지금 비어 있다 — 나중 기능이 그 칸을 채우면 파이프라인
   구조는 그대로다. 필드가 아예 없으면 전면 재작업이 된다.
2. **파이프라인이 아니라 상태.** 포섭의 '불명'이 새 쟁점으로 되돌아가므로
   (docs/REVIEW.md 핵심 ②) 단계들이 하나의 `ReviewState` 를 갱신한다.

세 트랙(C 해석검토 · B 적법성검토 · A 개정추적)이 이 타입들을 공유한다 —
B 는 `Fact.tense="계획"`, A 는 `Norm.version` + `Delta` 만 더 쓴다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional

# 포섭 판정 — '불명'이 곧 메인 쟁점이다 (docs/REVIEW.md 핵심 ②)
Judgment = Literal["충족", "불충족", "불명", "해당없음"]
# 결론 — 이분법을 쓰지 않는다. 실무의 답은 대개 조건부다.
Conclusion = Literal["가능", "불가", "조건부", "판단보류"]


def _nid(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------- ① 사실
@dataclass
class Fact:
    """사실 항목 — 주체·행위·대상의 삼각형 하나.

    트랙 B(적법성 검토)의 "아키텍처 해체"(주체·객체·행위)와 자료구조가 같다.
    다른 것은 시제뿐이다 — 검토는 "했다", 컴플라이언스는 "할 것이다".
    """
    text: str                              # 원문 그대로 — 정본은 언제나 입력이다
    subject: str = ""                      # 주체 — 누가
    action: str = ""                       # 행위 — 무엇을 한다
    object: str = ""                       # 대상 — 무엇을
    tense: Literal["과거", "계획"] = "과거"
    id: str = field(default_factory=lambda: _nid("f"))
    # 나중 칸 — 타임라인·증거 태깅이 채운다 (지금은 비운다)
    when: Optional[str] = None
    evidence: Optional[list] = None
    role: Optional[Literal["요건사실", "간접사실"]] = None


# ---------------------------------------------------------------- ② 쟁점
@dataclass
class Issue:
    """쟁점 — Yes/No 로 답할 수 있게 압축된 질문 하나.

    `gate` 는 관문 질문("이 사안에 개인정보가 있는가")이고, 이것이 어느 법을
    볼지 정한다. `card` 는 위키 쟁점 카드 슬러그 — 판단 축과 선례를 들고 온다.
    `from_req` 가 있으면 이 쟁점은 포섭의 '불명'에서 승격된 것이다(되먹임).
    """
    question: str                          # 압축된 쟁점 질문
    gate: str = ""                         # 관문 질문 — 이 법이 걸리는 이유
    axis: str = ""                         # 판단 축 (카드에서 옴)
    regulation: Optional[Literal["수평", "수직", "충돌"]] = None
    card: Optional[str] = None             # 위키 쟁점 카드 slug
    norms: list = field(default_factory=list)      # Norm.id
    status: Literal["미해결", "해결"] = "미해결"
    id: str = field(default_factory=lambda: _nid("i"))
    from_req: Optional[str] = None         # 되먹임 출처 (Sub.req_id)
    by_net: bool = False                   # 결정론 안전망이 세운 쟁점인가 (품질 표시)
    why: str = ""                          # 왜 이 쟁점·이 카드인가 — LLM 이 적는다 (검수·채점용)
    core: bool = True                      # 핵심(질문이 직접 묻는 것) / 부수(딸려 온 것)


# ---------------------------------------------------------------- ③ 규범
@dataclass
class Req:
    """요건 하나 — 잎이거나 가지다.

    단위는 **구조 스토어의 마디**다(조 → 항 → 호). 호는 한국 법령에서 요건의
    자연 단위이고 이미 마디로 파싱돼 있어서, 텍스트를 다시 자를 이유가 없다.
    `node` 를 들고 있으므로 id 가 좌표에서 나오고(= 실행마다 같다), 원장·되먹임이
    조문을 직접 가리킨다.

    `op` 가 있으면 가지(AND/OR/NOT)다. 지금은 계층만 세우고 연산자는 비어 있다 —
    요건 분해(docs/REVIEW.md 구현 2단계)가 논리 표지를 읽어 그 칸을 채운다.
    """
    text: str
    op: Optional[Literal["AND", "OR", "NOT"]] = None
    children: list = field(default_factory=list)   # list[Req]
    concepts: list = field(default_factory=list)   # 불확정 개념 ("정당한 사유")
    id: str = field(default_factory=lambda: _nid("r"))
    proviso: bool = False                  # 단서(다만…)에서 온 요건인가
    node: Optional[int] = None             # 구조 스토어 마디 — 요건의 좌표

    @staticmethod
    def coord_id(doc_id: str, node) -> str:
        """좌표에서 나온 안정 id — 재검토해도 같은 요건은 같은 id 다."""
        return f"r{(doc_id or '')[:6]}-{node}"


@dataclass
class Norm:
    """규범 하나 — 좌표 + 요건 트리 + 효과.

    지금은 요건 트리가 얕다(조문 텍스트에서 뽑은 요건 목록). 논리 표지
    승격(2단계)이 붙으면 같은 자리에 AND/OR/단서가 채워진다.
    """
    doc: str = ""                          # 문서명
    doc_id: str = ""
    node: Optional[int] = None             # 구조 스토어 마디
    path: str = ""                         # 사람이 읽는 좌표 ("제18조 ▸ ②")
    subject: str = ""                      # 수범자
    action: str = ""                       # 규율 대상 행위
    reqs: list = field(default_factory=list)       # list[Req]
    effect: str = ""                       # 법률효과
    excludes: list = field(default_factory=list)   # 배제 간선 (…에도 불구하고)
    parent_norm: Optional[str] = None      # 위임 상위 (법 ← 시행령 ← 규정)
    id: str = field(default_factory=lambda: _nid("n"))
    version: Optional[str] = None          # 트랙 A — 시행일/버전


# ---------------------------------------------------------------- ④ 포섭
@dataclass
class Sub:
    """포섭 — 요건 하나에 사실을 댄 결과.

    '불명'은 실패가 아니라 **발견**이다 — 실무에서 다투는 자리이고, 되먹임에서
    새 쟁점(Issue.from_req)이 되어 다음 회수의 목표가 된다.
    """
    issue_id: str
    norm_id: str
    req_id: str
    req_text: str = ""
    judgment: Judgment = "불명"
    facts: list = field(default_factory=list)      # 근거 Fact.id
    cites: list = field(default_factory=list)      # 근거 조문 좌표
    reason: str = ""
    id: str = field(default_factory=lambda: _nid("s"))


# ---------------------------------------------------------------- ⑤ 결론
@dataclass
class Verdict:
    """쟁점 하나의 결론 — 이분법이 아니라 조건부까지."""
    issue_id: str
    conclusion: Conclusion = "판단보류"
    summary: str = ""
    unmet: list = field(default_factory=list)      # 미충족·불명 Req.id
    actions: list = field(default_factory=list)    # 다음 손 (보완·구조화·출구)
    id: str = field(default_factory=lambda: _nid("v"))
    risk: Optional[dict] = None            # 나중 — {형사·행정·민사 등급}


# ---------------------------------------------------------------- 상태
@dataclass
class ReviewState:
    """검토 하나의 전체 상태 — 단계들이 이것을 갱신한다.

    트랙 B 의 대안 병렬 평가("이렇게 바꾸면?")는 상태를 복수로 두면 된다 —
    타입 변경이 아니다.
    """
    question: str = ""                     # 사용자의 원 요청
    track: Literal["해석", "적법성", "개정"] = "해석"
    facts: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    norms: list = field(default_factory=list)
    # 정의 마디 — **규범 상한(NORM_SECTIONS) 밖의 별도 칸**이다.
    # 정의는 판단 대상이 아니라 용어 해설이라 6칸을 쓸 이유가 없다. 그런데
    # 규범 자리에 넣으면 둘 다 안 된다(2026-08-17 골든 v2 네 판 실측):
    #   앞자리에 넣으면 정답을 상한 밖으로 밀어내고(회수 77%→73%),
    #   뒷자리에 넣으면 prior+rest 가 이미 6칸을 꽉 채워(쟁점당 6.0) 하나도 못 들어간다.
    # 그래서 칸을 따로 뗀다 — 회수 판정에도 세고, 판정 프롬프트에도 실린다.
    glossary: list = field(default_factory=list)
    subs: list = field(default_factory=list)
    verdicts: list = field(default_factory=list)
    trail: list = field(default_factory=list)      # 단계 기록 (사다리와 같은 규율)
    # 해석 트랙의 사안 수준 판정 — {direction, reason, basis}. 쟁점별 결론
    # (verdicts)과 별개다: 그쪽은 요건표의 보수적 접기(다툼 지점 관측)이고,
    # 이쪽이 법제처 회답 형식의 답이다 (pipeline.INTERPRET_SYSTEM 머리).
    overall: Optional[dict] = None
    rid: str = field(default_factory=lambda: _nid("R"))
    error: str = ""

    # --- 조회 도우미 — 되먹임과 렌더가 쓴다
    def issue(self, iid: str) -> Optional[Issue]:
        return next((i for i in self.issues if i.id == iid), None)

    def norm(self, nid: str) -> Optional[Norm]:
        return next((n for n in self.norms if n.id == nid), None)

    def fact(self, fid: str) -> Optional[Fact]:
        return next((f for f in self.facts if f.id == fid), None)

    def unresolved(self) -> list:
        """'불명'인 포섭 — 되먹임의 씨앗이자 이번 검토의 진짜 쟁점."""
        return [s for s in self.subs if s.judgment == "불명"]

    def step(self, stage: str, count: int, note: str = "") -> None:
        self.trail.append({"stage": stage, "count": count, "note": note})

    def to_dict(self) -> dict:
        return {
            "rid": self.rid, "question": self.question, "track": self.track,
            "facts": [asdict(f) for f in self.facts],
            "issues": [asdict(i) for i in self.issues],
            "norms": [asdict(n) for n in self.norms],
            "subs": [asdict(s) for s in self.subs],
            "verdicts": [asdict(v) for v in self.verdicts],
            "trail": self.trail,
            **({"overall": self.overall} if self.overall else {}),
            **({"error": self.error} if self.error else {}),
        }


def req_leaves(reqs: list) -> list:
    """요건 트리를 잎만 평평하게 — 포섭은 잎 단위로 판정한다."""
    out: list = []
    for r in reqs:
        if r.children:
            out.extend(req_leaves(r.children))
        else:
            out.append(r)
    return out
