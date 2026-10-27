"""Record one isolated defect recheck without changing its frozen execution."""
import json, sqlite3, sys
from common import ROOT,ADR,ART,read,save,sha
def rel(p):return str(p.relative_to(ROOT))
f=read(ART/'design-freeze.json');code=ROOT/f['code_root']
assert all(sha(code/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/n)==h for n,h in read(ART/'preservation.json')['files'].items())
d=ART/'matrix/001-cm-023-A0';r=read(d/'result.json');v=read(d/'metrics.json')
assert r['completed'] and v['request_acl_check']=='CHECKED'
budgets=[];views=[]
for p in sorted(d.glob('runtime/legal-agent/runs/*/*/journal.sqlite')):
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    for body, in db.execute("SELECT payload_json FROM event WHERE kind='MODEL_INPUT_BUDGET' ORDER BY seq"):
        body=json.loads(body);budgets.append({k:body.get(k) for k in ('source_stage','status','measured_chars','max_context_chars')})
    for body, in db.execute('SELECT body_json FROM model_view ORDER BY created_seq'):
        body=json.loads(body)
        if 'read_candidates' in body:
            views.append({'feedback':body.get('search_feedback'),'canonical_field_chars':sorted(
                [{'field':k,'chars':len(json.dumps(x,ensure_ascii=False,separators=(',',':')))} for k,x in body.items()],key=lambda x:x['chars'],reverse=True)[:8]})
    db.close()
