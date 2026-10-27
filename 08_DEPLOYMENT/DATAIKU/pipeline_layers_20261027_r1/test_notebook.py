"""Small sequential checks against the complete delivered notebook and sealed client."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE
RUNNER = HERE / 'DATAIKU_PIPELINE_RUN_20261027_R1.txt'
PREFIXES = ('transport', 'restore_inputs', 'dataiku_run', 'managed_job', 'lawrag', 'semantic_runtime')


class Folder:
    def __init__(self):
        self.data = {}; self.uploads = []; self.fail_save = False
    def get_id(self): return 'fixture-folder'
    def list_paths_in_partition(self): return list(self.data)
    def get_download_stream(self, path): return io.BytesIO(self.data[path.lstrip('/')])
    def upload_stream(self, path, stream):
        if self.fail_save: raise OSError('simulated save failure')
        self.data[path] = stream.read(); self.uploads.append(path)


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.work = self.root / 'work'; self.folder = Folder(); self.variables = {}
        self.saved_path = sys.path[:]
        self.saved_modules = {k: v for k, v in sys.modules.items() if k == 'dataiku' or self.client_module(k)}
        for k in self.saved_modules: del sys.modules[k]
        fake = types.SimpleNamespace(default_project_key=lambda: 'LEGAL_RAG',
                                     get_custom_variables=lambda: self.variables,
                                     Folder=lambda *a, **k: self.folder)
        sys.modules['dataiku'] = fake
        self.ns = {'__name__': 'test_notebook'}
        exec(compile(RUNNER.read_bytes(), str(RUNNER), 'exec'), self.ns)
        spec = importlib.util.spec_from_file_location('fixture_transport', HERE.parent/'pipeline_service_20261022_r3/src/transport.py')
        transport = importlib.util.module_from_spec(spec); spec.loader.exec_module(transport)
        source = self.root/'source'; source.write_bytes(b'tiny source')
        for name, member in [('RAW_INPUT.zip', '01_DATA/RAW/external/test.xml'),
                             ('PIPELINE_SUPPORT.zip', '01_DATA/LEXICON/test.txt')]:
            receipt = transport.pack({member: source}, self.root/name)
            self.folder.data[name] = (self.root/name).read_bytes()
            self.folder.data[name+'.receipt.json'] = json.dumps(receipt).encode()
        name = 'DATAIKU_PIPELINE_CLIENT_20261027_R1.zip'
        self.folder.data[name] = (BASE/name).read_bytes()
        self.output = io.StringIO(); self.capture = contextlib.redirect_stdout(self.output); self.capture.__enter__()

    @staticmethod
    def client_module(k): return any(k == p or k.startswith(p+'.') for p in PREFIXES)
    def tearDown(self):
        self.capture.__exit__(None, None, None)
        for k in list(sys.modules):
            if k == 'dataiku' or self.client_module(k): del sys.modules[k]
        sys.modules.update(self.saved_modules); sys.path[:] = self.saved_path; self.temp.cleanup()
    def run_cell(self, action='prepare'):
        return self.ns['run'](action, folder_name='fixture-folder', work_dir=str(self.work), job_name='new-job')
    def prepare(self):
        self.assertEqual(self.run_cell()['status'], 'READY')
        self.variables.update(LEGAL_PIPELINE_URL='https://example.invalid/pipeline', LEGAL_PIPELINE_TOKEN='api-secret')
        return sys.modules['dataiku_run']
    def reports(self): return [json.loads(p.read_text()) for p in (self.work/'diagnostics').glob('error-*.json')]
    def api_fixture(self, response=None, failure=None):
        module = self.prepare(); calls = []
        def execute(inputs, support, job, **kwargs):
            job.mkdir(parents=True, exist_ok=True)
            state = {'job_id': 'a'*32, 'job_token': 'b'*64, 'instance': 'fixture', 'code_sha256': 'c'*64, 'status': 'NEW'}
            (job/'client.json').write_text(json.dumps(state))
            return module.Client(self.variables['LEGAL_PIPELINE_URL'], self.variables['LEGAL_PIPELINE_TOKEN']).call(
                'START', **{k: state[k] for k in ('job_id','job_token','instance','code_sha256')})
        module.run_dataiku = execute
        def urlopen(request, timeout):
            calls.append(json.loads(request.data))
            if failure: raise failure
            return io.BytesIO(json.dumps(response).encode())
        return patch.object(module.urllib.request, 'urlopen', urlopen), calls, module

    def test_prepare_idempotent_keeps_binding(self):
        self.run_cell(); binding = (self.work/'input-binding.json').read_bytes()
        self.run_cell(); self.assertEqual(binding, (self.work/'input-binding.json').read_bytes())
        self.assertEqual(self.reports(), [])

    def test_new_target_cell_does_not_inherit_old_names_or_auto_run(self):
        ns = {'__name__':'__main__'}
        exec("def run(action='run', folder_name='LEGAL_PIPELINE_WORKSPACE', work_dir='actual-work', job_name='long-real-name'): pass", ns)
        exec(compile(RUNNER.read_bytes(), str(RUNNER), 'exec'), ns)
        self.assertEqual(ns['run'].__defaults__, ('prepare','SET_S3_MANAGED_FOLDER_ID','./legal_pipeline_layers_20261027_r1','layers_20261027_r1'))
        self.assertNotIn('PIPELINE_RESULT', ns)
        self.assertIn('RUNNER_READY', self.output.getvalue())

    def test_actual_client_busy_visible_and_durable(self):
        transport, calls, _ = self.api_fixture({'code':1,'error':'BUSY: retrieve/acknowledge or release the previous temporary job first'})
        with transport, self.assertRaisesRegex(self.ns['RunError'], 'BUSY'):
            self.run_cell('run')
        self.assertEqual([c['API_TYPE'] for c in calls], ['START'])
        report = self.reports()[0]
        self.assertEqual((report['code'],report['operation'],report['saved_status']), ('BUSY','START','NEW'))
        self.assertIn('previous temporary job', self.output.getvalue())
        self.assertIn('pipeline_jobs()', self.output.getvalue())
        self.assertTrue(self.folder.uploads)
        self.assertEqual(json.loads(self.folder.data[self.folder.uploads[0]]), report)

    def test_actual_client_http_failure_preserves_status_and_no_retry(self):
        error = urllib.error.HTTPError('https://example.invalid/pipeline',403,'Forbidden',{},None)
        transport, calls, _ = self.api_fixture(failure=error)
        with transport, self.assertRaisesRegex(self.ns['RunError'], 'HTTP_ERROR'):
            self.run_cell('run')
        report=self.reports()[0]; self.assertEqual(report['http_status'],403)
        self.assertIn('Forbidden',self.output.getvalue()); self.assertEqual(len(calls),1)
        error.close()

    def test_actual_client_timeout_cause_preserved(self):
        transport, calls, _ = self.api_fixture(failure=TimeoutError('TLS peer timed out'))
        with transport, self.assertRaisesRegex(self.ns['RunError'], 'TRANSPORT_UNCERTAIN'):
            self.run_cell('run')
        self.assertIn('TLS peer timed out', self.output.getvalue()); self.assertEqual(len(calls),1)

    def test_no_credential_in_screen_exception_or_journals(self):
        message = 'BUSY: api-secret ' + 'b'*64 + ' Authorization: Bearer other-token password=hidden Cookie="session=abc"'
        transport, _, _ = self.api_fixture({'code':1,'error':message})
        with transport, self.assertRaises(self.ns['RunError']) as caught: self.run_cell('run')
        combined = self.output.getvalue()+str(caught.exception)+json.dumps(self.reports())
        for secret in ('api-secret','b'*64,'other-token','hidden','session=abc'):
            self.assertNotIn(secret, combined)
        self.assertIn('[REDACTED]', combined)

    def test_repeat_observer_does_not_repeat_call(self):
        transport,calls,module = self.api_fixture({'code':0,'data':{'status':'COMPLETE','oracle_written':True}})
        first=module.Client.call
        self.ns['_observe_client'](module); self.ns['_observe_client'](module)
        self.assertIs(first,module.Client.call)
        with transport: self.assertEqual(self.run_cell('run')['status'],'COMPLETE')
        self.assertEqual(len(calls),1)

    def test_managed_log_failure_does_not_replace_original(self):
        transport,_,_=self.api_fixture({'code':1,'error':'BUSY: previous job'})
        self.folder.fail_save=True
        with transport,self.assertRaisesRegex(self.ns['RunError'],'BUSY'):self.run_cell('run')
        self.assertIn('DIAGNOSTIC_MANAGED_SAVE_FAILED',self.output.getvalue())
        self.assertEqual(self.reports()[0]['code'],'BUSY')

    def test_local_log_failure_does_not_replace_original(self):
        transport,_,_=self.api_fixture({'code':1,'error':'BUSY: previous job'})
        (self.work/'diagnostics').write_text('obstruction')
        with transport,self.assertRaisesRegex(self.ns['RunError'],'BUSY'):self.run_cell('run')
        self.assertIn('DIAGNOSTIC_LOCAL_SAVE_FAILED',self.output.getvalue())
        self.assertTrue(self.folder.uploads)

    def test_changed_input_binding_still_rejected(self):
        self.run_cell(); before=(self.work/'input-binding.json').read_bytes()
        receipt=json.loads(self.folder.data['RAW_INPUT.zip.receipt.json']); receipt['sha256']='0'*64
        self.folder.data['RAW_INPUT.zip.receipt.json']=json.dumps(receipt).encode()
        with self.assertRaisesRegex(self.ns['RunError'],'INPUT_BINDING_CHANGED'):self.run_cell()
        self.assertEqual(before,(self.work/'input-binding.json').read_bytes())

    def test_modified_client_still_rejected_before_import(self):
        self.folder.data['DATAIKU_PIPELINE_CLIENT_20261027_R1.zip']=b'corrupt'
        with self.assertRaisesRegex(self.ns['RunError'],'DOWNLOAD_HASH_OR_SIZE'):self.run_cell()
        self.assertNotIn('dataiku_run',sys.modules)

    def test_local_code_tampering_rejected(self):
        self.prepare(); path=self.work/'code/DATAIKU_PIPELINE_CLIENT_20261027_R1/dataiku_run.py'
        path.write_text('tampered')
        with self.assertRaisesRegex(self.ns['RunError'],'INSTALLED_CODE_CHANGED'):self.run_cell()

    def test_schema_error_directly_visible_without_api(self):
        module=self.prepare()
        def fail(*a,**k):raise ValueError('MISSING_COLUMN: SIDDS.LGL_DOC_VER_S.DOC_ID')
        module.run_dataiku=fail
        with self.assertRaisesRegex(self.ns['RunError'],'MISSING_COLUMN'):self.run_cell('check')
        self.assertIn('SIDDS.LGL_DOC_VER_S.DOC_ID',self.output.getvalue())
        self.assertEqual(self.reports()[0]['operation'],'not reached')

    def test_keyboard_interrupt_remains_interrupt(self):
        module=self.prepare()
        def fail(*a,**k):raise KeyboardInterrupt()
        module.run_dataiku=fail
        with self.assertRaises(KeyboardInterrupt):self.run_cell('run')
        self.assertEqual(self.reports()[0]['code'],'KeyboardInterrupt')

    def test_budget_exception_stays_failure(self):
        module=self.prepare()
        def fail(*a,**k):raise RuntimeError('JOB_SQL_BUDGET_EXHAUSTED')
        module.run_dataiku=fail
        with self.assertRaisesRegex(self.ns['RunError'],'JOB_SQL_BUDGET_EXHAUSTED'):self.run_cell('run')
        self.assertIn('초기화하지',self.output.getvalue())

    def test_message_limit_is_explicit(self):
        self.work.mkdir()
        report=self.ns['report_failure'](ValueError('X'*20000),work=self.work,action='check',job_name='new-job')
        self.assertTrue(report['exceptions'][0]['message_truncated'])
        self.assertIn('DETAIL_TRUNCATED',self.output.getvalue())

    def test_exception_cycle_is_bounded(self):
        error=RuntimeError('cycle');error.__context__=error
        self.assertEqual(len(list(self.ns['_exception_chain'](error))),1)

    def test_cookie_header_all_values_redacted(self):
        value=self.ns['_redact']('Cookie: first=one; second=two\nBUSY: previous job')
        self.assertNotIn('one',value);self.assertNotIn('two',value)
        self.assertIn('BUSY: previous job',value)

    def test_work_lock_still_blocks_duplicate(self):
        import fcntl
        self.work.mkdir()
        with (self.work/'runner.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(self.ns['RunError'],'RUNNING'):self.run_cell()
        self.assertFalse((self.work/'input-binding.json').exists())

    def test_managed_deadline_and_budget_survive_diagnostics(self):
        self.prepare()
        sys.path.insert(0,str(self.work/'code/DATAIKU_PIPELINE_CLIENT_20261027_R1/02_BACKEND'))
        import managed_job
        store=managed_job.ManagedJob(self.folder,'budget-job',{'fixture':'same'})
        deadline=store.value['deadline']
        class Client:
            SQL_PATH='/sql';schema_map=None
            def request(self,*a,**k):return 'ok'
        bounded=managed_job.BudgetClient(Client(),store,max_calls=65)
        self.assertEqual(bounded.request(),'ok')
        self.assertEqual(store.value['reserved_sql_calls'],64)
        self.ns['report_failure'](RuntimeError('BUSY: previous'),work=self.work,action='run',job_name='budget-job',folder=self.folder)
        resumed=managed_job.ManagedJob(self.folder,'budget-job',{'fixture':'same'})
        self.assertEqual(resumed.value['deadline'],deadline)
        self.assertEqual(resumed.value['reserved_sql_calls'],64)
        with self.assertRaisesRegex(ValueError,'JOB_BINDING_CHANGED'):
            managed_job.ManagedJob(self.folder,'budget-job',{'fixture':'changed'})

    def test_sealed_service_busy_through_actual_process_and_runner(self):
        import asyncio
        module=self.prepare();service_dir=self.root/'sealed-service';service_dir.mkdir()
        archive=HERE.parent/'pipeline_service_20261022_r3/GENOS_PIPELINE_SERVICE_20261022_R2.zip'
        with zipfile.ZipFile(archive) as z:
            for basename in ('service.py','CODE_PINS.json','transport.py'):
                member=next(n for n in z.namelist() if n.split('/',1)[1]==basename)
                (service_dir/basename).write_bytes(z.read(member))
        self.assertEqual((service_dir/'transport.py').read_bytes(),Path(module.t.__file__).read_bytes())
        spec=importlib.util.spec_from_file_location('sealed_pipeline_service',service_dir/'service.py')
        service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
        expected=(self.work/'code/DATAIKU_PIPELINE_CLIENT_20261027_R1/SERVICE_CODE_SHA256.txt').read_text().strip()
        self.assertEqual(service.code_pin(),expected)
        scratch=self.root/'scratch';previous=scratch/('0'*32);previous.mkdir(parents=True)
        before=json.dumps({'status':'FAILED','phase':'STRUCTURE','error':'fixture missing origin'}).encode()
        (previous/'state.json').write_bytes(before)
        calls=[]
        def urlopen(request,timeout):
            data=json.loads(request.data);calls.append(data['API_TYPE'])
            return io.BytesIO(json.dumps(asyncio.run(service.service({},data))).encode())
        def execute(inputs,support,job,**kwargs):
            return module.process(module.Client(self.variables['LEGAL_PIPELINE_URL'],self.variables['LEGAL_PIPELINE_TOKEN']),
                                  inputs,support,job,expected_code_sha256=expected)
        module.run_dataiku=execute
        with patch.dict(os.environ,{'PIPELINE_SCRATCH':str(scratch)}),patch.object(module.urllib.request,'urlopen',urlopen):
            with self.assertRaisesRegex(self.ns['RunError'],'BUSY'):self.run_cell('run')
        self.assertEqual(calls,['HEALTH','START'])
        self.assertEqual((previous/'state.json').read_bytes(),before)
        state=json.loads((self.work/'jobs/new-job/client.json').read_text())
        self.assertEqual(state['status'],'NEW')
        self.assertEqual(self.reports()[0]['operation'],'START')

    def add_checkpoint(self,name='old-job',status='FAILED',seq=1,corrupt=False,binding_change=False):
        state={'job_id':'d'*32,'job_token':'e'*64,'instance':'fixture','code_sha256':'f'*64,'status':status}
        binding={'service_url_sha256':hashlib.sha256(self.variables['LEGAL_PIPELINE_URL'].encode()).hexdigest(),
                 'service_code':'f'*64,'input':{'folder_id':self.folder.get_id(),'project':'LEGAL_RAG',
                 'client_sha256':self.ns['CLIENT_SHA256']}}
        if binding_change:binding['service_url_sha256']='0'*64
        raw=json.dumps({'binding':binding,'client':state,'deadline':123,'reserved_sql_calls':64}).encode()
        path=f'_pipeline/jobs/{name}/checkpoint-{seq:010d}-{hashlib.sha256(raw).hexdigest()}.json'
        self.folder.data[path]=b'bad' if corrupt else raw
        return path,raw

    def test_status_inspection_only_and_checkpoint_unchanged(self):
        module=self.prepare();path,raw=self.add_checkpoint();calls=[]
        def call(self,op,**fields):
            calls.append(op);return {'status':'FAILED','phase':'STRUCTURE','error':'missing source'}
        with patch.object(module.Client,'call',call):rows=self.ns['pipeline_jobs']()
        self.assertEqual(calls,['STATUS']);self.assertEqual(rows[0]['status'],'FAILED')
        self.assertEqual(raw,self.folder.data[path]);self.assertEqual(self.folder.uploads,[])
        self.assertNotIn('e'*64,self.output.getvalue())

    def test_inspection_refuses_corrupt_checkpoint(self):
        module=self.prepare();self.add_checkpoint(corrupt=True)
        with patch.object(module.Client,'call',side_effect=AssertionError('network forbidden')):
            with self.assertRaisesRegex(self.ns['RunError'],'CHECKPOINT_HASH'):self.ns['pipeline_jobs']()

    def test_inspection_skips_different_endpoint(self):
        module=self.prepare();self.add_checkpoint(binding_change=True)
        with patch.object(module.Client,'call',side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.ns['pipeline_jobs'](),[])

    def test_inspection_failed_status_does_not_claim_absence(self):
        module=self.prepare();self.add_checkpoint()
        with patch.object(module.Client,'call',side_effect=RuntimeError('PIPELINE_REPLY: JOB_LOST')):
            rows=self.ns['pipeline_jobs']()
        self.assertEqual(rows[0]['status'],'STATUS_UNCONFIRMED')

    def test_inspection_duplicate_checkpoint_rejected(self):
        self.prepare();self.add_checkpoint();self.add_checkpoint(status='NEW')
        with self.assertRaisesRegex(self.ns['RunError'],'CONCURRENT_JOB_CHECKPOINT'):self.ns['pipeline_jobs']()

    def test_delivered_zip_exact_runner_and_no_javascript(self):
        with zipfile.ZipFile(HERE/'DATAIKU_PIPELINE_LAYERS_20261027_R1.zip') as z:
            self.assertEqual(z.read('DATAIKU_PIPELINE_LAYERS_20261027_R1/'+RUNNER.name),RUNNER.read_bytes())
            self.assertIsNone(z.testzip())
            self.assertFalse(any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist()))


if __name__=='__main__':unittest.main(verbosity=2)
