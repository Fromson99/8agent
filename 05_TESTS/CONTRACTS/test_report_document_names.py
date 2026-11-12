"""The progress report names documents; the short numbers the model works with stay internal (user 2026-11-11).

Field reply: "내규 문서(D35, D31)를 검색 대상으로 설정했으나". Actual HTTP/store/pipeline boundary with a
scripted model; the numbers come from the request's real document table.
"""
import json
import test_guided_continue_bounds as bounds
from semantic_runtime.legal_agent import progress_report as pr
from test_multiturn_structured_scope import tree
from test_progress_report import Reporting, serve, pending


def number_in_reasons(value):
    if isinstance(value, dict):
        return {k: number_in_reasons(v) for k, v in value.items()}
    if isinstance(value, list):
        return [number_in_reasons(v) for v in value]
    return 'D2 문서를 확인' if value == '모의 이유: 다음 본문 확인' else value


def test_report_input_and_reply_carry_the_document_name(tree, tmp_path, monkeypatch):
    fill = bounds.fill
    monkeypatch.setattr(bounds, 'fill', lambda schema: number_in_reasons(fill(schema)))
    transport = Reporting()
    (response,), _ = serve(tree, tmp_path, transport, pending, monkeypatch)
    assert response.status_code == 200, response.text
    view = transport.reports[0]['view']
    sent = json.dumps({k: view[k] for k in ('actions', 'drafts', 'rejections')}, ensure_ascii=False)
    assert '모의승인규정 문서를 확인' in sent and 'D2' not in sent
    assert 'D2' not in response.json()['answer']['text']
    assert '문서 번호(C1·D35 같은 ID)' in transport.reports[0]['system']


def test_only_known_numbers_change_and_the_json_stays_valid():
    names = {'D3': '그 "상품" 준칙'}
    text = pr.named(json.dumps({'reason': 'D3, {D3}, D30, AD3 확인'}, ensure_ascii=False), names)
    assert json.loads(text)['reason'] == '그 "상품" 준칙, 그 "상품" 준칙, D30, AD3 확인'
    assert pr.named('D3 확인', {}) == 'D3 확인'


class Work:
    def __init__(self, rows):
        self.rows = rows
        self.db = self

    def find(self, table, where):
        assert table == 'navigation_handle'
        return [r for r in self.rows if where(r)]


def test_names_come_from_the_document_rows_with_the_folder_path_removed():
    work = Work([{'handle': '@model:D7', 'kind': 'model-document-v2', 'identity_json': json.dumps({'document_id': 'x', 'name': '내규 > 리스크 > 상품관리준칙'})},
                 {'handle': '@model:U1', 'kind': 'model-reference-v2', 'identity_json': '"unit"'}])
    assert pr.document_names(work) == {'D7': '상품관리준칙'}
