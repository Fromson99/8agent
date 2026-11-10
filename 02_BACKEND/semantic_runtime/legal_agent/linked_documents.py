"""Internal rules a read internal rule hands its details to by name only.

A read article of an internal rule often leaves the detail to another internal rule without an
article number and often without its exact title: "관련 준칙에서 정한 바에 따라 신상품으로 인정되는",
"세부 준칙에서 정한다", "상품 판매 및 사후관리 관련 준칙", "신규사업 심의위원회 지침에 따라",
"위험관리기준 시행세칙에서 정하는 바". No citation index row exists for such a sentence, so the
answer asked the user which rule was meant (field 2026-11-10, 상품위원회운영지침 → 상품관리준칙).

Here the server, with no model call and no body search:
  1. finds such phrases in originals already read (internal documents only),
  2. resolves the named document by its title in the request scope (exact title key; then the
     words of the phrase, its clause and the citing rule's title against candidate titles of the
     same kind word — a word in half or more of the candidates does not tell them apart),
  3. lists the target's article titles (the bounded structure root view) and keeps those whose
     title holds a word of the question or of the citing clause.
Rows are location hints ('specifies', 'delegated'); reading them is the answer stage's server read
and adopting them as evidence stays with the model. A guess is never stored as a citation link.
GENOS_DELEGATION_LINKS=off turns all of it off (no row, no event).
"""
import math
import os
import re
from copy import deepcopy

from ..contracts import digest

KIND_WORDS = ('시행세칙', '세칙', '준칙', '지침', '규정', '기준', '규칙')
KIND_GROUP = {'시행세칙': '세칙'}
GENERIC = ('관련', '세부', '해당', '별도', '각', '관계', '소관', '기타', '다른', '개별', '하위')
REFERRING = (r'(?:(?:에서|에|으로|로)\s*(?:정(?:하는|한|하여|할|함|한다|해진)|따(?:라|른|르며|른다|름)|의(?:하여|한|한다)|위임|규정)'
             r'|의\s*(?:제\s*[·ㆍ]?\s*개정|제정|개정|폐지|변경))')
PHRASE = re.compile(r'((?:[^\s.,;:()「」\[\]]+\s+){0,7}?[^\s.,;:()「」\[\]]*?(?:' + '|'.join(KIND_WORDS) + r'))\s*' + REFERRING)
ALIAS = re.compile(r'\(\s*이하\s*["“\'‘「]?([^"”\'’」()]{2,30}?)["”\'’」]?\s*(?:(?:이?라|로)\s*(?:한다|함|칭한다|칭함))?\s*\)')
PARTICLE_END = re.compile(r'(?:은|는|이|가|을|를|의|와|과|도|만|에서|에게|으로|로서|부터|까지|에|로|며|고|면|및|또는)$')
BREAK_WORDS = ('중', '등', '외', '내')
SELF = re.compile(r'^(?:이|본|동|같은|해당)\s*(?:' + '|'.join(KIND_WORDS) + r')$')
DATED_TAIL = re.compile(r'\s*[\(\[]\s*\d{2,4}[.\-]?\d{0,2}[.\-]?\d{0,4}[^\)\]]*[\)\]].*$')
LIMITS = {'anchors': 8, 'phrases': 8, 'documents': 3, 'rows': 4, 'targets': 2, 'articles': 2, 'walk_nodes': 400, 'choice': 3}
ARTICLE = re.compile(r'^제\d+(?:-\d+)?조(?:의\d+)?$')


def enabled():
    return os.environ.get('GENOS_DELEGATION_LINKS', 'on').strip().lower() not in ('0', 'off', 'false', 'no')


def nospace(text):
    return re.sub(r'[\s·ㆍ_]+', '', text or '').casefold()


def title_of(name):
    """Last path element without extension, edition date tail or leading folder number."""
    last = str(name or '').rsplit(' > ', 1)[-1]
    last = re.sub(r'\.(?:docx?|hwpx?|pdf|txt)$', '', last, flags=re.I)
    last = DATED_TAIL.sub('', last)
    last = re.sub(r'^\s*\d{1,3}(?:-\d+)?[.\s_]+', '', last)
    return last.strip()


