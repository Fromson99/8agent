"""ADR0354: invoke existing parser/interpreter, never product store or registry writes."""
import base64, copy, hashlib, json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0354-pdf-vlm-wiring-audit'
OUT=ADR/'artifacts'
PDF=ROOT/'04_EXPERIMENTS/ADR/ADR-0352-law-annex-pdf-vlm/artifacts/annex-derived-v2.pdf'
MODEL='claude-haiku-4-5-20251001'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
    with p.open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2,default=str)

class Recorder:
    def __init__(self,arm):self.arm=arm;self.calls=[]
    def structured(self,kind,system,user,schema,images=None,model=None,**kw):
        import httpx
        if len(self.calls)>=2:raise RuntimeError('Per-arm budget exhausted')
        if model and model!=MODEL:raise ValueError('Wrong backend model')
        if self.arm=='baseline' and images:raise ValueError('Baseline image not allowed')
        if kind!='structure_residual' and not kind.startswith('vlm_heading_p'):raise ValueError('Unexpected call kind')
        content=[]
        for uri in images or []:
            head,encoded=uri.split(',',1)
            if head!='data:image/png;base64':raise ValueError('Wrong image format')
            content.append({'type':'image','source':{'type':'base64','media_type':'image/png','data':encoded}})
        content.append({'type':'text','text':user})
        payload={'model':MODEL,'max_tokens':2200,'temperature':0,'system':system,
                 'messages':[{'role':'user','content':content}],
                 'tools':[{'name':'record_structure','description':'Record candidate decisions','input_schema':schema}],
                 'tool_choice':{'type':'tool','name':'record_structure'}}
        prefix=f'{self.arm}-call-{len(self.calls)+1}'
        write(OUT/(prefix+'.request.json'),payload)
        key=os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            for line in (ROOT/'.env').read_text().splitlines():
                if line.startswith('ANTHROPIC_API_KEY='):key=line.split('=',1)[1].strip().strip('\"\'')
        if not key:raise RuntimeError('Missing Anthropic credential')
        t=time.perf_counter()
        with httpx.Client(timeout=60,trust_env=False,follow_redirects=False) as client:
            response=client.post('https://api.anthropic.com/v1/messages',json=payload,
                         headers={'x-api-key':key,'anthropic-version':'2023-06-01'})
        body=response.json()
        row={'kind':kind,'images':len(images or []),'seconds':time.perf_counter()-t,'http_status':response.status_code,'body':body}
        write(OUT/(prefix+'.response.json'),row);self.calls.append(row)
        response.raise_for_status()
        if body.get('model')!=MODEL:raise ValueError('Model mismatch')
        answers=[x['input'] for x in body.get('content',[]) if x['type']=='tool_use']
        if len(answers)!=1:raise ValueError('Missing structured response')
        return answers[0]

def main():
    frozen=json.loads((OUT/'freeze.json').read_text())
    for p,digest in frozen['files'].items():
        assert sha(ROOT/p)==digest,p
    assert frozen['authorization']['allowed']
    # PDF pipeline may load cached local parsing models, never download new ones.
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ['OMP_NUM_THREADS']='2'
    os.environ['DOCLING_NUM_THREADS']='2'
    started=time.perf_counter()
    report={'scope':'Actual existing parser and interpreter wiring, same single law annex PDF; not MAIN/GENOS validation',
            'main_wiring':'unchanged','source_sha256_before':sha(PDF),'arms':{},'status':'started'}
    try:
        print('START actual parse_adapter.parse_pdf',flush=True)
        from lawrag.core import parse_adapter
        from lawrag.core.structure import pipeline,vlm_heading
        from lawrag.core.structure.model import Block
        t=time.perf_counter();parsed=parse_adapter.parse_pdf(PDF)
        report['parse_seconds']=time.perf_counter()-t
        report['parser']=parsed.parser;report['parser_stats']=parsed.stats;report['parser_warnings']=parsed.warnings
        blocks=Block.from_elements(parsed.elements)
        write(OUT/'blocks.json',[b.dump() for b in blocks])
        print('END parser',round(report['parse_seconds'],3),'blocks',len(blocks),flush=True)
        for arm in ['deterministic','baseline','vision']:
            recorder=Recorder(arm) if arm!='deterministic' else None
            t=time.perf_counter();print('START interpreter',arm,flush=True)
            result=pipeline.interpret(copy.deepcopy(blocks),doc='law-annex-wiring-audit',
                         llm=recorder,pdf_path=PDF if arm=='vision' else None,ledger=None)
            duration=time.perf_counter()-t
            nodes=[n.dump() for n in result.nodes()]
            write(OUT/(arm+'.structure.json'),result.dump())
            row={'seconds':duration,'nodes':nodes,'fitness_passed':result.fitness_passed,
                 'warnings':result.warnings,'stats':result.stats,'calls':len(recorder.calls) if recorder else 0,
                 'vision_calls':sum(bool(r['images']) for r in recorder.calls) if recorder else 0,
                 'usage':[r['body'].get('usage',{}) for r in recorder.calls] if recorder else [],
                 'eligible_heading_candidates':[b.idx for b in vlm_heading.candidates(blocks,result)]}
            report['arms'][arm]=row
            print('END interpreter',arm,round(duration,3),'nodes',len(nodes),'calls',row['calls'],flush=True)
        report['status']='complete'
    except Exception as exc:
        report['status']='failed';report['error']=f'{type(exc).__name__}: {exc}'
        print('FAILED',report['error'],flush=True)
    finally:
        report['source_unchanged']=sha(PDF)==report['source_sha256_before']
        report['seconds_total']=time.perf_counter()-started
        write(OUT/'results.json',report)
    return report['status']=='complete'

if __name__=='__main__':sys.exit(0 if main() else 1)
