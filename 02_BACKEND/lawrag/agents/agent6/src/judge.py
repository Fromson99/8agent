"""T-A6.5 판정 — **LLM 단독 판정 + 자기일관성** (AGENT6 §5-4).

판정자는 하나뿐이다. 문자열 매칭으로 위반을 판정하는 코드는 이 파일에 없다.

## lexicon 판정기를 없앤 이유

전에는 항목마다 `lexicon: {hit, guard}` 를 두고 전사에서 표현을 찾아 판정하는
`judge_deterministic()` 이 있었다. 적대적 검증에서 그 방식이 무너졌다 — 실제로 재현된 것들:

  · "지수가 여기서 더 내려갈 일은 없으니 안심하셔도 됩니다" → D-20 PASS (표현 목록에 없다)
  · 스펙 자신의 few_shot FAIL 예시 3건이 PASS 로 샘
  · guard 한 어절("원금 보장 안 됩니다만, …")로 위반이 통째로 소거됨
  · 존재형이 화자를 보지 않아 **고객이 "설명 못 들었다"고 한 말이 고지 이행의 증거**가 됨

한국어는 같은 뜻을 백 가지로 말한다. 목록으로 따라잡는 것은 원리적으로 불가능하고,
따라잡지 못한 자리는 조용한 PASS 가 된다. 그래서 판정표를 통째로 버렸다.

`cross_signal.py`(lexicon↔LLM 불일치 감지)도 같은 이유로 **삭제**했다. 두 관측기 중
하나가 사라졌으므로 교차할 것이 없다. 그 자리(모호함 감지)는 아래 **자기일관성**이 맡는다.

## 자기일관성 k회

같은 항목을 같은 프롬프트로 **독립 호출** k번(기본 3) 판정하고 이렇게 합친다.

    한 번이라도 FAIL      → FAIL      부재형 위반은 한 번이라도 걸리면 걸린 것이다.
    k회 만장일치 PASS     → PASS      다수결로 PASS 를 밀지 않는다.
    그 밖(갈림·UNCLEAR)   → UNCLEAR   판정자가 스스로와 다투는 항목은 사람이 본다.

호출이 실패해 회차를 다 채우지 못했으면 남은 회차가 전부 PASS 여도 PASS 가 아니다 —
k회 만장일치를 **확인하지 못한** 것이고, 확인하지 못한 것을 통과로 적으면 그것이 곧
놓침이다. FAIL 은 반대로 회차가 모자라도 유효하다(걸린 것은 걸린 것이다).

왜 다수결이 아닌가. 3회 중 2회 PASS 를 PASS 로 밀면, 모델이 흔들린다는 사실 자체가
리포트에서 사라진다. 흔들림은 "이 항목은 이 전사에서 애매하다"는 관측이고, 그 관측이
바로 준법감시가 봐야 할 것이다(§6). 반대로 FAIL 은 한 번으로 충분하다 — 거짓 FAIL 의
비용은 재설명 몇 분이고, 거짓 PASS 의 비용은 불완전판매가 그대로 통과하는 것이다(§0 원칙 4).

## 후처리 3종 — 비대칭 임계를 지키는 자리

lexicon 판정표가 하던 "의심 쪽으로 기울이기"를 이제 이 셋이 한다. 순서가 중요하다.

    (c) 인용 좌표 대조   전사에 없는 인용·좌표가 틀린 인용을 **버린다**
    (b) 화자 검사       존재형의 근거는 PB 발화여야 한다. 고객 발화는 고지의 증거가 아니다
    (a) 인용 없는 판정   있음을 주장하면서 인용을 못 대면 UNCLEAR 로 강등

(a) 는 "없음의 주장"을 예외로 둔다 — 부재형 PASS("금지 표현이 없다")와 존재형
FAIL("고지가 전사 어디에도 없다")은 인용할 스팬이 원리적으로 없다. 이 둘까지 강등하면
정상 통화의 리포트가 전부 UNCLEAR 가 되어 아무것도 판정하지 못한다.

후처리는 **회차마다** 적용한 뒤 합친다. 1회차가 지어낸 인용으로 PASS 했다면 그 회차는
UNCLEAR 로 내려가고, 그러면 만장일치가 깨져 항목 전체가 UNCLEAR 가 된다. 합친 뒤에
후처리하면 그 회차의 흠이 다른 회차의 인용에 가려진다.

## LLM 을 쓸 수 없으면

조용히 강등하지 않는다. **"점검하지 못했다"를 "통과"로 만드는 것이 이 시스템에서
가장 나쁜 실패다.** 키가 없거나 호출이 실패하면 그 항목은 UNCLEAR + 준법감시큐로 가고,
사유가 리포트에 실리며, CLI 는 판정 결과와 구별되는 종료코드로 끝난다.

## 녹화/재생

호출은 전부 `llm_cache.RecordingClient` 를 지난다. `live`(호출만)·`record`(호출+저장)·
`replay`(저장분만, 키 불필요·결정론) 셋이며 규약은 그 파일에 있다. 테스트가 키 없이
도는 길은 이제 그것뿐이다 — 결정론 판정기가 없어졌기 때문이다.

## method 값 (리포트를 읽는 사람이 "이 판정이 어떻게 나왔나"를 아는 칸)

    llm                     LLM 판정 — k=1 이거나 k회가 만장일치였다(회차는 사유에 적힌다)
    llm_self_consistency    회차가 갈렸거나 모자라, 합치기 규칙이 결과를 정했다
    llm_missing             배치 응답에 이 항목이 없었다
    llm_unavailable         LLM 을 쓸 수 없었다 — 점검하지 못했다
    evidence_missing        인용을 못 대서 강등했다
    evidence_unverified     전사에 없는/좌표가 틀린 인용이라 버리고 강등했다
    evidence_speaker        존재형인데 고객 발화만 근거였다
    derived                 aggregate 가 구성 항목으로 계산했다 (§9-5)
    when                    aggregate: when 이 비활성으로 판정했다
    basis_unresolved        aggregate: 근거 미해소로 **점검하지 못했다**
    disabled                aggregate: 스펙에서 꺼 둔 항목(enabled=false)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from lawrag.agents.agent6.src import context_asm, llm_cache, schema
from lawrag.agents.agent6.src.context_asm import Batch, BasisLoader
from lawrag.agents.agent6.src.llm_cache import CacheMiss, LLMUnavailable
from lawrag.agents.agent6.src.preprocess import Prepared, Transcript, Utterance

VERDICTS = ("PASS", "FAIL", "UNCLEAR")

# --- method 정본 목록 (모듈 설명의 표와 같다. 어긋나면 표가 정본이다) -----------
METHOD_LLM = "llm"
METHOD_SELF_CONSISTENCY = "llm_self_consistency"
METHOD_MISSING = "llm_missing"
METHOD_UNAVAILABLE = "llm_unavailable"
METHOD_NO_EVIDENCE = "evidence_missing"
METHOD_BAD_QUOTE = "evidence_unverified"
METHOD_CUSTOMER_ONLY = "evidence_speaker"   # 존재형인데 고객 발화만 근거였다
METHOD_DERIVED = "derived"                 # aggregate 가 붙인다
METHOD_WHEN = "when"                       # aggregate 가 붙인다
METHOD_BASIS_BLOCKED = "basis_unresolved"  # aggregate 가 붙인다 — 점검하지 못한 항목
METHOD_DISABLED = "disabled"               # aggregate 가 붙인다

METHODS = (METHOD_LLM, METHOD_SELF_CONSISTENCY, METHOD_MISSING, METHOD_UNAVAILABLE,
           METHOD_NO_EVIDENCE, METHOD_BAD_QUOTE, METHOD_CUSTOMER_ONLY,
           METHOD_DERIVED, METHOD_WHEN, METHOD_BASIS_BLOCKED, METHOD_DISABLED)

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "section_id": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["section_id", "text"],
                            "additionalProperties": False,
                        },
                    },
                    "reason": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["item_id", "verdict", "evidence", "reason", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["judgments"],
    "additionalProperties": False,
}


@dataclass
class Judgment:
    """항목 하나의 판정 — 리포트 행의 재료."""
    item_id: str
    verdict: str                                  # PASS | FAIL | UNCLEAR
    evidence: list[schema.EvidenceSpan] = field(default_factory=list)
    reason: str = ""
    confidence: str = "low"
    method: str = METHOD_LLM
    notes: list[str] = field(default_factory=list)
    attempts: list[str] = field(default_factory=list)   # 자기일관성 회차별 판정

    def downgrade(self, reason: str, *, method: Optional[str] = None) -> "Judgment":
        """UNCLEAR 로 내린다. **왜 내렸는지 없이는 내리지 않는다.**"""
        self.verdict = "UNCLEAR"
        self.confidence = "low"
        self.notes.append(reason)
        if method:
            self.method = method
        return self


@dataclass
class Judged:
    """판정 국면 전체의 산출."""
    judgments: dict[str, Judgment] = field(default_factory=dict)
    mode: str = "llm"
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    llm_totals: dict[str, Any] = field(default_factory=dict)
    batches: list[Batch] = field(default_factory=list)
    basis_audit: dict[str, Any] = field(default_factory=dict)
    # 점검하지 못한 항목 — 있으면 이 실행은 "판정"이 아니라 "점검 실패"다.
    unavailable: list[str] = field(default_factory=list)
    calls: int = 0                                # 실제 요청 수 (배치 × 자기일관성 회차)
    seconds: float = 0.0

    @property
    def usable(self) -> bool:
        return not self.unavailable


@dataclass
class JudgeConfig:
    """판정 국면 설정. 기본값이 곧 운영 설정이다."""
    llm_mode: str = "live"            # live | record | replay (llm_cache.MODES)
    consistency: int = 3              # 자기일관성 회차 k
    per_item: bool = False            # 배치 대신 항목당 한 호출 (§5-4)
    max_batch: int = 6
    model: Optional[str] = None
    cache_dir: Any = llm_cache.DEFAULT_CACHE_DIR

    def __post_init__(self) -> None:
        if self.llm_mode not in llm_cache.MODES:
            raise ValueError(f"llm_mode 는 {llm_cache.MODES} 중 하나여야 합니다 "
                             f"(받은 값 '{self.llm_mode}')")
        if self.consistency < 1:
            raise ValueError(f"consistency 는 1 이상이어야 합니다 (받은 값 {self.consistency})")


# ===========================================================================
# 후처리 3종 (§비대칭 임계)
# ===========================================================================

def requires_evidence(item_type: str, verdict: str) -> bool:
    """이 판정이 인용을 **댈 수 있어야 하는** 판정인가.

    규칙은 "있음을 주장하는 판정은 반드시 인용한다"이다:
        존재형 PASS(말했다) · 부재형 FAIL(말했다) · 충분성형 PASS/FAIL(정도를 판정했다)
    반대로 부재형 PASS 와 존재형 FAIL 은 **없음의 주장**이라 인용할 스팬이 없다.
    """
    if item_type == "존재형":
        return verdict == "PASS"
    if item_type == "부재형":
        return verdict == "FAIL"
    return verdict in ("PASS", "FAIL")


def postprocess(judgment: Judgment, item: schema.ChecklistItem,
                transcript: Transcript) -> Judgment:
    """(c) 좌표 대조 → (b) 화자 검사 → (a) 인용 없는 판정 강등. 회차마다 부른다.

    좌표 대조 자체는 `Transcript.verify_quote(인용, 좌표)` 가 한다(길이 하한·발화 경계·
    좌표 실재 여부). 여기서 다시 세지 않는다 — 같은 규칙을 두 곳에 두면 언젠가 갈라진다.
    """
    kept: list[tuple[schema.EvidenceSpan, Optional[Utterance]]] = []
    dropped = 0
    for ev in judgment.evidence:
        got = transcript.verify_quote(ev.text or "", ev.section_id)
        if not got.found:
            dropped += 1
            judgment.notes.append(
                f"인용을 버렸습니다({got.reason}): \"{(ev.text or '')[:40]}\"")
            continue
        # 좌표가 맞았으므로 전사가 가진 값(타임스탬프·원문)으로 다시 만든다. 인용문의
        # 표기는 판정자가 다듬었을 수 있고, 리포트에 실리는 것은 전사의 문장이어야 한다.
        kept.append((got.utterance.evidence(), got.utterance))

    judgment.evidence = [ev for ev, _ in kept]

    # (b) 존재형의 근거는 PB 발화여야 한다 — 고객이 "설명 못 들었다"고 한 말이 고지 이행의
    #     증거로 쓰이던 구멍을 여기서 막는다. 화자를 모르는 전사(미상)는 고객으로 몰지
    #     않는다(평문 전사의 모든 존재형이 UNCLEAR 가 되어 리포트가 못 쓰게 된다).
    if item.type == "존재형" and judgment.verdict == "PASS" and kept:
        customer = [u for _, u in kept if u is not None and u.is_customer()]
        others = [u for _, u in kept if u is None or not u.is_customer()]
        if customer and not others:
            judgment.evidence = []
            return judgment.downgrade(
                f"고객 발화만 근거였습니다({', '.join(u.section_id for u in customer)}) — "
                f"고객이 한 말은 판매자의 고지 이행을 입증하지 않습니다",
                method=METHOD_CUSTOMER_ONLY)
        if customer:
            judgment.evidence = [ev for ev, u in kept
                                 if u is None or not u.is_customer()]
            judgment.notes.append(
                f"고객 발화 인용 {len(customer)}건을 근거에서 뺐습니다"
                f"({', '.join(u.section_id for u in customer)})")

    # (a) 있음을 주장하면서 인용을 못 대면 판정이 아니다(§0 원칙 3).
    if requires_evidence(item.type, judgment.verdict) and not judgment.evidence:
        judgment.downgrade(
            "인용을 대지 못한 판정입니다 — 근거 없는 판정은 무효입니다(§0 원칙 3)",
            method=METHOD_BAD_QUOTE if dropped else METHOD_NO_EVIDENCE)
    return judgment


# ===========================================================================
# 자기일관성 합치기
# ===========================================================================

def combine(item: schema.ChecklistItem, attempts: Sequence[Judgment],
            k: int) -> Judgment:
    """회차별 판정 → 항목의 판정. 규칙은 모듈 설명의 표 그대로다."""
    if not attempts:
        j = Judgment(item_id=item.id, verdict="UNCLEAR", confidence="low",
                     method=METHOD_UNAVAILABLE)
        j.reason = "판정 응답을 하나도 받지 못했습니다 — 이 항목은 점검하지 못했습니다"
        return j

    verdicts = [a.verdict for a in attempts]
    short = len(attempts) < k          # 회차를 다 받지 못했다 (호출 실패·응답 누락)
    if "FAIL" in verdicts:
        # FAIL 은 한 번으로 충분하다 — 회차가 모자라도 걸린 것은 걸린 것이다.
        base = next(a for a in attempts if a.verdict == "FAIL")
        final = "FAIL"
    elif all(v == "PASS" for v in verdicts) and not short:
        base = attempts[0]
        final = "PASS"
    else:
        # PASS 와 UNCLEAR 가 섞였거나, 전부 UNCLEAR 거나, 회차가 모자라다.
        # 마지막 경우까지 PASS 로 두지 않는 이유: k회 만장일치를 확인하지 못했는데
        # 통과로 적으면 **하지 못한 점검이 통과가 된다**(§0 원칙 4).
        base = next((a for a in attempts if a.verdict != "PASS"), attempts[0])
        final = "UNCLEAR"

    unanimous = len(set(verdicts)) == 1 and not short
    j = Judgment(item_id=item.id, verdict=final, evidence=list(base.evidence),
                 reason=base.reason, method=base.method if unanimous
                 else METHOD_SELF_CONSISTENCY,
                 attempts=list(verdicts))

    # confidence — 만장일치면 회차 중 가장 낮은 것을, 갈리면 low. 갈렸다는 사실 자체가
    # "확신할 수 없다"는 관측이므로 회차의 자기 신고를 그대로 쓰지 않는다.
    if unanimous:
        j.confidence = max((a.confidence for a in attempts),
                           key=lambda c: schema.CONFIDENCE_ORDER.index(c)
                           if c in schema.CONFIDENCE_ORDER else 2)
    else:
        j.confidence = "low"

    # 회차 사이의 사정은 전부 남긴다 — 큐를 읽는 사람이 "왜 갈렸나"를 봐야 한다.
    seen: set[str] = set()
    for a in attempts:
        for n in a.notes:
            if n not in seen:
                seen.add(n)
                j.notes.append(n)

    if short:
        j.notes.append(f"자기일관성 {k}회 중 {len(attempts)}회만 응답을 받았습니다")
    if k > 1:
        line = f"자기일관성 {len(attempts)}회: {'/'.join(verdicts)}"
        if final == "FAIL" and not unanimous:
            line += " — 한 번이라도 FAIL 이면 FAIL 로 본다"
        elif final == "UNCLEAR" and short and all(v == "PASS" for v in verdicts):
            line += f" — {k}회를 채우지 못해 통과로 확정하지 않는다"
        elif final == "UNCLEAR" and not unanimous:
            line += " — 판정이 갈려 PASS 로 밀지 않는다"
        j.notes.append(line)
    return j


# ===========================================================================
# 배치 응답 해석
# ===========================================================================

def _parse_batch(payload: Any, batch: Batch, transcript: Transcript
                 ) -> tuple[dict[str, Judgment], list[str], list[str]]:
    """배치 응답 → 회차 판정. (판정, 빠진 항목, 잡음) — 빠진 항목은 조용히 사라지지 않는다."""
    rows: dict[str, Any] = {}
    stray: list[str] = []
    for row in (payload or {}).get("judgments") or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("item_id") or "").strip()
        if rid in batch.item_ids:
            rows.setdefault(rid, row)
        else:
            stray.append(rid or "(id 없음)")

    out: dict[str, Judgment] = {}
    missing: list[str] = []
    for ctx in batch.contexts:
        item = ctx.item
        row = rows.get(item.id)
        if row is None:
            missing.append(item.id)
            continue
        verdict = str(row.get("verdict") or "").upper()
        if verdict not in VERDICTS:
            verdict = "UNCLEAR"
        evidence: list[schema.EvidenceSpan] = []
        dropped = 0
        for e in row.get("evidence") or []:
            text = str((e or {}).get("text") or "").strip()
            sid = str((e or {}).get("section_id") or "").strip() or None
            if not text or not sid:
                dropped += 1                  # 좌표 없는 인용은 인용이 아니다(§0 원칙 3)
                continue
            evidence.append(schema.EvidenceSpan(text=text, section_id=sid))
        j = Judgment(item_id=item.id, verdict=verdict, evidence=evidence,
                     reason=str(row.get("reason") or "").strip(),
                     confidence=str(row.get("confidence") or "medium"),
                     method=METHOD_LLM)
        if j.confidence not in schema.CONFIDENCE_ORDER:
            j.confidence = "medium"
        if dropped:
            j.notes.append(f"좌표(발화NNN) 없는 인용 {dropped}건을 버렸습니다")
        out[item.id] = postprocess(j, item, transcript)
    return out, missing, sorted(set(stray))


# ===========================================================================
# 진입점
# ===========================================================================

def _unavailable(item: schema.ChecklistItem, why: str) -> Judgment:
    """점검하지 못한 항목. **PASS 로 만들지 않는다** — 못 한 점검은 놓침이다."""
    j = Judgment(item_id=item.id, verdict="UNCLEAR", confidence="low",
                 method=METHOD_UNAVAILABLE)
    j.reason = f"판정하지 못했습니다 — {why}"
    j.notes.append("LLM 판정을 받지 못해 준법감시 검토로 보냅니다(점검 실패)")
    return j


def run(prepared: Prepared, *, config: Optional[JudgeConfig] = None,
        loader: Optional[BasisLoader] = None, llm: Any = None) -> Judged:
    """활성 항목(파생 제외)을 판정한다.

    `llm` 을 직접 넘길 수 있다 — 테스트가 가짜 클라이언트를 꽂아 판정 경로를 실제로
    돌려 보기 위해서다. 넘긴 것도 녹화 래퍼로 감싸 호출 수를 같은 자리에서 센다.
    """
    cfg = config or JudgeConfig()
    items = prepared.judgeable_items()
    tr = prepared.transcript
    out = Judged()
    started = time.monotonic()

    ld = loader or BasisLoader()
    batches = context_asm.build_batches(items, tr, loader=ld,
                                        per_item=cfg.per_item, max_batch=cfg.max_batch)
    out.batches = batches
    out.basis_audit = context_asm.audit(batches)
    out.warnings.extend(ld.warnings)
    if ld.source != "basis.load_excerpt":
        out.notes.append(f"근거 발췌 적재기: {ld.source}")
    missing_basis = out.basis_audit.get("missing_excerpts") or {}
    if missing_basis:
        out.notes.append(
            f"근거 발췌가 없는 항목 {len(missing_basis)}개 — 운영정의·few_shot 만으로 판정했습니다 "
            f"({', '.join(sorted(missing_basis)[:6])}{'…' if len(missing_basis) > 6 else ''})")

    # --- 클라이언트 ---------------------------------------------------------
    try:
        client = (llm_cache.wrap(llm, mode=cfg.llm_mode, cache_dir=cfg.cache_dir)
                  if llm is not None
                  else llm_cache.open_client(cfg.llm_mode, model=cfg.model,
                                             cache_dir=cfg.cache_dir))
    except LLMUnavailable as exc:
        out.mode = "판정 실패(LLM 없음)"
        out.warnings.append(
            f"{exc} — 판정자가 없으므로 **아무 항목도 점검하지 못했습니다**. "
            f"결과를 통과로 읽지 마십시오")
        out.judgments = {i.id: _unavailable(i, str(exc)) for i in items}
        out.unavailable = [i.id for i in items]
        out.seconds = time.monotonic() - started
        return out

    k = cfg.consistency
    out.notes.append(f"판정 호출 계획: 배치 {len(batches)}개 × 자기일관성 {k}회 "
                     f"= {len(batches) * k}회 (모드 {cfg.llm_mode})")

    # --- 배치 × 회차 --------------------------------------------------------
    attempts: dict[str, list[Judgment]] = {i.id: [] for i in items}
    misses: dict[str, list[str]] = {}          # 항목 → 응답에서 빠진 회차
    for batch in batches:
        for n in range(1, k + 1):
            # 회차를 kind 에 적는다 — 녹화 키가 kind 를 포함하므로 회차마다 다른 녹화가
            # 되고, 재생에서 자기일관성의 **갈림까지** 그대로 재현된다(llm_cache 설명).
            kind = f"agent6-판정-{batch.batch_id}-{n}회차"
            payload = None
            try:
                payload = client.structured(kind=kind, system=batch.system,
                                            user=batch.user(), schema=RESPONSE_SCHEMA,
                                            summary=batch.item_ids)
                out.calls += 1
            except CacheMiss:
                raise                          # 재생 실패는 조용히 넘기지 않는다(위로 올린다)
            except Exception as exc:           # 호출 예외를 삼키지 않는다
                out.calls += 1
                out.warnings.append(f"배치 {batch.batch_id} {n}회차 호출 실패: "
                                    f"{type(exc).__name__}: {exc}")
            if payload is None:
                out.warnings.append(f"배치 {batch.batch_id} {n}회차 응답 없음")
                continue
            judged, missing, stray = _parse_batch(payload, batch, tr)
            for iid, j in judged.items():
                attempts[iid].append(j)
            for iid in missing:
                misses.setdefault(iid, []).append(str(n))
            if stray:
                out.warnings.append(f"배치 {batch.batch_id} {n}회차 응답에 모르는 항목 id: "
                                    f"{', '.join(stray)}")

    # --- 합치기 -------------------------------------------------------------
    for item in items:
        got = attempts[item.id]
        j = combine(item, got, k)
        if not got:
            j.method = METHOD_MISSING if item.id in misses else METHOD_UNAVAILABLE
            j.reason = (f"배치 응답에 이 항목의 판정이 한 번도 없었습니다"
                        if item.id in misses else j.reason)
            out.unavailable.append(item.id)
        elif item.id in misses:
            j.notes.append(f"{len(misses[item.id])}개 회차 응답에서 이 항목이 빠졌습니다"
                           f"({', '.join(misses[item.id])}회차)")
        out.judgments[item.id] = j

    if hasattr(client, "totals"):
        try:
            out.llm_totals = client.totals()
        except Exception:                       # 통계 실패로 판정을 잃지 않는다
            out.llm_totals = {}
    out.warnings.extend(getattr(client, "warnings", []) or [])
    for e in getattr(client, "log", []):
        if getattr(e, "error", ""):
            out.warnings.append(f"LLM 오류: {e.error}")

    stats = getattr(client, "stats", None)
    out.mode = (f"llm(자기일관성 {k}회, {cfg.llm_mode})" if k > 1
                else f"llm({cfg.llm_mode})")
    if stats is not None:
        out.notes.append(f"판정 호출: {stats.text()}")
    if out.unavailable:
        out.mode += " — 일부 점검 실패"
        out.warnings.append(
            f"판정을 받지 못한 항목 {len(out.unavailable)}개: "
            f"{', '.join(sorted(out.unavailable))} — 점검하지 못한 항목입니다")
    out.seconds = time.monotonic() - started
    return out
