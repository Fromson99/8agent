"""내규 → 외규 근거 점검 — 명시 인용의 건강 상태와, 인용이 빠진 근거 후보.

내규는 외규를 바탕으로 만들었지만 문면이 그것을 다 말하지 않는다. 세 가지 문제를 본다.

  1. 명시 인용이 낡았다 — 인용한 조가 현행 외규에 없거나(이동·폐지·오기), `삭제` 됐거나,
     내규를 마지막으로 고친 뒤에 외규 조가 개정됐거나, 인용 문맥과 조 내용이 어긋난다
     (번호는 살아 있는데 내용이 다른 조로 옮겨간 경우).
  2. 근거 인용이 빠졌다 — 조문이 외규를 이름으로 부르지 않지만 내용이 외규 조와 강하게
     겹친다. 후보를 뽑아 "내규 조 → 외규 조" 매핑표 초안으로 낸다(사람이 확정).
  3. 인용이 모자란다 — 법 조만 부르고 그 조가 위임한 시행령·규정 조를 부르지 않는다.
     law.go.kr 위임 간선(delegation.json)이 있으면 채운다.

판정 신호는 문서에 무관하다 — 날짜 표시(<개정 …>), 조 번호 존재, 문자 bigram TF-IDF 유사도의
상대 비율, 위임 간선. LLM·DB 없이 원문 파일만 읽는다(읽기 전용).

    python3 06_TOOLS/EXPERIMENTS/internal_basis_audit/audit.py \
        07_DOCS/REFERENCE/EXAMPLES/task5-risk-agent/internal-rules/위험관리기준시행세칙_v2_2026.md \
        --md /tmp/audit.md --json /tmp/audit.json
"""
import argparse
import html
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM').is_dir())
DEFAULT_EXTERNAL = [ROOT / '01_DATA/RAW/external', ROOT / '01_DATA/RAW/kofia']

ARTICLE_HEAD = re.compile(r'^\s*#*\s*(제\s*\d+(?:-\d+)*\s*조(?:\s*의\s*\d+)?)\s*(?:\(([^)]*)\))?\s*(.*)$')
ARTICLE_REF = re.compile(r'제\s*(\d+(?:-\d+)*)\s*조(?:\s*의\s*(\d+))?')
DATE = re.compile(r'(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})')
ANNEX_HEAD = re.compile(r'^#{1,4}\s*\[별표\s*([\d\s의]+)\]\s*(.*)$')
MARK = re.compile(r'[<＜]\s*(?:본조신설|전문개정|개정|신설|삭제|종전)[^<>＜＞]*[>＞]')
PROMULGATION = re.compile(r'^\s*(?:제정|개정|전부개정|일부개정)\s+(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2})')
DECLARED = re.compile(r'「([^」]{2,80})」\s*(시행령|시행규칙)?[^()「」]{0,20}?\(\s*이하\s*[“"‘\']([^”"’\']{1,20})[”"’\']\s*(?:이?라\s*한다|라고\s*한다)')
SAME_LAW = re.compile(r'(?:같은|동)\s*법\s*(시행령|시행규칙)?')
QUOTED = re.compile(r'「([^」]{2,80})」\s*(시행령|시행규칙)?')
# 인용 사슬 — `제27조 및 제28조제1항`, `제3-6조ㆍ제3-11조` 처럼 이름 뒤에 조가 이어지는 동안만 이름이 걸린다.
CHAIN = re.compile(r'^[\s\d조항호목의제,ㆍ·및또는과와부터까지\-]*$')


def nospace(text):
    return re.sub(r'[\s·ㆍ]+', '', text or '')


def article_key(text):
    m = ARTICLE_REF.search(text)
    return '제' + m[1] + '조' + ('의' + m[2] if m[2] else '') if m else None


def dates_in(text):
    """본문 안 개정 표시(<개정 2013. 9. 17., 2015. 6. 18.>)의 날짜들."""
    out = []
    for mark in MARK.finditer(html.unescape(text)):
        out += ['%04d-%02d-%02d' % tuple(map(int, d)) for d in DATE.findall(mark[0])]
    return out


# ── 외규 적재 ────────────────────────────────────────────────────────────────

