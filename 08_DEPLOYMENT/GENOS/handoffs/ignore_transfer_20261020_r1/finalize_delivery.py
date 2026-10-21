from pathlib import Path
import base64,hashlib,html,json,os,shutil,subprocess,tempfile,zipfile
R=Path('/home/jin/8-AGENT');H=R/'08_DEPLOYMENT/GENOS/handoffs/ignore_transfer_20261020_r1';N='GENOS_IGNORE_TRANSFER_20261020_R1'
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
v=json.loads((H/'VALIDATION.json').read_bytes());v['initial_failure']='Standalone launcher re-extracted ZIP and masked a tampered payload; changed to reuse complete extraction and reject changed payload. Final 32-command verification passed.';(H/'VALIDATION.json').write_bytes(enc(v))
f=json.loads((H/'INITIAL_CHECK_FAILURE.json').read_bytes());f['status']='fixed; complete 32-command verification passed';(H/'INITIAL_CHECK_FAILURE.json').write_bytes(enc(f))
files=['apply_ignore.py','IGNORE_RULES.txt','MAIN92_BASE_INVENTORY.json','PATCH_SPEC.json','GUIDE_UTF8.txt','VALIDATION.json',N+'_RUN.txt',*[p.relative_to(H).as_posix() for p in (H/'updated-source').rglob('*') if p.is_file()]]
contents={p:sha((H/p).read_bytes()) for p in files};(H/'PACKAGE_CONTENTS.json').write_bytes(enc(contents));files.append('PACKAGE_CONTENTS.json')
with zipfile.ZipFile(H/(N+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(files):
  i=zipfile.ZipInfo(p,(2026,10,20,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,(H/p).read_bytes())
with zipfile.ZipFile(H/(N+'.zip')) as z:
 assert len(z.namelist())==len(set(z.namelist()))
 for i in z.infolist():
  assert Path(i.filename).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
  if i.filename in contents:assert sha(z.read(i))==contents[i.filename]
trace=[]
env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GIT_AUTHOR_NAME':'Synthetic','GIT_AUTHOR_EMAIL':'synthetic@example.invalid','GIT_COMMITTER_NAME':'Synthetic','GIT_COMMITTER_EMAIL':'synthetic@example.invalid','PYTHONDONTWRITEBYTECODE':'1'}
with tempfile.TemporaryDirectory(prefix='genos-ignore-final-') as tmp:
 t=Path(tmp);r=t/'root';r.mkdir();transfer=t/'uploaded';transfer.mkdir()
 for p in ('.gitignore','genosIgnore'):(r/p).write_bytes((H/'updated-source'/p).read_bytes())
 (r/'service.py').write_text('# synthetic\n')
 for cmd in (['git','init','-q','-b','main'],['git','add','.'],['git','commit','-qm','synthetic']):subprocess.run(cmd,cwd=r,env=env,check=True,capture_output=True)
 shutil.copyfile(H/(N+'.zip'),transfer/(N+'.zip'))
 cmd=['python3','-m','zipfile','-e','./'+N+'.zip','./'+N];p=subprocess.run(cmd,cwd=transfer,env=env,capture_output=True,text=True);assert p.returncode==0;trace.append({'action':'extract','exit':p.returncode})
 for action in ('check','apply','status','undo'):
  p=subprocess.run(['bash','./'+N+'/'+N+'_RUN.txt',action,'--root',str(r)],cwd=transfer,env=env,capture_output=True,text=True,timeout=60)
  trace.append({'action':action,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert p.returncode==0,p.stdout+p.stderr
final={'status':'PASS','final_archive_commands':len(trace),'zip_sha256':sha((H/(N+'.zip')).read_bytes()),'zip_bytes':(H/(N+'.zip')).stat().st_size,'members':len(files),'javascript_members':0,'runtime_hashes_match_verified_source':True,'field_verified':False}
(H/'FINAL_TRACE.json').write_bytes(enc(trace));(H/'FINAL_VERIFICATION.json').write_bytes(enc(final))
attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION.json','FINAL_VERIFICATION.json']
(H/'SHA256SUMS.txt').write_text(''.join(sha((H/p).read_bytes())+'  '+p+'\n' for p in attachments));attachments.append('SHA256SUMS.txt')
text='''안녕하세요. 요청하신 GENOS ignore 수정 전용 패치를 보냅니다.

첨부 GENOS_IGNORE_TRANSFER_20261020_R1.zip을 사용하세요. 기존 MAIN92 누적 코드에 추가하는 작은 패치이며 서버 기능을 덮어쓰지 않습니다. .Trash/.Trash-* 휴지통, QUERY_TRANSFER_* 이관 작업 폴더, 임시 DB/journal을 Git과 코드 포장에서 제외합니다. updated-source에는 수정한 규칙 파일 7개 전체본을 포함했고, 현장 설치는 기존 파일을 보존하며 새 규칙만 추가합니다.

실제 ZIP을 업로드한 TRANSFER 폴더에서 아래 순서로 실행하세요. 각 단계가 성공해야 다음 단계로 진행합니다. --root /workspace는 사진에서 확인한 기존 Git checkout입니다.

python3 -m zipfile -e ./GENOS_IGNORE_TRANSFER_20261020_R1.zip ./GENOS_IGNORE_TRANSFER_20261020_R1
bash ./GENOS_IGNORE_TRANSFER_20261020_R1/GENOS_IGNORE_TRANSFER_20261020_R1_RUN.txt check --root /workspace
bash ./GENOS_IGNORE_TRANSFER_20261020_R1/GENOS_IGNORE_TRANSFER_20261020_R1_RUN.txt apply --root /workspace
bash ./GENOS_IGNORE_TRANSFER_20261020_R1/GENOS_IGNORE_TRANSFER_20261020_R1_RUN.txt status --root /workspace

기존 커밋에 들어간 QUERY_TRANSFER_20261020_R1의 DB는 ignore만으로 빠지지 않습니다. 사진에서는 commit은 완료됐고 push 중단 뒤의 원격 반영 여부는 아직 확인되지 않았습니다. status 결과와 GUIDE_UTF8.txt의 읽기 전용 원격 조회부터 확인하세요. 새 삭제 커밋만 추가하면 이전 커밋에 DB가 남아 계속 전송됩니다. 원격에 없는 마지막 단일 커밋으로 확인된 경우에만 파일을 보존하는 추적 제외·커밋 수정 절차를 안내에 따라 진행합니다. 설치기는 add/commit/push/amend/데이터 삭제를 자동 실행하지 않습니다.

패키지의 STATE.json은 원복·재개 기록입니다. 압축 해제 폴더와 genos-ignore-r1-logs를 보존하세요. 적용 후 사용자가 수정한 파일은 덮어쓰지 않고 중단합니다. 기존 MAIN92 R1 gate-code는 ignore 수정 전 해시 기준이므로, 커밋 정리 후 이번 패키지의 gate 명령을 사용합니다. gate는 MAIN92 1306파일과 필수 의존성·현장 설정·ignore 변경을 대조하며 원격 이력·실제 모델/리비전 성공까지 확인하는 검사는 아닙니다.

검증: 실제 ZIP/TXT의 합성 Git checkout 32명령(기대한 실패 4건 포함), 적용/재실행/부분 복구/변조 거부/사용자 수정 보존/원복/추적 데이터 감지/미전송 커밋 정리/MAIN92 코드 대조 및 최종 ZIP 5명령을 통과했습니다. JavaScript 첨부 0개, GENOS 현장 실행은 미확인입니다.

첨부 6개: ZIP, 별도 실행 TXT, 안내 TXT, 검증 JSON, 최종 ZIP 검증 JSON, SHA256SUMS TXT.
'''
(H/'EMAIL_BODY_UTF8.txt').write_text(text)
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':'<pre style="white-space:pre-wrap;font-family:sans-serif">'+html.escape(text)+'</pre>'}}]
for p in attachments:
 mime='application/zip' if p.endswith('.zip') else 'application/json' if p.endswith('.json') else 'text/plain'
 parts.append({'mime_type':mime,'filename':p,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode((H/p).read_bytes()).decode().rstrip('=')}})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS] ignore 수정 패치 — 휴지통·QUERY_TRANSFER Git 제외 (2026-10-20 R1)','payload':{'mime_type':'multipart/mixed','parts':parts}}
(H/'EMAIL_ARGS.json').write_bytes(enc(args))
(H/'SEALED.json').write_bytes(enc({'zip_sha256':final['zip_sha256'],'attachments':[{ 'name':p,'bytes':(H/p).stat().st_size,'sha256':sha((H/p).read_bytes())} for p in attachments]}))
print(json.dumps({'final':final,'email_arg_bytes':(H/'EMAIL_ARGS.json').stat().st_size,'attachments':attachments},ensure_ascii=False))
