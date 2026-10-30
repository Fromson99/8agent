from common import *
s=Path(__file__).with_name('report.py').read_text()
old="read(ART/'run-001/baseline/cm-023/first-assess-originals.json')==read(ART/'run-001/semantic/cm-023/first-assess-originals.json') if len(results)==2 else None"
s=s.replace(old,"read(ART/'post-selection-input-check.json')['same_first_assess_originals'] if len(results)==2 else None")
s=s.replace("'new_evaluator_calls':0,'semantic_evaluation'", "'new_evaluator_calls':0,'prefix_repair_observed':True,'causal_timing_claim':False,'semantic_evaluation'")
Path(__file__).with_name('report_final.py').write_text(s)
