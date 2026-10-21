"""Verify final ZIP bytes and execute the exact delivered TXT after metadata sealing."""
import base64,gzip,io,json,os,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path
from build import H,R,NAME,sha,enc

old=json.loads((H/'TESTED_PACKAGE_BINDING.json').read_bytes())
new=json.loads((H/'PACKAGE_BINDING.json').read_bytes())
assert new['runtime_sha256']==old['runtime_sha256']
for name in (NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt'):
    assert new['files'][name]['sha256']==old['files'][name]['sha256']
with zipfile.ZipFile(H/(NAME+'.zip')) as z:
    assert z.testzip() is None
    for n in (NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt','GUIDE_UTF8.txt','VALIDATION.json'):
        assert z.read(n)==(H/n).read_bytes(),n
    assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
txt=(H/(NAME+'_RUN.txt')).read_text()
raw=base64.b64decode(re.search(r"raw=base64.b64decode\('([A-Za-z0-9+/=]+)'\)",txt).group(1),validate=True)
assert sha(raw)==new['runtime_sha256']
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    assert z.read('code.zip')==(H/'code.zip').read_bytes()
passed=json.loads((H/'PASS_prior_main84.json').read_bytes());root=Path(passed['code_root'])
original=(root/'CODE_MANIFEST.json').read_bytes();transcripts=[]
with tempfile.TemporaryDirectory(prefix='final-transfer-',dir=H) as temp:
    transfer=Path(temp);shutil.copyfile(H/(NAME+'.zip'),transfer/(NAME+'.zip'))
    env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GENOS_PYTHON_DIR':str(R/'.venv/bin'),
         'GENOS_DEV_ROOT':str(root),'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','PYTHONDONTWRITEBYTECODE':'1'}
    env.pop('GENOS_GENERATION',None)
    commands=[['python3','-m','zipfile','-e','./'+NAME+'.zip','./'+NAME]]
    commands += [['bash','./'+NAME+'/'+NAME+'_RUN.txt',action] for action in ('check','apply','status','undo')]
    for args in commands:
        result=subprocess.run(args,cwd=transfer,env=env,text=True,capture_output=True,timeout=240)
        transcripts.append({'argv':args,'cwd':str(transfer),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (H/'FINAL_EXECUTION.json.gz').write_bytes(gzip.compress(enc(transcripts),mtime=0))
        assert result.returncode==0,result.stdout+result.stderr
    state=json.loads((transfer/'main87-patch-r1-state/STATUS.json').read_bytes())
    assert state['code_zip_sha256']==passed['installed_archive']
    assert (root/'CODE_MANIFEST.json').read_bytes()==original
assert (R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()==(H/'SOURCE_POINTER.json').read_bytes()
record={'status':'PASS','archive_sha256':sha((H/(NAME+'.zip')).read_bytes()),
        'run_sha256':sha((H/(NAME+'_RUN.txt')).read_bytes()),'commands':len(transcripts),
        'runtime_identical_to_tested_matrix':True,'applied_code_matches_committed_gate':True,
        'exact_rollback':True,'source_pointer_still_selected':True,'genos_field_verified':False,
        'model_calls':0,'execution_transcript_sha256':sha((H/'FINAL_EXECUTION.json.gz').read_bytes())}
(H/'FINAL_VERIFICATION.json').write_bytes(enc(record))
names=[NAME+'.zip',NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt','GUIDE_UTF8.txt',
       'VALIDATION.json','FINAL_VERIFICATION.json','SOURCE_BINDING.json','CODE_MANIFEST.json','PACKAGE_BINDING.json','code.zip']
rows={n:{'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in names}
(H/'SHA256SUMS.txt').write_text(''.join(x['sha256']+'  '+n+'\n' for n,x in rows.items() if n not in ('code.zip','PACKAGE_BINDING.json','SOURCE_BINDING.json','CODE_MANIFEST.json')))
rows['SHA256SUMS.txt']={'sha256':sha((H/'SHA256SUMS.txt').read_bytes()),'bytes':(H/'SHA256SUMS.txt').stat().st_size}
(H/'SEALED.json').write_bytes(enc({'version':NAME,'files':rows,'field_status':'NOT_VERIFIED'}))
print(json.dumps(record,ensure_ascii=False))
