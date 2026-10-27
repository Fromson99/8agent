"""Close the three frozen cells; retain all failures and state/usage records."""
import json,sqlite3,statistics,sys
from common import ROOT,ADR,ART,read,save,sha
def rel(p):return str(p.relative_to(ROOT))
f=read(ART/'design-freeze.json');code=ROOT/f['code_root']
assert all(sha(code/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/n)==h for n,h in read(ART/'preservation.json')['files'].items())
sys.path.insert(0,str(code/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import build_run_artifact,build_experiment_artifact
cells=[];ledgers=[]
for cell in f['execution_order']:
    d=ART/'matrix'/f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"
    r=read(d/'result.json');v=read(d/'metrics.json')
    assert r['completed'] and v['request_acl_check']=='CHECKED'
    budgets=[];projections=[]
    for path in sorted(d.glob('runtime/legal-agent/runs/*/*/journal.sqlite')):
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            for kind,body in db.execute("SELECT kind,payload_json FROM event WHERE kind IN ('MODEL_INPUT_BUDGET','MODEL_INPUT_PROJECTION') ORDER BY seq"):
                body=json.loads(body)
                if kind=='MODEL_INPUT_BUDGET':budgets.append({k:body.get(k) for k in ('source_stage','status','measured_chars','max_context_chars')})
                else:projections.append({k:body.get(k) for k in ('attempt_id','navigation_values','bound_scope_references','navigation_cards_expanded','canonical_view_sha256','wire_view_sha256')})
    cells.append({**cell,'service_status':r['service_status'],'service_outcome':r['outcome'],
        'answer_coverage':v['answer_coverage'],'accepted_outcome':v['outcome'],'calls':r['model_calls'],
        'usage':v['usage'],'seconds':r['seconds'],'peak_rss_kib':r['peak_rss_kib'],
        'source_integrity':v['source_integrity'],'request_acl_check':v['request_acl_check'],
        'input_budgets':budgets,'input_projections':projections,
        'failures':[{k:x.get(k) for k in ('error_code','error_message','stage')} for x in r['native_failures']],
        'metrics_path':rel(d/'metrics.json'),'metrics_sha256':sha(d/'metrics.json'),
        'response_path':rel(d/'response.json'),'response_sha256':sha(d/'response.json')})
    ledgers.append(read(d/'retrieval-ledger-case.json'))
run=build_run_artifact('run-001',ledgers,{'compact-input':['original_read','delivered','final_cited']})
save(ART/'retrieval-ledger.json',build_experiment_artifact('ADR-1059','ADR-1059-experiment-v1',[run]))
live={'status':'complete','cases':cells,'physical_calls':sum(r['calls'] for r in cells),
    'http_200_cases':sum(r['service_status']==200 for r in cells),
    'input_budget_exceeded_events':sum(b['status']=='EXCEEDED' for r in cells for b in r['input_budgets']),
    'cost_usd':sum(r['usage']['cost_usd']['total'] for r in cells),
    'input_tokens':sum(r['usage']['input_tokens']['total'] for r in cells),
    'output_tokens':sum(r['usage']['output_tokens']['total'] for r in cells),
    'legal_accuracy':None,'quality_certified':False,'paired_quality_comparison':False,
    'note':'Three preselected in-sample A0 cases. Execution completion is distinct from full answer or semantic correctness.'}
save(ART/'live-result.json',live)
tested=read(ART/'release-check-summary.json');api=read(ART/'frozen-api-summary.json');replay=read(ART/'saved-input-replay.json')
save(ART/'result.json',{'status':'complete','contract_passed':tested['passed'],'frozen_checks_passed':api['passed'],
    'runtime_import_leaks':0,'main_unchanged':True,'files':len(f['files']),
    'saved_input_replay_path':rel(ART/'saved-input-replay.json'),'saved_input_replay_sha256':sha(ART/'saved-input-replay.json'),
    'live_result_path':rel(ART/'live-result.json'),'live_result_sha256':sha(ART/'live-result.json')})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'live-result.json'))
