"""Run the added original-use check against the exact 29 earlier accepted generations."""
from common import *
frozen=read(DES/'candidate-repaired.json')
sys.path.insert(0,str(ROOT/frozen['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent.need_continuity import _validate_assigned_uses
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1372-assigned-original-use-repair-feedback/artifacts/previous-accepted-output-check.json'
matrix=ROOT/'04_EXPERIMENTS/ADR/ADR-1370-integration-oneclick-provider-repeat/artifacts/public-live'
rows=read(prior)['cases']
for row in rows:
    path=matrix/(row['case_id']+'-reka')/'raw'/('call-%03d'%row['call'])/'response.json.gz'
    assert sha(path)==row['recorded_output_sha256']
    raw=json.loads(read(path)['choices'][0]['message']['content'])
    assert len(raw['read_judgment_review']['original_reviews'])==row['checked_assignments']
    _validate_assigned_uses(raw)
put(ART/'previous-accepted-output-check.json',{'cases':rows,'checked':len(rows),'model_calls':0,
    'scope':'Original-use contract only. Extra dependent-need feedback runs solely inside the existing rejection.'})
