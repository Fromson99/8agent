"""Post-selection gold join, source audit and report; no product calls."""
from common import *
import sys,sqlite3,statistics,collections,csv
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
assert (RUN/'rerank-receipt.json').exists()
cases=read(DES/'cases.json');refs={x['id']:x for x in read(DES/'offline-reference.json')};corpus=read(RUN/'corpus-summary.json');criteria=read(DES/'criteria.json')
m=read(ADR/'실험/manifest.json');freeze=read(DES/'freeze.json')
assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
indexed={tuple(x) for x in corpus['indexed_articles']};allowed=set(criteria['scope']);by_arm={'dense':[],'dense-rerank':[]};graded=[];rows=[];audits=[];usages=[];model_calls=0
data=ROOT/criteria['generation_path'];db=sqlite3.connect((data/'store.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
nav=sqlite3.connect((data/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
def identities(rows,field='article'):return [{'doc_id':x['doc_id'],'node':int(x[field])} for x in rows]
def keys(rows):return {(x['doc_id'],x['node']) for x in rows}
def htext(text):return hashlib.sha256(text.encode()).hexdigest()
def percentile(v,p):
    a=sorted(v);return a[min(len(a)-1,max(0,round((len(a)-1)*p)))] if a else None
for c in cases:
    cid=c['id'];d=RUN/cid;pool=readgz(d/'pool.json.gz');ranked=readgz(d/'rerank.json.gz');gold=[];refaudit=[]
    for t in refs[cid]['targets']:
        if t.get('role')!='required':continue
        if not str(t.get('node','')).isdigit():
            refaudit.append({'target':t,'included':False,'reason':'no exact numeric article identity'});continue
        identity={'doc_id':t['doc_id'],'node':int(t['node'])};gold.append(identity)
        u=db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',(t['doc_id'],str(t['node']))).fetchone()
        unit=json.loads(u[0]) if u else None
        versions=[]
        for v, in nav.execute('SELECT json FROM source WHERE document_id=? AND article=?',(t['doc_id'],t['article'])):
            x=json.loads(v);versions.append({'source_id':x['id'],'text_sha256':htext(x.get('text','')),'reference_hash_match':htext(x.get('text',''))==t.get('source_text_sha256')})
        refaudit.append({'identity':identity,'included':True,'in_vector_corpus':(t['doc_id'],int(t['node'])) in indexed,'in_public_scope':t['doc_id'] in allowed,'coordinate_key_matches':bool(unit and unit.get('coordinate_key')==t.get('coordinate_key')),'reference_hash_matches':any(x['reference_hash_match'] for x in versions),'current_versions':versions})
    g=keys(gold);poolids=identities(pool);rids=identities(ranked)
    row={'id':cid,'required':len(g),'in_index':len(g&indexed),'vector50':len(g&keys(poolids))}
    for arm,rankids in [('dense',poolids),('dense-rerank',rids)]:
        ctx=readgz(d/(arm+'-context.json.gz'));present=identities(ctx['sources'],'node');top10=rankids[:10]
        checks=[]
        for s in ctx['sources']:
            actual=[]
            for b in s['block_ids']:
                got=db.execute('SELECT text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?',(s['doc_id'],str(b))).fetchone()
                assert got and got[1]==s['source_artifact_sha256'];actual.append(got[0])
            assert htext('\n'.join(actual))==s['text_sha256'] and '\n'.join(actual)==s['text'] and s['doc_id'] in allowed
            checks.append({'doc_id':s['doc_id'],'node':s['node'],'exact_source':True,'scope':True})
        audits.extend(checks)
        rec=StageLedgerRecorder(cid,arm,identity_canonicalizer);rec.record_stage('vector50','source',poolids)
        rec.record_stage('rank','rerank',rankids,parent_stage_ids=['vector50'])
        rec.record_stage('top10','select',top10,parent_stage_ids=['rank'],discard_reasons=[{'identity':x,'reason':'outside_frozen_top10'} for x in rankids if x not in top10])
        rec.record_stage('present','present',present,parent_stage_ids=['top10'],discard_reasons=[{'identity':x,'reason':'whole_article_context_budget'} for x in top10 if x not in present])
        ledger=grade_capture(rec.capture(),gold);graded.append(ledger)
        stats={'id':cid,'required':len(g),'hit10':len(g&keys(top10)),'prepared_hits':len(g&keys(present)),'prepared_count':len(present),'all_required_top10':bool(g and g<=keys(top10)),'all_required_prepared':bool(g and g<=keys(present)),'rerank_seconds':read(d/'rerank-timing.json')['seconds'] if arm=='dense-rerank' else 0,'retrieval_seconds':read(d/'retrieval.json')['seconds'],'answer_status':'not_run','semantic_verdict':'not_scored'}
        ar=d/arm/'result.json'
        if ar.exists():
            a=read(ar);stats['answer_status']=a['status'];model_calls+=a['calls'];usages.extend(a['usage'])
        judge=d/'judge/result.json'
        if judge.exists():
            j=read(judge)
            if j['status']=='complete':
                label=next(k for k,v in j['labels'].items() if v==arm);stats['semantic_verdict']=j['judgment'][label]['verdict']
        by_arm[arm].append(stats);row[arm+'_top10']=stats['hit10'];row[arm+'_prepared']=stats['prepared_hits']
    put(d/'reference-audit.json',refaudit);rows.append(row)
db.close();nav.close()
for path in RUN.glob('cm-*/judge/result.json'):
    j=read(path);model_calls+=j['calls'];usages.extend(j['usage'])
run=build_run_artifact('run-001',graded,{a:['vector50','rank','top10','present'] for a in by_arm})
ledger=build_experiment_artifact('ADR-0969',m['experiment_id'],[run]);put(RUN/'retrieval-ledger.json',ledger)
den=sum(x['required'] for x in rows);available=sum(x['in_index'] for x in rows);metrics={}
for arm,values in by_arm.items():
    counts=[x['prepared_count'] for x in values];hits=sum(x['hit10'] for x in values);prepared=sum(x['prepared_hits'] for x in values)
    durations=[x['retrieval_seconds']+x['rerank_seconds'] for x in values]
    metrics[arm]={'status':'complete','retrieval_cases':len(values),'required':den,'retrieved_at10':hits,'recall_at10':hits/den,'recall_at10_among_indexed_required':hits/available if available else None,'all_required_at10':sum(x['all_required_top10'] for x in values),'prepared_hits':prepared,'prepared_recall':prepared/den,'all_required_prepared':sum(x['all_required_prepared'] for x in values),'prepared_total':sum(counts),'prepared_mean':statistics.mean(counts),'prepared_p50':statistics.median(counts),'prepared_p95':percentile(counts,.95),'selectivity':statistics.mean(counts)/corpus['counts']['indexed_articles'],'answer_outcomes':dict(collections.Counter(x['answer_status'] for x in values)),'answer_correct':sum(x['semantic_verdict']=='pass' for x in values),'answer_scored':sum(x['semantic_verdict'] in ('pass','fail') for x in values),'latency_p50':statistics.median(durations),'latency_p95':percentile(durations,.95)}
pairs=collections.Counter()
for a,b in zip(by_arm['dense'],by_arm['dense-rerank']):
    key='both_covered' if a['all_required_top10'] and b['all_required_top10'] else 'rerank_only' if b['all_required_top10'] else 'dense_only' if a['all_required_top10'] else 'neither_covered';pairs[key]+=1
delta=metrics['dense-rerank']['recall_at10']-metrics['dense']['recall_at10']
success=delta>=.05 and metrics['dense-rerank']['all_required_at10']>metrics['dense']['all_required_at10'] and pairs['dense_only']<=2
result={'status':'complete_with_corpus_blockers','retrieval_execution_complete':True,'answer_quality_complete':all(x['answer_scored']==51 for x in metrics.values()),'quality_certified':False,'main_changed':False,'genos_executed':False,'corpus':corpus['counts'],'required':den,'required_in_vector_index':available,'vector50_hits':sum(x['vector50'] for x in rows),'by_arm':metrics,'paired_all_required_source_coverage':dict(pairs),'recall_delta':delta,'success_criteria_met':success,'actual_external_calls':model_calls,'usage_reported_calls':len(usages),'usage':{k:sum(u.get(k) or 0 for u in usages) for k in ('input_tokens','output_tokens','total_tokens','cost_usd')},'cost_note':'Only provider reported successful usage; missing usage is not zero billing','source_checks':{'checked_context_articles':len(audits),'mismatches':0},'limitations':['Known CM51 in-sample','Legacy vector coverage21/65 public documents; cannot certify full-corpus dense performance','Legacy800 character heads, no new chunking, small existing multilingual cross encoder512 token truncation','Raw registered-coordinate recall is diagnostic; reference source hash/version drift audited separately','Prepared context counts differ from actually delivered LLM context when provider blocks','No paired MAIN98 answer-quality comparison','Generation/evaluation same Qwen model; no human calibration'], 'cases':rows}
put(RUN/'result.json',result)
with (RUN/'summary.csv').open('w',encoding='utf-8-sig',newline='') as o:
    w=csv.DictWriter(o,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete_with_corpus_blockers',by_arm=metrics,comparisons=[{'baseline':'dense','candidate':'dense-rerank','recall_at10_delta':delta,'source_coverage_pairs':dict(pairs),'semantic_answer_comparison':'not established unless separately scored pairs complete'}],judge_disagreements=None,usage={'actual_external_calls':model_calls,**result['usage']},latency={a:{'p50':v['latency_p50'],'p95':v['latency_p95']} for a,v in metrics.items()},error_taxonomy=[{'kind':'retrieval_miss','scope':'registered targets missing in frozen vector corpus or top10; see per-question ledgers'},{'kind':'other','scope':'provider errors and unexecuted semantic grading preserved'}])
account=m['retrieval_accounting'];account.update(corpus_total=corpus['counts']['indexed_articles'],before_filter={a:51*50 for a in by_arm},after_filter={a:51*10 for a in by_arm})
for k,source_key in [('presented_total','prepared_total'),('presented_mean','prepared_mean'),('presented_p50','prepared_p50'),('presented_p95','prepared_p95'),('golden_recall','prepared_recall'),('selectivity','selectivity')]:account[k]={a:v[source_key] for a,v in metrics.items()}
account['presentation_semantics']='Frozen prepared answer context; actual sent/returned counts are separate answer outcomes.'
account['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
table='| 질문 | 필수 | 색인에 있음 | 벡터50 | 벡터10 | 리랭커10 |\n|---|---:|---:|---:|---:|---:|\n'
for i,(case,row) in enumerate(zip(cases,rows),1):
    cid=case['id'];d=RUN/cid
    sections=[f'run-001 / dense, dense-rerank / exact. 기준 동결 {m["reservation"]["created_at"]}. 실제 실행시각·모델 파일: artifacts/run-001의 단계 receipt 및 design/models.json.',case['question'],refs[cid]['reference_answer'],
     f'전체 indexed article {corpus["counts"]["indexed_articles"]}. 후보50→상위10→32000자 안의 온전한 조문. 제품에는 정답·필수좌표 미제공. 원문 중복 복사를 피하기 위해 무손실 원장을 연결한다.\n\n[벡터 후보 전체](../artifacts/run-001/{cid}/pool.json.gz) · [리랭커 순위 전체](../artifacts/run-001/{cid}/rerank.json.gz) · [벡터 원문 전체](../artifacts/run-001/{cid}/dense-context.json.gz) · [리랭커 원문 전체](../artifacts/run-001/{cid}/dense-rerank-context.json.gz) · [단계별 탈락 원장](../artifacts/run-001/retrieval-ledger.json) · [정답 판본 대조](../artifacts/run-001/{cid}/reference-audit.json)',
     '생성 모델은 Qwen3.8 / Parasail FP8 / reasoning none. 실제 전송한 모든 payload와 응답은 아래 raw 원장에 보존. 미전송은 답변 오답으로 계산하지 않는다.',
     '중간 LLM 호출 없음. 로컬 BGE-M3 질의 인코딩과 고정 cross encoder 점수만 사용. 전체 문서 범위 확장·참조 추적 없음.',
     '평가 가능한 완성 답변 쌍만 동결 judge로 판정. 판정 미수행은 정답률 미측정.',
     '```json\n'+json.dumps({a:by_arm[a][i-1] for a in by_arm},ensure_ascii=False,indent=2)+'\n```\n\n검색 실패와 색인 미확보, provider 실패를 분리한다. 근거 검색 성공은 답변 정답 인증이 아니다.']
    for arm in by_arm:
        ar=d/arm/'result.json'
        if ar.exists():sections[4]+=f'\n\n[{arm} 실제 결과](../artifacts/run-001/{cid}/{arm}/result.json) · [raw 디렉터리](../artifacts/run-001/{cid}/{arm}/raw)'
        else:sections[4]+=f'\n\n{arm}: provider 중단 정책에 따라 생성 미실행.'
    if (d/'judge/result.json').exists():sections[6]+=f'\n[채점 원문](../artifacts/run-001/{cid}/judge/result.json)'
    text=f'# 질문 {i:03d} — {cid}\n\n'+'\n\n'.join(f'## {j}. {h}\n\n{s}' for j,(h,s) in enumerate(zip(headers,sections),1))+'\n'
    q=ADR/'실험'/m['questions'][i-1]['file'];q.write_text(text);m['questions'][i-1]['sha256']=sha(q)
    table+=f'| [{cid}]({q.name}) | {row["required"]} | {row["in_index"]} | {row["vector50"]} | {row["dense_top10"]} | {row["dense-rerank_top10"]} |\n'
(ADR/'실험/README.md').write_text('# CM51 벡터·리랭커 비교\n\n숫자는 필수 조문 회수 수이며 답변 정답 수가 아니다. 원시 입출력은 각 질문의 무손실 파일 링크를 따른다.\n\n'+table)
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
summary=f'벡터10: {metrics["dense"]["retrieved_at10"]}/{den} ({metrics["dense"]["recall_at10"]:.1%}), 리랭커10: {metrics["dense-rerank"]["retrieved_at10"]}/{den} ({metrics["dense-rerank"]["recall_at10"]:.1%}). 차이 {delta:+.1%}p. 사전 검색 기준 통과={success}. 최종 답변 우위는 미확인.'
sections=[summary+' MAIN unchanged, Proposed. 원문 색인 범위 한계를 포함한 탐색 실험이며 품질 인증이 아니다.',
 '선택 MAIN98은 전체 공개65 범위의 도구 기반 탐색이며 선택 generation에 dense descriptor가 없다. 이번은 별도 연구 runner에서 기존 벡터 캐시의 순수 검색과 로컬 리랭커를 비교한다.',
 '[사전 동결 설계](artifacts/design/criteria.json). 리랭커 recall@10 5%p 이상 상승, 전체 필수 근거 충족 증가, 새 누락2건 이하를 사전 기준으로 두었다.',
 'CM51 원문 질문→BGE-M3→최대 코사인으로 조문50→그대로/리랭커→조문10→온전한 원문32000자→동일 Qwen 답변. 변경 단계만 격리 snapshot이며 정답은 선택 이후 평가에만 제공했다.',
 f'현재 MAIN98 store hash 고정. 기존120445벡터 중 범위·입력해시 대조를 통과한20582행, 공개65문서 중21문서다. 16개 분산 표본 fresh embedding cosine 검사 통과. 같은 해시의 모델 weight hardlink 사용. [결속](artifacts/design/freeze.json) · [모델](artifacts/design/models.json). 전체 법령·기준답변 최신성 인증 없음.',
 summary+'\n\n[질문별 비교](실험/README.md) · [전체 지표](artifacts/run-001/result.json) · [CSV](artifacts/run-001/summary.csv). 전체 필수근거 충족 쌍: '+json.dumps(dict(pairs),ensure_ascii=False),
 f'등록 필수좌표 {den}개 중 벡터 색인에 있는 것은 {available}개, 벡터50에 들어온 것은 {result["vector50_hits"]}개. 원문 버전/좌표 차이는 질문별 reference-audit에 따로 남겼다. 색인 없는 문서 실패와 리랭커 손실을 구분한다.',
 json.dumps({'by_arm':metrics,'external_calls':model_calls,'usage':result['usage'],'resource_receipts':'artifacts/resource-*.json'},ensure_ascii=False,indent=2)+'\n\n준비된 문맥 수와 실제 LLM 전송 수를 구분한다. 지연은 CPU 모델 로드/색인검사/질의 임베딩 제외 retrieve+rerank이며 전체 단계 receipt를 함께 보존한다.',
 '이 실험은 기존 벡터 캐시와 이 특정 소형 리랭커의 동작을 관찰한다. 다른 임베딩·청크·리랭커 또는 전체 최신 색인을 시험한 결과가 아니다. MAIN과의 최종 답변 정확도 비교는 성립하지 않았다.',
 '\n'.join('- '+x for x in result['limitations'])+'\n\n답변 생성/채점 실행 상태: [생성](artifacts/run-001/answer-summary.json), [채점](artifacts/run-001/judge-summary.json). 실패는 법률 오답으로 집계하지 않는다.',
 'Proposed, decision_eligible=false, MAIN/활성 데이터/GENOS 불변. 후속 후보나 새 전체 색인 비교는 새 ADR에 동결한다. 실패 기록·기존 원문은 보존하며 별도 승격 없음.',
 '실제 runner: `06_TOOLS/EXPERIMENTS/adr_0969/run.py corpus|embed|retrieve|rerank|answer`, `judge.py`, `report.py`. 이미 실행된 단계는 재실행 거절. `resource_guard.py`의 단일 lock과 RSS5.5GiB·가용RAM3GiB 기준을 사용했다. 새 호출은 새 ADR 필요. 계약 검사7통과. 최종 구조 검증과 graph 검사는 별도 원문 로그를 따른다.']
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
(ADR/'README.md').write_text('---'+front+'---\n\n# 단순 벡터 검색과 리랭커 비교\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{s}' for i,(t,s) in enumerate(zip(titles,sections),1))+'\n')
print(json.dumps({k:result[k] for k in ['required','required_in_vector_index','vector50_hits','by_arm','paired_all_required_source_coverage','success_criteria_met','actual_external_calls']},ensure_ascii=False,indent=2))
