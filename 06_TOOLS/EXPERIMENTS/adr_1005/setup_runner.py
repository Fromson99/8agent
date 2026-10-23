from common import *
import shutil
C=ROOT/read(ART/'stage.json')['roots']['candidate'];here=Path(__file__).parent;old=here.parent/'adr_1003'
for n in ('repin.py','trace.py','stop_policy.py','full_query.py','analyze.py'):
 t=(old/n).read_text().replace('ADR-1003','ADR-1005').replace('adr_1003','adr_1005').replace('correlated-progress-1003','visible-connections-1005')
 if n=='full_query.py':t=t.replace("'max_model_attempts':40","'max_model_attempts':14")
 (here/n).write_text(t)
p=C/'05_TESTS/CONTRACTS/test_answer_progress_api.py';t=p.read_text()
t=t.replace("('context',True)])","('context',True),('partial',False)])")
t=t.replace("if route=='context':first=", "if route in ('context','partial'):first=").replace("if route=='context' else []", "if route in ('context','partial') else []")
needle="                if route=='chain' and any('제2조' in s['heading'] for s in view['sources']):"
insert="""                if route=='partial' and view['sources'] and not read_target:
                    assert any(o['choice']=='FOLLOW_CONNECTION' for o in view['tool_options'])
                    scope=view['connection_scope_choices'][0]
                    assert scope['connections_presented_inline'] and not scope['connections_complete']
                    card=next(c for c in view['references']['dependency_cards'] if c.get('read_action') and '제2조' in c['target']['heading'])
                    self.link_selected=True;self.choices.append('READ_CONNECTION')
                    return wire({'choice':'READ','selections':[{'target':card['read_action'],'issue_id':'Q1',
                        'missing_need':'연결 목록이 일부여도 이미 제시된 필수 원문 읽기','relation':'DEPENDENCY',
                        'source_ref':view['sources'][0]['id']}]})
"""
assert needle in t;t=t.replace(needle,insert+needle).replace("if route=='connection'\n", "if route in ('connection','partial')\n")
p.write_text(t)