def kind_of(key):
    for word in KIND_WORDS:
        if key.endswith(word):
            return KIND_GROUP.get(word, word)
    return None


def terms(text):
    """Content words (the serving tokenizer), without document kind words."""
    from ..fulltext import question_terms
    try:
        words = question_terms(text or '')
    except Exception:
        words = re.findall(r'[가-힣A-Za-z]{2,}', text or '')
    return [w for w in dict.fromkeys(words) if len(w) >= 2 and w not in KIND_WORDS and w not in GENERIC]


def overlap(left, right):
    """Words of left that meet a word of right (equal, or one contains the other: 신상품 / 상품)."""
    return {a for a in left if any(a == b or (len(a) >= 2 and len(b) >= 2 and (a in b or b in a)) for b in right)}


def catalogue(session):
    """Internal documents of this request scope with their title key, kind and words.

    Built from the matcher's document names and metadata, already in memory for the request; no
    query. Cached per matcher and exact scope, so a narrower scope never sees another's names.
    """
    matcher = getattr(session, 'matcher', None)
    names = getattr(matcher, 'documents', None) or {}
    context = getattr(matcher, 'document_context', None) or {}
    scope = frozenset(getattr(session, 'scope', ()) or ())
    key = (id(matcher), digest(sorted(scope)))
    cache = session.__dict__.setdefault('_linked_document_catalogue', {})
    if key in cache:
        return cache[key]
    rows = []
    for did in sorted(scope):
        meta = context.get(did) or {}
        if (meta.get('source_category') or '') != 'internal':
            continue
        title = title_of(meta.get('document_title') or names.get(did) or '')
        k = nospace(title)
        if not k:
            continue
        date = re.findall(r'(?:19|20)\d{6}', str(names.get(did) or ''))
        rows.append({'document_id': did, 'title': title, 'key': k, 'kind': kind_of(k), 'team': meta.get('team'),
                     'terms': terms(title), 'edition': max(date) if date else ''})
    cache.clear()
    cache[key] = rows
    return rows


def _noun_phrase(raw):
    """The tokens of a captured name after the last token that ends a clause ("…사는 관련 준칙" → 관련 준칙)."""
    tokens = raw.split()
    kept = []
    for token in reversed(tokens):
        # "…에 관한 ○○준칙", "…에 대한 ○○지침": the 에 of a title is not a clause end.
        titled = kept and kept[0] in ('관한', '대한', '관하여', '대하여', '따른') and token.endswith('에')
        if kept and not titled and (PARTICLE_END.search(token) and token not in ('및',) or token in BREAK_WORDS
                                    or re.match(r'제\d', token) or re.search(r'\d', token)):
            break
        kept.insert(0, token)
    while kept and kept[0] in ('및', '또는', '그'):
        kept.pop(0)
    return ' '.join(kept)


def aliases(text):
    """{alias key: long name} declared as "긴 이름(이하 "약칭")" in one original text."""
    out = {}
    for m in ALIAS.finditer(text or ''):
        name = m.group(1).strip()
        long = _noun_phrase(re.split(r'[,.;:]', text[max(0, m.start() - 80):m.start()])[-1])
        if long and kind_of(nospace(long)) and kind_of(nospace(name)):
            out[nospace(name)] = long
    return out


