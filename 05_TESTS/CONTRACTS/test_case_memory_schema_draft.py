"""Uninstalled multi-turn schema contracts. No model or runtime DB is used."""
from pathlib import Path
import sqlite3

import pytest

SCHEMA = Path(__file__).resolve().parents[2] / '00_SYSTEM/SCHEMAS/legal-agent-case-memory-v1.draft.sql'
H = 'a' * 64


def put(db, table, **values):
    db.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))


def state(db, rev, branch='actual', source=None):
    put(db, 'cm_state', case_id='case1', branch_id=branch, revision=rev,
        parent_revision=rev-1 if rev else None, source_turn_id=source,
        state_json='{}', state_hash=H, created_at='2026-10-01')


def turn(db, ident, base, branch='actual', client_id=None):
    number = db.execute("SELECT COALESCE(MAX(turn_number),0)+1 FROM cm_turn WHERE conversation_id='chat'").fetchone()[0]
    put(db, 'cm_turn', turn_id=ident, conversation_id='chat', tenant_id='t1', case_id='case1',
        turn_number=number,
        branch_id=branch, base_revision=base, actor_id='u1', client_request_id=client_id or ident,
        original_text='모의 발언', input_json='{}', input_hash=H, created_at='2026-10-01')


def fact(db, rev, source, value='해외', branch='actual', ident='party'):
    put(db, 'cm_fact', case_id='case1', branch_id=branch, fact_id=ident, revision=rev,
        previous_revision=rev-1 if rev>1 else None, fact_key='당사자', value_json='"'+value+'"',
        basis='USER_ASSERTED', source_turn_id=source, origin_ref='mock:turn:'+source, origin_hash=H)


def member(db, state_rev, fact_rev, branch='actual', source_branch='actual', ident='party'):
    put(db, 'cm_state_fact', case_id='case1', branch_id=branch, state_revision=state_rev,
        fact_id=ident, fact_branch_id=source_branch, fact_revision=fact_rev)


@pytest.fixture
def db():
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA user_version=1')
    db.executescript(SCHEMA.read_text())
    put(db, 'cm_conversation', conversation_id='chat', tenant_id='t1', owner_id='u1', created_at='now')
    put(db, 'cm_case', case_id='case1', tenant_id='t1', owner_id='u1', title='모의 사건', created_at='now')
    put(db, 'cm_branch', case_id='case1', branch_id='actual', kind='ACTUAL', created_at='now')
    state(db, 0)
    put(db, 'cm_head', case_id='case1', branch_id='actual', revision=0)
    turn(db, 'turn1', 0)
    fact(db, 1, 'turn1')
    state(db, 1, source='turn1')
    member(db, 1, 1)
    db.execute("UPDATE cm_head SET revision=1 WHERE case_id='case1' AND branch_id='actual' AND revision=0")
    yield db
    db.close()


def correction(db):
    turn(db, 'turn2', 1)
    fact(db, 2, 'turn2', '국내')
    state(db, 2, source='turn2')
    member(db, 2, 2)
    return db.execute("UPDATE cm_head SET revision=2 WHERE case_id='case1' AND branch_id='actual' AND revision=1")


def decision(db, ident, run='run1'):
    put(db, 'cm_decision', case_id='case1', branch_id='actual', decision_id=ident, run_id=run,
        entity_kind='claim', entity_id=ident, entity_revision=1, entity_ref='mock:entity:'+ident,
        entity_hash=H, body_json='{}')


def run(db):
    put(db, 'cm_run_binding', run_id='run1', turn_id='turn1', case_id='case1', branch_id='actual',
        base_revision=0, journal_ref='mock:journal', created_at='now')


def test_schema_is_separate_and_integral(db):
    assert db.execute('PRAGMA user_version').fetchone()[0] == 1
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_correction_preserves_old_fact_and_rejects_stale_writer(db):
    assert correction(db).rowcount == 1
    assert db.execute('SELECT value_json FROM cm_fact ORDER BY revision').fetchall() == [('"해외"',), ('"국내"',)]
    assert db.execute("UPDATE cm_head SET revision=2 WHERE case_id='case1' AND branch_id='actual' AND revision=1").rowcount == 0
    assert db.execute('SELECT fact_revision FROM cm_state_fact ORDER BY state_revision').fetchall() == [(1,), (2,)]


def test_committed_state_cannot_gain_silent_fact(db):
    fact(db, 1, 'turn1', ident='other')
    with pytest.raises(sqlite3.IntegrityError, match='sealed'):
        member(db, 1, 1, ident='other')
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        db.execute("UPDATE cm_fact SET value_json='null'")


