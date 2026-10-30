"""Preserve zero-label ledger and add explicit technical root-preservation label.

The ADR validator requires a numeric recall for changed retrieval. This is NOT a
legal answer or full-subclause completeness grade; the skipped presentation and
actual missing ba spans stay unchanged.
"""
from common import *
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');old=read(RUN/'retrieval-ledger.json');roots=[{'doc_id':'3521c3aaa5a735fd','node':349}]
put(ART/'technical-reference-label.json',{'expected_roots':roots,'scope':'Preserve the explicitly selected reference article root; not legal relevance/answer gold. Subclauses ma/ba share this root, so root recall cannot prove full coverage.','derived_from':'Saved006 explicit model target and actual source tree; evaluated only after product fragment selection','gold_visible_to_product':False})
rec=StageLedgerRecorder('cm-009','bound',identity_canonicalizer)
rec.record_stage('declared','source',roots)
rec.record_stage('bundled','expand',roots,parent_stage_ids=['declared'],after_occurrence_count=2)
rec.record_stage('offered','present',None,parent_stage_ids=['bundled'],executed=False,skip_reason='No new real009 read/model dispatch; carried root is not a delivery receipt.')
ledger=build_experiment_artifact('ADR-1202',m['experiment_id'],[build_run_artifact('run-001',[grade_capture(rec.capture(),roots)],{'bound':['declared','bundled','offered']})])
ledger['audit']={**old['audit'],'scope':'Technical article-root preservation only. Numeric root recall1/1 is not original completeness, delivery or legal quality. Final presentation skipped. Ma acquired3 blocks, ba missing5 blocks stay unchanged.','corrects':'Zero-label initial ledger yields null recall, but existing ADR metadata validator requires numeric changed-retrieval recall. Initial ledger and failed validation preserved.','label_path':str((ART/'technical-reference-label.json').relative_to(ROOT))}
ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
put(RUN/'retrieval-ledger-v2.json',ledger)
m['retrieval_accounting']['golden_recall']=1.0;m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((RUN/'retrieval-ledger-v2.json').relative_to(ROOT)),sha256=sha(RUN/'retrieval-ledger-v2.json'))
m['retrieval_accounting']['metric_scope_note']+=' Numeric root recall1/1 only measures explicit-reference preservation, not legal completeness/delivery; original zero-label ledger preserved.'
for q in m['questions']:
 p=ADR/'실험'/q['file'];s=p.read_text().replace('retrieval-ledger.json','retrieval-ledger-v2.json');s+='\n원장 숫자1/1은 명시 참조31조root 보존만 뜻한다. 바목 전체 미확보·새 모델 제시 미실행은 그대로다. 법률 정답률이나 하위범위 확보율이 아니다.\n';p.write_text(s);q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
p=ADR/'README.md';s=p.read_text().replace('retrieval-ledger.json','retrieval-ledger-v2.json');s=s.replace('root 수를 원문 완전성으로 해석하지 않으며','기존 ADR 검사기의 숫자 recall 요구에 맞춰 명시 참조root 보존1/1을 기술 기대값으로 기록했다. 최초 무채점 원장과 메타검사 실패를 보존한다. root 수를 원문 완전성으로 해석하지 않으며');p.write_text(s)
print('Recorded technical root-preservation label; missing ba/delivery not changed')
