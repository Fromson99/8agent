from pathlib import Path
import importlib,os,sys,json,hashlib
R=Path(__file__).resolve().parents[3];code=Path(sys.argv[1]).resolve();sys.dont_write_bytecode=True
os.environ.update(SOURCE_PROVIDER_PROJECT_ROOT=str(R),LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R),LAWRAG_TOKEN_TEST_REPOSITORY=str(R))
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS'),str(R/'02_BACKEND')]
import semantic_runtime
assert Path(semantic_runtime.__file__).is_relative_to(code)
for name in ('lawrag','lawrag.pipeline','lawrag.core','lawrag.core.structure'):
 module=importlib.import_module(name);module.__path__.insert(0,str(code/'02_BACKEND'/name.replace('.','/')));module.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
plugin=importlib.import_module('conftest')
import pytest
result=pytest.main(['-q','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin])
paths={n:str(Path(m.__file__).resolve()) for n,m in list(sys.modules.items()) if n.startswith('semantic_runtime') and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(code) for p in paths.values()),paths
Path(os.environ['ADR_IMPORT_RECEIPT']).write_text(json.dumps(paths,indent=2)+'\n')
raise SystemExit(result)
