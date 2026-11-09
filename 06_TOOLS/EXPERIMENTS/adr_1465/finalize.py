"""Fill the ADR-1465 README and manifest results (hybrid initial search vs ADR-1464 vector-only)."""
from common import *
G=read(ART/'grades.json');S=G['stats'];g=S['grades']
def fill(readme,pairs):
    t=readme.read_text()
    for old,new in pairs:
        assert old in t,(old[:50]);t=t.replace(old,new,1)
    readme.write_text(t)
summary=('보류(Proposed 유지), 운영 배선 변경 없음. MAIN181 위 하이브리드 초기검색(벡터 상위 100 + 본문 검색 BM25 조문 순위, RRF k=60)으로 financial CM 51문항: '
 f"PASS {g['PASS']}·PARTIAL {g['PARTIAL']}·FAIL {g['FAIL']} vs ADR-1464(벡터만) 37·5·9. 해당 조문 있는 43문항 33/6/4 vs 34/2/7. 필수 조문 확보 74(하이픈 번호 정정 후)→77/98. "
 '나아짐 5(002·009·021·030·031), 나빠짐 6(007·008·036·041·047·049). 1회·in-sample·품질 인증 아님 — 통과 수 기준 개선은 확인되지 않음.')
fill(ADR/'README.md',[
 ('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',summary),
 ('TODO: 관찰된 문제, 기존 흐름, 재현 가능한 실패를 적는다.','ADR-1464(MAIN181 코드, 벡터만) 실패 상세: 질문 표현과 조문 표현이 달라 정답 조문이 벡터 순위 뒤로 밀리거나(009 18위, 031 37위, 029 102위) 화면에 있어도 고르지 않음. 본문 검색 순위를 더하면 질문 단어가 든 조문이 앞으로 올라올 것으로 보았다.'),
 ('### 가설\n\nTODO','### 가설\n\n벡터 순위와 본문 검색 순위를 합치면 필요한 조문이 첫 화면에 더 자주 오르고 통과 수가 늘어난다.'),
 ('TODO: primary metric, 비열등 한계, 허용 회귀 수, 비용·지연 한계를 실행 전에 고정한다.','design/criteria.json(실행 전 동결): 문항별 PASS/PARTIAL/FAIL(ADR-1464와 같은 규칙), 필수 조문 확보·첫 화면 위치, 원문/ACL/전송 불일치 0, 예산 500호출·$4·150분.'),
 ('### 반증 기준\n\nTODO','### 반증 기준\n\n원문/ACL/전송 불일치, 예산 초과, 통과 수 감소.'),
 ('| baseline | TODO | TODO | baseline |','| baseline | 참조만: ADR-1464 MAIN181 코드·벡터만 | 같은 51문항·같은 채점 규칙 | baseline |'),
 ('| candidate | TODO | TODO | candidate |','| candidate | MAIN181 + 벡터·본문 순위 합산(hybrid) | 같은 프로필·범위 44문서·같은 원문 세대 | candidate |'),
 ('- 데이터셋과 버전: TODO','- 데이터셋과 버전: financial CM 51(cm-field-core-e2e-v3), 원문 세대 latest-selection-20261015-r1(d4d1d8b4…)'),
 ('- frozen source와 SHA-256: TODO','- frozen source와 SHA-256: artifacts/design/live-cases.json '+sha(DES/'live-cases.json')),
 ('- 반복 수와 다수결: TODO','- 반복 수와 다수결: 문항당 1회, 다수결 없음'),
 ('- 법령·기준답변 버전 점검: TODO','- 법령·기준답변 버전 점검: 기준답변과 현재 저장 원문을 이 세션이 직접 대조, 판정 모델 없음'),
 ('| baseline | TODO | TODO | - | TODO | TODO |','| baseline | ADR-1464 벡터만(참조) | PASS37·PARTIAL5·FAIL9 | - | 291회·$1.41 | 중앙 68초·필수 74/98 |'),
 ('| candidate | TODO | TODO | TODO | TODO | TODO |',f"| candidate | 벡터+본문 하이브리드 | PASS{g['PASS']}·PARTIAL{g['PARTIAL']}·FAIL{g['FAIL']} | 나아짐5/나빠짐6 | {S['physical_calls']}회·${S['reported_cost_usd']:.2f} | 중앙 {S['request_seconds_median']}초·필수 {S['required_acquired']}/98 |"),
 ('| 비교 arm만 정답 | TODO | TODO |','| 비교 arm만 정답 | 4 | 002·009·021·031 (030은 FAIL→PARTIAL) |'),
 ('| 기준 arm만 정답(회귀) | TODO | TODO |','| 기준 arm만 정답(회귀) | 6 | 007·036·041·047·049(PARTIAL), 008(FAIL) |'),
 ('| 둘 다 정답 | TODO | TODO |','| 둘 다 정답 | 31 | artifacts/CM51_결과.csv |'),
 ('| 둘 다 오답 | TODO | TODO |','| 둘 다 오답 | 10 | PASS 아닌 문항 |'),
 ('| TODO | TODO | TODO | TODO |','| NOT_READ | 3/51 | 008·029·043 | 008은 하이브리드에서 정답 조문이 첫 화면 밖으로 밀림 |\n| MISREAD·MISLABEL | 2/51 | 010·022 | 읽은 조문의 다른 항으로 답함(그대로) |\n| NO_ANSWER | 1/51 | 012 | 원문 0건, 문서 되물음 |\n| 결론 유보·불완전·근거 다름 | 10/51 | 005·007·014·025·030·036·039·041·047·049 | 되물음·일부 누락 |'),
 ('| 전체 corpus | TODO | TODO |','| 전체 corpus | 요청 범위 44문서, 벡터 19문서 | article root 단위 |'),
 ('| 필터 전/후 후보 | TODO | TODO |','| 필터 전/후 후보 | 벡터 100 + 본문 조문(중앙 118) → 합쳐서 100 | 문항당, 본문만 들어온 후보 중앙 38 |'),
 ('| LLM 제시 수 | TODO | 평균·p50·p95 |','| LLM 제시 수 | 첫 화면 20 | 평균·p50·p95 |'),
 ('| golden recall | TODO | TODO |','| golden recall | 필수 조문 첫 화면 57/99(벡터 54), 확보 77/98 | ADR-1464 74/98 |'),
 ('| 제시 비율 | TODO | 제시 수 / 전체 corpus |','| 제시 비율 | 미집계 | 제시 수 / 전체 corpus |'),
 ('| LLM 호출·토큰·지연 | TODO | TODO |',f"| LLM 호출·토큰·지연 | {S['physical_calls']}회·${S['reported_cost_usd']:.3f}·결과 불명 0 | 요청 합계 {S['request_seconds_total']}초 |"),
 ('| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |',f"| run-001 | candidate | 51 | 51 | {S['physical_calls']} | 0 | ${S['reported_cost_usd']:.2f} | {S['request_seconds_total']}초 | 0 | 0 |"),
 ('TODO: 결과가 어떤 가정을 지지·반증하는지 사실과 추론을 분리한다.','사실: 하이브리드는 정답 조문의 첫 화면 위치를 일부 끌어올림(009 18→4위, 031 화면 밖→11위, 030 제2-6조 밖→7위·제2-4조 3→1위, 022 5→1위) 그러나 008(제13조 3위→밖)·007(유가 제13조 2위→밖)처럼 밀어낸 경우도 있음. 문항당 후보 100개 중 중앙 38개가 본문 검색에서만 들어온 후보로 바뀌었다. 통과 35 vs 37, 실패 6 vs 9, 확보 77 vs 74. 추론: 첫 화면 개선은 3건 정도이고, 나머지 차이(036·041·049의 결론 유보·단정 등)는 같은 질문 1회 실행 편차로 보인다. 하이브리드로 통과 수가 늘었다고 말할 근거는 없다.'),
 ('TODO: 인샘플 여부, 표본 크기, judge 변동성, 데이터·법령 버전 한계를 적는다.','51문항 모두 설계에 쓴 알려진 질문, 1회, 판정은 이 세션의 직접 대조. 1회 실행 편차가 개선 폭과 비슷해 반복 실행 없이는 효과를 분리할 수 없다. 하이브리드라 Oracle SQL·Agent 기록 미측정(Oracle 규모 점검은 별도 통과).'),
 ('TODO: 메인 배선 여부, 유지할 진단 부품, 롤백 trigger를 적는다.','MAIN 변경 없음. 코드는 GENOS_RAG_INITIAL_SEARCH=hybrid일 때만 동작(기본·vector·keyword 동작 불변)하며 MAIN181 위 stage·회귀 143파일 새 실패 0·Oracle 규모 점검(hybrid) 통과 상태. 반영 여부는 사용자 결정.'),
 ('```bash\nTODO\n```','```bash\ncd 06_TOOLS/EXPERIMENTS/adr_1465\npython setup.py && python embed_server.py --port 8765 ... & python live_hybrid.py cm-009 --preflight && python batch.py\npython audit.py && python collect_review.py && python grade.py && python finalize.py && python docs.py\n```'),
])
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',artifact_path=str((ART/'review-input.json').relative_to(ROOT)),sha256=sha(ART/'review-input.json'))
by={'questions':51,'pass':g['PASS'],'partial':g['PARTIAL'],'fail':g['FAIL'],'pass_rate':round(g['PASS']/51,3),**{k:S[k] for k in ('physical_calls','unknown','reported_cost_usd','request_seconds_total','request_seconds_median','required_acquired','required_cited','required_total','source_mismatches','acl_violations')}}
m['results']={'status':'complete','by_arm':{'candidate':by,'baseline':{'reference':'ADR-1464 MAIN181 code, vector-only','pass':37,'partial':5,'fail':9,'pass_rate':0.725,'required_acquired':'74 (73 counted + 1 hyphen-number correction)','physical_calls':291,'reported_cost_usd':1.411195}},
 'comparisons':[{'metric':'PASS','baseline':37,'candidate':g['PASS']},{'metric':'FAIL','baseline':9,'candidate':g['FAIL']},
  {'metric':'43 questions with a required provision','baseline':'34/2/7','candidate':'33/6/4'},
  {'metric':'required articles in the first menu (20)','baseline':'54/99','candidate':'57/99'},{'metric':'required acquired','baseline':74,'candidate':S['required_acquired']},
  {'metric':'transitions','improved':['cm-002','cm-009','cm-021','cm-030','cm-031'],'regressed':['cm-007','cm-008','cm-036','cm-041','cm-047','cm-049']},
  {'metric':'fusion','questions_fused':47,'lexical_only_kept_median':38,'both_median':28}],
 'judge_disagreements':None,'usage':{'physical_calls':S['physical_calls']},'latency':{'request_seconds_total':S['request_seconds_total'],'request_seconds_median':S['request_seconds_median']},
 'error_taxonomy':[{'kind':k,'cases':sorted(c for c,v in G['grades'].items() if v[1]==k)} for k in sorted({v[1] for v in G['grades'].values() if v[1]})],
 'deviation':'design/deviation.json (hybrid environment; inherited from ADR-1464)','grades_by':'this session; artifacts/grades.json'}
put(ADR/'실험/manifest.json',m)
print('ok')
