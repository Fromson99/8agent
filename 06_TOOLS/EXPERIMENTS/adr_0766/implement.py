"""Edit only the reserved candidate; production/selected releases stay unchanged."""
from pathlib import Path
import json, subprocess
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0766/narrative'
S=C/'snapshot'
def change(name,old,new):
    p=S/name;s=p.read_text();assert old in s,(name,old[:100]);p.write_text(s.replace(old,new))
B='02_BACKEND/semantic_runtime/legal_agent/'
newfile=B+'narrative_answer.py'
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',newfile,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
change(B+'workflow_tiers_policy.py',"'request_entry_policy':'legacy'}", "'request_entry_policy':'legacy', 'answer_presentation':'structured'}")
change(B+'workflow_tiers_policy.py',"    from .law_candidates import validate_policy", "    if p['answer_presentation'] not in ('structured','grounded-narrative-v1'):raise ContractError('unknown answer presentation')\n    from .law_candidates import validate_policy")
change(B+'workflow_tiers_policy.py',"'candidate_navigation', 'request_entry_policy'}:","'candidate_navigation', 'request_entry_policy', 'answer_presentation'}:")
p=S/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=json.loads(p.read_text());v['answer_presentation']='grounded-narrative-v1';p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
change(B+'completion_contracts.py',"    if sections:\n        if [c for s in sections", "    if plan.get('presentation') == 'grounded-narrative-v1':\n        from .narrative_answer import render as render_narrative\n        text = render_narrative(assessment, plan)\n    elif sections:\n        if [c for s in sections")
change(B+'completion_execution.py',"        contract=cc.version(profile)\n", "        contract=cc.version(profile)\n        from . import narrative_answer as narrative\n        rich = narrative.enabled(profile)\n")
old='''            # Preserve the seventh durable stage with no extra generative call.
            # Accepted wording is already produced in ASSESS; formatting is deterministic.
            plan = cc.default_plan(assessment, format, selection.get('issues'))
            result = cc.compose(assessment, plan)
            cc.verify_composition(assessment, result)'''
new='''            # The source-backed judgment remains immutable; presentation is separate.
            if rich:
                wire = narrative.input_data(utterance, assessment, sources, format)
                value = self.invoke(narrative.PROMPT, wire,
                    narrative.schema(wire['answer_claim_ids']), narrative.PHASE)
                plan = narrative.plan(assessment, value)
            else:
                plan = cc.default_plan(assessment, format, selection.get('issues'))
            result = cc.compose(assessment, plan)
            cc.verify_composition(assessment, result)
            if rich:
                from .answer_stream import current_sink
                sink = current_sink()
                if sink is not None and getattr(sink, 'started', False):
                    emitted = getattr(sink, 'text', '')
                    if not result['text'].startswith(emitted):
                        raise ContractError('final narrative differs from streamed paragraphs')
                    if result['text'][len(emitted):]:sink(result['text'][len(emitted):])'''
change(B+'completion_execution.py',old,new)
change(B+'completion_execution.py',"'text_hash': digest(result['text']), 'model_call': False}","'text_hash': digest(result['text']), 'model_call': rich,\n                'presentation': narrative.VERSION if rich else 'structured'}")
change(B+'completion_execution.py',"self.invoke(ASSESS_PROMPT+('\\n'+content_impl.PROMPT if modern else ''),", "self.invoke(ASSESS_PROMPT+('\\n'+content_impl.PROMPT if modern else '')+('\\n'+narrative.ASSESS_GUIDANCE if rich else ''),")
# The assessment cache is scoped to policy as well as sources and user request.
change(B+'completion_execution.py',"basis = {'contract':contract,'request_hash'", "basis = {'contract':contract,'answer_presentation':profile.get('answer_presentation','structured'),'request_hash'")
change(B+'bounded_source_session.py',"        value = gateway.generate(native_phase, view, 'BoundedSourceDecision')", "        from . import narrative_answer as narrative\n        rich = narrative.enabled(profile) and phase == narrative.PHASE\n        if rich:\n            # Coverage and references are checked in the gateway before accepting JSON.\n            prior_checked = gateway.protocol.validator\n            def check_answer(value):\n                narrative.checked(value, data['answer_claim_ids'])\n                if prior_checked is not None:prior_checked(value)\n            gateway.protocol.validator = check_answer\n        value = gateway.generate(native_phase, view, narrative.SCHEMA if rich else 'BoundedSourceDecision')")
change(B+'gateway.py',"        sink = current_sink()\n        streaming =", "        sink = current_sink()\n        from . import narrative_answer as narrative\n        rich = (narrative.enabled(self.profile) and schema_name == narrative.SCHEMA\n                and view.get('source_stage') == narrative.PHASE\n                and view.get('answer_presentation') == narrative.VERSION)\n        def new_projection():\n            return narrative.ParagraphStream(sink, view['answer_claim_ids']) if rich else DraftText(sink)\n        streaming =")
change(B+'gateway.py',"and phase == 'compose' and schema_name == 'Draft'", "and phase == 'compose' and (schema_name == 'Draft' or rich)")
change(B+'gateway.py',"projection = DraftText(sink) if streaming else None", "projection = new_projection() if streaming else None")
change(B+'gateway.py',"projection = DraftText(sink)\n", "projection = new_projection()\n")
change(B+'gateway.py',"repair_scheduled = repairs < self.profile['max_schema_repairs']", "repair_scheduled = repairs < self.profile['max_schema_repairs'] and not (rich and projection and projection.emitted)")
change(B+'answer_stream.py',"        send.started = True\n", "        send.started = True\n        send.text += text\n")
change(B+'answer_stream.py',"    token = _sink.set(send)\n", "    send.text = ''\n    token = _sink.set(send)\n")
# Expose the distinction between accepted judgment and generated presentation.
change(B+'unified_runtime.py',"text_integrity='ACCEPTED_CLAIMS_RENDERED',citation_integrity='ORIGINAL_SPANS')", "text_integrity=('SOURCE_BOUND_NARRATIVE' if composition.get('composition_plan',{}).get('presentation') == 'grounded-narrative-v1' else 'ACCEPTED_CLAIMS_RENDERED'),citation_integrity='ORIGINAL_SPANS')\n        if composition.get('composition_plan',{}).get('presentation'):\n            meta['answer_presentation']={'version':composition['composition_plan']['presentation'],\n                'streaming':'validated-paragraphs-during-generation', 'semantic_quality_certified':False}")
print('Guarded native presentation and internal model paragraph stream implemented in candidate only.')
