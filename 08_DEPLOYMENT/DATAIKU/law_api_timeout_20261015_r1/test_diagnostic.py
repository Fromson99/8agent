import contextlib
import hashlib
import http.server
import io
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

import requests
from urllib3.exceptions import ReadTimeoutError

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'law_api_20261015_r1'))
from relay_check import RelayCheck
SOURCE=(HERE/'DATAIKU_TIMEOUT_DIAG_20261015_R1_CELL.txt').read_text()
NS={}
with contextlib.redirect_stdout(io.StringIO()):exec(compile(SOURCE,'delivered-cell','exec'),NS)
diagnose=NS['diagnose_existing_timeout']


class Response:
    def __init__(self,status=200,body=b'<?xml version="1.0"?><result>ok</result>',error=None):
        self.status_code=status;self.body=body;self.error=error;self.closed=False
    def iter_content(self,chunk_size):
        if self.error:raise self.error
        yield self.body
    def close(self):self.closed=True


class Session(requests.Session):
    def __init__(self,response):
        super().__init__();self.response=response;self.requests=[];self.trust_env=False
    def request(self,*a,**kw):
        self.requests.append((a,kw))
        if isinstance(self.response,BaseException):raise self.response
        return self.response


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    def check(self,result=Response(),**cfg):
        config=dict(relay_origin='https://relay.example:8443',output_root=self.tmp.name)
        config.update(cfg)
        c=RelayCheck(config,'FAKE_OC_953',cookie='COOKIE_FAKE_582',session=Session(result))
        c.records={'law_published_body':dict(status='TIMEOUT',params={'ID':'010513','type':'XML'},elapsed_seconds=8.02)}
        c.calls=1;c.blocked=True;c._save_summary();return c
    def run_diag(self,c):
        with contextlib.redirect_stdout(io.StringIO()):return diagnose(c)
    def test_connect_timeout_preserves_parent(self):
        c=self.check(requests.exceptions.ConnectTimeout('timeout OC=FAKE_OC_953'))
        original=(c.out/'summary.json').read_bytes()
        r=self.run_diag(c)
        self.assertEqual(r['status'],'CONNECTION_SETUP_TIMEOUT')
        self.assertEqual((c.out/'summary.json').read_bytes(),original)
        self.assertEqual(c.calls,1);self.assertTrue(c.blocked)
        self.assertEqual(r['combined_known_calls'],2)
        self.assertNotIn('FAKE_OC_953',(c.out/'timeout_diag_r1.json').read_text())
    def test_read_timeout_headers(self):
        c=self.check(requests.exceptions.ReadTimeout('wait'))
        r=self.run_diag(c);self.assertEqual(r['status'],'RESPONSE_WAIT_TIMEOUT')
        self.assertEqual(r['stage'],'awaiting_response_headers')
    def test_wrapped_body_timeout(self):
        c=self.check(Response(error=requests.exceptions.ConnectionError(ReadTimeoutError(None,'/','wait'))))
        r=self.run_diag(c);self.assertEqual(r['status'],'BODY_READ_TIMEOUT')
        self.assertEqual(r['http_status'],200);self.assertTrue(c.session.response.closed)
    def test_tls_and_proxy_classification(self):
        for exc,status in [(requests.exceptions.SSLError('cert'),'TLS_ERROR'),
                           (requests.exceptions.ProxyError('proxy http://u:p@proxy.example:8'),'PROXY_ERROR')]:
            c=self.check(exc);r=self.run_diag(c);self.assertEqual(r['status'],status)
            self.assertNotIn('u:p@',json.dumps(r))
    def test_no_retry_or_reexecution(self):
        c=self.check(requests.exceptions.ReadTimeout('wait'));r=self.run_diag(c)
        self.assertEqual(self.run_diag(c),r);self.assertEqual(len(c.session.requests),1)
        a,k=c.session.requests[0]
        self.assertFalse(k['allow_redirects']);self.assertEqual(k['timeout'],(8,20))
        self.assertTrue(k['verify']);self.assertEqual(k['headers']['Cookie'],'COOKIE_FAKE_582')
        self.assertEqual(k['headers']['target_url'],'http://www.law.go.kr/DRF/lawService.do?target=law')
        self.assertNotIn('target',k['params'])
    def test_no_data_success_for_http200(self):
        c=self.check();r=self.run_diag(c)
        self.assertEqual(r['status'],'HTTP_200_WITH_FIRST_BYTES');self.assertFalse(r['legal_data_success'])
    def test_http_redirect_auth_error_not_followed(self):
        for status in [302,401,403,500]:
            c=self.check(Response(status=status));r=self.run_diag(c)
            self.assertEqual(r['status'],'HTTP_'+str(status));self.assertFalse(r['legal_data_success'])
            self.assertEqual(len(c.session.requests),1)
    def test_effective_proxy_redacted(self):
        c=self.check();c.session.proxies={'https':'http://proxyuser:proxypass@proxy.example:8080'}
        r=self.run_diag(c);self.assertTrue(r['effective_proxy_enabled'])
        self.assertEqual(r['effective_proxy_host'],'proxy.example:8080')
        self.assertNotIn('proxypass',json.dumps(r))
    def test_target_query_binding(self):
        c=self.check(target_in_header=False);self.run_diag(c)
        k=c.session.requests[0][1]
        self.assertEqual(k['params']['target'],'law');self.assertNotIn('?',k['headers']['target_url'])
    def test_unknown_or_invalid_prior_state_blocks(self):
        for key,value in [('status','BODY_OK'),('params',{'ID':'bad','type':'XML'})]:
            c=self.check();c.records['law_published_body'][key]=value
            with self.assertRaises(ValueError):self.run_diag(c)
            self.assertEqual(len(c.session.requests),0)
    def test_budget_and_retry_guard(self):
        c=self.check();c.calls=8
        with self.assertRaises(ValueError):self.run_diag(c)
        c=self.check();c.session.mount('https://',requests.adapters.HTTPAdapter(max_retries=2))
        with self.assertRaises(ValueError):self.run_diag(c)
        self.assertEqual(len(c.session.requests),0)
    def test_interruption_stays_inflight_no_retry(self):
        c=self.check(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):self.run_diag(c)
        r=self.run_diag(c);self.assertEqual(r['status'],'IN_FLIGHT');self.assertEqual(len(c.session.requests),1)
    def test_exact_cell_and_original_folder_upload(self):
        c=self.check();ns={'check':c}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(SOURCE,'delivered-cell','exec'),ns)
            exec(compile(SOURCE,'delivered-cell','exec'),ns)
        self.assertEqual(len(c.session.requests),1)
        import types
        from unittest.mock import patch
        class Folder:
            def __init__(self):self.data={}
            def upload_data(self,n,b):self.data[n]=b
            def get_download_stream(self,n):return io.BytesIO(self.data[n])
        folder=Folder()
        with patch.dict(sys.modules,{'dataiku':types.SimpleNamespace(Folder=lambda _:folder)}),contextlib.redirect_stdout(io.StringIO()):
            c.export_to_dataiku('fake')
        self.assertTrue(any(n.endswith('/timeout_diag_r1.json') for n in folder.data))
    def test_real_loopback_tls_request_same_cell(self):
        root=Path(self.tmp.name);cert=root/'cert.pem';key=root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-keyout',str(key),'-out',str(cert),'-subj','/CN=localhost',
                        '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)
        received=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                u=urlsplit(self.path);received.append({'path':u.path,'query':parse_qs(u.query),'target':self.headers.get('target_url')})
                body=b'<?xml version="1.0"?><response>test fixture</response>'
                self.send_response(200);self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            c=self.check(relay_origin='https://127.0.0.1:'+str(server.server_port),ca_bundle=str(cert))
            c.session=requests.Session();c.session.trust_env=False
            ns={'check':c}
            with contextlib.redirect_stdout(io.StringIO()):exec(compile(SOURCE,'delivered-cell','exec'),ns)
            r=ns['_timeout_diagnosis'];self.assertEqual(r['status'],'HTTP_200_WITH_FIRST_BYTES')
            self.assertEqual(received[0]['path'],'/law/DRF')
            self.assertEqual(received[0]['query']['OC'],['FAKE_OC_953'])
            self.assertEqual(received[0]['query']['ID'],['010513'])
            self.assertEqual(received[0]['target'],'http://www.law.go.kr/DRF/lawService.do?target=law')
            c.session.close()
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    (HERE/'TEST_TRANSCRIPT.txt').write_text(stream.getvalue())
    print(stream.getvalue())
    report={'status':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'exact_txt_sha256':hashlib.sha256(SOURCE.encode()).hexdigest(),
            'loopback_tls_same_cell':result.wasSuccessful(),'original_dataiku_folder_consumer':result.wasSuccessful(),
            'samsung_relay_calls':0,'external_law_calls':0,'genos_calls':0,'scope':'Synthetic failures and local HTTPS only'}
    (HERE/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
