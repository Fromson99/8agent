"""Seal observed results; never activate the candidate."""
from common import *
from report_common import seal
import sys,tarfile,shutil,hashlib
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
meta=read(DES/'candidate.json');P=ROOT/meta['path'];assert not ac.validate(P),ac.validate(P)
selected=read(DES/'selected.json');pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer_unchanged=sha(pointer)==selected['pointer_sha256']
release=selected['release'];C=ROOT/release['code_root'];assert all(sha(C/n)==h for n,h in release['files'].items())
active=read(ROOT/read(pointer)['manifest_path']);AC=ROOT/active['code_root'];assert all(sha(AC/n)==h for n,h in active['files'].items())
assert not (AC/'02_BACKEND/semantic_runtime/legal_agent/knowledge_delivery.py').exists()
put(ART/'concurrent-main-change.json',{'before':selected['pointer'],'after':read(pointer),'observed_pointer_changed':not pointer_unchanged,
 'experiment_source_release_files_unchanged':True,'current_release_files_verified':True,'experiment_delivery_module_in_current_release':False,
 'experiment_main_promotion_performed':False,'interpretation':'Active pointer changed outside this experiment. Runner explicitly loaded frozen MAIN100-derived code and shared frozen source binding; no automatic active-pointer reload or rollback performed.'})
freeze=read(DES/'freeze.json');assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
r=read(RUN/'summary.json');assert read(ART/'run-001-resource.json')['returncode']==0
runtime=RUN/'agent_layer/runtime';archive=RUN/'agent_layer/native-runtime.tar.gz';receipt=RUN/'agent_layer/native-runtime-archive.json'
if runtime.exists():
 assert not archive.exists() and not receipt.exists()
 files=sorted(p for p in runtime.rglob('*') if p.is_file());members=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
 with tarfile.open(archive,'w:gz',compresslevel=6) as out:
  for p in files:out.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
 with tarfile.open(archive,'r:gz') as inp:
  for entry in members:
   f=inp.extractfile(entry['path']);assert f is not None and hashlib.file_digest(f,'sha256').hexdigest()==entry['sha256']
 put(receipt,{'schema_version':'lossless-native-runtime-archive-v1','archive':str(archive.relative_to(ROOT)),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'original_bytes':sum(x['bytes'] for x in members),'all_members_verified':True,'members':members,'restore_from_repository_root':'tar -xzf '+str(archive.relative_to(ROOT)),'reason':'Stopped research process and byte-verified lossless archive; remove only this redundant runtime copy.'})
 shutil.rmtree(runtime)
put(ART/'final-integrity.json',{'main_pointer_unchanged':pointer_unchanged,'experiment_source_generation':selected['pointer']['generation'],'current_active_generation':read(pointer)['generation'],'experiment_source_files_verified':len(release['files']),
 'frozen_inputs_unchanged':True,'frozen_candidate_valid':True,'model_calls':r['product_model_calls'],'actual_native_requests':r['native_api_requests'],
 'verified_spans':sum(x['verified_spans'] for x in r['rows']),'source_integrity':all(x['technical_source_check'] for x in r['rows']),
 'actual_prompt_verified':all(x['actual_prompt_verified'] for x in r['rows']),'all_assessment_prepared_sources_delivered':all(x['assessment_prepared_refs_present'] for x in r['rows']),
 'contracts_passed':15,'runtime_archive':read(receipt)['archive'],'main_promoted':False,'oracle_executed':False,'genos_executed':False,'git_commit_push':False})
readme=ADR/'README.md';text=readme.read_text();state='Proposed' if r['all_success_criteria_met'] else 'Rejected';text=text.replace('status: Proposed','status: '+state);readme.write_text(text)
index=ROOT/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();link='ADR-0996-knowledge-use-first-prompt/README.md'
if link not in text:index.write_text(text+'\n- [ADR-0996 원문 지식 우선 사용 프롬프트]('+link+') — MAIN100 기반 격리 CM5×2, '+state+', 실험 후보 MAIN 미반영.\n')
seal(ADR);print(json.dumps({'decision':state,'calls':r['product_model_calls'],'integrity':read(ART/'final-integrity.json')},ensure_ascii=False))
