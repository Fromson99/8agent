"""T-A6.4 전처리 — 전사를 "판정할 수 있는 것"으로 편다 (AGENT6 §5-1).

이 파일이 하는 일은 셋뿐이다.

1. **전사 로드** — 반드시 라우터를 통한다. `router.require(path, doc_type="STT전사")`.
   여기서 json 을 직접 열면 agent6 만 다른 방식으로 전사를 자르게 되고, 발화 좌표
   ("발화001")가 코어의 것과 어긋난다. 좌표가 어긋나면 근거 인용이 어긋나고, 근거가
   어긋난 판정은 판정이 아니다(§0 원칙 3). 격리(fitness 미달) 문서는 `require` 가
   거부한다 — 형식이 안 맞는 파일을 그럴듯한 리포트로 바꾸지 않는다.

2. **인용 대조면 만들기** — 발화마다 정규화 문자열을 붙여 둔다. 판정자가 인용한
   문장이 **그 발화 안에 실제로 있는지** 대조하기 위한 것이고, 그 외의 쓰임은 없다
   (`Transcript.verify_quote`).

3. **활성 항목 확정** — 항목 스펙의 `when` 을 메타로 평가한다(when.py 3치 논리).
   UNKNOWN 은 **활성 쪽**이며 confidence 를 한 단계 깎는다. 모르면 켠다 — 끄면
   리포트에 흔적조차 남지 않기 때문이다.

## 여기서 lexicon 이 사라진 자리 (2026-08)

예전에는 이 파일이 **매칭용** 정규화기를 들고 있었다: kiwipiepy 형태소 모드, 조사가
끼어드는 자리를 벌려 주는 `chunks()/find_all()`, 적중을 원문 스팬으로 되돌리는 색인.
전부 lexicon(금지어 목록)이 쓰던 것이고, lexicon 과 함께 걷어냈다.

형태소 모드를 되살리지 않는 이유는 성능이 아니라 **안전**이다. 형태소 정규화는 어미를
버리므로 "원금 보장 안 됩니다"가 "원금보장안"이 되고, 인용문 "원금 보장됩니다"("원금보장")가
그 안에 들어 있는 것으로 대조된다 — 정반대 뜻의 문장이 서로의 근거가 된다. 인용 대조에
필요한 것은 공백·구두점 흔들림만 흡수하는 **문자 정규화**다.

## 왜 질문 수를 여기서 세는가

F-30 의 `when` 은 `customer_question_count >= 1` 이다. 이 수를 판정기(LLM)가 세면
같은 전사가 호출마다 다른 활성 집합을 갖게 된다. 전처리가 결정론으로 세어 메타에
넣고, 판정기는 그 결과를 받기만 한다. **메타에 값이 이미 있으면 덮지 않는다** —
사람이 준 값이 코드의 추정보다 우선이다.
"""

from __future__ import annotations

import unicodedata
import warnings as _warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from lawrag.core import router

from lawrag.agents.agent6.src import schema

# 라우터에 말할 수 있는 것은 doc_type 뿐이다. 형식·용어집은 등록부가 정한다(SPEC §00).
DOC_TYPE = "STT전사"

AGENT_ROOT = Path(__file__).resolve().parent.parent
ITEMS_DIR = AGENT_ROOT / "checklist" / "items"
VERSION_FILE = AGENT_ROOT / "checklist" / "VERSION"

# 정규화에서 살려 두는 기호. 문자·숫자 외에는 전부 지우지만 '%' 만은 남긴다 —
# 수익률·손실률 인용에서 "100%"가 "100"이 되면 "100만원"과 구별되지 않는다.
KEEP_SYMBOLS = frozenset("%")

# 인용으로 인정하는 최소 길이(정규화 문자 수). 이보다 짧은 것은 대개 맞장구
# ("네", "예", "아 네", "그렇죠")라 무엇의 근거도 되지 못한다. 실제로 뚫렸던 구멍이
# 이것이다 — 고객의 "네" 한 글자가 고지 이행의 인용으로 통과했다.
# judge 는 여기에 더해 자기 문턱(MIN_EVIDENCE_CHARS)을 쓴다. 둘 중 엄한 쪽이 이긴다.
MIN_QUOTE_CHARS = 4

