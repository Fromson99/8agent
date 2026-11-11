#!/usr/bin/env python3
"""Run pytest against one exact code tree (a release or a staged candidate).

run_tests.py --code-root starts one of these per batch.  The product packages
(semantic_runtime, workflow, lawrag modules that the tree contains) are imported
from CODE_ROOT; tests, fixtures and tool modules still come from the workspace.
This is the isolation the per-audit ``pytest_contracts.py`` copies used:

  * pytest.ini is not read (``-c /dev/null``) because its ``pythonpath = 02_BACKEND .``
    would put the working tree in front of the code tree;
  * 05_TESTS/conftest.py is loaded once as a plugin (``--noconftest``) after the
    standard ``inspect`` module, so 06_TOOLS/EXPERIMENTS/adr_0928/inspect.py cannot shadow it;
  * lawrag subpackages missing from the tree fall back to the workspace copy.

After the run it writes which product modules were loaded and from where; any
product module loaded from outside CODE_ROOT is an isolation violation and
makes the batch fail.

usage: pytest_code_root.py --code-root DIR --report FILE -- <pytest arguments>
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_PACKAGES = ('semantic_runtime', 'workflow', 'lawrag')
LAWRAG_SUBPACKAGES = ('pipeline', 'core', 'research')


def isolate(code: Path) -> None:
    os.environ.update(AD_WORKER_ENABLED='0', GENOS_AUTO_WARMUP='0', PYTHONDONTWRITEBYTECODE='1',
                      LOOP_TEST_CODE_ROOT=str(code), WORKFLOW_TEST_CODE_ROOT=str(code),
                      GENOS_ONTOLOGY_CODE_ROOT=str(code))
    sys.dont_write_bytecode = True  # a verified tree must not gain .pyc files
    sys.path[:0] = [str(code / '02_BACKEND'), str(code), str(ROOT / '05_TESTS'),
                    str(ROOT / '05_TESTS' / 'CONTRACTS'), str(ROOT / '06_TOOLS' / 'COMMANDS')]
    import lawrag
    lawrag.__path__.append(str(ROOT / '02_BACKEND' / 'lawrag'))
    for name in LAWRAG_SUBPACKAGES:
        try:
            package = importlib.import_module('lawrag.' + name)
        except ImportError:
            continue
        package.__path__.append(str(ROOT / '02_BACKEND' / 'lawrag' / name))
    import inspect, dataclasses, traceback  # noqa: E401,F401  stdlib before conftest
    # The conftest's tool-path setup puts 06_TOOLS/COMMANDS first; the code tree goes back in front.
    import conftest  # noqa: F401  (05_TESTS/conftest.py)
    sys.path[:0] = [str(code / '02_BACKEND'), str(code)]
    # Bind the workflow package to the tree now. Some test modules put the workspace 02_BACKEND in
    # front of sys.path at import; a later first `import workflow` then took the workspace copy
    # (2026-11-11, seen once the tree's workflow/repository.py differed from the workspace).
    if (code / '02_BACKEND' / 'workflow' / '__init__.py').is_file():
        importlib.import_module('workflow')


def loaded_outside(code: Path) -> tuple[dict[str, str], list[str], list[str]]:
    """(violations, same-bytes copies, workspace fallbacks) among the imported product modules.

    Every semantic_runtime module must come from the tree, as in the old
    per-audit runners.  A lawrag or workflow module that the tree does not
    contain legitimately comes from the workspace (see isolate).  When the tree
    has the file but not its package ``__init__.py`` (e.g. lawrag/api/routers),
    Python can only import the workspace copy; that is a violation only when
    the two copies differ, because then the run did not test the tree's code.
    """
    violations, same_bytes, fallbacks = {}, [], []
    for name, module in list(sys.modules.items()):
        top = name.split('.')[0]
        path = getattr(module, '__file__', None)
        if top not in PRODUCT_PACKAGES or not path:
            continue
        resolved = Path(path).resolve()
        if resolved.is_relative_to(code):
            continue
        # The workspace path as imported (a symlinked directory stays inside the workspace).
        absolute = Path(os.path.abspath(path))
        relative = (absolute.relative_to(ROOT) if absolute.is_relative_to(ROOT)
                    else resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else None)
        tree_copy = code / relative if relative is not None else None
        if tree_copy is not None and tree_copy.exists() and tree_copy.read_bytes() == resolved.read_bytes():
            same_bytes.append(name)
        elif top == 'semantic_runtime' or tree_copy is None or tree_copy.exists():
            violations[name] = str(resolved)
        else:
            fallbacks.append(name)
    return violations, sorted(same_bytes), sorted(fallbacks)


def main() -> int:
    if '--' not in sys.argv:
        raise SystemExit('usage: pytest_code_root.py --code-root DIR --report FILE -- <pytest arguments>')
    split = sys.argv.index('--')
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(sys.argv[1:split])
    pytest_args = sys.argv[split + 1:]
    code = args.code_root.resolve()
    os.chdir(ROOT)
    isolate(code)
    import conftest
    import pytest
    status = pytest.main(['--noconftest', '-c', '/dev/null', '--rootdir', str(ROOT), *pytest_args], plugins=[conftest])
    violations, same_bytes, fallbacks = loaded_outside(code)
    product = sorted(name for name in sys.modules if name.split('.')[0] in PRODUCT_PACKAGES)
    args.report.write_text(json.dumps({'code_root': str(code), 'exit_code': int(status),
                                       'product_modules': len(product), 'loaded_outside_code_root': violations,
                                       'same_bytes_outside_code_root': same_bytes,
                                       'workspace_fallback_modules': fallbacks},
                                      ensure_ascii=False, indent=1) + '\n')
    return int(status) if not violations else 3


if __name__ == '__main__':
    raise SystemExit(main())
