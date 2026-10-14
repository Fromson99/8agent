"""Reproduce R1 rejection and keep exact-byte guards for unknown modifications."""
import base64,gzip,importlib.util,json
from pathlib import Path
import pytest

OUT=Path(__file__).resolve().parent
PRIOR=OUT.with_name('ad_request_logs_20261013_r1')


def load(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(s);s.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def material():
    builder=load('budget_guard_prior_builder',PRIOR/'build_delivery.py')
    generated=builder.predecessors()
    try:_,payload,_=next(generated)
    finally:generated.close()
    return payload


@pytest.fixture
def checkout(tmp_path,material):
    for n,raw in material.items():
        p=tmp_path/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    return tmp_path


current=load('budget_guard_current',OUT/'apply_patch.py')
prior=load('budget_guard_prior',PRIOR/'apply_patch.py')
spec=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
prior_spec=json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))


def add_budget(root):
    folder=OUT.with_name('investigation_budget_20261007_r1')
    installer=load('guard_budget_source',folder/'install_budget.py')
    _,_,changes,_=installer.prepare(root,json.loads((folder/'PATCH_SPEC.json').read_bytes()))
    for n,raw in changes.items():(root/n).write_bytes(raw)


def snapshot(root):
    manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    return {n:(root/n).read_bytes() for n in ['CODE_MANIFEST.json']+[r['path'] for r in manifest['files']]}


def repin_service(root):
    p=root/'CODE_MANIFEST.json';manifest=json.loads(p.read_bytes());raw=(root/'service.py').read_bytes()
    for row in manifest['files']:
        if row['path']=='service.py':row.update(sha256=current.sha(raw),bytes=len(raw))
    p.write_bytes(current.encoded(manifest))


def test_r1_no_budget_runtime_bytes_identical(checkout):
    _,_,a,_=prior.prepared(checkout,prior_spec)
    _,_,b,_=current.prepared(checkout,spec)
    assert {n:r for n,r in a.items() if n!='CODE_MANIFEST.json'}=={n:r for n,r in b.items() if n!='CODE_MANIFEST.json'}


def test_r1_failure_r2_preserves_budget_and_binds_actual_output(checkout):
    add_budget(checkout);before=snapshot(checkout)
    with pytest.raises(ValueError,match='Unknown code bytes; preserved: service.py'):
        prior.prepared(checkout,prior_spec)
    _,payload,changes,after=current.prepared(checkout,spec)
    assert before==snapshot(checkout)
    assert after['investigation_budget_settings']==json.loads(before['CODE_MANIFEST.json'])['investigation_budget_settings']
    key=after['model_stream_fix']['input_signature'];state=spec['signatures'][key]
    canonical=base64.b64decode(spec['blobs'][state['patches']['service.py']['after_sha256']])
    assert current.budget_transform(changes['service.py'],spec,restore=False)==canonical
    actual_row=next(r for r in after['files'] if r['path']=='service.py')
    assert actual_row['sha256']==current.sha(changes['service.py'])!=current.sha(canonical)
    assert current.signature({**payload,**changes},after,spec)==state['output_signature']


@pytest.mark.parametrize('change',['raw_drift','altered_budget','unrelated_rehash','missing_receipt','forged_receipt'])
def test_unknown_modifications_rejected_before_write(checkout,change):
    add_budget(checkout);target=checkout/'service.py'
    if change in ('raw_drift','unrelated_rehash'):
        target.write_bytes(target.read_bytes()+b'\n# unreviewed change\n')
        if change=='unrelated_rehash':repin_service(checkout)
    elif change=='altered_budget':
        text=target.read_text();assert text.count("'GENOS_RAG_MAX_MODEL_ATTEMPTS'")==1
        target.write_text(text.replace("'GENOS_RAG_MAX_MODEL_ATTEMPTS'","'OTHER_UNREVIEWED_SETTING'"));repin_service(checkout)
    else:
        p=checkout/'CODE_MANIFEST.json';m=json.loads(p.read_bytes())
        if change=='missing_receipt':m.pop('investigation_budget_settings')
        else:m['investigation_budget_settings']['default_model_attempts_changed']=True
        p.write_bytes(current.encoded(m))
    before=snapshot(checkout)
    with pytest.raises(ValueError):current.prepared(checkout,spec)
    assert before==snapshot(checkout)


def test_every_shipped_service_output_restores_budget_reversibly():
    hashes={s['patches']['service.py']['after_sha256'] for s in spec['signatures'].values()}
    assert len(hashes)==6
    for h in hashes:
        raw=base64.b64decode(spec['blobs'][h])
        patched=current.budget_transform(raw,spec,restore=True)
        compile(patched,'service.py','exec')
        assert current.budget_transform(patched,spec,restore=False)==raw
