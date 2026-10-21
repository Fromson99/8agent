from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0808-workflow-mechanical-boundaries'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(A/'artifacts/replay/result.json');count=int(re.findall(r'(\d+) passed',(A/'artifacts/frozen-tests.txt').read_text())[-1]);assert r['model_calls']==1
result={'status':'complete','technical_contracts_passed':count,'model_replay':r,'quality_certified':False,'decision_eligible':False,'main_changed':False,'genos_changed':False}
put(A/'artifacts/run-001/result.json',result);m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['design']['arms'][0]['changes']='Completed ADR0807/connected fixed recorded BASIS packet; actual prior full workflow partial/0 rows retained'
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Archived ADR0807 call23/24, no new baseline calls'},'connected':{'status':'complete','contracts':count,'canonical_valid':r['canonical_valid']}},usage={'product_model_calls':1,'offline_evaluator_calls':0},latency={'recorded_packet_seconds':r['elapsed_seconds']},error_taxonomy=[] if r['canonical_valid'] else [r.get('error_type','REPLAY_INVALID')])
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[f"Proposed. 동결 코드 {count}검사. 기존 실제 BASIS 입력 1회 재생의 정본 검증={r['canonical_valid']}. 전체 질의 재실행/정답률 평가와 구분한다.",
 '종료 시 미사용 조사 배열, 행동별 gap_ids 필수 조건 누락, 근거 ID 자리에 문서 이름을 쓰는 출력이 수정 호출을 소비했다. 추가 조사에서는 사용자 사실의 인용 검증 대상이 생성된 추가 질문으로 바뀌었다.',
 '수정 전 criteria.json. 행동별 필수 필드는 같은 행동의 대체 형식 간 교집합/다른 행동 간 합집합으로 보존한다. 사용하지 않는 배열만 초기화하고 정본 전체 재검증. 원문·권한·해시·상태/의미 판단을 추정하지 않는다.',
 '완료 ADR0807/connected에서 분기. SOURCE/CLAIM 검색 변경 없음. 한 기록된 BASIS 입력의 정확 인용 선택지를 복원해 새 스키마로1회 호출한다. 채점 모델/제품 정답 주입 없음.',
 'Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음. ExperimentClient 최대1호출/180초. 입력 기록 해시·후보338파일·리플레이 스크립트/모델은 design/freeze.json과 replay/binding.json.',
 f"계약 {count}검사 통과. 실제 모델 재생1호출/{r['elapsed_seconds']:.2f}초, 정본 검증={r['canonical_valid']}, 짝={r.get('pairs')}, 부족={r.get('gaps')}. 전체 실제 질의의 직전 결과는 ADR0807 24호출/partial/0행이며 재시작9검사 통과다.",
 '근거/쟁점/명시 참조 끝점은 현재 제시된 ID만 선택한다. 없는 쪽의 짝은 만들 수 없다. 새 질문 인용을 복사하지 않으며 원 사용자 사실에 결속한다. 미사용 배열 정리는 선택한 행동을 바꾸거나 원문 채택을 만들지 않는다. 정본/의미 검사 실패는 남긴다.',
 '원문 조사 없음. 동일한 과거 입력의 제시 원문만 사용하므로 회수 원장은 해당 없음이다. 실제 요청/응답/usage는 replay/raw에 보존한다. 속도·정확도 향상으로 일반화하지 않는다.',
 '시스템이 기계적 결속과 미사용 값 처리를 담당하고, 모델은 현재 제시된 의미 선택지만 결정한다. 공급자 형식과 정본 검증의 책임을 분리한다.',
 '알려진 기록의 재생이다. 전 구간 RAG 대사나 법률 정답 성공이 아니다. 별표10/필요 내규/적용 판본 확보 문제는 자동 해결했다고 주장하지 않는다.',
 'MAIN74 선택 포인터와 작업 코드는 아직 불변. 신규 기술 경계 자격검증 후 같은 후보를 통합·승격한다. GENOS 미반영. 이전 실패 이력 불변 보존.',
 '06_TOOLS/EXPERIMENTS/adr_0808: prepare.py → repin.py → adr_candidate freeze/validate → freeze.py → run_tests.py/replay_basis.py → close.py. 이 ADR에서는 live.py/account.py를 실행하지 않는다.']
meta=(A/'README.md').read_text().split('---',2)[1];(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0808 시스템 소유 처리 경계 보완\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n')
qh=['1. 실행 메타','2. 사용자 질문 원문','3. 기준답변 — 채점 전용, 제품 입력 비공개','4. 제품 입력을 구성한 원값','5. 제품 모델 호출 — run·arm별 실제 원문','6. 중간 LLM 호출 — router/compiler/verifier/repair','7. 채점 호출과 반복 판정','8. 사례 최종 판정'];qt=['K01 알려진 BASIS 기록1회, in_sample=true.',read(A/'artifacts/design/criteria.json')['known_observation']['question'],'승인된 법률 정답 없음. 정본 경계만 검증.','ADR0807 call23의 정확한 제시 원문과 범위. 새 회수 없음.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n해당 없음: 기록된 고정 입력 재생이며 실제 검색을 수행하지 않는다.','../artifacts/replay/raw의 실제 request/response/validation-schema, binding.json.','제품 모델1회. 추가 수정/자동 재실행0.','평가 모델0. 기술 계약은 별도.',texts[5]]
p=A/'실험/질문-001-K01.md';p.write_text('\n\n'.join('## '+h+'\n\n'+t for h,t in zip(qh,qt))+'\n');m['questions']=[{'number':1,'case_id':'K01','file':p.name,'sha256':sha(p)}];put(A/'실험/manifest.json',m);(A/'실험/README.md').write_text('# 고정 입력 재생\n\n[K01](질문-001-K01.md). 전 구간 정답 검증과 구분한다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0808','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code and recorded input replay evidence','contains_raw_prompts_and_outputs':'raw' in p.parts} for p in files]})
print('Final records prepared',count,r['canonical_valid'])
