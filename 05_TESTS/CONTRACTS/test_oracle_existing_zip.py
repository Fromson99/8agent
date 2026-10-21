"""Historical archive -> same full importer, including prepopulated Oracle and exact handoff."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full
from lawrag.pipeline import oracle_existing_zip as legacy, oracle_full_package as pack
from semantic_runtime import oracle_dp_io as io

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_existing_zip_20261020_r1'
NAME='LEGAL_ORACLE_EXISTING_ZIP_20261020_R1'
GEN='/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'


def make_zip(root,tmp_path,*,damage=None):
    archive=tmp_path/'old.zip';data={};files={}
    for p in root.rglob('*'):
        if p.is_file():
            source=GEN+'/'+p.relative_to(root).as_posix();body=p.read_bytes()
            files[source]={'kind':'file','bytes':len(body),'sha256':io.file_sha(p)}
            data['old/payload/'+source.lstrip('/')]=body
    files['/nfs-root/diamo/8-agent/runtime/cases.sqlite']={'kind':'file','bytes':4,'sha256':'0'*64}
    data['old/payload/nfs-root/diamo/8-agent/runtime/cases.sqlite']=b'old!'
    meta={'schema_version':'genos-rag-data-live-v2','generation':GEN,'archive_restore_eligible':True,
          'generation_manifest_sha256':io.file_sha(root/'manifest.json'),'files':files}
    if damage=='ineligible':meta['archive_restore_eligible']=False
    if damage=='binding':meta['generation_manifest_sha256']='0'*64
    if damage=='content':data['old/payload/'+GEN.lstrip('/')+'/store.sqlite']=b'!'*files[GEN+'/store.sqlite']['bytes']
    data['old/DATA_MANIFEST.json']=json.dumps(meta).encode()
    data['old/RESTORE.sh']=b'never execute this file'
    if damage=='traversal':data['old/../escape']=b'bad'
    if damage=='undeclared':data['old/payload/'+GEN.lstrip('/')+'/store.sqlite-wal']=b'bad'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in data.items():z.writestr(n,b)
        if damage=='duplicate':z.writestr('old/RESTORE.sh',b'bad')
    return archive


def test_existing_data_reuse_missing_queries_and_fresh_job(full,tmp_path):
    # Populate existing source/assets as a previous independent notebook would.
    old=pack.import_generation(full[0],full[4],target_binding='synthetic',directory=tmp_path/'prior',action='publish')
    full[2].rows.clear();full[2].releases.clear()
    source_writes=full[1].writes
    archive=make_zip(full[7],tmp_path);out=tmp_path/'legacy'
    result=legacy.restore(archive,out)
    assert result['status']=='RESTORED_AND_VERIFIED'
    assert not (out/'runtime').exists() and not list(out.rglob('RESTORE.sh'))
    args=dict(target_binding='synthetic',directory=tmp_path/'newjob',action='publish')
    result=legacy.import_generation(full[0],out,**args)
    assert result['status']=='FULL_DATA_VERIFIED'
    assert result['source_release_id']==old['source_release_id']
    assert full[1].writes==source_writes and full[2].rows
    before=(full[1].writes,full[2].writes)
    assert legacy.import_generation(full[0],out,**args)==result
    assert (full[1].writes,full[2].writes)==before
    row_snapshot=dict(full[2].rows)
    args['directory']=tmp_path/'anotherjob'
    assert legacy.import_generation(full[0],out,**args)==result
    # Query SQL is guarded INSERT-if-absent plus content comparison. The mock's
    # writes counter counts SQL attempts, including no-op guarded statements.
    assert full[1].writes==before[0] and full[2].rows==row_snapshot
    assert not full[2].active and not full[2].states


@pytest.mark.parametrize('damage',['ineligible','binding','content','traversal','undeclared','duplicate'])
def test_bad_zip_rejected_before_completion(structured_generation,tmp_path,damage):
    archive=make_zip(structured_generation,tmp_path,damage=damage)
    with pytest.raises(io.DPError):legacy.restore(archive,tmp_path/'out')
    assert not (tmp_path/'out/full-manifest.json').exists()


def test_resume_conflict_deadline_and_expected_hash(structured_generation,tmp_path,monkeypatch):
    archive=make_zip(structured_generation,tmp_path);out=tmp_path/'out';original=pack._copy;calls=[0]
    def fail(*a,**kw):
        calls[0]+=1
        if calls[0]==2:raise io.DPError('INJECTED')
        return original(*a,**kw)
    monkeypatch.setattr(pack,'_copy',fail)
    with pytest.raises(io.DPError,match='INJECTED'):legacy.restore(archive,out)
    state=pack.bounded_json(out/'restore-state.json')
    monkeypatch.setattr(pack,'_copy',original)
    assert legacy.restore(archive,out)['status']=='RESTORED_AND_VERIFIED'
    assert pack.bounded_json(out/'restore-state.json')['deadline']==state['deadline']
    assert legacy.restore(archive,out)['status']=='RESTORED_AND_VERIFIED'
    with pytest.raises(io.DPError,match='ZIP_HASH'):legacy.restore(archive,tmp_path/'other',expected_sha='0'*64)
    with (out/'generation/store.sqlite').open('ab') as f:f.write(b'bad')
    with pytest.raises(io.DPError,match='RESTORE_CONFLICT'):legacy.restore(archive,out)
    state['deadline']=1;io.atomic_json(out/'restore-state.json',state)
    with pytest.raises(io.BudgetPause):legacy.restore(archive,out)


def test_split_join_strict_roundtrip(structured_generation,tmp_path):
    archive=make_zip(structured_generation,tmp_path);parts=tmp_path/'parts'
    value=legacy.split(archive,parts,chunk_bytes=4000)
    assert legacy.split(archive,parts,chunk_bytes=4000)==value
    joined=legacy.join(parts,tmp_path/'join');assert Path(joined).read_bytes()==archive.read_bytes()
    assert legacy.join(parts,tmp_path/'join')==joined
    p=parts/value['parts'][0]['name'];b=p.read_bytes();p.write_bytes(bytes([b[0]^1])+b[1:])
    with pytest.raises(io.DPError,match='PART_HASH'):legacy.join(parts,tmp_path/'badjoin')


@pytest.mark.parametrize('mode',['zip','parts'])
def test_delivered_notebook_restore_and_shell(structured_generation,tmp_path,mode):
    archive=make_zip(structured_generation,tmp_path);upload=tmp_path/'managed';upload.mkdir()
    shutil.copyfile(archive,upload/'old.zip');shutil.copyfile(DELIVERY/(NAME+'.zip'),upload/(NAME+'.zip'))
    proc=subprocess.run(['bash',str(DELIVERY/'package/ZIP_TRANSFER_RUN.txt'),'split','--archive',str(archive),'--output',str(tmp_path/'parts')],
                         cwd=tmp_path,env={**os.environ,'PATH':str(ROOT/'.venv/bin')+':'+os.environ['PATH']},capture_output=True,text=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    for p in (tmp_path/'parts').glob('*'):
        if p.name.startswith('data.zip.part') or p.name=='parts-manifest.json':shutil.copyfile(p,upload/p.name)
    text=(DELIVERY/'package/DATAIKU_EXISTING_ZIP_IMPORT_RUN.txt').read_text().replace('FOLDER_ID = "여기에_Managed_Folder_ID"','FOLDER_ID = "fixture"')
    text=text.replace('ACTION = "inspect"','ACTION = "restore"').replace('genos-rag-data-20261007T002029Z-7c0b050f_verified.zip','old.zip').replace('INPUT_MODE = "zip"','INPUT_MODE = '+repr(mode))
    shim='''import sys,types\nfrom pathlib import Path\nm=types.ModuleType('dataiku')\nclass Folder:\n def __init__(self,ident):assert ident=='fixture'\n def get_download_stream(self,name):return (Path(%r)/name.lstrip('/')).open('rb')\nm.Folder=Folder\nsys.modules['dataiku']=m\n'''%str(upload)
    runner=tmp_path/'notebook.py';runner.write_text(shim+text)
    proc=subprocess.run([sys.executable,str(runner)],cwd=tmp_path,capture_output=True,text=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert pack.verify_restored(tmp_path/'legal-existing-zip-work/restored')[1]['dataset_version']==io.file_sha(structured_generation/'manifest.json')


def test_partial_source_and_query_rows_fill_only_missing(full,tmp_path):
    prior=pack.import_generation(full[0],full[4],target_binding='synthetic',directory=tmp_path/'prior',action='publish')
    full[1].data['document'].pop(next(iter(full[1].data['document'])))
    full[2].rows.pop(next(iter(full[2].rows)))
    retained={k:dict(v) for k,v in full[2].rows.items()}
    archive=make_zip(full[7],tmp_path);legacy.restore(archive,tmp_path/'new')
    result=legacy.import_generation(full[0],tmp_path/'new',target_binding='synthetic',directory=tmp_path/'job',action='publish')
    assert result==prior
    assert all(full[2].rows[k]==v for k,v in retained.items())
    assert len(full[2].rows)==prior['query_rows']


def test_conflicting_source_stops_without_overwrite(full,tmp_path):
    pack.import_generation(full[0],full[4],target_binding='synthetic',directory=tmp_path/'prior',action='publish')
    row=next(iter(full[1].data['document'].values()));row['NAME']='conflicting target'
    before=(full[1].writes,full[2].writes)
    archive=make_zip(full[7],tmp_path);legacy.restore(archive,tmp_path/'new')
    with pytest.raises(io.DPError):
        legacy.import_generation(full[0],tmp_path/'new',target_binding='synthetic',directory=tmp_path/'job',action='publish')
    assert row['NAME']=='conflicting target' and (full[1].writes,full[2].writes)==before
