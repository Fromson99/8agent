from pathlib import Path
import hashlib,json,re,urllib.request,xml.etree.ElementTree as ET
R=Path.cwd();A=R/'04_EXPERIMENTS/ADR/ADR-0713-legal-knowledge-lab-deduction';C=R/'02_BACKEND/lawrag/research/candidates/adr_0713/lab'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(A/'artifacts/design/baseline.json');binding=read(A/'artifacts/design/launch-binding.json');browser=read(A/'artifacts/browser-final-rev7/result.json');assert browser['status']=='PASS'
suites=ET.parse(A/'artifacts/run-001/contracts-rev6.xml').getroot().findall('testsuite');tests=sum(int(s.attrib['tests']) for s in suites);failures=sum(int(s.attrib['failures'])+int(s.attrib['errors']) for s in suites);assert tests==25 and not failures
# rev007 changed only human-readable symbolic rendering. Verify all Python
# implementation bytes equal the rev006 code used by the contract suite.
for f in (C/'revisions/rev-006/snapshot/02_BACKEND/knowledge_lab').glob('*.py'):
 assert sha(f)==sha(C/'revisions/rev-007/snapshot/02_BACKEND/knowledge_lab'/f.name),f
qa=read(A/'artifacts/qa-setup-final/result.json');assert qa['http_status']==200 and qa['model_calls']==0
assert sha(C/'revisions/rev-003/snapshot/02_BACKEND/knowledge_lab/qa.py')==sha(C/'revisions/rev-007/snapshot/02_BACKEND/knowledge_lab/qa.py')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for n,h in b['working_files'].items():assert sha(R/n)==h,n
html=urllib.request.urlopen('http://127.0.0.1:5581').read().decode();token=re.search(r'name="lab-token" content="([^"]+)"',html).group(1)
request=urllib.request.Request('http://127.0.0.1:5581/api/status',headers={'X-Lab-Token':token});status=json.load(urllib.request.urlopen(request));assert status['main_unchanged']
result={'schema_version':'knowledge-lab-audit-v1','status':'complete','revision':binding,'baseline':{'release':b['pointer']['release_id'],'generation':b['pointer']['generation'],'pointer_sha256':b['pointer_sha256']},'contracts':{'tests':tests,'passed':tests,'failed':failures,'path':'artifacts/run-001/contracts-rev6.xml','final_python_byte_identical':True},'browser':browser,'qa_setup':{'status':'PASS','http_status':200,'model_calls':0,'loaded_modules':qa['loaded_modules'],'final_qa_byte_identical':True},'live_status':status,'model_calls':0,'production_changes':False,'main_promotion':False,'genos_deployed':False,'quality_certified':False,'limitations':['Real legal quality and performance not evaluated','Natural-language extraction is structural atomization, not automatic verified logical formalization','Derived knowledge is sandbox-only and not injected into current RAG answers','Original-source changes require explicit reviewed unit revision; no live legal source revalidation daemon','Local operator tool, not a multi-user deployment']}
put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','binding_unchanged':True,'release_id':b['pointer']['release_id'],'generation':b['pointer']['generation']},'lab':{'status':'complete','tests':25,'passed':25,'browser_checks':len(browser['checks']),'qa_setup':'PASS'}},usage={'model_calls':0,'input_tokens':0,'output_tokens':0},latency={'not_measured_reason':'Engineering contract audit; no real model answer or latency benchmark'},error_taxonomy=[],judge_disagreements=None)
m['design']['resolved_baseline']={'path':'artifacts/design/baseline.json','sha256':sha(A/'artifacts/design/baseline.json'),'release_id':b['pointer']['release_id'],'generation':b['pointer']['generation'],'note':'Initial read/claim scope referenced MAIN49; the immutable baseline captured at design freeze was already MAIN50, changed by work outside this task. This task never wrote the active pointer.'}
put(A/'실험/manifest.json',m)
front=(A/'README.md').read_text().split('---',2)[1]
body='''
# ADR-0713: legal_wiki 연역 합성과 독립 지식 연구실

## 1. 결정 요약

로컬 연구용 구현과 새 화면을 완성했다. MAIN 작업 코드·활성 포인터·원본 shortcut DB·원문/온톨로지 세대는 변경하지 않았다. 실제 법률 품질 실험이 아니므로 Proposed, decision_eligible=false, MAIN unchanged를 유지한다.

[사용 안내](USAGE.md) · [실행 결과](artifacts/run-001/result.json) · [검증 인덱스](실험/README.md).

첫 조회는 MAIN49였다. 구현 전 동결한 baseline.json은 이미 다른 작업에서 갱신된 `compact-input-20261009-r1`, generation50이다. 이 baseline과 이후 포인터/작업 파일의 동일성을 검사했다. 초기 claim의 MAIN49 문구는 원래 선점 이력으로 보존한다.

## 2. 문제와 변경 전 구조

기존 shortcut/위키에는 조건·원문·관계가 있지만 타입 있는 규칙 합성 및 증명 검사기가 연결되지 않았다. 기존 지식 조회 화면과 별도로 질문·답변, 조사 경로, 위키, 용어 관계 및 증명을 함께 확인할 필요가 있었다.

## 3. 가설과 사전 판정 기준

[구현 전 동결 계약](artifacts/design/contracts.json)을 기준으로 안전한 Horn 추론, 동일 대상/사건/시점/관할/세대, 권한 교집합, 명시 부정, 가설 의존성, 원본 불변, 저장 이력과 화면 동작을 검사한다. 모순 우회·증명 위조·외부 반출·원본 쓰기는 실패다. 법률 답변 정확도와 속도 개선 기준은 이번 감사 범위에 없다.

## 4. 실험 설계

| arm | 변경 | 고정 / 격리 |
|---|---|---|
| baseline | 선택 코드·원문·포인터 읽기 전용 감사 | 동결 MAIN50와 작업 파일 해시 |
| lab | 연역 엔진·별도 SQL·새 API·새 화면 | candidate snapshot rev-007, explicit research runner, 원본 DB mode=ro |

독립 제품 후보 비교나 holdout이 아닌 구현 계약 감사다. 가상 A/B/C/D/X/Y/K 사례를 사용했다. 실제 운영 registry에 등록하지 않았으며 PIPELINE과 기존 앱을 수정하지 않았다.

## 5. 데이터·모델·재현성

기존 shortcut 저장소 204개 지식(게시51·재검증51·중단102), 선택된 navigation의 용어245,569·관계48,101·정의10,092개를 페이지 조회한다. 원문 및 색인을 복제하지 않는다. 분해된 실제 원자 후보는 DRAFT이며 절차를 법률 규칙으로 승격하지 않는다.

검증의 외부 모델 호출은0회다. 수동 공개 질문 기능은 고정된 기존 RAG를 별도 프로세스·상태로 실행하고, ExperimentClient의 Qwen3.8/Parasail FP8/reasoning none/fallback 없음 정책을 사용한다. 공개 질문 표시와 기존 승인 문서 범위를 검사한다. 내부 위키/shortcut/연구 규칙을 모델 입력에 자동 추가하지 않는다.

## 6. 결과

- 연역·규칙 합성·저장·API·실제 원본 조회 계약25개 통과.
- 실제 Chromium에서 주요 화면/검색/수정/이력/분해/증명/파생저장/재로드/모바일을 포함한10개 검사 통과. 브라우저 오류0개.
- 선택된 RAG의 실제 create_app/health200, 모델0회. semantic_runtime과 lawrag 의존성이 모두 고정 릴리스에서 로드됨을 확인했다.
- 최종 rev-007은 rev-006에서 증명 화면의 내부 임시 상수를 읽기 쉬운 변수로 표시하는 JavaScript만 변경했다. Python 파일 전부와 계약 검사 코드의 동일성을 확인했다.
- 신규 경로 X∧Y∧C→D, A∧C의 K 정의, 미확인 C 반환, 역함의·사건혼합·타입오류·권한누락·순환 차단, 위조증명 거부, 규칙 철회 및 가설 의존성 보존을 확인했다.

## 7. 사례별 오류 분석

초기 브라우저 환경에 Chromium 공유 라이브러리와 한글 폰트가 없어 임시 로컬 의존성과 이미 설치된 Windows 글꼴로 검사했다. 앱 외부 네트워크 글꼴 요청은 없다. favicon404와 반복 보조정리 중복 저장을 수정했다. 중간 전제의 모순을 cached lemma가 우회할 수 있는 경로를 검토에서 찾아 proof guard로 보강하고 회귀 검사를 추가했다. 증명 검사기의 실제 파일 해시를 계약에 결속했다. 이전 검사 로그·화면·연구 데이터는 삭제하지 않았다.

## 8. 비용·지연·회수 규모

신규 모델 호출/입력/출력 토큰0. 실제 질의 지연·정답률·회수율·선택률은 측정하지 않았다. 원문 DB는 공유한다. 후보 코드 전체 약1.5MiB, 검사 화면/영수증 약6MiB, 연구 SQL 약0.2MiB 수준이다. 용어 전체 카탈로그 건수를 retrieval recall로 표현하지 않는다.

## 9. 해석

형식 규칙에서 새 경로를 만들고 검증·저장·재사용하는 초기 구현이 동작한다. 형식 증명은 주어진 전제를 의미하며 실제 원문의 올바른 형식화나 법적 정당성을 인증하지 않는다. 정리의 중간 전제도 현재 사실에서 검사하므로 저장된 정리를 이유로 모순 검사를 생략하지 않는다.

## 10. 한계와 일반화 가능 범위

실제 위키를 일반 법률 규칙으로 자동 추출·검토하는 LLM EBL/술어 발명은 구현하지 않았다. 현재는 기존 구조의 원자 후보 분해와 명시적 술어·규칙/정의 등록이다. 원문 개정은 운영자가 규칙 revision에 반영해야 하며, 외부 원문 변경 자동 감시/형식화 재검증은 없다. 등록된 규칙 변경·철회와 검사기 변경은 파생 지식을 무효화한다.

자연어 RAG와 형식 증명은 같은 화면 안의 별도 실행이다. 새 증명을 현재 RAG 답변에 자동 주입하거나 MAIN·GENOS에 반영하지 않는다. 실제 모델 답변 품질·추론 성능은 미검증이다. 로컬 단일 운영자 도구이며 여러 사용자에게 공개하는 서버가 아니다.

## 11. 운영 결정·롤백 조건

사용자 지시에 따라 MAIN 미반영. 운영 코드 통합, MAIN 승격, Git main 병합, GENOS 반입/배포는 모두 미수행이다. 연구 서버를 중지하면 기존 서비스만 남는다. 원본 파일의 원복 작업은 필요 없다. 연구실 데이터는 append-only revision과 이벤트를 보존한다.

## 12. 재현 명령

```bash
cd /home/jin/8-AGENT
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0713/run_lab.py --port 5581
.venv/bin/python -m pytest 06_TOOLS/EXPERIMENTS/adr_0713/test_contracts.py -q --override-ini addopts=''
.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0713/lab
```

브라우저 검증 명령과 시스템 의존성은 [사용 안내](USAGE.md)에 기록했다. 해시와 원시 검사 자료는 [artifact manifest](artifacts/manifest.json)를 따른다.
'''
(A/'README.md').write_text('---'+front+'---\n'+body)
(A/'실험/README.md').write_text('''# ADR-0713 검증 인덱스

구현 계약 감사이며 실제 법률 질문 평가·정답 채점은 수행하지 않았다. 질문 파일은0개다. reservation의 선점 이력은 manifest에 보존한다.

| 확인 | 결과 | 근거 |
|---|---|---|
| MAIN50 기준 결속·원본 불변 | 통과 | [baseline](../artifacts/design/baseline.json), [최종 결과](../artifacts/run-001/result.json) |
| 연역·저장·API 계약 | 25/25 | [JUnit](../artifacts/run-001/contracts-rev6.xml) |
| 새 화면 | 10개 검사 통과 | [브라우저 기록](../artifacts/browser-final-rev7/result.json) |
| 기존 RAG의 격리 실행 환경 | HTTP200·모델0회 | [실제 배선](../artifacts/qa-setup-final/result.json) |

사전 가설은 조건·권한·원문·원본 불변을 지키는 제한된 연역과 별도 화면을 구현할 수 있다는 것이다. 후보 정답률·paired delta·회수 원장·judge는 이 감사에 해당하지 않는다. 상세 조건과 arm/run/revision은 [manifest](manifest.json)에 있다. MAIN 및 GENOS 반영은 없다.
''')
print('result recorded',tests,len(browser['checks']))
