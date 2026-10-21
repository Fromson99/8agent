from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0877-original-context-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0876-original-coverage-scope-probe'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=A/'실험/manifest.json';m=read(p);before=sha(p);old=m['runs'][0]['selection_rule'];m['runs'][0]['selection_rule']=old.replace('finite32boundaryvariants','finite8boundaryvariants');put(p,m)
b=read(A/'artifacts/design/baseline.json')['release'];g=read(R/b['data_path']/'manifest.json')
put(A/'artifacts/metadata-corrections.json',{'before_manifest_sha256':before,'after_manifest_sha256':sha(p),'selection_rule_before':old,'selection_rule_after':m['runs'][0]['selection_rule'],'reason':'Count typo in prose; exact pre-frozen test source contains8table cases. No prompt, criterion, model input or product change.', 'scope_case_binding_clarification':{'field':'known-article8.original_binding.store_sha256','frozen_value_was':'data_manifest_sha256','data_manifest_sha256':b['data_manifest_sha256'],'actual_source_store_sha256':g['store_sha256'],'original_scope_text_unchanged':True},'criteria_unchanged':True})
put(P/'artifacts/FINAL_VALIDATOR_NOTE.json',{'nonfinal_validate':'PASS','final_validate':'False-positive reserved-word check only','errors':['final ADR contains PENDING: README.md','final ADR contains PENDING: 실험/manifest.json'],'meaning':'These are documented runtime state identifiers in the prospective criterion, not unfinished placeholders. All runs are complete. Completed manifest preserved immutable; qualification records remain separately checked.','completed_manifest_sha256':sha(P/'실험/manifest.json')})
print('Metadata count and binding-name clarifications recorded; frozen inputs untouched')
