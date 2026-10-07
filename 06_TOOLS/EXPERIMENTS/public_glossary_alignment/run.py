"""Public glossaries (econedu, nts, krx) against the 159-document corpus and MOLEG lists.

Read-only. For each headword:
  1. 본문용어 / 참고용어 — does a surface occur in some article as a morpheme-aligned
     noun span (semantic_runtime.term_morph, the MAIN matching rule), or as a whole
     phrase ending on a morpheme end (labels such as 신고·납부 that are no noun run)?
  2. 법제처 동일 표기 — same folded spelling in 법제처 법령용어목록 / 지식용어목록 /
     일상용어목록. Spelling only; meaning identity is not decided here. NTS hanja is
     compared with 법령용어목록 hanja where both exist.

Labels are split into surfaces without inventing words: the label itself, the label
with its parenthetical gloss removed, each comma/colon part inside the parenthesis,
and both sides of NTS "old→ new" renames. No LLM calls.

usage: run.py --output DIR [--workers N]
"""
import argparse, collections, json, multiprocessing as mp, re, sqlite3, sys, time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime import term_morph  # noqa: E402

DATA = ROOT / '01_DATA'
GEN = DATA / 'SEMANTIC/GENERATIONS/navigation-source-20260918-morph-v1/navigation/navigation.sqlite'
PUBLIC = DATA / 'STRUCTURE/glossaries/public-20260912'
KRX = DATA / 'LOGS/glossaries/public-20260912/krx-discovery.json'
MOLEG = DATA / 'LEXICON/moleg-alignment/alignment.sqlite'
OLD_DICT = DATA / 'LEXICON/glossary-v1/boundary-20260914-v3/dictionary.sqlite'
LISTS = {'moleg-knowledge-legal-terms': '법령용어목록',
         'moleg-knowledge-knowledge-terms': '지식용어목록',
         'moleg-knowledge-everyday-terms': '일상용어목록'}
DOTS = str.maketrans({c: '·' for c in 'ㆍ・‧∙•'})
PAREN = re.compile(r'\(([^()]*)\)')


def ro(path):
    return sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)


def key(text):
    return term_morph.fold(text.translate(DOTS))


def surfaces(label):
    """[(surface, kind)] — LABEL names the headword, ALIAS is a gloss/renamed form."""
    out = [(label, 'LABEL')]
    if '→' in label:
        for side in label.split('→'):
            out += [(s, 'LABEL') for s, _, _ in surfaces(side.strip())]
    head = PAREN.sub('', label).strip()
    if '→' not in label and head and head != label:
        out.append((head, 'LABEL'))
        for inner in PAREN.findall(label):
            out += [(p.strip(), 'ALIAS') for p in re.split(r'[,:;]', inner)
                    if p.strip() and not re.fullmatch(r'제목 ?개정|용어 ?변경', p.strip())]
    seen, result = set(), []
    for s, kind in out:
        k = key(s)
        if len(k) >= 2 and k not in seen:
            seen.add(k)
            result.append((s, k, kind))
    return result


def load_terms():
    terms = []
    for source in ('econedu', 'nts'):
        for line in open(PUBLIC / source / 'entries.jsonl', encoding='utf-8'):
            r = json.loads(line)
            terms.append({'id': r['id'], 'source': source, 'label': r['term'], 'hanja': r.get('hanja') or '',
                          'english': r.get('english') or '', 'category': r.get('category') or ''})
    for label in json.loads(KRX.read_text())['terms']:
        terms.append({'id': 'krx:catalog:' + label, 'source': 'krx', 'label': label, 'hanja': '', 'english': '', 'category': ''})
    for t in terms:
        t['surfaces'] = surfaces(t['label'])
    return terms


_WANTED = _PREFIX = None


def _init(wanted, prefix):
    global _WANTED, _PREFIX
    _WANTED, _PREFIX = wanted, prefix


