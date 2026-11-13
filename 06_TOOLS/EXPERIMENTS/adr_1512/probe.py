"""ADR-1512: pre-check of Qwen3.8 providers for the experiment fallback list (user 2026-11-12: "4~5개 정도 선정해놔서
문제 생기면 교체하게 공급자에 문제 없는지 검토 미리해서 유명한 공급자만 선별").

usage: probe.py freeze | probe.py run | probe.py report
Same model (qwen/qwen3.8-27b), reasoning none, no output cap, strict json_schema exactly as stored. Each provider gets
the same 4 requests in order, streamed (stream=true) so the time to the first content and to the first non-blank content
are measured; 180 s wall limit per request (the product per-call limit). Providers run in parallel (network only).
T1 small: tiny strict-schema request. T2 hang: the exact wire request that got no answer from Reka three times
(ADR-1510/1511 cmp-soundness call 3, 28.5K chars). T3 long: ADR-1510 cmp-liquidity call 16 (pairing, 87K chars).
T4 longest answer: ADR-1510 cmp-soundness-rerun call 20 (answer writing, 132K chars). Stored requests are replayed with
only provider routing and stream changed. Internal rules text is sent (user 2026-11-11/12: all documents may be sent)."""
import sys,json,gzip,time,hashlib,threading,os
from pathlib import Path
import httpx,jsonschema
ROOT=Path(__file__).resolve().parents[3];ADR=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1512-*'));ART=ADR/'artifacts';DES=ART/'design'
URL='https://openrouter.ai/api/v1/chat/completions';MODEL='qwen/qwen3.8-27b'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=1))
def read(p):return json.loads(Path(p).read_text())
def gzr(p):return json.loads(gzip.decompress(Path(p).read_bytes()))
CANDIDATES=[('deepinfra/bf16','DeepInfra'),('parasail/fp8','Parasail'),('coreweave/fp8','CoreWeave'),('reka/fp8','Reka'),
            ('chutes/fp8','Chutes'),('near-ai/fp8','Near AI'),('cloudflare','Cloudflare')]
SOURCES={'T2_hang':'04_EXPERIMENTS/ADR/ADR-1511-compare-research-budget-qwen/artifacts/live/candidate/cmp-soundness/raw/call-003/request.json.gz',
         'T3_long_pairing':'04_EXPERIMENTS/ADR/ADR-1510-compare-followup-budget-qwen/artifacts/live/candidate/cmp-liquidity/raw/call-016/request.json.gz',
         'T4_longest_answer':'04_EXPERIMENTS/ADR/ADR-1510-compare-followup-budget-qwen/artifacts/live/candidate/cmp-soundness-rerun/raw/call-020/request.json.gz'}
def small():
    schema={'type':'object','additionalProperties':False,'required':['document','article'],
            'properties':{'document':{'type':'string'},'article':{'type':'string'}}}
    return {'model':MODEL,'messages':[{'role':'system','content':'Answer with JSON only.'},
            {'role':'user','content':'주주총회 특별결의 요건을 정한 상법 조문의 문서 이름과 조문 번호를 하나만 적어 주세요.'}],
            'temperature':0,'reasoning':{'effort':'none'},
            'response_format':{'type':'json_schema','json_schema':{'name':'output','strict':True,'schema':schema}}}
def route(tag):
    return {'only':[tag],'order':[tag],**({'quantizations':[tag.rsplit('/',1)[1]]} if '/' in tag else {}),'allow_fallbacks':False,'require_parameters':True}
