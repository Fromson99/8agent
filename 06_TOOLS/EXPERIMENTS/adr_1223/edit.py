from common import *
S=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1223/source-refs/snapshot'
p=S/'02_BACKEND/semantic_runtime/ontology_work/accumulation.py';s=p.read_text().replace('def accumulation_schema(profile, observations, base=None):','def accumulation_schema(profile, observations, base=None, originals=None):')
s=s.replace("    def bind(value):\n        if isinstance(value, dict):", "    source_ids = sorted(s['id'] for s in originals) if originals is not None else None\n    def bind(value):\n        if isinstance(value, dict):\n            props = value.get('properties', {})\n            if set(props) == {'source', 'quote'} and source_ids:\n                props['source']['enum'] = source_ids")
pos=s.index('\n\ndef reference_contract')
s=s[:pos]+'''

PROMPT += (' 모든 basis.source는 제공된 originals의 id만 쓴다. 관찰키(o-...), 관찰 속 evidence_refs/source_ref, '
           '용어ID는 규정 원문 ID가 아니다. basis.quote는 그 originals 항목의 text에서 정확히 복사한다. '
           '관찰이 식별자뿐이거나 제공 원문으로 확인할 수 없어 UNKNOWN으로 판단하고 제안 노드도 없으면 '
           'basis=[]와 node_ids=[]가 허용된다. 이때 원문인 척 관찰값을 인용하지 말고 reason에 미확인 사유를 적는다.')


def check_basis_references(proposal, originals):
    sources = index(originals)
    errors = []
    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                here = path + '/' + key
                if key == 'basis':
                    for i, row in enumerate(child):
                        location = here + '/' + str(i)
                        source = sources.get(row['source'])
                        if source is None:
                            errors.append(f"{location}/source unknown={row['source']}; allowed originals.id={sorted(sources)}; observation IDs are not original source IDs")
                        elif not row['quote'] or row['quote'] not in source['text']:
                            errors.append(f"{location}/quote is not an exact nonempty substring of originals[{row['source']}].text; UNKNOWN comparisons may use basis=[] when there is no verified original basis")
                else:
                    visit(child, here)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                visit(child, path + '/' + str(i))
    visit(proposal, '')
    if errors:
        raise ContractError('accumulation original basis errors: ' + '; '.join(errors[:12]) +
                            (f'; {len(errors)-12} more errors' if len(errors)>12 else ''))
''' +s[pos:]
s=s.replace("    check_graph_references(proposal, incoming, base)\n", "    check_graph_references(proposal, incoming, base)\n    check_basis_references(proposal, originals)\n")
p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/ontology_work/domain_workflow.py';s=p.read_text().replace('acc.accumulation_schema(profile, observations, base),','acc.accumulation_schema(profile, observations, base, kwargs[\'originals\']),');p.write_text(s)
