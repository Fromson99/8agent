# Dataiku Python 레시피 · Gold 최신판본 선택 정보 보완 R7 (플로우용, 2026-11-09)
# 입력 폴더 gold_selection_input : SEARCH_SELECTION_GENERATION.json 하나(읽기만 한다)
# 폴더·버킷에는 아무것도 쓰지 않는다. 결과는 레시피 실행 로그에만 남고, 바뀌는 것은 Oracle Gold뿐이다.
# 출력 폴더는 Dataiku 레시피 형식상 연결만 해 두며 쓰지 않는다.
# 실행 모드는 프로젝트 변수 GOLD_FIX_MODE 로 바꾼다(코드 수정 불필요): APPLY(기본, 확인 후 바로 UPDATE) / CHECK(읽기만) / ROLLBACK
# 같은 방식으로 GOLD_FIX_ORACLE_CONNECTION, GOLD_FIX_EXPECTED_DB_USER, GOLD_FIX_GOLD_OWNER, GOLD_FIX_CHANNEL 도 덮어쓸 수 있다.
SETTINGS = {
    'MODE': 'APPLY',
    'ORACLE_CONNECTION': 'AIDP',        # 운영 Oracle 연결 이름
    'EXPECTED_DB_USER': 'PIDD2APP',     # 그 연결의 접속 계정
    'GOLD_OWNER': 'SIDDG',              # 운영 Gold owner
    'TABLE_PREFIX': 'IDD_B003_LGL_',
    'INPUT_FOLDER': 'gold_selection_input',
    'SELECTION_FILE': '',               # 비우면 입력 폴더의 .json 파일 하나
    'CHANNEL': '',                      # 비우면 SRCH_CHNL의 한 줄
    'UPDATE_BATCH_ROWS': 50000,         # UPDATE 한 번에 바꾸는 행 수(바꿀 때마다 COMMIT)
    'UPDATE_BLOCK_SECONDS': 120,        # DB 호출 한 번의 최대 시간
}

import base64
import copy
import gzip
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import time
import dataiku

try:
    _VARS = dataiku.get_custom_variables()
except Exception:
    _VARS = {}
for _k in ('MODE', 'ORACLE_CONNECTION', 'EXPECTED_DB_USER', 'GOLD_OWNER', 'CHANNEL'):
    _v = _VARS.get('GOLD_FIX_'+_k)
    if isinstance(_v, str) and _v.strip():
        SETTINGS[_k] = _v.strip().upper() if _k == 'MODE' else _v.strip()

SEL_V2 = 'filename-search-selection-v2'
VERSION = 'gold-selection-flow-20261109-r7f'
# 운영 Gold 등록 컬럼(R5 registration_current와 같음)
COLS = {
    'SRC_POST': {'id': 'BODY_POST_HASH_VALU', 'dtls': 'DTLS_HASH_VALU', 'body': 'BODY_POST_IFMN_CTNT', 'time': 'RGSN_ASTM'},
    'SRCH_POST': {'id': 'RFRN_POST_HASH_VALU', 'body': 'RFRN_POST_IFMN_CTNT'},
    'SRCH_CHNL': {'name': 'RFRN_CHNL_NAME', 'q': 'RFRN_POST_HASH_VALU', 'no': 'CHAN_NO'},
    'SRCH_ROW': {'q': 'RFRN_POST_HASH_VALU', 'type': 'RFRN_DTA_TYPE_VALU', 'id': 'RFRN_DTA_ID'},
    'VCTR_POST': {'id': 'VCTR_POST_ID', 'body': 'VCTR_POST_IFMN_CTNT'},
    'VCTR_HEAD': {'q': 'RFRN_POST_HASH_VALU', 'v': 'VCTR_POST_ID', 'no': 'CHAN_NO'},
    'VCTR_ITEM': {'v': 'VCTR_POST_ID'},
}


