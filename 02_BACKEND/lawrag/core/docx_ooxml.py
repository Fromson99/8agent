"""DOCX 원본 XML(OOXML)이 선언한 것을 요소에 되살린다 — 자동 번호, 들여쓰기, 글자 크기.

docling 의 msword 경로는 문단 글자와 표만 준다. 한국 내규에서 계층을 말하는 두 신호가
거기서 사라진다(실측 2026-09-18, 합성 docx):

1. **Word 자동 번호.** `제%1조` 는 살지만 `①`(decimalEnclosedCircle)·`가.`(ganada) 는
   통째로 빠지고, 3단계 `%3.` 는 `1.1.1.` 로 바뀐다. 마커가 없으면 구조화기는 항·목을
   볼 수 없다. 여기서 numbering.xml 의 형식·표시 문자열대로 번호를 다시 그린다.
2. **들여쓰기(w:ind)와 목록 수준(w:ilvl).** 요소 메타가 비어 합성 지면이 모두 같은 자리에
   찍혔고, 사다리의 들여쓰기 증거가 동률로 침묵했다. 문단의 실제 왼쪽 시작점을 싣는다.

추론이 아니라 독해다: 값은 모두 파일에 선언된 것이고, 선언이 없으면 싣지 않는다.
판정은 여전히 마커와 사다리가 한다 — 여기 값은 그 증거다.
"""
from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
TWIPS_PER_PT = 20.0

_CIRCLED = [chr(0x2460 + i) for i in range(20)] + [chr(0x3251 + i) for i in range(15)] \
    + [chr(0x32B1 + i) for i in range(15)]
_PAREN = [chr(0x2474 + i) for i in range(20)]            # ⑴…⒇
_FULLSTOP = [chr(0x2488 + i) for i in range(20)]         # ⒈…⒛
_GANADA = '가나다라마바사아자차카타파하'
_CHOSUNG = 'ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ'
_KDIGIT = '영일이삼사오육칠팔구'
_HANJA = '〇一二三四五六七八九'
_NATIVE = ['', '하나', '둘', '셋', '넷', '다섯', '여섯', '일곱', '여덟', '아홉']
_NATIVE_TENS = ['', '열', '스물', '서른', '마흔', '쉰', '예순', '일흔', '여든', '아흔']
_GAN = '甲乙丙丁戊己庚辛壬癸'


def _val(el, name='val'):
    return None if el is None else el.get(W + name)


def _on(el) -> Optional[bool]:
    """w:b 같은 토글. 없으면 None(상속), 있으면 val 이 0/false/off 가 아닌 한 True."""
    if el is None:
        return None
    return (_val(el) or 'true').lower() not in ('0', 'false', 'off')


