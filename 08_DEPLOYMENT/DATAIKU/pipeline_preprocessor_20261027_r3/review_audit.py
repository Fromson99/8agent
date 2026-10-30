"""Keep existing parser/recipe evidence with Dataiku; no new model runner."""
import json
import hashlib
from pathlib import Path
import transport as t


def inventory(workspace, strict=True):
    root = Path(workspace) / '01_DATA/STRUCTURE'
    paths = {}
    reserved = 0
    errors = []
    for p in t.files(root) if root.exists() else []:
        if p.suffix not in {'.json', '.jsonl', '.log', '.txt'}:
            continue
        relative = str(p.relative_to(root))
        paths['audit/structure/' + relative] = p
        if p.parent.name == 'model-calls' and p.suffix == '.json':
            try:
                envelope = json.loads(p.read_text())
                ledger = envelope['state']
                digest = hashlib.sha256(json.dumps(ledger,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                count = sum(e.get('status') == 'RESERVED' for e in ledger.get('events', []))
                if envelope['sha256'] != digest or type(ledger.get('calls')) is not int or ledger['calls'] != count:
                    raise ValueError('REVIEW_CALL_LEDGER_MISMATCH')
                reserved += count
            except (KeyError, TypeError, ValueError):
                if strict:
                    raise ValueError('REVIEW_CALL_LEDGER_MISMATCH') from None
                errors.append(relative)
    return paths, {'reserved_model_calls': None if errors else reserved,
                   'ledger_errors': errors, 'preprocessor_model_calls': None,
                   'count_scope': 'existing recipe call ledgers; includes unknown reserved attempts',
                   'quality_certified': False}


def export(folder):
    folder = Path(folder)
    paths, summary = inventory(folder / 'workspace', strict=False)
    logroot = folder / 'workspace/01_DATA/LOGS'
    for p in t.files(logroot) if logroot.exists() else []:
        paths['audit/pipeline-logs/' + str(p.relative_to(logroot))] = p
    paths['audit/compute.log'] = folder / 'compute.log'
    t.write(folder / 'review-summary.json', summary)
    paths['audit/review-summary.json'] = folder / 'review-summary.json'
    return t.pack(paths, folder / 'audit.zip', metadata=summary)
