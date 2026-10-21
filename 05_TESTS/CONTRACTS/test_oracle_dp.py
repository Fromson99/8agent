"""Real SQLite + simulated ORDS: no internal network, Oracle engine or model calls."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime import oracle_dp_io as io
from lawrag.pipeline import oracle_migration as migration


def fixture_source(root, n=45):
    root.mkdir(parents=True)
    path = root/'store.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT,PRIMARY KEY(document_id,unit_id));
        CREATE TABLE block_payload(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,json_text_elided INTEGER,PRIMARY KEY(document_id,block_id));
        CREATE VIEW source_block AS SELECT document_id,block_id,unit_id,text,source_artifact_sha256,
            CASE WHEN json_text_elided THEN json_set(json,'$.text',text) ELSE json END AS json FROM block_payload;
        ''')
        db.execute('INSERT INTO document VALUES(?,?,?,?)', ("doc'한글", '', 'a'*64, '{ "name": "원본 😀" }'))
        db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', ("doc'한글", 'unit-1', None, '{"parent_id":null}'))
        for i in range(n):
            text = "한글'😀\r\n" * (700 if i == 0 else 3)
            db.execute('INSERT INTO block_payload VALUES(?,?,?,?,?,?,?)',
                       ("doc'한글", str(i), 'unit-1', text, 'a'*64, '{ "x": "  원문 공백  " }', 1))
    manifest = {'schema_version':'term-source-generation-v2','generation_id':'mock-source',
                'store_sha256':io.file_sha(path),'counts':{'document':1,'source_unit':1,'source_block':n},
                'data_status':'TEST_ONLY','export_allowed':False}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False))
    return path


def substring(value, pos, count):
    if value is None: return None
    raw = value.encode('utf-16-le')
    raw = raw[(pos-1)*2:(pos-1+count)*2]
    if raw and 0xD800 <= int.from_bytes(raw[-2:],'little') <= 0xDBFF:
        raw = raw[:-2]
    return raw.decode('utf-16-le') or None


class Oracle:
    SQL_PATH = '/sql'
    def __init__(self):
        self.data = {k:{} for k in io.TABLES}
        self.calls, self.writes, self.mode = [], 0, None

    def request(self, method, path, json):
        assert (method,path)==('POST','/sql')
        self.calls.append(json)
        sql = json['statementText']; binds={b['name']:b['value'] for b in json.get('binds',[])}
        if sql.startswith('DECLARE'):
            self.writes += 1
            assert sql.endswith('EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
            assert sql.count('COMMIT;')==1 and 'DELETE ' not in sql and 'UPDATE ' not in sql
            if self.mode=='denied':return {'items':[{'errorCode':1031}]}
            if self.mode=='before_timeout':self.mode=None;raise TimeoutError('simulated')
            candidate=copy.deepcopy(self.data)
            for table,cols,vals in re.findall(r'INSERT INTO SIDDA\.(\w+) \(([^)]+)\) VALUES \((.*?)\);',sql):
                kind=next(k for k,t in io.TABLES.items() if t==table)
                expressions=vals.split(',')
                def value(x):
                    return binds[x[1:]] if x.startswith(':') else '' if x=='EMPTY_CLOB()' else None if x=='NULL' else 1/0
                row=dict(zip(cols.split(','),map(value,expressions)))
                io.validate_row(kind,row)
                key=tuple(row[c] for c in io.KEYS[kind])
                if key in candidate[kind] and candidate[kind][key]!=row:
                    return {'items':[{'errorCode':20001}]}
                candidate[kind][key]=row
            self.data=candidate
            if self.mode=='after_timeout':self.mode=None;raise TimeoutError('simulated committed response loss')
            return {'items':[{'result':0}]}
        if 'ALL_TAB_COLUMNS' in sql:
            rows=[]
            for kind,cols in io.COLUMNS.items():
                for c in cols:
                    typ='CLOB' if c in io.CLOBS else 'NUMBER' if c=='JSON_TEXT_ELIDED' else 'VARCHAR2'
                    rows.append({'TABLE_NAME':io.TABLES[kind],'COLUMN_NAME':c,'DATA_TYPE':typ,
                        'DATA_LENGTH':64 if c in ('DATASET_VERSION','SOURCE_ARTIFACT_SHA256') else 512,
                        'CHAR_USED':'B' if typ=='VARCHAR2' else None,'NULLABLE':'N' if c in io.KEYS[kind] else 'Y'})
        elif 'ALL_CONSTRAINTS' in sql:
            rows=[{'TABLE_NAME':io.TABLES[k],'COLUMN_NAME':c,'POSITION':i,'STATUS':'ENABLED','VALIDATED':'VALIDATED'}
                  for k,cs in io.KEYS.items() for i,c in enumerate(cs,1)]
        else:
            table=re.search(r'FROM SIDDA\.(\w+)',sql).group(1)
            kind=next(k for k,t in io.TABLES.items() if t==table)
            rows=list(self.data[kind].values())
            if 'COUNT(*) AS N' in sql:
                rows=[{'N':sum(r['DATASET_VERSION']==binds['v'] for r in rows)}]
            elif ' AS PIECE' in sql:
                selected=[r for r in rows if all(r[c]==binds['k'+str(i)] for i,c in enumerate(io.KEYS[kind]))]
                col=re.search(r'SUBSTR\((\w+),',sql).group(1)
                rows=[{'PIECE':substring(r[col],binds['pos'],io.LOB_UNITS),'TOTAL':io.units(r[col])} for r in selected]
            else:
                indices={int(n.split('_')[0][1:]) for n in binds if n.startswith('k')}
                selected=[r for r in rows if any(all(r[c]==binds[f'k{i}_{j}'] for j,c in enumerate(io.KEYS[kind])) for i in indices)]
                rows=[]
                for r in selected:
                    view=copy.deepcopy(r)
                    for c in io.CLOBS.intersection(io.COLUMNS[kind]):
                        view[c+'__TOTAL']=None if r[c] is None else io.units(r[c])
                        view[c]=substring(r[c],1,io.LOB_UNITS)
                    rows.append(view)
                if self.mode=='corrupt_read' and rows:rows[0]['DOCUMENT_ID']='wrong'
        return {'items':[{'resultSet':{'items':rows,'hasMore':False,'offset':0}}]}


def run(backend,source,root,**kwargs):
    return migration.transfer(backend,source,target_binding='mock-target',directory=root/'jobs',**kwargs)


def test_full_transfer_unicode_clob_and_idempotence(tmp_path):
    source=fixture_source(tmp_path/'source'); backend=Oracle(); before=source.read_bytes()
    checked=run(backend,source,tmp_path,action='check')
    assert checked['status']=='CHECKED_NO_WRITES' and backend.writes==0
    result=run(backend,source,tmp_path,action='run')
    assert result['status']=='SOURCE_COMPLETE' and result['counts']=={'document':1,'source_unit':1,'block_payload':45}
    writes=backend.writes
    verified=run(backend,source,tmp_path,action='verify')
    assert verified['status']=='VERIFIED' and backend.writes==writes
    assert source.read_bytes()==before
    assert any(':pos' in c['statementText'] for c in backend.calls)
    state=json.loads(Path(result['receipt']).read_text())
    for k,rows in backend.data.items():
        assert len(rows)==state['counts'][k]
    text=next(r['TEXT'] for r in backend.data['block_payload'].values() if r['BLOCK_ID']=='0')
    assert text=="한글'😀\r\n"*700
    log=''.join(p.read_text() for p in (tmp_path/'jobs').rglob('*.jsonl'))
    assert '원문 공백' not in log and 'mock-secret' not in log


@pytest.mark.parametrize('mode',['before_timeout','after_timeout','denied'])
def test_explicit_resume_after_uncertain_or_denied_write(tmp_path,mode):
    source=fixture_source(tmp_path/'source',n=2);backend=Oracle();backend.mode=mode
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'):
        run(backend,source,tmp_path,action='run')
    first=backend.writes
    backend.mode=None
    result=run(backend,source,tmp_path,action='run')
    assert result['status']=='SOURCE_COMPLETE'
    assert len(backend.data['document'])==1
    assert backend.writes==first+(2 if mode=='after_timeout' else 3)
    journal=next((tmp_path/'jobs').rglob('calls.jsonl')).read_text()
    assert 'WRITE_UNCONFIRMED' in journal and 'MIGRATION_FAILED' in journal


def test_pause_resume_uses_saved_cursor_and_cumulative_calls(tmp_path):
    source=fixture_source(tmp_path/'source');backend=Oracle()
    first=run(backend,source,tmp_path,action='run',max_batches=1)
    assert first['status']=='PAUSED' and len(backend.data['document'])==1
    second=run(backend,source,tmp_path,action='run')
    state=json.loads(Path(second['receipt']).read_text())
    assert state['attempts']==2 and state['calls']>first['calls']
    assert second['status']=='SOURCE_COMPLETE'


def test_existing_conflict_and_extra_rows_are_not_overwritten(tmp_path):
    source=fixture_source(tmp_path/'source',n=2);backend=Oracle()
    run(backend,source,tmp_path,action='run',max_batches=1)
    row=next(iter(backend.data['document'].values()));row['NAME']='different'
    with pytest.raises(io.DPError,match='ROW_CONFLICT'):
        run(backend,source,tmp_path,action='verify')
    assert row['NAME']=='different'
    extra=copy.deepcopy(row);extra['DOCUMENT_ID']='extra'
    backend.data['document'][tuple(extra[c] for c in io.KEYS['document'])]=extra
    with pytest.raises(io.DPError,match='TARGET_COUNT'):
        run(backend,source,tmp_path,action='run')


def test_bad_source_hash_and_expired_budget_write_nothing(tmp_path):
    source=fixture_source(tmp_path/'source');backend=Oracle()
    result=run(backend,source,tmp_path,action='run',seconds=0)
    assert result['status']=='PAUSED' and backend.writes==0
    p=source.parent/'manifest.json';value=json.loads(p.read_text());value['store_sha256']='f'*64;p.write_text(json.dumps(value))
    with pytest.raises(io.DPError,match='SOURCE_HASH'):
        run(backend,source,tmp_path,action='run')
    assert backend.writes==0


@pytest.mark.parametrize('response',[{}, {'items':[]}, {'items':[{'resultSet':{'items':[],'hasMore':True,'offset':0}}]},
    {'items':[{'resultSet':{'items':[],'hasMore':False,'offset':4}}]}, {'items':[{'errorCode':942}]}])
def test_incomplete_or_error_response_never_becomes_success(tmp_path,response):
    class Broken:
        SQL_PATH='/sql'
        def request(self,*a,**kw):return response
    sql=io.SQL(Broken(),journal=tmp_path/'calls',binding='test')
    with pytest.raises(io.DPError):sql.query('SELECT 1 FROM DUAL')


def test_bind_values_stay_out_of_sql_and_empty_clob_is_distinct(tmp_path):
    source=fixture_source(tmp_path/'source',n=1)
    with migration.source_open(source) as db: rows=migration.source_batch(db,'document','d'*64)
    statement,binds=io.insert_statement('document',rows)
    assert "doc'한글" not in statement and 'EMPTY_CLOB()' in statement
    assert 'DBMS_LOB.GETLENGTH(NAME)=0' in statement
    assert any(b[2]=='CLOB' for b in binds)
    assert 'COMMIT;' in statement and 'ROLLBACK;' in statement


def test_exact_standalone_notebook_entry(tmp_path,monkeypatch):
    from types import SimpleNamespace
    source=fixture_source(tmp_path/'source',n=2);backend=Oracle()
    original=Path.resolve
    def resolve(path,*args,**kwargs):
        return source if str(path)==migration.SOURCE else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',resolve)
    desk=SimpleNamespace(require_connection=lambda:SimpleNamespace(client=backend), recovery_required=False,
                         binding=lambda:'mock-notebook',settings={'log_dir':str(tmp_path/'logs')})
    cell=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_dp_20261016_r1/LEGAL_ORACLE_FULL_TRANSFER_20261016_R1_CELL.txt'
    namespace={'desk':desk}
    exec(compile(cell.read_text(),str(cell),'exec'),namespace)
    assert namespace['LEGAL_FULL_TRANSFER_RESULT']['status']=='SOURCE_COMPLETE'
    assert len(backend.data['block_payload'])==2