def freeze():
    assert not (DES/'freeze.json').exists(),'already frozen'
    DES.mkdir(parents=True,exist_ok=True)
    tests={'T1_small':small()}
    for k,p in SOURCES.items():
        body=gzr(ROOT/p);assert body['model']==MODEL and body.get('reasoning')=={'effort':'none'}
        assert not any(x in body for x in ('max_tokens','max_output_tokens','max_completion_tokens'))
        tests[k]=body
    for k,b in tests.items():put(DES/'requests'/(k+'.json'),b)
    put(DES/'candidates.json',[{'tag':t,'name':n} for t,n in CANDIDATES])
    put(DES/'sources.json',{k:{'path':p,'sha256':sha(ROOT/p)} for k,p in SOURCES.items()})
    put(DES/'criteria.json',{
     'question':'Which famous Qwen3.8 providers answer our real experiment requests (including the one Reka never answered) with strict JSON, and how fast does content start?',
     'pass_per_test':'HTTP 200, stream finished with finish_reason stop within 180 s, content is complete JSON valid against the request schema, response model qwen/qwen3.8-27b, provider name as routed, no reasoning tokens',
     'selection':'fallback list = providers that pass all 4 tests, ordered by (fewest failures, then median time to first non-blank content, then total seconds); at most 5. A provider failing T2 is not first. If fewer than 4 pass all, add providers passing 3 of 4 (not failing T2) and say so.',
     'fallback_threshold':'first-content limit for the transport = max(30 s, 3 x the largest time to first non-blank content among passing tests), capped at 60 s; stall limit 60 s without new content.',
     'limits':{'requests':28,'per_request_seconds':180,'reported_cost_usd':1.5},
     'model':MODEL,'reasoning':'none','output_cap':None,'repeats':1,'decision_eligible':False,'quality_certified':False})
    put(DES/'freeze.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in sorted(DES.rglob('*.json')) if p.name!='freeze.json'}|{str(Path(__file__).relative_to(ROOT)):sha(__file__)},
        'model_calls_before_freeze':0,'endpoints_snapshot':'/tmp/qwen-endpoints.json copied to design/endpoints.json'})
    print('frozen',len(tests),'tests',len(CANDIDATES),'providers')
def key():
    for line in (ROOT/'.env').read_text().splitlines():
        if line.startswith('OPEN_ROUTER='):return line.split('=',1)[1].strip().strip('"').strip("'")
    raise SystemExit('no key')
def one(tag,name,test,body,out):
    payload={**body,'provider':route(tag),'stream':True}
    payload.pop('stream_options',None)
    schema=(payload.get('response_format') or {}).get('json_schema',{}).get('schema')
    row={'provider':name,'tag':tag,'test':test,'request_chars':len(json.dumps(payload,ensure_ascii=False))}
    begin=time.monotonic();chunks=[];content=[];first=None;first_text=None;finish=None;usage=None;echo_provider=None;echo_model=None;err=None;status=None;reasoning=0
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=20,read=30,write=60,pool=20)) as c:
            with c.stream('POST',URL,json=payload,headers={'Authorization':'Bearer '+key(),'Content-Type':'application/json'}) as r:
                status=r.status_code
                if r.status_code!=200:
                    err=r.read().decode('utf-8','replace')[:500]
                else:
                    for line in r.iter_lines():
                        now=time.monotonic()-begin
                        if now>180:err='WALL_LIMIT_180S';break
                        chunks.append([round(now,3),line[:300]])
                        if not line.startswith('data:'):continue
                        data=line[5:].strip()
                        if data=='[DONE]':break
                        try:obj=json.loads(data)
                        except ValueError:continue
                        if 'error' in obj:err=json.dumps(obj['error'],ensure_ascii=False)[:500];break
                        echo_provider=obj.get('provider',echo_provider);echo_model=obj.get('model',echo_model)
                        if obj.get('usage'):usage=obj['usage']
                        for ch in obj.get('choices') or []:
                            d=ch.get('delta') or {}
                            if d.get('reasoning'):reasoning+=1
                            t=d.get('content') or ''
                            if t:
                                content.append(t)
                                if first is None:first=round(now,3)
                                if first_text is None and t.strip():first_text=round(now,3)
                            if ch.get('finish_reason'):finish=ch['finish_reason']
    except Exception as exc:
        err=type(exc).__name__+': '+str(exc)[:300]
    total=round(time.monotonic()-begin,3);text=''.join(content)
    valid=None
    if finish=='stop' and not err:
        try:
            v=json.loads(text);valid=True
            if schema:jsonschema.validate(v,schema)
        except Exception as exc:valid=False;err=(err or '')+' INVALID_JSON: '+str(exc)[:200]
    row.update(http_status=status,seconds=total,first_content_s=first,first_nonblank_s=first_text,finish_reason=finish,
        content_chars=len(text),blank_chars=len(text)-len(text.strip()),valid_json=valid,provider_echo=echo_provider,model_echo=echo_model,
        reasoning_chunks=reasoning,usage=usage,cost=(usage or {}).get('cost'),error=err,
        passed=bool(status==200 and finish=='stop' and valid and echo_model and echo_model.startswith(MODEL) and echo_provider==name and not reasoning and total<=180))
    d=out/name.replace(' ','_');d.mkdir(parents=True,exist_ok=True)
    (d/(test+'.sse.json.gz')).write_bytes(gzip.compress(json.dumps(chunks,ensure_ascii=False).encode()))
    (d/(test+'.content.txt')).write_text(text)
    put(d/(test+'.json'),row);return row
