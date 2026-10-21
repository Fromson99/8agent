"""Offline only, after immutable product selection: current-coordinate scoring and audit."""
from common import *
import sqlite3,statistics,collections,csv
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
assert (RUN/'rerank-receipt.json').exists()
criteria=read(DES/'criteria.json');cases=read(DES/'cases.json');refs={x['case_id']:x for x in read(DES/'offline-reference.json')}
corpus=read(RUN/'corpus-summary.json');coverage=read(RUN/'coverage.json');vector=read(RUN/'vector-manifest.json');m=read(ADR/'실험/manifest.json')
freeze=read(DES/'freeze.json')
for path,h in freeze['files'].items():assert sha(ROOT/path)==h
data=ROOT/criteria['generation_path'];src=sqlite3.connect((data/'store.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
idx=sqlite3.connect((RUN/'corpus.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
indexed=set(idx.execute('SELECT doc_id,node FROM groups WHERE EXISTS(SELECT 1 FROM chunks c WHERE c.doc_id=groups.doc_id AND c.node=groups.node)'))
allowed=set(criteria['scope']);graded=[];rows=[];audits=[];reference_audits=[];by_arm={a:[] for a in ['dense','dense-rerank']};usages=[];calls=0
def identities(items):return [{'doc_id':x['doc_id'],'node':int(x['node'])} for x in items]
def keys(items):return {(x['doc_id'],int(x['node'])) for x in items}
def percentile(values,p):
 a=sorted(values);return a[min(len(a)-1,round((len(a)-1)*p))] if a else None
for case in cases:
 cid=case['id'];directory=RUN/cid;pool=readgz(directory/'pool.json.gz');ranked=readgz(directory/'rerank.json.gz');gold=[];checks=[]
 for entry in refs[cid]['entries']:
  doc=entry['selected_document_id'];node=int(entry['selected_unit_id']);identity={'doc_id':doc,'node':node}
  u=src.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',(doc,str(node))).fetchone()
  unit=json.loads(u[0]) if u else None
  source=src.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(doc,)).fetchone()
  exact=bool(unit and unit.get('coordinate_key')==entry['coordinate_key'] and source and source[0]==entry['source_artifact_sha256'])
  root=bool(unit and (unit.get('family')=='kr_article' or ((unit.get('legal_coordinate') or {}).get('unit')=='조' and not (unit.get('legal_coordinate') or {}).get('chain'))))
  if not exact or not root:raise ValueError('Rebound reference identity/source drift: '+cid+' '+str(identity))
  gold.append(identity);checks.append({'identity':identity,'coordinate_key':entry['coordinate_key'],'source_hash_and_coordinate_match':exact,'canonical_article_root':root,'indexed':(doc,node) in indexed,'source_version':entry.get('gold_source_version'),'legal_interpretation_certified':False})
 g=keys(gold);poolids=identities(pool);rids=identities(ranked);row={'id':cid,'required':len(g),'indexed_required':len(g&indexed),'vector50':len(g&keys(poolids))}
 for arm,rank in [('dense',poolids),('dense-rerank',rids)]:
  ctx=readgz(directory/(arm+'-context.json.gz'));present=identities(ctx['sources']);top=rank[:10]
  for source in ctx['sources']:
   parts=[]
   for bid in source['block_ids']:
    r=src.execute('SELECT text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?',(source['doc_id'],str(bid))).fetchone()
    assert r and r[1]==source['source_artifact_sha256'];parts.append(r[0] or '')
   text='\n'.join(parts);assert text==source['text'] and hashlib.sha256(text.encode()).hexdigest()==source['text_sha256'] and source['doc_id'] in allowed
   audits.append({'case_id':cid,'arm':arm,'doc_id':source['doc_id'],'node':source['node'],'exact_source':True})
  rec=StageLedgerRecorder(cid,arm,identity_canonicalizer);rec.record_stage('vector50','source',poolids)
  rec.record_stage('rank','rerank',rank,parent_stage_ids=['vector50'])
  rec.record_stage('top10','select',top,parent_stage_ids=['rank'],discard_reasons=[{'identity':x,'reason':'outside_frozen_top10'} for x in rank if x not in top])
  rec.record_stage('present','present',present,parent_stage_ids=['top10'],discard_reasons=[{'identity':x,'reason':'whole_group_context_budget'} for x in top if x not in present])
  graded.append(grade_capture(rec.capture(),gold))
  stats={'id':cid,'required':len(g),'hit10':len(g&keys(top)),'prepared_hits':len(g&keys(present)),'prepared_count':len(present),'all_required_top10':bool(g and g<=keys(top)),'all_required_prepared':bool(g and g<=keys(present)),'rerank_seconds':read(directory/'rerank-timing.json')['seconds'] if arm=='dense-rerank' else 0,'answer_status':'not_run','semantic_verdict':'not_scored'}
  if (directory/arm/'result.json').exists():
   a=read(directory/arm/'result.json');stats['answer_status']=a['status'];calls+=a['calls'];usages.extend(a['usage'])
  if (directory/'judge/result.json').exists():
   j=read(directory/'judge/result.json')
   if j['status']=='complete':
    label=next(k for k,v in j['labels'].items() if v==arm);stats['semantic_verdict']=j['judgment'][label]['verdict']
  by_arm[arm].append(stats);row[arm+'_top10']=stats['hit10'];row[arm+'_prepared']=stats['prepared_hits']
 put(directory/'reference-audit.json',checks);reference_audits.extend(checks);rows.append(row)
src.close();idx.close()
for path in RUN.glob('cm-*/judge/result.json'):
 j=read(path);calls+=j['calls'];usages.extend(j['usage'])
run=build_run_artifact('run-001',graded,{a:['vector50','rank','top10','present'] for a in by_arm})
ledger=build_experiment_artifact('ADR-0971',m['experiment_id'],[run]);put(RUN/'retrieval-ledger.json',ledger)
den=sum(r['required'] for r in rows);metrics={}
for arm,values in by_arm.items():
 counts=[x['prepared_count'] for x in values];hits=sum(x['hit10'] for x in values);prepared=sum(x['prepared_hits'] for x in values)
 metrics[arm]={'status':'complete','retrieval_cases':len(values),'required':den,'retrieved_at10':hits,'recall_at10':hits/den,'all_required_at10':sum(x['all_required_top10'] for x in values),'prepared_hits':prepared,'prepared_recall':prepared/den,'prepared_total':sum(counts),'prepared_mean':statistics.mean(counts),'prepared_p50':statistics.median(counts),'prepared_p95':percentile(counts,.95),'selectivity':statistics.mean(counts)/len(indexed),'answer_outcomes':dict(collections.Counter(x['answer_status'] for x in values)),'answer_correct':sum(x['semantic_verdict']=='pass' for x in values),'answer_scored':sum(x['semantic_verdict'] in ['pass','fail'] for x in values),'rerank_seconds_p50':statistics.median(x['rerank_seconds'] for x in values),'rerank_seconds_p95':percentile([x['rerank_seconds'] for x in values],.95)}
pairs=collections.Counter('both_covered' if a['all_required_top10'] and b['all_required_top10'] else 'rerank_only' if b['all_required_top10'] else 'dense_only' if a['all_required_top10'] else 'neither_covered' for a,b in zip(by_arm['dense'],by_arm['dense-rerank']))
delta=metrics['dense-rerank']['recall_at10']-metrics['dense']['recall_at10'];success=delta>=.05 and metrics['dense-rerank']['all_required_at10']>metrics['dense']['all_required_at10'] and pairs['dense_only']<=2
result={'status':'complete','build_complete':True,'build_success':coverage['coverage']==1.0 and coverage['documents']==70,'retrieval_complete':True,'semantic_answer_comparison_complete':all(x['answer_scored']==6 for x in metrics.values()),'quality_certified':False,'main_changed':False,'genos_executed':False,'corpus':corpus,'coverage':coverage,'required':den,'indexed_required':sum(r['indexed_required'] for r in rows),'vector50_hits':sum(r['vector50'] for r in rows),'by_arm':metrics,'paired_all_required_source_coverage':dict(pairs),'recall_delta':delta,'rerank_superiority_criterion_met':success,'actual_external_calls':calls,'usage':{k:sum(u.get(k) or 0 for u in usages) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']},'cost_note':'Only provider-reported usage; unavailable usage is not zero billing','source_checks':{'checked_contexts':len(audits),'mismatches':0,'reference_coordinates_verified':len(reference_audits)},'limitations':['Known CM51 in-sample; no human-calibrated legal accuracy certification','Selected retained70 source documents, not official latest-version verification','No separate attachment documents or excluded2 PDFs','Stored parsed text coverage only; does not certify source parser visual/OCR completeness','Retrieval corpus includes explicit non-article groups; golden identities are true article roots','Reference coordinates rebound to current source; ADR0970 old coordinate scores are not directly comparable','Whole-group32000-character answer context budget can exclude selected groups; index coverage remains100%','No paired MAIN98 answer-quality comparison'],'cases':rows}
put(RUN/'result.json',result);put(RUN/'source-audit.json',audits)
with (RUN/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm=metrics,comparisons=[{'baseline':'dense','candidate':'dense-rerank','recall_at10_delta':delta,'source_coverage_pairs':dict(pairs)}],judge_disagreements=None,usage={'actual_external_calls':calls,**result['usage']},latency={'shared_retrieval_seconds':read(RUN/'retrieve-receipt.json')['seconds'],'embedding_seconds':read(RUN/'embed-receipt.json')['seconds']},error_taxonomy=['retrieval_miss','other'])
account=m['retrieval_accounting'];account.update(corpus_total=len(indexed),before_filter={a:51*50 for a in by_arm},after_filter={a:51*10 for a in by_arm})
for k,v in [('presented_total','prepared_total'),('presented_mean','prepared_mean'),('presented_p50','prepared_p50'),('presented_p95','prepared_p95'),('golden_recall','prepared_recall'),('selectivity','selectivity')]:account[k]={a:r[v] for a,r in metrics.items()}
account['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
account['presentation_semantics']='Prepared context; delivered product calls separately counted. Non-article root groups identified in corpus SQLite; canonical golden roots retain actual source-unit IDs.'
headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
table='| 질문 | 필수 | 색인 | 벡터50 | 벡터10 | 리랭커10 |\n|---|---:|---:|---:|---:|---:|\n'
for i,(case,row) in enumerate(zip(cases,rows),1):
 cid=case['id'];d=RUN/cid
 sections=[f'ADR0971 run-001 / dense,dense-rerank / exact. 원시 시각·모델 파일·hash는 단계 receipt와 design/models.json. 생성은 Qwen3.8 Parasail FP8 reasoning none.',case['question'],refs[cid]['reference_answer'],
 f'### 회수·탈락 단계 원장 — run·arm별\n\n전체 검색 그룹 {len(indexed)}개. 벡터50→그대로/리랭커→10개→온전한 그룹 원문32000자. 정답은 선택 이후에만 결합했다.\n\n[전체 후보](../artifacts/run-001/{cid}/pool.json.gz) · [리랭커](../artifacts/run-001/{cid}/rerank.json.gz) · [벡터 원문](../artifacts/run-001/{cid}/dense-context.json.gz) · [리랭커 원문](../artifacts/run-001/{cid}/dense-rerank-context.json.gz) · [정확 단계·탈락 원장](../artifacts/run-001/retrieval-ledger.json) · [현재 좌표 대조](../artifacts/run-001/{cid}/reference-audit.json). 원문은 무손실 압축 파일로 보존한다.',
 '완성·실패·미실행을 구분한다. system/user/schema/provider 원응답·usage는 실행된 arm의 raw 디렉터리에 보존한다.',
 '중간 생성 LLM 없음. 로컬 BGE-M3 및 cross-encoder 점수. 암묵적 tokenizer 절단0건.',
 '완성 답변 쌍만 동일 Qwen의 격리된 A/B 판정. 평가자 calibration 미수행. 원문 dictionary의 case_id를 읽는 결정적 어댑터를 첫 호출 전 결속했으며 기존 prompt/schema/reference 문구는 동일하다.',
 '```json\n'+json.dumps({a:by_arm[a][i-1] for a in by_arm},ensure_ascii=False,indent=2)+'\n```\n\n근거 회수와 법률 정답은 다른 지표다. 직접 원인은 단계별 탈락 원장에서 확인한다.']
 for arm in by_arm:
  sections[4]+=f'\n\n{arm}: '+(f'[실제 결과](../artifacts/run-001/{cid}/{arm}/result.json) · [전체 원시 입출력](../artifacts/run-001/{cid}/{arm}/raw)' if (d/arm/'result.json').exists() else '사전6문항 밖 또는 외부 호출 중단으로 미실행')
 if (d/'judge/result.json').exists():sections[6]+=f'\n\n[판정과 원시 호출](../artifacts/run-001/{cid}/judge/result.json)'
 q=ADR/'실험'/m['questions'][i-1]['file'];q.write_text(f'# 질문 {i:03} — {cid}\n\n'+'\n\n'.join(f'## {j}. {h}\n\n{s}' for j,(h,s) in enumerate(zip(headers,sections),1))+'\n');m['questions'][i-1]['sha256']=sha(q)
 table+=f'| [{cid}]({q.name}) | {row["required"]} | {row["indexed_required"]} | {row["vector50"]} | {row["dense_top10"]} | {row["dense-rerank_top10"]} |\n'
(ADR/'실험/README.md').write_text('# CM51 전체 원문 벡터 비교\n\n필수 조문 회수 수이며 법률 정답 수가 아니다.\n\n'+table)
put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
summary=f'외규70문서 전체 저장 원문 {coverage["source_characters"]:,}자, {coverage["chunks"]:,}벡터. 누락0. 벡터10 {metrics["dense"]["retrieved_at10"]}/{den}, 리랭커10 {metrics["dense-rerank"]["retrieved_at10"]}/{den}. MAIN unchanged.'
sections=[summary,'기존 캐시는 문서 일부와 구역 앞800자만 포함했다. 이번은 선택70문서 전체 block 텍스트를 구조 경계에 묶고 토큰 한도 내 중첩분할한다.','[사전 기준](artifacts/design/criteria.json). 구축 무누락과 검색 개선은 별도 판정.','동일 질문→BGE-M3→그룹50→그대로/리랭커→10→원문→동일 Qwen. 별도 참조 확장·정답 기반 검색 없음.','[freeze](artifacts/design/freeze.json), [vector manifest](artifacts/run-001/vector-manifest.json), [coverage](artifacts/run-001/coverage.json). 모델·원문 공유, 신규 원문 복제 없음.',summary+'\n\n[전체 결과](artifacts/run-001/result.json) · [질문별](실험/README.md)',json.dumps(dict(pairs),ensure_ascii=False)+'\n\n현재 source hash와 정확 좌표가 확인된 필수 근거만 집계한다. 과거0970의 좌표 미결속 점수와 직접 전후 비교하지 않는다.','[자원 원장](artifacts/resource-embed.json). '+json.dumps({'metrics':metrics,'calls':calls,'usage':result['usage']},ensure_ascii=False),'저장된 구조화 텍스트의 전체 색인 구축 확인이다. 원문 파싱 품질이나 법률 정답 전체 인증이 아니다.','\n'.join('- '+x for x in result['limitations']),'Proposed, in-sample, decision_eligible=false. 제품 코드·활성 MAIN·GENOS 변경 없음. 연구 산출물은 명시 runner로만 사용한다.','`06_TOOLS/EXPERIMENTS/adr_0971/run.py corpus|embed|retrieve|rerank|answer`. 완료 stage 재실행 금지. 신규 모델 비교는 새 ADR. 중단 embed는 동일 pin/deadline과 검증된 shard를 사용한1회 재개만 허용한다.']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 구조화 외규70 전체 벡터 구축\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{s}' for i,(t,s) in enumerate(zip(titles,sections),1))+'\n')
(ADR/'RESULT.txt').write_text(summary+'\n\n'+json.dumps({k:result[k] for k in ['build_complete','build_success','coverage','required','indexed_required','vector50_hits','by_arm','semantic_answer_comparison_complete','actual_external_calls','source_checks','limitations']},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['build_complete','coverage','required','indexed_required','vector50_hits','by_arm','actual_external_calls']},ensure_ascii=False,indent=2))
