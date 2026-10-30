from common import *
import re
f=read(sorted(DES.glob('freeze-*.json'))[-1]);b=read(DES/'baseline.json');tech=read(ART/'check-qualified.json');work=read(ART/'check-working.json');reg=read(ART/'regression-comparison.json');s=read(DES/'staging-final.json');integration=read(ART/'working-integration.json')
pins={r['manifest'] for r in read(ROOT/f['code_root']/'00_SYSTEM/PIPELINE.json')['engines'].values()}|{'00_SYSTEM/PIPELINE.json'}
products=set(s['products']);assert len(products)==6
baseprofile=read(ROOT/b['manifest']['code_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile=read(ROOT/f['code_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
checks={'prospective_contracts_pass':tech['all_passed'],
 'working_contracts_pass':work['passed']==tech['unique_conditions'] and work['failed']==0 and not work['import_leaks'],
 'same_regression':not reg['status_differences'] and not reg['new_regressions'],
 'same466inventory':set(s['files'])==set(b['manifest']['files']) and len(s['files'])==466,
 'only_six_products_and_pins':set(s['changed'])-pins==products,
 'all_other_selected_code_preserved':all(h==b['manifest']['files'][n] for n,h in s['files'].items() if n not in products|pins),
 'working_changes_preserved':integration['protected_unchanged'] and integration['targeted_merge_preserved_unrelated_hunks'],
 'model_provider_unchanged':all(s['files'][n]==b['manifest']['files'][n] for n in ('00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')),
 'profile_only_presentation_changed':{k:v for k,v in baseprofile.items() if k!='answer_presentation'}=={k:v for k,v in profile.items() if k!='answer_presentation'},
 'main116_before_promotion':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'rollback_previous_reader_compatible':read(ART/'rollback-compatibility.json')['passed'],
 'zero_external_calls':work['external_model_calls']==0}
assert all(checks.values()),checks
result={'status':'complete','strict_success':True,'checks':checks,'candidate':f['candidate_revision'],'files':466,'changed_files':len(s['changed']),'product_files_changed':6,'dependent_pins_changed':len(s['changed'])-6,'technical_conditions':tech['unique_conditions'],'working_conditions':work['passed'],'regression':reg,'external_model_calls':0,'quality_certified':False,'performance_certified':False,'genos_deployed':False,'known_case_diagnostic_excluded_from_eligibility':True,'evidence':{p.name:bind(p) for p in [ART/'check-qualified.json',ART/'check-working.json',ART/'regression-comparison.json',ART/'working-integration.json',ART/'rollback-compatibility.json',DES/'release-rebase.json']}}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'preserved':{'status':'complete','technical_success':True,'quality_certified':False}},comparisons=[reg],judge_disagreements=[],usage={'external_model_calls':0},latency={'performance_claim':False},error_taxonomy=['Reservation relation typo rejected before creation; corrected informed_by.', 'Freeze metadata referenced previous arm; five preflight errors corrected without product change.', 'rev001 digest import missing: 31 failed/83 passed. rev002 fixes import; original snapshot preserved.', 'Native fixture used unsupported format HTTP field: six failures and two negatives not reaching product. Route format corrected, eight cases rechecked on same rev002.', 'Rollback fixture helper imports were made explicit; same frozen code verified12 cases with previous reader.', 'Recheck native fixture team t rejected before COMPOSE; test_team accepted; eight cases passed on same rev002.', 'Saved diagnostic initially searched different spacing for initial acquisition; exact original phrase count3 used; all complete claims already matched.'],main_wiring='promotion-candidate',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[
('결정 요약','검증된 ASSESS 내용을 최종 표시에서 잃지 않도록 accepted-content-v1을 선택한다. 서버가 기존 내용 컴파일러로 문단·목록·표를 조립하고 마지막 자유 서술 COMPOSE 모델 호출을 생략한다.'),
('문제와 변경 전 구조','MAIN116은 COMPOSE의 주장ID 포함만 검사했다. 이미 accepted_claims에 있는 적용 조건·수치 분모가 문장 재작성에서 사라져도 저장과 해시 검증은 통과했다. ASSESS 프롬프트 강화만으로 해결되지 않았다.'),
('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json). 서버가 의미를 다시 추론하지 않고 이미 판단한 내용을 표시하면 재작성 손실을 제거할 수 있다. 검색·원문·ASSESS 자체의 의미 누락을 해결했다고 확대하지 않는다.'),
('실험 설계','MAIN116을 정확한 기반으로 격리했다. 새로운 합성 조건·예외·분모·기한 및 실제 native API로 보존·변조·오류·복구·재개·중복을 검사했다. 기존211회귀를 동일 코드별로 비교했다. 저장 CM007은 별도 인샘플 진단이며 승격 적격성 근거에서 제외한다.'),
('데이터·모델·재현성','같은466서빙파일·동일 데이터/모델/Parasail→확정429 NearAI 정책·40/1024/1800·개별180초·출력상한없음·온톨로지기본OFF. profile의 answer_presentation만 변경. 외부모델0. 레거시 grounded-narrative-v1의 저장·명시 프로필은 유지한다.'),
('결과',f"후보 고유{tech['unique_conditions']}·작업{work['passed']} 계약 통과. {reg['summary']} 새회귀0. 제품/설정6+pin{len(s['changed'])-6} 변경. [결과](artifacts/run-001/result.json)."),
('사례별 오류 분석','최초rev001의 canonical digest import 누락은 수정본rev002로 보완했다. API fixture의 unsupported format 필드를 기존 route command.format으로 옮기고 음성 검사가 실제 COMPOSE 변조 경로에 도달하도록 보강했다. 원본 실패/동결 후보/재검사를 모두 보존한다. 저장 진단의 문구 오기는 별도 정정했다.'),
('비용·지연·회수 규모','새 모델0. 새 경로는 자유 서술용 COMPOSE 호출과 그 형식 보완을 사용하지 않는다. 실제 전체 요청 비용·응답시간 개선률은 측정하지 않았다. 생성 중 토큰 대신 검증된 최종 응답을 반환하고 기존 workflow finish가 이를 표시한다.'),
('해석','claim의 검증된 content/text를 재컴파일 대조하고 ASSESS 해시에 결속한다. plan에 임의 text/paragraphs를 넣거나 claim을 누락·중복하면 거절한다. 원문 반환 전용·선택된 시나리오·별도 workflow task는 기존 전용 경로를 보존한다. 이전 저장 답변을 소급 변경하지 않는다.'),
('한계와 일반화 가능 범위','구조화된 ASSESS가 잘못 판단하거나 처음부터 필요한 내용을 누락하면 이 변경이 정답으로 고치지 않는다. FINAL_REVIEW_SKIPPED/UNREVIEWED와 quality_certified=false 유지. 자유로운 재서술은 줄며 완전한 내용을 표시하므로 답변은 길어질 수 있다. CM007 새 실모델 재시험0·CM0090·GENOS 배포0.'),
('운영 결정·롤백 조건','작업의 기존 압축 리더 등 관련 없는 변경을 hunk 단위로 보존하고 accepted-answer-20261029-r1을 공식 승격한다. 실제 선택service OFF/ON미설정/ON빈DB를 후속 확인한다. 문제가 있으면 공식 rollback으로 이전 final-answer-20261029-r1을 선택한다. 장기 프로세스는 새 binding 재시작이 필요하다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_1196의 setup/implement/freeze/check/recheck/regression/compare/saved_render/integrate/qualify/promote. 완료 산출물을 덮어쓰지 않는다. `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1196-accepted-answer-preservation --final`.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 검증한 답변 내용의 최종 표시 보존\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n[기준](../artifacts/design/criteria.json) · [결과](../artifacts/run-001/result.json). 외부모델0. 알려진 CM007은 별도 저장 재생 진단이다.\n')
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'test-runtime' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Technical frozen evidence, tests, diagnostics and targeted working integration','contains_raw_prompts_and_outputs':False} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('Qualified',len(s['changed']),'changed files; external calls0')
