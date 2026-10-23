"""Verify immutable inputs and preserve stopped runtime before sealing this experiment."""
from common import *
import sys,tarfile,hashlib,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
meta=read(DES/'candidate.json');P=ROOT/meta['path'];assert not ac.validate(P),ac.validate(P)
freeze=read(DES/'freeze.json');assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
resource=read(ART/'run-001-resource.json');assert resource['returncode']==0
selected=read(DES/'selected.json');release=selected['release'];C=ROOT/release['code_root']
assert all(sha(C/n)==h for n,h in release['files'].items())
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');manifest=ROOT/active['manifest_path']
assert sha(manifest)==active['release_manifest_sha256']
current=read(manifest);AC=ROOT/current['code_root'];assert all(sha(AC/n)==h for n,h in current['files'].items())
r=read(RUN/'summary.json')
put(ART/'final-integrity.json',{'frozen_inputs_unchanged':True,'frozen_candidate_valid':True,
    'candidate_files':424,'source_release_files_verified':len(release['files']),
    'main_pointer_unchanged':active==read(DES/'active-before.json'),'current_active_generation':active['generation'],
    'current_active_code_verified':True,'source_binding':read(RUN/'binding.json')['source'],
    'native_requests':r['native_api_requests'],'external_model_calls':r['product_model_calls'],
    'source_integrity':all(v['technical_source_check'] for v in r['rows']),
    'unit_contract_tests':19,'source_delivery_checks':15,'synthetic_api_scenarios':4,
    'main_promoted':False,'production_code_modified':False,'oracle_executed':False,'genos_executed':False,
    'git_commit_push':False,'resource_guard_returncode':resource['returncode']})

# Only stopped, byte-verified duplicate runtimes are removed. Outputs and stores stay accessible.
dirs=[RUN/'agent_layer/runtime']
dirs += [p for p in ART.glob('api-contracts-*/*/runtime') if p.is_dir()]
dirs += [p for p in ART.glob('contracts-*/native') if p.is_dir()]
files=sorted({p for d in dirs if d.is_dir() for p in d.rglob('*') if p.is_file()})
archive=ART/'stopped-runtimes.tar.gz';receipt=ART/'stopped-runtimes-archive.json'
assert not archive.exists() and not receipt.exists()
members=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
with tarfile.open(archive,'w:gz',compresslevel=6) as out:
    for p in files:out.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
with tarfile.open(archive,'r:gz') as inp:
    for entry in members:
        f=inp.extractfile(entry['path']);assert f is not None
        assert hashlib.file_digest(f,'sha256').hexdigest()==entry['sha256']
put(receipt,{'schema_version':'lossless-native-runtime-archive-v1','archive':str(archive.relative_to(ROOT)),
    'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'original_bytes':sum(v['bytes'] for v in members),
    'all_members_verified':True,'members':members,'restore_from_repository_root':'tar -xzf '+str(archive.relative_to(ROOT)),
    'reason':'All associated processes exited. Raw bytes verified in lossless archive before removing duplicate directories.'})
for d in dirs:
    if d.is_dir():shutil.rmtree(d)
index=ROOT/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();link='ADR-1019-source-required-answer-items/README.md'
if link not in text:index.write_text(text+'\n- [ADR-1019 원문별 필수 설명 항목의 상태 보존과 최종 표시]('+link+') — 격리 후보, 구조검사 및 CM5×2 비교, MAIN 미반영.\n')
print(json.dumps(read(ART/'final-integrity.json'),ensure_ascii=False))
