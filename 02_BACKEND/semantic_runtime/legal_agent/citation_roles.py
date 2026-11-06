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

# Further citations in the same enumeration before the governing phrase. Each
# repetition must consume a separator and a citation (no empty repetitions).
_UNIT = (r'(?:\s?제\d{1,4}항)?(?:\s?제\d{1,4}호)?(?:\s?[가-하]목)?(?:\s?각\s?호\s?외의\s?부분)?'
         r'(?:\s?(?:본문|단서|전단|후단))?')
_ITEM = r'(?:(?:같은\s?(?:법|영|규칙)\s?)?제\d{1,4}조(?:의\d{1,3})?' + _UNIT + r'|제\d{1,4}(?:항|호)' + _UNIT + r'|별표\s?\d{1,3}(?:의\d{1,3})?)'
_LIST = r'(?:\s?(?:,|ㆍ|·|및|또는|과|와)\s?' + _ITEM + r'){0,16}'
_EXCEPTION = re.compile(r'^' + _UNIT + _LIST +
    r'\s*(?:의\s*규정\s*)?(?:에도|에)\s*불구하고'
    r'|^' + _UNIT + _LIST + r'[^.。\n]{0,40}?(?:적용하지\s*아니|갈음|의\s*예외|의\s*특례)')
_MUTATIS = re.compile(r'^[^.。\n]{0,120}?준용(?:한다|하는|하여)')
_SUBJECT_AFTER = re.compile(r'^' + _UNIT + r'\s*의\s*[가-힣]{1,12}(?:은|는)\s')
_DELEGATED = re.compile(r'^' + _UNIT + r'\s*에서\s*(?:["“][^"”\n]{1,80}["”]\s*(?:이란|란|은|는)'
    r'|(?:대통령령|총리령|[가-힣]+부령|규칙|세칙|규정)\s*(?:으로|에서)\s*정(?:하는|한))')
_TRANSITIONAL = re.compile(r'^' + _UNIT + _LIST + r'\s?의?\s?개정\s?규정')
_LEAD = re.compile(r'^\s*(?:<[^>]*>\s*)*(?:[①-⑳]|\d+\.|[가-하]\.)?\s*$')
_HEADING = re.compile(r'제\d+조(?:의\d+)?\([^)]*\)\s*$')


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
    if _DELEGATED.search(after):
        return SPECIFIES
    return BORROWS
