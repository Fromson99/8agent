"""Finalize the user-authorized local MAIN selection audit, without new model calls."""
from common import *
import re

active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release_path=ROOT/active['manifest_path']
assert active['generation']==131 and active['release_id']==RELEASE
assert active['deployment_basis']=='USER_DIRECTED_CUTOVER' and active['quality_certified'] is False
assert sha(release_path)==active['release_manifest_sha256']
activation=read(OUT/'activation.json');entry=read(OUT/'main-entry.json');gold=read(OUT/'gold-entry.json')
workspace=read(ART/'workspace-check.json');api=read(ART/'prepared-api/result.json')
inherited=read(DES/'inherited-verification.json')
compat=ROOT/'04_EXPERIMENTS/ADR/ADR-1273-gold-user-directed-main-binding'
tests=read(compat/'artifacts/tests.json');freeze=read(compat/'artifacts/freeze.json')
assert entry['passed'] and gold['passed'] and all(entry['checks'].values()) and all(gold['checks'].values())
assert workspace['passed']==110 and workspace['failed']==0
assert api['passed']==13 and api['failed']==0 and api['code_unchanged']
assert tests['passed']==16 and tests['failed']==0 and tests['exit']==0
assert inherited['code_identity_all518'] and inherited['passed']==641 and inherited['actual_qwen_fault_cases_passed']==3
assert sha(ROOT/freeze['target'])==freeze['after']
evidence=[OUT/n for n in ('activation.json','main-entry.json','gold-entry.json','authorization.json','validation.json')]
checks={'inherited_loop_regression':641,'inherited_actual_qwen_fault_cases':3,
 'fresh_workspace_contracts':110,'fresh_prepared_release_api':13,'fresh_gold_authority_contracts':16,
 'actual_root_service_conditions':len(entry['checks']),'actual_gold_binding_conditions':len(gold['checks'])}
result={'status':'PASS','release_id':RELEASE,'generation':131,'serving_files':504,'changed_serving_files':57,
 'deployment_basis':active['deployment_basis'],'quality_certified':False,'checks':checks,
 'evidence':[bind(p) for p in evidence], 'inherited':bind(DES/'inherited-verification.json'),
 'new_model_calls':0,'oracle_calls':0,'genos_deployed':False,'git_pushed':False,
 'limitations':['Inherited tests and live cells are code-bound prior evidence, not new independent runs.',
 'Final NEED_TARGET_CLAIM_LINK 422 and provider UNKNOWN 504 remain unresolved.',
 'Actual Oracle workspace end-to-end, actual NFS, GENOS and legal quality are not certified.'],
 'rollback':'MAIN130 pointer plus saved Gold connector and binding; Oracle layout4 reader preserved'}
put(RUN/'result.json',result)
compat_result={'status':'PASS','tests_passed':16,'tests_failed':0,'tests':bind(compat/'artifacts/tests.json'),
 'freeze':bind(compat/'artifacts/freeze.json'),'actual_consumer':bind(OUT/'gold-entry.json'),
 'selected_release':RELEASE,'root_connector_equals_frozen':True,'gold_mapping_checks_in_workspace':27,
 'setup_failure_preserved':bind(compat/'artifacts/test-setup-failure.json'),
 'model_calls':0,'oracle_calls':0,'quality_certified':False}