# 고객 질문 판별표. **데이터다** — 새 어미가 현장에서 보이면 여기 한 줄을 늘린다.
# 판별을 좁게 잡는다: 못 세면 F-30 이 UNKNOWN 으로 보수 활성될 뿐이지만, 넓게 잡아
# 아무 발화나 질문으로 세면 F-30 이 늘 켜져 UNCLEAR 만 쌓인다.
QUESTION_MARKS = ("?", "？")
QUESTION_SUFFIXES = ("나요", "가요", "까요", "습니까", "ㅂ니까", "은지요", "던가요")

# 미해소 basis 항목을 어떻게 할 것인가 (§2 "미해소 basis 를 가진 항목은 활성화가 차단된다").
#
#   block — 스펙의 문언대로 활성을 끈다. 근거 없는 판정을 아예 만들지 않는다.
#   warn  — 활성은 유지하되 사유를 리포트에 싣고 confidence 를 한 단계 깎는다. (기본)
#
# 기본을 warn 으로 둔 이유: 지금 미해소인 코퍼스는 KOFIA-R 하나이고(원문은 있으나 사이드카의
# doc_type 이 등록부와 어긋나 배차되지 않는다), 그것을 basis 로 가진 항목이 30개 중 9개다.
# 기본을 block 으로 두면 **점검의 3분의 1이 조용히 사라진 리포트**가 운영에 나간다 —
# 차단은 "판정하지 않았다"를 알리는 장치이지 놓침을 만드는 장치가 아니다. 미수집을 막는
# 자리는 빌드 게이트(T-A6.2 (b), corpus manifest)이고, 런타임은 그 사실을 **시끄럽게 싣고**
# 계속 돈다. 운영에서 차단이 필요하면 CLI 로 켠다.
BASIS_POLICIES = ("warn", "block")


class PreprocessError(ValueError):
    """전사를 판정 가능한 형태로 펴지 못했다. 빈 결과를 돌려주지 않는다."""


# ===========================================================================
# 정규화 — 인용 대조의 기준면
# ===========================================================================

@dataclass(frozen=True)
class Norm:
    """정규화 결과. 인용문과 발화문을 같은 자로 재기 위한 것이다.

    예전에는 원문 위치로 되돌리는 색인(`index`)을 함께 들고 다녔다. lexicon 적중을
    원문 스팬으로 바꿔야 했기 때문인데, 인용 대조는 **발화 단위**로 하므로(인용의 좌표는
    발화 좌표다) 문자 단위 역매핑이 필요 없다. 쓰지 않는 색인을 유지하면 그것을 쓰는
    코드가 다시 생긴다.
    """
    text: str


class Normalizer:
    """인용 대조용 정규화기. 인용문과 발화문에 **같은 함수**를 적용한다.

    NFKC → 문자/숫자(+%)만 남기고 casefold. 공백·구두점·따옴표 흔들림은 흡수하고
    낱말은 건드리지 않는다. LLM 이 조사·문장부호를 다듬어 인용하는 것까지 위조로 몰면
    멀쩡한 판정이 전부 UNCLEAR 가 되지만, 이 기준면에서조차 없는 말은 전사에 없는 말이다.

    형태소 모드(kiwipiepy)는 lexicon 과 함께 제거했다 — 모듈 설명 참조. 어미를 버리는
    정규화는 "원금 보장 안 됩니다"와 "원금 보장됩니다"를 같은 것으로 만든다.
    """

    def __init__(self, *, prefer_morph: bool = False):
        # prefer_morph 는 형태소 모드가 있던 시절의 인자다. 호출부가 아직 명시적으로
        # False 를 넘기고 있어 받아만 두되, True 는 **조용히 무시하지 않고** 거절한다.
        if prefer_morph:
            raise PreprocessError(
                "형태소 정규화 모드는 lexicon 과 함께 제거했습니다 — 어미를 버리는 정규화는 "
                "'원금 보장 안 됩니다'를 '원금 보장됩니다'의 근거로 만듭니다. "
                "인용 대조는 문자 정규화로만 합니다")
        self.warnings: list[str] = []
        self.mode = "문자"

    def normalize(self, text: str) -> Norm:
        out: list[str] = []
        for raw in text or "":
            for ch in unicodedata.normalize("NFKC", raw):
                if unicodedata.category(ch)[0] in ("L", "N") or ch in KEEP_SYMBOLS:
                    out.append(ch.casefold())
        return Norm("".join(out))


# ===========================================================================
# 발화
# ===========================================================================

