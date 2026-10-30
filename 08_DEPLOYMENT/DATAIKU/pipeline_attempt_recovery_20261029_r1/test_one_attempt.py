import hashlib
import io
import json
from pathlib import Path
import sys
import time
import types
import pytest
from test_compute import env, module, Folder
from test_compute import test_published_sdk_installer_apply_repeat_rollback as check_sdk

HERE = Path(__file__).parent
R7 = '1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
R8 = 'f88b1426f29bc16a862a1a67c72bff8a0d15b106a84aa2ca3dc9f80f4820c084'
R9 = 'aa73eedbbee5f9f4e842c87e7f0fca2278c2dc56b936390871fbf268efea7c73'


def setup(e, code=R7):
    helper = module('prior_fixture', HERE.parent / 'pipeline_pod_20261028_r4/test_pod.py')
    helper.OLD = code
    folder, store, identity = helper.old_state(e)
    store.value['attempt_count'] = 3
    store.save()
    import one_attempt as one
    scoped = e.c.Scope(folder)
    latest = e.c.legacy_state(scoped, 'same')
    return one, folder, store, identity, latest


@pytest.mark.parametrize('code', [R7, R8, R9])
def test_explicit_grant_preserves_history_budgets_once(env, code):
    one, folder, old, identity, latest = setup(env, code)
    before = dict(folder.files)
    with pytest.raises(ValueError, match='COMPUTE_ATTEMPT_BUDGET_EXHAUSTED'):
        env.c.open_store(folder, 'same', identity)
    assert folder.files == before
    grant = one.authorize(old.folder, 'same', latest, identity, one.CONFIRMATION, 'operator requests corrected R10')
    assert env.c.legacy_state(old.folder, 'same') == latest
    assert len(folder.files) == len(before) + 1
    assert one.authorize(old.folder, 'same', latest, identity, one.CONFIRMATION, 'repeat') == grant
    result = env.c.open_store(folder, 'same', identity)
    assert result.value['attempt_count'] == 4 and result.value['phase'] == 'NEW'
    assert result.value['deadline'] == old.value['deadline']
    assert (result.value['reserved_sql_calls'], result.value['reserved_http_calls']) == (192, 512)
    assert result.value['operator_attempt_history'] == [grant]
    assert result.value['upgrade_history'][-1]['checkpoint_sha256'] == latest['sha256']
    assert result.value['upgrade_history'][-1]['zero_review_proof']['field_calls_measured'] is False
    after = dict(folder.files)
    assert env.c.open_store(folder, 'same', identity).value == result.value
    assert folder.files == after
    assert all(folder.files[k] == v for k, v in before.items())
    result.value.update(phase='FAILED', model_execution_possible=False, compute={'handle':'d'*32}, last_observed={'handle':'d'*32,'state':'FAILED'})
    result.save()
    result.folder.upload_stream('controls/same/retry.json', io.BytesIO(json.dumps({'handle':'d'*32}).encode()))
    before_retry = dict(folder.files)
    with pytest.raises(ValueError, match='COMPUTE_ATTEMPT_BUDGET_EXHAUSTED'):
        env.c.apply_retry(result, 'same', env.tmp)
    assert folder.files == before_retry


@pytest.mark.parametrize('case', ['no_confirmation','count2','count4','bool_count','running','unknown','other_input','result','return_receipt','oracle_written','deadline','nan_deadline','sql_budget','http_budget','negative_usage','previous_grant','stale_checkpoint'])
def test_invalid_grant_never_changes_saved_state(env, case):
    one, folder, store, identity, latest = setup(env)
    if case == 'count2': store.value['attempt_count'] = 2
    elif case == 'count4': store.value['attempt_count'] = 4
    elif case == 'bool_count': store.value['attempt_count'] = True
    elif case == 'running': store.value['last_observed']['state'] = 'RUNNING'
    elif case == 'unknown': store.value['compute']['code_sha256'] = 'f'*64
    elif case == 'other_input': identity['input'] = {'changed':True}
    elif case in ('result','return_receipt','oracle_written'): store.value['result_blob' if case == 'result' else case] = {'preserve': True}
    elif case == 'deadline': store.value['deadline'] = time.time() - 1
    elif case == 'nan_deadline': store.value['deadline'] = float('nan')
    elif case == 'sql_budget': store.value['reserved_sql_calls'] = 1000000
    elif case == 'http_budget': store.value['reserved_http_calls'] = 1000000
    elif case == 'negative_usage': store.value['reserved_http_calls'] = -1
    elif case == 'previous_grant': store.value['operator_attempt_history'] = [{'used':True}]
    store.save()
    if case != 'stale_checkpoint': latest = env.c.legacy_state(store.folder, 'same')
    before = dict(folder.files)
    with pytest.raises(ValueError):
        one.authorize(store.folder, 'same', latest, identity, '' if case == 'no_confirmation' else one.CONFIRMATION, 'test')
    assert folder.files == before


