"""Preserve already completed observations and bind the unchanged continuation."""
from supervise import *
import gzip
import importlib.util

def main():
 if (AUDIT/'resume-plan.json').exists():raise ValueError('resume plan already frozen')
 sys.path.insert(0,str(RUNNER));import run_case,run_matrix
 frozen,*_=run_case.load_frozen();freeze_sha=sha(EXPERIMENT/'design-freeze.json')
 assert not (EXPERIMENT/'matrix-stop.json').exists()
 completed=[];preserved_files={};ephemeral=[]
 for cell in frozen['execution_order']:
  p=run_case.cell_directory(cell)
  if p.exists():
   assert run_matrix.finished(cell,freeze_sha),cell
   completed.append(cell['ordinal'])
   for f in sorted(p.rglob('*')):
    if not f.is_file():continue
    relative=str(f.relative_to(ROOT))
    if f.name.endswith('-shm'):
     target=AUDIT/'original-lock-pages'/f'{cell["ordinal"]:03d}-{f.name}.gz';target.parent.mkdir(parents=True,exist_ok=True)
     with f.open('rb') as src,gzip.open(target,'xb') as dst:
      while part:=src.read(1024*1024):dst.write(part)
     ephemeral.append({'path':relative,'sha256':sha(f),'archive':str(target.relative_to(ROOT)),'archive_sha256':sha(target),'reason':'SQLite transient shared-memory lock/readmark pages may change on read-only metric collection; exact pre-recovery bytes archived.'})
    else:preserved_files[relative]=sha(f)
   for f in [p.with_suffix('.log'),p.with_suffix('.resources.json')]:
    if f.is_file():preserved_files[str(f.relative_to(ROOT))]=sha(f)
 assert completed==list(range(1,19)),completed
 assert not any(p.exists() for p in [EXPERIMENT/'matrix/019-cm-014-A0',EXPERIMENT/'evaluation'])
 pins={**frozen['runner_hashes'],str((EXPERIMENT/'design-freeze.json').relative_to(ROOT)):freeze_sha}
 for p in Path(__file__).parent.glob('*.py'):pins[str(p.relative_to(ROOT))]=sha(p)
 plan={'schema_version':'existing-experiment-service-continuation-v1','authorized_by':'user',
  'user_request':'왜 실행기가 종료됐는지 확인하고 고쳐줘. 기존 결과는 보존하고 중단된 지점부터 이어서 실험 끝까지 돌려봐.',
  'frozen_at':stamp(),'source_experiment':'ADR-1049-experiment-v1','audit_experiment':'ADR-1050-experiment-v1',
  'unit':UNIT,'preserved_completed_cells':completed,'resume_ordinal':19,'remaining_cells':93,
  'preserved_files':preserved_files,'ephemeral_originals':ephemeral,'pinned_files':pins,
  'product_and_judge_unchanged':True,'original_budget_and_deadline_preserved':True,
  'previous_requests_not_replayed':True,'provider_policy_changed':False,
  'missing_guard_receipts':[{'ordinal':18,'status':'NOT_RECORDED_BY_LOST_PARENT','process_exit_code':None,'guard_peak_rss_bytes':None,'reaped_by_original_guard':None,'child_result_complete':True,'child_process_no_longer_running':True}],
  'original_guard_gap':'Parent process disappeared while its detached cell18 child continued and saved a complete bounded outcome. Do not fabricate parent exit or resource measurements.',
  'service_policy':{'Restart':'no','KillMode':'control-group','TimeoutStopSec':45,'OOMPolicy':'stop','RemainAfterExit':True},
  'phases':[{'name':name,'script':script,'args':args} for name,script,args in PHASES]}
 save(AUDIT/'resume-plan.json',plan,exclusive=True)
 check(plan)
 print('Frozen continuation: existing18 preserved; next19;93remaining; unchanged111-cell design.')
if __name__=='__main__':main()