put(compat/'artifacts/result.json',compat_result)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
shared_limit='사용자 지시 전환이며 품질 승격 인증이 아니다. 과거 실제 실패와 in-sample 판정은 그대로 보존한다. 새 모델/Oracle 호출0, 현장 GENOS·NFS·법률품질 미검증.'
values={1272:[
 '사용자 “지금까지 된거 메인에 싹다 반영해”에 따라 MAIN131/cumulative-loop-workspace-20261102-r1을 공식 prepare/apply로 선택했다. 현재 서빙504파일, MAIN130 대비57변경(제품26+pin31), 신규8/삭제0. Gold도 동일 MAIN131에 연결했다.',
 'MAIN130은 저장 안전성·진행 중복축소를 포함하지만 이후 작업 코드의 에이전트 오류 복구·일반 원문 검토·자유 작업공간이 선택되지 않았다. 현재 코드 자체를 동결해 다른 작업을 덮어쓰지 않고 통합했다.',
 '[사전 기준](artifacts/design/criteria.json): 현재 모든 서빙 코드 정확 일치, 기존 검증 코드 결속, 작업공간·API·실제 진입 소비자 통과, 데이터·권한·상태 보존. 기준과 후보는 검사 전에 동결했다.',
 'baseline은 MAIN130 및 완료 부모의 읽기전용 근거다. integrated는 현재518파일 동결 중 공식 서빙504파일이다. 제외14개는 연구/미등록 보조 파일로 작업 공간에 보존했다. 부모1271/1251의 채택 항목·충돌 없음의 근거는 manifest.integration에 기록했다. 실패1255/1259/1260 후보 전용 변경을 성공 구현으로 가져오지 않았다.',
 '전체518파일이 ADR1271 최종 회귀·실제 Qwen 검증 코드와 같다. 이번 새 모델 호출0. 기존 원문 세대·Gold R18/물리 매핑·온톨로지 설정·권한을 유지했다. MAIN130 layout4 reader 및 구조화 Oracle/상세 NFS 정책을 보존했다.',
 '[결과](artifacts/run-001/result.json). 기존641회귀/실제Qwen 복구3종은 동일 코드 근거다. 이번 새 작업공간110, 준비 릴리스 API13, 별도1273 승인·변조거절16, 실제 root 진입16조건과 Gold 연결9조건을 통과했다. 범위가 겹치므로 독립 표본으로 합산하지 않는다.',
 '전환 전에 Gold가 VALIDATED_ADR_PROMOTION만 허용하는 소비자 차이를 발견했다. 별도 ADR1273에서 명시 사용자 승인·구조 검증 영수증을 해시로 결속하는 경로를 추가하고 거절 계약을 검사했다. 최종 근거 검토422와 공급자 UNKNOWN504는 미해결로 보존한다.',
 f'새 모델 비용/전송0, Oracle 읽기·쓰기/DDL0. 작업공간 {workspace["seconds"]:.3f}초, 준비 API {api["elapsed_seconds"]:.3f}초. 이 값은 합성 검사의 경과시간이며 실제 질의 지연·검색 회수율 측정이 아니다.',
 '정확히 검증된 현재 서빙 코드가 실제 진입점에서 선택됐다는 구조적 결론이다. quality_certified=false이며 실모델 전체 질의 성공률·법률품질 개선으로 확대하지 않는다.',
 shared_limit+' 실제 Oracle 작업공간 컴파일→승인→RAG 전체 성공은 여전히 미확인이다.',
 '선택 MAIN131. MAIN130 원복 포인터와 Gold 이전 connect.py/ENGINE_BINDING.json을 감사 폴더에 보존했다. 원복 시 writer를 정지하고 공식 rollback과 Gold 두 파일 복원을 함께 수행한다. layout4 미지원 MAIN129로 되돌리지 않는다. 이번 원복 실행0.',
 'prepare.py → workspace_check.py → prepare_release.py → 준비 릴리스 API 검사 → ADR1273 승인 계약 → activate.py → main_entry.py/gold_entry.py → finalize.py. 완료 릴리스 prepare/apply나 실모델 셀을 재실행하지 않는다. 재검토는 저장 해시/영수증으로 한다.'
 ],1273:[
 'Gold 연결기에 공식 USER_DIRECTED_CUTOVER의 명시 승인 영수증 검증을 추가했다. 동결 연결기1파일을 MAIN131 Gold binding과 함께 적용하고 실제 consumer 진입을 확인했다.',
 'Gold는 공식 runtime이 지원하는 사용자 지시 전환을 허용하지 않고 qualified 릴리스만 허용했다. 모든 현재 작업의 MAIN 반영 지시가 있어도 기존 guard에서 막히는 호환 차이다.',
 '[사전 기준](artifacts/criteria.json): 기존 qualified 경로 유지, 사용자 승인·구조 검사·릴리스 일치와 모든 코드/연결기 해시 검증, 누락·변조·다른 릴리스 거절.',
 'baseline 기존 guard를 보존하고 compatible 1파일 후보를 동결했다. 긍정2종과 부정14종의 합성 임시 파일 계약을 검사했다. 실제 Oracle에 접속하지 않았다.',
 '[동결](artifacts/freeze.json)과 tests.json에 실행 근거를 기록했다. 법령·기준답변·회수 측정은 해당 없다. 모델/평가모델 호출0.',
 '[결과](artifacts/result.json): 16/16 통과. 기존 Gold 매핑27검사는1272의110검사에 포함된다. 전환 후 실제 Gold load_runtime 9조건 통과. query release/데이터 경로/물리 매핑/온톨로지 설정 보존.',
 '첫 pytest plugin callback 인자 이름 오류는 검사 시작 전 실패로 test-setup-failure.json에 보존했다. 실행기 인자만 고친 뒤16검사 통과. 제품 후보 수정으로 결과를 바꾸지 않았다.',
 f'승인 계약 {tests["seconds"]:.3f}초. 새 모델/Oracle/임베딩0; 검색량·성능 비교 없음.',
 '명시 사용자 권한이 있는 공식 릴리스의 정확한 코드 소비를 지원한다. 사용자 전환을 품질 인증으로 바꾸거나 임의 미승인 릴리스를 허용하지 않는다.',
 shared_limit,
 'MAIN131과 함께 적용. MAIN130 원복 시 이전 Gold binding 및 이전 connect.py를 함께 복원해 연결기 자기 해시까지 일치시킨다. 원본 backup은1272 감사 폴더에 보존한다.',
 'prepare.py 후보 동결 → test_authority.py 16계약 →1272 activate.py → gold_entry.py. 증거는 원본 tests/freeze/consumer 영수증과 파일 해시로 재검토한다.'
 ]}