def _roman(n: int) -> str:
    out = ''
    for v, s in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'),
                 (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
        while n >= v:
            out, n = out + s, n - v
    return out


def _letter(n: int) -> str:
    # Word: A..Z, AA..ZZ, AAA… (같은 글자 반복)
    return chr(ord('A') + (n - 1) % 26) * ((n - 1) // 26 + 1)


def _korean_counting(n: int) -> str:
    if n <= 0:
        return str(n)
    out = ''
    for unit, word in ((1000, '천'), (100, '백'), (10, '십')):
        q, n = divmod(n, unit)
        if q:
            out += ('' if q == 1 else _KDIGIT[q]) + word
    return out + (_KDIGIT[n] if n else '')


def fmt(n: int, num_fmt: str) -> str:
    """한 수준의 번호를 numFmt 대로. 모르는 형식은 아라비아 숫자로 물러선다."""
    f = num_fmt or 'decimal'
    if f == 'none':
        return ''
    if f == 'decimalZero':
        return f'{n:02d}'
    if f == 'upperRoman':
        return _roman(n)
    if f == 'lowerRoman':
        return _roman(n).lower()
    if f == 'upperLetter':
        return _letter(n)
    if f == 'lowerLetter':
        return _letter(n).lower()
    if f in ('decimalEnclosedCircle', 'decimalEnclosedCircleChinese'):
        return _CIRCLED[n - 1] if 1 <= n <= len(_CIRCLED) else str(n)
    if f == 'decimalEnclosedParen':
        return _PAREN[n - 1] if 1 <= n <= 20 else f'({n})'
    if f == 'decimalEnclosedFullstop':
        return _FULLSTOP[n - 1] if 1 <= n <= 20 else f'{n}.'
    if f == 'ganada':
        return _GANADA[(n - 1) % 14]
    if f == 'chosung':
        return _CHOSUNG[(n - 1) % 14]
    if f == 'koreanDigital':
        return ''.join(_KDIGIT[int(d)] for d in str(n))
    if f == 'koreanDigital2':
        return ''.join(_HANJA[int(d)] for d in str(n))
    if f == 'koreanCounting':
        return _korean_counting(n)
    if f == 'koreanLegal':
        return (_NATIVE_TENS[n // 10] + _NATIVE[n % 10]) if 1 <= n <= 99 else str(n)
    if f == 'decimalFullWidth':
        return ''.join(chr(0xFF10 + int(d)) for d in str(n))
    if f == 'ideographTraditional':
        return _GAN[(n - 1) % 10]
    return str(n)


class _Styles:
    def __init__(self, root):
        self.by_id, self.default_para = {}, None
        self.default_sz = None
        if root is None:
            return
        rpr = root.find(f'{W}docDefaults/{W}rPrDefault/{W}rPr')
        if rpr is not None and _val(rpr.find(W + 'sz')):
            self.default_sz = int(_val(rpr.find(W + 'sz'))) / 2
        for s in root.findall(W + 'style'):
            sid = s.get(W + 'styleId')
            self.by_id[sid] = s
            if s.get(W + 'type') == 'paragraph' and _on_default(s):
                self.default_para = sid

    def chain(self, sid):
        seen = []
        sid = sid or self.default_para
        while sid and sid in self.by_id and sid not in seen:
            seen.append(sid)
            sid = _val(self.by_id[sid].find(W + 'basedOn'))
        return [self.by_id[s] for s in seen]

    def ppr(self, sid, tag):
        for s in self.chain(sid):
            el = s.find(f'{W}pPr/{W}{tag}')
            if el is not None:
                return el
        return None

    def rpr(self, sid, tag):
        for s in self.chain(sid):
            el = s.find(f'{W}rPr/{W}{tag}')
            if el is not None:
                return el
        return None


def _on_default(style) -> bool:
    return (style.get(W + 'default') or '').lower() in ('1', 'true', 'on')


class _Numbering:
    """numbering.xml → 문단마다 Word 가 그리는 번호 문자열. 카운터는 목록(abstractNum)이
    소유하고, startOverride 가 있는 num 은 그 수준을 처음 쓸 때 다시 시작한다."""

    def __init__(self, root):
        self.abstract, self.nums = {}, {}
        self.counters: dict[str, list] = {}
        self.restarted: set = set()
        if root is None:
            return
        for a in root.findall(W + 'abstractNum'):
            self.abstract[a.get(W + 'abstractNumId')] = {
                int(l.get(W + 'ilvl')): l for l in a.findall(W + 'lvl')}
        for n in root.findall(W + 'num'):
            overrides = {}
            for o in n.findall(W + 'lvlOverride'):
                overrides[int(o.get(W + 'ilvl'))] = o
            self.nums[n.get(W + 'numId')] = (_val(n.find(W + 'abstractNumId')), overrides)

    def level(self, num_id, ilvl):
        abstract_id, overrides = self.nums.get(num_id, (None, {}))
        o = overrides.get(ilvl)
        if o is not None and o.find(W + 'lvl') is not None:
            return abstract_id, o.find(W + 'lvl'), o
        return abstract_id, self.abstract.get(abstract_id, {}).get(ilvl), o

    def _start(self, num_id, ilvl):
        abstract_id, lvl, o = self.level(num_id, ilvl)
        if o is not None and _val(o.find(W + 'startOverride')):
            return int(_val(o.find(W + 'startOverride')))
        return int(_val(lvl.find(W + 'start')) or 1) if lvl is not None else 1

    def render(self, num_id, ilvl):
        """→ (표시 문자열, numFmt, 레벨 요소) 또는 None(번호 없음·numId 0)."""
        if not num_id or num_id == '0' or num_id not in self.nums:
            return None
        abstract_id, lvl, override = self.level(num_id, ilvl)
        if lvl is None:
            return None
        counters = self.counters.setdefault(abstract_id, [None] * 9)
        if override is not None and _val(override.find(W + 'startOverride')) \
                and (num_id, ilvl) not in self.restarted:
            self.restarted.add((num_id, ilvl))
            counters[ilvl] = None
        counters[ilvl] = self._start(num_id, ilvl) if counters[ilvl] is None else counters[ilvl] + 1
        for k in range(ilvl + 1, 9):
            counters[k] = None
        legal = lvl.find(W + 'isLgl') is not None
        text = _val(lvl.find(W + 'lvlText')) or ''
        num_fmt = _val(lvl.find(W + 'numFmt')) or 'decimal'
        if num_fmt == 'bullet':
            # 기호 글꼴의 사설 영역 문자는 화면 밖에서 뜻이 없다 — 가운뎃점으로
            label = ''.join('•' if 0xE000 <= ord(ch) <= 0xF8FF else ch for ch in text)
        else:
            def sub(m):
                k = int(m.group(1)) - 1
                _, lk, _ = self.level(num_id, k)
                n = counters[k] if counters[k] is not None else self._start(num_id, k)
                f = 'decimal' if (legal and k < ilvl) else (_val(lk.find(W + 'numFmt')) if lk is not None else 'decimal')
                return fmt(n, f)
            label = re.sub(r'%([1-9])', sub, text)
        return label, num_fmt, lvl


def _read(z, name):
    try:
        return ET.fromstring(z.read(name))
    except KeyError:
        return None


def _blocks(body):
    """본문 순서대로 최상위 문단과 표. 표 안의 문단은 표 요소가 이미 가진다."""
    for child in body:
        if child.tag in (W + 'p', W + 'tbl'):
            yield child
        elif child.tag == W + 'sdt':
            content = child.find(W + 'sdtContent')
            if content is not None:
                yield from _blocks(content)


def _text(p) -> str:
    out = []
    for el in p.iter():
        if el.tag == W + 't':
            out.append(el.text or '')
        elif el.tag == W + 'tab':
            out.append('\t')
        elif el.tag in (W + 'br', W + 'cr'):
            out.append('\n')
    return ''.join(out)


def _twips(ind, name, chars_name, size_pt):
    if ind is None:
        return None
    v = ind.get(W + name)
    if v is not None:
        return float(v)
    c = ind.get(W + chars_name)
    if c is not None and size_pt:
        return float(c) / 100.0 * size_pt * TWIPS_PER_PT
    return None


def read(path) -> list[dict]:
    """문단마다 {text, label, num_fmt, ilvl, suffix, start_twips, left_twips, size_pt, bold, outline}."""
    z = zipfile.ZipFile(path)
    doc = _read(z, 'word/document.xml')
    if doc is None:
        return []
    styles = _Styles(_read(z, 'word/styles.xml'))
    numbering = _Numbering(_read(z, 'word/numbering.xml'))
    body = doc.find(W + 'body')
    out = []
    for position, p in enumerate(_blocks(body if body is not None else [])):
        if p.tag == W + 'tbl':
            out.append({'table': True, 'position': position})
            continue
        ppr = p.find(W + 'pPr')
        sid = _val(ppr.find(W + 'pStyle')) if ppr is not None else None
        num_pr = ppr.find(W + 'numPr') if ppr is not None else None
        if num_pr is None:
            num_pr = styles.ppr(sid, 'numPr')
        num_id = _val(num_pr.find(W + 'numId')) if num_pr is not None else None
        ilvl = int(_val(num_pr.find(W + 'ilvl')) or 0) if num_pr is not None else None
        # 글자 크기·굵기: 글자 수로 가중한 최빈값 — 한두 글자 강조에 흔들리지 않게
        sizes, bold_chars, total = Counter(), 0, 0
        for r in p.iter(W + 'r'):
            t = ''.join(x.text or '' for x in r.iter(W + 't'))
            if not t.strip():
                continue
            rpr = r.find(W + 'rPr')
            sz = _val(rpr.find(W + 'sz')) if rpr is not None else None
            sz = float(sz) / 2 if sz else (float(_val(styles.rpr(sid, 'sz'))) / 2 if styles.rpr(sid, 'sz') is not None
                                           else styles.default_sz)
            b = _on(rpr.find(W + 'b')) if rpr is not None else None
            b = _on(styles.rpr(sid, 'b')) if b is None else b
            n = len(t.strip())
            if sz:
                sizes[sz] += n
            bold_chars += n if b else 0
            total += n
        size_pt = sizes.most_common(1)[0][0] if sizes else styles.default_sz
        rendered = numbering.render(num_id, ilvl) if num_id else None
        # 들여쓰기: 문단 직접 > 번호 수준 > 스타일 (Word 의 우선순위)
        ind = ppr.find(W + 'ind') if ppr is not None else None
        sources = [ind]
        if rendered:
            sources.append(rendered[2].find(f'{W}pPr/{W}ind'))
        sources.append(styles.ppr(sid, 'ind'))
        left = first = None
        for src in sources:
            if src is None:
                continue
            if left is None:
                left = _twips(src, 'left', 'leftChars', size_pt)
                left = _twips(src, 'start', 'startChars', size_pt) if left is None else left
            if first is None:
                h = _twips(src, 'hanging', 'hangingChars', size_pt)
                f = _twips(src, 'firstLine', 'firstLineChars', size_pt)
                first = -h if h is not None else f
        outline = ppr.find(W + 'outlineLvl') if ppr is not None else None
        outline = outline if outline is not None else styles.ppr(sid, 'outlineLvl')
        suffix = '\t'
        if rendered is not None:
            s = _val(rendered[2].find(W + 'suff'))
            suffix = {'space': ' ', 'nothing': ''}.get(s, '\t')
        out.append({
            'position': position, 'text': _text(p), 'label': rendered[0] if rendered else '',
            'num_fmt': rendered[1] if rendered else None, 'ilvl': ilvl if rendered else None,
            'suffix': suffix,
            'left_twips': left, 'start_twips': (left or 0.0) + (first or 0.0) if (left is not None or first is not None) else None,
            'size_pt': size_pt, 'bold': bool(total) and bold_chars * 2 > total,
            'outline_level': int(_val(outline)) if outline is not None and _val(outline) else None})
    return out


def text_width_pt(path) -> Optional[float]:
    """본문 영역 폭(pt) — 마지막 구역의 용지 폭 - 좌우 여백."""
    doc = _read(zipfile.ZipFile(path), 'word/document.xml')
    sect = doc.find(f'{W}body/{W}sectPr') if doc is not None else None
    if sect is None:
        return None
    size, mar = sect.find(W + 'pgSz'), sect.find(W + 'pgMar')
    try:
        w = float(size.get(W + 'w'))
        l = float(mar.get(W + 'left') or mar.get(W + 'start') or 0)
        r = float(mar.get(W + 'right') or mar.get(W + 'end') or 0)
    except (AttributeError, TypeError, ValueError):
        return None
    return (w - l - r) / TWIPS_PER_PT if w > l + r else None


_SPACE = re.compile(r'\s+')
# 짝짓기 창(문단 수). 실측 합성 목록의 뒤섞임은 한 묶음 안(수 문단)이었다.
MATCH_WINDOW = 40


def _norm(s: str) -> str:
    return _SPACE.sub('', s or '')


def enrich(path, elements) -> dict:
    """docling 요소에 OOXML 문단을 맞춰 번호·들여쓰기·글꼴을 싣고, **원문 순서로 되돌린다.**

    짝짓기는 글자로 한다 — docling 이 번호를 앞에 붙이거나 빼므로 **문단 글자가 요소
    글자의 꼬리**인지를 본다. 같은 글자 문단이 여럿이면(반복 조문, `삭제`) 직전 짝 뒤의
    가장 가까운 것을 고른다. 짝이 없는 요소는 건드리지 않는다.

    docling 은 중첩 목록을 묶음째 내보내며 순서를 바꾼다(실측: `나.` 가 `가.` 앞). 파일의
    본문 순서가 정답이므로 짝지은 요소를 그 순서로 다시 세운다 — 순서가 틀리면 사다리의
    리셋·덮음 증거가 통째로 오염된다. 요소 목록은 제자리에서 바뀌고 index 가 다시 매겨진다.
    반환 통계의 `index_map`(옛 index → 새 index)은 호출부가 그림 참조를 옮기는 데 쓴다.
    """
    rows = read(path)
    paras = [p for p in rows if not p.get('table') and _norm(p['text'])]
    tables = [p['position'] for p in rows if p.get('table')]
    sizes = Counter()
    for p in paras:
        if p['size_pt']:
            sizes[p['size_pt']] += len(_norm(p['text']))
    body_size = sizes.most_common(1)[0][0] if sizes else None
    width = text_width_pt(path)
    by_text: dict[str, list[int]] = {}
    for i, p in enumerate(paras):
        by_text.setdefault(_norm(p['text']), []).append(i)
    # 요소마다 짝 후보 글자(문단 글자가 요소 글자의 꼬리) — docling 이 붙인 번호는 앞에 있다
    keys = {}
    for e in elements:
        if getattr(e, 'table', None) is not None or not getattr(e, 'text', ''):
            continue
        target = _norm(e.text)
        key = next((target[cut:] for cut in range(0, min(25, len(target))) if target[cut:] in by_text), None)
        if key:
            keys[id(e)] = key
    # 1차: 같은 글자의 요소와 문단 수가 같으면 서로 순서대로 짝짓는다. docling 은 목록을
    # 묶음째 옮기지만(실측 56문단 거리) 같은 글자끼리의 앞뒤는 지킨다.
    assigned: dict[int, int] = {}
    groups: dict[str, list] = {}
    for e in elements:
        if id(e) in keys:
            groups.setdefault(keys[id(e)], []).append(e)
    for key, els in groups.items():
        if len(els) == len(by_text[key]):
            for e, i in zip(els, by_text[key]):
                assigned[id(e)] = i
    used = set(assigned.values())
    # 2차: 수가 다른 글자(표 속 글이 문단으로도 나온 경우 등)는 앞서 짝지은 자리 근처에서만
    last = -1
    for e in elements:
        if id(e) in assigned:
            last = assigned[id(e)]
            continue
        if id(e) not in keys:
            continue
        found = [i for i in by_text[keys[id(e)]] if i not in used]
        near = [i for i in found if last - MATCH_WINDOW <= i <= last + MATCH_WINDOW] if last >= 0 else found
        if not near:
            continue
        after = [i for i in near if i > last]
        hit = min(after) if after else max(near)
        assigned[id(e)] = hit
        used.add(hit)
        last = hit
    matched = restored = indented = 0
    position: dict[int, float] = {}
    docling_tables = [e for e in elements if getattr(e, 'table', None) is not None]
    if len(docling_tables) == len(tables):
        for e, pos in zip(docling_tables, tables):
            position[id(e)] = pos
    for e in elements:
        hit = assigned.get(id(e))
        if hit is None:
            continue
        target = _norm(e.text)
        p = paras[hit]
        position[id(e)] = p['position']
        matched += 1
        if p['label']:
            new = p['label'] + (' ' if p['suffix'] else '') + p['text'].strip()
            if _norm(new) != target:
                restored += 1
            e.text = new
        if p['start_twips'] is not None:
            indented += 1
        e.font_size = p['size_pt']
        e.size_ratio = round(p['size_pt'] / body_size, 3) if p['size_pt'] and body_size else None
        e.bold = p['bold']
        e.meta = {**(e.meta or {}), 'docx': {
            k: p[k] for k in ('label', 'num_fmt', 'ilvl', 'left_twips', 'start_twips', 'outline_level')
            if p[k] is not None}}
    # 순서는 **짝지은 문단이 이어진 구간 안에서만** 되돌린다. 짝 없는 요소(표 속 글이
    # docling 에서 문단으로 나온 것, 그림)와 표는 칸막이다 — 그 너머로 옮길 근거가 없다.
    ordered, segment, order = [], [], []

    def flush():
        segment.sort(key=lambda t: (t[0], t[1]))
        ordered.extend(e for _, _, e in segment)
        order.extend(n for _, n, _ in segment)
        segment.clear()
    for n, e in enumerate(elements):
        pos = position.get(id(e)) if getattr(e, 'table', None) is None else None
        if pos is None:
            flush()
            ordered.append(e)
            order.append(n)
        else:
            segment.append((pos, n, e))
    flush()
    moved = sum(a is not b for a, b in zip(ordered, elements))
    displaced = _displaced(order)
    index_map = {}
    if moved:
        for new_index, e in enumerate(ordered):
            index_map[e.index] = new_index
            e.index = new_index
        elements[:] = ordered
    return {'docx_paragraphs': len(paras), 'docx_matched': matched,
            'docx_numbering_restored': restored, 'docx_indented': indented,
            'docx_reordered': displaced, 'docx_tables_positioned': len(docling_tables) == len(tables),
            'docx_text_width_pt': width, 'index_map': index_map}


def _displaced(order: list[int]) -> int:
    """원래 순서에서 자리를 옮긴 요소 수 = 전체 - 최장 증가 부분열."""
    import bisect
    tails: list[int] = []
    for x in order:
        k = bisect.bisect_left(tails, x)
        tails[k:k + 1] = [x]
    return len(order) - len(tails)
