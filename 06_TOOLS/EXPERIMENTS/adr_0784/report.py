from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0784-length-adapter-parity'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[],judge_disagreements=0,usage=result['usage'],latency={'kind':'Synthetic host audit; field model latency unmeasured'},error_taxonomy=[]);put(A/'실험/manifest.json',m)
parts=[('결정 요약','Accepted promotion-candidate. 법령 탐색 length 수정에만 별도 출력 한도를 적용하고 기존 4개 계약 실패를 해결했다. 원문·모델·검색·정상 호출 한도는 유지한다.'),
('문제와 변경 전 구조','통합 서비스 RuntimeModel.invoke는 정상 및 수정 요청에 모두6400토큰을 넘겼다. length 뒤 같은 cap의 재생성을 반복해도 출력 길이 원인은 남는다.1536 기본값만 원인이라는 초기 가설은 실제API로 반증됐으며 개발 기록에 보존했다.'),
('가설과 사전 판정 기준','선택한 정책에서 법령 탐색 length 교정1회만12800토큰을 허용하면 동일 cap 재시도를 제거할 수 있다. 정상 응답/필터/일반 스키마 수정은 그대로여야 한다.296개 유한 계약과 모든 회귀 통과, 코드/원문/권한/재개/발행 불변조건이 기준이다. 기존 실패 예외 허용0.'),
('실험 설계','length/cap/완료사유/usage192조합 및 checkout·실제 의존 경로·엔진 성숙도64조합. MAIN65과 동결 후보를 별도 프로세스로 실행했다. ADR0780은 실행 전 fixture/import·배포 누락을 발견해 중단했고 ADR0781은885통과1실패로 승격하지 않았다. 완료된 MAIN65 arm만 부모로 사용했다.'),
('데이터·모델·재현성','308서빙 파일과 검사 소스를 동결했다. 후보/작업/선택 코드 바이트를 대조한다. 합성 원문과 모의 모델 응답만 사용하며 실제 모델 호출0. 이 유한 host 계약은 미사용 법률 질문 holdout이나 모델 정확도 평가가 아니다.'),
('결과',f"유한 계약296/296 통과; 기존 및 추가 회귀{result['contracts_passed']}개 통과, 실패/skip0. runtime은 동결 후보에서만 import했다. 기준 결과는 새 기술 계약에 대한 적합성 비교이며 법률 정답률로 해석하지 않는다."),
('사례별 오류 분석','①auth/format/model mismatch를 같은 durable decision에 재실행하던 검사는 독립 요청으로 나누고 동일 요청 중복 금지 추가.②PIPELINE의4확장 선언을 닫힌 typed schema에 연결하고 두 host schema를 엔진에 pin.③공개 오류는 request_id/503안내를 검증하며 내부run_id를 재노출하지 않음.④현재v6 기본과 명시v3 호환을 함께 검증. 후보 경로의 research 문자열을 의존성으로 오인하던 host는 실제 상대 의존 경로를 검사하도록 수정; 연구 모듈 차단 유지.'),
('비용·지연·회수 규모','정상 요청6400 유지. length 수정1회에만 최대12800; 추가 물리 호출 횟수 없음, 기존 한 번의 교정과 총deadline/모델 예산 사용. 출력 크기/지연은 해당 실패 수정에서 늘 수 있다. 입력·모델·검색 정책 변경0. 실제usage와 내부서빙context 상한은 미확인.'),
('해석','잘린 JSON은 실행하지 않고 원본 attempt에 보존한다. 같은 근거·schema·권한으로 완전한 결정을 다시 받아 원래 검증과 발행을 거친다. 수정도length거나 남은 출력/호출/시간 예산이 없으면 중단한다. 기존 프로필에 새 정책이 없으면 이전 동작을 유지한다.'),
('한계와 일반화 가능 범위','사진의 정확한 입력/usage/내부서빙한도는 없으므로 원래 현장요청 성공을 확정하지 않는다. 이 수정은 확인된 동일cap 복구 결함 해결이다. 무조건 모든length를 해결하거나 법률판단을 보장하지 않는다. 출력압축·부분JSON복원·후속부분도메인저장/사실질문/취소전달은 별도다.'),
('운영 결정·롤백 조건','사용자 검증 후 MAIN 반영과 삼성메일 발송 승인에 따라 표준 qualification prepare/apply --confirm-main을 수행한다. MAIN65 유지·표준rollback 가능. GENOS는 기존DEV에 누적패치 적용 후 같은commit generation gate, push, 새리비전, SSE재시작, workflow화면 재질의가 별도다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0784/{prepare,freeze,audit,report,prepare_promotion,verify_active}.py; stable adr_structure validate --final/graph; rag_main_promotion prepare/apply. 완료실험을 재실행하거나 이전 결과를 덮어쓰지 않는다.')]
meta=f"---\nadr_id: ADR-0784\ntitle: 길이 복구와 기존 계약 실패 수정의 MAIN 검증\nstatus: Accepted\ndecision_date: 2026-10-14\nphase: audit\nin_sample: false\ndecision_eligible: true\nmain_wiring: promotion-candidate\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 길이 복구·배포 계약 감사\n\n296개 유한 host 계약과 기존 회귀. 실제 모델0회·법률 정답률 측정 아님. 상세 ../artifacts/run-001/result.json.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0784','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen technical qualification evidence','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
