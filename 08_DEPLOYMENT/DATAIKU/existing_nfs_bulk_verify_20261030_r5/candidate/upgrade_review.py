"""A R3 failure may migrate only with hash-verified evidence of zero review calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile


def require_zero_review(store,old):
    info=old.get('audit_blob')
    observed=(old.get('last_observed') or {}).get('audit') or {}
    if (not isinstance(info,dict) or type(info.get('bytes')) is not int or not 0<info['bytes']<=1024**3
            or info.get('sha256')!=observed.get('sha256') or info['bytes']!=observed.get('bytes')):
        raise ValueError('R3_ZERO_REVIEW_AUDIT_REQUIRED')
    with tempfile.TemporaryDirectory(prefix='r4-audit-proof-') as tmp:
        p=Path(tmp)/'audit.zip';store.get_blob(info,p)
        with zipfile.ZipFile(p) as z:
            names=z.namelist()
            if len(set(names))!=len(names):raise ValueError('AUDIT_DUPLICATE')
            if z.getinfo('audit/review-summary.json').file_size>1024*1024:raise ValueError('AUDIT_SUMMARY_SIZE')
            # Full blob hash already binds all bytes. Verify the recorded summary
            # against every existing recipe model ledger, not the legacy llm_calls field.
            summary=json.loads(z.read('audit/review-summary.json'))
            if type(summary.get('reserved_model_calls')) is not int or summary['reserved_model_calls']!=0 or summary.get('ledger_errors')!=[]:
                raise ValueError('R3_MODEL_LEDGER_RESUME_REQUIRED')
            for n in names:
                if '/model-calls/' not in n or not n.endswith('.json'):continue
                if z.getinfo(n).file_size>16*1024*1024:raise ValueError('AUDIT_LEDGER_SIZE')
                envelope=json.loads(z.read(n));ledger=envelope['state']
                digest=hashlib.sha256(json.dumps(ledger,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                if envelope.get('sha256')!=digest or type(ledger.get('calls')) is not int or ledger['calls']!=0 or any(e.get('status')=='RESERVED' for e in ledger.get('events',[])):
                    raise ValueError('R3_MODEL_LEDGER_RESUME_REQUIRED')
    return {'audit_sha256':info['sha256'],'reserved_review_calls':0,'preprocessor_calls':'UNKNOWN_PRESERVED_IN_PRIOR_CHECKPOINT'}
