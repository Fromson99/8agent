"""Adapt the existing actual-worker/Oracle fixture to the new separated stages."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_layers_20261027_r1'
source=(BASE/'live_runner.py').read_text()
start=source.index('kwargs=dict(folder=folder')
end=source.index('counts={}',start)
source=source[:start]+'''
sys.path.insert(0,str(client_root.parent))
import recipes_runtime as recipes
recipes.CheckedClient=Remote
cfg={'landing':'fixture-landing','raw':'fixture-raw','structured':'fixture-structured','load':'fixture-load'}
folders={}
for role,name in cfg.items():
    folders[role]=Folder();folders[role].root=work/name;folders[role].root.mkdir()
for name in ['RAW_INPUT.zip','RAW_INPUT.zip.receipt.json','PIPELINE_SUPPORT.zip','PIPELINE_SUPPORT.zip.receipt.json']:
    with (exports/name).open('rb') as f:folders['landing'].upload_stream(name,f)
def stage_dir(name):
    path=work/name;path.mkdir(exist_ok=True);return path
assert recipes.unpack_raw(folders['landing'],folders['raw'],stage_dir('unpack'))['status']=='RAW_SAVED'
# Raw now lives in the managed folder. Later stages materialize it from this S3 adapter.
with admin.cursor() as cur:cur.execute('DROP INDEX SIDDS.LGL_SRCH_ROW_KEY_IX_S')
try:recipes.structure(cfg,folders,variables,stage_dir('preflight-fail'),'contract-job')
except ValueError as exc:assert 'TARGET_INDEX' in str(exc)
else:raise AssertionError('preflight accepted missing index')
assert not Remote.calls
with admin.cursor() as cur:
    cur.execute(next(sql for typ,k,n,sql in schema.ddl() if n=='LGL_SRCH_ROW_KEY_IX_S'))
result=recipes.structure(cfg,folders,variables,stage_dir('structure'),'contract-job')
assert result['status']=='STRUCTURED' and not result['oracle_written']
assert Executor.writes==0 and 'ACK' not in Remote.calls
prior_calls=list(Remote.calls)
# Repeat structure consumes durable state without a new GENOS execution or new deadline.
assert recipes.structure(cfg,folders,variables,stage_dir('structure-repeat'),'contract-job')==result
assert Remote.calls==prior_calls
structured_hashes={p:t.sha(p) for p in t.files(folders['structured'].root)}
try:recipes.load(cfg,folders,variables,stage_dir('load-write-loss'),'contract-job')
except io.DPError as exc:assert 'WRITE_UNCONFIRMED' in str(exc)
else:raise AssertionError('write uncertainty not retained')
assert 'ACK' not in Remote.calls
try:recipes.load(cfg,folders,variables,stage_dir('load-ack-loss'),'contract-job')
except RuntimeError as exc:assert 'ACK response loss' in str(exc)
else:raise AssertionError('ACK uncertainty not retained')
checkpoints=sorted((folders['load'].root/'_pipeline/jobs/contract-job').glob('checkpoint-*.json'))
latest=json.loads(checkpoints[-1].read_text())
assert latest['phase']=='LOAD_VERIFIED_ACK_PENDING' and latest['oracle_written']
original_deadline=latest['deadline'];reserved=latest['reserved_sql_calls']
assert not list(Path(__import__('os').environ['PIPELINE_SCRATCH']).rglob('store.sqlite'))
# New recipe process directory: restore result/state from managed folders, no local reuse.
result=recipes.load(cfg,folders,variables,stage_dir('load-new-scratch'),'contract-job')
assert result['status']=='COMPLETE' and result['query_rows']>0 and result['oracle_written']
assert Remote.calls.count('HEALTH')==1 and Remote.calls.count('EXECUTE')==1
checkpoints=sorted((folders['load'].root/'_pipeline/jobs/contract-job').glob('checkpoint-*.json'))
latest=json.loads(checkpoints[-1].read_text())
assert latest['deadline']==original_deadline and latest['reserved_sql_calls']>reserved
assert all(t.sha(p)==sha for p,sha in structured_hashes.items())
''' + source[end:]
source=source.replace("assert client.run_dataiku(inputs,exports/'PIPELINE_SUPPORT.zip',job,**kwargs)['status']=='COMPLETE'",
                      "assert recipes.load(cfg,folders,variables,stage_dir('load-duplicate'),'contract-job')['status']=='COMPLETE'")
source=source.replace("'field_dataiku_genos_adb_tested':False,", "'field_dataiku_genos_adb_tested':False,'separate_recipe_stages':True,'upstream_result_immutable':True,")
(HERE/'live_runner.py').write_text(source)
test=(Path(__file__).resolve().parents[3]/'05_TESTS/CONTRACTS/test_dataiku_pipeline_layers_live.py').read_text()
test=test.replace("pipeline_layers_20261027_r1'","pipeline_recipes_20261027_r1'")
test=test.replace("A8_LAYERS_ORACLE_LIVE","A8_RECIPES_ORACLE_LIVE")
a=test.index("    for archive in [")
b=test.index("    dev=tmp_path/'dev'",a)
test=test[:a]+'''    with zipfile.ZipFile(SERVICE_DELIVERY/'GENOS_PIPELINE_SERVICE_20261022_R2.zip') as z:z.extractall(tmp_path)
    with zipfile.ZipFile(DELIVERY/'DATAIKU_RECIPE_PACKAGE_20261027_R1.zip') as z:z.extractall(tmp_path/'recipe_payload')
    service=tmp_path/'GENOS_PIPELINE_SERVICE_20261022_R2';client=tmp_path/'recipe_payload/client'
'''+test[b:]
(Path(__file__).resolve().parents[3]/'05_TESTS/CONTRACTS/test_dataiku_pipeline_recipes_live.py').write_text(test)
