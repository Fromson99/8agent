"""Lossless storage/rollback/admission contracts; no model or corpus copies."""
import json
import sqlite3
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import journal_storage as storage
from semantic_runtime.legal_agent import storage_admission as quota
from semantic_runtime.legal_agent.errors import ContractError, AdmissionRejected
from semantic_runtime.legal_agent.repository import WorkRepository, encoded
from semantic_runtime.legal_agent.ontology_io import delivery_events
from test_legal_agent_double_harness import work, seed, visible_view


@pytest.fixture(autouse=True)
def compact(monkeypatch):
    monkeypatch.setenv('GENOS_JOURNAL_STORAGE', 'compact')


def database(path):
    db = storage.connect(path, isolation_level=None)
    storage.initialize(db)
    db.execute('CREATE TABLE IF NOT EXISTS record(id INTEGER PRIMARY KEY, value TEXT CHECK(json_valid(value)))')
    return db


def test_repeated_original_different_views_is_shared_and_exact(tmp_path):
    db = database(tmp_path/'journal.sqlite')
    text = '제1조의 원문과 판단 이유\\n "문자 보존"\n' * 1000
    values = [encoded({'view': i, 'original': text, 'failure': {'reason': '실패 이유 '+str(i)}}) for i in range(12)]
    db.execute('BEGIN')
    for i, raw in enumerate(values):
        db.execute('INSERT INTO record VALUES(?,?)', (i, storage.store(db, raw)))
    db.execute('COMMIT')
    assert [r[0] for r in db.execute('SELECT value FROM record ORDER BY id')] == values
    # One shared long string plus twelve small reconstruction records.
    assert db.execute('SELECT count(*) FROM journal_blob_v1').fetchone()[0] == 13
    assert (tmp_path/'journal.sqlite').stat().st_size < sum(len(v.encode()) for v in values)/5
    db.close()
    db = storage.connect((tmp_path/'journal.sqlite').as_uri()+'?mode=ro', uri=True)
    assert [r[0] for r in db.execute('SELECT value FROM record ORDER BY id')] == values
    db.close()


def test_transaction_rollback_removes_new_blobs_and_record(tmp_path):
    db = database(tmp_path/'journal.sqlite')
    db.execute('BEGIN')
    db.execute('INSERT INTO record VALUES(1,?)', (storage.store(db, encoded({'reason':'실패'*400})),))
    db.execute('ROLLBACK')
    assert db.execute('SELECT count(*) FROM journal_blob_v1').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM record').fetchone()[0] == 0
    db.close()


def test_plain_legacy_and_literal_reference_are_not_decoded(tmp_path):
    db = database(tmp_path/'journal.sqlite')
    raw = '{"genos_journal_blob_v1":"'+'a'*64+'"}'
    db.execute('INSERT INTO record VALUES(1,?)', (raw,))
    assert db.execute('SELECT value FROM record').fetchone()[0] == raw
    db.close()


@pytest.mark.parametrize('damage', ['missing','hash','zlib'])
def test_corruption_fails_closed(tmp_path, damage):
    db = database(tmp_path/'journal.sqlite')
    raw = encoded({'text':'진짜 원문'*500})
    ref = storage.store(db, raw)
    key = json.loads(ref)['genos_journal_blob_v1']
    if damage == 'missing': db.execute('DELETE FROM journal_blob_v1 WHERE hash=?',(key,))
    elif damage == 'hash': db.execute('UPDATE journal_blob_v1 SET size=size+1 WHERE hash=?',(key,))
    else: db.execute('UPDATE journal_blob_v1 SET data=? WHERE hash=?',(b'bad',key))
    with pytest.raises(ContractError): storage.restore(db,ref)
    db.close()


def test_plain_switch_can_read_compact_history(tmp_path,monkeypatch):
    path=tmp_path/'journal.sqlite';db=database(path)
    raw=encoded({'text':'기존 원문'*500});db.execute('INSERT INTO record VALUES(1,?)',(storage.store(db,raw),));db.close()
    monkeypatch.setenv('GENOS_JOURNAL_STORAGE','plain')
    db=storage.connect(path);storage.initialize(db)
    assert storage.store(db,raw)==raw
    assert db.execute('SELECT value FROM record').fetchone()[0]==raw
    db.close()


