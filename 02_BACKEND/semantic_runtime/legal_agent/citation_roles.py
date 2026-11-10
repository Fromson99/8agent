"""Deterministic role of one verified citation, from standard statutory phrasing.

A role is a reading policy, not a legal conclusion. From the cited article's
point of view an incoming citation either completes or overrides its rule
(SPECIFIES / EXCEPTION: read together with it) or reuses / extends it for a
different subject (BORROWS / MUTATIS: list only). No model call; the same
witness text always yields the same role.
"""
import re

SPECIFIES = 'SPECIFIES'    # "제433조제1항의 결의는 …", "법 제5조에서 대통령령으로 정하는 ~란"
EXCEPTION = 'EXCEPTION'    # "제X조에도 불구하고", "제X조를 적용하지 아니한다", "제X조의 통지를 갈음"
MUTATIS = 'MUTATIS'        # "제X조를 준용한다"
BORROWS = 'BORROWS'        # "제X조에 따른 결의로 …"
TRANSITIONAL = 'TRANSITIONAL'  # 부칙 "제X조의 개정규정에도 불구하고 종전의 규정에 따른다", "…의 개정규정은 … 적용한다"
PAIR_ROLES = (SPECIFIES, EXCEPTION)
# Finer relation kinds for an incoming link that stays a BORROWS/MUTATIS role (cards, never an automatic read).
APPLIES_CASE = 'APPLIES_CASE'  # "…하는 때에는 … 제X조에 따른 ○○으로 한다/본다"
IMPLEMENTS = 'IMPLEMENTS'      # 하위 규정의 "법 제X조에 따른 ○○ / 제X조에 따라"
CARD_KINDS = (MUTATIS, APPLIES_CASE, IMPLEMENTS)

# Further citations in the same enumeration before the governing phrase. Each
# repetition must consume a separator and a citation (no empty repetitions).
_UNIT = (r'(?:\s?제\d{1,4}항)?(?:\s?제\d{1,4}호)?(?:\s?[가-하]목)?(?:\s?각\s?[호목]\s?외의\s?부분)?'
         r'(?:\s?(?:본문|단서|전단|후단))?')
_ITEM = r'(?:(?:같은\s?(?:법|영|규칙)\s?)?제\d{1,4}조(?:의\d{1,3})?' + _UNIT + r'|제\d{1,4}(?:항|호)' + _UNIT + r'|별표\s?\d{1,3}(?:의\d{1,3})?)'
_LIST = r'(?:\s?(?:,|ㆍ|·|및|또는|과|와)\s?' + _ITEM + r'){0,16}'
_EXCEPTION = re.compile(r'^' + _UNIT + _LIST +
    r'\s*(?:의\s*규정\s*)?(?:에도|에)\s*불구하고'
    r'|^' + _UNIT + _LIST + r'[^.。\n]{0,40}?(?:적용하지\s*아니|갈음|의\s*예외|의\s*특례)')
_MUTATIS = re.compile(r'^[^.。\n]{0,120}?준용(?:한다|하는|하여)')
_SUBJECT_AFTER = re.compile(r'^' + _UNIT + r'\s*(?:의\s*[가-힣]{1,12})?(?:은|는)\s')
_DELEGATED = re.compile(r'^' + _UNIT + r'\s*에서\s*(?:["“][^"”\n]{1,300}["”]\s*(?:이란|란|은|는)'
    r'|(?:대통령령|총리령|[가-힣]+부령|규칙|세칙|규정)\s*(?:으로|에서)\s*정(?:하는|한))')
_APPLY_WHEN = re.compile(r'^' + _UNIT + _LIST + r'\s*(?:을|를|의\s*규정을)\s*적용(?:할\s*때|함에\s*있어|하는\s*경우)')
_APPLIES_CASE = re.compile(r'^' + _UNIT + _LIST + r'\s*(?:에\s*따른|에\s*의한|의\s*규정에\s*의한|의\s*규정에\s*따른)\s'
    r'[^.。\n,]{0,20}?(?:으로|로)\s*(?:한다|본다|보며|보아)')
_TRANSITIONAL = re.compile(r'^' + _UNIT + _LIST + r'\s?의?\s?개정\s?규정')
_LEAD = re.compile(r'^\s*(?:<[^>]*>\s*)*(?:[①-⑳]|\d+\.|[가-하]\.)?\s*(?:법|영|규정|「[^」\n]{1,60}」)?\s*$')
_HEADING = re.compile(r'제\d+조(?:의\d+)?\([^)]*\)\s*$')
_MUT_AFTER = re.compile(r'(?:은|는)\s*([^.,。\n]{2,60}?)\s?(?:에\s*관하여|에\s*대하여|의\s*경우에|에)\s*(?:이를\s*|각각\s*)?준용')
_MUT_BEFORE = re.compile(r'([가-힣A-Za-z0-9ㆍ·\s]{2,60}?)\s?(?:에\s*관하여는?|에\s*대하여는?|에\s*대해서는|의\s*경우에는?)\s*$')
_TAIL_TOKEN = re.compile(r'(?:제\d{1,4}(?:조(?:의\d{1,3})?|항|호(?:의\d{1,3})?)|[가-하]목|「[^」\n]{1,60}」|같은\s?(?:법|영|규칙|조|항)'
                         r'|및|또는|부터|까지|내지|[,ㆍ·])\s*$')
