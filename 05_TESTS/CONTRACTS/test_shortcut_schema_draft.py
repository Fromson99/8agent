"""Mechanical checks of an uninstalled SQL draft, not reuse quality evidence."""
from pathlib import Path
import sqlite3

import pytest


SCHEMA = Path(__file__).resolve().parents[2] / '00_SYSTEM/SCHEMAS/shortcut-experience-v1.draft.sql'
HASH = 'a' * 64


@pytest.fixture
def db():
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA user_version=1')
    db.executescript(SCHEMA.read_text())
    db.execute("INSERT INTO shortcut_question VALUES(?,?,?,?,?,?,?,?,?)",
               ('q1', 'tenant1', 'owner1', 'OWNER', 'UNKNOWN', '모의 질문', '{}', HASH, '2026-10-01'))
    yield db
    db.close()


def make_run(db):
    db.execute('INSERT INTO shortcut_run VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
               ('run1', 'q1', 'tenant1', 'native1', 'v5', 'mock:package', HASH,
                '{}', HASH, HASH, 'COMPLETED', '2026-10-01'))


def make_step(db, ident, ordinal):
    db.execute('INSERT INTO shortcut_step VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (ident, 'run1', ordinal, 'SOURCE_SELECT', 'DECISION', 'select', 'OK',
                'mock:input', HASH, 'mock:result', HASH, '모의 선택 이유', '{}', '[]', '2026-10-01'))


def test_schema_keeps_legacy_user_version_and_integrity(db):
    assert db.execute('PRAGMA user_version').fetchone()[0] == 1
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_same_text_is_not_identity_and_cross_tenant_selection_is_denied(db):
    db.execute('INSERT INTO shortcut_question VALUES(?,?,?,?,?,?,?,?,?)',
               ('q2', 'tenant2', 'owner2', 'OWNER', 'UNKNOWN', '모의 질문', '{}', HASH, '2026-10-01'))
    assert db.execute('SELECT count(*) FROM shortcut_question').fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO shortcut_route_selection VALUES(?,?,?,?,?,?,?,?,?,?)',
                   ('selection1', 'tenant1', 'q1', 'q2', 'other-wiki', 'group1', 'v1', 'owner1', '유사 질문 선택', '2026-10-01'))


def test_dependencies_require_parent_hash_and_no_cycles(db):
    make_run(db)
    make_step(db, 'A', 0)
    make_step(db, 'B', 1)
    make_step(db, 'C', 2)
    db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('B', 'A', HASH))
    with pytest.raises(sqlite3.IntegrityError, match='cyclic'):
        db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('A', 'B', HASH))
    with pytest.raises(sqlite3.IntegrityError, match='result mismatch'):
        db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('C', 'A', 'b' * 64))


def test_retracted_identity_cannot_be_resurrected(db):
    make_run(db)
    make_step(db, 'A', 0)
    db.execute('INSERT INTO shortcut_step_event VALUES(?,?,?,?,?,?,?,?)',
               ('event1', 'A', 1, 'OBSERVED', '모의 관찰', 'actor1', 'policy1', '2026-10-01'))
    db.execute('INSERT INTO shortcut_step_event VALUES(?,?,?,?,?,?,?,?)',
               ('event2', 'A', 2, 'RETRACTED', '잘못된 연결', 'actor1', 'policy1', '2026-10-01'))
    with pytest.raises(sqlite3.IntegrityError, match='new identity'):
        db.execute('INSERT INTO shortcut_step_event VALUES(?,?,?,?,?,?,?,?)',
                   ('event3', 'A', 3, 'REUSABLE', '자동 복구 시도', 'actor1', 'policy1', '2026-10-01'))
    with pytest.raises(sqlite3.IntegrityError, match='contiguous'):
        db.execute('INSERT INTO shortcut_step_event VALUES(?,?,?,?,?,?,?,?)',
                   ('event4', 'A', 4, 'RETRACTED', '누락 revision', 'actor1', 'policy1', '2026-10-01'))
    assert db.execute("SELECT state FROM shortcut_step_head WHERE step_id='A'").fetchone()[0] == 'RETRACTED'


def test_immutable_question_cannot_be_updated_deleted_or_replaced(db):
    for sql in ["UPDATE shortcut_question SET question_text='changed' WHERE question_id='q1'",
                "DELETE FROM shortcut_question WHERE question_id='q1'",
                "INSERT OR REPLACE INTO shortcut_question SELECT * FROM shortcut_question WHERE question_id='q1'"]:
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            db.execute(sql)


def test_capsule_must_bind_to_original_step_result(db):
    make_run(db)
    make_step(db, 'A', 0)
    with pytest.raises(sqlite3.IntegrityError, match='parent result mismatch'):
        db.execute('INSERT INTO shortcut_capsule VALUES(?,?,?,?,?,?,?,?)',
                   ('cap1', 'A', 1, '{}', HASH, 'b' * 64, '{}', '2026-10-01'))


def insert(db, table, **values):
    db.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
               tuple(values.values()))


