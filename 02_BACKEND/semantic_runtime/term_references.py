"""Resolve explicit article and annex citations within a pinned document-version selection.

Exact named documents only. Ambiguous versions, ranges and sub-article targets
remain unresolved; no model, fuzzy title inference or legal applicability claim.

An article that says "「별표 3」에 따른다" is unusable unless the reader can reach
별표 3 itself: the numbers live in the annex, not in the sentence that cites it.
Annex units carry their label in the unit surface (별표 14의1 · 별지 제1호 · 참고 4-1),
so the same literal-citation rule that links 제N조 links them too.
"""
import json
import hashlib
import re
from .contracts import digest

ARTICLE = re.compile(r'제\s*\d+(?:\s*-\s*\d+)*\s*조(?:\s*의\s*\d+)?')
NAMED = re.compile(r'「([^」\n]+)」\s*$')
ANNEX_KINDS = '별표|별지|별첨|서식|부록|참고'
# `[별표 3]`, `별표 제3호`, `별지 제7호서식`, `참고 4-1` — 수집처마다 표기가 다르다.
ANNEX = re.compile(r'\[?\s*(' + ANNEX_KINDS + r')\s*제?\s*(\d+(?:\s*[-의]\s*\d+)*)\s*호?\s*(?:서식)?\s*\]?')
# 마디 머리가 스스로 밝히는 별표 이름 — 본문 인용과 같은 좌표로 접는다.
ANNEX_HEADING = re.compile(r'^\[?\s*(' + ANNEX_KINDS + r')\s*제?\s*(\d+(?:\s*[-의]\s*\d+)*)\s*호?\s*(?:서식)?\s*\]?')

def coordinate(text):
    return re.sub(r'\s+', '', text)


# 조 뒤에 붙는 하위 경로 — `제1항제2호의2가목`. 항·호·목이 모두 선택이다.
SUBPATH = re.compile(r'\s*(?:제\s*(\d+)\s*항)?\s*(?:제\s*(\d+)\s*호(?:\s*의\s*(\d+))?)?\s*(?:([가나다라마바사아자차카타파하])\s*목)?')
# 같은 조 안의 인용 — `제2항`, `같은 조 제3항`, `이 조 제1항제2호`. 앞에 조가 없을 때만.
BARE = re.compile(r'(?<![조\d])(?:(?:같은|이)\s*조\s*)?제\s*(\d+)\s*(항|호)(?:\s*의\s*(\d+))?')
HANGUL_ORDER = '가나다라마바사아자차카타파하'


def subpath(match):
    """정규식 매치 → 서수 경로. 항·호·목은 조에서부터 한 칸씩 내려간다."""
    path = []
    if match[1]:
        path.append([int(match[1])])
    if match[2]:
        path.append([int(match[2])] + ([int(match[3])] if match[3] else []))
    if match[4]:
        path.append([HANGUL_ORDER.index(match[4]) + 1])
    return path


def descend(tree, article_unit, path):
    """조 마디에서 서수로 내려간다. 마커 모양(①·1)·(1)·가.)은 보지 않는다.

    한국 법문은 인용이 조에서부터 빈칸 없이 이어진다(항이 없는 조의 `제4조제2호` 는
    조 바로 아래가 호다). 그래서 인용의 첫 칸을 조의 첫 하위 층에 맞춘다.
    """
    current, found = str(article_unit), []
    for ordinal in path:
        children = tree.get(current, [])
        hit = [c for c in children if c['ordinal'] == ordinal]
        if len(hit) != 1:
            return None
        current = hit[0]['unit_id']
        found.append(hit[0])
    return found


def blocks_under(tree, unit):
    """마디와 그 아래 모든 블록 — `제1항` 을 읽으면 그 항의 호까지 함께 읽는다."""
    out, stack = [], [unit]
    while stack:
        u = stack.pop()
        out.extend(u['block_ids'])
        stack.extend(tree.get(u['unit_id'], []))
    return sorted(set(out), key=lambda x: int(x) if str(x).isdigit() else x)


