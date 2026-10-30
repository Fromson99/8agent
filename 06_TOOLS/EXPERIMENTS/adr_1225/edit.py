from common import *
p=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1225/authoring-contract/snapshot/02_BACKEND/semantic_runtime/ontology_work/accumulation.py';s=p.read_text()
pos=s.index('\n\ndef check_basis_references')
s=s[:pos]+"\n\nPROMPT += (' 새 관찰을 누적할 때 base.proposal.graph의 기존 노드·간선·목적도 포함한 전체 다음 그래프를 출력한다. 기존 노드를 빼면 removed_nodes에 정확한 ID·원문·이유가 필요하다. SUPPORTED는 원문 지지 여부이고 SAME은 이전 graph 전체와 구조·내용이 그대로인 경우에만 쓴다. 새 노드/간선/목적/미확인 내용을 추가·변경하면서 SAME이라고 쓰지 않는다.')"+s[pos:]
s=s.replace("    invalid = unused.keys() - nodes.keys()", "    if any(row['relation'] == 'SAME' for row in comparisons.values()) and (not base or base['proposal']['graph'] != proposal['graph']):\n        errors.append('comparisons.relation SAME requires the entire proposed graph to equal base.proposal.graph exactly; new/changed nodes or edges are not SAME; source verdict SUPPORTED is independent of graph relation')\n    invalid = unused.keys() - nodes.keys()")
p.write_text(s)
