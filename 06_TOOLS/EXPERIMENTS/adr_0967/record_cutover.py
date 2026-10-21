"""Record actual selection after the non-injected service consumer passes."""
from common import *
import shutil
A=ROOT/'09_ARTIFACTS/AUDITS/20261021-law-name-main';p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
c=read(ART/'consumer-active.json');assert c['status']=='PASS' and not c['app_injected'] and all(c['checks'].values())
assert p['release_id']=='law-name-recovery-20261021-r1' and p['generation']==98
m=read(ROOT/p['manifest_path']);s=read(ART/'stage.json');files=s['files']['candidate']
C=Path(c['code_root']);assert m['files']==files and all(sha(ROOT/n)==h and sha(ROOT/C/n)==h for n,h in files.items())
shutil.copyfile(ART/'consumer-active.json',A/'consumer-active.json')
save(A/'after-pointer.json',p)
save(A/'binding-check.json',{'all_working_candidate_selected_files_match':True,'file_count':len(files),'release_manifest_sha256':sha(ROOT/p['manifest_path']),'data_path':m['data_path'],'data_manifest_sha256':m['data_manifest_sha256'],'profile_sha256':c['profile_sha256'],'search_selection_fingerprint':c['search_selection_fingerprint'],'actual_service_binding':c['binding'],'workflow_version':c['workflow_version'],'quality_certified':False,'genos_verified':False})
graph=(A/'graph.json').read_text();errors=[x for x in graph.splitlines() if x.startswith('ERROR:')]
assert len(errors)==9 and not any('ADR-0965' in x or 'ADR-0966' in x or 'ADR-0967' in x for x in errors)
save(A/'graph-summary.json',{'existing_errors':errors,'new_scope_errors':[],'global_graph_passed':False})
summary=f'''로컬 MAIN98 적용 및 실제 서비스 선택 검증 완료

요청: 메인에 적용해봐 그리고 실험까지
릴리스: {p['release_id']}
workflow: {c['workflow_version']}
배포 근거: VALIDATED_ADR_PROMOTION / 품질 우회 없음 / quality_certified=false

법령명+제○조 조회 실패 → 조문 조건 제외 후 제목·별칭 형태소 검색 → 모델 후보 선택(RETRY_LAW_STRUCTURE) → 원래 조문 재조회 → 원문 읽기·전달 경로를 로컬 MAIN에 적용했다.
원래 조문·권한·상태·데이터 해시를 보존하며 이름 후보 자체는 근거가 아니다. 단일 본문 조문 쌍을 복구하며 후보는 최대8개다. 본문 전체에서 이름을 검색하는 방식은 아니다.

실험: ADR0966 신규 합성8사례×2arm, Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음.
기존8/8, 변경8/8. 변경의 이름 변형4/4가 실제 RETRY MATCH 뒤 정확한 조문 원문을 전달했다. 정확 이름2/2와 없는 조문·권한 범위 밖2/2 통과.
41물리호출(기존20/변경21), 입력155618·출력3446토큰, 보고 비용0.04001384 USD.
중앙 지연 기존5.62초/변경8.51초. 정확도·속도·비용 개선은 주장하지 않는다. 개발자 작성 합성8사례이며 일반 법률 답변 품질 인증은 아니다.

최종 통합 ADR0967: 모든 legal_agent 바이트를 위 모델 실험과 동일하게 유지했다. 최종 후보260계약 새 실행 통과, 기존7실패 제외(기능 추가 전에도 같은 실패로 재현). 원문·권한·해시·상태·중복·재개·API/응답 소비자 관련 검사를 포함한다.
후보/작업/실제 활성 서비스에서 각각 HEALTH200, 코스닥시장 상장지침 → 코스닥시장 상장규정 → 제2조 재조회와 원문 읽기를 통과했다.
실제 활성 검사는 앱 주입 없이 service.service.application()이 선택한 local-release에서 수행했다. 작업·후보·선택418파일 일치, 기존 데이터·모델 프로필·검색 선택 지문 유지. 최고 RSS 약{c['peak_rss_kib']/1024/1024:.2f}GiB, 무거운 실행은 순차 수행했다.

보존된 실패/제한:
- ADR0965: 첫 합성자료의 저장좌표 키 누락,54실제호출 및 ledger 기록 형식 오류. 무효 결과로 보존하며 승격 근거에서 제외했다.
- ADR0966: 모델 경로는 성공했으나 실제 데이터 캐시가 full_glossary compiler hash 불일치로 차단. 전체 통합 실패 상태를 보존했다.
- ADR0967: 무관한 구 full_glossary PLAN_SCHEMA/decision_schema 길이 제한 제거만 기존 캐시와 결속된 MAIN97 바이트로 유지. 작업본은 preserved-full_glossary.py.gz 및 감사 pre-integration에 무손실 보존했다. 다른 현재 RAG 글자 수 제한 제거 변경은 유지한다. 구 용어집 스키마 완화는 새 캐시 세대와 함께 별도 검증해야 한다.
- 전역 graph 기존9오류는 남고 이번 ADR0965~0967 관련 새 graph오류는 없다. ADR0966/0967 final validator 통과. ADR0965의 알려진 기록 형식 오류는 소급 수정하지 않았다.

MAIN97 복원(필요할 때만 실행):
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
복원은 이전 릴리스 콘텐츠를 선택하되 포인터 generation은 증가한다. 이전 포인터 previous-pointer.json, 릴리스 rollback/와 01_DATA/ACTIVE/local/receipts에 적용·복원 근거를 보존한다.

GENOS 반입·배포·내부 모델 검증 및 Git commit/push 미수행. 로컬 서빙 저장 방식을 GENOS Oracle 목표 구조의 구현 완료로 간주하지 않는다.
정본: authorization.json, validation.json, apply.json, consumer-active.json, binding-check.json, final-validation.txt와 ADR0967.
'''
(A/'RESULT.txt').write_text(summary)
block=f'''2026-10-21 사용자 “메인에 적용해봐 그리고 실험까지” 지시에 따라 **로컬 RAG MAIN98 / workflow{c['workflow_version']}**을 선택했다. 릴리스는 `law-name-recovery-20261021-r1`, 정본은 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`이다. 법령명+조문 조회 실패 뒤 제목·별칭만 검색하고 모델이 `RETRY_LAW_STRUCTURE`로 후보를 선택해 원래 조문을 재조회·원문 읽기로 연결한다. 조문·권한·원문·재개·상태 해시를 유지한다. 신규 합성8사례에서 기존8/8·변경8/8, 이름 복구 경로4/4, 실제Qwen41호출; 정확도·속도 개선은 주장하지 않는다. 최종260계약 통과, 기존7실패 제외. 후보·작업·실제 활성 service의 HEALTH·법령명 복구·범위 내 원문 읽기 통과, 작업·검증·선택418서빙파일 일치. 데이터·모델 프로필·선택 색인 유지. `VALIDATED_ADR_PROMOTION`, `quality_certified=false`, 품질 우회 없음. 구 용어집 스키마2곳의 미검증 변경은 캐시 호환성을 위해 별도 보존하고 기존 컴파일러를 유지했으며 다른 글자 수 제한 제거 변경은 포함한다. 관리 모드 비활성·멀티턴 범위·기존 조사 종료 보완을 유지한다. 전역 graph기존9오류, ADR0965 무효 자료/기록 오류와 이전 의미 오류는 해결한 것으로 보지 않는다. GENOS 반입·배포·내부 모델 검증 및 Git commit/push 미수행. 전환·복원: `09_ARTIFACTS/AUDITS/20261021-law-name-main/RESULT.txt`.'''
for n in ('AGENTS.md','00_SYSTEM/ARCHITECTURE.md'):
 path=ROOT/n;text=path.read_text();start=text.index('<!-- CURRENT_LOCAL_RAG_RELEASE -->');end=text.index('<!-- /CURRENT_LOCAL_RAG_RELEASE -->',start)+len('<!-- /CURRENT_LOCAL_RAG_RELEASE -->')
 path.write_text(text[:start]+'<!-- CURRENT_LOCAL_RAG_RELEASE -->\n'+block+'\n<!-- /CURRENT_LOCAL_RAG_RELEASE -->'+text[end:])
