"""Exact mapping definitions reused from frozen ADR1208 rev-021. No lab startup."""
from gold_io import canonical

READ_COLUMNS = {
    'document': ('DOC_VER', dict(zip(
        'DATASET_VERSION DOCUMENT_ID NAME SOURCE_ARTIFACT_SHA256 SOURCE_JSON'.split(),
        'MNFST_HASH_VALU DOC_ID DOC_NAME DOC_HASH_VALU DOC_ADDN_IFMN_CTNT'.split()))),
    'source_unit': ('DOC_UNIT', dict(zip(
        'DATASET_VERSION DOCUMENT_ID UNIT_ID PARENT_ID SOURCE_JSON'.split(),
        'MNFST_HASH_VALU DOC_ID STRC_UNIT_ID UPPR_STRC_UNIT_ID STRC_UNIT_ADDN_IFMN_CTNT'.split()))),
    'block_payload': ('DOC_BLK', dict(zip(
        'DATASET_VERSION DOCUMENT_ID BLOCK_ID UNIT_ID TEXT SOURCE_ARTIFACT_SHA256 SOURCE_JSON JSON_TEXT_ELIDED'.split(),
        'MNFST_HASH_VALU DOC_ID BODY_SLC_ID STRC_UNIT_ID BODY_CTNT DOC_HASH_VALU BODY_SLC_ADDN_IFMN_CTNT ADD_INFO_TEXT_OMIT_YN'.split()))),
    'source_release': ('SRC_POST', dict(zip(
        'RELEASE_ID DATASET_VERSION RELEASE_JSON CREATED_AT'.split(),
        'DOC_POST_HASH_VALU MNFST_HASH_VALU DOC_POST_IFMN_CTNT RGSN_AITM'.split()))),
    'query_release': ('SRCH_POST', {'RELEASE_ID': 'RFRN_POST_HASH_VALU', 'MANIFEST_JSON': 'RFRN_POST_IFMN_CTNT'}),
    'query_row': ('SRCH_ROW', dict(zip(
        'RELEASE_ID KIND ROW_ID DOCUMENT_ID LOOKUP_ID OWNER_ID TARGET_ID ROW_SHA256 VALUE_JSON'.split(),
        'RFRN_POST_HASH_VALU RFRN_DTA_TYPE_VALU RFRN_DTA_ID DOC_ID RFRN_DTA_IDNF_CTNT BLNG_DTA_IDNF_CTNT TAGT_DTA_IDNF_CTNT SRCH_DATA_HASH_VALU SRCH_DATA_CTNT'.split()))),
    'query_active': ('SRCH_CHNL', dict(zip(
        'CHANNEL RELEASE_ID REVISION'.split(), 'RFRN_CHNL_NAME RFRN_POST_HASH_VALU CHAN_NO'.split()))),
}

def mapped_source(kind,row):
    suffix,m=READ_COLUMNS[kind]
    return suffix,{m[k]:('Y' if v==1 else 'N' if v==0 else None) if k=='JSON_TEXT_ELIDED' else v for k,v in row.items()}

def mapped_query(qid,r):return dict(zip(READ_COLUMNS['query_row'][1].values(),[qid,r['kind'],r['row_id'],r['document_id'],r['lookup_id'],r['owner_id'],r['target_id'],r['sha256'],canonical(r['value'])]))