def unit_trees(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_unit_map'").fetchone():
        return {}
    trees = {}
    for sid, uid, parent, ordinal, surface, blocks in db.execute(
            'SELECT source_id,unit_id,parent_id,ordinal,surface,block_ids FROM source_unit_map'):
        trees.setdefault(sid, {}).setdefault(parent, []).append(
            {'unit_id': uid, 'ordinal': json.loads(ordinal) if ordinal else None,
             'surface': surface, 'block_ids': json.loads(blocks)})
    return trees


def annex_coordinate(kind, number):
    """`별지 제1호` 와 `별지1` 과 `[별지 제 1 호 서식]` 을 한 좌표로 모은다."""
    return kind + re.sub(r'\s+', '', number)


def compile_references(db):
    sources = [json.loads(r[0]) for r in db.execute('SELECT json FROM source ORDER BY id')]
    names, targets, annexes = {}, {}, {}
    for s in sources:
        # 문서 이름에 폴더 경로가 붙어도(`RAW > law > 상법`) 조문은 「상법」 이라고 부른다.
        # 맨 끝 마디가 문서 제목이다 — 같은 제목이 둘이면 아래에서 모호로 남는다.
        full = s['document_name'].strip()
        for name in {full, full.rsplit(' > ', 1)[-1].strip()}:
            names.setdefault(name, set()).add(s['document_id'])
        m = ARTICLE.match(s['heading'])
        if m:
            targets.setdefault((s['document_id'], coordinate(m[0])), []).append(s['id'])
        a = ANNEX_HEADING.match(s['heading'].strip())
        if a:
            annexes.setdefault((s['document_id'], annex_coordinate(a[1], a[2])), []).append(s['id'])
    trees = unit_trees(db)
    counts = {'total': 0, 'unresolved': 0}

    def provision(resolved, path):
        """조 인용에 항·호·목이 붙었으면 그 조 안의 실제 마디를 찾는다."""
        if not resolved or not path:
            return [] if resolved else None
        source = by_id[resolved[0]]
        tree = trees.get(resolved[0])
        if not tree or source.get('unit_id') is None:
            return None
        found = descend(tree, source['unit_id'], path)
        if not found:
            return None
        return [{'unit_id': u['unit_id'], 'surface': u['surface']} for u in found] + [
            {'block_ids': blocks_under(tree, found[-1])}]

    def record(s, b, text, start, end, loc, docname, resolved, units, reason, exact, hint, origin):
        target_units = [u for u in (units or []) if 'unit_id' in u]
        target_blocks = next((u['block_ids'] for u in (units or []) if 'block_ids' in u), [])
        resolution = exact if resolved else 'UNRESOLVED'
        ident = 'ref:' + digest([s['id'], b['block_id'], start, end, docname] + ([origin] if origin != 'raw_explicit_article_hint' else []))[:24]
        r = {'id': ident, 'source_id': s['id'], 'document_id': s['document_id'],
             'block_id': b['block_id'], 'source_text': text,
             'source_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
             'locator': loc, 'mention_start': start, 'mention_end': end,
             'document_name_hint': docname, 'target_source_ids': resolved,
             # 항·호·목까지 찾았으면 그 마디와 블록. READ 가 조 전체 대신 그 블록을 읽는다.
             'target_unit_path': [u['surface'] for u in target_units],
             'target_block_ids': target_blocks,
             'target_level': 'provision' if target_units else ('article' if resolved else None),
             'resolution': resolution, 'reason': reason,
             'navigation_hint': hint, 'origins': [origin], 'canonical_approval': False}
        db.execute('INSERT OR IGNORE INTO reference VALUES (?,?,?)', (ident, s['document_id'], json.dumps(r, ensure_ascii=False)))
        db.executemany('INSERT OR IGNORE INTO reference_end VALUES (?,?)', [(x, ident) for x in [s['id']] + resolved])
        counts['total'] += 1
        counts['unresolved'] += not bool(resolved)

    by_id = {s['id']: s for s in sources}

    def within_paragraph(article_sid, block_id):
        """블록이 조의 첫 하위 층(항) 안에 있고 그 항이 하위 마디를 가지면 그 항의 서수."""
        source, tree = by_id[article_sid], trees.get(article_sid)
        if not tree or source.get('unit_id') is None:
            return []
        for child in tree.get(str(source['unit_id']), []):
            if child['ordinal'] and tree.get(child['unit_id']) and block_id in blocks_under(tree, child):
                return [child['ordinal']]
        return []
    for s in sources:
        for b in s['blocks']:
            text = b['text']
            consumed = []
            for m in ARTICLE.finditer(text):
                # An article's own heading is structural metadata, not a reference.
                if b is s['blocks'][0] and m.start() == 0 and re.match(r'\s*\(', text[m.end():]):
                    continue
                prefix = text[:m.start()]
                named = NAMED.search(prefix)
                docname = named[1].strip() if named else None
                if not named:
                    matches = [name for name in names if re.search(r'(?<![가-힣A-Za-z0-9])' + re.escape(name) + r'\s*$', prefix)]
                    if matches:
                        docname = max(matches, key=len)
                loc = coordinate(m[0])
                sub = SUBPATH.match(text, m.end())
                path = subpath(sub)
                end = sub.end() if path else m.end()
                reason = None
                suffix = text[end:]
                if re.match(r'\s*(?:부터|내지|[~～∼])', suffix) or re.search(r'(?:부터|내지|[~～∼])\s*$', prefix):
                    reason = 'RANGE_OR_SUBARTICLE_UNRESOLVED'
                elif docname:
                    ids = names.get(docname, set())
                    if len(ids) != 1:
                        reason = 'DOCUMENT_MISSING' if not ids else 'DOCUMENT_VERSION_AMBIGUOUS'
                else:
                    # Unquoted named-law forms and chained foreign citations need review.
                    clause = re.split(r'[.。;\n]', prefix)[-1]
                    if re.search(r'(?:법|령|규칙|규정|세칙|지침)\s*$', clause) or '「' in clause:
                        reason = 'DOCUMENT_NAME_UNRESOLVED'
                    ids = {s['document_id']}
                resolved = []
                if reason is None:
                    did = next(iter(ids))
                    candidates = targets.get((did, loc), [])
                    if len(candidates) == 1 and (candidates[0] != s['id'] or path):
                        resolved = candidates
                    else:
                        reason = 'ARTICLE_MISSING_SELF_OR_AMBIGUOUS'
                units = provision(resolved, path)
                consumed.append((m.start(), end, {'article': resolved[0] if resolved else None,
                                                  'path': path, 'docname': docname}))
                if resolved and path and units is None:
                    reason = 'PROVISION_NOT_IN_STRUCTURE'   # 조까지는 이었고 항·호는 틀에 없다
                record(s, b, text, m.start(), end, coordinate(text[m.start():end]), docname, resolved, units, reason,
                    'EXACT_NAMED_DOCUMENT_ARTICLE' if docname else 'EXACT_SAME_DOCUMENT_ARTICLE',
                    '준용 단서' if '준용' in text else '인용 단서', 'raw_explicit_article_hint')
            # 조 없이 쓴 `제2항`·`제3호` — 어느 조의 것인지는 문맥이 정한다.
            #  · `제4조제1항 및 제2항` 처럼 접속어로 이어지면 바로 앞 인용의 조다.
            #  · 항 안에서 부르는 `제2호` 는 그 항의 호다.
            #  · 그 밖에는 이 조의 것이다. 조 마디가 아닌 곳(별표 등)에선 잇지 않는다.
            article_here = s['id'] if ARTICLE.match(s['heading']) else None
            for m in BARE.finditer(text):
                if any(a <= m.start() < z for a, z, _ in consumed):
                    continue
                before = [c for c in consumed if c[1] <= m.start()]
                gap = text[before[-1][1]:m.start()] if before else None
                if gap is not None and re.fullmatch(r'\s*(?:부터|내지|[~～∼])\s*', gap):
                    continue                                   # 범위 끝 — 앞 인용이 이미 범위로 남았다
                head = before[-1][2] if gap is not None and re.fullmatch(r'\s*(?:및|또는|과|와|이나|,|·|ㆍ)\s*', gap) else None
                owner = head['article'] if head else article_here
                if owner is None:
                    continue
                own = [int(m[1])] + ([int(m[3])] if m[3] else [])
                if head and m[2] == '호' and head['path']:
                    path = head['path'][:1] + [own]            # `제1항제1호 및 제2호`
                elif m[2] == '호' and owner == article_here and not head:
                    path = within_paragraph(owner, b['block_id']) + [own]
                else:
                    path = [own]
                if m[2] == '항':
                    more = re.match(r'\s*제\s*(\d+)\s*호(?:\s*의\s*(\d+))?', text[m.end():])
                    if more:
                        path.append([int(more[1])] + ([int(more[2])] if more[2] else []))
                units = provision([owner], path)
                docname = head.get('docname') if head else None
                consumed.append((m.start(), m.end(), {'article': owner, 'path': path, 'docname': docname}))
                record(s, b, text, m.start(), m.end(), coordinate(m[0]), docname,
                       [owner] if units else [], units,
                       None if units else 'PROVISION_NOT_IN_STRUCTURE',
                       'EXACT_SAME_ARTICLE_PROVISION' if owner == article_here else 'EXACT_CONTINUED_PROVISION',
                       '준용 단서' if '준용' in text else '인용 단서', 'raw_explicit_provision_hint')
            for m in ANNEX.finditer(text):
                # 별표 마디 자신의 머리는 구조 메타이지 인용이 아니다.
                if b is s['blocks'][0] and m.start() == 0:
                    continue
                prefix = text[:m.start()]
                named = NAMED.search(prefix)
                docname = named[1].strip() if named else None
                if not named:
                    matches = [name for name in names
                               if re.search(r'(?<![가-힣A-Za-z0-9])' + re.escape(name) + r'\s*$', prefix)]
                    if matches:
                        docname = max(matches, key=len)
                loc = annex_coordinate(m[1], m[2])
                reason = None
                ids = names.get(docname, set()) if docname else {s['document_id']}
                if docname and len(ids) != 1:
                    reason = 'DOCUMENT_MISSING' if not ids else 'DOCUMENT_VERSION_AMBIGUOUS'
                resolved = []
                if reason is None:
                    candidates = annexes.get((next(iter(ids)), loc), [])
                    if len(candidates) == 1 and candidates[0] != s['id']:
                        resolved = candidates
                    else:
                        reason = ('ANNEX_AMBIGUOUS' if len(candidates) > 1
                                  else 'ANNEX_BODY_NOT_IN_SELECTION')
                record(s, b, text, m.start(), m.end(), loc, docname, resolved, [], reason,
                       'EXACT_NAMED_DOCUMENT_ANNEX' if docname else 'EXACT_SAME_DOCUMENT_ANNEX',
                       '별표·서식 단서', 'raw_explicit_annex_hint')
    return counts['total'], counts['unresolved']
