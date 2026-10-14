"""Record the applied pointer, exact installed package, and actual local service selection."""
from pathlib import Path
import json,hashlib,datetime,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);smoke=read(A/'artifacts/main-smoke.json');base=read(A/'artifacts/design/baseline.json')
assert pointer['generation']==base['pointer']['generation']+1 and pointer['release_id']=='compact-input-20261009-r1'
assert smoke['status']=='passed' and smoke['pointer']==pointer
manifest=R/pointer['manifest_path'];release=read(manifest);rebase=read(A/'artifacts/design/release-rebase.json');assert release['files']==rebase['staged_files']
for name,h in release['files'].items():assert sha(R/name)==sha(R/release['code_root']/name)==h,name
auth=read(A/'artifacts/main-authorization.json')
for ref in auth['qualification'].values():
 if isinstance(ref,dict) and 'path' in ref:assert sha(R/ref['path'])==ref['sha256']
tests=list(E.parse(A/'artifacts/working-required.xml').iter('testcase'));assert len(tests)==288 and all(t.find('failure') is None and t.find('error') is None for t in tests)
receipts=[]
for candidate in (R/'01_DATA/ACTIVE/local/receipts').glob('*.json'):
 v=read(candidate)
 if v.get('action')=='VALIDATED_ADR_PROMOTION' and v.get('after')==pointer:receipts.append((candidate,v))