def _scan(item):
    sid, text = item
    text = (text or '').translate(DOTS)
    folded = term_morph.fold(text)
    literal = {k for i in range(len(folded) - 1) for k in _PREFIX.get(folded[i:i + 2], ()) if folded.startswith(k, i)}
    if not literal:
        return sid, {}, set()
    spans = term_morph.aligned_spans(text, literal)
    rest = literal - spans.keys()
    if rest:
        prefixes = collections.defaultdict(list)
        for k in rest:
            if len(k) >= 3:
                prefixes[k[:2]].append(k)
        for k, found in term_morph.phrase_spans(text, prefixes).items():
            spans.setdefault(k, set()).update(found)
    hits = {k: sorted(v)[0] for k, v in spans.items()}
    snippets = {k: text[max(0, s - 30):e + 30].replace('\n', ' ') for k, (s, e) in hits.items()}
    return sid, snippets, literal - hits.keys()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=12)
    a = ap.parse_args()
    t0 = time.time()
    terms = load_terms()
    wanted = frozenset(k for t in terms for _, k, _ in t['surfaces'])
    prefix = collections.defaultdict(list)
    for k in wanted:
        prefix[k[:2]].append(k)

    nav = ro(GEN)
    articles = nav.execute("SELECT id,json_extract(json,'$.text') FROM source").fetchall()
    meta = {sid: (doc, name, heading) for sid, doc, name, heading in nav.execute(
        "SELECT id,document_id,json_extract(json,'$.document_name'),json_extract(json,'$.heading') FROM source")}
    print('terms', len(terms), 'surfaces', len(wanted), 'articles', len(articles), flush=True)

    hit_articles = collections.defaultdict(list)   # key -> [(sid, snippet)]
    literal_only = collections.Counter()
    with mp.get_context('fork').Pool(a.workers, initializer=_init, initargs=(wanted, dict(prefix))) as pool:
        for n, (sid, snippets, rejected) in enumerate(pool.imap_unordered(_scan, articles, chunksize=32), 1):
            for k, snip in snippets.items():
                hit_articles[k].append((sid, snip))
            literal_only.update(rejected)
            if n % 5000 == 0:
                print('articles', n, round(time.time() - t0), 's', flush=True)

    moleg = collections.defaultdict(list)
    for tid, dataset, payload in ro(MOLEG).execute('SELECT id,dataset,payload FROM terms'):
        p = json.loads(payload)
        moleg[key(p.get('label') or '')].append({
            'list': LISTS[dataset], 'id': tid, 'label': p.get('label'), 'hanja': p.get('hanja') or '',
            'homonym': (p.get('fields') or {}).get('동음이의어존재여부', '')})
    old = dict(ro(OLD_DICT).execute('SELECT entry_id,corpus_class FROM classification'))

    rows = []
    for t in terms:
        found = [(s, k, kind) for s, k, kind in t['surfaces'] if hit_articles.get(k)]
        sids = sorted({sid for _, k, _ in found for sid, _ in hit_articles[k]})
        docs = sorted({meta[s][0] for s in sids})
        examples = []
        for s, k, kind in found:
            for sid, snip in hit_articles[k][:2]:
                examples.append({'surface': s, 'document': meta[sid][1], 'heading': meta[sid][2], 'snippet': snip})
        matches = []
        for s, k, kind in t['surfaces']:
            for m in moleg.get(k, []):
                hanja = ('AGREE' if t['hanja'] and m['hanja'] and key(t['hanja']) == key(m['hanja'])
                         else 'CONFLICT' if t['hanja'] and m['hanja'] else '')
                matches.append({**m, 'surface': s, 'surface_kind': kind, 'hanja_check': hanja})
        rows.append({
            'id': t['id'], 'source': t['source'], 'label': t['label'], 'category': t['category'],
            'hanja': t['hanja'], 'english': t['english'],
            'surfaces': [{'text': s, 'kind': kind} for s, _, kind in t['surfaces']],
            'class': '본문용어' if found else '참고용어',
            'matched_surfaces': [{'text': s, 'kind': kind, 'articles': len(hit_articles[k])} for s, k, kind in found],
            'articles': len(sids), 'documents': len(docs), 'examples': examples[:3],
            'literal_only_surfaces': [s for s, k, _ in t['surfaces'] if literal_only[k] and not hit_articles.get(k)],
            'old_class': {'CORPUS_PRESENT': '본문용어', 'GENERAL_IN_THIS_CORPUS': '참고용어'}.get(old.get(t['id']), ''),
            'moleg_lists': sorted({m['list'] for m in matches}),
            'moleg_label_match': any(m['surface_kind'] == 'LABEL' for m in matches),
            'moleg': matches[:12], 'moleg_match_count': len(matches)})

    a.output.mkdir(parents=True, exist_ok=True)
    with open(a.output / 'rows.jsonl', 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    summary = {'inputs': {'generation': str(GEN.relative_to(ROOT)), 'articles': len(articles),
                          'documents': len({m[0] for m in meta.values()}), 'moleg': str(MOLEG.relative_to(ROOT)),
                          'term_morph_top_n': term_morph.TOP_N, 'term_morph_margin': term_morph.MARGIN},
               'seconds': round(time.time() - t0), 'by_source': {}}
    for source in ('econedu', 'nts', 'krx'):
        rs = [r for r in rows if r['source'] == source]
        cnt = lambda f: sum(1 for r in rs if f(r))
        summary['by_source'][source] = {
            'terms': len(rs),
            '본문용어': cnt(lambda r: r['class'] == '본문용어'),
            '참고용어': cnt(lambda r: r['class'] == '참고용어'),
            '본문용어_via_alias_only': cnt(lambda r: r['matched_surfaces'] and all(m['kind'] == 'ALIAS' for m in r['matched_surfaces'])),
            '참고용어_literal_fragment_only': cnt(lambda r: r['class'] == '참고용어' and r['literal_only_surfaces']),
            'old_vs_new': dict(collections.Counter(f"{r['old_class'] or '-'}→{r['class']}" for r in rs)),
            'moleg_any': cnt(lambda r: r['moleg_lists']),
            'moleg_label': cnt(lambda r: r['moleg_label_match']),
            'moleg_by_list': {name: cnt(lambda r, n=name: n in r['moleg_lists']) for name in LISTS.values()},
            'moleg_none': cnt(lambda r: not r['moleg_lists']),
            'class_x_moleg': dict(collections.Counter(f"{r['class']}/{'법제처有' if r['moleg_lists'] else '법제처無'}" for r in rs)),
            'nts_hanja': dict(collections.Counter(m['hanja_check'] for r in rs for m in r['moleg'] if m['hanja_check'])),
            'homonym_flagged': cnt(lambda r: any(m['homonym'] == 'Y' for m in r['moleg']))}
    (a.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
