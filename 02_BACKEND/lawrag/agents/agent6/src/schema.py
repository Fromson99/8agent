"""T-A6.1 항목 스펙·리포트 스키마 — Agent6 의 데이터 계약 (AGENT6 §4·§7).

이 파일에는 **도메인 지식이 없다.** 어떤 항목을 점검하는지, 무슨 표현이 위반 신호인지는
전부 `checklist/items/*.yaml` 이 정한다. 여기서는 그 파일이 지켜야 할 형태를 검증하고,
런타임이 읽을 모델로 만들어 줄 뿐이다(§3 말미: INT 확보 시 표 전체를 교체해도 코드는
그대로여야 한다).

검증이 곧 안전장치인 곳 — 조용히 넘어가면 놓침이 되는 것들:
  · 부재형의 fail_route 는 반드시 준법감시큐다. 이미 한 말은 PB 재설명으로 지워지지 않는다.
  · basis 는 파일 경로가 아니라 **근거의 좌표**다 — 용어 앵커("KOFIA-R#고령투자자")이거나
    section 좌표("KSB/제19조/제3항")다. 경로를 적으면 거부한다.
  · 파일 하나가 깨지면 로드 전체가 실패한다. 항목이 27개만 로드되고 3개가 조용히 빠지는
    것이 이 시스템에서 가장 위험한 실패다(리포트는 여전히 "전부 통과"라고 말할 것이다).

## lexicon 이 여기 없는 이유 (2026-08 제거)

예전에는 항목마다 `lexicon: {hit: [...], guard: [...]}` 를 두고 전사에서 문자열을 찾아
위반을 판정했다. 적대적 검증에서 무너졌다 — "지수가 여기서 더 내려갈 일은 없으니
안심하셔도 됩니다"가 D-20 을 통과했고, guard 한 어절("원금 보장 안 됩니다만, …")이 위반을
통째로 지웠으며, 변이 테스트는 목록에 있는 표현만 주입하도록 강제되어 자기 자신을
채점했다. 한국어는 같은 뜻을 백 가지로 말한다 — 목록으로 따라잡는 것은 원리적으로
불가능하다. **판정은 전부 LLM 이 하고, 문자열 매칭으로 위반을 판정하는 코드는 남기지
않는다.** 그 자리를 메우는 것이 두꺼운 `operational_definition` 과 `few_shot` 이며,
비대칭 임계는 evidence 강등·PB 발화 규칙·자기일관성·인용 좌표 대조가 지킨다.
"""

from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Optional

import yaml
from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

from lawrag.agents.agent6.src import when as when_dsl

# --- 어휘 (§5 좌표·포맷 규약) ------------------------------------------------

ItemType = Literal["존재형", "부재형", "충분성형"]
Verdict = Literal["PASS", "FAIL", "UNCLEAR", "NOT_APPLICABLE"]
FewShotVerdict = Literal["PASS", "FAIL", "UNCLEAR"]
Route = Literal["PB보완", "준법감시큐"]
Confidence = Literal["high", "medium", "low"]
Overall = Literal["완전판매요건충족", "보완필요"]

CONFIDENCE_ORDER: tuple[str, ...] = ("high", "medium", "low")

ITEM_ID_RE = re.compile(r"^[A-F]-\d{2}$")
# 코퍼스 ID 목록을 코드에 박지 않는다 — 어떤 문서를 쓰는지는 corpus/manifest.json 의 몫이다.
# 여기서는 "ID처럼 생겼는가"만 본다(KSB, KSB-D, KOFIA-R, REC, CASE, INT …).
DOC_ID_RE = re.compile(r"^[A-Z][A-Z0-9-]*$")

# 좌표 표기의 구분자. `/` 는 section 경로를, `#` 는 용어 앵커를 가른다 —
# 용어 안에 이 둘이 들어오면 좌표를 되읽을 수 없으므로 거부한다.
COORD_SEPARATORS = ("/", "#")

# 운영 정의가 이 길이보다 짧으면 경고한다. lexicon 이 사라진 뒤 판정의 근거는 이것뿐이라
# "무엇이 위반인가"를 예시까지 담아 적어야 판정자가 표현이 바뀐 위반을 잡는다.
THIN_DEFINITION_CHARS = 200

