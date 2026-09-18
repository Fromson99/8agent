"""Golden infrastructure contracts using synthetic sources and provider doubles only."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from lawrag.pipeline import golden as g, golden_run as runner
from lawrag.pipeline import golden_authoring as authoring
from lawrag.pipeline import glossary_assembly, glossary_v1
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.app import create_app
from semantic_runtime.contracts import sha, write
from semantic_runtime.provider import Haiku

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def legacy_term_contract(monkeypatch):
    """Old provider double targets the pinned term-agent contract, not MAIN navigation."""
    import semantic_runtime.app as app_module
    original = app_module.create_app
    def pinned(*args, **kwargs):
        kwargs['contracts_root'] = ROOT / '08_DEPLOYMENT/RELEASES/term-source-rag-20260915-v1/code'
        return original(*args, **kwargs)
    monkeypatch.setattr(app_module, 'create_app', pinned)
    return pinned


@pytest.fixture
def generation(tmp_path):
    source = tmp_path / 'source.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        db.execute('INSERT INTO document VALUES (?,?,?,?)', ('mock-v1', '모의규정', 'a'*64, '{}'))
        for i, text in enumerate(['제1조 영업일은 토요일을 제외한다.', '제2조 영업일 계산에는 제1조를 준용한다.']):
            unit = {'id': str(i), 'parent': None, 'title': '모의', 'surface': f'제{i+1}조', 'family': 'kr_article', 'span': [i, i+1], 'block': i}
            db.execute('INSERT INTO source_unit VALUES (?,?,?,?)', ('mock-v1', str(i), None, json.dumps(unit)))
            db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)', ('mock-v1', str(i), str(i), text, 'a'*64, json.dumps({'idx': i, 'text': text, 'node': str(i)})))
    glossary = tmp_path / 'glossary'; glossary.mkdir()
    with sqlite3.connect(glossary / 'dictionary.sqlite') as db:
        glossary_assembly.tables(db)
        glossary_v1.add_entry(db, 'mock:day', 'econedu', '영업일', '모의 사전')
    write(glossary / 'report.json', {'schema_version': glossary_assembly.VERSION, 'dictionary_sha256': sha(glossary / 'dictionary.sqlite')})
    build_generation(source, glossary, tmp_path / 'build')
    return tmp_path / 'build/generation'


@pytest.fixture
def draft(generation):
    cat = g.catalog(generation)
    draft = g.template(); c = draft['cases'][0]
    c.update(question='영업일은?', as_of='2026-09-16', document_ids=['mock-v1'], required_points=['토요일 제외'],
             review={'status': 'approved', 'by': 'synthetic-reviewer', 'at': '2026-09-16T10:00:00+09:00'})
    c['evidence_groups'] = []
    for i, source in enumerate(cat['sources']):
        b = source['blocks'][0]
        c['evidence_groups'].append({'id': f'basis-{i}', 'role': 'required', 'any_of': [{
            'source_id': source['id'], 'document_id': source['document_id'], 'source_artifact_sha256': source['source_artifact_sha256'],
            'locator': source['heading'], 'block_id': b['block_id'], 'quote': b['text']}]})
    return draft


def result(suite):
    case = suite['cases'][0]
    a, b = [group['any_of'][0]['source_id'] for group in case['evidence_groups']]
    return {'query': {'question': case['question'], 'scope': {'document_version_ids': case['document_ids']}},
            'retrieval': {'candidates': [{'id': a}, {'id': b}], 'term_agent': {
                'use_llm': True, 'status': 'FINISH', 'trace': [{'search_results': [{'id': a}], 'after_evidence_ids': [a, b]}]}},
            'assembly': {'context': [{'id': a}]},
            'answer': {'generation_id': suite['binding']['generation_id'], 'source_store_sha256': suite['binding']['store_sha256'],
                       'text': '모의 답변', 'claims': [{'source_ids': [a]}]}}


def test_freeze_preserves_version_exact_quote_and_original(draft, generation):
    original = deepcopy(draft)
    suite = g.verify(g.freeze(draft, generation))
    assert draft == original
    assert suite['cases'][0]['evidence_groups'][0]['any_of'][0]['article_coordinate']['doc_id'] == 'mock-v1'
    assert suite['binding']['manifest_sha256'] == sha(generation / 'manifest.json')
    suite['version'] = 'modified'
    with pytest.raises(ValueError, match='hash'): g.verify(suite)


@pytest.mark.parametrize('change', ['draft', 'quote', 'version', 'scope', 'duplicate', 'date'])
def test_bad_mapping_cannot_freeze(draft, generation, change):
    c = draft['cases'][0]; ref = c['evidence_groups'][0]['any_of'][0]
    if change == 'draft': c['review']['status'] = 'draft'
    if change == 'quote': ref['quote'] = '원문에 없는 문자열'
    if change == 'version': ref['source_artifact_sha256'] = 'b'*64
    if change == 'scope': c['document_ids'] = ['missing']
    if change == 'duplicate': draft['cases'].append(deepcopy(c))
    if change == 'date': c['as_of'] = 'yesterday'
    with pytest.raises(ValueError): g.freeze(draft, generation)


def test_initial_is_not_cumulative_and_selection_loss_is_measured(draft, generation):
    suite = g.freeze(draft, generation)
    row = g.score(suite['cases'][0], result(suite), suite['binding'])
    assert [row['metrics'][s]['recall'] for s in g.STAGES] == [.5, 1, 1, .5, .5]
    assert row['metrics']['selected']['lost_groups_from_previous'] == ['basis-1']
    assert row['answer_quality'] == 'PENDING_HUMAN_REVIEW'


def test_alternatives_reference_and_no_evidence_are_not_false_misses(draft, generation):
    c = draft['cases'][0]
    c['evidence_groups'][0]['any_of'] += c['evidence_groups'][1]['any_of']
    c['evidence_groups'][1]['role'] = 'reference'
    suite = g.freeze(draft, generation)
    row = g.score(suite['cases'][0], result(suite), suite['binding'])
    assert row['metrics']['initial']['recall'] == 1
    c['expected_behavior'] = 'abstain'; c['evidence_groups'] = []
    frozen = g.freeze(draft, generation)
    assert g.score(frozen['cases'][0], result(suite), frozen['binding'])['metrics']['initial']['recall'] is None


def test_missing_trace_not_zero_and_source_only_rejected(draft, generation):
    suite = g.freeze(draft, generation); r = result(suite)
    r['retrieval']['term_agent'].update(trace=[], status='EXECUTION_FAILURE')
    row = g.score(suite['cases'][0], r, suite['binding'])
    assert row['metrics']['initial']['recall'] is None and row['execution_failed']
    r['retrieval']['term_agent']['use_llm'] = False
    with pytest.raises(ValueError, match='source-only'): g.score(suite['cases'][0], r, suite['binding'])


def test_review_bound_to_answer_and_pending_not_pass(draft, generation, tmp_path):
    suite = g.freeze(draft, generation)
    rows = [g.score(suite['cases'][0], result(suite), suite['binding'])]
    review = g.review_template(suite, rows)
    assert g.apply_reviews(suite, rows, review)[0]['answer_quality'] == 'PENDING_HUMAN_REVIEW'
    summary = g.report(suite, rows, tmp_path / 'report')
    assert summary['reviewed'] == 0 and summary['answer_pass_over_reviewed'] is None
    item = review['reviews'][0]
    item.update(by='reviewer', at=g.now(), required_points_met=[True], behavior_correct=True, citations_supported=True, no_unsupported_claims=True)
    assert g.apply_reviews(suite, rows, review)[0]['answer_quality'] == 'PASS'
    item['answer_sha256'] = 'bad'
    with pytest.raises(ValueError, match='stale'): g.apply_reviews(suite, rows, review)


def test_batch_product_input_is_gold_free_and_failures_kept(draft, generation, tmp_path):
    suite = g.freeze(draft, generation)
    second = deepcopy(suite['cases'][0]); second['id'] = 'case-002'
    suite['cases'].append(second)
    calls = []
    async def call(request):
        calls.append(request)
        assert set(request) == {'question', 'document_ids', 'use_llm'}
        if len(calls) == 2: raise RuntimeError('secret must not be in score')
        return result(suite)
    rows = asyncio.run(runner.run_cases(suite, call, tmp_path / 'batch'))
    assert len(rows) == 2 and rows[1]['execution_failed']
    assert 'secret' not in json.dumps(rows)
    assert (tmp_path / 'batch/cases/00001/response.json').is_file()


def test_plan_rejects_completed_adr_and_code_drift(draft, generation, tmp_path, monkeypatch):
    suite = g.freeze(draft, generation); sp = tmp_path / 'suite.json'; write(sp, suite)
    ap = tmp_path / 'adr.json'
    adr = {'reservation': {'status': 'in_progress'}, 'design': {'criteria_frozen_before_run': True, 'success_criteria': ['synthetic contract']},
           'experiment_id': 'fixture-only', 'runs': [{'id': 'run-001', 'arm_ids': ['baseline'], 'status': 'planned'}]}
    write(ap, adr)
    monkeypatch.setenv('SEMANTIC_LLM_BACKEND', 'genos'); monkeypatch.setenv('GENOS_BASE_URL', 'https://internal.invalid')
    monkeypatch.setenv('GENOS_QWEN_SERVING_ID', 'mock-serving')
    plan = runner.make_plan(sp, generation, ap, 'run-001', 'baseline', 'internal-mock')
    assert runner.check_plan(plan) == suite
    monkeypatch.setattr(runner, 'code_binding', lambda: {'changed': 'hash'})
    with pytest.raises(ValueError, match='drift'): runner.check_plan(plan)
    adr['reservation']['status'] = 'completed'; ap.write_text(json.dumps(adr))
    with pytest.raises(ValueError, match='in-progress'): runner.check_adr(ap, 'run-001', 'baseline')


def test_real_ask_route_trace_scores_with_synthetic_provider(draft, generation, tmp_path, legacy_term_contract):
    class MockProvider(Haiku):
        def call(self, role, task, context, schema):
            if role.endswith('plan'):
                value = {'questions_to_check': ['모의 확인'], 'seed_labels': ['영업일']}
            else:
                sid = context['documents'][0]['id']
                value = {'findings': [{'text': '모의 결론', 'source_ids': [sid]}], 'open_questions': [],
                         'evidence_ids': [sid], 'next_action': 'FINISH', 'next_term_ids': [], 'next_navigation_ids': [],
                         'reason': 'contract fixture', 'question_for_user': '', 'answer': ''}
            return value, self.record_local(value)
    suite = g.freeze(draft, generation)
    provider = MockProvider(ROOT, tmp_path / 'providers', False, backend='fixture', trust_zone='internal')
    app = legacy_term_contract(tmp_path, generation, contracts_root=ROOT, provider=provider)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=g.product_request(suite['cases'][0]))
        assert response.status_code == 200
        row = g.score(suite['cases'][0], response.json(), suite['binding'])
        assert not row['execution_failed']
        assert row['metrics']['initial']['observed']
        assert row['metrics']['selected']['count'] == 1


def test_full_run_receipts_review_report_and_replay_guard(draft, generation, tmp_path, monkeypatch, legacy_term_contract):
    """Execute the entire batch command without network or an actual model."""
    def resolve(self, secrets):
        self.model = 'internal-mock'
        return None, self.model
    def call(self, role, task, context, schema):
        if role.endswith('plan'):
            value = {'questions_to_check': [], 'seed_labels': ['영업일']}
        else:
            sid = context['documents'][0]['id']
            value = {'findings': [{'text': '모의 답변', 'source_ids': [sid]}], 'open_questions': [],
                     'evidence_ids': [sid], 'next_action': 'FINISH', 'next_term_ids': [], 'next_navigation_ids': [],
                     'reason': 'fixture', 'question_for_user': '', 'answer': ''}
        return value, self.record_local(value)
    monkeypatch.setattr(Haiku, '_resolve_genos', resolve)
    monkeypatch.setattr(Haiku, 'call', call)
    monkeypatch.setenv('SEMANTIC_LLM_BACKEND', 'genos')
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal.invalid')
    monkeypatch.setenv('GENOS_QWEN_SERVING_ID', 'mock')
    monkeypatch.setenv('GENOS_QWEN_KEY', 'never-store-this-value')
    sp = tmp_path / 'suite.json'; write(sp, g.freeze(draft, generation))
    ap = tmp_path / 'adr.json'
    write(ap, {'reservation': {'status': 'in_progress'}, 'design': {'criteria_frozen_before_run': True, 'success_criteria': ['contract only']},
               'experiment_id': 'fixture-only', 'runs': [{'id': 'run-001', 'arm_ids': ['baseline'], 'status': 'planned'}]})
    pp = tmp_path / 'plan.json'
    write(pp, runner.make_plan(sp, generation, ap, 'run-001', 'baseline', 'internal-mock'))
    out = tmp_path / 'run'
    runner.execute(pp, out)
    receipt = g.verify(g.read(out / 'receipt.json'))
    assert receipt['deployment_gateway_verified'] is False
    assert not receipt['quality_certified']
    assert 'never-store-this-value' not in json.dumps(g.read(pp))
    assert g.read(out / 'rows.json')[0]['execution_failed'] is False
    assert g.main(['report', '--run', str(out), '--output', str(tmp_path / 'view')]) == 0
    with pytest.raises(FileExistsError): runner.execute(pp, tmp_path / 'duplicate')
    # Even a newly created plan cannot replay the same ADR run/arm.
    newer = tmp_path / 'new-plan.json'
    write(newer, runner.make_plan(sp, generation, ap, 'run-001', 'baseline', 'internal-mock'))
    with pytest.raises(FileExistsError): runner.execute(newer, tmp_path / 'duplicate-new-plan')
    with (out / 'rows.json').open('a') as stream: stream.write(' ')
    with pytest.raises(ValueError, match='artifact changed'):
        g.main(['report', '--run', str(out), '--output', str(tmp_path / 'tampered')])


def test_authoring_preserves_public_golden_subparagraphs_and_does_not_approve(generation, tmp_path):
    s = g.catalog(generation)['sources'][0]
    article = authoring.article_of(s)
    source = tmp_path / 'public.json'; labels = tmp_path / 'labels.json'
    write(source, {'source': 'law.go.kr OPEN API (expc)', 'cases': [{'case_no': 'public-1', 'issue': '실제 입력 양식 질문', 'answer': '기준답변', 'decided': '2026-09-16'}]})
    write(labels, {'cases': {'public-1': {'decisive': [['모의규정', article]], 'decisive_full': [
        {'law': '모의규정', 'jo': article, 'hang_ho': '제1항', 'text': s['blocks'][0]['text'], 'node_id': 'old-node', 'why': '필수 근거'}]}}})
    output = tmp_path / 'authoring'
    bundle = authoring.prepare(source, 'moleg', generation, output, labels=labels)
    assert bundle['summary']['UNIQUE_CANDIDATE'] == 1
    ref = bundle['draft']['cases'][0]['evidence_groups'][0]['any_of'][0]
    assert ref['quote'] == s['blocks'][0]['text'] and ref['locator'].endswith('제1항')
    assert bundle['draft']['cases'][0]['review']['status'] == 'draft'
    with pytest.raises(ValueError, match='human approval'): g.freeze(bundle['draft'], generation)
    assert '법률' not in bundle['draft']['cases'][0]['document_ids']
    assert (output / 'review.html').is_file()
    assert (output / 'questions.csv').read_bytes().startswith(b'\xef\xbb\xbf')


def test_matching_never_conflates_body_addendum_versions_or_text(generation):
    source = g.catalog(generation)['sources'][0]
    target = {'law': source['document_name'], 'article': authoring.article_of(source), 'coordinate_scope': 'body'}
    addendum = {**source, 'id': 'addendum', 'coordinate_scope': 'addendum'}
    assert authoring.match_target(target, [source, addendum]) == [source]
    version = {**source, 'id': 'other-version', 'document_id': 'v2'}
    assert len(authoring.match_target(target, [source, version])) == 2
    assert not authoring.match_target({**target, 'node': 'absent'}, [source])
    assert not authoring.match_target({**target, 'quote': '原文にない'}, [source])


def test_csv_import_reports_missing_and_text_drift_without_dropping_case(generation, tmp_path):
    import csv
    source = g.catalog(generation)['sources'][0]
    path = tmp_path / 'input.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(authoring.FIELDS)
        writer.writerow(['1', '질문', '답', '2026-09-16', source['document_name'], authoring.article_of(source), 'body', 'g1', 'required', '변경된 구절'])
        writer.writerow(['1', '질문', '답', '2026-09-16', '없는문서', '제1조', 'body', 'g2', 'required', ''])
    bundle = authoring.prepare(path, 'csv', generation, tmp_path / 'out')
    assert bundle['summary']['cases'] == 1 and bundle['summary']['targets'] == 2
    assert bundle['summary']['TEXT_MISMATCH'] == 1 and bundle['summary']['NOT_FOUND'] == 1
    assert all(r['selected_source_id'] is None for r in bundle['mappings'])
    assert len(bundle['draft']['cases'][0]['evidence_groups']) == 2


def test_catalog_uses_same_explicit_index_binding_as_runtime(generation, tmp_path, monkeypatch):
    from lawrag.platform.workspace import load_layout
    before = g.catalog(generation)
    manifest = g.read(generation / 'manifest.json'); binding = manifest.pop('navigation')
    (generation / 'manifest.json').write_text(json.dumps(manifest))
    root = tmp_path / 'root'; (root / '00_SYSTEM').mkdir(parents=True)
    # External index is allowed only beneath the explicitly configured root.
    import shutil
    shutil.copytree(generation / binding['path'], root / 'index')
    write(root / '00_SYSTEM/PIPELINE.json', {'profiles': {'legal-rag': {'nodes': [
        {'id': 'retrieve', 'parameters': {'term_agent': {'index': {'path': 'index', 'manifest_sha256': sha(root / 'index/manifest.json')}}}}]}}})
    from types import SimpleNamespace
    monkeypatch.setattr('lawrag.platform.workspace.load_layout', lambda: SimpleNamespace(root=root))
    after = g.catalog(generation)
    assert before['sources'] == after['sources'] and before['store_sha256'] == after['store_sha256']


@pytest.fixture
def exchange_package(generation, tmp_path):
    import csv
    path = tmp_path / 'questions.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(authoring.FIELDS)
        for i, source in enumerate(g.catalog(generation)['sources']):
            writer.writerow(['case-1', '모의 질문', '모의 기준답변', '2026-09-16', source['document_name'],
                             authoring.article_of(source), 'body', f'g{i}', 'required', source['blocks'][0]['text']])
    folder = tmp_path / 'authoring'
    bundle = authoring.prepare(path, 'csv', generation, folder, suite_id='fixture')
    reviewed = deepcopy(bundle['draft'])
    reviewed['cases'][0]['review'] = {'status': 'approved', 'by': '모의 검토자', 'at': g.now()}
    return folder, reviewed


def test_offline_upload_freezes_only_all_valid_cases(exchange_package, generation, tmp_path):
    from lawrag.pipeline.golden_exchange import receive, checked_files
    folder, reviewed = exchange_package
    upload = tmp_path / 'reviewed.json'; write(upload, reviewed)
    output = tmp_path / 'received'
    assert receive(folder, upload, generation, output)['ok']
    suite = g.verify(g.read(output / 'suite.json'))
    assert suite['cases'][0]['id'] == 'case-1'
    assert (output / 'uploaded.json').read_bytes() == upload.read_bytes()
    checked_files(output, ['suite.json', 'validation.json', 'uploaded.json'])
    with pytest.raises(FileExistsError): receive(folder, upload, generation, output)


@pytest.mark.parametrize('change,code', [('drop-case','CASE_SET_CHANGED'), ('drop-group','GROUPS_CHANGED'),
    ('unapproved','CASE_INVALID'), ('quote','CASE_INVALID'), ('binding','PACKAGE_MISMATCH'), ('malformed','INVALID_JSON')])
def test_upload_reports_errors_without_silently_dropping_cases(exchange_package, generation, tmp_path, change, code):
    from lawrag.pipeline.golden_exchange import receive
    folder, reviewed = exchange_package
    if change == 'drop-case': reviewed['cases'] = []
    if change == 'drop-group': reviewed['cases'][0]['evidence_groups'].pop()
    if change == 'unapproved': reviewed['cases'][0]['review']['status'] = 'draft'
    if change == 'quote': reviewed['cases'][0]['evidence_groups'][0]['any_of'][0]['quote'] = '<script>bad</script>'
    if change == 'binding': reviewed['mapping_binding']['generation_id'] = 'other'
    path = tmp_path / 'uploaded.json'
    path.write_text('{broken' if change == 'malformed' else json.dumps(reviewed))
    output = tmp_path / 'validation'
    status = receive(folder, path, generation, output)
    assert not status['ok'] and code in {issue['code'] for issue in status['issues']}
    assert not (output / 'suite.json').exists()
    assert (output / 'validation.html').exists()


def test_answer_ui_export_and_review_report_roundtrip(draft, generation, tmp_path):
    from lawrag.pipeline.golden_exchange import review_answers, checked_run
    suite = g.freeze(draft, generation)
    async def call(_):
        response = result(suite)
        response['answer']['text'] = '</script><script>window.injected=true</script>'
        return response
    run = tmp_path / 'run'; rows = asyncio.run(runner.run_cases(suite, call, run))
    write(run / 'suite.json', suite); write(run / 'rows.json', rows)
    write(run / 'receipt.json', g.seal({'files': {str(p.relative_to(run)): sha(p) for p in run.rglob('*.json')}}))
    output = tmp_path / 'review-ui'
    review_answers(run, output)
    page = (output / 'answer-review.html').read_text()
    assert '</script><script>window.injected' not in page
    assert '\\u003c/script' in page and 'connect-src \'none\'' in page
    assert '최종 답변 채점' in page
    review = g.review_template(suite, rows)
    review['reviews'][0].update(by='모의 검토자', at=g.now(), required_points_met=[True],
        behavior_correct=True, citations_supported=True, no_unsupported_claims=False)
    path = tmp_path / 'answers-reviewed.json'; write(path, review)
    assert g.main(['report','--run',str(run),'--reviews',str(path),'--output',str(tmp_path / 'report')]) == 0
    assert g.read(tmp_path / 'report/report.json')['summary']['answer_pass'] == 0
    assert g.read(tmp_path / 'report/report.json')['summary']['reviewed'] == 1
    review['run_binding'] = 'wrong-run'
    with pytest.raises(ValueError, match='run mismatch'): g.apply_reviews(suite, rows, review)
    receipt = g.read(run / 'receipt.json'); receipt['files'].pop('cases/00001/response.json'); receipt.pop('content_sha256')
    (run / 'receipt.json').write_text(json.dumps(g.seal(receipt)))
    with pytest.raises(ValueError, match='cover answer'): checked_run(run)


def _registry_sources(generation, tmp_path):
    import csv
    source = g.catalog(generation)['sources'][0]
    article = authoring.article_of(source)
    cm = tmp_path / 'cm.json'
    write(cm, {'schema_version': 'cm-field-core-e2e-v3', 'evidence_contract': {'authority_as_of': '20260916'},
               'cases': [{'id': 'cm-001', 'question': 'CM 질문', 'reference_answer': 'CM 기준답변',
                          'axes': {'answer_type': 'yes_no'}, 'topic': '모의 주제', 'source_question_no': 2,
                          'expected_articles': [{'law': source['document_name'], 'article': article, 'coordinate_scope': 'body'}]}]})
    internal = tmp_path / 'internal.csv'
    with internal.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(['팀', '전사상태', '중복원본ID', *authoring.FIELDS])
        writer.writerow(['리스크관리팀', 'transcribed', '', 'IR-1', '답 없는 질문', '', '', '', '', '', '', '', ''])
        writer.writerow(['리스크관리팀', 'partial', '', 'IR-2', '잘린 질문', '답', '2026-09-16', source['document_name'], article, '', '', '', ''])
        writer.writerow(['리스크관리팀', 'transcribed', 'IR-1', 'IR-3', '작성된 질문', '내규 답', '2026-09-16', source['document_name'], article, '', '', '', ''])
    return cm, internal


def test_registry_merges_collections_and_keeps_incomplete_cases(generation, tmp_path):
    from lawrag.pipeline import golden_registry as registry
    cm, internal = _registry_sources(generation, tmp_path)
    built = registry.build(cm, internal)
    stages = {e['id']: e['stage'] for e in built['cases']}
    assert stages == {'cm-001': 'ready', 'IR-1': 'question_only', 'IR-2': 'incomplete', 'IR-3': 'ready'}
    assert built['summary']['collections']['internal']['blockers']['transcription_incomplete'] == 1
    ir3 = next(e for e in built['cases'] if e['id'] == 'IR-3')
    assert 'duplicate_of:IR-1' in ir3['warnings'] and 'transcription_unverified' in ir3['warnings']
    clash = tmp_path / 'clash.csv'
    clash.write_text(internal.read_text(encoding='utf-8-sig').replace('IR-1,', 'cm-001,', 1), encoding='utf-8-sig')
    with pytest.raises(ValueError, match='collide'): registry.build(cm, clash)
    notes = tmp_path / 'notes.json'; write(notes, {'IR-3': {'tags': ['unknown']}})
    with pytest.raises(ValueError, match='unknown tag'): registry.build(cm, internal, notes)
    stale = deepcopy(built); stale['cases'][1]['stage'] = 'ready'
    with pytest.raises(ValueError, match='hash'): registry.ready_cases(stale)


def test_registry_import_carries_collection_to_report_and_checks_tags(generation, tmp_path):
    from lawrag.pipeline import golden_registry as registry
    cm, internal = _registry_sources(generation, tmp_path)
    notes = tmp_path / 'notes.json'; write(notes, {'IR-3': {'tags': ['reconciliation']}})
    path = tmp_path / 'registry.json'; write(path, registry.build(cm, internal, notes))
    bundle = authoring.prepare(path, 'registry', generation, tmp_path / 'authoring')
    draft = bundle['draft']
    assert [c['id'] for c in draft['cases']] == ['cm-001', 'IR-3']
    assert {d['id'] for d in draft['import_provenance']['deferred']} == {'IR-1', 'IR-2'}
    assert [c['collection'] for c in draft['cases']] == ['cm', 'internal']
    for c in draft['cases']:
        c['review'] = {'status': 'approved', 'by': 'synthetic-reviewer', 'at': '2026-09-16T10:00:00+09:00'}
    # One mock document cannot satisfy a reconciliation tag.
    with pytest.raises(ValueError, match='two documents'): g.freeze(draft, generation)
    draft['cases'][1]['tags'] = []
    suite = g.freeze(draft, generation)
    assert all(set(g.product_request(c)) == {'question', 'document_ids', 'use_llm'} for c in suite['cases'])
    rows = []
    for c in suite['cases']:
        sid = c['evidence_groups'][0]['any_of'][0]['source_id']
        r = {'query': {'question': c['question'], 'scope': {'document_version_ids': []}},
             'retrieval': {'candidates': [{'id': sid}], 'term_agent': {'use_llm': True, 'status': 'FINISH',
                                                                        'trace': [{'search_results': [{'id': sid}]}]}},
             'assembly': {'context': [{'id': sid}]},
             'answer': {'generation_id': suite['binding']['generation_id'], 'source_store_sha256': suite['binding']['store_sha256'],
                        'text': '답', 'claims': [{'source_ids': [sid]}]}}
        rows.append(g.score(c, r, suite['binding']))
    summary = g.report(suite, rows, tmp_path / 'report')
    assert set(summary['by_collection']) == {'cm', 'internal'}
    assert summary['by_collection']['internal']['total'] == 1 and 'by_tag' not in summary