@dataclass(frozen=True)
class Utterance:
    """발화 하나 = 판정 좌표 하나(§5 규약: section_id 는 '발화001')."""
    section_id: str
    turn: int
    speaker: str
    text: str
    start: Optional[float]
    end: Optional[float]
    char_start: int
    char_end: int
    norm: Norm

    def is_customer(self) -> bool:
        """고객의 발화인가 — 존재형 근거의 자격을 가르는 물음이다(§비대칭 임계 2).

        고지·설명은 판매자가 하는 것이므로, 고객이 "그건 못 들었는데요"라고 한 말이
        고지 이행의 증거가 될 수 없다(실제로 뚫렸던 구멍). 화자를 모르는 전사("미상")를
        여기서 고객으로 몰지는 않는다 — 그러면 평문 전사의 존재형이 전부 UNCLEAR 가 되어
        리포트가 못 쓰게 된다. 그 판단은 judge 가 한다.
        """
        return self.speaker == "고객"

    def evidence(self) -> schema.EvidenceSpan:
        return schema.EvidenceSpan(text=self.text, start=self.start, end=self.end,
                                   section_id=self.section_id,
                                   char_start=self.char_start, char_end=self.char_end)

    def brief(self) -> str:
        stamp = f"{self.start:.1f}s" if self.start is not None else f"@{self.char_start}"
        return f"[{self.section_id} {self.speaker} {stamp}] {self.text}"


@dataclass(frozen=True)
class QuoteCheck:
    """인용문이 **그 좌표의 발화 안에** 실제로 있는가 — 환각 인용 차단의 결과(§5-4).

    실패는 전부 사유를 남긴다. "왜 이 evidence 를 버렸는가"가 리포트·큐에 남아야
    스펙을 고칠 수 있다(조용히 버리면 판정만 UNCLEAR 로 바뀌고 이유는 사라진다).
    """
    found: bool
    section_id: Optional[str] = None
    utterance: Optional[Utterance] = None
    spans_turns: bool = False          # 발화 경계를 넘는 인용(연속 발화 이어 붙임)
    reason: str = ""


@dataclass
class Transcript:
    """전사 하나 — 라우터가 만든 doc.json 을 판정기가 쓰기 좋은 형태로 편 것."""
    path: str
    doc_id: str
    utterances: list[Utterance]
    normalizer: Normalizer
    canonical: str                      # 발화문을 "\n" 으로 이은 정본 텍스트
    canonical_norm: Norm
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    fitness: dict[str, Any] = field(default_factory=dict)

    # --- 조회 ---------------------------------------------------------------
    def by_section(self, section_id: str) -> Optional[Utterance]:
        return next((u for u in self.utterances if u.section_id == section_id), None)

    @property
    def has_speaker_labels(self) -> bool:
        """누가 말했는지 아는가. 모르면 '고객 질문'을 셀 수 없다(아래 참조)."""
        return any(u.speaker != "미상" for u in self.utterances)

    def customer_questions(self) -> list[Utterance]:
        """고객이 던진 질문. F-30 의 `when` 이 이 수를 본다."""
        out = []
        for u in self.utterances:
            if not u.is_customer():
                continue
            body = u.text.strip()
            if any(m in body for m in QUESTION_MARKS):
                out.append(u)
                continue
            stripped = body.rstrip("".join(QUESTION_MARKS) + ". !~")
            if stripped.endswith(QUESTION_SUFFIXES):
                out.append(u)
        return out

    def verify_quote(self, quote: str, section_id: Optional[str]) -> QuoteCheck:
        """인용 좌표 대조 — **없는 말을 지어낸 판정을 여기서 잡는다**(§5-5·§9-2).

        예전 판(전사 전체의 정규화면에서 부분문자열 찾기)이 실제로 흘려보낸 것 셋:

          (a) "네" 한 글자 — 전사 어딘가에는 반드시 있으므로 늘 통과했다. 고객의
              맞장구가 고지 이행의 근거가 됐다.
          (b) 인접 두 발화를 이어 붙인 문장 — 발화문을 "\\n" 으로 이은 정본에서만
              존재하는, 아무도 말한 적 없는 문장이 통과했다.
          (c) 좌표가 틀린 인용 — 좌표를 아예 보지 않았으므로 `발화137` 이라고 적고
              `발화002` 의 말을 인용해도 통과했다.

        그래서 셋을 각각 막는다. 인용은 **주어진 좌표의 발화 안에서만** 찾고, 최소 길이를
        요구하며, 발화 경계를 넘으면 거부한다. 좌표가 실재하지 않으면 즉시 실패다.

        판정은 한 방향으로만 기운다(§0 원칙 4) — 애매하면 근거를 버린다. 근거를 잃은
        "있음의 주장"은 호출부에서 UNCLEAR 로 강등된다.
        """
        if not (section_id or "").strip():
            return QuoteCheck(found=False, reason="인용에 좌표(section_id)가 없습니다")
        u = self.by_section(section_id)
        if u is None:
            return QuoteCheck(found=False, section_id=section_id,
                              reason=f"좌표 '{section_id}' 인 발화가 전사에 없습니다")

        needle = self.normalizer.normalize(quote or "").text
        if len(needle) < MIN_QUOTE_CHARS:
            return QuoteCheck(
                found=False, section_id=section_id, utterance=u,
                reason=f"인용이 너무 짧습니다({len(needle)}자 < {MIN_QUOTE_CHARS}자) — "
                       f"맞장구 한 마디는 무엇의 근거도 되지 못합니다")
        if needle in u.norm.text:
            return QuoteCheck(found=True, section_id=u.section_id, utterance=u)

        # 발화 안에는 없다. 전사 전체에는 있는가 — 있다면 **발화를 이어 붙인 인용**이거나
        # 좌표를 잘못 적은 것이다. 둘 다 근거로 쓸 수 없지만 사유는 갈라서 적는다.
        if needle in self.canonical_norm.text:
            return QuoteCheck(
                found=False, section_id=section_id, utterance=u, spans_turns=True,
                reason=f"인용이 발화 '{section_id}' 안에 없습니다 — 여러 발화를 이어 붙였거나 "
                       f"좌표가 틀렸습니다(전사 전체에는 있음)")
        return QuoteCheck(found=False, section_id=section_id, utterance=u,
                          reason=f"인용이 전사에 없습니다 — 발화 '{section_id}' 와 대조 실패")

    def render(self) -> str:
        """판정 프롬프트에 실을 전사 전문.

        강조 표시(▶)는 없앴다 — 표시할 "후보 발화"를 만들던 lexicon 이 사라졌고, 남은
        표시는 전부 판정자에게 "여기만 보라"는 잘못된 힌트가 된다. 판정자는 전문을 읽는다.
        """
        return "\n".join("  " + u.brief() for u in self.utterances)


