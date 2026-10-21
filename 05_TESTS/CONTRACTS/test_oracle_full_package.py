"""Full generation transport to empty Oracle fixture, exact delivered entrypoints."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_dp_runtime import AssetOracle
from test_oracle_query_catalog import Oracle as QueryOracle
from test_oracle_query_schema import SchemaOracle
from lawrag.pipeline import oracle_full_package as pack
from semantic_runtime import oracle_dp_io as io, oracle_query_catalog as q

ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_full_parts_20261020_r1/package'


@pytest.fixture
def full(structured_generation, tmp_path):
    output = tmp_path/'export'
    result = pack.export(structured_generation, output, chunk_bytes=4000)
    restored = tmp_path/'restored'; pack.restore(output/'download', restored)
    source, query, schema = AssetOracle(), QueryOracle(), SchemaOracle()
    schema.created = {s.split()[2].split('.')[1] for s in q.DDL}
    class Client:
        SQL_PATH = '/sql'
        def request(self, method, path, json):
            text = json['statementText']
            if 'WHERE 1=0' in text:
                return {'items':[{'resultSet':{'items':[], 'hasMore':False, 'offset':0}}]}
            if 'ALL_' in text and ':owner' in text: target = schema
            elif 'LEGAL_RAG_QUERY_' in text: target = query
            else: target = source
            return target.request(method, path, json)
    return Client(), source, query, schema, restored, output, result, structured_generation


def call(full, tmp_path, action='publish'):
    return pack.import_generation(full[0], full[4], target_binding='synthetic', directory=tmp_path/'import', action=action)


def test_full_roundtrip_empty_target_repeated_publish_and_readonly_status(full, tmp_path):
    assert call(full,tmp_path,'check')['status']=='READY_FOR_FULL_IMPORT'
    assert full[1].writes == full[2].writes == 0
    result=call(full,tmp_path)
    assert result['status']=='FULL_DATA_VERIFIED'
    assert {k:len(v) for k,v in full[1].data.items()}==result['source_counts']
    assert full[1].parts and full[1].releases and full[2].rows and full[2].releases
    writes=(full[1].writes,full[2].writes)
    state=pack.bounded_json(tmp_path/'import/full-state.json')
    assert call(full,tmp_path,'status')==result
    assert call(full,tmp_path)==result
    assert (full[1].writes,full[2].writes)==writes
    assert pack.bounded_json(tmp_path/'import/full-state.json')['deadline']==state['deadline']
    assert not full[2].active and not full[2].states


@pytest.mark.parametrize('stage',['source','assets','query'])
def test_write_ack_lost_resume(full,tmp_path,stage,monkeypatch):
    if stage=='source': full[1].mode='after_timeout'
    elif stage=='query': full[2].fail_after_write=True
    else:
        original=pack.source_publish.publish
        def publish(*args,**kwargs):
            full[1].mode='after_timeout'
            monkeypatch.setattr(pack.source_publish,'publish',original)
            return original(*args,**kwargs)
        monkeypatch.setattr(pack.source_publish,'publish',publish)
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'): call(full,tmp_path)
    state=pack.bounded_json(tmp_path/'import/full-state.json')
    assert state['status']=='FAILED'
    assert call(full,tmp_path)['status']=='FULL_DATA_VERIFIED'
    assert state['deadline']==pack.bounded_json(tmp_path/'import/full-state.json')['deadline']


@pytest.mark.parametrize('damage',['append','missing','duplicate','traversal','extra'])
def test_strict_parts(full,tmp_path,damage):
    parts=full[5]/'download'; path=parts/'parts-manifest.json';value=pack.bounded_json(path);name=value['parts'][0]['name']
    if damage=='append':
        with (parts/name).open('ab') as f:f.write(b'X')
    elif damage=='missing':(parts/name).rename(parts/'saved')
    elif damage=='duplicate':value['parts'].append(value['parts'][0])
    elif damage=='traversal':value['files']['../escape']={'bytes':0,'sha256':'0'*64}
    else:(parts/(pack.ARCHIVE+'.part999999')).write_bytes(b'X')
    io.atomic_json(path,value)
    with pytest.raises(io.DPError): pack.restore(parts,tmp_path/'bad')
    assert not (tmp_path/'bad/full-manifest.json').exists()


@pytest.mark.parametrize('damage',['source','asset','query','extraquery'])
def test_final_readback_detects_remote_tamper(full,tmp_path,damage):
    call(full,tmp_path)
    if damage=='source':full[1].data['document'].clear()
    elif damage=='asset':full[1].parts.clear()
    elif damage=='query':full[2].rows.pop(next(iter(full[2].rows)))
    else:
        key=next(iter(full[2].rows));full[2].rows[(key[0],'unlisted','0'*64)]=full[2].rows[key]
    writes=(full[1].writes,full[2].writes)
    with pytest.raises(io.DPError):call(full,tmp_path,'status')
    assert (full[1].writes,full[2].writes)==writes
    assert pack.bounded_json(tmp_path/'import/full-state.json')['status']=='FAILED'


def test_binding_deadline_schema_and_lock(full,tmp_path):
    call(full,tmp_path,'check')
    with pytest.raises(io.DPError,match='IMPORT_BINDING'):
        pack.import_generation(full[0],full[4],target_binding='other',directory=tmp_path/'import')
    path=tmp_path/'import/full-state.json';state=pack.bounded_json(path);state['deadline']=1;io.atomic_json(path,state)
    with pytest.raises(io.BudgetPause):call(full,tmp_path)
    assert not full[1].writes and not full[2].writes
    with pack.transport.job(tmp_path/'locked'):
        with pytest.raises(io.DPError,match='IN_PROGRESS'):pack.export(full[7],tmp_path/'locked')
    full[3].created.remove('LEGAL_Q_ROW_LOOKUP')
    with pytest.raises(io.DPError,match='QUERY_SCHEMA'):
        pack.import_generation(full[0],full[4],target_binding='synthetic',directory=tmp_path/'missing-schema')


def test_exact_bash_and_notebook_restore(full,tmp_path):
    output=tmp_path/'cli'
    proc=subprocess.run(['bash',str(DELIVERY/'CODESPACE_FULL_50MB_RUN.txt'),'export','--generation',str(full[7]),'--output',str(output)],
        cwd=tmp_path,text=True,capture_output=True,env={**os.environ,'PATH':str(ROOT/'.venv/bin')+':'+os.environ['PATH']})
    assert proc.returncode==0,proc.stdout+proc.stderr
    upload=tmp_path/'managed';upload.mkdir()
    archive='LEGAL_ORACLE_FULL_PARTS_20261020_R1.zip'
    shutil.copyfile(DELIVERY.parent/archive,upload/archive)
    for f in (output/'download').iterdir():shutil.copyfile(f,upload/f.name)
    source=(DELIVERY/'DATAIKU_FULL_IMPORT_RUN.txt').read_text().replace('FOLDER_ID = "여기에_Managed_Folder_ID"','FOLDER_ID = "fixture"')
    shim='''import sys,types\nfrom pathlib import Path\nm=types.ModuleType('dataiku')\nclass Folder:\n    def __init__(self,ident):assert ident=='fixture'\n    def get_download_stream(self,name):return (Path(%r)/name.lstrip('/')).open('rb')\nm.Folder=Folder\nsys.modules['dataiku']=m\n''' % str(upload)
    runner=tmp_path/'notebook.py';runner.write_text(shim+source)
    proc=subprocess.run([sys.executable,str(runner)],cwd=tmp_path,text=True,capture_output=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert pack.verify_restored(tmp_path/'legal-full-transfer-work/restored')[1]['source_counts']==full[6]['source_counts']


def test_original_changed_and_restored_tamper_fail_before_sql(full,tmp_path):
    with (full[4]/'generation/store.sqlite').open('ab') as f:f.write(b'X')
    with pytest.raises(io.DPError,match='RESTORE_HASH'):call(full,tmp_path)
    assert not full[1].writes and not full[2].writes
    with (full[7]/'store.sqlite').open('ab') as f:f.write(b'X')
    with pytest.raises(io.DPError):pack.export(full[7],full[5],chunk_bytes=4000)


def test_export_resume_restore_resume_and_selection(structured_generation,tmp_path,monkeypatch):
    root=structured_generation
    manifest=json.loads((root/'manifest.json').read_text())
    selection=root.parent/'SEARCH_SELECTION'/(root.name+'.json');selection.parent.mkdir(exist_ok=True)
    value={'store_sha256':manifest['store_sha256'],'manifest_sha256':io.file_sha(root/'manifest.json'),'test_marker':'preserve'}
    io.atomic_json(selection,value)
    output=tmp_path/'resume-export';original=pack._copy;calls=[0]
    def fail(*args,**kwargs):
        calls[0]+=1
        if calls[0]==2:raise io.DPError('INJECTED_INTERRUPTION')
        return original(*args,**kwargs)
    monkeypatch.setattr(pack,'_copy',fail)
    with pytest.raises(io.DPError,match='INJECTED'):pack.export(root,output)
    deadline=pack.bounded_json(output/'export-state.json')['deadline']
    assert list(output.glob('*.partial-*'))
    monkeypatch.setattr(pack,'_copy',original)
    result=pack.export(root,output)
    assert pack.export(root,output)==result
    assert pack.bounded_json(output/'export-state.json')['deadline']==deadline
    restored=tmp_path/'resume-restore';calls[0]=0;monkeypatch.setattr(pack,'_copy',fail)
    with pytest.raises(io.DPError,match='INJECTED'):pack.restore(output/'download',restored)
    monkeypatch.setattr(pack,'_copy',original)
    pack.restore(output/'download',restored)
    assert pack.bounded_json(restored/'SEARCH_SELECTION/generation.json')==value
    before=(restored/'generation/store.sqlite').stat().st_ino
    pack.restore(output/'download',restored)
    assert (restored/'generation/store.sqlite').stat().st_ino==before