def run():
    fz=read(DES/'freeze.json')
    for rel,h in fz['files'].items():assert sha(ROOT/rel)==h,('frozen file changed',rel)
    assert not (ART/'results.json').exists(),'already run'
    tests={p.stem:read(p) for p in sorted((DES/'requests').glob('*.json'))}
    out=ART/'runs';results=[];lock=threading.Lock()
    def lane(tag,name):
        for t in ('T1_small','T2_hang','T3_long_pairing','T4_longest_answer'):
            r=one(tag,name,t,tests[t],out)
            with lock:results.append(r);print(name,t,'pass' if r['passed'] else 'FAIL',r['seconds'],'first',r['first_nonblank_s'],r['finish_reason'],(r['error'] or '')[:120],flush=True)
    th=[threading.Thread(target=lane,args=c) for c in [(c['tag'],c['name']) for c in read(DES/'candidates.json')]]
    [t.start() for t in th];[t.join() for t in th]
    put(ART/'results.json',results);print('cost',round(sum(r.get('cost') or 0 for r in results),5))
def report():
    rs=read(ART/'results.json');by={}
    for r in rs:by.setdefault(r['provider'],[]).append(r)
    rows=[]
    for p,lst in by.items():
        fails=sum(not r['passed'] for r in lst);t2=next(r for r in lst if r['test']=='T2_hang')
        fn=sorted(r['first_nonblank_s'] for r in lst if r['first_nonblank_s'] is not None)
        rows.append({'provider':p,'tag':lst[0]['tag'],'fails':fails,'t2_passed':t2['passed'],'median_first_nonblank_s':fn[len(fn)//2] if fn else None,
                     'max_first_nonblank_s':max(fn) if fn else None,'total_seconds':round(sum(r['seconds'] for r in lst),1),'cost':round(sum(r.get('cost') or 0 for r in lst),5),
                     'tests':{r['test']:{'pass':r['passed'],'s':r['seconds'],'first':r['first_nonblank_s'],'finish':r['finish_reason'],'err':(r['error'] or '')[:160]} for r in lst}})
    rows.sort(key=lambda x:(x['fails'],not x['t2_passed'],x['median_first_nonblank_s'] if x['median_first_nonblank_s'] is not None else 999,x['total_seconds']))
    put(ART/'ranking.json',rows)
    for x in rows:print(x['provider'],'fails',x['fails'],'T2',x['t2_passed'],'medFirst',x['median_first_nonblank_s'],'maxFirst',x['max_first_nonblank_s'],'total',x['total_seconds'],'cost',x['cost'])
    for x in rows:
        for t,v in x['tests'].items():print(' ',x['provider'],t,v)
if __name__=='__main__':{'freeze':freeze,'run':run,'report':report}[sys.argv[1]]()
