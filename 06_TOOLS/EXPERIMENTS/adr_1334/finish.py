from common import *
import tarfile
REPORT=ROOT/'09_ARTIFACTS/AUDITS/20261104-genos-gold-main141';REPORT.mkdir(exist_ok=True)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rp=ROOT/active['manifest_path'];r=read(rp);b=read(DES/'baseline.json')
assert active['generation']==141
assert all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
runtime={}
for base in [ART/'prepared-contracts/runtime',ART/'prepared-oracle/runtime',ART/'selected-entry-runtime']:
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
summary={'status':'COMPLETE_FIELD_UNVERIFIED','active':active,'serving_files':528,'changed_files':39,'product_changes':b['product_changes'],'working_files_unchanged':True,'prepared_passed':37,'prepared_failed':0,'selected_MAIN_checks':16,'Gold_binding_checks':9,'engine_preflight':{'engines':30,'files':500},'native_SQL_plans_unchanged':639,'data_path':r['data_path'],'data_manifest_sha256':r['data_manifest_sha256'],'prior_Gold_test_count':107,'prior_Gold_checks_repeated_not_additive':True,'Oracle_fixture':oracle,'runtime_files':len(runtime),'model_calls':0,'field_deployed':False,'email_sent':False,'quality_certified':False,'rollback_main140':str((rp.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),'rollback_gold':str((ART/'main/gold-before.json').relative_to(ROOT))}
put(ART/'result.json',summary);put(REPORT/'result.json',summary)
m=read(ADR/'실험/manifest.json');put(ART/'candidate-before-cutover.json',m)
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover','reason':'User explicitly requested MAIN promotion of the already validated Gold feature; prepared exact528-file release then applied after scoped checks. No product editing in this ADR.','production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],'release':{'manifest_path':str(rp.relative_to(ROOT)),'sha256':sha(rp),'release_id':r['release_id']}}
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference':'MAIN140 exact existing manifest; no fresh model or quality evaluation'},'integrated':summary},usage={'model_calls':0},latency={},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=[
 '사용자 “지금 메인에 반영해봐” 지시로 MAIN141 / genos-gold-b003-20261104-r1을 공식 prepare/apply로 선택했다. Gold B003 R5 매핑 선택 기능을 포함하며 실버 S_1 옵션도 유지한다.',
 'MAIN140에는 Gold 선택 분기가 없었다. 앞선 구현·검증이 완료된 MAIN140 기반 Gold 후보528파일을 그대로 사용했다. 제품7+native1+pin31=39변경이다.',
 '사전 criteria에 후보 동일성, 준비 계약36/Oracle1, 엔진30/500,639 실행계획 동일성, 선택 서비스/Gold 연결기 동일성, 원본 세대·병행 작업 보존과 원복을 고정했다.',
 'ADR1334 선점 뒤 기존528파일을 snapshot/freeze했다. 신규 제품변경0, 현재 작업의 멀티턴·검토·워크플로우 수정은 후보에 넣지 않았다. 이전 Gold 감사의107통과는 재사용 근거이며 새 독립 결과로 합산하지 않는다.',
 '준비된 릴리스에서 고정3차원 임베딩 대역과 로컬 Oracle23.26.3 임시17테이블로 API를 확인했다. ORDS는 로컬 SQL bridge이며 실제 현장 네트워크/모델을 사용하지 않았다. 기본 원문 generation과 hash는 MAIN140과 같다.',
 '준비37통과/실패0, 실제 root service16검사·HEALTH200, 유지 Gold연결기9검사 통과. 후보/선택528파일 전체hash일치. native639 실행SQL/list/AST 동일, 엔진30/500통과. 임시 Oracle 스키마2개 삭제 확인.',
 '이번 검사 실패0. 앞선 Gold 감사의 runner/import/프로세스 오염/공개 오류 기대 실패를 삭제하지 않았다. 권한·컬럼·owner변경 오류는 기존 실패 상태로 유지하며 자동 우회하지 않는다.',
 '모델0·새 성능/품질 실험0. Oracle 쿼리와 저장은 격리된 임시 fixture에서만 수행했고 기존 DB 내용은 변경하지 않았다. runtime 전체를 SHA와 무손실 압축으로 보관했다.',
 '메인 코드가 Gold를 선택할 수 있게 된 상태다. 환경변수는 DP=oracle, GENOS_ORACLE_TABLE_MAPPING=gold, GENOS_ORACLE_GOLD_OWNER=<실제owner>이며 Gold 게시채널/ID를 사용한다. 로컬 기본모드를 강제로 Oracle로 변경하지 않았다.',
 'GENOS 현장/실제모델/실답품질/성능은 미검증. 별도 완료1326·워크플로우 반영 요청이 적용 후 전달되어 후속 통합 릴리스로 처리하며 MAIN141 이력은 보존한다.',
 'USER_DIRECTED_CUTOVER/quality_certified=false. MAIN140 포인터와 Gold 이전 binding을 artifacts/main/gold-before.json에 보존했다. 회귀 시 공식 rollback과 같은 Gold binding 복원을 함께 수행한다. 새 메일/현장배포0.',
 '06_TOOLS/EXPERIMENTS/adr_1334/{setup,prepare_release,run,activate,main_entry,gold_entry,finish}.py. 환경설정은 기존 Gold handoff/ENVIRONMENT.txt와 같다. 실제 상태는 rag_main_promotion.py status에서 확인한다.'
]
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')+'\n---\n'
p.write_text(front+'\n# Gold B003 MAIN141 반영\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{x}' for i,(t,x) in enumerate(zip(titles,bodies),1))+'\n')
(ADR/'실험/README.md').write_text('# Gold 메인 연결 기술검증\n\n법률질문/모델0. [조건](../artifacts/design/criteria.json), [결과](../artifacts/result.json). 준비37통과, 실제MAIN16·Goldbinding9통과. 기존 Gold107검사와 중복 범위를 합산하지 않는다.\n')
(REPORT/'메인반영과_검증결과.txt').write_text('\n\n'.join(bodies)+'\n')
paths=sorted((ROOT/'06_TOOLS/EXPERIMENTS/adr_1334').glob('*.py'))+[rp,ART/'result.json',ART/'runtime-manifest.json',archive]
paths+=list(DES.glob('*.json'))+list((ART/'main').glob('*.json'))+list((ART/'main').glob('*.log'))+list(ART.glob('*.log'))+list(ART.glob('*/result.json'))
am=read(ART/'manifest.json');am['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact Gold MAIN141 cutover evidence and retained runtime','contains_raw_prompts_and_outputs':False} for p in sorted(set(paths))]
(ART/'manifest.json').write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('MAIN141 verification and immutable cutover evidence complete')
