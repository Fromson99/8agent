from common import *
import tarfile
REPORT=ROOT/'09_ARTIFACTS/AUDITS/20261104-gold-workflow-main142';REPORT.mkdir(exist_ok=True)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rp=ROOT/active['manifest_path'];r=read(rp);b=read(DES/'baseline.json')
assert active['generation']==142
assert all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
assert read(ART/'prepared-workflow/result.json')['passed']==73
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
runtime={}
for base in [ART/'prepared-contracts/runtime',ART/'prepared-workflow/runtime',ART/'prepared-oracle/runtime',ART/'selected-entry-runtime']:
 if base.exists():
  for p in base.rglob('*'):
   if p.is_file() and not p.is_symlink():runtime[str(p.relative_to(ART))]=sha(p)
archive=ART/'runtime-evidence.tar.gz'
with tarfile.open(archive,'w:gz') as t:
 for p in runtime:t.add(ART/p,arcname=p,recursive=False)
with tarfile.open(archive) as t:
 for x in t:assert hashlib.sha256(t.extractfile(x).read()).hexdigest()==runtime[x.name]
put(ART/'runtime-manifest.json',{'archive':str(archive.relative_to(ROOT)),'sha256':sha(archive),'files':runtime})
oracle=read(ART/'prepared-oracle/runtime/test_actual_main_oracle_source0/actual-oracle.json')
assert oracle['created']==oracle['dropped']
summary={'status':'COMPLETE_FIELD_UNVERIFIED','active':active,'serving_files':528,'changed_files':43,'product_changes':b['product_changes'],'working_files_unchanged':True,'prepared_passed':110,'prepared_failed':0,'selected_MAIN_checks':16,'Gold_binding_checks':9,'engine_preflight':{'engines':30,'files':500},'native_SQL_plans_unchanged':639,'data_path':r['data_path'],'data_manifest_sha256':r['data_manifest_sha256'],'prior_Gold_test_count':107,'prior_Gold_checks_repeated_not_additive':True,'Oracle_fixture':oracle,'runtime_files':len(runtime),'model_calls':0,'field_deployed':False,'email_sent':False,'quality_certified':False,'rollback_main141':str((rp.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),'rollback_gold':str((ART/'main/gold-before.json').relative_to(ROOT))}
put(ART/'result.json',summary);put(REPORT/'result.json',summary)
m=read(ADR/'실험/manifest.json');put(ART/'candidate-before-cutover.json',m)
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover','reason':'User requested combining the workflow/review handoff with MAIN141 Gold; exact three-way merge prepared and selected after technical checks. Later1332 working changes excluded.','production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],'release':{'manifest_path':str(rp.relative_to(ROOT)),'sha256':sha(rp),'release_id':r['release_id']}}
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference':'MAIN141 Gold and completed1326 workflow handoff; no fresh model or quality evaluation'},'integrated':summary},usage={'model_calls':0},latency={},error_taxonomy=[{'type':'build_fixture_missing_data_mount','fixed':'Temporarily link original immutable data for pin validation, then remove link before freeze','product_changes':0}])
put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=['사용자의 다른 MAIN 작업에 같이 반영하라는 요청을 전달받아 MAIN142 / gold-workflow-review-20261104-r1을 선택했다. 완료MAIN141 Gold를 유지하고 완료1326 기반 메일 워크플로우·검토 설명 수정을 통합했다.', 'MAIN141 Gold와 전달본525파일은 MAIN140을 공통 기준으로 제품 변경이 겹치지 않는다. Gold제품7을 유지하고 검토·메모리·화면11파일을 채택했다. 공유 native계획1+pin31은 정확한 합집합으로 다시 생성했다.', 'criteria에 준비/선택528파일 동일, Gold7/워크플로우11 exact, native639 실행계획 동일, workflow73+Gold계약기동36+Oracle1 통과, 실제선택/Gold연결기 및 원본세대·작업보존을 동결했다.', 'ADR1334/integrated와 완료1326/integrated를 merge 부모로 고정했다. 완료1326에 두 UI/검토설명 변경을 적용한 기존 전달본의 SHA와73통과 근거를 별도 연결했다. 최신 작업1332와 실제시험1333/1335는 포함하지 않았다. 다른 대화는 제품수정/포인터쓰기 없이 합집합496파일의 독립 대조를 맡았다.', '실험 후보528파일 동결 후 공식prepare 결과와 SHA를 대조했다. 모델0. Oracle검사는 로컬23.26.3 임시17테이블·SQLbridge·고정임베딩이며 현장실행이 아니다. 기본원문 generation/hash와 기존Gold 게시/물리매핑은 같다.', '준비110통과/실패0: workflow73,Gold/기동36,Oracle1. 엔진30/500·native639 실행SQL/list/AST동일. 실제MAIN16검사 HEALTH200와 Gold동일엔진9검사 통과. MAIN141대비43변경,MAIN140대비50변경,선택528파일이다.', '첫 rehash는 후보에 원본 데이터 경로가 없어 실패했다. 원본01_DATA를 일시 참조해 동일 데이터pin을 검증하고 참조링크를 제거한 뒤 동결했다. 제품/데이터 수정0, 실패로그 보존. ADR1335 번호는 별도의 voting-repeat-live 선점임을 확인하고1336으로 생성했다. 기존실모델실패와 품질판정은 변경하지 않았다.', '새모델0·성능비교0. runtime 원본 전체를 SHA와 무손실 압축으로 보존했다. 임시Oracle스키마2개 삭제, 기존원문·게시·상태데이터 변경0. 준비검사와 이전107/73 결과는 중복 범위이므로 누적 성공수로 합산하지 않는다.', 'Gold 선택기능과 원문 접기·검토실패 한국어 설명·같은대화 후속 안내가 한 메인에 들어갔다. Gold 옵션과 SIDDA 기록저장,실버S_1선택을 유지한다. 검토오류를 성공으로 보정하지 않는다.', '현장GENOS/실모델/법률품질/속도 미검증이다. 작업1332의 반복목표·claim 연결 수정은 포함하지 않았다. 이전Gold/워크플로우 메일 각각의 전체ZIP은 이 통합MAIN142 전체코드와 다르므로 둘을 순서대로 덮어쓰는 통합방법으로 사용하지 않는다.', 'USER_DIRECTED_CUTOVER/quality_certified=false. MAIN141 rollback포인터 및 이전Goldbinding 보존, 실제선택실패 시 공식rollback과 연결기binding 복원을 함께 수행한다. MAIN141 완료이력은 그대로다. 현재 작업528파일은 수정하지 않았고 새메일/현장배포0.', '06_TOOLS/EXPERIMENTS/adr_1336/{setup,resume_freeze,prepare_release,run,activate,main_entry,gold_entry,finish}.py. 실제선택상태는 rag_main_promotion.py status. 초기setup 실패보존 후 resume_freeze로 동일후보를 동결했다.']
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')+'\n---\n'
p.write_text(front+'\n# Gold·워크플로우 MAIN142 통합\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{x}' for i,(t,x) in enumerate(zip(titles,bodies),1))+'\n')
(ADR/'실험/README.md').write_text('# Gold 메인 연결 기술검증\n\n법률질문/모델0. [조건](../artifacts/design/criteria.json), [결과](../artifacts/result.json). 준비110통과, 실제MAIN16·Goldbinding9통과. 이전검사와 중복 범위를 합산하지 않는다.\n')
(REPORT/'메인반영과_검증결과.txt').write_text('\n\n'.join(bodies)+'\n')
paths=sorted((ROOT/'06_TOOLS/EXPERIMENTS/adr_1336').glob('*.py'))+[rp,ART/'result.json',ART/'runtime-manifest.json',archive]
paths+=list(DES.glob('*.json'))+list((ART/'main').glob('*.json'))+list((ART/'main').glob('*.log'))+list(ART.glob('*.log'))+list(ART.glob('*/result.json'))
am=read(ART/'manifest.json');am['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact Gold/workflow MAIN142 cutover evidence and retained runtime','contains_raw_prompts_and_outputs':False} for p in sorted(set(paths))]
(ART/'manifest.json').write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('MAIN142 verification and immutable cutover evidence complete')