def phrases(text):
    """Rule-name phrases followed by a referring ending, in order: NAMED / DESCRIBED / NAMELESS."""
    declared = aliases(text)
    out = []; seen = set()
    for m in PHRASE.finditer(text or ''):
        name = _noun_phrase(m.group(1))
        key = nospace(name)
        kind = kind_of(key)
        if not kind or SELF.match(name) or name in KIND_WORDS or '법' in key[-3:]:
            continue
        words = name.split()
        generic = next((i for i, w in enumerate(words) if w in GENERIC), None)
        # The words around the phrase in its own line (an item number "3." is not a sentence end).
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end()); line_end = len(text) if line_end < 0 else line_end
        line = text[line_start:line_end]
        at = m.start(1) + max(0, m.group(1).find(name)) - line_start
        clause = (line[:at] + ' ' + line[at + len(name):])[max(0, at - 160):at + 160]
        row = {'phrase': name, 'kind': kind, 'start': line_start + at, 'clause': clause.strip(), 'quote': line.strip()[:240]}
        # The same words may hand different matters to different rules (제3조①1 거래적격사, ①3 신상품).
        if (key, row['clause']) in seen:
            continue
        seen.add((key, row['clause']))
        if generic is not None:
            row.update(form='DESCRIBED' if generic > 0 else 'NAMELESS', descriptor=' '.join(words[:generic]))
        else:
            row.update(form='NAMED', name=declared.get(key, name), alias_of=declared.get(key))
        out.append(row)
    return out


def resolve(session, citing, phrase, question=''):
    """CONFIRMED (one document) / CHOICE (two or three) / NONE, with the deciding words."""
    rows = catalogue(session)
    own = next((r for r in rows if r['document_id'] == citing), None)
    own_key = own['key'] if own else None
    pool = [r for r in rows if r['document_id'] != citing and r['key'] != own_key and r['kind'] == phrase['kind']]
    if own and own.get('team') and any(r.get('team') == own['team'] for r in pool):
        pool = [r for r in pool if r.get('team') == own['team']]
    if phrase['form'] == 'NAMED':
        key = nospace(phrase['name'])
        hits = [r for r in pool if r['key'] == key]
        if not hits:
            return {'status': 'NONE', 'reason': 'NO_TITLE_MATCH', 'candidates': len(pool)}
        best = sorted(hits, key=lambda r: r['edition'], reverse=True)[0]
        return {'status': 'CONFIRMED', 'documents': [best], 'reason': 'TITLE_MATCH', 'words': []}
    if not pool:
        return {'status': 'NONE', 'reason': 'NO_CANDIDATE', 'candidates': 0}
    # Words that say which rule: the descriptor ("상품 판매 및 사후관리"), else the clause before the
    # phrase ("…신상품으로 인정되는"), and the citing rule's own title (상품위원회운영지침 → 상품).
    # The citing rule's own title and the question only break ties: 상품위원회운영지침's "위원회", "운영"
    # made 위험관리위원회운영준칙 tie with 상품관리준칙 for "신상품으로 인정되는" (ADR-1483 run 3).
    context = terms(phrase.get('descriptor') or '') or terms(phrase.get('clause') or '')
    titled = own['terms'] if own else []
    asked = terms(question)
    groups = {}
    for r in pool:
        groups.setdefault(r['key'], []).append(r)
    titles = [g[0] for g in groups.values()]
    df = {}
    for r in titles:
        for w in set(r['terms']):
            df[w] = df.get(w, 0) + 1
    common = {w for w, n in df.items() if len(titles) >= 2 and n * 2 >= len(titles) + (len(titles) % 2)}
    scored = []
    for r in titles:
        informative = [w for w in r['terms'] if w not in common]
        shared = overlap(informative, context)
        idf = lambda words: sum(math.log(1 + len(titles) / df[w]) for w in words)
        own_shared = overlap(informative, titled) - shared
        asked_shared = overlap(informative, asked)
        weight = idf(shared) + 0.5 * idf(own_shared)
        scored.append((weight + 0.25 * len(asked_shared), sorted(shared | own_shared), sorted(asked_shared), r))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] <= 0 or not scored[0][1]:
        return {'status': 'NONE', 'reason': 'NO_SHARED_TITLE_WORD', 'candidates': len(titles)}
    top = [s for s in scored if s[1] and abs(s[0] - scored[0][0]) < 1e-9]
    pick = lambda r: sorted(groups[r['key']], key=lambda x: x['edition'], reverse=True)[0]
    # A nameless phrase is confirmed only when its deciding word also stands in the citing rule's title
    # or the question (or the phrase describes the rule itself, "상품 판매 … 관련 준칙"). A word met
    # only in the clause is a candidate: 제3조①1 "집합투자업자 … 관련 준칙" met 투자위험관리준칙 by 투자.
    anchored = phrase['form'] == 'DESCRIBED' or bool(overlap(top[0][1], [*titled, *asked])) if len(top) == 1 else False
    if len(top) == 1 and not anchored:
        return {'status': 'CHOICE', 'documents': [pick(top[0][3])], 'reason': 'CLAUSE_WORD_ONLY',
                'words': top[0][1], 'candidates': len(titles)}
    if len(top) == 1:
        return {'status': 'CONFIRMED', 'documents': [pick(top[0][3])], 'reason': 'TITLE_WORDS',
                'words': top[0][1], 'question_words': top[0][2], 'candidates': len(titles)}
    if len(top) <= LIMITS['choice']:
        return {'status': 'CHOICE', 'documents': [pick(s[3]) for s in top], 'reason': 'TIED_TITLE_WORDS',
                'words': top[0][1], 'candidates': len(titles)}
    return {'status': 'NONE', 'reason': 'TOO_MANY_TIED', 'candidates': len(titles)}