def test_repository_original_attempt_failure_and_reopen(work):
    original='모의 원문으로 승인을 판단한다.\n'*500
    seed(work,original)
    view=work.save_view('investigate',{'text':original},['E1'])
    attempt=work.reserve_attempt(view,{'messages':[{'content':original}]},'physical-one',1,'investigate')
    work.attempt_sent(attempt)
    response={'broken_response':original,'reason':'invalid format'}
    work.finish_attempt(attempt,'FAILED',response,{'failure':'transport original failure'})
    work.fail('SYNTHETIC_FAILURE',diagnostics={'original':original})
    assert work.evidence('E1')['text']==original
    reopened=WorkRepository(work.path)
    try:
        assert reopened.run()['status']=='FAILED'
        row=reopened.db.execute('SELECT * FROM model_attempt').fetchone()
        assert row['status']=='FAILED' and json.loads(row['response_json'])==response
        assert reopened.budget()['model_reserved']==1
        assert reopened.evidence('E1')['text']==original
    finally: reopened.close()


def test_event_sql_index_and_error_history_restore(work):
    payload={'presentation_id':'shown-1','original':'원문'*900,'reason':'실패를 그대로 보존'}
    with work.transaction():work.event('NAVIGATION_INPUT_DELIVERED',payload)
    assert json.loads(delivery_events(work,'shown-1').fetchone()['payload_json'])==payload
    assert delivery_events(work,'absent').fetchone() is None
    with pytest.raises(sqlite3.IntegrityError,match='immutable event'):
        work.db.execute("UPDATE event SET payload_json='{}'")


def limits(monkeypatch):
    monkeypatch.setenv('GENOS_RUNTIME_LIMIT_MIB','8')
    monkeypatch.setenv('GENOS_RUNTIME_RESERVE_MIB','2')
    monkeypatch.setenv('GENOS_RUNTIME_MIN_FREE_MIB','1')


def test_limit_rejects_new_work_preserves_old_records(tmp_path,monkeypatch):
    limits(monkeypatch)
    old=tmp_path/'old-failure.json';old.write_text('{"failure":"preserved"}')
    with (tmp_path/'large').open('wb') as f:f.truncate(7*quota.MIB)
    with pytest.raises(AdmissionRejected,match='STORAGE_CAPACITY'):
        with quota.admission(tmp_path):pytest.fail('must not dispatch')
    assert json.loads(old.read_text())=={'failure':'preserved'}
    assert not list((tmp_path/'.storage-admission').glob('*.lease'))


def test_reservation_cleanup_after_failure_and_dead_owner(tmp_path,monkeypatch):
    limits(monkeypatch)
    d=tmp_path/'.storage-admission';d.mkdir();(d/'dead.lease').write_text('')
    with pytest.raises(RuntimeError):
        with quota.admission(tmp_path):
            assert len(list(d.glob('*.lease')))==1
            raise RuntimeError('owner failure')
    assert not list(d.glob('*.lease'))
    assert quota.ACTIVE.get() is None


def test_checkpoint_stops_before_next_call_and_allows_failure_write(tmp_path,monkeypatch):
    limits(monkeypatch)
    with quota.admission(tmp_path):
        with (tmp_path/'received-response').open('wb') as f:f.truncate(8*quota.MIB)
        quota.ACTIVE.get()['checked']=0
        with pytest.raises(AdmissionRejected):quota.checkpoint()
        (tmp_path/'failure.json').write_text('{"status":"FAILED"}')
    assert (tmp_path/'received-response').exists()
    assert (tmp_path/'failure.json').exists()


def test_invalid_limits_fail_closed(monkeypatch):
    monkeypatch.setenv('GENOS_RUNTIME_LIMIT_MIB','0')
    with pytest.raises(ContractError):quota.settings()


def test_span_text_and_json_original_share_one_blob(tmp_path):
    db=database(tmp_path/'journal.sqlite')
    text='동일 원문 "내용"\n'*200
    a=storage.store(db,text)
    b=storage.store(db,encoded({'text':text}))
    assert storage.restore(db,a)==text
    assert json.loads(storage.restore(db,b))['text']==text
    assert db.execute('SELECT count(*) FROM journal_blob_v1').fetchone()[0]==2
    db.close()


def test_noncanonical_json_bytes_are_preserved(tmp_path):
    db=database(tmp_path/'journal.sqlite')
    raw=json.dumps({'text':'한글'*500},ensure_ascii=True,indent=4)
    assert storage.restore(db,storage.store(db,raw))==raw
    db.close()


from test_unified_legal_agent import unified
from test_structure_first_search import structured_generation


