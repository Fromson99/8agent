"""Names a document declares for itself: `X(이하 "Y"라 한다)`.

Prepared once per serving process: the units of the published fulltext index that
hold the word 이하 are read in bounded batches, the declarations are parsed from
their original text and kept in process memory per document (no original text, no
disk, no DB change). Oracle serving builds the list in the background at warm-up
(oracle_query_service.Factory.preload_declared_names); while it runs, requests use
what is already cached instead of reading the same units on the request path. A request compares the words it was given with the cached
declared names literally, so tokenization differences between a question and the
original do not matter. The result is a search hint and a document-name alias,
never legal evidence: meaning, scope and applicability stay with the model reading
the original.
"""
import re
import threading
import time
import unicodedata

from .. import term_morph
from ..navigation_match import norm

VERSION = 'declared-names-v2'
QUOTES = '"“”‘’\'「」『』'
# Optional scope words between 이하 and the name: `(이하 이 조에서 "위원장"이라 한다)`.
DECLARATION = re.compile(
    r'[（(]\s*이하\s+(?:(?P<scope>(?:이|같은|해당)\s*[가-힣]{1,4}\s*에서는?)\s*)?'
    r'[' + QUOTES + r']?(?P<name>[^()（）\n' + QUOTES + r']{1,40}?)[' + QUOTES + r']?\s*'
    r'(?:이라|라)\s*(?:한다|합니다|함)')
TITLE = re.compile(r'「([^」]{2,80})」\s*$')
CLAUSE_BREAKS = ',，;；。\n:'
# Names a document uses for itself or its parent law. Their meaning depends on
# the declaring document, so they never become a search word or a document alias.
GENERIC = {norm(w) for w in ('법', '영', '규칙', '규정', '세칙', '시행령', '시행규칙', '시행세칙', '이 법', '동법',
                             '같은 법', '본 규정', '이 규정', '고시', '지침', '기준', '협회', '위원회')}
MARKER = '이하'          # index token every declaration unit holds
BATCH_UNITS = 2000       # stays under the Oracle fulltext projection (2,048 matches in one statement)
PAGE = 100               # fulltext pages are 1..100 rows
MAX_WORDS = 8
MAX_ADDED_QUERIES = 4
MAX_CACHED_DECLARATIONS = 200000
CONTENT_TAGS = ('NNG', 'NNP', 'NNB', 'XR', 'XSN', 'SL', 'SH', 'SN')


# `법 제32조제1항에 따른 창업지원 전담조직` -> `창업지원 전담조직`: the cited frame is not the name.
FRAME = re.compile(r'^.*(?:에\s*따른|에\s*의한|에서\s*정하는|에\s*규정된|으로\s*정하는|로\s*정하는)\s+')


def core(long_form):
    """The named thing of a clause long form, without a leading citation frame."""
    return FRAME.sub('', long_form).strip()


def generic(name):
    return norm(name) in GENERIC or len(norm(name)) < 2


def parse(text):
    """Every declaration in one original unit text, with its preceding long form."""
    found = []
    for m in DECLARATION.finditer(text):
        name = m['name'].strip()
        before = text[:m.start()]
        title = TITLE.search(before)
        if title:
            kind, long_form, start = 'TITLE', title[1].strip(), title.start(1)
        else:
            start = max([before.rfind(c) + 1 for c in CLAUSE_BREAKS] + [before.rfind(')') + 1, 0])
            start = max(start, m.start() - 120)
            kind, long_form = 'CLAUSE', before[start:].strip()
        if not name or not long_form:
            continue
        found.append({'name': name, 'kind': kind, 'long_form': long_form, 'scope_text': (m['scope'] or '').strip(),
                      'declaration': text[start:m.end()], 'declaration_start': start, 'declaration_end': m.end()})
    return found


