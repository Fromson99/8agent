"""Fill ADR-1464 (completed run) and ADR-1463 (resource stop on the first question) records."""
from common import *
import re
G=read(ART/'grades.json');S=G['stats']
def fill(readme,pairs):
    t=readme.read_text()
    for old,new in pairs:
        assert old in t,(readme,old[:40]);t=t.replace(old,new,1)
    readme.write_text(t)
summary=('보류(Proposed 유지), 운영 배선은 이 ADR에서 바꾸지 않음(사용자 지시에 따라 정의 우선순위 수정은 별도 main_release로 반영). '
 'MAIN179+탐색 수정 3파일+정의 우선순위 4가지·벡터 초기검색(하이브리드)으로 financial CM 51문항: PASS 37·PARTIAL 5·FAIL 9(72.5%), '
 'ADR-1461(MAIN178+3) PASS 25·PARTIAL 9·FAIL 17(49.0%). 필수 조문 확보 59→73/98, 인용 48→66. 첫 조사 행동 FOLLOW 32→6, READ 16→43. 1회·in-sample·품질 인증 아님.')
fill(ADR/'README.md',[
 ('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',summary),
 ('TODO: 관찰된 문제, 기존 흐름, 재현 가능한 실패를 적는다.','ADR-1461 진단: 미확보 12문항 대부분이 질문 속 용어의 정의 조문을 먼저 미리 읽고(첫 행동 FOLLOW 30여 건) 정의 연결을 따라가다 필요한 조문(벡터 상위 1~7위로 첫 메뉴에 있던 것 포함)을 고르지 않음. 다른 법령 정의(예: 금융회사지배구조법 제2조 감사)로 새는 경우도 있었다.'),
 ('### 가설\n\nTODO','### 가설\n\n정의를 묻지 않는 질문에서 정의 미리 읽기를 보류하고 정의 메뉴를 배경으로 표시하며, 벡터 상위·지정 문서 밖 법령의 정의를 빼고, 답변 전 벡터 상위 5위 중 질문 단어가 제목에 든 미열람 조문을 서버가 2개까지 읽으면 ADR-1461보다 통과 수와 필수 조문 확보가 늘어난다.'),
 ('TODO: primary metric, 비열등 한계, 허용 회귀 수, 비용·지연 한계를 실행 전에 고정한다.','design/criteria.json(실행 전 동결): 문항별 PASS/PARTIAL/FAIL(ADR-1424/1461 규칙), 필수 조문 확보·첫 행동·정의 판단 기록, 원문/ACL/전송 불일치 0, 예산 500호출·$4·150분.'),
 ('### 반증 기준\n\nTODO','### 반증 기준\n\n원문/ACL/전송 불일치, 예산 초과, 통과 수 감소.'),
 ('| baseline | TODO | TODO | baseline |','| baseline | 참조만: ADR-1461 MAIN178+3 하이브리드 결과 | 같은 51문항·같은 채점 규칙 | baseline |'),
 ('| candidate | TODO | TODO | candidate |','| candidate | MAIN179+3+정의 우선순위 4가지·벡터(하이브리드) | 같은 프로필·범위 44문서·같은 원문 세대 | candidate |'),
 ('- 데이터셋과 버전: TODO','- 데이터셋과 버전: financial CM 51(cm-field-core-e2e-v3), 원문 세대 latest-selection-20261015-r1(d4d1d8b4…)'),
 ('- frozen source와 SHA-256: TODO','- frozen source와 SHA-256: artifacts/design/live-cases.json '+sha(DES/'live-cases.json')),
 ('- 반복 수와 다수결: TODO','- 반복 수와 다수결: 문항당 1회, 다수결 없음'),
 ('- 법령·기준답변 버전 점검: TODO','- 법령·기준답변 버전 점검: 기준답변과 현재 저장 원문을 이 세션이 직접 대조, 판정 모델 없음'),
 ('| baseline | TODO | TODO | - | TODO | TODO |','| baseline | ADR-1461 MAIN178+3(참조, 미실행) | PASS25·PARTIAL9·FAIL17 | - | 308회·$1.03 | 중앙 55초·필수 59/98 |'),
 ('| candidate | TODO | TODO | TODO | TODO | TODO |','| candidate | MAIN179+3+정의 우선순위 | PASS37·PARTIAL5·FAIL9 | 나아짐13/나빠짐1 | 291회·$1.41 | 중앙 68초·필수 73/98 |'),
 ('| 비교 arm만 정답 | TODO | TODO |','| 비교 arm만 정답 | 13 | 004·006·007·008·013·020·027·041·042·044·047·048·049 |'),
 ('| 기준 arm만 정답(회귀) | TODO | TODO |','| 기준 arm만 정답(회귀) | 1 | 009(제13조⑥ 미확보, 제16조로 답함) |'),
 ('| 둘 다 정답 | TODO | TODO |','| 둘 다 정답 | 24 | artifacts/CM51_결과.csv |'),
 ('| 둘 다 오답 | TODO | TODO |','| 둘 다 오답 | 13 | PASS 아닌 문항 |'),
 ('| TODO | TODO | TODO | TODO |','| NOT_READ | 5/51 | 009·029·030·031·043 | 세칙·시행령 특정 항 미확보, 030은 반대 결론 |\n| MISREAD·MISLABEL | 2/51 | 010·022 | 읽은 조문의 다른 항으로 답함 |\n| PROCESSING_ERROR | 2/51 | 012·021 | "판단 처리 오류" 안내 |\n| 결론 유보·불완전 | 5/51 | 002·005·014·025·039 | 근거를 찾고 결론 대신 되물음 또는 일부 누락 |'),
 ('| 전체 corpus | TODO | TODO |','| 전체 corpus | 요청 범위 44문서, 벡터 19문서 | article root 단위 |'),
 ('| 필터 전/후 후보 | TODO | TODO |','| 필터 전/후 후보 | 벡터 상위 150 단위 → 원문 100 | 문항당 |'),
 ('| LLM 제시 수 | TODO | 평균·p50·p95 |','| LLM 제시 수 | 미집계 | 평균·p50·p95 |'),
 ('| golden recall | TODO | TODO |','| golden recall | 필수 조문 확보 73/98·인용 66 | 1461: 59/98·48 |'),
 ('| 제시 비율 | TODO | 제시 수 / 전체 corpus |','| 제시 비율 | 미집계 | 제시 수 / 전체 corpus |'),
 ('| LLM 호출·토큰·지연 | TODO | TODO |','| LLM 호출·토큰·지연 | 291회·$1.411·결과 불명 0 | 요청 합계 3,806초·중앙 68.3초 |'),
 ('| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |','| run-001 | candidate | 51 | 51 | 291 | 0 | $1.41 | 3,806초 | 0 | 0 |'),
 ('TODO: 결과가 어떤 가정을 지지·반증하는지 사실과 추론을 분리한다.','사실: 통과 25→37, 필수 조문 59→73/98, 첫 행동 FOLLOW 32→6·READ 16→43, 정의 미리 읽기 보류 40문항(정의 질문 판단 true 11문항), 정의 문서 범위 거름 28문항, 답변 전 벡터 상위 조문 읽기 22문항. 기준답변상 해당 조문이 없는 8문항(005·012·025·033·036·039·043·044)을 뺀 43문항: 1461 23/6/14 → 34/2/7. 추론: 정의 연결로 새던 첫 조사가 질문 요건 조문 읽기로 바뀐 것이 주원인이고, 답변 전 벡터 읽기는 004·007·008·013·020·047·048처럼 필요한 조문이 상위에 있던 문항을 구했다. 비용은 1회당 읽는 원문이 늘어 $1.03→$1.41.'),
 ('TODO: 인샘플 여부, 표본 크기, judge 변동성, 데이터·법령 버전 한계를 적는다.','51문항 모두 ADR-1461 진단에서 수정 설계에 쓴 알려진 질문(in-sample), 1회, 판정은 이 세션의 직접 대조. 하이브리드라 Oracle SQL·Agent 기록 미측정. 4가지 수정 각각의 효과는 분리하지 않음. ADR-1463은 같은 설계로 첫 문항에서 자원 감시 중단(판정 0).'),
 ('TODO: 메인 배선 여부, 유지할 진단 부품, 롤백 trigger를 적는다.','이 ADR은 MAIN을 바꾸지 않는다. 사용자 지시("메인에 반영")에 따라 같은 제품 5파일을 다른 세션의 MAIN180 위에 main_release.py로 다시 stage·회귀·Oracle 규모 점검 후 반영한다(USER_DIRECTED_CUTOVER, 품질 인증 아님).'),
 ('```bash\nTODO\n```','```bash\ncd 06_TOOLS/EXPERIMENTS/adr_1464\npython setup.py && python embed_server.py --port 8765 ... & python live_hybrid.py cm-007 --preflight && python batch.py\npython audit.py && python collect_review.py && python grade.py && python first_actions.py <ADR-1464> <ADR-1461> && python events.py <ADR-1464>\n```'),
])
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',artifact_path=str((ART/'review-input.json').relative_to(ROOT)),sha256=sha(ART/'review-input.json'))
by={'questions':51,'pass':37,'partial':5,'fail':9,'pass_rate':round(37/51,3),**{k:S[k] for k in ('physical_calls','unknown','reported_cost_usd','request_seconds_total','request_seconds_median','required_acquired','required_cited','required_total','source_mismatches','acl_violations')}}
m['results']={'status':'complete','by_arm':{'candidate':by,'baseline':{'reference':'ADR-1461 MAIN178+3 hybrid','pass':25,'partial':9,'fail':17,'pass_rate':0.49,'required_acquired':59,'required_cited':48,'physical_calls':308,'reported_cost_usd':1.032024}},
 'comparisons':[{'metric':'PASS','baseline':25,'candidate':37},{'metric':'required articles acquired','baseline':'59/98','candidate':'73/98'},
  {'metric':'43 questions with a required provision (PASS/PARTIAL/FAIL)','baseline':'23/6/14','candidate':'34/2/7','excluded':['cm-005','cm-012','cm-025','cm-033','cm-036','cm-039','cm-043','cm-044']},
  {'metric':'first navigation choice','baseline':{'FOLLOW':32,'READ':16,'SEARCH':3},'candidate':{'READ':43,'FOLLOW':6,'SEARCH':2}},
  {'metric':'mechanism events (questions)','DEFINITION_ENTRY_DEFERRED':40,'DEFINITION_ENTRY_SCOPED':28,'GUIDED_ANSWER_VECTOR_READS':22,'asks_definition_true':11},
  {'metric':'transitions','improved':13,'regressed':1}],
 'judge_disagreements':None,'usage':{'physical_calls':S['physical_calls']},'latency':{'request_seconds_total':S['request_seconds_total'],'request_seconds_median':S['request_seconds_median']},
 'error_taxonomy':[{'kind':k,'cases':sorted(c for c,g in G['grades'].items() if g[1]==k)} for k in sorted({g[1] for g in G['grades'].values() if g[1]})],
 'deviation':'design/deviation.json (hybrid; inherited from ADR-1461/1459)','grades_by':'this session; artifacts/grades.json','rerun_of':'ADR-1463 (resource stop)'}
