import ast
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import types
import pytest

HERE = Path(__file__).parent
BASE = HERE.parent/'pipeline_attempt_recovery_20261029_r1'
sys.path.insert(0, str(BASE))
from test_compute import env, Folder, module


def landing_folder():
    folder = Folder()
    for name in ('RAW_INPUT.zip','PIPELINE_SUPPORT.zip'):
        raw = ('fixture '+name).encode()
        folder.files[name] = raw
        receipt = {'archive':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        folder.files[name+'.receipt.json'] = json.dumps(receipt).encode()
        folder.files[name.replace('.zip',' (1).zip')] = b'other-copy'
        folder.files[name+'.receipt (1).json'] = b'invalid duplicate not selected'
    folder.files['DATAIKU_R10_RECOVERY_CLIENT_20261029_R1.zip'] = (BASE/'DATAIKU_R10_RECOVERY_CLIENT_20261029_R1.zip').read_bytes()
    return folder


@pytest.mark.parametrize('case', ['valid','missing_raw','missing_receipt','invalid_receipt','different_input','different_db','health_mismatch','expired','exhausted','no_confirmation'])
def test_delivered_whole_notebook_uses_real_receipts_and_preserves_guardrails(env, monkeypatch, case):
    landing = landing_folder()
    if case == 'missing_raw': del landing.files['RAW_INPUT.zip']
    if case == 'missing_receipt': del landing.files['RAW_INPUT.zip.receipt.json']
    if case == 'invalid_receipt': landing.files['RAW_INPUT.zip.receipt.json'] = json.dumps({'archive':'wrong','bytes':1,'sha256':'0'*64}).encode()
    helper = module('r2_prior_state', HERE.parent/'pipeline_pod_20261028_r4/test_pod.py')
    helper.OLD = '1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
    saved, old, identity = helper.old_state(env)
    # The production receipt parser is exercised, not replaced with an empty fixture.
    canonical = {n:{**json.loads(landing.files[n+'.receipt.json']),'remote':'/'+n}
        for n in ('RAW_INPUT.zip','PIPELINE_SUPPORT.zip') if n+'.receipt.json' in landing.files}
    original_input = {'archives':canonical, 'landing':'ehA8dpVm','raw':'r'}
    identity['input'] = original_input
    old.value['binding'] = {**identity, 'service_code':helper.OLD}
    old.value['attempt_count'] = 3
    if case == 'expired': old.value['deadline'] = 1
    if case == 'exhausted': old.value['attempt_count'] = 4
    old.save()
    cfg = dict(landing='ehA8dpVm',raw='r',structured='s',connection='c',load='l')
    recipe_code = (BASE/'bootstrap.txt').read_text()+'\nrun_recipe('+repr('structure')+', '+repr(cfg)+')\n'
    recipe = types.SimpleNamespace(get_settings=lambda:types.SimpleNamespace(get_code=lambda:recipe_code))
    project = types.SimpleNamespace(get_recipe=lambda _:recipe)
    dataiku = types.SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',
        api_client=lambda:types.SimpleNamespace(get_project=lambda _:project),
        get_custom_variables=lambda:{'LEGAL_RECIPE_JOB_NAME':'same'},
        Folder=lambda key:landing if key=='ehA8dpVm' else saved)
    monkeypatch.setitem(sys.modules,'dataiku',dataiku)
    before_landing, before_saved = dict(landing.files), dict(saved.files)
    source = (HERE/'DATAIKU_ONE_ATTEMPT_R2.txt').read_text()
    tree = ast.parse(source)
    # Execute the published bootstrap/package hash check, extraction, module reset,
    # and named-input installation, then substitute only the external DB context.
    setup_tree = ast.Module(body=tree.body[:-1],type_ignores=[])
    namespace = {}
    exec(compile(setup_tree,'published-notebook','exec'),namespace)
    import controller as c
    operations, receipts_seen = [], []
    class Wire:
        def call(self, op, **kwargs):
            operations.append(op)
            assert op == 'HEALTH'
            response = env.api.handle({'API_TYPE':'HEALTH'})
            if case == 'health_mismatch': response['code_sha256'] = 'f'*64
            return response
    def context(cfg_arg, receipts, variables):
        receipts_seen.append(receipts)
        actual = {**identity,'input':{'archives':receipts,'landing':'ehA8dpVm','raw':'r'}}
        if case == 'different_input': actual['input'] = {'changed':True}
        if case == 'different_db': actual['database'] = {'changed':True}
        return None,None,Wire(),actual
    monkeypatch.setattr(c,'context',context)
    if case == 'no_confirmation': namespace['CONFIRMATION'] = ''
    last = ast.Module(body=tree.body[-1:],type_ignores=[])
    try:
        if case == 'valid':
            exec(compile(last,'published-notebook','exec'),namespace)
            assert receipts_seen == [canonical]
            assert operations == ['HEALTH'] and env.api.HANDLES == {}
            assert c.legacy_state(c.Scope(saved),'same')['value']['attempt_count'] == 3
            grants = [p for p in saved.files if '/one-attempt/' in p]
            assert len(grants) == 1
            after_grant = dict(saved.files)
            exec(compile(last,'published-notebook','exec'),namespace)
            assert saved.files == after_grant
            migrated = c.open_store(saved,'same',identity)
            assert migrated.value['attempt_count'] == 4
            assert migrated.value['deadline'] == old.value['deadline']
            assert migrated.value['reserved_sql_calls'] == 192
            assert migrated.value['reserved_http_calls'] == 512
        else:
            expected_exception = c.r.legacy.RunError if case == 'invalid_receipt' else ValueError
            with pytest.raises(expected_exception):
                exec(compile(last,'published-notebook','exec'),namespace)
            assert saved.files == before_saved
            assert env.api.HANDLES == {}
        assert landing.files == before_landing
        assert all(saved.files[k] == v for k,v in before_saved.items())
    finally:
        shutil.rmtree(namespace['work'])


def test_original_notebook_missing_selection_reproduces_photo_error(env):
    landing = landing_folder()
    with pytest.raises(ValueError, match='INPUT_NAME_AMBIGUOUS_OR_MISSING: RAW_INPUT.zip'):
        env.c.r.input_receipts(landing)


def test_selected_reader_keeps_original_hash_checks(env):
    import named_inputs
    folder = landing_folder()
    named_inputs.install_input_selection(env.c.r)
    receipts = env.c.r.input_receipts(folder)
    original = env.c.r.input_receipts
    named_inputs.install_input_selection(env.c.r)
    assert env.c.r.input_receipts is original
    item = receipts['RAW_INPUT.zip']
    assert env.c.r.object_hash(folder,item['remote'],item['bytes']) == item['sha256']
    folder.files['RAW_INPUT.zip'] = b'x'*item['bytes']
    output = Folder()
    work = env.tmp/'hash-check'; work.mkdir()
    with pytest.raises(env.c.r.legacy.RunError, match='DOWNLOAD_HASH_OR_SIZE'):
        env.c.r.unpack_raw(folder, output, work)
    assert output.files == {}
