"""수집된 HWP5 원문 → 라우터가 받는 md — 수집과 분리된 변환 단계.

    python -m lawrag.pipeline.convert 01_DATA/INBOX/AUTHORING/corpus/kofia                 # 디렉터리 아래 모든 .hwp → 사이드카 .md
    python -m lawrag.pipeline.convert 01_DATA/INBOX/AUTHORING/corpus/kofia --force         # 산출물이 더 새것이어도 재변환
    python -m lawrag.pipeline.convert path/to/file.hwp             # 한 파일만
    python -m lawrag.pipeline.convert 01_DATA/INBOX/AUTHORING/corpus/kofia --report var/logs/convert.kofia.json

수집기(lawrag/pipeline/collect.py)는 원문을 보존만 하고 변환하지 않는다(Task_law_crawler §8-4).
이 스크립트가 그 "별도 파이프라인" 이다.

동작 계약:
- 원본 무변경. 산출물은 원본 옆의 `X.hwp.md` 사이드카다.
- 멱등: 사이드카가 존재하고 원본보다 새로우면 skip (--force 로 무시).
- 부분 실패 허용: 파일 하나의 실패는 기록하고 계속한다. 실패가 있으면 종료코드 1.
- 표 보존: hwp5txt 는 표 내용을 `<표>` 로 버린다 — 별표서식은 내용이 통째로
  사라진다. 그래서 레코드 모델을 읽어 표를 markdown 표로 굳힌다. 이 스크립트의 존재 이유다.
- 엔진 둘, 기본은 xml 직독: pyhwp 의 레코드 XML(`hwp5proc xml` 과 같은 모델)을
  메모리에서 받아 Paragraph/TableCell 을 직접 걷는다 — XSLT 가 없어 빠르고
  (실측: XSLT 로 120초를 두 번 넘긴 서식 파일이 5초), `TableCell(col,row,colspan,
  rowspan)` 이 그대로 있어 병합 셀 정렬을 보존한다. 옛 XSLT(html) 경로는
  `--engine html` 로 남겨 둔다 — 출력 대조용이지 기본이 아니다.
- 시간 초과 → 텍스트 폴백: 변환은 파일마다 자식 프로세스에서 돌리고, --timeout 을
  넘기면 죽인 뒤 같은 시한으로 텍스트 경로(hwp5txt 와 동일)로 다시 뽑는다. 표는
  잃지만 전문은 확보된다 — report 에 mode=text 로 남는 것이 그 손실의 기록이다.
  (xml 엔진으로 바꾼 뒤 실측 폴백은 없다 — 남겨 둔 이유는 손상 파일 방어다.)
- 확장자를 믿지 않는다: 매직바이트로 hwp5(ole) 만 변환한다. `.hwp` 로 내려받은
  hwpx·pdf 는 FORMAT 으로 보고만 하고 건드리지 않는다 (§8-5 와 같은 원칙).
- 출처 표기: 코퍼스 manifest.json 에서 찾은 출처를 첫머리 `# key: value` 주석으로
  남긴다 — corpus_build 가 읽고 strip_provenance_header 가 본문에서 떼는 규약.
  doc_id 와 verification 은 넣지 않는다. 그것은 큐레이션의 결정이지 변환기의
  결정이 아니다 (없으면 corpus_build 가 거부한다 — 그 거부가 게이트다).

레코드 XML 실측 (from_samsung 서식 9건 + 코퍼스 표본 692건):
- 본문 흐름: HwpDoc > BodyText > SectionDef > ColumnSet > Paragraph. 문단은
  LineSeg(시각 줄, 소프트 랩이라 이어 붙인다) > Text | ControlChar | 컨트롤.
- ControlChar: PARAGRAPH_BREAK(무시) · LINE_BREAK(\n) · TAB(\t) · FIXWIDTH_SPACE(버림, html 과 동일).
- TableControl > TableBody(rows,cols) > TableRow > TableCell(col,row,colspan,rowspan)
  > Paragraph… — 병합 셀은 앵커 칸에만 내용, 덮인 칸은 빈 칸(hwpx_md 와 같은 규약).
- GShapeObjectControl: ShapeComponent($rec) 의 TextboxParagraphList 는 글상자 —
  제자리에 블록으로 낸다. ShapeComponent($pic)/ShapePicture 는 그림 — 개수만 센다.
- FootNote/EndNote > ListHeader > Paragraph: 각주 — 문단 뒤에 `> ` 블록으로 낸다
  (parse_adapter._markdown_elements 가 `>` 줄을 footnote 로 읽는다).
- Header/Footer(ParagraphList): 쪽 머리·꼬리 — 버린다. (표준정관의 "제1장｜총칙" 옆탭
  글상자가 여기 산다 — html 엔진은 쪽마다 3번씩 중복해 냈고, 본문에 진짜 장 제목이
  따로 있으므로 버리는 게 맞다.)
- Field*(하이퍼링크·상호참조)·Control(수식) 안의 Text 는 본문 글이다 — 그대로 잇는다.

한계(알고 두기):
- html 엔진은 셀 병합을 펴지 않는다 — 병합 셀 뒤 칸이 왼쪽으로 당겨진다.
  (xml 엔진은 보존한다.)
- 그림은 버리고 개수만 센다. 본문에 자리표시자를 남기면 구조화 잔여로 잡힌다.
  (텍스트 폴백은 hwp5txt 그대로 `<그림>`·`<표>` 자리표시자가 남는다.)
- 수식(EqEdit)은 본문 글이 아니라 버려진다.
"""
from __future__ import annotations

