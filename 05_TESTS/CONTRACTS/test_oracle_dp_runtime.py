"""Functional DP migration/cache/service checks; fake ORDS, real serving files, no model/network."""
import asyncio
import copy
import json
import shutil
import time
from pathlib import Path

import pytest
from test_oracle_dp import Oracle, substring, run
from test_compact_v2_rag import structured_generation
from test_genos_compact_service_boot import entry
from semantic_runtime import oracle_dp as dp, oracle_dp_assets as assets, oracle_dp_io as io
from lawrag.pipeline import oracle_publish as publisher


class AssetOracle(Oracle):
    def __init__(self):
        super().__init__();self.parts={};self.releases={};self.truncate_clob=False
    def request(self, method, path, json):
        stmt=json['statementText']; b={x['name']:x['value'] for x in json.get('binds',[])}
        if 'LEGAL_RAG_' in stmt:
            self.calls.append(json)
            part='LEGAL_RAG_ASSET_PART_A' in stmt
            records=self.parts if part else self.releases
            key=(b['a'],b['p']) if part else b['r']
            if stmt.startswith('DECLARE'):
                self.writes+=1
                if self.mode=='denied':return {'items':[{'errorCode':1031}]}
                if self.mode=='before_timeout':self.mode=None;raise TimeoutError('before')
                assert key not in records
                records[key]=copy.deepcopy(b)
                if self.mode=='after_timeout':self.mode=None;raise TimeoutError('after')
                return {'items':[{'result':0}]}
            item=records.get(key);rows=[]
            if item:
                if 'RAW_BYTES,PART_SHA256' in stmt:rows=[{'RAW_BYTES':item['n'],'PART_SHA256':item['s']}]
                elif 'SELECT RELEASE_ID ' in stmt:rows=[{'RELEASE_ID':key}]
                elif 'SELECT q.I' in stmt:
                    rows=[{'I':i,'VALUE':item['body'][b['lob_start']-1+(i-1)*3000:b['lob_start']-1+i*3000]} for i in range(1,b['lob_parts']+1)]
                else:rows=[{'VALUE':item['body'][:100] if self.truncate_clob else item['body'],'N':io.units(item['body'])}]
            return {'items':[{'resultSet':{'items':rows,'hasMore':False,'offset':0}}]}
        if 'FETCH FIRST 100 ROWS ONLY' in stmt:
            self.calls.append(json)
            kind=next(k for k,t in io.TABLES.items() if t in stmt)
            keys=[c for c in io.KEYS[kind] if c!='DATASET_VERSION']
            rows=sorted((r for r in self.data[kind].values() if r['DATASET_VERSION']==b['v']), key=lambda r:tuple(r[c] for c in keys))
            if 'k0' in b:rows=[r for r in rows if tuple(r[c] for c in keys)>tuple(b['k'+str(i)] for i in range(len(keys)))]
            result=[]
            for row in rows[:100]:
                view=copy.deepcopy(row)
                for c in io.CLOBS.intersection(io.COLUMNS[kind]):
                    view[c+'__TOTAL']=None if row[c] is None else io.units(row[c]);view[c]=substring(row[c],1,io.LOB_UNITS)
                result.append(view)
            return {'items':[{'resultSet':{'items':result,'hasMore':False,'offset':0}}]}
        return super().request(method,path,json)


@pytest.fixture
def published(structured_generation,tmp_path):
    source=structured_generation/'store.sqlite';remote=AssetOracle()
    run(remote,source,tmp_path,action='run');transfer=run(remote,source,tmp_path,action='verify')
    result=publisher.publish(remote,source=source,transfer_receipt=transfer['receipt'],target_binding='mock-target',directory=tmp_path/'publish')
    return remote,result,structured_generation


def sql(remote,tmp_path,binding='mock-target',seconds=3600):
    return io.SQL(remote,journal=tmp_path/'calls.jsonl',binding=binding,seconds=seconds)


def test_cold_warm_source_free_exact_indices(published,tmp_path):
    remote,result,source=published
    manifest=json.loads((source/'manifest.json').read_text())
    _,files=assets.inventory(source)
    originals={a['path']:a['sha256'] for a in files if not a['path'].endswith('manifest.json')}
    shutil.rmtree(source.parent)
    generation,receipt=dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')
    assert not receipt['cache_hit']
    assert json.loads((generation/'manifest.json').read_text())['oracle_dp']['index_bytes_unchanged']
    assert all(io.file_sha(generation/name)==sha for name,sha in originals.items())
    from semantic_runtime.storage import Store
    store=Store(generation)
    try:assert store.manifest['counts']==manifest['counts']
    finally:store.close()
    count=len(remote.calls)
    same,receipt=dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')
    assert same==generation and receipt['cache_hit']
    assert all('LEGAL_RAG_RELEASE_A' in c['statementText'] for c in remote.calls[count:])
    with (generation/'store.sqlite').open('ab') as f:f.write(b'changed')
    with pytest.raises(io.DPError,match='CACHE_HASH'):
        dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')


