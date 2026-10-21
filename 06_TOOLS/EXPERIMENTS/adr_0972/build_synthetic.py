from common import *
import sys,sqlite3,inspect,pytest
sys.dont_write_bytecode=True
code=ROOT/read(ART/'stage.json')['roots']['candidate']
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag,lawrag.pipeline
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'));lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
from conftest import term_glossary
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.unit_fulltext import build
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import structure_selection as ss,query_scope as qs
from test_bounded_source_main import settings
from test_legal_agent_double_harness import BINDING
from types import SimpleNamespace as S
root=ART/'synthetic';root.mkdir(exist_ok=False)
glossary=term_glossary.__wrapped__(root);docs=read(ART/'documents.json')
raw=source(root/'raw.sqlite',[(d['id'],d['title'],d['texts']) for d in docs])
with sqlite3.connect(raw) as db:
    db.execute('DELETE FROM source_unit')
    for doc in docs:
        for node in doc['nodes']:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',(doc['id'],node['id'],node['parent'],json.dumps({k:v for k,v in node.items() if k not in ('id','parent')},ensure_ascii=False)))
build_generation(raw,glossary,root/'built',serving=True)
build(root/'built/generation',root/'built/generation/navigation',root/'unit-index',workers=1)
transport=S(binding=BINDING,validate_model=lambda:{'verified':True,'synthetic':True})
app=create_app(ROOT,root/'built/generation',contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'model_binding':BINDING},legal_agent_transport=transport,runtime_root=root/'preflight')
p=app.state.pipeline;request={'question':'합성 좌표 검증','document_ids':['A','B'],'use_llm':False};checked=0
with p.term_agent.open_session(request,query=p.plan(request['question'],request['document_ids']),runtime=root/'preflight/session') as native:
    for doc in docs:
        for node in doc['nodes']:
            actual=native.sources.matcher.stored_coordinates[(doc['id'],node['id'])]
            assert 'body:'+actual.canonical_surface()==node['coordinate_key']
            assert native.sources.matcher.units[(doc['id'],node['id'])].get('coordinate_binding',{}).get('mode')!='unresolved'
            checked+=1
p.store.close()
save(ART/'fixture-preflight.json',{'passed':True,'checked':checked,'generation_sha256':sha(root/'built/generation/manifest.json'),'documents_sha256':sha(ART/'documents.json'),'model_calls':0})
print('Synthetic coordinate preflight',checked)