index=ROOT/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();entries='''
- [ADR-0967 법령명 복구 MAIN 통합](ADR-0967-law-name-main-integration/README.md) — 최종260계약·실제 데이터 소비자·418파일 검증, MAIN98 선택. 구 용어집 스키마 변경 보존/제외, 데이터 유지.
- [ADR-0966 신규 법령명 복구 모델 검증](ADR-0966-law-name-bound-holdout/README.md) — 신규8사례 기존8/8·변경8/8, 복구4/4, Qwen41호출. 실제 데이터 캐시 해시 충돌로 해당 통합은 미승격; 후속0967에서 처리.
- [ADR-0965 초기 합성 입력 오류](ADR-0965-law-name-recovery-qualification/README.md) — 저장좌표 누락,54호출·기록 형식 오류 보존. 무효 결과, 승격 근거 제외.
'''
if 'ADR-0967 법령명 복구 MAIN 통합' not in text:index.write_text(text.replace('# ADR workspace\n','# ADR workspace\n'+entries,1))
backlog=ROOT/'07_DOCS/BACKLOG.md';text=backlog.read_text();note='''
## 2026-10-21 · 구 용어집 스키마 길이 제한과 캐시 컴파일러 결속

MAIN98 통합 중 `full_glossary.py`의 PLAN_SCHEMA·decision_schema 길이 제한 제거가 불변 캐시의 compiler_sha256을 바꿔 실제 데이터 세션을 차단했다. 해당2개 스키마 변경만 이전 컴파일러와 결속된 바이트로 유지하고 작업본을 [ADR0967 보존 기록](../04_EXPERIMENTS/ADR/ADR-0967-law-name-main-integration/artifacts/integration-delta.json)에 무손실 보존했다. 현재 RAG의 다른 글자 수 제한 제거는 유지한다. 구 스키마 완화는 캐시 생성 책임을 분리하거나 새 호환 세대를 작성·검증하는 후속 작업으로 남긴다. 해시 검사를 우회하거나 기존 세대 receipt를 덮어쓰지 않는다.

'''
if '## 2026-10-21 · 구 용어집 스키마 길이 제한과 캐시 컴파일러 결속' not in text:
 pos=text.index('\n')+1;backlog.write_text(text[:pos]+note+text[pos:])
print('Recorded MAIN98, workflow'+c['workflow_version']+',418 files, actual service PASS')
