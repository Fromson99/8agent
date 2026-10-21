"""Post-run reporting only. Never sends product or evaluator model calls."""
from common import *
import collections,csv,math,statistics,sqlite3

cases=read(DES/'cases.json');refs={c['id']:c for c in read(DES/'offline-reference.json')}
f=read(DES/'freeze.json');m=read(ADR/'실험/manifest.json')
assert all((RUN/c['id']/'result.json').exists() for c in cases),'Finish or explicitly record every case first'
assert all((RUN/c['id']/'audit.json').exists() for c in cases),'Run source audit first'
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['serving_files'].items())
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
rows=[];usage=[];spans=[];errors=[];audits={};summaries={}
for c in cases:
    cid=c['id'];P=RUN/cid;r=read(P/'result.json');a=read(P/'audit.json');audits[cid]=a
    b=read(P/'response.json').get('body',{}) if (P/'response.json').exists() else {};answer=b.get('answer') or {}
    text=answer.get('text','') if isinstance(answer,dict) else str(answer)
    unresolved=answer.get('unresolved',[]) if isinstance(answer,dict) else []
    outcome=('interrupted' if r.get('error_type')=='KeyboardInterrupt' or r.get('status')=='interrupted' else
             'response_with_unresolved' if r.get('http_status')==200 and text and unresolved else
             'response' if r.get('http_status')==200 and text else 'failed')
    required=[t for t in a['reference_availability'] if t.get('role')=='required' and t.get('bound')]
    errtypes=sorted({str(e['code']) for e in a['provider_errors']} | ({r['error_type']} if r.get('error_type') else set()))
    if b.get('error_code'):errtypes=sorted(set(errtypes+[str(b['error_code'])]))
    row={'id':cid,'outcome':outcome,'http_status':r.get('http_status'),'model_calls':r['model_calls'],
         'seconds':round(r.get('elapsed_seconds') or 0,3),'read_articles':len(a['read_coordinates']),
         'cited_articles':len(a['final_coordinates']),'unresolved_count':len(unresolved),
         'required_targets':len(required),'registered_coordinate_read':sum(t['exact_coordinate_read'] for t in required),
         'registered_coordinate_cited':sum(t['exact_coordinate_cited'] for t in required),
         'current_same_document_article_read':sum(any(v['read'] for v in t['current_candidates']) for t in required),
         'current_same_document_article_cited':sum(any(v['cited'] for v in t['current_candidates']) for t in required),
         'registered_text_still_present':sum(any(v['registered_hash_matches'] for v in t['current_candidates']) for t in required),
         'provider_429_calls':sum(e['code']==429 for e in a['provider_errors']),
         'retry_law_structure_proposals':sum(v['action']=='RETRY_LAW_STRUCTURE' for v in a['model_decisions']),
         'errors':','.join(errtypes),'legal_accuracy':'not_scored'}
    rows.append(row);usage.extend(r['usage']);spans.extend(a['span_checks']);errors.extend(a['provider_errors'])
    summaries[cid]={'result':row,'unresolved':unresolved,'error_message':b.get('message') or r.get('error'),
                    'answer_file':str((P/'answer.txt').relative_to(ROOT)) if (P/'answer.txt').exists() else None}

def percentile(values,p):
    values=sorted(values);return values[max(0,math.ceil(len(values)*p)-1)] if values else None
resources=[read(p) for p in sorted(ART.glob('resource-run-*.json'))]
binding=read(RUN/'binding.json');ledger=read(RUN/'retrieval-ledger.json')
counts=[r['cited_articles'] for r in rows];durations=[r['seconds'] for r in rows]
result={'status':'complete','execution_complete':True,'quality_certified':False,'legal_accuracy':'not_scored',
        'in_sample':True,'decision_eligible':False,'release_id':binding['binding']['release_id'],'generation':98,
        'registered_collection':'cm','scheduled_cases':51,'attempted_cases':len(rows),'outcomes':dict(collections.Counter(r['outcome'] for r in rows)),
        'http_status_counts':dict(collections.Counter(str(r['http_status']) for r in rows)),
        'model_calls':sum(r['model_calls'] for r in rows),'usage_reported_calls':len(usage),
        'provider_429_calls':sum(r['provider_429_calls'] for r in rows),
        'actual_models':sorted({u['model'] for u in usage}),'actual_providers':sorted({u['upstream_provider'] for u in usage}),
        'usage':{k:sum(u.get(k) or 0 for u in usage) for k in ('input_tokens','output_tokens','thinking_tokens','total_tokens','cost_usd')},
        'cost_basis':'Provider-reported usage only; errors without usage are not asserted to cost zero.',
        'latency':{'p50_seconds':statistics.median(durations),'p95_seconds':percentile(durations,.95),'total_request_seconds':sum(durations),
                   'basis':'All51 attempts including fast failures and interrupted request; resume waiting excluded'},
        'source_checks':{'evidence_units':len(spans),'original_mismatches':sum(not s['exact_original_match'] for s in spans),
                         'scope_violations':sum(not s['within_scope'] for s in spans),'unmapped_final_sources':sum(len(a['unmapped_final']) for a in audits.values())},
        'reference_coverage':{k:sum(r[k] for r in rows) for k in ('required_targets','registered_coordinate_read','registered_coordinate_cited',
                   'current_same_document_article_read','current_same_document_article_cited','registered_text_still_present')},
        'retry_law_structure_proposals':sum(r['retry_law_structure_proposals'] for r in rows),
        'resources':{'peak_group_rss_bytes':max((r.get('peak_group_rss_bytes',0) for r in resources),default=0),
                     'stop_reasons':[r.get('stop_reason') for r in resources if r.get('stop_reason')]},
        'main_pointer_unchanged':True,'selected_serving_files_verified':len(f['serving_files']),
        'product_code_or_profile_changes':False,'genos_executed':False,'cases':summaries}
