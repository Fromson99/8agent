from common import *
import re
f=read(DES/'freeze-rev-001.json');b=read(DES/'baseline.json')
tech=read(ART/'check-rev-001.json');work=read(ART/'check-working.json')
integration=read(ART/'working-integration.json');stage=read(DES/'staging-final.json')
pins={r['manifest'] for r in read(ROOT/f['code_root']/'00_SYSTEM/PIPELINE.json')['engines'].values()}|{'00_SYSTEM/PIPELINE.json'}
config='00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'
checks={
 'candidate_routing41':tech['passed']==41 and tech['failed']==0,
 'working_routing41':work['passed']==41 and work['failed']==0,
 'no_import_leaks':not tech['import_leaks'] and not work['import_leaks'],
 'same_466_file_inventory':set(stage['files'])==set(b['manifest']['files']) and len(stage['files'])==466,
 'only_provider_config_and_pins_changed':all(n==config or n in pins for n in stage['changed']),
 'all_application_code_unchanged':all(h==b['manifest']['files'][n] for n,h in stage['files'].items() if n!=config and n not in pins),
 'working_changes_preserved':integration['protected_unchanged'],
 'same_model_policy':stage['files']['00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']==b['manifest']['files']['00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'],
 'same_research_client':sha(ROOT/b['research_client']['path'])==b['research_client']['sha256'],
 'main114_before_promotion':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'zero_external_calls':tech['external_model_calls']==work['external_model_calls']==0,
}
assert all(checks.values()),checks
result={'status':'complete','strict_success':True,'checks':checks,'candidate':f['candidate_revision'],
 'files':466,'changed_files':len(stage['changed']),'configuration_files_changed':1,
 'dependent_pins_changed':len(stage['changed'])-1,'technical_conditions':41,'working_conditions':41,
 'external_model_calls':0,'quality_certified':False,'performance_certified':False,'genos_deployed':False,
 'full_regression_rerun':False,'full_regression_reason':'All application code identical to MAIN114; targeted existing provider and API contracts run on candidate and working code',
 'evidence':{p.name:bind(p) for p in [ART/'check-rev-001.json',ART/'check-working.json',ART/'working-integration.json',DES/'release-rebase.json']}}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'switched':{'status':'complete','technical_success':True,'quality_certified':False}},
 comparisons=[],judge_disagreements=[],usage={'external_model_calls':0},
 latency={'performance_claim':False,'reason':'No live provider comparison'},error_taxonomy=[],
 main_wiring='promotion-candidate',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:
 meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[
 ('결정 요약','사용자 요청으로 기본 공급자를 Parasail FP8로 변경하는 설정을 기술 검증했다. 확정429에만 Near AI FP8 1회 전환하며 실제 MAIN 선택은 별도 승격 영수증으로 기록한다. 속도·응답 품질 개선 인증이 아니다.'),
 ('문제와 변경 전 구조','MAIN114와 신규 실험은 Chutes 우선이었다. 사용자가 Parasail 복귀를 요청했다. 실제 서빙은 선택 릴리스의 설정을 읽으므로 작업 설정만 고치지 않고 검증한 설정을 별도 릴리스로 연결한다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). 기본 Parasail, 확정429만 Near AI 1회, 물리 호출별 차감, 응답불명/다른HTTP/잘못된형식/모델/공급자에서 전환 금지. 나머지 코드·데이터·모델·예산 보존.'),
 ('실험 설계','MAIN114의466파일을 격리 복사해 공급자 설정1개와 종속pin25개만 변경했다. 기존 공급자 계약 검사의 예상 기본 공급자만 변경하여 후보41·작업41검사를 수행했다. 라이브 모델 비교는 없다.'),
 ('데이터·모델·재현성','모델 Qwen3.8 FP8, reasoning none, 출력 상한 없음, 40/1024/1800 예산, 요청당 최대180초 기한을 보존한다. 데이터 변경0. 동결 파일과 runner SHA256을 manifest에 결속했다.'),
 ('결과','후보41·작업41검사 통과, import 누출0. 원문·요구검토·기한·전송 구현을 포함한 모든 애플리케이션 코드는 MAIN114와 동일하다. 신규 모델0. [결과](artifacts/run-001/result.json).'),
 ('사례별 오류 분석','기존 합성 오류 주입에서 확정429만 전환, 두 번째429 중단, UNKNOWN 무재시도, 잘못된 모델/공급자/형식 거절, 재개 시 전환상태·예산 보존, 실제 모의 API 호출을 검증했다. 기존 CM007 실패와 CM009 미실행 기록은 보존했다.'),
 ('비용·지연·회수 규모','외부 모델 호출0·외부 토큰0. 실제 비용·p50/p95·법률 품질·회수율은 측정하지 않았다. 코드 변경이 없어 전체211회귀는 재실행하지 않고 공급자 관련 기존 검사만 수행했다.'),
 ('해석','기본 공급자 변경이 실제 전송 설정에 도달하도록 기술 결속한다. Parasail이 Chutes보다 빠르거나 안정적이라는 결론은 낼 수 없다. 전환 조건과 검증 로직을 완화하지 않았다.'),
 ('한계와 일반화 가능 범위','Parasail 실통신·속도 비교·CM007/009·GENOS 현장 배포는 수행하지 않았다. 이번 검증은 공급자 설정 및 기존 코드 계약을 대상으로 하며 새 모델 성능 검증과 다르다.'),
 ('운영 결정·롤백 조건','검증한466파일을 parasail-primary-20261029-r1로 공식 승격하고 실제 선택 서비스 HEALTH/모의 전송을 확인한다. 작업의 기존 저장 압축 등은 보존했다. 실패 시 직전 requirement-coverage-20261029-r1로 공식 롤백하고 서비스를 재시작한다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1190의 setup/freeze/check/integrate/working_check/qualify/promote. 완료 산출물을 덮어쓰지 않는다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1190-parasail-primary-routing --final`'),
]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 기본 공급자 Parasail 복귀\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 공급자 기술 검증\n\n질문별 법률 평가 없음. 합성 라우팅·오류·예산·재개/API 계약의 후보41·작업41검사 통과. 신규 모델0. [결과](../artifacts/run-001/result.json).\n')
a=read(ART/'manifest.json')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'test-runtime' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
 'description':'Prospective routing configuration, frozen inventory, test results or runner',
 'contains_raw_prompts_and_outputs':False} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('Qualified',len(stage['changed']),'changed files; model calls0')
