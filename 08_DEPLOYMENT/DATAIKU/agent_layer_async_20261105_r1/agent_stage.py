"""Immutable SIDDA result parts. Sequence zero is the committed READY receipt."""
import base64
import hashlib
import os
from pathlib import Path
import re
import sys
import time

import transport as t

TABLE = 'SIDDA.LGL_PIPE_RESULT_A'
# Each VARCHAR2 bind/selected expression fits the ordinary Oracle SQL limit.
SLICE = 3000
SLICES = 32
PART = SLICE * SLICES * 3 // 4


def mounted_support():
    name = os.environ.get('AGENT_PIPELINE_SUPPORT_ZIP','').strip()
    checksum = os.environ.get('AGENT_PIPELINE_SUPPORT_SHA256','').strip()
    if not name and not checksum:
        return None
    path = Path(name)
    if (not path.is_absolute() or not path.is_file() or not re.fullmatch('[0-9a-f]{64}',checksum)
            or not 0 < path.stat().st_size <= 64*1024**3):
        raise ValueError('MOUNTED_SUPPORT_CONFIG')
    # Worker verifies actual bytes against this pin before unpacking on every run.
    return path.resolve(), {'bytes':path.stat().st_size,'sha256':checksum}


def binding(job, archives, code):
    return t.digest({'format': 'agent-result-v1', 'job': job, 'archives': archives, 'code': code})


def publish(h, code, result, guard):
    sys.path.insert(0, str(Path(__file__).resolve().parent / '02_BACKEND'))
    from semantic_runtime.oracle_dp_io import SQL
    from semantic_runtime.oracle_ords import create_client
    options = dict(schema=os.environ['ORACLE_ORDS_SCHEMA'],
                   auth_key=(os.environ['ORACLE_ORDS_CLIENT_ID'], os.environ['ORACLE_ORDS_CLIENT_SECRET']),
                   timeout=60, verify=True)
    if os.environ.get('ORACLE_ORDS_BASE_URL'):
        options['base_url'] = os.environ['ORACLE_ORDS_BASE_URL']
    sql = SQL(create_client(**options), journal=h['folder']/'ord-preview.jsonl',
              binding=binding(h['id'], h['archives'], code), seconds=h['deadline']-time.time())
    write_result(sql, h['folder']/'result.zip', h['id'], sql.binding, result, guard)


def write_result(sql, path, job, bound, receipt, guard):
    def insert(seq, sha, size, count, raw):
        args = [('job', job, 'VARCHAR2'), ('seq', seq, 'NUMBER'), ('bound', bound, 'VARCHAR2'),
                ('sha', sha, 'VARCHAR2'), ('sz', size, 'NUMBER'), ('cnt', count, 'NUMBER')]
        data = base64.b64encode(raw).decode('ascii')
        expr = 'NULL'
        if data:
            names = []
            for i in range(0, len(data), SLICE):
                name = 'v'+str(i//SLICE)
                args.append((name, data[i:i+SLICE], 'VARCHAR2'))
                names.append('TO_CLOB(:'+name+')')
            expr = ' || '.join(names)
        # An ambiguous acknowledgement can be reconciled by repeating these exact bytes.
        statement = f"""DECLARE body CLOB := {expr}; n NUMBER; BEGIN
          BEGIN INSERT INTO {TABLE}(JOB_ID,SEQ_NO,BIND_HASH,DATA_HASH,BYTE_CNT,PART_CNT,BODY_B64)
            VALUES(:job,:seq,:bound,:sha,:sz,:cnt,body);
          EXCEPTION WHEN DUP_VAL_ON_INDEX THEN
            SELECT COUNT(*) INTO n FROM {TABLE} WHERE JOB_ID=:job AND SEQ_NO=:seq
            AND BIND_HASH=:bound AND DATA_HASH=:sha AND BYTE_CNT=:sz AND PART_CNT=:cnt
            AND ((BODY_B64 IS NULL AND body IS NULL) OR DBMS_LOB.COMPARE(BODY_B64,body)=0);
            IF n<>1 THEN RAISE_APPLICATION_ERROR(-20051,'STAGE_CONFLICT'); END IF;
          END; COMMIT; END;"""
        sql.request(statement, args, write=True, limit=1)

    if not 0 < receipt['bytes'] <= 100*1024**3:
        raise ValueError('STAGE_ARCHIVE_SIZE')
    total = 0
    count = 0
    whole = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(PART):
            guard()
            count += 1
            insert(count, hashlib.sha256(block).hexdigest(), len(block), 0, block)
            total += len(block)
            whole.update(block)
    if not count or total != receipt['bytes'] or whole.hexdigest() != receipt['sha256']:
        raise ValueError('STAGE_SOURCE_CHANGED')
    guard()
    insert(0, whole.hexdigest(), total, count, b'')


def predicate(job, bound):
    if not re.fullmatch('[0-9a-f]{32}', job) or not re.fullmatch('[0-9a-f]{64}', bound):
        raise ValueError('STAGE_KEY')
    return f" FROM {TABLE} WHERE JOB_ID='{job}' AND BIND_HASH='{bound}'"


def ready(query, job, bound):
    rows = query('SELECT DATA_HASH, BYTE_CNT, PART_CNT'+predicate(job,bound)+' AND SEQ_NO=0')
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError('STAGE_HEADER_DUPLICATE')
    row = rows[0]
    size, count = int(row['BYTE_CNT']), int(row['PART_CNT'])
    if not 0 < size <= 100*1024**3 or count != (size+PART-1)//PART or not re.fullmatch('[0-9a-f]{64}',row['DATA_HASH']):
        raise ValueError('STAGE_HEADER_INVALID')
    return dict(bytes=size, parts=count, sha256=row['DATA_HASH'])


def restore(query, job, bound, receipt, path):
    if ready(query, job, bound) != receipt:
        raise ValueError('STAGE_NOT_READY_OR_CHANGED')
    if path.exists():
        if path.stat().st_size != receipt['bytes'] or t.sha(path) != receipt['sha256']:
            raise ValueError('STAGE_LOCAL_CONFLICT')
        return
    columns = ','.join(f'DBMS_LOB.SUBSTR(BODY_B64,{SLICE},{i*SLICE+1}) AS C{i}' for i in range(SLICES))
    select = 'SELECT SEQ_NO,DATA_HASH,BYTE_CNT,'+columns+predicate(job,bound)
    tmp = path.with_suffix('.partial')
    # Under a per-job filesystem lock. Restart only this disposable local reconstruction.
    whole, size = hashlib.sha256(), 0
    with tmp.open('wb') as out:
        for start in range(1, receipt['parts']+1, 16):
            end = min(start+15,receipt['parts'])
            rows = query(select+f' AND SEQ_NO BETWEEN {start} AND {end} ORDER BY SEQ_NO')
            if [int(r['SEQ_NO']) for r in rows] != list(range(start,end+1)):
                raise ValueError('STAGE_MISSING_PART')
            for r in rows:
                encoded = ''.join(r[f'C{i}'] for i in range(SLICES) if isinstance(r[f'C{i}'],str))
                data = base64.b64decode(encoded,validate=True)
                if len(data) != int(r['BYTE_CNT']) or hashlib.sha256(data).hexdigest() != r['DATA_HASH']:
                    raise ValueError('STAGE_PART_HASH')
                size += len(data)
                whole.update(data)
                out.write(data)
    if size != receipt['bytes'] or whole.hexdigest() != receipt['sha256']:
        raise ValueError('STAGE_WHOLE_HASH')
    os.replace(tmp,path)
