import copy
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
sys.path.insert(0,str(PACKAGE))
import gold_io
spec=importlib.util.spec_from_file_location('g19_runner',PACKAGE/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


@pytest.fixture
def contract():
    return gold_io.Contract(PACKAGE/'contract.json')


def doc(**changes):
    return dict({'MNFST_HASH_VALU':'a'*64,'DOC_ID':'doc1','DOC_NAME':'한글 법령',
                 'DOC_HASH_VALU':'b'*64,'DOC_ADDN_IFMN_CTNT':'{"원문":"한글"}'},**changes)


def test_exact_registration_and_explicit_placement(contract):
    original=json.loads((PACKAGE/'registration_r18.json').read_text())
    assert len(contract.tables)==17
    for key,expected in original['tables'].items():
        actual=contract.tables[key]
        assert actual['columns']==expected['columns']
        assert actual['primary_key']==expected['primary_key']
        assert actual['indexes']==expected['indexes']
        assert actual['owner']==('SIDDA' if key.startswith('ONTL_') else 'SIDDS')
        assert actual['name'].startswith('LGL_G19_')
    assert sum(len(t['columns']) for t in contract.tables.values() if t['group']=='GOLD_R19')==60


def test_common_agent_schema_shape_is_preserved_in_separate_suffix_table(contract):
    assert contract.table('EXEC_ST')=='SIDDA.LGL_EXEC_ST_A_1'
    assert len(contract.tables['EXEC_ST']['columns'])==5
    assert sum(len(contract.tables[k]['columns']) for k in ['AGT_RUN','AGT_REC','AGT_BODY'])==21
    assert sum(len(contract.indexes(k)) for k in ['AGT_RUN','AGT_REC','AGT_BODY'])==7


@pytest.mark.parametrize('change',[{'DOC_ID':'가'*17},{'DOC_ID':''},{'DOC_ID':None},
                                   {'DOC_NAME':'가'*751},{'DOC_ADDN_IFMN_CTNT':123}])
def test_length_and_null_mismatch_stops_without_truncation(contract,change):
    value=doc(**change);before=copy.deepcopy(value)
    with pytest.raises(gold_io.Stop):contract.validate('DOC_VER',[value])
    assert value==before


def test_duplicate_key_conflict_is_not_overwritten(contract):
    with pytest.raises(gold_io.Stop,match='BATCH_DUPLICATE_CONFLICT'):
        contract.validate('DOC_VER',[doc(),doc(DOC_NAME='다름')])
    assert contract.validate('DOC_VER',[doc(),doc()])==[doc()]


def test_empty_clob_and_null_are_separate(contract):
    sql,binds=contract.batch('DOC_VER',[doc(DOC_ADDN_IFMN_CTNT='')])
    payload=json.loads(binds[0][1])[0]
    assert payload['c4']=='' and payload['c4e']==1
    assert 'EMPTY_CLOB()' in sql and 'DBMS_LOB.COMPARE' in sql
    _,null_binds=contract.batch('DOC_VER',[doc(DOC_ADDN_IFMN_CTNT=None)])
    assert json.loads(null_binds[0][1])[0]['c4e']==0


def test_verify_never_inserts_or_commits(contract):
    sql,_=contract.batch('DOC_VER',[doc()],verify_only=True)
    assert 'INSERT INTO' not in sql and 'COMMIT;' not in sql
    assert 'ROLLBACK;' in sql and 'GOLD_ROW_CONFLICT_OR_MISSING' in sql


def test_insert_sql_has_exact_readback_and_conflict_rollback(contract):
    sql,_=contract.batch('DOC_VER',[doc()])
    assert 'WHERE NOT EXISTS' in sql and 'IF n<>:expected' in sql
    assert sql.index('DBMS_LOB.COMPARE')<sql.index('COMMIT;')
    assert 'EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE;' in sql


def test_generated_nonvector_ddl_parse(contract):
    import sqlglot
    from sqlglot import exp
    for key in contract.tables:
        statement=contract.ddl(key)
        if key=='VCTR_ITEM':
            # SQLGlot's Oracle parser does not implement Oracle VECTOR(*,FLOAT32).
            # Keep the exact registered type; native capability is tested in the field gate.
            assert 'EMBD_VCTR VECTOR(*,FLOAT32) NOT NULL' in statement
            continue
        assert isinstance(sqlglot.parse_one(statement,read='oracle'),exp.Create)
    # SQLGlot also omits JSON_TABLE column-level ERROR ON ERROR support.
    # Unmodified generated SQL is checked by the separate native Oracle contract test.


class ProbeDB:
    def __init__(self,leftover=False):self.blocks=[];self.queries=[];self.leftover=leftover
    def block(self,sql,binds=(),rollback=False):
        self.blocks.append((sql,rollback));return 0.01
    def query(self,sql,limit=200):
        self.queries.append(sql);return [{'N':1 if self.leftover else 0}]


def test_probe_always_rolls_back_and_rechecks_absence(contract):
    db=ProbeDB();contract.probe(db,'DOC_VER')
    sql,rollback=db.blocks[0]
    assert rollback and 'COMMIT' not in sql and 'ROLLBACK; EXCEPTION' in sql
    assert 'PROBE_KEY_EXISTS' in sql and 'SELECT COUNT(*)' in db.queries[-1]


def test_probe_leftover_blocks_gate(contract):
    with pytest.raises(gold_io.Stop,match='PROBE_ROLLBACK_UNCONFIRMED'):
        contract.probe(ProbeDB(leftover=True),'DOC_VER')


def test_vector_probe_checks_float32_and_flexible_dimensions(contract):
    db=ProbeDB();contract.probe(db,'VCTR_ITEM')
    assert len(db.blocks)==2
    assert all("VECTOR_DIMENSION_FORMAT(EMBD_VCTR)='FLOAT32'" in x[0] for x in db.blocks)
    assert 'VECTOR_DIMENSION_COUNT(EMBD_VCTR)=2' in db.blocks[0][0]
    assert 'VECTOR_DIMENSION_COUNT(EMBD_VCTR)=3' in db.blocks[1][0]


class Quiet:
    phase='TEST'
    def set(self,*a,**k):pass
    def emit(self,*a,**k):pass


class BatchDB:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def block(self,sql,binds=(),rollback=False):
        self.calls.append((sql,rollback))
        if self.fail:raise RuntimeError('ORA-12801 ORA-01653')
        return 0.1


def test_commit_unknown_retains_pending_then_readonly_reconciles(contract,tmp_path):
    db=BatchDB(fail=True)
    job=runner.Job(db,contract,tmp_path,{'x':1},Quiet())
    nxt={'rows':1}
    with pytest.raises(RuntimeError):job.batch('DOC_VER',[doc()],nxt,'source','document')
    saved=runner.read(tmp_path/'state.json')
    assert saved['status']=='WRITE_UNCONFIRMED' and saved['pending']['sha256']==gold_io.digest([doc()])
    assert 'document' not in saved['source']
    db2=BatchDB()
    job2=runner.Job(db2,contract,tmp_path,{'x':1},Quiet())
    job2.batch('DOC_VER',[doc()],nxt,'source','document')
    assert len(db2.calls)==1 and 'INSERT INTO' not in db2.calls[0][0]
    assert job2.state['source']['document']==nxt and job2.state['pending'] is None


def test_missing_pending_batch_does_not_blindly_retry(contract,tmp_path):
    db=BatchDB(fail=True);job=runner.Job(db,contract,tmp_path,{},Quiet())
    with pytest.raises(RuntimeError):job.batch('DOC_VER',[doc()],{'rows':1},'source','document')
    class Missing(BatchDB):
        def block(self,*args,**kwargs):
            self.calls.append(args);raise RuntimeError('ORA-20042: missing or conflict')
    missing=Missing();job2=runner.Job(missing,contract,tmp_path,{},Quiet())
    with pytest.raises(gold_io.Stop,match='PENDING_WRITE_REQUIRES_RECONCILIATION'):
        job2.batch('DOC_VER',[doc()],{'rows':1},'source','document')
    assert len(missing.calls)==1 and 'INSERT INTO' not in missing.calls[0][0]


def test_binding_change_rejects_old_progress(contract,tmp_path):
    runner.Job(BatchDB(),contract,tmp_path,{'objects':[1]},Quiet())
    with pytest.raises(gold_io.Stop,match='JOB_BINDING_CHANGED'):
        runner.Job(BatchDB(),contract,tmp_path,{'objects':[2]},Quiet())


def test_flag_translation_preserves_logical_values():
    fields=runner.SOURCE_MAP['block_payload'][1].split()
    row={k:None for k in fields}
    for original,expected in [(0,'N'),(1,'Y'),(None,None)]:
        row['JSON_TEXT_ELIDED']=original
        assert runner.source_row('block_payload',row)[1]['ADD_INFO_TEXT_OMIT_YN']==expected
    row['JSON_TEXT_ELIDED']=0.0
    with pytest.raises(gold_io.Stop,match='SOURCE_FLAG'):runner.source_row('block_payload',row)


def test_run_entrypoint_stops_before_inputs_or_load_when_probe_fails(monkeypatch,tmp_path):
    old=tmp_path/'oracle-import-r2';old.mkdir()
    calls=[]
    class FakeContract:
        sha256='a'*64
        tables={'A':{},'B':{}}
        def __init__(self,path):pass
        def create(self,db,emit):calls.append('create')
        def table(self,key):return key
        def probe(self,db,key):
            calls.append('probe:'+key)
            if key=='B':raise RuntimeError('ORA-01653')
            return 0
    class FakeDB:
        def __init__(self,executor):pass
        def query(self,*a,**k):return [{'LOGIN_USER':'PIDD2APP','DB_NAME':'TEST','SERVICE_NAME':'TEST'}]
    monkeypatch.setattr(runner,'verify_code',lambda:'pinned')
    monkeypatch.setattr(runner,'Contract',FakeContract)
    monkeypatch.setattr(runner,'Database',FakeDB)
    monkeypatch.setattr(runner,'inputs',lambda *args:calls.append('INPUTS_MUST_NOT_RUN'))
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **kwargs:object()))
    with pytest.raises(RuntimeError):runner.run('start',old)
    assert calls==['create','probe:A','probe:B']