# 항목당 권장 few_shot 수(PASS 예 / FAIL 예 / 경계 예). 미만이면 경고.
MIN_FEW_SHOT = 3


def downgrade(confidence: str, steps: int = 1) -> str:
    """confidence 를 steps 단계 낮춘다. when 이 UNKNOWN 으로 활성된 항목 등에 쓴다."""
    try:
        i = CONFIDENCE_ORDER.index(confidence)
    except ValueError:
        raise ValueError(f"confidence '{confidence}' 는 {CONFIDENCE_ORDER} 중 하나여야 합니다")
    return CONFIDENCE_ORDER[min(i + max(steps, 0), len(CONFIDENCE_ORDER) - 1)]


class ChecklistLoadError(ValueError):
    """항목 스펙 로드 실패. 어떤 파일이 왜 깨졌는지 반드시 담는다."""


class ChecklistWarning(UserWarning):
    """로드는 되지만 사람이 봐야 하는 것 (예: 운영 정의가 얇은 항목)."""


# --- 항목 스펙 (§4) ----------------------------------------------------------

def basis_ref(query: str, resolved: Optional[str] = None) -> str:
    """리포트에 실을 근거 표기 — **무엇을 물었나**와 **어디로 해소됐나**를 둘 다 남긴다.

        basis_ref("KOFIA-R#고령투자자", "KOFIA-R/Ⅳ/Ⅳ-2/11.")
          → "KOFIA-R#고령투자자 → KOFIA-R/Ⅳ/Ⅳ-2/11."

    해소 결과만 남기면 "왜 하필 그 조문인가"가 사라지고, 물은 것만 남기면 "정말 그 자리로
    갔는가"를 확인할 수 없다. 화살표 표기가 이 파일 하나에만 있어야 리포트·안내문·큐가
    같은 모양을 쓴다.
    """
    return query if not resolved or resolved == query else f"{query} → {resolved}"


