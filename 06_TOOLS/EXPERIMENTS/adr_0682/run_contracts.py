"""Explicit code inventory and workspace binding; no live model/provider calls."""
from pathlib import Path
import importlib
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
code = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(code/'02_BACKEND'), str(code), str(ROOT/'05_TESTS'),
               str(ROOT/'05_TESTS/CONTRACTS'), str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0682')]
import semantic_runtime
assert str(code) in semantic_runtime.__file__
for name in ('lawrag', 'lawrag.pipeline'):
    module = importlib.import_module(name)
    module.__path__.append(str(ROOT/'02_BACKEND'/name.replace('.', '/')))
import semantic_runtime.app as application
original = application.create_app
def explicit_workspace(*args, **kwargs):
    kwargs.setdefault('workspace_root', ROOT)
    kwargs.setdefault('runtime_root', Path(args[0])/'90_RUNTIME/semantic')
    return original(*args, **kwargs)
application.create_app = explicit_workspace
plugin = importlib.import_module('conftest')
helper = importlib.import_module('test_legal_agent_double_harness')
helper.ROOT = code
plugin.structured_generation = importlib.import_module('test_structure_first_search').structured_generation
import pytest
raise SystemExit(pytest.main(['-q', '--tb=short', '--noconftest', *sys.argv[2:]], plugins=[plugin]))
