"""PeCab rebuild keeps source bytes and refuses a partial search scope escape."""
import json,sqlite3
from contextlib import closing
import pytest
from test_genos_fulltext_repair import repair,source,build_generation,verify_assets,sha

def test_explicit_rebuild_preserves_input_and_checks_partial_scope(tmp_path,term_glossary):
    original=source(tmp_path/'source.sqlite',[('public:v1','모의공개규정',['영업일 승인 조건']),
                                             ('internal:v1','모의내규',['비공개 모의 조항'])])
    built=tmp_path/'built';build_generation(original,term_glossary,built,serving=True)
    generation=built/'generation'
    before={str(p.relative_to(generation)):sha(p) for p in generation.rglob('*') if p.is_file()}
    selected=tmp_path/'scope.json';selected.write_text(json.dumps({'document_version_ids':['public:v1']}))
    assert repair(['--source-generation',str(generation),'--output-root',str(tmp_path),
                   '--package-name','rebuilt','--workers','1','--rebuild','--document-scope',str(selected)])==0
    assert all(sha(generation/p)==h for p,h in before.items())
    result=tmp_path/'rebuilt/generation';assert verify_assets(result)['verified']
    from semantic_runtime.fulltext import FulltextIndex,question_terms
    nav=json.loads((result/'navigation/manifest.json').read_text());ft=FulltextIndex(result/'fulltext',nav)
    assert ft.manifest['tokenizer']==json.loads((generation/'fulltext/manifest.json').read_text())['tokenizer']
    assert ft.manifest['scope']['document_version_ids']==['public:v1']
    with sqlite3.connect(result/'navigation/navigation.sqlite') as db:
        ids=dict(db.execute('SELECT document_id,id FROM source'))
    with closing(ft.connect()) as db:
        assert ids['public:v1'] in ft.rank(db,question_terms('영업일'),{ids['public:v1']})
        with pytest.raises(ValueError,match='outside the rebuilt fulltext scope'):
            ft.rank(db,question_terms('승인'),set(ids.values()))