put(RUN/'result.json',result)
with (RUN/'summary.csv').open('w',encoding='utf-8-sig',newline='') as out:
    writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

G=ROOT/read(DES/'baseline.json')['release']['data_path'];db=sqlite3.connect((G/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
scope=binding['public_scope'];corpus=db.execute('select count(*) from source where document_id in ('+','.join('?' for _ in scope)+')',scope).fetchone()[0];db.close()
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'observed':{'status':'complete','attempted':51,'total':51,
    'outcomes':result['outcomes'],'quality_certified':False,'legal_accuracy':'not_scored','criteria_met':result['source_checks']['original_mismatches']==0 and result['source_checks']['scope_violations']==0}},
    usage={'product_model_calls':result['model_calls'],'offline_evaluator_calls':0,**result['usage']},latency=result['latency'],
    error_taxonomy=[{'case_id':r['id'],'outcome':r['outcome'],'types':r['errors']} for r in rows])
den=result['reference_coverage']['required_targets'];hits=result['reference_coverage']['registered_coordinate_cited']
m['retrieval_accounting'].update(corpus_total=corpus,before_filter=sum(r['read_articles'] for r in rows),after_filter=sum(counts),presented_total=sum(counts),
    presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=percentile(counts,.95),golden_recall=hits/den if den else None,
    selectivity=statistics.mean(counts)/corpus if corpus else None)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
labels={'response':'응답 생성','response_with_unresolved':'응답 생성·미확인 포함','failed':'실패','interrupted':'중단'}
table=['| 문항 | 실행 결과 | 호출 | 초 | 원문 읽기/인용 | 429 |','|---|---|---:|---:|---:|---:|']
for q,c,r in zip(m['questions'],cases,rows):
    cid=c['id'];P=RUN/cid;p=ADR/'실험'/q['file'];link='../artifacts/run-001/'+cid
    parts=['run-001/observed. 실제 선택 MAIN98 비주입 service.RAG_ASK. 문항 전체 재시도 없음; native gateway의 동일 요청 내 제한 재시도는 물리 호출별 기록.',
       c['question'],refs[cid]['reference_answer']+'\n\n[등록 원본·버전](../artifacts/design/offline-reference.json). 기준답변은 제품 입력 비공개, 사후 원문 좌표 대조에만 사용.',
       f'[실제 요청]({link}/request.json), [실행 binding](../artifacts/run-001/binding.json), [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[읽은 원문→최종 인용](../artifacts/run-001/retrieval-ledger.json). 현재 문서·조문 동일성, 등록 좌표·본문 해시 일치는 audit.json에서 별도 표시. 조문 일부 span을 읽은 경우 전체 본문 확보로 간주하지 않는다.',
       f'{link}/raw/ 또는 run-001/closed-records.tar.gz의 해당 경로에 call-*/request.json, response.json, binding.json, usage.json 보존. canonical/*.json.gz와 wire/*.json.gz는 전달 전 모델 문맥·스키마·실제 wire 원문이다. 압축 시 archive-manifest.json의 각 파일 해시와 복원 명령으로 대조한다.',
       f'[물리 호출]({link}/calls.json), [논리 호출]({link}/generations.json), [원문·행동 감사]({link}/audit.json). 제공자 실패·판단 수정·중단을 성공으로 바꾸지 않았다.',
       '채점 모델 호출 0. 법률 정답률 미채점. 원문 span/hash/권한, 등록 필수근거 좌표의 결정적 대조만 실시. 이미 사용한51문항이므로 unseen holdout으로 보지 않는다.',
       json.dumps(r,ensure_ascii=False)+'\n\n'+(f'[사용자에게 반환된 실제 답변]({link}/answer.txt)' if (P/'answer.txt').exists() else '완성된 답변 없음. 오류·중단 기록 보존.')]
    p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(headers,parts),1))+'\n');q['sha256']=sha(p)
    table.append(f"| [{cid}](실험/{q['file']}) | {labels[r['outcome']]} | {r['model_calls']} | {r['seconds']:.1f} | {r['read_articles']}/{r['cited_articles']} | {r['provider_429_calls']} |")
