"""Synthetic contracts: complete collection, homonyms, resumption and transfer."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from lawrag.pipeline import glossary_enrichment as e
from lawrag.pipeline.collect_moleg_knowledge import _publish
from lawrag.pipeline.glossary_alignment import import_catalog
from lawrag.pipeline.knowledge_transfer import dictionary, unpack, DictionaryHints
from lawrag.sources.moleg_knowledge import ENDPOINTS, parse_xml_page


def record(kind, source_id, fields=None):
    return dict(entity_type=kind, source_id=source_id, label='신탁', definition='', fields=fields or {})


def link(target, mst):
    return f'/DRF/lawService.do?target={target}&MST={mst}'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    catalogues = {
        'legal_terms': [record('legal_terms', '11,12')],
        'knowledge_terms': [record('knowledge_terms', '20', {
            '용어간관계링크': link('lstrmRlt', '20'), '조문간관계링크': link('lstrmRltJo', '20')})],
        'everyday_terms': [record('everyday_terms', '30', {'용어간관계링크': link('dlytrmRlt', '30')})],
    }
    packages = []
    for kind, rows in catalogues.items():
        work = tmp_path / kind
        (work / 'raw').mkdir(parents=True)
        records = work / 'records.jsonl'
        records.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows))
        plan = work / 'request-plan.json'
        plan.write_text(json.dumps({'parameters': {}, 'checkpoint': {
            'completed': True, 'record_count': len(rows), 'total_count': len(rows)}}))
        packages.append(_publish(tmp_path, kind, work, plan, records))
    state = tmp_path / 'state'
    import_catalog(state, packages)
    monkeypatch.setattr(e, 'repository_root', lambda: tmp_path)
    return state, packages


class Fake:
    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at

    def fetch(self, endpoint, parameters):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError('secret URL must never enter receipts')
        if endpoint == 'legal_term_detail':
            ident = parameters['trmSeqs']
            xml = f'''<LsTrmService><법령용어일련번호>{ident}</법령용어일련번호>
            <법령용어명_한글>신탁</법령용어명_한글><법령용어정의>정의 {ident}</법령용어정의>
            <출처>법률 {ident}</출처></LsTrmService>'''
        elif endpoint == 'term_articles':
            xml = '''<lstrmRltJoService><법령용어><법령용어명>신탁</법령용어명>
            <연계법령><법령명>신탁법</법령명><조번호>0001</조번호><조가지번호>00</조가지번호>
            <조문연계용어링크>/DRF/lawService.do?target=joRltLstrm&amp;ID=000001&amp;JO=000100</조문연계용어링크>
            </연계법령></법령용어></lstrmRltJoService>'''
        else:
            tag = 'dlytrmRltService' if endpoint == 'everyday_term_relations' else 'lstrmRltService'
            term = '일상용어' if endpoint == 'everyday_term_relations' else '법령용어'
            xml = f'''<{tag}><{term}><{term}명>신탁</{term}명><연계용어>
            <법령용어명>수탁</법령용어명><용어관계코드>140303</용어관계코드><용어관계>상위어</용어관계>
            <조문간관계링크>/DRF/lawService.do?target=lstrmRltJo&amp;MST=21</조문간관계링크>
            </연계용어></{term}></{tag}>'''
        if endpoint == 'legal_term_relations':
            xml = xml.replace('법령용어명>수탁</법령용어명', '일상용어명>수탁</일상용어명').replace('조문간관계링크', '용어간관계링크').replace('target=lstrmRltJo', 'target=dlytrmRlt')
        return xml, parse_xml_page(xml, ENDPOINTS[endpoint])


def test_completion_resumes_and_keeps_distinct_definitions_and_all_relations(setup, tmp_path):
    state, _ = setup
    first = Fake()
    report = e.run(state, 'initial', client=first, max_requests=1)
    assert first.calls == 1 and report['remaining_requests'] == 4
    assert not (state / 'COMPLETED.json').exists()
    resumed = Fake()
    result = e.run(state, 'initial', client=resumed)
    assert resumed.calls == 4 and result['collection_complete']
    assert result['coverage']['definitions_with_text'] == 2
    assert result['coverage']['terms_with_source_definition'] == 1
    assert result['coverage']['official_relations'] == 2  # Broader edges preserved, not discarded.
    with closing(sqlite3.connect(result['dictionary'])) as db:
        assert db.execute('SELECT count(*) FROM sense').fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM term_sense WHERE match_kind='LABEL_CANDIDATE'").fetchone()[0] == 4
        hints = e.definition_hints(db, 'moleg:knowledge_terms:20')
        assert len(hints['candidates']) == 2
        assert {x['source'] for x in hints['candidates']} == {'법률 11', '법률 12'}
    _, restored = unpack(result['zip'], tmp_path / 'restored')
    receipt = dictionary(restored, tmp_path / 'genos.sqlite')
    assert receipt['coverage'] == result['coverage']
    no_network = Fake(fail_at=1)
    assert e.run(state, 'initial', client=no_network)['zip_sha256'] == result['zip_sha256']
    assert no_network.calls == 0


def test_failed_request_is_retryable_and_does_not_publish(setup):
    state, _ = setup
    with pytest.raises(RuntimeError, match='resumable'):
        e.run(state, 'failure', client=Fake(fail_at=2))
    assert not (state / 'COMPLETED.json').exists()
    with closing(e.connect(state / 'completion/failure/collection.sqlite')) as db:
        assert db.execute("SELECT count(*) FROM request WHERE status='complete'").fetchone()[0] == 1
        assert db.execute("SELECT error FROM request WHERE status='failed'").fetchone()[0] == 'RuntimeError'
    resumed = Fake()
    e.run(state, 'failure', client=resumed)
    assert resumed.calls == 4


def test_snapshot_rejects_changed_catalogue(setup):
    state, _ = setup
    e.run(state, 'frozen', plan_only=True)
    with closing(sqlite3.connect(state / 'alignment.sqlite')) as db:
        db.execute("UPDATE terms SET fingerprint='changed'")
        db.commit()
    with pytest.raises(ValueError, match='new completion snapshot'):
        e.run(state, 'frozen', client=Fake())


def test_parser_preserves_nested_definition_records():
    xml = '''<LsTrmService><법령용어><법령용어일련번호>11</법령용어일련번호>
    <법령용어명_한글>신탁</법령용어명_한글><법령용어정의>정의 A</법령용어정의></법령용어>
    <법령용어><법령용어일련번호>12</법령용어일련번호><법령용어명_한글>신탁</법령용어명_한글>
    <법령용어정의>정의 B</법령용어정의></법령용어></LsTrmService>'''
    rows = parse_xml_page(xml, ENDPOINTS['legal_term_detail']).records
    assert [r['source_id'] for r in rows] == ['11', '12']
    assert [r['definition'] for r in rows] == ['정의 A', '정의 B']


def test_response_rejects_wrong_identity_and_error_envelope():
    with pytest.raises(ValueError, match='identity mismatch'):
        e.validate_response('legal_term_detail', {'trmSeqs': '11'}, '<LsTrmService/>',
                            [dict(source_id='12', label='신탁')])
    with pytest.raises(ValueError, match='envelope'):
        e.validate_response('term_articles', {'MST': '20'}, '<error/>', [])


def test_genos_authoring_receives_source_scoped_definition_candidates(setup, tmp_path):
    state, _ = setup
    result = e.run(state, 'hints', client=Fake())
    source = tmp_path / 'source.sqlite'
    with closing(sqlite3.connect(source)) as db:
        db.execute('CREATE TABLE authoring_job(job_id TEXT PRIMARY KEY,input_json TEXT)')
        db.execute('INSERT INTO authoring_job VALUES (?,?)', ('a', json.dumps({'blocks': [{'idx': 1, 'text': '신탁은 중요하다.'}]})))
        db.commit()
    receipt = tmp_path / 'receipt.json'
    receipt.write_text('{}')
    DictionaryHints(Path(result['dictionary'])).enrich(source, receipt)
    with closing(sqlite3.connect(source)) as db:
        body = json.loads(db.execute('SELECT input_json FROM authoring_job').fetchone()[0])
    match = next(m for m in body['dictionary_lookup']['matches'] if m['term_id'] == 'moleg:knowledge_terms:20')
    assert match['definitions']['total'] == 2
    assert all(x['match_kind'] == 'LABEL_CANDIDATE' for x in match['definitions']['candidates'])
    assert match['definitions']['canonical_approval'] is False


def test_officially_missing_definition_is_reported_without_fabrication(setup):
    class Missing(Fake):
        def fetch(self, endpoint, parameters):
            if endpoint == 'legal_term_detail':
                self.calls += 1
                xml = '<Law>일치하는 법령용어가 없습니다.  법령용어명을 확인하여 주십시오.</Law>'
                return xml, parse_xml_page(xml, ENDPOINTS[endpoint])
            return super().fetch(endpoint, parameters)
    state, _ = setup
    result = e.run(state, 'missing', client=Missing())
    assert result['coverage']['definitions_with_text'] == 0
    assert result['empty_responses'] == [{'endpoint': 'legal_term_detail', 'count': 2}]
    assert result['collection_complete']  # Request coverage, not semantic approval.


@pytest.mark.parametrize('compiler', ['genos', 'runtime'])
def test_batched_relation_packages_reach_actual_compilers(setup, tmp_path, compiler):
    from types import SimpleNamespace
    from lawrag.pipeline import genos_moleg_compile
    from semantic_runtime import moleg_links
    from lawrag.pipeline.knowledge_transfer import inspect_package, RELATIONS
    state, _ = setup
    result = e.run(state, 'compile', client=Fake())
    packages = [Path(p) for p in result['packages'] if inspect_package(p)[1] in RELATIONS]
    with closing(sqlite3.connect(':memory:')) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT);
            CREATE TABLE source_block(document_id TEXT,block_id TEXT,text TEXT);''')
        store = SimpleNamespace(db=db, manifest={'store_sha256': 'fixture'})
        build = genos_moleg_compile.compile_links if compiler == 'genos' else moleg_links.compile_links
        report = build(store, packages, tmp_path / 'links.sqlite')
        assert report['counts']['unresolved'] == 1
        assert report['excluded_relation_counts']['140303'] == 2
        assert report['counts']['edge'] == 0


def test_legal_to_everyday_relation_keeps_target_namespace():
    xml = '''<lstrmRltService><법령용어><법령용어명>노동관계</법령용어명>
      <연계용어><일상용어명>근로관계</일상용어명><용어관계코드>140301</용어관계코드>
      <용어관계>동의어</용어관계><용어간관계링크>
      /DRF/lawService.do?target=dlytrmRlt&amp;MST=14397</용어간관계링크>
      </연계용어></법령용어></lstrmRltService>'''
    row = parse_xml_page(xml, ENDPOINTS['legal_term_relations']).records[0]
    assert e.relation_target(row) == 'moleg:everyday_terms:14397'


def test_cli_completion_and_readonly_status(setup, monkeypatch, capsys):
    from lawrag.pipeline.glossary_alignment import main
    state, _ = setup
    assert main(['complete', '--state-dir', str(state), '--snapshot', 'cli', '--plan-only']) == 0
    capsys.readouterr()
    assert main(['status', '--state-dir', str(state), '--snapshot', 'cli']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['completion']['total_requests'] == 5
    assert result['completed_glossary'] is None


def test_invalid_response_retains_raw_and_never_publishes(setup):
    class Invalid(Fake):
        def fetch(self, endpoint, parameters):
            return '<broken/>', parse_xml_page('<broken/>', ENDPOINTS[endpoint])
    state, _ = setup
    with pytest.raises(RuntimeError):
        e.run(state, 'invalid', client=Invalid())
    with closing(e.connect(state / 'completion/invalid/collection.sqlite')) as db:
        import gzip
        row = db.execute("SELECT response,response_sha256 FROM request WHERE status='failed'").fetchone()
        assert gzip.decompress(row[0]) == b'<broken/>'
        assert row[1]
    assert not (state / 'COMPLETED.json').exists()
