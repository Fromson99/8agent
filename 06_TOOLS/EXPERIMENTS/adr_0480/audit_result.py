"""Post-probe accounting only; gold never changes the manual relation/READ probe."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0480-cm003-reviewed-source-relations'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def main():
    spec=importlib.util.spec_from_file_location('ledger',ROOT/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    m=read(ADR/'실험/manifest.json');r=read(ADR/'artifacts/run-001/result.json')
    gold_file=ROOT/'04_EXPERIMENTS/ADR/ADR-0474-double-harness-live-quality-probe/artifacts/frozen-inputs.json'
    case=next(c for c in read(gold_file)['cases'] if c['case_id']=='cm-003')
    coord={'article:3e4ab92e38b531a09f6419a9':{'doc_id':'3521c3aaa5a735fd','node':282},
           'article:1fa6eb7a10072f0d8f71bfc1':{'doc_id':'eae25aa6e8a83c58','node':202}}
    gold=h.ordered(coord[s] for s in case['decisive_source_ids'])
    arms=[]
    for arm,metrics in r['arms'].items():
        stages=[];before=[]
        start=[coord['article:3e4ab92e38b531a09f6419a9']]
        read_ids=h.ordered(coord[s] for s in metrics['read_sources'])
        for stage,after in zip(m['design']['retrieval_stage_plan']['stages_by_arm'][arm],[start,read_ids,read_ids,[]]):
            discarded=[i for i in before if i not in after]
            reasons={h.key(i):'no_model_execution_in_this_probe' for i in discarded}
            row=h.stage(stage['stage_id'],stage['kind'],stage['parent_stage_ids'],before,
                        [i for i in after if i not in before],discarded,reasons,gold)
            stages.append(row);before=row['after']
        c={'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,
           'accounting_unit':h.UNIT,'arm_id':arm,'case_id':'cm-003','gold_total':len(gold),
           'gold_identities':gold,'stages':stages}
        arms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in stages],'cases':[c],
                     'aggregate':{'presented_total':0,'gold_after':0,'gold_total':len(gold)}})
    ledger={'schema_version':h.SCHEMA,'adr_id':'ADR-0480','experiment_id':m['experiment_id'],
            'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,
            'runs':[{'run_id':'run-001','arms':arms}],
            'audit':{'gold_source_sha256':sha(gold_file),'stage_plan_frozen_before_run':True,
                     'manual_in_sample_relation':True,'autonomy_evaluated':False,
                     'note':'Known CM003 coordinates manually authored in fixture; gold file only joined after run. Not a blind retrieval benchmark.'}}
    ledger['artifact_sha256']=h._canonical_value_sha256(ledger)
    lp=ADR/'artifacts/retrieval-stage-ledger.json';write(lp,ledger)
    zero={a:0 for a in r['arms']}
    m['retrieval_accounting'].update(corpus_total=r['corpus_total'],before_filter={a:1 for a in r['arms']},
        after_filter={a:len(v['read_sources']) for a,v in r['arms'].items()},presented_total=zero,
        presented_mean=zero,presented_p50=zero,presented_p95=zero,golden_recall=zero,selectivity=zero)
    m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=str(lp.relative_to(ROOT)),sha256=sha(lp))
    m['runs'][0].update(status='complete',sha256=sha(ADR/'artifacts/run-001/result.json'))
    m['results'].update(status='complete',by_arm=r['arms'],
        comparisons=[{'arms':['baseline','explicit-link'],'metric':'target_original_blocks_read','baseline':0,'candidate':9,
                      'legal_accuracy_evaluated':False}],judge_disagreements=0,
        usage={'model_calls':0,'input_tokens':0,'output_tokens':0,'model_cost_usd':0},
        latency={'probe_total_seconds':r['seconds'],'model_latency':None},
        error_taxonomy=['preprobe_rev001_sql_placeholder_count_fixed_in_rev002'])
    write(ADR/'실험/manifest.json',m)
    print('Post-run ledger and metrics written; target READ recall separate from zero model presentation')

if __name__=='__main__':main()
