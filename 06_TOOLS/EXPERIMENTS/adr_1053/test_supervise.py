import importlib.util
import json
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('recovery_supervisor',Path(__file__).with_name('supervise.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_all_stages_order_and_no_replay():
 called=[]
 result=m.execute({},run=lambda phase,script,args:called.append(phase) or 0,ready=lambda:True,verify=lambda plan:None)
 assert called==['product','evaluation','report','providers']
 assert result['status']=='COMPLETE' and result['automatic_replay'] is False

@pytest.mark.parametrize('bad',['product','evaluation','report','providers'])
def test_failure_is_preserved_and_not_retried(bad):
 called=[]
 def run(phase,script,args):called.append(phase);return 2 if phase==bad else 0
 result=m.execute({},run=run,ready=lambda:True,verify=lambda plan:None)
 assert result['status']=='STOPPED' and result['failure']['phase']==bad
 assert called.count(bad)==1
 assert ('evaluation' in called)==(bad!='product')
 assert 'report' in called and 'providers' in called

def test_partial_matrix_cannot_start_judge():
 called=[]
 result=m.execute({},run=lambda phase,script,args:called.append(phase) or 0,ready=lambda:False,verify=lambda plan:None)
 assert 'evaluation' not in called and result['status']=='STOPPED'

def test_preserved_hash_changed_or_missing_fails(tmp_path):
 p=tmp_path/'result.json';p.write_text('original');plan={'preserved_files':{'result.json':m.sha(p)}}
 m.preserved(plan,tmp_path)
 p.write_text('changed')
 with pytest.raises(ValueError,match='result drift'):m.preserved(plan,tmp_path)
 p.unlink()
 with pytest.raises(ValueError):m.preserved(plan,tmp_path)

def test_original_execution_binding_changed_fails(tmp_path):
 p=tmp_path/'runner.py';p.write_text('original');plan={'preserved_files':{},'pinned_files':{'runner.py':m.sha(p)}}
 m.check(plan,tmp_path);p.write_text('changed')
 with pytest.raises(ValueError,match='binding'):m.check(plan,tmp_path)

def test_started_phase_never_replayed(tmp_path):
 (tmp_path/'product.log').write_text('old output')
 with pytest.raises(ValueError,match='already started'):m.run_phase('product','not-run.py',[],audit=tmp_path)
 assert (tmp_path/'product.log').read_text()=='old output'

def test_actual_child_failure_receipt_and_original_log(tmp_path):
 (tmp_path/'mock.py').write_text("print('saved failure');raise SystemExit(7)\n")
 result=m.run_phase('synthetic','mock.py',[],runner=tmp_path,audit=tmp_path,heartbeat_fn=lambda *args:{'status':'RUNNING'})
 receipt=m.read(tmp_path/'synthetic-process.json')
 assert result==7 and receipt['exit_code']==7 and receipt['reaped'] is True
 assert 'saved failure' in (tmp_path/'synthetic.log').read_text()
 with pytest.raises(ValueError):m.run_phase('synthetic','mock.py',[],runner=tmp_path,audit=tmp_path)

def test_readiness_requires_matching_reservations_and_all111(tmp_path):
 cells=[{'ordinal':i,'case_id':'q'+str(i),'arm':'A0'} for i in range(1,112)]
 m.save(tmp_path/'design-freeze.json',{'execution_order':cells});h=m.sha(tmp_path/'design-freeze.json')
 for c in cells:
  p=tmp_path/'matrix'/f"{c['ordinal']:03d}-{c['case_id']}-{c['arm']}"
  m.save(p/'reservation.json',{'design_freeze_sha256':h})
  m.save(p/'result.json',{'cell':c,'completed':True,'outcome':'SERVICE_COMPLETED'})
 assert m.product_ready(tmp_path)
 p=tmp_path/'matrix/111-q111-A0/result.json';old=m.read(p)
 m.save(p,{**old,'completed':False});assert not m.product_ready(tmp_path)
 m.save(p,old);m.save(p.with_name('reservation.json'),{'design_freeze_sha256':'other'})
 assert not m.product_ready(tmp_path)