put(ADR/'실험/manifest.json',m)
# ADR-1463: resource stop on the first question
A3=ROOT/'04_EXPERIMENTS/ADR/ADR-1463-main179-definition-priority-cm51-qwen'
fill(A3/'README.md',[
 ('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.','첫 문항(cm-001)에서 자원 감시 중단(호스트 swap 30초 만에 +604MiB, 기준 512MiB). 원인은 같은 세션이 동시에 돌린 넓은 파일 검색(grep -r)으로 판단. 모델 1호출은 정상 응답(HTTP200, $0.00229), 판정 0, 나머지 50문항 미실행. 같은 설계로 ADR-1464에서 다른 작업 없이 다시 실행. 운영 배선 변경 없음.'),
 ('TODO: 관찰된 문제, 기존 흐름, 재현 가능한 실패를 적는다.','ADR-1461 진단의 정의 미리 읽기 쏠림을 고친 후보를 51문항으로 확인하려 했다.'),
 ('### 가설\n\nTODO','### 가설\n\nADR-1464와 같음.'),
 ('TODO: primary metric, 비열등 한계, 허용 회귀 수, 비용·지연 한계를 실행 전에 고정한다.','design/criteria.json(실행 전 동결), ADR-1464와 같음.'),
 ('### 반증 기준\n\nTODO','### 반증 기준\n\nADR-1464와 같음.'),
 ('| baseline | TODO | TODO | baseline |','| baseline | 참조만: ADR-1461 | 같은 51문항 | baseline |'),
 ('| candidate | TODO | TODO | candidate |','| candidate | MAIN179+3+정의 우선순위 | 같은 프로필·범위 | candidate |'),
 ('- 데이터셋과 버전: TODO','- 데이터셋과 버전: financial CM 51(cm-field-core-e2e-v3)'),
 ('- frozen source와 SHA-256: TODO','- frozen source와 SHA-256: artifacts/design/live-cases.json'),
 ('- 반복 수와 다수결: TODO','- 반복 수와 다수결: 문항당 1회(1문항에서 중단)'),
 ('- 법령·기준답변 버전 점검: TODO','- 법령·기준답변 버전 점검: 판정 없음'),
 ('| baseline | TODO | TODO | - | TODO | TODO |','| baseline | ADR-1461 | - | - | - | - |'),
 ('| candidate | TODO | TODO | TODO | TODO | TODO |','| candidate | 0/0 | - | - | 1회·$0.0023 | - |'),
 ('| 비교 arm만 정답 | TODO | TODO |','| 비교 arm만 정답 | 0 | - |'),
 ('| 기준 arm만 정답(회귀) | TODO | TODO |','| 기준 arm만 정답(회귀) | 0 | - |'),
 ('| 둘 다 정답 | TODO | TODO |','| 둘 다 정답 | 0 | - |'),
 ('| 둘 다 오답 | TODO | TODO |','| 둘 다 오답 | 0 | - |'),
 ('| TODO | TODO | TODO | TODO |','| resource_guard_stop | 1/1 | cm-001 | 동시 파일 검색으로 호스트 swap 증가 |'),
 ('| 전체 corpus | TODO | TODO |','| 전체 corpus | 요청 범위 44문서 | - |'),
 ('| 필터 전/후 후보 | TODO | TODO |','| 필터 전/후 후보 | 해당 없음 | - |'),
 ('| LLM 제시 수 | TODO | 평균·p50·p95 |','| LLM 제시 수 | 해당 없음 | - |'),
 ('| golden recall | TODO | TODO |','| golden recall | 해당 없음 | - |'),
 ('| 제시 비율 | TODO | 제시 수 / 전체 corpus |','| 제시 비율 | 해당 없음 | - |'),
 ('| LLM 호출·토큰·지연 | TODO | TODO |','| LLM 호출·토큰·지연 | 1회·$0.00229 | - |'),
 ('| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |','| run-001 | candidate | - | - | 1 | 0 | - | - | - | resource stop |'),
 ('TODO: 결과가 어떤 가정을 지지·반증하는지 사실과 추론을 분리한다.','판정 없음.'),
 ('TODO: 인샘플 여부, 표본 크기, judge 변동성, 데이터·법령 버전 한계를 적는다.','실행 중 다른 작업을 하지 않는다는 규칙을 이 세션이 어겼다(동시 grep -r).'),
 ('TODO: 메인 배선 여부, 유지할 진단 부품, 롤백 trigger를 적는다.','변경 없음. ADR-1464에서 재실행.'),
 ('```bash\nTODO\n```','```bash\n# ADR-1464 참조\n```'),
])
m3=read(A3/'실험/manifest.json')
m3['runs'][0].update(status='complete',artifact_path=str((A3/'artifacts/batch-completed.json').relative_to(ROOT)),sha256=sha(A3/'artifacts/batch-completed.json'))
m3['results']={'status':'complete','by_arm':{'candidate':{'correct':0,'total':0,'accuracy':None,'decision_eligible':False,'scope':'resource stop on the first question, nothing judged'}},'comparisons':[],'judge_disagreements':0,
 'usage':{'physical_calls':1,'unknown':0,'reported_cost_usd':0.00229136},'latency':{'median':None,'reason':'no answer returned'},'error_taxonomy':[{'type':'resource_guard_stop','case_id':'cm-001','reason':'global swap growth above 512MiB since admission; concurrent recursive file search in the same session'}]}
p=A3/'실험/manifest.json';p.write_text(json.dumps(m3,ensure_ascii=False,indent=2)+'\n')
print('ok')
