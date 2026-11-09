"""문서 대사 외규 조사 수정(2026-11-08): 검색어·정의 자동 확보·조 전체 비교·묶음 안 공유.

Synthetic originals through the real API under the selected profile; scripted model only.
Run against a code root that has the document workflow, e.g. run_tests.py --code-root <code>.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from test_legal_agent_double_harness import wire

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('document_mode_base', HERE / 'test_document_compare_mode.py')
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)

PRINCIPAL = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['inside', 'outside', 'other']}
# Each internal article names the external rule it follows, so each unit searches one rule.
INSIDE = ['제1조(승인) 회사는 모의승인규정에 따라 승인 후 보고서를 제출한다.',
          '제2조(기록) 회사는 모의기록규정에 따라 기록을 5년 이상 보관한다.']
APPROVAL = ['제1조(승인)', '①승인 후 보고서를 제출한다.', '②보고서는 5영업일 이내에 제출한다.',
            '제2조(정의) 이 규정에서 “보고서”란 결과를 적은 문서를 말한다.']
RECORD = ['제1조(기록) 기록은 5년 이상 보관한다.']


# 제3조 shares no word with the unit's search words; only the internal citation can bring it in.
CITING = ['제1조(승인) 회사는 「모의승인규정」 제3조에 따라 승인 후 보고서를 제출한다.', INSIDE[1]]
CITED = APPROVAL + ['제3조(서류) 신청인은 원본 서류를 첨부한다.']


def build_tree(tmp_path, term_glossary, inside=INSIDE, approval=APPROVAL, name='tree4'):
    from lawrag.pipeline.term_generation import build_generation
    from lawrag.pipeline.fulltext_stage import derive
    folder = tmp_path / name; folder.mkdir()
    approval_units = [('0', None, {'family': 'kr_article', 'surface': '제1조', 'title': '승인', 'span': [0, 3]}),
                      ('1', '0', {'family': 'kr_paragraph', 'surface': '제1항', 'span': [1, 2]}),
                      ('2', '0', {'family': 'kr_paragraph', 'surface': '제2항', 'span': [2, 3]}),
                      ('3', None, {'family': 'kr_article', 'surface': '제2조', 'title': '정의', 'span': [3, 4]})]
    if len(approval) > 4:
        approval_units.append(('4', None, {'family': 'kr_article', 'surface': '제3조', 'title': '서류', 'span': [4, 5]}))
    documents = [('inside', '모의내규', 'internal', inside,
                  [('0', None, {'family': 'kr_article', 'surface': '제1조', 'title': '승인', 'span': [0, 1]}),
                   ('1', None, {'family': 'kr_article', 'surface': '제2조', 'title': '기록', 'span': [1, 2]})]),
                 ('outside', '모의승인규정', 'external', approval, approval_units),
                 ('other', '모의기록규정', 'external', RECORD,
                  [('0', None, {'family': 'kr_article', 'surface': '제1조', 'title': '기록', 'span': [0, 1]})])]
    with sqlite3.connect(folder / 'source.sqlite') as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
          CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
          CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        for did, name, category, texts, units in documents:
            artifact = hashlib.sha256(json.dumps(texts).encode()).hexdigest()
            db.execute('INSERT INTO document VALUES (?,?,?,?)', (did, name, artifact, json.dumps(
                {'document_category': category, 'document_metadata': {'team': 'risk_team'}}, ensure_ascii=False)))
            for uid, parent, unit in units:
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)', (did, uid, parent, json.dumps(unit, ensure_ascii=False)))
            for i, text in enumerate(texts):
                db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)', (did, str(i), str(i), text, artifact, '{}'))
    build_generation(folder / 'source.sqlite', term_glossary, folder / 'built', serving=True, fulltext_workers=1)
    derive(folder / 'built/generation', folder / 'indexed', workers=1)
    return folder / 'indexed', None


@pytest.fixture
def tree4(tmp_path, term_glossary):
    return build_tree(tmp_path, term_glossary)


@pytest.fixture
def tree5(tmp_path, term_glossary):
    return build_tree(tmp_path, term_glossary, inside=CITING, approval=CITED, name='tree5')


class UnitTransport(base.DocTransport):
    """One comparison unit per row, named with the internal article number.

    With ``child_finish`` the external child returns after its first reads, so it
    hands back only the passage its first search read (as real children often do).
    """

    def __init__(self, *, child_finish=False):
        super().__init__()
        self.child_finish = child_finish

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        stage = view.get('source_stage', view['phase'])
        if self.child_finish and stage.startswith('source-law-sources-'):
            self.views.append((stage, deepcopy(view)))
            return wire({'target_id': None, 'query': None, 'reason': '확보한 원문 반환'})
        if stage == 'workflow-group_read':
            self.views.append(('workflow-group_read', deepcopy(view)))
            return wire({'units': [{'label': row['label'].split(' ')[0] + ' ' + ('승인 보고' if '승인' in row['text'] else '기록 보관'),
                                    'rows': [row['ref']], 'summary': row['text'].split(') ', 1)[-1]} for row in view['rows']],
                         'not_target': [], 'hold': []})
        return super().send_once(body=body, ticket=ticket)


def workflow_module(name):
    """The workflow package as the app loaded it (a hash-named copy, see workflow_bridge.package)."""
    import importlib
    from semantic_runtime.workflow_bridge import package
    return importlib.import_module(package() + '.' + name)


def run(tmp_path, tree, request_id, *, child_finish=False, patch=None):
    transport = UnitTransport(child_finish=child_finish)
    app = base.application(tmp_path, tree, transport, PRINCIPAL)
    if patch:
        patch(workflow_module('risk_team_document_compare_workflow.flow'))
    with TestClient(app) as client:
        value = client.post('/v1/rag/ask', json=base.body('문서 대사: 모의내규', request_id)).json()
    assert value.get('workflow_id') == base.DOCUMENT_WORKFLOW and value['status'] == 'completed', value
    return app, transport, value


def child_journals(app, value):
    from semantic_runtime.legal_agent import journal_storage
    folder = app.state.workflow_runtime.root / value['run_id']
    out = []
    for path in sorted(folder.glob('children/*/legal-agent/runs/*/*/journal.sqlite')):
        with journal_storage.connect(str(path)) as db:
            events = [(kind, json.loads(payload)) for kind, payload in
                      db.execute('SELECT kind,journal_text(payload_json) FROM event ORDER BY seq')]
            texts = [r[0] for r in db.execute('SELECT journal_text(text) FROM evidence_span')]
        out.append({'events': events, 'texts': texts})
    return out


def compare_views(transport):
    return [v for s, v in transport.views if s == 'workflow-unit_compare']


def external_texts(view, found_for=None):
    return [o['text'] for s in view['sources'] if s['side'] == 'external' and (found_for is None or s.get('found_for') == found_for)
            for o in s['citation_options']]


def test_search_hints_drop_internal_numbering():
    from workflow.risk_team_document_compare_workflow.flow import external_task, plain
    unit = {'unit_id': 'g-U1', 'label': '제2-3조 적용대상', 'summary': '자산총액 1천억원 이상 회사에 적용하며, 제2-15조는 투자매매업 회사에 적용한다.'}
    question, task = external_task('모의 리스크관리 모범규준', unit, '제2-3조(적용대상) 이 규준은 …', '문서 전체 대사', [])
    assert task['search_hints'] == ['적용대상']
    assert task['question_definitions'] is False
    assert '"적용대상"' in task['issues'][0]['question'] and '외규의 같은 번호 조문과 관계없다' in question
    # Ordinary measurements, numbered items and circled paragraph marks.
    assert plain('최소 1.5배 유지') == '최소 1.5배 유지'
    assert plain('① 1. 가. (1) 이사회 보고') == '이사회 보고'
    assert plain('제4-11조의2 담보유지비율') == '담보유지비율'
    # A unit named only by its number searches its summary, never the bare number.
    assert external_task('규준', {**unit, 'label': '제3조'}, '본문', '요청', [])[1]['search_hints'] == [plain(unit['summary'])]


@pytest.mark.parametrize('value,ok', [(False, True), (True, False), ('false', False)])
def test_question_definitions_can_only_be_switched_off(value, ok):
    from semantic_runtime.legal_agent.errors import ContractError
    from semantic_runtime.legal_agent.workflow_execution import validate_task
    task = {'source_category': 'external', 'search_hints': ['승인'], 'facts': [],
            'issues': [{'id': 'u1', 'question': '승인 원문', 'numeric': False}], 'question_definitions': value}
    if ok:
        validate_task(task, '요청')
    else:
        with pytest.raises(ContractError):
            validate_task(task, '요청')


def test_compare_gets_whole_articles_and_the_neighbour_units_rule(tmp_path, tree4):
    app, transport, value = run(tmp_path, tree4, 'w1', child_finish=True)
    assert value['document_compare']['units'] == 2, value['document_compare']
    from semantic_runtime.legal_agent import journal_storage
    folder = app.state.workflow_runtime.root / value['run_id']
    with journal_storage.connect(str(folder / 'journal.sqlite')) as db:
        tasks = [json.loads(r[0])['args']['task'] for r in db.execute("SELECT input_json FROM workflow_call WHERE kind='rag'")]
        state = json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
    assert sorted(t['search_document_ids'][0] for t in tasks) == ['other', 'outside']
    assert all(t['question_definitions'] is False and not any('제1조' in h or '제2조' in h for h in t['search_hints']) for t in tasks)
    views = compare_views(transport)
    approval = next(v for v in views if '승인' in v['unit']['label'])
    record = next(v for v in views if '기록' in v['unit']['label'])
    # The child read the matching paragraph; the comparison shows the whole article 제1조.
    own = external_texts(approval, 'this_unit')
    assert {'①승인 후 보고서를 제출한다.', '②보고서는 5영업일 이내에 제출한다.'} <= set(own), own
    units = [u for g in state['groups'].values() for u in g.get('units', [])]
    child_texts = {t for c in child_journals(app, value) for t in c['texts']}
    assert not set(APPROVAL[:3]) <= child_texts, child_texts      # the child itself did not read all of 제1조
    assert any(set(u['articles']) != set(u['external']) for u in units), units
    # Each unit also sees the article its neighbour found (same reading group).
    assert any('5년 이상 보관' in t for t in external_texts(approval, 'nearby_unit'))
    assert any('보고서를 제출한다' in t for t in external_texts(record, 'nearby_unit'))
    assert all(u.get('shared_external') for u in units)
    # Repeating the request reuses the saved run.
    count = len(transport.views)
    with TestClient(app) as client:
        again = client.post('/v1/rag/ask', json=base.body('문서 대사: 모의내규', 'w1')).json()
    assert again['answer'] == value['answer'] and len(transport.views) == count


def definition_acquisitions(app, value):
    found = []
    for child in child_journals(app, value):
        for kind, payload in child['events']:
            if kind in ('SYSTEM_DEFINITION_ORIGINALS_ACQUIRED', 'SYSTEM_DEFINITION_ORIGINALS_PENDING'):
                found.extend(payload['targets'])
    return found


def test_definitions_of_terms_in_the_internal_original_are_not_acquired(tmp_path, tree4, monkeypatch):
    app, transport, value = run(tmp_path, tree4, 'd1')
    assert definition_acquisitions(app, value) == []
    assert not any('“보고서”란' in t for v in compare_views(transport) for t in external_texts(v))
    # Contrast: the same run without the switch acquires the 보고서 definition of 모의승인규정.
    def without_switch(flow):
        original = flow.external_task

        def task_without_switch(*args, **kwargs):
            question, task = original(*args, **kwargs)
            task.pop('question_definitions')
            return question, task
        monkeypatch.setattr(flow, 'external_task', task_without_switch)
    (tmp_path / 'contrast').mkdir()
    app2, transport2, value2 = run(tmp_path / 'contrast', tree4, 'd2', patch=without_switch)
    assert definition_acquisitions(app2, value2), 'fixture must have a definition the question names'



def test_neighbour_articles_are_bounded(tmp_path, tree4):
    def tiny(flow):
        flow.SHARED_CHARS = 1          # nothing of the neighbour fits; the unit's own articles stay
    app, transport, value = run(tmp_path, tree4, 's1', child_finish=True, patch=tiny)
    views = compare_views(transport)
    assert len(views) == 2 and all(external_texts(v, 'this_unit') for v in views)
    assert not any(external_texts(v, 'nearby_unit') for v in views)


def test_external_article_cited_in_the_unit_is_read_without_a_search(tmp_path, tree5):
    app, transport, value = run(tmp_path, tree5, 'c1', child_finish=True)
    approval = next(v for v in compare_views(transport) if '승인' in v['unit']['label'])
    cited = external_texts(approval, 'cited_in_unit')
    assert '제3조(서류) 신청인은 원본 서류를 첨부한다.' in cited, (cited, external_texts(approval))
    from semantic_runtime.legal_agent import journal_storage
    folder = app.state.workflow_runtime.root / value['run_id']
    with journal_storage.connect(str(folder / 'journal.sqlite')) as db:
        state = json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
    units = {u['label']: u for g in state['groups'].values() for u in g.get('units', [])}
    record = next(u for label, u in units.items() if '기록' in label)
    assert next(u for label, u in units.items() if '승인' in label)['cited'] and record['cited'] == []


# 제1조 declares "규정"; 제2조 cites "규정 제3조" (the index alone cannot name that document).
DECLARING = ['제1조(목적) 이 요령은 모의승인규정(이하 "규정"이라 한다)에 따라 정한다.',
             '제2조(서류) 회사는 규정 제3조에 따라 원본 서류를 첨부한다.']


@pytest.fixture
def tree6(tmp_path, term_glossary):
    return build_tree(tmp_path, term_glossary, inside=DECLARING, approval=CITED, name='tree6')


def test_a_name_declared_in_another_article_leads_to_the_cited_article(tmp_path, tree6):
    app, transport, value = run(tmp_path, tree6, 'n1', child_finish=True)
    view = next(v for v in compare_views(transport)
                if any('원본 서류를 첨부한다' in o['text'] for s in v['sources'] if s['side'] == 'internal' for o in s['citation_options']))
    assert '제3조(서류) 신청인은 원본 서류를 첨부한다.' in external_texts(view, 'cited_in_unit'), external_texts(view)
    from semantic_runtime.legal_agent import journal_storage
    folder = app.state.workflow_runtime.root / value['run_id']
    with journal_storage.connect(str(folder / 'journal.sqlite')) as db:
        state = json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
    names = [n for g in state['groups'].values() for u in g.get('units', []) for n in u.get('cited_names', [])]
    assert names and names[0]['name'] == '규정' and '모의승인규정' in names[0]['long_form'], names


class AbbreviatingTransport(UnitTransport):
    """Unit names written with the abbreviation another rule declared (승인규정)."""

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage', view['phase']) == 'workflow-group_read':
            self.views.append(('workflow-group_read', deepcopy(view)))
            return wire({'units': [{'label': '승인규정 서류 첨부', 'rows': [r['ref'] for r in view['rows']], 'summary': '승인규정에 따른 서류'}],
                         'not_target': [], 'hold': []})
        return super().send_once(body=body, ticket=ticket)


def test_the_model_is_shown_what_a_declared_abbreviation_stands_for(tmp_path, term_glossary):
    record = ['제1조(기록) 「모의승인규정」(이하 "승인규정"이라 한다)에 따른 기록은 5년 이상 보관한다.']
    global RECORD
    saved, RECORD = RECORD, record
    try:
        tree = build_tree(tmp_path, term_glossary, name='tree7')
    finally:
        RECORD = saved
    transport = AbbreviatingTransport(child_finish=True)
    app = base.application(tmp_path, tree, transport, PRINCIPAL)
    with TestClient(app) as client:
        value = client.post('/v1/rag/ask', json=base.body('문서 대사: 모의내규', 'a1')).json()
    assert value.get('workflow_id') == base.DOCUMENT_WORKFLOW, value
    child = [v for s, v in transport.views if s.startswith('source-law-sources-')]
    cards = [c for v in child for c in v.get('declared_names', [])]
    assert any(c['name'] == '승인규정' and c['means'] == '모의승인규정' and '모의기록규정' in c['declared_in'] for c in cards), \
        [sorted(v)[:60] for v in child]
