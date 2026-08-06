"""라우터 — 코어의 유일한 문서 진입점 (SPEC §00).

    from core import router
    routed = router.route("계약서.pdf", doc_type="특정금전신탁")
    doc = routed.doc          # doc.json (공통 그릇)

코어는 문서를 모른다. `registry.yaml` 을 보고 **판별·배차만** 한다(§00.1).
그 외 아무것도 하지 않는다 — 파싱은 플러그인이, 구조화는 형식이, 채점은 게이트가 한다.

## 이 파일이 존재하는 이유 — 강제

`route()` 는 형식·용어집 경로를 **인자로 받지 않는다.** 호출자는 doc_type 만 말할 수 있고,
무엇으로 처리할지는 registry 가 정한다. 따라서

    같은 doc_type 의 문서는 누가 호출하든 반드시 같은 규칙으로 처리된다.

에이전트가 자기 형식 파일을 몰래 끼워 넣을 구멍이 없다. 예전처럼 에이전트마다
`--format` 경로를 손으로 넘기면 agent1 과 agent6 이 같은 문서를 다르게 자를 수 있었고,
아무도 그것을 막지 못했다. 이 파일이 그 구멍을 닫는다.

## 판별 두 모드 (§00.3)

- **명시 모드(기본)**: 호출자가 doc_type 을 지정한다. 에이전트는 대개 자기가 다루는
  문서 종류를 안다.
- **자동 모드(보조)**: doc_type 없이 부르면 detect 규칙으로 판별한다. 두 route 에
  걸치거나 어디에도 안 걸리면 **추측하지 않고 시끄럽게 거부**한다(게이트 철학).
"""

from __future__ import annotations

import json
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
from core.parse_adapter import (                                   # noqa: E402
    ParseResult, assert_readable_pdf, decode_text)

DEFAULT_REGISTRY = ROOT / "core" / "registry.yaml"
PROBE_CHARS = 20_000          # 판별에 쓰는 앞부분 분량 — 판별은 싸야 한다


# ===========================================================================
# 오류 — 전부 시끄럽다. 조용한 실패가 이 시스템의 최악 실패 모드다.
# ===========================================================================

class RoutingError(Exception):
    """라우팅 실패의 기반. 모든 실패는 무엇을 어떻게 고치면 되는지 말한다."""


class UnregisteredDocType(RoutingError):
    """명시 모드에서 doc_type 이 registry 에 없다."""


class UnregisteredDocument(RoutingError):
    """자동 모드에서 어느 route 에도 걸리지 않았다 — 미등록 유형."""


class AmbiguousDocument(RoutingError):
    """자동 모드에서 두 개 이상의 route 에 걸렸다 — 추측하지 않는다."""


class RouteAssetMissing(RoutingError):
    """route 가 가리키는 형식·용어집 파일이 없거나 doc_type 이 어긋난다."""


# ===========================================================================
# registry 스키마
# ===========================================================================

class Detect(BaseModel):
    """자동 모드 판별 규칙. 지정된 조건이 **전부** 성립해야 적중이다."""
    extension: Optional[str] = None            # ".pdf" — 확장자 제한
    content_any: list[str] = Field(default_factory=list)   # 하나라도 나오면
    content_all: list[str] = Field(default_factory=list)   # 전부 나와야
    schema_hint: Optional[str] = None          # JSON 입력의 키 이름 (예: speaker)

    def is_empty(self) -> bool:
        return not (self.extension or self.content_any or self.content_all
                    or self.schema_hint)

    def matches(self, path: Path, probe: str) -> bool:
        if self.extension and path.suffix.lower() != self.extension.lower():
            return False
        if self.content_any and not any(k in probe for k in self.content_any):
            return False
        if self.content_all and not all(k in probe for k in self.content_all):
            return False
        if self.schema_hint and not _has_key(path, probe, self.schema_hint):
            return False
        return True


class Route(BaseModel):
    """문서 유형 하나의 처리 방법 전체 — 파서·형식·용어집·게이트 임계."""
    doc_type: str
    parser: str = "auto"
    detect: Optional[Detect] = None
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

    def detect(self, path: str | Path) -> Route:
        """자동 모드. 0개면 미등록, 2개 이상이면 모호 — 어느 쪽도 추측하지 않는다."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"입력 문서를 찾을 수 없습니다: {p}")
        probe = _probe(p)
        hits = [r for r in self.routes
                if r.detect and not r.detect.is_empty() and r.detect.matches(p, probe)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise UnregisteredDocument(
                f"'{p.name}' 은 미등록 유형입니다 — 어느 route 의 detect 규칙에도 걸리지 않았습니다. "
                f"등록된 유형: {self.doc_types()}. "
                f"doc_type 을 직접 지정하거나(명시 모드), registry 에 route 를 등록하세요.")
        raise AmbiguousDocument(
            f"'{p.name}' 이 {[r.doc_type for r in hits]} 에 동시에 걸립니다 — "
            f"추측하지 않습니다. detect 규칙을 좁히거나 doc_type 을 직접 지정하세요.")

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
# 판별 보조
# ===========================================================================

def _probe(path: Path) -> str:
    """판별용 앞부분 텍스트. 싸게 얻는다 — 여기서 docling 을 부르지 않는다.

    읽지 **못하는** 파일(암호화 PDF, 인코딩 불명 텍스트)은 여기서 그 사실을 그대로
    올린다. 조용히 빈 문자열로 떨어뜨리면 detect 가 아무 route 에도 못 걸어
    "미등록 유형입니다" 라고 답하게 되는데, 그건 원인을 가리키지 않는 거짓말이다.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError:
            return ""
        assert_readable_pdf(path)          # 암호화면 여기서 이름을 대고 멈춘다
        doc = fitz.open(str(path))
        out = []
        for i, page in enumerate(doc):
            if i >= 3 or sum(len(s) for s in out) > PROBE_CHARS:
                break
            out.append(page.get_text())
        doc.close()
        return "".join(out)[:PROBE_CHARS]
    try:
        return decode_text(path)[:PROBE_CHARS]
    except OSError:
        return ""


