"""Frozen offline criteria. Product outputs are sealed before gold is joined."""
import hashlib,importlib.util,json,sqlite3,statistics,sys
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair'
ARMS=['baseline','repaired'];RUNS=['run-001']
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    if p.exists():raise RuntimeError('Existing scoring receipt: '+str(p))
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def obj(props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
STR={'type':'string'};BOOL={'type':'boolean'}
SCHEMA=obj({'assessments':{'type':'array','minItems':2,'maxItems':2,'items':obj({'label':{'type':'string','enum':['A','B']},'correct':BOOL,'failure_type':{'type':'string','enum':['retrieval_miss','governing_rule_selection','scope_actor_mismatch','condition_exception','numeric_temporal','authority_or_version','definition_resolution','required_issue_omission','unsupported_inference','judge_or_gold_error','none']},'reason':STR,'sources':{'type':'array','items':obj({'source_key':STR,'relevant':BOOL,'reason':STR})}})}})
SYSTEM='''당신은 제품과 분리된 평가자다. 익명 A/B 각각을 독립 채점한다. correct는 저장 기준답의 결론과 핵심 조건을 답변이 실제 전달한 경우만 true. 빈 답·확인 불가·실행 오류는 false. 기준답의 현행 법률 정당성 자체는 이 평가에서 확정하지 않는다. 출처마다 원문 발췌가 질문 이해·판단에 필요한 원칙, 단서, 예외, 정의, 절차를 제공하는지를 relevant로 별도 채점한다. gold 목록에 없다고 무관하지 않으며 법적 결론이 불확실해도 필요한 원문은 관련성이 있다. 엉뚱한 조문이나 제목만 일치하는 원문은 무관. 답변 correct와 출처 relevant를 혼동하지 않는다. 모든 제공 source_key를 중복·누락 없이 그대로 반환한다. 빈 출처면 sources=[]다. 각 이유는 한두 문장.''' 
def cards(row,trace):
    b=row.get('result',{}).get('assembly',{}).get('term_agent',{}).get('source_bundle')
    if b is not None:return [{'source_key':c['selection_id'],'document_name':c['document_name'],'coordinate':c['coordinate_label'],'excerpt':c['excerpt']} for c in b['sources']]
    ids=set(row.get('stages',{}).get('answer',[]));seen=set();out=[]
    for e in trace.get('evidence',[]):
        if e['source_id'] in ids and e['source_id'] not in seen:
            seen.add(e['source_id']);out.append({'source_key':e['source_id'],'document_name':e['metadata'].get('document_name'),'coordinate':e['unit_id'],'excerpt':e['text']})
    return out

def main():
    from run_probe import pin
    pin()
    from lawrag.research.experiment_client import ExperimentClient
    products={run:read(A/'artifacts'/run/'results.json') for run in RUNS}
    assert all(x.get('finished_at') for x in products.values())
    product=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']}
    spec=importlib.util.spec_from_file_location('ledger_helper',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    gen=R/product['generation']
    with sqlite3.connect('file:'+str(gen/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
        coord={s:{'doc_id':d,'node':int(u)} for s,d,u in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(u).isdigit()}
    scope=set(product['public_scope_document_ids']);corpus=len({h.key(c) for c in coord.values() if c['doc_id'] in scope})
    plan=read(A/'실험/manifest.json')['design']['retrieval_stage_plan']['stages_by_arm'];ledgers=[];allrows=[];alljudges=[]
    for repeat,run in enumerate(RUNS):
        results=products[run];judge_out={'run_id':run,'model':'qwen/qwen3.5-122b-a10b','product_results_sha256':sha(A/'artifacts'/run/'results.json'),'cases':{},'usage':[]}
        for i,case in enumerate(product['cases']):
            cid=case['case_id'];rows=results['cases'][cid];labels={'A':ARMS[(i+repeat)%2],'B':ARMS[(i+repeat+1)%2]}
            variants=[]
            for label,arm in labels.items():
                row=rows[arm];trace=read(A/'artifacts'/run/cid/arm/'trace.json')
                variants.append({'label':label,'answer':row.get('result',{}).get('answer',{}).get('text') or '[빈 답변 또는 실행 실패]','sources':cards(row,trace)})
            client=ExperimentClient(R,A/'artifacts'/run/'judge'/cid,max_calls=2,max_output_tokens=2800)
            try:
                answer_variants=[{**v,'sources':[]} for v in variants]
                verdict=client.generate(SYSTEM,{'question':case['question'],'reference_answer':gold[cid]['reference_answer'],'variants':answer_variants},SCHEMA,phase='judge-answer-only')
                source_variants=[{**v,'answer':'[출처 관련성만 평가; 답변 평가 아님]'} for v in variants]
                relevance=client.generate(SYSTEM+' 이 호출에서는 sources[].relevant만 판단한다. correct는 모두 false로 반환한다.',{'question':case['question'],'variants':source_variants},SCHEMA,phase='judge-source-only')
                source_labels={x['label']:x for x in relevance['assessments']}
                for assessment in verdict['assessments']:
                    assessment['sources']=source_labels[assessment['label']]['sources']
                    arm=labels[assessment['label']]
                    if not rows[arm].get('result',{}).get('answer',{}).get('claims'):
                        assessment['raw_answer_judge_correct']=assessment['correct']
                        assessment['correct']=False
                        assessment['reviewed_answer_gate']='NO_REVIEWED_CLAIMS'

                assert {x['label'] for x in verdict['assessments']}==set(labels)
                by_label={x['label']:x for x in verdict['assessments']}
                for v in variants:
                    supplied=[s['source_key'] for s in v['sources']];got=[s['source_key'] for s in by_label[v['label']]['sources']]
                    assert sorted(supplied)==sorted(got),'judge omitted or duplicated source key'
                judged={a:by_label[l] for l,a in labels.items()}
                judge_error=None
            except Exception as exc:
                judge_error={'type':type(exc).__name__,'message':str(exc)}
                judged={a:{'correct':None,'reason':'evaluator failure','failure_type':'judge_or_gold_error','sources':[]} for a in ARMS}
            judge_out['cases'][cid]={'anonymous_order':labels,'by_arm':judged,'error':judge_error};judge_out['usage']+=client.usage
            print(run,cid,'judged',{a:judged[a]['correct'] for a in ARMS},flush=True)
        write(A/'artifacts'/run/'judged-results.json',judge_out);alljudges.append(judge_out)
        l_arms=[]
        for arm in ARMS:
            cases=[]
            for case in product['cases']:
                cid=case['case_id'];row=results['cases'][cid][arm];trace=read(A/'artifacts'/run/cid/arm/'trace.json');gids=h.ordered(coord[s] for s in gold[cid]['decisive_source_ids']);prev=[];stages=[]
                for st in plan[arm]:
                    raw=row.get('stages',{}).get(st['stage_id'],[])
                    after=h.ordered(coord[s] for s in raw if s in coord)
                    before_keys={h.key(x) for x in prev};after_keys={h.key(x) for x in after}
                    added=[x for x in after if h.key(x) not in before_keys];discarded=[x for x in prev if h.key(x) not in after_keys]
                    reasons={h.key(x):{'read':'not_read','presented':'not_presented_in_successful_model_view','selected':'not_explicitly_selected','final_sources':'not_delivered_in_final_source_payload'}.get(st['stage_id'],'not_carried') for x in discarded}
                    stage=h.stage(st['stage_id'],st['kind'],st['parent_stage_ids'],prev,added,discarded,reasons,gids)
                    stages.append(stage);prev=stage['after']
                cases.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(gids),'gold_identities':gids,'stages':stages})
                b=trace.get('source_bundle',{});selections=[x for x in trace.get('source_selections',[]) if x['validity']=='CURRENT' and x['payload']['status']=='SELECTED'];judge=judge_out['cases'][cid]['by_arm'][arm]
                tier_counts=Counter(c['tier'] for c in b.get('sources',[]));source_ids={c['selection_id'] for c in b.get('sources',[])}
                path=A/'artifacts'/run/cid/arm/'journal.sqlite'
                with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
                    attempts=[dict(zip(['phase','status','request_json'],x)) for x in db.execute('SELECT v.phase,a.status,a.request_json FROM model_attempt a JOIN model_view v USING(view_id)')]
                info={'run_id':run,'case_id':cid,'arm':arm,'correct':judge['correct'],'failure_type':judge['failure_type'],'judge_reason':judge['reason'],'judge_error':judge_out['cases'][cid]['error'],'sources':judge['sources'],
                    'gold_payload':stages[-2]['gold_after'],'gold_final':stages[-1]['gold_after'],'gold_total':len(gids),'gold_shown':stages[2]['gold_after'],'source_count':stages[-1]['after_count'],
                    'card_count':len(b.get('sources',[])) if arm!='baseline' else len(cards(row,trace)),
                    'execution_error':row.get('error'),'publication_status':row.get('publication_status'),'publication_error':row.get('publication_error'),
                    'selected_cards':len(selections),'lost_selections':[x['entity_id'] for x in selections if x['entity_id'] not in source_ids],
                    'tier_counts':dict(tier_counts),'tier_caps_valid':tier_counts.get('CORE',0)<=5 and tier_counts.get('SUPPLEMENTAL',0)<=5,
                    'saved_bundle_valid':row.get('saved_bundle_valid'),'semantic_errors':trace.get('errors',[]),'limitations':row.get('limitations',[]),
                    'calls':row['physical_calls'],'tool_used':row.get('budget',{}).get('tool_used',0),'seconds':row['seconds'],'controller_seconds':row.get('controller_seconds'),
                    'claims':len(row.get('result',{}).get('answer',{}).get('claims',[])),
                    'max_gateway_bytes':max([len(x['request_json'].encode()) for x in attempts],default=0),'phases':dict(Counter(x['phase'] for x in attempts)),
                    'relation_families':dict(Counter(x.get('family') for x in trace.get('notices',[])))}
                allrows.append(info)
            l_arms.append({'arm_id':arm,'declared_stage_ids':[x['stage_id'] for x in plan[arm]],'cases':cases})
        ledgers.append({'run_id':run,'arms':l_arms})
    ledger={'schema_version':h.SCHEMA,'adr_id':'ADR-0493','experiment_id':'ADR-0493-experiment-v1','accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':ledgers,'audit':{'public_canonical_corpus_total':corpus,'final_stage':'guarded publication only; unpublished payload_sources is a separate diagnostic stage','product_results_hashes':{r:sha(A/'artifacts'/r/'results.json') for r in RUNS}}}
    ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
    by_arm={}
    for arm in ARMS:
        rr=[x for x in allrows if x['arm']==arm];usage=[u for res in products.values() for p in res['cases'].values() for u in p[arm]['usage']];verdicts=[s for x in rr for s in x['sources']]
        by_arm[arm]={'correct':sum(x['correct'] is True for x in rr),'total':len(rr),'ungraded':sum(x['correct'] is None for x in rr),'gold_recall':sum(x['gold_final'] for x in rr)/sum(x['gold_total'] for x in rr),'payload_relevance_precision':sum(x['relevant'] for x in verdicts)/len(verdicts) if verdicts else None,'source_precision':sum(s['relevant'] for x in rr if x['publication_status']=='PUBLISHED' for s in x['sources'])/sum(len(x['sources']) for x in rr if x['publication_status']=='PUBLISHED') if any(x['sources'] and x['publication_status']=='PUBLISHED' for x in rr) else None,'payload_gold_recall':sum(x['gold_payload'] for x in rr)/sum(x['gold_total'] for x in rr),'source_judgments':len(verdicts),'card_count':sum(x['card_count'] for x in rr),'publication_success':sum(x['publication_status']=='PUBLISHED' for x in rr),'execution_errors':sum(x['execution_error'] is not None for x in rr),'calls':sum(x['calls'] for x in rr),'latency_p50_seconds':statistics.median(x['seconds'] for x in rr),'latency_p95_seconds':sorted(x['seconds'] for x in rr)[-1],'usage':{k:sum(u.get(k) or 0 for u in usage) for k in ['input_tokens','output_tokens','thinking_tokens','total_tokens','cost_usd']},'failure_types':dict(Counter(x['failure_type'] for x in rr if x['correct'] is not True))}
    pairs=Counter()
    for run in RUNS:
        for c in product['cases']:
            vals=[next(x for x in allrows if x['run_id']==run and x['case_id']==c['case_id'] and x['arm']==a)['correct'] for a in ARMS]
            pairs['ungraded' if None in vals else 'both_correct' if all(vals) else 'both_wrong' if not any(vals) else 'baseline_only' if vals[0] else 'candidate_only']+=1
    v=[x for x in allrows if x['arm']==ARMS[1]];b=by_arm[ARMS[0]];c=by_arm[ARMS[1]]
    source_checks={'no_source_recall_regression':c['gold_recall']>=b['gold_recall'],'cm018_decisive_source_published':all(x['gold_final']==x['gold_total'] for x in v),'precision_min_08':c['source_precision'] is not None and c['source_precision']>=.8}
    implementation_checks={'saved_bundle_valid_all':all(x['saved_bundle_valid'] for x in v),'no_lost_selections':all(not x['lost_selections'] for x in v),'tier_caps_valid':all(x['tier_caps_valid'] for x in v),'guarded_publication_1':c['publication_success']==1,'zero_execution_errors':c['execution_errors']==0}
    mechanism=[]
    for row in v:
        journal=A/'artifacts'/row['run_id']/row['case_id']/row['arm']/'journal.sqlite'
        with sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True) as db:
            errs=[json.loads(x[0]).get('error','') for x in db.execute("SELECT payload_json FROM event WHERE kind='OUTPUT_SCHEMA_INVALID'")]
        mechanism.append(not any('each current claim needs one review' in e.get('message','') for e in row['semantic_errors']) and not any('ReviewDecision' in e and '/claim' in e for e in errs) and not any('presentation cannot fit' in e or 'presentation metadata' in e for e in row['limitations']))
    implementation_checks['packing_and_claim_id_errors_zero']=all(mechanism)
    legal_checks={'agreement_min_1':c['correct']>=1,'no_regressions':pairs['baseline_only']==0,'all_graded':pairs['ungraded']==0}
    budget_checks={'physical_calls_max14':all(x['calls']<=14 for x in allrows),'tool_max56':all(x['tool_used']<=56 for x in allrows),'controller_max300':all(x['controller_seconds'] is not None and x['controller_seconds']<=300 for x in allrows)}
    metrics={'schema_version':'adr0493-source-quality-v1','by_arm':by_arm,'paired_outcomes':dict(pairs),'paired_delta':c['correct']-b['correct'],'by_case':allrows,'criteria':{'source_quality':source_checks,'implementation':implementation_checks,'legal_answer':legal_checks,'budget':budget_checks},'verdicts':{k:all(v.values()) for k,v in [('source_quality',source_checks),('implementation',implementation_checks),('legal_answer',legal_checks),('budget',budget_checks)]},'judge_usage':{k:sum(u.get(k) or 0 for j in alljudges for u in j['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']},'judge_calls':len(alljudges)*2,'judge_disagreements':None,'judge_note':'Separate answer-only and source-only Qwen calls per case; no-reviewed-claims false gate frozen before run; inherited control, no independent calibration','corpus_total':corpus,'main_wiring':'unchanged'}
    write(A/'artifacts/metrics.json',metrics);print(json.dumps({'by_arm':by_arm,'verdicts':metrics['verdicts']},ensure_ascii=False))
if __name__=='__main__':main()
