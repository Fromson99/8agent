"""Run transport contracts against the installed checkout, without copying runtime code."""
from pathlib import Path
import importlib
import os
import sys

R = Path(__file__).resolve().parents[4]
code = Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
# Fixture-only authoring modules read glossary schemas absent from the serving
# package. The imported runtime and every tested transport stay in code below.
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R), LAWRAG_TOOL_WORKSPACE_ROOT=str(R),
                  GENOS_TEST_INSTALLED_TRANSPORT='1')
sys.path[:0] = [str(code/'02_BACKEND'), str(code), str(R/'05_TESTS/CONTRACTS'),
               str(R/'05_TESTS'), str(R/'05_TESTS/REGRESSION/core')]
for name in ('semantic_runtime', 'semantic_runtime.genos', 'semantic_runtime.stdlib_http',
             'semantic_runtime.legal_agent.transport', 'semantic_runtime.legal_agent.model_stream'):
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(code), module.__file__
# Only fixture builders absent from the field release may come from working code.
for name in ('lawrag', 'lawrag.pipeline'):
    module = importlib.import_module(name)
    module.__path__.append(str(R/'02_BACKEND'/name.replace('.', '/')))
plugin = importlib.import_module('conftest')
for name in ('test_legal_agent_double_harness', 'test_genos_answer_stream'):
    importlib.import_module(name).ROOT = code
import pytest
import test_genos_model_stream_completion

@pytest.fixture
def prebuilt_gateway_generation():
    return Path(os.environ['TLS_GATEWAY_TEST_GENERATION'])

# Build-only modules are intentionally absent from the serving inventory.
# Use its unmodified fixture data built before installing; runtime readers,
# gateway, validation and commits are all supplied by this installed checkout.
test_genos_model_stream_completion.generation = prebuilt_gateway_generation
result = pytest.main(['-q', '--tb=short', '--show-capture=no', '-o', 'pythonpath=',
                     '--noconftest', *sys.argv[2:]], plugins=[plugin])
for name, module in list(sys.modules.items()):
    if name.startswith('semantic_runtime') and getattr(module, '__file__', None):
        assert Path(module.__file__).resolve().is_relative_to(code), module.__file__
print('INSTALLED_RUNTIME_IMPORTS PASS; '+str(code), flush=True)
raise SystemExit(result)
