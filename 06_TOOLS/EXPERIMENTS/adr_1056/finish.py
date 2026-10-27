"""Close the three-case diagnostic; preserve failed cells and original wire data."""
import json
import sqlite3
import statistics
import sys
from common import ROOT, ADR, ART, read, save, sha

def rel(p): return str(p.relative_to(ROOT))

freeze=read(ART/'design-freeze.json')
code=ROOT/freeze['code_root']
assert all(sha(code/n)==h for n,h in freeze['files'].items())
assert all(sha(ROOT/n)==h for n,h in freeze['runner_hashes'].items())
assert all(sha(ROOT/n)==h for n,h in read(ART/'preservation.json')['files'].items())
sys.path.insert(0,str(code/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import build_run_artifact, build_experiment_artifact

cells=[]; ledgers=[]
for cell in freeze['execution_order']:
    d=ART/'matrix'/f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"
    result=read(d/'result.json'); metrics=read(d/'metrics.json')
    assert result['completed'] and metrics['request_acl_check']=='CHECKED'
    budgets=[]; views=[]
    for path in sorted(d.glob('runtime/legal-agent/runs/*/*/journal.sqlite')):
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
        for body, in db.execute("SELECT payload_json FROM event WHERE kind='MODEL_INPUT_BUDGET' ORDER BY seq"):
            v=json.loads(body)
            budgets.append({k:v.get(k) for k in ('source_stage','status','measured_chars','max_context_chars')})
        for body, in db.execute('SELECT body_json FROM model_view ORDER BY created_seq'):
            v=json.loads(body)
            if 'read_candidates' not in v: continue
            views.append({'feedback':v.get('search_feedback'), 'canonical_field_chars':
                sorted([{'field':k,'chars':len(json.dumps(x,ensure_ascii=False,separators=(',',':')))}
                    for k,x in v.items()],key=lambda r:r['chars'],reverse=True)[:8]})
        db.close()
    queries=[]
    p=d/'model/call-001-service/response.json'
    if p.exists():
        value=read(p)['choices'][0]['message']['content']
        if isinstance(value,str): value=json.loads(value)
        queries=value.get('queries',[])
    row={**cell,'service_status':result['service_status'],'service_outcome':result['outcome'],
         'answer_coverage':metrics['answer_coverage'],'accepted_outcome':metrics['outcome'],
         'calls':result['model_calls'],'seconds':result['seconds'],'peak_rss_kib':result['peak_rss_kib'],
         'usage':metrics['usage'],'source_integrity':metrics['source_integrity'],
         'request_acl_check':metrics['request_acl_check'],'queries':queries,'input_budgets':budgets,
         'read_view_diagnostics':views,
         'failures':[{k:r.get(k) for k in ('error_code','error_message','stage')} for r in result['native_failures']],
         'metrics_path':rel(d/'metrics.json'),'metrics_sha256':sha(d/'metrics.json'),
         'response_path':rel(d/'response.json'),'response_sha256':sha(d/'response.json')}
    cells.append(row);ledgers.append(read(d/'retrieval-ledger-case.json'))

run=build_run_artifact('run-002',ledgers,{'grouped-query':['original_read','delivered','final_cited']})
ledger=build_experiment_artifact('ADR-1056','ADR-1056-experiment-v1',[run])
save(ART/'retrieval-ledger.json',ledger)
live={'status':'complete','cases':cells,'fully_answered':0,'limited_answers':1,'native_failures':2,
      'physical_calls':sum(r['calls'] for r in cells),
      'cost_usd':sum(r['usage']['cost_usd']['total'] for r in cells),
      'input_tokens':sum(r['usage']['input_tokens']['total'] for r in cells),
      'output_tokens':sum(r['usage']['output_tokens']['total'] for r in cells),
      'legal_accuracy':None,'quality_certified':False,'paired_comparison':False,
      'note':'Three preselected in-sample A0 cases only. Completion of execution is separate from answer completeness.'}
save(ART/'live-result.json',live)
tested=read(ART/'release-check-summary.json'); repeat=read(ART/'frozen-api-summary.json')
save(ART/'result.json',{'status':'complete','validation_only':True,'contract_passed':tested['passed'],
    'contract_failed':tested['failed'],'frozen_api_passed':repeat['passed'],
    'known_baseline_failures':11,'runtime_import_leaks':0,'main_unchanged':True,
    'files':len(freeze['files']),'menu_diagnostic_path':rel(ART/'saved-menu-check.json'),
    'live_result_path':rel(ART/'live-result.json'),'live_result_sha256':sha(ART/'live-result.json')})

m=read(ADR/'실험/manifest.json')
# The original synthetic-only run is a validation receipt, not a live retrieval run.
# Keep its pre-call reservation and result; exclude it explicitly from measured runs.
m['runs'][0].update(status='invalid',sha256=sha(ART/'result.json'),
    invalid_reason='Synthetic validation completed, but is not a question-level retrieval run. Excluded from live ledger; 176 passing checks retained.')
m['runs'][1].update(purpose='audit',status='complete',sha256=sha(ART/'live-result.json'))
m['dataset'].update(name='Three preselected approved MVP cases, current shared source generation',
    frozen_source=rel(ART/'design-freeze.json'),sha256=sha(ART/'design-freeze.json'),
    note='Product questions and evaluator targets are separately hash-bound in design-freeze. No semantic judge; missing originals remain missing.')
counts=[r['stages'][-1]['after_count'] for r in ledgers]
gold_total=sum(r['gold_total'] for r in ledgers)
gold_after=sum(r['stages'][-1]['gold_after'] for r in ledgers)
accounting=m['retrieval_accounting']
accounting.update(corpus_total=metrics['corpus_total_article_roots'],
    before_filter={'status':'unavailable','reason':'No exact full pre-filter snapshot; not inferred from pages'},
    after_filter={'status':'unavailable','reason':'No exact full post-filter snapshot; read/present/cited ledger only'},
    presented_total=sum(counts),presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),
    presented_p95=sorted(counts)[round((len(counts)-1)*.95)],golden_recall=gold_after/gold_total,
    selectivity=statistics.mean(counts)/metrics['corpus_total_article_roots'])
accounting['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
m['results']={'status':'complete','by_arm':{
    'baseline':{'status':'complete','total':0,'correct':None,'accuracy':None,'reason':'Immutable code reference, no paired live rerun'},
    'grouped-query':{'status':'complete','total':3,'correct':None,'accuracy':None,'limited_answers':1,'failures':2}},
    'comparisons':[],'judge_disagreements':None,
    'usage':{k:live[k] for k in ('physical_calls','cost_usd','input_tokens','output_tokens')},
    'latency':{'seconds_by_case':{r['case_id']:r['seconds'] for r in cells}},
    'error_taxonomy':['MODEL_INPUT_BUDGET','CONTENT_TOKEN_EMPTY_LITERAL','SOURCE_INVESTIGATION_INCOMPLETE']}
questions={r['case_id']:r['question'] for r in read(ROOT/freeze['product_cases_path'])['cases']}
m['questions']=[]
for row in cells:
    n=row['ordinal'];cid=row['case_id'];d=f"../artifacts/matrix/{n:03d}-{cid}-A0"
    filename=f'질문-{n:03d}-{cid}.md'
    body=f'''# 질문 {n:03d} — {cid}

## 1. 실행 메타
ADR-1056-experiment-v1 / run-002 / grouped-query (A0). Qwen3.8, 실제 API, exact 원기록. 실행 완료와 답변 완료를 구분한다.

## 2. 사용자 질문 원문
{questions[cid]}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개
기존 승인 평가 파일의 해당 case를 [동결 목록](../artifacts/design-freeze.json) 경로·해시로 참조한다. 기준답변은 제품 입력에 넣지 않았고 의미 채점은 미실행이다.

## 4. 제품 입력을 구성한 원값
[실제 요청]({d}/request.json), [모델 원요청·응답·schema·usage]({d}/model/), [저장된 원문·상태]({d}/runtime/), [원문·권한 검사]({d}/evidence-audit.json). 본문을 보고서에 중복 복사하지 않는다.

### 회수·탈락 단계 원장 — run·arm별
[정확한 읽기·전달·인용 좌표]({d}/retrieval-ledger-case.json). 원장 gold 결합은 제품 선택 후 수행. 전체 후보 수와 원문 부분 확보율은 구분하며 페이지로 전수 회수를 추정하지 않는다.

## 5. 제품 모델 호출 — run·arm별 실제 원문
위 model 폴더의 call 순번별 request.json, validation-schema.json, response.json 및 무손실 압축 wire를 참조한다. [합산 사용량]({d}/metrics.json). 호출 {row['calls']}회, 서비스 상태 {row['service_status']}.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair
모든 제품·중간 호출은 같은 순번 기록에 포함한다. 검색식 변환은 로컬 코드이며 추가 모델을 부르지 않는다. 실패 후 임의 재호출은 없다.

## 7. 채점 호출과 반복 판정
judge 호출0회. 원문 일치·권한·정확한 실제 전달 범위는 [검사]({d}/metrics.json)에 기록했다. 법률 정답 여부는 미검증이다.

## 8. 사례 최종 판정
실행 상태 {row['service_outcome']}, 답변 범위 {row['answer_coverage']}. [최종 응답]({d}/response.json), [입력 크기·오류 진단](../artifacts/live-result.json). 후속 후보는 별도 ADR에서 검증한다.
'''
    p=ADR/'실험'/filename;p.write_text(body)
    m['questions'].append({'number':n,'case_id':cid,'file':filename,'sha256':sha(p)})
save(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n'+f'''
# ADR-1056: AI 검색식 묶음과 공통 법령 선택

## 1. 결정 요약
AI가 작성한 검색식의 AND·OR·구문 경계를 보존하고 전체 법령 목록과 공통 선택을 연결했다. 조문20개·더보기·필요 항호 읽기를 유지한다. 격리 후보 구현과 실제3문항 실행 완료. 결과는 제한 답변1, 중단2이며 완전 답변은0이다. MAIN·GENOS 미반영.

## 2. 문제와 변경 전 구조
기존 AI 검색어가 형태소 OR 목록으로 풀리면서 약한 단어·숫자 하나에 많은 법령이 걸렸다. 법령마다 반복된 선택 안내도 입력을 키웠다. 기존111개 실행의93개가 첫 읽기 판단 입력 한도에서 막혔다.

## 3. 가설과 사전 판정 기준
[구현 전 기준](artifacts/implementation-plan.json)과 사용자 후속 요청에 따른 [3문항 실행 전 기준](artifacts/live-probe-plan.json)을 보존한다. 원문·권한·상태·판단·예산을 유지한다. 검색효과나 정답률은 합성 검사만으로 인증하지 않는다.

## 4. 실험 설계
완료1055/delta-repair의702파일 계보를 동결했다. run-001은 합성 검사였으므로 실회수 원장 대상에서 invalid로 제외하고 통과 기록을 보존했다. run-002는 사전 지정3문항, A0, 한 개씩 실행한 audit다. 이전에 실패를 관찰한 in-sample 사례이며 대조군 재실행은 없다.

## 5. 데이터·모델·재현성
470MB 원문과 기존 색인을 읽기 전용으로 공유한다. 모델 Qwen3.8, 실제9호출 모두 Parasail. 출력 상한 없음, 질문당40호출·1024도구·1800초 유지. [코드·데이터·승인·평가 분리 동결](artifacts/design-freeze.json). 기존 기록과 MAIN 지문을 보존했다.

## 6. 결과
계약/API176검사 및 같은 동결 코드2검사 통과. 확대검사의 기존11실패는1055에서도 동일 재현했다. [검사 요약](artifacts/result.json), [실행 결과](artifacts/live-result.json).

| 질문 | 결과 | 판단 입력 크기 | 실제 호출 |
|---|---|---:|---:|
| FSC005 겸직 | 제한 답변, 핵심 결론 미확정 | 첫99,916자 → 다음196,884자 한도 초과 |6|
| CM023 상장차익 | 검색식 변환 오류 | 검색 진입 전 중단 |2|
| FSC008 사업보고서 면제 | 원문 조사 중단 | 첫118,339자 한도 초과 |1|

## 7. 사례별 오류 분석
FSC005는 법령5개·조문7개로 줄었지만 다음 연결·참조 목록이 커져10만자 한도에 도달했다. FSC008은 법령4개·조문5개인데도 원문·읽기 상태·도구 선택 중복으로 첫 입력 한도에 걸렸다. CM023은 PeCab이 단독 ‘요건’을 NP로 분석해 내용어 필터가 빈 결과를 만들고 컴파일러가 잘못 거부한 결정적 코드 결함이다. 원 실패를 보존하고 수정은 새 ADR에서 한다. 제공자429·연결 오류는0이다.

## 8. 비용·지연·회수 규모
제품9호출, 입력{live['input_tokens']:,}토큰·출력{live['output_tokens']:,}토큰, 제공자 기록 비용 ${live['cost_usd']:.8f}. 사례216.4/30.0/73.0초, 최대RSS 약3.1GiB. 확보70원문 span의 불일치0, 권한 검사 통과. 원문 일치가 법률 정답을 뜻하지 않는다. [단계 원장](artifacts/retrieval-ledger.json).

## 9. 해석
검색식은 기존 AI 호출에서 생성하므로 추가 검색어 추천 호출이 없다. 기존 저장 입력의 법령 메뉴만 바꾼 진단에서는 view JSON이45.35~52.89% 줄었다. 이는 전체 요청 토큰 감소율이 아니다. 실실행에서도 법령 폭증은 줄었지만 연결 원문·상태 중복이 남아 전 질문 완료에는 이르지 못했다.

## 10. 한계와 일반화 가능 범위
기존 내용어 색인의 연속 표현은 원문 문자 그대로의 일치나 숫자 정확 일치를 보장하지 않는다. 같은 own-block 안에서 조건을 결합하므로 다른 항에 흩어진 조건은 AI가 별도 검색식으로 제안해야 한다. 로컬 SQLite만 지원하며 Oracle에는 명시적 미지원 오류를 반환한다. 실제 법률 정답률·A1/A2 효과 미측정.

## 11. 운영 결정·롤백 조건
Proposed, in_sample=true, decision_eligible=false. 운영 registry·MAIN 포인터·GENOS 변경 없음. 정답·근거 부족과 입력 한도 오류를 숨기지 않는다. 최종 ADR 검사 및 전역 계보 검사는 별도 로그에 기록한다.

## 12. 재현 명령
`.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1056/run_matrix.py --inspect-only`

완료 셀은 재실행하지 않는다. 새 호출은 새 ADR에서 동결한다. 원문·인덱스는 공유하며 실제 wire와 journal은 artifacts/matrix의 원기록을 사용한다.
''')
(ADR/'실험/README.md').write_text('# 3문항 실행 결과\n\n'+ '\n'.join(f"- [{r['case_id']}]({r['file']})" for r in m['questions'])+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md'
if ADR.name not in index.read_text():index.write_text(index.read_text()+f'\n- [ADR-1056: AI 검색식 묶음과 공통 법령 선택]({ADR.name}/README.md) — 실제3문항, 제한1·실패2, 후속 결함 기록.\n')
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1056','created_at':m['reservation']['created_at'],
    'files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact preserved experiment artifact',
              'contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='journal.sqlite'}
             for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and p.suffix!='.lock']})
print(json.dumps({k:live[k] for k in ('status','physical_calls','cost_usd','limited_answers','native_failures')},ensure_ascii=False))