import argparse
import io
import json
import multiprocessing
import re
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from lawrag.platform.paths import persisted_data_path, repository_root
from lawrag.sources.common import detect_format

REPO_ROOT = repository_root()
DEFAULT_TIMEOUT = 120.0    # 초 — 정상 문서는 수 초, 이걸 넘기면 XSLT 병증이다

# 상태 어휘 — report 와 요약이 같은 말을 쓴다
OK = "OK"          # 변환 완료 (row["mode"] 가 html/text 를 가른다)
SKIP = "SKIP"      # 사이드카가 원본보다 새것 — 멱등 skip
FORMAT = "FORMAT"  # .hwp 탈을 쓴 다른 형식 — 변환하지 않고 보고
FAIL = "FAIL"      # 열기·변환 실패 (암호화, 양쪽 경로 모두 시간 초과 등)

_XHTML_NS = "{http://www.w3.org/1999/xhtml}"

# fork 면 부모가 읽어 둔 모듈을 그대로 물려받아 자식 기동이 싸다. 없으면 기본값.
_MP = multiprocessing.get_context(
    "fork" if "fork" in multiprocessing.get_all_start_methods() else None)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ===========================================================================
# HWP5 → XHTML / 텍스트 — pyhwp 의 XSLT 경로를 파일 없이 메모리로 받는다
# ===========================================================================

def hwp5_to_xhtml(path: Path) -> bytes:
    from hwp5.hwp5html import HTMLTransform
    from hwp5.xmlmodel import Hwp5File

    buf = io.BytesIO()
    with closing(Hwp5File(str(path))) as hwp5file:
        HTMLTransform().transform_hwp5_to_xhtml(hwp5file, buf)
    return buf.getvalue()


def hwp5_to_text(path: Path) -> str:
    from hwp5.hwp5txt import TextTransform
    from hwp5.xmlmodel import Hwp5File

    buf = io.BytesIO()
    with closing(Hwp5File(str(path))) as hwp5file:
        TextTransform().transform_hwp5_to_text(hwp5file, buf)
    return buf.getvalue().decode("utf-8")


def hwp5_to_xml(path: Path) -> bytes:
    """레코드 모델 XML — `hwp5proc xml` 이 찍는 것과 같은 문서를 메모리로.

    xmllint 를 거치지 않는다(없는 환경이 많고, 있어도 c14n 만 할 뿐이다).
    embedbin=False — 그림 바이트는 싣지 않는다(어차피 버린다).
    """
    import logging
    from hwp5.xmlmodel import Hwp5File

    # pyhwp 가 모르는 enum 값(UnderlineStyle 15 등)을 만나면 WARNING 을 줄줄 찍는다 —
    # 변환에는 영향이 없는 소음이라 자식 프로세스 안에서만 낮춘다.
    logging.getLogger("hwp5").setLevel(logging.ERROR)
    buf = io.BytesIO()
    with closing(Hwp5File(str(path))) as hwp5file:
        for chunk in hwp5file.xmlevents(embedbin=False).bytechunks():
            buf.write(chunk)
    return buf.getvalue()


