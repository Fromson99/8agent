"""Record completed local MAIN separately from the immutable qualified ADR."""
from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');s=read(A/'artifacts/main-smoke.json');m=read(R/p['manifest_path'])
assert s['status']=='passed' and p==s['pointer'] and p['release_id']=='session-runtime-v6-20261007-r1'
assert m['files']==read(A/'artifacts/design/release-rebase.json')['staged_files']
for f,h in m['files'].items():assert sha(R/m['code_root']/f)==h
q=m['qualification']
for b in q.values():
 if isinstance(b,dict):assert sha(R/b['path'])==b['sha256']
tree=E.parse(A/'artifacts/working-maintained-tests-r2.xml').getroot();maintained=list(tree.iter('testcase'))
assert len(maintained)==35 and not any(v.find('failure') is not None or v.find('error') is not None for v in maintained)
install=read(A/'artifacts/working-install-receipt.json');runtime=[row for row in install['files'] if row['kind']=='runtime']
for row in runtime:assert sha(R/row['path'])==row['after']
receipts=[]
for f in (R/'01_DATA/ACTIVE/local/receipts').glob('semantic-apply-*.json'):
 value=read(f)
 if value.get('after',{}).get('release_id')==p['release_id']:receipts.append({'path':str(f.relative_to(R)),'sha256':sha(f)})
assert len(receipts)==1
record={'status':'complete','environment':'WSL local MAIN','selected_release':p,'serving_files':len(m['files']),'evaluated_release_inventory_matches':True,'scoped_working_runtime_matches_release':True,'unrelated_working_modules_and_pins_preserved':True,'contract_tests_passed':118,'maintained_working_tests_passed':35,'apply_receipt':receipts[0],'service_execution_binding':s['execution_binding'],'source_generation':m['data_path'],'model_calls':0,'genos_deployed':False,'git_main_merged':False,'resident_server_restarted':False,'graph_no_new_errors':read(A/'artifacts/graph-comparison.json')['no_new_graph_errors']}
put(A/'artifacts/main-completion.json',record)
(A/'MAIN_RESULT.md').write_text(f'''# 세션 멀티턴의 user_wiki·signing 제거 — 로컬 MAIN

선택 릴리스 `{p['release_id']}`, 활성 포인터 generation **{p['generation']}**로 반영했다. 사용자 지시와 검증한 후보268파일·데이터 generation을 hash로 결속하고 stable prepare/apply --confirm-main을 사용했다. [실제 배선 영수증](artifacts/main-completion.json).

user_wiki 생성·조회·모델 context, 개인 질문 이력의 자동 주입 및 별도 HMAC 발급·검증·환경키 의존성을 제거했다. GENOS_MEMORY_SIGNING_KEY를 등록하지 않는다. 기존 플랫폼/API 인증 경계에서 사용자·팀·대화 식별자는 저장 분할과 문서 선택용으로 사용한다. 세션 정정·재개·확인, shortcut capture와 공통 DB, legal_wiki compiler·조회·재구축, 공개 반출 제한과 AD 관리 진입을 보존한다. 과거 기록·DB·완료 위키 파일·릴리스를 삭제하지 않는다.

동결 후보 신규30개·동일 회귀88개를 통과했고, 이후 유지 계약35개도 현재 작업 코드에서 확인했다. 원본 실험·법률 질문을 재채점하지 않았고 외부/GENOS 모델 호출0회다. actual service.service의 HEALTH/RAG_SEARCH와 실제 선택 package의 unsigned validation/normalization을 새 프로세스에서 확인했다. 전체 세션 mutation은 같은 코드의 모의 generation 계약에서 검증했다. [서비스 확인](artifacts/main-smoke.json).

작업 코드에 있던 병행 latency 및 관련 engine pin을 보존했고 이번 선택 릴리스에는 섞지 않았다. 이번 runtime 수정 파일은 작업 코드와 선택 릴리스가 일치하며, 전체 작업 트리의 pending 개발 코드가 모두 선택되었다고 보고하지 않는다. 전역 ADR graph의 기존8문제는 기준과 동일하며 이 arm은 신규 문제를 추가하지 않았다. 최초 historical conftest 수집 문제·검증 보조 스크립트의 응답 필드 수정·구 테스트 fixture의 누락 profile 수정 로그는 보존했다. 제품 후보나 사전 기준은 변경하지 않았다.

환경 안내: [.env.genos.example](../../../.env.genos.example), [workflow.env.example](../../../08_DEPLOYMENT/GENOS/workflow/workflow.env.example). 기본 PIPELINE의 v6을 사용하고 workflow 멀티턴은 GENOS_MEMORY_ENABLED=1, 실제 사용자/대화 ID와 TEAM_ID를 사용한다. 분리 일반 질의의 팀은 workflow 입력으로 전달한다. AD 관리 모드의 server workspace는 TEAM_ID 또는 AD_WORKSPACE로 별도 고정한다.

롤백: `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 이전 포인터를 복구하고 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0681/rollback_working.py --confirm-working-rollback`으로 이 작업 파일만 복구한다. 이후 변경이 있으면 자동 덮어쓰기를 거부한다. [파일 적용과 백업](artifacts/working-install-receipt.json).

GENOS 현장 반입·리비전 배포·플랫폼 실제 ID 전달·내부 모델 검증, Git main 병합, 기존 로컬 상주 프로세스 재시작은 수행하지 않았다.
''')
backup=A/'artifacts/main-documentation-backup';backup.mkdir(exist_ok=False);rows=[]
for f in ('AGENTS.md','00_SYSTEM/ARCHITECTURE.md'):
 b=backup/f;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/f,b);rows.append({'path':f,'before':sha(R/f),'backup':str(b.relative_to(R))})
agent=R/'AGENTS.md';text=agent.read_text();old='`investigation-completion-v6-20261007-r1`(포인터 generation 44)';assert old in text;agent.write_text(text.replace(old,'`'+p['release_id']+'`(포인터 generation '+str(p['generation'])+')'))
arch=R/'00_SYSTEM/ARCHITECTURE.md';text=arch.read_text();head='# MAIN — 원문과 용어 기반 탐색\n\n';assert text.startswith(head)
intro=f"2026-10-07 현재 로컬 RAG MAIN은 `{p['release_id']}`(generation **{p['generation']}**)다. 세션 멀티턴에서 user_wiki 생성·조회·개인 질문 이력의 자동 모델 입력과 별도 signing을 제거했다. 세션 상태·shortcut 공통 저장소·legal_wiki 컴파일과 재구축·기존 플랫폼/API 경계는 유지한다. 후보/선택268파일 및 실제 새 service.service의 binding을 확인했고 신규30개·동일 회귀88개와 유지 계약35개를 통과했다. 병행 작업의 미선택 latency/engine 변경은 보존했으며 해당 pending 작업까지 승격한 것은 아니다. 원문 세대와 이전 릴리스·개인 위키 기록은 보존한다. GENOS 현장 배포는 별도다. [변경·실제 연결·원복](../04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing/MAIN_RESULT.md).\n\n아래는 이전 전환 시점의 이력이다.\n\n"
arch.write_text(head+intro+text[len(head):])
for row in rows:row['after']=sha(R/row['path'])
put(A/'artifacts/main-documentation-receipt.json',{'status':'applied','files':rows})
print('Local MAIN completed:',p['release_id'],p['generation'])
