"""Run build regressions against the installed build code, without runtime fallback."""
import importlib,os,sys
from pathlib import Path
R=Path(__file__).resolve().parents[4];code=Path(sys.argv[1]).resolve()
sys.dont_write_bytecode=True
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS'),str(R/'05_TESTS/CONTRACTS')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(code),LAWRAG_TOOL_WORKSPACE_ROOT=str(code))
import pytest
rc=pytest.main(['-q','--tb=short','--show-capture=no','--noconftest','-o','pythonpath=',*sys.argv[2:]])
for name,module in list(sys.modules.items()):
    if name.startswith(('lawrag','semantic_runtime')) and getattr(module,'__file__',None):
        assert Path(module.__file__).resolve().is_relative_to(code),module.__file__
print('INSTALLED_BUILD_IMPORTS PASS; '+str(code))
raise SystemExit(rc)
