from common import *
import shutil,subprocess
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main139_oneclick_mail_20261104_r1'
REPORT=ROOT/'09_ARTIFACTS/AUDITS/20261104-genos-embed-env-main139';REPORT.mkdir(exist_ok=True)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rp=ROOT/active['manifest_path'];release=read(rp)
assert active['generation']==139
assert all(sha(ROOT/release['code_root']/n)==sha(ROOT/n)==h for n,h in release['files'].items())
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
assert read(H/'VALIDATION.json')['passed']
logs=ART/'logs';logs.mkdir(exist_ok=True)
for p in Path('/tmp').glob('adr1320-*.log'):
 if not (logs/p.name).exists():shutil.copyfile(p,logs/p.name)
summary={'status':'COMPLETE_FIELD_UNVERIFIED','main':139,'release':active,'serving_files':525,'delta_from_main138':35,'product_files':4,'engine_pins':31,
 'final_contracts':60,'prepared_contracts':25,'overlap':True,'actual_selected_MAIN_checks':16,'Gold_binding_checks':9,
 'same_native_SQL_plans':639,'engine_preflight':{'engines':30,'files':497},'new_aliases':['GENOS_EMBED_ID','GENOS_EMBED_TOKEN','GENOS_URL'],
 'profile_env_required':False,'gateway_model_env_required':False,'explicit_profile_pin_checked':True,'Oracle_publication_validation_unchanged':True,
 'oneclick':read(H/'VALIDATION.json'),'email':read(H/'EMAIL_SENT.json'),'real_GENOS_calls':0,'new_Oracle_calls':0,'DB_writes':0,
 'working_frozen_selected_exact':True,'PeCab_pyarrow_unchanged':True,'field_deployed':False,'quality_certified':False,
 'failures_retained':['Initial test command named a missing mapping test file; no tests ran',
 'Preflight found stale catalogue source hash after editing vector module; regenerated plans and pins before MAIN',
 'First native check missed maintenance import path; corrected tool invocation'],
 'rollback_main138':str((rp.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),
 'rollback_gold_binding':str((ART/'main/gold-before.json').relative_to(ROOT))}
put(ART/'result.json',summary);put(REPORT/'result.json',summary)
m=read(ADR/'실험/manifest.json');put(ART/'candidate-audit-before-cutover.json',m)
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover','reason':'User requested removing manual profile hash and matching existing GENOS ID/TOKEN config in MAIN and replacement one-click handoff. Candidate frozen/tested before official prepare/apply. No field deployment.',
 'production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],
 'release':{'manifest_path':str(rp.relative_to(ROOT)),'sha256':sha(rp),'release_id':active['release_id']}}
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'integrated':summary},usage={'LLM_calls':0,'actual_embedding_calls':0},latency={},error_taxonomy=[{'type':'test_path_missing','count':1},{'type':'catalogue_source_pin_stale','count':1},{'type':'build_tool_import_path','count':1}])
put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=[
 '사용자 요청으로 MAIN139 genos-embed-env-20261104-r1 선택. GENOS_EMBED_ID/TOKEN을 그대로 받고 프로필 해시 수동입력을 선택사항으로 변경. gateway MODEL도 생략 가능. 기존 MAIN138 전체 위에 제품4(생성SQL포함)+pin31=35변경, 서빙525 동일 목록. 별도 Gold 매핑 파일 불필요·개발계 선택값은 유지.',
 '이전 PublishedEncoder는 PROFILE_SHA256/MODEL/KEY를 필수로 요구하여 현장에서 쓰는 ID/TOKEN만으로 실행할 수 없었다. 승호 integration af13f35c569b5b4500fff7f615ec5ced73763a29의 config/embedder 원본에서 ID/TOKEN·GENOS_URL·gateway model=genos 기본값을 확인·보존했다.',
 '결과 전 design/criteria.json에 alias호환/빈프로필/선택적pin/직접URL/LLM보존/환경변경감지/게시·차원·ACL보존/한줄설치·복구를 동결. 성능·법률품질 비교와 현장 실모델 호출은 범위 밖이다.',
 'ADR 선점→525파일 snapshot→rev001 기술검사→사전준비SQL 소스hash 재생성 rev002. final계약 후 공식prepare→같은준비코드검사→공식apply. 사용자 동일모델 확인을 전제로 구성 입력만 간소화. 멀티턴 ADR1319 변경은 포함하지 않는다.',
 '합성3차원 HTTP 응답과 Oracle SQL 대역, 보관 원문세대로 MAIN 기동 확인. 실제 GENOS/Oracle/LLM 호출0·DB변경0. 후보/작업/선택525 SHA 일치. source generation과 Gold매핑/게시/설정, PeCab/pyarrow 유지.',
 '최종60검사 통과; 준비릴리스25는 그 부분집합. 실제선택service16/Goldbinding9확인 통과. Oracle639계획은 소스hash/위치만 갱신하고 SQL/실행계획값 동일, engine30/497파일 preflight 통과. 최종 ZIP은 527코드(서빙524+도구3)와명세, 기존JS1해시검사. 무인자bash/링크경로/중복/이름변경/status/stage/commit/codegate/undo 및527기존파일복원 확인.',
 '최초 nonexistent mapping test 경로로 exit4/실검사0. native check 도구 import path 누락1, vector module 소스hash 변경을 catalog preflight가 차단1. 실패로그/후보rev001 보존 후 경로정정/정식catalog재생성. installer의 JS불일치는 의도한 변경전거절 검증이며 실제설치실패가 아니다.',
 '새 모델/토큰/비용0. 실제 속도·품질·recall 측정 없음. 동일639SQL과 기존 검색순서/상한/문서ACL/원문검증 유지, 합성조회1과 요청재사용을 계약검사로만 사용한다. 이전1317의 실제Oracle결과를 이번실행으로 합산하지 않는다.',
 'Oracle 게시 프로필 무결성/READY/source/query/dataset/documents검사 후 그 차원/COSINE/l2를 사용한다. 환경변수 해시는 없으면 자동프로필, 값이 있으면 일치검사. gateway ID가 모델을 선택하고 model 필드는 genos 기본. 실제동일모델은 사용자확인사항이며 해시/차원만으로 자동인증했다고 주장하지 않는다.',
 '현장 ORDS·실임베딩/답변 모델·서빙리비전 미실행. 직접 모델URL은 MODEL 필요. GENOS_URL alias는 임베딩에만 적용해 기존 LLM설정을 보존한다. ID/TOKEN이 옛 SERVING_ID/KEY보다 우선. 개발계 G19 계약과 실제 테이블의 현장 일치는 별도다.',
 'USER_DIRECTED_CUTOVER quality_certified=false. MAIN138 rollback포인터와 기존Goldbinding 보존. 삼성메일로 MAIN139 ZIP/완전실행TXT/GUIDE/ENVIRONMENT/VALIDATION/SHA합계6첨부 전송 후 SENT·수신자·제목·본문·첨부명/크기 확인, ID '+summary['email']['id']+'. Git push/현장배포0. 이전MAIN138메일파일은 수정하지 않았다.',
 '06_TOOLS/EXPERIMENTS/adr_1320의 setup→freeze→check→prepare_release→check --arm prepared→activate→main_entry/gold_entry→package→verify_oneclick→email_prepare. 현장 TRANSFER: bash MAIN139_ONECLICK_R1.txt. 이후 기존commit/push/코드서빙 환경설정/새revision 절차.']
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')+'\n---\n'
p.write_text(front+'\n# GENOS 임베딩 환경설정 간소화와 MAIN139\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{x}' for i,(t,x) in enumerate(zip(titles,bodies),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 확인 인덱스\n\n법률 질문 평가는 없으며 질문0개다. 실모델·Oracle 호출0. [조건](../artifacts/design/criteria.json), [최종 결과](../artifacts/result.json), [실패 포함 로그](../artifacts/logs), [정식 MAIN 반영](../artifacts/main). 60계약과 준비25계약은 중복 범위다.\n')
(REPORT/'수정_설정_검증결과.txt').write_text('GENOS 임베딩 환경변수와 MAIN139 — 2026-11-04\n\n'+'\n\n'.join(bodies)+'\n')
paths=[ART/'result.json',DES/'criteria.json',DES/'baseline.json',DES/'candidate-integrated.json',ART/'main/EMAIL_SENT.json',rp,H/'HANDOFF.json',H/'VALIDATION.json',H/'EMAIL_PRECHECK.json',H/'GUIDE.txt',H/'ENVIRONMENT.txt']
paths+=sorted((ROOT/'06_TOOLS/EXPERIMENTS/adr_1320').glob('*.py'))+sorted(logs.glob('*.log'))
paths+=sorted(ART.glob('*/result.json'))+sorted((ART/'main').glob('*.json'))
am=read(ART/'manifest.json');am['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen implementation, technical checks, retained failures, MAIN binding or verified handoff','contains_raw_prompts_and_outputs':False} for p in sorted(set(paths))]
(ART/'manifest.json').write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('Final audit and report prepared')
