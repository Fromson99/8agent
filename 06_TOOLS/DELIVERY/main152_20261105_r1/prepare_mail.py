from common import *
import zipfile,base64,ast,subprocess
H=ROOT/read(ART/'mail-package.json')['handoff'];pkg=read(ART/'mail-package.json');install=read(ART/'package-tests-r1/result.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert install['passed'] and active['generation']==152
assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
assert sha(H/'MAIN152_FULL_20261105_R1.zip')==pkg['zip_sha256']
workflow=H/'MAIN152_WORKFLOW.py';assert sha(workflow)==release['files']['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
ast.parse(workflow.read_text(),feature_version=(3,10))
subprocess.run(['/home/jin/.local/bin/python3.11','-c','import sys; compile(open(sys.argv[1],"rb").read(),sys.argv[1],"exec")',str(workflow)],check=True)
with zipfile.ZipFile(H/'MAIN152_FULL_20261105_R1.zip') as z:
 manifest=json.loads(z.read('CODE_MANIFEST.json'));members=z.namelist()
 assert len(members)==len(set(members))==len(manifest['files'])+1
 assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs','.zip','.gz','.tgz','.tar','.7z'} for n in members)
 for row in manifest['files']:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
 assert {row['path']:row['sha256'] for row in manifest['files'] if row['path'] in release['files']}|pkg['excluded_required']==release['files']
checks=read(SOURCE_ART/'main/activation.json');live=read(SOURCE_ART/'live-summary.json');reg=read(SOURCE_ART/'regression-comparison-final.json')
verification={'main_generation':152,'release_id':release['release_id'],'release_manifest_sha256':sha(ROOT/active['manifest_path']),
 'serving_files':len(release['files']),'serving_bytes_equal_to_MAIN152':True,'zip_sha256':pkg['zip_sha256'],'code_files':pkg['code_files'],'archive_members':pkg['members'],
 'existing_required_javascript':pkg['excluded_required'],'javascript_attachments':0,'nested_archives':0,'workflow_sha256':sha(workflow),'workflow_equals_MAIN152':True,
 'contracts':reg['candidate'],'baseline_failures':reg['baseline']['failed'],'new_failures':reg['new_failures'],'working_contracts':49,'prepared_contracts':49,'rechecks_overlap':True,
 'actual_MAIN_entry_checks':checks['main_checks'],'actual_Gold_engine_checks':checks['gold_checks'],
 'installer':install,'isolated_generation_gate':read(ART/'package-tests-r1/validated-deployment-checkout.json'),
 'actual_Qwen':{**{k:live[k] for k in ('physical_calls','normal','unknown','reported_cost_usd','source_checks','delivered_checks','source_acl_wire_mismatches','budget_matches','response_replay','no_post_unknown_send')},'first_turn_seconds':38.503,'first_turn_calls':5,'continuation':'Prior question and answer passed; action selection timed out after about180s, UNKNOWN/API504. Remaining cells and actual confirmation/reuse not executed.','semantic_limit':'First answer still has over-broad/exclusive wording. Not legal quality certification.','live_revision':'rev-009','selected_revision':'rev-010','post_live_change':'Local compatibility guard for explicit legacy answer modes; no more real model sends.'},
 'synthetic_multiturn_and_confirmed_experience_ontology':True,'syntax':{'bash':True,'package_python311_compile':True,'workflow_python311_compile':True,'workflow_python310_ast':True},
 'field_checkout':None,'field_commit':None,'field_revision':None,'field_generation':None,'field_deployed':False,'quality_certified':False,'new_model_calls_for_packaging':0,'source_database_modified':False,'local_MAIN_modified_by_packaging':False}
put(H/'VERIFICATION.json',verification)
guide='''MAIN152 — 사용자와 이어가는 조사 루프 / 전체 코드 덮어쓰기

대상: GENOS 코드스페이스의 기존 ~/DEV Git checkout, 별도 GENOS 워크플로우 Python 편집기.
릴리스: guided-navigation-20261105-r1 / 로컬 MAIN152 / 전체 서빙532파일.
이전 MAIN151 대신 이번 MAIN152 ZIP과 TXT 한 쌍을 사용하세요. 이전 전체 코드 ZIP을 나중에 다시 덮어쓰지 않습니다.

이번 변경
본문 읽기 / 연결 따라가기 / 검색 / 사용자 질문 / 답변 중 다음 행동 하나를 고릅니다.
불확실하거나 상충된 판단은 내부 보완을 반복하기보다 막힌 지점과 다음 조사 방향을 사용자에게 묻도록 했습니다.
같은 조사의 이전 질문·답변 전문과 행동 기록을 다음 판단에 전달하고, 추가 정보가 오면 기존 원문에서 이어갑니다.
미확보 원문과 미해결 상태를 보존합니다. 해결된 결과를 사용자가 확인한 경우 기존 경험 온톨로지에 조건·출처와 함께 저장·재사용합니다.
공유 온톨로지 자동 게시나 모델 의미 오류의 완전 검출을 보장하는 기능은 아닙니다.

1. 업로드와 전체 코드 교체
첨부 두 파일을 같은 TRANSFER 폴더에 그대로 업로드합니다. ZIP은 미리 풀지 않습니다.
  MAIN152_FULL_20261105_R1.zip
  MAIN152_ONECLICK_R1.txt
그 TRANSFER 폴더의 터미널에서 다음 한 줄을 실행합니다:
  bash MAIN152_ONECLICK_R1.txt

기존 ~/DEV가 링크이면 물리 checkout을 자동으로 찾습니다.
패키지 확인 → 백업 → 코드 덮어쓰기 → 엔진 해시 검사를 수행합니다. Python3.11 이상 기존 환경을 사용합니다.
원문 데이터·현재 generation·Oracle/NFS 연결·실제 .env/키·가상환경·Git 이력은 유지합니다.
사용자 첨부 선호에 따라 JavaScript 파일은 ZIP에서 제외했고, 기존 app.js의 필요한 해시를 교체 전에 확인합니다.
완료 표시: MAIN152_ONECLICK_DONE, MAIN152_EXIT=0.

2. 변경 확인과 코드서빙 배포
설치 상태 확인:
  bash MAIN152_ONECLICK_R1.txt status
변경된 코드만 스테이징하고 검토:
  bash MAIN152_ONECLICK_R1.txt stage
  git -C ~/DEV diff --cached --stat
  git -C ~/DEV diff --cached --check
기존 절차로 commit한 뒤, ZIP의 파일과 실제 commit 일치 확인:
  bash MAIN152_ONECLICK_R1.txt gate-code

NFS/SQLite 원문 세대 사용 환경에서는 현재 GENOS_GENERATION이 실제 절대경로로 설정된 터미널에서:
  python3 ~/DEV/06_TOOLS/COMMANDS/genos_release_gate.py --code-zip "$PWD/MAIN152_FULL_20261105_R1.zip" --deploy-root "$(realpath ~/DEV)" --generation "$GENOS_GENERATION"
GENOS_GENERATION은 기존에 실제 사용하는 값을 유지합니다. 임의 경로로 새로 설정하지 않습니다.
Oracle 환경에는 NFS 경로를 대신 넣지 않고 기존 Oracle 설정으로 기동·원문 조회를 확인합니다.
검증한 commit을 기존 절차로 push하고 그 commit의 새 코드서빙 리비전을 배포합니다.
시작 명령은 기존대로 유지합니다:
  python3 08_DEPLOYMENT/GENOS/start_sse.py
TXT는 Git push나 플랫폼 리비전 배포를 자동 실행하지 않습니다.

3. 워크플로우 전체 교체
별도 첨부 MAIN152_WORKFLOW.py는 MAIN152에 포함된 워크플로우와 바이트가 같습니다.
GENOS 워크플로우 Python 편집기에 전체 내용을 교체하거나 파일로 가져온 뒤 저장·배포합니다.
기존 코드서빙 연결 주소·인증 설정을 유지합니다. ZIP 설치가 별도 편집기를 자동 갱신하지는 않습니다.
워크플로우 표시 버전은 기존과 같은 workflow-guided-explanation-20261105-r3입니다.
이번 차이는 백엔드 탐색 루프이므로 표시 버전만으로 MAIN152 배포를 판정하지 않습니다.

4. 적용 확인
새 코드서빙 리비전이 검증한 commit/원문 generation을 선택하는지 확인하고 health·원문 조회를 실행합니다.
실제 질문에서 설명·출처를 확인하고, 모르는 부분은 구체 질문으로 반환하는지 확인합니다.
같은 chatId/session_id에서 추가 답을 보내며 새 메시지는 새 request_id를 사용합니다.
기존 GENOS_MEMORY_ENABLED=1 및 사용자/대화 식별자 전달을 유지합니다.
이전 질문·답변의 조건을 이어가는지, 미해결 상태를 숨기지 않는지 확인합니다.
해결 확인 후 '이 조건과 출처로 기억해줘' 같은 기존 확정 명령의 결과를 확인합니다.

5. 재실행·중단·원복
main152-install-logs에 로그, 설치 출력에 백업 경로가 남습니다.
완료 후 기본 명령을 다시 실행하면 동일 설치 여부를 확인합니다. 중간 실패 시 출력된 백업을 보존하고 먼저 원복합니다:
  bash MAIN152_ONECLICK_R1.txt undo --backup '출력된 백업 폴더 절대경로'
현재 설치 뒤의 추가 코드 변경이 있으면 이를 덮어쓰지 않고 중단할 수 있습니다.
이미 배포한 코드서빙·워크플로우 리비전은 플랫폼에서 별도로 이전 리비전으로 되돌립니다.

6. 검증 범위
관련166검사 통과, 변경 전에도 발생한 기존12실패 동일, 신규 회귀0.
작업/준비본 각49검사(부분집합 재확인), 실제 선택 서비스42/Gold 코드 연결9검사 통과.
정확한 첨부 ZIP/TXT를 링크 ~/DEV 대상으로 설치·재실행·commit·코드 및 원문세대 검사·원복했습니다.
실제 Qwen 공개 CM003 첫 답변은38.5초/5회로 설명과 추가 질문을 반환했습니다.
후속 행동 선택은 약180초 동안 완성 응답을 받지 못해 UNKNOWN/API504로 중단했으며 이후 호출하지 않았습니다.
실제 멀티턴 전체 성공·법률 의미 정확도·현장 GENOS 내부 모델 성능은 인증하지 않았습니다.
현장 checkout/commit/코드서빙 리비전/실제 원문 연결 성공은 현장 적용 후 확인해야 합니다.
검증 세부와 첨부 해시는 VERIFICATION.json, SHA256SUMS.txt에 있습니다.
'''
(H/'GUIDE.txt').write_text(guide)
names=['MAIN152_FULL_20261105_R1.zip','MAIN152_ONECLICK_R1.txt','MAIN152_WORKFLOW.py','GUIDE.txt','VERIFICATION.json']
(H/'SHA256SUMS.txt').write_text(''.join(sha(H/n)+'  '+n+'\n' for n in names));names.append('SHA256SUMS.txt')
subject='[MAIN152 전체 덮어쓰기] 사용자 질문·조사 재개 루프 — 코드 ZIP / 한 줄 실행 / 워크플로우'
html='''<p>안녕하세요.</p><p>요청하신 <b>MAIN152 전체 코드 덮어쓰기 전달본</b>입니다. 이전 MAIN151 대신 이번 ZIP과 TXT 한 쌍을 사용해 주세요.</p><p>본문 읽기·연결 따라가기·검색·사용자 질문·답변으로 행동을 단순화했습니다. 불확실하거나 상충된 판단은 막힌 지점과 다음 방향을 묻고, 같은 조사의 이전 질문·답변과 행동 기록을 이어갑니다. 해결 후 사용자가 확인한 결과는 기존 경험 온톨로지에 조건·근거와 함께 저장·재사용합니다.</p><p><b>실행:</b> ZIP과 실행 TXT를 같은 TRANSFER 폴더에 업로드한 뒤 그 폴더에서 <code>bash MAIN152_ONECLICK_R1.txt</code> 한 줄을 실행하세요. 기존 <code>~/DEV</code> 링크의 실제 checkout을 찾아 검사·백업·코드 교체·검증합니다. 완료 표시는 <code>MAIN152_ONECLICK_DONE</code>, <code>MAIN152_EXIT=0</code>입니다.</p><p>이후 GUIDE.txt에 따라 commit 검증·push·새 코드서빙 리비전을 반영하고, 별도 워크플로우 편집기는 <code>MAIN152_WORKFLOW.py</code> 전체로 교체합니다. 기존 원문 데이터와 Oracle/NFS·모델·키 설정은 유지합니다. 중단·재실행·원복 명령도 GUIDE.txt에 있습니다.</p><p><b>검증:</b> 관련166검사 통과, 기존12실패 동일·신규 회귀0. 실제 서비스42/Gold 코드 연결9검사 통과. 정확한 첨부의 설치·재실행·코드/원문세대 검사·원복을 격리 checkout에서 확인했습니다. 전체 서빙532파일과 결속했으며 JavaScript는 첨부 선호에 따라 제외하고 기존 파일 해시를 확인합니다.</p><p><b>실제 모델 한계:</b> Qwen CM003 첫 답변은38.5초/5회로 완료했으나 후속 행동 선택은 약180초 뒤 응답 미완료로 중단됐습니다. 실제 멀티턴 전체 성공이나 법률 정확성, 현장 GENOS 적용 완료를 뜻하지 않습니다.</p><p>첨부6개: 전체 코드 ZIP, 한 줄 실행 TXT, 워크플로우 Python, GUIDE.txt, VERIFICATION.json, SHA256SUMS.txt.</p>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':html}}];meta=[]
for n in names:
 p=H/n;typ='application/zip' if p.suffix=='.zip' else 'application/json' if p.suffix=='.json' else 'text/x-python' if p.suffix=='.py' else 'text/plain'
 assert p.is_file() and p.suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
 parts.append({'mime_type':typ,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode()}})
 meta.append({'filename':n,'mime_type':typ,'bytes':p.stat().st_size,'sha256':sha(p)})
mail={'to':'hyungjininfocz.son@partner.samsung.com','subject':subject,'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids','snippet']}
path=Path('/tmp/main152-mail-payload.json');path.write_text(json.dumps(mail,ensure_ascii=False))
put(H/'EMAIL_PREPARED.json',{'to':mail['to'],'subject':subject,'attachments':meta,'payload_path':str(path),'payload_sha256':sha(path),'payload_bytes':path.stat().st_size,'authorization':'삼성메일로 전체 어퍼치게 만들어줘'})
print('Email ready',len(names),'attachments',path.stat().st_size,'bytes; exact validated ZIP/TXT unchanged')
