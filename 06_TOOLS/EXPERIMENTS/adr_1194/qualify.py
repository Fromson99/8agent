from common import *
import re
f=read(DES/'freeze-rev-001.json');b=read(DES/'baseline.json');tech=read(ART/'check-final.json');work=read(ART/'check-working.json');reg=read(ART/'regression-comparison.json');stage=read(DES/'staging-final.json');integration=read(ART/'working-integration.json')
pins={r['manifest'] for r in read(ROOT/f['code_root']/'00_SYSTEM/PIPELINE.json')['engines'].values()}|{'00_SYSTEM/PIPELINE.json'}
products={'02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('completion_execution.py','completion_v8.py','completion_contracts.py')}
checks={'prospective_contracts_pass':tech['all_passed'] and tech['unique_conditions']==130,
 'working_contracts_pass':work['passed']==130 and work['failed']==0 and not work['import_leaks'],
 'same_regression':not reg['status_differences'] and not reg['new_regressions'],
 'same466inventory':set(stage['files'])==set(b['manifest']['files']) and len(stage['files'])==466,
 'only_three_product_files_and_pins':set(stage['changed'])-pins==products,
 'all_other_selected_code_preserved':all(h==b['manifest']['files'][n] for n,h in stage['files'].items() if n not in products|pins),
 'working_changes_preserved':integration['protected_unchanged'] and integration['prompt_only_merge_preserved_working_ast'],
 'model_provider_profile_unchanged':all(stage['files'][n]==b['manifest']['files'][n] for n in ('00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json','00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')),
 'main115_before_promotion':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'zero_external_calls':work['external_model_calls']==0}
assert all(checks.values()),checks
result={'status':'complete','strict_success':True,'checks':checks,'candidate':f['candidate_revision'],'files':466,'changed_files':len(stage['changed']),'product_files_changed':3,'dependent_pins_changed':len(stage['changed'])-3,'technical_conditions':130,'working_conditions':130,'regression':reg,'external_model_calls':0,'quality_certified':False,'performance_certified':False,'genos_deployed':False,'known_case_diagnostic_excluded_from_eligibility':True,'evidence':{p.name:bind(p) for p in [ART/'check-final.json',ART/'check-working.json',ART/'regression-comparison.json',ART/'working-integration.json',DES/'release-rebase.json']}}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'integrated':{'status':'complete','technical_success':True,'quality_certified':False}},comparisons=[reg],judge_disagreements=[],usage={'external_model_calls':0},latency={'performance_claim':False},error_taxonomy=['Initial test harness: three public/internal response mismatch and five fixture ROOT failures; recheck storage reader absent on selected code. Test corrections only; candidate466 hashes unchanged.','Saved-render reader initially used public answer then assumed issue_sections; corrected to stored COMPOSE and ASSESS without source mutation.'],main_wiring='promotion-candidate',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[
('결정 요약','사용자 요청에 따라 MAIN115 누적 기능에 최종 프롬프트2곳과 일반 미확인 문구 제거를 통합한다. 이번 채택은 기술 계약과 서빙 결속에 관한 것이며 모델 품질 인증이 아니다.'),
('문제와 변경 전 구조','조사 중단 stop_reason만 있어도 material gap 없이 일반 미확인 문구가 추가됐다. 충분한 근거로 답변한 내용과 모순됐다. 별도로 읽은 원문의 적용 범위·조건을 claims에 유지하도록1192 프롬프트를 통합한다.'),
('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json). 구체 부족과 최종 검토 출력중단 경고는 유지하고 근거 없는 일반 문구만 제거한다. 모델·원문·권한·해시·스키마·예산·공급자·재시도는 동일하다.'),
('실험 설계','1190/switched와1192/scoped의 완료 분기를 통합했다. 알려진007 재생은 별도 인샘플 진단이며 승격 적격성 근거에 포함하지 않는다. 사전 합성 계약130개, 작업 코드 동일 계약130개와 기존211회귀 비교를 사용한다.'),
('데이터·모델·재현성','MAIN115 데이터 및 Qwen3.8 Parasail FP8·확정429만 NearAI1회·물리별 차감·40/1024/1800·개별180초·출력상한없음 유지. 새 외부모델0. 후보466파일과 실제 소비자 pin을 고정했다.'),
('결과',f"후보 고유130·작업130검사 통과. 회귀 결과 {reg['summary']} / 새회귀0. 466파일 중 제품3+pin{len(stage['changed'])-3}만 변경. [결과](artifacts/run-001/result.json)."),
('사례별 오류 분석','초기 검사122통과/8실패는 API와 내부응답 형식3개 및 fixture ROOT5개 오류였다. 재검사5통과/3실패는 후보에 없는 압축 리더 import 오류였다. 같은 제품으로 남은3개를 다시 통과했다. 실패 원본을 보존하며 제품·검증조건을 완화하지 않았다.'),
('비용·지연·회수 규모','새 모델0·새 모델 단계0. 실제 서비스 HEALTH·모의 전송은 별도 승격 후 확인한다. 이번 성능·비용·법률 품질 비교 없음.'),
('해석','stop_reason은 운영 이력이다. 미확보 자료의 증거가 아니므로 gap이 없으면 미확인 범위를 만들어 표시하지 않는다. 실제 material gap과 ASSESSMENT_OUTPUT_LIMIT 경고는 그대로 유지한다. 과거 저장 publication은 refresh 없이 기존 rendering을 검증한다.'),
('한계와 일반화 가능 범위','1193의 감독 공백/UNKNOWN은 해결되지 않았고007 전체미통과·009미실행을 유지한다. 새 최종 프롬프트의 일반 성능·속도·법률 의미 정확도는 미인증이다. GENOS 배포 없음. 다른 작업의 저장압축·온톨로지 후보를 이번 릴리스에 자동 승격하지 않는다.'),
('운영 결정·롤백 조건','final-answer-20261029-r1로 공식 승격하고 선택service의OFF/ON미설정/ON빈DB를 확인한다. working completion_execution의 journal_text 변경은 상수만 병합해 보존한다. 회귀 시 이전 parasail-primary-20261029-r1로 공식 rollback하고 장기 프로세스가 있으면 재시작한다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_1194: setup/freeze/check/recheck/recheck2/regression/saved_render/integrate/qualify/promote. 완료 결과를 덮어쓰지 않는다. `.venv/bin/python 06_TOOLS/COMMANDS/adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1194-final-answer-main-integration --final`')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 최종 답변 MAIN 통합\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 통합 검증\n\n[기준](../artifacts/design/criteria.json) · [결과](../artifacts/run-001/result.json). 외부모델0. 알려진 CM007 재생은 별도 진단으로만 기록한다.\n')
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'test-runtime' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Technical integration frozen evidence, scripts, tests and diagnostics','contains_raw_prompts_and_outputs':False} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('Qualified',len(stage['changed']),'changed files; external calls0')
