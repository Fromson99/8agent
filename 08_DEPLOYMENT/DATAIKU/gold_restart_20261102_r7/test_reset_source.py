import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import reset_source as reset


@pytest.fixture
def work(tmp_path,monkeypatch):
    package=HERE.parent/'gold_shape_silver_20261102_r1/package'
    spec=importlib.util.spec_from_file_location('gold_io',package/'gold_io.py')
    gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold)
    monkeypatch.setitem(sys.modules,'gold_io',gold)
    contract=gold.Contract(package/'contract.json')
    old=tmp_path/'old';old.mkdir()
    directory=tmp_path/('gold-shape-'+contract.sha256[:12]);directory.mkdir()
    root=tmp_path/'generation';root.mkdir()
    source={'dataset_version':'v','source_rows':{kind:{'rows':100000} for kind in reset.SOURCE_KINDS.values()}};query={'query':'q'}
    binding={'code':'code','contract':contract.sha256,'database':[{'LOGIN_USER':'PIDD2APP'}],'objects':[],
             'generation':str(root),'files':{},'source_release':gold.digest(source),'query_release':gold.digest(query)}
    state={'binding':binding,'status':'WRITE_UNCONFIRMED','deadline':100,'source':{'document':{'rows':2}},'query':{},
           'pending':{'section':'source','table':'DOC_VER','rows':1}}
    path=directory/'state.json';path.write_text(json.dumps(state))
    original=path.read_bytes()
    row={'MNFST_HASH_VALU':'v','DOC_ID':'a','DOC_NAME':'name','DOC_HASH_VALU':'a'*64,'DOC_ADDN_IFMN_CTNT':'{"real":"backup"}'}
    data={'DOC_VER':[copy.deepcopy(row),{**row,'MNFST_HASH_VALU':'OTHER'}],'DOC_UNIT':[],'DOC_BLK':[]}
    flags={'deletes':0,'response_loss':False,'published':False,'foreign':False,'crash_after_new_state':False}
    class DB:
        def query(self,sql,**kwargs):
            if 'SYS_CONTEXT' in sql:return binding['database']
            if 'ALL_CONSTRAINTS' in sql:return [{'OWNER':'OTHER'}] if flags['foreign'] else []
            return [{'N':1 if flags['published'] else 0}]
        def block(self,sql,binds,rollback=False):
            key=next(k for k in reset.SOURCE_KEYS if contract.table(k) in sql)
            payload=json.loads(next(v for n,v,t in binds if n=='payload'))
            names=[n for n,c in contract.tables[key]['columns'].items() if not c['default']]
            rows=[{name:r.get('c'+str(i)) for i,name in enumerate(names)} for r in payload]
            keys=contract.tables[key]['primary_key']
            pk=lambda r:tuple(r[n] for n in keys)
            found={pk(r):r for r in data[key]}
            for r in rows:
                actual=found.get(pk(r))
                if actual is not None and actual!=r:raise ValueError('BACKUP_CONTENT_CHANGED')
                if rollback and actual is None:raise ValueError('BACKUP_VERIFY_MISSING')
            if 'DELETE FROM ' in sql:
                ids={pk(r) for r in rows};data[key]=[r for r in data[key] if pk(r) not in ids]
                flags['deletes']+=1
                if flags['response_loss']:
                    flags['response_loss']=False;raise RuntimeError('commit acknowledgement lost')
    db=DB()
    def atomic(p,value):
        p.write_text(json.dumps(value))
        if p==path and value.get('reset_id') and flags['crash_after_new_state']:
            flags['crash_after_new_state']=False;raise RuntimeError('crash after new state durable')
    loader=types.SimpleNamespace(Contract=lambda p:contract,Database=lambda e:db,
        read=lambda p:json.loads(p.read_text()),atomic=atomic,digest=gold.digest,canonical=gold.canonical,
        verify_code=lambda:'code',object_binding=lambda *a:[],resource_check=lambda p:None,
        inputs=lambda *a:(root,{},source,query,{}))
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **k:None))
    monkeypatch.setattr(contract,'preflight',lambda *a:None)
    monkeypatch.setattr(reset,'source_count',lambda db,c,k,v:sum(r['MNFST_HASH_VALU']==v for r in data[k]))
    def pages(db,c,k,v):
        rows=copy.deepcopy([r for r in data[k] if r['MNFST_HASH_VALU']==v])
        for start in range(0,len(rows),20):yield rows[start:start+20]
    monkeypatch.setattr(reset,'source_batches',pages)
    return types.SimpleNamespace(loader=loader,package=package,old=old,directory=directory,path=path,
                                 original=original,data=data,flags=flags,row=row)


