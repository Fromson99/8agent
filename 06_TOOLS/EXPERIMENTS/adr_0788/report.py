from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0788-navigation-finish-delivery-recovery'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(A/'artifacts/run-001/result.json');assert r['strict_success']
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm=r['by_arm'],comparisons=[],judge_disagreements=0,usage=r['usage'],latency={'kind':'Durable raw live calls contain measured usage and latency; synthetic tests are host contracts'},error_taxonomy=[])
put(A/'실험/manifest.json',m)
live={arm:[{'case':c['case'],'valid':c['valid'],'next_action':c.get('proposal',{}).get('next_action'),'error':c['error']} for c in v['cases']] for arm,v in r['live'].items()}
parts=[('결정 요약','Accepted promotion-candidate. 채택 없는 FINISH 충돌에 구체 교정 계약을 제공하고, 정상 응답으로 확인된 원문 전달 기록을 제안 승인과 분리한다. 한 쟁점 보류가 다른 쟁점의 채택을 취소한다고 오인하던 검증도 실제 저장 규칙과 맞췄다.'),
 ('문제와 변경 전 구조','현장 사진은 OUTPUT_LENGTH가 아니라 FINISH+DEFER→no adopted originals→교정 반복→SOURCE_INVESTIGATION_INCOMPLETE였다. 첫 원문은 모델에 전달됐지만 결정 검증 실패로 basis_history가 비어 fallback도 실패했다. 원래 현장 질문과 전체 입출력은 없어 보류 판단의 의미적 원인은 확정하지 않는다.'),
 ('가설과 사전 판정 기준','원문 전달과 채택을 분리하면 잘못된 결정을 실행하지 않고도 기존 ASSESS가 확인된 원문을 재검토할 수 있다. 5버전×2기존채택×5변경상태×2쟁점의100상태, 권한/해시/원문/상태/예산/중복/API 검사를 사전 지정했다. 구조·무결성·필수회귀 실패는 승격 차단; 모델 의미 판단은 별도 기록한다.'),
 ('실험 설계','MAIN66을 정확한 기준으로 하고 후보를 독립 snapshot에 고정했다. 기준/후보는 별도 프로세스와 실제 native API를 사용한다. JSON 스키마는 구조를 보장하고, 상태 의존 종료 조건은 실행 검증기가 검사한다. 생성 문법만으로 의미 일관성을 보장한다고 주장하지 않는다.'),
 ('데이터·모델·재현성','공개로 간주 가능한 새 합성 승인 규정만 외부로 보냈다. 실제 내부 질문·문서·사진은 반출하지 않았다. Qwen3.8/Parasail FP8/reasoning none/no fallback 공통 ExperimentClient를 사용했다. 유한 기술 계약의 전수검사이며 미사용 법률 질문 holdout의 증명이 아니다.'),
 ('결과',f"기준 공통 검사 {r['by_arm']['baseline']['passed']}/{r['by_arm']['baseline']['total']}, 후보 필수 회귀 {r['contracts_passed']}/{r['by_arm']['recovery']['total']} 통과. 합성 실제 모델4회 관찰: "+json.dumps(live,ensure_ascii=False)),
 ('사례별 오류 분석','수정 성공과 반복 충돌 및 JSON 오류 모두 API에서 검증된 답변 확정까지 연결한다. 보류·제외가 승인된 원문은 fallback에서 제외한다. length/필터/응답 모델 불일치/전송 결과 불명은 확인된 전달 기록이 없으며 답변 성공으로 위장하지 않는다. 개발 중 v2/v5 범위 fixture, 저널 열 이름, v8 source_ref fixture, 재사용 통계와 저널 선택을 정정했으며 기록을 보존했다.'),
 ('비용·지연·회수 규모','교정 횟수는 기존1회이며 요청 전체 예산/deadline/실패 이력을 유지한다. 원문 전달 확인은 해시와 기존 model_view/attempt에 연결한 작은 event로 남기며 별도 채택이 아니다. 정상 원문·검색·모델·6400/12800 길이 정책은 같다. 원문을 잃지 않은 실패에서는 기존 ASSESS가 실행되므로 이전 즉시실패 대비 판단 호출 비용이 생긴다.'),
 ('해석','모델의 틀린 제안을 완전히 방지하는 주장이 아니다. 충돌에 정확한 교정 선택지를 제공하고, 교정이 실패해도 실제 받은 원문의 검증·충분성 판단 경로를 복구한다. 근거 부족은 유지한다. 다른 쟁점의 명시 채택이 남아 있으면 일부 보류 후에도 기존 채택 원문으로 종료할 수 있다.'),
 ('한계와 일반화 가능 범위','GENOS 내부 모델·리비전에는 접근하지 않았고 현장 배포하지 않았다. 정상 완료 응답만 입력 전달의 근거로 사용하므로 timeout/length/필터에서는 보수적으로 보존하지 않는다. 모델이 원문을 이해했는지는 인증하지 않는다. 최종 ASSESS도 실패하면 실패 상태를 유지한다. 별도 사실 질문/취소/부분 도메인 저장 경로 전체 구현을 뜻하지 않는다.'),
 ('운영 결정·롤백 조건','사용자가 MAIN 즉시 반영을 명시 승인했다. 완료 ADR의 동일 동결 코드로 prepare/apply --confirm-main 후 선택 포인터와 service.service binding을 확인한다. 관련7소스만 기존 작업에 통합하고 다른 작업 변경은 보존한다. 기준 MAIN66을 표준 rollback 대상으로 유지한다. 로컬 MAIN과 GENOS 반입·배포는 별도다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0788/{prepare,freeze,audit,report,prepare_promotion,verify_active}.py. stable adr_structure validate --final, graph, rag_main_promotion prepare/apply. 완료 실험이나 기록을 덮어쓰지 않는다.')]
meta=f"---\nadr_id: ADR-0788\ntitle: 원문 미채택 종료 충돌과 전달 기록 복구 통합\nstatus: Accepted\ndecision_date: 2026-10-15\nphase: audit\nin_sample: false\ndecision_eligible: true\nmain_wiring: promotion-candidate\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 종료·전달 복구 검사\n\n합성 기술 계약 전수검사와 실제 모델4회 보조 관찰. 상세 ../artifacts/run-001/result.json.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0788','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen completion and delivery qualification evidence','contains_raw_prompts_and_outputs':'raw' in p.parts} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