def reuse_setup(db):
    make_run(db)
    for n, ident in enumerate(('A', 'B', 'C')):
        make_step(db, ident, n)
        db.execute('INSERT INTO shortcut_capsule VALUES(?,?,?,?,?,?,?,?)',
                   ('cap'+ident, ident, 1, '{}', HASH, HASH, '{}', '2026-10-01'))
    db.execute('INSERT INTO shortcut_question VALUES(?,?,?,?,?,?,?,?,?)',
               ('q2', 'tenant1', 'owner1', 'OWNER', 'UNKNOWN', '새 질문', '{}', HASH, '2026-10-01'))
    db.execute('INSERT INTO shortcut_route_selection VALUES(?,?,?,?,?,?,?,?,?,?)',
               ('sel', 'tenant1', 'q2', 'q1', 'wiki', 'group', 'rev1', 'owner1', '유사함', '2026-10-01'))
    insert(db, 'shortcut_run_binding', binding_id='binding', selection_id='sel', past_question_id='q1',
           tenant_id='tenant1', run_snapshot_id='run1', reason='실행 고정', created_at='2026-10-01')
    insert(db, 'shortcut_reuse_policy', policy_id='policy', stage='SOURCE_SELECT', operation='select',
           contract_json='{}', contract_hash=HASH, created_at='2026-10-01')
    insert(db, 'shortcut_prompt_packet', packet_id='packet', selection_id='sel', binding_id='binding',
           current_run_id='current', model_attempt_id='attempt1', phase='select', current_state_revision=1,
           body_json='{}', body_hash=HASH, request_hash=HASH, byte_count=2, token_count=2,
           request_byte_count=100, request_token_count=100, token_counter_binding='mock-counter',
           budget_policy_json='{}', delivery_ref='mock:delivery', created_at='2026-10-01')
    for n, ident in enumerate(('A', 'B', 'C'), 1):
        db.execute('INSERT INTO shortcut_packet_item VALUES(?,?,?,?)', ('packet', n, ident, 'cap'+ident))


def reuse(db, ident, action='ADOPTED'):
    insert(db, 'shortcut_reuse_event', reuse_event_id='reuse'+ident, packet_id='packet', step_id=ident,
           capsule_id='cap'+ident, policy_id='policy', action=action, reason='모의 적용', preflight_json='{}',
           current_result_ref='mock:current:'+ident, current_result_hash=HASH, created_at='2026-10-01')


def mapping(db, child, parent, compatibility='MATCH', parent_reuse=True):
    insert(db, 'shortcut_reuse_dependency', reuse_event_id='reuse'+child, past_prerequisite_id=parent,
           current_result_ref='mock:current:'+parent, current_result_hash=HASH,
           parent_reuse_event_id='reuse'+parent if parent_reuse else None, compatibility=compatibility,
           reason='부모 조건 확인', check_ref='mock:check', check_hash=HASH)


def work(db, ident='C', outcome='SKIPPED', current_run='current', attempt=1):
    insert(db, 'shortcut_work_receipt', receipt_id='receipt'+str(attempt), reuse_event_id='reuse'+ident,
           current_run_id=current_run, task_key='select:candidate3', attempt_no=attempt, operation='select',
           outcome=outcome, result_ref='mock:current:'+ident, result_hash=HASH,
           native_event_ref='mock:event:'+str(attempt), native_event_hash=HASH,
           reason='모의 작업 처리', created_at='2026-10-01')


def test_selected_run_must_belong_to_selected_question(db):
    reuse_setup(db)
    insert(db, 'shortcut_route_selection', selection_id='sel2', tenant_id='tenant1', current_question_id='q1',
           past_question_id='q2', wiki_provider='wiki', wiki_group_ref='group', wiki_revision='rev1',
           selector_id='owner1', selection_reason='역방향 선택', selected_at='2026-10-01')
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, 'shortcut_run_binding', binding_id='wrong', selection_id='sel2', past_question_id='q2',
               tenant_id='tenant1', run_snapshot_id='run1', reason='다른 질문 실행', created_at='2026-10-01')


def test_packet_cannot_mix_other_runs_or_undelivered_memories(db):
    reuse_setup(db)
    db.execute('INSERT INTO shortcut_run SELECT ?,question_id,tenant_id,?,journal_schema,package_ref,package_hash,'
               'binding_json,binding_hash,data_key,run_status,recorded_at FROM shortcut_run WHERE run_snapshot_id=?',
               ('run2', 'native2', 'run1'))
    db.execute('INSERT INTO shortcut_step SELECT ?,?,99,stage,record_kind,operation,outcome,input_ref,input_hash,'
               'result_ref,result_hash,reason,applicability_json,native_event_refs_json,created_at '
               'FROM shortcut_step WHERE step_id=?', ('other', 'run2', 'A'))
    db.execute('INSERT INTO shortcut_capsule VALUES(?,?,?,?,?,?,?,?)',
               ('capother', 'other', 1, '{}', HASH, HASH, '{}', '2026-10-01'))
    with pytest.raises(sqlite3.IntegrityError, match='selected run'):
        db.execute('INSERT INTO shortcut_packet_item VALUES(?,?,?,?)', ('packet', 4, 'other', 'capother'))
    with pytest.raises(sqlite3.IntegrityError):
        reuse(db, 'other')
    with pytest.raises(sqlite3.IntegrityError, match='one run'):
        db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('C', 'other', HASH))


