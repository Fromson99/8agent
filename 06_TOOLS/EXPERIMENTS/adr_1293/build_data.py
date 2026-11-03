from common import *
import importlib,os,inspect,asyncio
C=ROOT/read(DES/'candidate.json')['code_root']
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C),LOOP_TEST_CODE_ROOT=str(C),LAWRAG_WORKSPACE_ROOT=str(ROOT),PYTHONDONTWRITEBYTECODE='1')
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT)]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('core','pipeline'):
 m=importlib.import_module('lawrag.'+n);m.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import conftest
sys.path[:0]=[str(C/'02_BACKEND')]
from test_risk_team_compare_workflow import generation
from lawrag.pipeline.fulltext_stage import derive
from lawrag.pipeline.search_selection import plan,activate
tmp=ART/'comparison-corpus';tmp.mkdir(exist_ok=False)
glossary=conftest.term_glossary.__wrapped__(tmp)
gen=generation.__wrapped__(tmp,glossary)
derive(gen,tmp/'indexed',workers=1)
gen=tmp/'indexed';activate(plan(gen,latest=True))
put(DES/'comparison-source.json',{'data_path':str(gen.relative_to(ROOT)),'source_manifest':read(gen/'manifest.json'),'documents':['inside','outside'],'synthetic':True,'files':{str(p.relative_to(ROOT)):sha(p) for p in tmp.rglob('*') if p.is_file()}})
print('Synthetic two-document source prepared',gen)