def test_hypothesis_stays_at_its_parent_snapshot(db):
    put(db, 'cm_branch', case_id='case1', branch_id='whatif', kind='HYPOTHETICAL',
        parent_branch_id='actual', parent_revision=1, created_at='now')
    state(db, 0, branch='whatif')
    member(db, 0, 1, branch='whatif')
    put(db, 'cm_head', case_id='case1', branch_id='whatif', revision=0)
    correction(db)
    assert db.execute("SELECT fact_revision FROM cm_state_fact WHERE branch_id='whatif'").fetchone()[0] == 1
    assert db.execute("SELECT revision FROM cm_head WHERE branch_id='whatif'").fetchone()[0] == 0


def test_case_tenant_cannot_be_forged_by_turn(db):
    put(db, 'cm_case', case_id='other', tenant_id='t2', owner_id='u2', title='다른 조직', created_at='now')
    put(db, 'cm_branch', case_id='other', branch_id='actual', kind='ACTUAL', created_at='now')
    put(db, 'cm_state', case_id='other', branch_id='actual', revision=0, state_json='{}', state_hash=H, created_at='now')
    with pytest.raises(sqlite3.IntegrityError):
        put(db, 'cm_turn', turn_id='bad', conversation_id='chat', tenant_id='t1', case_id='other',
            turn_number=2,
            branch_id='actual', base_revision=0, actor_id='u1', client_request_id='bad',
            original_text='다른 사건', input_json='{}', input_hash=H, created_at='now')


def test_corrected_fact_finds_only_dependent_decisions(db):
    run(db)
    for ident in ('A', 'B', 'unrelated'):
        decision(db, ident)
    put(db, 'cm_decision_fact', case_id='case1', branch_id='actual', decision_id='A',
        fact_id='party', fact_branch_id='actual', fact_revision=1)
    put(db, 'cm_decision_parent', case_id='case1', branch_id='actual', decision_id='B', parent_id='A')
    correction(db)
    affected = db.execute('''WITH RECURSIVE affected(id) AS (
      SELECT d.decision_id FROM cm_decision_fact d
      WHERE d.case_id='case1' AND d.branch_id='actual' AND NOT EXISTS(
        SELECT 1 FROM cm_state_fact s WHERE s.case_id=d.case_id AND s.branch_id=d.branch_id
        AND s.state_revision=2 AND s.fact_id=d.fact_id AND s.fact_branch_id=d.fact_branch_id
        AND s.fact_revision=d.fact_revision)
      UNION SELECT p.decision_id FROM cm_decision_parent p JOIN affected a ON p.parent_id=a.id
      WHERE p.case_id='case1' AND p.branch_id='actual') SELECT id FROM affected ORDER BY id''').fetchall()
    assert affected == [('A',), ('B',)]
    for ident, in affected:
        put(db, 'cm_decision_check', case_id='case1', branch_id='actual', state_revision=2,
            decision_id=ident, check_no=1, status='NEEDS_CHECK', reason='사용한 사실 정정', receipt_ref='mock:check', receipt_hash=H)
    assert db.execute('SELECT count(*) FROM cm_decision').fetchone()[0] == 3


def test_decision_cycles_are_rejected(db):
    run(db)
    decision(db, 'A'); decision(db, 'B')
    put(db, 'cm_decision_parent', case_id='case1', branch_id='actual', decision_id='B', parent_id='A')
    with pytest.raises(sqlite3.IntegrityError, match='cycle'):
        put(db, 'cm_decision_parent', case_id='case1', branch_id='actual', decision_id='A', parent_id='B')


def test_user_statement_is_not_verified_without_receipt(db):
    with pytest.raises(sqlite3.IntegrityError):
        put(db, 'cm_fact', case_id='case1', branch_id='actual', fact_id='verified', revision=1,
            fact_key='당사자', value_json='"국내"', basis='SOURCE_VERIFIED', source_turn_id='turn1',
            origin_ref='mock:turn', origin_hash=H)


def test_user_wiki_does_not_accept_case_facts_or_unconfirmed_preferences(db):
    common = dict(tenant_id='t1', user_id='u1', memory_id='m1', revision=1, content_json='{}',
                  origin_ref='mock:turn', origin_hash=H, created_at='now')
    with pytest.raises(sqlite3.IntegrityError):
        put(db, 'cm_user_memory', kind='CASE_FACT', status='PROPOSED', **common)
    with pytest.raises(sqlite3.IntegrityError):
        put(db, 'cm_user_memory', kind='PREFERENCE', status='CONFIRMED', **common)
    put(db, 'cm_user_memory', kind='PREFERENCE', status='CONFIRMED', confirmation_ref='mock:explicit-user-request', **common)