# ===========================================================================
# 레코드 XML → markdown — 기본 엔진. 문단은 줄로, 표는 병합 정렬을 지킨 markdown 표로
# ===========================================================================

# LineSeg 아래 컨트롤 처리 규칙 — 모듈 머리의 실측 표와 한 몸이다.
# html XSLT 와 같은 규약: ControlChar 는 @char 만 글이다 — FIXWIDTH_SPACE(고정폭 빈칸,
# char 없음)는 정렬용이라 버린다("1984. 7.13." 이 아니라 "1984.7.13."). 문단 끝
# PARAGRAPH_BREAK 는 블록 경계가 대신한다.
_CTRL_CHAR_MAP = {"LINE_BREAK": "\n", "TAB": "\t", "FIXWIDTH_SPACE": "",
                  "PARAGRAPH_BREAK": ""}
_SKIP_CONTROLS = frozenset({"Header", "Footer", "AutoNumbering", "NewNumbering",
                            "PageHide", "PageNumberPosition", "ColumnsDef",
                            "BookmarkControl", "TCPSControl", "PageDef",
                            "PageBorderFill", "FootnoteShape"})
_NOTE_CONTROLS = frozenset({"FootNote", "EndNote"})


def xml_to_markdown(xml: bytes) -> tuple[str, dict]:
    """반환: (markdown, {"tables": n, "images": n, "footnotes": n}).

    xhtml_to_markdown 과 같은 출력 규약 — 블록은 빈 줄로, 표는 파이프 표,
    첫 행 뒤 구분선. 차이는 병합 셀 정렬 보존뿐이다.
    """
    root = ET.fromstring(xml)
    body = root.find("BodyText")
    if body is None:
        raise ValueError("레코드 XML 에 BodyText 가 없습니다")
    stats = {"tables": 0, "images": 0, "footnotes": 0}
    blocks: list[str] = []
    _xml_blocks(body, blocks, stats)
    md = "\n\n".join(blocks)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md, stats


def _flow_paragraphs(container: ET.Element):
    """흐름 문단 — 컨테이너 아래 Paragraph 를 문서 순서로, 문단 안으로는 안 들어간다.

    (셀·글상자·각주 속 문단은 그 문단을 처리하는 쪽이 따로 걷는다.)
    """
    for child in container:
        if child.tag == "Paragraph":
            yield child
        else:
            yield from _flow_paragraphs(child)


def _xml_blocks(container: ET.Element, blocks: list[str], stats: dict) -> None:
    for para in _flow_paragraphs(container):
        _xml_blocks_from_paragraph(para, blocks, stats)


def _xml_blocks_from_paragraph(para: ET.Element, blocks: list[str], stats: dict) -> None:
    """문단 하나 → 글 블록(+ 제자리 표·글상자 블록, 뒤따르는 각주 블록)."""
    buf: list[str] = []
    notes: list[str] = []

    def flush() -> None:
        text = _norm_para("".join(buf))
        buf.clear()
        if text:
            blocks.append(text)

    def walk(e: ET.Element) -> None:
        for c in e:
            tag = c.tag
            if tag == "Text":
                buf.append(c.text or "")
            elif tag == "ControlChar":
                name = c.get("name", "")
                buf.append(_CTRL_CHAR_MAP.get(name, c.get("char") or ""))
            elif tag == "TableControl":
                flush()
                md = _xml_table_md(c, stats)
                if md:
                    blocks.append(md)
            elif tag == "GShapeObjectControl":
                stats["images"] += sum(1 for _ in c.iter("ShapePicture"))
                boxes = list(c.iter("TextboxParagraphList"))
                if boxes:
                    flush()
                    for box in boxes:
                        _xml_blocks(box, blocks, stats)
            elif tag in _NOTE_CONTROLS:
                for p in _flow_paragraphs(c):
                    text = _xml_inline_text(p, stats)
                    if text:
                        notes.append(text)
                        stats["footnotes"] += 1
            elif tag in _SKIP_CONTROLS:
                continue
            else:                               # LineSeg·Field*·Control 등 — 안의 글은 본문이다
                walk(c)

    walk(para)
    flush()
    for n in notes:
        blocks.append("> " + n)


