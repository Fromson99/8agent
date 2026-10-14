"""Record local MAIN only after selected code and actual gateway agree."""
from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');s=read(A/'artifacts/main-smoke.json');m=read(R/p['manifest_path']);r=read(A/'artifacts/run-001/result.json')
assert s['status']=='passed' and s['pointer']==p and r['strict_success'] and s['native_binding']==s['evaluation_binding']
assert p['deployment_basis']=='VALIDATED_ADR_PROMOTION' and m['qualification']['source']['sha256']==sha(A/'실험/manifest.json')
rebase=read(A/'artifacts/design/release-rebase.json');assert rebase['staged_files']==m['files']
for f,h in m['files'].items():assert sha(R/f)==sha(R/m['code_root']/f)==sha(R/rebase['stage']/f)==h,f
receipts=[]
for f in (R/'01_DATA/ACTIVE/local/receipts').glob('semantic-apply-*.json'):
 v=read(f)
 if v.get('after',{}).get('release_id')==p['release_id'] and v['after'].get('release_manifest_sha256')==p['release_manifest_sha256']:receipts.append({'path':str(f.relative_to(R)),'sha256':sha(f),'quality_gate_override':v['quality_gate_override']})
assert len(receipts)==1 and receipts[0]['quality_gate_override'] is False
row=r['by_arm']['integrated'];counts={k:len(v) for k,v in r['semantic_outcomes'].items()}
record={'status':'complete','environment':'WSL local MAIN','selected_release':p,'code_root':m['code_root'],'data_generation':m['data_path'],'serving_files':len(m['files']),'exact_working_candidate_release_match':True,'source_result_sha256':sha(A/'artifacts/run-001/result.json'),'apply_receipt':receipts[0],'real_entrypoint':s['entrypoint'],'service_execution_binding':s['execution_binding'],'native_execution_binding':s['native_binding'],'main_smoke_sha256':sha(A/'artifacts/main-smoke.json'),'primary_semantic_outcomes':counts,'regression_responses':sum(x['http_status']==200 for x in r['regressions']),'completion_contract_tests_passed':30,'native_consumer_tests_passed':25,'genos_deployed':False,'git_main_merged':False,'resident_server_restarted':False,'quality_certified':False}
put(A/'artifacts/main-completion.json',record)
(A/'MAIN_RESULT.md').write_text(f'''# 조사 완료 계약의 로컬 MAIN 반영

선택 릴리스는 `{p['release_id']}`, 활성 포인터 generation **{p['generation']}**다. 검증 후보·작업 코드·선택 릴리스의 서빙 {len(m['files'])}파일 해시가 일치한다. 세대 `{m['data_path']}`를 유지했다.

읽기·채택 분리, 보류 원문 재열람과 기존 RETURN_TO, 진전 없는 반복 종료, 마무리 예산·같은 요청 재개 예산, 쟁점별 부족분과 제한된 재조사, 실제 원문 span 인용, 판단 이후 새 법률 문장 생성 방지, 오류 분류·확인된429 재시도 및 워크플로우·직접 채팅 JSON/SSE의 완료·부분·미완료·상류실패 표시를 연결했다. 일반 규칙 설명과 개별 사실 적용의 구분을 지침에 보완했다. **개인정보 자료제출 질문(REG-IC24)은 감독 권한 맥락을 정정·삭제 증거자료 제출로 좁히는 의미 오류가 이번에도 남았다.** 인용 정확성과 응답 성공을 의미 정답으로 보지 않는다.

핵심 계약30개와 최신 채팅 JSON/SSE 소비자25개 통과. 공통 gateway 회귀는 후보와 기존 MAIN 모두18통과·3실패로 동일하며 모든 저장소 테스트 통과를 주장하지 않는다. 동결 패키지·엔진 의존성·접근권한·워크플로우 소비 검사를 통과했다. 새로운 주 조문16질문의 응답은 {row['request_success_count']}/16, 단일 자동 평가 정답은 {row['correct_count']}/16, 알려진 회귀 응답은 {record['regression_responses']}/12다. 결과 분류는 {counts}이다. 의미 정답을 모두 맞혀야만 승격하는 기준은 사용하지 않았고, 원문·권한·해시·상태·게시 무결성을 검사했다.

실제 새 `service.service`에서 HEALTH/RAG_SEARCH/RAG_ASK를 확인했다. 실제 native binding이 평가 binding과 일치하며, 종전 마무리/재시도 프로필 보정 차이도 해소했다. 실제 확인 답변은 [서비스 실행 영수증](artifacts/main-smoke.json)에 보존했다. 평가 대상 밖 법률·내부 데이터 품질 인증은 아니다.

첫 후보 ADR0678은 HTTP200 출력 중단 오분류로 기각했다. 17개 결과와 미실행23개를 보존하고 새 ADR에서 수정했다. ADR0679는 직접 채팅의 완료 상태 오표시로 기각했으며, 실제10개 응답과 자동정답8개·자동오답2개 및 미실행18개를 보존했다. 새 후보에서 최신 채팅 작업 변경을 3방향 비교로 보존하고 소비자 계약을 수정했다. 원본 실패·판정·코드·세대를 덮어쓰지 않았다. 실행 로그 압축 보조 스크립트의 오류는 별도 복구 영수증에 기록했고 제품 코드·동결 조건을 유지했다.

- [독립 검증·한계·사례별 원결과](README.md)
- [판단 오류·미답변 진단](artifacts/run-001/GENERALIZATION_ERRORS.json)
- [코드·포인터·실제 서비스 연결](artifacts/main-completion.json)
- [작업 파일 적용·백업](artifacts/working-install-receipt.json)

롤백은 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 이전 선택 포인터를 복구한 뒤 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0680/rollback_working.py --confirm-working-rollback`으로 이 작업의 파일만 복원한다. 이후 다른 변경이 있으면 자동 덮어쓰기를 중단한다. DB 및 WAL/SHM은 무손실 압축 해시와 복원 경로로 보존한다.

Git main 병합, GENOS 현장 반입·리비전 배포·내부 모델 검증, 기존 로컬 상주 프로세스 재시작은 별도이며 완료로 보고하지 않는다.
''')
# Compact case table points to one canonical response rather than duplicating it.
dataset=read(A/'artifacts/design/dataset.json');table=['## 이번 실행의 사례별 상태','', '| 구분 | 질문 | 결과 | 호출 | 처리시간 | 원결과 |','|---|---|---|---:|---:|---|']
for group,cases in [('독립',dataset['cases']),('회귀',dataset['regression_cases'])]:
 for case in cases:
  parent='run-001' if group=='독립' else 'regression'
  relative=Path('artifacts')/parent/'integrated'/case['case_id']/'result.json';path=A/relative
  value=read(path);status='응답' if value['http_status']==200 else '미완료' if value.get('output',{}).get('code')=='SOURCE_INVESTIGATION_INCOMPLETE' else '미답변'
  if group=='독립' and value['http_status']==200:
   grade=read(path.parent/'grade.json');status+=' / 자동 정답' if grade['correct'] else ' / 자동 오답'
  if case['case_id']=='REG-IC24' and value['http_status']==200:status='응답 / 문맥 오류 확인'
  elapsed=value.get('request_seconds',value.get('total_seconds',0));question=case['question'].replace('\n',' ').replace('|','∣')
  table.append(f"| {group} | {question} | {status} | {value['model_calls']} | {elapsed:.1f}초 | [{case['case_id']}]({relative.as_posix()}) |")