def split_articles(lines):
    """줄 목록 → 조 목록. 조 머리(`제N조(제목)`)가 줄 맨 앞에 올 때만 새 조다. 부칙에서 멈춘다."""
    out, cur, seen, tail = [], None, set(), False
    for line in lines:
        plain = line.strip()
        # 부칙은 건너뛰고, 그 뒤 별표는 조처럼 읽는다 — 수치 기준(적기시정조치 100% 등)이 별표에 산다.
        annex = ANNEX_HEAD.match(plain)
        if annex:
            cur = {'jo': '별표' + re.sub(r'\s+', '', annex[1]), 'title': annex[2].strip(), 'lines': []}
            out.append(cur)
            tail = True
            continue
        if re.match(r'^#*\s*부\s*칙', plain):
            tail, cur = True, None
            continue
        if tail:
            if cur is not None and plain and not re.match(r'^#{1,2}\s', plain):
                cur['lines'].append(re.sub(r'^#+\s*', '', plain))
            continue
        m = ARTICLE_HEAD.match(plain)
        # 제목이 있거나, `삭제` 이거나, 마크다운 제목 줄 전체가 조 번호뿐일 때(`### 제16조`)만 조 머리다.
        if m and (m[2] is not None or re.match(r'\s*삭제', m[3] or '') or (plain.startswith('#') and not m[3])):
            # 같은 조 번호가 다시 나오면 문서가 되풀이된 것이다(협회 조문 페이지의 탭 여럿).
            if article_key(m[1]) in seen:
                break
            seen.add(article_key(m[1]))
            cur = {'jo': article_key(m[1]), 'title': (m[2] or '').strip(), 'lines': [m[3]] if m[3] else []}
            out.append(cur)
        elif cur is not None and plain and not re.match(r'^#{1,2}\s', plain):
            cur['lines'].append(re.sub(r'^#+\s*', '', plain))
    for a in out:
        a['text'] = '\n'.join(a.pop('lines'))
        a['dates'] = dates_in(a['text'])
        a['deleted'] = bool(re.match(r'^\s*삭제', a['text'])) and len(a['text']) < 40
        a['text'] = re.sub(r'^\s*삭제\s*(?=[<＜])', '삭제 ', a['text'])
    return out


def load_external(roots):
    """외규 원문 → {이름: [조]}. law.go.kr 열람본(*.xml.md)과 협회 조문(*조문.html)을 읽는다."""
    laws = {}
    for root in roots:
        for path in sorted(Path(root).rglob('*')):
            if path.name.endswith('.xml.md'):
                lines = path.read_text(encoding='utf-8').splitlines()
                name = re.sub(r'^#\s*|\s*본문\s*$', '', lines[0]).strip() if lines else path.parent.name
            elif path.name.endswith('조문.html'):
                raw = path.read_text(encoding='utf-8', errors='ignore')
                raw = re.sub(r'(?is)<(script|style).*?</\1>', '', raw)
                text = html.unescape(re.sub(r'<[^>]+>', '\n', raw))
                lines = [l for l in (x.strip() for x in text.splitlines()) if l]
                name = re.sub(r'\s*조문$', '', path.stem).strip()
            else:
                continue
            if name in laws or '별표' in path.parts[-2]:
                continue
            arts = split_articles(lines)
            if arts:
                for a in arts:
                    a['law'] = name
                laws[name] = arts
    return laws


# ── 내규 적재 ────────────────────────────────────────────────────────────────

def read_lines(path):
    path = Path(path)
    if path.suffix == '.docx':
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml').decode('utf-8')
        paras = re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)
        return [html.unescape(''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p))) for p in paras]
    return path.read_text(encoding='utf-8').splitlines()


def load_internal(path):
    lines = read_lines(path)
    first = next((i for i, l in enumerate(lines) if ARTICLE_HEAD.match(l.strip()) and '(' in l), len(lines))
    header = [PROMULGATION.match(l.strip()) for l in lines[:first]]
    stamps = ['%04d-%02d-%02d' % tuple(map(int, DATE.search(m[1]).groups())) for m in header if m]
    title = next((re.sub(r'^#+\s*', '', l).strip() for l in lines[:first] if l.strip().startswith('#')), Path(path).stem)
    return {'name': title, 'path': str(path), 'revised': max(stamps) if stamps else None,
            'articles': split_articles(lines)}


# ── 인용 해석 ────────────────────────────────────────────────────────────────

