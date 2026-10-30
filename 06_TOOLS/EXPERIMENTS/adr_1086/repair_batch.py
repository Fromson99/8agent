from pathlib import Path
import sys,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding';C=R/'02_BACKEND/lawrag/research/candidates/adr_1086/compact-r1';S=C/'snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=S/'02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py';s=p.read_text();old="                    acquired.update((e['evidence_id'], {**e, 'text': '\\n'.join(span['text'] for span in e['spans'])}) for e in projected)";assert old in s;s=s.replace(old,"                    if new:\n                        acquired = {e['evidence_id']: e for e in self.work.evidence()}");p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/repository.py';s=p.read_text();old="""        rows = self.db.execute('SELECT * FROM evidence_unit'+(' WHERE evidence_id=?' if ident else '')+' ORDER BY evidence_id',
                               (ident,) if ident else ())
        result = []
        for row in rows:
            spans = [dict(s) for s in self.db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal', (row['evidence_id'],))]""";new="""        rows = list(self.db.execute('SELECT * FROM evidence_unit'+(' WHERE evidence_id=?' if ident else '')+' ORDER BY evidence_id',
                               (ident,) if ident else ()))
        # One request-owned journal, two indexed/order-compatible reads. Keep
        # per-evidence span order and the original byte/hash validation below.
        spans_by_id = {}
        if rows:
            for span in self.db.execute('SELECT * FROM evidence_span'+(' WHERE evidence_id=?' if ident else '')+' ORDER BY evidence_id,ordinal',
                                        (ident,) if ident else ()):
                spans_by_id.setdefault(span['evidence_id'], []).append(dict(span))
        result = []
        for row in rows:
            spans = spans_by_id.get(row['evidence_id'], [])""";assert old in s;s=s.replace(old,new);p.write_text(s)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text());targets=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('bounded_source_session.py','repository.py')]
for ref in v['engines'].values():
 ep=S/ref['manifest'];e=json.loads(ep.read_text());changed=False
 for rel in targets:
  if rel in e['files']:e['files'][rel]=sha(S/rel);changed=True
 if changed:put(ep,e);ref['sha256']=sha(ep)
put(p,v)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac;ac.freeze(C)
f=json.loads((A/'artifacts/design/freeze.json').read_text());put(A/'artifacts/design/freeze-rev003.json',f)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';f.update(code_root=str(code.relative_to(R)),note='Contract development: use exact DB span rows including ordinal/evidence_id, refresh newly recorded assessment evidence in a batch; evidence() itself now2actual SQL SELECTs for all request-owned evidence. Original hashes/ordering/permissions unchanged. Before live run.')
f['binding'].update(manifest_sha256=sha(C/'candidate.json'),revision_id=rev['revision_id'],revision_sha256=rev['revision_sha256']);f['files']={n:sha(code/n) for n in f['files']};put(A/'artifacts/design/freeze.json',f)
m=json.loads((A/'실험/manifest.json').read_text());m['design']['code_isolation']['candidates'][0].update(f['binding'],runner_sha256=sha(R/'06_TOOLS/EXPERIMENTS/adr_1086/contracts.py'));m['design']['success_criteria'].append('Actual request journal SELECT count incl evidence spans: batch2, exact row/text equivalence, corrupt text rejected, selective ID index plan; prior1-call proxy is not1SQL.');put(A/'실험/manifest.json',m)