put(ADR/'실험/manifest.json',m)
totals={k:v for k,v in result.items() if k!='cases'}
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=[f"현재 로컬 MAIN98에서 등록 CM51 전체 요청을 실행했다. 결과: {json.dumps(result['outcomes'],ensure_ascii=False)}. 물리 모델 호출 {result['model_calls']}회. 제품 MAIN 변경 없음. 법률 정답률은 채점하지 않았다.",
    '사용자 요청은 현재 메인으로 전체 cm 실행. 등록부 collection=cm은51문항이며 별도 risk_cm105와 구분한다. MAIN98 법령명 복구가 배선된 실제 service 진입점의 현행 행동을 관찰한다.',
    '[호출 전 동결한 가설·성공·실패·예산 기준](artifacts/design/criteria.json). 전체51문항을 각각 한 번 요청하고 모든 실패·중단을 보존한다. 원문·권한·해시 불일치는 별도 중대 실패다.',
    '단일 observed arm, 기준 대비 A/B 없음. 같은 프로세스에서 원문·색인 캐시를 재사용하며 각 문항은 session/memory ID 없는 신규 RAG 요청이다. 부모 ADR0967/integrated. 초반 제공자429 반복으로 일시 중단한 후 미시작 문항만 계속했다. 시작된 문항을 다시 실행하거나 좋은 결과로 교체하지 않았다.',
    f"law-name-recovery-20261021-r1 / generation98, {len(f['serving_files'])}서빙파일, 현재 선택 데이터·검색·프로필 유지. Qwen3.8 / qwen/qwen3.8-27b, OpenRouter Parasail FP8, reasoning none, fallback 없음. [실행 지문](artifacts/run-001/binding.json), [질문 원문](artifacts/design/cases.json). 기준답변·근거 좌표는 사후 감사에만 사용.",
    '\n'.join(table),
    '초반 제공자429와 운영자 중단을 제품 판단 오류와 구분한다. 문항별 response/failed/interrupted, 미확인, 원문 읽기·인용, 제공자 실패는 [CSV](artifacts/run-001/summary.csv)와 질문별 audit.json에 기록했다. HTTP200/READY를 정답 판정으로 치환하지 않는다. [답변 내용의 관찰 메모](artifacts/run-001/qualitative-notes.json)에는 CM-006이 전문투자자 정의를 답하고 신규상장 의무보유 취급은 미확인으로 남긴 점을 기록했다.',
    '```json\n'+json.dumps(totals,ensure_ascii=False,indent=2)+'\n```\n\n[단계별 회수·탈락 원장](artifacts/run-001/retrieval-ledger.json). 읽은 원문→최종 인용만 사후 계측했다. 본문 일부 읽기와 조문 전체 확보는 다르다. 전체 검색 후보 제시 수와 이 원장의 인용 수를 혼동하지 않는다.',
    '응답 생성 여부, 인용 원문의 일치, 필수근거 좌표 회수, 법률 판단의 정확성은 서로 다른 결과다. 등록 근거와 현재 버전의 동일 조문 후보를 별도 대조했으며 자동으로 좌표를 재매핑하지 않았다. 제공자429가 포함된 지연·성공률은 검색 개선 효과를 뜻하지 않는다.',
    '기존에 사용한 CM51 in-sample 관찰이다. 초반 제공자 제한과 중단을 포함하므로 이 실행을 안정된 제공자 환경의 품질 측정으로 해석할 수 없다. 정답률·속도 개선을 주장하지 않는다. GENOS 내부 모델·현장 실행 및 risk_cm105는 이 기록의 대상이 아니다.',
    'MAIN98 선택 포인터, 제품 코드·프로필·데이터 유지. 승격·배포·Git commit/push 없음. 발견된 문제의 수정과 재실행은 후속 ADR에서 별도 동결한다. 원본 실패를 덮어쓰지 않는다.',
    'prepare.py와 동결 기록은 역사적 정본이며 덮어써 재실행하지 않는다. resource_guard.py 아래 live.py 순차 실행 → 프로세스 종료 확인 → audit.py → ledger.py → report.py → archive.py → seal.py → stable adr_structure.py validate --final 및 graph. 새로운 모델 재실행은 새 ADR 필요. 원시 기록 복원은 archive-manifest.json 참조.']
meta=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+meta+'---\n\n# MAIN98 CM51 전체 실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
(ADR/'실험/README.md').write_text('# CM51 실행 결과\n\n[전체 요약](../README.md) · [CSV](../artifacts/run-001/summary.csv)\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
print(json.dumps(totals,ensure_ascii=False,indent=2))
