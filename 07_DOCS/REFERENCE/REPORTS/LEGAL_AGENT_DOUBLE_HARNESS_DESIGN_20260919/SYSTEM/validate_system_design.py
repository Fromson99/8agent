"""Validate design artifacts only. No product controller or model calls are run."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/jin/8-AGENT')
REPORT = ROOT / '07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919'
checks = []

def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)

def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()

schema = json.loads((HERE / 'protocol.schema.json').read_text())
Draft202012Validator.check_schema(schema)
check('schema.draft202012', True)
examples = json.loads((HERE / 'protocol-examples.json').read_text())['examples']

def validator(name):
    return Draft202012Validator({'$ref': '#/$defs/' + name, '$defs': schema['$defs']})

for name, value in examples.items():
    validator(name).validate(value)
    check('schema.positive.' + name, True)
    if isinstance(value, dict):
        bad = {**value, 'unrecognized_property': True}
        check('schema.reject_extra.' + name, not validator(name).is_valid(bad))

for name in ['InvestigateDecision', 'ComposeDraft', 'ReviewDecision', 'Profile', 'DomainSpec', 'Control']:
    for field in schema['$defs'][name]['required']:
        bad = copy.deepcopy(examples[name]); del bad[field]
        check('schema.required.' + name + '.' + field, not validator(name).is_valid(bad))

bad = copy.deepcopy(examples['InvestigateDecision']); bad['updates'][0]['op'] = 'execute_sql'
check('schema.no_arbitrary_sql', not validator('InvestigateDecision').is_valid(bad))
bad = copy.deepcopy(examples['ComposeDraft']); bad['paragraphs'][0]['evidence_ids'] = []
check('schema.paragraph_needs_evidence', not validator('ComposeDraft').is_valid(bad))
bad = copy.deepcopy(examples['ReviewDecision']); bad['reviews'][0]['claim_version'] = 0
check('schema.review_version_positive', not validator('ReviewDecision').is_valid(bad))
bad = copy.deepcopy(examples['InvestigateDecision']); bad['base_state_revision'] = -1
check('schema.base_revision_nonnegative', not validator('InvestigateDecision').is_valid(bad))

fact = {'op': 'attach_fact', 'client_key': 'tmp:f1', 'issue_id': 'I1', 'text': '금액 미상',
        'status': 'unknown', 'question_piece_id': 'Q1', 'question_span': None}
validator('Update').validate(fact)
check('schema.unknown_fact_shape', True)
claim = {'kind': 'claim', 'text': '모의 문장', 'issue_ids': ['I1'], 'evidence_ids': ['E1'],
         'condition': 'conditional', 'purpose': 'answer'}
validator('EntityPayload').validate(claim)
check('schema.claim_shape', True)
del claim['purpose']
check('schema.claim_requires_purpose', not validator('EntityPayload').is_valid(claim))
for name, filename in [('Profile', 'profile.example.json'), ('DomainSpec', 'domain.example.json')]:
    value = json.loads((HERE / filename).read_text()); validator(name).validate(value)
    check('schema.example_file.' + name, value == examples[name])

db = sqlite3.connect(':memory:', isolation_level=None)
db.executescript((HERE / 'journal.sql').read_text())
tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
expected_tables = {'run', 'event', 'entity_version', 'entity_head', 'dependency', 'evidence_unit',
                  'evidence_span', 'observation', 'observation_evidence', 'evidence_dependency',
                  'frontier', 'model_view', 'presentation', 'model_attempt', 'budget',
                  'stage_artifact', 'publication'}
check('sql.tables', tables == expected_tables)
check('sql.foreign_keys_enabled', db.execute('PRAGMA foreign_keys').fetchone()[0] == 1)
check('sql.schema_version', db.execute('PRAGMA user_version').fetchone()[0] == 1)

def insert(table, **fields):
    # Names are constants in this test script, never model or user inputs.
    db.execute('INSERT INTO ' + table + '(' + ','.join(fields) + ') VALUES (' + ','.join('?' for _ in fields) + ')', tuple(fields.values()))

def rejects(name, fn):
    db.execute('SAVEPOINT negative_case')
    rejected = False
    try:
        fn()
    except sqlite3.IntegrityError:
        rejected = True
    finally:
        db.execute('ROLLBACK TO negative_case'); db.execute('RELEASE negative_case')
    check(name, rejected)

now = '2026-09-19T00:00:00Z'
h = 'a' * 64
insert('run', singleton=1, run_id='r1', query_id='q1', binding_hash=h, binding_json='{}',
       request_json='{}', status='RUNNING', phase='INVESTIGATE', owner_boot_id='boot-1', started_at=now, deadline_at=now)
insert('event', seq=1, event_id='ev1', kind='SYNTHETIC', state_before=0, state_after=0,
       payload_json='{}', payload_hash=digest({}), created_at=now)
insert('budget', singleton=1, model_limit=14, model_reserved=0, finalization_reserve=3, tool_limit=56, tool_used=0)

def entity(kind, ident, version=1):
    insert('entity_version', kind=kind, entity_id=ident, version=version, payload_json='{}', payload_hash=digest({}), created_seq=1)
    insert('entity_head', kind=kind, entity_id=ident, version=version, validity='CURRENT')

for kind, ident in [('issue','I1'), ('issue','I2'), ('assessment','A1'), ('assessment','A2'),
                    ('finding','F1'), ('claim','C1'), ('review','R1'), ('finding','F2')]:
    entity(kind, ident)
for dk, did, pk, pid in [('finding','F1','assessment','A1'), ('claim','C1','finding','F1'),
                         ('review','R1','claim','C1'), ('finding','F2','assessment','A2')]:
    insert('dependency', dependent_kind=dk, dependent_id=did, dependent_version=1,
           prerequisite_kind=pk, prerequisite_id=pid, prerequisite_version=1)

insert('evidence_unit', evidence_id='E1', source_id='source-1', document_id='doc-1', unit_id='u1',
       generation_id='synthetic', source_artifact_hash=h, text_hash=h, role='normative',
       temporal_status='unknown', metadata_json='{}', created_seq=1)
insert('evidence_span', evidence_id='E1', ordinal=0, block_id='b1', start_cp=0, end_cp=2,
       text='모의', block_hash=h, span_hash=h)
insert('evidence_dependency', kind='assessment', entity_id='A1', version=1, evidence_id='E1')
insert('evidence_dependency', kind='assessment', entity_id='A2', version=1, evidence_id='E1')
insert('observation', observation_id='O1', tool='read_node', request_key='read-1', request_json='{}',
       result_json='{}', result_hash=h, status='OK', created_seq=1)
insert('observation_evidence', observation_id='O1', evidence_id='E1')
insert('model_view', view_id='V1', phase='investigate', base_state_revision=0, evidence_revision=0,
       body_json='{}', body_hash=h, created_seq=1)
insert('presentation', view_id='V1', evidence_id='E1', delivered_text_hash=h)

rejects('sql.invalid_span_range', lambda: insert('evidence_span', evidence_id='E1', ordinal=1,
        block_id='b1', start_cp=4, end_cp=3, text='x', block_hash=h, span_hash=h))
rejects('sql.dangling_evidence', lambda: insert('presentation', view_id='V1', evidence_id='MISSING', delivered_text_hash=h))
rejects('sql.dangling_entity', lambda: insert('dependency', dependent_kind='finding', dependent_id='missing',
        dependent_version=1, prerequisite_kind='assessment', prerequisite_id='A1', prerequisite_version=1))
rejects('sql.duplicate_event_id', lambda: insert('event', seq=2, event_id='ev1', kind='x', state_before=0,
        state_after=0, payload_json='{}', payload_hash=h, created_at=now))
rejects('sql.budget_overflow', lambda: db.execute('UPDATE budget SET model_reserved=15'))
rejects('sql.invalid_json', lambda: insert('event', seq=2, event_id='bad-json', kind='x', state_before=0,
        state_after=0, payload_json='[', payload_hash=h, created_at=now))
for table in ['event','entity_version','dependency','evidence_unit','evidence_span','observation',
              'observation_evidence','evidence_dependency','model_view','presentation']:
    column = db.execute('PRAGMA table_info(' + table + ')').fetchone()[1]
    rejects('sql.immutable_update.' + table, lambda t=table, c=column: db.execute('UPDATE ' + t + ' SET ' + c + '=' + c))
    rejects('sql.immutable_delete.' + table, lambda t=table: db.execute('DELETE FROM ' + t))

affected_sql = '''WITH RECURSIVE affected(kind, entity_id, version) AS (
 SELECT :kind, :entity_id, :version
 UNION
 SELECT d.dependent_kind, d.dependent_id, d.dependent_version
 FROM dependency d JOIN affected a
 ON d.prerequisite_kind=a.kind AND d.prerequisite_id=a.entity_id AND d.prerequisite_version=a.version
) SELECT kind, entity_id, version FROM affected'''
affected = set(db.execute(affected_sql, {'kind':'assessment','entity_id':'A1','version':1}))
check('sql.transitive_closure', affected == {('assessment','A1',1),('finding','F1',1),('claim','C1',1),('review','R1',1)})
db.execute('BEGIN IMMEDIATE')
for kind, ident, version in affected:
    db.execute("UPDATE entity_head SET validity='STALE' WHERE kind=? AND entity_id=? AND version=?", (kind,ident,version))
db.execute('COMMIT')
check('sql.unrelated_issue_preserved', db.execute("SELECT validity FROM entity_head WHERE entity_id='F2'").fetchone()[0]=='CURRENT')
check('sql.source_preserved', db.execute("SELECT count(*) FROM evidence_unit WHERE evidence_id='E1'").fetchone()[0]==1)

state_before = db.execute('SELECT state_revision FROM run').fetchone()[0]
for _ in range(11):
    row = db.execute('UPDATE budget SET model_reserved=model_reserved+1 WHERE model_reserved<model_limit-finalization_reserve')
    if row.rowcount != 1:
        raise AssertionError('reservation early failure')
check('sql.investigator_stops_before_final_reserve', db.execute('UPDATE budget SET model_reserved=model_reserved+1 WHERE model_reserved<model_limit-finalization_reserve').rowcount == 0)
check('sql.reservation_not_state_change', db.execute('SELECT state_revision FROM run').fetchone()[0] == state_before)
for _ in range(3):
    db.execute('UPDATE budget SET model_reserved=model_reserved+1 WHERE model_reserved<model_limit')
check('sql.physical_attempt_limit', db.execute('UPDATE budget SET model_reserved=model_reserved+1 WHERE model_reserved<model_limit').rowcount == 0)
query = 'UPDATE run SET state_revision=1 WHERE singleton=1 AND status=\'RUNNING\' AND state_revision=0 AND binding_hash=?'
check('sql.cas_first_commit', db.execute(query,(h,)).rowcount == 1)
check('sql.cas_stale_rejected', db.execute(query,(h,)).rowcount == 0)

db.execute('BEGIN IMMEDIATE')
try:
    insert('event', seq=2, event_id='rollback-case', kind='x', state_before=1, state_after=2,
           payload_json='{}', payload_hash=h, created_at=now)
    insert('entity_head', kind='finding', entity_id='missing', version=99, validity='CURRENT')
except sqlite3.IntegrityError:
    db.execute('ROLLBACK')
else:
    raise AssertionError('expected failure during transaction')
check('sql.atomic_rollback', db.execute("SELECT count(*) FROM event WHERE event_id='rollback-case'").fetchone()[0] == 0)

insert('publication', singleton=1, result_json='{}', result_hash=digest({}), destination_key='runs/r1.json',
       status='PENDING', created_seq=1)
rejects('sql.publication_singleton', lambda: insert('publication', singleton=1, result_json='{}',
        result_hash=h, destination_key='runs/r1.json', status='PENDING', created_seq=1))
check('sql.integrity', db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not list(db.execute('PRAGMA foreign_key_check')))
db.close()

tree = ast.parse((HERE/'interfaces.py').read_text())
classes = {x.name for x in tree.body if isinstance(x, ast.ClassDef)}
check('interfaces.syntax_and_names', {'WorkRepository','SourceSession','ModelGateway','ModelTransport','LegalCoordinator','StageRunner','ServingLegalAgent'} <= classes)

current_pipeline = json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())
pipeline_schema = json.loads((ROOT/'00_SYSTEM/SCHEMAS/pipeline-v1.schema.json').read_text())
pv = Draft202012Validator(pipeline_schema)
check('wiring.current_registry_schema', pv.is_valid(current_pipeline))
bad = copy.deepcopy(current_pipeline); bad['contracts']['runtime.request']['schema_id']='invented'
check('wiring.schema_id_field_is_rejected', not pv.is_valid(bad))
wiring = json.loads((HERE/'wiring-plan.json').read_text())
check('wiring.blueprint_not_release', wiring['artifact_status']=='blueprint_not_loadable_release')
check('wiring.answer_ports', wiring['stages'][-1]['outputs']=={'result':'runtime.result','control':'legal.control'})
check('wiring.all_four_stages', [x['node_id'] for x in wiring['stages']]==['retrieve','select','assemble','answer'])

sources = json.loads((HERE/'sources.json').read_text())
for source in sources['sources']:
    path = Path(source['path'])
    check('source.' + source['id'], path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256'])

for filename in ['SYSTEM_DESIGN.md','SELF_REVIEW.md','README.md']:
    body = (HERE/filename).read_text()
    for label, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', body):
        if target.startswith(('http:', 'https:', '#')):
            continue
        path = Path(target.split('#')[0])
        candidate = path if path.is_absolute() else HERE/path
        if not candidate.exists() and target.startswith('../'):
            candidate = (REPORT/'SYSTEM'/path).resolve()
        if target=='validation.json':
            continue  # This file is emitted from the successful verifier output.
        check('document.link.'+filename+'.'+target, candidate.exists())

result = {'status':'passed','scope':'design SQL, schema examples, interface syntax, wiring constraints and source snapshots only',
          'check_count':len(checks),'sql_tables':len(tables),'schema_examples':len(examples),
          'source_snapshots':len(sources['sources']),'product_controller_tests_run':0,'model_calls':0,'live_genos_checks':0,
          'not_verified':['production repository/controller implementation','semantic model correctness','publisher crash recovery on real filesystem',
                          'GENOS connectivity/performance','active release wiring'], 'checks':checks}
print(json.dumps(result,ensure_ascii=False,indent=2))
