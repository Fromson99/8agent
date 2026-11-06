"""Request-only evidence for roles in a raw record, never inferred motivation."""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent.errors import ContractError
from .profile import validate
from .schema import obj, arr, text

INSTRUCTIONS = ('\nrecorded_reason/recorded_purpose는 원래 작성자가 기록한 판단 이유/작성 목적이다. '
    '정규화 담당자의 설명, 판단 본문, 식별자, 규정의 취지, 용어 연결 이유를 대신 넣지 않는다. '
    '기록이 없거나 역할이 불명확하면 null이다. statement에 있는 내용만으로 숨은 동기를 추론하지 않는다. '
    '명시된 이유/목적을 찾았을 때만 value와 locators를 정확히 인용한다. role_evidence는 '
    'LABELED_FIELD(실제 이유/목적 필드) 또는 EXPLICIT_TEXT(그 역할을 명시한 짧은 연결 표현)의 locator다. '
    'LABELED_FIELD의 label에는 실제 입력 필드명을 그대로 적고, EXPLICIT_TEXT의 label은 null이다. '
    'EXPLICIT_TEXT의 quote는 예컨대 원래 글의 “때문에”, “하기 위해” 같은 역할 표시 구절이다. '
    '본문 전체·식별자·임의 단어를 표시 구절로 쓰지 않는다. coverage.reason과 비교 reason은 새 처리 설명이며 원래 이유와 별개다.')
FIELDS = ('reason', 'purpose')


def glossary_mentions(raw, candidates, limit=128):
    """A bounded menu of exact positions; unlisted text still has the normal locator path."""
    labels = dict.fromkeys(label['text'] for candidate in candidates['candidates']
                           for label in candidate.get('card', {}).get('labels', [])
                           if isinstance(label.get('text'), str) and 0 < len(label['text']) <= 16000)
    options = {}
    for label in list(labels)[:128]:
        for row in raw['index']:
            start = -1
            occurrence = 0
            while len(options) < limit:
                start = row['text'].find(label, start + 1)
                if start < 0:
                    break
                options[f'M{len(options)+1}'] = {'pointer':row['pointer'], 'quote':label,
                                                'occurrence':occurrence, 'start':start, 'end':start+len(label)}
                occurrence += 1
            if len(options) == limit:
                return options
    return options


def request_schema(schema, raw, mentions=None):
    schema = deepcopy(schema)
    fields = schema['properties']['observations']['items']
    locator = obj({'pointer': {'enum': [r['pointer'] for r in raw['index']]},
                   'quote': text(16000), 'occurrence': {'type':'integer','minimum':0}})
    for key in FIELDS:
        del fields['properties'][key]; fields['required'].remove(key)
        name = 'recorded_' + key
        fields['properties'][name] = {'anyOf': [{'type':'null'}, obj({
            'value': text(16000), 'locators': arr(deepcopy(locator),1),
            'role_evidence': obj({'mode': {'enum':['LABELED_FIELD','EXPLICIT_TEXT']},
                                  'label': {'anyOf':[{'type':'null'},text(2000)]},
                                  'locator': deepcopy(locator)})})]}
        fields['required'].append(name)
    if mentions:
        refs = fields['properties']['glossary_refs']['items']['properties']['mention_refs']
        refs['items'] = {'anyOf':[{'enum':list(mentions)}, refs['items']]}
    return schema


def restore(proposal, raw, schema, restore_coordinates, mentions=None):
    # Generation must use the new request contract. Historical canonical readers
    # remain separate and continue to use validate_observations.
    validate(proposal, schema)
    converted = deepcopy(proposal); evidence = []
    segments = {r['pointer']:r['text'] for r in raw['index']}
    mention_choices = []
    for observation in converted['observations']:
        for link in observation['glossary_refs']:
            for index, location in enumerate(link['mention_refs']):
                if isinstance(location, str):
                    selected = (mentions or {}).get(location)
                    if selected is None:
                        raise ContractError('unoffered raw glossary mention')
                    pointer, start, end = selected['pointer'], selected['start'], selected['end']
                    if segments[pointer][start:end] != selected['quote']:
                        raise ContractError('raw glossary mention text changed')
                    link['mention_refs'][index] = {k:selected[k] for k in ('pointer','quote','occurrence')}
                    mention_choices.append({'observation_id':observation['id'], 'concept_id':link['concept_id'],
                                            'choice':location, 'locator':deepcopy(selected)})
                elif mentions and any(row['pointer']==location['pointer'] and row['quote']==location['quote']
                                       for row in mentions.values()):
                    # Keep all valid free-form spans, including occurrences beyond the menu cap.
                    try:
                        restore_coordinates({'mention':location}, raw)
                    except ContractError as exc:
                        offered = [k for k,row in mentions.items() if row['pointer']==location['pointer']
                                   and row['quote']==location['quote']]
                        raise ContractError(f'invalid occurrence for glossary mention {location["quote"]!r}; '
                                            f'choose the actual occurrence from {offered} or omit an unobserved mention') from exc
        for key in FIELDS:
            value = observation.pop('recorded_' + key)
            if value is None:
                observation[key] = {'state':'NOT_RECORDED','value':None,'locators':[]}
                continue
            proof = value['role_evidence']; locator = proof['locator']
            pointer, cue = locator['pointer'], locator['quote']
            locations = value['locators']
            if value['value'] not in [l['quote'] for l in locations]:
                raise ContractError('recorded '+key+' must preserve an exact raw value')
            if pointer not in {l['pointer'] for l in locations}:
                raise ContractError('recorded '+key+' role evidence must address its recorded value')
            if proof['mode'] == 'LABELED_FIELD':
                # The model classifies field meaning. The server only verifies
                # that the selected label is an actual object key on this path.
                labels = []; current = raw['payload']
                for token in pointer.split('/')[1:]:
                    token = token.replace('~1','/').replace('~0','~')
                    if isinstance(current,dict):labels.append(token);current=current[token]
                    elif isinstance(current,list):current=current[int(token)]
                if proof['label'] not in labels or cue != value['value']:
                    raise ContractError('recorded '+key+' has no matching actual field label/value')
            elif (proof['label'] is not None or not cue.strip() or cue not in value['value']
                  or cue == value['value'] or cue == segments[pointer]
                  or value['value'] == observation['statement']['value']):
                raise ContractError('recorded '+key+' needs an explicit short role cue, not a copied statement/identifier')
            # Restore proof separately too: an invented occurrence cannot pass.
            proof_canonical, _ = restore_coordinates({'proof': locator}, raw)
            evidence.append({'observation_id':observation['id'],'field':key,
                             'mode':proof['mode'],'label':proof['label'],'locator':proof_canonical['proof']})
            observation[key] = {'state':'PRESENT','value':value['value'],'locators':locations}
    canonical, receipt = restore_coordinates(converted, raw)
    receipt.update(version='normalization-recorded-role-v2', proposal_sha256=digest(proposal),
                   recorded_roles=evidence, canonical_sha256=digest(canonical))
    if mentions:
        receipt['glossary_mention_choices'] = mention_choices
        receipt['glossary_mention_menu_hash'] = digest(mentions)
    return canonical, receipt
