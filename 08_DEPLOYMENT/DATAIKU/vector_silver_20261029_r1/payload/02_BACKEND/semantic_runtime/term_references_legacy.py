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
BARE = re.compile(r'(?<![조\d])(?:(?:같은|이|동)\s*조\s*)?제\s*(\d+)\s*(항|호)(?:\s*의\s*(\d+))?')
HANGUL_ORDER = '가나다라마바사아자차카타파하'

ARTICLE_TEXT = r'제\s*\d+(?:\s*-\s*\d+)*\s*조(?:\s*의\s*\d+)?'
SUBLOC_TEXT = (r'(?:\s*제\s*\d+\s*항)?(?:\s*제\s*\d+\s*호(?:\s*의\s*\d+)?)?'
               r'(?:\s*[가나다라마바사아자차카타파하]\s*목)?')
BARE_LOC_TEXT = (r'(?:제\s*\d+\s*(?:항|호)(?:\s*의\s*\d+)?'
                 r'|[가나다라마바사아자차카타파하]\s*목)')
ARTICLE_RANGE = re.compile(
    r'(?P<start>' + ARTICLE_TEXT + SUBLOC_TEXT + r')\s*(?:부터|내지|[~～∼])\s*'
    r'(?P<end>(?:' + ARTICLE_TEXT + SUBLOC_TEXT + r'|' + BARE_LOC_TEXT + r'))\s*(?:까지)?')
BARE_RANGE = re.compile(
    r'(?P<start>' + BARE_LOC_TEXT + r')\s*(?:부터|내지|[~～∼])\s*'
    r'(?P<end>' + BARE_LOC_TEXT + r')\s*(?:까지)?')
BARE_ENDPOINT = re.compile(
    r'^(?:제\s*(?P<number>\d+)\s*(?P<role>항|호)(?:\s*의\s*(?P<branch>\d+))?'
    r'|(?P<letter>[가나다라마바사아자차카타파하])\s*목)$')


ROLE_ORDER = ('항', '호', '목')
# 틀의 층에 있어도 인용 대상이 아닌 계열 — 조 위 컨테이너, 번호 없는 글머리, 미구조 본문.
NOT_CITABLE = ('kr_article', 'kr_편', 'kr_장', 'kr_절', 'kr_관', 'annex', 'buchik', 'unstructured_text')


def frame_roles(ladder):
    """구조화가 세운 계층 틀(ladder) → 이 문서에서 항·호·목을 맡는 표기 계열.

    조 층 아래에서 처음 나타나는 순서대로 항→호→목이다. 법령 XML 은 계열 이름이 곧
    역할이고(circled=항), 추론 구조화는 실제 마커 계열(①·1.·가.)이 층을 받으므로
    어느 경로든 같은 규칙으로 읽힌다. 같은 층에 처음 나온 둘은 더 깊이까지 이어지는
    쪽을 아래 역할로 본다.
    """
    rungs = [r.get('families') or [] for r in (ladder or {}).get('rungs', [])]
    top = next((i for i, fams in enumerate(rungs) if 'kr_article' in fams), None)
    if top is None:
        return {'roles': {}}
    seen = {}
    for depth, fams in enumerate(rungs[top + 1:]):
        for fam in fams:
            if fam in NOT_CITABLE or fam.startswith('bullet'):
                continue
            first, _ = seen.get(fam, (depth, depth))
            seen[fam] = (first, depth)
    ordered = sorted(seen, key=lambda f: seen[f])
    return {'roles': {fam: ROLE_ORDER[i] for i, fam in enumerate(ordered[:len(ROLE_ORDER)])}}


def marker_shape(surface):
    """마디 표기 → 그 모양의 정규식. `1)`→숫자+`)`, `(1)`, `①`, `가.` … 문서에 실제로 쓰인 것만 쓴다."""
    surface = surface.strip()
    if not surface or len(surface) > 8:
        return None
    if re.fullmatch(r'[①-㊿]', surface):
        return r'[①-㊿]'
    out = ''
    for token in re.findall(r'\d+|[가나다라마바사아자차카타파하](?=[.)])|\S', surface):
        if token.isdigit():
            out += r'\d{1,3}'
        elif token in HANGUL_ORDER:
            out += '[' + HANGUL_ORDER + ']'
        else:
            out += re.escape(token)
        out += r'\s*'
    return out or None


def subpath(match):
    """정규식 매치 → (역할, 서수) 경로. `제1항제2호의2가목` → 항1·호2의2·목1."""
    path = []
    if match[1]:
        path.append(('항', [int(match[1])]))
    if match[2]:
        path.append(('호', [int(match[2])] + ([int(match[3])] if match[3] else [])))
    if match[4]:
        path.append(('목', [HANGUL_ORDER.index(match[4]) + 1]))
    return path


