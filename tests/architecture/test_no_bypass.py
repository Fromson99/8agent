"""강제를 코드로 굳힌다 — 에이전트는 자기 형식을 고를 수 없다 (SPEC §00).

## 왜 이 테스트가 있는가

`core/router.py` 는 형식·용어집 경로를 인자로 받지 않는다. 그래서 라우터를 **통해**
들어오는 한 같은 doc_type 은 누구에게나 같은 규칙으로 처리된다. 문제는 라우터를
안 통하는 길이다 — 에이전트가 자기 폴더의 `*.format.json` 을 직접 실어 버리면
강제는 없는 것과 같다. 실제로 이관 전 `agents/agent1/src/service.py` 가 그랬다.

    CONTRACT_FORMAT = AGENT_ROOT / "formats" / "trust_contract.format.json"
    fmt = format_model.load(CONTRACT_FORMAT)      # ← 등록부를 우회한 처리 규칙

리뷰로 막을 수 있는 종류의 실수가 아니다(한 줄이고, 그럴듯하고, 조용하다).
그래서 `agents/` 아래 모든 소스를 AST 로 훑어 **우회 자체를 문법 수준에서** 막는다.

## 무엇이 금지인가

금지되는 것은 자산을 **고르는 것**이지 읽는 것이 아니다. route 가 준 자산을 읽는 것
(`router.assets(routed.route)`)은 등록부가 결정자로 남아 있으므로 우회가 아니다.
반면 아래 셋은 결정 권한을 에이전트로 가져오므로 금지한다.

    core.glossary.load / core.format_model.load    처리 규칙을 직접 고름
    core.parse_adapter.parse                       파서를 직접 고름 (등록부의 parser 무시)
    "*.format.json" / "*.glossary.yaml" 리터럴      경로를 코드가 짚음

컴파일 국면 도구(형식을 **만드는** 쪽)는 이 금지의 대상이 아니다 — 아직 등록부에
없는 유형을 다루기 때문이다. 그런 파일은 ALLOWED 에 이유와 함께 적는다.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

AGENTS = ROOT / "agents"

# --- 예외 허용 목록 ---------------------------------------------------------
# 경로(저장소 루트 기준) → **왜** 예외인지. 이유 없는 등재는 금지다. 여기에 한 줄
# 추가하는 것은 "이 파일은 등록부 밖에서 처리 규칙을 정할 수 있다"는 선언이므로,
# 컴파일 국면 도구(core.cli compile / core.format_induce 를 감싸는 스크립트)에만
# 허용한다. 런타임 코드는 어떤 이유로도 여기 오면 안 된다.
ALLOWED: dict[str, str] = {
    # 예) "agents/agent1/tools/compile_trust_format.py":
    #       "컴파일 국면 — 아직 등록부에 없는 유형의 형식을 만드는 도구 (§2.4)",
}

_ROUTER_HINT = ("from core import router; "
                "routed = router.route(경로, doc_type=\"...\")  →  "
                "routed.doc / routed.fitness / routed.parsed")

BANNED_CALLS: dict[str, tuple[str, str]] = {
    "core.glossary.load": (
        "용어집을 직접 싣습니다 — 어느 용어집을 쓸지 에이전트가 고르게 됩니다",
        _ROUTER_HINT + " (route 가 실어 준 용어집은 router.assets(routed.route) 로 얻습니다)"),
    "core.format_model.load": (
        "형식을 직접 싣습니다 — 같은 doc_type 이 호출자마다 다르게 잘립니다",
        _ROUTER_HINT),
    "core.parse_adapter.parse": (
        "파서를 직접 부릅니다 — 등록부가 지정한 parser 플러그인을 건너뜁니다",
        _ROUTER_HINT),
}

BANNED_SUFFIXES = (".format.json", ".glossary.yaml")


@dataclass
class Violation:
    file: str
    line: int
    what: str
    why: str
    instead: str

    def __str__(self) -> str:
        return (f"{self.file}:{self.line}  {self.what}\n"
                f"      왜 안 되는가: {self.why}\n"
                f"      대신 무엇을: {self.instead}")


# ===========================================================================
# import 별칭 해석 — `from core import glossary as glossary_mod` 를 따라간다
# ===========================================================================

class _Aliases(ast.NodeVisitor):
    def __init__(self) -> None:
        self.modules: dict[str, str] = {}     # 지역 이름 → 모듈 경로
        self.symbols: dict[str, str] = {}     # 지역 이름 → 모듈.심볼

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.asname:
                self.modules[a.asname] = a.name          # import core.glossary as g
            else:
                head = a.name.split(".")[0]              # import core.glossary
                self.modules[head] = head                #   → 'core' 로 접근한다

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for a in node.names:
            local = a.asname or a.name
            full = f"{mod}.{a.name}" if mod else a.name
            # 모듈을 가져왔는지 심볼을 가져왔는지는 AST 만으로 알 수 없다 — 양쪽에 등록해
            # `glossary_mod.load(...)` 와 `load(...)` 를 모두 해석한다.
            self.modules[local] = full
            self.symbols[local] = full


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _resolve(name: str, al: _Aliases) -> str:
    head, _, rest = name.partition(".")
    if not rest:
        return al.symbols.get(head, name)
    return f"{al.modules.get(head, head)}.{rest}"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """설명문은 금지 대상이 아니다 — 막으려는 것은 경로를 **짚는 코드**다."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def check(path: Path, source: str) -> list[Violation]:
    """파일 하나를 훑어 우회를 찾는다. 반환이 비어 있으면 통과."""
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    tree = ast.parse(source, filename=str(path))
    al = _Aliases()
    al.visit(tree)
    docstrings = _docstring_nodes(tree)
    out: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if dotted:
                target = _resolve(dotted, al)
                if target in BANNED_CALLS:
                    why, instead = BANNED_CALLS[target]
                    out.append(Violation(rel, node.lineno, f"{dotted}(...) 직접 호출",
                                         why, instead))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if node.value.endswith(BANNED_SUFFIXES):
                out.append(Violation(
                    rel, node.lineno, f"자산 경로 리터럴 '{node.value}'",
                    "형식·용어집 파일을 코드가 짚습니다 — 등록부가 아니라 이 파일이 "
                    "처리 규칙을 정하게 됩니다",
                    "core/registry.yaml 의 route 에 경로를 적고, 코드는 "
                    "doc_type 만 말하세요"))
    return out


