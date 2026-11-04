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
from lawrag.core.legal_coordinate import MOK_LETTERS

ARTICLE = re.compile(r'제\s*\d+(?:\s*-\s*\d+)*\s*조(?:\s*의\s*\d+)?')
NAMED = re.compile(r'「([^」\n]+)」\s*$')
ANNEX_KINDS = '별표|별지|별첨|서식|부록|참고'
# `[별표 3]`, `별표 제3호`, `별지 제7호서식`, `참고 4-1` — 수집처마다 표기가 다르다.
ANNEX = re.compile(r'\[?\s*(' + ANNEX_KINDS + r')\s*제?\s*(\d+(?:\s*[-의]\s*\d+)*(?:\s*호\s*의\s*\d+)?)\s*호?\s*(?:서식)?\s*\]?')
# 마디 머리가 스스로 밝히는 별표 이름 — 본문 인용과 같은 좌표로 접는다.
ANNEX_HEADING = re.compile(r'^\[?\s*(' + ANNEX_KINDS + r')\s*제?\s*(\d+(?:\s*[-의]\s*\d+)*(?:\s*호\s*의\s*\d+)?)\s*호?\s*(?:서식)?\s*\]?')

def coordinate(text):
    return re.sub(r'\s+', '', text)


# 조 뒤에 붙는 하위 경로 — `제1항제2호의2가목`. 항·호·목이 모두 선택이다.
SUBPATH = re.compile(r'\s*(?:제\s*(\d+)\s*항)?\s*(?:제\s*(\d+)\s*호(?:\s*의\s*(\d+))?)?\s*(?:([가나다라마바사아자차카타파하])\s*목)?')
# 같은 조 안의 인용 — `제2항`, `같은 조 제3항`, `이 조 제1항제2호`. 앞에 조가 없을 때만.
BARE = re.compile(r'(?<![조\d])(?:(?:같은|이|동)\s*조\s*)?제\s*(\d+)\s*(항|호)(?:\s*의\s*(\d+))?')
HANGUL_ORDER = MOK_LETTERS
UNCONSUMED_SUFFIX = re.compile(r'^\s*(?:[' + HANGUL_ORDER + r']\s*목|의\s*\d+|'
    r'각\s*(?:호|목)\s*외의\s*부분|단서|본문|전단|후단|\d+\)|\(\d+\)|\([' + HANGUL_ORDER + r']\))')

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


def frame_roles_v2(ladder):
    from lawrag.core.structure.anchors import FAMILY_ROLES
    families={f for r in (ladder or {}).get('rungs',[]) for f in r.get('families',[])}
    return {'roles':{f:FAMILY_ROLES[f] for f in families if f in FAMILY_ROLES},
            'role_basis':'explicit_marker_family_not_compressed_depth'}


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
        typed = [c for c in children if (c.get('role') or (roles or {}).get(c.get('family'))) is not None]
        if typed:
            hit = [c for c in typed if (c.get('role') or (roles or {}).get(c.get('family'))) == role and c['ordinal'] == ordinal]
        else:
            hit = []  # An unknown family cannot acquire a legal role by ordinal alone.
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
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='structure_anchor'").fetchone():
        anchors={(sid,uid):json.loads(raw) for sid,uid,raw in db.execute('SELECT source_id,unit_id,json FROM structure_anchor')}
        for sid,tree in trees.items():
            for children in tree.values():
                for u in children:u.update({k:v for k,v in anchors.get((sid,u['unit_id']),{}).items() if k in ('role','own_spans','subtree_spans','coordinate_scope')})
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


