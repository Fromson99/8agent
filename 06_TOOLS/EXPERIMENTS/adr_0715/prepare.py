"""Freeze new audit inputs without running or importing the deduction kernel."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
import json
import random

ROOT = Path.cwd()
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0715-deduction-execution-audit'
PARENT = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0713/lab/revisions/rev-007/snapshot'
SCOPE = dict(jurisdiction='SYNTHETIC', generation='audit-v1', valid_from='2020-01-01', valid_to='2099-12-31')
CTX = dict(jurisdiction='SYNTHETIC', generation='audit-v1', date='2026-10-09', case_id='audit-case', principal='local-operator', entities={x:'Entity' for x in ['a','b','c','d']})

def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def atom(p, *args, neg=False):
    return dict(predicate=p, args=list(args or ('?x',)), negative=neg)

def rule(id, body, head, **kw):
    return dict(id=id, revision=1, kind='RULE', body=body, head=head,
        scope=deepcopy(SCOPE), source_refs=[dict(id='synthetic:'+id, revision='1', kind='SYNTHETIC')],
        assumptions=[], assessments=dict(formalization='REVIEWED', source='VERIFIED'),
        access=['*'], external_export_allowed=False, state='ACTIVE') | kw

def case(id, rules, facts, goal, expected, **extra):
    ats=[goal]+facts+[a for r in rules for a in r['body']+[r['head']]+r.get('guards',[])]
    arities={a['predicate']:len(a['args']) for a in ats}
    return dict(id=id, kb=dict(schema_version='legal-logic-unit-v1', predicates=[dict(id=p,label=p,types=['Entity']*n) for p,n in arities.items()], units=rules),
        facts=[dict(id=f'f{i}',atom=a,case_id=CTX['case_id'],scope=deepcopy(SCOPE)) for i,a in enumerate(facts)],
        goal=goal, context=deepcopy(CTX), expected=expected, **extra)

def build():
    a=atom; r=rule
    chain=[r('xy-a',[a('X'),a('Y')],a('A')),r('a-b',[a('A')],a('B')),r('bc-d',[a('B'),a('C')],a('D'))]
    cases=[]
    def add(id,rules,facts,goal,expected,**kw): cases.append(case(id,deepcopy(rules),facts,goal,expected,**kw))
    add('unseen-three-rule-path',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'CONDITIONAL', expect_dependencies=['xy-a','a-b','bc-d'])
    add('missing-c',chain,[a('X','a'),a('Y','a')],a('D','a'),'UNKNOWN', expect_missing=[a('C','a')])
    add('no-reverse-implication',chain,[a('D','a')],a('A','a'),'UNKNOWN')
    add('no-cross-subject-join',chain,[a('X','a'),a('Y','b'),a('C','a')],a('D','a'),'UNKNOWN')
    add('case-isolation',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'UNKNOWN')
    cases[-1]['facts'][1]['case_id']='other-case'
    add('effective-date-expired',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'UNKNOWN')
    cases[-1]['kb']['units'][1]['scope']['valid_to']='2026-10-08'
    add('unknown-jurisdiction',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'UNKNOWN')
    cases[-1]['kb']['units'][1]['scope']['jurisdiction']='UNKNOWN'
    add('access-denied',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'UNKNOWN')
    cases[-1]['kb']['units'][1]['access']=['another-operator']
    add('hypothesis-preserved',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'CONDITIONAL',expect_assumption='HYPOTHESIS:a-b')
    cases[-1]['kb']['units'][1]['kind']='HYPOTHESIS'
    add('source-unverified-preserved',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'CONDITIONAL',expect_assumption='SOURCE_UNVERIFIED:a-b')
    cases[-1]['kb']['units'][1]['assessments']['source']='UNVERIFIED'
    add('unreviewed-formalization',chain,[a('X','a'),a('Y','a'),a('C','a')],a('D','a'),'UNKNOWN')
    cases[-1]['kb']['units'][1]['assessments']['formalization']='DRAFT'
    add('intermediate-conflict',chain,[a('X','a'),a('Y','a'),a('C','a'),a('B','a',neg=True)],a('D','a'),'UNKNOWN')
    add('goal-conflict',chain,[a('X','a'),a('Y','a'),a('C','a'),a('D','a',neg=True)],a('D','a'),'CONFLICT')
    add('independent-proof-survives-conflict',chain+[r('z-d',[a('Z')],a('D'))],
        [a('X','a'),a('Y','a'),a('C','a'),a('B','a',neg=True),a('Z','a')],a('D','a'),'CONDITIONAL',expect_dependencies=['z-d'])
    add('unrelated-conflict-no-explosion',chain,[a('Z','a'),a('Z','a',neg=True)],a('D','a'),'UNKNOWN')
    guard=[r('guarded',[a('A')],a('D'),guards=[a('Except',neg=True)],exceptions=['Except'],exceptions_resolved=True)]
    add('absence-is-not-negation',guard,[a('A','a')],a('D','a'),'UNKNOWN')
    add('explicit-exception-clearance',guard,[a('A','a'),a('Except','a',neg=True)],a('D','a'),'CONDITIONAL')
    add('unresolved-exception',guard,[a('A','a'),a('Except','a',neg=True)],a('D','a'),'UNKNOWN')
    cases[-1]['kb']['units'][0]['exceptions_resolved']=False
    add('cycle-without-seed',[r('ab',[a('A')],a('B')),r('ba',[a('B')],a('A'))],[],a('B','a'),'UNKNOWN')
    add('cycle-with-seed',[r('ab',[a('A')],a('B')),r('ba',[a('B')],a('A'))],[a('A','a')],a('B','a'),'CONDITIONAL')
    definition=[r('def-k',[a('A'),a('C')],a('K'),kind='DEFINITION'),r('ac-d',[a('A'),a('C')],a('D'))]
    add('definition-unfold',definition,[a('K','a')],a('D','a'),'CONDITIONAL')
    add('effect-not-definition',definition,[a('D','a')],a('K','a'),'UNKNOWN')
    join=[r('join3',[a('Owns','?x','?y'),a('Tagged','?y','?z'),a('Ready','?z')],a('Eligible','?x'))]
    add('three-variable-relational-join',join,[a('Owns','a','b'),a('Tagged','b','c'),a('Ready','c')],a('Eligible','a'),'CONDITIONAL')
    add('relational-join-mismatch',join,[a('Owns','a','b'),a('Tagged','d','c'),a('Ready','c')],a('Eligible','a'),'UNKNOWN')
    add('missing-relational-exact-target',join,[a('Owns','a','b'),a('Tagged','b','c')],a('Eligible','a'),'UNKNOWN',expect_missing=[a('Ready','c')])
    add('missing-prefers-available-branch',join,[a('Owns','a','b'),a('Owns','a','c'),a('Tagged','c','d')],a('Eligible','a'),'UNKNOWN',expect_missing=[a('Ready','d')])
    add('repeated-variable-blocks-mismatch',[r('self',[a('Rel','?x','?x')],a('Self','?x'))],[a('Rel','a','b')],a('Self','a'),'UNKNOWN')
    add('repeated-variable-matches',[r('self',[a('Rel','?x','?x')],a('Self','?x'))],[a('Rel','a','a')],a('Self','a'),'CONDITIONAL')
    fact=r('reviewed-case-fact',[],a('A','a'),kind='FACT',case_id=CTX['case_id'])
    add('reviewed-case-fact-proof',[fact,r('ab',[a('A')],a('B'))],[],a('B','a'),'PROVED')
    add('retired-primary-independent-proof',chain+[r('z-d',[a('Z')],a('D'))],[a('Z','a')],a('D','a'),'CONDITIONAL',expect_dependencies=['z-d'])
    cases[-1]['kb']['units'][1]['state']='RETIRED'
    add('depth-limit-fails-closed',[r(f'r{i}',[a(f'P{i}')],a(f'P{i+1}')) for i in range(18)],[a('P0','a')],a('P18','a'),'LIMIT_REACHED')
    add('many-independent-supports',[r(f'p{i}-d',[a(f'P{i}')],a('D')) for i in range(9)],[a(f'P{i}','a') for i in range(9)],a('D','a'),'CONDITIONAL')
    add('unrelated-support-limit',[r(f'p{i}-d',[a(f'P{i}')],a('D')) for i in range(9)],[a(f'P{i}','a') for i in range(9)]+[a('Known','a')],a('Known','a'),'CONDITIONAL')
    # Clearly fictional compliance terminology exercises entity types and joins;
    # these are not assertions about actual legislation.
    legal=[r('wiki:control',[a('Controls','?firm','?fund')],a('Managed','?fund')),
           r('wiki:approval',[a('Managed','?fund'),a('Leverage','?fund')],a('ApprovalNeeded','?fund')),
           r('wiki:notice',[a('ApprovalNeeded','?fund'),a('Manager','?person','?fund')],a('MustNotify','?person','?fund'))]
    add('fictional-compliance-new-route',legal,[a('Controls','a','b'),a('Leverage','b'),a('Manager','c','b')],a('MustNotify','c','b'),'CONDITIONAL',expect_dependencies=['wiki:control','wiki:approval','wiki:notice'])
    add('fictional-compliance-wrong-fund',legal,[a('Controls','a','b'),a('Leverage','d'),a('Manager','c','b')],a('MustNotify','c','b'),'UNKNOWN')
    # Seed and generation are fixed here before any implementation outputs.
    rng=random.Random(202610090715)
    generated=[]
    for n in range(100):
        rules=[]
        for j in range(6):
            p,q,h=rng.choices(['A','B','C','D','E','F'],k=3)
            form=rng.randrange(5)
            body=[a(p)] if form==0 else [a(p),a(q)] if form==1 else [a('R','?x','?y'),a(p,'?y')] if form==2 else [a('R','?y','?x'),a(p,'?y')] if form==3 else [a('R','?x','?x'),a(p)]
            rules.append(r(f'g{n}-r{j}',body,a(h)))
        facts=[a(p,x) for p in ['A','B','C'] for x in ['a','b','c'] if rng.random()<.38]
        facts += [a('R',x,y) for x in ['a','b','c'] for y in ['a','b','c'] if rng.random()<.2]
        c=case(f'generated-{n:03}',rules,facts,a('F','a'),None)
        c['kb']['predicates']=[dict(id=p,label=p,types=['Entity']*(2 if p=='R' else 1)) for p in ['A','B','C','D','E','F','R']]
        c['goals']=[a(p,x) for p in ['A','D','E','F'] for x in ['a','b','c']]
        generated.append(c)
    return dict(schema_version='deduction-audit-inputs-v1',seed=202610090715,synthetic=True,handcrafted=cases,generated=generated)

if __name__=='__main__':
    data=build()
    put(ADR/'artifacts/design/inputs.json',data)
    plan=dict(hypothesis='The frozen rev007 kernel agrees with an independently grounded least-fixed-point oracle on finite positive Horn inputs and preserves guards, scope and dependencies in real HTTP/storage execution.',
        success_criteria=['No false positive proof; zero small-input closure discrepancies or proof replay failures',
                          'All handcrafted expected states and precise missing obligations match',
                          'HTTP compose/store/reload/reuse/withdrawal and nested dependency invalidation work',
                          'MAIN pointer and frozen parent bytes remain unchanged'],
        failure_criteria='Any expected mismatch is retained; LIMIT_REACHED is incompleteness, never a correct proof. No threshold relaxed after results.',
        oracle='Enumerate every rule variable assignment over finite declared entities, then apply ground implications to a set until no additions. No kernel helpers imported.',
        provenance='All facts and rules are synthetic. Fictional compliance rules only; no real legal answer-quality or natural-language formalization claim.',
        additional_checks=['symbolic compose + weak assumption', 'saved lemma used as proof root', 'HTTP restart persistence', 'nested parent invalidation', 'old proof with reordered units and independent new path', 'original 25 regression contracts'],
        selection='All 35 handcrafted cases plus all 100 seeded KBs x 12 goals, no selection by outcomes.',
        model_calls=0,main_wiring='unchanged',random_seed=data['seed'])
    plan['selection']=f"All {len(data['handcrafted'])} handcrafted cases plus all 100 seeded KBs x 12 goals, no selection by outcomes."
    put(ADR/'artifacts/design/plan.json',plan)
    sha=lambda p:sha256(p.read_bytes()).hexdigest()
    put(ADR/'artifacts/design/before.json',dict(pointer_sha256=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
        parent_files={str(f.relative_to(ROOT)):sha(f) for f in PARENT.rglob('*') if f.is_file() and '__pycache__' not in str(f)},
        working_files={p:sha(ROOT/p) for p in ['service.py','main.py','00_SYSTEM/PIPELINE.json','00_SYSTEM/WORKSPACE.json']}))
    m=json.loads((ADR/'실험/manifest.json').read_text())
    m['lineage']['hypothesis_delta']='Independent execution audit of unchanged parent rev007; no product logic change.'
    m['design'].update({k:plan[k] for k in ['hypothesis','success_criteria','failure_criteria']},primary_metric='Exact state/closure agreement, proof validity and HTTP storage behavior',criteria_frozen_before_run=True)
    for arm in m['design']['arms']:
        arm.update(changes='Pinned unchanged ADR0713 rev007' if arm['id']=='baseline' else 'Byte-identical isolated copy with new audit inputs',controls='No LLM; synthetic fixed inputs; expected results offline only; MAIN unchanged')
    m['runs'][0].update(selection_rule=plan['selection'],artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
    m['llm_policy']['llm_calls']=[]
    m['dataset'].update(name='Synthetic Horn execution and adversarial audit',version='deduction-audit-v1',frozen_source=str((ADR/'artifacts/design/inputs.json').relative_to(ROOT)),sha256=sha(ADR/'artifacts/design/inputs.json'))
    reason='No document retrieval or model answers; deterministic formal logic and persistence audit only'
    m['retrieval_accounting']['not_applicable_reason']=reason
    m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
    put(ADR/'실험/manifest.json',m)
    print('Frozen inputs:',len(data['handcrafted']),'handcrafted +',sum(len(c['goals']) for c in data['generated']),'oracle goals')