def run(work):reset.reset_if_needed(work.loader,work.package,work.old)


def test_reset_scope_backup_new_state_and_no_repeat(work):
    run(work)
    assert [r['MNFST_HASH_VALU'] for r in work.data['DOC_VER']]==['OTHER']
    fresh=json.loads(work.path.read_text());assert fresh['status']=='NEW' and fresh['pending'] is None
    assert fresh['deadline']>100 and fresh['source']=={}
    original=next((work.directory/'reset-backups').glob('*/old-state.json'))
    assert original.read_bytes()==work.original
    manifest=json.loads(next((work.directory/'reset-backups').glob('*/manifest.json')).read_text())
    entry=manifest['batches'][0]
    assert reset.load_backup(original.parent/entry['path'],entry['sha256'])==[work.row]
    work.data['DOC_VER'].append(copy.deepcopy(work.row))  # Newly reloaded data must survive another click.
    previous=work.flags['deletes'];run(work)
    assert work.flags['deletes']==previous and len(work.data['DOC_VER'])==2


def test_lost_commit_response_reconciles_without_resetting_old_state_early(work):
    work.flags['response_loss']=True
    with pytest.raises(RuntimeError):run(work)
    assert work.path.read_bytes()==work.original
    assert all(r['MNFST_HASH_VALU']=='OTHER' for r in work.data['DOC_VER'])
    run(work)
    assert json.loads(work.path.read_text())['status']=='NEW'


def test_crash_after_new_state_does_not_delete_new_data(work):
    work.flags['crash_after_new_state']=True
    with pytest.raises(RuntimeError):run(work)
    work.data['DOC_VER'].append(copy.deepcopy(work.row));previous=work.flags['deletes']
    run(work)
    assert work.flags['deletes']==previous and len(work.data['DOC_VER'])==2


@pytest.mark.parametrize('case',['published','foreign','later_state','vector','wrong_generation','too_many'])
def test_outside_scope_stops_before_any_delete(work,case,monkeypatch):
    if case in {'published','foreign'}:work.flags[case]=True
    elif case=='later_state':
        state=json.loads(work.path.read_text());state['query']={'a':{'rows':1}};work.path.write_text(json.dumps(state))
    elif case=='vector':
        folder=work.directory/'vectors';folder.mkdir();(folder/'history').write_text('retained')
    elif case=='wrong_generation':
        state=json.loads(work.path.read_text());state['binding']['generation']='other';work.path.write_text(json.dumps(state))
    else:monkeypatch.setattr(reset,'source_count',lambda *a:100001)
    with pytest.raises(ValueError):run(work)
    assert work.flags['deletes']==0 and len(work.data['DOC_VER'])==2


def test_corrupt_backup_prevents_resumed_deletion(work):
    work.flags['response_loss']=True
    with pytest.raises(RuntimeError):run(work)
    path=next((work.directory/'reset-backups').glob('*/snapshot-*/*.gz'));path.write_bytes(b'corrupt')
    previous=work.flags['deletes']
    with pytest.raises(ValueError,match='HASH_CHANGED'):run(work)
    assert work.flags['deletes']==previous


def test_unbacked_rows_prevent_new_state(work):
    original=work.loader.Database(None).block
    def changed(*args,**kwargs):
        result=original(*args,**kwargs)
        if 'DELETE FROM' in args[0]:work.data['DOC_VER'].append({**work.row,'DOC_ID':'unbacked'})
        return result
    work.loader.Database(None).block=changed
    with pytest.raises(ValueError,match='UNBACKED_ROWS'):run(work)
    assert work.path.read_bytes()==work.original


def test_progress_restarts_measurement_after_reset(work):
    from progress_display import Display
    view=Display(work.old,work.loader.Contract(None).sha256,'load')
    view.totals={'source':10,'query':20}
    view.render()
    view.baselines={'source':(0,1000)}
    run(work)
    text=view.render()
    assert view.baselines=={} and '0 / 10행' in text
