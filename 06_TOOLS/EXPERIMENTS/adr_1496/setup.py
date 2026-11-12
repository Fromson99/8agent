"""Freeze ADR-1496 before any model call. baseline = selected MAIN205 release code; candidate = that MAIN + legal-links-bundle-r1
(staged2 of 09_ARTIFACTS/AUDITS/20261111-merged-candidate-r2). Public documents only; each question once per arm."""
from common import *
import shutil
DES.mkdir(parents=True, exist_ok=False)
ptr = read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); assert ptr['generation'] == 205 and ptr['release_id'] == 'multiturn-reply-20261111-r1'
rel = read(ROOT/ptr['manifest_path']); B = ROOT/rel['code_root']; files = rel['files']
assert all(sha(B/n) == h for n, h in files.items())
STAGED = ROOT/'09_ARTIFACTS/AUDITS/20261111-merged-candidate-r2/staged2'
inventory = {str(p.relative_to(STAGED)): sha(p) for p in sorted(STAGED.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
changed = sorted(n for n in inventory if inventory[n] != files.get(n)); assert len(changed) == 47, len(changed)
public = read(B/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
def case(cid, question, targets, team='financial_team'):
    return {'id': cid, 'arms': ['baseline', 'candidate'], 'document_ids': public, 'targets': targets, 'team': team,
            'steps': [{'number': 1, 'question': question, 'mode': '외규', 'expect': 'any', 'article': None}]}
cases = [
 case('cm-030', 'IPO를 위한 증권신고서 제출 시 1분기 검토보고서를 첨부하여야 하는가?', ['제2-6조', '제2-4조']),
 case('cfd-limit', '금융투자회사가 차액결제거래를 매매·중개할 때 지켜야 하는 한도는 얼마이고 어떻게 계산하나요?', ['제5-49조의2'], team='risk_team'),
 case('bw-pricing', '신주인수권부사채를 발행할 때 행사가격은 어떤 기준으로 정해야 하나요?', ['제5-21조', '제5-22조'])]
criteria = {'authorization': '실모델 몇개만 돌려봐 3개정도 (2026-11-11); public documents only, CM questions approved in CM_EXPORT_AUTHORIZATION_20261024, no reference answers sent',
 'scope': 'Actual arm service.py, isolated runtime, selected SQLite source, public allowlist ∩ the case team (financial_team; risk_team for cfd-limit, whose documents are only there), default guided profile, one process per question, hyphen parameters at their defaults.',
 'primary_metric': 'Per question and arm: every target article acquired by the end of the turn (journal/response source ids), and how many are cited in the answer.',
 'secondary': ['Physical model calls per question: candidate not above baseline + 2', 'No UNKNOWN, source, ACL or code binding violation', 'Answer body carries the unread line, not the unread list'],
 'limits': {'physical_total': 90, 'per_cell_client_calls': 60, 'per_request': 40, 'per_physical_seconds': 180, 'reported_cost_usd': 1.0, 'time_box_minutes': 35, 'workers': 1},
 'stop': 'UNKNOWN or a resource stop ends that cell without retry; three consecutive cells with UNKNOWN, a third resource stop, source/ACL/code violation, budget or time box stop the batch.',
 'quality_certified': False, 'in_sample': True, 'note': 'Questions were picked after reading the provisions to exercise the changes; one run per arm. Probe only, not a quality or adoption claim.'}
put(DES/'criteria.json', criteria); put(DES/'live-cases.json', cases)
put(DES/'provider-policy.json', read(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')); assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json') == read(DES/'provider-policy.json')
put(DES/'authorization.json', {'request': criteria['authorization'], 'documents': public, 'scope': 'Public-law questions; intersect current financial team. No internal documents or grading answers are sent.'})
transport = ART/'transport'; transport.mkdir()
pins = read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    t = transport/name; t.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, t); pins['files'][name] = sha(t)
put(transport/'transport-pins.json', pins)
snapshot = ART/'candidate-code'
for n in inventory:
    (snapshot/n).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(STAGED/n, snapshot/n)
assert all(sha(snapshot/n) == h for n, h in inventory.items())
put(DES/'arms.json', {'baseline': {'code_root': rel['code_root'], 'files': files, 'label': 'multiturn-reply-20261111-r1 (MAIN205)'},
    'candidate': {'code_root': str(snapshot.relative_to(ROOT)), 'files': inventory, 'label': 'MAIN205 + legal-links-bundle-r1', 'changed': changed,
                  'contract_regression': '09_ARTIFACTS/AUDITS/20261111-merged-candidate-r2/regression-compare.json', 'oracle_guard': '09_ARTIFACTS/AUDITS/20261111-merged-candidate-r2/guard/보고서.txt'}})
m = read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta'] = 'A citation naming a document and hyphen article reaches that article without extra model calls; the bundle does not raise calls.'
m['design'].update(hypothesis=m['lineage']['hypothesis_delta'], primary_metric=criteria['primary_metric'], success_criteria=[criteria['primary_metric'], *criteria['secondary']], failure_criteria=[criteria['stop']], criteria_frozen=True)
m['dataset'].update(name='Three public-document questions', version='frozen-v1', frozen_source=str((DES/'live-cases.json').relative_to(ROOT)), sha256=sha(DES/'live-cases.json'), legal_version_checked=True)
m['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1}]
put(ADR/'실험/manifest.json', m)
paths = [*Path(__file__).parent.glob('*.py'), *(DES/x for x in ('criteria.json', 'live-cases.json', 'authorization.json', 'provider-policy.json', 'arms.json'))]
put(DES/'freeze-live.json', {'files': {str(p.relative_to(ROOT)): sha(p) for p in paths}, 'selected_pointer': ptr, 'source_manifest_sha256': rel['data_manifest_sha256'], 'model_calls_before_freeze': 0})
print('FROZEN', len(cases), 'questions;', len(changed), 'files changed; model 0')
