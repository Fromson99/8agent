from common import *
import re
P=ART/'live/cm-007';r=read(RUN/'result.json');d=read(P/'diagnosis.json');g=read(P/'gate.json')
f=read(DES/'freeze.json');review=read(P/'content-review.json');calls=read(P/'calls.json')
assert r['physical_calls']==12 and not g['passed'] and not (ART/'live/cm-009/dispatch.json').exists()
assert calls[0]['http_status']==429 and calls[0]['provider']['only']==['parasail/fp8']
assert all(x['actual_provider']=='Near AI' and x['http_status']==200 for x in calls[1:])
assert d['provider_switches']==1 and not d['remaining_worker_pids']
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-main115-parasail-test';O.mkdir(parents=True,exist_ok=True)
report=O/'실험결과.txt'
text='''MAIN115 Parasail 실제 시험 — 2026-10-29 / ADR1191

결과
Parasail 첫 요청은 약0.8초에 HTTP429로 거절됐다. 응답에는
provider_name=Parasail, limit_source=upstream_provider_shared_pool이 기록됐다.
설정대로 Near AI로 한 번 전환해 나머지11개 모델 응답을 받았다.
CM007은337.624초(약5분38초)에 HTTP200/READY, 최종 답변과 COMPLETE 저장까지 완료됐다.
그러나 사전 내용 검토 조건을 통과하지 못해 CM009는 실행하지 않았다. 같은7번 재시도0회.
이번 결과를 Parasail의 생성 속도나 Parasail 성공으로 설명하지 않는다.

실행 조건
사용자 “실험해봐” 요청에 따라 MAIN115 / parasail-primary-20261029-r1의466파일과
질문·데이터·65문서 권한을 동결한 뒤 실제 service.service → RAG_ASK 경로로 실행했다.
Qwen3.8 FP8·reasoning none·출력상한없음·40모델/1024도구/1800초 예산·개별180초 기한 유지.
확정429만 Near AI 1회 전환. 기준답변·평가용 필수 좌표는 제품 모델에 전달하지 않았다.
이전과 동일한 자원 기준을 유지했으며 제품 코드·공급자 정책·MAIN 선택은 변경하지 않았다.

통과한 부분
- 실제 물리 요청12회 = 예산 차감12회. Parasail 거절1회 + Near AI 응답11회. 도구44회.
- 두 시장 상장규정 제13조를 모두 확보하고 최종 답변에 인용했다.
- 추가 코스닥 시행세칙 제15조 등도 확보했다. 서버 source goal READ 완료4회.
- 원문 확보359구간·모델 입력922구간의 원문 불일치0·권한 위반0.
- 새 requirement_review가 실제 ASSESS에서1회 채택·저장됐다. 별도 검토 모델 단계 추가0.
- 첫 ASSESS는 판단·주장에 같은 원문 근거가 없다는 오류로 거절했고, 기존 보완1회 후 채택했다.
- 최종 주장6개, ANSWER/COVERED, material gap0, 반환/저장 답변과 판단 해시 일치.
- 요청 저장 COMPLETE / 실행 COMPLETED. UNKNOWN0·기한만료0·자원 중단0.
- 최소 가용RAM7.894GiB, 최대 작업RSS3.485GiB, 호스트 스왑 증가0MiB.
- 모든 관측 통신 자식 프로세스 종료 확인.

내용 검토 미통과 이유
1. 최종 주장 C6은 유가증권시장 의무인수를 모집·매출한 외국주권등의5%라고 설명하면서
   원문의 “상장예비심사를 신청한 후에 국내에서 모집·매출한” 범위를 빠뜨렸다.
   저장 기준답변에도 “국내 모집·매출분”이 명시돼 있다. 계산 대상 수량을 한정하는 조건이다.
   해당 원문은 이미 확보·전달돼 있었으므로 이번 문제는 검색 실패가 아니라 답변의 범위 누락이다.
2. 내부 ASSESS는 COVERED, gaps=[], “추가 미확인 사항 없음”이라고 판단했지만,
   화면 답변 끝에는 “확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.”가 붙었다.
   선택 코드 completion_contracts.py의 refresh_limitations는 gap이 없어도 stop_reason이 있으면
   이 일반 제한 문구를 붙인다. 이번 stop_reason은 DIRECTIVE_RESULT_REVIEW:BOUNDED_HANDOFF였다.
   모델이 이 문구를 만든 것이 아니라 서버의 최종 표현 조립에서 추가된 것으로 확인했다.
   이를 실제 원문 미확보나 새로운 material gap이 있었다는 증거로 해석하지 않는다.

국내/외국·기업 유형별 주요 비율·상한·기간과 코스닥 취득 방법은 답변에 있었다.
전체 답변이 전부 틀린 것은 아니며, 기술 완료와 최종 의미 정확도 검토를 나눠 판정했다.
gate13항목 중12개는 통과했고 content_review_passed가 실패했다.
새 요구별 검토 형식은 동작했지만 이번 의미상 범위 누락을 자동으로 검출하지는 못했다.
사전 조건대로9번은 미실행이며, 통과시키려고 기준을 완화하거나 답변을 재작성하지 않았다.

시간과 공급자 해석
모델 통신 합계208.867초, 나머지 로컬 준비·조회·검증·입출력 등128.756초.
모델 단계는 최초판단(429 포함2호출), 조사판단6회, 감독판단2회, ASSESS 및 보완2회다.
Near AI 정상 응답은7.342~36.255초였다. 이전 Chutes의 기한 초과 단계에 대응하는
조사판단은 이번22.363초에 완료됐다. 다만 실제 입력·상태·시점이 같지 않아 통제 A/B가 아니다.
Chutes 실패 실행의 전체238.5초와 이번 완성 실행337.6초를 속도 개선율로 비교하지 않는다.
이번 관찰은 공급자 전환이 실제로 작동하고 Near AI에서 답변까지 진행됐다는 증거다.
Parasail은 외부 공유 풀의429였으며 우리40회 호출 예산을 다 써서 발생한 오류가 아니다.
정상 응답11개의 공급자 보고 합계: 입력234161 / 출력12388토큰, 비용0.026090240달러.
429 응답에는 사용량 정보가 없으므로 전체 청구 비용이라고 단정하지 않는다.

보존·한계
준비 메타검사의 질문 문서 제목 누락 및 회수 설명 누락19오류를 첫 호출 전에 정정했다.
초기 오류 파일과 수정 후 검사 결과를 보존했으며 동결된 실행 입력·스크립트는 그대로 유지했다.
새 평가 모델0. 알려진 CM007 단일 실행이며 법률 정확도·공급자 성능 일반화 인증이 아니다.
현재 법령의 법률 자문이 아니라 저장 판본 기준의 시스템 답변 검토다.
MAIN115 유지. 코드 수정·GENOS 배포·Git commit/push·메일 발송은 수행하지 않았다.
후속 수정은 의미상 적용 범위 보존과 COVERED 답변의 불필요한 제한 문구를 분리해 다룰 수 있다.

근거
ADR: 04_EXPERIMENTS/ADR/ADR-1191-main115-parasail-cm007
실제 답변: artifacts/live/cm-007/answer.txt
원문/예산 검증: artifacts/live/cm-007/audit.json 및 storage-audit.json
내용 판정: artifacts/live/cm-007/content-review.json, gate.json
공급자·시간·자원: artifacts/live/cm-007/diagnosis.json, calls.json
원시 요청·응답: artifacts/live/cm-007/raw/call-*/*.json.gz
결과/회수 원장: artifacts/run-001/result.json, retrieval-ledger.json
'''
with report.open('x') as stream:stream.write(text)
put(ART/'report.json',{'path':str(report.relative_to(ROOT)),'sha256':sha(report)})
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
 'Parasail 첫 호출은429. Near AI1회 전환 후 CM007의11응답·최종 답변·저장을 완료했다. 내용 범위 누락으로7번 미통과·9번 미실행. MAIN115와 제품 코드 유지.',
 'MAIN115는 사용자 요청으로 기본 공급자만 Parasail로 변경한 상태다. 이전 Chutes 실행이 원문 확보 뒤 응답 미완료로 멈췄으므로 사용자가 실제 시험을 요청했다.',
 '[사전 기준](artifacts/design/criteria.json): 원문·권한·물리 호출 예산·필수 원문 확보/인용·요구별 검토·저장 및 최종 내용이 모두 통과해야009 실행. 같은 사례 자동 반복 없음.',
 '완료1190/switched의 실제 선택 MAIN115466파일을 변경 없이 동결했다. CM0071회, 통과 시만 CM0091회. 평가 모델0. [동결](artifacts/design/freeze.json).',
 'Qwen3.8 FP8·Parasail우선/확정429만NearAI1회. 동일65문서 권한·데이터·40/1024/1800·출력상한없음. 사용자 실험 승인 후 실행했고 기준답변은 제품에 전달하지 않았다.',
 '[결과](artifacts/run-001/result.json): 00712물리호출/337.624초, READY/ANSWER/COVERED·주장6·COMPLETE 저장. 원문359/입력922불일치0·권한위반0·차감12일치. gate13중12통과, 내용검토 실패로009미실행.',
 'Parasail 공유풀429를 약0.8초에 수신했고 Near AI 응답11개를 받았다. 판단·주장 근거 불일치로 ASSESS 보완1회. 최종 C6의 국내 모집·매출 범위 누락과 COVERED에도 붙는 서버 일반 제한 문구를 확인했다. 원문 미확보가 아니다. 준비 문서/회수 설명19오류는 호출 전 정정·원본 보존.',
 '총337.624초 중 모델208.867초, 기타128.756초. 정상11응답 입력234161/출력12388토큰·보고합계0.026090240달러.429 사용량 미보고. 새 평가 모델0·기한만료0·UNKNOWN0·자원중단0. [원장](artifacts/run-001/retrieval-ledger.json). p95·속도 개선율 산출 없음.',
 '429전환·원문 선집행·요구검토 저장·최종 응답 경로는 실제로 진행됐다. 요구검토의 형식적 결속이 의미상 범위 누락을 검출한다는 보장은 없다. 답변 끝 제한 문구는 서버 refresh_limitations의 stop_reason 조건에서 나왔다.',
 'Parasail의 생성 응답은 없으므로 성능 판정을 하지 않는다. Near AI 단일 known-case 관찰이며 다른 시점/입력의 Chutes와 통제비교가 아니다. 저장 판본 기준이고 현행 법률 자문·GENOS 현장 검증이 아니다.',
 'MAIN115·제품·자원 기준을 유지한다.009와 같은7번 자동재시험은 수행하지 않는다. 이번 실험은 코드 변경이 없어 롤백 없음. 필요한 후속 수정은 별도 작업으로 한다.',
 '06_TOOLS/EXPERIMENTS/adr_1191. 완료 실행을 재호출하지 않는다. `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1191-main115-parasail-cm007 --final`.',
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
p.write_text('---'+front+'---\n\n# MAIN115 Parasail 실제 시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 인덱스\n\n| 질문 | 실제 실행 | 판정 |\n|---|---|---|\n| [CM007](질문-001-cm-007.md) |1회·물리12호출|Parasail429→NearAI11응답·완료, 내용검토 미통과|\n| [CM009](질문-002-cm-009.md) |미실행|CM007 미통과로 후속 차단|\n\n[결과](../artifacts/run-001/result.json). 법률 품질 미인증.\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '__pycache__' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[report]
entries=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
 'description':'Exact MAIN115 live evidence; blocked preparation preserved',
 'contains_raw_prompts_and_outputs':('/raw/' in str(p) or '/canonical/' in str(p) or p.name.endswith('.sqlite'))} for p in paths]
(ART/'manifest.json').write_text(json.dumps({'schema_version':'adr-artifacts-v1','adr_id':'ADR-1191','created_at':read(ADR/'claim.json')['created_at'],'files':entries},ensure_ascii=False,indent=2)+'\n')
print(report)