def test_turn_is_idempotent_and_head_cannot_jump(db):
    with pytest.raises(sqlite3.IntegrityError):
        turn(db, 'duplicate', 1, client_id='turn1')
    with pytest.raises(sqlite3.IntegrityError, match='one revision'):
        db.execute("UPDATE cm_head SET revision=9")


def test_run_cannot_silently_change_turn_base(db):
    with pytest.raises(sqlite3.IntegrityError, match='base revision'):
        put(db, 'cm_run_binding', run_id='bad', turn_id='turn1', case_id='case1', branch_id='actual',
            base_revision=1, journal_ref='mock:journal', created_at='now')


def test_failed_state_transaction_leaves_head_and_fact_unchanged(db):
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        with db:
            correction(db)
            put(db, 'cm_delivery', event_id='missing-outbox', attempt=1, status='DELIVERED', receipt_ref='mock:receipt')
    assert db.execute("SELECT revision FROM cm_head WHERE branch_id='actual'").fetchone()[0] == 1
    assert db.execute('SELECT revision FROM cm_fact').fetchall() == [(1,)]


def test_access_revocation_preserves_history_and_cannot_skip_revision(db):
    common = dict(case_id='case1', principal_id='u2', actor_id='u1', reason='모의 권한 변경', created_at='now')
    put(db, 'cm_access_event', event_id='grant', revision=1, permission='READ', **common)
    put(db, 'cm_access_event', event_id='revoke', revision=2, permission='REVOKED', **common)
    with pytest.raises(sqlite3.IntegrityError, match='contiguous'):
        put(db, 'cm_access_event', event_id='jump', revision=4, permission='WRITE', **common)
    assert db.execute('SELECT permission FROM cm_access_event ORDER BY revision').fetchall() == [('READ',), ('REVOKED',)]


def bind_session(db, conversation, user, external, namespace='chat'):
    put(db, 'cm_session_binding', provider='mock-genos', namespace=namespace, tenant_id='t1',
        user_id=user, external_session_id=external, conversation_id=conversation,
        identity_receipt_ref='mock:auth', identity_receipt_hash=H, created_at='now')


def test_same_external_session_is_separate_for_each_user(db):
    bind_session(db, 'chat', 'u1', 'shared-session')
    put(db, 'cm_conversation', conversation_id='chat2', tenant_id='t1', owner_id='u2', created_at='now')
    bind_session(db, 'chat2', 'u2', 'shared-session')
    assert db.execute('SELECT count(*) FROM cm_session_binding').fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError, match='owner'):
        bind_session(db, 'chat2', 'u1', 'other-session')


def test_raw_session_identifiers_are_not_truncated_or_normalized(db):
    prefix = 'a' * 64
    bind_session(db, 'chat', 'u1', prefix + '/첫번째')
    put(db, 'cm_conversation', conversation_id='chat2', tenant_id='t1', owner_id='u1', created_at='now')
    bind_session(db, 'chat2', 'u1', prefix + '/두번째')
    assert {row[0] for row in db.execute('SELECT external_session_id FROM cm_session_binding')} == {
        prefix + '/첫번째', prefix + '/두번째'}
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        db.execute("UPDATE cm_session_binding SET user_id='u2'")


def edit(db, **overrides):
    values = dict(edit_id='edit1', source_turn_id='turn3', case_id='case1', branch_id='actual',
                  base_revision=1, target_turn_id='turn2', target_decision_id='scope2',
                  target_goal_id='G2', extent='TARGET_GOAL', operation='CHANGE_SCOPE',
                  patch_json='{"before":"INTERNAL","after":"EXTERNAL"}',
                  interpretation_ref='mock:explicit-correction', interpretation_hash=H, created_at='now')
    values.update(overrides)
    put(db, 'cm_edit', **values)


def target_fixture(db):
    run(db)
    decision(db, 'scope1')
    turn(db, 'turn2', 1)
    put(db, 'cm_run_binding', run_id='run2', turn_id='turn2', case_id='case1', branch_id='actual',
        base_revision=1, journal_ref='mock:journal2', created_at='now')
    decision(db, 'scope2', run='run2')
    turn(db, 'turn3', 1)


def test_correction_targets_second_question_not_latest_or_same_label(db):
    target_fixture(db)
    with pytest.raises(sqlite3.IntegrityError, match='exact turn'):
        edit(db, target_decision_id='scope1')
    edit(db)
    assert db.execute('''SELECT t.turn_number,e.target_decision_id,e.extent FROM cm_edit e
      JOIN cm_turn t ON t.turn_id=e.target_turn_id''').fetchone() == (2, 'scope2', 'TARGET_GOAL')
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        db.execute("UPDATE cm_edit SET target_decision_id='scope1'")


