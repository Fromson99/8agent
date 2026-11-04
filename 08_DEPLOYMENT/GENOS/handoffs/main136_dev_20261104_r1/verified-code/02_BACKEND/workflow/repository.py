"""Workflow checkpoints and call receipts beside the existing RAG attempt journal."""
from contextlib import contextmanager
import fcntl
import json
from semantic_runtime.oracle_runtime_paths import Path
from semantic_runtime import runtime_sqlite as sqlite3
from .contracts import WorkflowError, digest, encoded


@contextmanager
def execution_lock(root, run_id):
    path = Path(root)/run_id
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    from semantic_runtime.oracle_runtime_paths import virtual, records
    if virtual(path):
        try:
            with records().lease(['workflow-execution', str(path)]):
                yield path
        except BlockingIOError as exc:
            raise WorkflowError('WORKFLOW_BUSY', '같은 실행을 처리 중입니다.', 409) from exc
        return
    with (path/'execution.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkflowError('WORKFLOW_BUSY', '같은 실행을 처리 중입니다.', 409) from exc
        try:
            yield path
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class Repository:
    def __init__(self, work, request, binding):
        self.work, self.db = work, work.db
        self.db.create_function('workflow_hash',1,lambda value:digest(json.loads(value)),deterministic=True)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS workflow_state(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), request_json TEXT NOT NULL,
                request_hash TEXT NOT NULL, binding_hash TEXT NOT NULL, revision INTEGER NOT NULL,
                status TEXT NOT NULL, checkpoint_json TEXT NOT NULL, result_json TEXT,
                checkpoint_hash TEXT NOT NULL, result_hash TEXT);
            CREATE TABLE IF NOT EXISTS workflow_call(
                call_id TEXT PRIMARY KEY, kind TEXT NOT NULL, input_json TEXT NOT NULL,
                status TEXT NOT NULL, result_json TEXT, error_json TEXT, result_hash TEXT);
            CREATE TABLE IF NOT EXISTS workflow_active_tool(singleton INTEGER PRIMARY KEY CHECK(singleton=1), call_id TEXT);
            INSERT OR IGNORE INTO workflow_active_tool VALUES(1,NULL);
            CREATE TRIGGER IF NOT EXISTS workflow_observation_receipt AFTER INSERT ON observation
            BEGIN
                UPDATE workflow_call SET status='COMPLETE',
                    result_json=json_set(NEW.result_json,'$.observation_id',NEW.observation_id,'$.request_key',NEW.request_key),
                    result_hash=workflow_hash(json_set(NEW.result_json,'$.observation_id',NEW.observation_id,'$.request_key',NEW.request_key))
                WHERE call_id=(SELECT call_id FROM workflow_active_tool WHERE singleton=1) AND kind='rag' AND status='PREPARED';
            END;
        ''')
        row = self.db.execute('SELECT * FROM workflow_state').fetchone()
        if row is None:
            checkpoint={'stage':'INTAKE','history':[], 'gaps':[], 'repairs':{},'recovery_count':0}
            with work.transaction():
                self.db.execute('INSERT INTO workflow_state VALUES(1,?,?,?,1,?,?,NULL,?,NULL)',
                    (encoded(request), digest(request), digest(binding), 'running',
                     encoded(checkpoint),digest(checkpoint)))
                work.event('WORKFLOW_CREATED', {'workflow_id':request['workflow_id']})
        elif row['request_hash'] != digest(request) or row['binding_hash'] != digest(binding):
            raise WorkflowError('WORKFLOW_BINDING_CHANGED', '입력·코드·원문·권한 결속이 변경되어 재개할 수 없습니다.', 409)

    def state(self):
        row = dict(self.db.execute('SELECT * FROM workflow_state').fetchone())
        row['checkpoint'] = json.loads(row.pop('checkpoint_json'))
        row['result'] = json.loads(row.pop('result_json') or 'null')
        if digest(row['checkpoint'])!=row['checkpoint_hash'] or (
                row['result'] is not None and digest(row['result'])!=row['result_hash']) or (
                digest(json.loads(row['request_json']))!=row['request_hash']):
            raise WorkflowError('WORKFLOW_STATE_INTEGRITY','저장된 실행 상태의 해시가 다릅니다.',409)
        return row

    def save(self, checkpoint, *, status='running', result=None, expected=None):
        current = self.state()
        if expected is not None and expected != current['revision']:
            raise WorkflowError('WORKFLOW_STALE_REVISION', '이미 변경된 실행 상태입니다.', 409)
        revision = current['revision']+1
        if result is not None:
            result = {**result, 'revision':revision}
        with self.work.transaction():
            updated = self.db.execute('UPDATE workflow_state SET checkpoint_json=?,status=?,result_json=?,revision=?,checkpoint_hash=?,result_hash=? WHERE singleton=1 AND revision=?',
                (encoded(checkpoint),status,encoded(result) if result is not None else None,revision,
                 digest(checkpoint),digest(result) if result is not None else None,current['revision'])).rowcount
            if updated != 1:
                raise WorkflowError('WORKFLOW_STALE_REVISION', '동시 상태 변경입니다.', 409)
            self.work.event('WORKFLOW_CHECKPOINT', {'stage':checkpoint['stage'],'status':status,'revision':revision,
                                                    'checkpoint_hash':digest(checkpoint)})
        if checkpoint['stage'] != current['checkpoint']['stage'] or status != current['status']:
            from semantic_runtime import observability as obs
            obs.event(obs.get_logger('workflow'), 'workflow.stage.changed',
                      run_id=self.work.run()['run_id'], stage=checkpoint['stage'],
                      status=status, revision=revision)
        return result

    def call(self, ident):
        row = self.db.execute('SELECT * FROM workflow_call WHERE call_id=?',(ident,)).fetchone()
        if row is None: return None
        result=json.loads(row['result_json'] or 'null')
        if result is not None and digest(result)!=row['result_hash']:
            raise WorkflowError('WORKFLOW_CALL_INTEGRITY','저장된 호출 결과의 해시가 다릅니다.',409)
        return {**dict(row), 'result':result}

    def intent(self, ident, kind, value):
        old = self.call(ident)
        if old is not None:
            if old['kind'] != kind or old['input_json'] != encoded(value):
                raise WorkflowError('WORKFLOW_CALL_CONFLICT', '호출 식별자가 다른 입력에 사용되었습니다.', 409)
            return old
        with self.work.transaction():
            self.db.execute('INSERT INTO workflow_call VALUES(?,?,?,\'PREPARED\',NULL,NULL,NULL)',(ident,kind,encoded(value)))
            self.work.event('WORKFLOW_CALL_INTENT',{'call_id':ident,'kind':kind,'input_hash':digest(value)})
        return self.call(ident)

    def finish(self, ident, result):
        with self.work.transaction():
            self.db.execute("UPDATE workflow_call SET status='COMPLETE',result_json=?,result_hash=? WHERE call_id=? AND status='PREPARED'",
                            (encoded(result),digest(result),ident))
            self.work.event('WORKFLOW_CALL_RETURN',{'call_id':ident,'result_hash':digest(result)})

    def failure(self, ident, exc):
        detail={'type':type(exc).__name__,'code':getattr(exc,'code',type(exc).__name__),'message':str(exc)}
        with self.work.transaction():
            self.db.execute("UPDATE workflow_call SET status='FAILED',error_json=? WHERE call_id=?",(encoded(detail),ident))
            self.work.event('WORKFLOW_CALL_FAILED',{'call_id':ident,**detail})