class Stop(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def literal(value):
    if not isinstance(value, str) or '\0' in value or len(value.encode()) > 4000: raise Stop('SQL_LITERAL')
    return "'" + value.replace("'", "''") + "'"


# ---- R5 jdbc_transport.render 그대로: 큰 값은 gzip+base64로 보내 Oracle 안에서 UTF-8 CLOB로 복원 ----
TOKEN=re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/|:([A-Za-z][A-Za-z0-9_]*)")
CHUNK_BYTES=1800
PACKED_CHUNK_BYTES=2700  # 3600 ASCII base64 characters, below 4000-byte SQL literal limit.


def utf8_chunks(value,limit=CHUNK_BYTES):
    raw=value.encode('utf-8');start=0
    while start<len(raw):
        end=min(start+limit,len(raw))
        while end<len(raw) and raw[end]&0xC0==0x80:end-=1
        yield raw[start:end];start=end


def expression(raw):
    return "UTL_I18N.RAW_TO_CHAR(HEXTORAW('"+raw.hex().upper()+"'),'AL32UTF8')"


def render(statement,binds,*,write=False):
    values={};declarations=[];initializers=[];cleanup=[]
    for index,(name,value,kind) in enumerate(binds):
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name) or name in values:
            raise ValueError('JDBC_BIND_DUPLICATE_OR_INVALID')
        if value is None:values[name]='NULL';continue
        if kind=='NUMBER':
            if type(value) is not int:raise ValueError('JDBC_INTEGER_REQUIRED')
            values[name]=str(value)
        elif kind in {'VARCHAR2','CLOB'}:
            if type(value) is not str or '\0' in value:raise ValueError('JDBC_TEXT_REQUIRED')
            encoded=value.encode('utf-8')
            if kind=='VARCHAR2':
                if len(encoded)>4000:raise ValueError('JDBC_VARCHAR2_LIMIT')
                chunks=list(utf8_chunks(value))
                values[name]='('+' || '.join(expression(raw) for raw in chunks)+')' if chunks else 'NULL'
            else:
                if not write:raise ValueError('JDBC_CLOB_REQUIRES_BLOCK')
                var='g8_lob_'+str(index)
                values[name]=var;declarations.append(var+' CLOB;')
                initializers.append('DBMS_LOB.CREATETEMPORARY('+var+',TRUE,DBMS_LOB.CALL);')
                if len(encoded)>32768:
                    # Transfer large JSON as gzip bytes, then reconstruct the
                    # identical UTF-8 CLOB before executing the original SQL.
                    packed=gzip.compress(encoded,compresslevel=6,mtime=0)
                    blob='g8_zip_'+str(index);plain='g8_raw_'+str(index);prefix='g8_'+str(index)
                    declarations.extend([blob+' BLOB;',plain+' BLOB;',prefix+'_d INTEGER:=1;',
                                         prefix+'_s INTEGER:=1;',prefix+'_c INTEGER:=0;',prefix+'_w INTEGER;'])
                    initializers.append('DBMS_LOB.CREATETEMPORARY('+blob+',TRUE,DBMS_LOB.CALL);')
                    for offset in range(0,len(packed),PACKED_CHUNK_BYTES):
                        piece=packed[offset:offset+PACKED_CHUNK_BYTES]
                        payload=base64.b64encode(piece).decode('ascii')
                        initializers.append('DBMS_LOB.WRITEAPPEND('+blob+','+str(len(piece))+",UTL_ENCODE.BASE64_DECODE(UTL_RAW.CAST_TO_RAW('"+payload+"')));")
                    initializers.append(plain+':=UTL_COMPRESS.LZ_UNCOMPRESS('+blob+');')
                    initializers.append('DBMS_LOB.FREETEMPORARY('+blob+'); '+blob+':=NULL;')
                    initializers.append('DBMS_LOB.CONVERTTOCLOB('+var+','+plain+',DBMS_LOB.LOBMAXSIZE,'+
                                        prefix+'_d,'+prefix+"_s,NLS_CHARSET_ID('AL32UTF8'),"+prefix+'_c,'+prefix+'_w);')
                    initializers.append('IF '+prefix+"_w<>0 THEN RAISE_APPLICATION_ERROR(-20063,'JDBC_UTF8_CONVERSION_WARNING'); END IF;")
                    initializers.append('DBMS_LOB.FREETEMPORARY('+plain+'); '+plain+':=NULL;')
                    for item in (blob,plain):cleanup.append('IF DBMS_LOB.ISTEMPORARY('+item+')=1 THEN DBMS_LOB.FREETEMPORARY('+item+'); END IF;')
                else:
                    for raw in utf8_chunks(value):
                        initializers.append('DBMS_LOB.APPEND('+var+',TO_CLOB('+expression(raw)+'));')
                cleanup.append('IF DBMS_LOB.ISTEMPORARY('+var+')=1 THEN DBMS_LOB.FREETEMPORARY('+var+'); END IF;')
        else:raise ValueError('JDBC_UNSUPPORTED_BIND_TYPE')
    used=set()
    def replace(match):
        name=match.group(1)
        if name is None:return match.group()
        if name not in values:raise ValueError('JDBC_BIND_MISSING:'+name)
        used.add(name);return values[name]
    compiled=TOKEN.sub(replace,statement)
    if used!=set(values):raise ValueError('JDBC_BIND_UNUSED')
    if declarations:
        free='\n'.join(cleanup)
        compiled='DECLARE\n'+'\n'.join(declarations)+'\nBEGIN\n'+'\n'.join(initializers)+'\n'+compiled+'\n'+free+'\nEXCEPTION WHEN OTHERS THEN\n'+free+'\nRAISE;\nEND;'
    return compiled



