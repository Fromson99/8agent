import ast
import importlib.util
import json
from pathlib import Path
import sys
import types
from types import SimpleNamespace
import zipfile

import pytest

HERE=Path(__file__).resolve().parent
R6=HERE.parent/'agent_layer_zip_20261105_r6'
spec=importlib.util.spec_from_file_location('r6_safe_ords_diagnosis',HERE/'diagnose.py')
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
with zipfile.ZipFile(R6/'GENOS_AGENT_ZIP_R6.zip') as archive:
    io_source=archive.read('02_BACKEND/semantic_runtime/oracle_dp_io.py')
    agent_source=archive.read('agent_ords.py').decode()
native={};exec(compile(io_source,'<exact R6 oracle_dp_io>','exec'),native)
function=next(n for n in ast.parse(agent_source).body if isinstance(n,ast.FunctionDef) and n.name=='preflight')


def setup(tmp_path,client):
    sql=native['SQL'](diag.Observer(client),journal=tmp_path/'agent-ords.jsonl',binding='fixture',max_calls=3,seconds=60)
    env={'connection':lambda *_a:sql,'stage':SimpleNamespace(TABLE='SIDDA.LGL_PIPE_RESULT_A')}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<exact R6 preflight>','exec'),env)
    agent=SimpleNamespace(connection=lambda *_a:sql)
    def invoke(*args):
        env['connection']=agent.connection
        return env['preflight'](*args)
    agent.preflight=invoke
    return sql,agent


class Client:
    SQL_PATH='/_/sql'
    def __init__(self):self.calls=[]
    def request(self,method,path,json):
        assert method=='POST' and path=='/_/sql'
        self.calls.append(json['statementText'])
        if json['statementText'].startswith('SELECT'):
            rows=[{'SESSION_USER':'ORDS_USER','CURRENT_SCHEMA':'ORDS_USER','DB_NAME':'DB_TEST'}] if 'SYS_CONTEXT' in json['statementText'] else []
            return {'items':[{'resultSet':{'items':rows,'hasMore':False,'offset':0}}]}
        assert 'IF FALSE THEN INSERT INTO SIDDA.LGL_PIPE_RESULT_A' in json['statementText']
        return {'items':[{'result':1}]}


