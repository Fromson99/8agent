"""Strict source-reference accounting over already verified native evidence.

No corpus, model, retrieval, text search, coordinate inference or repair. Every
occurrence is verified before union, including redundant source/evidence views.
"""
from collections import defaultdict
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class AuditError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code=code


class Unknown(AuditError):
    pass


def require(condition, code):
    if not condition:raise AuditError(code)


def extent(row):
    lo,hi=row.get('start_cp'),row.get('end_cp')
    require(type(lo) is int and type(hi) is int and 0<=lo<hi,'INVALID_NATIVE_EXTENT')
    return lo,hi


def evidence_index(records, checks, acquired, allowed, generation):
    """Bind journal evidence to the frozen original collector's source checks."""
    require(bool(allowed),'ACL_UNKNOWN')
    proof=defaultdict(list)
    for row in checks:proof[row.get('evidence_id')].append(row)
    receipts=defaultdict(list)
    for row in acquired:
        key=(row.get('evidence_id'),row.get('document_id'),row.get('source_id'),
             str(row.get('block_id')),row.get('start_cp'),row.get('end_cp'))
        receipts[key].append(row)
    result={}
    for record in records:
        eid=record['evidence_id'];spans=record['spans']
        require(eid not in result,'DUPLICATE_NATIVE_EVIDENCE_ID')
        require(record['document_id'] in allowed,'SOURCE_OUTSIDE_ACL')
        require(record.get('generation_id')==generation,'NATIVE_GENERATION_MISMATCH')
        require(isinstance(record.get('source_artifact_hash'),str) and
                len(record['source_artifact_hash'])==64,'NATIVE_VERSION_UNKNOWN')
        require(bool(spans) and text_hash('\n'.join(s['text'] for s in spans))==record['text_hash'],
                'NATIVE_EVIDENCE_TEXT_HASH_MISMATCH')
        require(bool(proof[eid]) and all(p.get('exact_original_match') is True
                and p.get('span_count')==len(spans) for p in proof[eid]),'ORIGINAL_SOURCE_CHECK_UNKNOWN')
        for ordinal,span in enumerate(spans):
            lo,hi=extent(span)
            require(span.get('ordinal')==ordinal and len(span['text'])==hi-lo,'NATIVE_SPAN_ORDER_OR_LENGTH')
            require(span.get('span_hash')==text_hash(span['text']),'NATIVE_SPAN_HASH_MISMATCH')
            key=(eid,record['document_id'],record['source_id'],str(span['block_id']),lo,hi)
            found=receipts[key]
            require(bool(found) and all(r.get('text_sha256')==text_hash(span['text'])
                and r.get('source_artifact_sha256')==record['source_artifact_hash'] for r in found),
                'ORIGINAL_SOURCE_RECEIPT_MISMATCH')
        result[eid]=record
    return result


def _bind(native, text, eid, index, allowed, path):
    if not eid or eid not in index:raise Unknown('NATIVE_EVIDENCE_UNAVAILABLE')
    record=index[eid];did,sid=record['document_id'],record['source_id']
    require(did in allowed,'SOURCE_OUTSIDE_ACL')
    for key,value in (('document_id',did),('source_id',sid),('evidence_id',eid)):
        require(native.get(key,value)==value,'NATIVE_SOURCE_IDENTITY_MISMATCH')
    lo,hi=extent(native)
    require(isinstance(text,str) and len(text)==hi-lo,'DELIVERED_TEXT_EXTENT_MISMATCH')
    if 'text' in native:require(native['text']==text,'DELIVERED_TEXT_DIFFERS_FROM_NATIVE')
    if 'text_hash' in native:require(native['text_hash']==digest(text),'NATIVE_OPTION_TEXT_HASH_MISMATCH')
    if 'span_hash' in native:require(native['span_hash']==text_hash(text),'NATIVE_SPAN_HASH_MISMATCH')
    matches=[s for s in record['spans'] if str(s['block_id'])==str(native.get('block_id'))
             and s['start_cp']<=lo<hi<=s['end_cp']]
    if not matches:raise Unknown('ACQUIRED_SPAN_RANGE_UNAVAILABLE')
    require(all(s['text'][lo-s['start_cp']:hi-s['start_cp']]==text for s in matches),
            'DELIVERED_TEXT_DIFFERS_FROM_ACQUIRED')
    return {'document_id':did,'source_id':sid,'source_version':record['source_artifact_hash'],
        'evidence_id':eid,'block_id':str(native['block_id']),'start_cp':lo,'end_cp':hi,
        'text':text,'text_sha256':text_hash(text),'path':path}