# ===========================================================================
# 전사 로드 (라우터 경유)
# ===========================================================================

def load_transcript(path: str | Path, *, normalizer: Optional[Normalizer] = None,
                    strict: bool = True) -> Transcript:
    """전사 파일 → Transcript. **json 을 직접 열지 않는다**(모듈 설명 1 참조)."""
    p = Path(path)
    call = router.require if strict else router.route
    try:
        routed = call(p, doc_type=DOC_TYPE)
    except router.RoutingError as exc:
        raise PreprocessError(f"전사를 배차하지 못했습니다: {p} — {exc}") from exc

    norm = normalizer or Normalizer()
    utterances: list[Utterance] = []
    skipped: list[str] = []
    for section in routed.doc.sections:
        metas = [c.get("meta") for c in section.content if isinstance(c.get("meta"), dict)]
        if not metas:
            # 발화 좌표가 없는 구역 — 정상 입력에서는 나오지 않는다(형식의 default_section).
            skipped.append(section.section_id)
            continue
        for meta in metas:
            body = str(meta.get("utterance") or "")
            if not body.strip():
                continue
            utterances.append(Utterance(
                section_id=section.section_id,
                turn=int(meta.get("turn") or len(utterances) + 1),
                speaker=str(meta.get("speaker") or "미상"),
                text=body,
                start=meta.get("start"), end=meta.get("end"),
                char_start=int(meta.get("char_start") or 0),
                char_end=int(meta.get("char_end") or 0),
                norm=norm.normalize(body)))

    if not utterances:
        raise PreprocessError(
            f"발화 좌표가 있는 구역이 하나도 없습니다: {p} — "
            f"전사 형식이 바뀌었거나 파서가 meta 를 싣지 않았습니다")

    warns = list(routed.parsed.warnings) + list(routed.fitness.warnings) + norm.warnings
    if skipped:
        warns.append(f"발화 좌표가 없는 구역 {len(skipped)}개를 건너뜁니다: {', '.join(skipped[:5])}")
    canonical = "\n".join(u.text for u in utterances)
    return Transcript(
        path=str(p), doc_id=routed.parsed.doc_id, utterances=utterances,
        normalizer=norm, canonical=canonical, canonical_norm=norm.normalize(canonical),
        warnings=warns, stats=dict(routed.parsed.stats), fitness=routed.fitness.dump())


