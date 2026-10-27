"""Post-selection metrics from immutable native evidence; never imports a model.

Read one finished run at a time. Missing telemetry is unknown, never zero. The
canonical article ledger is a presence ledger; exact extent coverage is separate.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from common import ROOT, ADR, ART, read, save, sha


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def ro(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA cache_size=-4096')
    return db


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def merge_ranges(rows):
    out = []
    for lo, hi in sorted(rows):
        if hi <= lo:
            continue
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def overlaps(lo, hi, ranges):
    return sum(max(0, min(hi, z) - max(lo, a)) for a, z in merge_ranges(ranges))


def range_map(spans):
    out = defaultdict(list)
    for row in spans:
        out[(row['document_id'], str(row['block_id']))].append((row['start_cp'], row['end_cp']))
    return {key: merge_ranges(value) for key, value in out.items()}


def covered(span, mapping):
    return overlaps(span['start_cp'], span['end_cp'],
        mapping.get((span['document_id'], str(span['block_id'])), [])) == span['end_cp'] - span['start_cp']


def required_targets(case):
    return case.get('evidence_targets', []) + case.get('source_provenance', {}).get('required_external_evidence', [])


def ontology_receipt(card):
    payload=card.get('payload',{})
    return {'bundle_id':payload.get('bundle_id'),'revision':payload.get('revision'),
        'mode':card.get('mode'),'status':card.get('status'),'payload_sha256':card.get('payload_sha256'),
        'card_sha256':digest(card),'unresolved':payload.get('unresolved',[]),
        'remaining_connections':payload.get('remaining_connections',[]),
        'provisions':[{k:v for k,v in p.items() if k!='text'} for p in payload.get('provisions',[])],
        'original_card_location':'native model_view body_json; full text is not duplicated in this audit'}


class OriginalStore:
    def __init__(self, generation):
        self.path = Path(generation) / 'store.sqlite'
        self.stat_before = self.path.stat()
        self.manifest = read(Path(generation)/'manifest.json') if (Path(generation)/'manifest.json').exists() else {}
        self.db = ro(self.path)
        self.blocks = {}
        self.units = {}

    def block(self, did, bid):
        key = (did, str(bid))
        if key not in self.blocks:
            row = self.db.execute('SELECT block_id,unit_id,text,source_artifact_sha256 '
                'FROM block_payload WHERE document_id=? AND block_id=?', key).fetchone()
            if row is None:
                raise ValueError('source block missing: ' + repr(key))
            self.blocks[key] = dict(row)
        return self.blocks[key]

    def unit(self, did, uid):
        key = (did, str(uid))
        if key not in self.units:
            row = self.db.execute('SELECT parent_id,json FROM source_unit '
                'WHERE document_id=? AND unit_id=?', key).fetchone()
            self.units[key] = {'parent_id': row['parent_id'], **json.loads(row['json'])} if row else None
        return self.units[key]

    def coordinate(self, did, bid):
        uid = self.block(did, bid)['unit_id']
        seen = set()
        while uid is not None and str(uid) not in seen:
            seen.add(str(uid))
            unit = self.unit(did, uid)
            if not unit:
                break
            coordinate = unit.get('coordinate_key', '')
            if re.fullmatch(r'body:제\d+조(?:의\d+)?', coordinate):
                return {'doc_id': did, 'node': int(uid), 'coordinate_key': coordinate}
            uid = unit.get('parent_id')
        return None  # Annexes remain exact block coordinates, never invented articles.

    def verify(self, row, *, version=None, json_text_hash=False):
        raw = self.block(row['document_id'], row['block_id'])
        lo, hi = row['start_cp'], row['end_cp']
        if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(raw['text']):
            return False
        expected = raw['text'][lo:hi]
        return (row.get('text') == expected and
            (version is None or version == raw['source_artifact_sha256']) and
            (not row.get('block_hash') or row['block_hash'] == text_hash(raw['text'])) and
            (not row.get('span_hash') or row['span_hash'] == text_hash(expected)) and
            (not json_text_hash or row.get('text_hash') == digest(expected)))


def target_coverage(binding, spans, store):
    if binding.get('status') != 'BOUND':
        return {'status': 'UNAVAILABLE_IN_FROZEN_CORPUS', 'ratio': None,
                'covered_codepoints': 0, 'expected_codepoints': None}
    have = range_map(spans)
    did = binding['document_id']
    total = got = body_got = 0
    for block in binding['blocks']:
        lo, hi = block['start_cp'], block['end_cp']
        raw = store.block(did, block['block_id'])
        if text_hash(raw['text'][lo:hi]) != block['text_sha256']:
            raise ValueError('frozen target source changed')
        total += hi - lo
        ranges = have.get((did, str(block['block_id'])), [])
        got += overlaps(lo, hi, ranges)
        # Exclude the legal heading prefix only; following normative text counts.
        title = re.match(r'^제\d+조(?:의\d+)?(?:\([^)]*\))?\s*', raw['text'])
        body_start = title.end() if title and str(block['block_id']) == str(binding.get('unit_id')) else lo
        body_got += overlaps(max(lo, body_start), hi, ranges)
    status = 'COMPLETE' if got == total else 'PARTIAL' if body_got else 'TITLE_ONLY' if got else 'NONE'
    return {'status': status, 'ratio': got / total if total else None,
            'covered_codepoints': got, 'body_codepoints': body_got, 'expected_codepoints': total}


def usage_summary(usage, physical_calls):
    receipts=sum(1 for row in usage if (row.get('raw_usage') is not None if 'raw_usage' in row
        else row.get('usage') is not None if 'usage' in row else any(row.get(k) is not None for k in ('input_tokens','output_tokens','total_tokens'))))
    out = {'physical_calls': physical_calls, 'usage_receipts': receipts,
           'calls_without_usage_receipt': max(0, physical_calls - receipts)}
    for key in ('input_tokens', 'output_tokens', 'total_tokens', 'cost_usd', 'seconds'):
        known = [x[key] for x in usage if isinstance(x.get(key), (int, float))]
        missing = max(0, physical_calls - len(known))
        out[key] = {'known_sum': sum(known), 'unknown_calls': missing,
                    'total': sum(known) if not missing else None}
    return out


def collect(case, arm, out, generation, *, corpus_total=None):
    result = read(out / 'result.json')
    response = read(out / 'response.json') if (out / 'response.json').exists() else {}
    body = response.get('body', {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = {}
    meta = body.get('assembly', {}).get('term_agent', {})
    answer = body.get('answer', {})
    if not isinstance(answer, dict):
        answer = {}
    store = OriginalStore(generation)
    acquired, delivered, cited, checks, packets = [], [], [], [], {}
    budgets, attempts, ontology, failures, journals = [], [], [], [], []
    native_error_events = Counter()
    assessment_ref = meta.get('case', {}).get('judgment_refs', {}).get('ASSESS')
    assessment = None
    evidence_index = {}
    request = read(out/'request.json') if (out/'request.json').exists() else {}
    request_body = request.get('json', request)
    allowed_documents = set(request_body.get('document_ids', [])) or None
    try:
        for path in sorted((out / 'runtime').rglob('journal.sqlite')):
            db = ro(path)
            try:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'evidence_unit' not in tables:
                    continue
                run = dict(db.execute('SELECT * FROM run').fetchone())
                journals.append({'path': str(path.relative_to(out)), 'run_id': run['run_id'], 'status': run['status']})
                budgets.append(dict(db.execute('SELECT * FROM budget').fetchone()))
                for event in db.execute("SELECT kind,COUNT(*) n FROM event WHERE kind IN "
                        "('OUTPUT_SCHEMA_INVALID','LAW_DECISION_REJECTED','LAW_DECISION_REPAIRED','BOUNDED_SOURCE_FAILURE') GROUP BY kind"):
                    native_error_events[event['kind']] += event['n']
                for row in db.execute('SELECT attempt_id,status,input_tokens,output_tokens FROM model_attempt'):
                    attempts.append(dict(row))
                for e in db.execute('SELECT * FROM evidence_unit ORDER BY evidence_id'):
                    spans = [dict(x) for x in db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal', (e['evidence_id'],))]
                    valid = bool(spans) and text_hash('\n'.join(x['text'] for x in spans)) == e['text_hash']
                    if store.manifest.get('generation_id') and dict(e).get('generation_id') != store.manifest['generation_id']:
                        valid = False
                        failures.append({'kind':'EVIDENCE_GENERATION_MISMATCH','evidence_id':e['evidence_id']})
                    metadata = json.loads(e['metadata_json'])
                    for span in spans:
                        row = {**span, 'source_id': e['source_id'], 'document_id': e['document_id'],
                               'document_name':metadata.get('document_name'),
                               'source_artifact_sha256': e['source_artifact_hash']}
                        if allowed_documents is not None and e['document_id'] not in allowed_documents:
                            failures.append({'kind':'SOURCE_OUTSIDE_REQUEST_SCOPE','document_id':e['document_id']})
                        exact = store.verify(row, version=e['source_artifact_hash'])
                        valid = valid and exact
                        row['canonical'] = store.coordinate(row['document_id'], row['block_id'])
                        if exact:
                            acquired.append(row)
                            pid = 'P' + digest({k: row[k] for k in ('document_id','block_id','start_cp','end_cp','text')})[:28]
                            packets[pid] = {'packet_id': pid, 'source_id': row['source_id'],
                                'document_id': row['document_id'], 'document_name': metadata.get('document_name'),
                                'canonical': row['canonical'], 'block_id': row['block_id'],
                                'start_cp': row['start_cp'], 'end_cp': row['end_cp'],
                                'text': row['text'], 'text_sha256': text_hash(row['text'])}
                        else:
                            failures.append({'kind': 'SOURCE_TEXT_MISMATCH', 'evidence_id': e['evidence_id'], 'block_id': row['block_id']})
                    checks.append({'evidence_id': e['evidence_id'], 'exact_original_match': valid, 'span_count': len(spans)})
                    evidence_index[e['evidence_id']] = {'document_id': e['document_id'], 'source_id': e['source_id'], 'spans': spans}
                for event_row in db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='NAVIGATION_INPUT_DELIVERED'"):
                    event = json.loads(event_row['payload_json'])
                    vr = db.execute('SELECT body_json,body_hash FROM model_view WHERE view_id=?', (event['view_id'],)).fetchone()
                    ar = db.execute('SELECT view_id,status FROM model_attempt WHERE attempt_id=?', (event['attempt_id'],)).fetchone()
                    view = json.loads(vr['body_json']) if vr else {}
                    valid = (event.get('contract') == 'confirmed-navigation-input-v1' and
                        digest(event) == event_row['payload_hash'] and vr and ar and
                        ar['status'] == 'SUCCEEDED' and ar['view_id'] == event['view_id'] and
                        digest(view) == vr['body_hash'] == event['view_sha256'] and
                        digest(view.get('sources')) == event['sources_sha256'] and
                        view.get('source_stage') == event.get('source_stage') and
                        view.get('presentation_id') == event.get('presentation_id') and
                        view.get('state_version') == event.get('state_version'))
                    if not valid:
                        failures.append({'kind': 'DELIVERY_RECEIPT_INVALID', 'view_id': event['view_id']})
                        continue
                    for page in view.get('sources', []):
                        for span in page.get('spans', []):
                            row = {**span, 'document_id': page['document_id'], 'source_id': page['source_id'], 'view_id': event['view_id']}
                            if store.verify(row):
                                row['canonical'] = store.coordinate(row['document_id'], row['block_id'])
                                delivered.append(row)
                            else:
                                failures.append({'kind': 'DELIVERED_TEXT_MISMATCH', 'view_id': event['view_id']})
                # ASSESS/COMPOSE presentations also prove delivery. Each row binds
                # the exact acquired evidence hash to a successfully returned view.
                for row in db.execute('SELECT DISTINCT p.evidence_id,p.delivered_text_hash FROM presentation p '
                        "JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'"):
                    e = evidence_index.get(row['evidence_id'])
                    if e and text_hash('\n'.join(s['text'] for s in e['spans'])) == row['delivered_text_hash']:
                        delivered.extend({**s, 'document_id': e['document_id'], 'source_id': e['source_id'],
                            'canonical': store.coordinate(e['document_id'], s['block_id'])} for s in e['spans'])
                for vr in db.execute('SELECT view_id,body_json,body_hash FROM model_view ORDER BY created_seq'):
                    view = json.loads(vr['body_json'])
                    if digest(view) != vr['body_hash']:
                        failures.append({'kind':'VIEW_HASH_MISMATCH','view_id':vr['view_id']})
                        continue
                    for item in walk(view):
                        if 'ontology_bundles' in item or 'ontology_context_limits' in item:
                            ontology.append({'journal':str(path.relative_to(out)),'view_id':vr['view_id'],
                                             'bundles':[ontology_receipt(c) for c in item.get('ontology_bundles', [])],
                                             'limits':item.get('ontology_context_limits')})
                if assessment_ref and run['run_id'] == assessment_ref.get('run_id'):
                    ar = db.execute('SELECT payload_json,payload_hash FROM entity_version WHERE kind=? AND entity_id=? AND version=?',
                        (assessment_ref['kind'], assessment_ref['entity_id'], assessment_ref['version'])).fetchone()
                    if ar and ar['payload_hash'] == assessment_ref['payload_hash'] == digest(json.loads(ar['payload_json'])):
                        assessment = json.loads(ar['payload_json'])
                    else:
                        failures.append({'kind': 'ASSESSMENT_BINDING_MISMATCH'})
            finally:
                db.close()
        have = range_map(acquired)
        delivery_map = range_map(delivered)
        citation_unresolved = []
        if assessment is not None:
            expected = [{'id':'claim:'+str(i+1), 'text':c['text'],
                'source_ids':list(dict.fromkeys([c['source_id']] + [e['source_id'] for e in c.get('evidence', [])]))}
                for i,c in enumerate(assessment.get('claims', []))]
            if expected != answer.get('claims', []):
                failures.append({'kind':'PUBLIC_CLAIM_ASSESSMENT_MISMATCH'})
            else:
                for claim in assessment.get('claims', []):
                    receipts = claim.get('span_receipts', [])
                    if not receipts:
                        citation_unresolved.append({'claim_id':claim.get('claim_id'),'reason':'NO_EXACT_SPAN_RECEIPTS'})
                    for span in receipts:
                        valid = store.verify(span, json_text_hash=True) and covered(span, have) and covered(span, delivery_map)
                        if valid:
                            cited.append({**span, 'canonical':store.coordinate(span['document_id'],span['block_id'])})
                        else:
                            failures.append({'kind':'CITATION_SPAN_INVALID','receipt_id':span.get('id')})
        elif answer.get('claims'):
            citation_unresolved.append({'reason':'CURRENT_ASSESSMENT_UNAVAILABLE'})
        valid_delivered = []
        for span in delivered:
            if covered(span, have):
                valid_delivered.append(span)
            else:
                failures.append({'kind':'DELIVERY_NOT_ACQUIRED','document_id':span['document_id'],'block_id':span['block_id']})
        delivered = valid_delivered
        # Exact union, not a bounding range: never fill an unread gap.
        packets = {}
        by_block = defaultdict(list)
        for span in acquired:
            by_block[(span['document_id'],str(span['block_id']))].append(span)
        for (did,bid), ranges in have.items():
            prior = by_block[(did,bid)][0]
            for lo,hi in ranges:
                text = store.block(did,bid)['text'][lo:hi]
                pid = 'P' + digest([did,bid,lo,hi,text_hash(text)])[:28]
                packets[pid] = {'packet_id':pid,'source_id':prior['source_id'],
                    'document_id':did,'document_name':prior.get('document_name'),
                    'canonical':store.coordinate(did,bid),
                    'block_id':bid,'start_cp':lo,'end_cp':hi,'text':text,'text_sha256':text_hash(text)}
        targets = []
        for target in required_targets(case):
            binding = target['current_binding']
            targets.append({'role':target.get('role'), 'document_name':binding.get('document_name'),
                'document_id':binding.get('document_id'), 'unit_id':binding.get('unit_id'),
                'coordinate_key':binding.get('coordinate_key'), 'binding_status':binding.get('status'),
                **{stage:target_coverage(binding, rows, store) for stage, rows in
                   [('acquired',acquired),('delivered',delivered),('cited',cited)]}})
        def coords(rows):
            return [json.loads(s) for s in sorted({json.dumps({'doc_id':r['canonical']['doc_id'],'node':r['canonical']['node']},sort_keys=True)
                for r in rows if r.get('canonical')})]
        coordinates = {name:coords(rows) for name,rows in [('acquired',acquired),('delivered',delivered),('cited',cited)]}
        call_files = list((out/'model').glob('call-*/request.json'))
        wire_ranges = []
        wire_parse_errors = []
        for path in call_files:
            payload = read(path)
            for message in payload.get('messages', []):
                if message.get('role') != 'user' or not isinstance(message.get('content'), str):
                    continue
                try:
                    data = json.loads(message['content'])
                except ValueError:
                    wire_parse_errors.append(str(path.relative_to(out)))
                    continue
                for item in walk(data):
                    if item.get('document_id') and isinstance(item.get('spans'),list):
                        wire_ranges.extend({**s,'document_id':item['document_id']} for s in item['spans']
                            if all(k in s for k in ('block_id','start_cp','end_cp','text')))
        wire_map = range_map([s for s in wire_ranges if store.verify(s)])
        physical = max(len(call_files), result.get('model_calls', 0) or 0)
        usage = result.get('usage') or (read(out/'model'/'usage.json') if (out/'model'/'usage.json').exists() else [])
        if (out/'physical-calls.jsonl').exists():
            physical_events={}
            for line in (out/'physical-calls.jsonl').open():
                event=json.loads(line)
                physical_events[event['call']]=event
            usage=[{**u,'seconds':physical_events.get(u.get('call'),{}).get('seconds',u.get('seconds'))} for u in usage]
        errors = []
        for path in (out/'model').glob('call-*/response.json'):
            raw = read(path)
            errors.extend({'call':path.parent.name,'finish_reason':c.get('finish_reason')} for c in raw.get('choices', []) if c.get('finish_reason') != 'stop')
        metrics = {'schema_version':'ontology-mvp-metrics-v1','case_id':case['case_id'],'arm':arm,
            'source_generation_id':store.manifest.get('generation_id'),
            'service_status':response.get('status',result.get('service_status')),'service_error':result.get('error'),
            'service_outcome':result.get('outcome'),'native_failures':result.get('native_failures',[]),
            'answer':answer.get('text',''),'answer_status':body.get('answer_status'),
            'outcome':meta.get('accepted_outcome'),'answer_coverage':meta.get('answer_coverage'),
            'latency_seconds':result.get('seconds'),'peak_rss_kib':result.get('peak_rss_kib'),
            'usage':usage_summary(usage,physical),'native_budgets':budgets,
            'model_attempt_statuses':dict(Counter(a['status'] for a in attempts)),
            'native_error_event_counts':dict(native_error_events),
            'output_errors':errors,'source_integrity':{'evidence_count':len(checks),'mismatch_count':sum(not x['exact_original_match'] for x in checks),
                'failures':failures},'citation_unresolved':citation_unresolved,'required_targets':targets,
            'coordinates':coordinates,'corpus_total_article_roots':corpus_total,
            'presented_selectivity':len(coordinates['delivered'])/corpus_total if corpus_total else None,
            'unknown_metrics':{'pre_filter_candidates':'No exact complete retrieval-set snapshot is inferred from top-k pages.',
                'post_filter_candidates':'Scope catalogue traces retain exact observed groups but do not prove the complete filtered corpus.',
                'wire_delivery':'Native receipts prove confirmed delivery; explicit wire spans are independently checked. Quote-only compose inputs may not expose offsets.'},
            'wire_audit':{'explicit_spans':len(wire_ranges),'parse_errors':wire_parse_errors,
                'confirmed_spans_with_explicit_wire_range':sum(covered(s,wire_map) for s in delivered),
                'confirmed_spans_without_explicit_wire_range':sum(not covered(s,wire_map) for s in delivered)},
            'request_acl_check':'CHECKED' if allowed_documents is not None else 'UNKNOWN_REQUEST_SCOPE_NOT_RECORDED',
            'ontology':{'view_observations':len(ontology),'artifact':'ontology-audit.json'},
            'actual_source_packet_count':len(packets),'judgment_gaps':assessment.get('gaps',[]) if assessment else [],
            'completed_with_unresolved_connections':meta.get('completed_with_unresolved_connections'),
            'journals':journals,'gold_visible_to_product':False}
        save(out/'metrics.json',metrics)
        def receipt_rows(rows):
            return [{**{k:v for k,v in row.items() if k!='text'},'text_sha256':text_hash(row['text'])} for row in rows]
        save(out/'evidence-audit.json',{'checks':checks,'acquired':receipt_rows(acquired),
            'delivered':receipt_rows(delivered),'cited':receipt_rows(cited),
            'original_text_location':'native journals and exact union in judge-source-packets.json'})
        save(out/'judge-source-packets.json',{'schema_version':'actual-acquired-source-packets-v1','packets':list(packets.values()),'summarized':False})
        save(out/'ontology-audit.json',ontology)
        # Standard canonical ledger is kept distinct from full-span coverage.
        sys.path.insert(0,str(ROOT/'02_BACKEND'))
        from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder, identity_canonicalizer, grade_capture
        rec = StageLedgerRecorder(case['case_id'],'baseline' if arm=='A0' else arm,identity_canonicalizer)
        rec.record_stage('original_read','source',coordinates['acquired'])
        for name,parent in [('delivered','original_read'),('final_cited','delivered')]:
            values = coordinates['delivered' if name=='delivered' else 'cited']
            previous = coordinates['acquired' if name=='delivered' else 'delivered']
            rec.record_stage(name,'present',values,parent_stage_ids=[parent],discard_reasons=[
                {'identity':x,'reason':'Not confirmed delivered at this stage; no semantic irrelevance or source absence inferred.'}
                for x in previous if x not in values])
        gold = [{'doc_id':t['current_binding']['document_id'],'node':int(t['current_binding']['unit_id'])}
            for t in required_targets(case) if t['current_binding'].get('status')=='BOUND'
            and str(t['current_binding'].get('unit_id')).isdigit()]
        save(out/'retrieval-ledger-case.json',grade_capture(rec.capture(),gold))
        return metrics
    finally:
        store.db.close()
        after=store.path.stat()
        if (after.st_size,after.st_mtime_ns)!=(store.stat_before.st_size,store.stat_before.st_mtime_ns):
            raise ValueError('source store changed during metric collection')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',required=True)
    parser.add_argument('--arm',required=True,choices=['A0','A1','A2'])
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--generation',type=Path)
    args=parser.parse_args()
    freeze=read(ART/'design-freeze.json')
    for name in ('collect_metrics.py','common.py'):
        path=Path(__file__).with_name(name)
        if freeze.get('evaluation_scripts',{}).get(str(path.relative_to(ROOT)))!=sha(path):
            raise ValueError('collector script freeze changed')
    ledger=ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py'
    if freeze.get('evaluation_scripts',{}).get(str(ledger.relative_to(ROOT)))!=sha(ledger):
        raise ValueError('stage ledger implementation freeze changed')
    if sha(ROOT/freeze['evaluation_contract_path'])!=freeze['evaluation_contract_sha256']:
        raise ValueError('evaluation contract changed')
    generation=(args.generation or ROOT/freeze['data_path']).resolve()
    if generation!=(ROOT/freeze['data_path']).resolve():
        raise ValueError('collector generation differs from product freeze')
    if sha(generation/'manifest.json')!=freeze['data_manifest_sha256']:
        raise ValueError('source generation manifest changed')
    cases_path=ROOT/freeze['evaluator_cases_path']
    if sha(cases_path)!=freeze['evaluator_cases_sha256']:
        raise ValueError('evaluator case freeze changed')
    rows=[r for r in freeze['execution_order'] if r['case_id']==args.case and r['arm']==args.arm]
    if len(rows)!=1:
        raise ValueError('collector case/arm is not uniquely frozen')
    row=rows[0]
    expected_out=ART/'matrix'/f"{row['ordinal']:03d}-{row['case_id']}-{row['arm']}"
    if args.out.resolve()!=expected_out.resolve():
        raise ValueError('collector output differs from frozen product cell')
    result=read(args.out/'result.json');reservation=read(args.out/'reservation.json')
    if (result.get('completed') is not True or result.get('cell')!=row or
            result.get('outcome') not in ('SERVICE_COMPLETED','NATIVE_BOUNDED_FAILURE') or
            reservation.get('cell')!=row or reservation.get('design_freeze_sha256')!=sha(ART/'design-freeze.json')):
        raise ValueError('collector requires the completed product receipt from this freeze')
    case=next(c for c in read(cases_path)['cases'] if c['case_id']==args.case)
    metrics=collect(case,args.arm,args.out,generation,
                    corpus_total=freeze.get('corpus_total_article_roots'))
    print(json.dumps({k:metrics[k] for k in ('case_id','arm','service_status','source_integrity')},ensure_ascii=False))


if __name__=='__main__':
    main()