def descend(tree, article_unit, path, roles=None):
    """조 마디에서 (역할, 서수)로 내려간다. 역할은 이 문서 틀이 정한 계열로 가린다.

    `제4조제2호` 는 틀에서 호를 맡은 계열의 2번이다 — 조 아래에 항이 있으면 항 2번으로
    가지 않는다. 틀을 모르는 문서(역할표가 비었거나 계열이 없는 마디)만 서수로 찾는다.
    """
    current, found = str(article_unit), []
    for role, ordinal in path:
        children = tree.get(current, [])
        typed = [c for c in children if roles and (roles.get(c.get('family')) is not None)]
        if typed:
            hit = [c for c in typed if roles.get(c.get('family')) == role and c['ordinal'] == ordinal]
        else:
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
    columns = {r[1] for r in db.execute('PRAGMA table_info(source_unit_map)')}
    family = 'family' if 'family' in columns else 'NULL'
    for sid, uid, parent, ordinal, surface, blocks, fam in db.execute(
            'SELECT source_id,unit_id,parent_id,ordinal,surface,block_ids,' + family + ' FROM source_unit_map'):
        trees.setdefault(sid, {}).setdefault(parent, []).append(
            {'unit_id': uid, 'ordinal': json.loads(ordinal) if ordinal else None,
             'surface': surface, 'block_ids': json.loads(blocks), 'family': fam})
    return trees


