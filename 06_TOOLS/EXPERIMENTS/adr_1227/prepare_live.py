from pathlib import Path
import json,sys,shutil
ROOT=Path(__file__).resolve().parents[3];T=ROOT/'06_TOOLS/EXPERIMENTS/adr_1228';T.mkdir(exist_ok=True)
old=ROOT/'06_TOOLS/EXPERIMENTS/adr_1226'
for n in ('common.py','resource_guard.py','live.py','freeze.py'):
 s=(old/n).read_text().replace('ADR-1226-main122-authoring-revalidation','ADR-1228-source-first-authoring-live').replace('ADR1226-only','ADR1228-only')
 if n=='freeze.py':s=s.replace("candidate_id='main122'","candidate_id='source-first'").replace("arm_id='main122'","arm_id='source-first'").replace('run-001/MAIN122','run-001/source-first').replace('NORMALIZE 다음 ACCUMULATE.','NORMALIZE → SOURCE_ANALYSIS(관찰/기존지식 비공개) → ACCUMULATE.').replace('MAIN122에서 새 정규화부터 두 차례 누적까지','원문 독립 분석 후보에서 새 정규화부터 두 차례 누적까지')
 if n=='live.py':
  s=s.replace('phase=phase,timeout_seconds=remaining',"phase=stage_receipts[-1]['phase'],timeout_seconds=remaining")
  s=s.replace("'phase':phase,'prompt':prompt", "'phase':('source-'+phase.rsplit('-',1)[-1] if context.get('operation')=='SOURCE_ANALYSIS' else phase),'prompt':prompt")
  s=s.replace("row={'phase':phase,'attempt':", "row={'phase':('source-'+phase.rsplit('-',1)[-1] if context.get('operation')=='SOURCE_ANALYSIS' else phase),'attempt':")
  s=s.replace("print('STAGE_START',phase", "print('STAGE_START',row['phase']").replace("print('STAGE_RESPONSE',phase", "print('STAGE_RESPONSE',row['phase']")
  s=s.replace("for name in ('output_schema','accumulation_schema'):","for name in ('output_schema','accumulation_schema','source_schema'):")
  s=s.replace("schema=compiled[name]", "schema=compiled.get(name,{})")
  s=s.replace("schema=normalization_schema(w.load(raws[0]['bundle_id'])['raw'],compiled)","from semantic_runtime.ontology_work import recorded_fields\n    raw_value=w.load(raws[0]['bundle_id'])['raw']\n    schema=recorded_fields.request_schema(normalization_schema(raw_value,compiled),raw_value)")
  s=s.replace("   before=deepcopy(schema)","   if name=='source_schema':\n    from semantic_runtime.ontology_work import authoring_semantics as semantics\n    schema=semantics.source_schema(compiled,sources)\n   before=deepcopy(schema)")
 (T/n).write_text(s)
print(T)
