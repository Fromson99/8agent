"""Preserve failed experiment; reconstruct canonical telemetry without rerunning selection."""
from common import *
import sys,sqlite3,statistics
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
reason='Compound legal_coordinate.unit remains 조 for 항/호/목; original article_root incorrectly treated those descendants as article roots. Retrieval deduplication and whole-article expansion violated frozen design. All efficacy conclusions INVALID. Two completed generated answers retained; next physical call interrupted with unknown provider outcome. No rerun or semantic scoring.'
db=sqlite3.connect('file:'+str(ROOT/read(DES/'criteria.json')['generation_path']/'store.sqlite')+'?mode=ro',uri=True);cache={}
def canonical(coord):
    d,n=coord
    if (d,n) in cache:return cache[d,n]
    seen=set();current=n
    while current is not None:
        if current in seen:raise ValueError('cycle')
        seen.add(current);r=db.execute('SELECT parent_id,json FROM source_unit WHERE document_id=? AND unit_id=?',(d,str(current))).fetchone()
        if not r:return (d,n)
        parent,raw=r;u=json.loads(raw);c=u.get('legal_coordinate') or {}
        if u.get('family')=='kr_article' or c.get('unit')=='조' and not c.get('chain'):
            cache[d,n]=(d,int(current));return cache[d,n]
        current=parent
    return (d,n)
def ids(rows,field):return sorted(set(canonical((r['doc_id'],int(r[field]))) for r in rows))
def reasons(before,after,why):return [{'identity':{'doc_id':d,'node':n},'reason':why} for d,n in before if (d,n) not in after]
m=read(ADR/'실험/manifest.json');cases=read(DES/'cases.json');refs={x['id']:x for x in read(DES/'offline-reference.json')};graded=[]
for case in cases:
    cid=case['id'];d=RUN/cid;pool=readgz(d/'pool.json.gz');rank=readgz(d/'rerank.json.gz')
    gold=[(t['doc_id'],int(t['node'])) for t in refs[cid]['targets'] if t.get('role')=='required' and str(t.get('node','')).isdigit()]
    for arm,rows in [('dense',pool),('dense-rerank',rank)]:
        first=ids(pool,'article');ordered=ids(rows,'article');selected=ids(rows[:10],'article');present=ids(readgz(d/(arm+'-context.json.gz'))['sources'],'node')
        r=StageLedgerRecorder(cid,arm,identity_canonicalizer);r.record_stage('vector50','source',first);r.record_stage('rank','rerank',ordered,parent_stage_ids=['vector50'])
        r.record_stage('top10','select',selected,parent_stage_ids=['rank'],discard_reasons=reasons(ordered,selected,'original_invalid_unit_top10'))
        r.record_stage('present','present',present,parent_stage_ids=['top10'],discard_reasons=reasons(selected,present,'original_context_budget'))
        graded.append(grade_capture(r.capture(),gold))
