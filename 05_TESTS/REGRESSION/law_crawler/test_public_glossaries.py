import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from lawrag.pipeline import collect_public_glossaries as g

@pytest.fixture
def collector(tmp_path, monkeypatch):
    monkeypatch.setattr(g, 'data_path', lambda *p: tmp_path.joinpath(*p))
    return g.Collector('test')

def test_cache_checks_request_and_original_hash(collector):
    calls = []
    def request(*a, **kw):
        calls.append(a)
        return SimpleNamespace(content=b'original', status_code=200, headers={}, raise_for_status=lambda: None)
    collector.client.request = request
    assert collector.fetch('x', 'source', 'https://example.org/a') == b'original'
    assert collector.fetch('x', 'source', 'https://example.org/a') == b'original'
    assert len(calls) == 1
    with pytest.raises(ValueError, match='conflict'):
        collector.fetch('x', 'source', 'https://example.org/b')
    (collector.raw / 'x/source').write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='conflict'):
        collector.fetch('x', 'source', 'https://example.org/a')

def test_empty_http_200_is_not_collected(collector):
    collector.client.request = lambda *a, **k: SimpleNamespace(content=b'', raise_for_status=lambda: None)
    with pytest.raises(ValueError, match='Empty response'):
        collector.fetch('x', 'source', 'https://example.org')
    assert not (collector.raw / 'x/source').exists()

def nts_fetch(*, mismatched_detail=False, duplicate=False):
    def fetch(source, name, url, **kwargs):
        if name == 'landing.html': return b'<html/>'
        action = kwargs['data']['actionId']
        item = {'ntstTrgyDictBrkdId': '123', 'ntstTrgyDictCntn': '신탁',
                'ntstTrgyDictEnglCntn': 'trust', 'ntstTrgyDictChchCntn': None,
                'ntstTrgyDictEpnCntn': '목록의 잘린 설명 ...'}
        if action == 'ASISTJ001MR01':
            payload = {'recordCount': 2 if duplicate else 1, 'pageIndex': 1,
                       'trgyDictInqrDVOList': [item, item] if duplicate else [item]}
        else:
            item['ntstTrgyDictEpnCntn'] = '상세 화면이 제공하는 완전한 설명과 조건.'
            if mismatched_detail: item['ntstTrgyDictBrkdId'] = '456'
            payload = {'trgyDictInqrDVO': item}
        return json.dumps({'status': 'SUCCESS', 'data': {action: payload}}).encode()
    return fetch

def test_nts_uses_full_definition_and_preserves_identity(collector):
    collector.fetch = nts_fetch()
    collector.nts()
    path = collector.structured / 'nts/entries.jsonl'
    row = json.loads(path.read_text())
    assert row['id'] == 'nts:123'
    assert row['definition'] == '상세 화면이 제공하는 완전한 설명과 조건.'
    assert row['review_status'] == 'unreviewed'
    assert collector.receipt['sources']['nts']['entries'] == 1

@pytest.mark.parametrize('kwargs,error', [({'duplicate': True}, 'Duplicate NTS'),
                                          ({'mismatched_detail': True}, 'identity mismatch')])
def test_nts_rejects_incomplete_identity_mapping(collector, kwargs, error):
    collector.fetch = nts_fetch(**kwargs)
    with pytest.raises(ValueError, match=error): collector.nts()
    assert not (collector.structured / 'nts/entries.jsonl').exists()

def test_failure_does_not_mark_other_source_complete(collector):
    collector.bok = lambda: (_ for _ in ()).throw(ValueError('not a PDF'))
    collector.econedu = lambda: collector.record('econedu', status='collected', entries=3)
    result = collector.run(['bok', 'econedu'])
    assert result['collection_complete'] is False
    assert result['sources']['bok']['status'] == 'incomplete'
    assert result['sources']['econedu']['status'] == 'collected'


def test_external_status_reads_only_external_receipt(tmp_path, monkeypatch, capsys):
    from lawrag.pipeline import glossary_alignment as cli
    monkeypatch.setattr(cli, 'data_path', lambda *p: tmp_path.joinpath(*p))
    receipt = tmp_path / 'LOGS/glossaries/test/collection.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'sources': {'nts': {'details_complete': 25}}}))
    assert cli.main(['status', '--external', '--snapshot', 'test']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['sources']['nts']['details_complete'] == 25
    assert not (tmp_path / 'LEXICON').exists()


def test_source_filter_is_not_silently_ignored():
    from lawrag.pipeline import glossary_alignment as cli
    with pytest.raises(SystemExit) as error:
        cli.main(['status', '--source', 'nts'])
    assert error.value.code == 2
