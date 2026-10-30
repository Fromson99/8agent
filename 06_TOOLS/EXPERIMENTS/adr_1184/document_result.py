"""Document completed observations without mutating raw runs or serving state."""
from common import *
import gzip
f=read(DES/'freeze.json');r=read(RUN/'result.json');P=ART/'live/cm-007';a=read(P/'audit.json');check=read(ART/('check-'+f['execution_id']+'.json'));stop=read(P/'resource-stop.json')
assert r['physical_calls']==1 and not (ART/'live/cm-009/dispatch.json').exists()
assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
put(ART/'completion-receipt.json',{'technical':{'total':308,'same_product_inherited_passes':306,'same_product_rerun_passes':2,'provenance':check['inherited_from']},'preserved_failures':['rev001304pass/2recording errors: missing execution_id','rev002307pass/1recording error: prior fallback output filename collision; repaired with unique execution binding and no product change','actual007 stopped at frozen host swap-growth guard, not a transport deadline;009 not run'], 'live_call_count':1,'budget_reserved':1,'source_checks':57,'delivered_source_checks':0,'source_mismatches':a['source_mismatches'],'acl_violations':a['acl_violations'],'old_call003_upstream_cause_known':False,'actual_expired_call_tested':False,'offline_absolute_deadline_verified':True,'main112_unchanged':True,'new_model_calls_during_audit':0})
report=ROOT/'09_ARTIFACTS/AUDITS/20261028-model-absolute-deadline/수정과_7번_재시험결과.txt';report.parent.mkdir(parents=True,exist_ok=True)
body='''모델 호출의 전체 기한 강제 — 원인 확인·수정·7번 재시험
2026-10-28 / ADR1184 / 격리 최종 rev002466파일 / MAIN112 유지

1. 이전 3번째 호출은 어디서 멈췄나
ADR1179 CM007에서는 첫 모델 호출 뒤 서버가 두 시장 상장규정13조와 유가증권시장 상장규정 시행세칙9조를 실제로 확보했다. 2번째 모델은 연결 원문 조사를 선택했고, 3번째는 source-law-navigation-7-read-choice-page-1-0의 다음 판단 요청이었다.
3번째 전송 시 남은 단계 기한은179.751초였다. 요청은 전송됐으나 완성된 HTTP 응답·수신 헤더·부분 본문을 저장하지 못한 채5분 이상 기다려 제어 측에서 중단했다. 저장 상태SENT는 결과불명이며 공급자의 확정 timeout/429가 아니다. 공급자 내부 지연인지 중계의 공백/keepalive인지 기존 기록만으로 확정할 수 없다. 원격 취소와 미응답 호출 비용도 확인하지 못했다.
확정한 서버 결함은 httpx.Client(timeout=180)가 호출 전체의 기한을 강제하지 않는다는 점이다. 각 통신 작업/본문 조각 사이의 대기 제한이어서 데이터가 계속 들어오면 전체180초를 넘길 수 있다. 기존 코드는 별도의 전체 기한 타이머와 늦은 결과 채택 차단이 없었다.
공식 근거: https://www.python-httpx.org/advanced/timeouts/
대형 응답 스키마는 관찰한 요청 특성일 뿐, 공급자 지연의 확정 원인으로 기록하지 않았다.

2. 수정 동작
절대 시각으로 정한 기한에 요청 준비·전송·전체 본문 수신을 묶었다. 서빙 gateway가 남은 단계 기한을 실제 전송기에 넘기고, 공통 ExperimentClient도 같은 전송 함수를 사용한다. 확정429로 공급자를 바꾸어도 처음 정한 남은 시간을 공유한다.
실제 HTTP 요청은 해당 요청 동안만 살아 있는 작은 별도 프로세스가 소켓을 소유한다. 기한이 끝나면 로컬 통신 프로세스를 종료하고 회수한다. DNS/헤더 대기·본문 정지·지속 공백 때문에 본 서버가 무한 대기하지 않도록 한 것이다. 데이터 저장소·GENOS job registry를 추가하지 않았다. 인증키는 표준입력 파이프로만 넘기고 명령행·진단에 남기지 않는다.
기한 뒤 반환된 결과는 gateway와 전송기에서 채택하지 않는다. 시간 초과는 UNKNOWN/504로 남기고 재시도·공급자 전환을 하지 않으며 예약한 물리 호출 예산을 유지한다. 로컬 종료는 원격 계산 종료 확인을 뜻하지 않는다.
수신 상태·첫/마지막 조각 시각·수신량/hash·요청 ID·프로세스 회수 여부를 기록한다. 실제 시험의 미완료 본문은 별도 gzip 원시 기록으로 남기도록 했다. 모델에는 같은 질문·원문·스키마를 전달하며 출력 토큰 상한은 추가하지 않았다.
MockTransport는 명시적 동기 시험 전용 경계이며 실제 네트워크 전송기로 허용하지 않는다. GENOS 내부 모델 전송기나 전체 SQL 실행 시간을 강제 종료하는 변경은 아니다.

3. 기술 검증
부모1179 대비 제품4파일·pin31파일 변경, 최종466파일 동결.
- request_deadline.py: 요청 수명 동안의 통신 프로세스·절대 기한·부분 수신 진단
- local_gemma.py: 실제 로컬 서빙 전송기에 연결, 만료 결과 거절
- gateway.py: 남은 절대 기한 전달, 늦은 응답 거절·UNKNOWN 기록
- experiment_client.py: 공통 실험 호출과429 전환에 같은 제한 적용
기술308조건 통과. 신규15조건에는 실제 소켓의 무응답 헤더, 정지 본문, 지속 공백, 늦은 완료, 정상/429/500, 전송 전 만료, 프로세스 회수, 실제 API의504/UNKNOWN/재개 시 재전송 금지, 공통 클라이언트 준비시간과429 공유기한이 포함된다.
기존 httpx 방식은200ms 제한에서도 공백을 계속 받으면1초 넘게 기다리는 현상을 재현했다. 수정본은450ms 기한에서1.2초 이내에 통신을 끝내고 프로세스 부재를 확인했다(오류 주입 허용 오차 포함). 이는 실제 서비스 응답시간 개선율이나 원격 취소 인증이 아니다.
부모/후보211회귀: 각각189통과·기존9실패·준비오류13, 항목별 동일·새 회귀0·import 누출0.
rev001의 기록용 execution_id 누락2건, rev002의 이전 결과 파일명 충돌1건을 보존했다. 최종 제품의307통과 기록 중306건을 승계하고, 충돌 검사와 실제 저장 원문 재생2건을 같은466파일에서 새 식별자로 재검사해308조건을 확인했다. 모델 호출을 추가하지 않았다.

4. 이번 실제7번
최종 코드로 질문1회·Qwen3.8/Chutes FP8·물리1호출·예산차감1. 첫 모델 응답은14.502초에 HTTP200으로 완성됐고 통신 프로세스 회수를 확인했다. 입력3216/출력506토큰, 공급자 보고 비용0.000757924달러. 이번 실행의 결과불명 모델 호출은0이다.
서버는 동일한3원문 목표를 등록하고 첫 원문 읽기를 집행했다. 원문57구간 검증에서 불일치0·권한위반0. 다음 모델 호출 전이므로 원문 전달 검증 구간은0이며 이를 원문 전달 성공으로 확대하지 않는다. 코스닥시장 상장규정13조 원문은 확보됐지만 유가증권시장 상장규정13조는 이번 중단 시점에 미확보였다.
실행 시작46.193초에 자원 감시기가 종료코드125로 중단했다. 호스트 스왑 사용량 증가129.5MiB가 사전128MiB 기준을 넘겼다. 당시 사용 가능 RAM8.197GiB, 실행 프로세스 RSS3.177GiB여서 RAM 고갈이나 모델 장애로 단정하지 않는다. 이 기준은 호스트 전체 관측값이며 특정 다른 작업의 탓으로 확정하지 않았다.
중단은 원문 조사 중, 두 번째 모델 호출 전이었다. 이번 실제 실행에서180초 만료를 다시 관찰한 것은 아니다. 기한 종료 동작은 오류 주입과 실제 API 모의 시험으로 검증했고, 실제7번은 완료 답변·ASSESS·저장 완료가 없어 미통과다.
강제 종료 때문에 정상 결과/HTTP 응답 파일이 없었다. 후속 result.json은 개별 호출 영수증·저장 journal·resource-stop으로 재구성했음을 표시했고, 없는 응답을 만들지 않았다. journal의RUNNING 상태도 그대로 보존했다. 종료되지 않은 gzip 자원 로그는 원본을 보존하고 복구 가능한 행을 별도 기록했다. 시험 프로세스38027과 통신 프로세스38111이 모두 없는 것을 확인했다.

5. 후속과 반영 상태
7번 미통과이므로9번 미실행. 같은7번 자동 재실행0·추가 모델0. 사전 자원 기준을 낮추어 통과 처리하지 않았다.
수정은 격리 후보에 구현·검증했다. 작업 제품 통합·MAIN 승격·선택 서비스 변경·GENOS 배포·더 좋은 모델 비교는 미수행이며 MAIN112를 유지한다. 포인터 변경이 없어 서비스 롤백은 필요 없다. 다음 실제 시험은 자원 중단 조건을 따로 검토하고 새로운 실행 기록으로 진행해야 한다.

6. 주요 기록
04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/artifacts/diagnosis.json
04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/artifacts/design/execution-binding-001.json
04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/artifacts/check-rev-002-r1.json
04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/artifacts/regression-comparison.json
04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/artifacts/live/cm-007/resource-stop.json
04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/artifacts/live/cm-007/gate.json
04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/artifacts/completion-receipt.json
'''
assert not report.exists();report.write_text(body)
put(ART/'report.json',{'path':str(report.relative_to(ROOT)),'sha256':sha(report)})
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
'절대 모델 기한·로컬 통신 종료·늦은 결과 차단을 구현했다. 기술308조건·새회귀0. 실제0071호출 뒤 원문 조사 중 자원 기준으로 중단,009미실행·MAIN112유지. 법률 품질 미인증.',
'이전1179 CM007의3번째는 필요한 원문 확보 후 후속 판단 요청이었다. 완성 응답 없이 단계179.751초를 넘겼다. httpx의 작업/조각별 timeout 외에 전체 기한 강제가 없었다. 원격 원인은 미확인. [진단](artifacts/diagnosis.json).',
'[호출 전 기준](artifacts/design/criteria.json). 절대 기한, 종료/회수, 늦은 결과 거절, UNKNOWN 무재시도, 원문·권한·예산 보존. 실제0071회→통과할 때만0091회.',
'1179/scoped에서bounded 분기. 실제 서빙과 공통 클라이언트가 요청 수명의 별도 HTTP 프로세스를 사용한다. 실제 소켓 오류 주입·native API·기존 공급자/원문 계약·부모 대조 회귀를 순차 실행했다.',
'MAIN112 동일 데이터·65문서 권한, Qwen3.8/Chutes FP8·확정429일 때만NearAI1회.40물리/1024도구/1800초·출력상한없음 유지. 최종rev002466파일, [실행 결속](artifacts/design/execution-binding-001.json).',
'[결과](artifacts/run-001/result.json), [보완 영수증](artifacts/completion-receipt.json).308기술조건,211회귀189통과/기존9실패/준비오류13동일. 실제007모델1/차감1·원문57구간불일치0·권한위반0,최종답변없음.',
'rev001기록식별자누락2건·rev002기록경로충돌1건을 보존하고 제품 변경 없이 고유 실행 식별자로 재검사했다. 이번007은 기한 초과가 아니라 호스트 스왑증가129.5MiB가 사전128MiB 기준을 넘겨 종료됐다. RAM8.197GiB가 남아 있었으며 OOM으로 분류하지 않는다.',
'첫 실제 모델 응답14.502초, 입력3216/출력506토큰·보고비용0.000757924달러. 전체 관측46.193초는 자원 중단까지다. 속도개선율이 아니다. [회수 원장](artifacts/run-001/retrieval-ledger.json);009는executed=false.',
'오류 주입에서는 지속 공백에도 절대 기한에 로컬 통신이 끝났고 API는UNKNOWN/504를 저장했다. 실제007에서는 정상 응답 경로만 확인했으며 만료 경로의 실모델 재현·최종 답변 품질은 미확인이다.',
'외부 로컬 모델 전송 범위다. GENOS 내부 전송기·모든 SQL·원격 계산의 취소를 보장하지 않는다. 실제007 자원 중단으로 답변 완성 실패,009미실행. 같은 실패 자동 재요청 없음.',
'격리 후보 유지. 작업 제품 통합·MAIN승격·GENOS배포 미수행. MAIN112포인터 불변으로 롤백 불필요. 원문/권한/예산/늦은결과 위반시 채택 금지.',
'실행기는06_TOOLS/EXPERIMENTS/adr_1184. 완료 기록과 실모델을 덮어쓰거나 자동 재실행하지 않는다. 새시험은 독립 실행 기록으로 분기한다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline --final`'
]
pth=ADR/'README.md';front=pth.read_text().split('---',2)[1];pth.write_text('---'+front+'---\n\n# 모델 절대 기한과007조건부 재시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 인덱스\n\n[CM007](질문-001-cm-007.md):모델1호출 뒤 원문 조사 중 자원 기준 중단,미통과.\n\n[CM009](질문-002-cm-009.md):007미통과로미실행.\n\n[실행·계보](manifest.json), [결과](../artifacts/run-001/result.json), [보완 영수증](../artifacts/completion-receipt.json).\n')
pth=ROOT/'AGENTS.md';s=pth.read_text();marker='<!-- MODEL_DEADLINE_1184 -->';assert marker not in s
note='''<!-- MODEL_DEADLINE_1184 -->
**2026-10-28 — 모델 절대 기한 수정·007 재시험:** [결과 TXT](09_ARTIFACTS/AUDITS/20261028-model-absolute-deadline/수정과_7번_재시험결과.txt) · [ADR1184](04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/README.md). 이전1179의3번째호출은원문확보후후속판단중응답미완료였으며원격원인은미확인이다. 작업별httpx timeout만있던경로에절대기한·요청수명통신프로세스종료/회수·늦은결과거절·UNKNOWN/504무재시도를서빙gateway/공통클라이언트에연결했다. 격리rev002466파일·제품4/pin31변경·기술308조건·211회귀189통과/기존9실패/준비오류13동일·새회귀0. 기록식별자/경로오류는보존·정정했다. **실제007은1호출/차감1·정상응답14.502초뒤원문조사중호스트스왑증가129.5MiB가사전128MiB기준을넘겨46.193초에종료코드125로중단**. 당시가용RAM8.197GiB로OOM단정금지. 원문57구간불일치/권한위반0·원문전달0구간. 코스닥13확보·유가13미확보·최종답변없음·009미실행. 이번실제만료호출관찰없음,만료경로는오류주입/native API검증이다. 작업제품통합·MAIN승격·GENOS·강한모델비교미수행, **MAIN112유지**.
<!-- /MODEL_DEADLINE_1184 -->

'''
s=s.replace('# 8-AGENT 작업 가이드\n','# 8-AGENT 작업 가이드\n\n'+note,1);pth.write_text(s)
print(report)
