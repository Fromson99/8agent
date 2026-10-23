"""Sequential recovery contracts using the exact sealed GENOS service entrypoint."""
from pathlib import Path
import asyncio
import hashlib
import importlib.util
import io
import json
import os
import sys
import time
import unittest
from unittest.mock import patch
import zipfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('notebook_fixture',HERE.parent/'pipeline_diagnostics_20261023_r2/test_notebook.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


class RecoveryTests(base.NotebookTests):
    def setUp(self):
        super().setUp()
        self.client_module_loaded=self.prepare()
        self.ns['run'].__defaults__=('prepare','LEGAL_PIPELINE_WORKSPACE',str(self.work),'new-job')
        exec(compile((HERE/'DATAIKU_PIPELINE_RELEASE_FAILED_20261023_R1.txt').read_bytes(),'delivered-recovery','exec'),self.ns)
        service_dir=self.root/'service';service_dir.mkdir()
        archive=HERE.parent/'pipeline_service_20261022_r3/GENOS_PIPELINE_SERVICE_20261022_R2.zip'
        with zipfile.ZipFile(archive) as z:
            for basename in ('service.py','CODE_PINS.json','transport.py'):
                member=next(n for n in z.namelist() if n.split('/',1)[1]==basename)
                (service_dir/basename).write_bytes(z.read(member))
        spec=importlib.util.spec_from_file_location('recovery_sealed_service',service_dir/'service.py')
        self.service=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.service)
        self.assertEqual(self.service.code_pin(),self.ns['RECOVERY_SERVICE_SHA'])
        self.scratch=self.root/'scratch'
        self.env_patch=patch.dict(os.environ,{'PIPELINE_SCRATCH':str(self.scratch)})
        self.env_patch.start()
        health=self.service.handle({'API_TYPE':'HEALTH'});self.instance=health['instance']
        self.old_id='1'*32;self.new_id='2'*32;self.deadline=time.time()+600
        self.old_server=self.scratch/self.old_id;self.old_server.mkdir()
        self.calls=[];self.ack_drop=False;self.response_fault=None
        archives={slot:{'sha256':hashlib.sha256(self.folder.data[name]).hexdigest(),'bytes':len(self.folder.data[name])}
                  for slot,name in [('raw','RAW_INPUT.zip'),('support','PIPELINE_SUPPORT.zip')]}
        self.old_state={'job_id':self.old_id,'job_token':'a'*64,'instance':self.instance,
                        'code_sha256':self.service.code_pin(),'status':'FAILED','phase':'STRUCTURE',
                        'remote':{'status':'FAILED','phase':'STRUCTURE'},'archives':archives,'deadline':self.deadline,
                        'support_zip':str(self.root/'PIPELINE_SUPPORT.zip')}
        self.new_state={**self.old_state,'job_id':self.new_id,'job_token':'b'*64,'status':'NEW'}
        self.new_state.pop('remote');self.new_state.pop('phase')
        server={k:v for k,v in self.old_state.items() if k not in ('job_token','remote','support_zip')}
        server.update(token_hash=hashlib.sha256(('a'*64).encode()).hexdigest(),error='STAGE_FAILED: STRUCTURE; fixture',received={})
        self.write_server(server)
        (self.old_server/'worker.log').write_bytes(b'worker failed\n')
        (self.old_server/'structure.log').write_bytes(b'FileNotFoundError: original.hwp\n')
        (self.old_server/'workspace').mkdir();(self.old_server/'workspace/generated.tmp').write_bytes(b'regenerable')
        raw_blob={'path':'_pipeline/blobs/'+archives['raw']['sha256']+'.zip',**archives['raw']}
        self.folder.data[raw_blob['path']]=self.folder.data['RAW_INPUT.zip']
        binding={'service_url_sha256':hashlib.sha256(self.variables['LEGAL_PIPELINE_URL'].encode()).hexdigest(),
                 'service_code':self.service.code_pin(),'input':{'project':'LEGAL_RAG','folder_id':self.folder.get_id(),
                 'client_sha256':self.ns['RECOVERY_CLIENT_SHA']}}
        self.old_checkpoint={'binding':binding,'client':self.old_state,'raw_blob':raw_blob,'deadline':self.deadline,'reserved_sql_calls':128}
        self.new_checkpoint={'binding':binding,'client':self.new_state,'raw_blob':raw_blob,'deadline':self.deadline,'reserved_sql_calls':64}
        self.put_checkpoint('old-job',self.old_checkpoint)
        self.put_checkpoint('new-job',self.new_checkpoint)
        self.original_checkpoints={k:v for k,v in self.folder.data.items() if k.startswith('_pipeline/jobs/')}
        self.http_patch=patch.object(self.client_module_loaded.urllib.request,'urlopen',self.urlopen)
        self.http_patch.start()

    def tearDown(self):
        self.http_patch.stop();self.env_patch.stop();super().tearDown()
    def write_server(self,state):
        (self.old_server/'state.json').write_text(json.dumps(state))
    def server_state(self):return json.loads((self.old_server/'state.json').read_text())
    def put_checkpoint(self,name,value,seq=1):
        raw=json.dumps(value).encode();sha=hashlib.sha256(raw).hexdigest()
        self.folder.data[f'_pipeline/jobs/{name}/checkpoint-{seq:010d}-{sha}.json']=raw
    def urlopen(self,request,timeout):
        data=json.loads(request.data);self.calls.append(data)
        response=asyncio.run(self.service.service({},data))
        if data['API_TYPE']=='ACK' and self.ack_drop:raise TimeoutError('ACK response lost')
        if self.response_fault:response=self.response_fault(data,response)
        return io.BytesIO(json.dumps(response).encode())
    def recover(self):return self.ns['pipeline_release_previous']('old-job')
    def auth(self,state):return {k:state[k] for k in ('job_id','job_token','instance','code_sha256')}
    def assert_no_ack(self):self.assertNotIn('ACK',[c['API_TYPE'] for c in self.calls])
    def latest_recovery(self):return self.ns['_rc_latest'](self.folder,'_pipeline/recovery/'+self.old_id+'/event-')[1]
    def update_recovery(self,value):
        seq,_,_=self.ns['_rc_latest'](self.folder,'_pipeline/recovery/'+self.old_id+'/event-')
        raw=json.dumps(value).encode();sha=hashlib.sha256(raw).hexdigest()
        self.folder.data[f'_pipeline/recovery/{self.old_id}/event-{seq+1:010d}-{sha}.json']=raw

    def test_release_preserves_inputs_logs_and_same_new_start(self):
        with self.assertRaisesRegex(RuntimeError,'BUSY'):
            self.client_module_loaded.Client(self.variables['LEGAL_PIPELINE_URL'],self.variables['LEGAL_PIPELINE_TOKEN']).call(
                'START',**self.auth(self.new_state),archives=self.new_state['archives'],deadline=self.deadline)
        self.assertEqual(self.recover()['status'],'RELEASED')
        self.assertEqual([p.name for p in self.old_server.iterdir()],['state.json'])
        preserved=self.latest_recovery()['preserved']
        for info in preserved['inputs'].values():self.assertEqual(hashlib.sha256(self.folder.data[info['path']]).hexdigest(),info['sha256'])
        self.assertEqual(preserved['logs']['worker.log']['status'],'PRESERVED')
        self.assertEqual(preserved['logs']['prepare.log']['status'],'NOT_CREATED_ENOENT')
        self.assertEqual({k:self.folder.data[k] for k in self.original_checkpoints},self.original_checkpoints)
        result=self.client_module_loaded.Client(self.variables['LEGAL_PIPELINE_URL'],self.variables['LEGAL_PIPELINE_TOKEN']).call(
            'START',**self.auth(self.new_state),archives=self.new_state['archives'],deadline=self.deadline)
        self.assertEqual(result['status'],'UPLOADING');self.assertEqual(result['job_id'],self.new_id)
        self.assertNotIn('EXECUTE',[c['API_TYPE'] for c in self.calls])
        self.assertNotIn('a'*64,self.output.getvalue());self.assertNotIn('api-secret',self.output.getvalue())

    def test_running_is_not_released(self):
        state=self.server_state();state.update(status='RUNNING',worker=self.service.pid_identity(os.getpid()))
        self.write_server(state)
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_NOT_FAILED_STRUCTURE'):self.recover()
        self.assert_no_ack();self.assertEqual(self.server_state()['status'],'RUNNING')

    def test_complete_is_not_released(self):
        state=self.server_state();state.update(status='COMPLETE',result={'sha256':'f'*64});self.write_server(state)
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_NOT_FAILED_STRUCTURE'):self.recover()
        self.assert_no_ack()

    def test_other_phase_is_not_released(self):
        state=self.server_state();state['phase']='INDEX';self.write_server(state)
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_NOT_FAILED_STRUCTURE'):self.recover()
        self.assert_no_ack()

    def test_raw_hash_corruption_blocks_ack(self):
        self.folder.data[self.old_checkpoint['raw_blob']['path']]=b'corrupt'
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_ARCHIVE'):self.recover()
        self.assert_no_ack()

    def test_missing_mandatory_log_blocks_ack(self):
        (self.old_server/'structure.log').unlink()
        with self.assertRaises(self.ns['RunError']):self.recover()
        self.assert_no_ack()

    def test_wrong_log_chunk_hash_blocks_ack(self):
        def fault(data,response):
            if data['API_TYPE']=='DOWNLOAD' and response['code']==0:response['data']['sha256']='0'*64
            return response
        self.response_fault=fault
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_LOG_CHUNK_HASH'):self.recover()
        self.assert_no_ack()

    def test_managed_preservation_failure_blocks_ack(self):
        original=self.folder.upload_stream
        def fail(path,stream):
            if '/files/' in path:raise OSError('managed storage unavailable')
            return original(path,stream)
        self.folder.upload_stream=fail
        with self.assertRaises(self.ns['RunError']):self.recover()
        self.assert_no_ack();self.assertEqual(self.server_state()['status'],'FAILED')

    def test_instance_change_blocks_ack(self):
        (self.scratch/'instance.json').write_text(json.dumps({'instance':'different'}))
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_INSTANCE_CHANGED'):self.recover()
        self.assert_no_ack()

    def test_new_job_with_progress_is_not_treated_as_unaccepted(self):
        self.new_checkpoint['client']['status']='RUNNING';self.put_checkpoint('new-job',self.new_checkpoint,2)
        with self.assertRaisesRegex(self.ns['RunError'],'CURRENT_JOB_NOT_UNSTARTED'):self.recover()
        self.assert_no_ack()

    def test_uncertain_ack_reconciles_status_without_second_ack(self):
        self.ack_drop=True
        with self.assertRaisesRegex(self.ns['RunError'],'TRANSPORT_UNCERTAIN'):self.recover()
        self.assertEqual(self.server_state()['status'],'RELEASED')
        before=self.latest_recovery()['api_calls'];self.ack_drop=False
        self.assertEqual(self.recover()['status'],'RELEASED')
        self.assertEqual(sum(c['API_TYPE']=='ACK' for c in self.calls),1)
        self.assertEqual(self.latest_recovery()['api_calls'],before+2)

    def test_repeated_recovery_does_not_delete_again_or_reset_budget(self):
        self.recover();deadline=self.latest_recovery()['deadline'];calls=self.latest_recovery()['api_calls']
        self.recover();self.assertEqual(sum(c['API_TYPE']=='ACK' for c in self.calls),1)
        self.assertEqual(self.latest_recovery()['deadline'],deadline)
        self.assertEqual(self.latest_recovery()['api_calls'],calls+2)

    def test_exhausted_recovery_budget_does_not_call_api(self):
        self.recover();value=self.latest_recovery();value['api_calls']=100;self.update_recovery(value)
        before=len(self.calls)
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_API_BUDGET_EXHAUSTED'):self.recover()
        self.assertEqual(len(self.calls),before)

    def test_stale_checkpoint_after_preservation_blocks_ack(self):
        original=self.folder.upload_stream
        def update(path,stream):
            original(path,stream)
            if '/files/' in path:
                changed={**self.old_checkpoint,'last_error':'changed'};self.put_checkpoint('old-job',changed,2)
        self.folder.upload_stream=update
        with self.assertRaisesRegex(self.ns['RunError'],'RECOVERY_STALE_CHECKPOINT'):self.recover()
        self.assert_no_ack()

    def test_old_support_preserved_if_current_upload_changed(self):
        self.folder.data['PIPELINE_SUPPORT.zip']=b'new support'
        receipt=json.loads(self.folder.data['PIPELINE_SUPPORT.zip.receipt.json']);receipt['sha256']='0'*64
        self.folder.data['PIPELINE_SUPPORT.zip.receipt.json']=json.dumps(receipt).encode()
        self.recover();info=self.latest_recovery()['preserved']['inputs']['support']
        self.assertEqual(hashlib.sha256(self.folder.data[info['path']]).hexdigest(),self.old_state['archives']['support']['sha256'])


if __name__=='__main__':
    suite=unittest.TestSuite(RecoveryTests(name) for name in RecoveryTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
