"""Same frozen judge/ledger policy applied only to the corrected CM038 receipt."""
import json,sqlite3,hashlib
from pathlib import Path
import score
from run_retry import pin
ROOT=score.ROOT;ADR=score.ADR;OUT=ADR/'artifacts/run-002'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    if p.exists():raise RuntimeError('Never overwrite a completed scoring receipt')
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    pin()
    from lawrag.research.experiment_client import ExperimentClient
    result=read(OUT/'results.json');assert result.get('finished_at')
    initial=read(ADR/'artifacts/run-001/results.json');product=read(ADR/'product-cases.json');gold=read(ADR/'gold-cases.json')
    case=next(c for c in product['cases'] if c['case_id']=='cm-038');g=next(c for c in gold['cases'] if c['case_id']=='cm-038')
    old=initial['cases']['cm-038']['baseline'];new=result['cases']['cm-038']['relations-v3']
    # Same A=baseline / B=candidate slot as the first CM038 evaluation; baseline is inherited unchanged.
    client=ExperimentClient(ROOT,OUT/'judge/cm-038',max_calls=1,max_output_tokens=1200)
    value=client.generate(score.SYSTEM,{'question':case['question'],'reference_answer':g['reference_answer'],
        'variants':[{'label':'A','answer':score.answer(old)},{'label':'B','answer':score.answer(new)}]},score.SCHEMA,phase='judge')
    assert {v['label'] for v in value['assessments']}=={'A','B'}
    judged={'cases':{'cm-038':{'anonymous_order':{'A':'baseline','B':'relations-v3'},
        'by_arm':{('baseline' if v['label']=='A' else 'relations-v3'):v for v in value['assessments']}}},
        'usage':client.usage,'source_results_sha256':sha(OUT/'results.json'),
        'baseline_origin':{'run':'run-001','sha256':sha(ADR/'artifacts/run-001/cm-038/baseline/result.json')},
        'note':'Only candidate rerun after runner binding repair; no new baseline execution or independent sample.'}
    write(OUT/'judged-results.json',judged)
    helper=score.load_ledger_helpers();resolved,_=score.resolve_gold(gold)
    with sqlite3.connect('file:'+str(score.GEN/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as con:
        identities={s:{'doc_id':d,'node':int(u)} for s,d,u in con.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source WHERE json_extract(json,'$.unit_id') IS NOT NULL") if str(u).isdigit()}
    plan=read(ADR/'실험/manifest.json')['design']['retrieval_stage_plan']['stages_by_arm']['relations-v3'];cases=[]
    for c in product['cases']:
        cid=c['case_id'];raw=new.get('stages',{}) if cid=='cm-038' else {};gids=[r['identity'] for r in resolved[cid]]
        before=[];stages=[]
        for spec in plan:
            after=helper.ordered(identities[s] for s in raw.get(spec['stage_id'],[]) if s in identities)
            bk={helper.key(x) for x in before};ak={helper.key(x) for x in after}
            added=[x for x in after if helper.key(x) not in bk];discarded=[x for x in before if helper.key(x) not in ak]
            stages.append(helper.stage(spec['stage_id'],spec['kind'],spec['parent_stage_ids'],before,added,discarded,
                {helper.key(x):'not_carried_to_next_recorded_stage' for x in discarded},gids,
                skip_reason='not_selected_for_runner_repair_repeat' if cid!='cm-038' else None))
            before=after
        cases.append({'schema_version':helper.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,
            'accounting_unit':helper.UNIT,'arm_id':'relations-v3','case_id':cid,'gold_total':len(gids),'gold_identities':helper.ordered(gids),'stages':stages})
    ledger=read(ADR/'artifacts/retrieval-stage-ledger-run-001.json')
    ledger['runs'].append({'run_id':'run-002','arms':[{'arm_id':'relations-v3','declared_stage_ids':[x['stage_id'] for x in plan],'cases':cases,'aggregate':{}}]})
    ledger['audit']['repeat_note']='Only CM038 v3 was rerun; other cases have explicit not-selected stage receipts.'
    ledger.pop('artifact_sha256',None);ledger['artifact_sha256']=helper._canonical_value_sha256(ledger)
    write(ADR/'artifacts/retrieval-stage-ledger-combined.json',ledger)
    print(json.dumps({'retry_correct':judged['cases']['cm-038']['by_arm']['relations-v3']['correct'],'error':new['error'],'seconds':new['seconds'],'calls':new['physical_calls']},ensure_ascii=False))
if __name__=='__main__':main()