@pytest.mark.parametrize('field', ['checkpoint_sha256','authorized_attempt_count','original_deadline','reserved_sql_calls','to_code','authorization','extra'])
def test_tampered_grant_never_starts_next_attempt(env, field):
    one, folder, store, identity, latest = setup(env)
    grant = one.authorize(store.folder, 'same', latest, identity, one.CONFIRMATION, 'test')
    path = env.c.NAMESPACE + grant['grant_path']
    value = json.loads(folder.files[path]); value[field] = 'tampered'
    folder.files[path] = json.dumps(value).encode()
    before = dict(folder.files)
    with pytest.raises(ValueError, match='RECOVERY_GRANT_CHANGED'):
        env.c.open_store(folder, 'same', identity)
    assert folder.files == before


def test_checkpoint_changed_after_grant_is_not_authorized(env):
    one, folder, store, identity, latest = setup(env)
    one.authorize(store.folder, 'same', latest, identity, one.CONFIRMATION, 'test')
    store.value['reserved_http_calls'] += 1; store.save()
    before = dict(folder.files)
    with pytest.raises(ValueError, match='COMPUTE_ATTEMPT_BUDGET_EXHAUSTED'):
        env.c.open_store(folder, 'same', identity)
    assert folder.files == before


@pytest.mark.parametrize('case', ['zero', 'nonzero', 'tampered', 'count_mismatch'])
def test_present_audit_remains_mandatory_with_grant(env, case):
    one, folder, store, identity, latest = setup(env)
    n = 1 if case == 'nonzero' else 0
    ledger = {'calls':n, 'events':[{'status':'RESERVED'}]*n}
    if case == 'count_mismatch': ledger['events'] = [{'status':'RESERVED'}]
    h = hashlib.sha256(json.dumps(ledger, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()).hexdigest()
    summary = env.tmp/'review.json'; summary.write_text(json.dumps({'reserved_model_calls':n,'ledger_errors':[]}))
    journal = env.tmp/'ledger.json'; journal.write_text(json.dumps({'state':ledger,'sha256':h}))
    z = env.tmp/'audit.zip'
    arc = env.t.pack({'audit/review-summary.json':summary,'audit/structure/doc/model-calls/x.json':journal}, z, metadata={})
    store.value['audit_blob'] = store.put_blob(z)
    store.value['last_observed']['audit'] = {k:arc[k] for k in ('bytes','sha256')}
    if case == 'tampered': folder.files[env.c.NAMESPACE+store.value['audit_blob']['path']] += b'x'
    store.save(); latest = env.c.legacy_state(store.folder, 'same')
    one.authorize(store.folder, 'same', latest, identity, one.CONFIRMATION, 'test')
    before = dict(folder.files)
    if case == 'zero':
        result = env.c.open_store(folder, 'same', identity)
        assert result.value['upgrade_history'][-1]['zero_review_proof']['reserved_review_calls'] == 0
    else:
        with pytest.raises(ValueError): env.c.open_store(folder, 'same', identity)
        assert folder.files == before


def test_operator_inspection_authorization_health_only_and_install_sdk(env, monkeypatch):
    one, folder, store, identity, latest = setup(env)
    cfg = dict(landing='ehA8dpVm', raw='r', structured='s', connection='c', load='l')
    code = (HERE/'bootstrap.txt').read_text() + '\nrun_recipe('+repr('structure')+', '+repr(cfg)+')\n'
    settings = types.SimpleNamespace(get_code=lambda:code)
    recipe = types.SimpleNamespace(get_settings=lambda:settings)
    project = types.SimpleNamespace(get_recipe=lambda _:recipe)
    api = types.SimpleNamespace(get_project=lambda _:project)
    monkeypatch.setitem(sys.modules, 'dataiku', types.SimpleNamespace(api_client=lambda:api, get_custom_variables=lambda:{'LEGAL_RECIPE_JOB_NAME':'same'}, Folder=lambda _:folder))
    operations = []
    class Wire:
        def call(self, op, **kwargs):
            operations.append(op)
            assert op == 'HEALTH'
            return env.api.handle({'API_TYPE':op})
    monkeypatch.setattr(env.c.r, 'input_receipts', lambda _:[])
    monkeypatch.setattr(env.c, 'context', lambda *args:(None,None,Wire(),identity))
    before = dict(folder.files)
    result = one.run('inspect')
    assert result['attempt_count'] == 3 and not result['additional_attempt_authorized']
    assert operations == [] and folder.files == before
    result = one.run('authorize_one_attempt', one.CONFIRMATION, 'operator explicit request')
    assert result['additional_attempt_authorized'] and not result['compute_started']
    assert operations == ['HEALTH'] and env.api.HANDLES == {}
    result = one.run('inspect')
    assert result['additional_attempt_authorized'] and operations == ['HEALTH']
    assert env.c.legacy_state(store.folder, 'same') == latest


def test_exact_r10_flow_install_repeat_and_rollback(env, monkeypatch):
    ref = json.loads((env.dku/'REFERENCE.json').read_text())
    assert ref['prior_compute_bootstraps'][-1] == (HERE.parent/'pipeline_single_cpu_20261029_r10/bootstrap.txt').read_text()
    check_sdk(env, monkeypatch, -1)
