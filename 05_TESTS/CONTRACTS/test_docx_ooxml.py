"""DOCX 원본 선언(자동 번호·들여쓰기·원문 순서)이 구조화까지 가는가. 합성 내규, 모델 호출 없음."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import docx_synth as S
from lawrag.core import docx_ooxml as D


@pytest.mark.parametrize('n,f,expected', [
    (1, 'decimalEnclosedCircle', '①'), (21, 'decimalEnclosedCircle', '㉑'), (3, 'ganada', '다'),
    (2, 'chosung', 'ㄴ'), (14, 'upperRoman', 'XIV'), (12, 'koreanCounting', '십이'),
    (21, 'koreanLegal', '스물하나'), (27, 'lowerLetter', 'aa'), (5, 'none', ''), (7, 'unknownFmt', '7'),
])
def test_number_formats(n, f, expected):
    assert D.fmt(n, f) == expected


def test_labels_restart_per_article_and_indent_is_read(tmp_path):
    path = tmp_path / 'r.docx'
    S.build(path, 'auto_restart', with_parts=False)
    rows = [r for r in D.read(path) if not r.get('table') and r['text'].strip()]
    labels = [r['label'] for r in rows if r['label']]
    # 제3조: ①② 1. 2. ③ — 새 목록 인스턴스(startOverride)마다 ①부터
    assert labels[:9] == ['1.', '2.', '가.', '나.', '①', '②', '1.', '2.', '③']
    circled = next(r for r in rows if r['label'] == '①')
    assert circled['ilvl'] == 0 and circled['start_twips'] == 0.0 and circled['left_twips'] == 400.0


def test_docling_reorder_is_undone(tmp_path):
    from lawrag.core.parse_adapter import parse_docx
    path = tmp_path / 'r.docx'
    S.build(path, 'auto_restart', with_parts=False)
    parsed = parse_docx(path)
    texts = [e.text for e in parsed.elements]
    assert texts.index('가. 거래상대방별 한도') < texts.index('나. 상품별 한도')
    assert parsed.stats['docx_matched'] == parsed.stats['docx_paragraphs']
    assert [e.index for e in parsed.elements] == list(range(len(parsed.elements)))


@pytest.mark.parametrize('variant', [v for v in S.VARIANTS if v != 'typed_flat'])
@pytest.mark.parametrize('with_parts', [False, True])
def test_structure_matches_truth(tmp_path, variant, with_parts):
    from lawrag.core.ingest import ingest
    from lawrag.core.internal_rules import PROFILE
    from lawrag.pipeline.genos_e2e import paths
    path = tmp_path / f'{variant}.docx'
    truth = S.build(path, variant, with_parts)
    with paths(tmp_path / 'data'):
        r = ingest(path.read_bytes(), path.name, store=tmp_path / 'data/structure', name=variant,
                   use_llm=False, hints=PROFILE)
    result = json.loads((tmp_path / 'data/structure' / r['doc_id'] / 'result.json').read_text())
    assert S.paths(result['nodes']) == S.paths(truth)


def test_typed_markers_without_indentation_stay_as_before(tmp_path):
    # 원문에 층을 가를 신호가 없는 문서: 조·항·호 는 맞고, 여기서 무언가를 꾸며내지 않는다.
    path = tmp_path / 't.docx'
    S.build(path, 'typed_flat', with_parts=False)
    rows = D.read(path)
    assert not any(r.get('label') for r in rows if not r.get('table'))
    assert all(r.get('start_twips') is None for r in rows if not r.get('table'))
