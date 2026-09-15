"""Evidence-bound lexical observations. No canonical membership or runtime writes.

Field/enum authority is the versioned legal schema, including in a frozen candidate.
Definition source units remain candidates: this does not split polysemous prose.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
from jsonschema import Draft202012Validator


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


from lawrag.platform.paths import repository_root

ROOT = repository_root()
REGISTRY = json.loads((ROOT/'00_SYSTEM/GLOSSARY_SCHEMA.json').read_text())
CONTRACT = REGISTRY['authoring_contracts']['GLOSSARY_REVIEW']
SCHEMA_PATH = ROOT/CONTRACT['path']
if hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest() != CONTRACT['sha256']:
    raise ValueError('Lexical schema registry hash mismatch')
NORMATIVE = json.loads(SCHEMA_PATH.read_text())


def response_schema(context=None):
    def expand(value):
        if isinstance(value, list):
            return [expand(x) for x in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            return expand(NORMATIVE['$defs'][value['$ref'].split('/')[-1]])
        return {k: expand(v) for k, v in value.items()}
    result = expand(NORMATIVE['$defs']['SenseReviewResponse'])
    if context is not None:
        allowed = sorted(e['id'] for e in context['evidence'])
        def bind(value):
            if not isinstance(value, dict):
                return
            for key, child in value.get('properties', {}).items():
                if key == 'evidence_ids':
                    if allowed:
                        child['items']['enum'] = allowed
                    else:
                        child['maxItems'] = 0
                bind(child)
            bind(value.get('items'))
        bind(result)
    return result


def evidence_bundle(entry, items):
    """One candidate per explicit source definition, plus its definition context.

    Offsets are Unicode character offsets into the immutable selected source field.
    The original upstream locator remains in provenance; no document IDs are invented.
    """
    sources = {}; evidence = []; candidates = []
    contexts = [x for x in items if x['kind'] == 'DEFINITION_CONTEXT']
    for primary in items:
        if primary['kind'] == 'DEFINITION_CONTEXT':
            continue
        if primary.get('truncated'):
            continue
        local_sources = []; local_evidence = []
        for item in [primary, *contexts]:
            if item.get('truncated'):
                continue
            text = item['text']
            if not text.strip():
                continue
            expected = item.get('source_text_sha256', item.get('sha256'))
            if expected != text_hash(text):
                raise ValueError('Source text hash mismatch')
            source = {'entry_id': entry['id'], 'kind': item['kind'], 'text': text,
                      'sha256': expected, 'provenance': item.get('provenance', {})}
            sid = 'lexsrc:' + digest(source)
            sources[sid] = source; local_sources.append(sid)
            # Keep complete source text as context; sentence IDs select exact spans.
            start = 0
            ends = [m.end() for m in re.finditer(r'(?<=[.!?。])\s+|\n+', text)] + [len(text)]
            for end in ends:
                lo, hi = start, end; start = end
                while lo < hi and text[lo].isspace(): lo += 1
                while hi > lo and text[hi-1].isspace(): hi -= 1
                if hi == lo: continue
                span = {'source_id': sid, 'start': lo, 'end': hi,
                        'text': text[lo:hi], 'quote_sha256': text_hash(text[lo:hi]),
                        'kind': item['kind']}
                eid = 'lexev:' + digest(span)
                evidence.append({'id': eid, **span}); local_evidence.append(eid)
        if not local_evidence: continue
        scope = entry.get('scope') or {'status': 'UNRESOLVED',
            'document_id': entry.get('document_id'),
            'document_version_id': entry.get('document_version_id'),
            'document_sha256': entry.get('document_sha256'),
            'scope_hints': entry.get('scope_hints', [])}
        candidate = {'entry_id': entry['id'], 'label': entry['label'],
                     'definition_source_id': local_sources[0], 'scope': scope,
                     'evidence_ids': sorted(set(local_evidence)), 'status': 'PROPOSED',
                     'sense_partition': 'SOURCE_DEFINITION_UNIT_UNREVIEWED'}
        candidate['id'] = 'lexsense:' + digest(candidate)
        candidates.append(candidate)
    return candidates, sources, {e['id']: e for e in evidence}


def pair_context(left, right, left_bundle, right_bundle):
    sources = {**left_bundle[1], **right_bundle[1]}
    evidence = {**left_bundle[2], **right_bundle[2]}
    ids = set(left['evidence_ids'] + right['evidence_ids'])
    selected = [evidence[x] for x in sorted(ids)]
    source_ids = {e['source_id'] for e in selected}
    return {'left_sense': left, 'right_sense': right,
            'sources': {s: sources[s] for s in sorted(source_ids)}, 'evidence': selected,
            'scope_key': digest(sorted([left['scope'], right['scope']], key=lambda x: json.dumps(x, sort_keys=True))),
            'applicability': 'SUPPLIED_SOURCE_ONLY_NOT_LEGAL_APPLICABILITY'}


def validate_context(context):
    evidence = {e['id']: e for e in context['evidence']}
    if len(evidence) != len(context['evidence']):
        raise ValueError('Duplicate evidence IDs')
    for sid, source in context['sources'].items():
        if sid != 'lexsrc:' + digest(source) or text_hash(source['text']) != source['sha256']:
            raise ValueError('Source identity/hash mismatch')
    for eid, e in evidence.items():
        source = context['sources'][e['source_id']]
        if not 0 <= e['start'] < e['end'] <= len(source['text']):
            raise ValueError('Invalid source offsets')
        if source['text'][e['start']:e['end']] != e['text'] or text_hash(e['text']) != e['quote_sha256']:
            raise ValueError('Evidence span/quote mismatch')
        if eid != 'lexev:' + digest({k: v for k, v in e.items() if k != 'id'}):
            raise ValueError('Evidence identity mismatch')
    for side in ('left_sense', 'right_sense'):
        sense = context[side]
        if sense['id'] != 'lexsense:' + digest({k: v for k, v in sense.items() if k != 'id'}):
            raise ValueError('Sense identity mismatch')
        if not sense['evidence_ids'] or set(sense['evidence_ids']) - evidence.keys():
            raise ValueError('Sense evidence missing')
        if sense['definition_source_id'] not in context['sources']:
            raise ValueError('Definition source missing')
        if any(context['sources'][evidence[e]['source_id']]['entry_id'] != sense['entry_id'] for e in sense['evidence_ids']):
            raise ValueError('Evidence belongs to another source entry')
    expected_scope = digest(sorted([context['left_sense']['scope'], context['right_sense']['scope']], key=lambda x: json.dumps(x, sort_keys=True)))
    if context['scope_key'] != expected_scope: raise ValueError('Scope binding mismatch')
    return evidence


def validate(value, job, context):
    Draft202012Validator(response_schema(context)).validate(value)
    if value['job_id'] != job['id'] or value['input_sha256'] != job['input_sha256']:
        raise ValueError('Review output belongs to another job/input')
    if digest(context) != job['input_sha256']:
        raise ValueError('Review input hash mismatch')
    evidence = validate_context(context)
    if not value['rationale'].strip(): raise ValueError('Review rationale is empty')
    identity = value['identity']['decision']
    if (identity == 'UNKNOWN' or value['relation_assessment'] == 'UNKNOWN') and not value['missing_information'].strip():
        raise ValueError('Unknown assessment requires missing information')
    relations = value['relations']
    if (value['relation_assessment'] == 'IDENTIFIED') != bool(relations):
        raise ValueError('Relation assessment/list mismatch')
    kinds = [r['kind'] for r in relations]
    if len(set(kinds)) != len(kinds): raise ValueError('Duplicate relation kind')
    if len(set(kinds) & {'BROADER_THAN', 'NARROWER_THAN', 'OVERLAPS'}) > 1:
        raise ValueError('Contradictory inclusion relations')
    if relations and identity != 'DIFFERENT':
        raise ValueError('Distinct-sense relationship requires DIFFERENT identity')
    claims = [(value['identity'], identity != 'UNKNOWN', identity == 'DIFFERENT')]
    claims += [(r, True, False) for r in relations]
    for claim, required, allow_notes in claims:
        selected = set(claim['evidence_ids'])
        if selected - evidence.keys(): raise ValueError('Unknown evidence ID')
        if not required: continue
        for side in ('left_sense', 'right_sense'):
            own = selected & set(context[side]['evidence_ids'])
            if not own: raise ValueError('Each assertion requires evidence from both sides')
            primary = context[side]['definition_source_id']
            own_primary = [evidence[e] for e in own if evidence[e]['source_id'] == primary]
            if not own_primary: raise ValueError('Each side requires its own definition evidence')
            if not allow_notes and all(e['kind'] == 'SOURCE_SENSE_NOTE' for e in own_primary):
                raise ValueError('Sense note cannot establish equivalence or relationship')
    return value


def hydrate(value, context):
    """Only system-owned source bytes populate quotation fields."""
    evidence = validate_context(context)
    def citations(ids):
        return [{'evidence_id': eid, 'source_id': evidence[eid]['source_id'],
                 'start': evidence[eid]['start'], 'end': evidence[eid]['end'],
                 'quote': context['sources'][evidence[eid]['source_id']]['text'][evidence[eid]['start']:evidence[eid]['end']],
                 'quote_sha256': evidence[eid]['quote_sha256']} for eid in ids]
    result = copy.deepcopy(value)
    result['identity']['citations'] = citations(value['identity']['evidence_ids'])
    for claim in result['relations']: claim['citations'] = citations(claim['evidence_ids'])
    return result


def create_tables(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS sense_candidate(id TEXT PRIMARY KEY,entry_id TEXT NOT NULL,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS sense_source(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS sense_assertion(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,
        axis TEXT NOT NULL,value TEXT NOT NULL,source TEXT NOT NULL REFERENCES sense_candidate(id),
        target TEXT NOT NULL REFERENCES sense_candidate(id),scope_key TEXT NOT NULL,
        evidence_json TEXT NOT NULL,status TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS sense_conflict(id TEXT PRIMARY KEY,kind TEXT NOT NULL,assertion_ids TEXT NOT NULL);
    ''')


def store(db, value, context):
    validate(value, {'id': value['job_id'], 'input_sha256': value['input_sha256']}, context)
    enriched = hydrate(value, context)
    for s in (context['left_sense'], context['right_sense']):
        db.execute('INSERT OR IGNORE INTO sense_candidate VALUES (?,?,?)', (s['id'], s['entry_id'], json.dumps(s, ensure_ascii=False)))
    for sid, source in context['sources'].items():
        db.execute('INSERT OR IGNORE INTO sense_source VALUES (?,?)', (sid, json.dumps(source, ensure_ascii=False)))
    left, right = context['left_sense']['id'], context['right_sense']['id']
    claims = [('IDENTITY', enriched['identity']['decision'], enriched['identity']['citations'])]
    claims += [('RELATION', r['kind'], r['citations']) for r in enriched['relations']]
    claims += [('RELATION_ASSESSMENT', value['relation_assessment'], [])]
    for axis, kind, citations in claims:
        source, target = left, right
        if kind == 'NARROWER_THAN': source, target, kind = right, left, 'BROADER_THAN'
        elif kind != 'BROADER_THAN': source, target = sorted([left, right])
        ident = 'lexassert:' + digest([value['job_id'], axis, kind, source, target])
        db.execute('INSERT INTO sense_assertion VALUES (?,?,?,?,?,?,?,?,?)',
                   (ident, value['job_id'], axis, kind, source, target, context['scope_key'],
                    json.dumps(citations, ensure_ascii=False), 'PROPOSED'))
    return enriched


def detect_conflicts(db):
    """Flag review conflicts; never union canonical meanings or erase observations."""
    rows = [dict(zip(('id','axis','value','source','target','scope_key'), r)) for r in
            db.execute('SELECT id,axis,value,source,target,scope_key FROM sense_assertion')]
    conflicts = []
    for scope in sorted({r['scope_key'] for r in rows}):
        group = [r for r in rows if r['scope_key'] == scope]
        same = [r for r in group if r['axis'] == 'IDENTITY' and r['value'] == 'SAME']
        broader = [r for r in group if r['axis'] == 'RELATION' and r['value'] == 'BROADER_THAN']
        def path(edges, start, target, symmetric=False):
            stack = [(start, [])]; visited = set()
            while stack:
                node, ids = stack.pop()
                if node == target: return ids
                if node in visited: continue
                visited.add(node)
                for edge in edges:
                    if edge['source'] == node: stack.append((edge['target'], ids+[edge['id']]))
                    elif symmetric and edge['target'] == node: stack.append((edge['source'], ids+[edge['id']]))
            return None
        for row in group:
            if row['axis'] == 'IDENTITY' and row['value'] == 'DIFFERENT':
                ids = path(same, row['source'], row['target'], True)
                if ids is not None: conflicts.append(('IDENTITY_CONTRADICTION', sorted(set(ids+[row['id']]))))
        for row in broader:
            ids = path([r for r in broader if r['id'] != row['id']], row['target'], row['source'])
            if ids is not None: conflicts.append(('BROADER_CYCLE', sorted(set(ids+[row['id']]))))
    for kind, ids in conflicts:
        db.execute('INSERT OR IGNORE INTO sense_conflict VALUES (?,?,?)', ('lexconflict:'+digest([kind,ids]),kind,json.dumps(ids)))
        db.executemany("UPDATE sense_assertion SET status='CONFLICT_REVIEW_REQUIRED' WHERE id=?", [(i,) for i in ids])
    return db.execute('SELECT count(*) FROM sense_conflict').fetchone()[0]
