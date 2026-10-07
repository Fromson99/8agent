"""DOCX OOXML reader without Docling or model downloads.

Coordinates are assigned later by the existing synthetic-page renderer, not
claimed to be original Word pagination. Native numbering/styles remain evidence.
"""
from __future__ import annotations
import base64
from collections import Counter
import hashlib
import posixpath
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

from . import docx_ooxml as ox

VERSION = 'docx-ooxml-native-v1'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def parse(path):
    from .parse_adapter import Cell, Element, ParseResult, Table
    path = Path(path)
    elements, images, warnings = [], {}, []
    def add(kind, text='', **kw):
        item = Element(index=len(elements), type=kind, text=text, page=1, **kw)
        elements.append(item)
        return item
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read('word/document.xml'))
        body = document.find(ox.W + 'body')
        if body is None:
            raise ValueError('DOCX word/document.xml has no body')
        styles = ox._Styles(ox._read(archive, 'word/styles.xml'))
        rows = ox.read(path)
        sizes = Counter()
        for row in rows:
            if row.get('size_pt') and row.get('text', '').strip():
                sizes[row['size_pt']] += len(row['text'].strip())
        body_size = sizes.most_common(1)[0][0] if sizes else None
        blocks = list(ox._blocks(body))
        if len(rows) != len(blocks):
            raise ValueError('DOCX native paragraph order mismatch')
        relations = ox._read(archive, 'word/_rels/document.xml.rels')
        rels = {r.get('Id'): r for r in relations} if relations is not None else {}
        for block, row in zip(blocks, rows):
            if row.get('table'):
                cells, active, ncols = [], {}, 0
                trs = block.findall(ox.W + 'tr')
                for ri, tr in enumerate(trs):
                    offset = tr.find(f'{ox.W}trPr/{ox.W}gridBefore')
                    col = int(ox._val(offset) or 0)
                    continuing = {}
                    for tc in tr.findall(ox.W + 'tc'):
                        span = int(ox._val(tc.find(f'{ox.W}tcPr/{ox.W}gridSpan')) or 1)
                        if span < 1:
                            raise ValueError('DOCX invalid table gridSpan')
                        vm = tc.find(f'{ox.W}tcPr/{ox.W}vMerge')
                        text = '\n'.join(ox._text(p) for p in tc.iter(ox.W + 'p')).strip()
                        previous = active.get((col, span))
                        if vm is not None and ox._val(vm) != 'restart':
                            if previous is None:
                                raise ValueError('DOCX vertical merge has no preceding cell')
                            previous.row_span += 1
                            if text:
                                previous.text += '\n' + text
                            continuing[(col, span)] = previous
                        else:
                            cell = Cell(text=text, row=ri, col=col, col_span=span)
                            cells.append(cell)
                            if vm is not None:
                                continuing[(col, span)] = cell
                        col += span
                    ncols = max(ncols, col)
                    active = continuing
                table = Table(n_rows=len(trs), n_cols=ncols, cells=cells)
                add('table', table.text(), table=table)
                if len(list(block.iter(ox.W + 'tbl'))) > 1:
                    warnings.append('중첩 표는 외부 셀 안의 텍스트로 보존했습니다; 내부 격자 원문 대조 필요')
            else:
                text = row['text'].strip()
                if text:
                    level = row['outline_level']
                    ppr = block.find(ox.W + 'pPr')
                    sid = ox._val(ppr.find(ox.W + 'pStyle')) if ppr is not None else None
                    if level is None:
                        import re
                        for style in styles.chain(sid):
                            name = ox._val(style.find(ox.W + 'name')) or ''
                            match = re.fullmatch(r'heading\s*([1-9])', name, re.I)
                            if match:
                                level = int(match[1]) - 1
                                break
                    meta = {'docx': {k: row[k] for k in (
                        'label', 'num_fmt', 'ilvl', 'left_twips', 'start_twips', 'outline_level')
                        if row[k] is not None}}
                    if level is not None and 0 <= level <= 8:
                        meta['level'] = level + 1
                    if row['label']:
                        text = row['label'] + (' ' if row['suffix'] else '') + text
                    add('section_header' if 'level' in meta else 'text', text,
                        meta=meta, font_size=row['size_pt'], bold=row['bold'],
                        size_ratio=round(row['size_pt'] / body_size, 3)
                        if row['size_pt'] and body_size else None)
            for blip in block.iter(A + 'blip'):
                relationship = rels.get(blip.get(R + 'embed') or blip.get(R + 'link'))
                if relationship is None or relationship.get('TargetMode') == 'External':
                    warnings.append('외부/미확인 그림은 다운로드하지 않았습니다; 원문 대조 필요')
                    continue
                target = posixpath.normpath(posixpath.join('word', relationship.get('Target', '')))
                if not target.startswith('word/media/'):
                    raise ValueError('DOCX unexpected image relationship: ' + target)
                raw = archive.read(target)
                suffix = Path(target).suffix.lower()
                mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif', '.bmp': 'image/bmp', '.tiff': 'image/tiff'}.get(suffix)
                image = add('picture', meta={'native_media': target, 'has_image': bool(mime)})
                if mime:
                    images[image.index] = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode()
                else:
                    warnings.append('미지원 그림 형식 ' + suffix + ': 픽셀 검수 미확인')
        if list(body.iter(ox.W + 'object')):
            warnings.append('DOCX 포함 OLE 객체는 해석하지 않았습니다; 원문 대조 필요')
        if list(body.iter(ox.W + 'altChunk')):
            raise ValueError('DOCX altChunk content requires conversion; refusing silent omission')
        for name in ('footnotes', 'endnotes'):
            notes = ox._read(archive, 'word/' + name + '.xml')
            if notes is not None:
                for note in notes:
                    if int(note.get(ox.W + 'id', '0')) <= 0:
                        continue
                    text = '\n'.join(ox._text(p) for p in note.iter(ox.W + 'p')).strip()
                    if text:
                        add('text', text, meta={'docx_note': name, 'note_id': note.get(ox.W + 'id')})
        warnings.append('DOCX 지면은 합성 좌표입니다; Word 원래 페이지/머리말/꼬리말 배치와 다를 수 있습니다')
    if not elements:
        raise ValueError('DOCX has no readable paragraphs/tables/images')
    return ParseResult(path=str(path), doc_id=hashlib.sha256(path.read_bytes()).hexdigest()[:12],
                       parser=VERSION + ' (docx, tables=native)', born_digital=True, elements=elements, images=images,
                       warnings=list(dict.fromkeys(warnings)), stats={
                           'elements': len(elements), 'tables': sum(e.is_table for e in elements),
                           'pictures': sum(e.is_picture for e in elements), 'pictures_with_image': len(images),
                           'docx_paragraphs': sum(bool(r.get('text', '').strip()) for r in rows),
                           'docx_matched': sum(bool(r.get('text', '').strip()) for r in rows),
                           'headings_with_level': sum(bool(e.meta.get('level')) for e in elements)})
