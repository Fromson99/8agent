"""First frozen offline scoring; gold is never imported by the product process."""
from pathlib import Path
import collections, gzip, hashlib, importlib.util, json, sqlite3, statistics, sys

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0557-structure-main-qwen14'
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS, QUESTION_HEADINGS_V4, _canonical_value_sha256
spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def read(p):return json.loads(p.read_text())
def sha(p):
    d=hashlib.sha256()
    with p.open('rb') as f:
        while c:=f.read(8388608):d.update(c)
    return d.hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def utility(case,row,trace):
    answer=row.get('result',{}).get('answer',{});text=answer.get('text','')
    route=row.get('request_route') or {};mode=route.get('mode')
    receipts=[o for o in trace.get('observations',[]) if o.get('status') in ('OK','EMPTY','PARTIAL','REUSED')]
    passed=not row.get('error') and row.get('publication_status')=='PUBLISHED' and bool(text.strip()) and mode==case['expected_route']
    cid=case['case_id']
    if cid=='greeting':passed &= '법' in text and any(x in text for x in ('검색','도움','자료','규정'))
    elif cid=='out-of-domain':passed &= any(x in text for x in ('관련','범위','법률')) and not all(x in text for x in ('김치','돼지고기','끓'))
    else:
        passed &= bool(receipts) and not answer.get('claims')
        if cid=='catalogue-internal':passed &= any(x in text for x in ('허용','범위','요청'))
        if cid=='title-search':
            proposed=[json.loads(x['proposed_json']) for x in trace.get('actions',[]) if x.get('proposed_json')]
            passed &= any(x.get('tool')=='search' and x.get('args',{}).get('mode')=='title' and '내부회계' in x['args'].get('query','').replace(' ','') for x in proposed)
        if cid=='browse-uncertain':passed &= len(receipts)>=2
    return {'case_id':cid,'mode':mode,'expected_route':case['expected_route'],
            'automatic_rubric_pass':bool(passed),'actual_tool_receipts':len(receipts),
            'answer':text,'needs_content_review':True,'decision_events':row.get('progress_decisions',[])}

