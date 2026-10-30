"""Move explicitly listed inactive test fixtures from tmpfs; preserve path and bytes."""
from pathlib import Path
import os,stat,json,hashlib,shutil,time,subprocess
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261028-memory-reclaim'
NAMES=('agent8-pod-contract-r4','agent8-pod-contract-r4-2','agent8-pod-contract-r4-final','agent8-pod-contract-sealed')
def put(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_suffix(p.suffix+'.tmp')
 with temp.open('w') as stream:
  stream.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
 temp.replace(p)
 directory=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(directory)
 finally:os.close(directory)
def memory():
 return {x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','Shmem:','SwapTotal:','SwapFree:'))}
def manifest(root):
 rows={}
 for base,dirs,files in os.walk(root,followlinks=False):
  for name in dirs+files:
   p=Path(base)/name;s=p.lstat();row={'mode':stat.S_IMODE(s.st_mode),'mtime_ns':s.st_mtime_ns}
   if stat.S_ISLNK(s.st_mode):row.update(kind='link',target=os.readlink(p))
   elif stat.S_ISDIR(s.st_mode):row.update(kind='directory')
   elif stat.S_ISREG(s.st_mode):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    row.update(kind='file',bytes=s.st_size,sha256=h)
   else:raise RuntimeError('special file; refusing '+str(p))
   assert s.st_uid==os.getuid(),'foreign owner'
   assert time.time()-s.st_mtime>3600,'recently modified file'
   rows[str(p.relative_to(root))]=row
 return rows
def active(root):
 matches=[];unreadable=[];own_user_unreadable=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit() or p.name==str(os.getpid()):continue
  try:
   same_user=p.stat().st_uid==os.getuid()
   cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
   if str(root) in cmd:matches.append({'pid':p.name,'kind':'command'})
   for fd in [p/'cwd',p/'root',*list((p/'fd').iterdir())]:
    try:t=os.readlink(fd)
    except (FileNotFoundError,ProcessLookupError):continue
    if t==str(root) or t.startswith(str(root)+'/'):matches.append({'pid':p.name,'kind':'handle'})
   if str(root)+'/' in (p/'maps').read_text():matches.append({'pid':p.name,'kind':'mapping'})
  except PermissionError:
   unreadable.append(p.name)
   # Inspected host PIDs268/272 are the session systemd and PAM managers,
   # whose protected descriptors are unrelated to these completed test workers.
   if same_user:
    comm=(p/'comm').read_text().strip()
    if (p.name,comm) not in {('268','systemd'),('272','(sd-pam)')}:own_user_unreadable.append(p.name)
  except (FileNotFoundError,ProcessLookupError):pass
 if matches or own_user_unreadable:raise RuntimeError(json.dumps({'active':matches,'same_user_unreadable':own_user_unreadable}))
 return {'active_matches':matches,'foreign_processes_unreadable':len(unreadable)}
OUT.mkdir(parents=True,exist_ok=True)
assert not (OUT/'result.json').exists(),'completed operation already exists'
before=memory();rows=[];put(OUT/'before.json',before)
for name in NAMES:
 source=Path('/tmp')/name;target=OUT/'files'/name;retired=Path('/tmp')/('.offload-verified-'+name)
 assert source.is_dir() and not source.is_symlink() and not target.exists() and not retired.exists()
 assert source.stat().st_dev!=OUT.stat().st_dev
 initial_access=active(source);before_files=manifest(source)
 print('COPY',name,len(before_files),flush=True)
 shutil.copytree(source,target,symlinks=True,copy_function=shutil.copy2)
 assert manifest(target)==before_files,'copy mismatch'
 assert manifest(source)==before_files,'source changed while copying'
 # Make archive bytes durable before deleting the tmpfs duplicate.
 subprocess.run(['sync','-f',str(target)],check=True)
 final_access=active(source)
 put(OUT/(name+'-files.json'),before_files)
 receipt={'source':str(source),'target':str(target),'files':len(before_files),'logical_bytes':sum(x.get('bytes',0) for x in before_files.values()),'initial_access':initial_access,'final_access':final_access,'sha256_and_metadata_verified':True,'before':memory()}
 put(OUT/(name+'-receipt.json'),receipt)
 source.rename(retired)
 try:source.symlink_to(target,target_is_directory=True)
 except BaseException:retired.rename(source);raise
 assert source.resolve()==target and manifest(source)==before_files
 # Only this verified duplicate is removed; all original paths resolve to disk.
 shutil.rmtree(retired)
 receipt.update(after=memory(),source_path_preserved=True,completed_at=time.time());put(OUT/(name+'-receipt.json'),receipt);rows.append(receipt)
 print('OFFLOADED',name,'availableGiB',round(receipt['after']['MemAvailable']/1024**3,2),flush=True)
result={'before':before,'after':memory(),'folders':rows,'processes_stopped':0,'model_calls':0,'wsl_restarted':False,'wsl_config_changed':False}
put(OUT/'result.json',result)
(OUT/'복원안내.txt').write_text('원본 파일은 files/ 아래에 그대로 보존하고 /tmp 원래 경로는 심볼릭 링크로 연결했습니다. SHA256·크기·권한·수정시각·링크 대상을 대조했습니다. 실행 프로세스 종료/WSL 재시작/설정 변경은 없습니다.\n원복이 필요하면 충분한 RAM 확보 후 해당 /tmp 링크를 제거하고 디스크의 원본 폴더를 같은 /tmp 경로에 copytree(symlinks=True)로 복사하고 내용을 검증합니다. 디스크 원본은 검증 전 삭제하지 마십시오.\n')
print('COMPLETE',json.dumps({'available_before_gib':before['MemAvailable']/1024**3,'available_after_gib':result['after']['MemAvailable']/1024**3}),flush=True)