class Resolver:
    def __init__(self, laws, registered):
        self.by_compact = {nospace(n): n for n in laws}
        self.registered = registered

    def canonical(self, name):
        name = name.strip()
        full = self.registered.get(name, name)
        return self.by_compact.get(nospace(full)), full

    def citations(self, text, declared):
        """조문 글 → [(외규 이름, 조 키 또는 None, 인용 문맥 줄)]. 이름 없이 부른 조는 내규 자기 참조라 버린다."""
        tokens = []
        for m in QUOTED.finditer(text):
            tokens.append((m.start(), m.end(), m[1] + (' ' + m[2] if m[2] else '')))
        last = None
        for m in SAME_LAW.finditer(text):
            tokens.append((m.start(), m.end(), ('@same', m[1])))
        aliases = {**self.registered, **declared}
        if aliases:
            alias_re = re.compile(r'(?<![가-힣A-Za-z])(' + '|'.join(map(re.escape, sorted(aliases, key=len, reverse=True))) + r')(?=\s*제\s*\d)')
            for m in alias_re.finditer(text):
                if not any(s <= m.start() < e for s, e, _ in tokens):
                    tokens.append((m.start(), m.end(), aliases[m[1]]))
        tokens.sort()
        out, used = [], set()
        for i, (s, e, name) in enumerate(tokens):
            if isinstance(name, tuple):
                if not last:
                    continue
                base = re.sub(r'\s*(시행령|시행규칙)$', '', last)
                name = base + (' ' + name[1] if name[1] else '')
            last = name
            stop = tokens[i + 1][0] if i + 1 < len(tokens) else len(text)
            bound = False
            for ref in ARTICLE_REF.finditer(text, e, stop):
                if not CHAIN.match(text[e:ref.start()]) and not bound:
                    break
                if bound and not CHAIN.match(text[prev:ref.start()]):
                    break
                out.append((name, article_key(ref[0]), ref.start()))
                used.add(ref.start())
                bound, prev = True, ref.end()
            if not bound:
                out.append((name, None, s))
        return out


# ── 유사도 ───────────────────────────────────────────────────────────────────

def grams(text):
    text = re.sub(r'[<＜][^<>＜＞]*[>＞]|「[^」]*」|제\s*\d+(?:-\d+)*\s*조(?:의\s*\d+)?(?:제\s*\d+\s*[항호])*', ' ', text)
    # 같은 수치를 한 표기로 — 내규는 `100분의 450`, 외규는 `450%` 로 쓴다.
    text = re.sub(r'100\s*분의\s*(\d+)', r'\1%', text)
    out = Counter()
    for tok in re.findall(r'[가-힣A-Za-z0-9]+', text):
        out.update(tok[i:i + 2] for i in range(len(tok) - 1))
        # 낱말 자체도 특징이다 — `순자본비율` 이 흔한 bigram(`자본`·`비율`)으로 흩어지지 않게.
        word = JOSA.sub('', tok)
        if len(word) >= 4 and re.fullmatch(r'[가-힣]+', word):
            out['W:' + word] += 1
    return out


JOSA = re.compile(r'(?:으로|에게|에서|이란|이라|이|가|을|를|은|는|의|에|로|와|과|란)$')


class Index:
    """외규 줄(항·호·별표 행) 단위 문자 bigram TF-IDF. 조 점수 = 가장 가까운 줄의 점수.

    조 전체를 한 벡터로 두면 긴 조·별표(적기시정조치 기준 같은)가 길이에 묻힌다.
    """

    def __init__(self, articles, common=0.03):
        self.articles = articles
        df = Counter()
        bags = [grams(a['title'] + ' ' + a['text']) for a in articles]
        for b in bags:
            df.update(b.keys())
        self.lines = [(i, line) for i, a in enumerate(articles)
                      for line in a['text'].splitlines() if len(line.strip()) >= 12]
        n = len(articles)
        self.idf = {g: math.log((n + 1) / (c + 1)) + 1 for g, c in df.items()}
        # 법문 어디에나 나오는 bigram(`한다`·`경우`·`목적`)은 짝을 가르지 못한다 — 조의 일정 비율 넘게 나오면 버린다.
        self.common = {g for g, c in df.items() if c > common * n}
        self.post = defaultdict(list)
        for k, (_, line) in enumerate(self.lines):
            for g, w in self.vector(grams(line)).items():
                self.post[g].append((k, w))

    def vector(self, bag):
        v = {g: (1 + math.log(c)) * self.idf.get(g, math.log(len(self.articles) + 1) + 1)
             for g, c in bag.items() if g not in self.common}
        norm = math.sqrt(sum(w * w for w in v.values())) or 1
        return {g: w / norm for g, w in v.items()}

    def search(self, text, limit=10, among=None, evidence=None):
        """글(여러 줄이면 줄마다 따로 묻는다) → [(조, 점수)]. evidence 에 조별 (내 줄, 외규 줄)을 채운다."""
        best = {}
        for query in [l for l in text.splitlines() if len(l.strip()) >= 8] or [text]:
            q = self.vector(grams(query))
            score = defaultdict(float)
            for g, w in q.items():
                for k, dw in self.post.get(g, ()):
                    score[k] += w * dw
            for k, s in score.items():
                i = self.lines[k][0]
                if (among is None or i in among) and s > best.get(i, (0,))[0]:
                    best[i] = (s, query, self.lines[k][1])
        ranked = sorted(best.items(), key=lambda x: -x[1][0])[:limit]
        if evidence is not None:
            evidence.update({i: v[1:] for i, v in ranked})
        return [(i, v[0]) for i, v in ranked]

    def sim(self, text, i):
        """인용 문맥 ↔ 조의 가장 가까운 줄(항·호). 긴 정의 조가 길이 때문에 억울하게 지지 않게 한다."""
        return self.line_sim(text, self.articles[i]['text'])

    def line_sim(self, text, other):
        q = self.vector(grams(text))
        best = 0.0
        for line in other.splitlines() or [other]:
            v = self.vector(grams(line))
            best = max(best, sum(w * v.get(g, 0) for g, w in q.items()))
        return best


