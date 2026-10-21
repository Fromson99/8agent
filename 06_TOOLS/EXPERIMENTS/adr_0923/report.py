"""Post-selection measurement only; never modifies any product input."""
from pathlib import Path
import hashlib,json,re,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0923-connected-term-provider-recheck';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def unique(xs):return [json.loads(s) for s in sorted({canon(x) for x in xs})]
m=read(A/'실험/manifest.json');f=read(D/'freeze.json');manual=read(O/'manual-review.json')
assert all(sha(R/n)==h for n,h in f['files'].items())
G=R/read(D/'baseline.json')['manifest']['data_path'];db=sqlite3.connect('file:'+str(G/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
corpus=sum(json.loads(r[0]).get('unit_id') is not None for r in db.execute('select json from source'));db.close()
summaries={};counts={};arms=[];usage=[];checks=[]
for arm in ('observed',):
 P=O/arm/'leverage-comparison';a=read(P/'audit.json');run=read(P/'result.json');usage.extend(run['usage']);checks.extend(a['evidence_span_checks'])
 read_rows=[r for c in a['children'].values() for r in c['canonical_read']]
 adopted=[r for c in a['children'].values() for r in c['canonical_adopted']];final=a['canonical_final']
 counts[arm]=[len(unique(rows)) for rows in (read_rows,adopted,final)]
 stages=[];before=[];before_occ=0;plans=m['design']['retrieval_stage_plan']['stages_by_arm'][arm]
 for plan,raw in zip(plans,(read_rows,adopted,final)):
  after=unique(raw);bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
  reason='Not retained in current child return or final citations; no inference of legal irrelevance. Superseded reads remain in journals.'
  stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),'occurrence_counts':{'before':before_occ,'after':len(raw),'canonical_collapsed_before':before_occ-len(before),'canonical_collapsed_after':len(raw)-len(after)},'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]})
  before=after;before_occ=len(raw)
 case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':'leverage-comparison','gold_total':0,'gold_identities':[],'stages':stages}
 arms.append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in plans],'cases':[case],'aggregate':{'cases':1,'presented_total':len(unique(final)),'gold_total':0}})
 summaries[arm]={'status':'complete','http_status':run.get('http_status'),'product_status':run.get('status'),'model_calls':run['model_calls'],'elapsed_seconds':run['elapsed_seconds'],'peak_rss_kib':run['peak_rss_kib'],'field_rows':len(a['field_rows']),'comparison_rows':a['rows'],'consumer_checks':run.get('checks',{}),'stored_evidence_checks':len(a['evidence_span_checks']),'span_mismatches':sum(not x['exact_original_match'] for x in a['evidence_span_checks']),'source_counts':dict(zip(['read','returned','cited'],counts[arm])),'manual_review':manual[arm]}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'denominator':'All structured canonical roots in pinned navigation; not relevant-source gold.','scope':'Read receipts across every child run, current returned originals, actual final citations. Separate trace records document-term candidates and reference cards; no term hit is counted as a read.'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
