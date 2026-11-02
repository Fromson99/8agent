import copy
import importlib.util
import json
from pathlib import Path
import re
import types
import pytest
import reset_source as reset
import jdbc_transport as transport
from error_diagnostics import safe_message,event,banner
from test_reset_source import work,run
from test_reset_r7 import legacy_controller


@pytest.mark.parametrize('separator',['\n','\\n','#n'])
def test_plsql_message_after_06550_is_not_cut(separator):
    message=separator.join(['ORA-06550: line 1, column 38137:',
                           'PL/SQL: ORA-00932: inconsistent datatypes',
                           'PLS-00103: Encountered an unexpected symbol',
                           'SQL: SECRET_RAW_SOURCE ORA-99999: fake payload code'])
    shown=banner(event(RuntimeError(message)))
    assert 'ORA-06550' in shown and 'ORA-00932: inconsistent datatypes' in shown
    assert 'PLS-00103: Encountered an unexpected symbol' in shown
    assert 'SECRET_RAW_SOURCE' not in shown and 'ORA-99999' not in shown
    old=Path(__file__).parent.parent/'gold_restart_20261102_r7/error_diagnostics.py'
    spec=importlib.util.spec_from_file_location('prior_diagnostics',old)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if separator!='\n':assert 'ORA-00932' not in module.safe_message(RuntimeError(message))


@pytest.mark.parametrize('value',["'\\; -- :payload /* SQL */",'한글😀𠀀'*1000,'', 'line\nline\r\tend'])
def test_transport_payload_never_becomes_sql_text(value):
    sql=transport.render('BEGIN NULL; x := :payload; END;',[('payload',value,'CLOB')],write=True)
    pieces=re.findall(r"HEXTORAW\('([0-9A-F]+)'\)",sql)
    assert b''.join(bytes.fromhex(p) for p in pieces).decode()==value
    assert all(len(p)<=32000 for p in pieces)
    if value:assert value not in sql


def test_bind_scanner_preserves_literals_and_comments():
    sql="BEGIN x:=:real; y:=':fake'; -- :comment\n NULL; END;"
    rendered=transport.render(sql,[('real',2,'NUMBER')],write=True)
    assert "x:=2; y:=':fake'" in rendered and '-- :comment' in rendered
    with pytest.raises(ValueError):transport.render(sql,[],write=True)


def test_large_payload_uses_lossless_gzip_not_huge_source_literals():
    import gzip
    value="한글😀 quote' slash\\;\n"*40000
    sql=transport.render('BEGIN x := :payload; END;',[('payload',value,'CLOB')],write=True)
    packed=b''.join(bytes.fromhex(p) for p in re.findall(r"HEXTORAW\('([0-9A-F]+)'\)",sql))
    assert gzip.decompress(packed).decode()==value
    assert 'UTL_COMPRESS.LZ_UNCOMPRESS' in sql and 'DBMS_LOB.CONVERTTOCLOB' in sql
    assert value not in sql and len(sql)<len(value.encode())


def test_r7_backup_interruption_upgrade(work):
    root,path,control=legacy_controller(work)
    control.update(schema='gold-source-reset-r7',reset_code_sha256=reset.R7_HELPER_SHA256)
    path.write_text(json.dumps(control));original=path.read_bytes()
    (root/'snapshot-incomplete').mkdir();(root/'snapshot-incomplete'/'old.gz').write_bytes(b'keep')
    run(work)
    assert (root/('control-'+reset.R7_HELPER_SHA256[:16]+'-before-r9.json')).read_bytes()==original
    assert (root/'snapshot-incomplete'/'old.gz').read_bytes()==b'keep'
    assert json.loads(work.path.read_text())['reset_id']=='legacy'


@pytest.mark.parametrize('after_state',[False,True])
def test_r7_mid_delete_or_finished_upgrade_does_not_repeat_new_reset(work,after_state):
    if after_state:work.flags['crash_after_new_state']=True
    else:work.flags['response_loss']=True
    with pytest.raises(RuntimeError):run(work)
    path=work.directory/'reset-r6.json';control=json.loads(path.read_text())
    control.update(schema='gold-source-reset-r7',reset_code_sha256=reset.R7_HELPER_SHA256)
    path.write_text(json.dumps(control))
    if after_state:work.data['DOC_VER'].append(copy.deepcopy(work.row))
    deletes=work.flags['deletes'];run(work)
    assert json.loads(work.path.read_text())['status']=='NEW'
    if after_state:assert deletes==work.flags['deletes'] and len(work.data['DOC_VER'])==2


def test_no_db_block_during_backup_but_delete_still_checks_content(work):
    block=work.loader.Database(None).block;calls=[]
    def only_deletion(sql,*args,**kwargs):
        assert 'DELETE FROM ' in sql
        calls.append(sql)
        return block(sql,*args,**kwargs)
    work.loader.Database(None).block=only_deletion
    run(work)
    assert calls and all('RESET_BACKUP_CONTENT_CHANGED' in sql for sql in calls)


def test_changed_value_between_backup_and_delete_stops(work):
    block=work.loader.Database(None).block
    def changed(sql,*args,**kwargs):
        work.data['DOC_VER'][0]['DOC_NAME']='changed after backup'
        return block(sql,*args,**kwargs)
    work.loader.Database(None).block=changed
    with pytest.raises(ValueError,match='BACKUP_CONTENT_CHANGED'):run(work)
    assert work.flags['deletes']==0 and work.path.read_bytes()==work.original


def test_backup_display_uses_live_progress_not_old_failed_state(work):
    from progress_display import Display
    display=Display(work.old,work.loader.Contract(None).sha256,'load')
    display.observe({'phase':'RESET_BACKUP','completed_rows':1500,'total_rows':3854,
                     'elapsed_seconds':36,'remaining_seconds':56})
    shown=display.render()
    assert '백업: 1,500 / 3,854행' in shown and '0분 36초' in shown and '0분 56초' in shown
    assert '초기화 진행 중' in shown and '예상 잔여 중단됨' not in shown
    display.observe({'phase':'DIAGNOSTIC_ERROR'})
    assert '초기화 중단' in display.render()
