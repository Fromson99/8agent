"""T-A6.5 컨텍스트 조립 — "미리 연결"을 실제 프롬프트로 만든다 (AGENT6 §5-3).

**런타임 검색이 없다.** 이 파일에는 유사도 계산도, 벡터 조회도, "이 발화에 관련된 조문
찾기"도 없다. 항목 스펙이 컴파일 타임에 적어 둔 basis 좌표를 그대로 파일 경로로 바꿔
읽을 뿐이다(§0 원칙 1). 읽는 곳은 `corpus/excerpts/` 하나뿐이고, 읽는 파일의 목록은
항목 스펙이 전부 결정한다 — 런타임이 고를 여지가 없다.

조립 결과는 **검사 가능한 구조**로 돌려준다(`ItemContext.excerpts`,
`ItemContext.block`). 단위 테스트가 "판정 프롬프트에 코퍼스 발췌가 실제로 들어갔는가"를
검사하기 때문이다(§9-4). 프롬프트를 문자열 하나로만 돌려주면 그 검사가 문자열 검색이
되어 버리고, 발췌가 비었는데도 통과할 수 있다.

## 발췌를 못 읽으면

지어내지 않는다. `Excerpt.present=False` 로 남기고 프롬프트에는 "(발췌 없음 — 수집 대기)"
라고 적는다. 판정자는 운영정의와 few_shot 만으로 판정하게 되며, 그 사실이 리포트에
남는다(§4 절대 규칙: 없는 것을 있다고 쓰지 않는다).

## "후보 발화" 블록이 사라진 자리 (2026-08)

예전 프롬프트에는 lexicon 이 찾은 후보 발화가 ▶ 로 강조돼 실렸다. 그것이 판정을
망쳤다 — 목록에 없는 표현으로 말한 위반은 후보에 오르지 못했고, 판정자는 "후보가
비었으니 위반이 없나 보다"라고 읽었다. 지금은 **전사 전문만** 준다. 어디를 봐야
하는지는 운영 정의가 말하고, 어디를 봤는지는 판정자가 인용으로 증명한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from lawrag.agents.agent6.src import schema
from lawrag.agents.agent6.src.preprocess import Transcript

AGENT_ROOT = Path(__file__).resolve().parent.parent
EXCERPT_ROOT = AGENT_ROOT / "data" / "corpus" / "excerpts"

# 발췌 한 건의 상한. 조문 하나가 프롬프트를 통째로 잡아먹는 것을 막는다.
# 자르면 자른 사실을 본문에 적는다(조용히 줄이지 않는다).
MAX_EXCERPT_CHARS = 4000

# 근거 통로는 basis.py 하나뿐이다(그 파일의 설명 참조). 여기서 다시 열지 않는다.
# 없을 때만 §5 좌표 규약대로 직접 읽는다 — 그때도 읽는 곳은 excerpts/ 하나뿐이다.
try:
    from lawrag.agents.agent6.src import basis as basis_mod          # type: ignore
except ImportError:                                            # 코퍼스 도구가 아직 없는 저장소
    basis_mod = None

SYSTEM = """당신은 금융상품 판매 녹취를 체크리스트로 점검하는 준법 검토자다.

주어지는 것
- 통화 전사 전문 (발화마다 `발화NNN` 좌표와 화자·시각이 붙어 있다)
- 점검 항목마다: 운영 정의 / 근거 규정 발췌 / 판정 예시(few-shot)

해야 할 일
- 항목마다 **독립적으로** PASS / FAIL / UNCLEAR 를 판정한다. 항목끼리 서로의 판정을 참조하지 않는다.
- 판정마다 전사에서 **그대로 복사한** 발화를 근거로 인용한다. 좌표(`발화NNN`)를 함께 적는다.

판정 규약
- 존재형: 필요한 고지·설명이 전사에 있으면 PASS, 없으면 FAIL.
- 부재형: 금지된 표현이 없으면 PASS, 있으면 FAIL. 위반 발화를 반드시 인용한다.
- 충분성형: 운영 정의가 정한 기준으로 판정한다.
- **애매하면 UNCLEAR.** 거짓 PASS(불완전판매 통과)의 비용이 거짓 FAIL(재설명 몇 분)보다
  압도적으로 크다. 확신이 서지 않으면 PASS 로 밀지 말고 UNCLEAR 로 둔다.

