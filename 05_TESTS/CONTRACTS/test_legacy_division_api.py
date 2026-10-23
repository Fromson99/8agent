"""The real request/scope/READ consumer must cross a legacy repeated chapter."""
import json
import sqlite3

from lawrag.core.legal_coordinate import LegalCoordinate, find_coordinates
from lawrag.pipeline.term_generation import build_generation
from test_document_release import source


def test_legacy_division_scope_reads_original_and_preserves_duplicate_request(tmp_path,term_glossary):
    from test_model_structure_selection import test_real_api_model_scope_excludes_article_and_reuses_request as exercise
    raw=source(tmp_path/'raw.sqlite', [('d','모의승인규정',[
        '원칙상 이사회 승인을 받아야 한다. 다만 제2조의 예외를 확인한다.',
        '적법하게 위임된 경우에는 별도 이사회 승인을 받지 않는다.']),
        ('other','다른문서',['이번 요청 범위 밖이다.'])])
    with sqlite3.connect(raw) as db:
        rows=db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall()
        for did,uid,text in rows:
            unit=json.loads(text);c=find_coordinates(unit['surface'])[0].coordinate
            unit.update(legal_coordinate=c.as_dict(),coordinate_scope='body',coordinate_key='body:'+c.canonical_surface())
            db.execute('UPDATE source_unit SET parent_id=?,json=? WHERE document_id=? AND unit_id=?',
                ('chapter' if did=='d' else None,json.dumps(unit,ensure_ascii=False),did,uid))
        c=LegalCoordinate('장',1)
        db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d','chapter',None,json.dumps({
            'family':'kr_장','surface':'제1장','title':'승인','span':[0,2],
            'legal_coordinate':c.as_dict(),'coordinate_scope':'repeated',
            'coordinate_key':'repeated:제1장:chapter'},ensure_ascii=False)))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    exercise(tmp_path,tmp_path/'built/generation')
