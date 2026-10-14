from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0726/compact/snapshot';L=C/'02_BACKEND/semantic_runtime/legal_agent'
p=L/'local_gemma.py';s=p.read_text();s=s.replace('    return payload\n','    from .wire_schema import factor_schema\n    envelope=(payload.get(\'response_format\') or {}).get(\'json_schema\')\n    if envelope and isinstance(envelope.get(\'schema\'),dict):\n        envelope[\'schema\']=factor_schema(envelope[\'schema\'])\n    return payload\n',1);p.write_text(s)
p=L/'gateway.py';s=p.read_text();s=s.replace('    return result\n\n\ndef compact_original_text','    if result.get(\'input_projection\') == \'compact-selection-source-v2\':\n        compact_original_text(result)\n        compact_evidence_metadata(result)\n    return result\n\n\ndef compact_evidence_metadata(view):\n    """Omit opaque integrity hashes from the model copy; journal verification retains them."""\n    def walk(node):\n        if isinstance(node,list):\n            for x in node:walk(x)\n        elif isinstance(node,dict):\n            if (\'block_id\' in node and \'start_cp\' in node and \'end_cp\' in node\n                    and (\'text\' in node or \'text_ref\' in node)):\n                for key in (\'block_hash\',\'span_hash\',\'text_hash\'):\n                    node.pop(key,None)\n            for child in node.values():walk(child)\n    walk(view)\n\n\ndef compact_original_text',1)
s=s.replace("if view.get('input_projection')=='compact-selection-source-v1':", "if view.get('input_projection') in ('compact-selection-source-v1','compact-selection-source-v2'):")
p.write_text(s)
p=L/'bounded_source_session.py';s=p.read_text().replace("and phase.startswith('source-law-navigation-'):","and (phase.startswith('source-law-navigation-') or phase in ('memory-assess','memory-assess-repair')):",1).replace("'input_projection':'compact-selection-source-v1'","'input_projection':'compact-selection-source-v2'",1);p.write_text(s)
p=L/'law_navigation.py';s=p.read_text();s=s.replace('READ_ARTICLES는 article_matches 또는 structure_catalogue의 read_action으로 같은 법의 필요한 조문들을 함께 읽는다.', '질문의 대상·행위·세부 요구를 issues와 대조하고, 각 요구를 충족할 가장 직접적인 조문부터 읽는다. 순위가 높다는 이유만으로 주변 조문을 모두 묶어 읽거나 채택하지 않는다. 같은 요구의 정의·위임·예외를 확인할 필요가 있을 때만 해당 연결이나 항·호로 확장한다. 이는 다른 항의 필수 조건·예외를 생략하라는 뜻이 아니다.\nREAD_ARTICLES는 article_matches 또는 structure_catalogue의 read_action으로 같은 법의 필요한 조문들을 함께 읽는다.',1)
s=s.replace('SEARCH_STRUCTURE의 structure_filter는 coordinate/title/coordinate_scope이며 필터 사용시 queries는 비운다.','SEARCH_STRUCTURE의 structure_filter는 coordinate/title/coordinate_scope이며 문서가 지정된 target에서만 사용하고 queries는 비운다. 문서 전체 목록 검색은 queries를 사용한다.',1)
old='''        branches.append(branch)
    # Action constants'''
new='''        if kind == 'SEARCH_STRUCTURE':
            typed=deepcopy(branch)
            doc_targets={a['id'] for a in actions.values() if a['action']==kind and a['identity'].get('document_id') is not None}
            typed['properties']['targets']=dict(_strings(doc_targets),minItems=1,maxItems=1)
            typed['properties']['queries']=dict(_strings(),maxItems=0)
            typed['required'].append('structure_filter')
            if doc_targets:branches.append(typed)
            # Untyped catalogue/document queries cannot carry a typed filter.
            branch['properties'].pop('structure_filter')
            branch['properties']['queries']['minItems']=1
        branches.append(branch)
    # Action constants'''
assert old in s;s=s.replace(old,new,1);p.write_text(s)