artifact=build_experiment_artifact('ADR-0969',m['experiment_id'],[build_run_artifact('run-001',graded,{a:['vector50','rank','top10','present'] for a in ['dense','dense-rerank']})])
artifact['audit']={'reconstructed':True,'reason':reason,'original_rankings_unchanged':True,'scope':'canonical identities reconstructed only for truthful accounting; no new candidate run'}
from lawrag.runtime.retrieval_stage_ledger import deterministic_sha256
artifact.pop('artifact_sha256');artifact['artifact_sha256']=deterministic_sha256(artifact);put(RUN/'retrieval-ledger.json',artifact)
count=len({canonical(tuple(x)) for x in read(RUN/'corpus-summary.json')['indexed_articles']});account=m['retrieval_accounting'];account['corpus_total']=count
for key in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:account[key]={}
for arm in ['dense','dense-rerank']:
    ls=[x for x in graded if x['arm_id']==arm];counts=[x['stages'][-1]['after_count'] for x in ls];hits=sum(x['stages'][-1]['gold_after'] for x in ls);den=sum(x['gold_total'] for x in ls)
    for k,v in {'before_filter':sum(x['stages'][0]['after_count'] for x in ls),'after_filter':sum(x['stages'][2]['after_count'] for x in ls),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':hits/den,'selectivity':statistics.mean(counts)/count}.items():account[k][arm]=v
account['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json');account['invalid_measurement_notice']=reason
physical=list(RUN.glob('cm-*/*/raw/call-*/request.json'));finished=list(RUN.glob('cm-*/*/result.json'))
result={'status':'invalid','reason':reason,'physical_attempts':len(physical),'completed_arm_results':len(finished),'new_adr':'ADR-0970','main_changed':False,'efficacy_scores_withheld':True}
put(RUN/'result.json',result);put(RUN/'answer-summary.json',result);put(RUN/'judge-summary.json',{'attempted':0,'reason':'invalid source-selection implementation'})
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='invalid',by_arm={a:{'status':'invalid','reason':reason} for a in ['dense','dense-rerank']},comparisons=[],judge_disagreements=None,usage={'physical_attempts':len(physical),'unknown_interrupted_attempts':len(physical)-len(finished)},latency={'not_comparable':reason},error_taxonomy=[{'type':'other','reason':reason}]);m['design']['invalidated_after_execution']=reason
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
index='# 무효 실험 질문 원장\n\n'+reason+'\n\n'
for q,c in zip(m['questions'],cases):
    cid=c['id'];sections=[f'ADR0969 run-001, exact original files; reconstructed canonical audit. INVALID.',c['question'],refs[cid]['reference_answer'],f'[벡터 후보](../artifacts/run-001/{cid}/pool.json.gz) · [리랭커](../artifacts/run-001/{cid}/rerank.json.gz) · [벡터 원문](../artifacts/run-001/{cid}/dense-context.json.gz) · [리랭커 원문](../artifacts/run-001/{cid}/dense-rerank-context.json.gz) · [정규화 감사](../artifacts/run-001/retrieval-ledger.json)',f'실행된 요청·provider 원응답·스키마·usage는 artifacts/run-001/{cid}/dense 또는 dense-rerank/raw에 보존. 두 완성 결과 이후 작업자 중단. 미실행을 정답/오답으로 계산하지 않음.','중간 LLM 없음. 로컬 encoder와 cross encoder 원장은 보존.','무효 실험이므로 채점하지 않음.',reason]
    path=ADR/'실험'/q['file'];path.write_text(f'# {cid} — INVALID\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(zip(heads,sections),1))+'\n');q['sha256']=sha(path);index+=f'- [{cid}]({q["file"]})\n'
(ADR/'실험/README.md').write_text(index);put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=[reason,'조문 root 구분에서 compound legal_coordinate의 조/항 체계를 잘못 읽었다. 제품 검색·원문 확장에 영향을 줘 점수를 폐기한다.','[수정하지 않은 사전 설계](artifacts/design/criteria.json). 결과를 통과하도록 기준을 바꾸지 않았다.','CM51 dense/rerank 계획대로 로컬 검색 실행. 잘못된 article-root로 효력 무효.','원문·모델·코드·질문 동결 및 원본 보존. [freeze](artifacts/design/freeze.json).','검색·답변 품질 수치를 주장하지 않는다. 정규화한 사후 원장은 이미 선택된 항/호를 실제 조문에 연결하는 감사만 한다.','[51문항 원장](실험/README.md). 잘못된 조문 단위의 top50/top10을 새 검색으로 재구성하지 않았다.',json.dumps(result,ensure_ascii=False),'모델 성능 문제가 아니라 실험 코드 오류다.','효과 비교 불가. 생성 두 결과는 재사용하지 않으며 세 번째 시도의 provider 수락·과금은 불명이다.','Rejected/invalid. MAIN·GENOS 불변. 후속 ADR0970에 사전 재동결.','원래 runner를 재실행하지 않는다. invalid_finish.py는 사후 감사만 수행. 후보 원본·raw 파일을 보존하고 정정 사항은 별도 새 ADR에 기록.']
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR0969 무효 실험 보존\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{s}' for i,(t,s) in enumerate(zip(titles,bodies),1))+'\n')
print(result)
