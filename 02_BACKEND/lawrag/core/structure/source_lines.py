"""Split explicit numbered lines, retaining exact original text provenance.

Do not split tables, inline references, dates, or infer sub-line rectangles.
This is segmentation before structural selection, never tree repair/approval.
"""
from dataclasses import replace
import hashlib
import re

MARKER = re.compile(r'(?m)^[ \t]*(?:[①-⑳㉑-㉟㊱-㊿]|'
                    r'제\s*\d+(?:의\d+)?\s*[장절조항](?:\s|[.(（]|$)|'
                    r'\d{1,3}[.)](?=\s|[가-힣])|[가-하][.)](?=\s)|'
                    r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+[.．](?=\s))')


def split(blocks):
    result = []
    for block in blocks:
        starts = [m.start() for m in MARKER.finditer(block.text)] if block.kind == 'text' else []
        # A single ordinary paragraph stays untouched, including inline anchors.
        if len(starts) < 2:
            result.append(replace(block, idx=len(result)))
            continue
        boundaries = sorted({0, *starts, len(block.text)})
        source_sha = hashlib.sha256(block.text.encode('utf-8')).hexdigest()
        for lo, hi in zip(boundaries, boundaries[1:]):
            if not block.text[lo:hi].strip():
                continue
            result.append(replace(block, idx=len(result), text=block.text[lo:hi],
                source_range={'version': 'numbered-lines-v1', 'original_block': block.idx,
                              'element_index': block.element_index, 'characters': [lo, hi],
                              'source_text_sha256': source_sha,
                              'geometry': 'shared_original_bbox_not_subline_geometry'}))
    return result
