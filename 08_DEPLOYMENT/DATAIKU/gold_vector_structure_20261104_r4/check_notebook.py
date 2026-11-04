"""Execute the delivered TXT in a real local Jupyter kernel with a fixture worker."""
from pathlib import Path
import json
import sys
import tempfile
from jupyter_client import KernelManager

HERE = Path(__file__).resolve().parent


def run():
    results = []
    with tempfile.TemporaryDirectory(prefix='vector-r4-kernel-') as temp:
        root = Path(temp)
        km = KernelManager(kernel_name='python3')
        km.kernel_spec.argv[0] = sys.executable
        km.start_kernel(cwd=str(root))
        client = km.client(); client.start_channels(); client.wait_for_ready(timeout=30)
        try:
            for failed in (False,True):
                case = root/('failed' if failed else 'success');case.mkdir();(case/'old').mkdir()
                lines = [json.dumps({'phase':'VECTOR_PLANNING','completed_sources':0,'total_sources':1000,'planned_rows':0}),
                         json.dumps({'phase':'VECTOR_PLAN_COMPLETE','total_rows':1000,'total_sources':1000})]
                lines += [json.dumps({'phase':'VECTOR_PROGRESS','rows':i,'total_rows':1000,
                                     'rows_per_second':10,'remaining_seconds':100,'run_seconds':i,'sdk_calls':i//16})
                          for i in range(1000)]
                lines += [json.dumps({'phase':'DIAGNOSTIC_ERROR','causes':[{'type':'Stop','message':'fixture <script>error</script>'}]}
                                    if failed else {'phase':'VECTORS_STORED_INSERT_ACK_NOT_ACTIVATED','rows':1000})]
                worker='import sys\nsys.stdout.write('+repr('\n'.join(lines)+'\n')+')\nsys.stdout.flush()\nraise SystemExit('+str(int(failed))+')'
                worker_path=case/'fixture_worker.py';worker_path.write_text(worker)
                code="""import io,json,sys,os,tempfile,subprocess
from pathlib import Path
from types import SimpleNamespace as NS
os.chdir(%r)
archive=Path(%r)
folder=NS(list_paths_in_partition=lambda:['/'+archive.name],get_download_stream=lambda name:io.BytesIO(archive.read_bytes()))
sys.modules['dataiku']=NS(Folder=lambda name:folder)
tempfile.gettempdir=lambda:%r
real_popen=subprocess.Popen
def fixture(args,**kwargs):return real_popen([sys.executable,'-u',%r],**kwargs)
subprocess.Popen=fixture
try:
    script=Path(%r).read_text().replace('OLD_JOB_DIR = ""','OLD_JOB_DIR = '+repr(%r),1)
    namespace={}
    exec(compile(script,'delivered-notebook','exec'),namespace)
    Path('result.json').write_text(json.dumps(namespace['VECTOR_RESULT']))
finally:subprocess.Popen=real_popen
""" % (str(case),str(HERE/'DATAIKU_GOLD_VECTOR_STRUCTURE_20261104_R4.zip'),str(case),str(worker_path),
                         str(HERE/'DATAIKU_GOLD_VECTOR_STRUCTURE_RUN_R4.txt'),str(case/'old'))
                message_id=client.execute(code)
                messages=[]
                while True:
                    message=client.get_iopub_msg(timeout=30)
                    if message['parent_header'].get('msg_id')!=message_id:continue
                    messages.append(message)
                    if message['msg_type']=='status' and message['content'].get('execution_state')=='idle':break
                errors=[m['content'] for m in messages if m['msg_type']=='error']
                assert not errors,[(e['ename'],e['evalue']) for e in errors]
                displays=[m for m in messages if m['msg_type']=='display_data']
                updates=[m for m in messages if m['msg_type']=='update_display_data']
                streams=[m for m in messages if m['msg_type']=='stream']
                assert len(displays)==1 and 1<=len(updates)<=8
                display_id=displays[0]['content']['transient']['display_id']
                assert all(m['content']['transient']['display_id']==display_id for m in updates)
                assert not streams,streams
                html=updates[-1]['content']['data']['text/html']
                result=json.loads((case/'result.json').read_text())
                assert result['status']==('FAILED_OR_STOPPED' if failed else 'COMPLETE')
                assert result['process_exit']==int(failed)
                assert ('오류' in html or '중단' in html) if failed else '적재 완료' in html
                assert '<script>' not in html
                log=Path(result['log_path']).read_text()
                assert all(line in log for line in lines)
                results.append({'case':'failure' if failed else 'success','display_data':len(displays),
                                'update_display_data':len(updates),'same_display_id':True,'stream_messages':0,
                                'raw_lines_retained':len(lines),'result':result['status'],'process_exit':result['process_exit']})
                (HERE/('PANEL_FAILURE.html' if failed else 'PANEL_SUCCESS.html')).write_text(html)
        finally:
            client.stop_channels();km.shutdown_kernel(now=True)
    report={'status':'PASS','environment':'local Jupyter kernel / Python '+sys.version.split()[0],
            'field_dataiku':False,'model_calls':0,'oracle_calls':0,'cases':results}
    (HERE/'NOTEBOOK_RESULT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
