"""Record local MAIN only after selected code and actual gateway agree."""
from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification'
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
record={'status':'complete','environment':'WSL local MAIN','selected_release':p,'code_root':m['code_root'],'data_generation':m['data_path'],'serving_files':len(m['files']),'exact_working_candidate_release_match':True,'source_result_sha256':sha(A/'artifacts/run-001/result.json'),'apply_receipt':receipts[0],'real_entrypoint':s['entrypoint'],'service_execution_binding':s['execution_binding'],'native_execution_binding':s['native_binding'],'main_smoke_sha256':sha(A/'artifacts/main-smoke.json'),'primary_semantic_outcomes':counts,'regression_responses':sum(x['http_status']==200 for x in r['regressions']),'completion_contract_tests_passed':30,'genos_deployed':False,'git_main_merged':False,'resident_server_restarted':False,'quality_certified':False}
put(A/'artifacts/main-completion.json',record)
(A/'MAIN_RESULT.md').write_text(f'''# 조사 완료 계약의 로컬 MAIN 반영

선택 릴리스는 `{p['release_id']}`, 활성 포인터 generation **{p['generation']}**다. 검증 후보·작업 코드·선택 릴리스의 서빙 {len(m['files'])}파일 해시가 일치한다. 세대 `{m['data_path']}`를 유지했다.

읽기·채택 분리, 보류 원문 재열람과 기존 RETURN_TO, 진전 없는 반복 종료, 마무리 예산·같은 요청 재개 예산, 쟁점별 부족분과 제한된 재조사, 실제 원문 span 인용, 판단 이후 새 법률 문장 생성 방지, 오류 분류·확인된429 재시도 및 워크플로우의 미완료·상류실패 표시를 연결했다. 일반 규칙 설명과 개별 사실 적용의 구분을 지침에 보완했으며 의미 오류 가능성은 남는다.

핵심 계약30개 통과. 공통 gateway 회귀는 후보와 기존 MAIN 모두18통과·3실패로 동일하며 모든 저장소 테스트 통과를 주장하지 않는다. 동결 패키지·엔진 의존성·접근권한·워크플로우 소비 검사를 통과했다. 새로운 주 조문16질문의 응답은 {row['request_success_count']}/16, 단일 자동 평가 정답은 {row['correct_count']}/16, 알려진 회귀 응답은 {record['regression_responses']}/12다. 결과 분류는 {counts}이다. 의미 정답을 모두 맞혀야만 승격하는 기준은 사용하지 않았고, 원문·권한·해시·상태·게시 무결성을 검사했다.

실제 새 `service.service`에서 HEALTH/RAG_SEARCH/RAG_ASK를 확인했다. 실제 native binding이 평가 binding과 일치하며, 종전 마무리/재시도 프로필 보정 차이도 해소했다. 실제 확인 답변은 [서비스 실행 영수증](artifacts/main-smoke.json)에 보존했다. 평가 대상 밖 법률·내부 데이터 품질 인증은 아니다.

첫 후보 ADR0678은 HTTP200 출력 중단 오분류로 기각했다. 17개 결과와 미실행23개를 보존하고 새 ADR에서 수정했다. 원본 실패·판정·코드·세대를 덮어쓰지 않았다. 실행 로그 압축 보조 스크립트의 오류는 별도 복구 영수증에 기록했고 제품 코드·동결 조건을 유지했다.

- [독립 검증·한계·사례별 원결과](README.md)
- [판단 오류·미답변 진단](artifacts/run-001/GENERALIZATION_ERRORS.json)
- [코드·포인터·실제 서비스 연결](artifacts/main-completion.json)
- [작업 파일 적용·백업](artifacts/working-install-receipt.json)

롤백은 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 이전 선택 포인터를 복구한 뒤 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0679/rollback_working.py --confirm-working-rollback`으로 이 작업의 파일만 복원한다. 이후 다른 변경이 있으면 자동 덮어쓰기를 중단한다. DB 및 WAL/SHM은 무손실 압축 해시와 복원 경로로 보존한다.

Git main 병합, GENOS 현장 반입·리비전 배포·내부 모델 검증, 기존 로컬 상주 프로세스 재시작은 별도이며 완료로 보고하지 않는다.
''')
docdir=A/'artifacts/main-documentation-backup';docdir.mkdir(exist_ok=False);plan=[]
for name,path in [('AGENTS.md',R/'AGENTS.md'),('ARCHITECTURE.md',R/'00_SYSTEM/ARCHITECTURE.md')]:
 saved=docdir/name;shutil.copy2(path,saved);plan.append({'path':str(path.relative_to(R)),'before':sha(path),'backup':str(saved.relative_to(R))})
put(A/'artifacts/main-documentation-plan.json',{'status':'prepared','files':plan})
agent=R/'AGENTS.md';text=agent.read_text();old='`investigation-control-v6-20261007-r1`(포인터 generation 43)';assert old in text;agent.write_text(text.replace(old,'`'+p['release_id']+'`(포인터 generation '+str(p['generation'])+')'))
arch=R/'00_SYSTEM/ARCHITECTURE.md';text=arch.read_text();head='# MAIN — 원문과 용어 기반 탐색\n\n';assert head in text
intro=f"2026-10-07 **조사 완료 계약의 로컬 MAIN**은 `{p['release_id']}`(generation **{p['generation']}**)다. 기존7단계와 전체 MAIN의 상위 파이프라인을 유지하면서 읽기/채택 계약, 보류·복귀, 진전·예산·재개, 부족분 재조사, 원문 span 인용, 확정 판단 표시, 오류 분류와 워크플로우 소비를 개선했다. 검증 후보·작업 코드·선택 릴리스268파일 및 실제 새 service.service의 실행 지문을 확인했다. 30개 핵심 계약과 새로운 주 조문16질문, 알려진12회귀 결과·의미 오류·미답변을 분리해 기록했다. 사용자 지시에 따라 세부 정답100%를 요구하지 않았으며 심각한 무결성 기준과 quality_certified=false를 유지한다. GENOS 현장 실행은 별도다. [현재 결과와 원복](../04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification/MAIN_RESULT.md).\n\n아래는 이전 전환 시점의 이력이다.\n\n"
arch.write_text(text.replace(head,head+intro,1))
for item in plan:item['after']=sha(R/item['path'])
put(A/'artifacts/main-documentation-plan.json',{'status':'applied','files':plan})
print('Local MAIN completed',p['release_id'],p['generation'])
