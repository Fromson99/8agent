from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate'];D=C/'02_BACKEND/semantic_runtime/legal_agent';T=C/'05_TESTS/CONTRACTS'
p=D/'law_navigation.py';t=p.read_text().replace("{'id':g['id']} for g in directory['groups']", "{'id':g['key']} for g in directory['groups']")
t=t.replace("if size(value) > limit and isinstance(value.get('references'), dict) and 'dependency_cards' in value['references']:", "if size(value) > limit and not self.policy.get('selected_connection_scope') and isinstance(value.get('references'), dict) and 'dependency_cards' in value['references']:")
p.write_text(t)
p=D/'connection_scope.py';t=p.read_text();a=t.index('                # Only the presentation is bounded.');b=t.index("                if 'read_action' in card:",a)
t=t[:a]+"                # Preserve every verified witness for this endpoint.\n                additional.append(witness)\n"+t[b:];p.write_text(t)
p=T/'test_selected_connection_scope_api.py';t=p.read_text();a=t.index("                if route=='batch' and");t=t[:a]+'''                if view['sources'] and not read_target and route not in ('batch','missing','failure'):
                    wanted='제3조' if route=='chain' and any('제3조에 따른 승인 기준' in s['text'] for s in view['sources']) else '제10조' if route=='context' else '제2조'
                    cards=view['references']['dependency_cards']
                    candidates=[c for c in cards if c.get('read_action') and wanted in c['target']['heading']]
                    if candidates:
                        if route=='context':assert len(cards)==9
                        if nested:
                            headings={c['target']['heading'].split()[0] for c in cards}
                            assert headings==({'제2조'} if route=='narrow' else {'제2조','제3조'})
                        c=candidates[0];self.choices.append('READ_LINK')
                        return wire({'choice':'READ','selections':[{'target':c['read_action'],'issue_id':'Q1',
                            'missing_need':'필요한 연결 원문 확인','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']}]})
''' + t[a:]
a=t.index("            if phase.startswith('source-reference-law-'):");b=t.index("            if phase.startswith('memory-assess'):",a)
t=t[:a]+"            if phase.startswith('source-reference-law-'):raise AssertionError('Nested reference model must not run')\n"+t[b:]
t=t.replace("                        assert view['tool_recovery']", "                        assert any(c['connection_preview']['status']=='FAILED' for c in view['connection_scope_choices'])")
t=t.replace("assert transport.reference_calls == (2 if route=='chain' else 0 if route in ('missing','failure') else 1)", "assert transport.reference_calls == 0")
t=t.replace("['READ','FOLLOW_CONNECTION','FOLLOW_CONNECTION','FINISH']", "['READ','FOLLOW_CONNECTION','READ_LINK','FOLLOW_CONNECTION','READ_LINK','FINISH']")
t=t.replace("['READ','FOLLOW_CONNECTION','FINISH'])", "['READ','FOLLOW_CONNECTION','READ_LINK','FINISH'])")
p.write_text(t)
p=T/'test_retained_partial_connections.py';t=p.read_text().replace('assert len(shown)==min(5,count)','assert len(shown)==count');p.write_text(t)
