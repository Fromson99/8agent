from common import *
import sys, shutil
sys.path.insert(0, str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
meta=read(DES/'candidate.json'); P=ROOT/meta['path']; S=P/'snapshot'/meta['selected_code_relative']
base=S/'02_BACKEND/semantic_runtime/legal_agent'

def change(name, before, after):
    p=base/name; text=p.read_text()
    if after in text:
        return
    assert text.count(before)==1, (name, before[:90], text.count(before))
    p.write_text(text.replace(before, after))

target=base/'required_items.py'
if not target.exists():
    shutil.copyfile(Path(__file__).with_name('required_items.py'),target)
    ac.register_file(P,str(target.relative_to(P/'snapshot')),upstream_state='absent')
else:
    assert sha(target)==sha(Path(__file__).with_name('required_items.py'))
change('unified_rag.py', "'knowledge_bridge.py','knowledge_delivery.py'", "'knowledge_bridge.py','knowledge_delivery.py','required_items.py'")
change('unified_rag.py', '        system += assessment_prompt(self, phase)',
       '        system += assessment_prompt(self, phase)\n        from . import required_items\n        data, schema, required_prompt = required_items.model_input(self, data, schema, phase)\n        system += required_prompt')
change('unified_rag.py', '        if delivery:self.s.work.event(\'KNOWLEDGE_INPUT_RETURNED\', delivery)\n        return result',
       '        if delivery:self.s.work.event(\'KNOWLEDGE_INPUT_RETURNED\', delivery)\n        return required_items.capture(self, result, phase)')
change('completion_execution.py', '        options = cc.evidence_options(sources)',
       '        options = cc.evidence_options(sources)\n        from . import required_items\n        required_context = required_items.prepare(self, selection, sources, utterance)')
change('completion_execution.py', "'previous_assessment_hash':digest(previous_assessments),",
       "'previous_assessment_hash':digest(previous_assessments),\n            'required_review_context': digest(required_context),")
change('completion_execution.py', '                if not cached:decision_journal.accept(attempt,value)',
       '                result = required_items.accept(self, result, sources)\n                if not cached:decision_journal.accept(attempt,value)')
needle="                if candidate is None:\n                    self.s.work.event('COMPLETION_ASSESSMENT_UNNORMALIZABLE', {'reason': changes})"
replacement="""                if candidate is None and required_context and sources:
                    # Preserve original rejection and end as an explicit partial result.
                    # No malformed output becomes a claim, no semantic repair is invented.
                    self.s.work.event('REQUIRED_REVIEW_ASSESSMENT_UNRESOLVED', {'reason': changes, 'original_error': str(exc)})
                    self.required_review_proposal = {}
                    result = {'claims': [], 'gaps': [], 'disposition': 'LIMITED_ANSWER',
                        'issue_assessments': [{'issue_id': i['id'], 'status': 'INSUFFICIENT',
                            'reason': '판단 응답을 확정하지 못했습니다.'} for i in self.issues],
                        'completion_contract': contract, 'model_proposal': {'failed_output_preserved_in_journal': True}}
                    result = required_items.accept(self, result, sources)
                    notes.append('REQUIRED_REVIEW_UNRESOLVED'); normalized = True
                    break
"""+needle
change('completion_execution.py',needle,replacement)
change('completion_contracts.py', "    schema['properties'].update(extra)",
       "    schema['properties']['required_review'] = {'type': 'object'}\n    schema['properties'].update(extra)")
change('completion_contracts.py', "    return text\n\n\ndef _escape(value):",
       "    if assessment.get('required_review'):\n        from .required_items import render as render_required\n        text += '\\n\\n' + render_required(assessment['required_review'])\n    return text\n\n\ndef _escape(value):")
change('completion_contracts.py', "            'text': render(assessment, plan), 'claims': deepcopy(assessment['claims']),",
       "            **({'required_review': deepcopy(assessment['required_review'])} if 'required_review' in assessment else {}),\n            'text': render(assessment, plan), 'claims': deepcopy(assessment['claims']),")
change('completion_contracts.py', "            or answer.get('source_excerpt_reply') != assessment.get('source_excerpt_reply')",
       "            or answer.get('required_review') != assessment.get('required_review')\n            or answer.get('source_excerpt_reply') != assessment.get('source_excerpt_reply')")
change('knowledge_bridge.py', "    return {'schema_version': 'legal-knowledge-usage-v1', 'model_calls_added': 0,",
       "    from .required_items import publication_metadata\n    return {'schema_version': 'legal-knowledge-usage-v1', 'model_calls_added': 0,\n            **publication_metadata(work),")
change('knowledge_bridge.py', "    with current[0]() as service:\n        service.limit_deadline(time.monotonic()+1.5)",
       "    if usage.get('required_review'):\n        from .required_items import validate_sources, validate_receipt\n        receipt = usage['required_review']; validate_receipt(receipt)\n        if receipt['binding']['generation'] != store.manifest['generation_id'] or receipt['binding']['store_sha256'] != store.manifest['store_sha256']:\n            raise KnowledgeError('KNOWLEDGE_SOURCE_BINDING', '필수 검토 원문 세대가 다릅니다.', 409)\n        validate_sources(receipt['rows'], store, current[1]['document_ids'])\n    with current[0]() as service:\n        service.limit_deadline(time.monotonic()+1.5)")
change('unified_publication.py', "            verify_composition(assessment,composition)",
       "            verify_composition(assessment,composition)\n            if assessment.get('required_review'):\n                from .required_items import validate_receipt\n                review = assessment['required_review']; validate_receipt(review)\n                if meta.get('legal_knowledge', {}).get('required_review') != review:\n                    raise ContractError('required review public metadata differs from accepted assessment')\n                if not {r['document_id'] for item in review['rows'] for r in item['source_refs']} <= (set(state['document_ids']) & set(principal['document_ids'])):\n                    raise ContractError('required review source permission changed')\n                for item in review['rows']:\n                    for claim in item['claims']:verify_span_claim(claim,list(originals.values()))")

# Bind new executable source into every existing engine which consumes this path.
config=read(S/'00_SYSTEM/PIPELINE.json')
for entry in config['engines'].values():
    path=S/entry['manifest']; engine=read(path)
    if '02_BACKEND/semantic_runtime/legal_agent/knowledge_delivery.py' in engine['files']:
        engine['files']['02_BACKEND/semantic_runtime/legal_agent/required_items.py']=sha(target)
        put(path,engine)

print('IMPLEMENTED isolated source obligations; live/model calls 0; production unchanged')