def test_error_codes_preserve_underlying_capacity_error():
    original=RuntimeError('ORA-12801 ORA-06512 ORA-01653')
    wrapped=gold_io.Stop('safe message');wrapped.__cause__=original
    assert gold_io.error_codes(wrapped)==['ORA-12801','ORA-06512','ORA-01653']


def test_reused_gold_definitions_match_the_frozen_importer():
    import ast
    root=HERE.parents[2]
    old=root/'02_BACKEND/lawrag/research/candidates/adr_1208/gold-b03/revisions/rev-021/snapshot/08_DEPLOYMENT/LOCAL/gold_connection_r12'
    copied=ast.parse((PACKAGE/'legacy_gold_mapping.py').read_text())
    for filename,names in [('gold_lab.py',{'mapped_source','mapped_query'}),('gold_connection.py',{'READ_COLUMNS'})]:
        tree=ast.parse((old/filename).read_text())
        def selected(nodes):
            return [ast.dump(n,include_attributes=False) for n in nodes if
                    isinstance(n,ast.FunctionDef) and n.name in names or isinstance(n,ast.Assign) and
                    any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
        assert selected(tree.body)==selected(copied.body)


def test_hash_encoding_matches_existing_source_query_release_contract():
    from semantic_runtime.oracle_dp_io import canonical,digest
    value={'문서':'한글 법령','null':None,'text':'café 😀'}
    assert gold_io.canonical(value)==canonical(value)
    assert gold_io.digest(value)==digest(value)


def test_real_sqlite_query_projection_resumes_completed_asset_and_rejects_changed_input(contract,tmp_path,monkeypatch):
    import sqlite3
    from lawrag.pipeline import oracle_query_publish as pub
    root=tmp_path/'generation';root.mkdir();path=root/'sample.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sample(id TEXT PRIMARY KEY,document_id TEXT,value TEXT)')
        db.executemany('INSERT INTO sample VALUES(?,?,?)',[('one','doc','한글'),('two','doc',None)])
    source={'source_manifest':{}}
    expected=list(pub.projected_rows(path,'sample.sqlite',source))
    assert len(expected)>=2
    class ProjectDB(BatchDB):
        def query(self,*a,**k):return [{'N':len(expected)}]
    db=ProjectDB();jobdir=tmp_path/'job';jobdir.mkdir()
    job=runner.Job(db,contract,jobdir,{},Quiet())
    query={'tables':{'test':{'rows':len(expected)}}}
    paths={'sample.sqlite':runner.file_hash(path)}
    runner.load_query(job,root,{},source,query,paths)
    assert job.state['query']['sample.sqlite']=={'rows':len(expected),'complete':True}
    assert len(db.calls)==1
    def must_not_project(*args):raise AssertionError('completed asset was replayed')
    monkeypatch.setattr(pub,'projected_rows',must_not_project)
    runner.load_query(job,root,{},source,query,paths)
    assert len(db.calls)==1
    with sqlite3.connect(path) as source_db:source_db.execute("INSERT INTO sample VALUES('three','doc','changed')")
    with pytest.raises(gold_io.Stop,match='QUERY_INPUT_HASH'):
        runner.load_query(job,root,{},source,query,paths)
