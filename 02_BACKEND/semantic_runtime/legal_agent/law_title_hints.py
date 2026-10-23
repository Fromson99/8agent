"""Bounded title-only clues, with reversible offsets into both original strings.

No body search, model call, alias registration, source acquisition or scope grant.
Derived abbreviations are deliberately separate from registered aliases.
"""
import re
from ..navigation_match import SurfaceIndex, normalized_span, norm
from ..document_roles import role_of_metadata
from ..contracts import digest

CONTRACT = 'law-title-hints-v1'
GENERIC = {'법', '법률', '시행령', '시행규칙', '규정', '규칙', '관한', '대한', '및', '등'}
LAW_WORD = re.compile(r'(?<![가-힣A-Za-z0-9])([가-힣]{3,24}법)(?:\s*(시행령|시행규칙))?')


def span(text, start, end):
    return {'start': start, 'end': end, 'text': text[start:end]}


def suffix(text):
    m = re.search(r'(시행규칙|시행령)$', norm(text))
    return m.group() if m else ''


def subsequence(short, title):
    """A lexical possibility, not proof that the speaker meant this law."""
    if len(short) < 3 or not title.endswith('법'):
        return None
    positions = []; offset = 0
    for char in short:
        i = title.find(char, offset)
        if i < 0:
            return None
        positions.append(i); offset = i + 1
    return positions if positions[-1] == len(title)-1 else None


def hints(question, matcher, scope, *, limit=None):
    # Filter before matching and ranking; hidden names cannot shadow allowed names.
    allowed = sorted(set(scope) & set(matcher.documents))
    index = SurfaceIndex(); titles = {}; aliases = {}
    for did in allowed:
        if role_of_metadata(matcher.document_context.get(did, {})) != 'body':
            continue
        metadata = matcher.document_context.get(did, {})
        title = metadata.get('document_title') or matcher.documents[did]
        # Recent stores use the folder display path as document.name.
        # A missing real title must not turn folder labels into title evidence.
        if not metadata.get('document_title') and ('>' in title or '/' in title or '\\' in title):
            continue
        titles[did] = title
        aliases[did] = tuple(matcher.document_aliases.get(did, ()))
        for label, kind in [(title, 'EXACT_TITLE'), *[(a, 'REGISTERED_ALIAS') for a in aliases[did]]]:
            index.add(label, (did, kind, label))
    rows = {}

    def add(did, kind, surface, matches, score, label=None):
        row = {'hint_id': 'T'+digest([CONTRACT, did])[:16], 'document_id': did,
               'title': titles[did], 'match_kind': kind, 'question_span': surface,
               'title_matches': matches, 'matched_label': label,
               'identity_confirmed': kind in ('EXACT_TITLE', 'REGISTERED_ALIAS'),
               'citation_eligible': False}
        if did not in rows or score > rows[did][0]:
            rows[did] = (score, row)

    for hit in index.match(question, include_nested=True):
        for did, kind, label in hit['values']:
            # A bare base law followed by 시행령 must not masquerade as an exact base-law request.
            tail = question[hit['end']:]
            requested = re.match(r'\s*(시행규칙|시행령)', tail)
            if requested and suffix(titles[did]) != requested.group(1):
                continue
            add(did, kind, span(question, hit['start'], hit['end']),
                [span(titles[did], 0, len(titles[did]))] if kind == 'EXACT_TITLE' else [],
                (4 if kind == 'EXACT_TITLE' else 3, len(hit['key'])), label)

    for did, title in titles.items():
        title_norm, offsets = normalized_span(title); ending = suffix(title)
        base = title_norm[:-len(ending)] if ending else title_norm
        for word in LAW_WORD.finditer(question):
            short = word.group(1)
            if (word.group(2) or '') != ending or norm(short) == base:
                continue
            positions = subsequence(short, base)
            if positions is not None:
                add(did, 'DERIVED_ABBREVIATION', span(question, *word.span()),
                    [span(title, offsets[i], offsets[i]+1) for i in positions],
                    (2, len(short)/len(base)), None)

        # Title words only: legal body terms and generic 법/시행령 never seed a match.
        fragments = []
        for token in re.finditer(r'[가-힣A-Za-z0-9]+', title):
            text = token.group()
            if text in GENERIC or len(text) < 2:
                continue
            variants = [text]
            if text.endswith('법') and len(text) >= 4:
                variants.append(text[:-1])
            for part in variants:
                pindex = SurfaceIndex(); pindex.add(part, None)
                hits = pindex.match(question)
                if hits:
                    h = hits[0]
                    fragments.append((span(question, h['start'], h['end']), span(title, token.start(), token.start()+len(part))))
                    break
        matched = sum(len(norm(t['text'])) for _, t in fragments)
        # Generic two-syllable overlap alone should not flood the front with irrelevant laws.
        if fragments:
            lo = min(q['start'] for q, _ in fragments); hi = max(q['end'] for q, _ in fragments)
            nearby = question[max(0, lo-1):min(len(question), hi+10)]
            req = re.search(r'시행규칙|시행령', nearby)
            if req and ending != req.group():
                continue
            add(did, 'PARTIAL_TITLE', span(question, lo, hi), [t for _, t in fragments],
                (1, matched/max(1, len(base))), None)
    ranked = sorted(rows.values(), key=lambda pair: (tuple(-x for x in pair[0]), pair[1]['title'], pair[1]['document_id']))
    return {'contract': CONTRACT, 'candidates': [v for _, v in ranked[:limit]],
            'total_candidates': len(ranked), 'omitted_candidates': max(0, len(ranked)-limit) if limit is not None else 0,
            'navigation_hint_only': True, 'citation_eligible': False,
            'no_match_means': 'No title-form match; does not mean no relevant law exists.'}
