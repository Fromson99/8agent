"""PeCab morpheme boundaries for glossary terms and question matching.

The chosen PeCab analysis supplies source spans and POS tags. It has no Kiwi-style
near-best analyses, so this tokenizer change needs a new generation and quality review.
"""
from dataclasses import dataclass
from importlib.metadata import version
import threading
import unicodedata

PACKAGE = 'pecab'
PIN = '1.0.8'
_LOCK = threading.RLock()
_ANALYZER = None


@dataclass(frozen=True)
class Token:
    form: str
    tag: str
    start: int
    len: int


def installed_version():
    return version(PACKAGE)


def analyzer():
    global _ANALYZER
    with _LOCK:
        if _ANALYZER is None:
            actual = installed_version()
            if actual != PIN:
                raise RuntimeError(f'PeCab version mismatch: expected {PIN}, installed {actual}')
            from pecab import PeCab
            _ANALYZER = PeCab()
        return _ANALYZER


def tokenize(text):
    """Source spans from PeCab 1.0.8's private _tokenize contract."""
    if not isinstance(text, str):
        raise TypeError('PeCab input must be text')
    with _LOCK:
        value = analyzer()._tokenize(text)
        if isinstance(value, dict):
            value = {key: tuple(value[key]) for key in ('terms', 'offsets', 'pos_tags')
                     if key in value}
    required = ('terms', 'offsets', 'pos_tags')
    if not isinstance(value, dict) or any(key not in value for key in required):
        raise RuntimeError('PeCab 1.0.8 token span contract changed')
    terms, offsets, tags = (value[key] for key in required)
    if not (len(terms) == len(offsets) == len(tags)):
        raise RuntimeError('PeCab token span lengths differ')
    result = []
    for form, span, tag in zip(terms, offsets, tags):
        if not (isinstance(span, (list, tuple)) and len(span) == 2
                and all(type(pos) is int for pos in span)
                and 0 <= span[0] < span[1] <= len(text)):
            raise RuntimeError('PeCab returned an invalid source span')
        if tag == 'SP':
            continue
        result.append(Token(form, tag.split('+', 1)[0], span[0], span[1] - span[0]))
    return result

NOUN_TAGS = frozenset({'NNG', 'NNP', 'XSN', 'XPN', 'SL', 'SH'})
# Pronouns and roots may open a compound (자기/NP+주식, 우리/NP+사주+조합원, 민감/XR+도)
# but never end a term, so 자기, 무엇 or 상이(한) alone are not terms.
INNER_TAGS = frozenset({'NP', 'XR'})
# Statute locators: '각 호의', '같은 조의' are unit + genitive, never 호의(好意)/조의(弔意).
LOCATOR_UNITS = '편장절관조항호목'
def fold(text):
    """Spacing-free comparison key, same as navigation_match.norm."""
    return ''.join(v for c in text for v in unicodedata.normalize('NFKC', c).casefold() if not v.isspace())


def analyses(text, top_n=1, margin=None):
    """Preserve the caller's list-of-analyses contract with PeCab's one analysis."""
    tokens = tokenize(text)
    return [tokens] if tokens else []


def runs(tokens, text):
    """Maximal runs of noun morphemes joined directly or by whitespace only.

    Each item is (start, end, may_start, may_end): a term never begins with a suffix
    (규정'상') nor ends with a prefix ('대'주 read as 대/XPN).
    """
    run, prev_end, prev = [], None, None
    for t in tokens:
        start, end = t.start, t.start + t.len
        joined = prev_end is not None and (start == prev_end or not text[prev_end:start].strip())
        # '각 호의', '제2호의': a tagger can read the locator as 호의(好意); after 각 or a
        # number the unit is a locator whatever the analysis says.
        locator = (len(t.form) == 2 and t.form[0] in LOCATOR_UNITS and t.form[1] == '의'
                   and prev is not None and (prev.form == '각' or prev.tag == 'SN'))
        prev = t
        if (t.tag in NOUN_TAGS or t.tag in INNER_TAGS) and not locator:
            if run and not joined:
                yield run
                run = []
            run.append((start, end, t.tag != 'XSN', t.tag not in INNER_TAGS and t.tag != 'XPN'))
        elif run:
            yield run
            run = []
        prev_end = end
    if run:
        yield run