def _body(card, pool, *, owner=None):
    text=card.get('text')
    if 'text_ref' in card:
        ref=card['text_ref']
        require(isinstance(ref,dict) and set(ref)=={'id','start','end'},'INVALID_PARENT_TEXT_REF')
        if ref['id'] not in pool:raise Unknown('PARENT_TEXT_REF_UNAVAILABLE')
        parent=pool[ref['id']]
        if owner is not None:
            require((parent.get('document_id'),parent.get('source_id'))==owner,'PARENT_TEXT_REF_OWNER_MISMATCH')
        lo,hi=ref['start'],ref['end']
        require(type(lo) is int and type(hi) is int and 0<=lo<=hi<=len(parent['text']),
                'PARENT_TEXT_REF_OUT_OF_RANGE')
        part=parent['text'][lo:hi]
        require(text is None or text==part,'PARENT_TEXT_REF_VALUE_MISMATCH')
        text=part
    if not isinstance(text,str):raise Unknown('DELIVERED_TEXT_UNAVAILABLE')
    return text


def _same_extent(actual,native):
    require(all(actual.get(k)==native.get(k) for k in ('block_id','start_cp','end_cp')),
            'WIRE_NATIVE_COORDINATE_MISMATCH')
    for key in ('ordinal','evidence_id'):
        if key in actual:require(actual[key]==native.get(key),'WIRE_NATIVE_SPAN_IDENTITY_MISMATCH')


