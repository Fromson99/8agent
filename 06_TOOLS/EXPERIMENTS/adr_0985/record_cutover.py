"""Record actual selection only after native service and exact bytes agree."""
from common import *
import shutil
A=ROOT/'09_ARTIFACTS/AUDITS/20261022-unified-scope-main'
s=read(ART/'stage.json');p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
m=read(ROOT/p['manifest_path']);c=read(ART/'consumer-active.json')
a=read(ART/'analysis.json');r=read(ART/'result.json');q=read(ART/'known-query-review.json')
assert p['generation']==s['base_pointer']['generation']+1
assert p['release_id']=='unified-scope-semantics-20261022-r1'
assert c['status']=='PASS' and not c['app_injected'] and all(c['checks'].values())
assert m['files']==s['files']['candidate']
assert all(sha(ROOT/n)==h and sha(ROOT/m['code_root']/n)==h for n,h in m['files'].items())
search=c['health']['body']['search_selection']
assert search==read(ART/'consumer-candidate.json')['health']['body']['search_selection']
assert search['sha256']==read(ROOT/'09_ARTIFACTS/AUDITS/20261021-structured-selection-main/binding-check.json')['search_selection_fingerprint']
shutil.copyfile(ART/'consumer-active.json',A/'consumer-active.json')
save(A/'after-pointer.json',p)
save(A/'binding-check.json',{'all_working_candidate_selected_files_match':True,'file_count':len(m['files']),
 'actual_service_binding':c['binding'],'release_manifest_sha256':sha(ROOT/p['manifest_path']),
 'data_path':m['data_path'],'data_manifest_sha256':m['data_manifest_sha256'],
 'profile_sha256':c['profile_sha256'],'search_selection_fingerprint':search['sha256'],
 'workflow_version':c['workflow_version'],'quality_certified':False,'genos_verified':False})
counts=a['correct'];ac=a['assessment_correct']
block=f'''2026-10-22 사용자 “현재 main에 있는문제들 전부다 고쳐” 지시에 따라 **로컬 RAG MAIN{p['generation']} / workflow{c['workflow_version']}**을 선택했다. 릴리스는 `{p['release_id']}`, 정본은 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`이다. 명시 법령 범위를 검색에 일관되게 연결하고, 내용 질문의 범위 내 fulltext 탐색, 제목·용어 후보의 임의 누락 제거, 모델의 추가 조사 필요성·이유 보존, 기존 계층 수정과 추가 조사 사이의 근거·판단 전달을 통합했다. 이전 판단은 현재 권한·원문·위치·해시와 다시 결속하여 검토하며 정답으로 자동 확정하지 않는다. ADR0985 신규 범위16사례 기존{counts['baseline']}/16·후보{counts['candidate']}/16, 별도 합성 판단4사례 기존{ac['baseline']}/4·후보{ac['candidate']}/4, 최종{r['contracts']}계약 통과. 원래 상법 질문은 별도 in-sample 실제 서비스 진단에서 제434조와 두 의결정족수의 설명 전달을 확인했다. 해당 ADR 실제 Qwen{r['physical_model_calls']}호출이며 전체 법률 정확도·현장 성능 인증은 아니다. 이전 거절 ADR0977/0978/0980/0981/0982는 보존했다. 작업·검증후보·선택릴리스419파일과 실제 로컬 서비스 바인딩·HEALTH를 확인했다. 데이터·모델 프로필·검색 선택 유지, `VALIDATED_ADR_PROMOTION`, 품질 우회 없음, `quality_certified=false`. 저장 데이터의 기존 중첩 조문2건과 전역 graph·과거 의미 오류는 해결한 것으로 보지 않는다. GENOS 반입·배포 및 Git commit/push 미수행. 전환·복원: `09_ARTIFACTS/AUDITS/20261022-unified-scope-main/RESULT.txt`.'''
for n in ('AGENTS.md','00_SYSTEM/ARCHITECTURE.md'):
 path=ROOT/n;t=path.read_text();lo=t.index('<!-- CURRENT_LOCAL_RAG_RELEASE -->')
 hi=t.index('<!-- /CURRENT_LOCAL_RAG_RELEASE -->',lo)+len('<!-- /CURRENT_LOCAL_RAG_RELEASE -->')
 path.write_text(t[:lo]+'<!-- CURRENT_LOCAL_RAG_RELEASE -->\n'+block+'\n<!-- /CURRENT_LOCAL_RAG_RELEASE -->'+t[hi:])
