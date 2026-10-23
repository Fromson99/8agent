from common import *
C=ROOT/read(ART/'stage.json')['root']; B=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name, old, new):
 p=B/name;t=p.read_text();assert old in t,(name,old[:100]);p.write_text(t.replace(old,new,1))
edit('completion_execution.py',"        investigation = selection.get('investigation_state') or {}\n        previous_assessments=", """        investigation = selection.get('investigation_state') or {}
        from . import read_judgment_final as final_judgment
        judgment_context = None
        if modern and profile.get('candidate_navigation',{}).get('read_judgment'):
            judgment_context = final_judgment.context(investigation,utterance,self.issues,options,self.s.sources.scope)
            schema = final_judgment.attach(schema,judgment_context,options)
        previous_assessments=""")
edit('completion_execution.py',"'previous_assessment_hash':digest(previous_assessments),", "'previous_assessment_hash':digest(previous_assessments), 'read_judgments_hash':digest(judgment_context),")
edit('completion_execution.py',"        generation_schema,expand_assessment=assessment_projection(schema", "        if judgment_context is not None:answer_policy += '\\n'+final_judgment.PROMPT\n        generation_schema,expand_assessment=assessment_projection(schema")
edit('completion_execution.py',"                    'previous_assessments':previous_assessments,", "                    'previous_assessments':previous_assessments,\n                    **({'read_judgments':judgment_context} if judgment_context is not None else {}),")
edit('completion_execution.py',"                    accepted, proposal=content_impl.prepare(value,schema,self.issues,options,fact_sources)", """                    core_value, core_schema = value, schema
                    if judgment_context is not None:
                        final_judgment.validate_review(value,judgment_context,options)
                        core_value,core_schema=final_judgment.core(value,schema)
                    accepted, proposal=content_impl.prepare(core_value,core_schema,self.issues,options,fact_sources)""")
edit('completion_execution.py',"                if not cached:decision_journal.accept(attempt,value)\n                break", """                if not cached:decision_journal.accept(attempt,value)
                if judgment_context is not None:final_judgment.retain(result,value,judgment_context,investigation)
                break""")
edit('completion_execution.py',"                    normalized=True\n                    break", "                    if judgment_context is not None:final_judgment.incomplete(result,judgment_context)\n                    normalized=True\n                    break")
edit('completion_execution.py',"        result.update(answer_coverage=ic.coverage(result), semantic_quality_certified=False)", """        material_open = final_judgment.limitations(result)
        result.update(answer_coverage=('PARTIAL' if material_open and ic.coverage(result)=='COVERED' else ic.coverage(result)), semantic_quality_certified=False)""")
edit('judgment_view.py',"            row['actions'] = ['읽은 원문에서 답변에 사용할 근거 선택']", """            row['actions'] = ['읽은 원문에서 답변에 사용할 근거 선택']
            from .read_judgment import checked
            ledgers = [checked(s) for s in (payload.get('investigation_state') or {}).get('read_judgments',{}).values()]
            if ledgers:
                row['read_judgments'] = [{k:s.get(k,{}) for k in ('request_key','heads','needs','conflicts','history','receipts','final_reviews')} for s in ledgers]
                if any(h['document_id'] not in allowed for s in ledgers for h in s['heads'].values()):
                    raise ContractError('judgment display escaped current authorization')
                row['actions'] = ['원문별 잠정 판단·이유·미확인·다음 행동 기록']""")
edit('judgment_view.py',"            row['limitations'] = payload.get('limitations', [])", """            if payload.get('read_judgment_review'):
                row['read_judgment_review'] = payload['read_judgment_review']
            row['limitations'] = payload.get('limitations', [])""")
# Acquisition must not be displayed as adopted just because it reached ASSESS.
edit('judgment_view.py',"'action': '답변 근거 채택' if sid in selected else '최종 근거에 미포함',", "'action': ('최종 검토에 전달' if ledgers else '답변 근거 채택') if sid in selected else '최종 근거에 미포함',")