class Basis(BaseModel):
    """근거 좌표. "미리 연결"의 실체 — 런타임은 이 좌표의 발췌만 읽는다(§2).

    두 가지로 적는다.

      · **용어 앵커** `{ doc: KOFIA-R, term: 고령투자자 }` — 권장. 코퍼스 doc.json 의
        facts 에서 그 용어를 찾아 section 좌표를 얻는다. 손으로 조 번호를 세지 않아도
        되고, 법 개정으로 번호가 밀려도 용어는 남는다(준법 시스템에서 이 차이가 크다).
      · **좌표 직접 지정** `{ doc: KSB, section: "제21조/제1호" }` — 번호를 이미 아는
        경우. 금소법처럼 조/항/호가 규칙적인 문서는 이쪽이 정확하다.

    둘을 함께 적으면 "이 좌표 **안에서** 그 용어를 찾는다"는 뜻이다(범위 좁히기).
    **둘 다 없으면 거부한다.** 예전에는 `{ doc: REC }` 처럼 코퍼스 ID 만 적는 것을
    허용했지만 그것은 근거가 아니라 수집 대기 메모였고, 어느 조문을 말하는지 아무도 몰라
    영원히 미해소로 남았다. 수집 대기는 항목의 `note` 에 적는다 — basis 는 근거의 자리다.

    해소(용어 → section 좌표)는 여기서 하지 않는다. 코퍼스 manifest 와 `basis.py` 의
    몫이고, 여기서는 좌표의 **형태**만 본다.
    """
    doc: str
    term: Optional[str] = None
    section: Optional[str] = None
    note: Optional[str] = None

    @field_validator("doc")
    @classmethod
    def _doc_id(cls, v: str) -> str:
        if not DOC_ID_RE.match(v):
            raise ValueError(f"basis.doc '{v}' 는 코퍼스 ID 형식(대문자·숫자·-)이어야 합니다")
        return v

    @field_validator("term")
    @classmethod
    def _term(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("basis.term 이 비어 있습니다 (모르면 필드를 아예 쓰지 않는다)")
        if any(sep in s for sep in COORD_SEPARATORS):
            raise ValueError(f"basis.term '{v}' 에 좌표 구분자({', '.join(COORD_SEPARATORS)})가 "
                             "있습니다 — 용어는 원문에 나오는 낱말 그대로 적는다")
        return s

    @field_validator("section")
    @classmethod
    def _section_coord(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("basis.section 이 비어 있습니다 (모르면 필드를 아예 쓰지 않는다)")
        if "\\" in s or ".." in s or Path(s).suffix:
            raise ValueError(f"basis.section '{v}' 가 파일 경로처럼 보입니다 — "
                             "좌표는 section 경로다 (예: 제19조/제3항)")
        if s.startswith("/") or s.endswith("/") or any(not p.strip() for p in s.split("/")):
            raise ValueError(f"basis.section '{v}' 의 경로 성분이 비어 있습니다")
        if "#" in s:
            raise ValueError(f"basis.section '{v}' 에 '#' 가 있습니다 — 용어는 term 에 적는다")
        return s

    @model_validator(mode="after")
    def _needs_anchor_or_coord(self) -> "Basis":
        if self.term is None and self.section is None:
            raise ValueError(
                f"basis '{self.doc}' 에 term 도 section 도 없습니다 — 코퍼스 ID 만으로는 "
                f"근거를 특정할 수 없습니다. 원문에 실제로 나오는 용어를 term 으로 걸거나, "
                f"조문 좌표를 section 으로 적으세요. 원문 자체가 없으면 basis 에서 빼고 "
                f"항목의 note 에 수집 대기 사실을 적습니다")
        return self

    @property
    def anchored(self) -> bool:
        """용어 앵커인가 — 해소가 필요한 basis 다."""
        return self.term is not None

    @property
    def pinned(self) -> bool:
        """section 좌표가 스펙에 이미 박혀 있는가."""
        return self.section is not None

    def coordinate(self) -> str:
        """스펙이 **물은** 좌표. manifest·리포트의 키이며 발췌를 찾는 입력이다.

            { doc: KSB,     section: 제21조/제1호 }        → "KSB/제21조/제1호"
            { doc: KOFIA-R, term: 고령투자자 }              → "KOFIA-R#고령투자자"
            { doc: KSB,     term: 설명의무, section: 제19조 } → "KSB/제19조#설명의무"
        """
        base = f"{self.doc}/{self.section}" if self.section else self.doc
        return f"{base}#{self.term}" if self.term else base

    def excerpt_relpath(self) -> Optional[str]:
        """컴파일 타임에 물질화되는 발췌 파일의 위치(§2).

        용어 앵커는 **해소되기 전에는 알 수 없다** — 어느 section 으로 갈지가 facts 에
        달려 있기 때문이다. None 을 돌려주고, 실제 경로는 manifest 가 적는다.
        """
        if self.term is not None or not self.section:
            return None
        return f"corpus/excerpts/{self.doc}/{self.section.replace('/', '_')}.txt"


class FewShot(BaseModel):
    """사람이 해소한 결과가 여기로 재적재된다(§6 수렴 루프, harvest CLI)."""
    utterance: str
    verdict: FewShotVerdict
    reason: str
    source: Optional[str] = None        # 어디서 왔는가 (예: "queue/2026-08-05", "CASE/2023-046")

    @field_validator("utterance", "reason")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("few_shot 의 utterance·reason 은 비울 수 없습니다")
        return v


class JudgmentHints(BaseModel):
    """유형이 라우팅을 결정한다(§4 말미). 기본값에 기대지 말고 스펙에 적게 한다.

    `scan_scope` 는 없앴다(2026-08). 값이 `candidate` 이면 "lexicon 이 찾은 후보 발화
    주변만 본다"는 뜻이었는데, 후보를 만들던 lexicon 이 사라져 어떤 값을 적어도 전사
    전문을 읽는다. 아무 일도 하지 않는 손잡이는 남겨 두면 켜 놓고 켰다고 믿게 된다.
    """
    fail_route: Route
    unclear_route: Route = "준법감시큐"     # §6: 모든 UNCLEAR 는 사람에게 간다


class Derived(BaseModel):
    """파생 항목 규칙 — 충분성을 직접 판정하지 않고 관찰 가능한 항목의 논리 조합으로 만든다.

    F-29("위험 설명의 충분성")가 이 형태다. "충분히 설명했는가"는 LLM 에게도 열린 문제라
    판정이 흔들린다. 대신 B-07·B-09·F-28 처럼 존재 여부가 명확한 항목의 곱으로 정의하면
    결정론이 되고, 실패했을 때 PB 에게 "무엇을 더 말해야 하는지"까지 나온다.
    """
    all_pass: list[str] = Field(default_factory=list)   # 전부 PASS 여야 PASS
    any_fail: list[str] = Field(default_factory=list)   # 하나라도 FAIL 이면 FAIL
    note: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "Derived":
        if not self.all_pass and not self.any_fail:
            raise ValueError("derived 규칙이 비어 있습니다 (all_pass / any_fail 중 하나는 필요)")
        for ref in self.sources():
            if not ITEM_ID_RE.match(ref):
                raise ValueError(f"derived 가 참조하는 '{ref}' 는 항목 id 형식이 아닙니다")
        if len(self.sources()) != len(set(self.sources())):
            raise ValueError("derived 의 참조 항목이 중복됩니다")
        return self

    def sources(self) -> list[str]:
        return [*self.all_pass, *self.any_fail]

    def evaluate(self, verdicts: Mapping[str, str]) -> str:
        """참조 항목의 판정으로 이 항목의 판정을 만든다. **LLM 을 부르지 않는다**(§9-5).

        NOT_APPLICABLE 인 참조는 계산에서 빠진다(비활성 항목이 파생을 끌어내리면 안 된다).
        참조가 아예 없으면 예외 — 집계 순서가 틀렸다는 뜻이지 PASS 가 아니다.
        """
        missing = [r for r in self.sources() if r not in verdicts]
        if missing:
            raise ValueError(f"파생 계산에 필요한 판정이 없습니다: {', '.join(missing)}")
        live = {r: verdicts[r] for r in self.sources() if verdicts[r] != "NOT_APPLICABLE"}
        if not live:
            return "NOT_APPLICABLE"
        if any(verdicts[r] == "FAIL" for r in self.any_fail if r in live):
            return "FAIL"
        checked = [verdicts[r] for r in self.all_pass if r in live]
        if any(v == "FAIL" for v in checked):
            return "FAIL"
        if any(v != "PASS" for v in checked):
            return "UNCLEAR"                # UNCLEAR 가 섞이면 충분성도 단정할 수 없다
        return "PASS"


class ChecklistItem(BaseModel):
    """항목 스펙 하나 — 이 시스템의 심장(§4)."""
    id: str
    name: str
    type: ItemType
    when: str = "always"
    basis: list[Basis] = Field(default_factory=list)
    operational_definition: str
    few_shot: list[FewShot] = Field(default_factory=list)
    judgment_hints: JudgmentHints
    derived: Optional[Derived] = None
    enabled: bool = True                    # 끄는 것도 스펙에 남긴다 (파일 삭제 금지)
    note: Optional[str] = None              # 번역·판단 근거 기록 (예: when 자연어를 어떻게 옮겼나)

    _when_ast: Any = PrivateAttr(default=None)
    _warnings: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "ChecklistItem":
        problems: list[str] = []
        if not ITEM_ID_RE.match(self.id):
            problems.append(f"id '{self.id}' 는 'A-01' 형식이어야 합니다")
        if not self.name.strip():
            problems.append("name 이 비어 있습니다")
        if len(self.operational_definition.strip()) < 20:
            problems.append("operational_definition 이 너무 짧습니다 — "
                            "판정자가 읽고 바로 판정할 수 있어야 합니다")
        # when 은 로드 시점에 파싱한다. 런타임에 터지면 판정 도중에 멈춘다.
        try:
            self._when_ast = when_dsl.parse(self.when)
        except when_dsl.WhenSyntaxError as exc:
            problems.append(str(exc))

        # 유형↔라우팅 정합. 부재형 위반은 **이미 발화된 사실**이라 재설명으로 소거되지 않는다.
        if self.type == "부재형":
            if self.judgment_hints.fail_route != "준법감시큐":
                problems.append("부재형의 fail_route 는 '준법감시큐' 여야 합니다 — "
                                "이미 한 말은 PB 재설명으로 지울 수 없습니다")
            if self.judgment_hints.unclear_route != "준법감시큐":
                problems.append("부재형의 unclear_route 는 '준법감시큐' 여야 합니다")

        # 파생 항목은 독립 LLM 판정을 하지 않는다(§3 주). 유형도 충분성형이어야 앞뒤가 맞는다.
        if self.derived is not None:
            if self.type != "충분성형":
                problems.append(f"derived 를 가진 항목의 type 은 '충분성형' 이어야 합니다 "
                                f"(현재 '{self.type}')")
            if self.id in self.derived.sources():
                problems.append("derived 가 자기 자신을 참조합니다")

        if problems:
            raise ValueError("항목 스펙 오류:\n  - " + "\n  - ".join(problems))

        # --- 경고 (로드는 되지만 사람이 봐야 한다) ---
        #
        # lexicon 을 없앤 뒤 판정자가 읽는 것은 운영정의·근거발췌·few_shot 셋뿐이다.
        # 그래서 경고도 "표현 목록이 비었나"가 아니라 **판정 재료가 얇은가**를 본다.
        w = self._warnings
        if self.derived is None:
            if len(self.operational_definition.strip()) < THIN_DEFINITION_CHARS:
                w.append(f"{self.id}: operational_definition 이 얇습니다"
                         f"({len(self.operational_definition.strip())}자) — 판정 근거가 이것뿐이므로 "
                         f"위반 예·적법 예를 각각 셋 이상, 표현을 바꾼 위반까지 적으세요")
            if len(self.few_shot) < MIN_FEW_SHOT:
                w.append(f"{self.id}: few_shot 이 {len(self.few_shot)}개입니다 — "
                         f"PASS 예·FAIL 예·경계 예로 {MIN_FEW_SHOT}개 이상을 권합니다")
            if self.type == "부재형" and not any(f.verdict == "FAIL" for f in self.few_shot):
                w.append(f"{self.id}: 부재형인데 FAIL 예시가 없습니다 — "
                         f"무엇이 위반인지 보여 주지 않으면 판정자가 경계에서 PASS 로 기웁니다")
            if not self.basis:
                w.append(f"{self.id}: basis 가 비어 있습니다 — 근거 발췌 없이 판정합니다"
                         f"(원문 수집 대기라면 항목의 note 에 그 사실을 적으세요)")
        if self.type == "존재형" and self.judgment_hints.fail_route != "PB보완":
            w.append(f"{self.id}: 존재형 미비는 보통 PB 재설명으로 해소됩니다 "
                     f"(fail_route={self.judgment_hints.fail_route})")
        if self.derived is not None and self.few_shot:
            w.append(f"{self.id}: 파생 항목에 few_shot 이 있습니다 — 독립 판정으로 오해될 수 있습니다")
        return self

    # --- 조회 ---------------------------------------------------------------
    @property
    def load_warnings(self) -> list[str]:
        return list(self._warnings)

    def when_ast(self) -> Any:
        return self._when_ast

    def when_fields(self) -> set[str]:
        return when_dsl.fields(self._when_ast)

    def activation(self, meta: Any = None) -> when_dsl.WhenResult:
        """메타로 활성 여부를 판정한다. UNKNOWN 은 보수적 활성 + confidence 감점이다."""
        return when_dsl.evaluate(self._when_ast, meta)

    def basis_refs(self) -> list[str]:
        """스펙이 물은 좌표들. 용어 앵커는 `KOFIA-R#고령투자자` 꼴로 섞여 나온다."""
        return [b.coordinate() for b in self.basis]

    def anchored_basis(self) -> list[Basis]:
        """용어 앵커인 근거 — 코퍼스 facts 에서 해소해야 하는 것들이다.

        (예전의 `unresolved_basis()` 를 대신한다. "해소됐는가"는 스펙이 아니라 manifest 가
        아는 사실이라 여기서 답할 수 없다 — 여기서는 "해소가 필요한가"만 안다.)
        """
        return [b for b in self.basis if b.anchored]

    def route_for(self, verdict: str) -> Optional[Route]:
        if verdict == "FAIL":
            return self.judgment_hints.fail_route
        if verdict == "UNCLEAR":
            return self.judgment_hints.unclear_route
        return None

    def dump(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


# --- 로더 --------------------------------------------------------------------

def load_item(path: str | Path) -> ChecklistItem:
    """파일 하나를 항목으로. 실패는 전부 ChecklistLoadError 로 올린다."""
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ChecklistLoadError(f"{p}: YAML 을 읽지 못했습니다 — {exc}") from exc
    if not isinstance(data, dict):
        raise ChecklistLoadError(f"{p}: 항목 스펙은 매핑이어야 합니다 (읽은 것: {type(data).__name__})")
    try:
        item = ChecklistItem.model_validate(data)
    except Exception as exc:                     # pydantic ValidationError 포함
        raise ChecklistLoadError(f"{p}: {exc}") from exc
    if p.stem != item.id:
        raise ChecklistLoadError(f"{p}: 파일명이 id 와 다릅니다 (id={item.id} → {item.id}.yaml)")
    return item


def load_items(directory: str | Path, *, warn: bool = True) -> list[ChecklistItem]:
    """디렉터리의 항목 스펙 전부를 로드한다.

    **조용한 스킵이 없다**: 파일 하나가 깨지면 전체가 실패한다. 27개만 로드되고 3개가
    빠진 채로 "활성 항목 전부 PASS" 리포트가 나가는 것이 최악의 실패다(§0 원칙 4).
    """
    d = Path(directory)
    if not d.is_dir():
        raise ChecklistLoadError(f"항목 디렉터리가 없습니다: {d}")
    paths = sorted(p for p in d.iterdir() if p.suffix in (".yaml", ".yml"))
    if not paths:
        raise ChecklistLoadError(f"항목 스펙이 하나도 없습니다: {d}")

    items: list[ChecklistItem] = []
    seen: dict[str, Path] = {}
    for p in paths:
        item = load_item(p)
        if item.id in seen:
            raise ChecklistLoadError(f"{p}: id '{item.id}' 가 {seen[item.id]} 와 중복됩니다")
        seen[item.id] = p
        items.append(item)

    ids = {i.id for i in items}
    for item in items:
        if item.derived is None:
            continue
        for ref in item.derived.sources():
            if ref not in ids:
                raise ChecklistLoadError(
                    f"{seen[item.id]}: derived 가 없는 항목 '{ref}' 을 참조합니다")
            src = next(i for i in items if i.id == ref)
            if src.derived is not None:
                raise ChecklistLoadError(
                    f"{seen[item.id]}: derived 가 또 다른 파생 항목 '{ref}' 을 참조합니다 — "
                    "파생의 연쇄는 금지한다(순환 위험)")

    if warn:
        for item in items:
            for msg in item.load_warnings:
                warnings.warn(msg, ChecklistWarning, stacklevel=2)
    return sorted(items, key=lambda i: i.id)


# --- 전사 메타 (§1) ----------------------------------------------------------

class TranscriptMeta(BaseModel):
    """상품·고객 메타. **전부 선택**이다 — 없으면 when 이 UNKNOWN 으로 보수 활성된다.

    아래 필드는 항목 스펙의 when 이 실제로 참조하는 것들이다. 새 필드가 필요하면 스펙에
    쓰고 여기에 선언한다(모르는 키도 받아 두되, 선언된 것은 형이 검사된다).
    """
    model_config = {"extra": "allow"}

    product_type: Optional[str] = None            # ELS | ELB | DLS | DLB | 펀드 | 신탁 …
    customer_age: Optional[int] = None
    risk_profile: Optional[str] = None            # 안정형 | 안정추구형 | 위험중립형 …
    is_high_difficulty: Optional[bool] = None     # 고난도금융투자상품 여부
    is_suitable: Optional[bool] = None            # 투자성향 대비 적합 여부 (E-26)
    has_early_termination_penalty: Optional[bool] = None   # 중도해지 불이익 유무 (B-13)
    has_withdrawal_right: Optional[bool] = None   # 청약철회권 대상 상품 여부 (C-16)
    customer_question_count: Optional[int] = None # 전처리가 전사에서 세어 넣는다 (F-30)
    stt_confidence: Optional[float] = None        # STT 신뢰도 — confidence 에 반영(§11)

    def as_dict(self) -> dict[str, Any]:
        """when 평가용 사전. None 은 '없음'과 같게 취급되므로 그대로 넘긴다."""
        return self.model_dump()


# --- 리포트 (§7) --------------------------------------------------------------

class EvidenceSpan(BaseModel):
    """근거 인용. 이것을 못 대면 판정은 무효다(§0 원칙 3)."""
    text: str
    start: Optional[float] = None          # 초 단위 타임스탬프
    end: Optional[float] = None
    section_id: Optional[str] = None       # 발화001 … (전사 section 좌표, §5 규약)
    char_start: Optional[int] = None       # 타임스탬프 없는 평문 txt 의 대체 좌표
    char_end: Optional[int] = None

    @model_validator(mode="after")
    def _has_locator(self) -> "EvidenceSpan":
        if not self.text.strip():
            raise ValueError("evidence.text 가 비어 있습니다")
        if (self.start is None and self.section_id is None and self.char_start is None):
            raise ValueError("evidence 에 좌표가 없습니다 (start / section_id / char_start 중 하나)")
        return self


class ItemVerdict(BaseModel):
    """리포트의 한 행. 활성 항목은 **정확히 한 행씩** 나타난다(§7).

    `basis_refs` 는 `basis_ref()` 가 만든 문자열이다 — 용어 앵커면
    "KOFIA-R#고령투자자 → KOFIA-R/Ⅳ/Ⅳ-2/11." 처럼 물은 것과 해소된 곳이 함께 남는다.

    `method` 는 판정이 어떻게 나왔는지다(자유 문자열이되 아래를 정본으로 쓴다):
      llm · derived · evidence_missing · evidence_unverified · evidence_speaker(고객
      발화만 인용한 존재형) · self_conflict(자기일관성 k회 불일치) · llm_missing.
    `lexicon_hits` 는 없앴다 — 문자열 매칭 판정을 하지 않으므로 실을 적중이 없다.
    """
    id: str
    name: str
    type: ItemType
    active: bool
    verdict: Verdict
    route: Optional[Route] = None
    evidence: Optional[list[EvidenceSpan]] = None
    llm_reason: Optional[str] = None
    basis_refs: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    method: str = "llm"
    inactive_reason: Optional[str] = None  # 비활성 사유 — §7 이 명시를 요구한다
    when_notes: list[str] = Field(default_factory=list)   # "메타 부족: customer_age" 등

    @model_validator(mode="after")
    def _check(self) -> "ItemVerdict":
        problems: list[str] = []
        if not ITEM_ID_RE.match(self.id):
            problems.append(f"id '{self.id}' 형식 오류")
        # 비활성과 NOT_APPLICABLE 은 같은 사실의 두 표현이다. 어긋나면 집계가 틀어진다.
        if self.active and self.verdict == "NOT_APPLICABLE":
            problems.append("active=true 인데 판정이 NOT_APPLICABLE 입니다")
        if not self.active:
            if self.verdict != "NOT_APPLICABLE":
                problems.append(f"active=false 인데 판정이 '{self.verdict}' 입니다")
            if not (self.inactive_reason or "").strip():
                problems.append("비활성 항목에는 inactive_reason 이 필요합니다")
        # FAIL/UNCLEAR 는 반드시 갈 곳이 있어야 한다. 라우팅 없는 미비는 사라진 미비다.
        if self.verdict in ("FAIL", "UNCLEAR") and self.route is None:
            problems.append(f"{self.verdict} 인데 route 가 없습니다")
        if problems:
            raise ValueError(f"항목 판정({self.id}) 오류:\n  - " + "\n  - ".join(problems))
        return self


class Report(BaseModel):
    """report.json (§7)."""
    transcript: str
    checklist_version: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    overall: Overall = "보완필요"
    items: list[ItemVerdict] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    unclear_rate_history: dict[str, list[float]] = Field(default_factory=dict)
    meta: Optional[TranscriptMeta] = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_rows(self) -> "Report":
        ids = [i.id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("리포트에 같은 항목이 두 번 나타납니다")
        return self

    def recount(self) -> "Report":
        """stats 와 overall 을 항목에서 다시 계산한다. 손으로 세지 않는다."""
        v = [i.verdict for i in self.items]
        self.stats = {
            "total": len(v),
            "active": sum(1 for i in self.items if i.active),
            "pass": v.count("PASS"),
            "fail": v.count("FAIL"),
            "unclear": v.count("UNCLEAR"),
            "not_applicable": v.count("NOT_APPLICABLE"),
        }
        # 자동 통과 문턱이 가장 높다(§0 원칙 4): FAIL 도 UNCLEAR 도 하나 없어야 통과다.
        self.overall = ("완전판매요건충족"
                        if self.stats["fail"] == 0 and self.stats["unclear"] == 0
                        else "보완필요")
        return self

    def assert_complete(self, items: Iterable[ChecklistItem]) -> "Report":
        """체크리스트의 모든 항목이 리포트에 한 행씩 있는지 — 조용한 스킵 검출(§9-3)."""
        expected = {i.id for i in items if i.enabled}
        got = {i.id for i in self.items}
        missing, extra = sorted(expected - got), sorted(got - expected)
        if missing or extra:
            raise ValueError(
                "리포트 행이 체크리스트와 맞지 않습니다"
                + (f" — 빠짐: {', '.join(missing)}" if missing else "")
                + (f" — 없는 항목: {', '.join(extra)}" if extra else ""))
        return self

    def dump(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class GuidanceEntry(BaseModel):
    """guidance.md 의 한 항목 — PB 가 지금 다시 말해야 하는 것(§5-7)."""
    item_id: str
    name: str
    verdict: Verdict
    route: Route
    missing: str                            # 무엇이 빠졌는가
    recommended_script: str = ""            # 권장 안내 문구 (basis 기반)
    basis_refs: list[str] = Field(default_factory=list)
    status: Literal["재안내필요", "검토중"] = "재안내필요"

    @model_validator(mode="after")
    def _route_status(self) -> "GuidanceEntry":
        # 준법감시큐로 간 항목은 PB 가 재설명해서 해소할 수 없다 — 안내문에는 "검토 중"으로만 뜬다.
        if self.route == "준법감시큐" and self.status != "검토중":
            raise ValueError(f"{self.item_id}: 준법감시큐 항목은 status='검토중' 이어야 합니다")
        return self


class QueueEntry(BaseModel):
    """review_queue.jsonl 의 한 줄. 사람 해소 결과가 few_shot 으로 돌아온다(§6·§8 harvest)."""
    transcript: str
    item_id: str
    name: str
    type: ItemType
    verdict: Verdict
    route: Route
    reason: str = ""
    confidence: Confidence = "low"
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    basis_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    # --- 사람이 채우는 칸 ---
    resolved_verdict: Optional[FewShotVerdict] = None
    resolved_reason: Optional[str] = None
    resolver: Optional[str] = None
    resolved_at: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.resolved_verdict is not None

    def to_few_shot(self) -> FewShot:
        """해소된 큐 항목 → few_shot. 이것이 §6 수렴 루프의 마지막 한 걸음이다."""
        if not self.resolved:
            raise ValueError(f"{self.item_id}: 아직 해소되지 않은 큐 항목은 few_shot 이 될 수 없습니다")
        utterance = self.evidence[0].text if self.evidence else ""
        if not utterance.strip():
            raise ValueError(f"{self.item_id}: 인용 발화가 없어 few_shot 을 만들 수 없습니다")
        return FewShot(utterance=utterance, verdict=self.resolved_verdict,
                       reason=self.resolved_reason or "사람 해소",
                       source=f"queue/{self.created_at}")
