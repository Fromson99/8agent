"""Losslessly retain completed test scratch; verify before removing local copies."""
from pathlib import Path
import hashlib,json,shutil,tarfile
R=Path(__file__).resolve().parents[3];O=R/'09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance/test-scratch-archives'
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
logs=[('adr0835-tests-r1',R/'04_EXPERIMENTS/ADR/ADR-0835-comparison-llm-judgment/artifacts/tests-r1.log','43 passed'),('adr0836-tests-r1',R/'04_EXPERIMENTS/ADR/ADR-0836-comparison-owned-tools/artifacts/tests-r1.log','40 passed'),('adr0837-tests-r1',R/'04_EXPERIMENTS/ADR/ADR-0837-comparison-advisory-items/artifacts/tests-r1.log','53 passed'),('adr0838-working-tests-r1',R/'04_EXPERIMENTS/ADR/ADR-0838-comparison-judgment-qualification/artifacts/working-api.log','53 passed')]
for name,log,passed in logs:
 assert passed in log.read_text();root=Path('/tmp')/name;archive=O/(name+'.tar.gz');receipt=O/(name+'.json')
 if receipt.exists():continue
 if not root.exists():
  receipt.write_text(json.dumps({'status':'scratch_not_present_at_archival','original_path':str(root),'archived':False,'test_log':str(log.relative_to(R)),'test_log_sha256':digest(log),'note':'Permanent test logs, raw model outputs and service journals remain in ADR artifacts. Missing ephemeral scratch was not removed by this archive step.'},ensure_ascii=False,indent=2)+'\n');print(name,'scratch unavailable; permanent records retained',flush=True);continue
 assert root.is_dir() and not archive.exists()
 files={str(p.relative_to(root.parent)):{'sha256':digest(p),'bytes':p.stat().st_size} for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
 with tarfile.open(archive,'w:gz',compresslevel=1) as tar:tar.add(root,arcname=name)
 verified=set()
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    with tar.extractfile(member) as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    assert files[member.name]=={'sha256':h,'bytes':member.size};verified.add(member.name)
 assert verified==set(files)
 assert all(digest(root.parent/n)==v['sha256'] for n,v in files.items())
 value={'archive':str(archive.relative_to(R)),'sha256':digest(archive),'archive_bytes':archive.stat().st_size,'original_bytes':sum(v['bytes'] for v in files.values()),'files':files,'verification':'Every regular file compared after archive decompression; source files unchanged before removal. Symlinks and metadata preserved by tar.','restore':'tar -xzf '+str(archive.relative_to(R))+' -C /tmp','test_log':str(log.relative_to(R)),'test_log_sha256':digest(log)}
 receipt.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');shutil.rmtree(root)
 print(name,'verified and archived',value['original_bytes'],'->',value['archive_bytes'],flush=True)
