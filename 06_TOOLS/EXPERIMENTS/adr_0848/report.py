from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0848-minimal-model-output'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(A/'artifacts/design/freeze.json');measured=read(A/'artifacts/run-001/measurements.json')
checks={'frozen_inputs':all(sha(R/n)==h for n,h in f['files'].items()),
 'technical_tests_121':'121 passed' in (A/'artifacts/candidate-tests.log').read_text(),
 'schema_and_roundtrip':measured['strict_success'],
 'MAIN81_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(A/'artifacts/design/baseline.json')['pointer_sha256']}
limits=['No actual LLM calls, legal accuracy or GENOS latency measurement.',
 'Response byte fixture retained optional host fields while baseline omitted them; its 221/249 comparison is not a valid generated-output reduction estimate. Preserve and supersede in a follow-up measurement.',
 'Review found early schema validation must preserve existing exact-duplicate normalization and partial-operation consumers; reference decoding must use reconstructed canonical schema. Follow-up required before working integration.',
 'Schema counts are synthetic shapes, not the photographed 78856-byte request replay.']
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'model_calls':0,
 'tests_passed':121,'measurements':measured['cases'],'ready_for_integration':False,'limitations':limits}
put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'same synthetic original schemas; no model generation'},
 'compact':{'status':'complete','tests_passed':121,'integration_eligible':False}},comparisons=[],
 usage={'product_model_calls':0,'offline_evaluator_calls':0},latency={},error_taxonomy=['review: normalization/partial-consumer ordering','measurement: generated-output size not comparable'])
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. 탐색 구현과 측정 완료. 후속 호환성 검증 전 작업 코드·MAIN 반영 보류.',
 'RAG·대사 gateway와 AD·구축 호출의 반복 스키마/고정 JSON 출력을 공통 projection으로 이동.',
 read(A/'artifacts/design/criteria.json')['hypothesis'],
 '동일한 실제 navigation schema 생성기로 행동 1·4·12개를 생성했다. JSON 복원·실패·재개·스트리밍과 실제 서비스 API를 모의 모델로 검사했다.',
 'candidate revision과 runner/test 입력은 design/freeze.json에 고정. 실제 제품/evaluator 모델 호출은 0회.',
 json.dumps(result,ensure_ascii=False,indent=2), '\n'.join(limits),
 '스키마 UTF-8 바이트만 측정했다. 실제 토큰·모델 출력 길이·LLM 지연·현장 busy 여부는 미측정.',
 '시스템 상수 복원과 행동 분기 축약은 가능하다. 의미 판단·인용·최종 답변은 코드가 추정하지 않는다.',
 '\n'.join(limits),'완료된 probe는 운영 채택 근거가 아니다. 후속 유한 계약 검증 후 선택적 코드 통합. GENOS 배포 별도.',
 'freeze.py → measure.py → run_tests.py(artifacts/candidate-tests.log 대상) → report.py → adr_structure.py status/validate --final/graph']
meta=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+meta+'---\n\n# 최소 모델 출력 탐색\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
for q in m['questions']:
 p=A/'실험'/q['file'];p.write_text(f"# {q['case_id']} — 유한 소프트웨어 계약\n\n"+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate([
 ('실행 메타','ADR-0848 / run-001 / baseline, compact. 합성 입력 exact. 실제 모델 호출 없음.'),
 ('사용자 질문 원문','시스템이 확정 가능한 필드는 모델 대신 JSON에 조립하고 필요한 판단만 받는다.'),
 ('기준답변 — 채점 전용','법률 정답 없음. 기존 canonical JSON과 정확 일치해야 한다.'),
 ('제품 입력을 구성한 원값','06_TOOLS/EXPERIMENTS/adr_0848/test_minimal_output.py와 test_gateway_minimal.py. frozen hash는 design/freeze.json. 원문 검색 없음.'),
 ('제품 모델 호출 — run·arm별 실제 원문','실제 모델 호출 0. 모의 HTTP·SSE 원응답은 테스트 파일에 그대로 보존. 측정은 run-001/measurements.json.'),
 ('중간 LLM 호출','[] — 없음. 복원 자체는 추가 호출하지 않는다.'),
 ('채점 호출과 반복 판정','[] — evaluator 호출 없음. JSON 동등성과 기존 API 결과로 검사.'),
 ('사례 최종 판정','121개 계약 통과. 후속 수정이 필요한 경계와 출력 바이트 측정 한계는 README 및 run-001/result.json에 보존.')],1))+'\n')
 q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 최소 응답의 복원 계약\n\n모든 테스트는 모의 전송이며 실제 모델 성능 검증이 아니다. 입력·runner·candidate hash는 design/freeze.json에 고정했다.\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','final-validation.txt','graph-final.txt')]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0848','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Prospective synthetic contracts and review limits','contains_raw_prompts_and_outputs':False} for p in paths]})
print(json.dumps(checks));assert all(checks.values())
