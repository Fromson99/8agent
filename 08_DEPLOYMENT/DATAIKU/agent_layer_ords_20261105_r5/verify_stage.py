"""Real Oracle contracts for batch inserts, conflicts and incomplete jobs."""
import hashlib
import os
import secrets


def check_stage(writer, stage, client, query, out, login):
    from semantic_runtime.oracle_dp_io import SQL
    job, bound = secrets.token_hex(16), secrets.token_hex(32)
    raw = os.urandom(stage.PART * 9 + 13)
    path = out / 'batch-fixture.bin'
    path.write_bytes(raw)
    receipt = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    sql = SQL(client, journal=out / 'batch-sql.jsonl', binding=bound, seconds=120)
    writer.write_result(sql, path, job, bound, receipt, lambda: None)
    assert sql.calls == 3  # 10 parts, two batch INSERTs and the READY commit.
    ready = stage.ready(query, job, bound)
    assert ready['parts'] == 10
    stage.restore(query, job, bound, ready, out / 'batch-restored.bin')
    assert (out / 'batch-restored.bin').read_bytes() == raw
    writer.write_result(sql, path, job, bound, receipt, lambda: None)
    assert query(f"SELECT COUNT(*) AS N FROM {stage.TABLE} WHERE JOB_ID='{job}'")[0]['N'] == 11
    path.write_bytes(b'x' + raw[1:])
    conflict = {'bytes': len(raw), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        writer.write_result(sql, path, job, bound, conflict, lambda: None)
    except Exception:
        pass
    else:
        raise AssertionError('conflicting existing result was accepted')
    assert stage.ready(query, job, bound) == ready
    stage.restore(query, job, bound, ready, out / 'after-conflict.bin')
    assert (out / 'after-conflict.bin').read_bytes() == raw
    bad_job = secrets.token_hex(16)
    try:
        writer.write_result(sql, path, bad_job, bound, receipt, lambda: None)
    except ValueError as exc:
        assert str(exc) == 'STAGE_SOURCE_CHANGED'
    else:
        raise AssertionError('source hash change was accepted')
    assert stage.ready(query, bad_job, bound) is None
    before = sql.calls
    def cancelled():
        raise ValueError('CANCELLED')
    try:
        writer.write_result(sql, path, secrets.token_hex(16), bound, conflict, cancelled)
    except ValueError as exc:
        assert str(exc) == 'CANCELLED'
    else:
        raise AssertionError('cancelled publication continued')
    assert before == sql.calls
    with login('STG_WRITER') as db, db.cursor() as cursor:
        try:
            cursor.execute('SELECT * FROM STG_GOLD.IDD_B003_LGL_DOC_VER WHERE 1=0')
        except Exception as exc:
            assert 'ORA-00942' in str(exc) or 'ORA-01031' in str(exc)
        else:
            raise AssertionError('GENOS Agent writer has unintended Gold access')
    return ['ten_parts_three_ORDS_writes_exact_byte_restore', 'repeat_batch_preserves_row_count',
            'conflicting_body_rollback_preserves_original', 'changed_source_has_no_READY',
            'cancelled_write_sends_no_request', 'GENOS_Agent_writer_has_no_Gold_privilege']
