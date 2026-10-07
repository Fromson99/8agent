"""Project collected MOLEG lexical relations onto legal-term IDs.

User-directed exact-label rule, not a semantic approval or a LegalRelation
compiler. The complete legal catalogue controls ambiguity; immutable collected
edges control coverage. No API/LLM calls or active generation writes.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from lawrag.platform.paths import root_path
from . import glossary_assembly as assembly
from .glossary_v1 import read_db, sha

VERSION = 'moleg-legal-term-projection-v1'
CODES = {'140301': '동의어', '140302': '반의어', '140303': '상위어',
         '140304': '하위어', '140305': '연관어'}
INVERSE = {c: c for c in CODES} | {'140303': '140304', '140304': '140303'}
POLICY = {
    'matching': 'exact source label, no whitespace removal or aliases',
    'legal_namespace': 'moleg:knowledge_terms',
    'daily_namespace': 'moleg:everyday_terms',
    'zero_candidates': 'EXCLUDED; no API or semantic processing',
    'one_candidate': 'user-authorized unique exact label; declared homonym is held',
    'multiple_candidates': 'one inverse-relation witness candidate and unique source-label anchor, otherwise HELD',
    'reciprocal_evidence': 'existing opposite legal-to-daily edge; not an independent semantic evaluation',
    'direction': 'hierarchy always parent -> child, code 140304; symmetric codes ordered by ID',
    'identity': 'mapped self synonym is IDENTITY_ONLY; other self relations held',
    'conflicts': 'synonym/antonym/hierarchy pair conflict and hierarchy SCC cycles held',
    'coverage': 'all edges in explicit glossary snapshot; missing remote relations are not inferred',
    'approval': 'rule projection only; no canonical meaning membership or runtime activation',
}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def tables(db):
    db.executescript('''
      PRAGMA foreign_keys=ON;
      CREATE TABLE entry(id TEXT PRIMARY KEY,kind TEXT,label TEXT,note TEXT,
        homonym TEXT,payload_sha256 TEXT);
      CREATE INDEX entry_label ON entry(label,kind);
      CREATE TABLE daily_mapping(daily_id TEXT PRIMARY KEY REFERENCES entry(id),
        candidates TEXT,base_status TEXT,observed_relations INTEGER);
      CREATE TABLE source_request(id TEXT PRIMARY KEY,term_id TEXT,parameters TEXT,
        status TEXT,response BLOB,response_sha256 TEXT,records TEXT,error TEXT);
      CREATE TABLE official_relation(id TEXT PRIMARY KEY,source_id TEXT REFERENCES entry(id),
        target_id TEXT REFERENCES entry(id),code TEXT,label TEXT,
        request_id TEXT REFERENCES source_request(id),payload TEXT);
      CREATE TABLE decision(relation_id TEXT PRIMARY KEY REFERENCES official_relation(id),
        status TEXT,reason TEXT,mapped_legal_id TEXT REFERENCES entry(id),
        candidates TEXT,witnesses TEXT,edge_id TEXT);
      CREATE TABLE edge(id TEXT PRIMARY KEY,source_id TEXT REFERENCES entry(id),
        target_id TEXT REFERENCES entry(id),code TEXT,status TEXT,reason TEXT);
      CREATE INDEX decision_edge ON decision(edge_id,status);
      CREATE INDEX official_target ON official_relation(target_id);
      CREATE INDEX edge_source ON edge(source_id);
      CREATE INDEX edge_target ON edge(target_id);
      CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
    ''')


def normalize(source, target, code):
    if code == '140303':
        return target, source, '140304'
    if code == '140304':
        return source, target, code
    return *sorted((source, target)), code


def cycle_edges(edges):
    """Iterative Kosaraju: safe for long real-world hierarchies."""
    graph = defaultdict(set); reverse = defaultdict(set)
    for _, a, b in edges:
        graph[a].add(b); reverse[b].add(a)
    vertices = set(graph) | set(reverse)
    seen = set(); order = []
    for start in sorted(vertices):
        if start in seen:
            continue
        seen.add(start); stack = [(start, iter(graph[start]))]
        while stack:
            vertex, children = stack[-1]
            child = next(children, None)
            if child is None:
                order.append(vertex); stack.pop()
            elif child not in seen:
                seen.add(child); stack.append((child, iter(graph[child])))
    component = {}; sizes = Counter()
    for start in reversed(order):
        if start in component:
            continue
        key = len(sizes); stack = [start]; component[start] = key
        while stack:
            vertex = stack.pop(); sizes[key] += 1
            for child in reverse[vertex]:
                if child not in component:
                    component[child] = key; stack.append(child)
    return {ident for ident, a, b in edges
            if component[a] == component[b] and (a == b or sizes[component[a]] > 1)}


def project(db):
    """One terminal disposition per original edge; never form a cross product."""
    entries = {r['id']: dict(r) for r in db.execute('SELECT * FROM entry ORDER BY id')}
    legal = defaultdict(list)
    for ident, row in entries.items():
        if row['kind'] == 'knowledge_terms':
            legal[row['label']].append(ident)
    relations = [dict(r) for r in db.execute('SELECT * FROM official_relation ORDER BY id')]
    observed = Counter(r['target_id'] for r in relations)
    index = defaultdict(list)
    for r in relations:
        index[(r['source_id'], entries[r['target_id']]['label'], r['code'])].append(r['id'])
    for ident, row in entries.items():
        if row['kind'] != 'everyday_terms':
            continue
        candidates = legal.get(row['label'], [])
        status = 'NO_LEGAL_LABEL' if not candidates else (
            'UNIQUE_LEGAL_LABEL' if len(candidates) == 1 else 'MULTIPLE_LEGAL_IDS')
        db.execute('INSERT INTO daily_mapping VALUES (?,?,?,?)',
                   (ident, encode(candidates), status, observed[ident]))
    for r in relations:
        source = r['source_id']; daily = r['target_id']; code = r['code']
        candidates = legal.get(entries[daily]['label'], [])
        mapped = None; witnesses = []; edge_id = None
        if not candidates:
            status, reason = 'EXCLUDED', 'NO_LEGAL_LABEL'
        elif code not in CODES:
            status, reason = 'HELD', 'UNKNOWN_RELATION_CODE'
        elif len(candidates) == 1:
            mapped = candidates[0]
            if entries[mapped]['homonym'] == 'Y':
                mapped = None; status, reason = 'HELD', 'DECLARED_HOMONYM'
            else:
                status, reason = 'CONNECTED', 'UNIQUE_LEGAL_LABEL'
        else:
            # The opposite edge refers to the source by its label. It may only
            # disambiguate the target if this source label itself is unique.
            anchor = legal[entries[source]['label']]
            matches = {candidate: index[(candidate, entries[source]['label'], INVERSE[code])]
                       for candidate in candidates
                       if index[(candidate, entries[source]['label'], INVERSE[code])]}
            if len(anchor) == 1 and entries[source]['homonym'] != 'Y' and len(matches) == 1:
                mapped, witnesses = next(iter(matches.items()))
                status, reason = 'CONNECTED', 'UNIQUE_RECIPROCAL_RELATION'
            else:
                status, reason = 'HELD', 'AMBIGUOUS_LEGAL_LABEL'
                witnesses = sorted({w for values in matches.values() for w in values})
        if status == 'CONNECTED':
            if mapped == source:
                status = 'IDENTITY_ONLY' if code == '140301' else 'HELD'
                reason = 'SELF_SYNONYM' if code == '140301' else 'SELF_RELATION'
            else:
                a, b, normalized = normalize(source, mapped, code)
                edge_id = digest([a, b, normalized])
                db.execute('INSERT OR IGNORE INTO edge VALUES (?,?,?,?,?,?)',
                           (edge_id, a, b, normalized, 'CONNECTED', 'RULE_PROJECTED'))
        db.execute('INSERT INTO decision VALUES (?,?,?,?,?,?,?)',
                   (r['id'], status, reason, mapped, encode(candidates), encode(sorted(witnesses)), edge_id))
    # Relations such as RELATED plus a hierarchy edge are not inherently
    # contradictory. Only the explicitly incompatible combinations are held.
    pairs = defaultdict(list)
    for r in db.execute('SELECT * FROM edge'):
        pairs[tuple(sorted((r['source_id'], r['target_id'])))].append(dict(r))
    for group in pairs.values():
        codes = {r['code'] for r in group} - {'140305'}
        if len(codes) > 1:
            db.executemany("UPDATE edge SET status='HELD',reason='RELATION_KIND_CONFLICT' WHERE id=?",
                           [(r['id'],) for r in group if r['code'] != '140305'])
    cyclic = cycle_edges([(r['id'], r['source_id'], r['target_id']) for r in db.execute(
        "SELECT * FROM edge WHERE status='CONNECTED' AND code='140304'")])
    db.executemany("UPDATE edge SET status='HELD',reason='HIERARCHY_CYCLE' WHERE id=?",
                   [(ident,) for ident in sorted(cyclic)])
    db.execute("""UPDATE decision SET status='HELD',reason=(SELECT reason FROM edge WHERE id=edge_id)
        WHERE edge_id IN (SELECT id FROM edge WHERE status='HELD')""")
    db.commit()


def verify_db(db):
    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise ValueError('Projection integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('Projection foreign key failure')
    expected = db.execute('SELECT count(*) FROM official_relation').fetchone()[0]
    if expected != db.execute('SELECT count(*) FROM decision').fetchone()[0]:
        raise ValueError('Missing source edge decisions')
    if db.execute("""SELECT 1 FROM edge g JOIN entry a ON a.id=g.source_id
        JOIN entry b ON b.id=g.target_id WHERE a.kind!='knowledge_terms'
        OR b.kind!='knowledge_terms' OR g.source_id=g.target_id LIMIT 1""").fetchone():
        raise ValueError('Non-legal or self graph endpoint')
    if db.execute("""SELECT 1 FROM decision d JOIN official_relation r ON r.id=d.relation_id
        JOIN daily_mapping m ON m.daily_id=r.target_id
        WHERE m.base_status='NO_LEGAL_LABEL' AND d.status!='EXCLUDED' LIMIT 1""").fetchone():
        raise ValueError('Excluded daily term was processed')
    if db.execute("""SELECT 1 FROM edge e WHERE e.status='CONNECTED' AND NOT EXISTS
        (SELECT 1 FROM decision d WHERE d.edge_id=e.id AND d.status='CONNECTED') LIMIT 1""").fetchone():
        raise ValueError('Edge without connected source evidence')
    if cycle_edges([tuple(r) for r in db.execute(
            "SELECT id,source_id,target_id FROM edge WHERE status='CONNECTED' AND code='140304'")]):
        raise ValueError('Connected hierarchy has a cycle')
    for row in db.execute('SELECT response,response_sha256 FROM source_request WHERE response IS NOT NULL'):
        if hashlib.sha256(gzip.decompress(row[0])).hexdigest() != row[1]:
            raise ValueError('Raw response hash mismatch')
    return {'integrity': 'ok', 'foreign_keys': 'ok', 'source_edge_accounting': expected,
            'legal_endpoints_only': True, 'excluded_terms_not_processed': True,
            'connected_hierarchy_acyclic': True, 'raw_response_hashes': 'ok'}


def summaries(db):
    decisions = dict(db.execute('SELECT status,count(*) FROM decision GROUP BY status'))
    return {
        'catalogue_entries': dict(db.execute('SELECT kind,count(*) FROM entry GROUP BY kind')),
        'daily_mapping': dict(db.execute('SELECT base_status,count(*) FROM daily_mapping GROUP BY base_status')),
        'eligible_daily_without_observed_edges': db.execute("SELECT count(*) FROM daily_mapping WHERE base_status!='NO_LEGAL_LABEL' AND observed_relations=0").fetchone()[0],
        'input_relations': db.execute('SELECT count(*) FROM official_relation').fetchone()[0],
        'decisions': decisions,
        'decision_reasons': dict(db.execute('SELECT reason,count(*) FROM decision GROUP BY reason')),
        'distinct_held_daily_terms': db.execute("SELECT count(DISTINCT r.target_id) FROM decision d JOIN official_relation r ON r.id=d.relation_id WHERE d.status='HELD'").fetchone()[0],
        'distinct_excluded_observed_daily_terms': db.execute("SELECT count(DISTINCT r.target_id) FROM decision d JOIN official_relation r ON r.id=d.relation_id WHERE d.status='EXCLUDED'").fetchone()[0],
        'edges': dict(db.execute('SELECT status,count(*) FROM edge GROUP BY status')),
        'connected_relation_codes': dict(db.execute("SELECT code,count(*) FROM edge WHERE status='CONNECTED' GROUP BY code")),
        'connected_legal_nodes': db.execute("SELECT count(*) FROM (SELECT source_id FROM edge WHERE status='CONNECTED' UNION SELECT target_id FROM edge WHERE status='CONNECTED')").fetchone()[0],
    }


def export_tsv(db, path, query):
    cursor = db.execute(query)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow([d[0] for d in cursor.description])
        writer.writerows(cursor)


def build(glossary, catalogue_db, output, emit=print):
    glossary, catalogue_db, output = map(lambda p: Path(p).resolve(), (glossary, catalogue_db, output))
    if output.exists():
        raise ValueError('Output already exists; use a new version directory')
    report = assembly.inspect(glossary)
    catalogue_before = sha(catalogue_db)
    identity = {'glossary': str(glossary), 'glossary_sha256': report['dictionary_sha256'],
                'catalogue_db': str(catalogue_db), 'catalogue_db_sha256': catalogue_before,
                'collection': report['collection'], 'collection_identity': report['identity']['collection_identity'],
                'implementation_sha256': sha(Path(__file__)),
                'cli_sha256': sha(root_path('tools', 'pipeline.py'))}
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
    (temp/'policy.json').write_text(encode(POLICY)+'\n')
    (temp/'inputs.json').write_text(encode(identity)+'\n')
    emit('전체 원천 목록과 수집 관계를 고정합니다.', flush=True)
    with closing(read_db(catalogue_db)) as incoming, closing(read_db(glossary/'dictionary.sqlite')) as source, closing(sqlite3.connect(temp/'relations.sqlite')) as db:
        incoming.execute('BEGIN'); source.execute('BEGIN'); db.row_factory = sqlite3.Row; tables(db)
        catalogue_identity = json.loads(incoming.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
        if catalogue_identity != identity['collection_identity']:
            raise ValueError('Catalogue does not belong to the selected glossary collection')
        for ident, payload in incoming.execute('SELECT id,payload FROM catalogue ORDER BY id'):
            row = json.loads(payload); kind = row['entity_type']
            if kind not in {'knowledge_terms', 'everyday_terms'}:
                continue
            if ident != 'moleg:' + kind + ':' + row['source_id']:
                raise ValueError('Catalogue ID/namespace mismatch')
            fields = row.get('fields', {})
            db.execute('INSERT INTO entry VALUES (?,?,?,?,?,?)',
                       (ident, kind, row['label'], fields.get('비고', ''), fields.get('동음이의어존재여부', ''), digest(row)))
        # Newly observed neighbours absent from the older catalogue remain source
        # daily entries; never silently create a new legal mapping candidate.
        for ident, label, provenance in source.execute("SELECT id,label,provenance FROM entry WHERE id LIKE 'moleg:%'"):
            existing = db.execute('SELECT label FROM entry WHERE id=?', (ident,)).fetchone()
            if existing is not None:
                if existing[0] != label:
                    raise ValueError('Source label drift')
            elif ident.startswith('moleg:everyday_terms:'):
                db.execute('INSERT INTO entry VALUES (?,?,?,?,?,?)',
                           (ident, 'everyday_terms', label, '', '', digest(json.loads(provenance))))
        for row in source.execute('SELECT * FROM source_request ORDER BY id'):
            db.execute('INSERT INTO source_request VALUES (?,?,?,?,?,?,?,?)', tuple(row))
        for row in source.execute('SELECT * FROM official_relation ORDER BY id'):
            if not row['source_id'].startswith('moleg:knowledge_terms:') or not row['target_id'].startswith('moleg:everyday_terms:'):
                raise ValueError('Unexpected source relation namespaces')
            if row['code'] in CODES and row['label'] != CODES[row['code']]:
                raise ValueError('Relation code/label mismatch')
            db.execute('INSERT INTO official_relation VALUES (?,?,?,?,?,?,?)', tuple(row))
        db.execute('INSERT INTO meta VALUES (?,?)', ('identity', encode(identity)))
        db.execute('INSERT INTO meta VALUES (?,?)', ('policy', encode(POLICY)))
        db.commit()
        incoming.rollback(); source.rollback()
        emit('동일 표기 대응·상호 관계 대조·충돌 검사를 실행합니다.', flush=True)
        project(db)
        checks = verify_db(db); counts = summaries(db)
        export_tsv(db, temp/'decisions.tsv', '''SELECT d.status,d.reason,a.label AS source_label,
          r.source_id,b.label AS daily_label,r.target_id AS daily_id,r.label AS original_relation,
          m.label AS mapped_legal_label,d.mapped_legal_id,d.candidates,d.witnesses,d.edge_id,r.id AS relation_id
          FROM decision d JOIN official_relation r ON r.id=d.relation_id
          JOIN entry a ON a.id=r.source_id JOIN entry b ON b.id=r.target_id
          LEFT JOIN entry m ON m.id=d.mapped_legal_id ORDER BY d.status,d.reason,a.label,r.id''')
        export_tsv(db, temp/'daily-mapping.tsv', '''SELECT e.label,m.daily_id,m.base_status,m.candidates,m.observed_relations
          FROM daily_mapping m JOIN entry e ON e.id=m.daily_id ORDER BY m.base_status,e.label,m.daily_id''')
        export_tsv(db, temp/'legal-relations.tsv', '''SELECT g.status,g.reason,a.label AS source_label,
          g.source_id,g.code,b.label AS target_label,g.target_id,count(d.relation_id) AS evidence_count,g.id AS edge_id
          FROM edge g JOIN entry a ON a.id=g.source_id JOIN entry b ON b.id=g.target_id
          JOIN decision d ON d.edge_id=g.id GROUP BY g.id ORDER BY g.status,g.code,a.label,b.label''')
        edges = [dict(r) for r in db.execute("SELECT * FROM edge WHERE status='CONNECTED' ORDER BY id")]
        nodes = [dict(r) for r in db.execute("""SELECT id,label,note FROM entry WHERE id IN
          (SELECT source_id FROM edge WHERE status='CONNECTED' UNION SELECT target_id FROM edge WHERE status='CONNECTED') ORDER BY id""")]
        (temp/'graph.json').write_text(encode({'schema_version': VERSION, 'approval': 'RULE_PROJECTED',
                                            'nodes': nodes, 'edges': edges, 'relation_codes': CODES})+'\n')
    if sha(catalogue_db) != catalogue_before or sha(glossary/'dictionary.sqlite') != identity['glossary_sha256']:
        raise ValueError('Input changed during projection; output was not published')
    result = {'schema_version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
              'identity': identity, 'policy': POLICY, 'counts': counts, 'verification': checks,
              'semantic_approval': False, 'runtime_promoted': False, 'api_calls': 0, 'model_calls': 0,
              'coverage': 'Entire selected collected relation snapshot, not the entire remote API graph',
              'output': str(output)}
    result['files'] = {p.name: sha(p) for p in sorted(temp.iterdir()) if p.is_file()}
    (temp/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    d = counts['decisions']; reasons = counts['decision_reasons']
    lines = ['# 법제처 지식용어 간 관계 구축 결과', '',
             '법제처 지식용어(knowledge_terms) ID끼리 연결한 사용자 규칙 기반 DRAFT다. 본문 출현 기준의 본문용어/참고용어 분류와는 별개다.',
             '동일 표기 대응과 원천 관계를 보존하며 법적 의미 정본 승인·MAIN/RAG 활성화는 별도다.', '',
             '## 범위와 결과', '',
             f"- 입력: 선택된 용어집의 공식 관계 **{counts['input_relations']:,}건 전부**.",
             f"- 연결된 원천 관계: **{d.get('CONNECTED', 0):,}건**.",
             f"- 중복 경로를 합친 법제처 지식용어 관계: **{counts['edges'].get('CONNECTED', 0):,}개**, 노드 **{counts['connected_legal_nodes']:,}개**.",
             f"- 보류: **{d.get('HELD', 0):,}건** / 관련 법제처 일상용어 **{counts['distinct_held_daily_terms']:,}개**.",
             f"- 동일명 법제처 지식용어 없음으로 제외: **{d.get('EXCLUDED', 0):,}건** / 법제처 일상용어 **{counts['distinct_excluded_observed_daily_terms']:,}개**.",
             f"- 자기 동의어(별도 간선 불필요): **{d.get('IDENTITY_ONLY', 0):,}건**.", '',
             '## 원천 관계별 처리 사유', '', '| 사유 | 건수 |', '|---|---:|']
    lines += [f'| {reason} | {count:,} |' for reason, count in sorted(reasons.items())]
    lines += ['', '## 산출물', '',
              '- [지식용어 관계 목록](legal-relations.tsv): 연결·보류 간선, 양 끝 법제처 지식용어 ID, 근거 경로 수.',
              '- [원천 관계별 판정](decisions.tsv): 원천 관계 전수의 연결·보류·제외·동일항목 처리.',
              '- [법제처 일상용어 대응 목록](daily-mapping.tsv): 전체 목록의 동일명 지식용어 후보와 관측 관계 수.',
              '- [그래프](graph.json): 연결 규칙을 통과한 노드·간선.',
              '- [재현·검증 영수증](report.json), [원천 및 처리 DB](relations.sqlite).', '',
              '## 수집 범위', '',
              '지식용어→일상용어 수집 간선을 역으로 읽어 일상용어→지식용어 연결의 관측 부분을 재사용했다(모두 법제처 목록). 새 API 호출은 없다.',
              '같은 이름의 법제처 지식용어가 있지만 이 snapshot에서 관계가 관측되지 않은 법제처 일상용어는 '
              f"{counts['eligible_daily_without_observed_edges']:,}개다. 무관계·규칙 실패로 단정하지 않는다.",
              '관계의 누락 범위와 사전 전체를 새로 조회한 결과는 이번 전수 처리 범위가 아니다.', '',
              '## 재개·롤백', '',
              '완료본은 덮어쓰지 않는다. 새 입력은 새 --output으로 구축한다. 기본 포인터를 바꾸지 않았으므로 활성 환경의 롤백은 필요 없다.',
              '`pipeline.py glossary legal-relations verify --state <이 디렉터리>`로 출력과 원천 응답 hash·회계를 검증한다.', '']
    (temp/'REPORT.md').write_text('\n'.join(lines))
    temp.rename(output)
    return result


def inspect(state, term=None, verify=False):
    state = Path(state).resolve(); report = json.loads((state/'report.json').read_text())
    if report['schema_version'] != VERSION:
        raise ValueError('Unsupported projection version')
    for name, expected in report['files'].items():
        if sha(state/name) != expected:
            raise ValueError('Projection output hash mismatch: ' + name)
    with closing(read_db(state/'relations.sqlite')) as db:
        if verify:
            return verify_db(db)
        if term is None:
            return report
        rows = [dict(r) for r in db.execute('''SELECT g.*,a.label AS source_label,b.label AS target_label
          FROM edge g JOIN entry a ON a.id=g.source_id JOIN entry b ON b.id=g.target_id
          WHERE a.label=? OR b.label=? ORDER BY g.status,g.code,a.label,b.label''', (term, term))]
        decisions = [dict(r) for r in db.execute('''SELECT d.*,a.label AS source_label,b.label AS daily_label,
          r.code AS original_code FROM decision d JOIN official_relation r ON r.id=d.relation_id
          JOIN entry a ON a.id=r.source_id JOIN entry b ON b.id=r.target_id
          WHERE a.label=? OR b.label=? ORDER BY d.status,r.id''', (term, term))]
        return {'term': term, 'edges': rows, 'decisions': decisions, 'semantic_approval': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'inspect', 'verify'])
    parser.add_argument('--glossary', type=Path)
    parser.add_argument('--catalogue-db', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--term')
    args = parser.parse_args(argv)
    if args.action == 'build':
        config = json.loads(root_path('system', 'GLOSSARY_PIPELINE.json').read_text())
        selected = config['current_draft']
        glossary = args.glossary or root_path(selected['root_id'], selected['path'])
        assembly_report = json.loads((glossary/'report.json').read_text())
        catalogue = args.catalogue_db or Path(assembly_report['identity']['collection_path'])
        if args.output is None:
            parser.error('build requires --output for a new immutable version')
        import sys
        result = build(glossary, catalogue, args.output, emit=lambda *a, **kw: print(*a, file=sys.stderr, **kw))
    else:
        if args.state is None:
            parser.error('inspect/verify requires --state')
        result = inspect(args.state, args.term, args.action == 'verify')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