LOG = []


def log(phase, **fields):
    line = json.dumps(dict(phase=phase, at=time.strftime('%H:%M:%S'), **fields), ensure_ascii=False)
    LOG.append(line); print(line, flush=True)


class DB:
    """R5 gold_io.Database와 같은 방식: 읽기는 query_to_df, 쓰기는 pre_queries의 PL/SQL 블록."""
    def __init__(self, connection):
        self.ex = dataiku.SQLExecutor2(connection=connection)

    def query(self, sql, limit=1000):
        frame = self.ex.query_to_df(sql, infer_from_schema=True, parse_dates=False)
        frame = frame.astype(object).where(frame.notna(), None)
        rows = frame.to_dict(orient='records')
        if len(rows) > limit: raise Stop('RESULT_LIMIT')
        return [{str(k).upper(): (v.item() if hasattr(v, 'item') else v) for k, v in r.items()} for r in rows]

    def block(self, sql, binds=(), rollback=False):
        rendered = render(sql, binds, write=True)
        frame = self.ex.query_to_df('SELECT 1 AS OK FROM DUAL', pre_queries=[rendered],
                                    post_queries=['ROLLBACK' if rollback else 'COMMIT'])
        if len(frame) != 1 or int(frame.iloc[0]['OK']) != 1: raise Stop('WRITE_RESPONSE_UNCONFIRMED')


