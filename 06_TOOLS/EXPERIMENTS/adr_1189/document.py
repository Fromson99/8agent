from common import *
P=ART/'live/cm-007';r=read(RUN/'result.json');d=read(P/'diagnosis.json');g=read(P/'gate.json');f=read(DES/'freeze.json')
assert r['physical_calls']==2 and not g['passed'] and not (ART/'live/cm-009/dispatch.json').exists()
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-main114-cm007-retest';O.mkdir(parents=True,exist_ok=True)
report=O/'7번_실제시험_결과.txt'
text='''MAIN114 실제 CM007 시험·조건부 CM009 결과
2026-10-29 / ADR1189 / MAIN114 유지

결과
7번을 실제 선택 MAIN114 서비스에서1회 실행했다. 두 시장 상장규정13조는 확보했으나 두 번째 모델 호출이 절대 기한에 도달해 최종 답변 없이 HTTP504로 종료됐다. 사전 조건대로9번은 실행하지 않았다. 같은7번 자동 반복도 하지 않았다.

실행 조건
릴리스 requirement-coverage-20261029-r1의466파일과 데이터·프로필·질문·공개문서65개 권한을 호출 전에 고정했다. 실제 service.service → /v1/rag/ask 경로를 사용했으며 후보와 실제 선택 코드의 해시가 일치한다.
Qwen3.8 / qwen/qwen3.8-27b / Chutes FP8. 확정429일 때만 Near AI로1회 전환하는 기존 정책이다. 이번에는429가 없어 전환0회였다.
예산40물리호출·1024도구·1800초, 단계기한180초, 출력 토큰 상한 없음 유지. 온톨로지는 기본OFF였다. 기준답변과 필수 근거 좌표는 제품 모델에 보내지 않았다.
외부 전송 자동 승인 검토가2회 거절한 이력과 기존 승인 근거를 보존했다. 사용자가 이번 목적지·전송 범위를 안내받은 뒤 “진행해”라고 승인해 실행했다. 앞선 차단 당시의 모델 호출0 기록은 당시 상태이며 이번 새 실제 호출은2회다.

어디까지 됐나
1. 첫 모델 호출(request-entry)은8.657초에 정상 완료했다.
2. 서버가 표제에서 원문 목표를 등록하고 추가 선택 모델 호출 없이 코스닥시장 상장규정13조, 유가증권시장 상장규정13조, 유가증권시장 상장규정 시행세칙9조를 확보했다. 목표 READ 완료3개를 원장으로 확인했다.
3. 두 번째 호출(source-law-navigation-6-read-choice-page-1-0)은 확보한 원문을 보고 다음 행동을 정하는 조사 판단이었다. HTTP200 헤더는 받았지만58개 수신 조각·660바이트의 공백만 수신했고 완성 JSON은 받지 못했다. 원시 부분 본문의 길이와 공백 여부·SHA256을 별도로 확인했다.
4. 남은 절대 기한 약179.7초에 로컬 통신 프로세스를 종료·회수했고 UNKNOWN으로 기록했다. 서버는 HTTP504를 반환했으며 요청·실행 저장 상태는 모두FAILED다. 늦은 결과 채택·동일 요청 재시도·공급자 전환은 없었다. 실행기와 두 통신 프로세스가 종료된 것을 확인했다.

검증 결과
- 전체 요청238.503초, 물리 모델2회 = 예산 차감2회, 도구26회.
- 확보 원문73구간과 모델 입력 원문 view61구간 비교: 불일치0·권한 위반0. 예약 요청과 실제 전송 본문도 일치했다.
- 두 필수13조 확보 확인, 최종 인용·최종 답변 없음.
- 새 requirement_review/ASSESS 단계 도달0회. 따라서 이번 실행으로 MAIN114의 새 요구별 검토 효과를 통과로 판정할 수 없다.
- 기한 초과 뒤 통신 종료·UNKNOWN·504·FAILED 저장은 이번 실제 호출에서 확인했다. 원격 계산 취소와 두 번째 호출의 비용은 미확인이다.
- 자원 중단 없음. 관측 최소 가용RAM8.100GiB, 최대 작업RSS3.197GiB, 호스트 스왑 증가0MiB.1~3번 로컬 자원 문제 수정이나 자원 기준 완화는 하지 않았다.
- 첫 정상 응답 사용량은 입력3212/출력479토큰, 공급자 보고 비용0.000724018달러다. 두 번째 결과불명 호출의 사용량·비용이 없어 전체 비용으로 합산하지 않는다.

원인과 한계
관측한 직접 중단 원인은 모델 응답 미완료로 인한 MODEL_DEADLINE_EXCEEDED다. OpenRouter·Chutes 내부의 어느 구간에서 왜 완성 응답이 없었는지는 미확인이다. 큰 응답 스키마가 포함된 것은 관측 사실이며 원인으로 확정하지 않았다. 모델이 틀린 법률 판단을 했다고 채점할 답변 자체가 없다.
이번 새 테스트는 알려진 질문의 단일 probe다. 법률 정확도·성능 개선 인증이나 GENOS 현장 확인이 아니다.

판정·유지 범위
7번 완료 게이트 미통과 →9번 미실행. 원문 확보·무결성·예산 검사는 통과했으나 HTTP READY·완성 답변·최종 요구 검토 조건은 충족하지 못했다.
코드·데이터·모델·자원 기준·MAIN 포인터는 변경하지 않았다. 선택 MAIN114 유지. GENOS 배포·더 좋은 모델 비교·Git commit/push·메일 발송 없음. 재실행은 이번 실패·호출 예산을 보존한 별도 시험으로만 한다.
준비 단계의 메타데이터 검사2오류는 첫 호출 전에 정정하고 보존했다. 전체 ADR graph의 기존 오류와 본 ADR의 검사 결과는 별도 최종 영수증에 기록한다.

근거
04_EXPERIMENTS/ADR/ADR-1189-main114-cm007-conditional009/artifacts/run-001/result.json
04_EXPERIMENTS/ADR/ADR-1189-main114-cm007-conditional009/artifacts/live/cm-007/diagnosis.json
04_EXPERIMENTS/ADR/ADR-1189-main114-cm007-conditional009/artifacts/live/cm-007/gate.json
원시 입출력: 같은 cm-007/raw/call-*/*.json.gz
실제 요청별 저장: 같은 cm-007/runtime/legal-agent/runs/20261029/7aa22ace00af48e486bbe0898305f274/journal.sqlite
'''
with report.open('x') as stream:stream.write(text)
put(ART/'report.json',{'path':str(report.relative_to(ROOT)),'sha256':sha(report)})
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
'MAIN114의 실제 CM0071회는 두 필수13조 확보 후 두 번째 모델의 응답 미완료로504 종료했다.7번 미통과·9번 미실행. MAIN114와 제품 코드는 유지한다.',
'MAIN114는 질문 요구별 충족·제외·미해결 검토를 기존 ASSESS에 추가했다. 기술검사는 통과했으나 실제 CM007/009 품질은 확인하지 않았다. 이전1184의 자원 중단은 보존하고 이번에는 같은 자원 기준을 유지했다.',
'[동결 기준](artifacts/design/criteria.json): 원문·권한·호출 예산 일치와 필수 원문 확보/인용, 최종 답변·요구 검토·저장 COMPLETE가 모두 통과한 경우에만009를 실행한다. 같은 사례 자동 반복 없음.',
'완료1188/reviewed의 선택 MAIN114를 변경 없이 재시험. 서비스 진입점과466파일을 고정했다. CM0071회→전 조건 통과 시에만 CM0091회, 평가모델0. [동결](artifacts/design/freeze.json).',
'Qwen3.8·Chutes FP8, 확정429만 NearAI1회,65공개문서 권한, 기존 데이터·40/1024/1800·출력상한없음. 기준답변/정답좌표는 제품 입력과 분리. 사용자 추가 전송 승인 후 실행했다. [결속](artifacts/live/cm-007/binding.json).',
'[결과](artifacts/run-001/result.json), [진단](artifacts/live/cm-007/diagnosis.json).7번2호출/238.503초·원문73/입력view61구간 불일치0·권한위반0. 두13조 확보, 최종답변과 요구별검토는 미완료.9번 미실행.',
'첫 호출8.657초 정상. 두 번째는 HTTP200헤더 후58조각660바이트 공백만 받고179.699초에 AbsoluteDeadlineExceeded. UNKNOWN/FAILED/HTTP504로 종료·프로세스 회수. 원격 원인은 미확인. 자원중단0·스왑증가0MiB. 준비 메타데이터2오류 및 자동승인검토2거절은 각각 정정/명시승인 이전 기록으로 보존.',
'물리2=차감2,도구26. 첫 응답 입력3212/출력479토큰·보고비용0.000724018달러. 두 번째 사용량과비용 미확인. 전체238.503초이며 p95·속도 개선율은 산출하지 않는다. [회수원장](artifacts/run-001/retrieval-ledger.json).',
'서버 원문 선집행과 실제 절대 기한 종료는 확인했다. 새 요구별 검토 ASSESS 이전에 멈췄으므로 그 효과는 미검증이다. 충분성/제외 판단의 정오를 평가한 결과가 아니다.',
'알려진 CM007 단일 실행이며009는 조건부 미실행. 원격 취소·결과불명 호출 비용·공급자 내부 원인 미확인. 로컬 SQLite 확인을 GENOS Oracle 성능·법률 품질로 일반화하지 않는다.',
'MAIN114·제품·자원 기준 유지. 후속009 및 자동재시험을 수행하지 않았다. 실행 실패는 보존하며 코드·데이터 변경이 없어 이번 시험에 따른 롤백은 없다.',
'06_TOOLS/EXPERIMENTS/adr_1189. 완료 질문을 자동 재호출하지 않는다. 읽기 전용 구조 검사: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1189-main114-cm007-conditional009 --final`.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];p.write_text('---'+front+'---\n\n# MAIN114 CM007 실제 시험과 조건부 CM009\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 인덱스\n\n| 질문 | 실제 실행 | 판정 |\n|---|---|---|\n| [CM007](질문-001-cm-007.md) |1회·모델2호출|원문 확보 후 응답 미완료·504·미통과|\n| [CM009](질문-002-cm-009.md) |미실행|CM007 미통과로 후속 차단|\n\n[동결·계보](manifest.json) · [결과](../artifacts/run-001/result.json). 법률 품질 미인증.\n')
# Bind raw outputs once. Runtime SQLite remains the native source, never rewritten.
paths=list(ART.rglob('*'))+[p for p in Path(__file__).parent.glob('*.py')]+[report]
entries=[]
for p in paths:
 if not p.is_file() or p==ART/'manifest.json' or '__pycache__' in p.parts:continue
 entries.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact MAIN114 live-run evidence; historical failed and blocked preparation records preserved','contains_raw_prompts_and_outputs':('/raw/' in str(p) or '/canonical/' in str(p) or p.name.endswith('.sqlite'))})
(ART/'manifest.json').write_text(json.dumps({'schema_version':'adr-artifacts-v1','adr_id':'ADR-1189','created_at':read(ADR/'claim.json')['created_at'],'files':entries},ensure_ascii=False,indent=2)+'\n')
print(report)
