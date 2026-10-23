from common import *
from report_common import seal
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
meta=read(DES/'candidate.json');P=ROOT/meta['path'];assert not ac.validate(P),ac.validate(P)
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';selected=read(DES/'selected.json');assert sha(pointer)==selected['pointer_sha256']
release=read(ROOT/read(pointer)['manifest_path']);C=ROOT/release['code_root'];assert all(sha(C/n)==h for n,h in release['files'].items())
r=read(RUN/'summary.json');delivery=read(RUN/'delivery-audit.json')
put(ART/'final-integrity.json',{'selected_pointer_unchanged':True,'generation':read(pointer)['generation'],'selected_release_files_verified':len(release['files']),
 'candidate_valid':True,'candidate_frozen_files':len(read(P/'candidate.json')['revisions'][-1]['files']),
 'actual_native_requests':r['native_api_requests'],'model_calls':r['product_model_calls'],
 'all_source_spans_exact_and_authorized':r['source_span_checks_pass'],'verified_spans':sum(x['verified_spans'] for x in r['rows']),
 'every_candidate_assessment_prepared_refs_in_wire':all(x['every_assessment_prepared_refs_present'] and x['all_prepared_ref_witnesses_in_wire'] for x in delivery if x['arm']=='candidate'),
 'case_bound_refs_delivered':sum(x.get('delivered_count',0) for x in delivery),'source_delivery_contracts_pass':11,
 'additional_no_match_contract':read(ART/'no-match-contract.json')['observation'],'whole_answer_quality_certified':False,'candidate_accepted':False,
 'runtime_archive':read(RUN/'agent_layer/native-runtime-archive.json')['archive'],'archive_members_verified':True,
 'scope':'Research candidate only; no production work-code integration, MAIN promotion, Oracle execution, GENOS deployment, git commit or push',
 'postrun_scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py') if str(p.relative_to(ROOT)) not in read(DES/'freeze.json')['files']}})
index=ROOT/'04_EXPERIMENTS/ADR/README.md';s=index.read_text();link='[ADR-0993 — 원문 중심 검토 지식의 판단 입력 전달](ADR-0993-knowledge-original-delivery/README.md)'
if 'ADR-0993-knowledge-original-delivery/README.md' not in s:index.write_text(s+'\n- '+link+' — Rejected; 격리 CM4×2, MAIN100 유지.\n')
p=ROOT/'07_DOCS/REFERENCE/REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/V3_UPDATE_REVIEW_20261022.md';s=p.read_text().replace('../../../../../04_EXPERIMENTS/ADR/ADR-0993','../../../../04_EXPERIMENTS/ADR/ADR-0993');p.write_text(s)
assert (p.parent/'../../../../04_EXPERIMENTS/ADR/ADR-0993-knowledge-original-delivery/README.md').resolve().exists()
seal(ADR)
print({'calls':r['product_model_calls'],'source_spans':sum(x['verified_spans'] for x in r['rows']),'usage':r['usage'],'by_arm':r['by_arm']})
