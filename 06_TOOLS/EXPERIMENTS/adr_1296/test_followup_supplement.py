"""Exercise the existing native follow-up fixture beyond obsolete wording.

Parent1294 keeps the failure at the literal 'same conversation' phrase. Here
only that sentence-level assertion is replaced: unresolved reasons must remain
nonempty. All same-case, source reuse, claims, revision, and duplicate checks in
the original native test remain intact. No product/model reply is modified.
"""
import importlib.util,inspect
from pathlib import Path
R=Path('/home/jin/8-AGENT')
spec=importlib.util.spec_from_file_location('recovery_original_1274',R/'06_TOOLS/EXPERIMENTS/adr_1274/test_recovery.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
source=inspect.getsource(original.test_exhausted_review_delivers_sources_then_fact_followup_in_same_case)
old="assert any('같은 대화' in s['reason'] for s in result['answer']['unresolved'])"
new="assert result['answer']['unresolved'] and all(isinstance(s.get('reason'),str) and s['reason'].strip() for s in result['answer']['unresolved'])"
assert source.count(old)==1
source=source.replace(old,new).replace('def test_exhausted_review_delivers_sources_then_fact_followup_in_same_case','def test_native_same_case_followup_with_semantic_unresolved_check',1)
ns=dict(original.__dict__);exec(compile(source,__file__,'exec'),ns)
test_native_same_case_followup_with_semantic_unresolved_check=ns['test_native_same_case_followup_with_semantic_unresolved_check']
