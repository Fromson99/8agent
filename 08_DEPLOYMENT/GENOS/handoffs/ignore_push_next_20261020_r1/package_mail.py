from pathlib import Path
import base64,hashlib,html,json,zipfile
R=Path('/home/jin/8-AGENT');H=R/'08_DEPLOYMENT/GENOS/handoffs/ignore_push_next_20261020_r1';N='GENOS_NEXT_COPY_PASTE_20261020_R1'
enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode();sha=lambda b:hashlib.sha256(b).hexdigest()
script=H/(N+'.txt');v=json.loads((H/'VALIDATION.json').read_bytes());assert sha(script.read_bytes())==v['tested_txt_sha256']
guide='''사진의 커밋 수정까지 완료된 상태에서 쓰는 다음 단계입니다.
첨부 GENOS_NEXT_COPY_PASTE_20261020_R1.txt 전체를 현재 GENOS 터미널에 한 번에 붙여넣으세요.
또는 파일을 업로드한 폴더에서 bash ./GENOS_NEXT_COPY_PASTE_20261020_R1.txt 로 실행해도 같습니다.
기존 GENOS_IGNORE_TRANSFER_20261020_R1 폴더와 STATE.json을 보존하세요.
스크립트가 현재 위치·checkout·홈의 바로 아래에서 실제 TRANSFER와 적용된 패키지를 찾습니다.
찾지 못하거나 둘 이상이면 중단하며 잘못된 폴더를 임의 선택하지 않습니다.
검증 통과 뒤 수정된 main 커밋 하나만 일반 push합니다. 비밀번호를 물으면 평소처럼 입력하세요.
add/rm/amend/force-push/데이터 삭제는 실행하지 않습니다.
PUSH_CONFIRMED=... 가 나오면 Git 전송 확인 완료입니다.
다음은 GENOS 코드서빙에서 그 커밋의 리비전 배포입니다.
기존 MAIN92 WORKFLOW_PASTE_ALL.txt를 아직 반영하지 않았다면 편집기에 교체·저장한 뒤 워크플로우 테스트 화면에서 확인하세요.
코드서빙 직접 테스트 화면/API 실행은 요구하지 않습니다.
로그 경로와 종료코드는 마지막에 출력됩니다. 오류 시 다음 작업을 자동 진행하지 않습니다.
ZIP으로 받았다면 실제 업로드한 TRANSFER 위치에서 다음과 같이 풉니다.
python3 -m zipfile -e ./GENOS_NEXT_COPY_PASTE_20261020_R1.zip ./GENOS_NEXT_COPY_PASTE_20261020_R1
bash ./GENOS_NEXT_COPY_PASTE_20261020_R1/GENOS_NEXT_COPY_PASTE_20261020_R1.txt
'''
(H/'README_UTF8.txt').write_text(guide)
with zipfile.ZipFile(H/(N+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for name in (N+'.txt','README_UTF8.txt','VALIDATION.json'):
  i=zipfile.ZipInfo(name,(2026,10,20,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,(H/name).read_bytes())
with zipfile.ZipFile(H/(N+'.zip')) as z:
 assert z.read(N+'.txt')==script.read_bytes()
 assert all(Path(p).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
text='''사진상 이관 파일을 뺀 커밋 수정까지 끝났습니다. 남은 단계만 모았습니다.

이번 메일의 GENOS_NEXT_COPY_PASTE_20261020_R1.txt 하나를 열어 전체 복사한 다음, 현재 GENOS 터미널에 한 번에 붙여넣으세요. 이전 add/rm/amend 명령은 다시 실행하지 않아도 됩니다. ZIP은 동일 TXT를 담은 반입용 사본입니다.

TXT가 기존 ignore 패키지를 찾아 코드 검증 → 원격 상태 확인 → 수정된 main 커밋 하나만 일반 push 순서로 진행합니다. Git 사용자명/비밀번호를 물으면 평소처럼 입력하세요. 강제 push·커밋 재수정·파일 삭제는 하지 않습니다. 오류가 나면 즉시 멈추고 로그 경로를 표시합니다.

마지막에 PUSH_CONFIRMED=커밋번호가 나오면 Git 전송 확인까지 완료입니다.
그다음 GENOS 코드서빙에서 해당 커밋의 리비전을 배포하세요. 기존 MAIN92 워크플로우 전체 TXT를 아직 반영하지 않았다면 편집기에 교체·저장한 뒤 워크플로우 테스트 화면에서 확인하면 됩니다.

기존 GENOS_IGNORE_TRANSFER_20261020_R1 폴더와 STATE.json은 그대로 두세요.
테스트 저장소에서 정상 push·재실행·중단 조건 등 31명령을 검증했으며 실제 GENOS push/배포는 아직 실행하지 않았습니다.
'''
(H/'EMAIL_BODY_UTF8.txt').write_text(text)
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':'<pre style="white-space:pre-wrap;font-family:sans-serif">'+html.escape(text)+'</pre>'}}]
files=[N+'.txt',N+'.zip']
for name in files:
 parts.append({'mime_type':'application/zip' if name.endswith('.zip') else 'text/plain','filename':name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode((H/name).read_bytes()).decode().rstrip('=')}})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS] 지금부터 할 것 — TXT 전체 복사·붙여넣기 한 번 (검증→push)','payload':{'mime_type':'multipart/mixed','parts':parts}}
(H/'EMAIL_ARGS.json').write_bytes(enc(args));(H/'SEALED.json').write_bytes(enc({'attachments':[{ 'name':p,'bytes':(H/p).stat().st_size,'sha256':sha((H/p).read_bytes())} for p in files],'zip_members':3,'javascript_members':0,'txt_matches_tested_bytes':True,'observed_photo_commit_prefix':'96a5d4a','field_gate_push_verified':False}))
print(json.dumps({'email_args_bytes':(H/'EMAIL_ARGS.json').stat().st_size,'attachments':files,'txt_bytes':script.stat().st_size,'zip_bytes':(H/(N+'.zip')).stat().st_size},ensure_ascii=False))
