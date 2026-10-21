"""Post-selection measurement only; never modifies any product input."""
from pathlib import Path
import hashlib,json,re,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0925-source-lead-exact-observation';D=A/'artifacts/design';O=A/'artifacts/run-001'
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
 summaries[arm]={'status':'complete','http_status':run.get('http_status'),'product_status':run.get('status'),'model_calls':run['model_calls'],'elapsed_seconds':run['elapsed_seconds'],'peak_rss_kib':run['peak_rss_kib'],'field_rows':len(a['field_rows']),'comparison_rows':a['rows'],'consumer_checks':run.get('checks',{}),'stored_evidence_checks':len(a['evidence_span_checks']),'span_mismatches':sum(not x['exact_original_match'] for x in a['evidence_span_checks']),'source_counts':dict(zip(['read','returned','cited'],counts[arm])),'execution_status':'preflight_failed' if run.get('preflight_only') else 'executed','manual_review':manual[arm],'known_locations':read(P/'trace.json')['coverage']}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'denominator':'All structured canonical roots in pinned navigation; not relevant-source gold.','scope':'Read receipts across every child run, current returned originals, actual final citations. Separate trace records document-term candidates and reference cards; no term hit is counted as a read.'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
result={'status':'complete','arms':summaries,'technical_contracts':read(R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff/artifacts/checks/test-disposition.json'),'model_calls':sum(s['model_calls'] for s in summaries.values()),'offline_evaluator_model_calls':0,'actual_models':sorted({v['model'] for v in usage}),'actual_providers':sorted({v['upstream_provider'] for v in usage}),'usage':{'input_tokens':sum(v.get('input_tokens') or 0 for v in usage),'output_tokens':sum(v.get('output_tokens') or 0 for v in usage),'cost_usd':sum(v.get('cost_usd') or 0 for v in usage)},'all_stored_spans_match':all(v['exact_original_match'] for v in checks),'in_sample':True,'decision_eligible':False,'main_changed':False,'main_generation':88,'working_code_integrated':False,'genos_executed':False,'limitations':manual['limitations']}
put(O/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm=summaries,comparisons=[manual['comparison']],usage={'product_model_calls':result['model_calls'],'offline_evaluator_calls':0,**result['usage']},latency={a:s['elapsed_seconds'] for a,s in summaries.items()},error_taxonomy=manual['error_taxonomy'])
m['retrieval_accounting'].update(corpus_total=corpus,**{key:{a:c[i] for a,c in counts.items()} for key,i in [('before_filter',0),('after_filter',1),('presented_total',2),('presented_mean',2),('presented_p50',2),('presented_p95',2)]},golden_recall={a:None for a in counts},selectivity={a:c[2]/corpus for a,c in counts.items()})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json')
headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 p=A/'실험'/q['file'];texts=['run-001 / observed once; exact completed0924 bridged rev-005; in_sample=true; no product changes or adaptive rerun.',read(D/'cases.json')[0]['question'],'승인 gold 없음. 사용자 지적 조항과 원문 확보를 사후 대조한다. 자동 법률 정답 판정 금지.','design/cases.json 및 각 arm request.json, binding.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/run-001/retrieval-ledger.json','observed/canonical/*.json.gz, wire/*.json.gz; raw-runtime.tar.gz의 원시 request/response. 압축 전후 해시와 복원법은 archive-manifest.json.','각 arm generations.json, calls.json 및 journal. 실패·복구 이력 보존.','평가 모델0회. 원문 span/hash 및 저장·중복 응답 실제 소비자를 확인. 적은 사례로 일반 성능 추정 금지.',json.dumps(summaries,ensure_ascii=False,indent=2)]
 p.write_text('# 연결 탐색 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headers,texts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
headers=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. 완료0924에서 검증한 정확한 연결 단서 전달 코드를 실제 모델로 관측했다. 알려진 질문의 관측이며 이 ADR만으로 MAIN을 승격하지 않는다.',
'기존 자식 선택기가 연결된 조문을 보고도 원문을 읽지 않고 반환하면 부모에는 미열람 용어 후보가 전달되지 않았다. v2 반환에 별도 비인용 단서를 넣고 기존 ITEMS/locator/read_node로 원문을 확보하게 한다.',
json.dumps(read(D/'criteria.json'),ensure_ascii=False,indent=2),
'완료0924/bridged rev-005 코드를 그대로 재사용했다. 부모의 후보 모델 실행은 미사용 테스트의 동시 수정으로 사전검사에서 멈췄다. 새 실행에서는 실제 실행 소비 파일만 동결하고 1회 관측한다. 이전 rebased 결과는 맥락 참고이며 새 A/B 쌍이 아니다.',
'정확한 observed-binding, parent-provenance, parent-result, freeze는 artifacts/design에 있고 병합 원장은 부모0924에 있다. 데이터·공개 범위·Qwen3.8/Parasail FP8/reasoning none/fallback 없음은 공통이다.',
json.dumps(result,ensure_ascii=False,indent=2),json.dumps(manual,ensure_ascii=False,indent=2),
'실제 호출·사용량·지연과 자원 기록은 각 arm result/calls 및 resource receipt. 확보→자식 반환→최종 인용 원장은 retrieval-ledger.json. 단서와 원문은 따로 집계한다. 한 질문의 차이로 일반 성능 비율을 계산하지 않는다.',
'연결·용어 적중은 추가로 읽을 위치다. 실제 원문 확보 이후 A+B의 적용성·충분성·채택을 모델이 판단한다. 제목만 읽힌 경우 PARTIAL이며 미리보기는 인용 근거가 아니다. 모르는 내용은 원문 반환을 막지 않는다.',
'\n'.join(result['limitations']),
'현재 작업 코드의 Oracle 직접 조회 관련 변경을 후보에 보존했다. MAIN88과 GENOS는 이 관측에서 변경하지 않았다. 후속 유한 기술 검증과 실제 packager dependency census가 통과하면 정확한 같은 코드로 작업 통합/MAIN 승격을 진행한다.',
'prepare → guarded live observed → audit → trace → manual review → report/archive → stable hash/status/validate --final/graph. 완료 기록은 덮어쓰지 않는다.']
meta=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+meta+'---\n\n# 연결 원문 재선택과 문서 내 용어 탐색\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headers,texts),1))+'\n')
(A/'RESULT.txt').write_text('연결 원문 재선택과 문서 내 용어 탐색\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(A/'실험/README.md').write_text('# 연결 탐색 실험\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
print(json.dumps({'calls':result['model_calls'],'source_counts':counts,'source_integrity':result['all_stored_spans_match']},ensure_ascii=False))