무엇이 위반인가 — 낱말이 아니라 뜻으로 본다
- 금지 표현의 목록 같은 것은 없다. 같은 뜻을 다르게 말한 것도 똑같이 위반이다.
  "무조건 오릅니다"와 "여기서 더 내려갈 일은 없습니다"와 "손해 볼 일은 없다고 보시면
  됩니다"는 전부 같은 위반이다. 표현이 조심스럽다고 위반이 아닌 것이 아니다.
- 부정어가 문장 어딘가에 있다고 위반이 지워지지 않는다. "원금 보장은 안 됩니다만,
  이 상품은 사실상 원금보장이라고 보시면 됩니다"는 뒤 절이 위반이다. 문장 전체가 고객에게
  남기는 인상으로 판정한다.

근거로 인정하는 발화 (§비대칭 임계)
- **존재형의 근거는 PB(판매자)의 발화만 인정한다.** 고지·설명은 판매자가 하는 것이다.
  고객이 "그건 못 들었는데요", "원금 손실 나는 거 알아요"라고 말한 것은 판매자가 고지했다는
  증거가 **아니다**. 고객 발화밖에 인용할 것이 없으면 PASS 를 주장하지 말고 UNCLEAR 로 둔다.
- 부재형은 반대다 — 문제 삼는 것이 PB 의 발언이므로 PB 발화를 인용한다.

인용 규칙 (어기면 그 근거는 폐기되고 판정이 UNCLEAR 로 내려간다)
- 전사에 없는 문장을 지어내지 않는다. 요약·의역하지 않고 발화문을 그대로 옮긴다.
- 인용은 **한 발화 안에서** 끊는다. 앞뒤 발화를 이어 붙인 문장은 아무도 말한 적이 없는
  문장이다. 두 발화가 필요하면 evidence 를 두 개로 적는다.
- 좌표(`발화NNN`)는 인용한 그 발화의 것이어야 한다. 좌표와 인용문은 대조된다.
- "네", "예" 같은 맞장구 한 마디는 근거가 아니다.
- 인용할 발화가 없으면 PASS/FAIL 을 주장하지 말고 UNCLEAR 로 둔다.
  (예외: 존재형이 "전사 어디에도 없음"이라 FAIL 인 경우 — 이때는 evidence 를 비우고
   reason 에 '전사 전체에서 미발견' 이라고 적는다.)
