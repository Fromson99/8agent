"""Verify the smaller final transfer ZIP preserves tested bytes and executes."""
import base64,gzip,hashlib,io,json,os,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path
from build import H,R,NAME,sha,enc

def main():
    old=json.loads((H/'TESTED_PACKAGE_BINDING.json').read_bytes());new=json.loads((H/'PACKAGE_BINDING.json').read_bytes())
    assert new['runtime_sha256']==old['runtime_sha256']
    for n in (NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt'):
        assert new['files'][n]['sha256']==old['files'][n]['sha256']
    with zipfile.ZipFile(H/(NAME+'.zip')) as z:
        assert z.testzip() is None
        assert z.read(NAME+'_RUN.txt')==(H/(NAME+'_RUN.txt')).read_bytes()
        assert z.read('VALIDATION.json')==(H/'VALIDATION.json').read_bytes()
    txt=(H/(NAME+'_RUN.txt')).read_text()
    raw=base64.b64decode(re.search(r"raw=base64.b64decode\('([A-Za-z0-9+/=]+)'\)",txt).group(1),validate=True)
    assert sha(raw)==new['runtime_sha256']
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        code=z.read('code.zip');assert code==(H/'code.zip').read_bytes()
    with zipfile.ZipFile(io.BytesIO(code)) as z:
        m=json.loads(z.read('CODE_MANIFEST.json'))
        assert all(sha(z.read(n))==pin for n,pin in m['main_basis']['deployment_serving_files'].items())
    previous=json.loads(gzip.decompress((H/'TEST_photo_legacy.json.gz').read_bytes()))
    root=Path(previous[0]['argv'][-1]);assert root.is_dir()
    manifest=(root/'CODE_MANIFEST.json').read_bytes();old_llm=(root/'02_BACKEND/lawrag/core/llm.py').read_bytes()
    transcripts=[]
    with tempfile.TemporaryDirectory(prefix='sealed-main-full-') as t:
        transfer=Path(t);shutil.copyfile(H/(NAME+'.zip'),transfer/(NAME+'.zip'))
        env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GENOS_PYTHON_DIR':str(R/'.venv/bin'),
             'GENOS_DEV_ROOT':str(root),'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','PYTHONDONTWRITEBYTECODE':'1'}
        env.pop('GENOS_GENERATION',None)
        commands=[['python3','-m','zipfile','-e','./'+NAME+'.zip','./'+NAME]]
        commands.extend([['bash','./'+NAME+'/'+NAME+'_RUN.txt',action] for action in ('check','install','status','undo')])
        for args in commands:
            result=subprocess.run(args,cwd=transfer,env=env,text=True,capture_output=True,timeout=240)
            transcripts.append({'argv':args,'cwd':str(transfer),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
            (H/'FINAL_EXECUTION.json.gz').write_bytes(gzip.compress(enc(transcripts),mtime=0))
            assert result.returncode==0,result.stdout+result.stderr
        state=json.loads((transfer/'main-full-r1-state/STATUS.json').read_bytes())
        gate=next(json.loads(line[len('CODE_CHECK PASS '):]) for row in previous for line in row['stdout'].splitlines() if line.startswith('CODE_CHECK PASS '))
        assert state['code_zip_sha256']==gate['code_zip_sha256']
        assert (root/'CODE_MANIFEST.json').read_bytes()==manifest
        assert (root/'02_BACKEND/lawrag/core/llm.py').read_bytes()==old_llm
    active=(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()
    record={'status':'PASS','final_archive_sha256':sha((H/(NAME+'.zip')).read_bytes()),'run_sha256':sha((H/(NAME+'_RUN.txt')).read_bytes()),
            'runtime_identical_to_full_matrix':True,'deployed_code_zip_identical_to_tested_committed_gate':True,
            'final_zip_commands':len(transcripts),'exact_rollback':True,'source_pointer_still_selected':active==(H/'SOURCE_POINTER.json').read_bytes(),
            'genos_field_verified':False,'models_called':0,'output_files':new['files'],'execution_transcript_sha256':sha((H/'FINAL_EXECUTION.json.gz').read_bytes())}
    (H/'FINAL_VERIFICATION.json').write_bytes(enc(record));print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':main()