for number,adr,arm,res,rp in [(1272,ADR,'integrated',result,RUN/'result.json'),(1273,compat,'compatible',compat_result,compat/'artifacts/result.json')]:
 m=read(adr/'실험/manifest.json')
 m['design']['frozen_pre_cutover_isolation']=m['design']['code_isolation']
 m['design']['operational_audit']=True
 m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover',
  'reason':'User explicitly authorized cumulative MAIN selection; final audit follows the official cutover. Original pre-cutover candidate isolation remains recorded separately.',
  'production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,
  'main_wiring_unchanged':False,'candidates':[],
  'release':{'manifest_path':str(release_path.relative_to(ROOT)),'sha256':sha(release_path),'release_id':RELEASE}}
 m['runs'][0].update(status='complete',sha256=sha(rp))
 m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},arm:res},
  judge_disagreements=0,usage={'new_model_calls':0,'oracle_calls':0},latency={'no_end_to_end_performance_claim':True},
  error_taxonomy=[{'type':'KNOWN_LIMITS_PRESERVED','detail':shared_limit}])
 if number==1273:
  m['dataset'].update(name='Synthetic explicit release authority and hash rejection matrix',version='20261102',
   frozen_source=str((adr/'artifacts/criteria.json').relative_to(ROOT)),sha256=sha(adr/'artifacts/criteria.json'))
 (adr/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 p=adr/'README.md';front=p.read_text().split('---',2)[1]
 front=re.sub(r'(?m)^status:.*$','status: Accepted',front)
 front=re.sub(r'(?m)^main_wiring:.*$','main_wiring: user-directed-cutover',front)
 p.write_text('---'+front+'---\n\n# '+m['adr_id']+' MAIN131 사용자 지시 반영 감사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values[number]),1))+'\n')
 (adr/'실험/README.md').write_text('# 구조·반영 감사 인덱스\n\n새 법률 질문·제품/평가 모델 호출0. 합성 계약과 실제 진입 소비자를 확인했다. 기존 실모델 결과는 원래 ADR1271에 보존한다.\n\n- [실행 manifest](manifest.json)\n- [결정과 결과](../README.md)\n- [동결·실행 산출물](../artifacts/manifest.json)\n')
 p=adr/'artifacts/manifest.json';am=read(p)
 files=[x for x in (adr/'artifacts').rglob('*') if x.is_file() and x!=p
        and not any(t in str(x) for t in ('/selected-entry-runtime/','/runtime/','/__pycache__/'))]
 files+=evidence+[OUT/'gold-before.json',OUT/'gold-connector-before.py',OUT/'gold-binding-prepared.json']
 am['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,
  'description':'Frozen design, preserved contract results, official selection and consumer evidence',
  'contains_raw_prompts_and_outputs':False} for x in sorted(set(files))]
 p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
put(OUT/'summary.json',result)
print(json.dumps({'MAIN':131,'passed':True,'checks':checks},ensure_ascii=False))