def test_api_publishes_reads_compact_journal_and_reuses_request(unified):
    client,send,transport,principal,runtime=unified
    response=send(request_id='storage-once')
    assert response.status_code==200,response.text
    value=response.json();count=len(transport.phases)
    journal=next((runtime/'legal-agent'/'runs').glob('*/'+value['run_id']+'/journal.sqlite'))
    db=storage.connect(journal.as_uri()+'?mode=ro',uri=True)
    assert db.execute('SELECT status FROM run').fetchone()[0]=='COMPLETED'
    pub=json.loads(db.execute('SELECT result_json FROM publication').fetchone()[0])
    assert pub['answer']==value['answer']
    assert db.execute('SELECT count(*) FROM journal_blob_v1').fetchone()[0]>0
    assert all(isinstance(r[0],str) for r in db.execute('SELECT request_json FROM model_attempt'))
    db.close()
    repeated=send(request_id='storage-once')
    assert repeated.status_code==200,repeated.text
    assert repeated.json()['answer']==value['answer']
    assert len(transport.phases)==count


def test_api_capacity_503_before_any_model_call(unified,monkeypatch):
    client,send,transport,principal,runtime=unified
    limits(monkeypatch)
    runtime.mkdir(parents=True,exist_ok=True)
    with (runtime/'preserved-history').open('wb') as f:f.truncate(7*quota.MIB)
    response=send()
    assert response.status_code==503,response.text
    assert 'STORAGE_CAPACITY' in response.text
    assert transport.phases==[]
    assert (runtime/'preserved-history').stat().st_size==7*quota.MIB


def test_separate_case_state_counts_toward_capacity(tmp_path,monkeypatch):
    limits(monkeypatch)
    runtime=tmp_path/'runtime';runtime.mkdir()
    state=tmp_path/'state';state.mkdir()
    monkeypatch.setenv('GENOS_STATE_DIR',str(state))
    with (state/'case-history.sqlite').open('wb') as f:f.truncate(7*quota.MIB)
    with pytest.raises(AdmissionRejected):
        with quota.admission(runtime):pytest.fail('separate state must count')


def test_live_concurrent_reservations_count_and_release(tmp_path,monkeypatch):
    from contextvars import Context
    limits(monkeypatch)
    with (tmp_path/'history').open('wb') as f:f.truncate(5*quota.MIB)
    context=Context();manager=quota.admission(tmp_path)
    context.run(manager.__enter__)
    try:
        with pytest.raises(AdmissionRejected):
            with quota.admission(tmp_path):pytest.fail('headroom already reserved')
    finally:context.run(manager.__exit__,None,None,None)
    with quota.admission(tmp_path):pass


def test_failure_log_keeps_full_diagnostics_without_second_json_copy(work,monkeypatch):
    from semantic_runtime.legal_agent import repository
    records=[]
    monkeypatch.setattr(repository.obs,'event',lambda logger,event,**fields:records.append((event,fields)))
    payload={'reason':'실패 원인','original':'원문'*1000}
    work.event('SYNTHETIC_REJECTED',payload)
    error=next(fields for event,fields in records if event=='agent.error')
    assert error['error_diagnostics']==payload
    assert 'error_record' not in error
    row=work.db.execute('SELECT payload_json,payload_hash FROM event WHERE seq=?',(error['journal_seq'],)).fetchone()
    assert json.loads(row[0])==payload and row[1]==error['error_payload_hash']


def test_operator_trace_reads_v6_compressed_failure_history(work,tmp_path):
    import importlib.util
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    from test_legal_agent_double_harness import PROFILE
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('storage_operator_trace',root/'06_TOOLS/COMMANDS/legal_agent_trace.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    runtime=tmp_path/'trace-runtime'
    repo=UnifiedRepository(runtime/'legal-agent/runs/day'/work.context.run_id/'journal.sqlite',work.context,PROFILE)
    repo.fail('SYNTHETIC_FAILURE',diagnostics={'original':'원문'*900})
    repo.close()
    trace=module.read_trace(runtime,work.context.run_id)
    assert trace['status']=='FAILED'
    assert {'UNASSESSED_AT_STOP','RUN_FAILED'} <= {event['kind'] for event in trace['events']}
    with pytest.raises(ValueError):module.read_trace(runtime,'../other-user')


def test_model_message_json_inside_json_shares_the_original(tmp_path):
    import hashlib
    db=database(tmp_path/'journal.sqlite')
    original='동일한 실제 원문 '*1000
    stored=[]
    for turn in range(5):
        value=encoded({'messages':[{'role':'user','content':encoded({'turn':turn,'original':original})}]})
        ref=storage.store(db,value);stored.append((ref,value))
    original_key=hashlib.sha256(original.encode()).hexdigest()
    assert db.execute('SELECT count(*) FROM journal_blob_v1 WHERE hash=?',(original_key,)).fetchone()[0]==1
    assert db.execute('SELECT count(*) FROM journal_blob_v1 WHERE codec=?',('zlib',)).fetchone()[0]==1
    assert all(storage.restore(db,ref)==value for ref,value in stored)
    db.close()
