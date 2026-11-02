from pathlib import Path
import sys,json,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live'
sys.path.insert(0,str(Path(__file__).parent));import quota_fence as f
with f.connect() as db:v=f.inspect(db)
original=f.ORIGINAL;disk=shutil.disk_usage(R);host=shutil.disk_usage('/mnt/c');out={'sidda_used_bytes':v['used_bytes'],'sidda_actual_quota_bytes':v['quota_bytes'],'sidda_reference_quota_bytes':original,'sidda_used_percent':v['used_percent_of_original'],'original_reference_MiB':300,'fixed_cap_MiB':270,'prewrite_reserve_bytes':0,'disk_used_percent':disk.used/disk.total*100,'host_disk_used_percent':host.used/host.total*100,'within_limit':v['used_bytes']<=f.CAP and v['quota_bytes']==f.CAP and max(disk.used/disk.total,host.used/host.total)<=.9,'denominator':'Original300MiB reference, not new270MiB quota; server270MiB is the hard90percent fence'}
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(A/'artifacts'/sys.argv[1],out);assert out['within_limit'];print(json.dumps(out))
