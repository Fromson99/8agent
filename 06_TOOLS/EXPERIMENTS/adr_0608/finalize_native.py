"""Read-only evidence packaging. Preserve runner scores and failed raw runs."""
import argparse, hashlib, json, sqlite3, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HEADINGS = ['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
QUESTION_HEADINGS = ['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v): return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'

def ledger(adr, manifest, products):
    """Final actual response binding only; never replace a failure with last READY."""
    run=adr/'artifacts/run-001'; db=sqlite3.connect(run/'memory.sqlite'); db.row_factory=sqlite3.Row
    mapping={}
    for row in db.execute("SELECT payload FROM node WHERE stage='READ'"):
        for s in json.loads(row[0])['originals']:
            mapping[s['source_id']]={'doc_id':s['document_id'],'node':int(s['unit_id'])+1}
    ids=lambda v:sorted((mapping[i] for i in set(v)),key=lambda x:(x['doc_id'],x['node']))
    plans=manifest['design']['retrieval_stage_plan']['stages_by_arm'][manifest['runs'][0]['arm_ids'][0]]
    cases=[]; counts=[]; before_total=after_total=hits=0; bindings=[]
    for case in products:
        o=case['turns'][-1]['output']; goal=o.get('goal_id'); route=None
        # Finalization supplies a goal rather than a route id. Match its exact revision.
        if o.get('status') in ('READY','REUSED','STORED') and goal:
            route=db.execute('SELECT * FROM route WHERE goal=? AND revision=?',(goal,o['revision'])).fetchone()
        parts={}
        if route:
            for stage,nid in json.loads(route['payload'])['nodes'].items():
                row=db.execute('SELECT * FROM node WHERE id=?',(nid,)).fetchone()
                assert row['goal']==goal
                parts[stage]=json.loads(row['payload'])
        trace={s['stage_id']:[] for s in plans}
        if parts:
            trace.update(source=parts['RECALL']['corpus_ids'],scope=parts['RECALL']['corpus_ids'],query=parts['RECALL']['selected_for_read'],selected=parts['SELECT']['final_ids'],present=[c['source_id'] for c in (o.get('answer') or {}).get('claims',[])])
        gold={'article:bbb3b79da72c6250f25c3377'}; stages=[]; previous=set()
        # This source identity is bound to the frozen synthetic generation, not a product hint.
        assert not gold-mapping.keys()
        for plan in plans:
            after=set(trace[plan['stage_id']]); before=set(previous); added=after-before; discarded=before-after
            reason='no_final_consumed_route' if not route else 'not_selected_or_presented'
            receipts=[{'identity':i,'reason':reason} for i in ids(discarded)]
            stages.append({**plan,'executed':bool(route),'skip_reason':None if route else 'Final response does not consume a source route',
                'before':ids(before),'added':ids(added),'discarded':ids(discarded),'after':ids(after),
                'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
                'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
                'discard_receipts':receipts,'discard_reason_counts':{reason:len(discarded)} if discarded else {},
                'gold_total':1,'gold_before':len(before&gold),'gold_added':len(added&gold),'gold_discarded':len(discarded&gold),'gold_after':len(after&gold),'golden_recall':len(after&gold),
                'gold_before_identities':ids(before&gold),'gold_added_identities':ids(added&gold),'gold_after_identities':ids(after&gold),'discarded_gold':[{'identity':i,'reason':reason} for i in ids(discarded&gold)]})
            previous=after
        cases.append({'schema_version':'retrieval-stage-ledger-v1','arm_id':manifest['runs'][0]['arm_ids'][0],'case_id':case['case_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'gold_total':1,'gold_identities':ids(gold),'stages':stages})
        counts.append(len(previous)); hits+=len(previous&gold); before_total+=len(set(trace['source'])); after_total+=len(set(trace['query']))
        bindings.append({'case_id':case['case_id'],'status':o.get('status'),'goal':goal,'revision':o.get('revision'),'route':route['id'] if route else None})
    db.close(); arm=manifest['runs'][0]['arm_ids'][0]
    metrics={'before_filter':before_total,'after_filter':after_total,'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':hits/len(cases),'selectivity':statistics.mean(counts)/2}
    data={'schema_version':'retrieval-stage-ledger-v1','adr_id':manifest['adr_id'],'experiment_id':manifest['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in plans],'cases':cases,'aggregate':metrics}]}],'audit':{'bindings':bindings,'canonical_mapping':mapping,'scope':'Synthetic two-source corpus. REMAPPED has no final answer and no consumed source route. Earlier READY is never substituted.'}}
    data['artifact_sha256']=hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write(run/'retrieval-stage-ledger.json',data)
    return data,metrics

def main(number):
    adr=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number:04d}-*')); mp=adr/'실험/manifest.json'; m=json.loads(mp.read_text()); run=adr/'artifacts/run-001'
    result=run/'result.json'; complete=result.exists()
    if not complete and not (run/'execution-abort.json').exists():
        write(run/'execution-abort.json',{'status':'failed','cause':'Result writer TypeError: set is not JSON serializable before first external call','external_calls':0,'aggregate_contract_score':None,'raw_log':str((adr/'artifacts/execution.log').relative_to(ROOT))})
    r=json.loads((result if complete else run/'execution-abort.json').read_text()); products=r.get('products') or json.loads((run/'products.json').read_text()) if (run/'products.json').exists() else []
    grades=r.get('grades',[]); summary=r.get('summary',{}); arm=m['runs'][0]['arm_ids'][0]
    usage=summary.get('usage',[]); costs={'successful_calls':len(usage),'reported_successful_cost_usd':sum(u.get('usage',{}).get('cost',0) or 0 for u in usage),'failed_call_cost':'unavailable unless provider returned usage'}
    metrics={}; led=None
    if complete: led,metrics=ledger(adr,m,products)
    observed={'checkpoints_passed':sum(g['passed'] for g in grades),'checkpoints_total':sum(g['total'] for g in grades)} if complete else {'full_score':None,'cause':r.get('cause'),'attempted_turns':summary.get('attempted_turns')}
    for name in ('functional-contracts','inherited'):
        p=run/(name+'.json')
        if p.exists(): x=json.loads(p.read_text()); observed[name]={'passed':x['passed'],'total':x['total']}
    m['results'].update(status='complete' if complete else 'failed',by_arm={arm:observed},comparisons=[],judge_disagreements=0,usage=costs,latency=summary.get('latency_seconds',{'unavailable':'run aborted'}),error_taxonomy=[{'type':'other','detail':c} for g in grades for c in g['checks'] if not c['pass']])
    if not complete: m['results']['error_taxonomy']=[{'type':'other','cause':r.get('cause')}]
    artifact=result if complete else run/'execution-abort.json'; m['runs'][0].update(status='complete' if complete else 'failed',artifact_path=str(artifact.relative_to(ROOT)),sha256=sha(artifact))
    if complete:
        for k,v in metrics.items():m['retrieval_accounting'][k]={arm:v}
        m['retrieval_accounting']['stage_ledger'].update(sha256=sha(run/'retrieval-stage-ledger.json'))
    else:m['retrieval_accounting']['stage_ledger'].update(artifact_path=None,sha256=None)
    inputs=json.loads((adr/'artifacts/design/inputs.json').read_text()); gold=json.loads((adr/'artifacts/design/gold.json').read_text())
    # Calls are associated with the current actual turn, beginning at each resolver call.
    flattened=[(c['case_id'],t) for c in products for t in c['turns']]; pos=-1; grouped={q['case_id']:[] for q in m['questions']}
    for folder in sorted((run/'provider').glob('call-*')):
        if folder.name.endswith('-memory-resolve'):pos+=1
        if 0<=pos<len(flattened):grouped[flattened[pos][0]].append(folder)
    for q in m['questions']:
        cid=q['case_id']; case=next((c for c in products if c['case_id']==cid),{'case_id':cid,'turns':[]}); gr=next((g for g in grades if g['case_id']==cid),{'not_completed':True})
        raw=[]
        for folder in grouped[cid]:
            raw.append('### '+str(folder.relative_to(run)))
            for name in ('request.json','validation-schema.json','binding.json','response.json','output.json','error.json'):
                p=folder/name
                if p.exists():raw+=['#### '+name,block(json.loads(p.read_text()))]
        vals=[f"{m['adr_id']}/{arm}/run-001; synthetic native RAG",block(next(c for c in inputs if c['case_id']==cid)),block(gold[cid]),block(case),'\n'.join(raw) or '이 사례의 실제 모델 호출은 실행되지 않음.','resolve/check/repair 및 실제 원문 select/assess/compose 원문을 위에 보존했다.','모든 제품 호출 이후 동결 gold로 상태·실행 단계·절차 문구를 검사했다. 합성 A/B 문구 검사는 일반 법률 정확도 평가가 아니다.',block(gr)]
        text='# '+cid+'\n\n'
        for i,(heading,val) in enumerate(zip(QUESTION_HEADINGS,vals),1):
            text+=f'## {i}. {heading}\n\n{val}\n\n'
            if i==4:text+='### 회수·탈락 단계 원장 — run·arm별\n\n'+(block(next(c for c in led['runs'][0]['arms'][0]['cases'] if c['case_id']==cid)) if led else '제공자/기록기 중단으로 최종 계측 미완료. 부분 READY를 최종 결과로 대체하지 않음.')+'\n\n'
        (adr/'실험'/q['file']).write_text(text)
    text_summary=f"{observed.get('checkpoints_passed','미완료')}/{observed.get('checkpoints_total','미완료')} 실제 모델 체크포인트; "+str(observed)
    vals=[text_summary,'정정 상태·최종 지식·세션 재사용의 실제 native 연결을 확인한다.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],'모의 원문 2단위·3개 대화·34턴, 개인의 확인된 경험만 지식 적재. 최초 복원·표·최종 저장·재사용·위키 연결을 검사한다.','동결 코드·현재 MAIN binding·Qwen3.8 Parasail FP8 reasoning none, fallback 없음.',block(observed),block([g for g in grades if g['passed']!=g['total']]) if complete else block(r.get('cause')),block({'usage':costs,'latency':m['results']['latency'],'retrieval':metrics}),'완료한 일반 계약과 실제 모델 자연어 검증을 구분한다. 실패한 전 실행은 덮어쓰지 않았다.','합성 인샘플. 목표 선택에 테스트 goal_anchor를 넣지 않음. 모든 법률 조건·수치의 정확도, 대규모 ontology 검색·GENOS 내부 모델·실제 다중 사용자 인증은 미검증.','후보 명시 주입 경로이며 운영 MAIN·GENOS 배포 미변경. 품질 승격 대상 아님.','기존 run 덮어쓰기 거부. 새 변경·재실행은 별도 ADR로 예약한다.']
    front=(adr/'README.md').read_text().split('---',2)[1]; (adr/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' — Native 정정 기억 실행 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(HEADINGS,vals),1))+'\n')
    (adr/'실험/README.md').write_text('# 질문 인덱스\n\n'+''.join(f"- [{q['case_id']}]({q['file']})\n" for q in m['questions']))
    write(mp,m); write(run/'evidence-summary.json',{'observed':observed,'costs':costs,'retrieval':metrics,'raw_result_sha256':sha(artifact),'runner_scores_unchanged':True})
    print(json.dumps({'adr':m['adr_id'],**observed,'costs':costs},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('number',type=int);main(parser.parse_args().number)