_SENTENCE_END = re.compile(r'(?<=[다함음임])\.(?=\s|$|<)|\n')
_LOWER_SUFFIX = ('시행령', '시행규칙', '시행세칙')


def role(text, start, end):
    """Role of the mention text[start:end] for the article it cites."""
    if not (isinstance(text, str) and type(start) is int and type(end) is int and 0 <= start < end <= len(text)):
        return BORROWS
    after = text[end:end + 160]
    if _TRANSITIONAL.search(after):
        return TRANSITIONAL
    if _EXCEPTION.search(after):
        return EXCEPTION
    if _MUTATIS.search(after):
        return MUTATIS
    before = _HEADING.sub('', text[:start])
    sentence_start = before.rsplit('.', 1)[-1] if '.' in before else before
    if _LEAD.match(sentence_start) and _SUBJECT_AFTER.search(after):
        return SPECIFIES
    if _DELEGATED.search(text[end:end + 400]) or _APPLY_WHEN.search(after):
        return SPECIFIES
    return BORROWS


def sentence(text, start, end, limit=200):
    """The one sentence holding the mention, whitespace-collapsed and clipped around it."""
    if not (isinstance(text, str) and type(start) is int and type(end) is int and 0 <= start < end <= len(text)):
        return ''
    head = 0
    for match in _SENTENCE_END.finditer(text, max(0, start - 600), start):
        head = match.end()
    head = max(head, start - 600)
    tail = _SENTENCE_END.search(text, end, min(len(text), end + 600))
    stop = tail.end() if tail else min(len(text), end + 600)
    before = re.sub(r'\s+', ' ', text[head:start]); after = re.sub(r'\s+', ' ', text[end:stop])
    mention = re.sub(r'\s+', ' ', text[start:end])
    room = max(0, limit - len(mention))
    lead = before[-(room // 2):] if room // 2 else ''
    rest = room - len(lead)
    if len(after) > rest > 60:
        # A long enumeration: keep the governing phrase at the sentence end.
        after = after[:rest - 50] + ' … ' + after[-46:]
    return (lead + mention + after[:max(rest, 0) + 3]).strip()


def _document(name):
    parts = [p.strip() for p in (name or '').split(' > ')]
    if '별표서식' in parts:
        parts = parts[:parts.index('별표서식')]
    return parts[-1] if parts else ''


def lower_regulation(citing_document, cited_document):
    """시행령·시행규칙·시행세칙 citing the rule it implements (same base name, lower rank)."""
    a, b = _document(citing_document), _document(cited_document)
    def split(name):
        for rank, suffix in ((1, '시행령'), (2, '시행규칙'), (2, '시행세칙')):
            if name.endswith(suffix):
                return name[:-len(suffix)].strip(), rank
        return name, 0
    (base_a, rank_a), (base_b, rank_b) = split(a), split(b)
    return bool(a and b and base_a == base_b and rank_a > rank_b)


def subject(text, start, end):
    """For a 준용 sentence, the subject it is extended to ("감사", "유한회사의 이사"); else None."""
    if role(text, start, end) != MUTATIS:
        return None
    head = _HEADING.sub('', re.sub(r'\s+', ' ', text[max(0, start - 300):start]))
    for _ in range(80):
        match = _TAIL_TOKEN.search(head)
        if not match:
            break
        head = head[:match.start()]
    found = _MUT_BEFORE.search(head)
    if found and not re.search(r'(?:이|그)\s*경우$', found.group(1).strip()):
        return found.group(1).strip()[-40:].split('. ')[-1].strip()
    found = _MUT_AFTER.search(re.sub(r'\s+', ' ', text[end:end + 300]))
    if found and not re.match(r'(?:이|그)\s*경우|전항|제\d', found.group(1)):
        return found.group(1).strip()
    return None


def relation(text, start, end, *, citing_document='', cited_document='', declared_name=False):
    """Finer reading kind of one citation; BORROWS covers what the phrasing cannot tell."""
    kind = role(text, start, end)
    if kind == BORROWS and isinstance(text, str) and type(end) is int:
        if _APPLIES_CASE.search(text[end:end + 160]):
            kind = APPLIES_CASE
        elif citing_document != cited_document and (declared_name or lower_regulation(citing_document, cited_document)):
            kind = IMPLEMENTS
    return {'kind': kind, 'subject': subject(text, start, end) if kind == MUTATIS else None,
            'sentence': sentence(text, start, end)}
