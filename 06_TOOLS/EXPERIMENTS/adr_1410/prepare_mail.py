from common import *
import zipfile,base64,ast,subprocess
H=ROOT/read(ART/'mail-package.json')['handoff'];pkg=read(ART/'mail-package.json');install=read(ART/'mail-package-tests-r3/result.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert install['passed'] and active['generation']==151
assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
assert all(sha(ROOT/n)==h for n,h in release['files'].items())
workflow=H/'MAIN151_WORKFLOW.py';assert sha(workflow)==release['files']['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
ast.parse(workflow.read_text(),feature_version=(3,10))
subprocess.run(['/home/jin/.local/bin/python3.11','-c','import sys; compile(open(sys.argv[1],"rb").read(),sys.argv[1],"exec")',str(workflow)],check=True)
results=[read(ART/('actual-final-r'+str(n))/'result.json') for n in (3,4,5,6)]
verification={'main_generation':151,'release_id':release['release_id'],'release_manifest_sha256':sha(ROOT/active['manifest_path']),'serving_files':531,'serving_bytes_equal_to_MAIN151':True,
 'zip_sha256':pkg['zip_sha256'],'code_files':pkg['code_files'],'archive_members':pkg['members'],'existing_required_javascript':pkg['excluded_required'],
 'javascript_attachments':0,'nested_archives':0,'workflow_sha256':sha(workflow),'workflow_equals_MAIN151':True,
 'candidate_contracts':42,'working_contracts':39,'prepared_contracts':39,'rechecks_overlap':True,'actual_MAIN_entry_checks':38,'actual_Gold_engine_checks':9,
 'installer':install,'isolated_generation_gate':read(ART/'mail-package-tests-r3/validated-deployment-checkout.json'),
 'actual_Qwen':{'scope':'CM003 final stage using previous real original sources, full retrieval and actual user multi-turn not rerun','trial_count':len(results),'physical_calls':sum(r['model_calls'] for r in results),'normal_responses':4,'known_http429':1,'unknown':0,'reported_cost_usd':sum(u['cost_usd'] for r in results for u in r['usage']),'latest_result':results[-1],'latest_limit':'Explains then asks; exception detail omission and over-broad conditional wording remain. No legal accuracy certification.'},
 'synthetic_multiturn_and_confirmed_experience_ontology':True,'actual_Qwen_multiturn_and_ontology_not_retested':True,
 'syntax':{'bash':True,'package_python311_compile':True,'workflow_python311_compile':True,'workflow_python310_ast':True},
 'initial_failures_preserved':['Model runner import and authorization-key errors before calls','Candidate initial keyword argument and legacy test fixture failures','Native receipt test initially used version5 fixture, corrected to actual version6','Working-copy checker import path error after byte-verified copy','First package omitted asset verifier dependencies; generation E2E passed but full gate failed','Second package legacy helper trailing space failed diff --check; one helper whitespace normalized with identical AST'],
 'field_checkout':None,'field_commit':None,'field_revision':None,'field_deployed':False,'quality_certified':False}
put(H/'VERIFICATION.json',verification)
names=['MAIN151_FULL_20261105_R1.zip','MAIN151_ONECLICK_R1.txt','MAIN151_WORKFLOW.py','GUIDE.txt','VERIFICATION.json']
(H/'SHA256SUMS.txt').write_text(''.join(sha(H/n)+'  '+n+'\n' for n in names))
names.append('SHA256SUMS.txt')
assert all((H/n).is_file() for n in names)
subject='[MAIN151] 설명 후 추가 질문 — 최종 검토 제거 / 전체 코드·실행 TXT·워크플로우'
html='''<p>안녕하세요.</p><p>요청하신 수정본을 로컬 MAIN151(<code>guided-answer-20261105-r1</code>)에 반영했습니다.</p><p>일반 대화의 최종 조건·예외 판단과 재검토·보완을 한 번의 답변 작성으로 바꿨습니다. 확인한 내용을 먼저 설명하고, 마지막에 모르는 부분과 구체적인 추가 질문을 표시합니다. 원문과 문서명은 출처 카드에서 확인합니다. 추가 정보는 같은 대화에서 반영하며, 해결 후 사용자 확인을 거친 조건·답변·근거를 기존 경험 온톨로지에 저장합니다. 대화·조사 검토와 별도 업무 경로는 유지합니다.</p><p><b>적용:</b> ZIP과 실행 TXT를 같은 TRANSFER 폴더에 업로드한 뒤 <code>bash MAIN151_ONECLICK_R1.txt</code> 한 줄을 실행하세요. 기존 <code>~/DEV</code> 링크의 실제 checkout을 찾아 검사·백업·코드 교체·검증합니다. 이후 GUIDE.txt의 commit/push 및 새 코드서빙 리비전 절차를 진행하고, 별도 워크플로우 편집기에 MAIN151_WORKFLOW.py 전체를 반영하세요. 기존 원문·Oracle/NFS·모델 연결 설정은 유지합니다.</p><p><b>완료 확인:</b> <code>MAIN151_ONECLICK_DONE</code>, <code>MAIN151_EXIT=0</code>. 워크플로우 표시 버전은 <code>workflow-guided-explanation-20261105-r3</code>입니다. 중단·재개·원복과 환경별 확인은 GUIDE.txt에 있습니다.</p><p><b>검증:</b> 핵심42검사, 준비본39 재확인, 실제 선택 서비스38/Gold 코드 연결9항목 통과. 정확한 첨부 실행 명령의 설치·재실행·commit·코드 및 데이터 세대 검사·원복을 격리 checkout에서 확인했습니다. 서빙531파일은 메인과 일치하고, 자바스크립트는 첨부에서 제외하여 기존 의존성 해시를 검사합니다.</p><p><b>실제 Qwen 한계:</b> 기존 CM003 원문으로 시험한 최신 최종 단계는 24.752초/1회, 재검토·보완0회였습니다. 설명과 추가 질문은 나왔지만 예외 설명 누락이 남아 있습니다. 전체 검색 성능·법률 정확성·실제 Qwen 연속 대화/온톨로지 저장을 인증한 결과는 아닙니다. 현장 GENOS 내부 모델·새 리비전·화면 확인은 별도입니다.</p><p>첨부6개: 전체 코드 ZIP, 실행 TXT, 워크플로우 Python, GUIDE.txt, VERIFICATION.json, SHA256SUMS.txt.</p>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':html}}]
meta=[]
for n in names:
 p=H/n;typ='application/zip' if p.suffix=='.zip' else 'application/json' if p.suffix=='.json' else 'text/x-python' if p.suffix=='.py' else 'text/plain'
 parts.append({'mime_type':typ,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode()}})
 meta.append({'filename':n,'mime_type':typ,'bytes':p.stat().st_size,'sha256':sha(p)})
mail={'to':'hyungjininfocz.son@partner.samsung.com','subject':subject,'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids','snippet']}
path=Path('/tmp/adr1410-mail-payload.json');path.write_text(json.dumps(mail,ensure_ascii=False))
put(H/'EMAIL_PREPARED.json',{'to':mail['to'],'subject':subject,'attachments':meta,'payload_path':str(path),'payload_sha256':sha(path),'payload_bytes':path.stat().st_size,'authorization':'메인에 반영하고 삼성메일로 쏴줘'})
print('Email ready',len(names),'attachments',path.stat().st_size,'bytes')
