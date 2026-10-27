"""Finish the report index after its placeholder artifact manifest collision."""
from common import *
from datetime import datetime, timezone
manifest = read(ADR/'실험/manifest.json')
assert manifest['results']['status'] == 'failed' and manifest['reservation']['status'] == 'in_progress'
previous = read(ADR/'artifacts/manifest.json')
assert previous['files'][0]['path'] == 'TODO'
put(ADR/'artifacts/report-finalization.json', {'issue':'closeout_failed.py wrote source/results, then append-only artifact-manifest creation encountered the original scaffold placeholder.',
    'resolution':'Only replace the scaffold artifact index and add the top-level index. No experiment result, frozen code, criteria or raw failure is changed.',
    'product_or_experiment_execution':False})
paths = [p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name != 'manifest.json']
paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1076').glob('*.py'))
put(ADR/'artifacts/manifest.json', {'schema_version':'adr-artifacts-v1','adr_id':'ADR-1076',
    'created_at':manifest['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'Frozen finite census, failed native reconstruction or post-failure reporting. Success-only helpers were prepared but not executed.',
        'contains_raw_prompts_and_outputs':'run-002' in str(p)} for p in sorted(paths)]},replace=True)
index = ROOT/'04_EXPERIMENTS/ADR/README.md'
text = index.read_text()
line = '- [ADR1076 원문 준비 재사용 검증](ADR-1076-navigation-view-preparation-reuse/README.md) — 주1,318쌍 동등; native baseline38번째 생성ID 비교 실패·후보재생 미실행. 승격자격 없음·MAIN104 유지.\n\n'
if 'ADR-1076-navigation-view-preparation-reuse/README.md' not in text:
    index.write_text(text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
print('Failed source and artifact index complete; no experiment rerun')
