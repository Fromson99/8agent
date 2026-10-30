from common import *
f=read(DES/'freeze.json');report=ROOT/'09_ARTIFACTS/AUDITS/20261028-response-contract-recovery/수정과_재시험결과.txt';put(ART/'report.json',{'path':str(report.relative_to(ROOT)),'sha256':sha(report)})
assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items());assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
# Final evidence files are registered only after they stop changing. Validation logs
# are written separately afterwards; never hash a log and then overwrite it.
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=ART/'manifest.json'];paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path'],report]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Contained original implementation,263contracts,stored actual source proof,regression and final report','contains_raw_prompts_and_outputs':bool('raw' in p.parts or 'canonical' in p.parts or p.suffix in ('.log','.sqlite','.gz'))} for p in paths];put(ART/'manifest.json',a);print('Registered stable artifacts;464files and MAIN112 pointer verified')
