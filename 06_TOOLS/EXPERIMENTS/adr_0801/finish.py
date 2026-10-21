from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');ptr=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/ptr['manifest_path']);active=read(A/'artifacts/active-consumer-v2.json');working=read(A/'artifacts/working-integration.json')
assert ptr['release_id']=='workflow-adopted-evidence-20261015-r1' and ptr['generation']==74
assert all(active['checks'].values()) and release['files']==f['serving_files']
assert all(sha(R/release['code_root']/n)==h for n,h in release['files'].items())
assert '101 passed' in (A/'artifacts/working-tests.txt').read_text()
receipt={'status':'PASS','environment':'WSL local','active_pointer':ptr,'release_code_root':release['code_root'],'data_path':release['data_path'],'serving_files_verified':len(release['files']),'candidate_code_identical':True,'actual_service_checks':active['checks'],'preserved_unrelated_working_differences':working['preserved_other_working_differences'],'known_real_qwen_comparison_rows':0,'known_real_qwen_status':'partial','genos_deployed':False,'git_main_merged':False}
put(A/'artifacts/active-verification.json',receipt)
text=f'''대사 근거 전달 최적화 — 로컬 MAIN74 반영 완료 (2026-10-15)

구현
- 자식 RAG가 읽은 전체 원문 대신, 반환한 SELECT/ASSESS 판단에 결속된 채택 span만 전달합니다.
- 원문 좌표·해시·권한을 검사하고 새 정규 evidence ID로 묶습니다. 중복 원문은 합치고 각 claim의 조건·예외 의존성과 출처를 보존합니다.
- 과거 조사 기록은 자식 journal에 보존합니다. 현재 revision의 근거만 비교에 활성화합니다.
- 비교 입력을 제한된 묶음으로 전달하고 실제 표시한 ID만 검증에 허용합니다. 불완전한 조건·판본으로 부합/상충을 확정하지 않습니다.
- 필요한 문맥은 이미 읽은 원문에서 먼저 복원합니다. 추가 조사는 같은 사건과 총 예산을 유지합니다.
- 최종 표에서 인용한 근거만 표시합니다. 비교 미완료 결과는 채택된 자식 근거만 제한적으로 표시합니다.
- 사용자 질문과 조사 지시를 분리했습니다. 인용은 원문 선택지로 제약하며 잘못된 인용을 사후 잘라 통과시키지 않습니다.
- 기존 정의 연결 최초 검색과 최신 문서 선택을 유지했습니다. workflow 버전1.1.0입니다.

측정
- 같은 ADR0795 자식 반환 기록을 재생: 전달94→16근거, 원문45088→1132자, 비교 입력128976→26301자.
- 채택 판단의 의존 조문11개를 모두 보존했습니다. 이 집합은 법률 정답 집합이 아닙니다.
- 의미상 필요한 문맥은 추가될 수 있으므로 최종 근거 개수를 고정한 정책은 아닙니다.

검증
- 동결 코드278계약, UI4검사 통과. 작업 코드101계약 통과.
- 후보 실제 로컬 서비스12검사, 활성 MAIN 실제 로컬 서비스12검사 통과.
- 통제된 모델 응답을 쓰는 실제 native API에서 내규 RAG→외규 RAG→근거 관계→비교→표시 및 재시작/복구를 검사했습니다.
- 실제 Qwen 결과는 별도입니다. ADR0800 7호출/136.02초, partial, 비교0행입니다.
  양측의 사용자 인용 오류는 해소했지만 내규 탐색 제안이 target과 exploration을 중복/누락했고,
  외규 호출은 전송 결과 미확인으로 중단됐습니다. 임의 재전송하거나 성공 근거로 기록하지 않았습니다.
  해당 실패 응답의 상태·중복·새 프로세스 재사용과 추가 호출0을 확인했습니다.
- 실제 유동성 정답 및 필요한 내규·외규 조문 회수 성공은 미해결입니다. 실제 LLM 대사 성공으로 보고하지 않습니다.
- ADR0797~0800의 기각 결과는 그대로 보존했습니다. ADR0801은 구현 코드 변경 없이 기능·실패·표시·서비스 경계로 사전 동결한 별도 감사입니다.
- ADR0801 final validation 통과. 전체 graph 기존 오류8개 외 이 작업의 새 오류 없음.

실제 연결
- release: {ptr['release_id']}
- pointer generation: {ptr['generation']}
- manifest SHA256: {ptr['release_manifest_sha256']}
- serving code: {release['code_root']}
- data: {release['data_path']}
- 선택336파일과 검증 후보 hash가 동일합니다. 다른 작업 코드 차이는 working-integration.json에 보존했습니다.
- 실제 서비스 binding/프로필/검색 정책/원문 세대: artifacts/active-consumer-v2.json 및 active-verification.json.
- 적용 영수증: artifacts/main-apply-receipt.json. 이전 MAIN73 포인터는 릴리스 rollback/ACTIVE_RELEASE.json에 보존합니다.
- 현재 선택이 이 릴리스인 것을 확인한 뒤 원복 명령: .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
- Git main 병합/푸시, GENOS 반입·배포는 수행하지 않았습니다.
'''
(A/'MAIN_RESULT.txt').write_text(text)
p=R/'AGENTS.md';s=p.read_text();old='`latest-document-selection-20261015-r1`(포인터 generation 73)';assert old in s;s=s.replace(old,'`workflow-adopted-evidence-20261015-r1`(포인터 generation 74)',1);p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text().replace('현행 로컬 RAG **MAIN73','이전 로컬 RAG **MAIN73',1);i=s.index('\n')+1;s=s[:i]+'\n2026-10-15 현행 로컬 RAG **MAIN74 `workflow-adopted-evidence-20261015-r1`**은 대사 자식의 채택 원문만 전달하고 현재 판단·조건 의존성·입력 한도·비교·표시를 연결한다. MAIN72 최초 정의 탐색과 MAIN73 최신 선택을 유지한다. 기능278계약/UI4/실제 서비스12 검사 통과. 실제 Qwen 유동성 질의는 partial·비교0행으로 미해결이며 기능 검증과 구분한다. [완료·한계·원복](../04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification/MAIN_RESULT.txt). GENOS 미반영.\n'+s[i:];p.write_text(s)
p=R/'07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md';s=p.read_text();i=s.index('\n')+1;s=s[:i]+'\n현행 로컬 MAIN74의 workflow1.1.0은 답변이 채택한 정확 원문 span만 전달한다. 조사 기록 전체는 자식 원장에 남고 비교/표시는 현재 근거와 필요한 문맥만 사용한다. 최종 표의 인용만 표시하며 불완전한 조건·판본은 보류한다. [기능 검증과 실제 질의 실패](../../../04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification/MAIN_RESULT.txt). GENOS는 미반영이다.\n'+s[i:];s=s.replace('"workflow_version": "1.0.0"','"workflow_version": "1.1.0"');p.write_text(s)
p=R/'04_EXPERIMENTS/ADR/README.md';s=p.read_text();i=s.index('\n')+1;s=s[:i]+'''\n- [ADR-0801 대사 근거 전달 MAIN74](ADR-0801-workflow-handoff-qualification/MAIN_RESULT.txt) — 같은 기록94→16근거/128976→26301자, 기능278·UI4·실제 서비스12 검사. 실제 Qwen 비교0행 한계 유지, GENOS 미반영.
- [ADR-0800 정확 원문 인용 선택](ADR-0800-workflow-literal-request-quotes/README.md) — 양측 인용 진입 성공, 내규 탐색 제안/외규 전송 결과 미확인으로 실제 비교 기준 미달.
- [ADR-0799 조사 지시 분리](ADR-0799-workflow-handoff-task-context/README.md) — 원래 질문 보존·최종 완전성 검사, 외규 모델의 인용 덧붙이기 반복.
- [ADR-0798 짧은 자식 질문](ADR-0798-workflow-handoff-scoped-question/README.md) — 실제 인용/탐색 실패 보존.
- [ADR-0797 채택 근거 전달](ADR-0797-workflow-adopted-evidence/README.md) — 전달 최적화 재생 통과, 실제 인용 실패 보존.
'''+s[i:];p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text()+'''\n## 2026-10-15 · MAIN74 대사 전달 기능 반영과 남은 실제 질의 실패

- [완료 기록](../04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification/MAIN_RESULT.txt): 채택 span 전달·현재 revision·제한 입력·최종 인용 표시. 같은 기록94→16근거, 입력128976→26301자. GENOS 미반영.
- 후속 미실행: 실제 유동성 정답 조문 회수, 탐색 제안의 target/exploration 중복·누락 반복, 전송 결과 미확인 이후 상태 조회 가능한 공급자 복구 경로, 적용 판본 검증. ADR0800 실제 결과는 partial·비교0행이다. 새 실험 기준 동결 후 개선하며 실패 호출을 근거 확보로 재분류하지 않는다.
''';p.write_text(s)
(R/'07_DOCS/REFERENCE/REPORTS/WORKFLOW_EVIDENCE_HANDOFF_20261015/IMPLEMENTATION_RESULT.txt').write_text(text)
print('MAIN74 verified:336 identical serving files; working101; active service12; actual Qwen comparison remains unavailable')
