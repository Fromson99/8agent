"""Summarize the completed diagnostic; no product changes or model calls."""
from pathlib import Path
from collections import Counter
import json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile'
O = A / 'artifacts/run-001'
read = lambda p: json.loads(p.read_text())
s = read(O / 'summary.json')
r = read(O / 'result.json')
obs = read(A / 'artifacts/observations/summary.json')
assert s['completed'] == obs['completed'] == 51
rows = r['cases']
metric = s['final_answer_excluded']
seq = read(O / 'sequential-execution.json')
archives = [read(p) for p in O.glob('*/raw-archive.json')]
failures = [x['case_id'] for x in rows if x['http_status'] != 200]
complete = len(rows) - len(failures)
top = '| 실제 질문 | 최종 답변 제외 호출 | LLM 시간 | 응답 |\n|---|---:|---:|---|\n'
for x in s['final_answer_excluded_top_calls']:
    q = x['question'].replace('\n', ' ').replace('|', '\\|')
    top += f"| [{x['case_id']}](artifacts/run-001/{x['case_id']}/answer.txt) {q} | {x['calls']} | {x['seconds']:.1f}초 | {x['http_status']} |\n"
phase = '| 구간 | 물리 호출 | API 시간 합계 | 입력/출력 토큰 |\n|---|---:|---:|---:|\n'
labels = {'entry': '앞단 해석·검색 선택', 'navigation': '탐색 선택·읽기·종료 판단',
          'reference': '명시 참조 연결 선택', 'investigation_repair': '탐색 판단 수정',
          'assessment': '답변·중간 판단·해당 수정', 'other_investigation': '기타 탐색'}
for k, v in obs['by_phase'].items():
    phase += f"| {labels.get(k, k)} | {v['calls']} | {v['seconds']:.1f}초 | {v['input_tokens']:,} / {v['output_tokens']:,} |\n"
