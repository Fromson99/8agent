"""Explicit frozen candidate injection into the existing reference-resolution CLI."""
import hashlib,json,pathlib,sys
ROOT=next(p for p in pathlib.Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0525/repaired'
m=json.loads((C/'candidate.json').read_text());revision=m['revisions'][-1]
rpath=C/'revisions'/revision['revision_id'];frozen=revision
for row in frozen['files']:
 p=ROOT/row['frozen_path']
 if hashlib.sha256(p.read_bytes()).hexdigest()!=row['snapshot_sha256']:raise SystemExit('Frozen code drift: '+str(p))
sys.path.insert(0,str(rpath/'snapshot/02_BACKEND'))
if __name__=='__main__':
 from lawrag.pipeline.reference_resolution import main
 raise SystemExit(main(sys.argv[1:]))
