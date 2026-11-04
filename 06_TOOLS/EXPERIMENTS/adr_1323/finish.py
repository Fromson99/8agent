from common import *
import shutil
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main140_oneclick_mail_20261104_r1'
REPORT=ROOT/'09_ARTIFACTS/AUDITS/20261104-genos-oracle-startup-main140';REPORT.mkdir(exist_ok=True)
a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rp=ROOT/a['manifest_path'];r=read(rp)
b=read(DES/'baseline.json');changes=read(ART/'working-integration.json')['after']
assert a['generation']==140 and len(changes)==2
assert all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
assert all(sha(ROOT/n)==h for n,h in changes.items())
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items() if n not in changes)
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
assert read(H/'VALIDATION.json')['passed']
logs=ART/'logs';logs.mkdir(exist_ok=True)
for p in Path('/tmp').glob('adr1323-*.log'):
 if not (logs/p.name).exists():shutil.copyfile(p,logs/p.name)
summary={'status':'COMPLETE_FIELD_UNVERIFIED','main':140,'release':a,'serving_files':525,'changed_files':changes,
 'baseline_screenshot_failure_reproduced':read(ART/'baseline-result.json'),'candidate_passed':27,'candidate_failed':1,'baseline_existing_passed':21,'baseline_existing_failed':1,
 'same_existing_failure':'test_failure_inside_sse_result_is_failed_not_answered expects old public error wording',
 'new_clean_startup_checks':6,'prepared_checks':6,'counts_overlap':True,'selected_MAIN_checks':16,'Gold_binding_checks':9,
 'native_SQL_and_engine_pins_unchanged':True,'engine_preflight':{'engines':30,'files':497},
 'actual_local_HTTP':['health','SSE_CHECK','JSON_PING'],'extra_env_required':False,'new_dependencies':False,
 'real_Oracle_calls':0,'model_calls':0,'field_deployed':False,'quality_certified':False,
 'preexisting_working_differences_preserved':b['preexisting_working_changes'],'only_own_changes_integrated':True,
 'oneclick':read(H/'VALIDATION.json'),'email':read(H/'EMAIL_SENT.json'),
 'rollback_main139':str((rp.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),'rollback_gold':str((ART/'main/gold-before.json').relative_to(ROOT))}
put(ART/'result.json',summary);put(REPORT/'result.json',summary)
m=read(ADR/'실험/manifest.json');put(ART/'candidate-audit-before-cutover.json',m)
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover','reason':'User development MAIN/oneclick handoff request continued with screenshot of Oracle startup failure. Isolated MAIN139-based two-file fix tested before official MAIN140 prepare/apply. Working multiturn changes preserved separately.',
 'production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],
 'release':{'manifest_path':str(rp.relative_to(ROOT)),'sha256':sha(rp),'release_id':a['release_id']}}
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'startup_import':'failed_reproduced','existing_passed':21,'existing_failed':1},'integrated':summary},
 usage={'model_calls':0,'Oracle_calls':0},latency={},error_taxonomy=[{'type':'startup_backend_path_order','baseline_failed':True,'fixed':True},{'type':'old_error_wording_fixture','count':1,'same_in_baseline':True}])
