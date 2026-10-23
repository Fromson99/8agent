"""Four-case report, offline core review and immutable observed binding."""
from common import *
import collections,statistics,math,sqlite3,csv
cases=read(DES/'cases.json');refs={c['id']:c for c in read(DES/'offline-reference.json')}
f=read(DES/'freeze.json');m=read(ADR/'실험/manifest.json');manual=read(RUN/'manual-review.json')
assert all((RUN/c['id']/'result.json').exists() and (RUN/c['id']/'audit.json').exists() for c in cases)
assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['serving_files'].items())
binding=read(RUN/'binding.json');generation=binding['binding']['generation'];rows=[];usage=[];checks=[]
for c in cases:
    cid=c['id'];P=RUN/cid;r=read(P/'result.json');a=read(P/'audit.json');g=read(P/'law-connections.json')
    answer=(P/'answer.txt').read_text() if (P/'answer.txt').exists() else ''
    rows.append({'id':cid,'http_status':r.get('http_status'),'completed_answer':r.get('http_status')==200 and bool(answer),
      'core_pass':manual[cid]['core_pass'],'whole_answer_pass':manual[cid].get('whole_answer_pass'),
      'model_calls':r['model_calls'],'seconds':round(r.get('elapsed_seconds') or 0,2),'read_articles':len(a['read_coordinates']),
      'cited_articles':len(a['final_coordinates']),'stored_edges_among_read_sources':len(g['stored_reference_edges']),
      'max_stored_path_edges':max((len(x)-1 for x in g['longest_simple_paths_among_read_sources']),default=0),
      'failure_types':','.join(manual[cid].get('failure_types',[]))})
    usage.extend(r.get('usage',[]));checks.extend(a['span_checks'])
def percentile(xs,p):return sorted(xs)[max(0,math.ceil(len(xs)*p)-1)] if xs else None
durations=[r['seconds'] for r in rows];counts=[r['cited_articles'] for r in rows]
res=read(ART/'resource-run-001.json')
result={'status':'complete','execution_complete':True,'generation':generation,'release_id':binding['binding']['release_id'],
 'in_sample':True,'decision_eligible':False,'quality_certified':False,'scheduled':4,'attempted':len(rows),
 'completed_answers':sum(r['completed_answer'] for r in rows),'core_pass':sum(r['core_pass'] for r in rows),
 'core_accuracy':sum(r['core_pass'] for r in rows)/len(rows),'manual_review_scope':'Frozen core requirements plus selected original evidence; full-answer caveats are reported separately.',
 'model_calls':sum(r['model_calls'] for r in rows),'usage_reported_calls':len(usage),
 'actual_models':sorted({u['model'] for u in usage}),'actual_providers':sorted({u['upstream_provider'] for u in usage}),
 'usage':{k:sum(u.get(k) or 0 for u in usage) for k in ('input_tokens','output_tokens','thinking_tokens','total_tokens','cost_usd')},
 'cost_basis':'Provider-reported usage; failures without reported usage are not asserted to cost zero.',
 'latency':{'p50_seconds':statistics.median(durations),'p95_seconds':percentile(durations,.95),'total_seconds':sum(durations)},
 'source_checks':{'evidence_units':len(checks),'original_mismatches':sum(not x['exact_original_match'] for x in checks),'scope_violations':sum(not x['within_scope'] for x in checks)},
 'peak_rss_bytes':res['peak_group_rss_bytes'],'resource_stop':res['stop_reason'],
 'pointer_unchanged_at_finish':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],
 'pointer_at_finish':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'selected_serving_files_verified':len(f['serving_files']),'product_code_changes':False,'main_promoted_by_this_experiment':False,'genos_executed':False,
 'cases':rows,'manual_review':manual,'historical_control':'ADR0895 was used to select known cases only; no simultaneous baseline or causal improvement claim.'}
put(RUN/'result.json',result)
with (RUN/'summary.csv').open('w',encoding='utf-8-sig',newline='') as out:
    writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
G=ROOT/read(DES/'baseline.json')['release']['data_path']
db=sqlite3.connect((G/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
scope=binding['public_scope'];corpus=db.execute('select count(*) from source where document_id in ('+','.join('?' for _ in scope)+')',scope).fetchone()[0];db.close()
gold_total=0;gold_hits=0
for c in cases:
    a=read(RUN/c['id']/'audit.json')
    for t in refs[c['id']]['targets']:
        if t.get('role')=='required' and str(t.get('node','')).isdigit():
            gold_total+=1;gold_hits+=({'doc_id':t['doc_id'],'node':int(t['node'])} in a['final_coordinates'])
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'observed':{'status':'complete','correct':result['core_pass'],'total':4,'accuracy':result['core_accuracy'],
 'completed_answers':result['completed_answers'],'criteria_met':result['core_pass']==4 and not result['source_checks']['original_mismatches'] and not result['source_checks']['scope_violations'],
 'quality_certified':False,'scope':'Frozen core answer criteria; no whole-system certification'}},comparisons=[],judge_disagreements=0,
 usage={'product_model_calls':result['model_calls'],'offline_evaluator_calls':0,**result['usage']},latency=result['latency'],
 error_taxonomy=[{'case_id':cid,'types':v.get('failure_types',[])} for cid,v in manual.items()])
m['retrieval_accounting'].update(corpus_total=corpus,before_filter=sum(r['read_articles'] for r in rows),after_filter=sum(counts),presented_total=sum(counts),
 presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=percentile(counts,.95),golden_recall=gold_hits/gold_total if gold_total else None,selectivity=statistics.mean(counts)/corpus)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
