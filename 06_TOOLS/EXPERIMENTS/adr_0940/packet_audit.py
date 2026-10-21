"""Size attribution for repeated parent review packets; not a semantic failure score."""
from pathlib import Path
from collections import Counter
import gzip,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0940-research-continuity-prompt-cost'
for P in (A/'artifacts/run-001').glob('*/*'):
 if not (P/'audit.json').exists():continue
 rows=[]
 for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  with gzip.open(p,'rt') as f:v=json.load(f)['view']
  if v.get('source_stage')!='workflow-items':continue
  packet=v.get('packet',{});ids=packet.get('evidence_ids',[])
  rows.append({'generation':int(p.name[:3]),'review_mode':v.get('review_mode'),'source_ids_sha256':hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest(),'packet_source_count':len(ids),'new_evidence_count':len(v.get('new_evidence_ids',[])),'view_chars':len(json.dumps(v,ensure_ascii=False,separators=(',',':'))),'sources_chars':len(json.dumps(v.get('sources'),ensure_ascii=False,separators=(',',':')))})
 counts=Counter(r['source_ids_sha256'] for r in rows)
 result={'reviews':rows,'repeated_source_packet_presentations':sum(n-1 for n in counts.values()),'interpretation':'Same packet source identities may be reviewed again with changed findings or remaining evidence. This metric isolates repeated context cost; it is not by itself proof of an invalid retry.'}
 (P/'packet-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