table+=['','회귀의 ‘응답’은 게시 성공과 원문 인용·실행 계약 확인을 뜻하며, 자동 정답 판정과 구분한다. 알려진 회귀 의미 오류는 [REG-IC24](artifacts/manual-review/REG-IC24.json), 재무제표 미완료는 [REG-NG13](artifacts/manual-review/REG-NG13.json)에 보존했다. 두 독립 미완료의 상세 분류는 [H05](artifacts/manual-review/H05.json)와 [H10](artifacts/manual-review/H10.json)에 남겼다.']
with (A/'MAIN_RESULT.md').open('a') as handle:handle.write('\n'+'\n'.join(table)+'\n')

docdir=A/'artifacts/main-documentation-backup';docdir.mkdir(exist_ok=False);plan=[]
for name,path in [('AGENTS.md',R/'AGENTS.md'),('ARCHITECTURE.md',R/'00_SYSTEM/ARCHITECTURE.md')]:
 saved=docdir/name;shutil.copy2(path,saved);plan.append({'path':str(path.relative_to(R)),'before':sha(path),'backup':str(saved.relative_to(R))})
put(A/'artifacts/main-documentation-plan.json',{'status':'prepared','files':plan})
agent=R/'AGENTS.md';text=agent.read_text();old='`investigation-control-v6-20261007-r1`(포인터 generation 43)';assert old in text;agent.write_text(text.replace(old,'`'+p['release_id']+'`(포인터 generation '+str(p['generation'])+')'))
arch=R/'00_SYSTEM/ARCHITECTURE.md';text=arch.read_text();head='# MAIN — 원문과 용어 기반 탐색\n\n';assert head in text
intro=f"2026-10-07 **조사 완료 계약의 로컬 MAIN**은 `{p['release_id']}`(generation **{p['generation']}**)다. 기존7단계와 전체 MAIN의 상위 파이프라인을 유지하면서 읽기/채택 계약, 보류·복귀, 진전·예산·재개, 부족분 재조사, 원문 span 인용, 확정 판단 표시, 오류 분류와 워크플로우 소비를 개선했다. 검증 후보·작업 코드·선택 릴리스268파일 및 실제 새 service.service의 실행 지문을 확인했다. 30개 핵심 계약 및25개 소비자 계약과 새로운 주 조문16질문, 알려진12회귀 결과·의미 오류·미답변을 분리해 기록했다. 사용자 지시에 따라 세부 정답100%를 요구하지 않았으며 심각한 무결성 기준과 quality_certified=false를 유지한다. GENOS 현장 실행은 별도다. [현재 결과와 원복](../04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration/MAIN_RESULT.md).\n\n아래는 이전 전환 시점의 이력이다.\n\n"
arch.write_text(text.replace(head,head+intro,1))
for item in plan:item['after']=sha(R/item['path'])
put(A/'artifacts/main-documentation-plan.json',{'status':'applied','files':plan})
print('Local MAIN completed',p['release_id'],p['generation'])
