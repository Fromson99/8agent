"""관리소 — 신호를 **role 로 등록만** 한다 (SPEC §3, §6).

    role: proposer | local_guard | global_outer | global_inner

## 계약

파일 1개 = 함수 1개. 각 신호 모듈은 아래를 노출한다.

    ID          신호 이름 (파일명과 같아야 한다)
    ROLE        위 넷 중 하나
    LANG        "any" | "ko" | "en" …  (가드는 언어별로 갈린다 — §3.2)
    그리고 role 에 맞는 함수 하나
        proposer      propose(block, lex) -> list[Candidate]
        local_guard   score(cand, blocks, lex) -> dict[str, float]

core 파이프라인은 고정이고 신호는 plug-in 이다. **새 신호 추가 = 파일 떨궈 등록,
파이프라인 코드 불변.** 그래서 파이프라인은 이 관리소를 통해서만 신호를 본다.

## 어휘에 없는 것

`level` 이 없다(§6). 제안자는 "마커가 어떻게 생겼나" 와 "서수를 어떻게 읽나" 만 알고,
"몇 번째 레벨이냐" 는 절대 담지 않는다 — 레벨은 문서가 유도한다.
등록 시점에 그것을 검사한다.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from functools import lru_cache
from types import ModuleType
from typing import Iterable

ROLES = ("proposer", "local_guard", "family_coherence", "global_outer", "global_inner")

# role 별로 있어야 하는 함수 이름
ENTRYPOINT = {"proposer": "propose", "local_guard": "score"}

# 어휘에 들어오면 안 되는 이름 — 계층 지식은 신호가 아니라 문서가 쥔다(§6)
FORBIDDEN_ATTRS = ("LEVEL", "RANK", "DEPTH_ORDER", "PARENT")


class RegistryError(Exception):
    """등록 실패. 전부 시끄럽다 — 조용히 빠진 신호가 제일 찾기 어렵다."""


@dataclass
class Signal:
    id: str
    role: str
    lang: str
    module: ModuleType
    family: str = ""
    surface: str = ""

    def fn(self):
        return getattr(self.module, ENTRYPOINT[self.role])


@dataclass
class Registry:
    signals: dict[str, Signal] = field(default_factory=dict)

    def by_role(self, role: str) -> list[Signal]:
        """id 순 — 순회 순서가 결과를 흔들지 않게 한다(결정론)."""
        return sorted((s for s in self.signals.values() if s.role == role),
                      key=lambda s: s.id)

    def proposers(self, lang: str = "any") -> list[Signal]:
        return [s for s in self.by_role("proposer") if _lang_ok(s.lang, lang)]

    def guards(self, lang: str = "any") -> list[Signal]:
        return [s for s in self.by_role("local_guard") if _lang_ok(s.lang, lang)]

    def describe(self) -> str:
        lines = [f"관리소 — 신호 {len(self.signals)}개"]
        for role in ROLES:
            got = self.by_role(role)
            if not got:
                continue
            lines.append(f"  [{role}]")
            for s in got:
                extra = f"  family={s.family}" if s.family else ""
                lines.append(f"    {s.id:<18} lang={s.lang:<4}{extra}  {s.surface}")
        return "\n".join(lines)


def _lang_ok(signal_lang: str, doc_lang: str) -> bool:
    return signal_lang == "any" or doc_lang == "any" or signal_lang == doc_lang


def _register(reg: Registry, module: ModuleType, expected_role: str) -> None:
    mid = getattr(module, "ID", None)
    role = getattr(module, "ROLE", None)
    name = module.__name__.rsplit(".", 1)[-1]

    if mid is None or role is None:
        raise RegistryError(f"{module.__name__}: ID 와 ROLE 을 노출해야 등록됩니다")
    if mid != name:
        raise RegistryError(f"{module.__name__}: ID '{mid}' 가 파일명 '{name}' 과 다릅니다 "
                            f"— 신호는 이름으로 찾을 수 있어야 합니다")
    if role != expected_role:
        raise RegistryError(f"{module.__name__}: ROLE '{role}' 이 이 패키지의 역할 "
                            f"'{expected_role}' 과 다릅니다")
    if role not in ROLES:
        raise RegistryError(f"{module.__name__}: 알 수 없는 ROLE '{role}' (가능: {ROLES})")
    for bad in FORBIDDEN_ATTRS:
        if hasattr(module, bad):
            raise RegistryError(
                f"{module.__name__}: '{bad}' 를 노출합니다 — 신호는 계층 지식을 담지 "
                f"않습니다(SPEC §6). 레벨은 문서가 유도합니다")
    entry = ENTRYPOINT.get(role)
    if entry and not callable(getattr(module, entry, None)):
        raise RegistryError(f"{module.__name__}: role '{role}' 은 {entry}() 를 노출해야 합니다")
    if mid in reg.signals:
        raise RegistryError(f"신호 id '{mid}' 가 중복됩니다")

    reg.signals[mid] = Signal(
        id=mid, role=role, lang=getattr(module, "LANG", "any"), module=module,
        family=getattr(module, "FAMILY", ""), surface=getattr(module, "SURFACE", ""))


def _load_package(reg: Registry, package: str, role: str) -> None:
    pkg = importlib.import_module(package)
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        _register(reg, importlib.import_module(f"{package}.{info.name}"), role)


def load(packages: Iterable[tuple[str, str]] | None = None) -> Registry:
    """신호 패키지들을 훑어 등록한다."""
    reg = Registry()
    for package, role in (packages or (
            ("core.structure.proposers", "proposer"),
            ("core.structure.guards", "local_guard"))):
        _load_package(reg, package, role)
    if not reg.by_role("proposer"):
        raise RegistryError("제안자가 하나도 등록되지 않았습니다 — 후보를 만들 수 없습니다")
    return reg


@lru_cache(maxsize=2)
def default() -> Registry:
    return load()