assert len(receipts)==1 and receipts[0][1]['before']==base['pointer']
result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
record={'status':'local-main-verified','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_pointer':bound(p),'release_manifest':bound(manifest),'pointer':pointer,'qualification':auth['qualification'],'working_install_receipt':bound(A/'artifacts/working-install-receipt.json'),'working_tests':bound(A/'artifacts/working-required.xml'),'working_passed':len(tests),'service_verification':bound(A/'artifacts/main-smoke.json'),'execution_binding':smoke['execution_binding'],'exact_working_validated_release_inventory':True,'serving_file_count':len(release['files']),'apply_receipt':bound(receipts[0][0]),'rollback_files':[bound(q) for q in (manifest.parent/'rollback').iterdir() if q.is_file()],'git_main_merged':False,'genos_deployed':False,'resident_server_restarted':False,'new_external_model_calls':sum(v['calls'] for v in result['by_arm'].values()),'semantic_quality_certified':False}
(A/'artifacts/main-completion.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
comparison=result['primary_comparison'];b,c=comparison['baseline'],comparison['compact']
tokens=(1-c['input_tokens']/b['input_tokens'])*100;seconds=(1-c['request_seconds']/b['request_seconds'])*100
table='| 신규 공개 질문 | MAIN49 호출 / 입력 / 시간 | MAIN50 호출 / 입력 / 시간 |\n|---|---:|---:|\n'
for old in result['by_arm']['baseline']['cases']:
 new=next(x for x in result['by_arm']['compact']['cases'] if x['case_id']==old['case_id'])
 table+=f"| {old['case_id']} | {old['physical_model_attempts']}회 / {old['usage']['input_tokens']:,} / {old['request_seconds']:.1f}초 | {new['physical_model_attempts']}회 / {new['usage']['input_tokens']:,} / {new['request_seconds']:.1f}초 |\n"
wire=read(A/'artifacts/run-001/wire-audit.json');install=read(A/'artifacts/working-install-receipt.json')
text=f'''# 선택 환경과 입력 축소 — 로컬 MAIN50

`compact-input-20261009-r1`을 로컬 RAG MAIN generation50으로 선택했다. 전체 MAIN 중 서빙 부분을 변경했고 원문·용어집·구조화·색인 세대는 그대로다. GENOS 현장 배포와 Git main 병합은 별도다.

## 반영 내용

- 미선택 법령의 상세 목차는 필요할 때 펼친다. 초기 조문 적중은 기존 순서 상위2개와 더보기로 제공한다. 전체 결과는 삭제하지 않으며 바로 읽기·구조/본문 검색·페이지 경로를 유지한다.
- 명확히 특정된 구조 위치는 상세 구조와 바로 읽기를 함께 보여준다. 관련 후보가 있으면 먼저 원문을 읽고, 아직 필요한 위치가 없을 때 추가 탐색하는 선택 맥락을 간결하게 제공한다. 별도 선택/요약 모델 호출은 없다.
- 탐색 호출 안의 같은 원문은 전체 본문과 정확한 위치 참조로 연결한다. 호출 간 기억을 가정하지 않으며 필요한 원문은 매 호출에 온전히 제공한다. 최종 판단의 구절–인용ID 표시는 유지한다.
- 모든 행동의 순서·대상·결과·짧은 이유를 유지하고 긴 설명과 원시 화면은 서버에 보존한다. 전체 출력 규칙 중 빈 배열의 불필요한 상세만 줄인다.
- 기존 제목 힌트·앞단1회·중복 검색 거절·읽기/채택 분리·최신 승인 판단·오류 로그 분리·최대5단계 진행 카드·접힘의 실제 호출수/개별시간 계측을 유지한다.

## 실제 검증

{table}
신규3문항의 입력 토큰 합계 **{b['input_tokens']:,}→{c['input_tokens']:,}({tokens:.1f}% 감소)**, 실제 모델 호출 **{b['calls']}→{c['calls']}회**, 요청 시간 합계 **{b['request_seconds']:.1f}→{c['request_seconds']:.1f}초**다. 원문 근거 포함 응답은 {b['supported']}/3→{c['supported']}/3이다. 실패/교정 호출도 포함한 실제 E2E 관측이며3문항으로 일반 속도·법률 정확도를 인증하지 않는다.

알려진 회귀2문항은 신규 주 비교에 포함하지 않고 별도로 확인했다. 후보 {result['by_arm']['compact']['supported_known']}/2가 원문 근거 응답을 완료했다. 이전0711 실패는 원래 결과로 보존했다. 필요한 주 조문이 실제 모델에 전달됐고 인용·권한·판단 상태·복귀/재개 경계 검증을 통과했다. 실제 전송 원문과 저장본은 동일하며 {wire['references_checked']}개 위치 참조가 정확히 원문을 복원한다.

후보와 통합 작업 코드 각각288계약 통과. 변경 {len(install['files'])}파일만 현재 해시를 확인하고 백업 후 통합했다. 작업 코드·검증 후보·선택 릴리스287파일이 일치한다. 실제 새 WSL 프로세스의 service.service HEALTH/RAG_SEARCH에서 generation50 및 코드·프로필·데이터·검색 정책·탐색 모듈의 선택을 확인했다. 이 선택 검사는 모델0회이며 실제 모델 성능은 위의 동일 코드 paired 실행 결과다. 별도 상주 서버 재시작은 하지 않았다.

## 한계·실패 보존

첫0711 후보는 입력156,315→161,313, 호출13→17, 응답3→2로 실패해 승격하지 않았다. 큰 메뉴는 줄었지만 핵심 조문을 인식하고도 페이지 이동·복귀·재검색을 선택했고 판단의 조건 그룹 연결도 실패했다.0712에서는 탐색 지침과 표시 범위를 좁히고 최종 판단의 근거 구절은 유지했다. 이유와 행동의 의미 일치를 일반적으로 보증하지 않는다.

H02/R02에서는 모델 자유서술의 회사 목록·구체적인 권리가 규칙 결론에 충분히 포함되지 않아 최종 조립 표시에서 빠졌다. 원문은 모두 전달됐지만 완전한 정답이라고 주장하지 않는다. 이 내용 보존 문제를 별도 후속 항목으로 등록했다.

교정 입력의 추가 축소·참조 메뉴 지연 제공·최종 판단의 원문 중복 축소·난이도별 예산은 남은 과제다. 이번 결과를 내부 CM 및 GENOS 성능으로 확대하지 않는다. 전체 graph에는 기존8개 역사 오류가 남으며 이번 두 ADR 자체 final 검사는 통과했다.

## 롤백

서빙 포인터는 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 MAIN49를 새 generation으로 선택한다. 실행 전 현재 포인터·직전 릴리스 receipt가 이 변경에 해당하는지 확인한다. 작업 파일은 `06_TOOLS/EXPERIMENTS/adr_0712/rollback_working.py`의 dry check 후 `--confirm-working-rollback`으로 별도 복구한다. 백업·해시·apply receipt·이전 포인터는 보존했다. 실제 롤백은 수행하지 않았다.

[판정](README.md) · [실제 서비스 선택](artifacts/main-smoke.json) · [완료 영수증](artifacts/main-completion.json) · [E2E 결과](artifacts/run-001/result.json) · [전송 원문 감사](artifacts/run-001/wire-audit.json)
'''
(A/'MAIN_RESULT.md').write_text(text)
p=R/'AGENTS.md';s=p.read_text().replace('`grounded-entry-20261009-r1`(포인터 generation 49)','`compact-input-20261009-r1`(포인터 generation 50)');p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text().replace('2026-10-09 현재 로컬 RAG MAIN은 `grounded-entry','2026-10-09 MAIN49 전환 당시 로컬 RAG MAIN은 `grounded-entry',1)
intro=f'2026-10-09 현재 로컬 RAG MAIN은 `compact-input-20261009-r1`(포인터 generation **50**)이다. MAIN49 위에 미선택 법령 상세 지연 제공, 간결한 탐색 지침·전체 행동 이력, 탐색 원문 중복 축소를 연결했다. 신규 공개3질문 입력 {tokens:.1f}% 감소·모델 {b["calls"]}→{c["calls"]}회, 알려진2질문·후보/작업288계약과 실제 service.service 선택을 확인했다. 원문 세대는 유지하고 구조/fulltext는 계속 선택형 도구다. GENOS 배포는 별도다. [실제 반영·검증·롤백](../04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context/MAIN_RESULT.md).\n\n'
s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text();start=s.index('- 상태:',s.index('## BL-009'));end=s.index('\n',start)
s=s[:start]+f'- 상태: **MAIN49 앞단·제목 힌트·선택형 검색 위에 입력 최적화를 MAIN50으로 반영.** 미선택 상세 지연 제공·간결한 지침/행동 이력·탐색 원문 중복 축소. 신규 공개3문항 입력 {tokens:.1f}% 감소·호출 {b["calls"]}→{c["calls"]}회, 알려진2문항과 후보/작업288계약·287서빙 파일·실제 로컬 선택 확인. [MAIN 결과](../04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context/MAIN_RESULT.md). 이유/행동 일치의 일반 보증·교정/참조 입력 추가 축소·난이도별 시간 정책은 후속이다.'+s[end:]
s=s.replace('토큰/시간 개선은 아직 미검증이다.','당시 토큰/시간 효과는 미검증이었다. 후속0711 실패를 보존하고0712에서 위 범위의 공개 E2E 검증을 완료했다.',1);p.write_text(s)
p=R/'07_DOCS/REFERENCE/REPORTS/RAG_TOKEN_INPUT_OPTIMIZATION_DESIGN_20261009.md';s=p.read_text();pos=s.index('\n\n')+2
note=f'**후속 구현(2026-10-09):** 미선택 상세 메뉴·간결한 전체 행동 이력·탐색 원문 중복/빈 배열 규칙 축소를 [ADR0712의 로컬 MAIN50](../../../04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context/MAIN_RESULT.md)에 반영했다. 신규 공개3문항 입력 {tokens:.1f}% 감소, 호출 {b["calls"]}→{c["calls"]}회. 최종 판단의 구절 표시·교정/참조 입력 추가 축소는 보류했다. 아래 본문은 구현 전 읽기 전용 진단·설계 기록이다.\n\n'
p.write_text(s[:pos]+note+s[pos:])
print('Recorded local MAIN50; exact working, candidate and selected code verified')
