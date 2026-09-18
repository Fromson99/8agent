"""내규 형태의 합성 DOCX — Word 가 계층을 표현하는 방식별로, 정답 트리와 함께 만든다.

사용자 제공 가짜 내규(위험관리기준시행세칙·투자및인수위험관리지침·MOCK-IR)는 번호를 모두
손으로 쳤다. 현장 내규는 Word 자동 번호·들여쓰기로 계층을 그릴 수 있어 그 변형을 만든다.
외부 라이브러리 없이 OOXML 을 직접 쓴다 — 무엇이 파일에 선언됐는지가 곧 시험 대상이다.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
CT = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
      '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
SECT = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'

FAMILY = {'편': 'kr_편', '장': 'kr_장', '절': 'kr_절', '조': 'kr_article', '항': 'circled', '호': 'dot_number:1', '목': 'hangul_dot'}
CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮'
GANADA = '가나다라마바사아자차카타파하'

# 조문 뼈대: (단위, 제목/본문). 편·장·절은 번호가 편마다 다시 1부터 — 실제 규정 그대로.
CLAUSES = [
    ('조', '(목적) 이 기준은 회사의 위험관리에 필요한 사항을 정함을 목적으로 한다.'),
    ('조', '(정의) 이 기준에서 사용하는 용어의 뜻은 다음과 같다.'),
    ('호', '"위험"이란 손실이 발생할 가능성을 말한다.'),
    ('호', '"한도"란 위험관리위원회가 정한 최대 노출액을 말한다.'),
    ('목', '거래상대방별 한도'), ('목', '상품별 한도'),
    ('조', '(적용범위) 이 기준은 회사의 모든 부서에 적용한다.'),
    ('항', '위험관리위원회는 매 분기 1회 이상 소집한다.'),
    ('항', '위원장은 필요한 경우 임시회의를 소집할 수 있다.'),
    ('호', '긴급한 손실 발생 시'), ('호', '감독당국의 요청이 있는 경우'),
    ('항', '회의 결과는 이사회에 보고한다.'),
]


def outline(with_parts=True):
    """정답 순서열: [(단위, 번호, 본문)] — 번호는 사람이 읽는 표기."""
    parts = [('편', 1, '총칙'), ('편', 2, '위험관리 조직')] if with_parts else [(None, 0, '')]
    seq, article = [], 0
    for part_no, (unit, n, title) in enumerate(parts, 1):
        if unit:
            seq.append(('편', f'제{n}편', title))
        for chap in (1, 2):
            seq.append(('장', f'제{chap}장', '총칙' if chap == 1 else '운영'))
            for sec in (1, 2):
                if with_parts:
                    seq.append(('절', f'제{sec}절', '통칙' if sec == 1 else '세부'))
                counters = {}
                for u, text in CLAUSES:
                    if u == '조':
                        article += 1
                        counters = {}
                        seq.append(('조', f'제{article}조', text))
                        continue
                    counters[u] = counters.get(u, 0) + 1
                    for deeper in {'항': ('호', '목'), '호': ('목',), '목': ()}[u]:
                        counters.pop(deeper, None)
                    n = counters[u]
                    label = {'항': CIRCLED[n - 1], '호': f'{n}.', '목': f'{GANADA[n - 1]}.'}[u]
                    seq.append((u, label, text))
    return seq


def truth_nodes(seq):
    """정답 트리 → 채점기가 읽는 노드 목록(family·surface·parent)."""
    order = ['편', '장', '절', '조', '항', '호', '목']
    stack, nodes = {}, []
    for i, (u, label, _) in enumerate(seq):
        lvl = order.index(u)
        parent = next((stack[x] for x in reversed(order[:lvl]) if x in stack), None)
        nodes.append({'id': i, 'parent': parent, 'family': FAMILY[u], 'surface': label, 'block': i})
        stack[u] = i
        for x in order[lvl + 1:]:
            stack.pop(x, None)
    return nodes


def _p(text, ppr=''):
    esc = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return f'<w:p>{"<w:pPr>" + ppr + "</w:pPr>" if ppr else ""}<w:r><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'


def _lvl(ilvl, fmt, text, left, hanging=400):
    return (f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/>'
            f'<w:suff w:val="space"/><w:pPr><w:ind w:left="{left}" w:hanging="{hanging}"/></w:pPr></w:lvl>')


def _num(abstracts, nums):
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {NS}>' + ''.join(abstracts)
            + ''.join(nums) + '</w:numbering>')


STYLES_PLAIN = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}>'
                '<w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="20"/></w:rPr></w:rPrDefault></w:docDefaults>'
                '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>')


def _write(path, body, numbering, styles=STYLES_PLAIN):
    doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{body}{SECT}</w:body></w:document>'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', CT)
        z.writestr('_rels/.rels', RELS)
        z.writestr('word/_rels/document.xml.rels', DOC_RELS)
        z.writestr('word/document.xml', doc)
        z.writestr('word/numbering.xml', numbering)
        z.writestr('word/styles.xml', styles)


HEAD_TYPED = {'편': 0, '장': 0, '절': 0}


def build(path: Path, variant: str, with_parts=True):
    """variant:
    typed_flat     번호를 손으로 치고 들여쓰기 없음 (제공 샘플과 같은 방식)
    typed_indent   번호를 손으로 치고 w:ind 로만 층을 그림
    auto_multilevel 조·항·호·목이 하나의 다단계 자동 번호 (제%1조 / ① / %3. / 가.)
    auto_restart   조는 손으로, 항·호·목은 자동 번호 — 조마다 startOverride 로 다시 시작
    style_linked   번호가 문단 스타일에 연결(numPr 이 스타일에만 있음)
    """
    seq = outline(with_parts)
    body, abstracts, nums = [_p('위험관리기준 (합성 ' + variant + ')')], [], []
    indent = {'조': 0, '항': 400, '호': 800, '목': 1200}
    if variant in ('auto_multilevel', 'style_linked'):
        abstracts.append('<w:abstractNum w:abstractNumId="0">' + _lvl(0, 'decimal', '제%1조', 0, 0)
                         + _lvl(1, 'decimalEnclosedCircle', '%2', 400) + _lvl(2, 'decimal', '%3.', 800)
                         + _lvl(3, 'ganada', '%4.', 1200) + '</w:abstractNum>')
        nums.append('<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>')
    if variant == 'auto_restart':
        abstracts.append('<w:abstractNum w:abstractNumId="0">' + _lvl(0, 'decimalEnclosedCircle', '%1', 400)
                         + _lvl(1, 'decimal', '%2.', 800) + _lvl(2, 'ganada', '%3.', 1200) + '</w:abstractNum>')
    styles = STYLES_PLAIN
    if variant == 'style_linked':
        lv = ''.join(f'<w:style w:type="paragraph" w:styleId="L{i}"><w:name w:val="List {i}"/><w:basedOn w:val="Normal"/>'
                     f'<w:pPr><w:numPr><w:ilvl w:val="{i}"/><w:numId w:val="1"/></w:numPr></w:pPr></w:style>' for i in range(4))
        styles = STYLES_PLAIN.replace('</w:styles>', lv + '</w:styles>')
    level = {'조': 0, '항': 1, '호': 2, '목': 3}
    num_id = 1
    for u, label, text in seq:
        if u in HEAD_TYPED:
            body.append(_p(f'{label} {text}', '<w:jc w:val="center"/>'))
            continue
        if variant in ('typed_flat', 'typed_indent'):
            ppr = f'<w:ind w:left="{indent[u] + 400}" w:hanging="400"/>' if variant == 'typed_indent' and u != '조' else ''
            body.append(_p(f'{label} {text}', ppr))
        elif variant == 'auto_multilevel':
            body.append(_p(text, f'<w:numPr><w:ilvl w:val="{level[u]}"/><w:numId w:val="1"/></w:numPr>'))
        elif variant == 'style_linked':
            body.append(_p(text, f'<w:pStyle w:val="L{level[u]}"/>'))
        elif variant == 'auto_restart':
            if u == '조':
                num_id += 1          # 조마다 새 목록 인스턴스, 1부터 다시
                nums.append(f'<w:num w:numId="{num_id}"><w:abstractNumId w:val="0"/>'
                            f'<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>')
                body.append(_p(f'{label} {text}'))
            else:
                body.append(_p(text, f'<w:numPr><w:ilvl w:val="{level[u] - 1}"/><w:numId w:val="{num_id}"/></w:numPr>'))
    _write(path, ''.join(body), _num(abstracts, nums), styles)
    return truth_nodes(seq)


VARIANTS = ('typed_flat', 'typed_indent', 'auto_multilevel', 'auto_restart', 'style_linked')


def paths(nodes):
    """노드 목록 → 원문 순서의 (조상 단위·표기 …, 자기 단위·표기) 경로. 채점용."""
    unit = {v: k for k, v in FAMILY.items()}
    unit['hangul_jamo'] = '목'
    by = {n['id']: n for n in nodes}
    out = []
    for n in sorted(nodes, key=lambda n: (n.get('block') or 0, n['id'])):
        if n.get('family') not in unit:
            continue
        chain, cur = [], n
        while cur is not None:
            if cur.get('family') in unit:
                chain.append((unit[cur['family']], (cur.get('surface') or '').replace(' ', '')))
            cur = by.get(cur.get('parent'))
        out.append(tuple(reversed(chain)))
    return out
