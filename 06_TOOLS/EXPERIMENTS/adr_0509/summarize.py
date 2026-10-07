"""Post-run audit; gold is only joined here, never passed to product calls."""
import hashlib
import importlib.util
import json
import sqlite3
import statistics
from pathlib import Path

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0509-gemma-search-skill-harness-paired'

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, x): p.write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n')

def main():
    product = read(A/'product-cases.json')
    gold = {c['case_id']: c for c in read(A/'gold-cases.json')['cases']}
    res = read(A/'artifacts/run-001/results.json')
    m = read(A/'실험/manifest.json')
    spec = importlib.util.spec_from_file_location('ledger', R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    with sqlite3.connect('file:'+str(R/product['generation']/'navigation/navigation.sqlite')+'?mode=ro', uri=True) as db:
        coords = {s: {'doc_id': d, 'node': int(u)} for s,d,u in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(u).isdigit()}
        unit_sources = {}
        for sid, uid in db.execute('SELECT source_id,unit_id FROM source_unit_map'):
            if sid in coords: unit_sources.setdefault((coords[sid]['doc_id'],str(uid)),set()).add(sid)
    corpus = len({h.key(v) for v in coords.values() if v['doc_id'] in product['public_scope_document_ids']})
    arm_records, summaries, totals = [], [], {}
    for arm in ('baseline','integrated'):
        cases = []
        for case in product['cases']:
            cid = case['case_id']; row = res['cases'][cid][arm]
            base = A/'artifacts/run-001'/cid/arm
            trace=read(base/'trace.json')
            handles={x['handle']:json.loads(x['identity_json']) for x in trace['handles']}
            discovered=set(row.get('stages',{}).get('discovered',[]))
            def collect_cards(value):
                if isinstance(value,list):
                    for child in value: collect_cards(child)
                elif isinstance(value,dict):
                    if value.get('candidate_id') in handles:
                        ident=handles[value['candidate_id']]
                        discovered.update(unit_sources.get((ident.get('document_id'),str(ident.get('unit_id'))),set()))
                    for child in value.values(): collect_cards(child)
            collect_cards(trace['observations'])
            collect_cards(row.get('question_matches',{}).get('explicit_structure',[]))
            g = h.ordered(coords[x] for x in gold[cid]['decisive_source_ids'])
            stages, prev = [], []
            for st in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
                stage_ids=discovered if st['stage_id']=='discovered' else row.get('stages',{}).get(st['stage_id'],[])
                after = h.ordered(coords[x] for x in stage_ids if x in coords)
                bk = {h.key(x) for x in prev}; ak = {h.key(x) for x in after}
                added = [x for x in after if h.key(x) not in bk]; dropped = [x for x in prev if h.key(x) not in ak]
                stage = h.stage(st['stage_id'],st['kind'],st['parent_stage_ids'],prev,added,dropped,{h.key(x):'not_carried_to_'+st['stage_id'] for x in dropped},g)
                stages.append(stage); prev = stage['after']
            cases.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages})
            calls=[]
            for p in sorted((base/'calls').glob('*/request.json')):
                req=read(p); rp=p.with_name('response.json'); raw=read(rp) if rp.exists() else {}
                user=json.loads(req['messages'][1]['content']); view=user['view']
                try: output=json.loads(raw['choices'][0]['message']['content'])
                except (KeyError,IndexError,TypeError,ValueError): output=None
                calls.append({'call':str(p.parent.relative_to(A)),'phase':view['phase'],'model':raw.get('model'),'provider':raw.get('provider'),'request_utf8_bytes':len(json.dumps(req,ensure_ascii=False,separators=(',',':')).encode()),'view_chars':len(json.dumps(view,ensure_ascii=False,separators=(',',':'))),'output':output,'finish_reason':raw.get('choices',[{}])[0].get('finish_reason'),'error':raw.get('error')})
            with sqlite3.connect('file:'+str(base/'journal.sqlite')+'?mode=ro',uri=True) as db:
                db.row_factory=sqlite3.Row
                events=[dict(x) for x in db.execute('SELECT * FROM event')]
                attempts=[dict(x) for x in db.execute('SELECT * FROM model_attempt')]
            evidence=trace['evidence']
            summaries.append({'case_id':cid,'arm':arm,'question':case['question'],'reference_answer':gold[cid]['reference_answer'],'answer':row.get('result',{}).get('answer',{}),'calls':row['physical_calls'],'usage':{k:sum(u.get(k) or 0 for u in row['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']},'seconds':row['seconds'],'error':row['error'],'limitations':row.get('limitations',[]),'gold_by_stage':{s['stage_id']:s['gold_after'] for s in stages},'count_by_stage':{s['stage_id']:s['after_count'] for s in stages},'gold_total':len(g),'read_evidence_count':len(evidence),'controller_seconds':row.get('controller_seconds'),'matches':row.get('question_matches',{}),'events':events,'attempts':attempts,'semantic_errors':trace.get('errors',[]),'outputs':calls})
        counts=[c['stages'][-1]['after_count'] for c in cases]; ga=sum(c['stages'][-1]['gold_after'] for c in cases); gt=sum(c['gold_total'] for c in cases)
        arm_records.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':cases,'aggregate':{'presented_total':sum(counts),'gold_after':ga,'gold_total':gt}})
        metrics={'before_filter':sum(c['stages'][0]['after_count'] for c in cases),'after_filter':sum(c['stages'][1]['after_count'] for c in cases),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':ga/gt if gt else None,'selectivity':statistics.mean(counts)/corpus}
        for k,v in metrics.items():
            if not isinstance(m['retrieval_accounting'].get(k),dict): m['retrieval_accounting'][k]={}
            m['retrieval_accounting'][k][arm]=v
        rows=[s for s in summaries if s['arm']==arm]
        totals[arm]={'physical_calls':sum(x['calls'] for x in rows),'usage':{k:sum(x['usage'][k] for x in rows) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']},'wall_p50':statistics.median(x['seconds'] for x in rows),'wall_p95':max(x['seconds'] for x in rows),'gold_by_stage':{k:sum(x['gold_by_stage'][k] for x in rows) for k in ['discovered','read','presented','selected','answer']},'gold_total':gt,'answers_with_claims':sum(bool(x['answer'].get('claims')) for x in rows),'model_ids':sorted({c['model'] for x in rows for c in x['outputs'] if c['model']}),'providers':sorted({c['provider'] for x in rows for c in x['outputs'] if c['provider']}),'max_request_utf8_bytes':max((c['request_utf8_bytes'] for x in rows for c in x['outputs']),default=0),'max_view_chars':max((c['view_chars'] for x in rows for c in x['outputs']),default=0)}
    ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arm_records}],'audit':{'corpus_total':corpus,'final_stage':'Final answer claims; primary presented metric separately recorded. Publication is not evaluated.','product_sha256':sha(A/'artifacts/run-001/results.json')}}
    ledger['artifact_sha256']=h._canonical_value_sha256(ledger); write(A/'artifacts/retrieval-stage-ledger.json',ledger)
    m['retrieval_accounting']['corpus_total']=corpus
    m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),sha256=sha(A/'artifacts/retrieval-stage-ledger.json'))
    candidates=[x for x in summaries if x['arm']=='integrated']
    baseline=[x for x in summaries if x['arm']=='baseline']
    matched={x['case_id']:x for x in baseline}
    criteria={'reviewed_answers_minimum_met':totals['integrated']['answers_with_claims']>=4,
              'reviewed_answers_increased':totals['integrated']['answers_with_claims']>totals['baseline']['answers_with_claims'],
              'per_case_presented_gold_regressions':[x['case_id'] for x in candidates if x['gold_by_stage']['presented']<matched[x['case_id']]['gold_by_stage']['presented']],
              'schema_failure_events':{arm:sum(e['kind']=='OUTPUT_SCHEMA_INVALID' for x in summaries if x['arm']==arm for e in x['events']) for arm in totals},
              'input_token_ratio':totals['integrated']['usage']['input_tokens']/max(1,totals['baseline']['usage']['input_tokens']),
              'context_chars':60000,'quality_audit':'See separate qualitative-findings.json; no automatic judge',
              'model_call_bound_pass':all(x['calls']<=14 for x in summaries)}
    controller={arm:[x['controller_seconds'] for x in summaries if x['arm']==arm and x['controller_seconds'] is not None] for arm in totals}
    criteria['controller_p95_ratio']=max(controller['integrated'])/max(controller['baseline']) if all(len(v)==6 for v in controller.values()) else None
    criteria['controller_latency_missing']={k:6-len(v) for k,v in controller.items()}
    write(A/'artifacts/trace-summary.json',{'by_case':summaries,'by_arm':totals,'criteria':criteria,'assessment':'Source trace audit only; no automatic legal-answer grading'})
    m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
    m['dataset']['sha256']=sha(A/'product-cases.json')
    m['results'].update(status='complete',by_arm={arm:{'status':'complete','total':6,**totals[arm]} for arm in totals},comparisons=[criteria],judge_disagreements=None,usage={a:t['usage'] for a,t in totals.items()},latency={a:{k:t[k] for k in ['wall_p50','wall_p95']} for a,t in totals.items()},error_taxonomy=[{'arm':x['arm'],'case_id':x['case_id'],'error':x['error'],'limitations':x['limitations'],'semantic_errors':x['semantic_errors']} for x in summaries if x['error'] or x['limitations']])
    write(A/'실험/manifest.json',m)
    print(json.dumps({'by_arm':totals,'criteria':criteria},ensure_ascii=False))

if __name__=='__main__': main()
