from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0850-minimal-output-qualification';D=A/'artifacts/design';O=A/'artifacts/run-001'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');metrics=read(O/'measurements.json');log=(A/'artifacts/candidate-tests.log').read_text();base=(A/'artifacts/baseline-existing-failure.log').read_text()
failure='test_gateway_workflow_calls_internal_interpreter_without_legal_bootstrap'
checks={'frozen_inputs':all(sha(R/n)==h for n,h in f['files'].items()),
 'all17_new_boundaries_pass':not any('FAILED '+str(p.relative_to(R)) in log for p in (R/'06_TOOLS/EXPERIMENTS/adr_0850').glob('test_*.py')),
 '164_pass_one_unchanged_baseline_failure':'1 failed, 164 passed' in log and failure in log and failure in base and "KeyError: 'ad_mode'" in log and "KeyError: 'ad_mode'" in base,
 'schema_and_roundtrip':metrics['strict_success'],
 'working_still_baseline':all((sha(R/n) if (R/n).exists() else None)==h for n,h in read(D/'working-rebased-before.json').items()),
 'MAIN_untouched_by_this_task':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline-rebased.json')['pointer_sha256']}
limits=['No actual LLM calls, output-token or GENOS latency/quality measurement.',
 'Navigation synthetic response remained 221 bytes: the prior projection already removed these host fields. The measured 67–94% saving concerns the generation schema, not response text.',
 'The unrelated AD workflow interception fixture fails identically before and after this change (KeyError ad_mode); it remains visible and is not called a passing test.',
 'Legacy TurnDecision/SourceSelectionDecision preserve their partial-operation consumers without fixed-field elision. Scoped/reference schemas stay conservative. Final text/citations are never truncated.',
 'Working integration does not change selected MAIN81, deploy GENOS or certify that the photographed timeout is resolved.']
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'tests_passed':164,'new_boundary_tests':17,
 'unchanged_baseline_failures':[failure],'model_calls':0,'measurements':metrics['cases'],
 'qualification':'finite component and consumer contracts; no new observed regression', 'quality_certified':False,'limitations':limits}
put(O/'result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','existing_failure':failure,'basis':'retained original contract tests plus exact current working baseline reproduction'},
 'qualified':{'status':'complete','passed':164,'new_boundary_tests':17,'existing_failure':failure}},comparisons=[],
 usage={'product_model_calls':0,'offline_evaluator_calls':0},latency={},error_taxonomy=['preexisting: AD workflow interception fixture missing ad_mode'])
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Accepted for working-code integration. 최소 응답 복원과 기존 복구·참조·부분 성공 경계를 검증했다. 활성 릴리스와 GENOS는 변경하지 않는다.',
 '모델에 반복된 행동별 전체 JSON과 시스템이 정할 값을 보내던 부분을 공통 projection으로 분리. 정확 중복 보정은 복원 전에 적용하고, 번호 참조는 복원된 전체 schema로 해독한다.',
 read(D/'criteria.json')['hypothesis'],
 '고정값 생략/일치/충돌×원문 수0/1/3=9, 구형 부분 성공 계약2×정상/부분=4, 중복 보정 설정2, 전송 상태2의 총17개 신규 경계. 기존 회귀148개를 같은 코드에서 실행. 모델 대신 모의 HTTP/SSE를 사용했다.',
 '후보 rebased/rev-001과 runner/test hash는 design/freeze.json. 동시 작업 ADR0849의 근거 연결 기능을 보존한 새 snapshot. 실제 제품·평가 모델 호출0.',
 json.dumps(result,ensure_ascii=False,indent=2),
 '전체165개 중164통과, AD workflow 기존 fixture1실패. 수정 전 working baseline에서도 같은 KeyError를 재현했다. 초기 잘못된 fixture와 freeze 실패도 artifacts에 보존했다.',
 '행동1개5198→1726B, 4개10601→1289B, 12개24988→1499B. 같은 navigation 응답221B는 변화 없음. 토큰/실제 생성시간 미측정.',
 '알 수 있는 상수와 inactive empty fields는 서버가 채운다. 실제 판단과 간결한 이유, 의견·미확인 사항·정확 인용은 모델에서 받고 canonical/권한/상태 검사는 유지한다.',
 '\n'.join(limits),
 '검증된7개 구현 파일의 delta만 working에 적용하고 engine/PIPELINE 해시를 연결한다. 이전 bytes를 보존하며 동시 변경이 있으면 중단한다. 선택 포인터는 갱신하지 않는다.',
 'setup.py → rebase.py → repin/adr_candidate refresh·freeze → freeze.py → measure.py → run_tests.py → baseline failure reproduction → report.py → final validate/graph → integrate.py → same working tests.']
meta=(A/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted' if result['strict_success'] else 'Rejected'),('in_sample','false'),('decision_eligible','true'),('main_wiring','unchanged')]:meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 최소 출력과 소비자 호환성\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
for q in m['questions']:
 p=A/'실험'/q['file'];p.write_text('# 최소 출력의 유한 경계\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate([
 ('실행 메타','ADR-0850 / run-001 / baseline, qualified. 합성 입력 exact. 실제 모델 호출 없음.'),
 ('사용자 질문 원문','필요한 판단만 받고 시스템이 JSON의 확정 가능한 값을 조립한다.'),
 ('기준답변 — 채점 전용, 제품 입력 비공개','법률 정답 없음. 고정값·번호 참조 복원/기존 부분 성공/동일 오류 계약을 그대로 유지해야 한다.'),
 ('제품 입력을 구성한 원값','test_boundaries.py와 ADR0848의 두 테스트 파일. 원값·모의 전송은 해당 파일에 보존. hash는 design/freeze.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n해당 없음: 검색 정책을 바꾸지 않는 소프트웨어 계약 검사.'),
 ('제품 모델 호출 — run·arm별 실제 원문','모델0회. 모의 HTTP/SSE body와 문자열은 고정한 테스트에 보존. 소프트웨어 검사 결과는 artifacts/candidate-tests.log.'),
 ('중간 LLM 호출 — router/compiler/verifier/repair','[] — 모의 응답을 사용하는 기존 복구 검사만 수행. 실제 호출 없음.'),
 ('채점 호출과 반복 판정','[] — 모델 채점 없음. JSON 일치, raw 보존, 호출 예산, 기존 소비자/서비스 API 검사.'),
 ('사례 최종 판정','신규17경계와 회귀147개 통과. 기존 AD workflow fixture1개는 baseline에서도 동일 실패. schema 바이트 감소는 합성 구조에 한정. 결정은 README와 result.json 참조.')],1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 유한 소프트웨어 경계 검증\n\n17개 신규 경계와148개 회귀를 검사했다. 기존 실패는 baseline과 함께 보존했다. 모델 품질 평가가 아니다.\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','final-validation.txt','graph-final.txt')]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0850','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen technical contracts, unchanged baseline failure and measurements','contains_raw_prompts_and_outputs':False} for p in paths]})
print(json.dumps(checks));assert all(checks.values())
