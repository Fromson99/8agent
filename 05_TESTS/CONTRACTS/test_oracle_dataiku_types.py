"""JDBC schema inference regression and same R3 checkpoint resume, synthetic SQL."""
import ast
import importlib.util
import io as textio
from pathlib import Path

import pandas as pd
import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full
import test_oracle_deferred_indexes as prior_tests
from lawrag.pipeline import oracle_full_package as pack, oracle_query_dataiku as bridge
from semantic_runtime import oracle_dp_io as io

ROOT = Path(__file__).resolve().parents[2]
D = ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_existing_zip_20261020_r4'
R3 = D.with_name('legal_oracle_existing_zip_20261020_r3')


def load_bridge(folder, name):
    path = folder/'package/runtime/lawrag/pipeline/oracle_query_dataiku.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('value', ['0007', '0', '001', '1e3', '123456789012345678901234567890'])
def test_schema_types_preserve_identifier_bytes_and_real_numeric_fields(value):
    old = load_bridge(R3, 'old_bridge')
    class Executor:
        def query_to_df(self, text, **kwargs):
            csv = 'UNIT_ID,N\n'+value+',7\n'
            types = {'UNIT_ID': str, 'N': 'int64'} if kwargs.get('infer_from_schema') else None
            return pd.read_csv(textio.StringIO(csv), dtype=types)
    payload = {'statementText':'SELECT UNIT_ID,N FROM synthetic','limit':1}
    before = old.DataikuClient(Executor(), 'c', 'p').request('POST',old.DataikuClient.SQL_PATH,payload)
    new = load_bridge(D, 'new_bridge')
    after = new.DataikuClient(Executor(), 'c', 'p').request('POST',new.DataikuClient.SQL_PATH,payload)
    assert after['items'][0]['resultSet']['items'] == [{'UNIT_ID': value, 'N': 7}]
    if value != '123456789012345678901234567890':
        assert before != after


def test_unsupported_schema_option_is_not_silently_retried():
    class Executor:
        calls = 0
        def query_to_df(self, text, **kwargs):
            self.calls += 1
            raise TypeError('unsupported option; private payload')
    executor = Executor();client = bridge.DataikuClient(executor,'c','p')
    with pytest.raises(io.DPError, match='JDBC_FAILURE: TypeError') as e:
        client.request('POST',client.SQL_PATH,{'statementText':'SELECT 1 FROM DUAL'})
    assert executor.calls == 1 and 'private' not in str(e.value)


def transport_client(module, full, monkeypatch):
    """Run real render/adapter; only replace the remote SQL boundary."""
    captured = {}
    original = module.render
    def render(text, binds, **kwargs):
        captured.update(statementText=text, binds=[{'name':n,'value':v,'data_type':t} for n,v,t in binds])
        return original(text,binds,**kwargs)
    monkeypatch.setattr(module, 'render', render)
    class Executor:
        def query_to_df(self, text, **kwargs):
            result=full[0].request('POST','/sql',json={**captured,'limit':100})
            if kwargs.get('pre_queries'):return pd.DataFrame([{'OK':1}])
            frame=pd.DataFrame(result['items'][0]['resultSet']['items'])
            # Inject the field symptom at the SQL/Pandas boundary. No key repair.
            if 'UNIT_ID' in frame.columns and not kwargs.get('infer_from_schema'):
                frame['UNIT_ID'] = 0
            return frame
    return module.DataikuClient(Executor(),'c','p')


def test_r3_partial_write_failure_r4_diagnosis_and_exact_checkpoint_resume(full,tmp_path,monkeypatch):
    full[3].created -= prior_tests.INDEXES
    work=tmp_path/'work';logs=work/'oracle-import-r3'
    old=load_bridge(R3,'old_resume_bridge');new=load_bridge(D,'new_resume_bridge')
    before=transport_client(old,full,monkeypatch)
    def run(client, action='publish'):
        return pack.import_generation(client,full[4],target_binding='fixture',
            directory=logs,action=action,allow_missing_lookup_indexes=True)
    with pytest.raises(io.DPError,match='ROW_KEY'):run(before)
    receipt=next((logs/'source').glob('*/state.json'))
    failed=pack.bounded_json(receipt)
    assert failed['tables']['document']['rows']>0 and failed['tables']['source_unit']['rows']==0
    assert full[1].data['source_unit']  # Simulates lost validation after a committed batch.
    deadline=failed['deadline'];full_deadline=pack.bounded_json(logs/'full-state.json')['deadline']
    docs=dict(full[1].data['document']);units=dict(full[1].data['source_unit'])
    after=transport_client(new,full,monkeypatch)
    # Read-only probe from the exact delivered TXT, no IDs or body in the output.
    text=(D/'package/DATAIKU_EXISTING_ZIP_IMPORT_RUN.txt').read_text()
    helper=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='_diagnose_keys')
    namespace={'Path':Path,'json':__import__('json')}
    exec(compile(ast.Module(body=[helper],type_ignores=[]),'delivered-probe','exec'),namespace)
    # The probe imports maintained render; same real renderer with boundary capture.
    monkeypatch.setattr(bridge,'render',new.render)
    state_bytes=receipt.read_bytes();writes=(full[1].writes,full[2].writes)
    result=namespace['_diagnose_keys'](after,work,'fixture')
    assert result['status']=='TYPE_INFERENCE_DIFFERENCE_CONFIRMED' and result['writes'] is False
    assert receipt.read_bytes()==state_bytes and (full[1].writes,full[2].writes)==writes
    assert run(after,'check')['status']=='READY_FOR_FULL_IMPORT'
    result=run(after)
    assert result['status']=='FULL_DATA_VERIFIED'
    assert pack.bounded_json(receipt)['deadline']==deadline
    assert pack.bounded_json(logs/'full-state.json')['deadline']==full_deadline
    assert all(full[1].data['document'][k]==v for k,v in docs.items())
    assert all(full[1].data['source_unit'][k]==v for k,v in units.items())
    writes=(full[1].writes,full[2].writes)
    assert run(after)==result and run(after,'status')==result
    assert writes==(full[1].writes,full[2].writes)


def test_exact_r4_notebook_startup_and_pinned_import(full,tmp_path,monkeypatch):
    monkeypatch.setattr(prior_tests,'D',D)
    monkeypatch.setattr(prior_tests,'N','LEGAL_ORACLE_EXISTING_ZIP_20261020_R4')
    prior_tests.test_exact_r2_failure_to_r3_notebook_reuses_restore_and_budget(full,tmp_path)


def test_only_adapter_runtime_changed_from_r3():
    runtime=D/'package/runtime';changed=[]
    for f in runtime.rglob('*.py'):
        rel=f.relative_to(D/'package')
        if f.read_bytes()!=(R3/'package'/rel).read_bytes():changed.append(str(rel))
    assert changed==['runtime/lawrag/pipeline/oracle_query_dataiku.py']
