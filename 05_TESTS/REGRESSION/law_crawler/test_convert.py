"""lawrag/core/hwp5_md.py — 변환 로직은 합성 XML/XHTML 로, 끝단은 실제 HWP 픽스처로 본다.

기본 엔진은 레코드 XML 직독(xml_to_markdown); 옛 XSLT 경로(xhtml_to_markdown)는
--engine html 로만 쓰이지만 출력 규약이 같아야 하므로 둘 다 본다.
"""
from __future__ import annotations

import json
from pathlib import Path

from lawrag.core import hwp5_md as convert

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "law_crawler" / "hwp"
NS = "http://www.w3.org/1999/xhtml"


def _xhtml(body_inner: str) -> bytes:
    return (f'<html xmlns="{NS}"><head><title></title></head>'
            f'<body><div>{body_inner}</div></body></html>').encode("utf-8")


# ---------------------------------------------------------------- 문단

def test_paragraphs_become_blocks_and_cr_becomes_newline():
    md, stats = convert.xhtml_to_markdown(_xhtml(
        "<p><span>제1조</span><span>&#13;목적</span></p><p></p><p>제2조</p>"))
    assert md == "제1조\n목적\n\n제2조\n"
    assert stats == {"tables": 0, "images": 0}


def test_images_are_dropped_but_counted():
    md, stats = convert.xhtml_to_markdown(_xhtml(
        '<p>본문<img src="bindata/x.png"/></p>'))
    assert "img" not in md and "png" not in md
    assert md.strip() == "본문"
    assert stats["images"] == 1


# ---------------------------------------------------------------- 표

def test_grid_table_becomes_markdown_table():
    md, stats = convert.xhtml_to_markdown(_xhtml(
        "<p><span><table>"
        "<tr><td><p>구분</p></td><td><p>내용</p></td></tr>"
        "<tr><td><p>가|나</p></td><td><p>다</p></td></tr>"
        "</table></span></p>"))
    assert "| 구분 | 내용 |" in md
    assert "| --- | --- |" in md
    assert "| 가\\|나 | 다 |" in md          # 파이프는 셀 안에서 이스케이프
    assert stats["tables"] == 1


def test_wrapper_1x1_table_is_unwrapped_without_duplication():
    # HWP 서식의 "테두리 박스": 문서 전체가 1×1 표 안에 있고 그 안에 진짜 표가 중첩된다.
    inner = ("<table><tr><td><p>a</p></td><td><p>b</p></td></tr>"
             "<tr><td><p>c</p></td><td><p>d</p></td></tr></table>")
    md, stats = convert.xhtml_to_markdown(_xhtml(
        f"<p><span><table><tr><td><p>머리글</p><p><span>{inner}</span></p>"
        f"</td></tr></table></span></p>"))
    assert md.count("머리글") == 1            # 바깥 셀 텍스트로 또 들어가면 두 벌이 된다
    assert md.count("| a | b |") == 1
    assert stats["tables"] == 1               # 래퍼는 표로 세지 않는다


def test_nested_table_in_multicell_grid_is_flattened_once():
    inner = "<table><tr><td><p>x</p></td><td><p>y</p></td></tr></table>"
    md, _ = convert.xhtml_to_markdown(_xhtml(
        f"<p><span><table>"
        f"<tr><td><p>왼쪽</p><span>{inner}</span></td><td><p>오른쪽</p></td></tr>"
        f"<tr><td><p>아래1</p></td><td><p>아래2</p></td></tr>"
        f"</table></span></p>"))
    assert md.count("x") == 1 and md.count("y") == 1
    assert "왼쪽 x y" in md                   # 중첩 표는 셀 텍스트로 펴진다


def test_empty_decorative_table_is_dropped():
    md, _ = convert.xhtml_to_markdown(_xhtml(
        "<p><span><table><tr><td><p></p></td><td><p></p></td></tr></table></span></p>"
        "<p>본문</p>"))
    assert md.strip() == "본문"


# ---------------------------------------------------------------- 출처 표기

