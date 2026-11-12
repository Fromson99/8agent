"""대사: a failed report or an unexpected investigation failure keeps what was done (user 2026-11-12).

MAIN217 runs lost the whole 대사 answer to a report-stage 409 four times ("마무리 답변의 출처 연결이 없습니다").
Real API under the selected profile; synthetic originals and scripted model only.
"""
from dataclasses import is_dataclass, replace
import importlib.util
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from semantic_runtime.chat_adapter import views

HERE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('failure_compare_profile', HERE / '05_TESTS/CONTRACTS/test_comparison_selected_profile.py')
profile = importlib.util.module_from_spec(spec); spec.loader.exec_module(profile)
tree = profile.tree


def patched(app, **changes):
    """The registered workflow definition with some callables replaced (the loaded package is private)."""
    runtime = app.state.workflow_runtime
    real = runtime.registry.resolve

    def resolve(*args, **kwargs):
        definition = real(*args, **kwargs)
        if is_dataclass(definition):
            return replace(definition, **changes)
        copy = type(definition).__new__(type(definition)); copy.__dict__.update(definition.__dict__)
        for key, value in changes.items():
            setattr(copy, key, value)
        return copy
    runtime.registry.resolve = resolve
    return sys.modules[type(runtime).__module__.rsplit('.', 1)[0] + '.contracts'].WorkflowError


def failing_finalize(app):
    """finalize.apply of the loaded (private) workflow package raises the field's report-stage 409 every time."""
    runtime = app.state.workflow_runtime
    package = type(runtime).__module__.rsplit('.', 1)[0]
    real = runtime.registry.resolve
    calls = []

    def resolve(*args, **kwargs):
        definition = real(*args, **kwargs)
        module = sys.modules[package + '.risk_team_compare_workflow.finalize']
        error = sys.modules[package + '.contracts'].WorkflowError

        def apply(*a, **k):
            calls.append(1)
            raise error('WORKFLOW_FINALIZATION_SOURCE', '마무리 답변의 출처 연결이 없습니다.', 409)
        module.apply = apply
        return definition
    runtime.registry.resolve = resolve
    return calls


def test_a_failed_report_answers_with_finished_items_and_read_originals(tmp_path, tree):
    app, transport = profile.application(tmp_path, tree)
    with TestClient(app, raise_server_exceptions=False) as client:
        calls = failing_finalize(app)
        response = client.post('/v1/rag/ask', json=profile.BODY)
        assert calls, 'the report stage of the flow ran and failed'
        assert response.status_code == 200, response.text
        value = response.json()
        again = client.post('/v1/rag/ask', json=profile.BODY)
    assert value['response_schema'] == 'workflow-result-v1' and value['status'] == 'partial'
    assert value['answer']['answer_status'] == 'PARTIAL' and value['answer']['claims'] == []
    text = value['answer']['text']
    assert text.startswith('대사 보고서를 정리하는 중 멈췄습니다.') and '**읽은 조문**' in text
    cards = value['assembly']['term_agent']['source_bundle']['sources']
    assert cards and {c['side'] for c in cards} <= {'internal', 'external'}
    assert all(c['interpretation_status'] == 'UNVERIFIED' for c in cards)
    points = value['failure_points']
    assert any(p['stage'] == '보고서 정리' and p['title'] == '마무리 답이 근거 조문과 이어지지 않아 멈춤' for p in points)
    assert [p['no'] for p in points] == list(range(1, len(points) + 1))
    shown = views().render(views().public_response(value))
    assert 'data-genos-failure="true"' in shown and '(409)' not in shown and '(500)' not in shown
    assert again.status_code == 200 and again.json()['answer'] == value['answer'], 'the saved partial report is returned'


def test_an_unexpected_investigation_failure_still_reports(tmp_path, tree):
    app, transport = profile.application(tmp_path, tree)
    with TestClient(app, raise_server_exceptions=False) as client:
        def broken(ctx):
            raise TypeError('defect in the comparison flow')
        patched(app, entrypoint=broken)
        response = client.post('/v1/rag/ask', json=profile.BODY)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['status'] in ('partial', 'failed') and value['response_schema'] == 'workflow-result-v1'
    assert any(p['stage'] == '조문 찾기·읽기' and p['title'] == '시스템 오류로 멈춤' for p in value.get('failure_points', []))