def article_titles(session, did):
    """[(unit id, coordinate, title)] of the document's articles, document order; bounded root walk."""
    cache = session.__dict__.setdefault('_linked_document_articles', {})
    if did in cache:
        return cache[did]
    matcher = session.matcher; units = matcher.units
    children = {}
    if hasattr(units, 'children_for'):
        def kids(parent):
            if parent not in children:
                children[parent] = [str(key[1]) for key, _ in units.children_for(did, parent)]
            return children[parent]
    else:
        from .structure_query import document_tree
        tree = document_tree(matcher, did)['children']
        kids = lambda parent: [str(u) for u in tree.get(parent, ())]
    out = []; stack = list(kids(None)); nodes = 0
    while stack and nodes < LIMITS['walk_nodes']:
        uid = stack.pop(0); nodes += 1
        node = units.get((did, uid)) or {}
        surface = str(node.get('surface') or '')
        if ARTICLE.match(surface):
            out.append((uid, surface, str(node.get('title') or '')))
        elif not re.match(r'^(?:제\d+항|제?\d+호|[①-⑳]|\d+\.)', surface):
            stack[:0] = kids(uid)
    cache[did] = out
    return out


def target_articles(session, did, words):
    """Articles of did whose title holds one of words, most words first, then document order."""
    found = []
    for order, (uid, coordinate, title) in enumerate(article_titles(session, did)):
        matched = sorted(overlap(words, terms(title)))
        if matched:
            found.append((-len(matched), order, uid, coordinate, title, matched))
    found.sort()
    return [{'unit_id': f[2], 'coordinate': f[3], 'title': f[4], 'matched': f[5]} for f in found[:LIMITS['articles']]]


