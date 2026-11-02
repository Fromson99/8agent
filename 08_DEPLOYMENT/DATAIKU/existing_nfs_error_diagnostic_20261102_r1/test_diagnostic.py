from pathlib import Path
import ast,hashlib,importlib.util,json,sys,zipfile
import pytest
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('r11_error_diagnostic',HERE/'error_diagnostic.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

def test_original_r11_suppressed_context_and_exact_cursor(tmp_path):
    root=tmp_path/'r11'
    with zipfile.ZipFile(HERE.with_name('existing_nfs_set_bulk_20261031_r11')/'DATAIKU_EXISTING_NFS_CLIENT_20261031_R11.zip') as z:z.extractall(root)
    sys.path[:0]=[str(root),str(root/'client'),str(root/'client/02_BACKEND')]
    from lawrag.pipeline.oracle_query_dataiku import DataikuClient
    from semantic_runtime.oracle_dp_io import SQL,DPError
    class Executor:
        calls=0
        def query_to_df(self,*args,**kwargs):
            self.calls+=1
            raise RuntimeError('ORA-12801: parallel error\nORA-01652: unable to extend temp segment\nORA-06512: line7\nSECRET_PASSWORD quoted_source_text')
    ex=Executor();db=SQL(DataikuClient(ex,'test','test'),journal=tmp_path/'journal.jsonl',binding='synthetic')
    job=tmp_path/'job';job.mkdir()
    (job/'full-state.json').write_text(json.dumps({'status':'FAILED','deferred':{'loaded_query_batches':12345,'load_finished':False},'deadline':7200}))
    (job/'progress-latest.json').write_text(json.dumps({'phase':'FTS_POSTINGS_SORT','write_rows_this_run':50000,'write_requests_this_run':10}))
    (job/'deferred_load.jsonl').write_text(json.dumps({'status':'WRITE_UNCONFIRMED','call':123,'error':'JDBC_FAILURE: ORA-12801'})+'\n')
    env={'db':db};exec(compile('def invoke(directory):\n db.request("BEGIN NULL; END;",write=True)\n','existing_client.py','exec'),env)
    try:env['invoke'](job)
    except DPError as e:exc=e
    else:pytest.fail('failure missing')
    assert str(exc)=='WRITE_UNCONFIRMED: JDBC_FAILURE: ORA-12801'
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    lines=d.report(exc,now=3600);s='\n'.join(lines)
    assert len(lines)<=24 and 'ORA-01652' in s and 'ORA-12801' in s and 'SECRET_PASSWORD' not in s and 'quoted_source_text' not in s
    assert '12345 (1~20행 단위, 행수 아님)' in s and '50000행 / 10요청' in s and '기존 기한 잔여: 1.0시간' in s
    assert ex.calls==1 and all(p.read_bytes()==raw for p,raw in before.items())

def test_missing_exception_is_not_zero_progress():
    s='\n'.join(d.report(None))
    assert '원래 예외 없음' in s and '적재가 0행이라는 뜻은 아님' in s and '원인 확정 불가' in s

def test_cycle_and_large_errors_are_bounded():
    a=RuntimeError('ORA-12801');b=ValueError('ORA-01653');a.__context__=b;b.__context__=a
    assert len(d.error_chain(a))==2
    codes,cut=d.error_codes(RuntimeError('ORA-12801\n'+'x'*(2*d.TEXT_LIMIT)+'\nORA-22922'))
    assert codes==['ORA-12801','ORA-22922'] and cut
    assert len(d.report(a))<=24

def test_ambiguous_path_is_not_guessed(tmp_path):
    a=tmp_path/'a';b=a/'oracle-import-r2';b.mkdir(parents=True)
    for p in (a,b):(p/'full-state.json').write_text('{}')
    assert d.find_job([],str(a)) is None

def test_bounded_file_and_incomplete_tail(tmp_path):
    p=tmp_path/'large.json';p.write_text('x'*20)
    assert d.read_json(p,10)==({},'SIZE_LIMIT')
    p=tmp_path/'tail.jsonl';p.write_text('{"call":5,"status":"WRITE_UNCONFIRMED"}\n{"broken')
    assert d.tail_event(p)['call']==5

def test_same_cell_source_and_no_executor_import():
    raw=(HERE/'error_diagnostic.py').read_bytes()
    assert raw==(HERE/'01_DIAGNOSE_R11_ERROR.txt').read_bytes()
    tree=ast.parse(raw,feature_version=(3,10))
    imports={a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
    assert not {'dataiku','requests','subprocess'} & imports