def test_actual_service_rejects_legacy_cache_configuration(entry,published,tmp_path,monkeypatch):
    remote,result,source=published
    monkeypatch.setenv('DP','oracle')
    monkeypatch.setenv('DP_RELEASE_ID',result['release_id'])
    monkeypatch.setenv('DP_CACHE_DIR',str(tmp_path/'legacy-cache'))
    monkeypatch.setattr(dp,'prepare',lambda *a,**k:pytest.fail('legacy corpus download selected'))
    health=asyncio.run(entry.service({}, {'API_TYPE':'HEALTH'}))
    assert health['status']==503 and health['body']['code']=='ORACLE_QUERY_ERROR',health
    assert 'QUERY_STATE_PATH' in health['body']['detail']
    assert not (tmp_path/'legacy-cache').exists()


def test_changed_or_missing_oracle_source_never_publishes(published,tmp_path):
    remote,result,_=published
    row=next(iter(remote.data['block_payload'].values()));row['TEXT']='변경'
    with pytest.raises(io.DPError,match='ORACLE_SOURCE_HASH'):
        dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')
    assert not list((tmp_path/'cache').rglob('READY.json'))
    with pytest.raises(io.DPError,match='RELEASE_MISSING'):
        dp.prepare(sql(remote,tmp_path),'0'*64,tmp_path/'cache')


def test_resume_after_bind_failure_preserves_original_assets(published,tmp_path):
    remote,result,_=published
    def fail(path):raise RuntimeError('interrupted after rebinding')
    with pytest.raises(RuntimeError):dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache',verifier=fail)
    generation,_=dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')
    assert dp.verify_runtime(generation)['verified']


def test_publisher_response_loss_resume_and_clob_fallback(published,tmp_path):
    remote,result,_=published
    remote.truncate_clob=True
    assert assets.get_release(sql(remote,tmp_path),result['release_id'])['status']=='COMPLETE'
    payload=b'abc'*5000;sha=io.digest({'x':'extra'})
    remote.mode='after_timeout'
    with pytest.raises(io.DPError):assets.put_part(sql(remote,tmp_path),sha,0,payload)
    before=remote.writes;assets.put_part(sql(remote,tmp_path),sha,0,payload)
    assert remote.writes==before and assets.get_part(sql(remote,tmp_path),sha,0)==payload
    remote.parts[(sha,0)]['s']='0'*64
    with pytest.raises(io.DPError,match='ASSET_HASH'):assets.get_part(sql(remote,tmp_path),sha,0)


def test_config_invalid_and_paths():
    assert dp.enabled({'DP':'oracle'}) and not dp.enabled({'DP':''})
    with pytest.raises(io.DPError):dp.enabled({'DP':'bad'})
    for path in ('../escape','/abs','x\\y'):
        with pytest.raises(io.DPError):assets.safe_relative(path)


def test_partial_local_corruption_and_budget_are_not_reset(published,tmp_path):
    remote,result,_=published
    def fail(path):raise RuntimeError('interrupted')
    folder=tmp_path/'cache'/result['release_id']
    with pytest.raises(RuntimeError):dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache',verifier=fail)
    import sqlite3
    with sqlite3.connect(folder/'partial/generation/store.sqlite') as db:
        db.execute("UPDATE document SET name='changed'")
    with pytest.raises(io.DPError,match='CACHE_SOURCE_HASH'):
        dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')
    checkpoint=folder/'download.json';state=json.loads(checkpoint.read_text());state['deadline']=time.time()-1
    io.atomic_json(checkpoint,state)
    with pytest.raises(io.BudgetPause):dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')
    assert json.loads(checkpoint.read_text())['deadline']==state['deadline']


def test_cached_generation_complete_rag_with_synthetic_transport(published,tmp_path):
    remote,result,source=published
    shutil.rmtree(source.parent)
    generation,_=dp.prepare(sql(remote,tmp_path),result['release_id'],tmp_path/'cache')
    import test_unified_legal_agent as cases
    fixture=cases.unified.__wrapped__(tmp_path,generation)
    instance=next(fixture)
    try:cases.test_v6_returns_answer_without_assessment_or_composition_judge(instance)
    finally:
        try:next(fixture)
        except StopIteration:pass


def test_exact_standalone_asset_publisher(published,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from lawrag.pipeline import oracle_migration as migration
    remote,result,generation=published
    transfer=run(remote,generation/'store.sqlite',tmp_path,action='verify')
    original=Path.resolve
    def resolve(path,*args,**kwargs):
        return generation/'store.sqlite' if str(path)==migration.SOURCE else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',resolve)
    desk=SimpleNamespace(require_connection=lambda:SimpleNamespace(client=remote),recovery_required=False,
        binding=lambda:'mock-target',settings={'log_dir':str(tmp_path/'notebook-logs')})
    cell=Path(__file__).resolve().parents[2]/'08_DEPLOYMENT/GENOS/handoffs/oracle_dp_20261016_r1/GENOS_ORACLE_DP_20261016_R1_PUBLISH_CELL.txt'
    namespace={'desk':desk,'LEGAL_FULL_TRANSFER_RESULT':transfer}
    before=remote.writes
    exec(compile(cell.read_text(),str(cell),'exec'),namespace)
    assert namespace['LEGAL_DP_PUBLISH_RESULT']['release_id']==result['release_id']
    assert remote.writes==before
