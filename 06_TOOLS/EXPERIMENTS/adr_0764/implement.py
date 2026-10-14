from pathlib import Path
R=Path(__file__).resolve().parents[3];p=R/'02_BACKEND/lawrag/research/candidates/adr_0764/normalized/snapshot/02_BACKEND/semantic_runtime/legal_agent/structure_query.py'
s=p.read_text();needle='def heading_term_candidates(matcher, docs, query, term_cache):'
helper='''# Match-only metadata cleanup. Legal parentheses and original display/evidence
# are untouched; dates are stripped only inside a recognized amendment marker.
_AMENDMENT_DATE = r'\\s*(?:개정|신설|전문개정|전부개정|본조신설|제목개정)\\s+[0-9][0-9년월일.,ㆍ·\\s]*'
_AMENDMENT = re.compile(r'<' + _AMENDMENT_DATE + r'>|\\[' + _AMENDMENT_DATE + r'\\]|\\(' + _AMENDMENT_DATE + r'\\)')


def matching_heading(title):
    return _AMENDMENT.sub(' ', title or '').strip()


'''
assert needle in s;s=s.replace(needle,helper+needle)
needle="set(question_terms(unit.get('title', '')))";assert needle in s;s=s.replace(needle,"set(question_terms(matching_heading(unit.get('title', ''))))")
p.write_text(s)
print('B1 match-only title normalization implemented; original and threshold unchanged')