def audit_view(restored, stored, index, allowed):
    """Only called after exact frozen codec verification and ID restoration."""
    rows=[];unknown=[];resolved_parent_children=0
    pool={}
    for card in restored.get('sources',[]):
        if card.get('text_id'):
            require(card['text_id'] not in pool,'DUPLICATE_TEXT_POOL_ID')
            require(isinstance(card.get('text'),str),'TEXT_POOL_BODY_UNKNOWN')
            pool[card['text_id']]=card
    for container in ('sources','exact_evidence'):
        visible=restored.get(container,[]);native=stored.get(container,[])
        # ASSESS intentionally omits duplicate exact_evidence after its frozen
        # codec proves all subspans are in evidence_options. Audit those below.
        if not visible:
            require(container!='sources' or not native,'SOURCE_CONTAINER_CARDINALITY_MISMATCH')
            continue
        require(len(visible)==len(native),'SOURCE_CONTAINER_CARDINALITY_MISMATCH')
        for number,(card,original) in enumerate(zip(visible,native,strict=True)):
            path=f'{container}/{number}'
            try:
                for key in ('source_id','document_id','evidence','evidence_id','evidence_ref','evidence_refs'):
                    if key in card:require(card[key]==original.get(key),'WIRE_NATIVE_SOURCE_BINDING_MISMATCH')
                if 'evidence_refs' in original:
                    require(card.get('evidence_refs')==original['evidence_refs'],'SOURCE_EVIDENCE_REFS_CHANGED')
                spans=card.get('spans',[]);original_spans=original.get('spans',[])
                if not spans:
                    # Source headers carry no original body and make no body
                    # claim. Their evidence_refs are separately mandatory below.
                    if any(k in card for k in ('text','text_ref')) and not original_spans:
                        raise Unknown('SOURCE_BODY_WITHOUT_NATIVE_SPANS')
                    continue
                require(len(spans)==len(original_spans),'NATIVE_SPAN_CARDINALITY_MISMATCH')
                eid=original.get('evidence') or original.get('evidence_id')
                owner=(original.get('document_id'),original.get('source_id'))
                if eid in index:owner=(index[eid]['document_id'],index[eid]['source_id'])
                for key,value in zip(('document_id','source_id'),owner,strict=True):
                    if key in card:require(card[key]==value,'WIRE_SOURCE_OWNER_MISMATCH')
                parent=_body(card,pool,owner=owner)
                require(isinstance(original.get('text'),str) and parent==original['text'],
                        'PARENT_BODY_DIFFERS_FROM_NATIVE')
                require('\n'.join(s.get('text','') for s in original_spans)==parent,
                        'PARENT_BODY_SPAN_SEQUENCE_MISMATCH')
                for offset,(span,native_span) in enumerate(zip(spans,original_spans,strict=True)):
                    _same_extent(span,native_span)
                    if 'text' in span or 'text_ref' in span:
                        text=_body(span,pool,owner=owner)
                    else:
                        # The verified parent body is an exact newline-joined
                        # sequence, never a substring search or guessed offset.
                        text=native_span['text'];resolved_parent_children+=1
                    row={**native_span,'document_id':owner[0],'source_id':owner[1]}
                    rows.append(_bind(row,text,native_span.get('evidence_id',eid),index,allowed,path+f'/spans/{offset}'))
            except Unknown as error:unknown.append({'path':path,'code':error.code})
    options=restored.get('evidence_options',[])
    native_options={}
    for option in stored.get('evidence_options',[]):
        require(option.get('id') not in native_options,'DUPLICATE_NATIVE_OPTION_ID')
        native_options[option.get('id')]=option
    require(len(options)==len(native_options),'OPTION_CONTAINER_CARDINALITY_MISMATCH')
    visible_options={}
    for number,option in enumerate(options):
        ident=option.get('id')
        require(ident not in visible_options,'DUPLICATE_DELIVERED_OPTION_ID')
        require(ident in native_options,'DELIVERED_OPTION_ID_NOT_IN_NATIVE_VIEW')
        visible_options[ident]=option;original=native_options[ident]
        for key,value in option.items():
            if key not in ('text_ref',):require(original.get(key)==value,'DELIVERED_OPTION_CHANGED')
        path=f'evidence_options/{number}'
        try:
            text=_body(option,pool,owner=(original.get('document_id'),original.get('source_id')))
            rows.append(_bind(original,text,original.get('evidence_id'),index,allowed,path))
        except Unknown as error:unknown.append({'path':path,'code':error.code})
    for number,source in enumerate(restored.get('sources',[])):
        for ident in source.get('evidence_refs',[]):
            require(ident in visible_options,'SOURCE_EVIDENCE_REF_NOT_DELIVERED')
            original=native_options[ident]
            require(source.get('source_id')==original.get('source_id'),'SOURCE_EVIDENCE_REF_OWNER_MISMATCH')
    return {'status':'UNKNOWN' if unknown else 'VERIFIED','occurrences':rows,
        'unknown':unknown,'parent_children_resolved':resolved_parent_children,
        **union(rows)}


def union(rows):
    """Validate each overlap's original bytes before merging any ranges."""
    groups=defaultdict(list)
    for row in rows:
        groups[(row['document_id'],row['source_id'],row['source_version'],row['block_id'])].append(row)
    merged=[]
    for key,items in sorted(groups.items()):
        for i,a in enumerate(items):
            for b in items[i+1:]:
                lo=max(a['start_cp'],b['start_cp']);hi=min(a['end_cp'],b['end_cp'])
                if lo<hi:require(a['text'][lo-a['start_cp']:hi-a['start_cp']]==
                    b['text'][lo-b['start_cp']:hi-b['start_cp']],'CONFLICTING_OVERLAP_TEXT')
        ranges=[]
        for row in sorted(items,key=lambda r:(r['start_cp'],r['end_cp'])):
            lo,hi=row['start_cp'],row['end_cp']
            if ranges and lo<=ranges[-1][1]:ranges[-1][1]=max(ranges[-1][1],hi)
            else:ranges.append([lo,hi])
        merged.extend({'document_id':key[0],'source_id':key[1],'source_version':key[2],
            'block_id':key[3],'start_cp':lo,'end_cp':hi} for lo,hi in ranges)
    return {'occurrence_count':len(rows),'unique_ranges':merged,
        'unique_range_count':len(merged),'unique_codepoints':sum(r['end_cp']-r['start_cp'] for r in merged)}
