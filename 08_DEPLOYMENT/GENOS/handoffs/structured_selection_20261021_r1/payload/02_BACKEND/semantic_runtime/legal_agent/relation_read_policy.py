"""Reading obligations from verified citation wording, not legal applicability.

Old generation role labels are whole-frame hints. Recheck the predicate beside
the exact mention; preserve uncertainty instead of borrowing a nearby predicate.
"""
import re

REVISION = 'relation-reading-policy-20261018-r3'
RULES = {
    'CITES': ('OPTIONAL', 'OPTIONAL'),
    'BASED_ON': ('OPTIONAL', 'OPTIONAL'),
    'APPLIES_MUTATIS_MUTANDIS': ('REQUIRED', 'OPTIONAL'),
    'USES_DEFINITION': ('REQUIRED', 'OPTIONAL'),
    'SPECIFIES_DELEGATED_CASES_OF': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    'DELEGATES_TO': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    'EXCLUDES': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    'HAS_EXCEPTION': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    'DEEMS': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    'VIOLATION_SANCTIONED_BY': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    'TEMPORAL': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
    'ANNEX_STANDARD': ('CHECK_APPLICABILITY', 'OPTIONAL'),
    'ANNEX_FORM': ('CHECK_APPLICABILITY', 'OPTIONAL'),
    'UNKNOWN': ('CHECK_APPLICABILITY', 'CHECK_APPLICABILITY'),
}
GUIDANCE = '''연결 읽기 정책: 답변에 채택한 원문의 준용 대상·적용 정의는 선언한 범위를 확보한다.
본문과 그에 붙은 단서, 상위 항·호의 조건은 함께 확인한다. 별도 예외·배제·불구하고·의제는
정방향/역방향 모두 적용 여부를 확인한다. 위임·수임·단서 구체화는 질문에 필요한 세부 기준이나
권한을 맡긴 경우 읽는다. 상위 조문을 인용한 시행령이 그 단서를 구체화하면 역방향도 필수다.
별표는 답변의 기준·수치가 그곳에 있을 때 해당 범위를 읽고, 별지서식은 절차·기재사항을 묻거나
본문이 필요한 정보를 서식에 맡긴 경우만 읽는다. 단순 역인용 서식은 자동으로 읽지 않는다.
시행일·적용례·경과는 적용 시점이 결론을 바꾸는 경우, 제재는 위반 결과가 쟁점인 경우 읽는다.
단순 인용·근거와 정의/준용의 역방향 사용자 목록은 선택 탐색이며 모두 읽을 의무가 없다.
관계 종류는 문언의 단서이고 적용 결론이 아니다. 질문에 없는 사실을 가정하지 않는다.
CHECK_APPLICABILITY를 SKIP하려면 applicability=DOES_NOT_APPLY와 구체적 사유를 기록한다.
적용 여부가 불명확하면 DEFER 또는 FOLLOW다. REQUIRED도 문언상 읽기 단서이며 질문에 대한 적용 결론은 아니다. 질문과 무관하다고 판단하면 DOES_NOT_APPLY와 구체적 사유를 기록하여 SKIP할 수 있다. 필요한 준용·정의의 범위를 임의로 줄이지 않는다.
FOLLOW 범위는 required_block_ids를 전부 포함한다. 이미 읽은 범위는 재사용한다.
모든 판단에 applicability와 applicability_reason을 함께 출력한다. FOLLOW는 APPLIES 또는
UNDETERMINED, DEFER는 UNDETERMINED와 미확인 사유다. 조건부 SKIP은 DOES_NOT_APPLY와
실제 질문 범위에 연결한 제외 사유다. 단순 연결도 생략 사유를 기록한다.
필수 범위를 못 읽거나 조건을 확인하지 못하면 그 연결을 미확인으로 남기고 해결됐다고 표시하지 않는다.
전체 조사 완료 가능 여부는 상위 조사 단계의 completion_policy를 따른다.'''