# ===========================================================================
# 활성 항목 확정
# ===========================================================================

@dataclass(frozen=True)
class Activation:
    """항목 하나의 활성 여부와 그 사유. 사유 없는 비활성은 리포트에 실을 수 없다(§7)."""
    item_id: str
    state: str                       # ACTIVE | INACTIVE | UNKNOWN
    active: bool
    reasons: tuple[str, ...]
    confidence_penalty: int
    text: str
    blocked_reason: Optional[str] = None    # 미해소 basis (warn 이면 활성 유지 + 감점)

    @property
    def unknown(self) -> bool:
        return self.state == "UNKNOWN"


def _basis_block(items: Sequence[schema.ChecklistItem],
                 allow_missing: Sequence[str],
                 sink: list[str]) -> dict[str, str]:
    """근거가 미해소인 항목 → 사유. 판단은 basis.py(코퍼스 manifest)가 한다.

    manifest 가 없으면 **판단할 수 없다**. 그때 조용히 "전부 해소됨"으로 치지 않고
    사실을 남긴다 — 근거 유무를 모르는 채 돌았다는 것 자체가 리포트에 남아야 한다.
    """
    try:
        from lawrag.agents.agent6.src import basis            # type: ignore
    except ImportError:
        sink.append("basis 모듈이 없어 근거 해소 여부를 확인하지 못했습니다")
        return {}
    try:
        return basis.blocked_items(items, allow_missing=allow_missing)
    except Exception as exc:                            # manifest 없음·깨짐 등
        sink.append(f"근거 해소 여부를 확인하지 못했습니다({type(exc).__name__}) — "
                    f"코퍼스를 먼저 빌드하세요: {exc}")
        return {}


@dataclass
class Prepared:
    """§5-1 의 산출 — 이후 모든 단계의 입력."""
    transcript: Transcript
    meta: schema.TranscriptMeta
    items: list[schema.ChecklistItem]
    activations: dict[str, Activation]
    checklist_version: str
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def item(self, item_id: str) -> schema.ChecklistItem:
        return next(i for i in self.items if i.id == item_id)

    def active_items(self) -> list[schema.ChecklistItem]:
        # 꺼진 항목(enabled=false)은 활성이 아니다 — 스펙에 남아 있을 뿐이다(§4).
        return [i for i in self.items
                if i.enabled and self.activations[i.id].active]

    def judgeable_items(self) -> list[schema.ChecklistItem]:
        """활성 항목 중 **독립 판정 대상**. 파생 항목은 빠진다(§9-5)."""
        return [i for i in self.active_items() if i.derived is None]


def checklist_version(items_dir: Path, items: Sequence[schema.ChecklistItem]) -> str:
    """체크리스트 판본. VERSION 파일이 있으면 그것을, 없으면 내용 해시를 쓴다.

    판본을 손으로 적지 않는 이유: few_shot 재적재(harvest)로 스펙이 바뀌면 판본도
    바뀌어야 하는데, 사람이 그때마다 파일을 고치리라 기대할 수 없다. 내용 해시는
    같은 스펙이면 같은 값이고 바뀌면 반드시 달라진다.
    """
    if VERSION_FILE.exists():
        line = VERSION_FILE.read_text(encoding="utf-8").strip().splitlines()
        if line and line[0].strip():
            return line[0].strip()
    import hashlib
    h = hashlib.sha256()
    for p in sorted(items_dir.glob("*.y*ml")):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return f"items{len(items)}-{h.hexdigest()[:8]}"


def _load_items(items_dir: Path, sink: list[str]) -> list[schema.ChecklistItem]:
    """항목 스펙 로드. 로더의 경고를 삼키지 않고 리포트로 넘긴다."""
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always", schema.ChecklistWarning)
        items = schema.load_items(items_dir, warn=True)
    sink.extend(str(w.message) for w in caught
                if issubclass(w.category, schema.ChecklistWarning))
    return items


