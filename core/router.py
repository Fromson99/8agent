"""라우터 — 코어의 유일한 문서 진입점 (SPEC §00).

    from core import router
    routed = router.route("계약서.pdf", doc_type="특정금전신탁")
    doc = routed.doc          # doc.json (공통 그릇)

코어는 문서를 모른다. `registry.yaml` 을 보고 **배차만** 한다(§00.1).
그 외 아무것도 하지 않는다 — 파싱은 플러그인이, 구조화는 형식이, 채점은 게이트가 한다.

## 이 파일이 존재하는 이유 — 강제

`route()` 는 형식·용어집 경로를 **인자로 받지 않는다.** 호출자는 doc_type 만 말할 수 있고,
무엇으로 처리할지는 registry 가 정한다. 따라서

    같은 doc_type 의 문서는 누가 호출하든 반드시 같은 규칙으로 처리된다.

에이전트가 자기 형식 파일을 몰래 끼워 넣을 구멍이 없다. 예전처럼 에이전트마다
`--format` 경로를 손으로 넘기면 agent1 과 agent6 이 같은 문서를 다르게 자를 수 있었고,
아무도 그것을 막지 못했다. 이 파일이 그 구멍을 닫는다.

## doc_type 은 호출자가 말한다

자동 판별(detect 규칙)은 뺐다: 사용자가 유형에 맞게 넣는 운영이라 "무슨 유형인지
추측"하는 층이 할 일이 없고, "그 유형이 맞긴 한가"는 구조화 뒤 fitness 게이트가
정량으로 판정한다(임계 미달 = 격리). 유형을 모르는 문서는 라우터가 아니라
구조 해석기(형식-무관 유도, api/routers/structure.py)로 들어간다.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import fitness_gate, format_model, structurize          # noqa: E402
from core import glossary as glossary_mod                          # noqa: E402
from core.parse_adapter import ParseResult                         # noqa: E402

DEFAULT_REGISTRY = ROOT / "core" / "registry.yaml"


# ===========================================================================
# 오류 — 전부 시끄럽다. 조용한 실패가 이 시스템의 최악 실패 모드다.
# ===========================================================================

class RoutingError(Exception):
    """라우팅 실패의 기반. 모든 실패는 무엇을 어떻게 고치면 되는지 말한다."""


class UnregisteredDocType(RoutingError):
    """doc_type 이 registry 에 없다."""


class RouteAssetMissing(RoutingError):
    """route 가 가리키는 형식·용어집 파일이 없거나 doc_type 이 어긋난다."""


# ===========================================================================
# registry 스키마
# ===========================================================================

class Route(BaseModel):
    """문서 유형 하나의 처리 방법 전체 — 파서·형식·용어집·게이트 임계."""
    doc_type: str
    parser: str = "auto"
    format: Optional[str] = None               # 저장소 루트 기준 상대 경로
    glossary: Optional[str] = None
    threshold: float = fitness_gate.DEFAULT_THRESHOLD
    owner: Optional[str] = None                # 등록한 에이전트 (감사용)
    note: Optional[str] = None

    def format_path(self) -> Optional[Path]:
        return (ROOT / self.format) if self.format else None

    def glossary_path(self) -> Optional[Path]:
        return (ROOT / self.glossary) if self.glossary else None


class Registry(BaseModel):
    version: int = 1
    parsers: dict[str, str] = Field(default_factory=dict)
    routes: list[Route] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Registry":
        problems: list[str] = []
        types = [r.doc_type for r in self.routes]
        for t in sorted({t for t in types if types.count(t) > 1}):
            problems.append(f"doc_type '{t}' 이 두 번 등록됐습니다 — 같은 문서가 두 규칙을 갖습니다")
        for r in self.routes:
            if r.parser not in self.parsers:
                problems.append(
                    f"route '{r.doc_type}' 의 parser '{r.parser}' 가 parsers 에 없습니다")
            if not (0.0 <= r.threshold <= 1.0):
                problems.append(f"route '{r.doc_type}' 의 threshold 가 0~1 밖입니다")
        for pid, target in self.parsers.items():
            if ":" not in target:
                problems.append(f"parsers.{pid} 는 '모듈:함수' 형태여야 합니다 (받은 값 '{target}')")
        if problems:
            raise ValueError("등록부 오류:\n  - " + "\n  - ".join(problems))
        return self

    # --- 조회 --------------------------------------------------------------
    def doc_types(self) -> list[str]:
        return [r.doc_type for r in self.routes]

    def get(self, doc_type: str) -> Route:
        """명시 모드. 없으면 비슷한 이름을 제안하며 거부한다."""
        for r in self.routes:
            if r.doc_type == doc_type:
                return r
        near = [t for t in self.doc_types() if _similar(t, doc_type)]
        hint = f" 혹시 {near} 입니까?" if near else ""
        raise UnregisteredDocType(
            f"doc_type '{doc_type}' 은 등록되지 않았습니다.{hint} "
            f"등록된 유형: {self.doc_types()}. "
            f"새 유형은 core/registry.yaml 에 route 를 추가해 등록하세요(SPEC §00.5).")

    # --- 파싱 로직 배차 ----------------------------------------------------
    def parser_for(self, route: Route) -> Callable[..., ParseResult]:
        """플러그인 ID → 호출 가능 객체. 코어는 문자열을 데이터로 읽을 뿐이다."""
        target = self.parsers[route.parser]
        module_name, _, func_name = target.partition(":")
        try:
            module = __import__(module_name, fromlist=[func_name])
        except ImportError as exc:
            raise RoutingError(
                f"파싱 로직 '{route.parser}' ({target}) 를 불러오지 못했습니다: {exc}") from exc
        fn = getattr(module, func_name, None)
        if not callable(fn):
            raise RoutingError(f"파싱 로직 '{route.parser}' 의 {target} 이 호출 가능하지 않습니다")
        return fn


# ===========================================================================
# 조회 보조
# ===========================================================================

def _similar(a: str, b: str) -> bool:
    """'특정금전신탁계약서' 를 물었는데 '특정금전신탁' 이 있을 때 알려주기 위한 것."""
    na, nb = re.sub(r"\s", "", a), re.sub(r"\s", "", b)
    return na in nb or nb in na


# ===========================================================================
# 진입점
# ===========================================================================

@dataclass
class Routed:
    """배차 결과 — 문서와, 그것을 어떻게 처리했는지의 전말.

    `glossary`·`fmt` 를 함께 싣는 이유: 소비자가 용어 별칭이나 마커 정의를 알아야 할 때
    (용어 앵커 해소, 범위 좁히기) 이것이 없으면 **자기가 파일을 다시 싣게 되고**, 그러면
    "어느 용어집을 쓸지 에이전트가 고른다"는 우회가 생긴다. 라우터가 이미 고른 것을
    그대로 건네주는 편이 옳다 — 고르는 권한은 여전히 등록부에만 있다.
    """
    doc: structurize.Document
    fitness: fitness_gate.Fitness
    route: Route
    parsed: ParseResult
    glossary: glossary_mod.Glossary    # route 가 지정한 것 (소비자가 고를 수 없다)
    fmt: format_model.Format

    @property
    def doc_type(self) -> str:
        return self.route.doc_type

    @property
    def quarantined(self) -> bool:
        return not self.fitness.passed


@lru_cache(maxsize=8)
def load(path: str | Path | None = None) -> Registry:
    """등록부를 싣는다(캐시). 경로는 **부를 때** 정한다 — 기본값을 인자에 박으면
    모듈 적재 시점에 굳어, 등록부 자리를 바꿔도 옛 파일을 계속 읽는다."""
    p = Path(path or DEFAULT_REGISTRY)
    if not p.exists():
        raise RoutingError(f"등록부를 찾을 수 없습니다: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Registry.model_validate(data)


def assets(route: Route) -> tuple[glossary_mod.Glossary, format_model.Format]:
    """route 가 가리키는 자산을 싣고, doc_type 이 서로 맞는지 확인한다.

    형식·용어집·registry 의 doc_type 이 어긋나면 "같은 유형을 같게 처리한다"가
    깨진다. 그 어긋남은 조용히 굴러가다 엉뚱한 문서를 그럴듯하게 구조화하므로,
    적재 시점에 막는다.

    용어집은 **선택**이다 — 용어는 전역 용어집이 담당하는 방향이라, 유형별
    용어집이 없는 route(UI 컴파일 등재분)는 빈 용어집으로 돈다: 용어형 마커와
    fact 추출만 비활성일 뿐 마커 구조화·게이트는 그대로다.
    """
    fp = route.format_path()
    if fp is None:
        raise RouteAssetMissing(
            f"route '{route.doc_type}' 에 형식이 없어 구조화할 수 없습니다 "
            f"(format={route.format}). "
            f"컴파일 국면(core.cli compile)으로 형식을 만든 뒤 registry 에 연결하세요.")
    if not fp.exists():
        raise RouteAssetMissing(
            f"route '{route.doc_type}' 의 형식 파일이 없습니다: {fp}")
    fmt = format_model.load(fp)

    gp = route.glossary_path()
    if gp is None:
        # route 에 용어집이 없으면 **전역 용어집**을 쓴다 — 용어는 유형별이 아니라
        # 시스템 전체의 것이라는 방향(§용어). 비어 있으면 마커만으로 돈다.
        g = glossary_mod.load_global(route.doc_type)
    else:
        if not gp.exists():
            raise RouteAssetMissing(
                f"route '{route.doc_type}' 의 용어집 파일이 없습니다: {gp}")
        g = glossary_mod.load(gp)

    mismatched = [f"{label} '{val}'" for label, val in
                  (("용어집", g.doc_type), ("형식", fmt.doc_type)) if val != route.doc_type]
    if mismatched:
        raise RouteAssetMissing(
            f"route '{route.doc_type}' 와 {', '.join(mismatched)} 의 doc_type 이 다릅니다. "
            f"세 곳이 같아야 같은 문서가 같은 규칙으로 처리됩니다.")
    return g, fmt


def route(path: str | Path, doc_type: str, *,
          registry: Optional[Registry] = None,
          threshold: Optional[float] = None) -> Routed:
    """문서 하나를 배차해 doc.json 까지 만든다 — 코어의 유일한 진입점.

    형식·용어집은 인자로 받지 않는다. 그것이 이 함수의 요점이다(모듈 설명 참조).
    doc_type 은 호출자가 말한다 — 유형이 맞긴 한지는 게이트가 정량으로 판정한다.
    """
    reg = registry or load()
    p = Path(path)
    r = reg.get(doc_type)
    if not p.exists():
        raise FileNotFoundError(f"입력 문서를 찾을 수 없습니다: {p}")

    g, fmt = assets(r)
    parsed = reg.parser_for(r)(p)
    doc = structurize.run(parsed, fmt, g)
    fit = fitness_gate.apply(doc, fmt, len(parsed.elements),
                             r.threshold if threshold is None else threshold)
    return Routed(doc=doc, fitness=fit, route=r, parsed=parsed,
                  glossary=g, fmt=fmt)


def require(path: str | Path, doc_type: str, **kw) -> Routed:
    """route() 와 같되, 게이트에 걸린 문서를 통과시키지 않는다.

    형식과 다른 문서를 그럴듯한 결과로 내보내는 것이 가장 위험한 실패 모드다(§3.4).
    태스크(비교·판정)는 이 함수를 쓴다.
    """
    routed = route(path, doc_type, **kw)
    if routed.quarantined:
        first = routed.fitness.warnings[0] if routed.fitness.warnings else ""
        raise RoutingError(
            f"'{Path(path).name}' 이 형식 '{routed.doc_type}' 과 "
            f"{routed.fitness.score:.0%}만 부합해 격리됐습니다. {first} "
            f"(다른 양식이거나 양식이 개정됐을 수 있습니다 — router.route() 로 강제할 수 있습니다)")
    return routed


def describe(registry: Optional[Registry] = None) -> str:
    """등록부를 사람이 읽는 표로 — '지금 무엇을 처리할 수 있는가'의 답."""
    reg = registry or load()
    lines = [f"등록부  {DEFAULT_REGISTRY}  (route {len(reg.routes)}개)"]
    for r in reg.routes:
        g, f = r.glossary_path(), r.format_path()
        state = "".join(("g" if g and g.exists() else "-",
                         "f" if f and f.exists() else "-"))
        lines.append(f"  {r.doc_type:<14} parser={r.parser:<11} owner={r.owner or '-':<8} "
                     f"자산[{state}] 임계 {r.threshold:.2f}")
    missing = [r.doc_type for r in reg.routes
               if not (r.glossary_path() and r.glossary_path().exists()
                       and r.format_path() and r.format_path().exists())]
    if missing:
        lines.append(f"  ! 자산 미비: {missing} — 이 유형은 배차되지 않습니다")
    return "\n".join(lines)