def shared_terms(a, b, idf, k=6):
    """두 글이 함께 쓰는 드문 말 — 후보를 사람에게 보여 줄 근거."""
    words = lambda t: {w for w in re.findall(r'[가-힣]{3,}', t)}
    common = words(a) & words(b)
    rank = lambda w: -sum(idf.get(w[i:i + 2], 0) for i in range(len(w) - 1)) / max(len(w) - 1, 1)
    return sorted(common, key=rank)[:k]


# ── 점검 ─────────────────────────────────────────────────────────────────────

def load_delegation(path):
    """(법 이름, 조) ↔ (하위 규범 이름, 조) 양방향 이웃."""
    near = defaultdict(set)
    if not path or not Path(path).is_file():
        return near
    for e in json.loads(Path(path).read_text(encoding='utf-8')).get('edges', []):
        s, d = e.get('src') or {}, e.get('dst') or {}
        if s.get('jo') and d.get('jo'):
            if e.get('kind') not in ('시행령', '시행규칙', '위임행정규칙'):
                continue
            a, b = (nospace(s['name']), s['jo']), (nospace(d['name']), d['jo'])
            near[a].add((d['name'], d['jo'], e.get('kind')))
            near[b].add((s['name'], s['jo'], '상위'))
    return near


def audit(rule, laws, registered, near, top=3, floor=0.12):
    resolver = Resolver(laws, registered)
    flat = [a for arts in laws.values() for a in arts if not a['deleted']]
    index = Index(flat)
    pos = {(nospace(a['law']), a['jo']): i for i, a in enumerate(flat)}
    by_law = defaultdict(set)
    for i, a in enumerate(flat):
        by_law[nospace(a['law'])].add(i)
    all_by_key = {(nospace(a['law']), a['jo']): a for arts in laws.values() for a in arts}

    whole = '\n'.join(a['text'] for a in rule['articles'])
    declared = {}
    for m in DECLARED.finditer(whole):
        declared.setdefault(m[3].strip(), m[1].strip() + (' ' + m[2] if m[2] else ''))

    # 문서가 스스로 밝힌 근거 법 — 후보 순위의 약한 사전 신호.
    cited_laws = Counter()
    report = []
    for art in rule['articles']:
        text = art['text']
        basis_date = max(art['dates'] + ([rule['revised']] if rule['revised'] else [])) if (art['dates'] or rule['revised']) else None
        entry = {'jo': art['jo'], 'title': art['title'], 'text': text, 'basis_date': basis_date,
                 'citations': [], 'candidates': []}
        covered = set()
        for name, jo, at in resolver.citations(text, declared):
            law, full = resolver.canonical(name)
            line = text[text.rfind('\n', 0, at) + 1:(text.find('\n', at) + 1 or len(text) + 1) - 1]
            c = {'cited': full + (' ' + jo if jo else ''), 'law': law, 'jo': jo, 'context': line.strip(), 'issues': []}
            entry['citations'].append(c)
            if not law:
                c['issues'].append({'kind': 'NOT_IN_CORPUS', 'note': '외규 적재분에 없는 이름 — 내규·미수집 외규이거나 명칭 오기'})
                continue
            cited_laws[nospace(law)] += 1
            if not jo:
                continue
            key = (nospace(law), jo)
            target = all_by_key.get(key)
            if not target:
                best = index.search(c['context'], 1, by_law[nospace(law)])
                c['issues'].append({'kind': 'NO_SUCH_ARTICLE', 'note': '현행 외규에 이 조가 없다 — 이동·폐지·오기',
                                    'suggest': [flat[i]['jo'] + '(' + flat[i]['title'] + ')' for i, _ in best]})
                continue
            covered.add(pos.get(key))
            c['target_title'] = target['title']
            if target['deleted']:
                c['issues'].append({'kind': 'DELETED', 'note': target['text'][:60]})
                continue
            if basis_date and target['dates'] and max(target['dates']) > basis_date:
                newer = sorted({d for d in target['dates'] if d > basis_date})
                changed = [l for l in target['text'].splitlines() if any(d in dates_in(l) for d in newer)]
                c['issues'].append({'kind': 'AMENDED_AFTER_RULE',
                                    'note': '외규 조가 내규 기준일 %s 뒤에 개정됨(%s)' % (basis_date, ', '.join(newer)),
                                    'changed': changed[:4]})
            # 인용 바로 뒤 말이 인용한 조의 내용이다(`제3-6조에 따라 영업용순자본에서 …`). 줄 전체는 다른 인용과 섞인다.
            window = re.split(r'「|」|\n', text[at:at + 80])
            window = ' '.join(window[:2]) if window else ''
            here = index.sim(window, pos[key])
            best = [(i, index.sim(window, i)) for i, _ in index.search(window, 5, by_law[nospace(law)])]
            best = max(best, key=lambda x: x[1]) if best else None
            if best and best[0] != pos[key] and best[1] >= 2 * floor and here < 0.5 * best[1]:
                b = flat[best[0]]
                c['issues'].append({'kind': 'TOPIC_MISMATCH',
                                    'note': '인용 문맥이 인용한 조(%.2f)보다 %s(%s)와 훨씬 가깝다(%.2f) — 번호 이동 의심'
                                            % (here, b['jo'], b['title'], best[1])})
            for issue in c['issues']:
                if issue['kind'] == 'AMENDED_AFTER_RULE':
                    # 바뀐 줄이 인용 문맥과 닿는지 — 닿지 않으면 사람이 곧바로 넘길 수 있다.
                    issue['touches_context'] = any(index.line_sim(window, l) >= 2 * floor for l in issue['changed'])
            below = [(n, j) for n, j, kind in near.get(key, ()) if kind != '상위' and (nospace(n), j) in all_by_key]
            c['delegated'] = sorted({'%s %s(%s)' % (n, j, all_by_key[(nospace(n), j)]['title']) for n, j in below})
            covered.update(pos.get((nospace(n), j)) for n, j in below)
        entry['_covered'] = covered
        report.append(entry)

    # 틀 조 — `목적`·`정의`·`적용범위`·`시행일` 처럼 적재한 외규 여럿이 같은 제목으로 두는 조.
    # 근거가 문서 전체라 조 단위 짝을 제안하지 않는다(제목 빈도 비율로만 가른다).
    title_spread = Counter(t for t in {(a['law'], a['title']) for a in flat} for t in [t[1]])
    frame = lambda title: title_spread.get(title, 0) >= 0.1 * len(laws)
    for entry in report:
        covered = entry.pop('_covered')
        why = {}
        hits = index.search(entry['text'], 40, evidence=why)
        if not hits or frame(entry['title']):
            continue
        top_score = hits[0][1]
        ranked = []
        for i, s in hits:
            a = flat[i]
            prior = 1.15 if cited_laws.get(nospace(a['law'])) else 1.0
            ranked.append((s * prior, s, i))
        ranked.sort(reverse=True)
        shown = set()
        for boosted, s, i in ranked:
            if len(entry['candidates']) >= top:
                break
            if frame(flat[i]['title']) or (flat[i]['law'], flat[i]['jo']) in shown:
                continue
            shown.add((flat[i]['law'], flat[i]['jo']))
            # 절대 바닥 + 이 조에서 가장 높은 점수의 상대 비율 — 둘 다 넘어야 후보다.
            if s < floor or s < 0.6 * top_score:
                break
            a = flat[i]
            entry['candidates'].append({
                'target': '%s %s(%s)' % (a['law'], a['jo'], a['title']), 'score': round(s, 3),
                'already_cited': i in covered,
                'matched': {'rule_line': why[i][0][:120], 'external_line': why[i][1][:160]},
                'shared_terms': shared_terms(entry['text'], a['text'], index.idf)})
        if not entry['citations'] and any(not c['already_cited'] for c in entry['candidates']):
            entry['finding'] = 'UNCITED_BASIS'
        elif any(not c['already_cited'] for c in entry['candidates']) and entry['citations']:
            entry['finding'] = 'ADDITIONAL_BASIS'
    return {'rule': rule['name'], 'path': rule['path'], 'revised': rule['revised'],
            'declared_aliases': declared, 'articles': report}


