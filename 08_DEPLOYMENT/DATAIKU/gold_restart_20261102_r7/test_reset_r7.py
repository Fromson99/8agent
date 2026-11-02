import copy
from decimal import Decimal
import json
from pathlib import Path
import types

import pytest
import reset_source as reset
from test_reset_source import work,run
ACTUAL_SOURCE_COUNT=reset.source_count


@pytest.mark.parametrize('value',[0,3854,3854.0,Decimal('3854'),Decimal('3854.000'),'3854'])
def test_exact_db_count_types(value):
    assert reset.count_integer(value,'table')==int(value)


@pytest.mark.parametrize('value',[True,-1,1.5,Decimal('1.5'),None,float('nan'),float('inf'),
                                  Decimal('NaN'),Decimal('Infinity'),float(2**53),'3.5'])
def test_invalid_count_is_not_reported_as_excess_rows(value):
    with pytest.raises(ValueError,match='RESET_COUNT_INVALID:table:type='):
        reset.count_integer(value,'table')


def test_source_count_decimal_from_dataiku(work,capsys):
    contract=work.loader.Contract(None)
    db=types.SimpleNamespace(query=lambda sql:[{'N':Decimal('3854')}])
    assert ACTUAL_SOURCE_COUNT(db,contract,'DOC_VER','v')==3854
    out=capsys.readouterr().out
    assert '3854' in out and 'Decimal' in out and contract.table('DOC_VER') in out


def test_more_than_ten_thousand_bound_rows_complete_reset(work):
    # Actual row backup + verifier + delete + new state, not just a changed constant.
    work.data['DOC_VER'].extend({**work.row,'DOC_ID':'id'+str(i)} for i in range(10001))
    run(work)
    assert len(work.data['DOC_VER'])==1 and work.data['DOC_VER'][0]['MNFST_HASH_VALU']=='OTHER'
    manifest=json.loads(next((work.directory/'reset-backups').glob('*/manifest.json')).read_text())
    assert manifest['counts']['DOC_VER']==10002
    assert json.loads(work.path.read_text())['status']=='NEW'


def test_exact_scope_failure_shows_actual_and_expected_before_delete(work,monkeypatch,capsys):
    monkeypatch.setattr(reset,'source_count',lambda *a:100001)
    with pytest.raises(ValueError,match='actual=100001:expected_max=100000'):run(work)
    assert 'RESET_SCOPE' in capsys.readouterr().out and work.flags['deletes']==0


def legacy_controller(work):
    # Represent precisely R6's failed gate: controller durable, old state backup, no manifest or delete.
    root=work.directory/'reset-backups'/'legacy';root.mkdir(parents=True)
    (root/'old-state.json').write_bytes(work.original)
    state=json.loads(work.original)
    control={'schema':'gold-source-reset-r6','id':'legacy','binding':state['binding'],
             'old_state_sha256':reset.raw_sha(work.path),'phase':'BACKING_UP','created_at':1,
             'original_deadline':100,'reset_code_sha256':reset.R6_HELPER_SHA256}
    path=work.directory/'reset-r6.json';path.write_text(json.dumps(control))
    return root,path,control


def test_r6_failed_gate_migrates_without_losing_original_or_reset_id(work):
    root,path,control=legacy_controller(work);original=path.read_bytes()
    run(work)
    assert (root/'control-r6-before-upgrade.json').read_bytes()==original
    assert (root/'old-state.json').read_bytes()==work.original
    assert json.loads(work.path.read_text())['reset_id']=='legacy'
    assert json.loads(path.read_text())['upgrade']['from_helper_sha256']==reset.R6_HELPER_SHA256
    work.data['DOC_VER'].append(copy.deepcopy(work.row));previous=work.flags['deletes']
    run(work)
    assert work.flags['deletes']==previous and len(work.data['DOC_VER'])==2


@pytest.mark.parametrize('case',['changed_helper','deleting','manifest','changed_original','backup_changed'])
def test_r6_migration_rejects_unverified_state_before_delete(work,case):
    root,path,control=legacy_controller(work)
    if case=='changed_helper':control['reset_code_sha256']='unknown'
    elif case=='deleting':control['phase']='DELETING'
    elif case=='manifest':(root/'manifest.json').write_text('{}')
    elif case=='changed_original':work.path.write_text(work.path.read_text()+' ')
    else:(root/'old-state.json').write_text('{}')
    path.write_text(json.dumps(control))
    with pytest.raises(ValueError):run(work)
    assert work.flags['deletes']==0


def test_r6_migration_crash_after_archive_is_resumable(work):
    root,path,control=legacy_controller(work)
    (root/'control-r6-before-upgrade.json').write_bytes(path.read_bytes())
    run(work)
    assert json.loads(work.path.read_text())['reset_id']=='legacy'


def test_backup_batches_bound_memory_preserve_all_rows(monkeypatch):
    monkeypatch.setattr(reset,'BACKUP_TARGET_BYTES',100)
    rows=[{'id':i,'text':'한글'*12} for i in range(12)]
    canonical=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':'))
    batches=list(reset.backup_batches(iter([rows]),canonical))
    assert [r for batch in batches for r in batch]==rows
    assert len(batches)>1
    assert all(len(canonical(batch).encode())<=100 or len(batch)==1 for batch in batches)


def test_r6_original_bytes_remain_known():
    previous=Path(__file__).parent.parent/'gold_restart_20261102_r6/reset_source.py'
    assert reset.raw_sha(previous)==reset.R6_HELPER_SHA256