sys.path.insert(0,str(code/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import build_run_artifact,build_experiment_artifact
case=read(d/'retrieval-ledger-case.json')
run=build_run_artifact('run-001',[case],{'grouped-query':['original_read','delivered','final_cited']})
save(ART/'retrieval-ledger.json',build_experiment_artifact('ADR-1057','ADR-1057-experiment-v1',[run]))
tested=read(ART/'release-check-v2-summary.json');api=read(ART/'frozen-api-v2-summary.json')
assert tested['status']==api['status']==0
live={'status':'complete','case_id':'cm-023','arm':'A0','service_status':r['service_status'],
      'service_outcome':r['outcome'],'answer_coverage':v['answer_coverage'],'accepted_outcome':v['outcome'],
      'calls':r['model_calls'],'usage':v['usage'],'seconds':r['seconds'],'peak_rss_kib':r['peak_rss_kib'],
      'source_integrity':v['source_integrity'],'request_acl_check':v['request_acl_check'],
      'input_budgets':budgets,'read_view_diagnostics':views,
      'failures':[{k:x.get(k) for k in ('error_code','error_message','stage')} for x in r['native_failures']],
      'parser_admitted':bool(views),'legal_accuracy':None,'quality_certified':False,
      'contract_passed':tested['passed'],'frozen_api_passed':api['passed'],
      'code_files':len(f['files']),'code_root':f['code_root'],
      'parent_preserved':True,'main_unchanged':True,
      'metrics_path':rel(d/'metrics.json'),'metrics_sha256':sha(d/'metrics.json'),
      'response_path':rel(d/'response.json'),'response_sha256':sha(d/'response.json')}
save(ART/'live-result.json',live)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'live-result.json'))
m['dataset'].update(frozen_source=rel(ART/'design-freeze.json'),sha256=sha(ART/'design-freeze.json'))
last=case['stages'][-1];n=last['after_count'];gold=last['gold_after']/case['gold_total']
m['retrieval_accounting'].update(corpus_total=v['corpus_total_article_roots'],
    before_filter={'status':'unavailable','reason':'Full candidate set was not captured; never inferred from top-k pages'},
    after_filter={'status':'unavailable','reason':'Only exact original-read, delivered and final-cited sets measured'},
    presented_total=n,presented_mean=n,presented_p50=n,presented_p95=n,
    golden_recall=gold,selectivity=n/v['corpus_total_article_roots'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
m['results']={'status':'complete','by_arm':{
    'baseline':{'status':'complete','total':0,'correct':None,'accuracy':None,'reason':'Completed1056 reference only'},
    'grouped-query':{'status':'complete','total':1,'correct':None,'accuracy':None,
        'parser_admitted':bool(views),'service_outcome':r['outcome'],'answer_coverage':v['answer_coverage']}},
    'comparisons':[],'judge_disagreements':None,'usage':v['usage'],
    'latency':{'seconds':r['seconds']},'error_taxonomy':[x['error_code'] for x in r['native_failures']]}
question=next(x['question'] for x in read(ROOT/f['product_cases_path'])['cases'] if x['case_id']=='cm-023')
filename='질문-001-cm-023.md';q=ADR/'실험'/filename
q.write_text(f'''# 질문001 — CM023

## 1. 실행 메타
ADR-1057-experiment-v1 / run-001 / grouped-query (A0). Qwen3.8 실제 API. 원기록 exact. 코드 {f['code_root']}.

## 2. 사용자 질문 원문
{question}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개
1056과 같은 승인 evaluator 파일을 [동결 목록](../artifacts/design-freeze.json)의 경로와 해시로 참조한다. 제품에 넣지 않았고 의미 채점도 하지 않았다.

## 4. 제품 입력을 구성한 원값
[실제 요청](../artifacts/matrix/001-cm-023-A0/request.json), [모델 입출력·schema·usage](../artifacts/matrix/001-cm-023-A0/model/), [원문·상태](../artifacts/matrix/001-cm-023-A0/runtime/). 중복 복사를 피하고 원기록을 참조한다.

### 회수·탈락 단계 원장 — run·arm별
[원문 읽기·전달·인용 좌표](../artifacts/retrieval-ledger.json). 제품 선택 후 gold를 결합했고 원문 부분 확보율은 metrics의 required_targets에서 별도 표시한다. 관찰하지 않은 전체 후보는 미확정이다.

## 5. 제품 모델 호출 — run·arm별 실제 원문
제품과 중간 단계 전체는 model/call 순번별 request.json, response.json, validation-schema.json, 압축 wire에 보존한다. [최종 응답](../artifacts/matrix/001-cm-023-A0/response.json), [실행 결과](../artifacts/live-result.json).

## 6. 중간 LLM 호출 — router/compiler/verifier/repair
제품 기록에 모든 중간 호출을 포함하며 검색어 변환은 로컬 코드다. 새 모델 호출·재시도 계층 없음. 최초1056의 실패 기록과 합산하거나 덮어쓰지 않는다.

## 7. 채점 호출과 반복 판정
judge0회. 원문·권한·정확한 전달 검사만 실제 저장 기록으로 수행했다. 법률 정답 인증 없음.

## 8. 사례 최종 판정
서비스 {r['service_status']} / {r['outcome']}, 답변 범위 {v['answer_coverage']}. 검색식 진입 {bool(views)}. 이후 입력 한도나 판단 오류는 검색식 오류와 별개로 기록한다.
''')
m['questions']=[{'number':1,'case_id':'cm-023','file':filename,'sha256':sha(q)}]
save(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n'+f'''
# ADR-1057: 검색어 원 단어 보존

## 1. 결정 요약
1056에서 재현한 ‘요건’ 검색식 거부를 고쳤다. 유효 단어에 내용어 형태소가 없으면 정규화한 원 단어를 인용 검색식으로 보존한다. 조건을 버리거나 OR로 넓히지 않는다. 격리 후보 구현·실제 CM023 A0 재검증이며 MAIN·GENOS 미반영이다.

## 2. 문제와 변경 전 구조
PeCab의 문맥 없는 단독 ‘요건’ 분석이 NP여서 내용어 필터가 빈 목록을 만들었다. 컴파일러가 유효한 검색식을 거부하여 모델이 같은 검색식을 보완해도1056에서2호출 뒤 중단됐다.

## 3. 가설과 사전 판정 기준
[구현 전 기준](artifacts/implementation-plan.json). 같은 실제 검색식 허용, AND/OR·구문 경계 보존, 실제 불일치/0건 유지, 원문·권한·상태와 기존 한도 유지. 문장부호·금지 연산자는 계속 거부한다.

## 4. 실험 설계
완료1056/grouped-query를 정확한 부모로 삼았다. 같은 CM023 A0 한 문항, 같은 데이터·모델·프롬프트·예산. 기존 실패를 보고 만든 in-sample 결함 재검증이며 정답률 비교가 아니다. [실행 동결](artifacts/design-freeze.json).

## 5. 데이터·모델·재현성
703파일 rev-002. 초기 rev-001의 정책 해시 결속 오류는 외부 호출 전 실제 어댑터 검사에서 검출했다. 기록·동결본을 보존하고 승인 grant 해시만 새 정책에 결속한 rev-002에서81검사와 같은 동결 API·어댑터2검사를 통과했다. 데이터·색인은 읽기 전용 공유이며 재구축하지 않았다.

## 6. 결과
검색식 진입 {bool(views)}. 서비스 {r['service_status']} / {r['outcome']}, 답변 범위 {v['answer_coverage']}. [실제 결과](artifacts/live-result.json), [답변](artifacts/matrix/001-cm-023-A0/response.json). 실행 완료는 질문 전체 해결이나 법률 정답 인증이 아니다.

## 7. 사례별 오류 분석
검색식 변환 오류와 이후 단계의 중단을 분리한다. 실제 단계별 입력 크기·실패 이유는 live-result의 input_budgets와 failures에 있다. 저장한 원문·미확인과 사용량을 유지한다. 연관 원문·상태 중복 축소는 이 결함 수정에 포함하지 않았다.

## 8. 비용·지연·회수 규모
실제{r['model_calls']}호출, {r['seconds']:.1f}초. 비용 ${v['usage']['cost_usd']['total']:.8f}, 입력{v['usage']['input_tokens']['total']:,}·출력{v['usage']['output_tokens']['total']:,}토큰. 원문 {v['source_integrity']['evidence_count']}span 검사, 불일치{v['source_integrity']['mismatch_count']}. 권한 검사 {v['request_acl_check']}. [회수 원장](artifacts/retrieval-ledger.json).

## 9. 해석
단독 품사 분석을 검색어 유효성 판단으로 쓰는 결함을 제거했다. 원 단어가 기존 색인에 없으면 검색0건일 수 있으며 이를 부재 증명으로 승격하지 않는다. 이 수정은 포괄적인 한국어 형태소 검색 품질 개선이나 모든 입력 한도 해결을 뜻하지 않는다.

## 10. 한계와 일반화 가능 범위
1문항 재검증이며 A1/A2·정답률 평가 없음. 기존 내용어 색인, 로컬 SQLite 적용 범위, 숫자/원문 인용의 독립 검증을 유지한다. 법률 의미는 미검증이다.

## 11. 운영 결정·롤백 조건
Proposed, in_sample=true, decision_eligible=false.1056 결과·MAIN 포인터·원문 세대 보존. 새 후보를 활성 기본값으로 선택하지 않았다. 최종 구조·계보 검사 결과는 별도 로그에 보존한다.

## 12. 재현 명령
`.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1057/run_matrix.py --inspect-only`

실행 완료 셀 재호출 없음. 새 후보/재실행은 새 ADR에서 동결한다. 실제 API, raw wire, 원문·상태 기록을 artifacts/matrix에서 확인한다.
''')
(ADR/'실험/README.md').write_text('# CM023 결함 재검증\n\n[질문별 기록](질문-001-cm-023.md) · [결과](../artifacts/live-result.json)\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md'
if ADR.name not in index.read_text():index.write_text(index.read_text()+f'\n- [ADR-1057: 검색어 원 단어 보존]({ADR.name}/README.md) — CM023 A0 실제 재검증, MAIN 보존.\n')
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1057','created_at':m['reservation']['created_at'],
    'files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact preserved experiment artifact',
              'contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='journal.sqlite'}
             for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and p.suffix!='.lock']})
print(json.dumps({k:live[k] for k in ('service_status','calls','answer_coverage','parser_admitted')},ensure_ascii=False))
