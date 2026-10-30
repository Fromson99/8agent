from common import *
import re
f=read(sorted(DES.glob('freeze-*.json'))[-1]);rev=f['candidate_revision']['revision_id']
tech=read(ART/f'check-{rev}.json');work=read(ART/'check-working.json');reg=read(ART/'regression-comparison.json');integration=read(ART/'working-integration.json');stage=read(DES/'staging-final.json');b=read(DES/'baseline.json')
checks={'technical78':tech['passed']==78 and tech['failed']==0,'working58':work['passed']==58 and work['failed']==0,
 'no_import_leaks':not tech['import_leaks'] and not work['import_leaks'],'same_regression':not reg['status_differences'] and not reg['new_regressions'],
 'serving466':len(stage['files'])==466 and stage['files']==f['files'],'six_product_files':len(integration['product_files'])==6,
 'working_storage_preserved':integration['three_way_merges']==['02_BACKEND/semantic_runtime/legal_agent/completion_execution.py'],
 'main113_selected_before_promotion':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'resource_items_unchanged':all(f['files'][n]==h for n,h in b['manifest']['files'].items() if n.endswith(('request_deadline.py','experiment_client.py','local_gemma.py'))),
 'new_external_calls_zero':tech['external_model_calls']==work['external_model_calls']==0}
assert all(checks.values()),checks
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
result={'status':'complete','strict_success':True,'checks':checks,'scope':'Technical qualification of requirement coverage; selected service validation follows activation','candidate':f['candidate_revision'],
 'files':466,'changed_files':len(stage['changed']),'technical_conditions':78,'working_conditions':58,'regression':reg,
 'external_model_calls':0,'separate_review_model_stage_added':False,'quality_certified':False,'semantic_completeness_certified':False,'genos_deployed':False,
 'cm007_cm009_rerun':False,'local_resource_items_1_to_3':'Explicitly excluded by user',
 'preserved_failures':['rev001 standard inspect shadowed by legacy test filename before collection','rev002 missing test-runtime parent:51 pass22 setup errors','rev003 missing candidate engine hash update and fixture ROOT binding:61 pass4 fail8 errors','rev004 new assessment receipt missing downstream schema:70pass3fail; fixed in rev005','rev00573pass; rev006 same product plus5 additional verification cases78pass'],
 'evidence':{p.name:bind(p) for p in [ART/f'check-{rev}.json',ART/'check-working.json',ART/'regression-comparison.json',ART/'working-integration.json',DES/'release-rebase.json']}}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'reviewed':{'status':'complete','technical_success':True,'quality_certified':False}},comparisons=[reg],usage={'external_model_calls':0},latency={'performance_claim':False},error_taxonomy=result['preserved_failures'],main_wiring='promotion-candidate',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[('결정 요약','사용자가 요청한4번만 구현했다. 기존 ASSESS에 질문 전체의 요구별 원문 충족 검토를 넣고 기술 통합을 채택한다. 법률 의미 정확도와 전체 필요 조문 발견의 인증은 아니다. 실제 MAIN 선택 확인은 별도 승격 영수증으로 구분한다.'),
 ('문제와 변경 전 구조','확정된 목표의 선집행은 있었지만 목표나 초기 쟁점에서 빠진 질문 요구를 최종 검토에서 별도 대조하는 구조가 없었다. 충분하다는 의견을 실제 주장·원문·미해결 부족과 연결할 필요가 있었다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). 질문 원문 전체·기존 쟁점의 누락, 없는 주장/근거/부족 번호, 이유만의 제외, 잘못된 완료를 거절한다. 의미 판단은 모델 의견으로 남기고 기존 원문·권한·상태·예산 계약을 유지한다.'),
 ('실험 설계','MAIN113의465파일에서 출발해 최종466파일로 동결했다. 제품/설정6개와 의존성 pin을 수정했다. 기존 최종 판단에 같은 응답의 requirement_review를 추가하며 별도 모델 단계는 없다. 합성 단위/API 검사와 MAIN113 동일 회귀만 수행했다.'),
 ('데이터·모델·재현성','데이터·Qwen3.8·Chutes/NearAI 확정429정책·40/1024/1800예산·출력상한없음 유지. 외부 모델0·CM007/009 재실행0. 같은 코드/원문/상태를 결속하고 기준답변을 제품 입력에 넣지 않았다.'),
 ('결과','최종78조건 통과(요구 계약·API5사례·기존 보완 계약 포함), 병합한 작업 코드58조건 통과(기존 저장 압축22검사 포함). 동일211회귀는 MAIN113/후보 모두189통과·기존9실패·준비오류13, 항목별 동일·새회귀0. [결과](artifacts/run-001/result.json).'),
 ('사례별 오류 분석','검사 준비의 inspect 이름 충돌·임시 폴더 누락·기준 경로와 후보 pin 누락을 보존했다. 실제 API에서 새 검토 영수증이 최종 저장 스키마에 없던 연결 누락을 발견하여 ASSESS/COMPOSE 스키마·전달·일치 검사를 수정했다. 이후 전체 검사 통과.'),
 ('비용·지연·회수 규모','새 외부 모델0, 별도 검토 단계0. 모의 API에서 정상/제한 답변은 기존 ASSESS1회이며 형식 보완 때만 기존 한도1회를 쓴다. 새 모델 토큰·속도·정답률 비교를 수행하지 않았다.'),
 ('해석','SATISFIED는 같은 쟁점의 실제 claims/evidence, EXCLUDED는 현재 원문 또는 사용자의 실제 범위 발언, UNRESOLVED는 같은 응답의 material gap에 연결한다. 질문의 문단 번호는 위치이며 의미 분해는 모델이 한다. 제목 직접 일치와 무관하게 빠진 요구를 재검토하고 필요한 원문은 기존 추가 조사로 보낸다. 예산 소진·반복 부족은 제한 답변에 남긴다.'),
 ('한계와 일반화 가능 범위','원문과 의미상 무관한 주장을 모델이 잘못 연결하는 오류까지 코드로 판정하지 않는다. 문단을 모두 표시했다고 의미적 완전성이 보장되지 않는다. 온톨로지 데이터는 유지하지만 요구 검토 ON에서는 시나리오 선택만으로 완료하지 않고 기존 원문 ASSESS를 거친다. 이 경로의 실제 모델 비용·품질은 미측정이다. 사용자가 보류한 자원1~3, GENOS 현장, CM007/009 실모델은 미수행.'),
 ('운영 결정·롤백 조건','작업 코드의 completion_execution.py는3방향 병합으로 기존 저장 기능을 보존했다. 검증한466파일을 기존 공식 승격 경로로 연결한 뒤 선택 서비스의 OFF/ON/빈DB를 확인한다. 실패하면 이전 MAIN113 릴리스로 되돌린다. 완료 ADR은 고치지 않으며 실제 선택은 별도 영수증에 남긴다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1188의 setup/freeze/check/regression/integrate/working_check/qualify. 완료 실행을 덮어쓰지 않는다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1188-requirement-coverage-review --final`')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 질문 요구별 종료 전 원문 충족 검토\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n[기준](../artifacts/design/criteria.json), [결과](../artifacts/run-001/result.json), [정확한 서빙 파일](../artifacts/design/release-rebase.json). 합성 계약 검사이며 새 실모델·법률 정답률 측정은 없다.\n')
print('Qualified',result['files'],'files',result['changed_files'],'changed')