class DeclarationCache:
    """Declarations per document of one published fulltext index, kept for the process.

    Only documents a request is authorized for are read and returned; a document is
    read once. A failed read is not cached, so a later request may try again.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.indexes = {}
        self.preloading = set()

    def reserve(self, identity):
        """Mark an index as being built in the background; False when one already is."""
        with self.lock:
            if identity in self.preloading:
                return False
            self.preloading.add(identity)
            return True

    def release(self, identity):
        with self.lock:
            self.preloading.discard(identity)

    def documents(self, index, db, sources, document_ids, *, read=True, preload=False):
        """Cached declarations of the documents; `read=False` never touches the index
        (structure-first discovery must not search bodies) and returns only what is cached.
        While a background build of the same index runs, a request does not read either;
        `preload=True` is that build."""
        identity = index.manifest['index_sha256']
        wanted = sorted(set(document_ids))
        with self.lock:
            known = self.indexes.setdefault(identity, {})
            missing = [d for d in wanted if d not in known]
            waiting = not preload and identity in self.preloading
        read = read and not waiting
        report = {'documents': len(wanted), 'read_documents': 0, 'read_units': 0, 'seconds': 0.0,
                  'not_loaded_documents': 0 if read else len(missing), **({'preloading': True} if waiting else {})}
        if missing and read:
            started = time.monotonic()
            loaded, units = _read(index, db, sources, missing)
            report.update(read_documents=len(missing), read_units=units, seconds=round(time.monotonic() - started, 3))
            with self.lock:
                known = self.indexes.setdefault(identity, {})
                if sum(len(v) for v in known.values()) + sum(len(v) for v in loaded.values()) > MAX_CACHED_DECLARATIONS:
                    raise ValueError('declared-name cache exceeds its bound')
                known.update(loaded)
        with self.lock:
            known = self.indexes[identity]
            return {d: known[d] for d in wanted if d in known}, report


CACHE = DeclarationCache()


def _scope(sources, document_ids):
    if hasattr(sources, 'ids_for_documents'):
        return sources.ids_for_documents(frozenset(document_ids))
    return {sid for sid in sources if sources[sid]['document_id'] in document_ids}


def _read(index, db, sources, document_ids):
    """Parse every declaration of the given documents from the units holding 이하.

    Per-document counts come first (one grouped list), then documents are read in
    batches of at most BATCH_UNITS matching units, PAGE units at a time. Ranked pages
    carry the unit bodies (one Oracle body lookup per page); the navigation page path
    would read the same keys' metadata again for every page.
    """
    counts, cursor = {}, None
    while True:
        page = index.law_groups_page(db, [MARKER], _scope(sources, document_ids), cursor=cursor, limit=PAGE)
        for row in page['items']:
            counts[row['document_id']] = row['unit_count']
        cursor = page['next_cursor']
        if cursor is None:
            break
    loaded = {d: [] for d in document_ids}
    batches, current, size = [], [], 0
    for did in sorted(counts):
        if current and size + counts[did] > BATCH_UNITS:
            batches.append(current); current, size = [], 0
        current.append(did); size += counts[did]
    if current:
        batches.append(current)
    units = 0
    for batch in batches:
        allowed, cursor = _scope(sources, batch), None
        while True:
            page = index.rank_page(db, [MARKER], allowed, cursor=cursor, limit=PAGE)
            for item in page['items']:
                units += 1
                if item['document_id'] not in loaded:
                    raise ValueError('declared-name read outside the requested documents')
                for d in parse(item.get('text') or ''):
                    loaded[item['document_id']].append(_record(item, d))
            cursor = page['next_cursor']
            if cursor is None:
                break
    return {d: _unique(v) for d, v in loaded.items()}, units


def _record(item, declaration):
    return {**declaration, 'document_id': item['document_id'], 'document_name': item.get('document_name'),
            'source_id': item['source_id'], 'unit_id': item.get('unit_id'), 'block_ids': list(item.get('block_ids') or [])}


def _unique(records):
    # Nested units (article and its paragraph) carry the same declaration text.
    seen, out = set(), []
    for r in records:
        key = (r['document_id'], r['name'], r['long_form'], r['declaration'])
        if key not in seen:
            seen.add(key); out.append(r)
    return out


def written_forms(word, written=None):
    """Normalized readings of a written word: the noun part up to the whole word.

    The tokenizer cannot tell a suffix from a particle in a name it does not know
    (`승인기준서` -> 승인/기준/서:JKB, `내국법인` -> 내국법/인:VCP), so a declared
    name may end anywhere between the noun part and the end of the written word.
    """
    nw, nl = norm(written or word), norm(word)
    if not nw.startswith(nl):
        return {nl}
    # A suffix tagged as a noun part (`공정거래법상` -> 상:XSN) may also end the noun part.
    return {nw[:k] for k in range(max(2, len(nl) - 2), len(nw) + 1)}


def as_name(declarations, word, written=None):
    """Declarations whose declared name is `word` as written (`외감법의` -> `외감법`)."""
    readings = written_forms(word, written)
    return [{**d, 'word': word, 'direction': 'NAME_TO_LONG_FORM'}
            for rows in declarations.values() for d in rows if norm(d['name']) in readings]


def as_long_form(declarations, word, written=None):
    """Declarations whose long form ends with `word` as written.

    `exact` marks a long form that is `word` itself (after a citation frame or as
    a 「title」). A list such as `시ㆍ도경찰청장 또는 경찰서장(이하 "경찰관서장")`
    names more than `word`.
    """
    readings = written_forms(word, written)
    out = []
    for rows in declarations.values():
        for d in rows:
            long_form = norm(d['long_form'])
            if any(long_form.endswith(r) for r in readings) and norm(d['name']) not in readings:
                out.append({**d, 'word': word, 'direction': 'LONG_FORM_TO_NAME',
                            'exact': norm(core(d['long_form'])) in readings})
    return out


def query_words(text):
    """Nouns as written in a query, as (noun part, written words) pairs.

    Space-separated words are the unit, not morphemes: the tokenizer splits names
    it does not know (`명의개서대행계약` -> 명/의/개서…, `부가가치세액` -> 부/가치…).
    A word's noun part runs from its first character to its last content morpheme
    (`외감법의` -> `외감법`). Consecutive words whose noun part is the whole word
    form multi-word names (`창업지원 전담조직의`); single words come first.
    """
    text = unicodedata.normalize('NFKC', text)
    tokens = term_morph.tokenize(text)
    words = []
    for m in re.finditer(r'[^\s,.;:?!()「」『』"\'“”‘’]+', text):
        ends = [t.start + t.len for t in tokens
                if t.tag in CONTENT_TAGS and m.start() <= t.start and t.start + t.len <= m.end()]
        words.append((m.start(), max(ends) if ends else None, m.end(),
                      text[m.end():m.end() + 1] == ' '))
    single, multi = [], []
    for j, (start, noun_end, end, _) in enumerate(words):
        if noun_end is None:
            continue
        single.append((text[start:noun_end], text[start:end]))
        i = j
        while i > 0 and j - i < 3:
            prev_start, prev_noun, prev_end, spaced = words[i - 1]
            if prev_noun != prev_end or not spaced or prev_end + 1 != words[i][0]:
                break
            i -= 1
            multi.append((text[words[i][0]:noun_end], text[words[i][0]:end]))
    # Longer words first: a lookup budget is better spent on `명의개서대행계약` than on `기준`.
    single.sort(key=lambda pair: -len(norm(pair[0])))
    out = {}
    for noun, written in single + multi:
        # Article numbers (`제8조`, `외감법 제8조`) are coordinates, not names.
        if re.search(r'(?:^|\s)제?\s*\d', noun):
            continue
        if not generic(noun) and len(norm(noun)) >= 2 and len(norm(written)) >= 3:
            out.setdefault((noun, written), None)
    return list(out)


def _index(holder):
    index = getattr(holder, 'unit_fulltext', None)
    db = getattr(holder, 'unit_fulltext_db', None)
    if index is None or db is None or not all(hasattr(index, a) for a in ('rank_page', 'law_groups_page', 'manifest')):
        return None, None
    return index, db


def title_documents(matcher, name, authorized, resolve_title):
    """Documents named by a declared law-title abbreviation, e.g. `외감법`.

    Each declaration's 「title」 is resolved with the caller's own name matching.
    Returns the declarations used and the resolved document IDs; several
    different documents mean the abbreviation is ambiguous for this request.
    """
    if generic(name):
        return [], []
    index, db = _index(matcher)
    sources = getattr(matcher, 'sources', None)
    if index is None or sources is None:
        return [], []
    declarations, _ = CACHE.documents(index, db, sources, authorized)
    used, documents = [], []
    for record in as_name(declarations, name):
        if record['kind'] != 'TITLE':
            continue
        for did in resolve_title(record['long_form']):
            if did not in documents:
                documents.append(did)
        used.append(record)
    return used, documents


def expand(session, queries, document_ids, *, read=True):
    """Search queries plus the 「title」 of law-title abbreviations declared in the corpus.

    A declared law-title abbreviation (`외감법`) adds the query with the 「title」 in its
    place. Other declarations (clause long forms, names declared for what the user
    wrote) are reported in DECLARED_NAME_QUERIES but add no query: their scope is
    the declaring document. With `read=False` only declarations already cached in
    this process are used.
    """
    added, used, skipped = [], [], []
    words = list(dict.fromkeys(w for q in queries for w in query_words(q)))[:MAX_WORDS]
    index, db = _index(session.matcher)
    sources = getattr(getattr(session, 'tools', None), 'sources', None) or getattr(session.matcher, 'sources', None)
    report = {'version': VERSION, 'words': [w for _, w in words], 'added_queries': added, 'skipped': skipped, 'cache': None}
    if not words or index is None or sources is None:
        report['declarations'] = []
        return list(queries), report
    try:
        declarations, report['cache'] = CACHE.documents(index, db, sources, document_ids, read=read)
    except (ValueError, RuntimeError) as exc:
        # Hints only: a failed read leaves the accepted queries unchanged.
        skipped.append({'reason': type(exc).__name__ + ': ' + str(exc)[:200]})
        report['declarations'] = []
        return list(queries), report
    for word, written in words:
        for record in as_name(declarations, word, written) + as_long_form(declarations, word, written):
            if record['direction'] == 'NAME_TO_LONG_FORM' and record['kind'] == 'TITLE':
                name = record['name'] if any(record['name'] in q for q in queries) else word
                extra = [q.replace(name, record['long_form']) for q in queries if name in q]
            else:
                extra = []
            extra = [q for q in extra if q not in queries and q not in added]
            if extra or len(used) < 16:
                used.append(record)
            added.extend(extra)
    del added[MAX_ADDED_QUERIES:]
    report['declarations'] = [{k: r.get(k) for k in ('word', 'direction', 'kind', 'name', 'long_form', 'scope_text',
                                                    'document_id', 'document_name', 'source_id', 'unit_id')}
                              for r in used][:16]
    return list(queries) + added, report


# `이 규정`, `동 법`, `같은 규정`: a demonstrative before the name points elsewhere, not at the declaration.
POINTER = re.compile(r'(?:^|[^가-힣A-Za-z0-9])(?:이|본|동|같은|해당|그|위|상기)\s*$')
# `규정 제32조제1항`, `법 제9조 제5항`: an article (and paragraph) written right after a declared name.
CITED_ARTICLE = re.compile(r'\s*(제\s*\d+(?:\s*-\s*\d+)*\s*조(?:\s*의\s*\d+)?)(\s*제?\s*\d+\s*항)?')


def document_declarations(holder, sources, document_id):
    """Every name one document declares for itself, generic ones (법·규정·영) included.

    Search expansion leaves generic names out because their meaning differs between
    documents. Inside the declaring document the meaning is fixed, so a citation that
    document writes with the name (`규정 제32조`) can be resolved from its own declaration.
    """
    index, db = _index(holder)
    if index is None or sources is None:
        return []
    found, _ = CACHE.documents(index, db, sources, [document_id])
    return found.get(document_id, [])


def declared_citations(declarations, spans):
    """Citations written with a declared name in the given original spans.

    `spans` are {'block_id', 'text', 'source_id'} of the declaring document. A name must
    stand as its own word (not the end of `한국은행법`). A declaration limited to one
    provision (`이하 이 조에서 …`) counts only inside the source that declares it.
    Returns {'name', 'long_form', 'kind', 'article', 'paragraph', 'block_id', 'start', 'end', 'text'}.
    """
    names = {}
    for d in declarations:
        names.setdefault(d['name'], []).append(d)
    out = []
    for span in spans:
        text, taken = span['text'] or '', []
        for name in sorted(names, key=len, reverse=True):
            pattern = r'(?<![가-힣A-Za-z0-9])' + re.escape(name) + CITED_ARTICLE.pattern
            for m in re.finditer(pattern, text):
                if any(a <= m.start() < b for a, b in taken):
                    continue
                if POINTER.search(text[:m.start()]):
                    continue      # `이 규정 제5조`, `같은 법 제3조`: the citing document or the last one named
                usable = [d for d in names[name] if not d['scope_text'] or d['source_id'] == span.get('source_id')]
                forms = {d['long_form'] for d in usable}
                if len(forms) != 1:
                    continue      # undeclared here or declared differently: not resolved
                d = usable[0]
                taken.append((m.start(), m.end()))
                out.append({'name': name, 'long_form': d['long_form'], 'kind': d['kind'],
                            'declared_source_id': d['source_id'], 'article': re.sub(r'\s+', '', m.group(1)),
                            'paragraph': re.sub(r'\s+', '', m.group(2) or '') or None, 'block_id': str(span['block_id']),
                            'start': m.start(), 'end': m.end(), 'text': text[m.start():m.end()]})
    return out


def resolve_citation(citation, matcher, scope):
    """Structure pairs the cited article names, with the existing structure resolver.

    The long form names the document (`이 요령은 코스닥시장상장규정`, `「자본시장과 금융투자업에
    관한 법률」`); a long form naming no registered document, or several, resolves to nothing.
    """
    from .structure_query import resolve
    target = core(citation['long_form']) + ' ' + citation['article'] + (citation['paragraph'] or '')
    found = resolve(target, matcher, scope)
    if found['status'] != 'MATCH':
        found = resolve(core(citation['long_form']) + ' ' + citation['article'], matcher, scope)
    if found['status'] == 'MATCH':
        return [p for p in found['pairs'] if p.get('document_id') in scope]
    # Documents without stored coordinates: one named document, one article with that surface.
    from .structure_query import document_hits
    documents = {d for hit in document_hits(core(citation['long_form']), matcher) for d in hit['values'] if d in scope}
    if len(documents) != 1:
        return []
    did = next(iter(documents))
    units = matcher.units
    rows = units.for_document(did) if hasattr(units, 'for_document') else units.items()
    articles = [u for (d, u), v in rows if d == did and norm(v.get('surface') or '') == norm(citation['article'])]
    return [{'document_id': did, 'unit_id': articles[0], 'source_id': None}] if len(articles) == 1 else []


def upgrade_reference(session, ref):
    """A stored reference the index left without a target, resolved from the citing document's declaration.

    The index stores `제32조제1항` in `규정 제32조제1항` as a citation but cannot tell which
    document `규정` is. When the citing document itself declared the name
    (`이 요령은 코스닥시장상장규정(이하 "규정"이라 한다)`, in any article), the reference
    is completed for this request: same reference ID and witness, targets from the
    structure resolver, resolution EXACT_DECLARED_NAME. Returns the completed copy or None.
    The stored index is not changed.
    """
    if ref.get('targets') or ref.get('target_source_ids') or str(ref.get('resolution', '')).startswith('EXACT_'):
        return None
    did, start = ref.get('document_id'), ref.get('mention_start')
    if did is None or type(start) is not int:
        return None
    try:
        declarations = document_declarations(session.matcher, session.tools.sources, did)
        text = session.store.source(did, str(ref['block_id']))['text']
    except (KeyError, ValueError, RuntimeError, TypeError):
        return None
    mention = text[start:ref.get('mention_end', start)] if type(ref.get('mention_end')) is int else (ref.get('mention_text') or '')
    article = CITED_ARTICLE.match(mention)
    if not declarations or not article:
        return None
    before = text[max(0, start - 60):start].rstrip()
    spans = [{'block_id': ref['block_id'], 'source_id': ref.get('source_id'), 'text': before + ' ' + mention.strip()}]
    found = [c for c in declared_citations(declarations, spans) if c['end'] >= len(spans[0]['text']) - 1]
    if len(found) != 1:
        return None
    pairs = resolve_citation(found[0], session.matcher, list(session.scope))
    targets = []
    for pair in pairs:
        sid = pair.get('source_id')
        if sid is None:
            ids = session.matcher._unit_sources(pair['document_id'], str(pair['unit_id']))
            sid = ids[0] if len(ids) == 1 else None
        if sid is None or sid not in session.tools.sources:
            continue
        targets.append({'source_id': sid, 'unit_id': str(pair['unit_id']) if pair.get('unit_id') is not None else None,
                        'unit_path': [], 'block_ids': [], 'target_level': 'paragraph' if found[0]['paragraph'] else 'article'})
    if not targets:
        return None
    return {**ref, 'targets': targets, 'target_source_ids': [t['source_id'] for t in targets],
            'resolution': 'EXACT_DECLARED_NAME', 'stored_resolution': ref.get('resolution'),
            'declared_name': {k: found[0][k] for k in ('name', 'long_form', 'kind')}}