class Fix:
    def __init__(self):
        s = SETTINGS
        if s['MODE'] not in ('CHECK', 'APPLY', 'ROLLBACK'): raise Stop('MODE_MUST_BE_CHECK_APPLY_ROLLBACK')
        for name in ('UPDATE_BATCH_ROWS', 'UPDATE_BLOCK_SECONDS'):
            if type(s[name]) is not int or not 1 <= s[name] <= 1000000: raise Stop('INVALID:'+name)
        for name in ('GOLD_OWNER', 'EXPECTED_DB_USER'):
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', s[name]): raise Stop('INVALID:'+name)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,20}', s['TABLE_PREFIX']): raise Stop('INVALID:TABLE_PREFIX')
        self.mode = s['MODE']
        self.inp = dataiku.Folder(s['INPUT_FOLDER'])
        self.db = DB(s['ORACLE_CONNECTION'])
        rows = self.db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS U FROM DUAL")
        if rows != [{'U': s['EXPECTED_DB_USER']}]: raise Stop('DATABASE_USER_MISMATCH:'+str(rows))
        for key in COLS: self.db.query('SELECT 1 AS N FROM '+self.T(key)+' WHERE 1=0')
        self.run_id = time.strftime('%Y%m%d-%H%M%S')

    def T(self, key): return SETTINGS['GOLD_OWNER']+'.'+SETTINGS['TABLE_PREFIX']+key
    def C(self, key, name): return COLS[key][name]

    # ---------- 읽기 ----------
    def body(self, key, value):
        rows = self.db.query('SELECT '+self.C(key,'body')+' AS BODY FROM '+self.T(key)+' WHERE '+
                             self.C(key,'id')+'='+literal(value), limit=2)
        if len(rows) > 1: raise Stop('DUPLICATE_ROW:'+key)
        if not rows: return None
        v = json.loads(rows[0]['BODY'])
        if digest(v['manifest'] if key == 'VCTR_POST' else v) != value: raise Stop('CONTENT_HASH_MISMATCH:'+key)
        return v

    def count(self, key, col, value):
        return int(self.db.query('SELECT COUNT(*) AS N FROM '+self.T(key)+' WHERE '+self.C(key,col)+'='+literal(value))[0]['N'])

    def exists(self, key, col, value):
        return int(self.db.query('SELECT COUNT(*) AS N FROM '+self.T(key)+' WHERE '+self.C(key,col)+'='+literal(value)+
                                 ' AND ROWNUM<=1')[0]['N']) == 1

    def channel(self):
        c = lambda n: self.C('SRCH_CHNL', n)
        rows = self.db.query('SELECT '+c('name')+' AS NAME,'+c('q')+' AS Q,'+c('no')+' AS NO FROM '+self.T('SRCH_CHNL'))
        if SETTINGS['CHANNEL']: rows = [r for r in rows if r['NAME'] == SETTINGS['CHANNEL']]
        if len(rows) != 1: raise Stop('CHANNEL_NOT_ONE: SRCH_CHNL 줄이 '+str(len(rows))+'개입니다. SETTINGS["CHANNEL"]을 지정하세요.')
        return {'name': rows[0]['NAME'], 'q': rows[0]['Q'], 'no': int(rows[0]['NO'])}

    def vector_head(self, q):
        c = lambda n: self.C('VCTR_HEAD', n)
        rows = self.db.query('SELECT '+c('v')+' AS V FROM '+self.T('VCTR_HEAD')+' WHERE '+c('q')+'='+literal(q), limit=2)
        return rows[0]['V'] if rows else None

    # ---------- 폴더 ----------
    def selection(self):
        paths = [p for p in self.inp.list_paths_in_partition()
                 if (PurePosixPath(p).name == SETTINGS['SELECTION_FILE'] if SETTINGS['SELECTION_FILE'] else p.lower().endswith('.json'))]
        if len(paths) != 1: raise Stop('PUT_ONE_SELECTION_JSON_IN_INPUT_FOLDER (찾은 수 '+str(len(paths))+')')
        with self.inp.get_download_stream(paths[0]) as f: raw = f.read(16*1024**2+1)
        if len(raw) > 16*1024**2: raise Stop('SELECTION_FILE_TOO_LARGE')
        value = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(value, dict) or value.get('schema_version') != SEL_V2: raise Stop('SELECTION_NOT_V2')
        rows = value.get('excluded')
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('document_id'), str)
                                             or not r['document_id'] for r in rows): raise Stop('SELECTION_EXCLUDED_INVALID')
        excluded = [r['document_id'] for r in rows]
        if len(set(excluded)) != len(excluded): raise Stop('SELECTION_DUPLICATE_EXCLUDED')
        marks = value.get('latest_documents')
        if not isinstance(marks, list) or {m.get('document_id') for m in marks if m.get('is_latest') is False} != set(excluded):
            raise Stop('SELECTION_LATEST_MARK_EXCLUSION_MISMATCH')
        log('SELECTION_FILE', path=paths[0], sha256=hashlib.sha256(raw).hexdigest(), excluded=len(excluded))
        return value, hashlib.sha256(raw).hexdigest()

    # ---------- DB에서 원래 번호 찾기(파일에 저장하지 않음) ----------
    def post_ids(self, key):
        return [r['ID'] for r in self.db.query('SELECT '+self.C(key,'id')+' AS ID FROM '+self.T(key), limit=1000)]

    def original_vector(self, q0id):
        """벡터 연결이 이미 새 번호로 바뀐 중단 상태에서도 원래 벡터 게시본을 DB에서 찾는다."""
        found = [v for v in self.post_ids('VCTR_POST') if (self.body('VCTR_POST', v) or {}).get('manifest', {}).get('query_id') == q0id]
        if len(found) > 1: raise Stop('VECTOR_POST_AMBIGUOUS')
        return found[0] if found else None

    def derive_applied(self, q1id):
        """채널이 이미 새 번호면, 같은 선택 정보로 계산했을 때 그 번호가 나오는 원래 명세를 SRCH_POST에서 찾는다."""
        q1 = self.body('SRCH_POST', q1id)
        sel = q1['search_selection']
        for q0id in self.post_ids('SRCH_POST'):
            if q0id == q1id: continue
            q0 = self.body('SRCH_POST', q0id)
            if (q0.get('search_selection') or {}).get('schema_version') == SEL_V2 or q0.get('dataset_version') != q1.get('dataset_version'):
                continue
            plan = self.plan(q0id, sel, digest(sel))[0]
            if plan['q1'] == q1id: return plan
        raise Stop('ORIGINAL_RELEASE_NOT_FOUND')

    # ---------- 새 게시본 계산 ----------
    def plan(self, q0id, sel, sel_sha):
        q0 = self.body('SRCH_POST', q0id)
        if q0 is None: raise Stop('QUERY_RELEASE_MISSING')
        if (q0.get('search_selection') or {}).get('schema_version') == SEL_V2: raise Stop('CHANNEL_ALREADY_HAS_SELECTION')
        s0id = q0['source_release_id']; s0 = self.body('SRC_POST', s0id)
        if s0 is None: raise Stop('SOURCE_RELEASE_MISSING')
        manifest = s0['source_manifest']
        checks = {'generation_id': (sel.get('generation_id'), manifest.get('generation_id')),
                  'manifest_sha256': (sel.get('manifest_sha256'), s0.get('dataset_version')),
                  'store_sha256': (sel.get('store_sha256'), manifest.get('store_sha256')),
                  'query_dataset_version': (q0.get('dataset_version'), s0.get('dataset_version'))}
        wrong = {k: v for k, v in checks.items() if v[0] != v[1]}
        if wrong: raise Stop('SELECTION_BELONGS_TO_ANOTHER_GENERATION:'+json.dumps(wrong))
        scope = manifest['scope']['document_version_ids']
        excluded = {r['document_id'] for r in sel['excluded']}
        if not excluded <= set(scope): raise Stop('SELECTION_EXCLUDES_UNKNOWN_DOCUMENT')
        s1 = copy.deepcopy(s0); s1['search_selection'] = sel; s1id = digest(s1)
        q1 = copy.deepcopy(q0); q1['search_selection'] = sel; q1['source_release_id'] = s1id
        q1['selection_proof'] = {'fingerprint': digest(sel), 'native_latest_verified': False}
        q1id = digest(q1)
        v0 = self.vector_head(q0id) or self.original_vector(q0id)
        vector = env1 = None
        if v0:
            env0 = self.body('VCTR_POST', v0)
            if env0 is None or set(env0) != {'manifest', 'completion'}: raise Stop('VECTOR_POST_INVALID')
            m0 = env0['manifest']
            if m0.get('query_id') != q0id or m0.get('source_release_id') != s0id: raise Stop('VECTOR_BINDING_MISMATCH')
            m1 = copy.deepcopy(m0); m1['query_id'] = q1id; m1['source_release_id'] = s1id
            env1 = {'manifest': m1, 'completion': env0['completion']}
            vector = {'v0': v0, 'v1': digest(m1), 'count': env0['completion']['count']}
        plan = {'version': VERSION, 'q0': q0id, 's0': s0id, 'q1': q1id, 's1': s1id, 'vector': vector,
                'dataset_version': s0['dataset_version'], 'generation_id': manifest['generation_id'],
                'selection_sha256': sel_sha, 'selection_fingerprint': digest(sel), 'documents': len(scope), 'excluded': len(excluded),
                'searchable': len(scope)-len(excluded), 'search_rows': sum(t['rows'] for t in q0['tables'].values()),
                'kinds': {k: q0['tables'][k]['rows'] for k in sorted(q0['tables'])}}
        return plan, s1, q1, env1

    # ---------- 권한 ----------
    def privileges(self):
        missing = []
        def can(kind, key, statement):
            try: self.db.block('BEGIN IF FALSE THEN '+statement+'; END IF; END;', rollback=True)
            except Exception as exc:
                if any(code in str(exc) for code in ('ORA-01031', 'ORA-00942', 'PLS-')): missing.append((kind, key))
                else: raise
        for key in ('SRC_POST', 'SRCH_POST', 'VCTR_POST'):
            can('INSERT', key, 'INSERT INTO '+self.T(key)+' SELECT * FROM '+self.T(key)+' WHERE 1=0')
        for key, col in (('SRCH_ROW', 'q'), ('VCTR_ITEM', 'v'), ('VCTR_HEAD', 'q'), ('SRCH_CHNL', 'q')):
            can('UPDATE', key, 'UPDATE '+self.T(key)+' SET '+self.C(key,col)+'='+self.C(key,col)+' WHERE 1=0')
        if missing:
            grants = ['GRANT '+k+' ON '+self.T(t)+' TO '+SETTINGS['EXPECTED_DB_USER']+';' for k, t in missing]
            log('PRIVILEGE_REQUIRED', message='DBA에게 아래 권한을 요청하세요. 아무것도 바꾸지 않고 멈췄습니다.', grants=grants)
            raise Stop('PRIVILEGE_REQUIRED: '+' '.join(grants))

    # ---------- 쓰기 ----------
    def insert(self, key, value_id, content):
        if self.exists(key, 'id', value_id):
            if self.body(key, value_id) is None: raise Stop('EXISTING_POST_UNREADABLE:'+key)
            log('POST_EXISTS', table=key); return
        cols = [self.C(key,'id')]; vals = [':row_id']; binds = [('row_id', value_id, 'VARCHAR2')]
        if key == 'SRC_POST':
            cols += [self.C(key,'dtls'), self.C(key,'time')]; vals += [':dtls', 'SYSTIMESTAMP']
            binds.append(('dtls', content['dataset_version'], 'VARCHAR2'))
        cols.append(self.C(key,'body')); vals.append(':body'); binds.append(('body', canonical(content), 'CLOB'))
        self.db.block('BEGIN INSERT INTO '+self.T(key)+' ('+','.join(cols)+') VALUES ('+','.join(vals)+'); COMMIT; END;', binds)
        if self.body(key, value_id) is None: raise Stop('POST_READBACK:'+key)
        log('POST_INSERTED', table=key)

    def move(self, key, col, old, new, label):
        if not self.exists(key, col, old): log('MOVE_DONE', table=label, remaining=0); return
        total = self.count(key, col, old); log('MOVE_START', table=label, rows=total)
        sql = ('DECLARE n NUMBER; t0 NUMBER := DBMS_UTILITY.GET_TIME; BEGIN LOOP UPDATE '+self.T(key)+' SET '+
               self.C(key,col)+'=:new_id WHERE '+self.C(key,col)+'=:old_id AND ROWNUM<=:batch_rows; '
               'n := SQL%ROWCOUNT; COMMIT; EXIT WHEN n=0 OR DBMS_UTILITY.GET_TIME-t0>=:limit_cs; END LOOP; END;')
        binds = [('new_id', new, 'VARCHAR2'), ('old_id', old, 'VARCHAR2'),
                 ('batch_rows', SETTINGS['UPDATE_BATCH_ROWS'], 'NUMBER'), ('limit_cs', SETTINGS['UPDATE_BLOCK_SECONDS']*100, 'NUMBER')]
        started = time.monotonic(); calls = 0
        while True:
            self.db.block(sql, binds); calls += 1
            if not self.exists(key, col, old): break
            if calls % 5 == 0:
                left = self.count(key, col, old)
                log('MOVE_PROGRESS', table=label, done=total-left, total=total, seconds=round(time.monotonic()-started))
        log('MOVE_DONE', table=label, rows=total, seconds=round(time.monotonic()-started))

    def move_search_rows(self, old, new, kinds, label):
        """검색 행 번호 변경: 종류별로 PK 인덱스(번호, 종류, ID) 순서를 따라 앞에서부터 구간씩 바꾼다.
        다음 구간의 끝 ID를 인덱스로 먼저 찾고 '지난 끝 < ID <= 이번 끝' 만 UPDATE 하므로 이미 바꾼 부분을 다시 읽지 않는다.
        종류 목록 밖에 남은 행이 있으면 마지막에 기존 방식으로 마저 바꾼다."""
        T, q, ty, ix = self.T('SRCH_ROW'), self.C('SRCH_ROW','q'), self.C('SRCH_ROW','type'), self.C('SRCH_ROW','id')
        hint = '/*+ INDEX_ASC(t ('+q+' '+ty+' '+ix+')) */'
        n = SETTINGS['UPDATE_BATCH_ROWS']
        if not self.exists('SRCH_ROW', 'q', old): log('MOVE_DONE', table=label, remaining=0); return
        total = self.count('SRCH_ROW', 'q', old)
        log('MOVE_START', table=label, rows=total, method='KEYED_BY_TYPE_ID', batch_rows=n)
        started = time.monotonic(); done = 0; last_log = started
        for kind in kinds:
            lower = None
            base = q+'='+literal(old)+' AND '+ty+'='+literal(kind)
            while True:
                after = (' AND '+ix+'>'+literal(lower)) if lower is not None else ''
                rows = self.db.query('SELECT ID FROM (SELECT ID, ROWNUM RN FROM (SELECT '+hint+' '+ix+' AS ID FROM '+T+' t WHERE '+
                                     base+after+' ORDER BY '+ix+') WHERE ROWNUM<='+str(n)+') WHERE RN='+str(n), limit=1)
                upper = rows[0]['ID'] if rows else None
                until = (' AND '+ix+'<='+literal(upper)) if upper is not None else ''
                self.db.block('BEGIN UPDATE '+hint+' '+T+' t SET '+q+'='+literal(new)+' WHERE '+base+after+until+'; COMMIT; END;')
                done += n if upper is not None else 0
                now = time.monotonic()
                if now - last_log >= 60 or upper is None:
                    if upper is None: done = total - self.count('SRCH_ROW', 'q', old)
                    rate = done/max(now-started, 1)
                    log('MOVE_PROGRESS', table=label, kind=kind, done=done, total=total, seconds=round(now-started),
                        rows_per_second=round(rate), eta_minutes=round((total-done)/rate/60) if rate else None)
                    last_log = now
                if upper is None: break
                lower = upper
        if self.exists('SRCH_ROW', 'q', old):
            log('MOVE_SWEEP', table=label, message='종류 목록 밖에 남은 행을 기존 방식으로 마저 바꿉니다.')
            self.move('SRCH_ROW', 'q', old, new, label)
        log('MOVE_DONE', table=label, rows=total, seconds=round(time.monotonic()-started))

    def swap(self, key, where, sets, label):
        assign = ','.join(self.C(key,c)+'='+v for c, v in sets)
        cond = ' AND '.join(self.C(key,c)+'='+literal(v) for c, v in where)
        self.db.block('DECLARE n NUMBER; BEGIN UPDATE '+self.T(key)+' SET '+assign+' WHERE '+cond+'; n := SQL%ROWCOUNT; '
                      "IF n>1 THEN ROLLBACK; RAISE_APPLICATION_ERROR(-20071,'POINTER_NOT_UNIQUE'); END IF; COMMIT; END;")
        log('POINTER', table=label)

    # ---------- 확인 ----------
    def verify(self, plan, applied):
        q, s = (plan['q1'], plan['s1']) if applied else (plan['q0'], plan['s0'])
        vec = plan['vector']
        ch = self.channel()
        if ch['q'] != q: raise Stop('VERIFY_CHANNEL:'+ch['q'])
        qm = self.body('SRCH_POST', q)
        if qm is None or qm.get('status') != 'COMPLETE' or qm.get('source_release_id') != s: raise Stop('VERIFY_QUERY_RELEASE')
        sm = self.body('SRC_POST', s)
        if sm is None or sm.get('status') != 'COMPLETE': raise Stop('VERIFY_SOURCE_RELEASE')
        if applied:
            sel = qm.get('search_selection') or {}
            # 서빙 시작 검사(oracle_query_store.Selection.require_latest)와 같은 조건
            if sel.get('schema_version') != SEL_V2 or (qm.get('selection_proof') or {}).get('fingerprint') != digest(sel):
                raise Stop('VERIFY_SELECTION')
            # 원문 게시본 검사(oracle_query.Snapshot.open)와 같은 조건
            if sm.get('search_selection') != sel or sel.get('manifest_sha256') != sm['dataset_version'] \
                    or sel.get('store_sha256') != sm['source_manifest']['store_sha256']:
                raise Stop('VERIFY_SOURCE_SELECTION_BINDING')
        if self.count('SRCH_ROW', 'q', q) != plan['search_rows']: raise Stop('VERIFY_SEARCH_ROWS')
        if self.exists('SRCH_ROW', 'q', plan['q0'] if applied else plan['q1']): raise Stop('VERIFY_SEARCH_ROWS_LEFT_BEHIND')
        if vec:
            v = vec['v1'] if applied else vec['v0']
            if self.vector_head(q) != v: raise Stop('VERIFY_VECTOR_HEAD')
            env = self.body('VCTR_POST', v); m = env['manifest']
            if m.get('query_id') != q or m.get('source_release_id') != s or env['completion'].get('status') != 'READY':
                raise Stop('VERIFY_VECTOR_BINDING')
            if self.count('VCTR_ITEM', 'v', v) != vec['count']: raise Stop('VERIFY_VECTOR_ROWS')
        log('VERIFIED', state='APPLIED' if applied else 'ORIGINAL', channel=ch['name'], query_release=q)

    # ---------- 실행 ----------
    def run(self):
        ch = self.channel()
        log('START', mode=self.mode, version=VERSION, channel=ch['name'], current_release=ch['q'],
            connection=SETTINGS['ORACLE_CONNECTION'], owner=SETTINGS['GOLD_OWNER'])
        current = self.body('SRCH_POST', ch['q'])
        if current is None: raise Stop('CHANNEL_RELEASE_MISSING')
        switched = (current.get('search_selection') or {}).get('schema_version') == SEL_V2
        if self.mode == 'ROLLBACK':
            if switched: plan = self.derive_applied(ch['q'])
            else:
                sel, sel_sha = self.selection(); plan = self.plan(ch['q'], sel, sel_sha)[0]
            vec = plan['vector']
            log('PLAN', **{k: plan[k] for k in ('q0', 'q1')})
            self.privileges()
            if ch['q'] == plan['q1']:
                self.swap('SRCH_CHNL', [('name', ch['name']), ('q', plan['q1'])],
                          [('q', literal(plan['q0'])), ('no', self.C('SRCH_CHNL','no')+'+1')], '채널')
            if vec:
                self.swap('VCTR_HEAD', [('q', plan['q1']), ('v', vec['v1'])],
                          [('q', literal(plan['q0'])), ('v', literal(vec['v0'])), ('no', self.C('VCTR_HEAD','no')+'+1')], '벡터 연결')
            self.move_search_rows(plan['q1'], plan['q0'], list(plan['kinds']), '검색 행')
            if vec: self.move('VCTR_ITEM', 'v', vec['v1'], vec['v0'], '벡터 행')
            self.verify(plan, applied=False)
            return self.finish('ROLLED_BACK', plan)
        sel, sel_sha = self.selection()
        if switched:
            plan = self.derive_applied(ch['q'])
            if plan['selection_fingerprint'] != digest(sel): raise Stop('SWITCHED_BY_ANOTHER_SELECTION')
            self.verify(plan, applied=True)
            return self.finish('ALREADY_APPLIED', plan)
        plan, s1, q1, env1 = self.plan(ch['q'], sel, sel_sha)
        log('PLAN', **{k: plan[k] for k in ('documents', 'excluded', 'searchable', 'search_rows', 'q0', 'q1')},
            vector_rows=(plan['vector'] or {}).get('count'))
        self.privileges()
        if self.mode == 'CHECK':
            log('CHECK_OK', message='확인만 했고 아무것도 바꾸지 않았습니다. 프로젝트 변수 GOLD_FIX_MODE=APPLY 로 다시 실행하세요.')
            return self.finish('CHECK_OK', plan)
        vec = plan['vector']
        self.insert('SRC_POST', plan['s1'], s1)
        self.insert('SRCH_POST', plan['q1'], q1)
        if vec: self.insert('VCTR_POST', vec['v1'], env1)
        if vec: self.move('VCTR_ITEM', 'v', vec['v0'], vec['v1'], '벡터 행')
        self.move_search_rows(plan['q0'], plan['q1'], list(plan['kinds']), '검색 행')
        if vec:
            self.swap('VCTR_HEAD', [('q', plan['q0']), ('v', vec['v0'])],
                      [('q', literal(plan['q1'])), ('v', literal(vec['v1'])), ('no', self.C('VCTR_HEAD','no')+'+1')], '벡터 연결')
        self.swap('SRCH_CHNL', [('name', ch['name']), ('q', plan['q0'])],
                  [('q', literal(plan['q1'])), ('no', self.C('SRCH_CHNL','no')+'+1')], '채널')
        self.verify(plan, applied=True)
        return self.finish('APPLIED', plan)

    def finish(self, status, plan):
        result = {'status': status, 'version': VERSION, 'mode': self.mode, 'run_id': self.run_id,
                  'channel': self.channel(), 'plan': plan}
        log('RESULT', result=result)
        log(status, message={'CHECK_OK': '확인 통과(변경 없음)', 'APPLIED': '적용 완료. 코드서빙을 재기동하세요.',
                             'ALREADY_APPLIED': '이미 적용되어 있습니다.', 'ROLLED_BACK': '원래 상태로 되돌렸습니다.'}[status])
        return result


def main():
    fix = None
    try:
        fix = Fix()
        return fix.run()
    except Exception as exc:
        log('FAILED', error=type(exc).__name__+': '+str(exc)[:2000])
        raise


RESULT = main()
