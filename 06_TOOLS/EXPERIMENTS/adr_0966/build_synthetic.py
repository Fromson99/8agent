"""One small shared synthetic generation, explicitly separate from production data."""
from common import *
import sys,sqlite3,inspect,pytest
sys.dont_write_bytecode=True
code=ROOT/read(ART/'stage.json')['roots']['candidate']
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
import lawrag.pipeline
lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
from conftest import term_glossary
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.unit_fulltext import build
from lawrag.core.legal_coordinate import find_coordinates
root=ART/'synthetic';root.mkdir(exist_ok=True)
glossary=root/'dictionary'
if not glossary.exists():glossary=term_glossary.__wrapped__(root)
docs=read(ART/'documents.json')
raw=root/'raw.sqlite'
if not raw.exists():source(raw,[(d['id'],d['title'],d['texts']) for d in docs])
with sqlite3.connect(raw) as db:
    for did,uid,payload in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
        value=json.loads(payload);coordinate=find_coordinates(value['surface'])[0].coordinate
        value.update(legal_coordinate=coordinate.as_dict(),coordinate_scope='body',coordinate_key='body:'+coordinate.canonical_surface())
        db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',(json.dumps(value,ensure_ascii=False),did,uid))
build_generation(raw,glossary,root/'built',serving=True)
build(root/'built/generation',root/'built/generation/navigation',root/'unit-index',workers=1)
save(ART/'synthetic-binding.json',{'documents_sha256':sha(ART/'documents.json'),'generation_manifest_sha256':sha(root/'built/generation/manifest.json'),'raw_sha256':sha(raw),'kind':'new synthetic holdout, not real law'})
from types import SimpleNamespace
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import query_scope as qs
from test_bounded_source_main import settings
from test_legal_agent_double_harness import BINDING
transport=SimpleNamespace(binding=BINDING,validate_model=lambda:{'verified':True,'synthetic':True})
profile={**settings(),'model_binding':BINDING}
app=create_app(ROOT,root/'built/generation',contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=root/'preflight')
p=app.state.pipeline;scope=[d['id'] for d in docs];checks=[]
request={'question':'합성 구조 바인딩 사전 확인','document_ids':scope,'use_llm':False}
with p.term_agent.open_session(request,query=p.plan(request['question'],scope),runtime=root/'preflight/lookup') as native:
    for doc in docs:
        for n in range(1,len(doc['texts'])+1):
            page=qs.catalogue(native.sources,document_id=doc['id'],structure_filter={'coordinate':f'제{n}조','title':'','coordinate_scope':'body'})
            checks.append({'document_id':doc['id'],'node':n-1,'coordinate':f'제{n}조','status':page['lookup_status'],'items':len(page['items'])})
assert all(x['status']=='MATCH' and x['items']==1 for x in checks),checks
save(ART/'fixture-preflight.json',{'passed':True,'checks':checks,'model_calls':0,'criterion':'All32 exact body coordinates must resolve before any model trial'})
p.store.close()