table=['| 질문 | 핵심 판정 | 호출 | 초 | 읽은 원문 단위/인용 |','|---|---|---:|---:|---:|']
for q,c,r in zip(m['questions'],cases,rows):
    cid=c['id'];link='../artifacts/run-001/'+cid
    parts=[f'run-001/observed. 실제 선택 MAIN{generation}, service.service.application 비주입, Qwen3.8/Parasail FP8. 한 번 실행; 전체 질문 재시도 없음.',c['question'],
      refs[cid]['reference_answer']+'\n\n제품 입력에는 제공하지 않았다. 등록 판본·좌표와 현재 선택 원문 차이는 audit.json에서 구분한다.',
      f'[요청]({link}/request.json), [binding](../artifacts/run-001/binding.json), [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json)은 읽은 원문→최종 인용의 사후 계측이다. 검색 후보 전체 흐름이나 조문 전문 읽기로 확대하지 않는다.',
      'call-*/request.json,response.json,binding.json,usage.json은 원시 기록이며 압축 후 closed-records.tar.gz와 archive-manifest.json으로 복원 가능하다. canonical/과 wire/의 gzip은 모델 문맥·스키마·전달 원값을 보존한다.',
      f'[실제 호출]({link}/calls.json), [논리 호출]({link}/generations.json), [원문 감사]({link}/audit.json), [실제 도구 기록과 별도 원문 연결 그래프]({link}/law-connections.json).',
      '채점 모델0회. 사전 기준과 현재 선택 원문을 사후 검토했다. 핵심 통과와 전체 문장의 정확성, 원문/권한 검사는 별개다. 과거에 성공한 것으로 고른 알려진4문항이며 분리 평가가 아니다.',
      json.dumps(manual[cid],ensure_ascii=False,indent=2)+f'\n\n[실제 답변]({link}/answer.txt)']
    target=ADR/'실험'/q['file'];target.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(headers,parts),1))+'\n');q['sha256']=sha(target)
    table.append(f"| [{cid}](실험/{q['file']}) | {'충족' if r['core_pass'] else '미충족'} | {r['model_calls']} | {r['seconds']} | {r['read_articles']}/{r['cited_articles']} |")
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=[f"실제 선택 MAIN{generation}에서4문항 실행. 답변 생성{result['completed_answers']}/4, 사전 핵심 기준{result['core_pass']}/4. 코드·프로필·데이터 수정과 MAIN 승격은 하지 않았다.",
 '이전 성공 사례를 최신 메인으로 다시 실행하라는 사용자 요청이다. CM051·022·008·038을 선택했으며 과거 성공을 새 실행 결과로 재사용하지 않는다.',
 '[호출 전 동결한 기준과 한도](artifacts/design/criteria.json). 기본40호출/문항,1800초/문항,동시1개. 원문·권한·해시 무결성 실패와 의미 오류를 구분한다.',
 '단일 observed arm. 실제 선택 service 진입점을 사용했고 앱이나 제품 선택을 주입하지 않았다. 기준답변은 분리했다. 최초 선택 릴리스를4문항 동안 고정하고 이후 타 작업의 포인터 변경은 별도 기록한다.',
 f"{result['release_id']} / MAIN{generation}, {len(f['serving_files'])}파일. Qwen3.8/Parasail FP8/reasoning none/fallback 없음. [실행 binding](artifacts/run-001/binding.json). [동결 질문](artifacts/design/cases.json).",
 '\n'.join(table),
 '\n\n'.join('**'+cid+'**: '+v['summary'] for cid,v in manual.items()),
 json.dumps({k:result[k] for k in ('model_calls','usage_reported_calls','usage','latency','source_checks','peak_rss_bytes','resource_stop')},ensure_ascii=False,indent=2)+'\n\n[단계 원장](artifacts/run-001/retrieval-ledger.json). 등록 좌표 회수율은 판본·문서ID 차이를 포함하므로 의미 정답률이 아니다.',
 '실제 읽은 조문, 최종 인용 조문, 그 조문들 사이에 저장된 참조 간선, 모델이 실제 수행한 탐색을 구분했다. 간선이 존재한다고 모델이 그 경로를 순서대로 따라갔다고 말하지 않는다.',
 '알려진4문항 단발 실행이다. 전체 성능·일반화·GENOS 내부 모델을 인증하지 않는다. 과거 기록과의 차이는 동시 대조 효과가 아니다. 최신성은 첫 실행 당시 선택 포인터 기준이며 종료 포인터도 결과에 보존한다.',
 '실험에서 제품·MAIN 선택을 변경하지 않았다. 발견된 문제의 수정·전체 질문 재실행은 새 ADR에서 한다. 원시 실패와 중간 응답은 보존한다.',
 'prepare.py → resource_guard.py 아래 live.py → 프로세스 종료 → audit.py → paths.py → ledger.py → offline manual-review.json → report.py → archive.py → seal.py → adr_structure.py hash/status/validate --final/graph. 동결된 실행을 덮어쓰지 말고 새 모델 재실행은 새 ADR로 남긴다.']
meta=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 최신 MAIN CM4 실제 실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
(ADR/'실험/README.md').write_text('# CM4 실제 실행\n\n[전체 결과](../README.md)\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('manual_review','pointer_at_finish')},ensure_ascii=False,indent=2))
