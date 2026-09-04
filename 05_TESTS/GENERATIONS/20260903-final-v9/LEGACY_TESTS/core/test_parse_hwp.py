"""HWP 파싱 경로 — 변환(hwp5/hwpx)을 거쳐 같은 Element 그릇으로 (parse_adapter.parse_hwp).

픽스처는 law_crawler 의 실제 수집 파일을 그대로 쓴다 (네트워크 없음):
- hwp/byulji2.hwp          hwp5(ole) — 표 있는 별지 서식
- lawgo/annex_byul16.hwpx  hwpx(zip) — 표 있는 별표
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core import parse_adapter                                     # noqa: E402
from lawrag.core.structure import synthpdf                                # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "law_crawler"
HWP5 = FIX / "hwp" / "byulji2.hwp"
HWPX = FIX / "lawgo" / "annex_byul16.hwpx"

pytest.importorskip("hwp5", reason="pyhwp 필요 (hwp5 변환)")


def test_hwp5_parses_with_table():
    r = parse_adapter.parse(HWP5)
    assert r.parser.startswith("hwp5(ole)")
    assert r.stats["tables"] == 1          # 표가 md 표를 거쳐 논리 셀로 살아 있다
    texts = [e.text for e in r.elements if not e.is_table]
    assert any("기업탐방 신청서" in t for t in texts)


def test_hwpx_parses_with_table():
    r = parse_adapter.parse(HWPX)
    assert r.parser.startswith("hwpx(zip)")
    assert r.stats["tables"] == 1
    table = next(e.table for e in r.elements if e.is_table)
    assert "배당주식" in table.text()


def test_extension_is_not_trusted(tmp_path):
    """확장자만 .hwp 인 다른 형식은 이름을 대고 거부된다 — 조용한 오파싱 방지."""
    fake = tmp_path / "fake.hwp"
    fake.write_bytes(b"%PDF-1.4 whatever")
    with pytest.raises(ValueError, match="실제로는 PDF"):
        parse_adapter.parse(fake)
    junk = tmp_path / "junk.hwp"
    junk.write_bytes(b"\x00\x01\x02\x03garbage")
    with pytest.raises(ValueError, match="한글 문서가 아닙니다"):
        parse_adapter.parse(junk)


def test_legacy_doc_rejected_with_remedy(tmp_path):
    """.doc 은 hwp5 와 같은 OLE 라 확장자로 먼저 갈라야 정확한 처방이 나간다."""
    doc = tmp_path / "old.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 16)
    with pytest.raises(ValueError, match="docx"):
        parse_adapter.parse(doc)


def test_probe_text_is_cheap_and_readable():
    """전체 변환 없이 앞부분 텍스트만 — 구조 없이 글만, hwpx 도 같은 통로."""
    assert "기업탐방" in parse_adapter.hwp_probe_text(HWP5)
    assert "배당주식" in parse_adapter.hwp_probe_text(HWPX)


def test_paginate_plants_coordinates():
    """합성 지면 — page·bbox(TOPLEFT) 가 요소에 심겨야 재해석 오버레이가 성립한다."""
    r = parse_adapter.parse(HWP5)
    pdf = synthpdf.paginate(r.elements)
    assert pdf.startswith(b"%PDF")
    assert all(e.bbox and e.bbox_origin == "TOPLEFT" for e in r.elements)
    assert all(e.page >= 1 for e in r.elements)
    # 심긴 좌표는 dump/restore 를 살아남는다 — parse.json 캐시 경유 재해석의 전제
    back = parse_adapter.result_from_dump(parse_adapter.result_to_dump(r))
    assert [e.bbox for e in back.elements] == [e.bbox for e in r.elements]
