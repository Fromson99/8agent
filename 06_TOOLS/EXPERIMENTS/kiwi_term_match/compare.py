"""Compare question->term seeding: current reverse matcher vs Kiwi noun-chunk matching.

Read-only over the pinned navigation-source generation. No LLM, no serving change.
Kiwi path: morphemes decide where a term may start and end, so endings (하나요),
verbs (위해) and article fragments (조의) cannot become terms.
"""
import argparse, collections, glob, json, sqlite3, sys, time
from pathlib import Path
from types import SimpleNamespace

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime import navigation_match as nm  # noqa: E402

GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1'
NOUN = {'NNG', 'NNP', 'XSN', 'XPN', 'SL', 'SH'}


def ro(path):
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


class KiwiIndex:
    """Same match() shape as SurfaceIndex, anchored on Kiwi noun chunks."""

    def __init__(self, surface_index, kiwi):
        self.values, self.kiwi = surface_index.values, kiwi

    def chunks(self, text):
        run, prev_end = [], None
        for t in self.kiwi.tokenize(text):
            start, end = t.start, t.start + t.len
            joined = prev_end is not None and (start == prev_end or not text[prev_end:start].strip())
            if t.tag in NOUN:
                if run and not joined:
                    yield run; run = []
                run.append((start, end))
            elif run:
                yield run; run = []
            prev_end = end
        if run:
            yield run

    def match(self, text):
        result = []
        for run in self.chunks(text):
            i = 0
            while i < len(run):
                hit = None
                for j in range(len(run) - 1, i - 1, -1):
                    s, e = run[i][0], run[j][1]
                    key = nm.spaced(text[s:e])
                    if len(key.replace(' ', '')) >= 2 and key in self.values:
                        hit = (j, s, e, key); break
                if hit is None:
                    i += 1; continue
                j, s, e, key = hit
                result.append({'key': key, 'start': s, 'end': e, 'text': text[s:e], 'values': self.values[key]})
                i = j + 1
        return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / '09_ARTIFACTS/AUDITS/20260918-kiwi-term-match')
    a = ap.parse_args()
    t0 = time.time()
    L = ro(glob.glob(str(GEN / 'glossary/cache/*.sqlite'))[0])
    I = ro(GEN / 'glossary/bundle/identity.sqlite')
    NV = ro(GEN / 'navigation/navigation.sqlite')
    terms = {r[0]: json.loads(r[1]) for r in NV.execute('SELECT id,json FROM term')}
    df = dict(NV.execute('SELECT term_id,n FROM term_stats').fetchall())
    total = NV.execute('SELECT count(*) FROM source').fetchone()[0]
    scope = sorted(r[0] for r in ro(GEN / 'store.sqlite').execute('SELECT document_id FROM document'))

    body = nm.SurfaceIndex(spacing=True)
    marks = ','.join('?' * len(nm.ReverseMatcher.TERM_SOURCES))
    for label, key in L.execute('SELECT DISTINCT label,key FROM label WHERE length(key)>=2 AND source IN (' + marks + ')',
                                nm.ReverseMatcher.TERM_SOURCES):
        body.add(label, key)
    from kiwipiepy import Kiwi
    kiwi_index = KiwiIndex(body, Kiwi())
    # User dictionary: only curated legal-term sources, never the knowledge base
    # (it registers 하나/경우/해당) or everyday words.
    D = ro(GEN / 'glossary/dictionary.sqlite')
    words = {r[0] for r in D.execute("SELECT label FROM entry WHERE id LIKE 'moleg:legal_terms:%' "
                                     "OR source IN ('econedu','nts')")}
    words |= {r[0] for r in L.execute("SELECT DISTINCT label FROM label WHERE source='fibo'")}
    words = {w for w in words if 2 <= len(w) <= 20 and all('가' <= c <= '힣' for c in w)}
    user_kiwi = Kiwi()
    for w in sorted(words):
        user_kiwi.add_user_word(w, 'NNP', 0)
    user_index = KiwiIndex(body, user_kiwi)
    print('user words', len(words))
    # Register only words plain Kiwi cannot already read as a noun sequence, so a
    # dictionary word never overrides a correct analysis (기부여 -> 기+부여 stays).
    plain = Kiwi()
    missing = sorted(w for w in words
                     if not all(t.tag in NOUN for t in plain.tokenize(w)))
    fix_kiwi = Kiwi()
    for w in missing:
        fix_kiwi.add_user_word(w, 'NNP', 0)
    fix_index = KiwiIndex(body, fix_kiwi)
    print('user words (noun-unreadable only)', len(missing), missing[:30])

    def matcher(index):
        m = nm.ReverseMatcher.__new__(nm.ReverseMatcher)
        m.tools = SimpleNamespace(validate_scope=lambda x: x, terms=terms, db=NV)
        m.glossary = SimpleNamespace(dbs={'lookup': L, 'identity': I})
        m.documents, m.document_context = {}, {}
        m.document_names, m.structures, m.body = nm.SurfaceIndex(), nm.SurfaceIndex(), index
        return m

    arms = {'current': matcher(body), 'kiwi': matcher(kiwi_index), 'kiwi_dict': matcher(user_index), 'kiwi_fix': matcher(fix_index)}
    golden = json.loads((ROOT / '01_DATA/GOLDEN/registry-v1.json').read_text())
    items = golden if isinstance(golden, list) else next(v for v in golden.values() if isinstance(v, list))
    questions = [(it['id'], it['question'].split('\n')[0]) for it in items if it.get('question')]

    rows, freq = [], {k: collections.Counter() for k in arms}
    for qid, q in questions:
        row = {'id': qid, 'question': q}
        for name, m in arms.items():
            seeds = m.starts(q, scope)['terms']
            surfaces = collections.OrderedDict()
            for t in seeds:
                for s in t['question_spans']:
                    surfaces.setdefault(s['text'], set()).add(t['id'])
            ranked = sorted(surfaces, key=lambda s: -max((total / (df.get(t, 0) + 1)) for t in surfaces[s]))
            row[name] = {'candidates': len(seeds), 'surfaces': ranked,
                         'bridged': sorted({terms[t['id']]['label'] + '←' + t['question_spans'][0]['text']
                                            for t in seeds if t.get('bridged_from')})}
            freq[name].update(list(surfaces))
        rows.append(row)

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    n = len(rows)
    summary = {name: {'questions': n,
                      'avg_candidates': round(sum(r[name]['candidates'] for r in rows) / n, 1),
                      'avg_surfaces': round(sum(len(r[name]['surfaces']) for r in rows) / n, 2),
                      'top_surfaces': freq[name].most_common(30)} for name in arms}
    only = {'current_only': (freq['current'] - freq['kiwi_dict']).most_common(40),
            'kiwi_dict_only': (freq['kiwi_dict'] - freq['current']).most_common(40),
            'dict_gain_over_kiwi': (freq['kiwi_dict'] - freq['kiwi']).most_common(40),
            'dict_loss_over_kiwi': (freq['kiwi'] - freq['kiwi_dict']).most_common(40),
            'fix_gain_over_kiwi': (freq['kiwi_fix'] - freq['kiwi']).most_common(40),
            'fix_loss_over_kiwi': (freq['kiwi'] - freq['kiwi_fix']).most_common(40),
            'current_only_vs_fix': (freq['current'] - freq['kiwi_fix']).most_common(40)}
    (a.out / 'summary.json').write_text(json.dumps({'summary': summary, 'diff': only,
                                                    'seconds': round(time.time() - t0)}, ensure_ascii=False, indent=1))
    print(json.dumps({k: {x: y for x, y in v.items() if x != 'top_surfaces'} for k, v in summary.items()}, ensure_ascii=False))
    for k, v in only.items():
        print(k, v[:25])


if __name__ == '__main__':
    main()
