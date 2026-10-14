from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0738/integrated/snapshot';L=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=L/name;s=p.read_text();assert old in s,(name,old);p.write_text(s.replace(old,new))
edit('completion_contracts.py','KNOWN = (V1, V2, V3, CONTRACT, V5, V6)',"V7 = 'investigation-completion-v7'\nKNOWN = (V1, V2, V3, CONTRACT, V5, V6, V7)")
edit('completion_contracts.py','(V3, CONTRACT, V5, V6)','(V3, CONTRACT, V5, V6, V7)')
edit('request_repair.py',"(VERSION, 'investigation-completion-v6')","(VERSION, 'investigation-completion-v6', 'investigation-completion-v7')")
edit('law_candidates.py',"'investigation-completion-v6')","'investigation-completion-v6','investigation-completion-v7')")
edit('memory_rag.py','(cc.V5,cc.V6)','(cc.V5,cc.V6,cc.V7)')
edit('law_navigation.py','(cc.V5,cc.V6)','(cc.V5,cc.V6,cc.V7)')
edit('investigation_scope.py',"==cc.V6","in (cc.V6,cc.V7)")
edit('bounded_source_session.py',"=='investigation-completion-v6'", "in ('investigation-completion-v6','investigation-completion-v7')")
edit('completion_execution.py','from . import completion_v6','from . import completion_v6,completion_v7')
edit('completion_execution.py','content_impl=completion_v6 if contract==cc.V6 else v5','content_impl=completion_v7 if contract==cc.V7 else completion_v6 if contract==cc.V6 else v5')
edit('completion_v5.py',"    if claim['answer_content'].get('content_contract')=='source-modality-v1':", "    if claim['answer_content'].get('content_contract')=='source-modality-v2':\n        from .completion_v7 import verify_content\n        return verify_content(claim)\n    if claim['answer_content'].get('content_contract')=='source-modality-v1':")
edit('navigation_input.py',"TEXT_FIELDS={'text'", "TEXT_FIELDS={'explanation','text'")
p=C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=json.loads(p.read_text());v['candidate_navigation']['completion_policy_version']='investigation-completion-v7';p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=L/'completion_v7.py';s=p.read_text().replace("''' + v6.PROMPT.split('아래 공통 원문 계약도 따른다.')[0]", "norm.kind는 OBLIGATION(의무)/PERMISSION(허용)/PROHIBITION(금지)/UNSPECIFIED(미확정)다.\n'''+'\\n'.join(v6.PROMPT.split('\\n')[1:3])")
p.write_text(s)