# ── 보고 ─────────────────────────────────────────────────────────────────────

def render(result):
    out = ['# 근거 점검 — %s' % result['rule'], '',
           '- 원문: `%s`' % result['path'], '- 내규 기준일: %s' % (result['revised'] or '미상'),
           '- 문서 선언 약칭: %s' % (', '.join('"%s"=%s' % kv for kv in result['declared_aliases'].items()) or '없음'), '']
    issues = [(a, c, i) for a in result['articles'] for c in a['citations'] for i in c['issues']]
    out += ['## 1. 명시 인용의 문제 (%d건)' % len(issues), '']
    for a, c, i in issues:
        out.append('- **%s** %s — `%s` : %s' % (i['kind'], a['jo'], c['cited'], i['note']
                                               + (' → 후보 ' + ', '.join(i['suggest']) if i.get('suggest') else '')))
        if 'touches_context' in i:
            out[-1] += ' — 바뀐 줄이 인용 문맥과 %s' % ('닿는다 ★' if i['touches_context'] else '무관해 보인다')
        out.append('  > 내규: %s' % c['context'][:160])
        for line in i.get('changed', []):
            out.append('  > 외규 현행: %s' % line[:200])
    out += ['', '## 2. 인용 없는 근거 후보 (매핑표 초안)', '']
    for a in result['articles']:
        if a.get('finding') not in ('UNCITED_BASIS', 'ADDITIONAL_BASIS'):
            continue
        out.append('### %s(%s) — %s' % (a['jo'], a['title'], a['finding']))
        out.append('> %s' % a['text'].replace('\n', ' ')[:200])
        for c in a['candidates']:
            mark = ' (이미 인용/위임)' if c['already_cited'] else ''
            out.append('- %.3f %s%s — 공통어: %s' % (c['score'], c['target'], mark, ', '.join(c['shared_terms'])))
            out.append('  - 내규 `%s`' % c['matched']['rule_line'][:70])
            out.append('  - 외규 `%s`' % c['matched']['external_line'][:110])
        out.append('')
    cited = {c['cited'] for a in result['articles'] for c in a['citations']}
    for a in result['articles']:
        for c in a['citations']:
            c['delegated'] = [d for d in c.get('delegated', []) if d.split('(')[0] not in cited]
    chains = [(a, c) for a in result['articles'] for c in a['citations'] if c.get('delegated')]
    out += ['## 3. 인용한 조가 위임했는데 내규가 부르지 않은 하위 조 (%d건)' % len(chains), '']
    for a, c in chains:
        out.append('- %s `%s` → %s' % (a['jo'], c['cited'], ', '.join(c['delegated'][:6])))
    return '\n'.join(out) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rules', nargs='+', help='내규 파일 (.md/.txt/.docx)')
    ap.add_argument('--external', nargs='*', default=[str(p) for p in DEFAULT_EXTERNAL])
    ap.add_argument('--aliases', default=str(ROOT / '01_DATA/aliases.json'))
    ap.add_argument('--delegation', default=str(ROOT / '01_DATA/delegation.json'))
    ap.add_argument('--top', type=int, default=3)
    ap.add_argument('--md')
    ap.add_argument('--json')
    args = ap.parse_args()

    laws = load_external(args.external)
    registered = {}
    if Path(args.aliases).is_file():
        registered = {k: v for k, v in json.loads(Path(args.aliases).read_text(encoding='utf-8')).items() if isinstance(v, str)}
    near = load_delegation(args.delegation)
    print('외규 %d건 · 조 %d개 적재' % (len(laws), sum(map(len, laws.values()))), file=sys.stderr)

    results = [audit(load_internal(p), laws, registered, near, args.top) for p in args.rules]
    md = '\n'.join(render(r) for r in results)
    if args.md:
        Path(args.md).write_text(md, encoding='utf-8')
    else:
        print(md)
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
