from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0809-system-mechanics-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');ptr=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/ptr['manifest_path']);active=read(A/'artifacts/active-consumer-v2.json');working=read(A/'artifacts/working-integration.json')
assert ptr['release_id']=='system-owned-workflow-20261015-r1' and ptr['generation']==75
assert all(active['checks'].values()) and release['files']==f['serving_files']
assert all(sha(R/release['code_root']/n)==h for n,h in release['files'].items())
wt=(A/'artifacts/working-tests.txt').read_text();assert not re.search(r'\b[1-9]\d* failed\b',wt);working_count=int(re.findall(r'(\d+) passed',wt)[-1])
receipt={'status':'PASS','environment':'WSL local','active_pointer':ptr,'release_code_root':release['code_root'],'data_path':release['data_path'],
 'serving_files_verified':len(release['files']),'candidate_code_identical':True,'actual_service_checks':active['checks'],
 'working_tests':working_count,'preserved_unrelated_working_differences':working['preserved_other_working_differences'],
 'quality_certified':False,'genos_deployed':False,'git_main_merged':False}
put(A/'artifacts/active-verification.json',receipt)
text=f'''대사 워크플로우의 기계적 처리 이관 — 로컬 MAIN75 반영 완료

시스템으로 이관한 처리
- 부모가 정한 쟁점·내규/외규 조사 과제·사용자 사실을 자식에게 그대로 전달합니다. 자식의 같은 질문 재해석 호출을 없앴습니다. 1~12개 쟁점을 각각 보존합니다.
- 정확한 원문 인용은 선택 ID에서 복원합니다. 모델이 원문·줄바꿈·현재 식별자·상태 버전·기준일을 다시 쓰지 않습니다. 근거·쟁점·명시 참조 끝점은 현재 제시된 선택지만 허용합니다.
- 질문의 정의 원문과 확인된 명시 참조를 최초 조사에서 기존 원문 읽기 도구로 확보합니다. 읽었다는 이유로 자동 채택하지 않습니다.
- 자식의 구조화된 판단을 시스템이 답변 형태로 조립합니다. 자식의 추가 문장화 모델 호출을 없앴습니다.
- 이미 확인된 적용/근거 부족은 시스템이 보류 행으로 조립합니다. 그 보류를 다시 판단하려는 모델 호출을 없앴습니다.
- 쟁점별 비교행을 즉시 저장합니다. 뒤 쟁점의 실패가 앞의 통과 행을 지우지 않으며 재시작 시 저장된 행을 검증해서 재사용합니다.
- 종료/읽기 등 각 행동에서 사용하지 않는 배열은 정해진 규칙으로 비웁니다. 원래 출력과 변경 규칙은 남기고 전체 정본 검사를 다시 합니다. 원문 채택·의미·권한·상태 식별자는 임의로 고치지 않습니다.
- 추가 조사에서도 사용자 사실은 부모의 원래 질문에 결속합니다. 추가 조사 지시를 사용자 사실로 취급하지 않습니다.
- 최종 표·근거 카드는 실제 비교행에서 인용한 원문과 필요한 근거 경로만 표시합니다. 비교행이 없을 때 자식의 전체 근거를 대신 쏟아내던 동작을 제거했습니다.

함께 고친 연결 오류
- 외부 생성 형식에서 행동별 필수 의미 선택(gap_ids 포함)이 사라지던 문제를 수정했습니다. 같은 행동의 대체 입력 형식은 유지합니다.
- 공백이 아닌 문자가 있어야 한다는 정규식을 전체 문자열 조건으로 명시했습니다. 실제 Qwen에서 한 글자 이유/공백 반복이 사라지고 정상 문장 이유가 반환되는 것을 관측했습니다. 공급자 내부 구현 원인은 직접 확인하지 않았습니다.
- 연결 전에 실패했음이 확인되는 오류만 단일 담당이 제한 재시도할 수 있도록 분류했습니다. 전송 완료 여부가 불명확한 오류는 자동 재전송하지 않습니다.
- 긴 비모델 질문의 검색식 길이를 기존 원문 RAG 계약에 맞췄으며 전체 질문/쟁점은 보존합니다.

LLM에 남긴 책임
- 질문의 의미와 여러 쟁점 구분, 검색어·다음 조사 대상 선택, 원문 채택·해석, 내용 차이와 법률 적용·부합/상충 판단입니다.
- 검증기는 형식·원문·권한·판본·상태 계약을 검사하는 시스템 코드입니다. 형식 통과를 정답으로 인정하지 않습니다.

검증과 실제 모델 결과
- 최종 후보269개 계약·회귀 검사 통과. 코드가 같은 별도 기술 자격검증의 신규 경계8검사 통과.
- 통합한 작업 코드 {working_count}검사 통과. 후보 실제 로컬 서비스12검사와 활성 MAIN 실제 로컬 서비스12검사 통과.
- 모의 응답을 쓰는 실제 API에서 내규→외규→근거 관계→대사 비교→표시, 복구/재시작/예산/중복/권한/해시/상태 경계를 확인했습니다.
- 실제 Qwen 전체 질의(ADR0807)는24호출/769.33초, partial, 최종 비교0행입니다. 자식 질문 재해석0·자식 문장화0을 확인했습니다. 실제 결과의 재시작9검사 및 동일 요청4검사도 통과했고 추가 모델 호출은0입니다.
- 그 기록의 실패한 BASIS 입력을 최종 수정으로1회 재생(ADR0808)했으며75.74초,3개 짝이 정본 검증을 통과했습니다. 추가 비교 모델 호출 없이 시스템이3개 보류 행을 만들고 인용을 검증했습니다. 이 재생은 전체 RAG 재실행이 아닙니다.
- 필요한 내규·별표10·적용 판본/조건 확보 및 전체 법률 답변 정확도는 미해결입니다. 위 보류 행을 부합 판정이나 정답3건으로 세지 않습니다.
- ADR0803~0808의 실패·중단·부분 성공은 각각 보존했습니다. ADR0809는 의미 품질 우회가 아니라 사전 동결한 새로운 유한 소프트웨어 경계의 자격검증입니다.
- ADR0809 최종 구조 검사 통과. 전체 graph의 기존 오류8개 외 이번 계보의 새 오류 없음.

실제 연결과 원복
- release: {ptr['release_id']}
- pointer generation: {ptr['generation']}
- release manifest SHA256: {ptr['release_manifest_sha256']}
- serving code: {release['code_root']}
- data: {release['data_path']}
- 선택338파일과 검증 후보의 해시가 동일합니다. 변경한 소스/공통 실험 연결부는 작업 코드에 통합했으며 다른 작업 차이36개는 덮어쓰지 않았습니다.
- 프로필/원문 세대/검색 정책/실제 서비스 binding: artifacts/active-consumer-v2.json 및 active-verification.json.
- 적용 영수증: artifacts/main-apply-receipt.json. 작업 코드 백업: artifacts/working-before. 이전 MAIN74 포인터/코드/데이터는 릴리스 rollback에 보존합니다.
- 현재 선택이 이 릴리스일 때 원복: .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
- Git main 병합·push 및 GENOS 반입·배포·현장 검증은 수행하지 않았습니다.
'''
(A/'MAIN_RESULT.txt').write_text(text)
p=R/'AGENTS.md';s=p.read_text();old='`workflow-adopted-evidence-20261015-r1`(포인터 generation 74)';assert old in s;s=s.replace(old,'`system-owned-workflow-20261015-r1`(포인터 generation 75)',1);p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text().replace('현행 로컬 RAG **MAIN74','이전 로컬 RAG **MAIN74',1);i=s.index('\n')+1;s=s[:i]+'\n2026-10-15 현행 로컬 RAG **MAIN75 `system-owned-workflow-20261015-r1`**는 대사의 질문 재해석·인용 복사·고정 필드·정의 원문 읽기·자식 문장화·보류 재판단·행 저장/재개·최종 근거 표시를 시스템에 맡긴다. 의미 판단은 모델에 유지한다. 후보269/신규기술8/활성서비스12 검사, 선택338파일 동일. 전체 Qwen 유동성 질의는 partial·0행이며 수정한 BASIS 재생의3짝/3보류행과 구분한다. [완료·한계·원복](../04_EXPERIMENTS/ADR/ADR-0809-system-mechanics-qualification/MAIN_RESULT.txt). GENOS 미반영.\n'+s[i:];p.write_text(s)
p=R/'07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md';s=p.read_text().replace('현행 로컬 MAIN74','이전 로컬 MAIN74',1);i=s.index('\n')+1;s=s[:i]+'\n현행 로컬 MAIN75는 부모의1~12쟁점/사실을 자식에 재해석 없이 연결하고 인용·ID·정의 읽기·자식 조립·보류·중간 행 저장·표시를 시스템이 처리한다. 모델은 의미 선택·해석·차이·적용 판단을 맡는다. 최종 인용만 표시하며 비교행이 없을 때 전체 자식 근거를 대신 표시하지 않는다. [검증과 한계](../../../04_EXPERIMENTS/ADR/ADR-0809-system-mechanics-qualification/MAIN_RESULT.txt). GENOS 미반영.\n'+s[i:];p.write_text(s)
p=R/'04_EXPERIMENTS/ADR/README.md';s=p.read_text();i=s.index('\n')+1;s=s[:i]+'\n- [ADR-0809 시스템 소유 처리 MAIN75](ADR-0809-system-mechanics-qualification/MAIN_RESULT.txt) — 후보269·신규기술8·활성서비스12,338파일 동일. 실제 전체 Qwen partial/0행과 고정 BASIS 재생3짝/3보류행 구분. GENOS 미반영.\n'+s[i:];p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text()+'''\n## 2026-10-15 · MAIN75 대사 기계적 처리 이관 완료

- [완료 기록](../04_EXPERIMENTS/ADR/ADR-0809-system-mechanics-qualification/MAIN_RESULT.txt): 부모 쟁점 전달·정확 인용/ID 결속·정의 원문 읽기·자식 조립·보류·행 저장/재개·최종 인용 표시를 시스템에 이관했다.
- 후속: 필요한 내규/별표10/적용 판본 확보와 의미 판단 개선, 최종 수정 이후 전체 실제 질의의 추가 품질 검증. 고정 입력 재생3개 보류 행은 정답 인증이 아니다. GENOS 현장 반입/워크플로우 검증은 아직 수행하지 않았다.
''';p.write_text(s)
print('MAIN75 verified;338 identical files; working tests',working_count,'active service12; legal accuracy unqualified; GENOS unchanged')
