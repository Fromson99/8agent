from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0845/terminal/snapshot/02_BACKEND'
p=S/'semantic_runtime/legal_agent/source_handoff.py';t=p.read_text();start=t.index('        old=child.db.execute');end=t.index('        return envelope',start)
t=t[:start]+'''        with child.transaction():
            old=child.db.execute("SELECT payload_json,payload_hash FROM source_handoff_export WHERE singleton=1").fetchone()
            if old:
                if digest(json.loads(old[0]))!=old[1] or json.loads(old[0])!=envelope:raise ContractError('source publication changed')
                if child.run()['status']!='COMPLETED' or child.run()['phase']!='END':raise ContractError('source publication terminal changed')
            else:
                if child.run()['status']!='RUNNING':raise ContractError('source handoff cannot publish failed work')
                child.db.execute('INSERT INTO source_handoff_export VALUES(1,?,?)',(encoded(envelope),digest(envelope)))
                child.event('SOURCE_HANDOFF_PUBLISHED',{'goal_id':result['goal_id'],'revision':result['revision'],
                    'envelope_hash':digest(envelope),'legal_answer_accepted':False})
                child.db.execute("UPDATE run SET status='COMPLETED',phase='END' WHERE singleton=1")
'''+t[end:]
t=t.replace("    if envelope.get('kind')!='SOURCE_HANDOFF'", "    if child.run()['status']!='COMPLETED' or child.run()['phase']!='END':raise ContractError('source work is not complete')\n    if envelope.get('kind')!='SOURCE_HANDOFF'")
t+='''

def schema():
    """Internal SELECT terminal; model output remains the three-field action wire."""
    def obj(**props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
    return obj(status={'const':'sources_returned'},terminal={'const':'SOURCE_HANDOFF'},next_action={'const':'DONE'},
        needs_fulltext={'const':False},final_ids={'const':[]},selected_originals={'const':[]},
        selected_evidence={'type':'array','items':{'type':'object'}},investigation_state={'type':'object'},
        source_return=obj(schema_version={'const':'source-investigation-v1'},read_evidence_ids={'type':'array','items':{'type':'string'},'uniqueItems':True},
            reason={'type':'string'},stop_reason={'type':['string','null']},acquisition={'type':'object'},research_tasks={'type':'object'},
            semantic_quality_certified={'const':False},absence_proven={'const':False}))
''';p.write_text(t)
p=S/'semantic_runtime/legal_agent/memory_rag.py';t=p.read_text().replace("    def schema(self,stage):\n        if stage=='INTENT':", "    def schema(self,stage):\n        from .source_handoff import enabled as source_mode,schema as source_schema\n        if stage=='SELECT' and source_mode():return source_schema()\n        if stage=='INTENT':");p.write_text(t)