- reason 은 한국어 한두 문장. 무엇을 근거로 그렇게 판정했는지 쓴다."""


class ContextError(ValueError):
    """컨텍스트를 조립하지 못했다."""


# ===========================================================================
# 근거 발췌 적재 — W4 의 basis.py 를 쓰고, 없으면 좌표 규약대로 직접 읽는다
# ===========================================================================

@dataclass(frozen=True)
class Excerpt:
    """근거 발췌 하나. `present=False` 면 원문이 아직 없다는 뜻이다.

    좌표가 둘인 이유: 스펙이 **물은 것**(`query`, 예 "KOFIA-R#고령투자자")과 그것이
    **해소된 곳**(`coordinate`, 예 "KOFIA-R/Ⅳ/Ⅳ-2/11.")이 다를 수 있다. 둘 다 남겨야
    "왜 이 조문인가"와 "정말 그 자리로 갔는가"를 함께 확인할 수 있다(§새 basis 표기).
    """
    query: str                          # 스펙이 적은 좌표 (용어 앵커 또는 section 좌표)
    coordinate: str = ""                # 해소된 section 좌표. 비면 query 와 같다고 본다
    text: str = ""
    path: Optional[str] = None
    present: bool = False
    note: str = ""
    truncated: bool = False
    ambiguous: tuple[str, ...] = ()     # 용어가 여러 곳에 걸렸다 — 추측하지 않는다
    # 발췌 머리글에서 그대로 실어 오는 출처. 판정자에게 **무슨 법의 어디**인지 말하는
    # 데 쓴다 — `KSB/제21조/제1호` 는 파일을 찾는 키일 뿐 인용이 아니다.
    law: str = ""                       # "금융소비자 보호에 관한 법률"
    article: str = ""                   # "제21조(부당권유행위 금지) 제1호"
    edition: str = ""                   # "법률 제21065호 / 시행 2026-01-02"
    verification: str = ""              # 사람이 원문과 대조했는가 (리포트·감사용)
    siblings: tuple[str, ...] = ()      # 같은 부모를 공유하는 구역들 (children 간선)

    @property
    def where(self) -> str:
        """실제로 읽은 자리. 미해소면 물은 좌표 그대로."""
        return self.coordinate or self.query

    def ref(self) -> str:
        """리포트에 실을 표기 — "물은 것 → 해소된 곳"."""
        return schema.basis_ref(self.query, self.coordinate or None)

    def citation(self) -> str:
        """사람이 인용하는 표기. 없으면 좌표로 물러선다 — 지어내지 않는다."""
        both = f"{self.law} {self.article}".strip()
        return both or self.ref()

    def render(self) -> str:
        if self.ambiguous:
            return (f"[{self.ref()}] (용어가 {len(self.ambiguous)}곳에 걸려 근거를 "
                    f"특정하지 못했습니다: {', '.join(self.ambiguous[:5])} — "
                    f"항목 스펙에 section 을 함께 적어 좁히세요)")
        if not self.present:
            return f"[{self.ref()}] (발췌 없음 — {self.note or '코퍼스 수집 대기'})"
        # 첫 줄이 인용 표기, 둘째 줄이 판본·내부좌표, 그 아래가 조문 원문이다.
        # 판정자가 "무슨 법 몇 조를 근거로 판정했다" 를 쓸 수 있어야 한다.
        head = [f"[{self.citation()}]"]
        tag = " · ".join(x for x in (self.edition, f"좌표 {self.ref()}") if x)
        if tag:
            head.append(f"  ({tag})")
        if len(self.siblings) > 1:
            # 같은 조 아래 호가 여럿이면 그 사실을 말해 준다 — 인용한 호 하나가
            # 그 조의 전부라고 판정자가 오해하지 않게.
            head.append(f"  (같은 상위 구역의 다른 항·호: {', '.join(self.siblings)})")
        tail = "\n… (이하 생략)" if self.truncated else ""
        return "\n".join(head) + f"\n{self.text}{tail}"


class BasisLoader:
    """발췌 적재기 — 좌표 하나를 발췌 하나로 바꾼다.

    적재는 `basis.load_excerpt(좌표)` 가 정본이다. 그 파일이 발췌 파일명 규약·머리글
    처리·manifest 해소 상태를 모두 알고 있으므로 여기서 다시 구현하지 않는다.
    basis 모듈이 없는 저장소에서만 §5 좌표 규약대로 파일을 직접 읽는다.

    **용어 앵커도 여기서는 좌표 하나일 뿐이다.** `KOFIA-R#고령투자자` 를 어느 section 으로
    풀지는 basis.py 가 코퍼스 facts 로 정한다. 그 모듈이 `load_ref(좌표)` 를 제공하면
    해소된 좌표까지 함께 받아 리포트에 남기고(무엇을 물었나 / 어디로 해소됐나), 없으면
    `load_excerpt(좌표)` 로 본문만 받는다 — 그때는 물은 좌표만 리포트에 남는다.

    **발췌가 없는 것은 실패가 아니다.** 아직 원문을 수집하지 못한 코퍼스(KOFIA-R·REC·
    CASE·INT)가 있고, 그 사실은 `present=False` 로 리포트까지 그대로 흘러간다.
    적재기가 예외를 던져 파이프라인을 멈추면 "근거가 없다"는 정보 자체가 사라진다.
    """

    def __init__(self, *, excerpt_root: Path = EXCERPT_ROOT,
                 loader: Optional[Callable[[str], Any]] = None):
        self.excerpt_root = Path(excerpt_root)
        self.warnings: list[str] = []
        self._fn = loader
        if loader is not None:
            self.source = "주입"
        elif basis_mod is not None:
            self.source = ("basis.load_ref" if hasattr(basis_mod, "load_ref")
                           else "basis.load_excerpt")
        else:
            self.source = "파일(좌표 규약)"
            self.warnings.append(
                "basis 모듈이 없어 발췌 파일을 좌표 규약대로 직접 읽습니다 — "
                "manifest 의 해소 상태는 확인되지 않습니다")
        self._cache: dict[str, Excerpt] = {}

    # --- 적재 ---------------------------------------------------------------
    def load(self, b: schema.Basis) -> Excerpt:
        coord = b.coordinate()
        if coord in self._cache:
            return self._cache[coord]
        ex = self._load_uncached(b, coord)
        self._cache[coord] = ex
        return ex

    def _load_uncached(self, b: schema.Basis, coord: str) -> Excerpt:
        if self._fn is not None:
            return self._via_callable(self._fn, coord)
        if basis_mod is not None:
            fn = getattr(basis_mod, "load_ref", None) or basis_mod.load_excerpt
            return self._via_callable(fn, coord, missing=basis_mod.ExcerptMissing)
        if b.anchored:
            # 용어를 section 으로 푸는 것은 basis.py 의 일이다. 여기서 코퍼스를 뒤지기
            # 시작하면 "런타임에 규정을 검색하지 않는다"(§0 원칙 1)가 무너진다.
            return Excerpt(query=coord,
                           note="용어 앵커는 basis 모듈이 있어야 해소됩니다")
        # 파일 이름은 스키마가 정한다(§5 규약) — 여기서 다시 짚으면 규약이 두 곳에 산다.
        rel = b.excerpt_relpath()
        p = (self.excerpt_root / Path(rel).relative_to("corpus/excerpts")) if rel else None
        if p is None or not p.exists():
            return Excerpt(query=coord, path=str(p) if p else None,
                           note="발췌 파일 없음 — 코퍼스 빌드 대기")
        text = p.read_text(encoding="utf-8").strip()
        if not text:
            return Excerpt(query=coord, path=str(p), note="발췌 파일이 비어 있습니다")
        return self._wrap(coord, text, path=str(p))

    def _via_callable(self, fn: Callable[[str], Any], coord: str,
                      missing: type[BaseException] = FileNotFoundError) -> Excerpt:
        ambiguous = getattr(basis_mod, "AmbiguousTerm", None)
        try:
            got = fn(coord)
        except missing as exc:                    # 미물질화 — 정상적인 "없음"이다
            return Excerpt(query=coord, note=str(exc).split(".")[0])
        except Exception as exc:
            # 용어가 여러 곳에 걸린 경우. **추측하지 않고 시끄럽게** 남긴다 — 아무 곳이나
            # 골라 발췌를 실으면 판정자는 엉뚱한 조문을 근거로 확신하게 된다.
            if ambiguous is not None and isinstance(exc, ambiguous):
                cands = tuple(str(c) for c in getattr(exc, "candidates", ()) or ())
                self.warnings.append(
                    f"{coord}: 용어가 여러 곳에 걸립니다({len(cands) or '?'}곳) — "
                    f"항목 스펙에 section 을 함께 적어 좁히세요")
                return Excerpt(query=coord, ambiguous=cands, note=str(exc))
            self.warnings.append(f"{coord}: 발췌 적재 실패 — {type(exc).__name__}: {exc}")
            return Excerpt(query=coord, note=f"적재 실패({type(exc).__name__})")
        # load_ref 는 해소 좌표와 머리글을 함께 준다. load_excerpt 는 본문만 준다.
        text = str(getattr(got, "text", got) or "").strip()
        resolved = str(getattr(got, "coordinate", "") or "")
        header = getattr(got, "header", None) or {}
        if not text:
            return Excerpt(query=coord, coordinate=resolved, note="발췌가 비어 있습니다")
        return self._wrap(coord, text, path=None, resolved=resolved, header=header)

    @staticmethod
    def _wrap(coord: str, text: str, path: Optional[str], resolved: str = "",
              header: Optional[dict] = None) -> Excerpt:
        cut = len(text) > MAX_EXCERPT_CHARS
        h = header or {}
        # `코퍼스: 금융소비자 보호에 관한 법률 — law.go.kr (국가법령정보센터)` 에서
        # 법령명만 뗀다. 출처(어디서 받았나)는 프롬프트에 필요 없다.
        law = str(h.get("코퍼스", "")).split("—")[0].strip()
        sibs = tuple(s.strip() for s in str(h.get("형제 구역", "")).split(",") if s.strip())
        return Excerpt(query=coord, coordinate=resolved, text=text[:MAX_EXCERPT_CHARS],
                       path=path, present=True, truncated=cut,
                       law=law, article=str(h.get("조문", "")).strip(),
                       edition=str(h.get("판본", "")).strip(),
                       verification=str(h.get("verification", "")).strip(),
                       siblings=sibs)


# ===========================================================================
# 항목 컨텍스트
# ===========================================================================

@dataclass
class ItemContext:
    """항목 하나에 주입할 것 전부. 프롬프트 문자열과 그 재료를 함께 들고 다닌다."""
    item: schema.ChecklistItem
    excerpts: list[Excerpt] = field(default_factory=list)
    block: str = ""

    @property
    def item_id(self) -> str:
        return self.item.id

    def basis_refs(self) -> list[str]:
        """리포트에 실을 근거 표기 — 용어 앵커는 "물은 것 → 해소된 곳"으로 나온다."""
        return [e.ref() for e in self.excerpts]

    def ambiguous_excerpts(self) -> list[str]:
        """용어가 여러 곳에 걸려 근거를 특정하지 못한 것 — 스펙 보강 대상이다."""
        return [e.query for e in self.excerpts if e.ambiguous]

    def present_excerpts(self) -> list[Excerpt]:
        return [e for e in self.excerpts if e.present]

    def missing_excerpts(self) -> list[str]:
        return [e.query for e in self.excerpts if not e.present]

    def has_basis_text(self) -> bool:
        """근거 원문이 실제로 실렸는가 — §9-4 단위 테스트가 보는 것."""
        return any(e.present and e.text.strip() for e in self.excerpts)

    def block_contains_excerpts(self) -> bool:
        """조립된 블록에 발췌 원문이 **문자로** 들어갔는가.

        구조(`excerpts`)와 문자열(`block`)이 어긋나는 일을 막는 자기 검사다.
        """
        present = self.present_excerpts()
        return bool(present) and all(e.text[:60] in self.block for e in present)


@dataclass
class Batch:
    """한 번의 LLM 호출 단위. 카테고리(A~F) 단위로 묶되 항목별 독립 판정을 유지한다(§5-4)."""
    batch_id: str
    contexts: list[ItemContext]
    transcript_view: str
    system: str = SYSTEM

    @property
    def item_ids(self) -> list[str]:
        return [c.item_id for c in self.contexts]

    def user(self) -> str:
        head = ["## 통화 전사 (판정 근거는 반드시 이 안에서 인용한다)", "", self.transcript_view, ""]
        body = [c.block for c in self.contexts]
        tail = ["", f"## 판정할 항목: {', '.join(self.item_ids)}",
                "각 항목마다 독립적으로 판정하고, 위 목록의 항목을 하나도 빠뜨리지 않는다."]
        return "\n".join(head + body + tail)


# ===========================================================================
# 조립
# ===========================================================================

def _few_shot_lines(item: schema.ChecklistItem) -> list[str]:
    if not item.few_shot:
        return ["  (예시 없음)"]
    out = []
    for fs in item.few_shot:
        src = f" [{fs.source}]" if fs.source else ""
        out.append(f'  - "{fs.utterance}" → {fs.verdict} ({fs.reason}){src}')
    return out


def build_item_context(item: schema.ChecklistItem, loader: BasisLoader) -> ItemContext:
    """항목 하나의 컨텍스트. 전사는 배치가 공통으로 싣는다.

    (예전에는 `signal` 인자로 lexicon 이 찾은 후보 발화를 받아 블록 끝에 실었다.
     그 블록이 판정자에게 "여기만 보면 된다"는 잘못된 힌트를 줬으므로 인자째 없앴다.)
    """
    if item.derived is not None:
        raise ContextError(
            f"{item.id}: 파생 항목은 LLM 판정 대상이 아닙니다 — 프롬프트에 넣지 않는다(§9-5)")
    excerpts = [loader.load(b) for b in item.basis]
    ctx = ItemContext(item=item, excerpts=excerpts)
    lines = [
        f"### {item.id} {item.name}  ({item.type})",
        "",
        "운영 정의:",
        "  " + item.operational_definition.strip().replace("\n", "\n  "),
        "",
        "근거 규정 발췌:",
    ]
    if excerpts:
        for e in excerpts:
            lines.append("  " + e.render().replace("\n", "\n  "))
    else:
        lines.append("  (이 항목에는 연결된 근거 좌표가 없다 — 운영 정의로만 판정한다)")
    lines += ["", "판정 예시:", *_few_shot_lines(item), ""]
    ctx.block = "\n".join(lines)
    return ctx


def build_batches(items: Sequence[schema.ChecklistItem],
                  transcript: Transcript,
                  *, loader: Optional[BasisLoader] = None,
                  per_item: bool = False,
                  max_batch: int = 6) -> list[Batch]:
    """활성·판정대상 항목을 배치로 묶는다.

    묶는 기준은 **항목 id 의 카테고리 문자(A~F)** 다 — 같은 카테고리는 서로 비슷한
    발화 구간을 보므로 한 프롬프트에 넣어도 판정이 섞이지 않는다. 한 배치의 상한은
    `max_batch`(기본 6, §5-4 의 "3~6항목"). `per_item=True` 면 항목당 한 호출이다.

    모든 배치가 **전사 전문**을 싣는다. 항목마다 다른 조각을 보여 주던 길
    (scan_scope=candidate)은 그 조각을 만들던 lexicon 과 함께 없앴다.
    """
    ld = loader or BasisLoader()
    full: dict[str, list[ItemContext]] = {}
    batches: list[Batch] = []

    for item in items:
        if item.derived is not None:
            continue                          # 파생은 aggregate 가 계산한다
        full.setdefault(item.id.split("-")[0], []).append(build_item_context(item, ld))

    view = transcript.render()
    for category in sorted(full):
        group = full[category]
        size = 1 if per_item else max(1, max_batch)
        for i in range(0, len(group), size):
            chunk = group[i:i + size]
            suffix = "" if len(group) <= size else f"#{i // size + 1}"
            batches.append(Batch(batch_id=f"{category}{suffix}", contexts=chunk,
                                 transcript_view=view))
    batches.sort(key=_batch_order)
    return batches


def _batch_order(batch: Batch) -> tuple[str, int]:
    """호출 순서 — 카테고리 안에서 번호 순으로. 문자열 정렬이면 #10 이 #2 앞에 온다."""
    head, _, tail = batch.batch_id.partition("#")
    return (head, int(tail) if tail.isdigit() else 0)


def audit(batches: Sequence[Batch]) -> dict[str, Any]:
    """조립 결과 감사 — 근거가 실제로 실렸는지 사람이 보는 요약."""
    ctxs = [c for b in batches for c in b.contexts]
    with_basis = [c.item_id for c in ctxs if c.has_basis_text()]
    missing = {c.item_id: c.missing_excerpts() for c in ctxs if c.missing_excerpts()}
    ambiguous = {c.item_id: c.ambiguous_excerpts() for c in ctxs if c.ambiguous_excerpts()}
    return {
        "batches": len(batches),
        "items": len(ctxs),
        "with_basis_text": len(with_basis),
        "missing_excerpts": missing,
        "ambiguous_terms": ambiguous,
        "chars": sum(len(b.user()) for b in batches),
    }
