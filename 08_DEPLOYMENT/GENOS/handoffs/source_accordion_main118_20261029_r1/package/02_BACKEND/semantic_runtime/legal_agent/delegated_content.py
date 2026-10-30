"""Lexical wording hints over exact source spans; no legal applicability judgment."""
import re

WORDING = re.compile(r'(?:대통령령|총리령|[가-힣]+부령|규칙|세칙|규정)\s*(?:으로|에서)\s*정(?:하|한)|준용|별표[^\n]{0,100}(?:따른|정한|정하는)')

def definition_wording(ref, anchor_text):
    """Exact attributed quote defining wording present at the verified endpoint.

    A lexical relationship only: it neither selects a READ nor decides whether
    the definition matters to this request. Another mention cannot donate it.
    """
    text=ref.get('source_text','');a=ref.get('mention_start');z=ref.get('mention_end')
    if not (type(a) is int and type(z) is int and 0<=a<z<=len(text)
            and ref.get('mention_text') and text[a:z]==ref['mention_text']):return None
    match=re.match(r'\s*(?:본문|단서|전단|후단)?\s*에서\s*["“]([^"”\n]{1,300})["”]\s*(?:이란|란)',text[z:])
    if not match:return None
    quote=match.group(1)
    if not WORDING.search(quote):return None
    normalized=lambda s:re.sub(r'\s+','',s)
    if normalized(quote) not in normalized(anchor_text):return None
    return {'quote':quote,'witness_start':z+match.start(1),'witness_end':z+match.end(1),
            'basis':'exact_mention_and_quoted_anchor_wording','necessity_judgment':'MODEL'}
