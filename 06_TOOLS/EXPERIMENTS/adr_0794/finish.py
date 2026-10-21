from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');ptr=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/ptr['manifest_path']);active=read(A/'artifacts/active-consumer-v2.json');live=read(A/'artifacts/live/diagnostic.json');integrated=read(A/'artifacts/working-integration.json')
assert ptr['release_id']=='definition-entry-navigation-20261015-r1' and ptr['generation']==72
assert all(active['checks'].values()) and release['files']==f['serving_files']
C=R/release['code_root'];assert all(sha(C/n)==h for n,h in release['files'].items())
core=[n for n,h in release['files'].items() if h!=read(D/'baseline.json')['manifest']['files'].get(n) and not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json'];assert all(sha(R/n)==sha(C/n) for n in core)
profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');assert profile['candidate_navigation']['definition_entry'] is True
receipt={'status':'PASS','environment':'WSL local','active_pointer':ptr,'release_code_root':release['code_root'],'data_path':release['data_path'],'serving_files_verified':len(release['files']),'candidate_code_identical':True,'changed_working_runtime_files_identical':core,'preserved_unrelated_working_differences':integrated['preserved_other_working_differences'],'actual_service_checks':active['checks'],'known_public_case':{'model_calls':live['model_calls'],'initial_definitions':live['initial_navigation_has_definitions'],'target_original_acquired':live['target_original_evidence_count']>0,'target_in_final_answer':live['target_coordinate_in_answer'],'accepted_outcome':live['accepted_outcome']},'genos_deployed':False,'git_main_merged':False}
put(A/'artifacts/active-verification.json',receipt)
text=f'''로컬 MAIN72 완료 — 2026-10-15

스키마 오류의 의미
- 스키마는 LLM의 답변이 아니라 호출 코드가 보내는 출력 규격이다.
- 과거 call015는 Parasail HTTP400 Grammar error: schema too large로 생성 전에 거절됐다.
- 답변을 내용이 어렵다고 버린 사건이 아니다. 행동별 전체 객체 규칙을 중복한 외부 문법 설계 문제였다.
- 제공자용 문법만 단일 기본 형식으로 줄였다. 과거 실패 입력 기준43,804→12,934바이트.
- 원래 서버 스키마·현재 상태·근거·권한·버전 검증은 그대로 수행한다. 잘못된 출력은 기존 bounded repair 경로로 처리한다.

최초 검색의 정의 연결
- 질문 원문의 용어를 저장된 문서 정의에서 찾는다. 정확한 표기/공백 정규화, 단어 경계, 긴 명칭 우선.
- 정의의 원문 위치와 definition_reference의 명시 참조 대상을 첫 모델 메뉴의 READ_ARTICLES로 제시한다.
- 참조 캐시가 원문 읽기 뒤에 채워지는 의존성을 제거하고, 불변 reference 저장소를 직접 조회한다.
- 정의/참조의 원문·해시와 출발/도착 문서 권한을 확인한다. 여러 정의와 미확인 적용 범위는 보존한다.
- 기존 전문검색·구조검색을 유지한다. 페이지는8개씩, 다음 페이지와 재시작 상태를 결속한다.
- 위치 후보는 근거 채택이 아니다. 실제 원문 읽기와 검증을 거친 뒤 판단한다.

실제 확인
- 관련 계약516건 통과. 실제 서비스/API8건은 후보와 활성 릴리스 각각 통과.
- 기존 MAIN71의 실패5건을 별도로 재현해 신규 회귀와 구분했다. 역사적 도구37개 검사에는 신규 페이지 도구1개를 추가한 검사로 보완했다.
- 동일 공개 scope15,777조문, 기존 초기 회수12개 동일. 첫 읽기 후보25→27개이며 기존25개를 모두 보존했다.
- 유동성비율 → 시행세칙 제2-8조의3 → 금융투자업규정 제3-24조의4제2항이 첫 입력에 제공됐다.
- Qwen 첫 읽기 선택에서 정의와 대상 조문을 골랐고 원문을 확보했다. 최종 답변에도 제3-24조의4를 포함했다.
- Qwen3.8/Parasail FP8/reasoning none/no fallback6회, {live['seconds']:.1f}초, 제공자 오류0.
- 모델 출력 형식 거절1건은 원본 기록을 유지하고 기존 복구 경로를 거쳤다. 최종 저장 상태는 ANSWER/COVERED다.
- 알려진 공개 사례다. 답변 전체 정확도·다른 질문 일반화를 인증하지 않는다.

실제 배선
- release: {ptr['release_id']}
- pointer generation: {ptr['generation']}
- release manifest SHA256: {ptr['release_manifest_sha256']}
- candidate: {f['code_root']}
- serving: {release['code_root']}
- data: {release['data_path']} (MAIN71과 동일 원문·정의·참조·검색 세대)
- 검증 후보와 선택329개 파일 hash 동일. 변경한 작업 runtime 파일도 동일; 다른 기존 작업 변경은 보존.
- WORKING integration: artifacts/working-integration.json
- actual service binding: artifacts/active-consumer-v2.json 및 artifacts/active-verification.json
- apply receipt: artifacts/main-apply.json
- 과거 MAIN71/백업: artifacts/working-before 및 design/baseline.json
- 정식 원복은 stable rag_main_promotion.py rollback의 해당 apply receipt/hash를 사용한다.
- ADR0793 첫 연결 실패는 보존했고 ADR0794 별도 기술 감사로 교정했다.
- ADR0793/0794 final validation 통과. 전체 graph의 기존 오류8건은 남아 있고 두 ADR의 신규 오류는 없다.
- GENOS 미배포. Git main 병합 없음.
'''
(A/'MAIN_RESULT.txt').write_text(text)
p=R/'AGENTS.md';s=p.read_text().replace('`risk-committee-team-metadata-20261015-r1`(포인터 generation 71)','`definition-entry-navigation-20261015-r1`(포인터 generation 72)');p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text();s=s.replace('2026-10-15 현행 로컬 RAG **MAIN71','2026-10-15 이전 로컬 RAG **MAIN71',1);intro='2026-10-15 현행 로컬 RAG **MAIN72 `definition-entry-navigation-20261015-r1`**은 질문에 일치하는 저장 정의와 명시 참조 조문을 첫 탐색 읽기 후보에 제공한다. 정의·참조 원문/해시·권한을 검사하며 기존 전문검색을 보존한다. 외부 제공자 문법의 반복 행동 조건을 줄이고 서버의 원래 검증을 유지했다. 계약516건, 후보/활성 실제 서비스8건씩, 선택329파일 hash 확인. 공개 유동성 사례에서 첫 선택으로 정의와 제3-24조의4제2항을 읽고 최종 답변에 포함했다. 알려진 사례이며 일반 답변 정확도 미인증, GENOS 미배포. [검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding/MAIN_RESULT.txt).\n\n';idx=s.index('\n')+1;s=s[:idx]+'\n'+intro+s[idx:].lstrip('\n');s=s.replace('현재 결합 세대 선택은 위 MAIN71','현재 결합 세대 선택은 위 MAIN72').replace('현재 선택은 위 MAIN71','현재 선택은 위 MAIN72');p.write_text(s)
p=R/'01_DATA/README.md';s=p.read_text().replace('2026-10-15 로컬 MAIN71은','2026-10-15 로컬 MAIN72는 MAIN71과 동일한',1);s=s.replace('이후 로컬 선택은 위 MAIN71 기록','이후 로컬 선택은 위 MAIN72 기록');idx=s.index('\n')+1;s=s[:idx]+'\nMAIN72의 정의·명시 참조 최초 탐색 연결은 데이터를 재구축하지 않고 기존 색인을 소비한다. [실제 연결 검증](../04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding/MAIN_RESULT.txt).\n'+s[idx:];p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text();anchor='- 2026-10-15 원인 정정/부분 완료:';i=s.index(anchor);s=s[:i]+'- 2026-10-15 최초 정의 연결/문법 수정 완료: [ADR-0794](../04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding/MAIN_RESULT.txt), 로컬 MAIN72. 첫 메뉴에서 정의와 명시 참조 조문을 함께 읽을 수 있으며 실제 Qwen이 유동성 제3-24조의4제2항을 읽고 답변에 포함했다. 제공자 schema too large는 재발하지 않았다. 알려진 사례여서 답변 전체 정확도·일반화 개선은 계속 별도 관리한다.\n'+s[i:];p.write_text(s)
print('MAIN72 verified: 329 serving files, 8 actual consumer checks, working delta integrated')