def prepare(transcript_path: str | Path,
            meta: Any = None,
            *,
            items_dir: str | Path = ITEMS_DIR,
            normalizer: Optional[Normalizer] = None,
            basis_policy: str = "warn",
            allow_missing_basis: Sequence[str] = (),
            strict: bool = True) -> Prepared:
    """§5-1 전처리 전체. 같은 입력이면 같은 결과다(LLM 없음)."""
    if basis_policy not in BASIS_POLICIES:
        raise PreprocessError(f"basis_policy 는 {BASIS_POLICIES} 중 하나여야 합니다 "
                              f"(받은 값 '{basis_policy}')")
    warns: list[str] = []
    notes: list[str] = []

    d = Path(items_dir)
    items = _load_items(d, warns)
    version = checklist_version(d, items)

    tr = load_transcript(transcript_path, normalizer=normalizer, strict=strict)
    warns.extend(tr.warnings)

    m = _as_meta(meta)

    # 질문 수는 전처리가 센다 — 판정기가 세면 활성 집합이 호출마다 흔들린다(모듈 설명).
    questions = tr.customer_questions()
    if not tr.has_speaker_labels and m.customer_question_count is None:
        # 화자를 모르는 전사에서 "고객 질문 0개"는 사실이 아니라 **못 센 것**이다.
        # 0 을 넣으면 F-30 이 조용히 꺼진다. 비워 두면 when 이 UNKNOWN 으로 보수 활성한다.
        notes.append("화자 라벨이 없어 고객 질문 수를 세지 못했습니다 — "
                     "메타를 비워 둡니다(F-30 은 보수적으로 활성됩니다)")
    elif m.customer_question_count is None:
        m.customer_question_count = len(questions)
        notes.append(f"고객 질문 {len(questions)}개를 전사에서 세어 메타에 넣었습니다 "
                     f"(customer_question_count) — F-30 활성 판단에 쓰입니다")
    elif m.customer_question_count != len(questions):
        notes.append(f"메타의 고객 질문 수({m.customer_question_count})가 전사에서 센 값"
                     f"({len(questions)})과 다릅니다 — 메타 값을 씁니다")

    blocked = _basis_block(items, allow_missing_basis, notes)
    if blocked:
        notes.append(
            f"근거 미해소 항목 {len(blocked)}개 "
            f"({', '.join(sorted(blocked)[:6])}{'…' if len(blocked) > 6 else ''}) — "
            + ("활성을 차단했습니다(basis_policy=block)" if basis_policy == "block"
               else "판정은 운영정의·few_shot 만으로 이루어지며 confidence 를 한 단계 낮춥니다"))

    activations: dict[str, Activation] = {}
    for item in items:
        r = item.activation(m)
        reason = blocked.get(item.id)
        if reason and basis_policy == "block" and r.active:
            activations[item.id] = Activation(
                item_id=item.id, state="INACTIVE", active=False, reasons=(reason,),
                confidence_penalty=0, text=f"근거 미해소로 판정하지 않았습니다 — {reason}",
                blocked_reason=reason)
            continue
        activations[item.id] = Activation(
            item_id=item.id, state=r.state, active=r.active, reasons=r.reasons,
            confidence_penalty=r.confidence_penalty + (1 if reason and r.active else 0),
            text=r.reason_text(), blocked_reason=reason)

    inactive = [i for i in items if not activations[i.id].active]
    unknown = [i for i in items if activations[i.id].unknown]
    notes.append(f"활성 {len(items) - len(inactive)}개 / 비활성 {len(inactive)}개 "
                 f"(메타 부족으로 보수 활성 {len(unknown)}개)")

    return Prepared(transcript=tr, meta=m, items=items, activations=activations,
                    checklist_version=version, warnings=warns, notes=notes)


def _as_meta(meta: Any) -> schema.TranscriptMeta:
    """메타 입력을 모델로. 없으면 빈 메타 — when 이 UNKNOWN 으로 보수 활성한다."""
    if meta is None:
        return schema.TranscriptMeta()
    if isinstance(meta, schema.TranscriptMeta):
        return meta.model_copy(deep=True)
    if isinstance(meta, (str, Path)):
        import json
        p = Path(meta)
        if not p.exists():
            raise PreprocessError(f"메타 파일을 찾을 수 없습니다: {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PreprocessError(f"메타 JSON 을 읽을 수 없습니다: {p} — {exc}") from exc
        if not isinstance(data, dict):
            raise PreprocessError(f"메타는 객체여야 합니다: {p} (받은 형태: {type(data).__name__})")
        return schema.TranscriptMeta.model_validate(data)
    if isinstance(meta, dict):
        return schema.TranscriptMeta.model_validate(meta)
    raise PreprocessError(f"메타를 읽을 수 없습니다: {type(meta).__name__}")
