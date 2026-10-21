"""Finalize deterministic integration without claiming new model trials."""
from common import *
import xml.etree.ElementTree as ET
m=read(ADR/'실험/manifest.json');assert m['reservation']['status']=='in_progress'
seal=read(ART/'stage.json');C=ROOT/seal['roots']['candidate'];delta=read(ART/'integration-delta.json')
assert all(sha(C/n)==h and sha(ROOT/n)==h for n,h in seal['files']['candidate'].items())
for n,h in delta['legal_agent_files'].items():assert sha(C/n)==h
f=read(ART/'design-freeze.json')
for key in ('script_bindings','test_bindings'):
 for n,h in f['design'][key].items():assert sha(ROOT/n)==h,n
ref=m['design']['inherited_model_outcomes'];assert sha(ROOT/ref['path'])==ref['sha256'];parent=read(ROOT/ref['path']);assert parent['strict_success']
assert all(x['pass'] for x in parent['by_arm']['candidate']) and all(x['successful_name_retry'] for x in parent['by_arm']['candidate'][:4])
suites=ET.parse(ART/'contracts-002.xml').getroot().findall('testsuite');count=sum(int(s.get('tests')) for s in suites)
assert count==260 and all(int(s.get('failures',0))==int(s.get('errors',0))==0 for s in suites)
for mode in ('candidate','working'):
 v=read(ART/f'consumer-{mode}.json');assert v['status']=='PASS' and all(v['checks'].values())