def _xml_inline_text(para: ET.Element, stats: dict) -> str:
    """문단을 한 줄 글로 — 셀·각주용. 안의 표는 행을 ' / ' 로 이어 평문화한다."""
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        for c in e:
            tag = c.tag
            if tag == "Text":
                parts.append(c.text or "")
            elif tag == "ControlChar":
                parts.append(_CTRL_CHAR_MAP.get(c.get("name", ""), c.get("char") or ""))
            elif tag == "TableControl":
                rows = _xml_table_grid(c, stats)
                flat = [" ".join(filter(None, r)) for r in rows]
                parts.append(" " + " / ".join(filter(None, flat)) + " ")
            elif tag == "GShapeObjectControl":
                stats["images"] += sum(1 for _ in c.iter("ShapePicture"))
                for box in c.iter("TextboxParagraphList"):
                    for p in _flow_paragraphs(box):
                        parts.append(" " + _xml_inline_text(p, stats) + " ")
            elif tag in _NOTE_CONTROLS or tag in _SKIP_CONTROLS:
                continue
            else:
                walk(c)

    walk(para)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _xml_cell_text(cell: ET.Element, stats: dict) -> str:
    """셀 텍스트 — 문단 경계는 공백 하나(markdown 셀은 한 줄이다), 파이프는 이스케이프."""
    texts = [_xml_inline_text(p, stats) for p in _flow_paragraphs(cell)]
    return " ".join(t for t in texts if t).replace("|", "\\|")


def _xml_table_grid(table: ET.Element, stats: dict) -> list[list[str]]:
    """TableControl → 행렬. 병합 셀은 앵커 칸(row,col)에만 내용, 덮인 칸은 빈 칸."""
    body = table.find("TableBody")
    if body is None:
        return []
    n_rows = int(body.get("rows", 0) or 0)
    n_cols = int(body.get("cols", 0) or 0)
    cells: list[tuple[int, int, ET.Element]] = []
    # 직계만 — iter() 로 내려가면 셀 속 중첩 표의 칸이 바깥 격자를 덮어쓴다
    for tr in body.findall("TableRow"):
        for tc in tr.findall("TableCell"):
            r, c = int(tc.get("row", 0)), int(tc.get("col", 0))
            rs, cs = int(tc.get("rowspan", 1) or 1), int(tc.get("colspan", 1) or 1)
            cells.append((r, c, tc))
            n_rows, n_cols = max(n_rows, r + rs), max(n_cols, c + cs)
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for r, c, tc in cells:
        grid[r][c] = _xml_cell_text(tc, stats)
    return grid


def _xml_table_md(table: ET.Element, stats: dict) -> str:
    body = table.find("TableBody")
    if body is None:
        return ""
    # HWP 서식은 내용 전체를 1×1 "테두리 박스" 표로 감싸는 일이 많다(xhtml 경로와
    # 같은 처리). 그대로 표로 굳히면 문서 전체가 셀 하나가 된다 — 풀어서 안쪽을
    # 다시 블록으로 처리한다(여러 겹이면 재귀로 다 풀린다).
    cells = [tc for tr in body.findall("TableRow") for tc in tr.findall("TableCell")]
    if len(cells) == 1:
        blocks: list[str] = []
        _xml_blocks(cells[0], blocks, stats)
        return "\n\n".join(blocks)

    rows = _xml_table_grid(table, stats)
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""                                  # 내용 없는 장식 표
    stats["tables"] += 1
    width = max(len(r) for r in rows)
    lines = []
    for i, r in enumerate(rows):
        r = r + [""] * (width - len(r))
        lines.append("| " + " | ".join(r) + " |")
        if i == 0:
            lines.append("|" + " --- |" * width)
    return "\n".join(lines)


# ===========================================================================
# XHTML → markdown — 문단은 줄로, 표는 markdown 표로
# ===========================================================================

def xhtml_to_markdown(xhtml: bytes) -> tuple[str, dict]:
    """반환: (markdown, {"tables": n, "images": n}).

    구조화 파이프라인은 줄 단위로 본다 — 문단 안 줄바꿈(CR)을 살리고,
    빈 문단은 블록 구분으로만 쓴다.
    """
    root = ET.fromstring(xhtml)
    body = root.find(f"{_XHTML_NS}body")
    if body is None:
        raise ValueError("XHTML 에 body 가 없습니다")
    stats = {"tables": 0, "images": 0}
    blocks: list[str] = []
    _walk_container(body, blocks, stats)
    md = "\n\n".join(blocks)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md, stats