put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=[
 'MAIN140 genos-oracle-startup-20261104-r1 선택·삼성메일 수정본 전달. MAIN139 서빙525파일 중 start_sse.py/stream_app.py 두 파일의 import 경로 등록 순서만 수정. 추가환경변수/패키지0. 이전 MAIN139 임베딩 ID/TOKEN·프로필자동사용과 개발계 G19 매핑은 그대로다.',
 '사용자 사진의 시작명령 python3 08_DEPLOYMENT/GENOS/start_sse.py는 ROOT만 등록한 뒤 install_system_logging을 호출했다. DP=oracle이면 genos_diagnostics.py:286에서 semantic_runtime.detailed_log_storage를 import하지만 02_BACKEND가 아직 검색경로에 없어 ModuleNotFoundError. stream_app.py도 같은 순서였다. 로깅OFF만으로는 우회되지 않는 점까지 재현했다.',
 'design/criteria.json에 사진 오류 재현, PYTHONPATH 없는 별도프로세스/root·다른cwd, 직접HTTP모듈 import, 실제서버 health/SSE_CHECK/PING, 기존포트/1worker, NFS검사/모델·DB 미호출, 배포·복구를 사전동결. 다른 작업제품은 유지하며 선택MAIN139만 기준으로 삼는다.',
 'ADR선점 뒤 현재작업525파일과 선택139를 각각hash. 작업의 기존38차이는 격리복사에서만 MAIN139로 되돌리고 두파일수정→525파일rev001동결. pytest 프로세스가 미리 import한 경로와 별도로 깨끗한 자식프로세스와 실제 uvicorn 서버를 사용. 준비릴리스에서도 같은6검사 재실행 후 공식apply.',
 '로컬 Python3.14·Python3.11 AST문법검사. fresh subprocess에 PYTHONPATH/Oracle·모델키를 상속하지 않음. 사진의DP와시작명령만재현, 사진의토큰값은복사/사용0. 원문·Oracle·임베딩실데이터0. 사용자필드서빙623화면관찰이며정확한배포커밋은미확인.',
 '후보27통과/1실패 중 새기동6전부통과. 기존오류문구fixture1실패는 MAIN139 기존검사21통과/1실패와동일. 준비6은중복범위. 실제MAIN16·Goldbinding9 통과. 기존engine30/497파일·nativeSQL639바이트그대로. 실제TCP HTTP /health200·SSE_CHECK·JSON PING200, DB/모델자격증명없이동작. 무인자bash/DEV링크/재실행/rename/status/stage/commit/codegate/undo·527기존파일복원통과.',
 '제품 오류는 로그 초기화보다 앞에 BACKEND경로 등록으로 수정. 기존SSE회귀검사의 실행 오류 (HTTP500) 옛문구 기대1건은 최신공개오류문구와달라 기준/후보동일실패, 결과와원본유지. 성공으로바꾸거나표시로직을추가수정하지않았다.',
 '새모델/Oracle0·DB변경0. 법률질문/속도/품질/회수효과실험없음. 서버/포트프로세스는검사후정리. 새환경변수와NFS검사우회0, import문제만수정했다.',
 '환경변수추가나패키지설치가원인이아니었다. APP초기화가요구하는선행검색경로를양쪽entry에서먼저등록하면같은명령으로기동된다. 원문/모델준비는기존lazy시점유지. HTTP기동성공과Oracle/최종답변성공은별개다.',
 '현장GENOS/ORDS/NFS/실임베딩·답변LLM/리비전배포는미실행. Python3.11실행인증아님. 기존멀티턴작업38파일차이를보존하되MAIN140에는포함하지않았다. 선택525와작업전체가같다고보고하지않으며이번두파일만같다.',
 'USER_DIRECTED_CUTOVER quality_certified=false. MAIN139 rollback포인터·Gold이전binding 보존. 삼성메일 SENT '+summary['email']['id']+' 수신자/제목/본문/6첨부명·크기확인. 이전MAIN139메일불변. Git push/현장배포0. 현장은checkout적용→기존commit/push→새리비전배포, 시작명령그대로사용.',
 '06_TOOLS/EXPERIMENTS/adr_1323 setup/freeze/check/prepare_release/activate/main_entry/gold_entry/package. 현장 TRANSFER: bash MAIN140_ONECLICK_R1.txt. 코드서빙 시작: python3 08_DEPLOYMENT/GENOS/start_sse.py. 선택사전검사 --check.']
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')+'\n---\n'
p.write_text(front+'\n# Oracle 기동 import 순서와 MAIN140\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{x}' for i,(t,x) in enumerate(zip(titles,bodies),1))+'\n')
(ADR/'실험/README.md').write_text('# 시작 경로 기술검증\n\n법률질문0·모델0·Oracle0. [사진오류재현](../artifacts/baseline-startup.log), [조건](../artifacts/design/criteria.json), [결과](../artifacts/result.json), [로그](../artifacts/logs). 기존문구fixture1실패는MAIN139/140동일이며 새기동6검사는통과했다.\n')
(REPORT/'시작오류_수정_검증.txt').write_text('Oracle 모드 기동 오류 수정과 MAIN140\n\n'+'\n\n'.join(bodies)+'\n')
paths=[ART/'result.json',ART/'baseline-startup.log',ART/'baseline-result.json',DES/'criteria.json',DES/'baseline.json',DES/'candidate-integrated.json',rp,H/'HANDOFF.json',H/'VALIDATION.json',H/'EMAIL_PRECHECK.json',H/'GUIDE.txt',H/'ENVIRONMENT.txt']
paths+=sorted((ROOT/'06_TOOLS/EXPERIMENTS/adr_1323').glob('*.py'))+sorted(logs.glob('*.log'))+sorted(ART.glob('*/result.json'))+sorted((ART/'main').glob('*.json'))
am=read(ART/'manifest.json');am['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen startup fix, actual local HTTP checks, retained failures, MAIN/handoff bindings','contains_raw_prompts_and_outputs':False} for p in sorted(set(paths))]
(ART/'manifest.json').write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('Audit prepared; all concurrent workspace changes preserved')