def _has_key(path: Path, probe: str, key: str) -> bool:
    """JSON 입력의 키 존재 확인 — 최상위 객체 또는 리스트 첫 원소를 본다."""
    if path.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f'"{key}"' in probe
    if isinstance(data, dict):
        if key in data:
            return True
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and key in v[0]:
                return True
        return False
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return key in data[0]
    return False


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
    detected: bool                     # 자동 모드로 판별했는가
    glossary: glossary_mod.Glossary    # route 가 지정한 것 (소비자가 고를 수 없다)
    fmt: format_model.Format

    @property
    def doc_type(self) -> str:
        return self.route.doc_type

    @property
    def quarantined(self) -> bool:
        return not self.fitness.passed

    def dump(self) -> dict[str, Any]:
        return self.doc.dump()


@lru_cache(maxsize=8)
def load(path: str | Path = DEFAULT_REGISTRY) -> Registry:
    p = Path(path)
    if not p.exists():
        raise RoutingError(f"등록부를 찾을 수 없습니다: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Registry.model_validate(data)


def assets(route: Route) -> tuple[glossary_mod.Glossary, format_model.Format]:
    """route 가 가리키는 자산을 싣고, doc_type 이 서로 맞는지 확인한다.

    형식·용어집·registry 세 곳의 doc_type 이 어긋나면 "같은 유형을 같게 처리한다"가
    깨진다. 그 어긋남은 조용히 굴러가다 엉뚱한 문서를 그럴듯하게 구조화하므로,
    적재 시점에 막는다.
    """
    gp, fp = route.glossary_path(), route.format_path()
    if gp is None or fp is None:
        raise RouteAssetMissing(
            f"route '{route.doc_type}' 에 형식 또는 용어집이 없어 구조화할 수 없습니다 "
            f"(format={route.format}, glossary={route.glossary}). "
            f"컴파일 국면(core.cli compile)으로 형식을 만든 뒤 registry 에 연결하세요.")
    for label, p in (("용어집", gp), ("형식", fp)):
        if not p.exists():
            raise RouteAssetMissing(
                f"route '{route.doc_type}' 의 {label} 파일이 없습니다: {p}")
    g = glossary_mod.load(gp)
    fmt = format_model.load(fp)
    mismatched = [f"{label} '{val}'" for label, val in
                  (("용어집", g.doc_type), ("형식", fmt.doc_type)) if val != route.doc_type]
    if mismatched:
        raise RouteAssetMissing(
            f"route '{route.doc_type}' 와 {', '.join(mismatched)} 의 doc_type 이 다릅니다. "
            f"세 곳이 같아야 같은 문서가 같은 규칙으로 처리됩니다.")
    return g, fmt


def route(path: str | Path, doc_type: Optional[str] = None, *,
          registry: Optional[Registry] = None,
          threshold: Optional[float] = None) -> Routed:
    """문서 하나를 배차해 doc.json 까지 만든다 — 코어의 유일한 진입점.

    형식·용어집은 인자로 받지 않는다. 그것이 이 함수의 요점이다(모듈 설명 참조).
    """
    reg = registry or load()
    p = Path(path)
    if doc_type is None:
        r, detected = reg.detect(p), True
    else:
        r, detected = reg.get(doc_type), False
        if not p.exists():
            raise FileNotFoundError(f"입력 문서를 찾을 수 없습니다: {p}")

    g, fmt = assets(r)
    parsed = reg.parser_for(r)(p)
    doc = structurize.run(parsed, fmt, g)
    fit = fitness_gate.apply(doc, fmt, g, len(parsed.elements),
                             r.threshold if threshold is None else threshold)
    return Routed(doc=doc, fitness=fit, route=r, parsed=parsed, detected=detected,
                  glossary=g, fmt=fmt)


def require(path: str | Path, doc_type: Optional[str] = None, **kw) -> Routed:
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
        det = "-"
        if r.detect and not r.detect.is_empty():
            bits = []
            if r.detect.extension:
                bits.append(r.detect.extension)
            if r.detect.content_any:
                bits.append("any:" + "|".join(r.detect.content_any[:2]))
            if r.detect.schema_hint:
                bits.append(f"key:{r.detect.schema_hint}")
            det = " ".join(bits)
        lines.append(f"  {r.doc_type:<14} parser={r.parser:<11} owner={r.owner or '-':<8} "
                     f"자산[{state}] 임계 {r.threshold:.2f}  detect: {det}")
    missing = [r.doc_type for r in reg.routes
               if not (r.glossary_path() and r.glossary_path().exists()
                       and r.format_path() and r.format_path().exists())]
    if missing:
        lines.append(f"  ! 자산 미비: {missing} — 이 유형은 배차되지 않습니다")
    return "\n".join(lines)
