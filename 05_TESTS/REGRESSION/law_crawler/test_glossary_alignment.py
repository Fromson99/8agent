import json
from pathlib import Path

import pytest

from lawrag.pipeline.glossary_alignment import Matcher, documents, start, compact
from lawrag.pipeline.collect_moleg_knowledge import _publish


def package(root, labels):
    work = root / 'work'
    work.mkdir(exist_ok=True)
    (work / 'raw').mkdir(exist_ok=True)
    plan = work / 'request-plan.json'
    plan.write_text(json.dumps({'parameters': {}, 'checkpoint': {
        'completed': True, 'total_count': len(labels), 'record_count': len(labels)}}))
    records = work / 'records.jsonl'
    records.write_text('\n'.join(json.dumps({
        'entity_type': 'legal_terms', 'source_id': str(i), 'label': label,
        'fields': {}, 'definition': '',
    }, ensure_ascii=False) for i, label in enumerate(labels, 1)), encoding='utf-8')
    return _publish(root, 'legal_terms', work, plan, records)


def projection(result):
    return json.loads(Path(result['glossary']).read_text())['terms']


def test_long_terms_josa_and_substring_boundaries():
    long = '법령에 따라 등록된 전문인력으로서 등록 경력이 있는 자 또는 해당 기관에서 근무하는 자'
    matcher = Matcher([('investment', '투자'), ('trust', '투자신탁'), ('long', compact(long))])
    text = f'투자신탁은 허용한다. 투자는 가능하다. {long}에게 적용한다.'
    hits = list(matcher.find(text))
    assert [h[0] for h in hits] == ['trust', 'investment', 'long']
    assert text[hits[-1][1]:hits[-1][2]] == long


def test_definition_is_target_not_article_membership():
    text = '제2조(정의) “투자자”란 투자신탁에 가입한 자를 말한다.'
    hits = list(Matcher([('a', '투자자'), ('b', '투자신탁')]).find(text))
    assert [(h[0], h[3]) for h in hits] == [('a', True), ('b', False)]


def test_positive_and_negative_checks_are_skipped(tmp_path):
    docs = tmp_path / 'docs'
    docs.mkdir()
    (docs / 'law.txt').write_text('투자신탁은 가능하다.', encoding='utf-8')
    p = package(tmp_path, ['투자신탁', '없는용어'])
    state = tmp_path / 'state'
    first = start(state, [p], docs)
    second = start(state, [p], docs)
    assert (first['checked_pairs'], first['promoted_terms']) == (2, 1)
    assert (second['checked_pairs'], second['skipped_pairs']) == (0, 2)
    assert first['glossary'] == second['glossary']
    assert projection(second)[0]['status'] == '활성'


def test_incremental_terms_documents_and_retraction(tmp_path):
    docs = tmp_path / 'docs'
    docs.mkdir()
    first_doc = docs / 'a.txt'
    first_doc.write_text('투자신탁과 투자금은 중요하다.', encoding='utf-8')
    state = tmp_path / 'state'
    first = start(state, [package(tmp_path, ['투자신탁'])], docs)
    updated = start(state, [package(tmp_path, ['투자신탁', '투자금'])], docs)
    assert updated['checked_pairs'] == 1
    assert updated['promoted_terms'] == 2
    second_doc = docs / 'b.txt'
    second_doc.write_text('투자금은 반환한다.', encoding='utf-8')
    added = start(state, [], docs)
    assert (added['checked_pairs'], added['skipped_pairs']) == (2, 2)
    first_doc.write_text('의무를 준수한다.', encoding='utf-8')
    revised = start(state, [], docs)
    assert revised['checked_pairs'] == 2
    assert revised['promoted_terms'] == 1
    second_doc.unlink()
    removed = start(state, [], docs)
    assert removed['checked_pairs'] == 0
    assert removed['removed_documents'] == 1
    assert removed['promoted_terms'] == 0
    assert Path(first['glossary']).is_file()  # Historical generation survives.


def test_changed_and_removed_terms_retract_old_evidence(tmp_path):
    docs = tmp_path / 'docs'
    docs.mkdir()
    (docs / 'a.txt').write_text('투자신탁과 투자금은 중요하다.', encoding='utf-8')
    state = tmp_path / 'state'
    start(state, [package(tmp_path, ['투자신탁', '투자금'])], docs)
    result = start(state, [package(tmp_path, ['보증금'])], docs)
    assert result['checked_pairs'] == 1
    assert result['promoted_terms'] == 0
    assert len(projection(result)) == 1


def test_body_only_ignores_metadata_and_records_offsets(tmp_path):
    p = tmp_path / 'law.xml'
    p.write_text('<법령><기본정보><법령명>없는용어</법령명></기본정보>'
                 '<조문내용>투자자는</조문내용><항내용>보호한다.</항내용></법령>', encoding='utf-8')
    values = documents(tmp_path)
    blocks = next(iter(values.values()))[1]
    assert [text for _, text in blocks] == ['투자자는', '보호한다.']


def test_missing_document_directory_does_not_retract_state(tmp_path):
    with pytest.raises(ValueError, match='디렉터리'):
        start(tmp_path / 'state', [], tmp_path / 'missing')
