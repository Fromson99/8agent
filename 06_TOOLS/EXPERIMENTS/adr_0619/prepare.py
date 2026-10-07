"""Freeze continuation before additional calls; never rewrite the interrupted run."""
import hashlib,json,re,shutil,sqlite3,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-0618-unified-cm-guidance-two-failures'
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0619-unified-cm-guidance-interrupted-continuation'
D=ADR/'artifacts/design';R=ADR/'artifacts/run-001'
sys.path.insert(0,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0618'))
from common import sha,read,put

def compact(dbpath):
    out={}
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for table in ('goal','event','head','route','knowledge','wiki','judgment_ref','request'):
            out[table]=[]
            for raw in db.execute('SELECT * FROM '+table):
                x=dict(raw)
                for k in ('state','command','before_state','after_state','payload','ref','response'):
                    if isinstance(x.get(k),str):
                        try:x[k]=json.loads(x[k])
                        except ValueError:pass
                if table=='knowledge' and isinstance(x.get('payload'),dict):x['payload']={k:v for k,v in x['payload'].items() if k!='parts'}
                out[table].append(x)
        out['node']=[]
        for ident,goal,stage in db.execute('SELECT id,goal,stage FROM node'):
            if stage=='READ':fields=('originals','binding')
            elif stage=='RECALL':fields=('selected_for_read','corpus_ids','binding','discovery.discovered')
            elif stage=='SELECT':fields=('final_ids','binding')
            else:fields=()
            if fields:
                payload={}
                for field in fields:
                    raw=db.execute("SELECT json_extract(payload,?) FROM node WHERE id=?",('$.'+field,ident)).fetchone()[0]
                    value=json.loads(raw) if isinstance(raw,str) else raw
                    if '.' in field:
                        a,b=field.split('.');payload.setdefault(a,{})[b]=value
                    else:payload[field]=value
            else:payload=json.loads(db.execute('SELECT payload FROM node WHERE id=?',(ident,)).fetchone()[0])
            out['node'].append({'id':ident,'goal':goal,'stage':stage,'payload':payload})
    out['full_authority_sqlite']=str(dbpath.relative_to(ROOT));out['projection_note']='Compact report projection. Immutable full checkpoints and all source/LLM receipts remain in the original SQLite journals.'
    return out

def prefix_row(path):
    with path.open() as f:text=f.read(16*1024*1024)
    result={}
    for key in ('case_id','arm','turn','input','http_status','output','seconds','provider_attempt_start','provider_attempt_end'):
        match=re.search(r'^  "'+key+r'":\s*',text,re.M)
        if match:result[key]=json.JSONDecoder().raw_decode(text[match.end():])[0]
    assert 'output' in result
    return result

def main():
    assert not (D/'freeze.json').exists()
    for name in ('inputs.json','gold.json','source-binding.json','source-coordinates.json','snapshot-source-files.json'):
        target=D/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OLD/'artifacts/design'/name,target)
    oldmanifest=read(OLD/'실험/manifest.json')
    put(OLD/'artifacts/interruption.json',{'status':'interrupted','frozen_inputs_unchanged':True,
        'completed_answer_records_preserved':True,'continuation_adr':'ADR-0619',
        'cause':'Processes no longer running after turn interruption; no product output fabricated. Reporting serialized complete node histories produced 275MiB turn artifacts; continuation uses compact projections plus full SQLite authority.'})
    oldmanifest['results'].update(status='failed',execution_interruption=str((OLD/'artifacts/interruption.json').relative_to(ROOT)))
    oldmanifest['runs'][0].update(status='failed',artifact_path=str((OLD/'artifacts/interruption.json').relative_to(ROOT)),sha256=sha(OLD/'artifacts/interruption.json'))
    put(OLD/'실험/manifest.json',oldmanifest)
    subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py','status','--path',str(OLD),'--status','abandoned','--note','Interrupted incomplete run preserved; remaining requests continued under ADR-0619 with identical frozen product code and input criteria.'],check=True)
    fresh=read(ADR/'실험/manifest.json');old=read(OLD/'artifacts/design/pre-run-manifest.json')
    for key in ('design','dataset','retrieval_accounting','llm_policy'):fresh[key]=old[key]
    fresh['lineage']['hypothesis_delta']='Continue the interrupted fixed CM comparison; identical model/code/guides/rubric. No result-driven candidate changes.'
    fresh['design']['recovery_protocol']={'prior_adr':'ADR-0618','completed_responses':'Read-only replay or copy exact persisted output',
        'additional_requests':['cm-051 guided1 same request ID resumes pending SELECT','cm-051 guided2 original fixed locator guide','cm-003 unguided1 finish cached result publication without changing answer','cm-003 unguided2 original fixed review request'],
        'native_attempt_cap':'40 cumulative physical attempts per user turn including pre-interruption calls; no retries/fallback',
        'report_projection':'Remove duplicated full node history from JSON, preserve complete immutable authority in SQLite',
        'primary_judge':'Exactly ADR0618 frozen prompt/schema and two repeats; never previously executed.',
        'latency_caveat':'Continuation segment time and original completed turn times separately; interrupted interval is not ordinary end-to-end latency.'}
    fresh['design']['code_isolation']['candidates']=[]
    fresh['dataset']['frozen_source']=str((D/'inputs.json').relative_to(ROOT))
    fresh['retrieval_accounting']['stage_ledger']['artifact_path']=str((R/'retrieval-stage-ledger.json').relative_to(ROOT))
    fresh['runs'][0].update(selection_rule=old['runs'][0]['selection_rule'],artifact_path=str((R/'result.json').relative_to(ROOT)))
    path=OLD/'실험/manifest.json'
    fresh['relationships']=[{'adr_id':'ADR-0618','experiment_id':'ADR-0618-experiment-v1','relation':'depends_on','record_path':str(path.relative_to(ROOT)),'record_sha256':sha(path),'note':'Interrupted record/source checkpoints; not an accepted completed parent arm. ROOT continuation study with explicit carried-over evidence.'}]
    put(ADR/'실험/manifest.json',fresh)
    paths=read(D/'snapshot-source-files.json')
    for arm in ('baseline','unguided','guided'):
        args=[str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_candidate.py','snapshot','--adr',str(ADR),'--candidate-id','unified-'+arm,'--experiment-id',fresh['experiment_id'],'--arm-id',arm,'--run-id','run-001']
        for path in paths:args+=['--source',path]
        subprocess.run(args,check=True)
        oldc=read(ROOT/'02_BACKEND/lawrag/research/candidates/adr_0618'/('unified-'+arm)/'candidate.json')
        target=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0619'/('unified-'+arm)/'snapshot'
        for f in oldc['revisions'][-1]['files']:
            relative=f['snapshot_path'].split('/snapshot/',1)[1];shutil.copy2(ROOT/f['frozen_path'],target/relative)
    for case in read(D/'inputs.json'):
        for arm in ('baseline','unguided','guided'):
            origin=OLD/'artifacts/run-001'/case['case_id']/arm;target=R/case['case_id']/arm
            target.mkdir(parents=True,exist_ok=True);shutil.copytree(origin/'runtime',target/'runtime')
            if (origin/'provider').exists():shutil.copytree(origin/'provider',target/'inherited-provider')
            receipts={str(p.relative_to(origin)):sha(p) for p in origin.rglob('*') if p.is_file() and not p.name.endswith(('-shm','-wal'))}
            put(target/'inherited-receipt.json',{'origin':str(origin.relative_to(ROOT)),'files':receipts,'checkpoint_db_sha256':sha(origin/'runtime/case-memory/cases-v3.sqlite')})
            products=[]
            for p in sorted(origin.glob('turn-*.json')):
                x=prefix_row(p)
                if isinstance(x['turn'],int):x['db']=compact(target/'runtime/case-memory/cases-v3.sqlite');products.append(x)
            if products:put(target/'products.json',products)
    # The grader source stays byte-identical, importing this continuation common.
    directory=ROOT/'06_TOOLS/EXPERIMENTS/adr_0619'
    for name in ('common.py','package.py','grade.py','finalize.py'):
        text=(ROOT/'06_TOOLS/EXPERIMENTS/adr_0618'/name).read_text()
        if name!='grade.py':text=text.replace('adr_0618','adr_0619').replace('ADR-0618-unified-cm-guidance-two-failures','ADR-0619-unified-cm-guidance-interrupted-continuation').replace('ADR-0618','ADR-0619')
        else:text=text.replace('adr_0618/unified-baseline','adr_0619/unified-baseline')
        (directory/name).write_text(text)
    put(D/'continuation-provenance.json',{'prior_freeze_sha256':sha(OLD/'artifacts/design/freeze.json'),
        'same_inputs':sha(D/'inputs.json')==sha(OLD/'artifacts/design/inputs.json'),
        'same_gold_rubric':sha(D/'gold.json')==sha(OLD/'artifacts/design/gold.json'),
        'same_judge_system_schema':True,'original_product_files_modified':False,'model_calls':0})
    print('Continuation prepared, no new model calls',flush=True)

if __name__=='__main__':main()