def test_skip_requires_all_parents_and_records_fallback_separately(db):
    reuse_setup(db)
    for parent in ('A', 'B'):
        db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('C', parent, HASH))
        reuse(db, parent)
    reuse(db, 'C')
    mapping(db, 'C', 'A')
    with pytest.raises(sqlite3.IntegrityError, match='all matching parents'):
        work(db)
    mapping(db, 'C', 'B')
    work(db)
    work(db, outcome='FALLBACK', attempt=2)
    assert db.execute('SELECT outcome FROM shortcut_work_receipt ORDER BY attempt_no').fetchall() == [('SKIPPED',), ('FALLBACK',)]
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('compatibility', ['CHANGED', 'UNKNOWN'])
def test_unconfirmed_parent_cannot_skip(db, compatibility):
    reuse_setup(db)
    db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('C', 'A', HASH))
    reuse(db, 'C')
    mapping(db, 'C', 'A', compatibility, parent_reuse=False)
    with pytest.raises(sqlite3.IntegrityError, match='all matching parents'):
        work(db)


def test_newly_computed_parent_can_satisfy_dependency(db):
    reuse_setup(db)
    db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('C', 'A', HASH))
    reuse(db, 'C')
    mapping(db, 'C', 'A', parent_reuse=False)
    work(db)


def test_hint_is_not_work_skipping_and_cross_run_receipt_is_denied(db):
    reuse_setup(db)
    reuse(db, 'C', 'HINT_USED')
    with pytest.raises(sqlite3.IntegrityError, match='adopted result'):
        work(db)
    with pytest.raises(sqlite3.IntegrityError, match='run mismatch'):
        work(db, outcome='EXECUTED', current_run='other')
    work(db, outcome='EXECUTED')


def test_parent_hint_cannot_be_claimed_as_adopted_parent(db):
    reuse_setup(db)
    db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)', ('C', 'A', HASH))
    reuse(db, 'A', 'HINT_USED')
    reuse(db, 'C')
    with pytest.raises(sqlite3.IntegrityError, match='parent reuse result/run mismatch'):
        mapping(db, 'C', 'A')


def test_pinned_run_and_work_receipts_are_immutable(db):
    reuse_setup(db)
    reuse(db, 'C')
    work(db)
    for table in ('shortcut_run_binding', 'shortcut_packet_item', 'shortcut_work_receipt'):
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            db.execute(f'DELETE FROM {table}')


def test_wrong_stage_policy_cannot_authorize_reuse(db):
    reuse_setup(db)
    insert(db, 'shortcut_reuse_policy', policy_id='wrong-policy', stage='READ', operation='read',
           contract_json='{}', contract_hash=HASH, created_at='2026-10-01')
    with pytest.raises(sqlite3.IntegrityError, match='policy stage/operation mismatch'):
        insert(db, 'shortcut_reuse_event', reuse_event_id='bad', packet_id='packet', step_id='A',
               capsule_id='capA', policy_id='wrong-policy', action='ADOPTED', reason='다른 단계 규칙',
               preflight_json='{}', current_result_ref='mock:result', current_result_hash=HASH, created_at='2026-10-01')


def test_integrity_review_cannot_overwrite_legal_failure(db):
    reuse_setup(db)
    common = dict(step_id='A', reviewer_kind='HUMAN', reviewer_id='reviewer', reason='모의 검토',
                  proof_ref='mock:review', proof_hash=HASH, policy_version='v1', created_at='2026-10-01')
    insert(db, 'shortcut_review', review_id='legal-fail', review_kind='LEGAL_CORRECTNESS', verdict='FAIL', **common)
    with pytest.raises(sqlite3.IntegrityError, match='same target/kind'):
        insert(db, 'shortcut_review', review_id='integrity-pass', review_kind='SOURCE_INTEGRITY', verdict='PASS',
               supersedes_review_id='legal-fail', **common)
    insert(db, 'shortcut_review', review_id='legal-pass', review_kind='LEGAL_CORRECTNESS', verdict='PASS',
           supersedes_review_id='legal-fail', **common)


def test_work_skip_must_supply_the_adopted_result(db):
    reuse_setup(db)
    reuse(db, 'C')
    with pytest.raises(sqlite3.IntegrityError, match='adopted result'):
        insert(db, 'shortcut_work_receipt', receipt_id='wrong', reuse_event_id='reuseC', current_run_id='current',
               task_key='select:candidate3', attempt_no=1, operation='select', outcome='SKIPPED',
               result_ref='mock:other-result', result_hash=HASH, native_event_ref='mock:event', native_event_hash=HASH,
               reason='결과 불일치', created_at='2026-10-01')
