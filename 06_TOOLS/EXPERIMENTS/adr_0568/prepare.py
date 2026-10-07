"""Prepare isolated action-plan + SQL scope candidate before any effect call."""
from pathlib import Path
import hashlib
import json
import shutil

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql'
D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0568/integrated'
P=R/'04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def main():
    D.mkdir(exist_ok=False)
    for name in ['corpus.json','cases.json','expected-offline.json','ontology.json','schemas.json','prompts.json']:
        shutil.copyfile(P/'artifacts/design'/name,D/name)
    # Parent gold remains byte identical. No prior answer enters the product.
    prompt=json.loads((D/'prompts.json').read_text());prompt.pop('classifier');write(D/'prompts.json',prompt)
    schemas=json.loads((D/'schemas.json').read_text());schemas.pop('classifier');write(D/'schemas.json',schemas)
    planner=C/'snapshot/02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py'
    planner.write_text(planner.read_text()+'''

# ADR-0568: existing catalogue call produces semantic context per search action.
ACTION_SYSTEM = CATALOGUE_SYSTEM + """
SEARCH에서 검색할 각 query마다 search_actions에 동일한 순서로 행동 근거를 기록한다.
각 행동에는 query, reason, expected_information, concept_refs가 있다.
concept_refs는 supplied investigation_concepts에서 이번 행동이 확인하려는 정보에 해당하는
개념 ID를 최대1개 고른다. 불명확하거나 여러 목적이 섞인 행동은 빈 배열로 남긴다.
질문 전체의 주제 대신 해당 검색 행동의 이유·기대 정보를 기준으로 고른다.
서로 다른 정보를 확인하는 복합 질문은 검색 행동을 분리한다. 규정 적용·요건·예외·절차
확인과 업무 실적 수치 확인을 하나의 행동에 합치지 않는다. 자료 목록 조회는 규정 적용이 아니다.
각 query는 그 행동의 기대 정보에 맞게 만든다. BROWSE/DIRECT/OUT_OF_DOMAIN의 search_actions는 비운다.
concept_refs는 근거 탐색의 맥락 참조이며 법률 결론이나 자료 제외 지시가 아니다.
reason과 expected_information은 각각50자 이내로 간결하게 쓴다.
"""

def action_catalogue_schema(names, concept_ids):
    value=catalogue_schema(names)
    action={'type':'object','additionalProperties':False,'properties':{
        'query':{'type':'string','minLength':2,'maxLength':250},
        'reason':{'type':'string','minLength':1,'maxLength':200},
        'expected_information':{'type':'string','minLength':1,'maxLength':200},
        'concept_refs':{'type':'array','uniqueItems':True,'maxItems':1,
                        'items':{'type':'string','enum':concept_ids}}},
        'required':['query','reason','expected_information','concept_refs']}
    value['properties']['search_actions']={'type':'array','maxItems':4,'items':action}
    value['required'].append('search_actions')
    return value

def validate_action_catalogue(value,names,concept_ids):
    jsonschema.validate(value,action_catalogue_schema(names,concept_ids))
    validate_catalogue({k:v for k,v in value.items() if k!='search_actions'},names)
    if [a['query'] for a in value['search_actions']] != value['queries']:
        raise ValueError('each planned query must have one action context in matching order')
    return value
''')
    # Per-query scopes constrain rank; aggregate union constrains reference/READ.
    for name in ['source_recall.py','source_recall_global.py']:
        p=C/'snapshot/02_BACKEND/semantic_runtime/legal_agent'/name;text=p.read_text()
        needle='        self.scores = defaultdict(float)';assert text.count(needle)==1
        text=text.replace(needle,'        policy_scope = getattr(sources, "investigation_allowed_source_ids", None)\n'
                               '        if policy_scope is not None:\n            self.allowed &= set(policy_scope)\n'+needle)
        old='            ids = self.s.matcher.fulltext.rank(self.s.matcher.fulltext_db, terms, self.allowed)'
        new='            scope_for_query = getattr(self.s, "investigation_query_scope", None)\n'
        new+='            allowed = self.allowed if scope_for_query is None else self.allowed & set(scope_for_query(variant))\n'
        new+='            ids = self.s.matcher.fulltext.rank(self.s.matcher.fulltext_db, terms, allowed)'
        assert text.count(old)==1;text=text.replace(old,new);p.write_text(text)
    p=C/'snapshot/02_BACKEND/semantic_runtime/fulltext.py';text=p.read_text()
    text=text.replace('def rank(self, db, terms, allowed=None, limit=None):','def rank(self, db, terms, allowed=None, limit=None, *, eligible_rowids=None):')
    text=text.replace('        out = []\n        tied = []',
        '        params = [expression(terms), rank]\n'
        '        if eligible_rowids is not None:\n'
        '            eligible_rowids = sorted(set(eligible_rowids))\n'
        '            if not eligible_rowids:\n                return []\n'
        '            if not all(type(r) is int and r > 0 for r in eligible_rowids):\n                raise ValueError("invalid current FTS row projection")\n'
        '            sql = sql.replace(" ORDER BY rank", " AND rowid IN (" + ",".join("?" for _ in eligible_rowids) + ") ORDER BY rank")\n'
        '            params.extend(eligible_rowids)\n'
        '        out = []\n        tied = []')
    text=text.replace('lambda:db.execute(sql,(expression(terms),rank))','lambda:db.execute(sql,params)')
    p.write_text(text)
    old=R/'02_BACKEND/lawrag/research/candidates/adr_0567/graph/revisions/rev-001/snapshot/02_BACKEND/lawrag/core/investigation_graph.py'
    dest=C/'snapshot/02_BACKEND/lawrag/core/investigation_graph.py';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old,dest)
    write(D/'concept-catalogue.json',[{'id':'purpose:applicable','label':'확인 중인 규정의 적용요건·정의·예외·절차'},
        {'id':'purpose:performance','label':'업무 실적 통계의 수치·관측'},
        {'id':'purpose:inventory','label':'보유 자료의 전체 목록·종류'}])
    write(D/'criteria.json',{'primary':'candidate-only answer/evidence regressions0; all required originals presented; standalone purpose calls0; genuine mixed action scopes; SQL results subset of precompiled graph scope',
        'functional_score':'same byte-identical parent required citation/term rubric retained; common parent missing general-rule citation disclosed separately, no silent gold relaxation',
        'mixed_gate':'MIX-01 plan includes separate applicable and performance action contexts; applicable query returns no performance-class nodes; performance query retains required performance original',
        'efficiency':'APP read reduction >=30%; SQL fetched rows fewer on constrained searches; product token/cost/wall reported, no speed certification from7case single repeat',
        'guards':'unknown/ambiguous references do not exclude; unsupported concept IDs rejected; current version mismatch reverts before SQL; direct/ancestor READ cannot bypass scope; SQL score order/ties equal baseline allowed filtering',
        'controls':'same corpus/gold/model/native source-selection/answer; real catalogue planning once each arm; candidate extends output per action and SQL rowid constraints; all catalogue prompt/body/schema pinned',
        'routing':'BROWSE executes native browse then shared deterministic original-search continuation to honor example-original request; not full BoundedSourceSession browse/Compose',
        'call_policy':'Gemma Parasail FP8 thinking off; max1536; schema in prompt; retries/repairs0; each case alternate arm order; failed calls retained',
        'scope':'in-sample synthetic hand-curated graph; excludes real log-learning and GENOS/NFS certification'})
    pins=json.loads((P/'artifacts/design/code-pins.json').read_text())
    extra=[R/'06_TOOLS/EXPERIMENTS/adr_0567/run.py',R/'02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py',
           R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
    for f in extra:pins[str(f.relative_to(R))]=sha(f)
    write(D/'code-pins.json',pins)
    write(D/'upstream-receipts.json',{'parent_gold_path':str((P/'artifacts/design/expected-offline.json').relative_to(R)),
        'parent_gold_sha256':sha(P/'artifacts/design/expected-offline.json'),
        'parent_graph_path':str(old.relative_to(R)),'parent_graph_sha256':sha(old),
        'sql_scope_note':'FTS rowid adapter is index-version-bound projection of generic source-node eligibility; core graph has no fulltext dependency'})
    print('Prepared integrated existing-planner action contexts, pre-execution SQL scope, parent gold unchanged.')


if __name__=='__main__':main()
