"""Read-only evidence of internal child failure; never supplied to the product."""
from pathlib import Path
from collections import Counter
import json,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0839-main79-live-comparison';C=A/'artifacts/run-001/committee-duties-01'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=next((C/'runtime').glob('workflows/*/children/internal/**/journal.sqlite'));db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
es=[dict(x) for x in db.execute('select evidence_id,document_id,metadata_json from evidence_unit')];docs=Counter(x['document_id'] for x in es);errors=[dict(x) for x in db.execute("select seq,kind,payload_json from event where kind in ('COMPLETION_ASSESSMENT_REJECTED','RUN_FAILED') order by seq")];state=dict(db.execute('select status,phase from run').fetchone());db.close()
proposals=[]
for p in sorted((C/'raw').glob('*memory-assess*/response.json')):
 r=read(p);v=json.loads(r['choices'][0]['message']['content']);proposals.append({'path':str(p.relative_to(R)),'sha256':sha(p),'disposition':v.get('disposition'),'gaps':v.get('gaps')})
b=read(A/'artifacts/design/baseline.json')['manifest'];code=R/b['code_root']/'02_BACKEND/semantic_runtime/legal_agent/request_repair.py'
v={'case_id':'committee-duties-01','offline_diagnosis':True,'child_state':state,'read_evidence_units':len(es),'requested_internal_document_id':'11478916f48b00e5','requested_internal_read_units':docs['11478916f48b00e5'],'read_units_by_document':dict(docs),'events':errors,'proposals':proposals,'guard_source':{'path':str(code.relative_to(R)),'sha256':sha(code),'function':'bind_gaps'},'finding':'The intended internal document was read. After the model refined missing_target with (제5조 이후) while retaining the prior gap ID, the computed target identity changed and the completion guard rejected both assessment attempts. This is a transfer/completion failure, not a failure to find the internal document.','product_unchanged':True}
(C/'internal-transfer-diagnosis.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v[k] for k in ('child_state','read_evidence_units','requested_internal_read_units','read_units_by_document')},ensure_ascii=False))
