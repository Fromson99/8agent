"""Explicit frozen candidate injection, exact provider receipts and offline grading."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentCallError
from functional_probes import run_all

ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0591-case-memory-functional-mock-probe'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0591/guarded-context'
DESIGN=ADR/'artifacts/design'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def load_candidate():
    manifest=json.loads((CAND/'candidate.json').read_text());rev=manifest['revisions'][-1]
    paths={}
    for f in rev['files']:
        p=ROOT/f['frozen_path']
        if sha(p)!=f['snapshot_sha256']:raise RuntimeError('frozen candidate hash mismatch')
        paths[f['snapshot_path'].split('/snapshot/',1)[1]]=p
    module=paths['02_BACKEND/semantic_runtime/case_memory_probe.py']
    spec=importlib.util.spec_from_file_location('adr0591_frozen',module);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    native_spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent.adr0591_repository',paths['02_BACKEND/semantic_runtime/legal_agent/repository.py'])
    native=importlib.util.module_from_spec(native_spec);sys.modules[native_spec.name]=native;native_spec.loader.exec_module(native);mod.NativeRepository=native.WorkRepository
    return mod,paths

def exact(output,gold):return output is not None and all(output.get(k)==v for k,v in gold.items())

def dispatch(mod,store,who,cid,case,product,output):
    """Server guards do not see gold; no dynamic SQL from model."""
    text=product['utterance'];intent=output['intent'];snapshot=store.read_state(who,case)
    if intent=='CLARIFY':return {'status':'CLARIFY','mutated':False}
    if intent=='CORRECT' and output['field']=='scope' and output['extent']=='TARGET_GOAL':
        requested=None
        if product.get('target_anchor'):requested=product['target_anchor']
        elif '두 번째' in text:requested='G2-scope'
        elif '첫 번째' in text:requested='G1-scope'
        if requested is None:raise mod.GuardError('target ambiguous; no write')
        if output['decision_id']!=requested:raise mod.GuardError('model target conflicts with explicit target')
    if intent in {'CORRECT','CONTINUE'}:
        result=store.apply(who,cid,case,text,output,snapshot['revision'],product['id']);result['mutated']=True
        if result.get('affected'):result['replacement_decisions']=store.recompute_mock(who,case,result,json.loads((DESIGN/'RAW/documents.json').read_text()))
        return result
    if intent=='HYPOTHETICAL':
        branch=store.fork(who,case)
        result=store.apply(who,cid,case,text,{**output,'intent':'CORRECT'},0,product['id'],branch=branch)
        return {**result,'branch_id':branch,'actual_revision':snapshot['revision'],'mutated':True,'hypothetical_only':True}
    if intent=='SWITCH_CASE':return {'status':'NEW_CASE','case_id':store.create_case(who),'mutated':True,'copied_facts':0}
    if intent=='INSPECT_MEMORY':
        target=output['decision_id']
        if not target and output['goal_id']:target=output['goal_id']+'-scope'
        if not target:raise mod.GuardError('history target ambiguous')
        return {'status':'INSPECTED','decision':store.inspect(who,case,target),'mutated':False}
    if intent=='UPDATE_USER_MEMORY':
        if '앞으로' not in text:raise mod.GuardError('persistent preference not explicitly requested')
        store.preference(who,output['value']);return {'status':'PREFERENCE','values':store.preferences(who),'mutated':True}
    if intent=='PROPOSE_KNOWLEDGE_CHANGE':
        # An immutable candidate artifact, no wiki publication adapter exists.
        ref,h=store.asset({'state':'PROPOSED','text':text,'author':who.user,'target_version':'mock-wiki-v1'})
        return {'status':'PROPOSED','ref':ref,'hash':h,'mutated':True,'wiki_accepted_changed':False,'mock_handler':True}
    raise mod.GuardError('unsupported intent')

ANSWER_SCHEMA={'type':'object','properties':{'text':{'type':'string'},'procedure':{'type':'string'},'source_ids':{'type':'array','items':{'type':'string'}},'limitations':{'type':'array','items':{'type':'string'}}},'required':['text','procedure','source_ids','limitations'],'additionalProperties':False}
ANSWER_PROMPT='''현재 사건 상태와 제공된 가상 절차 문서만으로 짧게 새 답변을 작성한다. 실제 법률이 아니므로 가상 절차라고 표시한다.
party와 scope 조건에 맞는 A/B/C/D 절차 문자 하나를 procedure에 기록하고 근거 문서의 정확한 ID를 source_ids에 적는다.
과거 답변 B를 복사하지 않는다. 가정 분기는 가정임을 설명하고 실제 상태를 고쳤다고 말하지 않는다. 긴급 예외는 별도 미확인이다.'''

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-model',action='store_true');args=parser.parse_args()
    for path,h in json.loads((DESIGN/'freeze.json').read_text()).items():
        if sha(ROOT/path)!=h:raise RuntimeError('design changed: '+path)
    mod,paths=load_candidate();run=ADR/'artifacts/run-001'
    if run.exists():raise RuntimeError('run-001 exists; do not overwrite or rerun')
    run.mkdir()
    features=run_all(mod,run/'functional',DESIGN,paths['00_SYSTEM/SCHEMAS/legal-agent-case-memory-v1.draft.sql'],paths['00_SYSTEM/SCHEMAS/shortcut-experience-v1.draft.sql'])
    write(run/'feature-progress.json',features)
    print(json.dumps({'phase':'features','pass':sum(r['status']=='PASS' for r in features),'total':len(features)},ensure_ascii=False),flush=True)
    inputs=json.loads((DESIGN/'inputs.json').read_text());seed=json.loads((DESIGN/'seed.json').read_text());nl=[];answers=[]
    client=None
    if not args.no_model:
        try:client=ExperimentClient(ROOT,run/'provider',max_calls=44,max_output_tokens=1600,max_repairs=0)
        except ExperimentCallError as e:write(run/'model-init-error.json',{'error':str(e)})
    # No gold is loaded until product outputs have all been produced.
    for i,product in enumerate(inputs):
        row={'id':product['id'],'utterance':product['utterance'],'arms':{}}
        for arm in (['baseline','GUARDED'] if i%2==0 else ['GUARDED','baseline']):
            folder=run/'natural-language'/product['id']/arm
            store=mod.ContextStore(folder/'context.sqlite',paths['00_SYSTEM/SCHEMAS/legal-agent-case-memory-v1.draft.sql'],folder/'assets')
            who=mod.DevIdentity(seed['tenant'],seed['user']);cid=store.session(who,seed['session']);case=store.seed(who,cid,copy.deepcopy(seed))
            context={'goals':seed['goals'],'turns':seed['turns'],'decisions':seed['decisions'],'facts':seed['facts'],'revision':3} if arm=='GUARDED' else None
            if product['id']=='NL20' and context:
                # Fixed fixture of an already-completed correction for an inspect-only question.
                context=copy.deepcopy(context);context['goals'][1]['scope']='EXTERNAL';context['corrections']=[{'goal_id':'G2','completed':True,'from':'INTERNAL','to':'EXTERNAL'}]
            if product['id']=='NL18' and context:context['accessible_users']=[who.user]
            data={'current_utterance':product['utterance'],'target_anchor':product['target_anchor'] if arm=='GUARDED' else None,'context':context}
            write(folder/'input.json',data);output=None;call_error=None;start=time.perf_counter()
            if client:
                try:output=client.generate(mod.RESOLVER_PROMPT,data,mod.COMMAND_SCHEMA,phase=product['id']+'-'+arm)
                except ExperimentCallError as e:call_error={'type':type(e).__name__,'message':str(e)}
            else:call_error={'type':'UNAVAILABLE','message':'No authorized model transport'}
            elapsed=time.perf_counter()-start;dispatch_result=None
            if output:
                try:dispatch_result=dispatch(mod,store,who,cid,case,product,output)
                except (mod.GuardError,sqlite_error()) as e:dispatch_result={'status':'REJECTED','mutated':False,'reason':str(e)}
            observed={'output':output,'call_error':call_error,'seconds':elapsed,'dispatch':dispatch_result}
            write(folder/'observed.json',observed);row['arms'][arm]=observed
            if arm=='GUARDED' and product['id'] in ['NL01','NL04','NL05','NL17'] and output and dispatch_result and dispatch_result.get('status')!='REJECTED':
                branch=dispatch_result.get('branch_id','actual');state=store.read_state(who,case,branch)
                goal=next(g for g in state['body']['goals'] if g['id']==(output.get('goal_id') or 'G2'))
                party=next(f['value'] for f in state['facts'] if f['fact_id']=='party');doc=next(d for d in json.loads((DESIGN/'RAW/documents.json').read_text()) if d['category']==goal['scope'])
                answer_input={'data_kind':'synthetic','party':party,'scope':goal['scope'],'hypothetical':branch!='actual','source':doc,'current_goal':goal['title'],'previous_answer':'가상 B 검토'}
                write(folder/'answer-input.json',answer_input);answer=None;err=None
                try:answer=client.generate(ANSWER_PROMPT,answer_input,ANSWER_SCHEMA,phase=product['id']+'-answer')
                except ExperimentCallError as e:err={'type':type(e).__name__,'message':str(e)}
                expected_proc={'INTERNAL':{'국내':'B','해외':'A'},'EXTERNAL':{'국내':'D','해외':'C'}}[goal['scope']][party]
                answers.append({'id':product['id'],'input':answer_input,'output':answer,'error':err,'pass':bool(answer and answer['procedure']==expected_proc and answer['source_ids']==[doc['id']]),'expected_procedure':expected_proc})
                write(folder/'answer-observed.json',answers[-1])
            store.close()
        nl.append(row);write(run/'nl-progress.json',nl)
        print(json.dumps({'phase':'natural_language','case':row['id'],'completed':i+1,'total':20},ensure_ascii=False),flush=True)
    gold=json.loads((DESIGN/'gold.json').read_text())
    for row in nl:
        row['gold']=gold[row['id']]
        for arm,result in row['arms'].items():result['exact_match']=exact(result['output'],row['gold'])
    usage=client.usage if client else []
    token_in=sum(u.get('input_tokens',0) or 0 for u in usage);token_out=sum(u.get('output_tokens',0) or 0 for u in usage)
    for row in nl:
        file=next(q['file'] for q in json.loads((ADR/'실험/manifest.json').read_text())['questions'] if q['case_id']==row['id'])
        text='# '+row['id']+' — 모의 사건 기억 기능 검사\n\n## 실행 메타\n\nrun-001; baseline / GUARDED; 모델 qwen/qwen3.8-27b; 합성 자료; exact provider JSON 별도 artifact.\n\n## 사용자 질문 원문\n\n'+row['utterance']+'\n\n## 기준답변 — 채점 전용, 제품 입력에 포함하지 않음\n\n```json\n'+json.dumps(row['gold'],ensure_ascii=False,indent=2)+'\n```\n\n'
        for arm,result in row['arms'].items():
            folder=run/'natural-language'/row['id']/arm
            text+='## '+arm+' 실제 입력·출력\n\n```json\n'+(folder/'input.json').read_text()+'\n```\n\n```json\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n```\n\n'
        receipts=[]
        for p in sorted((run/'provider').glob('call-*/request.json')):
            if '-'+row['id']+'-' in str(p):receipts.append(str(p.parent.relative_to(ROOT)))
        text+='## 호출 원문·중간 결과·채점\n\n'+ '\n'.join('- ['+p+'](../../../'+p+')' for p in receipts)+'\n\n채점은 사전 동결 gold 필드와 문자열/ID의 결정론적 비교다. 별도 LLM judge·repair는 0회다. 반출 허용된 합성 자료만 사용했다.\n'
        (ADR/'실험'/file).write_text(text)
    # Explicit paired counts, excluding none: failures count as failed targets.
    paired={'candidate_only':0,'baseline_only':0,'both_correct':0,'both_incorrect':0}
    for r in nl:
        a=r['arms']['baseline']['exact_match'];b=r['arms']['GUARDED']['exact_match'];paired['both_correct' if a and b else 'candidate_only' if b else 'baseline_only' if a else 'both_incorrect']+=1
    result={'schema_version':'case-memory-functional-probe-v1','run_id':'run-001','data_kind':'synthetic','features':features,'natural_language':nl,'answers':answers,
        'summary':{'features_pass':sum(r['status']=='PASS' for r in features),'features_total':len(features),
        'sql_writer_boundaries':sum(r.get('observed',{}).get('unsafe_insert_accepted',False) for r in features),
        'commands':{arm:{'exact':sum(r['arms'][arm]['exact_match'] for r in nl),'total':20,'call_errors':sum(bool(r['arms'][arm]['call_error']) for r in nl)} for arm in ['baseline','GUARDED']},
        'paired':paired,'mock_answers':{'pass':sum(a['pass'] for a in answers),'total':len(answers),'planned':4},
        'usage':{'calls':len(usage),'input_tokens':token_in,'output_tokens':token_out,'reported_cost_usd':sum(u.get('usage',{}).get('cost',0) or 0 for u in usage)},
        'latency':{'resolver_seconds':{arm:{'p50':statistics.median([r['arms'][arm]['seconds'] for r in nl]),'p95':sorted(r['arms'][arm]['seconds'] for r in nl)[18]} for arm in ['baseline','GUARDED']},'speedup_certified':False}},
        'limits':['not production API/Coordinator integration','wiki/identity/review are mock fixtures','dispatch task savings are simulated','no GENOS internal model or storage evidence','in-sample single seed family']}
    write(run/'result.json',result);print(json.dumps(result['summary'],ensure_ascii=False),flush=True)

def sqlite_error():
    import sqlite3
    return sqlite3.IntegrityError

if __name__=='__main__':main()