(A/'RESULT.txt').write_text(f'''로컬 MAIN{p['generation']} 반영 및 실제 선택 서비스 확인

릴리스: {p['release_id']}
workflow: {c['workflow_version']}
검증 ADR: ADR0985 / 후보 candidate / 기존 MAIN99 기준 비교
검증: {r['contracts']}계약 통과. 신규 범위16사례 기존{counts['baseline']}/16, 후보{counts['candidate']}/16.
독립 합성 판단4사례 기존{ac['baseline']}/4, 후보{ac['candidate']}/4.
해당 ADR 실제 Qwen 호출 {r['physical_model_calls']}회: 범위32 + 합성판단8 + 원래질문{q['model_calls']}.
원래 질문은 in-sample 진단이다. 실제 서비스 HTTP{q['service_status']}, 제434조 원문 및 두 정족수의 근거 있는 설명 전달을 확인했다.
Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음. 법률 정답·일반화·GENOS 내부 모델 인증은 아니다.

주요 수정:
명시된 법령 범위 판단을 검색 범위와 일관되게 연결한다. 없는 문서는 미확인으로 유지하며 임의로 넓히지 않는다.
내용 질문은 지정 법령 안의 본문 검색으로 진입한다. 제목 일치 점수·후보 수·최장 용어만 남기던 누락을 제거했다.
추가 조사 때 이전 근거와 그 근거에 연결된 판단을 전달한다. 부족 목록만 남아 기존 판단이 입력에서 빠지던 배선을 수정했다.
모델이 현재 원문을 보고 유지·수정·제외를 재판단한다. 이전 의견 자체는 근거나 정답으로 승격하지 않는다.
충분성·적용성·추가 조사 필요성·이유를 코드의 임의 판단으로 덮어쓰던 경로를 수정했다.
기존 계층·복수·범위·제외 선택을 보존했다. 사용자 지시로 새 멀티턴 기능 수정은 이번 범위에서 제외했다. 상세 전체 항목은 해당 ADR artifacts/fix-coverage.json을 따른다.

작업 코드 / 검증 후보 / 선택 릴리스419파일 일치.
native service.service.application() 선택 바인딩과 HEALTH200 확인. 데이터·모델프로필·검색선택 지문 유지.
원문·권한·해시·상태·재개·중복·예산 검사는 유지했다. 확인하지 못한 근거를 만들거나 자동 승인하지 않는다.
기존 데이터 중첩 조문2건 및 과거 전역 ADR graph 오류는 별도 미해결이다.
GENOS 현장 반입·배포·내부 모델 검증, Git commit/push는 수행하지 않았다.

필요할 때 이전 MAIN99 복원:
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
복원 후 실제 선택 서비스 바인딩을 다시 확인한다. previous-pointer.json과 릴리스 apply/rollback receipt를 보존한다.
''')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';t=index.read_text()
note=f'\n- [ADR-0985 근거·판단 연속성과 통합 검색 수정](ADR-0985-model-resolved-scope-authority/README.md) — 신규 범위 후보{counts["candidate"]}/16, 합성판단{ac["candidate"]}/4, {r["contracts"]}계약,419파일 결속; 로컬 MAIN{p["generation"]}. 이전 거절 후보 보존.\n'
if 'ADR-0985 근거·판단 연속성과 통합 검색 수정' not in t:index.write_text(t.replace('# ADR workspace\n','# ADR workspace\n'+note,1))
print('Recorded selected MAIN',p['generation'],'and native binding; no GENOS deployment')