def document_frames(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_frame'").fetchone():
        return {}
    return {d: json.loads(j).get('roles', {}) for d, j in db.execute('SELECT document_id,json FROM document_frame')}


# 문서가 스스로 선언한 약칭 — `「자본시장과 금융투자업에 관한 법률」(이하 "법"이라 한다)`,
# `같은 법 시행령(이하 "영"이라 한다)`. 선언이 명명 관례보다 앞선다.
DECLARED = re.compile(r'(?:「([^」]{2,80})」|(같은|동)\s*법\s*(시행령|시행규칙))[^()「」]{0,20}?\(\s*이하\s*[“"‘\']([^”"’\']{1,20})[”"’\']\s*(?:이?라\s*한다|라고\s*한다)')
NAMED_SUFFIX = re.compile(r'「([^」\n]+)」\s*(시행령|시행규칙)\s*$')
SELF_ALIAS = re.compile(r'(?<![가-힣])이\s*(법|영|규칙|규정|세칙|시행령|시행규칙|기준|지침|준칙|규준|약관)\s*$')
SAME_ALIAS = re.compile(r'(?<![가-힣])(?:동|같은)\s*(법|영|규칙|규정)?\s*(시행령|시행규칙)?\s*$')


def nospace(text):
    return re.sub(r'[\s·ㆍ]+', '', text or '')


def title_of(name):
    return (name or '').rsplit(' > ', 1)[-1].strip()


def convention_aliases(title):
    """법령 명명 관례로 정해지는 약칭. `X 시행령` 안의 `법` 은 X, `X 시행규칙` 안의 `영` 은 X 시행령."""
    out = {}
    for suffix in ('시행규칙', '시행령', '시행세칙'):
        if nospace(title).endswith(suffix):
            base = re.sub(r'\s*' + suffix + r'$', '', title).strip()
            if suffix == '시행세칙':
                out['규정'] = base
            else:
                out['법'] = base
                out['시행령'] = base + ' 시행령'
                out['시행규칙'] = base + ' 시행규칙'
                if suffix == '시행규칙':
                    out['영'] = base + ' 시행령'
            return out
    out['시행령'] = title + ' 시행령'
    out['시행규칙'] = title + ' 시행규칙'
    return out


def declared_aliases(blocks):
    out, last = {}, None
    for b in blocks:
        for m in DECLARED.finditer(b['text']):
            if m[1]:
                full = m[1].strip()
                last = full
            elif last:
                full = last + ' ' + m[3]
            else:
                continue
            out.setdefault(m[4].strip(), full)
    return out


def load_reference_inputs():
    """참조 해석이 쓰는 등록 입력 — 약칭 사전과 law.go.kr 위임 간선. 없으면 비운다."""
    from pathlib import Path
    import hashlib as _h
    try:
        from lawrag.platform.paths import data_path
        root = Path(data_path())
    except Exception:
        return {}, [], {}
    aliases, delegations, identity = {}, [], {}
    for name in ('aliases.json', 'delegation.json'):
        path = root / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        identity[name] = _h.sha256(raw).hexdigest()
        value = json.loads(raw)
        if name == 'aliases.json':
            aliases = {k: v for k, v in value.items() if isinstance(v, str)}
        else:
            delegations = [e for e in value.get('edges', []) if e.get('kind') in ('시행령', '시행규칙', '위임행정규칙')]
    return aliases, delegations, identity


def annex_coordinate(kind, number):
    """`별지 제1호` 와 `별지1` 과 `[별지 제 1 호 서식]` 을 한 좌표로 모은다."""
    return kind + re.sub(r'\s+', '', number)


def reference_targets(reference):
    """Return per-target extents, with a lossless v4 path and a v2/v3 fallback."""
    if isinstance(reference.get('targets'), list):
        return [dict(target) for target in reference['targets']]
    return [{'source_id': source_id,
             'unit_id': reference.get('target_unit_id'),
             'unit_path': reference.get('target_unit_path', []),
             'block_ids': reference.get('target_block_ids', []),
             'target_level': reference.get('target_level') or 'article'}
            for source_id in reference.get('target_source_ids', [])]


def compile_references(db, aliases=None, delegations=None):
    # Direct compiler tests and older callers may provide only the legacy tables.
    # The new tables are additive; legacy readers can keep using reference JSON and
    # reference_end while range-aware readers retain one extent per target.
    db.executescript('''
      CREATE TABLE IF NOT EXISTS reference_target(reference_id TEXT,ordinal INTEGER,source_id TEXT,unit_id TEXT,
        unit_path TEXT,block_ids TEXT,target_level TEXT,PRIMARY KEY(reference_id,ordinal));
      CREATE INDEX IF NOT EXISTS reference_target_source ON reference_target(source_id,reference_id);
      CREATE TABLE IF NOT EXISTS reference_candidate(reference_id TEXT,candidate_id TEXT,ordinal INTEGER,
        source_id TEXT,unit_id TEXT,unit_path TEXT,block_ids TEXT,target_level TEXT,basis TEXT,json TEXT,
        PRIMARY KEY(reference_id,candidate_id));
      CREATE TABLE IF NOT EXISTS reference_candidate_end(source_id TEXT,reference_id TEXT,candidate_id TEXT,
        PRIMARY KEY(source_id,reference_id,candidate_id));
    ''')
    from .reference_build import BuildSources, LiteralSuffixIndex, ReferenceWriter, ReferenceCheckpoint
    sources = BuildSources(db)
    writer = ReferenceWriter(db)
    checkpoint = ReferenceCheckpoint(db)
    names, targets, annexes = {}, {}, {}
    aliases = aliases or {}
    for s in sources.metadata():
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
    roles_of = document_frames(db)
    compact = {}
    for name, ids in names.items():
        compact.setdefault(nospace(name), set()).update(ids)
    title_by_doc = {s['document_id']: title_of(s['document_name']) for s in sources.metadata()}
    doc_aliases = {did: {**convention_aliases(title), **declared_aliases(sources.blocks(did))}
                   for did, title in title_by_doc.items()}
    doc_alias_indexes = {did: LiteralSuffixIndex(table) for did,table in doc_aliases.items()}
    registered_index = LiteralSuffixIndex(aliases)
    annex_titles = LiteralSuffixIndex(names)

    def lookup(name):
        """이름 → 문서. 띄어쓰기·가운뎃점 차이는 같은 이름으로 본다."""
        return names.get(name) or compact.get(nospace(name)) or set()

    def cited_document(s, prefix, last_named):
        """인용 바로 앞 말 → (문서 이름, 근거). 명시 > 선언 약칭 > 관례 > 등록 사전 > 이름 일치."""
        named = NAMED.search(prefix)
        if named:
            return named[1].strip(), 'named'
        m = NAMED_SUFFIX.search(prefix)
        if m:
            return m[1].strip() + ' ' + m[2], 'named'
        if SELF_ALIAS.search(prefix):
            return title_by_doc[s['document_id']], 'self'
        same = SAME_ALIAS.search(prefix)
        if same and last_named and (same[1] or same[2]):
            base = re.sub(r'\s*(시행령|시행규칙)$', '', last_named)
            return (base + ' ' + same[2]) if same[2] else last_named, 'same'
        own = doc_aliases.get(s['document_id'], {})
        for table, index, how in ((own, doc_alias_indexes[s['document_id']], 'declared'),
                                  (aliases, registered_index, 'registered')):
            key = index.match(prefix)
            if key is not None:
                return table[key], how
        # 이름 일치 — 띄어쓰기가 달라도(`독점규제및공정거래에관한법률`) 같은 이름이다.
        # 낱말 경계에서 시작하는 가장 긴 꼬리만 본다.
        window = prefix[-80:]
        for start in range(len(window)):
            if start and re.match(r'[가-힣A-Za-z0-9]', window[start - 1]):
                continue
            piece = nospace(window[start:])
            if len(piece) >= 2 and piece in compact:
                return window[start:].strip(), 'name'
        return None, None
    counts = checkpoint.counts()

    by_id = sources

    def provision(resolved, path):
        """조 인용에 항·호·목이 붙었으면 그 조 안의 실제 마디를 찾는다."""
        if not resolved or not path:
            return [] if resolved else None
        source = by_id[resolved[0]]
        tree = trees.get(resolved[0])
        if not tree or source.get('unit_id') is None:
            return None
        found = descend(tree, source['unit_id'], path, roles_of.get(source['document_id']))
        if not found:
            return None
        return [{'unit_id': u['unit_id'], 'surface': u['surface']} for u in found] + [
            {'block_ids': blocks_under(tree, found[-1])}]

    def source_extent(source, block_id):
        """인용 문장이 속한 조의 첫 하위 마디와 그 자손 블록을 고정한다.

        역참조는 대상 조 전체가 아니라 인용을 실제로 쓴 항(항이 없는 문서는 첫
        구조 마디)을 읽어야 한다. 구조가 없으면 witness 블록 하나로 좁혀 둔다.
        """
        tree = trees.get(source['id'])
        if tree and source.get('unit_id') is not None:
            for child in tree.get(str(source['unit_id']), []):
                block_ids = blocks_under(tree, child)
                if block_id in block_ids:
                    return {'unit_id': child['unit_id'], 'unit_path': [child['surface']],
                            'block_ids': block_ids, 'level': 'provision'}
        return {'unit_id': None, 'unit_path': [], 'block_ids': [block_id], 'level': 'block'}

    def explicit_role(text):
        """문언 자체가 밝힌 참조 역할만 분류한다. 사례 적용 판단은 하지 않는다."""
        if '단서에서' in text and '정하는 경우' in text and re.search(r'["”]?\s*란', text):
            return 'SPECIFIES_DELEGATED_CASES_OF'
        if '준용' in text:
            return 'APPLIES_MUTATIS_MUTANDIS'
        return 'CITES'

    def target_record(source_id, units=None):
        target_units = [u for u in (units or []) if 'unit_id' in u]
        target_blocks = next((u['block_ids'] for u in (units or []) if 'block_ids' in u), [])
        return {'source_id': source_id,
                'unit_id': target_units[-1]['unit_id'] if target_units else None,
                'unit_path': [u['surface'] for u in target_units],
                'block_ids': target_blocks,
                'target_level': 'provision' if target_units else 'article'}

    def record(s, b, text, start, end, loc, docname, resolved, units, reason, exact, hint, origin,
               basis=None, *, target_records=None):
        details = list(target_records if target_records is not None else
                       ([target_record(resolved[0], units)] if resolved and units and len(resolved) == 1 else
                        [target_record(source_id) for source_id in resolved]))
        # Candidate IDs are required to be one-to-one with canonical target coordinates.
        unique = {}
        for detail in details:
            key = (detail['source_id'], detail.get('unit_id'), tuple(detail.get('block_ids') or ()))
            unique.setdefault(key, detail)
        details = list(unique.values())
        resolved = list(dict.fromkeys(d['source_id'] for d in details))
        one = details[0] if len(details) == 1 else None
        source_part = source_extent(s, b['block_id'])
        resolution = exact if details else 'UNRESOLVED'
        if details:
            resolution_state = 'RESOLVED' if len(details) == 1 else 'MULTI_TARGET'
        elif reason in {'DOCUMENT_MISSING', 'ANNEX_BODY_NOT_IN_SELECTION', 'PROVISION_NOT_IN_STRUCTURE'}:
            resolution_state = 'DATA_GAP'
        else:
            resolution_state = 'UNKNOWN'
        ident = 'ref:' + digest([s['id'], b['block_id'], start, end, docname] + ([origin] if origin != 'raw_explicit_article_hint' else []))[:24]
        mention = text[start:end] if 0 <= start <= end <= len(text) else ''
        case_id = 'refcase:' + digest([s['id'], b['block_id'], start, end,
                                      hashlib.sha256(mention.encode()).hexdigest(), origin])[:32]
        witness_hash, witness_role = writer.witness(text, explicit_role)
        r = {'id': ident, 'source_id': s['id'], 'document_id': s['document_id'],
             'block_id': b['block_id'], 'source_text': text,
             'source_text_sha256': witness_hash,
             'mention_text': mention, 'mention_text_sha256': hashlib.sha256(mention.encode()).hexdigest(),
             'locator': loc, 'mention_start': start, 'mention_end': end,
             'document_name_hint': docname, 'target_source_ids': resolved,
             'targets': details, 'target_unit_ids': [d.get('unit_id') for d in details],
             # 문서를 어떻게 알았나: named·declared·registered·name·self·same·continued
             'document_hint_basis': basis if docname else None,
             # 역방향 탐색은 인용을 쓴 조 전체가 아니라 이 항/마디와 그 하위만 읽는다.
             'source_unit_id': source_part['unit_id'],
             'source_unit_path': source_part['unit_path'],
             'source_block_ids': source_part['block_ids'],
             'source_level': source_part['level'],
             # 항·호·목까지 찾았으면 그 마디와 블록. READ 가 조 전체 대신 그 블록을 읽는다.
             # Legacy singular extent is populated only when exactly one target exists.
             # Applying one extent to several targets would silently read the wrong unit.
             'target_unit_id': one.get('unit_id') if one else None,
             'target_unit_path': one.get('unit_path', []) if one else [],
             'target_block_ids': one.get('block_ids', []) if one else [],
             'target_level': one.get('target_level') if one else ('multi' if details else None),
             # 이 값은 명시 문언의 모양이지, 질문 사례에 대한 법률 결론이 아니다.
             'reference_role': witness_role,
             'reference_role_basis': 'explicit_text_frame',
             'resolution': resolution, 'resolution_state': resolution_state,
             'resolution_basis': 'deterministic' if details else None,
             'review_receipt_sha256': None, 'case_id': case_id, 'reason': reason,
             'navigation_hint': hint, 'origins': [origin], 'canonical_approval': False}
        writer.insert(r)
        db.executemany('INSERT OR IGNORE INTO reference_end VALUES (?,?)', [(x, ident) for x in [s['id']] + resolved])
        db.executemany('INSERT OR IGNORE INTO reference_target VALUES (?,?,?,?,?,?,?)', [
            (ident, ordinal, d['source_id'], d.get('unit_id'), json.dumps(d.get('unit_path') or [], ensure_ascii=False),
             json.dumps(d.get('block_ids') or [], ensure_ascii=False), d.get('target_level') or 'article')
            for ordinal, d in enumerate(details)])
        counts['total'] += 1
        counts['unresolved'] += not bool(details)

    # 문서마다 그 문서 틀이 실제로 쓰는 표기로 인용 패턴을 만든다.
    #  · 조 머리 모양: `제4조` 또는 `14.`
    #  · 하위 마디 모양: 그 문서의 항·호에 실제로 쓰인 `①`·`1)`·`(1)`·`1.`·`가.`
    # 조 머리 + 하위 마디를 이은 글자(`14.1)`, `제4조(1)`)가 그 문서 안 마디 좌표다.
    frames, shapes = {}, {}
    for s in sources.metadata():
        tree = trees.get(s['id'])
        if not tree or s.get('unit_id') is None:
            continue
        m = ARTICLE.match(s['heading'])
        head = coordinate(m[0]) if m else coordinate(s['heading'].split(' ', 1)[0])
        if not m and not re.fullmatch(r'\d{1,3}(?:-\d{1,2})?\.', head):
            continue
        doc = shapes.setdefault(s['document_id'], {'heads': set(), 'markers': set()})
        doc['heads'].add('article' if m else 'dotted')
        for child in tree.get(str(s['unit_id']), []):
            key = head + coordinate(child['surface'])
            frames.setdefault((s['document_id'], key), []).append((s['id'], [child]))
            doc['markers'].add(marker_shape(child['surface']))
            for grand in tree.get(child['unit_id'], []):
                frames.setdefault((s['document_id'], key + coordinate(grand['surface'])), []).append((s['id'], [child, grand]))
                doc['markers'].add(marker_shape(grand['surface']))
    patterns = {}
    for did, doc in shapes.items():
        markers = sorted(x for x in doc['markers'] if x)
        if not markers:
            continue
        heads = []
        if 'article' in doc['heads']:
            heads.append(ARTICLE.pattern)
        if 'dotted' in doc['heads']:
            heads.append(r'(?<![\d.)\w])\d{1,3}(?:-\d{1,2})?\s*\.')
        marker = '(?:' + '|'.join(markers) + ')'
        # 인용 뒤에는 조사·접속어가 온다. 목록 번호와 가르는 문서 무관 신호다.
        patterns[did] = re.compile('(?:' + '|'.join(heads) + r')\s*' + marker + r'(?:\s*' + marker + ')?'
                                   + r"(?=\s*(?:에|의|을|를|과|와|및|은|는|이|가|부터|까지|’|'|,|·|\.|\)))")

    def within_paragraph(article_sid, block_id):
        """블록이 조의 첫 하위 층(항) 안에 있고 그 항이 하위 마디를 가지면 그 항의 서수."""
        source, tree = by_id[article_sid], trees.get(article_sid)
        if not tree or source.get('unit_id') is None:
            return []
        roles = roles_of.get(source['document_id']) or {}
        for child in tree.get(str(source['unit_id']), []):
            if child['ordinal'] and tree.get(child['unit_id']) and block_id in blocks_under(tree, child):
                role = roles.get(child.get('family'), '항')
                return [(role, child['ordinal'])] if role == '항' else []
        return []

    def parse_endpoint(value, inherited_article=None, start_path=None):
        """Range endpoint text -> article coordinate and role-aware subpath."""
        value = value.strip()
        article = ARTICLE.match(value)
        if article:
            tail = SUBPATH.match(value, article.end())
            return coordinate(article[0]), subpath(tail)
        bare = BARE_ENDPOINT.match(coordinate(value))
        if not bare or inherited_article is None:
            return None, None
        if bare['letter']:
            own = ('목', [HANGUL_ORDER.index(bare['letter']) + 1])
        else:
            own = (bare['role'], [int(bare['number'])] + ([int(bare['branch'])] if bare['branch'] else []))
        prefix = []
        for item in start_path or []:
            if item[0] == own[0]:
                break
            prefix.append(item)
        return inherited_article, prefix + [own]

    def article_key(locator):
        values = tuple(int(x) for x in re.findall(r'\d+', coordinate(locator)))
        return values or None

    def expand_article_range(document_id, first, last):
        lo, hi = article_key(first), article_key(last)
        if lo is None or hi is None or lo > hi:
            return []
        axis = {}
        for (did, locator), source_ids in targets.items():
            if did != document_id:
                continue
            key = article_key(locator)
            if key is None or not lo <= key <= hi:
                continue
            if len(source_ids) != 1 or key in axis:
                return []
            axis[key] = source_ids[0]
        if lo not in axis or hi not in axis:
            return []
        # A simple integer range must contain every numbered article. Branch articles
        # already present in the structure are included between the two endpoints.
        if len(lo) == len(hi) == 1:
            main = {k[0] for k in axis if len(k) == 1}
            if any(number not in main for number in range(lo[0], hi[0] + 1)):
                return []
        return [target_record(axis[key]) for key in sorted(axis)]

    def expand_provision_range(source_id, first_path, last_path):
        if (not first_path or len(first_path) != len(last_path)
                or first_path[:-1] != last_path[:-1]
                or first_path[-1][0] != last_path[-1][0]):
            return []
        source, tree = by_id[source_id], trees.get(source_id)
        if not tree or source.get('unit_id') is None:
            return []
        prefix = first_path[:-1]
        prefix_units = descend(tree, source['unit_id'], prefix, roles_of.get(source['document_id'])) if prefix else []
        if prefix and not prefix_units:
            return []
        parent = prefix_units[-1]['unit_id'] if prefix_units else str(source['unit_id'])
        role = first_path[-1][0]
        roles = roles_of.get(source['document_id']) or {}
        children = tree.get(str(parent), [])
        typed = [child for child in children if roles.get(child.get('family')) == role]
        if not typed and not roles:
            typed = children
        lo, hi = first_path[-1][1], last_path[-1][1]
        if lo > hi:
            return []
        selected = [child for child in typed if child.get('ordinal') is not None and lo <= child['ordinal'] <= hi]
        if len([child for child in typed if child.get('ordinal') == lo]) != 1 or len(
                [child for child in typed if child.get('ordinal') == hi]) != 1:
            return []
        if len(lo) == len(hi) == 1:
            ordinals = {child['ordinal'][0] for child in selected if len(child['ordinal']) == 1}
            if any(number not in ordinals for number in range(lo[0], hi[0] + 1)):
                return []
        prefix_path = [unit['surface'] for unit in prefix_units]
        return [{'source_id': source_id, 'unit_id': child['unit_id'],
                 'unit_path': prefix_path + [child['surface']],
                 'block_ids': blocks_under(tree, child), 'target_level': 'provision'}
                for child in sorted(selected, key=lambda value: value['ordinal'])]

    def resolve_range(s, prefix, first_text, last_text, paragraph_prefix=()):
        docname, via = cited_document(s, prefix, None)
        if docname is None:
            # The range may continue an earlier named citation in the same clause:
            # `「A법」 제9조 ... 및 제3조부터 제5조까지`.
            clause = re.split(r'[.。;\n]', prefix)[-1]
            named = re.findall(r'「([^」\n]+)」', clause)
            if named and lookup(named[-1].strip()):
                docname, via = named[-1].strip(), 'continued'
        if via == 'self':
            docname = None
        if docname:
            document_ids = lookup(docname)
            if len(document_ids) != 1:
                return [], docname, via, ('DOCUMENT_MISSING' if not document_ids else 'DOCUMENT_VERSION_AMBIGUOUS')
            document_id = next(iter(document_ids))
        else:
            clause = re.split(r'[.。;\n]', prefix)[-1]
            if via != 'self' and (re.search(r'(?:법|령|규칙|규정|세칙|지침)\s*$', clause) or '「' in clause):
                return [], None, via, 'DOCUMENT_NAME_UNRESOLVED'
            document_id = s['document_id']
        first_article, first_path = parse_endpoint(first_text)
        if first_article is None:
            # Bare ranges live in the current article and may inherit their paragraph.
            if not ARTICLE.match(s['heading']):
                return [], docname, via, 'RANGE_OR_SUBARTICLE_UNRESOLVED'
            first_article = coordinate(ARTICLE.match(s['heading'])[0])
            first_article, first_path = parse_endpoint(first_text, first_article)
            if paragraph_prefix and first_path and first_path[0][0] == '호':
                first_path = list(paragraph_prefix) + first_path
        last_article, last_path = parse_endpoint(last_text, first_article, first_path)
        if last_article is None:
            return [], docname, via, 'RANGE_OR_SUBARTICLE_UNRESOLVED'
        first_sources = targets.get((document_id, first_article), [])
        last_sources = targets.get((document_id, last_article), [])
        if len(first_sources) != 1 or len(last_sources) != 1:
            return [], docname, via, 'RANGE_OR_SUBARTICLE_UNRESOLVED'
        if not first_path and not last_path:
            details = expand_article_range(document_id, first_article, last_article)
        elif first_sources == last_sources:
            details = expand_provision_range(first_sources[0], first_path, last_path)
        else:
            details = []
        return details, docname, via, None if details else 'RANGE_OR_SUBARTICLE_UNRESOLVED'

    for s in checkpoint.sources(sources, counts):
        for b in s['blocks']:
            text = b['text']
            consumed = []
            last_named = None
            # A range is one mention and one reference case. It must be consumed before
            # the ordinary article/provision scanners can split its endpoints.
            for m in ARTICLE_RANGE.finditer(text):
                details, docname, via, reason = resolve_range(s, text[:m.start()], m['start'], m['end'])
                if docname:
                    last_named = docname
                consumed.append((m.start(), m.end(), {'article': None, 'path': [], 'docname': docname}))
                record(s, b, text, m.start(), m.end(), coordinate(m[0]), docname,
                       [d['source_id'] for d in details], [], reason, 'EXACT_DETERMINISTIC_RANGE',
                       '준용 단서' if '준용' in text else '범위 인용 단서', 'raw_explicit_range_hint', via,
                       target_records=details)
            article_here = s['id'] if ARTICLE.match(s['heading']) else None
            for m in BARE_RANGE.finditer(text):
                if any(a <= m.start() < z for a, z, _ in consumed):
                    continue
                paragraph = within_paragraph(article_here, b['block_id']) if article_here else []
                details, docname, via, reason = resolve_range(
                    s, text[:m.start()], m['start'], m['end'], paragraph_prefix=paragraph)
                consumed.append((m.start(), m.end(), {'article': article_here, 'path': [], 'docname': docname}))
                record(s, b, text, m.start(), m.end(), coordinate(m[0]), docname,
                       [d['source_id'] for d in details], [], reason, 'EXACT_DETERMINISTIC_RANGE',
                       '준용 단서' if '준용' in text else '범위 인용 단서', 'raw_explicit_range_hint', via,
                       target_records=details)
            # 1) 이 문서 틀의 표기로 쓴 인용(`14. 1)`, `제4조(1)`) — 문서 전용 패턴이 먼저다.
            pattern = patterns.get(s['document_id'])
            for m in (pattern.finditer(text) if pattern else ()):
                if any(a <= m.start() < z for a, z, _ in consumed):
                    continue
                if re.search(r'\d{4}\s*\.\s*$', text[:m.start()]):
                    continue                                   # `(2022. 1. 1)` — 날짜의 월·일
                whole = coordinate(m[0])
                hit, loc = None, None
                for cut in range(len(whole), 0, -1):          # 긴 좌표 먼저: `14.1)(2)` → `14.1)`
                    found = frames.get((s['document_id'], whole[:cut]), [])
                    if len(found) == 1:
                        hit, loc = found[0], whole[:cut]
                        break
                    if found:
                        break
                if hit is None:
                    continue                                   # 틀에 없는 번호는 목록 번호일 수 있어 남기지 않는다
                target, units = hit
                if target == s['id'] and b is s['blocks'][0] and m.start() == 0:
                    continue
                tree = trees[target]
                roles = roles_of.get(s['document_id']) or {}
                consumed.append((m.start(), m.end(), {'article': target, 'docname': None,
                    'path': [(roles.get(u.get('family')) or ROLE_ORDER[i], u['ordinal']) for i, u in enumerate(units)]}))
                record(s, b, text, m.start(), m.end(), loc, None, [target],
                       [{'unit_id': u['unit_id'], 'surface': u['surface']} for u in units]
                       + [{'block_ids': blocks_under(tree, units[-1])}],
                       None, 'EXACT_SAME_DOCUMENT_PROVISION',
                       '준용 단서' if '준용' in text else '인용 단서', 'raw_explicit_frame_hint')
            # 2) 법문 표준 표기(`제4조제1항제2호`)
            for m in ARTICLE.finditer(text):
                if any(a <= m.start() < z for a, z, _ in consumed):
                    continue
                # An article's own heading is structural metadata, not a reference.
                if b is s['blocks'][0] and m.start() == 0 and re.match(r'\s*\(', text[m.end():]):
                    continue
                prefix = text[:m.start()]
                docname, via = cited_document(s, prefix, last_named)
                # `「A법」 제3조 및 제5조`·`A법 제3조, 제5조` — 접속어로 이어진 조는 앞 인용의 법이다.
                previous = sorted((c for c in consumed if c[1] <= m.start() and c[2].get('docname')), key=lambda c: c[1])
                if docname is None and via is None and previous and re.fullmatch(
                        r'(?:\s*(?:제\s*\d+\s*(?:항|호)(?:\s*의\s*\d+)?|[가-하]\s*목|\([^()]{0,80}\)))*\s*(?:및|또는|과|와|이나|,|·|ㆍ|、)\s*',
                        text[previous[-1][1]:m.start()]):
                    docname, via = previous[-1][2]['docname'], 'continued'
                if via == 'self':
                    docname = None                           # `이 법 제3조` 는 같은 문서
                elif docname:
                    last_named = docname
                loc = coordinate(m[0])
                sub = SUBPATH.match(text, m.end())
                path = subpath(sub)
                end = sub.end() if path else m.end()
                reason = None
                suffix = text[end:]
                if re.match(r'\s*(?:부터|내지|[~～∼])', suffix) or re.search(r'(?:부터|내지|[~～∼])\s*$', prefix):
                    reason = 'RANGE_OR_SUBARTICLE_UNRESOLVED'
                elif docname:
                    ids = lookup(docname)
                    if len(ids) != 1:
                        reason = 'DOCUMENT_MISSING' if not ids else 'DOCUMENT_VERSION_AMBIGUOUS'
                else:
                    # Unquoted named-law forms and chained foreign citations need review.
                    clause = re.split(r'[.。;\n]', prefix)[-1]
                    if via != 'self' and (re.search(r'(?:법|령|규칙|규정|세칙|지침)\s*$', clause) or '「' in clause):
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
                    '준용 단서' if '준용' in text else '인용 단서', 'raw_explicit_article_hint', via)
            # 조 없이 쓴 `제2항`·`제3호` — 어느 조의 것인지는 문맥이 정한다.
            #  · `제4조제1항 및 제2항` 처럼 접속어로 이어지면 바로 앞 인용의 조다.
            #  · 항 안에서 부르는 `제2호` 는 그 항의 호다.
            #  · 그 밖에는 이 조의 것이다. 조 마디가 아닌 곳(별표 등)에선 잇지 않는다.
            for m in BARE.finditer(text):
                if any(a <= m.start() < z for a, z, _ in consumed):
                    continue
                if re.search(r'(?:별지|별표|별첨|서식|부록)\s*$', text[:m.start()]) or re.match(r'\s*서식', text[m.end():]):
                    continue                                   # `별지 제6호의14서식` — 별표 쪽이 읽는다
                before = sorted((c for c in consumed if c[1] <= m.start()), key=lambda c: c[1])   # 가장 가까운 앞 인용
                gap = text[before[-1][1]:m.start()] if before else None
                if gap is not None and re.fullmatch(r'\s*(?:부터|내지|[~～∼])\s*', gap):
                    continue                                   # 범위 끝 — 앞 인용이 이미 범위로 남았다
                # 앞 인용에 이어진 것: 접속어(`및`), 괄호 열기(`제65조(제1항`), 조 제목 괄호 뒤
                # (`제238조(…산정 등)제6항`), `같은 조`. 이때 조는 앞 인용의 조다.
                continued = gap is not None and re.fullmatch(
                    r'\s*(?:\([^()]{0,80}\))?\s*(?:및|또는|과|와|이나|,|·|ㆍ|\()?\s*', gap)
                head = before[-1][2] if continued or (before and re.match(r'(?:같은|동)\s*조', m[0])) else None
                if head is not None and head['article'] is None:
                    continue                                   # 앞 인용이 풀리지 않았으면 이 조로 잘못 잇지 않는다
                owner = head['article'] if head else article_here
                if owner is None:
                    continue
                own = (m[2], [int(m[1])] + ([int(m[3])] if m[3] else []))
                if head and m[2] == '호' and head['path'] and head['path'][0][0] == '항':
                    path = head['path'][:1] + [own]            # `제1항제1호 및 제2호`
                elif m[2] == '호' and owner == article_here and not head:
                    path = within_paragraph(owner, b['block_id']) + [own]
                else:
                    path = [own]
                end = m.end()
                if m[2] == '항':
                    more = re.match(r'\s*제\s*(\d+)\s*호(?:\s*의\s*(\d+))?', text[m.end():])
                    if more:
                        path.append(('호', [int(more[1])] + ([int(more[2])] if more[2] else [])))
                        end = m.end() + more.end()
                units = provision([owner], path)
                docname = head.get('docname') if head else None
                consumed.append((m.start(), end, {'article': owner, 'path': path, 'docname': docname}))
                record(s, b, text, m.start(), end, coordinate(text[m.start():end]), docname,
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
                    docname = annex_titles.match(prefix)
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
    # law.go.kr 이 공표한 위임 관계(lsDelegated). 법 조의 위임 문구 → 그것을 정한 시행령·규칙·고시 조.
    # 본문에 `법 제N조` 가 없어도 위임은 성립하므로 글자 인용과 별개로 잇는다.
    seen = set()
    for e in delegations or []:
        src, dst = e.get('src') or {}, e.get('dst') or {}
        s_ids, d_ids = lookup(src.get('name', '')), lookup(dst.get('name', ''))
        if len(s_ids) != 1 or len(d_ids) != 1 or not src.get('jo') or not dst.get('jo'):
            continue
        s_art = targets.get((next(iter(s_ids)), coordinate(src['jo'])), [])
        d_art = targets.get((next(iter(d_ids)), coordinate(dst['jo'])), [])
        if len(s_art) != 1 or len(d_art) != 1 or s_art == d_art:
            continue
        anchor = src.get('anchor') or src['jo']
        head = ARTICLE.match(anchor)
        path = subpath(SUBPATH.match(anchor, head.end())) if head else []
        units = provision(s_art, path) if path else []
        source = by_id[s_art[0]]
        wanted = next((u['block_ids'] for u in (units or []) if 'block_ids' in u), None)
        block = next((b for b in source['blocks'] if wanted and b['block_id'] in wanted), source['blocks'][0])
        key = (s_art[0], block['block_id'], d_art[0])
        if key in seen:
            continue
        seen.add(key)
        record(source, block, block['text'], 0, 0, coordinate(anchor) + '→' + title_of(dst['name']) + coordinate(dst['jo']),
               dst['name'], d_art, [], None, 'OFFICIAL_DELEGATION',
               '위임 (' + str(e.get('link') or e.get('kind')) + ')', 'official_delegation_lawgokr')
    return counts['total'], counts['unresolved']
