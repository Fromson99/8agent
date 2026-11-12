"""대사 항목 검토의 조사 위치는 근거 자체 위치만 쓰고 인용 연결 SQL을 보내지 않는다(현장 11-11 60초 시간 초과)."""
from types import SimpleNamespace

from semantic_runtime.comparison_research_bridge import locators


class NoSql:
    def execute(self, *args):
        raise AssertionError('locators must not query the reference join')


def port():
    matcher = SimpleNamespace(units={('d', 'u1'): {'surface': '제1조'}}, documents={'d': '문서'},
                              _unit_sources=lambda did, uid: ['s1'])
    session = SimpleNamespace(verify=lambda e: None, matcher=matcher,
                              store=SimpleNamespace(source=lambda did, block: {'unit_id': 'u1'}),
                              tools=SimpleNamespace(db=NoSql()))
    return SimpleNamespace(session=session, all_scope={'d'}, categories={'d': 'internal'})


EVIDENCE = {'document_id': 'd', 'unit_id': 'u1', 'source_id': 's1', 'evidence_id': 'e1',
            'spans': [{'block_id': 1, 'text': '본문'}]}


def test_own_unit_locator_without_reference_query():
    found = list(locators(port(), [EVIDENCE]).values())
    assert len(found) == 1
    assert found[0]['unit_id'] == 'u1' and found[0]['source_id'] == 's1'
    assert found[0]['origin_evidence_id'] == 'e1' and found[0]['reference_id'] is None
    assert found[0]['side'] == 'internal' and found[0]['coordinate'] == '제1조'


def test_evidence_outside_scope_gives_no_locator():
    p = port()
    p.all_scope = set()
    assert locators(p, [EVIDENCE]) == {}
