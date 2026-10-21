from pathlib import Path
import json,hashlib,sqlite3,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0876-original-coverage-scope-probe';O=A/'artifacts/run-001';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=A/'실험/manifest.json';m=read(p);m['design']['arms']=[a for a in m['design']['arms'] if a['id']=='scoped'];m['design']['arms'][0]['derived_from']=['ADR-0875-experiment-v1/observed'];m['results']['by_arm'].pop('baseline',None)
lp=O/'retrieval-ledger.json';v=read(lp);v['audit']={'scope':'Post-run native/return/final-set diagnosis; ranking menus not measured; not a legal-quality gold evaluation','ordinary_rag_final':'Ordinary final source IDs retained in response, workflow evidence-reference stage is empty for ordinary RAG and must not be interpreted as no quoted source.'};v['artifact_sha256']=hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest();put(lp,v)
g=read(A/'artifacts/design/baseline.json')['release']['data_path'];db=sqlite3.connect('file:'+str(R/g/'navigation/navigation.sqlite')+'?mode=ro',uri=True);total=db.execute("SELECT count(*) FROM source WHERE json_extract(json,'$.unit_id') IS NOT NULL").fetchone()[0];db.close()
counts=[len(c['stages'][-1]['after']) for c in v['runs'][0]['arms'][0]['cases']]
r=m['retrieval_accounting'];r.update(corpus_total=total,presented_total={'scoped':sum(counts)},presented_mean={'scoped':statistics.mean(counts)},presented_p50={'scoped':statistics.median(counts)},presented_p95={'scoped':sorted(counts)[round((len(counts)-1)*.95)]},selectivity={'scoped':statistics.mean(counts)/total});r['stage_ledger']['sha256']=sha(lp);put(p,m)
p=A/'artifacts/manifest.json';v=read(p)
for row in v['files']:
 path=R/row['path'];row.update(sha256=sha(path),bytes=path.stat().st_size)
put(p,v)