def _agent_sources() -> list[Path]:
    return sorted(p for p in AGENTS.rglob("*.py") if "__pycache__" not in p.parts)


# ===========================================================================
# 강제
# ===========================================================================

def test_agents_do_not_bypass_the_router():
    """agents/ 아래 어떤 코드도 형식·용어집·파서를 직접 고르지 않는다."""
    violations: list[Violation] = []
    for p in _agent_sources():
        rel = str(p.relative_to(ROOT))
        if rel in ALLOWED:
            continue
        violations += check(p, p.read_text(encoding="utf-8"))

    assert not violations, (
        "\n\n등록부 우회가 발견됐습니다 — 에이전트가 처리 규칙을 스스로 고르고 있습니다.\n"
        "같은 doc_type 이 호출자마다 다르게 처리되면 이 시스템의 전제가 무너집니다.\n\n"
        + "\n".join(str(v) for v in violations)
        + "\n\n컴파일 국면 도구라면 이 파일의 ALLOWED 에 경로와 이유를 적으세요.\n")


def test_allowlist_entries_are_real_files_with_reasons():
    """예외는 썩는다 — 사라진 파일의 면제가 남아 있으면 다음 사람이 그것을 근거로 삼는다."""
    for rel, reason in ALLOWED.items():
        assert (ROOT / rel).exists(), f"ALLOWED 에 없는 파일이 남아 있습니다: {rel}"
        assert len(reason.strip()) > 10, f"ALLOWED['{rel}'] 에 이유가 없습니다"


def test_the_checker_actually_catches_a_bypass(tmp_path):
    """검사기 자신의 회귀 — 아무것도 못 잡는 그물이 되지 않게 한다."""
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        '"""설명문 안의 x.format.json 은 잡지 않는다."""\n'
        "from core import format_model, parse_adapter\n"
        "from core import glossary as glossary_mod\n"
        "from pathlib import Path\n"
        "F = Path('formats') / 'trust_contract.format.json'\n"
        "def go(p):\n"
        "    g = glossary_mod.load('x.glossary.yaml')\n"
        "    fmt = format_model.load(F)\n"
        "    return parse_adapter.parse(p), g, fmt\n",
        encoding="utf-8")
    found = check(bypass, bypass.read_text(encoding="utf-8"))
    kinds = [v.what for v in found]
    assert sum("직접 호출" in k for k in kinds) == 3, kinds
    assert sum("리터럴" in k for k in kinds) == 2, kinds      # 설명문의 것은 빠진다
    assert all(v.why and v.instead for v in found)


def test_every_agent_source_parses():
    """구문이 깨진 파일은 검사되지 않는다 — 그 자체가 구멍이므로 시끄럽게 실패한다."""
    broken = []
    for p in _agent_sources():
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as exc:
            broken.append(f"{p.relative_to(ROOT)}:{exc.lineno} {exc.msg}")
    assert not broken, "구문 오류로 우회 검사를 할 수 없는 파일:\n  " + "\n  ".join(broken)


def test_there_is_something_to_check():
    """agents/ 가 비어 있으면 이 테스트는 아무것도 지키지 않는다."""
    assert len(_agent_sources()) >= 3
