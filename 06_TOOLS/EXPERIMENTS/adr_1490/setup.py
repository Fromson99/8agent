"""Freeze ADR-1490 before any model call. baseline = selected MAIN203 release code, candidate = staged MAIN203 +
the reply/review loosening (corrected_memory, memory_methods, request_report). Public documents only.
Three new ask-back chats on both arms (the field photos of 2026-11-11), and the ADR-1457 eight branch chats on the candidate only."""
from common import *
import shutil
DES.mkdir(parents=True, exist_ok=False)
ptr = read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); assert ptr['generation'] == 204 and ptr['release_id'] == 'sql-loops-20261111-r1'
rel = read(ROOT/ptr['manifest_path']); B = ROOT/rel['code_root']; files = rel['files']
assert all(sha(B/n) == h for n, h in files.items())
STAGED = ROOT/'09_ARTIFACTS/AUDITS/20261111-multiturn-loosen/r2/staged'
inventory = {n: sha(STAGED/n) for n in files}
changed = sorted(n for n in files if inventory[n] != files[n]); assert len(changed) == 34, len(changed)
public = read(B/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
def st(n, q, expect, mode=None, article=None): return {'number': n, 'question': q, 'mode': mode, 'expect': expect, 'article': article}
Q1 = '현업에서 심사검토기간을 10일 정도 줬는데 적정한거야?'
Q2 = '회사에서 공시 준비기간을 5일로 잡았는데 괜찮은 거야?'
Q3 = '이 거래 승인은 누가 해야 돼?'
Q4 = '이 업무 기한을 10일로 둬도 돼?'
new = [
 {'id': 'r1-review-period', 'arms': ['baseline', 'candidate'], 'steps': [st(1, Q1, 'any', '외규'), st(2, '증권 인수업무 쪽을 알려줘', 'continue:1'), st(3, '“'+Q1+'”에 이어서 확인해줘', 'continue:1')]},
 {'id': 'r2-disclosure-period', 'arms': ['baseline', 'candidate'], 'steps': [st(1, Q2, 'any', '외규'), st(2, '유상증자 증권신고서 쪽이야', 'continue:1'), st(3, '“'+Q2+'”에 이어서 확인해줘', 'continue:1')]},
 {'id': 'r3-approval', 'arms': ['baseline', 'candidate'], 'steps': [st(1, Q3, 'any', '외규'), st(2, '이사와 회사 간 거래 쪽이야', 'continue:1'), st(3, '“'+Q3+'”에 이어서 확인해줘', 'continue:1')]},
 {'id': 'r4-vague-deadline', 'arms': ['baseline', 'candidate'], 'steps': [st(1, Q4, 'any', '외규'), st(2, '증권신고서 심사 업무 쪽이야', 'continue:1'), st(3, '“'+Q4+'”에 이어서 확인해줘', 'continue:1')]}]
old = read(ROOT/'04_EXPERIMENTS/ADR/ADR-1457-multiturn-followups-r15-qwen/artifacts/design/live-cases.json')
for c in old: c['arms'] = ['candidate']
new = [c for c in new if c['id'] == 'r2-disclosure-period']; new[0]['arms'] = ['candidate']
cases = new+old
for c in cases: c['document_ids'] = public
criteria = {'authorization': '싹다 수정하고 qwen으로 실험하고 메인에 반영해줘 그리고 우리 멀티턴은 로그가 안남는것 같은데 (2026-11-11); public documents only, no internal rules',
 'scope': 'Actual arm service.py, isolated runtime, selected SQLite source, public allowlist ∩ financial_team, default guided profile, one process per chat, LOG=on into the cell. New ask-back chats on both arms; the eight ADR-1457 chats on the candidate only.',
 'expect_rules': {'any': 'turn 1, not graded (recorded: whether it asked back)', 'new': 'CASE_START', 'continue:n': 'executes the goal created by turn n', 'background:n,m': 'CASE_START', 'ask': 'CLARIFY naming an earlier question'},
 'primary_metric': 'Candidate: graded turns whose branch matches the frozen expectation; replies not re-asked as "새 질문/이어서" (text "판단이 엇갈려" absent).',
 'secondary': ['Baseline reproduces the field ask-back on the new chats (observation)', 'Eight regression chats not worse than ADR-1457 r15 19/20 (reference, different base release)', '.log contains MULTITURN blocks on candidate turns', 'Source/ACL/wire integrity, UNKNOWN recorded'],
 'limits': {'physical_total': 700, 'per_cell_client_calls': 120, 'per_request': 40, 'per_physical_seconds': 180, 'reported_cost_usd': 5.0, 'time_box_minutes': 300, 'workers': 1},
 'stop': 'UNKNOWN or a resource stop ends that chat without retry; three consecutive chats with UNKNOWN, a third resource stop, source/ACL/code violation, budget or time box stop the batch. Each chat waits for other sessions pytest workers to end and 8GiB available before it starts (ADR-1488 stopped on swap from a concurrent test run).',
 'quality_certified': False, 'in_sample': True, 'note': 'One run per arm/chat. Turn 1 may answer instead of asking back; recorded. Internal rules of the field photos are not sent; these are public-document analogues. Runs what ADR-1489 left (r2 candidate, the eight regression chats) on the final candidate (MAIN204 + the same three files + the log fix).'}
put(DES/'criteria.json', criteria); put(DES/'live-cases.json', cases)
put(DES/'provider-policy.json', read(B/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')); assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json') == read(DES/'provider-policy.json')
put(DES/'authorization.json', {'request': criteria['authorization'], 'documents': public, 'scope': 'Public-law scenarios; intersect current financial team. No internal documents or grading answers are sent.'})
transport = ART/'transport'; transport.mkdir()
pins = read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    t = transport/name; t.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, t); pins['files'][name] = sha(t)
put(transport/'transport-pins.json', pins)
m = read(ADR/'실험/manifest.json')
m['runs'] = [{**m['runs'][0], 'id': 'run-001', 'purpose': 'primary'}] if m.get('runs') else m.get('runs')
put(ADR/'실험/manifest.json', m)
# Selected-release code is not in the shared working tree (behind since MAIN188): freeze a hash-pinned copy of the tested stage.
snapshot = ART/'candidate-code'
for n in files:
    (snapshot/n).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(STAGED/n, snapshot/n)
assert all(sha(snapshot/n) == h for n, h in inventory.items())
arms = {'baseline': {'code_root': rel['code_root'], 'files': files, 'label': 'sql-loops-20261111-r1 (MAIN204)'},
        'candidate': {'code_root': str(snapshot.relative_to(ROOT)), 'files': inventory, 'label': 'MAIN203 + reply/review loosening', 'changed_vs_main203': changed,
                      'tested_copy': str(STAGED.relative_to(ROOT)), 'contract_regression': '09_ARTIFACTS/AUDITS/20261111-multiturn-loosen/r2/regression-compare.json', 'oracle_guard': '09_ARTIFACTS/AUDITS/20261111-multiturn-loosen/r2/oracle-guard/보고서.txt'}}
put(DES/'arms.json', arms)
m['lineage']['hypothesis_delta'] = 'A reply to what the system asked continues that question (prompt rule in the related choice, the command and the review); a disagreement about which kind of continuation is recorded, not refused; an explicit reply is not asked again; the .log names the selection, proposal and refusal.'
m['design'].update(hypothesis=m['lineage']['hypothesis_delta'], primary_metric=criteria['primary_metric'], success_criteria=[criteria['primary_metric'], *criteria['secondary']], failure_criteria=[criteria['stop']], criteria_frozen_before_run=True, criteria_freeze_evidence={'path': str((DES/'criteria.json').relative_to(ROOT)), 'sha256': sha(DES/'criteria.json')})
m['dataset'].update(name='Ask-back replies + ADR-1457 branch chats (public documents)', version='frozen-v1', frozen_source=str((DES/'live-cases.json').relative_to(ROOT)), sha256=sha(DES/'live-cases.json'), legal_version_checked=True, reference_version_checked=False)
m['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1}]
put(ADR/'실험/manifest.json', m)
paths = [*Path(__file__).parent.glob('*.py'), *(DES/x for x in ('criteria.json', 'live-cases.json', 'authorization.json', 'provider-policy.json', 'arms.json'))]
put(DES/'freeze-live.json', {'files': {str(p.relative_to(ROOT)): sha(p) for p in paths}, 'selected_pointer': ptr, 'source_manifest_sha256': rel['data_manifest_sha256'], 'model_calls_before_freeze': 0})
print('FROZEN', len(cases), 'chats;', len(changed), 'files changed; model 0')
