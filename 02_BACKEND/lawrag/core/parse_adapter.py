r"""T2. 파싱 어댑터 — 문서 → 정규화된 요소 리스트 (SPEC §2.2, §3.1-1).

이 단계는 **도메인을 모른다.** 용어집도 형식도 보지 않고 "무엇이 어디에 있다"만 낸다.
born-digital 전제이므로 OCR 을 끈다(텍스트 레이어가 있는데 OCR 을 돌리면 느려지고
한국어 법률 용어에서 재인식 오류가 난다 — v1 실측).

## docling 에서 무엇을 어떻게 가져오는가 (v1 에서 세 가지를 잃었던 자리)

1. **읽기 순서** — `doc.texts` / `doc.tables` 는 저장용 컬렉션이지 읽기 순서가 아니다.
   두 컬렉션을 이어붙이면 표가 전부 문서 끝으로 밀린다. `doc.iterate_items()` 가
   `doc.body` 트리를 순회해 표를 제자리에 끼워 준다 — 이쪽을 쓴다.
2. **표의 논리 셀** — `table.data.grid` 는 병합 셀을 자기가 덮는 모든 칸에 펼쳐 넣은
   격자다(colspan=5 면 같은 셀이 5번 나온다). `table.data.table_cells` 는 span 정보를
   가진 논리 셀 목록이다 — 이쪽을 쓴다. 열 위치가 남으므로 한 행에 여러 필드가 있어도 가른다.
3. **리스트 마커** — docling 은 `1. ` 을 `marker` 로 떼어내고 `text` 에서 지운다.
   `text` 만 쓰면 호 번호가 사라져 `^\d+\.` 정규식이 영영 안 맞는다. marker 를 되붙인다.
4. **그림** — `PictureItem` 은 `text` 가 비어 있다. 텍스트 항목과 같은 길로 흘리면
   `if not text: continue` 에 걸려 **캡션까지 함께** 사라지고, 통계에도 안 잡혀
   유실이 보이지 않는다. 표보다 앞에서 건져 `type="picture"` 요소로 남긴다.
   픽셀도 함께 받는다(`generate_picture_images`) — docling 이 찾아 놓은 것을 버리고
   좌표만 남기면 도장·서명이 거기 있었다는 사실만 알고 무엇인지는 모르게 된다.

`type` 은 docling 레이아웃 모델의 판단이므로 **힌트로만** 보존한다(§2.2 주의).
구조 판정은 형식 파일의 마커가 한다.

## 입구에서 막는 것 두 가지

암호화 PDF 와 cp949 텍스트는 **파싱 이전**에 갈린다. 둘 다 예전에는 라이브러리 내부
예외로 터졌다 — fitz 의 `document closed or encrypted`, `'utf-8' codec can't decode
byte 0xc1`. 둘 다 시끄럽긴 하지만 **무엇을 어떻게 고치면 되는지 말하지 않는다**.
실패가 원인을 말하지 않으면 사용자는 우리 코드의 버그로 읽는다(§00 게이트 철학).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lawrag.core import reading_order, typography

# docling 의 heading 계열 라벨 — section 용어가 제목 위치인지 보는 신호(§1.3)
HEADING_TYPES = {"title", "section_header", "page_header"}
FURNITURE_TYPES = {"page_header", "page_footer"}
# 그림 계열 라벨. 표와 마찬가지로 **구조를 열지 않고 구조에 담기는** 요소다.
PICTURE_TYPES = {"picture", "chart"}
# 그림을 몇 배로 렌더할지. 도장·서명 확인에는 2배면 충분하고, 더 키우면 payload 만 는다.
IMAGE_SCALE = 2.0

# 텍스트 파일 인코딩 후보 — **순서가 곧 안전장치다.**
# utf-8 을 먼저 두는 이유: strict 디코더라 cp949 바이트를 만나면 실패한다. 반대로
# cp949 는 거의 모든 바이트열을 받아 주므로 먼저 두면 utf-8 원문을 조용히 깨뜨린다.
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")
# **어떤 바이트열도 실패시키지 않는** 단일바이트 인코딩들. 후보에 끼면 한글 파일이
# 예외 없이 깨진 글자로 통과한다 — 디코딩 실패보다 나쁘다(틀린 줄 모르고 판정한다).
_NEVER_FAILS = {"iso-8859-1", "latin-1", "latin1", "windows-1252", "cp1252", "ascii"}
_CHARDET_SAMPLE = 10_000       # 추정에 쓰는 앞부분 — 추정은 싸야 한다

_CONVERTER = None


class EncryptedDocument(ValueError):
    """비밀번호/DRM 이 걸린 문서. 파싱을 시도하지 않고 입구에서 막는다."""


class UndecodableText(ValueError):
    """어느 후보 인코딩으로도 읽히지 않는 텍스트 파일."""


@dataclass
class Cell:
    """표의 논리 셀 하나 — span 과 좌표를 잃지 않는다."""
    text: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    # 셀 자신의 bbox. **좌표계가 표와 다르다** — 셀은 TOPLEFT, 표 prov 는 BOTTOMLEFT.
    # 여기서는 셀 원본을 그대로 두고, 쓰는 쪽이 origin 을 보고 해석한다.
    bbox: Optional[list[float]] = None
    origin: str = "TOPLEFT"
    # 표 **안의** 좌표축. 값 셀 하나는 자기 열의 머리(`1년 미만`)와 자기 행의
    # 머리(`중도해지수수료`)로 의미가 정해진다 — 이게 없으면 셀을 표 밖으로 꺼낸
    # 순간 `0.7` 이 무엇의 0.7 인지 알 길이 없다.
    is_col_header: bool = False
    is_row_header: bool = False

    def spans(self) -> bool:
        return self.row_span > 1 or self.col_span > 1

    @property
    def is_header(self) -> bool:
        return self.is_col_header or self.is_row_header


@dataclass
class Table:
    n_rows: int
    n_cols: int
    cells: list[Cell] = field(default_factory=list)

    def rows(self) -> list[list[Cell]]:
        """행마다 그 행에서 **시작하는** 논리 셀만, 열 순서로. 복제가 없다."""
        out: list[list[Cell]] = [[] for _ in range(self.n_rows)]
        for c in self.cells:
            if 0 <= c.row < self.n_rows:
                out[c.row].append(c)
        for r in out:
            r.sort(key=lambda c: c.col)
        return out

    def text(self) -> str:
        return "\n".join(" | ".join(c.text for c in row) for row in self.rows())

    def dump(self) -> dict:
        return {"n_rows": self.n_rows, "n_cols": self.n_cols,
                "cells": [c.__dict__ for c in self.cells]}

    def cell_at(self, row: int, col: int) -> Optional[Cell]:
        """span 을 고려해 (row, col) 을 덮는 셀. 격자를 펼치지 않고 찾는다."""
        for c in self.cells:
            if (c.row <= row < c.row + c.row_span
                    and c.col <= col < c.col + c.col_span):
                return c
        return None

    def col_header_of(self, col: int) -> str:
        """이 열의 머리글. 병합된 머리(`수수료 ┬ 1년 미만 / 1년 이상`)면 위에서부터
        이어 붙인다 — `수수료 · 1년 미만` 이 사람이 읽는 그대로다."""
        parts = [c.text for c in sorted(self._headers(is_col=True), key=lambda c: c.row)
                 if c.col <= col < c.col + c.col_span and c.text]
        return " · ".join(dict.fromkeys(parts))

    def row_header_of(self, row: int) -> str:
        parts = [c.text for c in sorted(self._headers(is_col=False), key=lambda c: c.col)
                 if c.row <= row < c.row + c.row_span and c.text]
        return " · ".join(dict.fromkeys(parts))

    def _headers(self, *, is_col: bool) -> list[Cell]:
        """머리글 셀들. docling 이 표시해 주지 않으면 **관습으로 되돌아간다** —
        첫 행이 열 머리, 첫 열이 행 머리. 틀릴 수 있으므로 `header_source` 로
        어느 쪽이었는지 남긴다."""
        flagged = [c for c in self.cells
                   if (c.is_col_header if is_col else c.is_row_header)]
        if flagged:
            return flagged
        if is_col:
            return [c for c in self.cells if c.row == 0] if self.n_rows > 1 else []
        return [c for c in self.cells if c.col == 0] if self.n_cols > 1 else []

    def header_source(self) -> str:
        """머리글 판단이 파서에서 왔는가, 관습에서 왔는가."""
        return "parser" if any(c.is_header for c in self.cells) else "convention"


@dataclass
class Element:
    """정규화된 요소 하나 — {type, text, page, bbox, reading_order} (§2.2)."""
    index: int                          # reading_order
    type: str                           # docling 판단 (힌트)
    text: str = ""
    table: Optional[Table] = None
    page: int = 1
    bbox: Optional[list[float]] = None
    # bbox 의 좌표원점. PDF prov 는 BOTTOMLEFT, 표 셀은 TOPLEFT 라 섞인다.
    bbox_origin: str = "BOTTOMLEFT"
    # 글자가 **실제로 시작하는** x (typography 가 심는다). bbox[0] 과 다를 수
    # 있다 — 들여쓰기를 선행 공백으로 표현한 조판에서 bbox 는 공백까지 왼쪽으로
    # 늘어난다. 들여쓰기 증거(S3)는 이 값을 봐야 층을 구별한다. x 는 좌표원점과
    # 무관하므로(뒤집히는 것은 y 뿐) bbox[0] 과 그대로 비교된다.
    text_x: Optional[float] = None
    # --- 타이포그래피 (`core.typography` 가 심는다) --------------------------
    # 마커 없는 제목은 **크고 굵고 위가 트여** 있어서 제목이다. 그 축이 없으면
    # 판별기가 아무리 정교해도 볼 수 없다. `None` 은 재지 못했다는 뜻이고 0 과 다르다.
    font_size: Optional[float] = None
    size_ratio: Optional[float] = None      # 본문 최빈 크기 대비 배율 — 판별은 이쪽을 본다
    bold: bool = False
    bold_ratio: float = 0.0
    # 굵기를 이름 끝 한 글자로 표현하는 글꼴이 있다(실측 ss2207: SECGCL/M/R).
    # 그 규약은 회사마다 달라 파서가 맞히지 않는다 — 이름을 그대로 실어 보낸다.
    font_name: str = ""
    gap_before: Optional[float] = None      # 같은 쪽에서 앞 요소 아래와의 세로 간격(pt)
    # 파싱 로직이 실어 보내는 부가 좌표. 문서 종류마다 다르므로 **스키마를 늘리지 않고**
    # 여기에 담는다(§00.4 "문서 고유의 특수 정보는 기존 그릇 안에"). 예: STT 전사의
    # {speaker, start, end} — 페이지·bbox 가 없는 문서의 출처가 여기로 온다.
    meta: dict = field(default_factory=dict)

    @property
    def is_table(self) -> bool:
        return self.table is not None

    @property
    def is_picture(self) -> bool:
        return self.type in PICTURE_TYPES

    @property
    def is_heading(self) -> bool:
        return self.type in HEADING_TYPES

    @property
    def is_furniture(self) -> bool:
        return self.type in FURNITURE_TYPES

    @property
    def opens_structure(self) -> bool:
        """이 요소가 **구조 경계를 열 수 있는가.**

        표와 그림은 낼 수 없다. 표는 셀 안의 번호가, 그림은 캡션의 `<그림 3>` 이
        마커처럼 생겼지만 둘 다 구역을 여는 것이 아니라 구역에 담기는 것이다.
        판정하는 쪽마다 `e.table` 을 따로 검사하다 그림을 빠뜨리는 일이 없도록
        여기 한 곳에 모은다.
        """
        return not self.is_table and not self.is_picture and bool(self.text)

    def content(self) -> str:
        return self.table.text() if self.table else self.text

    def dump(self) -> dict:
        d = {"index": self.index, "type": self.type, "page": self.page}
        if self.bbox:
            d["bbox"] = self.bbox
            d["bbox_origin"] = self.bbox_origin
        if self.text_x is not None:
            d["text_x"] = self.text_x
        if self.font_size is not None:
            d["font"] = {"size": self.font_size, "ratio": self.size_ratio,
                         "bold": self.bold, "bold_ratio": self.bold_ratio,
                         "name": self.font_name, "gap_before": self.gap_before}
        if self.meta:
            d["meta"] = self.meta
        if self.table:
            d["table"] = self.table.dump()
        else:
            d["text"] = self.text
        return d


@dataclass
class ParseResult:
    path: str
    doc_id: str
    parser: str
    born_digital: bool
    elements: list[Element] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    # 요소 index → 그림 data URI. 요소 밖에 두는 이유는 `_picture_meta` 주석 참조 —
    # 구조화 산출 JSON 에 base64 픽셀이 섞이지 않게 옆길로 나른다.
    images: dict[int, str] = field(default_factory=dict)

    def pages(self) -> int:
        return max((e.page for e in self.elements), default=0)


# ---------------------------------------------------------------------------

def norm_ws(s) -> str:
    """공백 정규화 — NBSP 를 펴고 연속 공백을 하나로.

    파싱 층의 표준 정규화다. grid_recover · agent6 전사도 이걸 쓴다 — 같은 4줄이
    세 곳에 복붙되어 있으면 한 곳만 고쳐지는 사고가 난다.
    (값 비교용 정규화는 별개다 — `core.normalize.normalize_text`.)
    """
    return " ".join(str(s or "").replace("\xa0", " ").split())


def decode_text(path: str | Path) -> str:
    """텍스트 파일을 읽는다 — 인코딩을 맞혀 보되, **못 맞히면 거부한다.**

    한국어 문서는 cp949/euc-kr 로 오는 일이 흔하다. utf-8 고정이면 원문이 멀쩡한데
    파이프라인이 `UnicodeDecodeError` 로 죽는다.

    `errors="replace"` 최종 폴백을 두지 않는 이유: 그건 실패를 성공으로 바꾸는 것이지
    읽는 게 아니다. 깨진 글자(``)로 만든 section 과 fact 는 게이트도 통과해 버릴 수
    있고, 그러면 **틀린 줄 모르는 판정**이 나간다. 못 읽으면 못 읽었다고 말한다.
    """
    p = Path(path)
    raw = p.read_bytes()
    if not raw:
        return ""

    candidates = list(TEXT_ENCODINGS)
    # chardet 은 있으면 쓰고 없으면 만다(설치를 강제하지 않는다). 추정은 utf-8 **뒤**에
    # 끼운다 — 앞에 두면 오추정 하나가 멀쩡한 utf-8 원문을 가로챈다.
    try:
        import chardet
    except ImportError:
        pass
    else:
        guess = ((chardet.detect(raw[:_CHARDET_SAMPLE]) or {}).get("encoding") or "").strip()
        if guess and guess.lower() not in _NEVER_FAILS and guess.lower() not in candidates:
            candidates.insert(candidates.index("utf-8") + 1, guess)

    for enc in candidates:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise UndecodableText(
        f"'{p.name}' 의 인코딩을 알 수 없습니다 — {', '.join(candidates)} 로 모두 실패했습니다. "
        f"UTF-8 로 변환해 다시 넣어 주세요. "
        f"(텍스트 파일이 아니라 바이너리일 수도 있습니다)")


def _check_not_encrypted(doc, path: str | Path) -> None:
    """열린 fitz 문서가 암호화됐으면 거부한다.

    fitz 는 암호화 PDF 도 **열어 준다** — 인증 전이라 텍스트만 못 줄 뿐이다. 그래서
    그대로 두면 `is_born_digital` 이 텍스트 0자를 보고 "스캔본"으로 오판해 OCR 을
    켜거나(느리고 결과도 쓰레기), fitz 내부의 `document closed or encrypted` 로 터진다.
    """
    if getattr(doc, "needs_pass", False):
        raise EncryptedDocument(
            f"'{Path(path).name}' 은 비밀번호/DRM 이 걸린 PDF 입니다 — "
            f"보호를 해제한 파일을 넣어 주세요. "
            f"(암호화된 채로는 텍스트 레이어를 읽을 수 없어 OCR 도 의미가 없습니다)")


def assert_readable_pdf(path: str | Path) -> None:
    """파싱 전에 암호화 여부만 싸게 확인한다 — 판별(라우팅) 경로가 쓴다."""
    import fitz

    doc = fitz.open(str(path))
    try:
        _check_not_encrypted(doc, path)
    finally:
        doc.close()


def is_born_digital(path: Path, min_chars: int = 200) -> tuple[bool, dict]:
    import fitz

    doc = fitz.open(str(path))
    try:
        _check_not_encrypted(doc, path)
        total, empty = 0, 0
        scan_pages = []
        for p in doc:
            t = p.get_text().strip()
            total += len(t)
            if not t:
                empty += 1
                if p.get_images(): scan_pages.append(p.number+1)
        n = doc.page_count
    finally:
        doc.close()
    return (total >= min_chars and empty < n and not scan_pages,
            {"pages": n, "text_chars": total, "empty_pages": empty, "scan_candidate_pages": scan_pages})


def pdf_parser_identity(path):
    """Bind parser cache to exact source and explicit OCR assets; no auto download."""
    from lawrag.platform.paths import data_path
    born, _ = is_born_digital(Path(path))
    policy = {'version': 'pdf-korean-ocr-v1', 'source_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
              'docling': docling_version(), 'ocr': not born}
    if not born:
        directory = Path(os.environ.get('STRUCTURE_OCR_MODEL_DIR', str(data_path('MODELS', 'rapidocr-korean-v4-native'))))
        manifest = directory / 'manifest.json'
        if not manifest.is_file():
            raise ValueError('Korean OCR assets missing: prepare rapidocr-korean-v4 or set STRUCTURE_OCR_MODEL_DIR')
        receipt = json.loads(manifest.read_text('utf-8'))
        if receipt.get('profile') != 'rapidocr-korean-v4-torch':
            raise ValueError('Unsupported OCR profile')
        expected = {r['file']: r['sha256'] for r in receipt.get('files', [])}
        assets = {}
        for name in ('ch_PP-OCRv4_det_mobile.pth', 'ch_ptocr_mobile_v2.0_cls_mobile.pth', 'korean_PP-OCRv4_rec_mobile.pth', 'korean_dict.txt'):
            p = directory / name
            if not p.is_file(): raise ValueError('Korean OCR asset missing: ' + name)
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h != expected.get(name): raise ValueError('Korean OCR asset hash mismatch: ' + name)
            assets[name] = {'path': str(p.resolve()), 'sha256': h}
        policy.update(profile=receipt['profile'], language='korean', assets=assets,
                      mixed_script_quality='unverified; Korean model does not guarantee Hanja preservation')
    return policy


def _converter(ocr: bool, *, policy=None):
    """docling 변환기 — 프로세스당 한 번만 만든다(모델 로딩이 비싸다)."""
    global _CONVERTER
    identity = json.dumps({k:v for k,v in policy.items() if k != 'source_sha256'}, sort_keys=True) if policy is not None else str(ocr)
    if _CONVERTER and _CONVERTER[0] == identity:
        return _CONVERTER[1]

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    if ocr:
        if not policy or not policy.get('assets'):
            raise ValueError('Explicit Korean OCR asset policy required')
        from docling.datamodel.pipeline_options import RapidOcrOptions
        from rapidocr import LangRec, OCRVersion
        assets = policy['assets']
        # Docling's language list selects its detector bundle; recognition is
        # explicitly overridden with the Korean model and matching dictionary.
        opts.ocr_options = RapidOcrOptions(
            backend='torch', lang=['chinese'],
            det_model_path=assets['ch_PP-OCRv4_det_mobile.pth']['path'], cls_model_path=assets['ch_ptocr_mobile_v2.0_cls_mobile.pth']['path'],
            rec_model_path=assets['korean_PP-OCRv4_rec_mobile.pth']['path'], rec_keys_path=assets['korean_dict.txt']['path'],
            rapidocr_params={'Rec.lang_type': LangRec.KOREAN,
                'Det.ocr_version': OCRVersion.PPOCRV4, 'Rec.ocr_version': OCRVersion.PPOCRV4})
    opts.do_ocr = ocr                      # born-digital 이면 끈다 (§2.2)
    opts.do_table_structure = True         # 값은 표 안에 있다 — 반드시 켠다
    opts.table_structure_options.do_cell_matching = True
    # 그림을 **실제 픽셀까지** 받는다. 이걸 켜지 않으면 docling 이 그림을 찾아 놓고도
    # 좌표만 주고 내용은 버린다 — 도장·서명·로고가 그 자리에 있었다는 사실만 남고
    # 무엇이었는지는 영영 알 수 없게 된다.
    opts.generate_picture_images = True
    opts.images_scale = IMAGE_SCALE
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    _CONVERTER = (identity, conv)
    return conv


def docling_version() -> str:
    try:
        from importlib.metadata import version
        return version("docling")
    except Exception:                      # pragma: no cover
        return "?"


def _prov(item) -> tuple[int, Optional[list[float]], str]:
    """(페이지, bbox, 좌표원점).

    원점을 함께 돌려주는 이유: PDF prov 는 BOTTOMLEFT, 표 셀은 TOPLEFT 라 섞여 있다.
    여기서 통일하지 않고 그대로 실어 보낸다 — 쓰는 쪽(뷰어 오버레이)이 페이지 높이를
    알아야 뒤집을 수 있고, 파싱 단계는 페이지 크기를 모른다.
    """
    prov = getattr(item, "prov", None)
    if not prov:
        return 1, None, "BOTTOMLEFT"
    page = getattr(prov[0], "page_no", None) or 1
    bb = getattr(prov[0], "bbox", None)
    if bb is None:
        return page, None, "BOTTOMLEFT"
    origin = str(getattr(bb, "coord_origin", "BOTTOMLEFT")).split(".")[-1]
    try:
        return page, [round(bb.l, 2), round(bb.t, 2), round(bb.r, 2), round(bb.b, 2)], origin
    except AttributeError:                 # pragma: no cover
        return page, None, origin


def _table_of(item) -> Optional[Table]:
    """논리 셀을 그대로 가져온다 — grid 로 펼치지 않는다."""
    data = getattr(item, "data", None)
    if data is None:
        return None
    cells = []
    for c in getattr(data, "table_cells", []) or []:
        t = norm_ws(getattr(c, "text", "") or "")
        bb = getattr(c, "bbox", None)
        box, origin = None, "TOPLEFT"
        if bb is not None:
            try:
                box = [round(bb.l, 2), round(bb.t, 2), round(bb.r, 2), round(bb.b, 2)]
                origin = str(getattr(bb, "coord_origin", "TOPLEFT")).split(".")[-1]
            except AttributeError:                 # pragma: no cover
                box = None
        cells.append(Cell(
            text=t,
            row=getattr(c, "start_row_offset_idx", 0),
            col=getattr(c, "start_col_offset_idx", 0),
            row_span=getattr(c, "row_span", 1) or 1,
            col_span=getattr(c, "col_span", 1) or 1,
            bbox=box, origin=origin,
            is_col_header=bool(getattr(c, "column_header", False)),
            is_row_header=bool(getattr(c, "row_header", False)
                               or getattr(c, "row_section", False))))
    if not cells:
        return None
    return Table(n_rows=getattr(data, "num_rows", 0) or (max(c.row for c in cells) + 1),
                 n_cols=getattr(data, "num_cols", 0) or (max(c.col for c in cells) + 1),
                 cells=cells)


def _caption_refs(doc) -> set[str]:
    """그림이 자기 캡션이라고 가리키는 텍스트 항목들의 self_ref.

    캡션은 `doc.texts` 에도 들어 있어 `iterate_items()` 가 **한 번 더** 내보낸다.
    그림 요소에 캡션을 실으면서 이걸 두면 같은 문장이 두 번 들어간다. 그림 캡션만
    걷어낸다 — 표 캡션은 지금도 독립 텍스트로 흐르고 있고, 여기서 같이 바꾸면
    기존 문서의 구조 판정이 함께 움직인다.
    """
    refs: set[str] = set()
    for pic in getattr(doc, "pictures", []) or []:
        for cap in getattr(pic, "captions", []) or []:
            cref = getattr(cap, "cref", None)
            if cref:
                refs.add(cref)
    return refs


def _picture_meta(item, doc) -> tuple[str, dict, str]:
    """(캡션, meta, 이미지 data URI). docling 이 찾아 놓은 것을 버리지 않는다.

    data URI 는 meta 에 넣지 않고 따로 돌려준다 — meta 는 구조화 산출 JSON 을 타고
    끝까지 흐르는데, 거기에 base64 픽셀이 섞이면 사람이 읽을 수 없는 파일이 된다.
    픽셀은 `ParseResult.images` 로 옆길로 보내고, 요소에는 있었다는 사실만 남긴다.
    """
    caption = ""
    try:
        caption = norm_ws(item.caption_text(doc) or "")
    except Exception:                          # pragma: no cover - docling 버전차
        caption = ""
    meta: dict = {"ref": getattr(item, "self_ref", "")}
    if caption:
        meta["caption"] = caption

    img = getattr(item, "image", None)
    uri = str(getattr(img, "uri", "") or "") if img is not None else ""
    size = getattr(img, "size", None) if img is not None else None
    # docling 의 `Size` 는 pydantic 모델이다 — 언패킹하면 (필드명, 값) 쌍이 나온다.
    w, h = getattr(size, "width", None), getattr(size, "height", None)
    if w and h:
        meta["image_size"] = [int(w), int(h)]
    meta["has_image"] = bool(uri)

    for ann in getattr(item, "annotations", []) or []:
        cls = getattr(ann, "predicted_classes", None)
        if cls:
            top = max(cls, key=lambda c: getattr(c, "confidence", 0))
            name = getattr(top, "class_name", "")
            if name:
                meta["classification"] = name
            break
    return caption, meta, uri


def _item_text(item) -> str:
    """마커를 되붙인다 — docling 이 `1. ` 을 text 에서 떼어 marker 로 옮긴다."""
    text = getattr(item, "text", "") or ""
    marker = (getattr(item, "marker", "") or "").strip()
    if marker and not text.strip().startswith(marker):
        text = f"{marker} {text}"
    return norm_ws(text)


def _elements_from_docling(doc) -> tuple[list[Element], dict[int, str], dict]:
    """docling 문서 → Element 리스트. **포맷 무관** — PDF·DOCX 가 같은 길을 탄다.

    반환: (elements, picture_uris, docling_stats). picture_uris 는 요소 index →
    data URI 인데, 호출 쪽이 재정렬을 한다면 재정렬 **전** index 이므로 스스로
    다시 맞춰야 한다(parse_pdf 가 그렇게 한다).

    `iterate_items()` 는 기본이 BODY 레이어뿐이다 — 머리말/꼬리말이 통째로 빠진다.
    그런데 **파트 마커가 거기 숨어 있다**: 실측(ss2207)에서 `[별지1]` 이
    page_header 로 분류됐고, 그걸 못 받으면 별지1 구역을 통째로 놓친다.
    그래서 받아 두고, 무엇을 무시할지는 형식(마커)이 정하게 한다.
    """
    from docling_core.types.doc.common.content_layer import ContentLayer
    layers = {ContentLayer.BODY, ContentLayer.FURNITURE}

    caption_refs = _caption_refs(doc)
    picture_uris: dict[int, str] = {}

    elements: list[Element] = []
    for item, _level in doc.iterate_items(included_content_layers=layers):   # ← 진짜 읽기 순서
        kind = type(item).__name__
        if kind == "TableItem":
            table = _table_of(item)
            if table is None:
                continue
            page, bbox, origin = _prov(item)
            elements.append(Element(index=len(elements), type="table",
                                    table=table, page=page, bbox=bbox,
                                    bbox_origin=origin))
            continue
        # 그림은 텍스트가 없다 — `if not text: continue` 앞에서 건져야 한다.
        # 그냥 흘리면 캡션까지 함께 사라지고, 유실이 통계에도 안 잡힌다.
        if kind == "PictureItem":
            caption, meta, uri = _picture_meta(item, doc)
            page, bbox, origin = _prov(item)
            label = str(getattr(item, "label", "picture")).split(".")[-1].strip("'\"").lower()
            el = Element(index=len(elements),
                         type=label if label in PICTURE_TYPES else "picture",
                         text=caption, page=page, bbox=bbox,
                         bbox_origin=origin, meta=meta)
            elements.append(el)
            if uri:
                picture_uris[el.index] = uri
            continue
        if getattr(item, "self_ref", None) in caption_refs:
            continue                           # 그림 요소가 이미 싣고 갔다
        text = _item_text(item)
        if not text:
            continue
        label = str(getattr(item, "label", "text")).split(".")[-1].strip("'\"").lower()
        page, bbox, origin = _prov(item)
        meta: dict = {}
        # 제목 level. PDF 레이아웃 모델은 어휘에 Section-header 하나뿐이라 전부 1로
        # 평면화되지만, DOCX 는 Word 스타일의 **진짜 계층**이 온다(msword_backend 가
        # outlineLvl·스타일명에서 읽는다). docling 판단이므로 힌트로만 싣는다(§2.2).
        if kind == "SectionHeaderItem":
            lvl = getattr(item, "level", None)
            if lvl is not None:
                meta["level"] = int(lvl)
        elements.append(Element(index=len(elements), type=label, text=text,
                                page=page, bbox=bbox, bbox_origin=origin, meta=meta))

    docling_stats = {
        "docling_texts": len(getattr(doc, "texts", [])),
        "docling_tables": len(getattr(doc, "tables", [])),
        "docling_pictures": len(getattr(doc, "pictures", [])),
        "docling_elements": len(elements),
    }
    return elements, picture_uris, docling_stats


def parse_pdf(path: str | Path, *, recognize_grids=None) -> ParseResult:
    p = Path(path)
    born, pdf_stats = is_born_digital(p)
    warnings: list[str] = []
    if not born:
        warnings.append("한국어 OCR 적용 — 국한문 혼용·작은 글자·표의 원문 대조가 필요합니다")

    policy = pdf_parser_identity(p)
    doc = _converter(ocr=not born, policy=policy).convert(str(p)).document
    # picture_uris 는 요소 index → data URI (재정렬 뒤 다시 맞춘다)
    elements, picture_uris, docling_stats = _elements_from_docling(doc)

    # 양식 페이지는 읽기 순서가 좌표와 어긋나 온다(T2b). 요소 index 가 여기서 다시
    # 매겨지므로 **index 를 쓰는 무엇보다 먼저** 돌아야 한다.
    was = {id(e): i for i, e in enumerate(elements)}
    elements, order_stats, order_warnings = reading_order.reorder(elements)
    warnings.extend(order_warnings)
    images = {e.index: picture_uris[was[id(e)]]
              for e in elements if was[id(e)] in picture_uris}

    # 표로 인식되지 못한 격자를 좌표로 되찾는다(T2c). **기본은 꺼져 있다** —
    # 인식기를 준 쪽만 돈다. 글자는 여기서 오지 않고 docling 것이 그대로 담긴다.
    grid_stats: dict = {}
    if recognize_grids is not None:
        from lawrag.core import grid_recover
        elements, grid_stats, grid_warn = grid_recover.recover(
            p, elements, recognize=recognize_grids,
            page_heights=grid_recover.page_heights(p))
        warnings.extend(grid_warn)

    # 글자의 크기·굵기·간격을 심는다(T2c). 재정렬 **뒤에** 돈다 — `gap_before` 는
    # "앞 요소와의 간격"이라 리스트 순서를 그대로 믿는다. 뒤섞인 순서로 재면 음수
    # 간격이 나오거나 엉뚱한 요소와의 거리가 잡힌다.
    type_stats = typography.annotate(p, elements)

    stats = {
        "parser_identity": policy,
        **docling_stats,
        **order_stats,
        **type_stats,
        **grid_stats,
        "elements": len(elements),
        "tables": sum(1 for e in elements if e.is_table),
        "pictures": sum(1 for e in elements if e.is_picture),
        "captioned_pictures": sum(1 for e in elements if e.is_picture and e.text),
        "pictures_with_image": len(images),
        **pdf_stats,
    }
    if stats["tables"] == 0 and stats["docling_tables"] == 0:
        warnings.append("표가 하나도 인식되지 않았습니다 — 값이 서술로 처리됩니다")
    lost = stats["pictures"] - stats["pictures_with_image"]
    if lost:
        warnings.append(
            f"그림 {lost}개는 픽셀을 받지 못했습니다 — 자리와 좌표만 남습니다")

    return ParseResult(
        path=str(p), doc_id=hashlib.sha256(p.read_bytes()).hexdigest()[:12],
        parser=f"docling {docling_version()} (ocr={'on' if not born else 'off'}, "
               f"tables=on, images=on)",
        born_digital=born, elements=elements, warnings=warnings, stats=stats,
        images=images)


# ---------------------------------------------------------------------------
# DOCX — 추론이 없는 경로
# ---------------------------------------------------------------------------

def parse_docx(path: str | Path) -> ParseResult:
    """DOCX — 레이아웃 모델도 OCR 도 TableFormer 도 돌지 않는다.

    docling 의 msword_backend 가 OOXML 태그를 그대로 읽는다: 문단·표·제목이 파일
    안에 선언돼 있어 **추론이 아니라 독해**다. PDF 와 결정적으로 다른 것 둘:

    1. 제목 계층이 진짜다 — Word 스타일(outlineLvl·"Heading N")의 level 이
       section_header 요소의 meta.level 로 온다. PDF 는 전부 1로 평면화된다.
    2. 지면 좌표가 없다 — DOCX 는 리플로우 문서라 페이지·bbox 가 파일에 존재하지
       않는다. page=1 고정, 타이포그래피 주석(T2c)·reading_order 재정렬(T2b)·
       격자 복구도 없다. iterate_items() 의 순서가 곧 문서 순서다.

    구조 판정은 여기서도 형식의 마커가 한다 — meta.level 은 힌트다(§2.2).
    """
    p = Path(path)
    doc = _converter(ocr=False).convert(str(p)).document
    elements, picture_uris, docling_stats = _elements_from_docling(doc)
    images = dict(picture_uris)            # 재정렬이 없으니 index 가 그대로다

    warnings: list[str] = []
    stats = {
        **docling_stats,
        "elements": len(elements),
        "tables": sum(1 for e in elements if e.is_table),
        "pictures": sum(1 for e in elements if e.is_picture),
        "captioned_pictures": sum(1 for e in elements if e.is_picture and e.text),
        "pictures_with_image": len(images),
        "headings_with_level": sum(1 for e in elements if e.meta.get("level")),
    }
    if stats["tables"] == 0 and stats["docling_tables"] == 0:
        warnings.append("표가 하나도 인식되지 않았습니다 — 값이 서술로 처리됩니다")

    return ParseResult(
        path=str(p), doc_id=hashlib.sha256(p.read_bytes()).hexdigest()[:12],
        parser=f"docling {docling_version()} (docx, tables=native)",
        born_digital=True, elements=elements, warnings=warnings, stats=stats,
        images=images)


# ---------------------------------------------------------------------------
# Markdown — 요약서·설명서가 마크다운으로 오는 경우, 그리고 테스트용
# ---------------------------------------------------------------------------

_MD_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]*)\)")


def _markdown_elements(raw: str) -> list[Element]:
    """마크다운 본문 → Element 리스트. 표는 파이프 표를 논리 셀로 읽는다.

    parse_markdown(.md 파일)과 parse_hwp(HWP 변환분)가 같은 빌더를 쓴다 —
    두 곳에 복붙되어 있으면 한 곳만 고쳐지는 사고가 난다.
    """
    elements: list[Element] = []
    buf: list[str] = []                    # 표 블록 누적

    def flush_table() -> None:
        nonlocal buf
        rows, buf = buf, []
        raw_rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
        # 구분선(`|---|---|`)은 셀이 아니라 **머리글 경계 표시**다. 지우기 전에
        # 몇 번째 줄이었는지 기억한다 — 그 위가 열 머리글이다.
        sep = next((i for i, r in enumerate(raw_rows)
                    if r and all(set(c) <= set("-: ") for c in r if c)), None)
        parsed = [r for i, r in enumerate(raw_rows) if i != sep]
        if not parsed:
            return
        n_header = sep if sep is not None else 0
        cells = [Cell(text=c, row=i, col=j, is_col_header=i < n_header)
                 for i, r in enumerate(parsed) for j, c in enumerate(r) if c]
        if cells:
            elements.append(Element(index=len(elements), type="table",
                                    table=Table(n_rows=len(parsed),
                                                n_cols=max(len(r) for r in parsed),
                                                cells=cells), page=1))

    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("|"):
            buf.append(s)
            continue
        if buf:
            flush_table()
        if not s:
            continue
        img = _MD_IMAGE.fullmatch(s)
        if img:
            alt = norm_ws(img.group("alt"))
            meta = {"ref": img.group("src")}
            if alt:
                meta["caption"] = alt
            elements.append(Element(index=len(elements), type="picture",
                                    text=alt, page=1, meta=meta))
            continue
        if s.startswith("#"):
            elements.append(Element(index=len(elements), type="section_header",
                                    text=norm_ws(s.lstrip("#").strip()), page=1))
        elif s.startswith(">"):
            elements.append(Element(index=len(elements), type="footnote",
                                    text=norm_ws(s.lstrip(">").strip()), page=1))
        elif set(s) <= set("-=_*") and (len(s) >= 3 or s[0] not in "-*"):
            continue                        # 수평선 — 리스트 검사보다 먼저 와야 한다:
            #                                 `---`/`***` 가 `-`/`*` 시작이라 불릿으로 오분류됐다
        elif s.startswith(("-", "*")) or (s[:2].rstrip(".").isdigit() and "." in s[:3]):
            elements.append(Element(index=len(elements), type="list_item",
                                    text=norm_ws(s), page=1))
        else:
            elements.append(Element(index=len(elements), type="text",
                                    text=norm_ws(s), page=1))
    if buf:
        flush_table()
    return elements


def parse_markdown(path: str | Path) -> ParseResult:
    """마크다운을 같은 Element 리스트로.

    docling 없이 코어 전체를 돌릴 수 있게 하는 통로이기도 하다 — 테스트가 빨라진다.
    """
    p = Path(path)
    raw = decode_text(p)
    elements = _markdown_elements(raw)
    return ParseResult(
        path=str(p), doc_id=hashlib.sha256(raw.encode()).hexdigest()[:12],
        parser="markdown", born_digital=True, elements=elements,
        stats={"elements": len(elements),
               "tables": sum(1 for e in elements if e.is_table),
               "pictures": sum(1 for e in elements if e.is_picture)})


# ---------------------------------------------------------------------------
# HWP — 변환을 거치는 경로 (hwp5 는 pyhwp, hwpx 는 OWPML 직독)
# ---------------------------------------------------------------------------

# 판별용 텍스트 추출 시한(초). 전체 변환 시한(convert.DEFAULT_TIMEOUT)보다 짧다 —
# 판별은 싸야 하고, 이 시한을 넘기는 파일은 doc_type 명시 모드로 넣으면 된다.
_HWP_PROBE_TIMEOUT = 30.0


def _hwp_kind(path: Path) -> str:
    """매직바이트 판별 — 확장자를 믿지 않는다(lawrag/core/hwp5_md.py §8-5 와 같은 계약).

    .hwp 로 내려받은 파일이 실제로는 hwpx·pdf 인 일이 실측으로 잦다. 조용히
    엉뚱한 파서에 넣으면 라이브러리 내부 예외로 터진다 — 입구에서 이름을 대고 가른다.
    """
    from lawrag.sources.common import detect_format
    with Path(path).open("rb") as f:
        return detect_format(f.read(8))


def _hwp_reject(p: Path, kind: str) -> None:
    """hwp5/hwpx 가 아닌 것을 원인과 처방을 말하며 거부한다. 항상 raise."""
    if kind == "pdf":
        raise ValueError(
            f"'{p.name}' 은 확장자만 hwp 이고 실제로는 PDF 입니다 — "
            f".pdf 로 바꿔 넣으면 그대로 처리됩니다")
    raise ValueError(
        f"'{p.name}' 은 한글 문서가 아닙니다 (감지: {kind}) — "
        f"hwp5(ole)·hwpx(zip) 만 받습니다")


def _convert_module():
    """저장소 루트의 lawrag/core/hwp5_md.py — hwp5→md 변환의 단일 소유자라 코어가 빌려 쓴다.

    (자식 프로세스 격리·시간 초과·텍스트 폴백이 전부 저기에 있다 — 복제하면
    XSLT 병증 대응이 두 벌이 된다.)
    """
    from lawrag.core import hwp5_md
    return hwp5_md


def parse_hwp(path: str | Path) -> ParseResult:
    """HWP → markdown → 같은 Element 그릇. 지면 좌표가 없는 경로다(DOCX 와 같은 제약).

    - hwp5(ole): lawrag/core/hwp5_md.py 경로 그대로 — 자식 프로세스에서 레코드 XML 을
      직독해 표를 md 표로 굳히고(병합 셀 정렬 보존), 시한을 넘기면 텍스트 폴백으로
      전문만 건진다. 그림은 변환이 버린다 — 개수만 경고로 남긴다.
    - hwpx(zip): core.hwpx_md 가 OWPML 태그를 직독한다. 추론이 없다.

    HWP 실측(KOFIA): 개요/named 스타일이 전무해 DOCX 경유로도 제목 계층은 오지
    않는다. 구조는 여기서도 마커가 판정한다 — md 를 거치는 것이 손실이 아니다.
    """
    p = Path(path)
    kind = _hwp_kind(p)
    warnings: list[str] = []
    conv: dict = {}

    if kind == "hwpx(zip)":
        from lawrag.core import hwpx_md
        if not hwpx_md.is_hwpx(p):
            raise ValueError(
                f"'{p.name}' 은 zip 이지만 HWPX(OWPML) 가 아닙니다 — "
                f"docx 라면 확장자를 .docx 로 바꿔 넣어 주세요")
        md = hwpx_md.hwpx_to_md(p)
        parser = "hwpx(zip) → md (core.hwpx_md)"
    elif kind == "hwp5(ole)":
        convert = _convert_module()
        try:
            try:
                md, conv = convert.extract_in_child(p, convert.DEFAULT_ENGINE,
                                                    convert.DEFAULT_TIMEOUT)
            except convert.ExtractTimeout:
                md, conv = convert.extract_in_child(p, "text", convert.DEFAULT_TIMEOUT)
                warnings.append("HWP 변환이 시한을 넘겨 텍스트 폴백으로 뽑았습니다 — "
                                "표가 <표> 자리표시자로 남습니다")
        except convert.ExtractError as exc:
            raise ValueError(
                f"'{p.name}' 을 HWP5 로 읽지 못했습니다 — {exc} "
                f"(OLE 파일이지만 한글 문서가 아닐 수 있습니다. 구형 Word .doc 이면 "
                f".docx 나 PDF 로 다시 저장해 주세요)") from exc
        parser = f"hwp5(ole) → md (core.hwp5_md, {convert.DEFAULT_ENGINE})"
        if conv.get("images"):
            warnings.append(f"그림 {conv['images']}개는 HWP 변환이 버립니다 — 개수만 남습니다")
    else:
        _hwp_reject(p, kind)

    elements = _markdown_elements(md)
    stats = {"elements": len(elements),
             "tables": sum(1 for e in elements if e.is_table),
             "pictures": sum(1 for e in elements if e.is_picture),
             "md_chars": len(md)}
    if conv:
        stats["hwp_tables"] = conv.get("tables", 0)
        stats["hwp_images"] = conv.get("images", 0)
    if stats["tables"] == 0:
        warnings.append("표가 하나도 인식되지 않았습니다 — 값이 서술로 처리됩니다")
    return ParseResult(
        path=str(p), doc_id=hashlib.sha256(p.read_bytes()).hexdigest()[:12],
        parser=parser, born_digital=True, elements=elements,
        warnings=warnings, stats=stats)


def hwp_probe_text(path: str | Path, limit: int = 20_000) -> str:
    """앞부분 텍스트만 싸게 — 내용 미리보기·경량 검사용 (전체 변환 없이).

    hwp5 는 텍스트 경로만 돌린다(XSLT 없음) — 표는 안 나오지만 빠르고, 시한도
    전체 변환보다 짧게 잡는다. 읽지 못하면 parse_hwp 와 같은 말로 거부한다.
    """
    p = Path(path)
    kind = _hwp_kind(p)
    if kind == "hwpx(zip)":
        from lawrag.core import hwpx_md
        if not hwpx_md.is_hwpx(p):
            raise ValueError(
                f"'{p.name}' 은 zip 이지만 HWPX(OWPML) 가 아닙니다 — "
                f"docx 라면 확장자를 .docx 로 바꿔 넣어 주세요")
        return hwpx_md.hwpx_to_md(p)[:limit]
    if kind == "hwp5(ole)":
        convert = _convert_module()
        try:
            text, _ = convert.extract_in_child(p, "text", _HWP_PROBE_TIMEOUT)
        except (convert.ExtractTimeout, convert.ExtractError) as exc:
            raise ValueError(
                f"'{p.name}' 의 판별용 텍스트를 뽑지 못했습니다 — {exc} "
                f"(doc_type 을 직접 지정하는 명시 모드로 넣어 주세요)") from exc
        return text[:limit]
    _hwp_reject(p, kind)


def element_from_dump(d: dict) -> Element:
    """`Element.dump()` 의 역. 표는 논리 셀째 되살린다."""
    table = None
    if d.get("table"):
        t = d["table"]
        cells = [Cell(**c) for c in t.get("cells", [])]
        table = Table(n_rows=t.get("n_rows", 0), n_cols=t.get("n_cols", 0), cells=cells)
    font = d.get("font") or {}
    return Element(
        index=d["index"], type=d.get("type", "text"), text=d.get("text", ""),
        table=table, page=d.get("page", 1), bbox=d.get("bbox"),
        bbox_origin=d.get("bbox_origin", "BOTTOMLEFT"), text_x=d.get("text_x"),
        meta=d.get("meta") or {},
        font_size=font.get("size"), size_ratio=font.get("ratio"),
        bold=bool(font.get("bold")), bold_ratio=font.get("bold_ratio", 0.0),
        font_name=font.get("name", ""), gap_before=font.get("gap_before"))


def result_from_dump(d: dict) -> ParseResult:
    """저장해 둔 파싱 결과를 되살린다 — **docling 을 다시 돌리지 않기 위한 통로**다.

    규칙을 고치고 다시 해석할 때 비싼 것은 파싱(모델 추론)이고 해석(S0~S5)은 싸다.
    둘을 갈라 두지 않으면 규칙 한 줄 고칠 때마다 몇 분을 기다리게 된다.
    """
    return ParseResult(
        path=d.get("path", ""), doc_id=d.get("doc_id", ""),
        parser=d.get("parser", ""), born_digital=bool(d.get("born_digital", True)),
        elements=[element_from_dump(e) for e in d.get("elements", [])],
        warnings=list(d.get("warnings", [])), stats=dict(d.get("stats", {})),
        images={int(k): v for k, v in (d.get("images") or {}).items()})


def result_to_dump(r: ParseResult) -> dict:
    return {"path": r.path, "doc_id": r.doc_id, "parser": r.parser,
            "born_digital": r.born_digital, "warnings": r.warnings, "stats": r.stats,
            "elements": [e.dump() for e in r.elements],
            "images": {str(k): v for k, v in r.images.items()}}


def parse(path: str | Path) -> ParseResult:
    """확장자로 갈라 준다. 형식·용어집과 무관하게 동작한다."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"입력 문서를 찾을 수 없습니다: {p}")
    if p.suffix.lower() == ".pdf":
        return parse_pdf(p)
    if p.suffix.lower() == ".docx":
        return parse_docx(p)
    if p.suffix.lower() in (".hwp", ".hwpx"):
        return parse_hwp(p)
    if p.suffix.lower() in (".md", ".markdown", ".txt"):
        return parse_markdown(p)
    if p.suffix.lower() == ".doc":
        # OLE 라 hwp5 와 매직이 같다 — 확장자로 먼저 갈라야 정확한 처방이 나간다
        raise ValueError(
            f"구형 Word(.doc)는 읽는 파서가 없습니다 — Word/한컴오피스에서 .docx 로 "
            f"다시 저장해 넣어 주세요 ('{p.name}')")
    raise ValueError(f"지원하지 않는 형식입니다: {p.suffix} (pdf/docx/hwp/hwpx/md)")
