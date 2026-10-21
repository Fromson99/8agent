from pathlib import Path
import base64,hashlib,html,json,zipfile
R=Path('/home/jin/8-AGENT');H=R/'08_DEPLOYMENT/GENOS/handoffs/ignore_push_next_20261020_r2';N='GENOS_NEXT_COPY_PASTE_20261020_R2'
enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode();sha=lambda b:hashlib.sha256(b).hexdigest()
script=H/(N+'.txt');v=json.loads((H/'VALIDATION.json').read_bytes());assert sha(script.read_bytes())==v['tested_txt_sha256']
text='''제가 보낸 검사 목록에 오류가 있었습니다. Git에서는 제외하는 과거 corpus 데이터 파일을 검사기가 필수 코드로 요구해서 멈춘 것입니다. 휴지통 정리는 통과했고 이번 실행도 push 전 중단됐습니다.

이전 R1 TXT 대신 이번 GENOS_NEXT_COPY_PASTE_20261020_R2.txt 전체를 현재 GENOS 터미널에 한 번에 붙여넣으세요. 다른 명령을 먼저 실행할 필요는 없습니다. 문제가 된 파일을 강제로 add하거나 커밋을 다시 수정하지 마세요.

R2는 기존 패키지와 STATE.json을 그대로 사용합니다. 새로 압축을 풀거나 코드를 덮어쓸 필요가 없습니다. ZIP은 동일 TXT를 담은 반입용 사본입니다.

검증 후 원격 상태를 확인하고, 수정된 main 커밋 하나만 일반 push합니다. Git 사용자명/비밀번호를 물으면 평소처럼 입력하세요. 마지막에 PUSH_CONFIRMED=커밋번호가 나오면 Git 전송까지 확인된 것입니다.

그다음 GENOS 코드서빙에서 그 커밋의 리비전을 배포하세요. 기존 MAIN92 워크플로우 전체 TXT를 아직 반영하지 않았다면 편집기에 교체·저장한 뒤 워크플로우 테스트 화면에서 확인하면 됩니다.

검증 근거: 기존 반입 목록의 과거 agent6 corpus 자료 6개(별도 빌드 manifest 1개, raw 메타데이터 3개, 구조화 문서 2개)를 코드 전용 검사 목록에서 분리했습니다. 이 자료들은 기존 포장 정책의 제외 대상이며 선택된 서빙 코드 389개에 포함되지 않습니다. 데이터 파일과 기존 반입 기록은 삭제·수정하지 않습니다. 나머지 MAIN92 코드 1300파일, 필수 의존성, 현장 설정, ignore, Git 상태와 원격 검사는 유지합니다.

이전 테스트가 git add -f로 제외 자료까지 등록해 이 모순을 놓쳤습니다. 이번에는 일반 git add 조건으로 같은 실패를 재현한 뒤, R2 통과·실제 코드 변조/누락 차단·정상 push·재실행·원격 변경 중단 등 43명령을 확인했습니다. 실제 GENOS 실행 결과는 아직 미확인입니다.
'''
(H/'EMAIL_BODY_UTF8.txt').write_text(text)
guide='''R2 수정본 사용법
GENOS_NEXT_COPY_PASTE_20261020_R2.txt 전체를 현재 GENOS 터미널에 붙여넣으세요.
이전 R1 TXT는 사용하지 않습니다. 기존 GENOS_IGNORE_TRANSFER_20261020_R1 폴더와 STATE.json은 보존합니다.
다른 add/rm/amend 명령, 데이터 파일 강제 add, 코드 재설치는 필요하지 않습니다.
PUSH_CONFIRMED=커밋번호가 나오면 Git 전송 확인 완료입니다.
그다음 해당 커밋의 GENOS 코드서빙 리비전 배포와 워크플로우 편집기 반영/테스트를 진행합니다.
실패하면 로그 경로와 종료코드를 남기고 중단합니다.
ZIP 경로를 이용할 경우 실제 업로드한 TRANSFER에서 아래처럼 실행할 수도 있습니다.
python3 -m zipfile -e ./GENOS_NEXT_COPY_PASTE_20261020_R2.zip ./GENOS_NEXT_COPY_PASTE_20261020_R2
bash ./GENOS_NEXT_COPY_PASTE_20261020_R2/GENOS_NEXT_COPY_PASTE_20261020_R2.txt
'''
(H/'README_UTF8.txt').write_text(guide)
files=(N+'.txt','README_UTF8.txt','VALIDATION.json','ROOT_CAUSE.json','CORRECTED_CODE_INVENTORY.json')
with zipfile.ZipFile(H/(N+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for name in files:
  i=zipfile.ZipInfo(name,(2026,10,20,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,(H/name).read_bytes())
with zipfile.ZipFile(H/(N+'.zip')) as z:
 assert z.read(N+'.txt')==script.read_bytes()
 assert all(Path(p).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':'<pre style="white-space:pre-wrap;font-family:sans-serif">'+html.escape(text)+'</pre>'}}]
attachments=[N+'.txt',N+'.zip']
for name in attachments:
 parts.append({'mime_type':'application/zip' if name.endswith('.zip') else 'text/plain','filename':name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode((H/name).read_bytes()).decode().rstrip('=')}})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS 수정본 R2] 검사 목록 오류 수정 — 이 TXT만 다시 붙여넣으세요','payload':{'mime_type':'multipart/mixed','parts':parts}}
(H/'EMAIL_ARGS.json').write_bytes(enc(args));(H/'SEALED.json').write_bytes(enc({'attachments':[{ 'name':p,'bytes':(H/p).stat().st_size,'sha256':sha((H/p).read_bytes())} for p in attachments],'zip_members':len(files),'javascript_members':0,'txt_matches_tested_bytes':True,'field_gate_push_verified':False}))
print(json.dumps({'email_args_bytes':(H/'EMAIL_ARGS.json').stat().st_size,'attachments':attachments,'txt_bytes':script.stat().st_size,'zip_bytes':(H/(N+'.zip')).stat().st_size},ensure_ascii=False))
