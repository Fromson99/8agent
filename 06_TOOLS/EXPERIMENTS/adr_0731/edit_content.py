from pathlib import Path
R=Path(__file__).resolve().parents[3];L=R/'02_BACKEND/lawrag/research/candidates/adr_0731/integrated/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=L/'navigation_input.py';p.write_text(p.read_text().replace('from ..repository import encoded','from .repository import encoded'))
s=(R/'02_BACKEND/semantic_runtime/legal_agent/completion_v5.py').read_text().replace("VERSION = 'investigation-completion-v5'", "VERSION = 'investigation-completion-v6'")
s=s.replace("PROMPT = '''", "PROMPT = '''v6 계약: rule.obligations 대신 rule.norms를 쓴다. norms의 kind는 OBLIGATION(의무)/PERMISSION(허용)/PROHIBITION(금지)/UNSPECIFIED(명시 양태 미확정)다.\n각 norm의 source_quote는 그 양태를 직접 보여주는 evidence_refs 원문의 연속 문장·절이다. 서로 다른 양태가 섞인 인용은 더 정확한 절로 나누거나 UNSPECIFIED로 보존한다.\n‘할 수 있다’는 허용이며 ‘하여야 한다’라는 의무로 바꾸지 않는다. ‘하여서는 아니 된다’는 금지다. 결론·세부 설명에도 같은 양태를 유지한다.\n적용 조건은 효과 발생의 전제이고, 이행 의무는 그 효과에 따라 요구되는 행동이다. 결론은 질문에 직접 답하는 짧은 요약, 구체 내용은 details/조건/norms/예외 중 알맞은 한 곳에만 쓴다.\n" ,1).replace('v5 계약이 우선한다.','아래 공통 원문 계약도 따른다.').replace('obligations는 적용 조건과 구분되는 행위 의무다.','norms는 조건과 구분된 원문의 의무·허용·금지이며 분류가 불확실하면 UNSPECIFIED로 보존한다.')
s=s.replace("'obligations':{'type':'array','maxItems':12,'items':fragment}", "'norms':{'type':'array','maxItems':12,'items':cc.obj({'kind':{'enum':['OBLIGATION','PERMISSION','PROHIBITION','UNSPECIFIED']},'text':text,'source_quote':{'type':'string','minLength':2,'maxLength':2000},'evidence_refs':cc.refs(ids,1)})}")
s=s.replace("claim['required'] += ['conclusion','details','rule']", "claim['properties']['content_contract']={'const':'source-modality-v1'}\n    claim['required'] += ['conclusion','details','rule','content_contract']")
s=s.replace("fragment_refs(rule['obligations'])", "fragment_refs(rule['norms'])")
start=s.index('def render_content(');end=s.index('\n\ndef prepare(',start)
s=s[:start]+'''def render_content(content):
    rule=content['rule'];typed=set()
    def key(text):return ' '.join(text.split()).rstrip(' .。')
    def leaves(node):
        if node is None:return []
        if node['mode']=='LEAF':return [node['text']]
        return [text for c in node['children'] for text in leaves(c)]
    if rule:
        typed={key(x['text']) for x in rule['norms']+rule['exceptions']}|{key(x) for x in leaves(rule['condition_tree'])}
    pieces=[];seen=set()
    for text in [content['conclusion']]+[x['text'] for x in content['details']]:
        ident=key(text)
        if ident not in typed and ident not in seen:pieces.append(text);seen.add(ident)
    def render_node(node):
        if node['mode']=='LEAF':return node['text']
        prefix={'ALL':'모두 충족','ANY':'하나 이상 충족','UNKNOWN':'요건 관계 미확인'}[node['mode']]
        return '('+prefix+': '+'; '.join(render_node(c) for c in node['children'])+')'
    if rule is not None:
        pieces.append('적용 범위: '+' · '.join(dict.fromkeys(rule[k] for k in ('subject','action','scope'))))
        if rule['condition_tree'] is not None:pieces.append('적용 조건: '+render_node(rule['condition_tree']))
        labels={'OBLIGATION':'의무','PERMISSION':'허용','PROHIBITION':'금지','UNSPECIFIED':'규정'}
        rows=[]
        for row in rule['norms']:
            ident=(row['kind'],key(row['text']))
            if ident not in rows:pieces.append(labels[row['kind']]+': '+row['text']);rows.append(ident)
        pieces+=['예외 ('+r['target']+'): '+r['text'] for r in rule['exceptions']]
        if rule['fact_refs']:pieces.append('사용자가 제공한 전제: '+'; '.join(r['quote'] for r in rule['fact_refs']))
    return '\\n'.join(pieces)


def source_modality(text):
    """Explicit language guard, not a legal entailment classifier."""
    import re
    patterns={
      'PROHIBITION':r'(?:하여서는|해서는|해서|하여|되어서는|돼서는|되어|할|될|받을|둘)\\s*(?:아니\\s*된다|안\\s*된다|수\\s*없(?:다|으며|고))',
      'PERMISSION':r'(?:할|될|받을|둘|갈음할|제외할|면제할|변경할|신청할|지급할|정할)\\s*수\\s*있(?:다|으며|고|는)',
      'OBLIGATION':r'(?:하여야|해야|되어야|돼야|이어야|여야|져야|받아야|내야|두어야|알려야|정하여야|제출하여야|신고하여야|신청하여야)\\s*(?:한다|하며|하고|할|합니다)'}
    found={kind for kind,pattern in patterns.items() if re.search(pattern,text)}
    if re.search(r'(?:의무가\\s*없|필요가\\s*없|(?:하여야|해야).{0,18}(?:아니|않|없))',text):return 'UNSPECIFIED'
    return next(iter(found)) if len(found)==1 else 'UNSPECIFIED'


def verify_modalities(value,options):
    offered={o['id']:o for o in options}
    for claim in value['claims']:
        if claim['rule'] is None:continue
        for norm in claim['rule']['norms']:
            quote=norm['source_quote']
            if not any(quote in offered.get(i,{}).get('text','') for i in norm['evidence_refs']):
                raise ProposalError('norm source_quote must be an exact clause of its selected evidence')
            actual=source_modality(quote)
            if norm['kind']!=actual:
                raise ProposalError('norm kind differs from explicit source modality: '+actual)
            proposed=source_modality(norm['text'])
            if proposed!='UNSPECIFIED' and proposed!=actual:
                raise ProposalError('norm wording reverses the source permission/obligation/prohibition')
''' + s[end:]
s=s.replace('    validate(value,schema)\n', '    validate(value,schema)\n    verify_modalities(value,options)\n',1)
(L/'completion_v6.py').write_text(s)