result={'status':'complete','arms':summaries,'technical_contracts':read(A/'artifacts/checks/test-disposition.json'),'model_calls':sum(s['model_calls'] for s in summaries.values()),'offline_evaluator_model_calls':0,'actual_models':sorted({v['model'] for v in usage}),'actual_providers':sorted({v['upstream_provider'] for v in usage}),'usage':{'input_tokens':sum(v.get('input_tokens') or 0 for v in usage),'output_tokens':sum(v.get('output_tokens') or 0 for v in usage),'cost_usd':sum(v.get('cost_usd') or 0 for v in usage)},'all_stored_spans_match':all(v['exact_original_match'] for v in checks),'in_sample':True,'decision_eligible':False,'main_changed':False,'main_generation':88,'working_code_integrated':False,'genos_executed':False,'limitations':manual['limitations']}
put(O/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm=summaries,comparisons=[manual['comparison']],usage={'product_model_calls':result['model_calls'],'offline_evaluator_calls':0,**result['usage']},latency={a:s['elapsed_seconds'] for a,s in summaries.items()},error_taxonomy=manual['error_taxonomy'])
m['retrieval_accounting'].update(corpus_total=corpus,**{key:{a:c[i] for a,c in counts.items()} for key,i in [('before_filter',0),('after_filter',1),('presented_total',2),('presented_mean',2),('presented_p50',2),('presented_p95',2)]},golden_recall={a:None for a in counts},selectivity={a:c[2]/corpus for a,c in counts.items()})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json')
headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 p=A/'실험'/q['file'];texts=['run-001 / normalized once; exact completed0921 parent; in_sample=true; no adaptive live rerun.',read(D/'cases.json')[0]['question'],'승인 gold 없음. 사용자 지적 조항과 원문 확보를 사후 대조한다. 자동 법률 정답 판정 금지.','design/cases.json 및 각 arm request.json, binding.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/run-001/retrieval-ledger.json','normalized/canonical/*.json.gz, wire/*.json.gz; raw-runtime.tar.gz의 원시 request/response. 압축 전후 해시와 복원법은 archive-manifest.json.','각 arm generations.json, calls.json 및 journal. 실패·복구 이력 보존.','평가 모델0회. 원문 span/hash 및 저장·중복 응답 실제 소비자를 확인. 적은 사례로 일반 성능 추정 금지.',json.dumps(summaries,ensure_ascii=False,indent=2)]
 p.write_text('# 연결 탐색 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headers,texts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
headers=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. 색인과 같은 용어 구문·현재 원문 참조 범위 동일 코드 제공자 복구 관측. 작업 코드/활성 배선은 변경하지 않았다.','부모0921은 세 조항을 확보했으나 추가 용어 탐색은 미분해 단어를 FTS에 전달하여0건이었다. 같은 색인 형태소를 구문으로 묶고, 최초 화면의 검증된 원문 페이지를 참조 범위에 전달한다. 자동 채택은 하지 않는다.',json.dumps(read(D/'criteria.json'),ensure_ascii=False,indent=2),'완료0921/connected의 정확한 코드를 부모로 삼아 코드를 그대로 유지했다. observed1회 실행. 이전 baseline/connected의 완료 결과는 비교 맥락으로만 참조하고 재실행하지 않았다. 정확한 동일 코드의 부모104개 계약 통과를 재사용했다.','정확한 부모는 parent-binding.json과 parent-observation.json; 새 후보 없음; 완료0922/normalized rev-001 그대로 재사용. design/freeze.json에 코드·설정·데이터·테스트 고정. 외부 Qwen3.8/Parasail FP8/reasoning none/fallback 없음.',json.dumps(result,ensure_ascii=False,indent=2),json.dumps(manual,ensure_ascii=False,indent=2),'각 arm calls.json 및 resource receipt, 전체 result.json과 retrieval-ledger.json. 한 후속 실행과 이전 관측으로 p50/p95 성능 일반화 금지.','원문 확보, 모델에게 전달, 부모에게 반환, 최종 인용은 각각 측정한다. 연결 자체는 법률 적용성의 증명이 아니며 A+B 채택 판단은 모델이 한다.','\n'.join(result['limitations']),'작업 코드의 기존 Oracle 변경을 보존하고 격리 후보에 구현했다. 로컬 활성 MAIN88·GENOS 미변경. MAIN 승격은 분리된 검증 및 명시적 적용 절차가 필요하다.','prepare.py → frozen parent binding → live.py observed leverage-comparison → audit.py 각 arm → trace.py → report.py → archive.py → stable hash/validate --final/graph. 완료 기록 덮어쓰기 금지.']
meta=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+meta+'---\n\n# 연결 원문 재선택과 문서 내 용어 탐색\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headers,texts),1))+'\n')
(A/'RESULT.txt').write_text('연결 원문 재선택과 문서 내 용어 탐색\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(A/'실험/README.md').write_text('# 연결 탐색 실험\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
print(json.dumps({'calls':result['model_calls'],'source_counts':counts,'source_integrity':result['all_stored_spans_match']},ensure_ascii=False))
