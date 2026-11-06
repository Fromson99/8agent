"""GENOS publishes immutable result parts to the existing Oracle Agent table.

One ORDS request inserts up to eight parts. READY (sequence zero) is committed
only after every part has been acknowledged and the source digest is verified.
There is no transport retry. PUBLISH explicitly resumes the same saved result.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import agent_stage as stage
import transport as t

BATCH_PARTS = 8
REQUIRED = ('ORACLE_ORDS_SCHEMA', 'ORACLE_ORDS_CLIENT_ID', 'ORACLE_ORDS_CLIENT_SECRET')


def configuration():
    return {'table': stage.TABLE, 'configured': all(os.environ.get(k, '').strip() for k in REQUIRED),
            'missing': [k for k in REQUIRED if not os.environ.get(k, '').strip()],
            'batch_parts': BATCH_PARTS, 'part_bytes': stage.PART}


def connection(h, code):
    if not configuration()['configured']:
        raise ValueError('AGENT_ORDS_CONFIGURATION_REQUIRED')
    sys.path.insert(0, str(Path(__file__).resolve().parent / '02_BACKEND'))
    from semantic_runtime.oracle_dp_io import SQL
    from semantic_runtime.oracle_ords import create_client
    options = dict(schema=os.environ['ORACLE_ORDS_SCHEMA'],
                   auth_key=(os.environ['ORACLE_ORDS_CLIENT_ID'], os.environ['ORACLE_ORDS_CLIENT_SECRET']),
                   timeout=60, verify=True)
    if os.environ.get('ORACLE_ORDS_BASE_URL'):
        options['base_url'] = os.environ['ORACLE_ORDS_BASE_URL']
    return SQL(create_client(**options), journal=h['folder'] / 'agent-ords.jsonl',
               binding=stage.binding(h['id'], h['archives'], code),
               seconds=max(0, h['deadline'] - time.time()))


def preflight(h, code):
    sql = connection(h, code)
    # Parse both privileges without writing a probe row or performing DDL.
    sql.request(f"""DECLARE n NUMBER; BEGIN
      SELECT COUNT(*) INTO n FROM {stage.TABLE} WHERE 1=0;
      IF FALSE THEN INSERT INTO {stage.TABLE}
        (JOB_ID,SEQ_NO,BIND_HASH,DATA_HASH,BYTE_CNT,PART_CNT)
        VALUES(NULL,0,NULL,NULL,1,1); END IF;
    END;""", write=False, limit=1)


def batch_statement(job, bound, rows):
    stage.predicate(job, bound)
    if not rows or len(rows) > BATCH_PARTS or len({r['seq'] for r in rows}) != len(rows):
        raise ValueError('STAGE_BATCH_ROWS')
    payload = json.dumps(rows, separators=(',', ':'), ensure_ascii=True)
    args = [('job', job, 'VARCHAR2'), ('bound', bound, 'VARCHAR2'), ('expected', len(rows), 'NUMBER')]
    names = []
    # Small VARCHAR2 binds also work with the existing GENOS ORDS SDK, without
    # depending on its handling of a large CLOB bind or embedding data in SQL.
    for start in range(0, len(payload), stage.SLICE):
        name = 'p' + str(len(names))
        args.append((name, payload[start:start + stage.SLICE], 'VARCHAR2'))
        names.append('TO_CLOB(:' + name + ')')
    source = """JSON_TABLE(payload,'$[*]' ERROR ON ERROR COLUMNS(
      seq NUMBER PATH '$.seq' ERROR ON ERROR,
      sha VARCHAR2(64) PATH '$.sha' ERROR ON ERROR,
      sz NUMBER PATH '$.size' ERROR ON ERROR,
      cnt NUMBER PATH '$.count' ERROR ON ERROR,
      body CLOB PATH '$.body' ERROR ON ERROR)) s"""
    statement = f"""DECLARE payload CLOB := {' || '.join(names)}; n NUMBER; BEGIN
      BEGIN
        INSERT INTO {stage.TABLE}(JOB_ID,SEQ_NO,BIND_HASH,DATA_HASH,BYTE_CNT,PART_CNT,BODY_B64)
        SELECT :job,s.seq,:bound,s.sha,s.sz,s.cnt,s.body FROM {source}
        WHERE NOT EXISTS (SELECT 1 FROM {stage.TABLE} t WHERE t.JOB_ID=:job AND t.SEQ_NO=s.seq);
      EXCEPTION WHEN DUP_VAL_ON_INDEX THEN NULL;
      END;
      SELECT COUNT(*) INTO n FROM {source} JOIN {stage.TABLE} t
        ON t.JOB_ID=:job AND t.SEQ_NO=s.seq
        WHERE t.BIND_HASH=:bound AND t.DATA_HASH=s.sha AND t.BYTE_CNT=s.sz AND t.PART_CNT=s.cnt
          AND ((t.BODY_B64 IS NULL AND s.body IS NULL) OR DBMS_LOB.COMPARE(t.BODY_B64,s.body)=0);
      IF n<>:expected THEN RAISE_APPLICATION_ERROR(-20051,'STAGE_CONFLICT'); END IF;
      COMMIT;
    EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;"""
    return statement, args


def write_result(sql, path, job, bound, receipt, guard):
    if (type(receipt.get('bytes')) is not int or not 0 < receipt['bytes'] <= 100 * 1024**3
            or not isinstance(receipt.get('sha256'), str) or len(receipt['sha256']) != 64):
        raise ValueError('STAGE_ARCHIVE_SIZE_OR_HASH')
    count, total, pending = 0, 0, []
    whole = hashlib.sha256()

    def flush(rows):
        guard()
        statement, binds = batch_statement(job, bound, rows)
        sql.request(statement, binds, write=True, limit=1)

    with Path(path).open('rb') as stream:
        while block := stream.read(stage.PART):
            guard()
            count += 1
            total += len(block)
            whole.update(block)
            pending.append({'seq': count, 'sha': hashlib.sha256(block).hexdigest(),
                            'size': len(block), 'count': 0, 'body': base64.b64encode(block).decode('ascii')})
            if len(pending) == BATCH_PARTS:
                flush(pending)
                pending = []
    if not count or total != receipt['bytes'] or whole.hexdigest() != receipt['sha256']:
        raise ValueError('STAGE_SOURCE_CHANGED')
    if pending:
        flush(pending)
    flush([{'seq': 0, 'sha': whole.hexdigest(), 'size': total, 'count': count, 'body': None}])


def publish(h, code, result, guard):
    path = h['folder'] / 'result.zip'
    guard()
    if path.stat().st_size != result['bytes'] or t.sha(path) != result['sha256']:
        raise ValueError('STAGE_SAVED_RESULT_CHANGED')
    write_result(connection(h, code), path, h['id'], stage.binding(h['id'], h['archives'], code), result, guard)
