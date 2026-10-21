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
root=ART/'synthetic';root.mkdir(exist_ok=True)
glossary=root/'dictionary'
if not glossary.exists():glossary=term_glossary.__wrapped__(root)
docs=read(ART/'documents.json')
raw=root/'raw.sqlite'
if not raw.exists():source(raw,[(d['id'],d['title'],d['texts']) for d in docs])
with sqlite3.connect(raw) as db:
    for did,uid,payload in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
        value=json.loads(payload);value.update(coordinate_scope='body',coordinate_binding={'mode':'stored'})
        db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',(json.dumps(value,ensure_ascii=False),did,uid))
build_generation(raw,glossary,root/'built',serving=True)
build(root/'built/generation',root/'built/generation/navigation',root/'unit-index',workers=1)
save(ART/'synthetic-binding.json',{'documents_sha256':sha(ART/'documents.json'),'generation_manifest_sha256':sha(root/'built/generation/manifest.json'),'raw_sha256':sha(raw),'kind':'new synthetic holdout, not real law'})