def main():
    f=read(A/'artifacts/frozen-design.json');m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json')
    index=read(A/'artifacts/run-001/results.json');arm='structure-main'
    for p,expected in {**f['file_hashes'],**f['grader_only_hashes']}.items():assert sha(R/p)==expected,p
    gold={x['case_id']:x for x in read(A/'gold-cases.json')['cases']}
    db=sqlite3.connect('file:'+str(R/f['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
    coords={sid:{'doc_id':did,'node':int(uid)} for sid,did,uid in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(uid).isdigit()};db.close()
    corpus=sum(c['doc_id'] in prod['public_scope_document_ids'] for c in coords.values())
    rows=[];records=[];usages=[];utility_rows=[];historical=[]
    for case in prod['cases']:
        cid=case['case_id'];path=R/index['cases'][cid][arm]['path'];row=read(path);out=path.parent
        trace={}
        if (out/'trace.json.gz').exists():
            with gzip.open(out/'trace.json.gz','rt') as z:trace=json.load(z)
        stages=row.get('stages',{})
        if not stages:
            journals=list((out/'runtime').glob('legal-agent/runs/*/*/journal.sqlite'))
            if journals:
                j=sqlite3.connect('file:'+str(journals[0])+'?mode=ro',uri=True)
                ev={eid:sid for eid,sid in j.execute('SELECT evidence_id,source_id FROM evidence_unit')}
                delivered={ev[eid] for (eid,) in j.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'") if eid in ev}
                stages={'discovered':sorted(set(ev.values())),'read':sorted(set(ev.values())),'presented':sorted(delivered)};j.close()
        required=set(gold.get(cid,{}).get('decisive_source_ids',[]));assert required<=set(coords)
        g=h.ordered(coords[s] for s in required);outputs={};ledger_stages=[]
        for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
            previous=h.ordered(x for parent in plan['parent_stage_ids'] for x in outputs[parent])
            after=h.ordered(coords[s] for s in stages.get(plan['stage_id'],[]) if s in coords)
            after_keys={h.key(x) for x in after};previous_keys={h.key(x) for x in previous}
            dropped=[x for x in previous if h.key(x) not in after_keys]
            reason={'read':'not_fully_read','selected':'not_selected','presented':'no_successful_exact_evidence_presentation_receipt'}.get(plan['stage_id'],'not_observed')
            stage=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],previous,[x for x in after if h.key(x) not in previous_keys],dropped,{h.key(x):reason for x in dropped},g)
            ledger_stages.append(stage);outputs[plan['stage_id']]=stage['after']
        records.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':ledger_stages})
        answer=row.get('result',{}).get('answer',{})
        usage=row.get('usage',[]);usages+=usage
        counts={k:len(set(v)) for k,v in stages.items()}
        measured={'case_id':cid,'kind':case['kind'],'error':row.get('error'),'counts':counts,
            'gold_total':len(required),'gold_by_stage':{k:len(required&set(v)) for k,v in stages.items()},
            'missing_presented':sorted(required-set(stages.get('presented',[]))),
            'publication_status':row.get('publication_status'),'control':row.get('control'),
            'route':row.get('request_route'),'structure_first_search':row.get('structure_first_search'),
            'seconds':row.get('seconds'),'physical_calls':row['physical_calls'],'usage':usage,
            'answer':answer.get('text',''),'claims':answer.get('claims',[]),'limitations':row.get('limitations',[]),
            'session_errors':trace.get('errors',[]),'result_path':str(path.relative_to(R)),
            'result_sha256':sha(path),'journal_path':row.get('journal_path'),
            'progress_decisions':row.get('progress_decisions',[]),
            'substantive_published':bool(not row.get('error') and row.get('publication_status')=='PUBLISHED' and answer.get('text','').strip() and answer.get('claims'))}
        rows.append(measured)
        if case['kind']=='utility':utility_rows.append(utility(case,row,trace))
        elif cid in f['historical_paths']:
            old=read(R/f['historical_paths'][cid])
            historical.append({'case_id':cid,'question_identical':True,'old_model':'qwen/qwen3.5-122b-a10b',
                'old_artifact':f['historical_paths'][cid], 'old_delivered_gold':len(required&set(old.get('stages',{}).get('presented',[]))),
                'main_delivered_gold':measured['gold_by_stage'].get('presented',0),'gold_total':len(required),
                'old_calls':old.get('physical_calls'),'main_calls':row['physical_calls'],
                'same_conditions':False,'interpretation':'Descriptive only: model, tokenizer, workflow differ'})
    counts=sorted(r['stages'][-1]['after_count'] for r in records)
    n=sum(r['gold_total'] for r in records);got=sum(r['stages'][-1]['gold_after'] for r in records)
    recall=got/n if n else None
    totals={'cases':14,'error_cases':sum(bool(x['error']) for x in rows),
        'published':sum(x['publication_status']=='PUBLISHED' for x in rows),
        'before_filter':sum(r['stages'][0]['after_count'] for r in records),
        'after_filter':sum(r['stages'][1]['after_count'] for r in records),
        'presented_total':sum(counts),'presented_mean':statistics.mean(counts),
        'presented_p50':statistics.median(counts),'presented_p95':counts[round((len(counts)-1)*.95)],
        'golden_recall':recall,'gold_obtained':got,'gold_total':n,
        'selectivity':statistics.mean(counts)/corpus,'physical_calls':sum(x['physical_calls'] for x in rows),
        'mean_seconds':statistics.mean(x['seconds'] or 360 for x in rows),
        'median_seconds':statistics.median(x['seconds'] or 360 for x in rows),
        'structure_matches':sum((x['structure_first_search'] or {}).get('status')=='MATCH' for x in rows),
        'fulltext_fallbacks':sum(bool((x['structure_first_search'] or {}).get('fulltext_fallback')) for x in rows)}
    ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
        'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':[{'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(counts),'gold_after':got,'gold_total':n}}]}],
        'audit':{'presentation':'Successful model_attempt linked to exact evidence; article identity is not paragraph completeness','gold_join':'Offline after every product process ended'}}
    ledger['artifact_sha256']=_canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
    criteria={'utility_correct':sum(x['automatic_rubric_pass'] for x in utility_rows),
        'utility_target':sum(x['automatic_rubric_pass'] for x in utility_rows)>=5,
        'core_substantive_published':sum(x['substantive_published'] for x in rows if x['kind']=='legal'),
        'core_publication_target':all(x['substantive_published'] for x in rows if x['kind']=='legal'),
        'delivered_recall_target':recall is not None and recall>=.8,
        'structure_match_observed':totals['structure_matches']>=1,
        'scope_and_structural_fallback_need_content_review':True,'quality_certified':False}
    summary={'release':f['release_binding'],'totals':totals,'rows':rows,'utility_rubric':utility_rows,
        'historical_comparison':historical,'frozen_criteria_outcomes':criteria,
        'quality_certified':False,'main_changed_by_experiment':False,'model':'qwen/qwen3.8-27b',
        'usage':{'physical_calls':totals['physical_calls'],'cost_usd':sum(u.get('cost_usd') or 0 for u in usages),
                 'cost_missing_calls':totals['physical_calls']-sum(u.get('cost_usd') is not None for u in usages),
                 'input_tokens':sum(u.get('input_tokens') or 0 for u in usages),'output_tokens':sum(u.get('output_tokens') or 0 for u in usages),
                 'reasoning_tokens':sum(u.get('thinking_tokens') or 0 for u in usages)},
        'limitations':['Exact selected MAIN code; external Qwen override and declared execution budgets, not GENOS internal model measurement',
            'Same historical questions observed before; in-sample one run, no independent legal correctness certification',
            'Article-level recall does not prove decisive paragraph/item completeness',
            'Three WSL processes overlap; wall time includes cold resource preparation and publication',
            'Old comparison has different model/workflow/tokenizer and is descriptive only',
            'Internal absence means absent in this approved public scope, not absence from actual GENOS']}
    write(A/'artifacts/summary.json',summary)
    decision='Deferred: selected MAIN measured in-sample; frozen targets and every failure retained. No quality certification or MAIN mutation.'
    m['results'].update(status='complete',by_arm={arm:totals},comparisons=[{'candidate':arm,'interpretation':decision}],judge_disagreements=None,usage=summary['usage'],latency={'mean_seconds':{arm:totals['mean_seconds']}},error_taxonomy=sorted({x['error']['type'] for x in rows if x['error']}))
    m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
    m['actual_model_binding']={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','thinking':'none','physical_calls':totals['physical_calls']}
    m['retrieval_accounting']={'changed':True,'corpus_total':corpus,'not_applicable_reason':None,
        'stage_ledger':{'mode':'measured','schema_version':h.SCHEMA,'accounting_unit':h.UNIT,'summary_run_id':'run-001','artifact_path':str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),'sha256':sha(A/'artifacts/retrieval-stage-ledger.json'),'not_applicable_reason':None},
        **{k:{arm:totals[k]} for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}}
    m['questions']=[]
    for number,case in enumerate(prod['cases'],1):
        cid=case['case_id'];filename=f'질문-{number:03d}-{cid}.md';qp=A/'실험'/filename;out=A/'artifacts/run-001'/cid/arm
        raw=[f'- [{p.name}](../{p.relative_to(A)}) SHA256 `{sha(p)}`' for p in sorted((out/'calls').rglob('*.json'))]
        measured=next(x for x in rows if x['case_id']==cid)
        blocks=[f'ADR0557/run-001/{cid}; source question exact; selected MAIN generation30.',case['question'],
            '```json\n'+json.dumps(gold.get(cid,{'expected_route':case['expected_route']}),ensure_ascii=False,indent=2)+'\n```',
            'Frozen selected release, profile, public source scope and Qwen transport. Gold unavailable to product.',
            'Article-root coordinate ledger; read/selected/presented separately counted.',
            '\n'.join(raw) or 'No model sends; actual product metadata route.',
            'All physical calls, including routing/selection/question-plan/compose, have request+response+usage receipts. No hidden repair/retry.',
            'No evaluator model calls. Frozen deterministic rubric and source coordinates only; content review separately reported.',
            '```json\n'+json.dumps(measured,ensure_ascii=False,indent=2)+'\n```']
        qp.write_text('# '+cid+'\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(QUESTION_HEADINGS_V4,blocks))+'\n')
        m['questions'].append({'number':number,'case_id':cid,'file':filename,'sha256':sha(qp)})
    write(A/'실험/manifest.json',m)
    (A/'실험/README.md').write_text('# Current MAIN14\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
    original=(A/'README.md').read_text();front=original.split('---',2)[1]
    blocks=[decision,'User requested the newly activated structure-first MAIN, rather than the interrupted earlier runtimes. Exact release generation30 code and PeCab data are fixed.',
        m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],(A/'PLAN.md').read_text(),
        'artifacts/frozen-design.json pins all selected release bytes, source provenance, prompts, schemas, profile, scoped Qwen model and report code.',
        '```json\n'+json.dumps({'totals':totals,'criteria':criteria},ensure_ascii=False,indent=2)+'\n```',
        'Every question links exact physical sends, responses, journals, publication and decision events; summary.json preserves errors and source misses.',
        '```json\n'+json.dumps(summary['usage'],indent=2)+'\n```',
        'Inspect structure MATCH/MISS and fallback separately from original delivery and legal correctness. Historical comparison is descriptive.',
        '\n'.join('- '+s for s in summary['limitations']),
        'No MAIN activation or GENOS deployment by this experiment. Current selected product path is invoked without editing it.',
        '```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0557/run_probe.py --execute\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0557/summarize.py\n```\nCompleted outputs are immutable; another execution or changed rubric requires a new ADR.']
    (A/'README.md').write_text('---'+front+'---\n\n# ADR0557 selected structure MAIN\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(ADR_HEADINGS,blocks))+'\n')
    print(json.dumps({'totals':totals,'criteria':criteria,'usage':summary['usage']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
