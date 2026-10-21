"""Exercise installed recovery contracts; fixture builders alone use the workspace."""
from pathlib import Path
import importlib, json, os, sys
R=Path(__file__).resolve().parents[4];code=Path(sys.argv[1]).resolve()
sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R))
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(Path(__file__).resolve().parent),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
for name in ('semantic_runtime','semantic_runtime.legal_agent.completion_contracts'):
    module=importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(code),module.__file__
for name in ('lawrag','lawrag.pipeline'):
    module=importlib.import_module(name)
    module.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
# Generation is a fixture builder, not shipped serving functionality. Build
# synthetic sources in a separate workspace process; runtime imports stay pinned.
import subprocess
fixture_builder=importlib.import_module('lawrag.pipeline.term_generation')
def build_synthetic(source,glossary,output,**kwargs):
    command="import json,sys;from lawrag.pipeline.term_generation import build_generation;args=json.loads(sys.argv[1]);build_generation(*args['paths'],**args['kwargs'])"
    environment={**os.environ,'PYTHONPATH':str(R/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(R),'LAWRAG_TOOL_WORKSPACE_ROOT':str(R)}
    result=subprocess.run([str(R/'.venv/bin/python'),'-c',command,json.dumps({'paths':list(map(str,(source,glossary,output))),'kwargs':kwargs})],cwd=R,env=environment,text=True,capture_output=True,timeout=60)
    if result.returncode:raise RuntimeError('synthetic fixture builder failed: '+result.stdout+result.stderr)
    return json.loads((Path(output)/'result.json').read_bytes())
fixture_builder.build_generation=build_synthetic
plugin=importlib.import_module('conftest')
import pytest
from semantic_runtime.unit_fulltext import UnitFulltextIndex
@pytest.fixture
def prebuilt_unit_tree():
    generation=Path(os.environ['METRICS_TEST_GENERATION'])
    return generation,UnitFulltextIndex(Path(os.environ['METRICS_TEST_UNIT_INDEX']),json.loads((generation/'navigation/manifest.json').read_bytes()))
# Import only these contract suites before rebinding their declared ROOT.
for path in sys.argv[2:]:
    if path.endswith('.py'):
        sys.path.insert(0,str(Path(path).resolve().parent))
        importlib.import_module(Path(path).stem)
# The shipped field inventory serves existing generations and does not contain
# the local raw-ingestion builders. Build only the two search fixtures in an
# isolated current-workspace process, retaining every serving assertion below.
if 'test_search_selection' in sys.modules:
    import inspect,textwrap
    search_tests=sys.modules['test_search_selection']
    source=inspect.getsource(search_tests.test_existing_database_search_and_actual_api)
    start=source.index("    raw = tmp_path/'RAW'\n")
    end=source.index('    oldid, newid = sha(old)[:16], sha(new)[:16]\n')
    build_block=textwrap.dedent(source[start:end])
    def search_fixture(tmp_path,term_glossary,mode):
        script='''import json,os,sys
from pathlib import Path
from test_latest_internal_versions import docx
from lawrag.pipeline import genos_corpus,genos_stages,document_release
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.contracts import sha
tmp_path=Path(sys.argv[1]);term_glossary=Path(sys.argv[2]);mode=sys.argv[3]
os.environ['STRUCTURE_RECIPE_VLM']='off'
'''+build_block+"\n(tmp_path/'fixture_paths.json').write_text(json.dumps(list(map(str,(old,new,g)))))\n"
        environment={**os.environ,'PYTHONPATH':str(R/'02_BACKEND')+':'+str(R/'05_TESTS/CONTRACTS'),
                     'LAWRAG_WORKSPACE_ROOT':str(R),'LAWRAG_TOOL_WORKSPACE_ROOT':str(R)}
        for key in ('GENOS_GENERATION','GENOS_DATA_ROOT'):environment.pop(key,None)
        result=subprocess.run([str(R/'.venv/bin/python'),'-c',script,str(tmp_path),str(term_glossary),mode],
            cwd=R,env=environment,text=True,capture_output=True,timeout=90)
        if result.returncode:raise RuntimeError('isolated search fixture failed: '+result.stdout+result.stderr)
        return tuple(Path(p) for p in json.loads((tmp_path/'fixture_paths.json').read_text()))
    search_tests._isolated_search_fixture=search_fixture
    replacement="    old,new,g = _isolated_search_fixture(tmp_path,term_glossary,mode)\n    before = {p:sha(p) for p in g.rglob('*') if p.is_file()}\n"
    exec(compile(source[:start]+replacement+source[end:],inspect.getsourcefile(search_tests), 'exec'),search_tests.__dict__)
for name,module in list(sys.modules.items()):
    if name.startswith('test_') and getattr(module,'ROOT',None)==R:module.ROOT=code
result=pytest.main(['-q','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin])
imports={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if name.startswith('semantic_runtime') and getattr(module,'__file__',None)}
assert all(Path(path).is_relative_to(code) for path in imports.values()),imports
print('INSTALLED_RUNTIME_IMPORTS PASS; modules='+str(len(imports))+'; '+str(code),flush=True)
raise SystemExit(result)