m['dataset'].update(name='Same3 approved MVP cases; original current generation',frozen_source=rel(ART/'design-freeze.json'),sha256=sha(ART/'design-freeze.json'),note='Evaluator references separate from product. No judge calls.')
counts=[r['stages'][-1]['after_count'] for r in ledgers];gold_total=sum(r['gold_total'] for r in ledgers);gold_after=sum(r['stages'][-1]['gold_after'] for r in ledgers)
m['retrieval_accounting'].update(corpus_total=v['corpus_total_article_roots'],
    before_filter={'status':'unavailable','reason':'No full pre-filter snapshot; not inferred from pages'},
    after_filter={'status':'unavailable','reason':'Read/delivered/cited ledger only'},
    presented_total=sum(counts),presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),
    presented_p95=sorted(counts)[round((len(counts)-1)*.95)],golden_recall=gold_after/gold_total if gold_total else None,
    selectivity=statistics.mean(counts)/v['corpus_total_article_roots'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
m['results']={'status':'complete','by_arm':{
    'baseline':{'status':'complete','total':0,'correct':None,'accuracy':None,'reason':'Completed1057 immutable reference; no live paired rerun'},
    'compact-input':{'status':'complete','total':3,'correct':None,'accuracy':None,
        'http_200_cases':live['http_200_cases'],'input_budget_exceeded_events':live['input_budget_exceeded_events']}},
    'comparisons':[],'judge_disagreements':None,
    'usage':{k:live[k] for k in ('physical_calls','cost_usd','input_tokens','output_tokens')},
    'latency':{'seconds_by_case':{r['case_id']:r['seconds'] for r in cells}},
    'error_taxonomy':sorted({x['error_code'] for r in cells for x in r['failures']})}
questions={r['case_id']:r['question'] for r in read(ROOT/f['product_cases_path'])['cases']};m['questions']=[]
for r in cells:
    n=r['ordinal'];cid=r['case_id'];d=f'../artifacts/matrix/{n:03d}-{cid}-A0';name=f'질문-{n:03d}-{cid}.md';p=ADR/'실험'/name
    p.write_text(f'''# 질문 {n:03d} — {cid}

## 1. 실행 메타
ADR-1059-experiment-v1 / run-001 / compact-input (A0), Qwen3.8 실제 API. 실행 완료와 질문 해결을 구분한다.

## 2. 사용자 질문 원문
{questions[cid]}

## 3. 기준답변 — 채점 전용
[동결 목록](../artifacts/design-freeze.json)의 승인 evaluator 경로·해시로 참조. 제품 입력 비공개, 의미 채점 미실행.

## 4. 제품 입력을 구성한 원값
[요청]({d}/request.json), [원문·상태]({d}/runtime/), [무손실 입력 재구성](../artifacts/saved-input-replay.json). 보고서에 본문을 복제하지 않는다.

### 회수·탈락 단계 원장 — run·arm별
[원문 읽기·전달·인용 좌표]({d}/retrieval-ledger-case.json). 제품 선택 뒤 gold를 결합했으며 전체 후보를 페이지에서 추정하지 않는다.

## 5. 제품 모델 호출 — run·arm별 실제 원문
[모델 입력·응답·schema·usage]({d}/model/), 호출 {r['calls']}회, [합산]({d}/metrics.json).

## 6. 중간 LLM 호출 — router/compiler/verifier/repair
위 원기록에 모두 포함한다. 입력 압축은 로컬 코드이며 추가 모델 호출·새 재시도 계층이 없다.

## 7. 채점 호출과 반복 판정
judge0회. 원문·권한·전달 검사만 실행. 법률 정답 인증 없음.

## 8. 사례 최종 판정
서비스 {r['service_status']} / {r['service_outcome']}, 답변 범위 {r['answer_coverage']}. [응답]({d}/response.json), [입력 크기·실패](../artifacts/live-result.json). 미확인은 유지한다.
''')
    m['questions'].append({'number':n,'case_id':cid,'file':name,'sha256':sha(p)})
save(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
size_rows='\n'.join(f"| {r['case']} / {r['source_stage']} | {r['original_request_chars']:,} | {r['reconstructed_request_chars']:,} | {r['reduction_percent']}% |" for r in replay['rows'])
case_rows='\n'.join(f"| {r['case_id']} | {r['service_status']} | {r['answer_coverage']} | {r['calls']} | {max((b['measured_chars'] for b in r['input_budgets']),default=0):,} |" for r in cells)
(ADR/'README.md').write_text('---'+front+'---\n'+f'''
# ADR-1059: 탐색 입력 중복 축소

## 1. 결정 요약
같은 읽기 판단에서 도구·연결·원문의 반복 값을 정확한 참조와 공통 필드 표로 보낸다. RESEARCH에 붙던1536개 내부 문서 ID는 서버가 원목록·권한·해시를 유지하고 도구 범위 참조로 전달한다. 필수 판단·원문·권한·상태 검증 및10만자 한도는 유지한다. 격리 후보이며 MAIN·GENOS 미반영이다.

## 2. 문제와 변경 전 구조
1058의 CM023 후속 입력에서 서버 메타데이터를 생략한 사본으로 안내를 검증하던 오류를 수정했다. 화면 형식 탐지와 서버 정본 검증을 나누며, 실제 실패 저장본의 준비·복원·예약 및 변조 거부 검사를 추가했다.1058은1완료·1실패·1미실행/12호출로 보존하고 부모 완료 실험으로 사용하지 않는다.

원문만이 아니라 도구의 허용 문서 ID 목록29,185자와 연결 근거의 반복 구조가 컸다. 후보 문서를 임의 제거하거나 원문을 잘라내는 변경은 없다.

## 3. 가설과 사전 판정 기준
[구현 전 계획](artifacts/implementation-plan.json), [실행 전 승인·한도](artifacts/live-probe-plan.json). 원문·선택지·범위·상태를 독립 저장본으로 복원하여 일치해야 하며4개 저장 READ 입력을10만자 안에 넣는다.

## 4. 실험 설계
완료1057/grouped-query를 부모로 삼은3문항 A0 순차 probe다. 사전에 관찰한 실패 사례의 in-sample 재검증이다. 정답률 비교나111회 재실험이 아니다.

## 5. 데이터·모델·재현성
[동결](artifacts/design-freeze.json): 같은 데이터·Qwen3.8·승인 제공자 경로,40호출·1024도구·1800초. 출력 상한 없음.{len(f['files'])}파일, 계약{tested['passed']}개 및 동결 코드{api['passed']}개 통과. 데이터·색인은 읽기 전용 공유한다.

## 6. 결과
저장된 총 요청 크기에 변경되는 직렬화 입력·안내의 정확한 차이를 적용했다. schema·단계 상태·나머지 안내는 고정했다. 실제 저장 요청이 있는1개는 전체 요청의 차이까지 대조했다. 이는 토큰 추정치가 아니다.

| 저장 입력 | 이전 문자 | 수정 후 문자 | 감소 |
|---|---:|---:|---:|
{size_rows}

실제 모델 실행 결과:

| 질문 | HTTP | 답변 범위 | 호출 | 최대 요청 문자 |
|---|---:|---|---:|---:|
{case_rows}

## 7. 사례별 오류 분석
[live-result](artifacts/live-result.json)에 단계별 한도·정확한 오류를 보존한다. 입력 초과 이벤트 {live['input_budget_exceeded_events']}개. 실행 완료·HTTP200·완전한 답·정답 여부는 각각 구분한다.

## 8. 비용·지연·회수 규모
실제 {live['physical_calls']}호출, ${live['cost_usd']:.8f}, 입력{live['input_tokens']:,}·출력{live['output_tokens']:,}토큰. [사용량·자원](artifacts/live-result.json), [회수 원장](artifacts/retrieval-ledger.json). 추가 judge 없음.

## 9. 해석
입력 복원은 내용·순서·타입을 검사하고 호출 예약 전에 저장 원문·상태와 결속한다. 비정상 참조·순환·변조·stale 상태는 모델 재시도로 우회하지 않는다. 범위 참조는 서버의 기존 허용 목록을 가리키며 권한을 확대하지 않는다.

## 10. 한계와 일반화 가능 범위
일부 표현을 공통 표로 읽는 실제 모델 판단 품질은 별도 평가가 필요하다. 데이터나 조사량이 더 커지면10만자를 다시 넘을 수 있다.3문항 A0 검사이며 A1/A2·정답률·GENOS 검증은 없다.

## 11. 운영 결정·롤백 조건
Proposed / in_sample=true / decision_eligible=false. 이전1056·1057 결과, MAIN 포인터, 원문 세대 해시를 보존했다. 새 후보는 기본값으로 선택하지 않았다.

## 12. 재현 명령
`.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1059/run_matrix.py --inspect-only`

완료 셀은 재호출하지 않는다. 실제 저장 입출력·원문·검증 결과는 artifacts/matrix에 있다. 새 실호출은 새 ADR에서 동결한다.
''')
(ADR/'실험/README.md').write_text('# 입력 중복 축소3문항\n\n[실행 결과](../artifacts/live-result.json) · [읽기·전달·인용](../artifacts/retrieval-ledger.json)\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md'
if ADR.name not in index.read_text():index.write_text(index.read_text()+f'\n- [ADR-1059: 탐색 입력 중복 축소]({ADR.name}/README.md) — 3문항 A0 검증, MAIN 보존.\n')
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1059','created_at':m['reservation']['created_at'],
    'files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved input optimization evidence',
        'contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='journal.sqlite'}
        for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and p.suffix!='.lock']})
print(json.dumps({k:live[k] for k in ('physical_calls','http_200_cases','input_budget_exceeded_events','cost_usd')},ensure_ascii=False))