def classify(ref, direction, target):
    text = ref.get('source_text', '')
    a, z = ref.get('mention_start'), ref.get('mention_end')
    exact = (type(a) is int and type(z) is int and 0 <= a < z <= len(text)
             and bool(ref.get('mention_text')) and text[a:z] == ref['mention_text'])
    kind, basis = 'UNKNOWN', 'unattributed_witness'
    tail = re.split(r'[。;\n]|\.(?!\d)', text[z:], maxsplit=1)[0] if exact else ''
    if exact and text[a:z].rstrip().endswith('단서'):
        tail = '단서' + tail
    # A different article mention breaks attribution to this endpoint.
    if exact and not re.search(r'제\s*\d+(?:의\d+)?\s*조', tail):
        kind, basis = 'CITES', 'verified_mention_following_clause'
        if re.search(r'단서에서.*정하는\s*경우.*란', tail):
            kind = 'SPECIFIES_DELEGATED_CASES_OF'
        elif '준용' in tail:
            kind = 'APPLIES_MUTATIS_MUTANDIS'
        elif re.search(r'에도\s*불구하고|적용하지\s*(?:아니|않)|적용을\s*배제', tail):
            kind = 'EXCLUDES'
        elif re.search(r'예외로\s*한다|제외한다|면제한다', tail):
            kind = 'HAS_EXCEPTION'
        elif re.search(r'정의(?:를|에)\s*(?:따|의)|정한\s*뜻', tail):
            kind = 'USES_DEFINITION'
        elif re.search(r'으로\s*본다|로\s*본다|의제한다', tail):
            kind = 'DEEMS'
        elif re.search(r'위반.*(?:벌금|과태료|처벌|제재)', tail):
            kind = 'VIOLATION_SANCTIONED_BY'
        elif re.search(r'시행일|경과조치|적용례|시행\s*이후|시행\s*전에', tail):
            kind = 'TEMPORAL'
    origins = ref.get('origins', [])
    if 'official_delegation_lawgokr' in origins:
        kind, basis = 'DELEGATES_TO', 'verified_official_delegation'
    elif 'raw_explicit_annex_hint' in origins and kind == 'CITES':
        kind = 'ANNEX_FORM' if re.search(r'별지|서식', ref.get('locator', '')) else 'ANNEX_STANDARD'
    # Word "단서" selects a span; it does not establish EXCEPTION_TO by itself.
    return {'revision': REVISION, 'kind': kind, 'kind_basis': basis,
            'stored_role_hint': ref.get('reference_role'),
            'direction': direction,
            'obligation': RULES[kind][direction == 'INCOMING'],
            'target_qualifiers': [x for x in ('단서', '본문', '전단', '후단')
                                  if x in ref.get('locator', '')],
            'canonical_approval': False}


def validate_decision(decision, group):
    action = decision['action']; applicability = decision.get('applicability')
    if not str(decision.get('applicability_reason', '')).strip():
        raise ValueError('reference applicability reason must not be blank')
    if action == 'FOLLOW' and applicability not in ('APPLIES', 'UNDETERMINED'):
        raise ValueError('FOLLOW requires applicable or undetermined reference')
    if action == 'DEFER' and applicability != 'UNDETERMINED':
        raise ValueError('DEFER requires undetermined applicability')
    for link in group.get('connections', []):
        policy = link.get('reading_policy', {})
        obligation = policy.get('obligation', 'OPTIONAL')
        if link.get('already_read'):
            continue
        if decision['action'] == 'SKIP':
            if obligation in ('REQUIRED', 'CHECK_APPLICABILITY') and (
                    decision.get('applicability') != 'DOES_NOT_APPLY'
                    or not decision.get('applicability_reason', '').strip()):
                raise ValueError('conditional relation skip requires inapplicability reason')
        if decision['action'] == 'FOLLOW':
            covered = set().union(*(set(group['offers'][scope][1]['block_ids'])
                                    for scope in decision['scopes']))
            if not set(link.get('required_block_ids', [])) <= covered | set(group.get('read_blocks', [])):
                raise ValueError('relation READ omits declared endpoint extent')