def _walk_container(elem: ET.Element, blocks: list[str], stats: dict) -> None:
    """div/body/셀 층 — p 와 table 만 블록을 만들고 나머지는 통과한다."""
    for child in elem:
        tag = _local(child.tag)
        if tag == "p":
            _blocks_from_p(child, blocks, stats)
        elif tag == "table":
            md = _table_md(child, stats)
            if md:
                blocks.append(md)
        elif tag == "img":
            stats["images"] += 1
        else:
            _walk_container(child, blocks, stats)


def _blocks_from_p(p: ET.Element, blocks: list[str], stats: dict) -> None:
    """문단 하나 — 안에 표가 끼어 있으면(span.TableControl) 그 자리에서 표 블록으로 뗀다."""
    buf: list[str] = []

    def flush() -> None:
        text = _norm_para("".join(buf))
        buf.clear()
        if text:
            blocks.append(text)

    def walk(e: ET.Element) -> None:
        if e.text:
            buf.append(e.text)
        for c in e:
            tag = _local(c.tag)
            if tag == "table":
                flush()
                md = _table_md(c, stats)
                if md:
                    blocks.append(md)
            elif tag == "img":
                stats["images"] += 1
            else:
                walk(c)
            if c.tail:
                buf.append(c.tail)

    walk(p)
    flush()