def lines(text):
    """Analyse line by line so alternatives stay local to one sentence."""
    offset = 0
    for line in text.split('\n'):
        if line.strip():
            yield offset, line
        offset += len(line) + 1


def aligned_keys(text, max_tokens=12):
    """Every morpheme-aligned noun span of an article, folded without spaces."""
    keys = set()
    for base, line in lines(text):
        for tokens in analyses(line):
            for run in runs(tokens, line):
                for i in range(len(run)):
                    if not run[i][2]:
                        continue
                    for j in range(i, min(len(run), i + max_tokens)):
                        if not run[j][3]:
                            continue
                        key = fold(line[run[i][0]:run[j][1]])
                        if len(key) >= 2:
                            keys.add(key)
    return keys


def aligned_spans(text, wanted, max_tokens=12):
    """Positions of aligned_keys that are in wanted: {key: {(start, end), ...}}."""
    spans = {}
    for base, line in lines(text):
        for tokens in analyses(line):
            for run in runs(tokens, line):
                for i in range(len(run)):
                    if not run[i][2]:
                        continue
                    for j in range(i, min(len(run), i + max_tokens)):
                        if not run[j][3]:
                            continue
                        key = fold(line[run[i][0]:run[j][1]])
                        if key in wanted:
                            spans.setdefault(key, set()).add((base + run[i][0], base + run[j][1]))
    return spans


def morpheme_ends(text):
    """Offsets where some near-best analysis ends a morpheme."""
    ends = set()
    for base, line in lines(text):
        for tokens in analyses(line):
            ends.update(base + t.start + t.len for t in tokens)
    return ends


def phrase_label(label):
    """A multi-word label that is not one noun run but still ends on a noun.

    Statutory definitions name phrases (대통령령으로 정하는 경우, 홈페이지의 운영); they
    can never be a noun span, so they are matched as whole words instead (phrase_spans).
    """
    key = fold(label)
    if len(key) < 3 or key in aligned_keys(label):
        return False
    tokens = analyses(label.strip(), top_n=1)
    return bool(tokens) and tokens[0][-1].tag in NOUN_TAGS


def phrase_spans(text, prefixes, ends=None):
    """Phrase labels found in text: start on a word start, end on a morpheme end.

    prefixes maps the first two folded characters to folded phrase keys.
    """
    chars, offsets = [], []
    for index, char in enumerate(text):
        for value in unicodedata.normalize('NFKC', char).casefold():
            if not value.isspace():
                chars.append(value)
                offsets.append(index)
    folded, found = ''.join(chars), {}
    for i in range(len(folded) - 2):
        keys = prefixes.get(folded[i:i + 2])
        if not keys:
            continue
        start = offsets[i]
        if (i and offsets[i - 1] == start) or (start and text[start - 1].isalnum()):
            continue
        for key in keys:
            if folded.startswith(key, i):
                end = offsets[i + len(key) - 1] + 1
                if ends is None:
                    ends = morpheme_ends(text)
                if end in ends:
                    found.setdefault(key, set()).add((start, end))
    return found


def longest(text, has_key, key_of, short=None, *, include_nested=False):
    """Question side: left-to-right longest match inside noun runs, no overlap.

    The best analysis goes first; a near-best alternative only fills spans the best
    analysis left empty. has_key(key) tests the lexicon, key_of(span_text) builds keys.
    One-syllable keys count only when short(key) admits them (everyday words: 빚, 숏).
    """
    found, taken = [], []
    for tokens in analyses(text):
        for run in runs(tokens, text):
            i = 0
            while i < len(run):
                hit = None
                for j in range(len(run) - 1, i - 1, -1) if run[i][2] else ():
                    if not run[j][3]:
                        continue
                    start, end = run[i][0], run[j][1]
                    key = key_of(text[start:end])
                    if (len(key.replace(' ', '')) >= 2 or (short is not None and short(key))) and has_key(key):
                        if include_nested:
                            row = (start, end, key)
                            if row not in found: found.append(row)
                            continue
                        hit = (j, start, end, key)
                        break
                if hit is None:
                    i += 1
                    continue
                j, start, end, key = hit
                if not any(start < e and s < end for s, e in taken):
                    found.append((start, end, key))
                    taken.append((start, end))
                i = j + 1
    return sorted(found)
