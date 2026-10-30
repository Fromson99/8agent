"""Contracts of the exact delivered R4, no live DB/model calls."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

import pytest

HERE=Path(__file__).resolve().parent
TMP=tempfile.TemporaryDirectory(prefix='nfs-r4-contract-')
CODE=Path(TMP.name)
with zipfile.ZipFile(HERE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R4.zip') as z:z.extractall(CODE)
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
from lawrag.pipeline import oracle_full_package as full
from semantic_runtime import oracle_dp_io as io
from managed_job import BudgetClient
ORIGIN='36e52b270f8b9f73b1bfdd92d60a742afcc04fed969bce98af828dda6e54d267'

def identities():
    original=dict(target='same-db',data='same-data',generation='same-path',code=ORIGIN)
    current=dict(original,code=io.file_sha(full.__file__))
    return original,current

def test_sealed_payload_and_unchanged_r3_runtime():
    base=HERE.with_name('existing_nfs_fast_20261030_r3')
    with zipfile.ZipFile(base/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R3.zip') as z:
        changed={n for n in z.namelist() if z.read(n)!=(CODE/n).read_bytes()}
    assert changed=={'existing_client.py','client/02_BACKEND/lawrag/pipeline/oracle_full_package.py','PACKAGE_FILES.json','client/CODE_PINS.json'}
    for n,h in json.loads((CODE/'PACKAGE_FILES.json').read_text()).items():assert io.file_sha(CODE/n)==h
    for n,h in json.loads((CODE/'client/CODE_PINS.json').read_text())['files'].items():assert io.file_sha(CODE/'client'/n)==h

def test_compatible_identity_preserves_origin_and_old_receipt(tmp_path):
    original,current=identities()
    state=dict(identity=original,deadline=123456,status='PAUSED',stages={'source':{'receipt':'same'}},pending={'rows':4},error='old-failure')
    io.atomic_json(tmp_path/'full-state.json',state)
    raw=(tmp_path/'full-state.json').read_bytes(); before=copy.deepcopy(state)
    assert full._import_identity(state,current,tmp_path)==original
    assert {k:v for k,v in state.items() if k!='compatible_executor'}==before
    record=state['compatible_executor']
    assert record['prior_receipt_sha256']==hashlib.sha256(raw).hexdigest()
    assert (tmp_path/record['prior_receipt_file']).read_bytes()==raw
    assert record['execution_code_sha256']==current['code']
    io.atomic_json(tmp_path/'full-state.json',state)
    same=copy.deepcopy(state)
    assert full._import_identity(state,current,tmp_path)==original and state==same
    assert len(list(tmp_path.glob('pre-r4-state-*')))==1

@pytest.mark.parametrize('field',['target','data','generation','code','extra'])
def test_unknown_or_changed_binding_cannot_resume(tmp_path,field):
    original,current=identities();original[field]='unapproved'
    state={'identity':original};io.atomic_json(tmp_path/'full-state.json',state)
    before=(tmp_path/'full-state.json').read_bytes()
    with pytest.raises(io.DPError,match='IMPORT_BINDING'):full._import_identity(state,current,tmp_path)
    assert (tmp_path/'full-state.json').read_bytes()==before
    assert not list(tmp_path.glob('pre-r4-state-*'))

@pytest.mark.parametrize('value',[0,-1,True,'unlimited',float('inf'),float('nan')])
def test_invalid_time_budget_rejected(value,tmp_path):
    with pytest.raises(io.DPError,match='BUDGET:'):full.import_generation(None,tmp_path,target_binding='x',directory=tmp_path/'log',seconds=value)

@pytest.mark.parametrize('seconds',[None,21601,43200])
def test_none_and_more_than_six_hours_accepted(seconds,tmp_path,monkeypatch):
    class ReachedDataValidation(Exception):pass
    def verify(path):raise ReachedDataValidation
    monkeypatch.setattr(full,'verify_restored',verify)
    with pytest.raises(ReachedDataValidation):full.import_generation(None,tmp_path,target_binding='x',directory=tmp_path/'log',seconds=seconds)

def test_same_current_identity_needs_no_compatibility(tmp_path):
    _,current=identities();state={'identity':current}
    assert full._import_identity(state,current,tmp_path)==current
    assert state=={'identity':current}

def test_changed_compatibility_executor_is_rejected(tmp_path):
    original,current=identities();state={'identity':original,'compatible_executor':{'execution_code_sha256':'unknown'}}
    with pytest.raises(io.DPError,match='compatible executor'):full._import_identity(state,current,tmp_path)

@pytest.mark.parametrize('exhausted',['deadline','calls'])
def test_persistent_job_limits_remain(exhausted):
    from types import SimpleNamespace
    value=dict(deadline=0 if exhausted=='deadline' else 10**12,reserved_sql_calls=1000000 if exhausted=='calls' else 0)
    calls=[]
    client=SimpleNamespace(SQL_PATH='fake',schema_map=None,request=lambda *a,**k:calls.append(1))
    store=SimpleNamespace(value=value,save=lambda:calls.append('save'))
    budget=BudgetClient(client,store)
    with pytest.raises(io.BudgetPause,match='JOB_'):budget.request()
    assert calls==[]