def structural_heading_end(source, block, tree):
    """Exclude an actual structure marker, including headings inside a supplement.

    A citation at the beginning of an ordinary body block remains a citation.
    Merely matching ``제N조(...)`` is insufficient without a matching structure node.
    """
    text = block['text']
    marker = ARTICLE.match(text.lstrip())
    if not marker:
        return 0
    start = len(text) - len(text.lstrip())
    surfaces = []
    if source['blocks'] and block['block_id'] == source['blocks'][0]['block_id']:
        own = ARTICLE.match(source['heading'])
        if own:
            surfaces.append(own[0])
    for children in (tree or {}).values():
        for unit in children:
            if (unit.get('family') == 'kr_article'
                    and unit.get('block_ids') and unit['block_ids'][0] == block['block_id']):
                surfaces.append(unit['surface'])
    if coordinate(marker[0]) not in {coordinate(x) for x in surfaces}:
        return 0
    end = start + marker.end()
    title = re.match(r'\s*\([^()\n]*\)', text[end:])
    return end + title.end() if title else end


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
            annexes.setdefault((s['document_id'], annex_coordinate(a[1], a[2].replace('호',''))), []).append(s['id'])
    from . import annex_files
    detached = annex_files.index((s['id'], s['document_id'], s['document_name']) for s in sources.metadata())
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
        if re.search(r'(?:이|같은|동)\s*부칙\s*$', prefix):
            return title_by_doc[s['document_id']], 'supplement'
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

    def source_extent(source, block_id, start=0, end=None):
        """Keep the deepest unique structure containing the witness, not its siblings."""
        tree = trees.get(source['id'])
        if tree and source.get('unit_id') is not None:
            current = str(source['unit_id']); path = []; seen = set()
            while current not in seen:
                seen.add(current)
                matches = [u for u in tree.get(current, []) if any(str(p['block_id'])==str(block_id) and p['start_cp']<=start and (end is None or end<=p['end_cp']) for p in u.get('subtree_spans',[]))] if any('subtree_spans' in u for u in tree.get(current,[])) else [u for u in tree.get(current, []) if block_id in blocks_under(tree, u)]
                if len(matches) != 1:
                    break
                unit = matches[0]; path.append(unit['surface']); current = unit['unit_id']
            if path:
                return {'unit_id': current, 'unit_path': path,
                        'block_ids': blocks_under(tree, unit), 'spans':unit.get('subtree_spans',[]), 'level': 'provision'}
        return {'unit_id': None, 'unit_path': [], 'block_ids': [block_id], 'level': 'block'}

    def explicit_role(text, start, end):
        """Attribute a predicate only to the current mention's following clause."""
        tail = re.split(r'[.。;\n]', text[end:], maxsplit=1)[0]
        # Another citation before the predicate makes attribution uncertain.
        if ARTICLE.search(tail) or BARE.search(tail):
            return 'UNKNOWN'
        if '단서에서' in tail and '정하는 경우' in tail and re.search(r'["”]?\s*란', tail):
            return 'SPECIFIES_DELEGATED_CASES_OF'
        if '준용' in tail:
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
               basis=None, *, target_records=None, missing_paths=None):
        details = list(target_records if target_records is not None else
                       ([target_record(resolved[0], units)] if resolved and units and len(resolved) == 1 else
                        [target_record(source_id) for source_id in resolved]))
        # Candidate IDs are required to be one-to-one with canonical target coordinates.
        unique = {}
        for detail in details:
            key = (detail['source_id'], detail.get('unit_id'), tuple(detail.get('block_ids') or ()))
            unique.setdefault(key, detail)
        details = list(unique.values())
        if details and end > start and origin.startswith('raw_explicit_') and UNCONSUMED_SUFFIX.match(text[end:]):
            reason = 'COORDINATE_SUFFIX_UNRESOLVED'
        # Reaching the article does not resolve a requested paragraph/item. Keep
        # that article as a witness-bound inspection candidate outside canonical edges.
        inspection = details if reason in {'PROVISION_NOT_IN_STRUCTURE', 'COORDINATE_SUFFIX_UNRESOLVED'} else []
        if reason in {'PROVISION_NOT_IN_STRUCTURE', 'COORDINATE_SUFFIX_UNRESOLVED'} and not inspection and resolved:
            inspection = [target_record(source_id) for source_id in resolved]
        if inspection:
            details = []
        resolved = list(dict.fromkeys(d['source_id'] for d in details))
        one = details[0] if len(details) == 1 else None
        source_part = source_extent(s, b['block_id'], start, end)
        resolution = exact if details else 'UNRESOLVED'
        if details:
            resolution_state = 'RESOLVED' if len(details) == 1 else 'MULTI_TARGET'
        elif reason in {'DOCUMENT_MISSING', 'ANNEX_BODY_NOT_IN_SELECTION', 'PROVISION_NOT_IN_STRUCTURE'}:
            resolution_state = 'DATA_GAP'
        else:
            resolution_state = 'UNKNOWN'
        identity_parts = [s['id'], b['block_id'], start, end, docname]
        if origin != 'raw_explicit_article_hint':
            identity_parts.append(origin)
        # Official delegation has no literal mention span. One source clause can
        # delegate to several articles in the same destination document, so the
        # destination article identity is part of this synthetic reference key.
        if origin == 'official_delegation_lawgokr':
            identity_parts.extend([loc, *resolved])
        ident = 'ref:' + digest(identity_parts)[:24]
        mention = text[start:end] if 0 <= start <= end <= len(text) else ''
        case_id = 'refcase:' + digest([s['id'], b['block_id'], start, end,
                                      hashlib.sha256(mention.encode()).hexdigest(), origin])[:32]
        witness_hash, witness_role = writer.witness(text, None)
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
             'source_spans': source_part.get('spans') or [{'block_id':str(b['block_id']),'start_cp':0,'end_cp':len(text),'block_hash':hashlib.sha256(text.encode()).hexdigest()}],
             # 항·호·목까지 찾았으면 그 마디와 블록. READ 가 조 전체 대신 그 블록을 읽는다.
             # Legacy singular extent is populated only when exactly one target exists.
             # Applying one extent to several targets would silently read the wrong unit.
             'target_unit_id': one.get('unit_id') if one else None,
             'target_unit_path': one.get('unit_path', []) if one else [],
             'target_block_ids': one.get('block_ids', []) if one else [],
             'target_level': one.get('target_level') if one else ('multi' if details else None),
             # 이 값은 명시 문언의 모양이지, 질문 사례에 대한 법률 결론이 아니다.
             'reference_role': explicit_role(text, start, end),
             'reference_role_basis': 'mention_following_clause',
             'resolution': resolution, 'resolution_state': resolution_state,
             'resolution_basis': 'deterministic' if details else None,
             'review_receipt_sha256': None, 'case_id': case_id, 'reason': reason,
             'navigation_hint': hint, 'origins': [origin], 'canonical_approval': False,
             'inspection_targets': inspection,
             'coverage_state':'PARTIAL' if missing_paths else 'COMPLETE' if details else 'UNRESOLVED',
             'unresolved_paths':missing_paths or [],
             'coordinate_status': 'PARTIAL_GROUP' if missing_paths and details else 'EXACT' if details else 'ARTICLE_ONLY' if inspection else 'UNRESOLVED',
             'relation_contract': 'reference-scope-v2',
             'source_namespace': 'supplement' if s['heading'].startswith('부칙') else 'body'}
        writer.insert(r, ignore=False)
        db.executemany('INSERT OR IGNORE INTO reference_end VALUES (?,?)', [(x, ident) for x in [s['id']] + resolved])
        db.executemany('INSERT OR IGNORE INTO reference_target VALUES (?,?,?,?,?,?,?)', [
            (ident, ordinal, d['source_id'], d.get('unit_id'), json.dumps(d.get('unit_path') or [], ensure_ascii=False),
             json.dumps(d.get('block_ids') or [], ensure_ascii=False), d.get('target_level') or 'article')
            for ordinal, d in enumerate(details)])
        for ordinal, d in enumerate(inspection):
            candidate_id = 'refcandidate:' + digest([ident, d])[:24]
            candidate = {**d, 'candidate_id': candidate_id,
                         'basis': 'EXACT_PREFIX_UNCONSUMED_SUFFIX' if reason == 'COORDINATE_SUFFIX_UNRESOLVED' else 'EXACT_ARTICLE_MISSING_PROVISION',
                         'canonical_approval': False, 'reference_id': ident}
            db.execute('INSERT OR IGNORE INTO reference_candidate VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (ident, candidate_id, ordinal, d['source_id'], d.get('unit_id'),
                        json.dumps(d.get('unit_path', [])), json.dumps(d.get('block_ids', [])),
                        d.get('target_level', 'article'), candidate['basis'], json.dumps(candidate, ensure_ascii=False)))
            db.execute('INSERT OR IGNORE INTO reference_candidate_end VALUES (?,?,?)',
                       (d['source_id'], ident, candidate_id))
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
        stack=[(str(s['unit_id']),[],head)]
        while stack:
            parent,path,key=stack.pop()
            for child in tree.get(parent,[]):
                childkey=key+coordinate(child['surface']);childpath=path+[child]
                frames.setdefault((s['document_id'],childkey),[]).append((s['id'],childpath))
                doc['markers'].add(marker_shape(child['surface']))
                stack.append((child['unit_id'],childpath,childkey))
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
        patterns[did] = re.compile('(?:' + '|'.join(heads) + r')\s*' + marker + r'(?:\s*' + marker + ')*'
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

    from lawrag.core.reference_coordinate import expression, path as parse_path, inherit, ORDER
    from lawrag.core.structure.anchors import span as make_span
    start_pattern=re.compile(ARTICLE.pattern+r'|(?:같은|동|이)\s*(?:항|호|목)\s*|제\s*\d+\s*(?:항|호)(?:\s*의\s*\d+)?|['+HANGUL_ORDER+r']\s*목')

    def main_sentence_breaks(text):
        """Sentence ends in the cited body, excluding nested titles and asides."""
        pairs={'(':')','[':']','「':'」','『':'』','“':'”','‘':'’'}
        # A legal sentence can end with 가액. as well as 한다.  The leading
        # 가./나. mok marker is a label, so it cannot be a sentence boundary.
        embedded=[m.span() for m in re.finditer(r'<img\b[^>]*>.*?</img\s*>',text,
                                                  re.IGNORECASE|re.DOTALL)]
        ends={m.end():m.start()+1 for m in re.finditer(r'(?<=[가-힣)\]])\.\s+(?=[가-힣])',text)
              if m.start()>3 and not any(a<=m.start()<b for a,b in embedded)}
        stack=[];cuts=[]
        for pos,char in enumerate(text,1):
            if char in pairs:stack.append(pairs[char])
            elif stack and char==stack[-1]:stack.pop()
            if pos in ends and not stack:cuts.append((ends[pos],pos))
        return cuts

    def detailed(sid, requested, qualifiers):
        tree=trees.get(sid,{})
        found=descend(tree,by_id[sid]['unit_id'],requested,roles_of.get(by_id[sid]['document_id'])) if requested else []
        if requested and not found:return None
        root=None
        if qualifiers and not requested:
            row=db.execute('SELECT json FROM structure_anchor WHERE source_id=? AND unit_id=?',
                           (sid,str(by_id[sid]['unit_id']))).fetchone()
            root=json.loads(row[0]) if row else None
            if not root or not root.get('own_spans'):return None
        d=target_record(sid,[{'unit_id':u['unit_id'],'surface':u['surface']} for u in found]+([{'block_ids':blocks_under(tree,found[-1])}] if found else []))
        if root:
            d.update(unit_id=str(by_id[sid]['unit_id']),unit_path=[],target_level='provision')
        spans=found[-1].get('subtree_spans') if found else root.get('subtree_spans') if root else None
        if qualifiers:
            scope=found[-1] if found else root
            if not scope:return None
            if any(x.startswith('각') for x in qualifiers):spans=scope.get('own_spans')
            tail=next((x for x in qualifiers if x in ('단서','본문','전단','후단')),None)
            if tail:
                base=scope.get('own_spans',[]);pieces=[]
                for p in base:
                    block=next(b for b in by_id[sid]['blocks'] if str(b['block_id'])==str(p['block_id']))
                    pieces.append((block,p,block['text'][p['start_cp']:p['end_cp']]))
                hits=[(i,t.find('다만')) for i,(_,_,t) in enumerate(pieces) if '다만' in t]
                if tail in ('단서','본문'):
                    if len(hits)!=1:return None
                    idx,offset=hits[0];chosen=[]
                    for i,(block,p,t) in enumerate(pieces):
                        a=p['start_cp'];z=p['end_cp']
                        if tail=='단서':
                            if i<idx:continue
                            if i==idx:a+=offset
                        else:
                            if i>idx:continue
                            if i==idx:z=a+offset
                        if a<z:chosen.append(make_span(block,a,z))
                    spans=chosen
                else:
                    if len(pieces)!=1:return None
                    block,p,t=pieces[0];sent=main_sentence_breaks(t)
                    if len(sent)!=1:return None
                    before,after=sent[0]
                    cut=p['start_cp']+(before if tail=='전단' else after)
                    end=p['end_cp']
                    if tail=='후단':
                        amendment=re.search(r'\s+<(?:개정|신설|본조신설)[^>]*>\s*$',t)
                        if amendment:end=p['start_cp']+amendment.start()
                    spans=[make_span(block,p['start_cp'] if tail=='전단' else cut,
                                     cut if tail=='전단' else end)]
        if spans is not None:
            d['spans']=spans;d['block_ids']=list(dict.fromkeys(p['block_id'] for p in spans))
        d['requested_path']=requested;d['qualifiers']=qualifiers;return d

    for s in checkpoint.sources(sources, counts):
        article_here=s['id'] if ARTICLE.match(s['heading']) else None
        for b in s['blocks']:
            text=b['text'];heading_end=structural_heading_end(s,b,trees.get(s['id']))
            consumed=[];contexts=[];last_named=None
            # Preserve deterministic article ranges; provision ranges use the complete grammar below.
            for m in ARTICLE_RANGE.finditer(text):
                if m.start()<heading_end:continue
                details,docname,via,reason=resolve_range(s,text[:m.start()],m['start'],m['end'])
                # Bind every returned endpoint to its actual character scope.
                for d in details:
                    if d.get('unit_id'):
                        u=next((u for cs in trees.get(d['source_id'],{}).values() for u in cs if u['unit_id']==d['unit_id']),{})
                        if u.get('subtree_spans'):d['spans']=u['subtree_spans']
                record(s,b,text,m.start(),m.end(),coordinate(m[0]),docname,[],[],reason,'EXACT_DETERMINISTIC_RANGE','범위 인용 단서','raw_explicit_range_hint',via,target_records=details)
                consumed.append((m.start(),m.end()))
            # Annexes first: their 호 is never a provision or an article heading.
            for m in ANNEX.finditer(text):
                consumed.append((m.start(),m.end()))
                if m.start()<heading_end or not text[:m.start()].strip(' \t\n[(') and (ANNEX_HEADING.match(s['heading']) or m.end()>=len(text.rstrip())):continue
                docname,via=cited_document(s,text[:m.start()],last_named)
                ids=lookup(docname) if docname else {s['document_id']};loc=annex_coordinate(m[1],m[2].replace('호',''))
                candidates=annexes.get((next(iter(ids)),loc),[]) if len(ids)==1 else []
                resolved=candidates if len(candidates)==1 and candidates[0]!=s['id'] else []
                reason=None if resolved else 'ANNEX_BODY_NOT_IN_SELECTION' if len(ids)==1 else 'DOCUMENT_VERSION_AMBIGUOUS' if ids else 'DOCUMENT_MISSING'
                annex_exact='EXACT_SAME_DOCUMENT_ANNEX'
                if reason=='ANNEX_BODY_NOT_IN_SELECTION':
                    # A separately stored file under the owning regulation's annex folder.
                    owner=annex_files.owner_for(detached,s['document_name'],docname)
                    found=annex_files.resolve(detached,owner,annex_files.label(m[1],m[2]),s['document_id']) if owner else None
                    if found and found[0]!='AMBIGUOUS':
                        resolved,reason,annex_exact=found[1],None,annex_files.RESOLUTION
                    elif found:
                        reason='DETACHED_ANNEX_AMBIGUOUS'
                exp=expression(text,m.end());end=exp['end'] if exp else m.end()
                consumed[-1]=(m.start(),end)
                details=[];missing=[]
                if resolved and len(resolved)>1:
                    # A detached file with several stored roots keeps every root.
                    details=[target_record(sid) for sid in resolved]
                elif resolved:
                    if exp:
                        for requested in exp['paths']:
                            detail=detailed(resolved[0],requested,exp['qualifiers'])
                            if detail:details.append(detail)
                            else:missing.append(requested)
                        for first,last in exp['ranges']:
                            expanded=expand_provision_range(resolved[0],first,last)
                            if expanded:details.extend(expanded)
                            else:missing.append([first,last])
                        if missing:reason='PROVISION_NOT_IN_STRUCTURE'
                    else:details=[target_record(resolved[0])]
                record(s,b,text,m.start(),end,coordinate(text[m.start():end]) if exp else loc,
                       docname,resolved,[],None if details else reason,annex_exact,
                       '별표·서식 단서','raw_explicit_annex_hint',via,target_records=details,missing_paths=missing)
                if missing and details:
                    record(s,b,text,m.start(),end,coordinate(text[m.start():end]),docname,resolved,[],reason,
                           'UNRESOLVED','별표 하위 좌표 확인 필요','raw_explicit_annex_hint_gap',via)
            # Frame-native references must match the entire observed marker sequence.
            pattern=patterns.get(s['document_id'])
            for m in pattern.finditer(text) if pattern else ():
                if m.start()<heading_end or any(a<=m.start()<z for a,z in consumed):continue
                whole=coordinate(m[0]);hits=frames.get((s['document_id'],whole),[])
                if len(hits)!=1:continue
                sid,units=hits[0];d=target_record(sid,[{'unit_id':u['unit_id'],'surface':u['surface']} for u in units]+[{'block_ids':blocks_under(trees[sid],units[-1])}])
                if units[-1].get('subtree_spans'):d['spans']=units[-1]['subtree_spans']
                record(s,b,text,m.start(),m.end(),whole,None,[],[],None,'EXACT_FRAME_PATH','구조 틀 인용','raw_explicit_frame_hint',target_records=[d]);consumed.append((m.start(),m.end()))
            for m in start_pattern.finditer(text):
                if m.start()<heading_end or any(a<=m.start()<z for a,z in consumed):continue
                prefix=text[:m.start()];is_article=bool(ARTICLE.fullmatch(m[0]));same=re.fullmatch(r'(같은|동|이)\s*(항|호|목)\s*',m[0])
                previous=contexts[-1] if contexts else None
                docname,via=cited_document(s,prefix,last_named)
                owner=article_here;context_path=[];reason=None;end=m.end()
                if is_article:
                    if via=='self':docname=None
                    if docname is None and previous and previous.get('docname') and re.fullmatch(r'\s*(?:및|또는|,|와|과)\s*',text[previous['end']:m.start()]):docname=previous['docname'];via='continued'
                    ids=lookup(docname) if docname else {s['document_id']}
                    candidates=targets.get((next(iter(ids)),coordinate(m[0])),[]) if len(ids)==1 else []
                    owner=candidates[0] if len(candidates)==1 else None
                    reason=None if owner else 'DOCUMENT_MISSING' if not ids else 'DOCUMENT_VERSION_AMBIGUOUS' if len(ids)>1 else 'ARTICLE_MISSING_OR_AMBIGUOUS'
                    if docname is None and via is None and re.search(r'(?:법|령|규칙|규정|세칙|지침)\s*$',prefix):
                        owner=None;reason='DOCUMENT_NAME_UNRESOLVED'
                    if via=='supplement' or re.search(r'부칙\s*$',prefix):
                        owner=None;reason='SUPPLEMENT_COORDINATE_REQUIRES_NAMESPACE'
                    exp=expression(text,m.end())
                    if exp:end=exp['end']
                else:
                    gap=text[previous['end']:m.start()] if previous else None
                    continued=previous and (same or re.fullmatch(r'\s*(?:및|또는|와|과|,|·|ㆍ|\()\s*',gap or ''))
                    if continued:
                        owner=previous['owner'];context_path=previous['path'];docname=previous['docname']
                    else:
                        sourcepart=source_extent(s,b['block_id'],m.start(),m.end())
                        sourceunits={u['unit_id']:u for cs in trees.get(s['id'],{}).values() for u in cs}
                        # Use current actual ancestors only for omitted enclosing levels.
                        uid=sourcepart['unit_id'];chain=[]
                        while uid in sourceunits:
                            u=sourceunits[uid]
                            if u.get('role'):chain.append((u['role'],u['ordinal']))
                            uid=next((parent for parent,cs in trees[s['id']].items() if u in cs),None)
                        context_path=list(reversed(chain))
                    if same:
                        if not continued or not owner:reason='CONTEXT_UNRESOLVED';context_path=[]
                        else:
                            rank=ORDER.index(same[2]);context_path=[p for p in context_path if ORDER.index(p[0])<=rank]
                            if not context_path or context_path[-1][0]!=same[2]:reason='CONTEXT_UNRESOLVED'
                        exp=expression(text,m.end(),context_path)
                        if not exp:exp={'paths':[context_path],'ranges':[],'last_path':context_path,'end':m.end(),'qualifiers':[]}
                    else:exp=expression(text,m.start(),context_path)
                    if exp:end=exp['end']
                if docname:last_named=docname
                details=[];missing=[]
                if owner and not reason:
                    if exp:
                        for requested in exp['paths']:
                            d=detailed(owner,requested,exp['qualifiers'])
                            if d:details.append(d)
                            else:missing.append(requested)
                        for first,last in exp['ranges']:
                            ds=expand_provision_range(owner,first,last)
                            if not ds:missing.append([first,last])
                            for d in ds:
                                u=next(u for cs in trees[owner].values() for u in cs if u['unit_id']==d['unit_id'])
                                if 'subtree_spans' in u:d['spans']=u['subtree_spans']
                                details.append(d)
                    else:
                        # Unparsed numbered suffixes cannot be approved as article-only.
                        if re.match(r'\s*(?:\(?\d+\)|제\s*\d+|['+HANGUL_ORDER+r']\s*목)',text[end:]):reason='COORDINATE_SUFFIX_UNRESOLVED'
                        elif owner!=s['id']:details=[target_record(owner)]
                if missing:reason='PROVISION_NOT_IN_STRUCTURE'
                if not details and not reason:reason='PROVISION_NOT_IN_STRUCTURE'
                consumed.append((m.start(),end));contexts.append({'owner':owner,'path':exp['last_path'] if exp else [],'docname':docname,'end':end})
                # Partial groups retain resolved members and an explicit gap record for
                # the same raw mention; they never become a silently complete group.
                origin='raw_explicit_article_hint' if is_article else 'raw_explicit_provision_hint'
                record(s,b,text,m.start(),end,coordinate(text[m.start():end]),docname,[owner] if owner and not details and reason=='PROVISION_NOT_IN_STRUCTURE' else [],[],None if details else reason,'EXACT_COMPLETE_COORDINATE','명시 인용 단서',origin,via,target_records=details,missing_paths=missing)
                if missing and details:
                    record(s,b,text,m.start(),end,coordinate(text[m.start():end]),docname,[owner] if owner else [],[],reason,'UNRESOLVED','전체 좌표 확인 필요',origin+'_gap',via)
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


# Pre-v5 generations and lightweight legacy callers have no character anchors.
# Preserve their existing reference contract while new builds use the complete
# scope-v2 compiler. Existing rows are never silently reinterpreted.
_compile_references_v2 = compile_references


def compile_references(db, aliases=None, delegations=None):
    has_anchors = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='structure_anchor'"
    ).fetchone() is not None
    if has_anchors:
        return _compile_references_v2(db, aliases, delegations)
    from .term_references_legacy import compile_references as compile_legacy
    return compile_legacy(db, aliases, delegations)


def frame_roles(ladder):
    from .term_references_legacy import frame_roles as legacy_roles
    return legacy_roles(ladder)