def binding(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
result={'strict_success':True,'checks':{'all260_final_contracts':True,'native_candidate_real_data':True,'native_working_real_data':True,'all418_working_staged_files_match':True,'unchanged_legal_agent_model_path':True,'parent_source_navigation8of8_retry4of4':True,'original_cache_compiler_exact':True,'frozen_scripts_tests_exact':True},
 'physical_model_calls':0,'inherited_model_outcomes':ref,'inherited_model_calls':parent['physical_model_calls'],'contracts':count,
 'consumers':{x:binding(ART/f'consumer-{x}.json') for x in ('candidate','working')},'excluded_legacy_schema':delta['preserved_unapplied_change'],
 'limits':['No new model calls; parent ADR0966 source-navigation outcomes inherited on exact legal-agent modules. Parent integration failed, not accepted wholesale.',
 'Synthetic baseline8/8 and candidate8/8; retry4/4. No accuracy or latency improvement established; candidate21 calls versus baseline20.',
 'Two unrelated legacy full-glossary schema changes excluded and preserved losslessly. All other current text-length changes remain. Legacy schema relaxation needs a separately compatible cache generation.',
 'Seven pre-recorded contract failures remain excluded, reproduced on pre-feature bytes. ADR0965 invalid fixture and ledger format errors remain preserved and excluded.',
 'Actual post-activation service binding is separately checked in promotion audit. No GENOS/internal model/Oracle deployment or legal quality certification.']}
save(ART/'result.json',result)
paragraphs=[
 'Accepted / promotion-candidate. 법령명 후보 선택 도구와 원래 조문 재조회를 통합하고 실제 데이터 원문 읽기까지 검증했다. 포인터 전환·활성 서비스 검증은 별도 감사 기록에 연결한다.',
 'ADR0966의 합성 모델 검증은 성공했으나 실제 데이터 세션에서 glossary compiler/cache hash 불일치가 확인됐다. 같은 파일의 미검증 legacy PLAN_SCHEMA·decision_schema 변경만 기존 캐시와 결속된 MAIN97 바이트로 유지한다. 변경 전 작업본은 무손실 압축·SHA로 보존했다. 무결성 검사를 약화하지 않았다.',
 m['design']['success_criteria'],
 '부모 ADR0966/candidate의8/8 원문 전달·4/4 이름 복구 기록만 상속한다. 부모의 실패한 전체 통합을 성공으로 재해석하지 않는다. 새 통합 후보의 법령명/조사/응답 legal_agent 모듈은 전부 같은 바이트다. 바뀐 기능 부분은 legacy 용어집 스키마2개이며 나머지 AST 노드는 같다. 이 스키마는 현재 v6/v8 source-navigation에서 호출되지 않는다.',
 '실제 local MAIN97의 데이터·모델 프로필·선택 색인을 유지했다. 외부 모델 새 호출0. 부모 Qwen3.8 Parasail FP8 reasoning none의41호출은 원시 입력/출력/usage와 함께 보존하며 새 호출로 계산하지 않는다. 후보·작업 real-data consumer는 직렬 실행, 프로세스 주소공간6GiB 한도다.',
 f'최종 후보260계약 통과, 기존7실패 제외. 후보·작업 코드 각각 service HEALTH200, 코스닥시장 상장지침 이름 후보 → 코스닥시장 상장규정 선택 → 원래 조문 재조회 → 권한 범위 내 원문 읽기 통과. 원문·데이터·프로필·helper 경로·418코드 해시 통과. 이름 후보 자체는 citation_eligible=false다.',
 '이번 결정적 통합 검사 실패0. 초기 ADR0965의 잘못된 합성 저장좌표·기록 형식 오류와 ADR0966 실제 데이터 캐시 해시 실패는 보존했다. 결과를 덮어쓰지 않고 별도 완료 기록으로 이어 왔다.',
 '모델0회 신규, 부모41회 상속. 260계약은 최종 후보에서 새로 실행했다. 실제 데이터 consumer의 peak RSS·모드·바인딩은 artifacts/consumer-candidate.json 및 consumer-working.json에 있다. 새 검색 효과 비교는 없으며 부모의 exact 단계 원장을 참조한다.',
 '기능 확인과 무결성 보존을 지지한다. 기준과 변경 모두8/8이므로 정확도 개선은 주장하지 않는다. 부모 후보의 호출·중앙 지연도 증가했으므로 속도 개선을 주장하지 않는다.',
 '\n\n'.join(result['limits']),
 '사용자 요청에 따라 stable prepare/apply --confirm-main으로 로컬 MAIN을 전환한다. 선택 서비스의 불일치·원문/권한/상태/해시 실패 시 이전 MAIN97로 복원한다. 품질 우회 없이 VALIDATED_ADR_PROMOTION을 사용하고 quality_certified=false를 유지한다. 현장 GENOS 배포·Git commit/push는 수행하지 않는다.',
 '06_TOOLS/EXPERIMENTS/adr_0967/{freeze,run_contracts,seal_release,consumer,finish}.py. 기존 호출을 재생성하지 않는다. .venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0967-law-name-main-integration --final 및 graph. [결과](artifacts/result.json), [통합](artifacts/integration.json), [정확418파일](artifacts/stage.json), [보존·복원](artifacts/integration-delta.json).'
]
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted').replace('main_wiring: unchanged','main_wiring: promotion-candidate')
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0967: 법령명 복구 통합과 실제 데이터 검증\n\n'+''.join(f'## {i}. {h}\n\n{p}\n\n' for i,(h,p) in enumerate(zip(heads,paragraphs),1)))
q=m['questions'][0];p=ADR/'실험'/q['file']
p.write_text('''# 최종 통합 소비자 검증

## 1. 실행 메타

ADR0967 / run-001 / integrated. 모델 신규 호출0, 최종 후보 계약과 실제 서비스 연결 검사.

## 2. 사용자 질문 원문

메인에 적용해봐 그리고 실험까지

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

260계약과418파일 검증, 부모 법령명 복구4/4의 모든 legal_agent 코드 동일, 실제 후보/작업 서비스에서 원문 읽기 성공. 법률 정답을 평가하는 사례가 아니다.

## 4. 제품 입력을 구성한 원값

정본은 [동결418파일](../artifacts/stage.json), [사전 기준](../artifacts/design-freeze.json), [통합 차이](../artifacts/integration-delta.json), [테스트 명령](../artifacts/contract-command.json).

### 회수·탈락 단계 원장 — run·arm별

새 회수 효과 비교 없음. 부모 ADR0966의 [선택 후 정확 원장](../../ADR-0966-law-name-bound-holdout/artifacts/retrieval-ledger.json)을 상속한다. 현재 회차는 캐시 호환성·상태·권한·서비스 연결 검증이다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

신규0회. 부모의 실제41호출은 [질문별 원시 기록](../../ADR-0966-law-name-bound-holdout/실험/README.md)에 있다. 신규 실행으로 집계하지 않는다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

없음. 소비자의 명시적 법령 선택은 결정적 연결 검사다. 모델의 후보 선택 능력은 부모의4/4 실제 호출에 근거한다.

## 7. 채점 호출과 반복 판정

모델 judge 없음. 해시·원문·스코프·계약을 결정적으로 검사한다. [260계약](../artifacts/contracts-002.xml), [후보](../artifacts/consumer-candidate.json), [작업](../artifacts/consumer-working.json).

## 8. 사례 최종 판정

통합 통과, 승격 후보 채택. [결과](../artifacts/result.json). 실제 활성 포인터와 비주입 서비스 선택 검사는 별도 승격 감사에서 수행하며 실패 시 복원한다. GENOS 검증은 아니다.
''');q['sha256']=sha(p)
(ADR/'실험/README.md').write_text(f'# ADR0967 통합 실행\n\n최종260계약과 실제 데이터 소비자 통과. 모델 신규0회; 부모 모델 결과는 별도8사례 기록으로 보존.\n\n- [최종 통합]({q["file"]})\n- [동결·결과·계보](manifest.json)\n')
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','source':'Parent source-navigation8/8; parent cache failure preserved'},'integrated':{'status':'complete','strict_success':True,'contracts':count}},comparisons=[],judge_disagreements=0,usage={'model_calls':0,'inherited_model_calls':41},latency={},error_taxonomy=['Seven pre-existing excluded failures','Legacy glossary schemas preserved outside current integration'])
save(ADR/'실험/manifest.json',m)
files=[]
for p in sorted(ART.rglob('*')):
 if not p.is_file() or p==ART/'manifest.json' or any(x=='code' or x.startswith('runtime-') for x in p.relative_to(ART).parts):continue
 files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Final integration evidence or preserved prior work','contains_raw_prompts_and_outputs':False})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':files})
print('Accepted integration evidence assembled; validate before completing reservation')
