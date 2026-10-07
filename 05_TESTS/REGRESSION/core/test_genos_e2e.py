"""Offline operational contracts; synthetic source and fake HTTP, no live models."""
import json
from pathlib import Path

import pytest

from lawrag.pipeline import genos_e2e as e2e
from semantic_runtime import genos
from semantic_runtime.genos_backend import unit_vector


XML = '''<법령><기본정보><법령명_한글>테스트규정</법령명_한글></기본정보><조문>
<조문단위><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>목적</조문제목>
<조문내용>제1조(목적) 이 규정은 위험관리 기준을 정한다.</조문내용></조문단위>
<조문단위><조문번호>2</조문번호><조문여부>조문</조문여부><조문제목>의무</조문제목>
<조문내용>제2조(의무) 담당자는 위험관리 내용을 기록하여야 한다.</조문내용></조문단위>
</조문></법령>'''


@pytest.mark.parametrize('case', ['success', 'bad_quote', 'empty', 'bad_embedding', 'dimension', 'bad_citation', 'limit'])
@pytest.mark.parametrize('source_kind', ['external', 'internal'])
def test_one_document_existing_pipeline(tmp_path, monkeypatch, case, source_kind):
    from lawrag.core import llm
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    monkeypatch.setenv('GENOS_BASE_URL', 'http://genos.invalid:30908')
    monkeypatch.setenv('GENOS_GATEWAY_API_PREFIX', '/v1')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '226')
    monkeypatch.setenv('GENOS_LLM_KEY', 'dummy-secret')
    monkeypatch.setenv('GENOS_EMBED_SERVING_ID', '19')
    monkeypatch.setenv('GENOS_EMBED_KEY', 'dummy-embed-secret')
    for key in ('GENOS_LLM_URL', 'GENOS_EMBED_URL', 'GENOS_LLM_MODEL', 'GENOS_LLM_MODEL', 'GENOS_EMBED_MODEL'):
        monkeypatch.delenv(key, raising=False)
    untouched = tmp_path / 'existing-structure'
    untouched.mkdir()
    monkeypatch.setenv('STRUCTURE_STORE', str(untouched))
    raw = tmp_path / 'test.xml'
    raw.write_text(XML, encoding='utf-8')
    calls = []

    def request(target, path, payload=None, **kwargs):
        assert '/v1' in target.root
        calls.append((target.root, path, payload))
        if payload is None:
            return {'data': [{'id': '2292' if '/226/' in target.root else 'embed-model'}]}
        if path == '/embeddings':
            assert payload['model'] == 'embed-model'
            count = len(payload['input'])
            dim = 3 if case == 'dimension' and count == 1 and '질문' in payload['input'][0] else 2
            return {'data': [{'index': 0 if case == 'bad_embedding' else i, 'embedding': [1.] * dim}
                             for i in reversed(range(count))]}
        assert payload['model'] == '2292'  # Not gateway ID 226.
        assert payload['chat_template_kwargs']['enable_thinking'] is False
        context = json.loads(payload['messages'][1]['content'])['context']
        if 'chunks' in context:
            value = {'chunks': [{'id': c['id'], 'quote': 'not in source' if case == 'bad_quote' else c['text'][:20]}
                                for c in context['chunks']]}
        elif 'candidates' in context:
            value = {'selected_ids': [c['id'] for c in context['candidates'][:2]]}
        else:
            c = context['context'][0]
            value = {'text': '검증된 답변', 'claims': [{'text': '위험관리 기준을 정한다.',
                     'citations': [{'source_id': c['id'], 'quote': 'not in source' if case == 'bad_citation' else c['text'][:20]}]}],
                     'unresolved': []}
        return {'choices': [{'message': {'content': '' if case == 'empty' else json.dumps(value, ensure_ascii=False)},
                             'finish_reason': 'stop'}], 'usage': {'total_tokens': 10}}

    monkeypatch.setattr(genos, 'request_json', request)
    argv = ['e2e', '--backend', 'genos', '--document', str(raw), '--source', source_kind,
            '--data-root', str(tmp_path / 'old-data'), '--run-root', str(tmp_path / 'results'),
            '--question', '질문: 위험관리 의무는 무엇인가?', '--execute']
    if case == 'limit':
        argv += ['--max-chunks', '1']
    code = e2e.main(argv)
    output = next((tmp_path / 'results/e2e').iterdir())
    assert raw.read_text() == XML
    assert not list(untouched.iterdir())
    assert __import__('os').environ['STRUCTURE_STORE'] == str(untouched)
    assert not list(output.rglob('CURRENT.json'))
    for file in output.rglob('*.json'):
        assert 'dummy-secret' not in file.read_text()
        assert 'dummy-embed-secret' not in file.read_text()
    if case == 'success':
        assert code == 0, (output / 'failure.json').read_text() if (output / 'failure.json').exists() else output
        result = json.loads((output / 'result.json').read_text())
        assert result['vector_search'] and result['cited_claims'] and not result['main_activated']
        assert (output / 'answer.txt').read_text().strip()
        retrieval = json.loads((output / 'retrieval.json').read_text())
        assert retrieval['routes']['vector'] > 0
        assert json.loads((output / 'selection.json').read_text())['method'] == 'genos'
        assert len([c for c in calls if c[1] == '/models']) == 2
    else:
        assert code == 1
        assert (output / 'failure.json').exists()
        assert not (output / 'result.json').exists()
        if case == 'limit':
            assert not calls


@pytest.mark.parametrize('values', [[], [0, 0], [True, 1], [float('nan')], [float('inf')], ['1']])
def test_invalid_vectors(values):
    with pytest.raises(ValueError):
        unit_vector(values)


def test_unregistered_requires_explicit_source(tmp_path):
    raw = tmp_path / 'internal.xml'
    raw.write_text(XML)
    with pytest.raises(ValueError, match='--source'):
        e2e.choose_document(tmp_path, str(raw), 'auto')