def locations(inv, rows, known, units):
    """Readable locations of the rules that read internal originals hand details to (see module doc)."""
    if not enabled():
        return []
    from . import evidence_inventory as inventory
    from .guided_navigation import readable_article, _location_label
    session = inv.s
    store = getattr(session, 'store', None)
    if store is None or not hasattr(store, 'source') or getattr(session, 'matcher', None) is None:
        return []
    by_id = {r['document_id']: r for r in catalogue(session)}
    texts = session.__dict__.setdefault('_read_original_text', {})
    question = getattr(inv, 'question', '') or ''
    read_docs = {(r.get('document_id')) for r in inventory.acquired_records(inv.p, include_context=False).values()}
    offered = {(r['identity']['document_id'], str(r['identity'].get('unit_id'))) for r in rows}
    decisions = []; out = {}; anchors = 0; walked = set()
    for record in inventory.acquired_records(inv.p, include_context=False).values():
        did = record.get('document_id'); offer = record.get('offer') or {}
        if did not in by_id or did not in session.scope or anchors >= LIMITS['anchors']:
            continue
        blocks = known.get(record.get('source_id'), set())
        if not blocks:
            continue
        text = ''
        for bid in sorted(blocks, key=lambda b: (len(b), b)):
            if (did, bid) not in texts:
                texts[(did, bid)] = str((store.source(did, bid) or {}).get('text') or '')
            text += texts[(did, bid)] + '\n'
        found = phrases(text)
        if not found:
            continue
        anchors += 1
        anchor_label = _location_label(inv, {'document_id': did, 'source_id': record['source_id'], 'unit_id': offer.get('unit_id')}, {}, {})
        for phrase in found[:LIMITS['phrases']]:
            decision = resolve(session, did, phrase, question)
            entry = {'anchor': anchor_label, 'phrase': phrase['phrase'], 'form': phrase['form'], 'quote': phrase['quote'],
                     'status': decision['status'], 'reason': decision['reason'], 'words': decision.get('words', []),
                     'documents': [d['title'] for d in decision.get('documents', [])], 'articles': []}
            decisions.append(entry)
            if decision['status'] == 'NONE':
                continue
            wanted = list(dict.fromkeys([*terms(question), *terms(phrase.get('descriptor') or ''), *terms(phrase.get('clause') or '')]))
            for target in decision['documents'][:LIMITS['targets'] if decision['status'] == 'CONFIRMED' else LIMITS['choice']]:
                tid = target['document_id']
                if tid not in walked and len(walked) >= LIMITS['documents']:
                    entry['articles'].append({'document': target['title'], 'skipped': 'DOCUMENT_LIMIT'})
                    continue
                walked.add(tid)
                try:
                    picks = target_articles(session, tid, wanted)
                except Exception as error:  # a structure failure leaves this hint out; it proves nothing
                    entry['articles'].append({'document': target['title'], 'error': type(error).__name__})
                    continue
                for pick in picks[:LIMITS['articles'] if decision['status'] == 'CONFIRMED' else 1]:
                    link = {'kind': 'DELEGATED_DOCUMENT', 'anchor_source_id': record['source_id'], 'phrase': phrase['phrase']}
                    identity, unavailable = readable_article(inv, tid, pick['unit_id'], link)
                    entry['articles'].append({'document': target['title'], 'coordinate': pick['coordinate'], 'title': pick['title'],
                                              'matched': pick['matched'], 'readable': identity is not None, 'reason': unavailable})
                    if identity is None:
                        continue
                    key = (tid, str(identity['unit_id']))
                    if key in offered or key in out or len(out) >= LIMITS['rows']:
                        continue
                    sid = identity.get('source_id')
                    if sid and known.get(sid):
                        continue  # already read
                    hint = ('읽은 「' + anchor_label + '」의 "' + phrase['phrase'] + '"가 가리키는 문서로 '
                            + ('제목이 일치' if decision['reason'] == 'TITLE_MATCH' else '제목 낱말(' + ', '.join(decision.get('words') or []) + ')이 맞는')
                            + ' 「' + target['title'] + '」' + ('' if decision['status'] == 'CONFIRMED' else '(후보 ' + str(len(decision['documents'])) + '개 중 하나)')
                            + '의 조문. 조문 제목에 질문 낱말(' + ', '.join(pick['matched']) + ')이 있음')
                    row = {'identity': identity, 'label': _location_label(inv, identity, {'heading': pick['coordinate'] + ' ' + pick['title']}, {}),
                           'delegated': hint, 'connection': link}
                    if decision['status'] == 'CONFIRMED':
                        row.update(specifies=[anchor_label], specifies_score=3 + len(pick['matched']))
                    out[key] = row
    if decisions:
        session.repo.event('DELEGATED_DOCUMENTS_RESOLVED', {'decisions': deepcopy(decisions[:12]), 'locations': [r['label'] for r in out.values()],
            'model_called': False, 'search_called': False, 'stored_as_citation': False, 'read_documents': len(read_docs)})
    return list(out.values())
