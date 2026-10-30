"""Qualification for a measured release, separate from historical waivers."""
import json
from pathlib import Path
from .contracts import sha


def bound(root, binding):
    if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
        raise ValueError('qualification requires exact path/hash binding')
    path = (root / binding['path']).resolve()
    if Path(binding['path']).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('qualification path outside workspace')
    if not path.is_file() or sha(path) != binding['sha256']:
        raise ValueError('qualification artifact drift')
    return path


def verify(root, authorization, report):
    """Recheck the completed source and frozen rebase on prepare and apply."""
    root = Path(root).resolve()
    q = authorization.get('qualification')
    if not isinstance(q, dict) or set(q) != {'source', 'readme', 'arm', 'result', 'rebase'}:
        raise ValueError('qualified release authorization is incomplete')
    if authorization.get('quality_gate_override') is not False:
        raise ValueError('qualified release cannot use a quality waiver')
    source_path = bound(root, q['source'])
    readme_path = bound(root, q['readme'])
    if source_path.name != 'manifest.json' or source_path.parent.name != '실험' or readme_path != source_path.parent.parent / 'README.md':
        raise ValueError('qualification must reference an ADR source')
    source = json.loads(source_path.read_text())
    text = readme_path.read_text().split('---', 2)
    meta = dict(line.split(':', 1) for line in text[1].splitlines() if ':' in line) if len(text) > 2 else {}
    if meta.get('status', '').strip() != 'Accepted' or meta.get('main_wiring', '').strip() != 'promotion-candidate':
        raise ValueError('qualified source must be Accepted promotion-candidate')
    if source.get('in_sample') is not False or source.get('decision_eligible') is not True:
        raise ValueError('qualified source requires out-of-sample decision eligibility')
    if source.get('reservation', {}).get('status') != 'completed' or source.get('results', {}).get('status') != 'complete':
        raise ValueError('qualified source must be completed')
    arm = source.get('results', {}).get('by_arm', {}).get(q['arm'], {})
    if arm.get('status') != 'complete':
        raise ValueError('qualified arm must be complete')
    result_path = bound(root, q['result'])
    result = json.loads(result_path.read_text())
    if result.get('strict_success') is not True or not result.get('checks') or not all(v is True for v in result['checks'].values()):
        raise ValueError('qualified result checks must all pass')
    if not any(r.get('artifact_path') == q['result']['path'] and r.get('sha256') == q['result']['sha256'] and q['arm'] in r.get('arm_ids', []) and r.get('status') == 'complete' for r in source.get('runs', [])):
        raise ValueError('qualified result is not the completed source run')
    bound(root, q['rebase'])
    if source.get('design', {}).get('release_rebase') != q['rebase'] or report.get('integration', {}).get('rebase_receipt') != q['rebase']:
        raise ValueError('qualified rebase differs from frozen evaluation')
    if report.get('structural_checks_passed') is not True:
        raise ValueError('qualified release structural checks failed')
    return q