def test_exact_R6_preflight_and_three_bounded_readonly_calls(tmp_path):
    client=Client();sql,agent=setup(tmp_path,client)
    results=diag.run_checks(sql,agent,{},diag.EXPECTED_PIN)
    assert [r['status'] for r in results]==['PASS']*3
    assert sql.calls==3 and len(client.calls)==3
    assert results[0]['identity']['SESSION_USER']=='ORDS_USER'
    assert all(not s.startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER','DROP')) for s in client.calls)


@pytest.mark.parametrize('failure_at',[1,2])
def test_oracle_object_or_privilege_failure_retains_only_ORA_codes(tmp_path,failure_at):
    class OracleFailure(Client):
        def request(self,*args,**kwargs):
            if len(self.calls)==failure_at:
                self.calls.append(kwargs['json']['statementText'])
                return {'items':[{'errorCode':6550,'errorDetails':'private-sql-secret ORA-06550 ORA-00942'}]}
            return super().request(*args,**kwargs)
    client=OracleFailure();sql,agent=setup(tmp_path,client)
    result=diag.run_checks(sql,agent,{},diag.EXPECTED_PIN)
    assert sql.calls==failure_at+1
    assert result[-1]['status']=='FAILED'
    assert result[-1]['response_metadata'][0]['oracle_codes']==['ORA-00942','ORA-06550']
    assert 'private-sql-secret' not in json.dumps(result)


def test_HTTP_auth_failure_stops_after_one_request_and_hides_secrets(tmp_path):
    class Unauthorized(Client):
        def request(self,*args,**kwargs):
            exc=RuntimeError('client-secret-DO-NOT-LOG and https://private-host/token')
            exc.response=SimpleNamespace(status_code=401)
            raise exc
    sql,agent=setup(tmp_path,Unauthorized())
    result=diag.run_checks(sql,agent,{},diag.EXPECTED_PIN)
    assert len(result)==1 and sql.calls==1
    assert result[0]['response_metadata'][0]['transport_error']['http_status']==[401]
    assert 'DO-NOT-LOG' not in json.dumps(result)
    assert 'private-host' not in json.dumps(result)
    assert 'DO-NOT-LOG' not in (tmp_path/'agent-ords.jsonl').read_text()


def test_unexpected_SDK_shape_is_reported_without_accepting_it(tmp_path):
    class WrongShape(Client):
        def request(self,*args,**kwargs):return {'data':{'secret':'must-not-emit'}}
    sql,agent=setup(tmp_path,WrongShape())
    result=diag.run_checks(sql,agent,{},diag.EXPECTED_PIN)
    assert result[0]['status']=='FAILED' and 'RESPONSE_SHAPE' in result[0]['tags']
    assert sql.calls==1 and 'must-not-emit' not in json.dumps(result)


@pytest.mark.parametrize('message,tag',[
    ('DP_CONFIG: hidden endpoint','DP_CONFIG'),('DP_CONNECT: missing SDK','DP_CONNECT'),
    ('AGENT_ORDS_CONFIGURATION_REQUIRED','AGENT_ORDS_CONFIGURATION_REQUIRED'),
    ('EXACT_R6_CODE_ROOT_NOT_FOUND','EXACT_R6_CODE_ROOT_NOT_FOUND'),
    ('ORDS_SQL_HTTP: 403','ORDS_SQL_HTTP'),('BUDGET_PAUSED: keep checkpoint','BUDGET_PAUSED')])
def test_safe_local_config_and_protocol_error_tags(message,tag):
    result=diag.safe_error(RuntimeError(message+' secret-value'))
    assert tag in result['tags'] and 'secret-value' not in json.dumps(result)


def test_negative_Oracle_error_number_is_kept_without_error_text():
    output=diag.safe_response({'items':[{'errorCode':-1031,'errorMessage':'private-source'}]})
    assert output['oracle_codes']==['ORA-01031'] and 'private-source' not in json.dumps(output)


def test_R6_root_mismatch_is_reported_before_network(monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['diagnose.py','--code-root',str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    from io import StringIO
    output=StringIO();monkeypatch.setattr('sys.stdout',output)
    diag.main()
    report=json.loads(output.getvalue().removeprefix('ORDS_DIAGNOSTIC '))
    assert report['status']=='SETUP_FAILED' and 'EXACT_R6_CODE_ROOT_NOT_FOUND' in report['error']['tags']
    assert 'sql_calls' not in report


def test_full_cli_exact_R6_root_three_calls_and_tamper_guard(monkeypatch,tmp_path,capsys):
    root=tmp_path/'r6';work=tmp_path/'work';work.mkdir()
    with zipfile.ZipFile(R6/'GENOS_AGENT_ZIP_R6.zip') as archive:archive.extractall(root)
    class FixtureClient(Client):
        def __init__(self,**options):
            super().__init__()
            assert options['auth_key']==('fixture-id','private-secret-value')
    genos=types.ModuleType('genos');genos.__path__=[]
    ords=types.ModuleType('genos.ords');ords.ORDSClient=FixtureClient
    monkeypatch.setitem(sys.modules,'genos',genos);monkeypatch.setitem(sys.modules,'genos.ords',ords)
    for name in list(sys.modules):
        if name in ('agent_ords','agent_stage','transport') or name.startswith('semantic_runtime'):
            monkeypatch.delitem(sys.modules,name,raising=False)
    monkeypatch.setattr(sys,'path',sys.path[:])
    monkeypatch.setenv('ORACLE_ORDS_SCHEMA','fixture')
    monkeypatch.setenv('ORACLE_ORDS_CLIENT_ID','fixture-id')
    monkeypatch.setenv('ORACLE_ORDS_CLIENT_SECRET','private-secret-value')
    monkeypatch.setattr(sys,'argv',['diagnose.py','--code-root',str(root)])
    monkeypatch.chdir(work)
    diag.main()
    printed=capsys.readouterr().out
    report=json.loads(printed.removeprefix('ORDS_DIAGNOSTIC '))
    assert report['status']=='PASS' and report['sql_calls']==3
    assert Path(report['saved_report']).is_file() and 'private-secret-value' not in printed
    (root/'agent_ords.py').write_text('# changed\n')
    with pytest.raises(ValueError,match='R6_CODE_FILE_MISMATCH'):diag.code_root(str(root))
