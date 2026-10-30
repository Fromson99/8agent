from common import *
S=ROOT/read(DES/'candidate.json')['snapshot'];L=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=L/name;s=p.read_text();assert old in s,name;p.write_text(s.replace(old,new,1))
edit('final_original_review.py', '''row=repo.db.execute("SELECT payload_json FROM event WHERE kind='FINAL_ORIGINAL_REVIEW_FINISHED' AND json_extract(journal_text(payload_json),'$.input_hash')=? ORDER BY seq DESC LIMIT 1",(key,)).fetchone()
    if row:
        saved=json.loads(row[0]);verify(saved,data);return saved
    started=repo.db.execute("SELECT 1 FROM event WHERE kind='FINAL_ORIGINAL_REVIEW_STARTED' AND json_extract(journal_text(payload_json),'$.input_hash')=? LIMIT 1",(key,)).fetchone()''', '''def events(kind):
        for raw,h in repo.db.execute('SELECT payload_json,payload_hash FROM event WHERE kind=? ORDER BY seq DESC',(kind,)):
            v=json.loads(raw)
            if digest(v)!=h:raise ContractError('review event hash changed')
            if v.get('input_hash')==key:yield v
    saved=next(events('FINAL_ORIGINAL_REVIEW_FINISHED'),None)
    if saved is not None:verify(saved,data);return saved
    started=next(events('FINAL_ORIGINAL_REVIEW_STARTED'),None)''')
edit('final_original_review.py','except (ProposalError,ValidationError,TransportError,BudgetExhausted) as exc:', 'except (ProposalError,ValidationError,TransportError,BudgetExhausted,TimeoutError) as exc:')
edit('workflow_tiers_policy.py',"'answer_presentation':'structured'}","'answer_presentation':'structured', 'final_original_review_policy':'disabled'}")
edit('workflow_tiers_policy.py',"if type(p['final_review_enabled']) is not bool: raise ContractError('final_review_enabled must be bool')", "if type(p['final_review_enabled']) is not bool: raise ContractError('final_review_enabled must be bool')\n    if p['final_original_review_policy'] not in ('disabled','advisory-v1'):raise ContractError('invalid final original review policy')")
edit('workflow_tiers_policy.py',"'request_entry_policy', 'answer_presentation'}:","'request_entry_policy', 'answer_presentation', 'final_original_review_policy'}:")
edit('completion_execution.py',"""            self.s.work.event('FINAL_REVIEW_SKIPPED', {'stage': stage, 'policy': 'disabled',
                'structural_render_verified': True, 'claim_review_status': 'UNREVIEWED',
                'quality_certified': False})""", """            from . import final_original_review as original_review
            if original_review.enabled(profile):
                result['final_original_review']=original_review.run(self,utterance,assessment,result,sources)
            else:
                self.s.work.event('FINAL_REVIEW_SKIPPED', {'stage': stage, 'policy': 'disabled',
                    'structural_render_verified': True, 'claim_review_status': 'UNREVIEWED',
                    'quality_certified': False})""")
edit('completion_contracts.py',"extra.update(composition_plan={'type': 'object'}, assessment_hash={'type': 'string'})", "extra.update(composition_plan={'type': 'object'}, assessment_hash={'type': 'string'})\n        schema['properties']['final_original_review']={'type':'object'}")
edit('bounded_source_session.py',"phase in ('memory-assess','memory-assess-repair','memory-compose','memory-compose-repair')", "phase in ('memory-assess','memory-assess-repair','memory-compose','memory-compose-repair','memory-final-original-review')")
edit('bounded_source_session.py',"if output.owner_for(phase) != 'gateway':", "if output.owner_for(phase) != 'gateway' or phase == 'memory-final-original-review':")
edit('unified_runtime.py',"    routing=result.get('request_routing')", "    from .final_original_review import metadata as review_metadata\n    review_composition=parts.get('COMPOSE',{}).get('payload',{})\n    if review_composition.get('final_original_review') is not None:\n        meta['final_original_review']=review_composition['final_original_review']\n    routing=result.get('request_routing')")
edit('unified_runtime.py',"'final_review_policy':'disabled','final_review_status':'SKIPPED',\n                'claim_review_status':'UNREVIEWED'", "**review_metadata(review_composition)")
edit('unified_publication.py',"            expected_text=composition['text']", """            from . import final_original_review as original_review
            receipt=composition.get('final_original_review')
            if meta.get('final_original_review')!=receipt:raise ContractError('published review differs from committed review')
            if receipt is not None:
                chosen=[s for s in originals.values() if s['source_id'] in selection['final_ids']]
                original_review.verify(receipt,original_review.input_data(
                    assessment.get('assessment_basis',{}).get('request_text',state['task']),assessment,composition,chosen))
            expected_review=original_review.metadata(composition)
            if any(result['answer']['provider_receipt'].get(k)!=v for k,v in expected_review.items()):
                raise ContractError('published review status differs from committed review')
            expected_text=composition['text']""")
# The exact current request text is bound in the review receipt as part of input_data;
# publication verifies with the stored question instead of reconstructing utterance context.
edit('final_original_review.py',"'scope':data['scope'],'quality_certified':False", "'scope':data['scope'],'question':data['question'],'quality_certified':False")
edit('unified_publication.py',"assessment.get('assessment_basis',{}).get('request_text',state['task']),assessment,composition,chosen)", "receipt['question'],assessment,composition,chosen)")
p=S/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=read(p);v['final_original_review_policy']='advisory-v1';p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ROOT/read(DES/'candidate.json')['root'];new='02_BACKEND/semantic_runtime/legal_agent/final_original_review.py'
ac.register_file(C,new,upstream_state='absent')
for e in read(S/'00_SYSTEM/PIPELINE.json')['engines'].values():
 p=S/e['manifest'];v=read(p)
 if '02_BACKEND/semantic_runtime/legal_agent/completion_execution.py' in v.get('files',{}):v['files'][new]=sha(S/new);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('candidate reviewer module and native COMPOSE/publication hooks implemented')
