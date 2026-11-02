"""Read-only inspection and deterministic evaluator probes; no model client."""
from common import *
import ast
f=read(DES/'freeze.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import scenario_facts
from lawrag.legal_knowledge.ontology import evaluate
modules=['scenario_branch','scenario_facts','scenario_review','review_actions']
checks=[]
for name in modules:
 p=C/'02_BACKEND/semantic_runtime/legal_agent'/f'{name}.py'
 tree=ast.parse(p.read_text());strings={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
 checks.append({'module':name,'sha256':sha(p),'exact_case_literals_found':sorted(strings & {'cost','limit','1500000','500000','1000000','1380000','735000','1725000','2450000','작업 비용','가정검증규정'}),
 'numeric_literals':sorted({str(n.value) for n in ast.walk(tree) if isinstance(n,ast.Constant) and type(n.value) in (int,float)}),
 'fixed_approval_guidance':[s for s in strings if '승인' in s]})
rows=[]
for key,ceiling,amount,expected in [('spend_zeta','937','936','TRUE'),('importe','937','938','FALSE'),('ledger_quantity','2400000','2399999','TRUE'),('ledger_quantity','2400000','2400001','FALSE')]:
 field={'kind':'FACT','type':'money','unit':'KRW'};state={'facts':[{'name':'자유 입력 이름','value':amount+'원'}]}
 ids=scenario_facts.options(state);bound,values,_=scenario_facts.bind(state,{key:field},{key:[ids[0]['id']]})
 expression={'op':'lte','args':[{'field':key},{'literal':{'type':'money','unit':'KRW','value':ceiling}}]}
 result=evaluate(expression,{key:{'status':'ASSERTED','origin_ref':'explicit-test-binding','value':values[key]}},binding='read-only-probe')
 assert result['status']==expected
 rows.append({'field':key,'amount':amount,'threshold':ceiling,'expected':expected,'actual':result['status']})
put(ART/'hardcoding-audit.json',{'candidate_revision':f['candidate_revision'],'modules':checks,'generic_numeric_probes':rows,'case_literal_branch_found':any(c['exact_case_literals_found'] for c in checks),'limitations':'Literal inspection and four deterministic probes are not proof of all semantic correctness. Fixed type/unit/review safety policies are intentional. Approval wording exists in general guidance, not amount-specific outcomes.'})
print('Inspected4 modules; generic renamed-field probes4 passed; exact case literals',sum(len(c['exact_case_literals_found']) for c in checks))