def _norm_para(text: str) -> str:
    """CR(문단 안 줄바꿈) → 개행. 줄 끝 공백만 지우고 안쪽 공백은 건드리지 않는다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return "\n".join(lines).strip("\n").strip()


def _table_md(table: ET.Element, stats: dict) -> str:
    trs = [c for c in table if _local(c.tag) == "tr"]
    if not trs:                                    # tbody 등 한 겹 아래
        trs = [tr for grp in table for tr in grp if _local(tr.tag) == "tr"]
    grid = [[td for td in tr if _local(td.tag) in ("td", "th")] for tr in trs]

    # HWP 서식은 내용 전체를 1×1 "테두리 박스" 표로 감싸는 일이 많다. 그대로 표로
    # 굳히면 문서 전체가 셀 하나가 되고 안쪽 진짜 표는 문장으로 뭉개진다 — 풀어서
    # 안쪽을 다시 블록으로 처리한다(여러 겹이면 재귀로 다 풀린다).
    if len(grid) == 1 and len(grid[0]) == 1:
        blocks: list[str] = []
        _walk_container(grid[0][0], blocks, stats)
        return "\n\n".join(blocks)

    stats["tables"] += 1
    rows = [[_cell_text(td) for td in tr] for tr in grid]
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""                                  # 내용 없는 장식 표
    width = max(len(r) for r in rows)
    lines = []
    for i, r in enumerate(rows):
        r = r + [""] * (width - len(r))
        lines.append("| " + " | ".join(r) + " |")
        if i == 0:
            lines.append("|" + " --- |" * width)
    return "\n".join(lines)


def _cell_text(td: ET.Element) -> str:
    """셀 텍스트 — 문단·중첩 셀 경계는 공백 하나로 잇는다(markdown 셀은 한 줄이다).

    중첩 표는 markdown 이 표현하지 못한다 — 텍스트 노드를 문서 순서대로 **한 번씩만**
    걷어서 편다. 문단마다 itertext 를 부르면 중첩 표 안 문단이 바깥 문단의 일부로
    또 들어가 내용이 두 벌이 된다.
    """
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if _local(e.tag) in ("p", "td", "tr"):
            parts.append(" ")
        if e.text:
            parts.append(e.text)
        for c in e:
            walk(c)
            if c.tail:
                parts.append(c.tail)

    walk(td)
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    return text.replace("|", "\\|")


# ===========================================================================
# 자식 프로세스 격리 — 시간 초과를 죽일 수 있어야 한다
# ===========================================================================
# lxml 의 XSLT 는 C 안에서 돌아 시그널로 끊을 수 없다. 파일마다 자식 프로세스에서
# 변환하고, 시한을 넘기면 프로세스째 죽인다. 손상 파일이 세그폴트를 내도 배치가
# 같이 죽지 않는 부수 효과도 있다.

class ExtractTimeout(Exception):
    pass


class ExtractError(Exception):
    pass


ENGINES = ("xml", "html")                      # 표를 살리는 엔진들 — 기본은 첫 번째
DEFAULT_ENGINE = ENGINES[0]


def _extract(src: Path, mode: str) -> tuple[str, dict]:
    if mode == "xml":
        return xml_to_markdown(hwp5_to_xml(src))
    if mode == "html":
        return xhtml_to_markdown(hwp5_to_xhtml(src))
    return hwp5_to_text(src).strip() + "\n", {"tables": 0, "images": 0}


def _child(conn, src_str: str, mode: str) -> None:
    try:
        conn.send(("ok", _extract(Path(src_str), mode)))
    except BaseException as exc:                   # noqa: BLE001 — 부모에게 그대로 전한다
        conn.send(("err", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def extract_in_child(src: Path, mode: str, timeout: float) -> tuple[str, dict]:
    recv_conn, send_conn = _MP.Pipe(duplex=False)
    proc = _MP.Process(target=_child, args=(send_conn, str(src), mode), daemon=True)
    proc.start()
    send_conn.close()                              # 부모 사본을 닫아야 EOF 가 보인다
    deadline = time.monotonic() + timeout
    try:
        while True:
            if recv_conn.poll(0.2):
                status, payload = recv_conn.recv()
                break
            if not proc.is_alive():
                if recv_conn.poll(0):              # 죽기 직전에 보냈을 수 있다
                    status, payload = recv_conn.recv()
                    break
                raise ExtractError(
                    f"자식 프로세스가 결과 없이 죽었습니다 (exitcode={proc.exitcode})")
            if time.monotonic() > deadline:
                raise ExtractTimeout(f"{mode} 변환이 {timeout:.0f}초를 넘겼습니다")
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
            proc.join()
        recv_conn.close()
    if status == "err":
        raise ExtractError(payload)
    return payload


# ===========================================================================
# 출처 표기 — corpus manifest.json 에서 찾아 첫머리 주석으로
# ===========================================================================

def manifest_index(paths: list[Path]) -> dict[Path, dict]:
    """입력 경로들에서 manifest.json 을 찾아 {절대경로: 출처 정보} 를 만든다.

    파일 인자는 부모 디렉터리를 거슬러 올라가며 찾는다 — 01_DATA/INBOX/AUTHORING/corpus/kofia/규정명/x.hwp
    처럼 manifest 가 두 층 위에 있는 배치를 위해서다.
    """
    manifests: set[Path] = set()
    for p in paths:
        start = (p if p.is_dir() else p.parent).resolve()
        for cand in [start, *start.parents]:
            m = cand / "manifest.json"
            if m.exists():
                manifests.add(m)
                break
            if cand == REPO_ROOT:
                break
    index: dict[Path, dict] = {}
    for m in manifests:
        data = json.loads(m.read_text(encoding="utf-8"))
        collected = str(data.get("collected_at", ""))[:10]
        for item in data.get("items", []):
            common = {"regulation": item.get("name", ""), "collected": collected,
                      "enforced": item.get("enforce", ""),
                      "revision_date": item.get("revised", "")}
            if item.get("body_file"):
                index[persisted_data_path(item["body_file"]).resolve()] = {
                    **common, "role": "body", "title": f"{item.get('name', '')} 전문",
                    "sha256": item.get("body_sha256", ""),
                }
            for att in item.get("attachments", []):
                if not att.get("file"):
                    continue
                index[persisted_data_path(att["file"]).resolve()] = {
                    **common, "role": att.get("role", "attachment"),
                    "title": att.get("title", ""), "source": att.get("url", ""),
                    "sha256": att.get("sha256", ""),
                }
    return index


def provenance_header(src: Path, info: dict | None, mode: str = DEFAULT_ENGINE) -> str:
    """첫머리 `# key: value` 블록 — corpus_build._header_comments 가 읽는 형태.

    converted 줄이 엔진을 말한다: `md(xml)` / `md(html)` / `md(text 폴백 — 표 손실)`.
    사이드카만 보고 어느 경로로 나왔는지 알 수 있어야 재변환 대상을 고를 수 있다.
    """
    lines = []
    if info:
        for key in ("title", "regulation", "role", "source", "collected",
                    "enforced", "revision_date", "sha256"):
            if info.get(key):
                lines.append(f"# {key}: {info[key]}")
    else:
        lines.append(f"# title: {src.stem}")
    how = f"md({mode})" if mode in ENGINES else "md(text 폴백 — 표 손실)"
    lines.append(f"# converted: hwp5(ole) → {how}, lawrag/core/hwp5_md.py(pyhwp)")
    return "\n".join(lines) + "\n\n"


# ===========================================================================
# 파일 하나 / 일괄
# ===========================================================================

def convert_file(src: Path, info: dict | None, force: bool,
                 timeout: float = DEFAULT_TIMEOUT, engine: str = DEFAULT_ENGINE) -> dict:
    if engine not in ENGINES:
        raise ValueError(f"모르는 엔진 {engine!r} — {ENGINES} 중 하나")
    out = src.with_name(src.name + ".md")
    row = {"file": str(src.relative_to(REPO_ROOT) if src.is_relative_to(REPO_ROOT) else src),
           "status": OK}
    if not force and out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        row["status"] = SKIP
        return row
    with src.open("rb") as f:
        fmt = detect_format(f.read(8))
    if fmt != "hwp5(ole)":
        row.update(status=FORMAT, format=fmt)
        return row
    try:
        try:
            md, stats = extract_in_child(src, engine, timeout)
            mode = engine
        except ExtractTimeout:
            md, stats = extract_in_child(src, "text", timeout)
            mode = "text"
    except (ExtractTimeout, ExtractError) as exc:  # 부분 실패 허용 — 기록하고 계속
        row.update(status=FAIL, error=f"{type(exc).__name__}: {exc}")
        return row
    out.write_text(provenance_header(src, info, mode) + md, encoding="utf-8")
    row.update(mode=mode, chars=len(md), tables=stats["tables"],
               images=stats["images"], out=out.name)
    return row


def gather(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.hwp")))
        elif p.suffix.lower() == ".hwp":
            files.append(p)
        else:
            raise SystemExit(f"lawrag/core/hwp5_md.py: .hwp 파일이나 디렉터리가 아닙니다 — {p}")
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--force", action="store_true", help="사이드카가 새것이어도 재변환")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help=f"파일당 변환 시한(초, 기본 {DEFAULT_TIMEOUT:.0f}) — "
                         "넘기면 텍스트 폴백")
    ap.add_argument("--engine", choices=ENGINES, default=DEFAULT_ENGINE,
                    help="표를 살리는 엔진 — xml(레코드 직독, 기본)·html(옛 XSLT, 대조용)")
    ap.add_argument("--report", type=Path, help="파일별 결과를 JSON 으로 남길 경로")
    args = ap.parse_args(argv)

    for p in args.paths:
        if not p.exists():
            raise SystemExit(f"lawrag/core/hwp5_md.py: 없는 경로 — {p}")

    index = manifest_index(args.paths)
    files = gather(args.paths)
    if not files:
        raise SystemExit("lawrag/core/hwp5_md.py: 변환할 .hwp 가 없습니다")

    rows = []
    for src in files:
        row = convert_file(src.resolve(), index.get(src.resolve()), args.force,
                           timeout=args.timeout, engine=args.engine)
        rows.append(row)
        if row["status"] != SKIP:
            if row["status"] == OK:
                tail = f"{row['chars']:>8}자 표{row['tables']}"
                if row["mode"] == "text":
                    tail += " (text 폴백)"
            else:
                tail = row.get("error", row.get("format", ""))
            print(f"[{row['status']:^6}] {row['file']} {tail}", flush=True)

    counts = {s: sum(1 for r in rows if r["status"] == s)
              for s in (OK, SKIP, FORMAT, FAIL)}
    fallbacks = sum(1 for r in rows if r.get("mode") == "text")
    print(f"\n변환 {counts[OK]} (text 폴백 {fallbacks}) · skip {counts[SKIP]}"
          f" · 형식 불일치 {counts[FORMAT]} · 실패 {counts[FAIL]} (총 {len(rows)})")
    for r in rows:
        if r["status"] == FAIL:
            print(f"  실패: {r['file']} — {r['error']}")
        elif r["status"] == FORMAT:
            print(f"  형식 불일치: {r['file']} — 실제 {r['format']}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "converted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "argv": [str(p) for p in args.paths], "engine": args.engine,
            "counts": counts, "rows": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report → {args.report}")

    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
