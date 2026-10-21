from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0779-tool-recovery-main'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[],judge_disagreements=0,usage=result['usage'],latency={'kind':'Synthetic host contract audit; model latency unmeasured'},error_taxonomy=[]);put(A/'실험/manifest.json',m)
parts=[('결정 요약','Accepted promotion-candidate. 도구 실패 P1~P3와 앞서 개발한 원문 subtree·의존 조사·도구 노출 수정을 동일 코드로 묶었다. 선택 원문/모델/검색 설정은 보존한다.'),
('문제와 변경 전 구조','MAIN62에는 최근 작업 코드의 구조 부모 읽기·도구 가용성·도구 원인/receipt 계약이 아직 없다. 이번 ADR은 기존 구현을 바꾸지 않고 사전 동결한 새 유한 계약 행렬과 기존 회귀로 승격 가능 여부를 검사했다. 이미 알려진 개발 검사 결과를 새 holdout이라고 부르지 않는다.'),
('가설과 사전 판정 기준','37개 선택 항목 × 9종 원인 × 3종 예외 연결 × 6종 상태=5994개 공통 정책 계약 전부 통과가 기준이다. 과거 842개 정상 검사 통과와 동일 4개 기존 실패만 허용하며 새 실패/누락/코드 drift는 승격 차단이다.'),
('실험 설계','기준 MAIN62와 동결 후보를 별도 프로세스로 확인했다. 기준에는 typed 계약 모듈이 없어 미지원으로 기록했으며 0점 정답률로 만들지 않았다. 후보는 상태/원인/예산과 원래 담당의 보존을 검사한다. 개별 도구 handler의 모든 경우나 법률 답변 품질 전수 검사를 주장하지 않는다.'),
('데이터·모델·재현성','306개 서빙 파일, 기존 회귀 소스, 테스트 runner, WORKSPACE/모델 정책과 원문 세대 포인터를 동결했다. 실제 모델 호출0. 내부 질문/원문은 외부로 전송하지 않았다. 연구 snapshot은 운영에서 자동 선택되지 않는다.'),
('결과','공통 정책5994/5994 통과. 동결 후보의 기존 검사842통과·4기존실패. semantic_runtime 모듈은 모두 후보에서 import됨을 확인했다. 실패4개는 결과 불명 재실행 기대, 구 PIPELINE schema, 공개 내부run_id 기대, v5 기본값 기대이며 해결된 문제로 계산하지 않는다.'),
('사례별 오류 분석','사진의 자체 원문 없는 구조 부모는 같은 source의 실제 자식 원문 subtree로 읽는다. 원문 없는 DEPENDENCY와 틀린 인용은 교정 또는 명시 중단하며 원인을 보존한다. 실패한 도구를 원문 부재/성공 관측으로 바꾸지 않는다. 동일 실패 대상은 반복하지 않고 같은 도구의 다른 유효 대상은 기존 예산 안에서 허용한다.'),
('비용·지연·회수 규모','실제 모델/토큰0. 같은 도구 자동 retry0, 기존 단일 교정 담당과 예산/deadline을 유지한다. 원문 검색 정확도·실제 내부 모델 속도와 오류 빈도는 미측정이다.'),
('해석','이 결과는 유한 host 계약과 실제 합성 API 경계의 검증이다. 기존 허용 제안·원문·인용·권한·상태·발행 검증을 없애서 성공 처리하지 않는다.'),
('한계와 일반화 가능 범위','finish_reason=length 자체 해소·모든 의미 판단 성공·GENOS 현장 성공은 미확인이다. 후속 사실 질문 terminal/사건 부분 변경 멱등 receipt/취소 전달 관리는 미구현이며 출력 압축은 보류다. 기존 4실패도 미해결이다.'),
('운영 결정·롤백 조건','사용자 “메인에 반영하고 삼성으로 메일쏴줘”에 따라 현재 검증 결과의 qualified prepare/apply --confirm-main을 수행한다. MAIN62는 그대로 보존한다. 회귀 시 표준 rollback으로 이전 코드/데이터에 새 generation을 부여한다. GENOS 패치는 기존 DEV 적용과 같은 checkout의 generation gate, 새 리비전 및 workflow 테스트를 별도로 요구한다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0779/{prepare,freeze,audit,report,prepare_promotion,verify_active}.py; stable adr_structure validate --final/graph 및 rag_main_promotion prepare/apply. 완료 run을 덮어쓰거나 재실행하지 않는다.')]
meta=f"---\nadr_id: ADR-0779\ntitle: 도구 실패 계약·정책 및 기존 장애 수정의 로컬 MAIN 통합 검증\nstatus: Accepted\ndecision_date: 2026-10-14\nphase: audit\nin_sample: false\ndecision_eligible: true\nmain_wiring: promotion-candidate\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 도구 복구 계약 감사\n\n5994개 사전 고정 유한 host 정책 상태와842개 기존 회귀. 질문 단위 법률 평가0·실제 모델0회. baseline 계약 미지원은 점수로 환산하지 않는다. 상세 ../artifacts/run-001/result.json.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0779','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen technical qualification evidence','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
