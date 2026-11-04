import base64,json,sys,time,threading,importlib.util
from copy import deepcopy
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest,httpx
from stream_decoder import decode_stream

IDENT={'id':'gen-fixture','model':'qwen/qwen3.8-27b','provider':'Parasail'}
def chunk(content='',finish=None,**extra):
    return {**IDENT,'choices':[{'index':0,'delta':{'content':content},'finish_reason':finish}],**extra}
def wire(rows,done=True):
    return (': OPENROUTER PROCESSING\r\n\r\n'+''.join('data: '+json.dumps(r,ensure_ascii=False)+'\r\n\r\n' for r in rows)+('data: [DONE]\r\n\r\n' if done else '')).encode()
def rows():return [chunk('{"문장":'),chunk('"한글"}', 'stop'),chunk('', 'stop',usage={'prompt_tokens':2,'completion_tokens':5,'total_tokens':7,'cost':0})]

def test_content_and_usage_terminal_are_not_duplicated():
    value=decode_stream(wire(rows()))
    assert value['choices'][0]['message']['content']=='{"문장":"한글"}'
    assert value['usage']['total_tokens']==7 and value['provider']=='Parasail'

@pytest.mark.parametrize('mutation',['missing_done','identity','provider','model','index','extra_content','finish','usage','tools','role','partial','after_done'])
def test_bad_stream_cannot_become_success(mutation):
    r=rows();done=True
    if mutation=='missing_done':done=False
    if mutation in ('identity','provider','model'):r[1][{'identity':'id'}.get(mutation,mutation)]='changed'
    if mutation=='index':r[1]['choices'][0]['index']=1
    if mutation=='extra_content':r[2]['choices'][0]['delta']['content']='extra'
    if mutation=='finish':r[2]['choices'][0]['finish_reason']='length'
    if mutation=='usage':r[2].pop('usage')
    if mutation=='tools':r[0]['choices'][0]['delta']['tool_calls']=[{}]
    if mutation=='role':r[0]['choices'][0]['delta']['role']='user'
    raw=wire(r,done)
    if mutation=='partial':raw=raw[:-2]
    if mutation=='after_done':raw+=b'data: {}\n\n'
    with pytest.raises(ValueError):decode_stream(raw)

def test_length_and_reasoning_are_preserved_for_original_validator():
    r=rows()
    for c in r[1:]:c['choices'][0]['finish_reason']='length'
    r[0]['choices'][0]['delta']['reasoning']='not allowed'
    value=decode_stream(wire(r))
    assert value['choices'][0]['finish_reason']=='length'
    assert value['choices'][0]['message']['reasoning']=='not allowed'

def test_remote_error_is_preserved_even_with_http200():
    value=decode_stream(wire([chunk('', 'error',error={'message':'grammar failed'})]))
    assert value['error']['message']=='grammar failed'

def test_actual_worker_capture_and_assembly():
    root=Path('/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1356-qwen-stream-schema-diagnosis/artifacts/transport')
    spec=importlib.util.spec_from_file_location('stream_deadline',root/'02_BACKEND/lawrag/core/request_deadline.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    raw=wire(rows());seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('X-Generation-Id','gen-fixture');self.end_headers()
            self.wfile.write(raw)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        response=mod.post_json('http://127.0.0.1:'+str(server.server_port),headers={},json_body={'stream':True},deadline=time.monotonic()+10)
        assert response.json()==decode_stream(raw)
        assert response.extensions['stream_raw']==raw
        assert response.extensions['absolute_deadline']['response_headers']['x-generation-id']=='gen-fixture'
        assert response.extensions['absolute_deadline']['worker_reaped']
        assert seen==[{'stream':True}]
    finally:server.shutdown();server.server_close();thread.join()
