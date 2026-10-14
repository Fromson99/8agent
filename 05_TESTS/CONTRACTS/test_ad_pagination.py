"""AD list paging boundaries and the SQL context seen by the next turn."""
import re

import pytest

from semantic_runtime import ad_language
from semantic_runtime.ad_mode import ENTER, handle
from semantic_runtime.ad_store import Store


@pytest.mark.parametrize('total', [0, 1, 19, 20, 21, 25, 40, 41, 51])
@pytest.mark.parametrize('kind', ['shortcut', 'wiki'])
def test_pages_round_trip_without_gaps_and_keep_the_last_page(tmp_path, total, kind):
    store = Store(tmp_path / 'ad.sqlite')
    try:
        with store.transaction():
            sid = store.session('team', 'genos', 'chat')['id']
            view = store.view(sid, kind, [
                {'kind': kind, 'id': str(i), 'title': f'항목 {i}'}
                for i in range(1, total + 1)
            ])
            expected = [list(range(i, min(i + 20, total + 1)))
                        for i in range(1, total + 1, 20)] or [[]]

            def check(page, ordinals, number):
                assert [r['ordinal'] for r in page['rows']] == ordinals
                assert page['view_id'] == view
                assert page['page_number'] == (number if total else 0)
                assert page['page_count'] == (len(expected) if total else 0)
                assert page['has_previous'] == (number > 1)
                assert page['has_more'] == (number < len(expected))
                context = ad_language.state(store, sid)['active_view']
                assert [r['ordinal'] for r in context['rows']] == ordinals
                assert context['has_more'] == page['has_more']
                assert context['has_previous'] == page['has_previous']

            for number, ordinals in enumerate(expected, 1):
                check(store.page(sid), ordinals, number)
            # Asking beyond either boundary keeps a usable table on screen.
            check(store.page(sid), expected[-1], len(expected))
            for number in range(len(expected) - 1, 0, -1):
                check(store.page(sid, previous=True), expected[number - 1], number)
            check(store.page(sid, previous=True), expected[0], 1)
            if len(expected) > 1:
                check(store.page(sid), expected[1], 2)
    finally:
        store.close()


@pytest.mark.parametrize('kind', ['shortcut', 'wiki'])
@pytest.mark.parametrize('use_model', [False, True])
def test_chat_pagination_survives_reopen_and_retry(tmp_path, monkeypatch, kind, use_model):
    path = tmp_path / 'ad.sqlite'
    assert handle(path, 'team', 'genos', 'chat', ENTER, 'enter')['ad_mode']
    rows = [{'kind': kind, 'id': str(i), 'title': f'항목 {i}', 'status': 'READY'}
            for i in range(1, 52)]
    # Isolate display/command wiring from unrelated source ingestion.
    monkeypatch.setattr('semantic_runtime.ad_backend.Backend.list', lambda *a, **k: rows)
    monkeypatch.setattr('semantic_runtime.ad_backend.Backend.revision', lambda *a: 1)
    calls = []

    def model(context, *_):
        calls.append(context)
        action = {'다음': 'next', '이전': 'previous'}.get(context['question'], 'list')
        plan = {'action': action, 'args': {'kind': kind, 'query': ''} if action == 'list' else {}}
        return {'plan': plan, 'receipt': {'provider': 'genos', 'trust_zone': 'internal'}, 'raw': plan}

    def ask(question, request):
        return handle(path, 'team', 'genos', 'chat', question, request,
                      interpret=model if use_model else None)

    view = None
    for request, (question, first, last) in enumerate([
        (kind + ' 목록', 1, 20), ('다음', 21, 40), ('다음', 41, 51),
        ('다음', 41, 51), ('이전', 21, 40), ('이전', 1, 20), ('이전', 1, 20),
    ]):
        result = ask(question, str(request))
        assert result['answer_status'] == 'administration', result
        view = view or result['view_id']
        assert result['view_id'] == view
        assert [int(x) for x in re.findall(r'\| ' + view + r':(\d+) \|', result['text'])] == list(range(first, last + 1))
        assert result['has_more'] == (last < 51)
        assert result['has_previous'] == (first > 1)
        assert '채팅에' in result['text'] and '채팅에' in result['table_html']
        call_count = len(calls)
        assert ask(question, str(request)) == result
        assert len(calls) == call_count


def test_page_cannot_read_another_conversations_view(tmp_path):
    store = Store(tmp_path / 'ad.sqlite')
    try:
        with store.transaction():
            sid = store.session('team', 'genos', 'chat')['id']
            other = store.session('team', 'genos', 'other')['id']
            view = store.view(other, 'shortcut', [{'kind': 'shortcut', 'id': 'private'}])
            with pytest.raises(ValueError, match='AD_VIEW'):
                store.page(sid, view)
    finally:
        store.close()
