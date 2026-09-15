"""ADR0355 exact full-loop runner, isolated candidate imports, no MAIN writes."""
import base64,copy,hashlib,importlib.util,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'02_BACKEND'))
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0355-recipe-vlm-correction-loop';OUT=ADR/'artifacts'
PDF=ROOT/'04_EXPERIMENTS/ADR/ADR-0352-law-annex-pdf-vlm/artifacts/annex-derived-v2.pdf'
PNG=ROOT/'04_EXPERIMENTS/ADR/ADR-0352-law-annex-pdf-vlm/artifacts/v2-page-001.png'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0355/loop/candidate.json'
MODEL='claude-haiku-4-5-20251001'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
    with p.open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2,default=str)
def load_candidate():
    rev=json.loads(CAND.read_text())['revisions'][0];mods=[]
    for i,row in enumerate(rev['files']):
        path=ROOT/row['frozen_path'];assert sha(path)==row['snapshot_sha256']
        spec=importlib.util.spec_from_file_location(f'adr0355_frozen_{i}',path)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);mods.append(module)
    return mods

class Calls:
    def __init__(self):self.records=[];self.arm='loop'
    def __call__(self,kind,system,data,schema,vision):
        import httpx,jsonschema
        if len(self.records)>=7:raise RuntimeError('Global7call budget exhausted')
        content=[]
        if vision:content.append({'type':'image','source':{'type':'base64','media_type':'image/png','data':base64.b64encode(PNG.read_bytes()).decode()}})
        content.append({'type':'text','text':json.dumps(data,ensure_ascii=False)})
        payload={'model':MODEL,'max_tokens':2200,'temperature':0,'system':system,'messages':[{'role':'user','content':content}],
                 'tools':[{'name':'record_recipe','description':'Record bounded recipe or review','input_schema':schema}],
                 'tool_choice':{'type':'tool','name':'record_recipe'}}
        n=len(self.records)+1;prefix=f'call-{n:02d}-{self.arm}-{kind}'
        write(OUT/(prefix+'.request.json'),payload)
        record={'id':n,'arm':self.arm,'kind':kind,'vision':vision,'request':prefix+'.request.json'}
        self.records.append(record)
        key=os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            for line in (ROOT/'.env').read_text().splitlines():
                if line.startswith('ANTHROPIC_API_KEY='):key=line.split('=',1)[1].strip().strip('\"\'')
        if not key:raise RuntimeError('Missing Anthropic credential')
        print('START',prefix,flush=True);t=time.perf_counter()
        with httpx.Client(timeout=90,trust_env=False,follow_redirects=False) as client:
            response=client.post('https://api.anthropic.com/v1/messages',json=payload,headers={'x-api-key':key,'anthropic-version':'2023-06-01'})
        body=response.json();record.update(seconds=time.perf_counter()-t,http_status=response.status_code,usage=body.get('usage',{}))
        write(OUT/(prefix+'.response.json'),{'record':record,'body':body})
        print('END',prefix,response.status_code,round(record['seconds'],2),flush=True)
        response.raise_for_status()
        if body.get('model')!=MODEL or body.get('stop_reason')!='tool_use':raise ValueError('Wrong model or incomplete response')
        answers=[x['input'] for x in body.get('content',[]) if x['type']=='tool_use']
        if len(answers)!=1:raise ValueError('Expected one structured result')
        jsonschema.validate(answers[0],schema)
        return answers[0]

def main():
    frozen=json.loads((OUT/'freeze.json').read_text())
    assert frozen['authorization']['allowed']
    for p,h in frozen['files'].items():assert sha(ROOT/p)==h,p
    os.environ.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',OMP_NUM_THREADS='2',DOCLING_NUM_THREADS='2')
    engine,loop=load_candidate();calls=Calls();report={'arms':{},'main_wiring':'unchanged'}
    started=time.perf_counter();source_before=sha(PDF)
    try:
        from lawrag.core import parse_adapter
        from lawrag.core.structure.model import Block
        print('START parse',flush=True);t=time.perf_counter();parsed=parse_adapter.parse_pdf(PDF)
        report['parse_seconds']=time.perf_counter()-t;blocks=Block.from_elements(parsed.elements)
        write(OUT/'blocks.json',[b.dump() for b in blocks]);print('END parse',len(blocks),flush=True)
        baseline=engine.interpret(copy.deepcopy(blocks),doc='recipe-loop-law-annex',llm=None,ledger=None)
        write(OUT/'baseline.structure.json',loop.tree_record(baseline))
        catalog={}
        for node in baseline.nodes():
            catalog.setdefault(node.family,{'component':node.family,'source_examples':[]})
            if len(catalog[node.family]['source_examples'])<3:
                catalog[node.family]['source_examples'].append({'block':node.block_idx,'surface':node.surface,'text':blocks[node.block_idx].text})
        write(OUT/'catalog.json',catalog)
        levels={}
        for n in baseline.nodes():levels.setdefault(n.level,set()).add(n.family)
        existing={'tag':'observed_existing','version':1,'levels':[sorted(levels[k]) for k in sorted(levels)]}
        loop.validate(existing,catalog);write(OUT/'existing.recipe.json',existing)
        inventory=loop.inventory(baseline)
        report['arms']['baseline']={'tree':loop.tree_record(baseline),'recipe':existing}
        # Both paths use the same frozen correction implementation. No gold supplied.
        for arm in ['loop','repair-replay']:
            calls.arm=arm;directory=OUT/arm;directory.mkdir(exist_ok=False)
            def save(name,data):write(directory/name,data)
            t=time.perf_counter()
            try:
                initial=loop.assemble(blocks,catalog,calls) if arm=='loop' else existing
                outcome=loop.correct(engine,blocks,initial,catalog,inventory,calls,save,max_corrections=2)
                outcome['seconds']=time.perf_counter()-t
                if outcome['status']=='candidate_ready':
                    reused=loop.build(engine,blocks,outcome['recipe'],catalog,inventory)
                    outcome['reuse_tree_identical']=loop.digest(loop.tree_record(reused))==loop.digest(outcome['tree'])
                    # Candidate only; name+source version binding, never overwrite actual registry.
                    tag={'schema_version':'document-recipe-tags-v1','documents':{
                         'law/금융복합기업집단의 감독에 관한 법률/별표서식/금융회사 및 임직원에 대한 처분 사유.hwp':{
                           'source_sha256':'13e1df4f2a944beb7e711c4b80a3bc4a0bfed2f831ed582c792952aad913a933',
                           'derived_pdf_sha256':source_before,'tag':outcome['recipe']['tag'],
                           'recipe':outcome['recipe'],'recipe_sha256':loop.digest(outcome['recipe']),
                           'catalog_sha256':loop.digest(catalog),'status':'candidate','main_registered':False}}}
                    save('tags.candidate.json',tag)
                report['arms'][arm]=outcome
                print('ARM',arm,outcome['status'],outcome.get('reason',''),flush=True)
            except Exception as exc:
                report['arms'][arm]={'status':'failed','error':f'{type(exc).__name__}: {exc}'}
        report['status']='complete'
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}')
    finally:
        report.update(calls=calls.records,source_unchanged=sha(PDF)==source_before,seconds_total=time.perf_counter()-started)
        write(OUT/'results.json',report)
        print('RESULT',report['status'],'calls',len(calls.records),flush=True)

if __name__=='__main__':main()
