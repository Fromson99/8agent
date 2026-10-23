import gzip
import contextlib
import io
import http.server
import json
import os
import runpy
from pathlib import Path
import selectors
import signal
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'GENOS_RELAY_CHECK_20261023_R2.txt'
LAW = ('<?xml version="1.0" encoding="UTF-8"?><법령><기본정보><법령ID>010513</법령ID>'
       '<법령명_한글>자본시장과 금융투자업에 관한 법률</법령명_한글></기본정보>'
       '<조문><조문단위><조문내용>제1조 합성 조문</조문내용></조문단위></조문></법령>').encode()
NOTICE = b'<notice><items><item><title>synthetic fixture</title></item></items></notice>'


class Delivery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='relay-r2-check-')
        cls.root = Path(cls.temp.name)
        cls.cert, cls.key = cls.root/'ca.pem', cls.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cls.key),
                        '-out',str(cls.cert),'-days','1','-subj','/CN=localhost',
                        '-addext','subjectAltName=IP:127.0.0.1,DNS:localhost'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.records = []
        cls.payload, cls.status, cls.delay, cls.truncated = LAW, 200, 0, False
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle(self):
                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    # TLS-only and interrupt checks intentionally close without a full request.
                    pass

            def do_GET(self):
                cls.records.append(('GET', self.path, dict(self.headers)))
                payload, status, delay, truncated = cls.payload, cls.status, cls.delay, cls.truncated
                time.sleep(delay)
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/xml; charset=utf-8')
                    self.send_header('Content-Length', str(len(payload)+(100 if truncated else 0)))
                    if status == 302:
                        self.send_header('Location','https://127.0.0.1:9/do-not-follow')
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass

            def do_HEAD(self):
                cls.records.append(('HEAD',self.path,dict(self.headers)))
                self.send_error(405)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1',0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert,cls.key)
        cls.server.socket = context.wrap_socket(cls.server.socket,server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.origin = 'https://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        type(self).records.clear()
        type(self).payload, type(self).status, type(self).delay, type(self).truncated = LAW,200,0,False
        self.output = self.root/self._testMethodName
        self.env = dict(os.environ, MAKING_OC='mock-making-auth', LAW_OC='mock-law-auth',
                        RELAY_COOKIE='JSESSIONID=mock-session-auth; second=mock-secondary-auth',
                        HTTP_PROXY='http://127.0.0.1:9',HTTPS_PROXY='http://127.0.0.1:9')

    def command(self,*extra):
        return [sys.executable,str(SCRIPT),'--relay',self.origin,'--ca',str(self.cert),
                '--output',str(self.output),*extra]

    def invoke(self,*extra,expected=0):
        p = subprocess.run(self.command(*extra),env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(expected,p.returncode,p.stdout+p.stderr)
        for value in ('mock-making-auth','mock-law-auth','mock-session-auth','mock-secondary-auth'):
            self.assertNotIn(value,p.stdout+p.stderr)
        return p

    def state(self,name='law-01'):
        return json.loads((self.output/name/'result.json').read_text())

    def test_photo_contract_single_get_and_notice_status(self):
        type(self).payload = NOTICE
        p = self.invoke(expected=3)
        self.assertEqual(1,len(self.records))
        method,path,headers = self.records[0]
        self.assertEqual('GET',method)
        self.assertEqual('/law/making',urlsplit(path).path)
        self.assertEqual({'OC':['mock-making-auth'],'lsClsCd':['BA0103'],'closing':['Y'],
                          'asndOfiNm':['금융위원회'],'admRulNm':['지주']},parse_qs(urlsplit(path).query))
        self.assertEqual('https://opinion.lawmaking.go.kr/rest/ptcpAdmPp.xml',headers['target_url'])
        self.assertEqual(self.env['RELAY_COOKIE'],headers['Cookie'])
        self.assertNotIn('Content-Length',headers)
        state = self.state('notice-01')
        self.assertEqual('NOTICE_XML_REVIEW_REQUIRED',state['status'])
        self.assertEqual('REVIEW_REQUIRED',state['business_validation'])
        self.assertIn('BODY_PREVIEW',p.stdout)

    def test_law_success_same_socket_phases_and_persistent_logs(self):
        p = self.invoke('--request','law')
        state = self.state()
        self.assertEqual('BODY_OK',state['status'])
        self.assertEqual(1,state['physical_connections'])
        self.assertTrue(all(state[k] for k in ('tcp_connected','tls_established','http_request_sent','http_response_received')))
        phases = ['DNS_START','DNS_OK','TCP_START','TCP_OK','TLS_START','TLS_OK','HTTP_SEND','HTTP_WAIT',
                  'HTTP_HEADERS','HTTP_BODY','XML_VALIDATE','RESPONSE_SAVED','BODY_PREVIEW','RESULT']
        events = [json.loads(line)['event'] for line in (self.output/'law-01/events.jsonl').read_text().splitlines()]
        self.assertEqual(phases, [event for event in events if event in phases])
        log = (self.output/'law-01/terminal.log').read_text()
        for line in log.splitlines():
            self.assertIn(line,p.stdout)
        self.assertEqual(LAW,gzip.decompress((self.output/'law-01/response.body.gz').read_bytes()))
        self.assertEqual(0o600,(self.output/'law-01/result.json').stat().st_mode & 0o777)

    def test_network_only_no_credentials_or_http(self):
        self.env.pop('LAW_OC'); self.env.pop('MAKING_OC'); self.env.pop('RELAY_COOKIE')
        self.invoke('--request','tls')
        self.assertEqual('TLS_OK',self.state('tls-01')['status'])
        self.assertEqual([],self.records)

    def test_tls_timeout_is_after_successful_same_tcp(self):
        class Stall(socketserver.BaseRequestHandler):
            def handle(self):
                time.sleep(.6)
        server = socketserver.ThreadingTCPServer(('127.0.0.1',0),Stall)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            self.invoke('--request','law','--relay','https://127.0.0.1:'+str(server.server_address[1]),
                        '--tls-timeout','.1',expected=2)
            state=self.state()
            self.assertEqual('TIMEOUT',state['status'])
            self.assertEqual('TLS_START',state['failure_phase'])
            self.assertTrue(state['tcp_connected']); self.assertFalse(state['tls_established'])
            self.assertFalse(state['http_request_sent'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_http_wait_timeout_after_tls_and_request(self):
        type(self).delay=.5
        self.invoke('--request','law','--read-timeout','.1',expected=2)
        state=self.state()
        self.assertEqual('TIMEOUT',state['status'])
        self.assertEqual('HTTP_WAIT',state['failure_phase'])
        self.assertTrue(state['tls_established']); self.assertTrue(state['http_request_sent'])
        self.assertFalse(state['http_response_received'])

    def start_waiting(self):
        type(self).delay=1.2
        process=subprocess.Popen(self.command('--request','law'),env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
        data=b'';deadline=time.time()+5
        while time.time()<deadline and b'HTTP_WAIT' not in data:
            if selector.select(.2):
                data+=os.read(process.stdout.fileno(),65536)
        selector.close()
        self.assertIn(b'HTTP_WAIT',data)
        self.assertIsNone(process.poll())
        return process,data

    def test_console_and_file_show_progress_before_request_finishes(self):
        process,data=self.start_waiting()
        try:
            log=(self.output/'law-01/terminal.log').read_text()
            self.assertIn('HTTP_WAIT',log);self.assertNotIn('HTTP_HEADERS',log)
            rest,error=process.communicate(timeout=5)
            self.assertEqual(0,process.returncode,(data+rest+error).decode())
        finally:
            if process.poll() is None:process.kill();process.communicate()

    def test_concurrency_interrupt_and_no_replay(self):
        process,data=self.start_waiting()
        try:
            p=self.invoke('--request','law',expected=2);self.assertIn('RUN_BUSY',p.stdout)
            process.send_signal(signal.SIGINT)
            process.communicate(timeout=5)
            self.assertEqual(130,process.returncode)
            self.assertEqual('INTERRUPTED',self.state()['status'])
            self.invoke('--request','law',expected=2)
            self.assertEqual(1,len(self.records))
        finally:
            if process.poll() is None:process.kill();process.communicate()

    def test_success_failure_and_unknown_are_never_replayed(self):
        self.invoke('--request','law')
        self.invoke('--request','law')
        type(self).status=403
        self.invoke('--request','law','--run-id','failed',expected=2)
        self.invoke('--request','law','--run-id','failed',expected=2)
        state=self.state('failed');state['status']='IN_FLIGHT'
        (self.output/'failed/result.json').write_text(json.dumps(state))
        self.invoke('--request','law','--run-id','failed',expected=2)
        self.assertEqual(2,len(self.records))

    def test_http_error_redirect_and_no_follow(self):
        for status in (401,403,429,302):
            type(self).status=status
            self.invoke('--request','law','--run-id','http-'+str(status),expected=2)
            self.assertEqual('HTTP_'+str(status),self.state('http-'+str(status))['status'])
        self.assertEqual(4,len(self.records))

    def test_malformed_wrong_identity_entity_and_truncated_body(self):
        for i,payload in enumerate((b'<html>Login</html>',LAW.replace(b'010513',b'999999'),
                                   b'<!DOCTYPE a [<!ENTITY b "bad">]><a>&b;</a>',LAW[:80])):
            type(self).payload=payload
            self.invoke('--request','law','--run-id','bad-'+str(i),expected=2)
            self.assertEqual('RESPONSE_REJECTED',self.state('bad-'+str(i))['status'])
        type(self).payload=LAW;type(self).truncated=True
        self.invoke('--request','law','--run-id','truncated',expected=2)
        self.assertEqual('TRUNCATED_HTTP_BODY',self.state('truncated')['reason'])

    def test_secrets_redacted_in_preview_console_and_all_files(self):
        type(self).status=403
        type(self).payload=b'<error>mock-making-auth mock-session-auth mock-secondary-auth</error>'
        self.invoke(expected=2)
        folder=self.output/'notice-01'
        saved=b''.join((folder/n).read_bytes() for n in ('result.json','terminal.log','events.jsonl'))
        saved+=gzip.decompress((folder/'response.body.gz').read_bytes())
        for value in (b'mock-making-auth',b'mock-session-auth',b'mock-secondary-auth'):
            self.assertNotIn(value,saved)
        self.assertTrue(self.state('notice-01')['credential_redacted'])

    def test_tls_trust_error_and_tcp_refusal(self):
        args=self.command('--request','law');index=args.index('--ca');del args[index:index+2]
        p=subprocess.run(args,env=self.env,capture_output=True,text=True,timeout=5)
        self.assertEqual(2,p.returncode)
        self.assertEqual('TLS_ERROR',self.state()['status'])
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.invoke('--request','law','--relay','https://127.0.0.1:'+str(port),'--run-id','closed',expected=2)
        self.assertEqual('TCP_START',self.state('closed')['failure_phase'])
        self.assertFalse(self.state('closed')['tcp_connected'])

    def test_changed_binding_expired_budget_and_size_limit(self):
        self.invoke('--request','law')
        p=self.invoke('--request','law','--law-origin','https://www.law.go.kr',expected=2)
        self.assertIn('BINDING_CHANGED',p.stdout)
        state=self.state();state.update(status='READY',deadline=time.time()-1)
        (self.output/'law-01/result.json').write_text(json.dumps(state))
        p=self.invoke('--request','law',expected=2)
        self.assertIn('BUDGET_EXHAUSTED',p.stdout)
        self.assertEqual(1,len(self.records))
        type(self).payload=b'x'*(12*1024*1024+1)
        self.invoke('--request','law','--run-id','large',expected=2)
        self.assertEqual('RESPONSE_SIZE_LIMIT',self.state('large')['reason'])

    def test_uncertain_http_write_is_not_reported_as_unsent(self):
        program=runpy.run_path(str(SCRIPT),run_name='relay_r2_test')
        output=io.StringIO()
        previous_umask=os.umask(0o077)
        try:
            with mock.patch.dict(os.environ,self.env), mock.patch.object(sys,'argv',self.command('--request','law')[1:]), \
                 mock.patch.object(program['http'].client.HTTPConnection,'request',side_effect=BrokenPipeError('synthetic partial write')), \
                 contextlib.redirect_stdout(output):
                result=program['main']()
        finally:
            os.umask(previous_umask)
        self.assertEqual(2,result)
        state=self.state()
        self.assertEqual('HTTP_SEND',state['failure_phase'])
        self.assertIsNone(state['http_request_sent'])
        self.assertTrue(state['tls_established'])


if __name__=='__main__':
    unittest.main(verbosity=2)