def test_displayed_answer_anchor_must_point_to_its_own_run(db):
    target_fixture(db)
    anchor = dict(publication_ref='mock:answer2', publication_hash=H, anchor_id='paragraph1',
                  anchor_text='내규를 검색 범위로 사용했습니다.', case_id='case1', branch_id='actual', run_id='run2')
    with pytest.raises(sqlite3.IntegrityError, match='from its run'):
        put(db, 'cm_answer_anchor', decision_id='scope1', **anchor)
    put(db, 'cm_answer_anchor', decision_id='scope2', **anchor)
    assert db.execute('SELECT decision_id FROM cm_answer_anchor').fetchone()[0] == 'scope2'


def test_edit_is_only_applied_to_state_created_by_correcting_turn(db):
    target_fixture(db)
    edit(db)
    common = dict(edit_id='edit1', case_id='case1', branch_id='actual', receipt_ref='mock:apply', receipt_hash=H)
    with pytest.raises(sqlite3.IntegrityError, match='state created by its turn'):
        put(db, 'cm_edit_application', state_revision=1, **common)
    state(db, 2, source='turn3')
    member(db, 2, 1)
    put(db, 'cm_edit_application', state_revision=2, **common)
    db.execute('UPDATE cm_head SET revision=2 WHERE revision=1')
    assert db.execute('SELECT state_revision FROM cm_edit_application').fetchone()[0] == 2
    assert db.execute('SELECT count(*) FROM cm_decision').fetchone()[0] == 2


def test_fact_correction_must_target_fact_used_in_decision(db):
    target_fixture(db)
    args = dict(operation='CORRECT_FACT', target_fact_id='party', target_fact_branch_id='actual', target_fact_revision=1)
    with pytest.raises(sqlite3.IntegrityError, match='dependency'):
        edit(db, **args)
    put(db, 'cm_decision_fact', case_id='case1', branch_id='actual', decision_id='scope2',
        fact_id='party', fact_branch_id='actual', fact_revision=1)
    edit(db, **args)


def test_fact_scope_cannot_change_between_case_and_question(db):
    with pytest.raises(sqlite3.IntegrityError, match='goal scope'):
        put(db, 'cm_fact', case_id='case1', branch_id='actual', fact_id='party', revision=2,
            previous_revision=1, fact_key='당사자', goal_id='G2', value_json='"국내"', basis='USER_ASSERTED',
            source_turn_id='turn1', origin_ref='mock:turn1', origin_hash=H)


def test_new_decision_preserves_explicit_replacement_link(db):
    target_fixture(db)
    put(db, 'cm_run_binding', run_id='run3', turn_id='turn3', case_id='case1', branch_id='actual',
        base_revision=1, journal_ref='mock:journal3', created_at='now')
    put(db, 'cm_decision', case_id='case1', branch_id='actual', decision_id='scope2-new', run_id='run3',
        entity_kind='assessment', entity_id='scope2-new', entity_revision=1,
        entity_ref='mock:scope2-new', entity_hash=H, body_json='{"scope":"EXTERNAL"}',
        supersedes_decision_id='scope2')
    assert db.execute('SELECT count(*) FROM cm_decision').fetchone()[0] == 3
    assert db.execute("SELECT supersedes_decision_id FROM cm_decision WHERE decision_id='scope2-new'").fetchone()[0] == 'scope2'


def test_scope_edit_rechecks_its_descendants_and_preserves_other_question(db):
    target_fixture(db)
    decision(db, 'select2', run='run2')
    decision(db, 'conclusion2', run='run2')
    for child, parent in [('select2', 'scope2'), ('conclusion2', 'select2')]:
        put(db, 'cm_decision_parent', case_id='case1', branch_id='actual', decision_id=child, parent_id=parent)
    edit(db)
    affected = db.execute('''WITH RECURSIVE affected(case_id,branch_id,id) AS (
      SELECT case_id,branch_id,target_decision_id FROM cm_edit WHERE edit_id='edit1'
      UNION SELECT p.case_id,p.branch_id,p.decision_id FROM cm_decision_parent p
      JOIN affected a ON p.case_id=a.case_id AND p.branch_id=a.branch_id AND p.parent_id=a.id
    ) SELECT id FROM affected ORDER BY id''').fetchall()
    assert affected == [('conclusion2',), ('scope2',), ('select2',)]
    assert db.execute("SELECT decision_id FROM cm_decision WHERE run_id='run1'").fetchall() == [('scope1',)]