usage = {k: sum(x['usage'][k] for x in rows) for k in ('input_tokens', 'output_tokens', 'cost_usd')}
counts = ' · '.join(f'{k}회 {v}문항' for k, v in metric['calls_distribution'].items())
search_counts = {k: sum(x[k] for x in rows) for k in ('structure_search', 'fulltext_global', 'fulltext_scoped', 'research', 'returns', 'assessment_reentries')}
sections = [
    ('결정 요약', f'사용자가 승인한 CM51을 **한 문항씩 51/51회** 실행하고 기록을 검증했다. '
     f'답변 반환 {complete}/51, 실패 {len(failures)}/51. **최종 답변 제외 평균 {metric["calls_mean"]:.2f}회·{metric["seconds_mean"]:.1f}초**, '
     f'중앙값 {metric["seconds_median"]:.1f}초, p95 {metric["seconds_p95"]:.1f}초, 최대 {metric["seconds_max"]:.1f}초다. '
     '중간 판단·재조사·수정은 포함하고, 마지막 답변 작성·수정 묶음 및 코드/캐시 시간은 제외했다. 최종 작성 실패에도 같은 기준을 적용하며 전체 소모량은 별도 보존했다. '
     'MAIN50 제품 코드·활성 포인터와 GENOS는 변경하지 않았다.\n\n'
     '[51개 실제 질문·호출·시간](artifacts/run-001/questions.md) · [CSV](artifacts/run-001/questions.csv) · '
     '[모든 물리 호출 CSV](artifacts/observations/physical-calls.csv) · [실제 이동 경로](artifacts/run-001/traces.md).'),
    ('문제와 변경 전 구조', '단독 CM018의 빠른 탐색만으로 여러 규정을 넘나드는 질문도 안정적인지 판단할 수 없었다. '
     'CM51 전체에서 탐색, 참조 이동, 조사 종료 뒤 재진입, 판단 수정, 최종 답변 작성을 분리해 측정했다. '
     'ADR0716은 3개 요청 초기화 중 중단되어 모델 전송 기록이 없고, 사용자 순차 실행 지시에 따라 이 ADR에서 새로 동결했다. '
     '이전 중단이 OOM 때문이라는 증거는 확보하지 못했다.'),
    ('가설과 사전 판정 기준', '[criteria.json](artifacts/design/criteria.json)을 호출 전에 고정했다. '
     '사전 주 지표는 memory-assess 전체를 뺀 순수 탐색 호출·시간이며, 중간 판단을 포함한 마지막 assessment 직전 지표도 사전 선언했다. '
     '6회 이상·60초 이상·복수 원문/읽기·재검색/복귀/재진입을 관찰 대상으로 정했다. 실패도 포함하며 결과 확인 후 재호출하지 않았다.\n\n'
     '보고 시 보정한 파생 지표: CM019처럼 마지막 assessment가 답변이 아니라 NEEDS_INVESTIGATION이고 이후 실패할 수 있다. '
     '사용자용 「최종 답변 제외」는 마지막 작성 묶음의 실제 응답이 ANSWER/LIMITED_ANSWER인 경우 검증 성공 여부와 관계없이 작성 시간을 제외한다. '
     '마지막 응답이 NEEDS_INVESTIGATION이면 중간 판단이므로 포함한다. 단순히 실패 여부로 모든 호출을 포함하던 중간 집계는 이 역할 기준으로 보정했다. '
     '사전 지표와 원시 기록은 수정하지 않았고 파생 지표의 계산식은 summarize.py 및 summary.json에 명시했다. '
     f'기록 완결성 검사: {r["checks"]}.'),
    ('실험 설계', '완료 부모 ADR0712-experiment-v1/compact, 측정 arm measured-main50 하나, known in-sample probe다. '
     '선택 MAIN50의 287개 서빙 파일과 후보 snapshot을 byte 단위로 대조했다. 제품 코드/프로필/데이터 변경과 비교 arm은 없다. '
     '각 질문은 새로운 앱·세션·runtime·감사 client로 한 번 실행하되, 단일 Python worker가 불변 자료 캐시를 재사용했다. '
     '한 요청의 완료·무결성 검사·무손실 압축을 끝낸 후 다음 요청을 시작했다. '
     f'실제 프로세스 {seq["process_ids"]}, 요청 순서 비중첩 검사 {seq["ordered_nonoverlapping_cases"]}.'),
    ('데이터·모델·재현성', '기존 cm 51문항의 질문과 업무 문맥을 원문 그대로 사용했다. 별도 risk_cm 105문항은 대상이 아니다. '
     '승인된 공개65문서만 제품 범위로 설정했다. 과거 기준답변과 98개 참조 좌표는 오프라인 전용이며 제품 입력에 넣지 않았다. '
     '외부 전송은 사용자의 「이번 CM 51문항 외부 실험 승인」을 별도 영수증으로 보존했고 원본 패키지의 미승인 플래그는 변경하지 않았다. '
     'Qwen3.8 qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none / fallback 없음. '
     f'실제 응답 model/provider 확인 {obs["model_and_provider_verified"]}. '
     '선택 릴리스 compact-input-20261009-r1 / 포인터50 / 원문 term-source-8729f978a28924cb8c5b. '
     '[동결 지문](artifacts/design/freeze.json), [기준 binding](artifacts/design/baseline.json), [전송 승인](artifacts/question-export-authorization.json).'),
    ('결과', f'호출 분포: {counts}. HTTP 분포: {s["http_statuses"]}. '
     f'실제 반환 상태: {obs["response_outcomes"]}. ANSWER/LIMITED_ANSWER는 모델의 상태이며 독립 정답률이 아니다.\n\n' + top +
     '\n[전체51 표](artifacts/run-001/questions.md), [질문별 원시 기록 연결](실험/README.md). '
     '독립 의미 정답률·비교쌍 회귀율은 측정하지 않았다. 단일 arm이므로 paired delta는 해당하지 않는다.'),
    ('사례별 오류 분석', '직접 참조 이동은 CM004(상장규정26조→시행세칙23조), CM006(상장규정27조→시행세칙21조) 등에서 나타났다. '
     'CM051 「보유비율은 어떻게 산정하는가?(공동주관회사 선임의무)」는 원문 읽기1회 뒤 FINISH를 세 번 적용했다. '
     '두 번의 재조사에서 새 원문·검색 없이 종료했고, 중간 판단·수정4회에129.0초를 썼다. '
     '순수 탐색5회30.3초에 그 중간 판단을 포함하면 최종 작성 제외9회159.3초가 된다. 필요한 시행규칙14조 원문은 승인 범위에 존재하지만 읽지 않았다. '
     'CM014는 질문의 기준시가와 업무 문맥의 부여요건을 함께 질문으로 확장하고, 부여 절차 조문을 읽은 뒤 종료·재조사를 두 번 반복했다. '
     'CM016은 시행령 위임 요건이 빠졌는데 COVERED로 표시했다가 수정·재조사했다. '
     'CM019는 전체 조문이 입력에 있는데도 그 안의 부분을 두 번 다시 선택했고, 후속 재조사에서 decision_retry의 이전 입력과 새 입력이 충돌해 실행 오류가 났다. '
     'CM021·032·041은 마지막 답변 조건 연결 검증을 수정 후에도 통과하지 못했고, CM030은 채택 근거 없이 종료하려다 실패했다. '
     f'전체 실패: {", ".join(failures) or "없음"}.\n\n'
     '[근거 있는 사례 관찰](artifacts/trace-inspection-notes.json) · [CM019 실제 입력 동일성 증명](artifacts/observations/cm-019-redundant-read-proof.json). '
     '모든 호출 이상 사례의 이유·행동·수정 원문은 [이동 기록](artifacts/run-001/traces.md)과 질문별 observations에 보존했다.'),
    ('비용·지연·회수 규모', phase + f'\n전체 물리 호출 {s["all_model_calls"]}회, 입력 {usage["input_tokens"]:,}·출력 {usage["output_tokens"]:,}토큰, '
     f'공급자 기록 비용 ${usage["cost_usd"]:.6f}. 순수 탐색 사전 주 지표 평균 {s["main"]["calls_mean"]:.2f}회·{s["main"]["seconds_mean"]:.1f}초. '
     f'검색·이동 이벤트 합계 {search_counts}. '
     '후보 카탈로그 수는 메타데이터 수이며 전부 모델에 읽힌 본문 수가 아니다. 확보·모델 전달·채택은 질문 표와 회수 원장에 구분했다. '
     f'질문 완료 시점 RSS 최대 표본 {seq["rss_after_case_max_kib"]/1024/1024:.2f}GiB, 다음 질문 시작 전 여유 메모리 최소 표본 {seq["available_before_case_min_mib"]}MiB. '
     '요청 도중의 최대 메모리는 따로 계측하지 않았다. '
     f'원시 기록 {sum(x["original_bytes"] for x in archives)/1e6:.1f}MB → {sum(x["archive_bytes"] for x in archives)/1e6:.1f}MB로 무손실 압축하고 파일별 해시를 확인했다.'),
    ('해석', '세 번의 짧은 경로는 앞단 해석·읽을 원문 선택·채택/종료 판단이다. 참조를 더 읽는 정상 조사와, '
     '답변 단계에서야 부족함을 발견하여 다시 조사하는 경로를 구분해야 한다. '
     '같은 검색식의 fulltext 반복은 확인하지 못했다(46개 지문 이벤트 검사); 이미 전달한 부분의 다시 읽기는 별개로 존재했다. '
     '관찰된 개선 후보는 질문 본문과 업무 문맥의 역할 구분, 새 근거 없는 재조사에서 반복되는 종료 판단과 회차마다 초기화되는 무진행 상태, '
     '이미 전달한 상위 조문에 포함되는 부분 읽기 선택, 재조사 진입 시 이전 수정 상태 처리다. '
     '이번 실행에서 이를 수정하지 않았다. 동시 A/B나 원인 분리 실험이 아니므로 관찰된 연쇄를 개선 효과의 인과 증명으로 사용하지 않는다.'),
    ('한계와 일반화 가능 범위', '각 질문을 한 번 실행한 외부 모델 로컬 진단이다. 질문 간 분포를 측정한 것이며 같은 질문을 반복했을 때의 안정성은 미측정이다. '
     '공급자 부하·네트워크·생성 시간이 API 지연에 합쳐져 있으며 따로 분리하지 않았다. '
     '과거 참조 근거 전달률과 인용 문자열 일치는 현행 법률 정답률이 아니다. '
     'CM013처럼 좁은 조문만 읽고 빨리 종료하는 사례도 있어 속도만으로 답변 완전성을 판단할 수 없다. GENOS 모델·현장 성능은 확인하지 않았다.'),
    ('운영 결정·롤백 조건', 'Proposed / probe / in_sample=true / decision_eligible=false. 진단 결과이며 운영 승격 근거로 사용하지 않는다. '
     '선택 MAIN50과 동일 코드로 측정했고 MAIN 포인터·제품 코드·원문 세대·GENOS는 변경하지 않았다. '
     '[최종 관찰 검사](artifacts/final-observation-audit.json)에서 반환46건의 표시 호출·시간, 모든273회 모델/provider, 원시 압축 해시, 작업·후보·선택 릴리스의287파일을 대조했다. '
     '실패와 원본 기록은 그대로 보존했다. 수정 후보 또는 완료 사례 재실행은 새 ADR에서 조건을 동결한다. '
     '전체 저장소 graph에 남아 있는 과거 오류8건은 이번 ADR와 분리하여 검증 기록에 명시한다.'),
    ('재현 명령', '기록 읽기: 06_TOOLS/EXPERIMENTS/adr_0717/summarize.py, observe.py, report.py. 이들은 외부 모델을 호출하지 않는다. '
     'run_worker.py는 1개 질문씩 실행하며 기존 완료 질문을 건너뛰고 중단/미검사 기록이 있으면 자동 재호출하지 않는다. '
     '각 raw.tar.gz는 새 빈 폴더에 복원하고 raw-archive.json의 모든 파일 해시·크기를 확인한다. '
     '최종 검사: .venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path ' + str(A.relative_to(R)) + ' --final 및 graph. '
     '정확한 최종 검사 결과는 artifacts/validation-status.json을 따른다.'),
]
front = (A / 'README.md').read_text().split('---', 2)[1]
(A / 'README.md').write_text('---' + front + '---\n\n' + '\n\n'.join(f'## {i}. {title}\n\n{body}' for i, (title, body) in enumerate(sections, 1)) + '\n')
print('Wrote completed51 diagnostic report with observed limitations.')