def test_manifest_index_maps_body_and_attachments(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "collected_at": "2026-08-07 16:51:54",
        "items": [{
            "name": "규정A", "enforce": "2026-01-01", "revised": "2025-12-01",
            "body_file": "01_DATA/INBOX/AUTHORING/corpus/kofia/규정A/전문.hwp", "body_sha256": "b" * 64,
            "attachments": [
                {"title": "별표1", "role": "attachment", "url": "https://x/1",
                 "file": "01_DATA/INBOX/AUTHORING/corpus/kofia/규정A/별표서식/별표1.hwp", "sha256": "a" * 64},
                {"title": "실패한 첨부", "role": "attachment", "file": None},
            ],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    index = convert.manifest_index([tmp_path])
    body = index[(convert.REPO_ROOT / "01_DATA/INBOX/AUTHORING/corpus/kofia/규정A/전문.hwp").resolve()]
    assert body["role"] == "body" and body["regulation"] == "규정A"
    assert body["collected"] == "2026-08-07" and body["enforced"] == "2026-01-01"
    att = index[(convert.REPO_ROOT / "01_DATA/INBOX/AUTHORING/corpus/kofia/규정A/별표서식/별표1.hwp").resolve()]
    assert att["title"] == "별표1" and att["source"] == "https://x/1"
    assert len(index) == 2                    # file 없는 첨부(다운로드 실패)는 건너뛴다


def test_provenance_header_is_comment_block():
    header = convert.provenance_header(Path("x.hwp"), {
        "title": "별표1", "regulation": "규정A", "role": "attachment",
        "source": "https://x/1", "collected": "2026-08-07", "sha256": "a" * 64})
    lines = header.strip().splitlines()
    assert all(ln.startswith("# ") for ln in lines)
    assert lines[0] == "# title: 별표1"
    assert lines[-1].startswith("# converted: hwp5(ole)")
    assert header.endswith("\n\n")            # 본문과 빈 줄로 나뉜다


# ---------------------------------------------------------------- 끝단 (실제 HWP)

def test_convert_file_end_to_end(tmp_path):
    src = tmp_path / "byulji2.hwp"
    src.write_bytes((FIXTURES / "byulji2.hwp").read_bytes())

    row = convert.convert_file(src, None, force=False)
    assert row["status"] == convert.OK
    assert row["tables"] >= 1
    out = tmp_path / "byulji2.hwp.md"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# title: byulji2\n")
    assert "기업탐방 신청서" in text
    assert "| 구분 | 내용 |" in text          # hwp5txt 였다면 통째로 사라졌을 내용

    assert "md(xml)" in text.splitlines()[1]    # converted 줄이 엔진을 말한다

    # 멱등 — 사이드카가 더 새것이면 건너뛴다
    assert convert.convert_file(src, None, force=False)["status"] == convert.SKIP
    assert convert.convert_file(src, None, force=True)["status"] == convert.OK


def test_html_engine_still_works_and_agrees_on_content(tmp_path):
    src = tmp_path / "byulji2.hwp"
    src.write_bytes((FIXTURES / "byulji2.hwp").read_bytes())
    row = convert.convert_file(src, None, force=True, engine="html")
    assert row["status"] == convert.OK and row["mode"] == "html"
    html_text = (tmp_path / "byulji2.hwp.md").read_text(encoding="utf-8")
    assert "md(html)" in html_text.splitlines()[1]
    row = convert.convert_file(src, None, force=True)          # 기본(xml)
    xml_text = (tmp_path / "byulji2.hwp.md").read_text(encoding="utf-8")
    # 두 엔진이 같은 글을 본다 — 표 행이 같은 칸으로 떨어진다
    assert "| 구분 | 내용 |" in html_text and "| 구분 | 내용 |" in xml_text
    assert "기업탐방 신청서" in xml_text


def test_engine_timeout_falls_back_to_text(tmp_path, monkeypatch):
    # fork 컨텍스트라 monkeypatch 가 자식에도 산다 — 기본 엔진만 병적으로 느린 상황.
    import time as _time

    def stuck(path):
        _time.sleep(30)

    monkeypatch.setattr(convert, "hwp5_to_xml", stuck)
    src = tmp_path / "byulji2.hwp"
    src.write_bytes((FIXTURES / "byulji2.hwp").read_bytes())

    row = convert.convert_file(src, None, force=True, timeout=2.0)
    assert row["status"] == convert.OK
    assert row["mode"] == "text"
    text = (tmp_path / "byulji2.hwp.md").read_text(encoding="utf-8")
    assert "text 폴백" in text.splitlines()[1]     # converted 줄에 손실이 기록된다
    assert "기업탐방 신청서" in text
    assert "| 구분" not in text                    # 표는 잃는다 — 그게 폴백의 값이다


def test_both_paths_timing_out_is_fail(tmp_path, monkeypatch):
    import time as _time

    def stuck(path):
        _time.sleep(30)

    monkeypatch.setattr(convert, "hwp5_to_xml", stuck)
    monkeypatch.setattr(convert, "hwp5_to_text", stuck)
    src = tmp_path / "byulji2.hwp"
    src.write_bytes((FIXTURES / "byulji2.hwp").read_bytes())

    row = convert.convert_file(src, None, force=True, timeout=1.0)
    assert row["status"] == convert.FAIL
    assert "초를 넘겼습니다" in row["error"]
    assert not (tmp_path / "byulji2.hwp.md").exists()


def test_convert_file_rejects_non_hwp5_magic(tmp_path):
    fake = tmp_path / "fake.hwp"
    fake.write_bytes(b"PK\x03\x04 not a real hwp")
    row = convert.convert_file(fake, None, force=False)
    assert row["status"] == convert.FORMAT
    assert row["format"] == "hwpx(zip)"
    assert not (tmp_path / "fake.hwp.md").exists()


# ---------------------------------------------------------------- 레코드 XML 엔진 (기본)

def _para(*inner: str) -> str:
    """Paragraph > LineSeg > (Text|ControlChar|컨트롤)…  — 문단 끝 PARAGRAPH_BREAK 포함."""
    return ("<Paragraph><LineSeg>" + "".join(inner)
            + '<ControlChar name="PARAGRAPH_BREAK" char="&#13;"/></LineSeg></Paragraph>')


def _t(s: str) -> str:
    return f"<Text>{s}</Text>"


def _cell(row: int, col: int, text: str, rowspan: int = 1, colspan: int = 1) -> str:
    return (f'<TableCell row="{row}" col="{col}" rowspan="{rowspan}" colspan="{colspan}">'
            f"{_para(_t(text)) if text else _para()}</TableCell>")


def _table(rows: int, cols: int, *trs: str) -> str:
    return (f'<TableControl><TableBody rows="{rows}" cols="{cols}">'
            + "".join(f"<TableRow>{tr}</TableRow>" for tr in trs)
            + "</TableBody></TableControl>")


def _doc(*paras: str) -> bytes:
    return ("<HwpDoc><DocInfo/><BodyText><SectionDef><ColumnSet>"
            + "".join(paras) + "</ColumnSet></SectionDef></BodyText></HwpDoc>").encode("utf-8")


def test_xml_paragraphs_linebreak_tab_and_softwrap():
    md, stats = convert.xml_to_markdown(_doc(
        _para(_t("제1조"), '<ControlChar name="LINE_BREAK" char="&#10;"/>', _t("목적")),
        # 소프트 랩 — LineSeg 둘은 한 문단이다. 줄을 끊지 않는다.
        "<Paragraph><LineSeg>" + _t("이어지는 ") + "</LineSeg><LineSeg>" + _t("문장")
        + '<ControlChar name="PARAGRAPH_BREAK" char="&#13;"/></LineSeg></Paragraph>',
        _para(_t("가"), '<ControlChar name="TAB" char="&#9;"/>', _t("나")),
    ))
    assert md == "제1조\n목적\n\n이어지는 문장\n\n가\t나\n"
    assert stats == {"tables": 0, "images": 0, "footnotes": 0}


def test_xml_merged_cells_keep_grid_alignment():
    # 2×3 — 첫 행은 (0,0)이 두 칸 병합, 둘째 행은 세 칸. html 엔진이 못 하던 정렬이다.
    md, stats = convert.xml_to_markdown(_doc(_para(_table(
        2, 3,
        _cell(0, 0, "구분", colspan=2) + _cell(0, 2, "비고"),
        _cell(1, 0, "가") + _cell(1, 1, "나") + _cell(1, 2, "다|라"),
    ))))
    lines = md.strip().splitlines()
    assert lines[0] == "| 구분 |  | 비고 |"            # 덮인 칸은 빈 칸으로 남는다
    assert lines[1] == "| --- | --- | --- |"
    assert lines[2] == "| 가 | 나 | 다\\|라 |"
    assert stats["tables"] == 1


def test_xml_wrapper_1x1_table_is_unwrapped_without_duplication():
    inner = _table(1, 2, _cell(0, 0, "a") + _cell(0, 1, "b"))
    wrapper = ('<TableControl><TableBody rows="1" cols="1"><TableRow>'
               '<TableCell row="0" col="0" rowspan="1" colspan="1">'
               + _para(_t("머리글")) + _para(inner)
               + "</TableCell></TableRow></TableBody></TableControl>")
    md, stats = convert.xml_to_markdown(_doc(_para(wrapper)))
    assert md.count("머리글") == 1
    assert md.count("| a | b |") == 1
    assert stats["tables"] == 1                 # 래퍼는 표로 세지 않는다


def test_xml_nested_table_in_cell_is_flattened_once():
    inner = _table(1, 2, _cell(0, 0, "x") + _cell(0, 1, "y"))
    md, _ = convert.xml_to_markdown(_doc(_para(_table(
        2, 2,
        ('<TableCell row="0" col="0" rowspan="1" colspan="1">' + _para(_t("왼쪽"))
         + _para(inner) + "</TableCell>") + _cell(0, 1, "오른쪽"),
        _cell(1, 0, "아래1") + _cell(1, 1, "아래2"),
    ))))
    assert md.count("x") == 1 and md.count("y") == 1
    assert "| 왼쪽 x y | 오른쪽 |" in md


def test_xml_textbox_emits_blocks_and_pictures_are_counted():
    gso = ('<GShapeObjectControl><ShapeComponent chid="$rec"><TextboxParagraphList>'
           + _para(_t("제1장｜총칙")) + "</TextboxParagraphList></ShapeComponent>"
           '</GShapeObjectControl>')
    pic = ('<GShapeObjectControl><ShapeComponent chid="$pic"><ShapePicture/>'
           "</ShapeComponent></GShapeObjectControl>")
    md, stats = convert.xml_to_markdown(_doc(_para(gso), _para(_t("본문"), pic)))
    assert md == "제1장｜총칙\n\n본문\n"
    assert stats["images"] == 1


def test_xml_footnote_becomes_quote_block_after_paragraph():
    fn = ("<FootNote><ListHeader>" + _para('<AutoNumbering kind="footnote"/>',
                                            _t(" 각주 내용")) + "</ListHeader></FootNote>")
    md, stats = convert.xml_to_markdown(_doc(_para(_t("본문"), fn, _t(" 계속"))))
    assert md == "본문 계속\n\n> 각주 내용\n"
    assert stats["footnotes"] == 1


def test_xml_header_footer_are_dropped_and_fields_keep_text():
    hdr = ("<Header><HeaderParagraphList>" + _para(_t("쪽머리"))
           + "</HeaderParagraphList></Header>")
    link = '<FieldHyperLink chid="%hlk">' + _t("www.x.kr") + "</FieldHyperLink>"
    md, _ = convert.xml_to_markdown(_doc(_para(hdr, _t("홈페이지 "), link)))
    assert md == "홈페이지 www.x.kr\n"


def test_xml_empty_decorative_table_is_dropped():
    md, _ = convert.xml_to_markdown(_doc(
        _para(_table(1, 2, _cell(0, 0, "") + _cell(0, 1, ""))), _para(_t("본문"))))
    assert md.strip() == "본문"
