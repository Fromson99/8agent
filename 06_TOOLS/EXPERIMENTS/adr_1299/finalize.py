"""Publish the bounded diagnosis, preserving observed failures and all original inputs."""
from common import *
import re
F=read(DES/'freeze.json');run=read(RUN/'result.json');a=read(ART/'actual-audit.json')
assert all(run['calibration'].values()) and len(run['rows'])==12
assert all(x['source_text_preserved'] for x in run['rows'])
assert all(sha(ROOT/n)==h for n,h in F['inputs'].items())
assert all(sha(ROOT/n)==h for n,h in F['scripts'].items())
assert all(sha(ROOT/F['code_root']/n)==h and sha(ROOT/n)==h for n,h in F['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==F['pointer_sha256']
checks={'actual_generation_schema_exact':run['calibration']['generation_schema_exact'],'actual_wire_schema_exact':run['calibration']['provider_schema_exact'],
 'actual_user_bytes_exact':run['calibration']['provider_user_exact'],'all12_measured':len(run['rows'])==12,
 'all_sources_preserved':all(x['source_text_preserved'] for x in run['rows']),'no_model_calls':True,
 'working_frozen_selected_unchanged':True,'resource_stop':not (RUN/'resource-stop.json').exists()}
result={'status':'DIAGNOSIS_COMPLETE','checks':checks,'model_calls':0,'quality_certified':False,
 'causal_timeout_diagnosis':'NOT_ESTABLISHED','current_main':134,'candidate_files':539,
 'actual':a,'scaling_rows':run['rows'],'raw_scaling_result':str((RUN/'result.json').relative_to(ROOT)),
 'primary_findings':['Actual baseline ASSESS claims identical before and after review-link repair',
  'Ordinary input repeats exact question9 times and first source6 times; scenario wire both1',
  'Shared review links and lossless assessment factoring apply only to scenario requests',
  'At200 short originals, per-source-goal topology requires603 judgment/need/scope rows; bulk topology203',
  'Schema grows moderately due existing factoring, while data plus mandatory output ledger grow more sharply'],
 'limits':'Frozen ordinary ASSESS construction; no corpus retrieval, model generation, legal scoring, Oracle latency or provider context-fit trial. Added source rows are synthetic component fixtures; no fake publication or accepted answer.'}
put(ART/'diagnosis.json',result)
table='| 원문 수 | 입력 본문 KB | 출력 스키마 KB | 필수 검토행 |\n|---:|---:|---:|---:|\n'
for x in run['rows']:
 if x['mode']=='per-source' and x['extra_text_chars']==100:table+=f'| {x["source_count"]} | {x["user_bytes"]/1000:.1f} | {x["schema_bytes"]/1000:.1f} | {x["required_review_rows_total"]} |\n'
findings='''직접 중단 원인과 별개로 과도한 작성 부담이 확인됐다.

1. 최근 저액 가정 중단은 HTTP200 헤더 뒤 공백60조각660bytes만 수신하다 약180초에 기한이 끝난 것이다. 공급자 내부 원인은 알 수 없고, 스키마가 공백 응답을 일으켰다는 인과 증거는 없다. 초기1295의 기록기 오류는 이 현상과 다른 이미 보존된 실패다.
2. 기준 사건에서는 최초/보완의 claims 4개, issue_assessments, gaps가 모두 그대로였다. 보완은 검토표 needs 두 행의 C4 참조를 빼서 NEED_CLAIM_LINK·NEED_TARGET_CLAIM_LINK·SOURCE_WORK_CLAIM_LINKS를 해결했다. 답변 내용이 바뀌지 않아도 연결표를 맞추느라 실제 보완1회/17.730초/$0.00429687이 들었다. 이 연결의 검증을 없애자는 뜻은 아니며 동일 관계를 여러 곳에 작성시키는 부담이다.
3. 원문2개/고유본문450bytes인 실제 기준 ASSESS에서 출력 스키마22668bytes, 시스템 지침21171bytes, user 본문24204bytes였다. 실제 출력6110bytes 중 read_judgment_review+requirement_review가3317bytes(54.3%)였고 claims는2240bytes였다. 원문 판단·제외 이유도 이 검토표에 포함되므로54.3% 전부를 불필요하다고 세지 않는다.
4. 일반 RAG의 질문은9회, 첫 조문 원문은6회 전달됐다. 가정 검토에서는 각각1회다. assessment_input.applies는 hypothetical_scenario가 있을 때만 무손실 동일문자 공유를 적용하고, completion_execution의 shared_reviews도 scenario_context가 있을 때만 켠다. 일반 RAG에는 이미 만들어 둔 두 축소 기능이 적용되지 않는다.
5. 최종 검토는 모든 판단/need/범위 target에 행을 강제한다. 자료별 SOURCE_GOAL과 전체 STRUCTURE_SELECTION이 겹치면 같은 원문이 여러 범위에서 다시 검토된다. 읽기 완료라는 서버 사실, 해당 자료를 쓸지 말지의 의미 판단, 주장-근거 연결이 여러 표에 섞여 있다. 역할은 구분해야 하지만 동일 연결을 모델이 반복 작성할 필요는 줄일 수 있다.'''
priorities='''권장 수정 순서(이번에는 제품 수정하지 않음)

P1. 일반 ASSESS/보완에도 기존 무손실 입력 공유와 review_links를 적용한다. 현재/가정 의미를 바꾸지 않고 같은 원문/질문/주장-근거 조합만 재사용한다. 구형 저장 응답 reader, 보완 오류 경로, 원문·ACL·span/hash 검사는 유지한다.
P2. 조사 목적·전체 범위·개별 조문의 중첩을 서버에서 정리한다. 모델은 원문별 USE/EXCLUDE/OPEN와 이유, 실제 주장-근거 관계를 판단하고, 서버가 그 결과를 조사 작업/범위 장부에 연결한다. 서로 다른 제외·충돌·적용 범위의 의미 판단을 하나로 합치지 않는다. 유일성이 증명되는 연결만 복원한다.
P3. 이미 검토한 자료의 전체 장부를 새 답변마다 재작성하는 대신, 변경된 사실·질문·원문에 영향을 받는 검토만 다시 요구하는 계약을 설계한다. 영향 범위와 예외 연결 검증 전에는 과거 판단을 자동으로 유효하다고 재사용하지 않는다.
P4. 선택 가능한 원문·온톨로지 사용 연결은 짧은 참조 선택으로 표현하고 해시/좌표/버전은 서버가 복원한다. ontology_usage는 현재 선택적 필드이며, 사용을 기록할 때 package_sha256/path/node/claim을 요구한다. 미기록을 사용 성공으로 간주하지 않는다.

줄이면 안 되는 것: 실제 인용의 원문 일치, 문서 권한/판본, 미확인·예외 보존, 원래 모델 제안/실패, 상태·재개·예산 검증. 모든 스키마를 자유문으로 바꾸거나 자료를 임의 절단하는 방식은 이 진단의 제안이 아니다.'''
interpretation='''큰 자료에서 더 크게 증가하는 것은 스키마 문서 크기보다 모델 입력과 반드시 다시 작성할 검토행이다. 자료별 조사 목적1개와 전체 묶음1개를 둔 합성 조건에서 N개 원문은 judgments=N, needs=N+2, scope_reviews=N+1로 총3N+3행을 요구한다. scope_reviews 안의 groups와 requirement_review 행은 이 합계에서 제외했으므로 실제 전체 출력 필드 수가 아니다.

한 묶음으로만 읽은 통제 조건에서는200원문에203행이므로 회수 이력의 모양도 영향을 준다. 모든 실제 요청이603행이라는 뜻은 아니다. 추가 원문을1000자로 늘린200개 조건은 user본문606337bytes, 스키마34437bytes, 전체 요청680209bytes였다. 행 수는603으로 같았다. KB는1000bytes이고 토큰수/모델 컨텍스트 한도와 다르다. 기존 schema factoring 때문에2→10에서는 스키마가 약간 줄기도 했으며 단순 폭증이나 지수증가로 보고하지 않는다.

이번12조건은 현재MAIN134의 schema 생성→stable ID→minimal input/output→외부 wire 변환 함수만 실행한 가벼운 구조 검사다. 실제 기준 자료2개와 추가 합성 자료를 사용했으며 새 검색·모델·승인·Oracle 작업은 없다. 원문 수를 늘린 실제 모델의 답변 성공률/시간초과율은 별도 검증이 필요하다.'''
report=ROOT/'09_ARTIFACTS/AUDITS/20261103-main134-schema-scaling';report.mkdir(exist_ok=False)
(report/'문제와_과도한요구_자료증가_점검.txt').write_text(findings+'\n\n자료 수 증가 결과\n'+table+'\n'+interpretation+'\n\n'+priorities+'\n')
(report/'수치.json').write_text(json.dumps({'actual':a,'scaling':run['rows'],'checks':checks},ensure_ascii=False,indent=2)+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '진단 완료. 실제 계약 재작성 부담·일반RAG 중복입력·자료 증가에 따른 검토행 증가 확인. 제품/MAIN134 변경0. 모델 시간초과의 스키마 인과 원인은 미확정.',
 findings,
 '[실행 전 기준](artifacts/design/criteria.json). 실제 입력/schema 정확 재구성 후2/10/40/100/200원문과 읽기이력2형태, 긴원문2조건을 검사. 실제 응답/기준/실패를 소급 변경하지 않는다.',
 '선택515서빙/완료1292/동결539 동일. 12조건 고정·1회씩·같은 질문/사실/온톨로지/처음 두 원문. added 원문100자/1000자. per-source는자료별목적+전체묶음, bulk는전체묶음만. 모델가설 검증이나 법률 holdout이 아닌 구조probe.',
 '외부모델0·생성/채점0. 과거1297의 실제Qwen4/5/6 요청과 응답만 읽었다. 고정코드로 원래 generation schema 및 실제 user bytes/provider schema 정확 일치. 모든 원문문자 보존·raw gzip/hash. 현재 정책/MAIN 원문·DB·권한 설정 변경0.',
 table+'\n검증: '+json.dumps(checks,ensure_ascii=False),
 '실제1297 보완 전후 claims/issue_assessments/gaps 동일. 바뀐need행과 진단3코드는 actual-audit.json. 1297 저액UNKNOWN은 미완성 공백 응답으로 별개. 스케일 셀은 모의 답변을 생성/채택하지 않았으며 의미 정오 판정0.',
 '새모델 비용0. 측정단위는 UTF-8 bytes/필수배열행/구성요소 조립시간이며 토큰과 다르다. 원문2개는450bytes, 출력6110bytes 중 검토2표3317bytes.12회 구성요소는각약0.03~0.15초이나 서비스/Oracle/LLM속도 추정 아님. resource 표본1개 RSS약59.5MiB/가용약9GiB·감시중단0, 표본값을 실제peak로 부르지 않는다. 다른 세션의 무거운 모델 작업은 이 작은 입력함수 검사와 별개이며 전체 서비스 병렬성능을 주장하지 않는다.',
 interpretation,
 '단일 알려진 합성형태/짧은추가원문과 긴추가원문2조건. 실제 검색·native 전체승인·모델출력0. SOURCE_GOAL/STRUCTURE_SELECTION 토폴로지는 사전 고정한 모형, 모든실제작업의 행수 아님. 필수이름 occurrence/anyOf 대안 합계를 실제출력필드개수로 세지 않음. 새 사용자 대용량 실제모델/GENOS/Oracle 미검증.',
 priorities+'\nMAIN134 유지, 작업/선택/동결제품 동일. 수정 후보 구현·승격·자동게시0. 실패 원본 무변경.',
 'prepare.py→probe.py --preflight(정확재구성)→freeze.py→probe.py(12조건)→actual_audit.py(관측기록 분석)→finalize.py→hash/status/validate/graph. freeze.json의 입력/코드/스크립트 SHA에 결속. 완료셀 덮어쓰기 없음. 새로운 코드수정·성능비교는 새ADR.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
p.write_text('---'+front+'---\n\n# ADR1299 MAIN134 스키마와 자료 증가 진단\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_actual_wire':True},'verified':{'diagnosis':str((ART/'diagnosis.json').relative_to(ROOT)),'sha256':sha(ART/'diagnosis.json'),'checks':checks,'cells':12,'model_calls':0}},judge_disagreements=0,usage={'physical_model_calls':0,'cost_usd':0},latency={'scope':'component construction only'},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
sections=[('실행 메타','run-001/verified. 신규 외부모델0; 현재MAIN134 동일539파일. 실제 과거Qwen wire에 결속한 구조 점검.'),('사용자 질문 원문','문제가 뭔가 그리고 지금 우리 과도한 스키마를 요ㅗ구하는게 있나? 찾은데이터가 많아졌을때도 한번확읺배ㅘ'),('기준답변 — 채점 전용, 제품 입력 비공개','법률정답/외부judge없음. 사전 동결criteria의 정확재구성/무손실/규모별계수 검사. 제품에 정답 주입0.'),('제품 입력을 구성한 원값','design/inputs.json에 과거 실제 질문/원문/스키마/원응답 경로와SHA. 추가 합성 입력과 실제wire생성 결과는run-001/*.json.gz.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수미실행·집합필터/랭킹 변경0. 회수 후 자료 수/이력구조만 가정한 구성요소 점검.'),('제품 모델 호출 — run·arm별 실제 원문','신규0. 과거1297 physical4/5/6의 전체system/user/schema/원응답/partial은design/inputs의불변경로. 크기/중복/출력구성은actual-audit.json.'),('중간 LLM 호출 — router/compiler/verifier/repair','신규0. 과거보완에서 실제claims그대로/need참조수정만 확인. 이번합성입력은 모델에 보내지 않음.'),('채점 호출과 반복 판정','judge0.12조건 각1회·무손실/정확한코드경로검사, 표본p95·일반화 없음. 기존실패 재채점0.'),('사례 최종 판정','진단 완료. 구조부담확인, 시간초과와스키마 인과미확정. MAIN134 유지. 제품후속수정은 미구현.')]
(ADR/'실험/질문-001-schema-growth.md').write_text('# 구조 점검\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 구조 점검\n\n[질문](질문-001-schema-growth.md) · [manifest](manifest.json) · [결정](../README.md)\n')
print('Diagnosis report written; 12 cells, external0, MAIN134 unchanged')
