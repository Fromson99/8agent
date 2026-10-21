"""Nonseekable legacy SHA-part streams and exact Dataiku R2 delivery."""
import hashlib
import io as memory
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import pytest
from lawrag.pipeline import oracle_legacy_parts as p, oracle_existing_zip as legacy, oracle_full_package as fullpack
from semantic_runtime import oracle_dp_io as io
from test_oracle_existing_zip import make_zip
from test_oracle_full_package import full
from test_compact_v2_rag import structured_generation

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_existing_zip_20261020_r2'
NAME='LEGAL_ORACLE_EXISTING_ZIP_20261020_R2'
sha=lambda b:hashlib.sha256(b).hexdigest()


def bundle(raw=None):
    if raw is None:
        b=memory.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('test.txt',b'content'*500)
        raw=b.getvalue()
    chunks=[raw[i:i+1000] for i in range(0,len(raw),1000)]
    files={f'old.zip.part{i:06d}':b for i,b in enumerate(chunks)}
    files['ORIGINAL.sha256']=(sha(raw)+'  old.zip\n').encode()
    files['PARTS.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in files.items() if '.part' in n).encode()
    return raw,files


class Nonseekable(memory.BytesIO):
    def read(self,n=-1):assert 0<n<=1024**2;return super().read(min(n,127))
    def seek(self,*a):raise AssertionError('remote stream is nonseekable')


class Folder:
    def __init__(self,files):self.files=files;self.calls=[]
    def open(self,name):
        self.calls.append(name);return Nonseekable(self.files[name.lstrip('/')])
    def names(self):return ['/'+n for n in self.files]


def join(folder,out,**kw):return p.join_parts(folder.open,folder.names(),out,**kw)


def test_normal_short_reads_renamed_checksums_and_reuse(tmp_path):
    raw,files=bundle();files['ORIGINAL (4).sha256']=files.pop('ORIGINAL.sha256').decode().replace('\n','\r\n').encode('utf-16')
    files['PARTS (1).sha256']=files['PARTS.sha256'];folder=Folder(files)
    ready=p.inspect_parts(folder.open,folder.names());assert ready['part_count']==4
    assert not any('.part' in n for n in folder.calls)
    target=Path(join(folder,tmp_path/'out'));assert target.read_bytes()==raw
    deadline=json.loads((tmp_path/'out/legacy-join-state.json').read_text())['deadline']
    folder.calls=[];assert join(folder,tmp_path/'out')==str(target)
    assert not any('.part' in n for n in folder.calls)
    assert json.loads((tmp_path/'out/legacy-join-state.json').read_text())['deadline']==deadline


def test_one_appended_byte_recovery_preserves_uploads(tmp_path):
    raw,files=bundle();n='old.zip.part000001';files[n]+=b'X';folder=Folder(files)
    assert Path(join(folder,tmp_path/'out')).read_bytes()==raw
    assert files[n].endswith(b'X')
    state=json.loads((tmp_path/'out/legacy-join-state.json').read_text())
    assert state['whole_sha256_verified'] and state['tail_recovery']['part']==n


@pytest.mark.parametrize('damage',['missing','extra','gap','duplicate','path','ambiguous','middle','two_bytes','two_parts','whole'])
def test_reject_bad_parts_without_completed_zip(tmp_path,damage):
    raw,files=bundle();n='old.zip.part000001'
    if damage=='missing':files.pop(n)
    if damage=='extra':files['old.zip.part000099']=b'bad'
    if damage=='gap':files['PARTS.sha256']=files['PARTS.sha256'].replace(b'part000001',b'part000009')
    if damage=='duplicate':files['PARTS.sha256']+=files['PARTS.sha256'].splitlines(keepends=True)[0]
    if damage=='path':files['PARTS.sha256']=files['PARTS.sha256'].replace(b'old.zip.part000000',b'../old.zip.part000000')
    if damage=='ambiguous':files['ORIGINAL (2).sha256']=b'0'*64+b'  old.zip\n'
    if damage=='middle':files[n]=b'!'+files[n][1:]
    if damage=='two_bytes':files[n]+=b'XX'
    if damage=='two_parts':files[n]+=b'X';files['old.zip.part000002']+=b'X'
    if damage=='whole':files['ORIGINAL.sha256']=b'0'*64+b'  old.zip\n';files[n]+=b'X'
    folder=Folder(files)
    with pytest.raises(io.DPError):join(folder,tmp_path/'out')
    assert not (tmp_path/'out/legacy-verified.zip').exists()
    if damage in {'missing','extra','gap','duplicate','path','ambiguous'}:assert not any('.part' in n for n in folder.calls)


def test_explicit_metadata_selection(tmp_path):
    raw,files=bundle();files['ORIGINAL (2).sha256']=b'0'*64+b'  old.zip\n';folder=Folder(files)
    assert Path(join(folder,tmp_path/'out',original_file='ORIGINAL.sha256')).read_bytes()==raw


def test_interrupted_merge_binding_deadline_and_conflict(tmp_path):
    raw,files=bundle();folder=Folder(files);out=tmp_path/'out';original=folder.open
    def fail(name):
        if name.endswith('part000002'):raise TimeoutError('simulated stream failure')
        return original(name)
    folder.open=fail
    with pytest.raises(TimeoutError):join(folder,out)
    saved=json.loads((out/'legacy-join-state.json').read_text());assert saved['status']=='FAILED'
    partial=Path(saved['partial_output']);assert partial.exists()
    folder.open=original;assert Path(join(folder,out)).read_bytes()==raw and partial.exists()
    assert json.loads((out/'legacy-join-state.json').read_text())['deadline']==saved['deadline']
    with pytest.raises(io.DPError,match='JOIN_BINDING'):join(folder,out,binding='other')
    (out/'legacy-verified.zip').write_bytes(b'preserve')
    with pytest.raises(io.DPError,match='ZIP_CONFLICT'):join(folder,out)
    saved['deadline']=1;io.atomic_json(out/'legacy-join-state.json',saved)
    with pytest.raises(io.BudgetPause):join(folder,out)


def test_exact_delivered_notebook_inspect_merge_restore(structured_generation,tmp_path):
    archive=make_zip(structured_generation,tmp_path);raw,files=bundle(archive.read_bytes());files['old.zip.part000001']+=b'X'
    files['ORIGINAL (4).sha256']=files.pop('ORIGINAL.sha256')
    upload=tmp_path/'managed';upload.mkdir()
    for n,b in files.items():(upload/n).write_bytes(b)
    shutil.copyfile(D/(NAME+'.zip'),upload/(NAME+'.zip'))
    text=(D/'package/DATAIKU_EXISTING_ZIP_IMPORT_RUN.txt').read_text().replace('FOLDER_ID = "여기에_Managed_Folder_ID"','FOLDER_ID = "fixture"')
    shim='''import sys,types\nfrom pathlib import Path\nm=types.ModuleType('dataiku')\nclass Folder:\n def __init__(self,ident):assert ident=='fixture'\n def get_download_stream(self,name):return (Path(%r)/name.lstrip('/')).open('rb')\n def list_paths_in_partition(self):return ['/'+p.name for p in Path(%r).iterdir()]\nm.Folder=Folder\nsys.modules['dataiku']=m\n'''%(str(upload),str(upload))
    for action in ['inspect','merge','restore']:
        runner=tmp_path/'notebook.py';runner.write_text(shim+text.replace('ACTION = "inspect"','ACTION = '+repr(action)))
        r=subprocess.run([sys.executable,str(runner)],cwd=tmp_path,capture_output=True,text=True)
        assert r.returncode==0,r.stdout+r.stderr
    assert fullpack.verify_restored(tmp_path/'legal-existing-zip-r2-work/restored')[1]['dataset_version']==io.file_sha(structured_generation/'manifest.json')
    assert not (tmp_path/'legal-existing-zip-r2-work/parts').exists()


def test_parts_restore_to_existing_oracle(full,tmp_path):
    prior=fullpack.import_generation(full[0],full[4],target_binding='fixture',directory=tmp_path/'prior',action='publish')
    full[2].rows.clear();full[2].releases.clear();before=full[1].writes
    raw,files=bundle(make_zip(full[7],tmp_path).read_bytes());folder=Folder(files)
    archive=join(folder,tmp_path/'joined');legacy.restore(archive,tmp_path/'restored')
    result=legacy.import_generation(full[0],tmp_path/'restored',target_binding='fixture',directory=tmp_path/'new-import',action='publish')
    assert result==prior and full[1].writes==before
    assert not full[2].active and not full[2].states
