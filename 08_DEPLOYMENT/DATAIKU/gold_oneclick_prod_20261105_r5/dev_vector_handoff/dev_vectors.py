from tempfile import TemporaryDirectory


def run_dev_vectors(params, package):
    engine = package/'engine'
    sys.path[:0] = [str(engine), str(engine/'vendor'), str(engine/'vendor/02_BACKEND')]
    from prod_config import identifier, target
    from prod_pipeline import Contract, code_binding, connection
    from gold_io import Contract as OracleContract, Stop, canonical, digest, literal
    from vector_stage import check_coordinates, rows_for, vector_sql

    code_binding()
    owner = identifier(params['DEV_OWNER'])
    login = identifier(params['EXPECTED_DB_USER'])
    names = {'VCTR_ITEM':'TST_B003_LGL_VCTR_ITEM_R5',
             'VCTR_POST':'TST_B003_LGL_VCTR_POST_R5',
             'VCTR_HEAD':'TST_B003_LGL_VCTR_HEAD_R5'}
    configured = target({'TARGET_MODE':'GOLD', 'GOLD_OWNER':owner, 'TABLE_NAMES':names})
    configured['tables'] = {key:configured['tables'][key] for key in names}
    accepted = {'VECTOR(*,*,DENSE)', 'VECTOR(*,FLOAT32,DENSE)', 'VECTOR(1024,FLOAT32,DENSE)'}

    class DevTables(OracleContract):
        # Use the field screen's plain VECTOR declaration when creating the test ITEM.
        def ddl(self, key):
            sql = super().ddl(key)
            if key == 'VCTR_ITEM':
                field = 'EMBD_VCTR VECTOR(*,FLOAT32) NOT NULL'
                if sql.count(field) != 1:
                    raise Stop('R5_TEST_DDL_CONTRACT_CHANGED')
                return sql.replace(field, 'EMBD_VCTR VECTOR NOT NULL')
            return sql

        def preflight(self, db, key):
            if key == 'VCTR_ITEM':
                rows = db.query('SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,VECTOR_INFO '
                                'FROM ALL_TAB_COLUMNS WHERE OWNER=' + literal(owner)
                                + ' AND TABLE_NAME=' + literal(names[key])
                                + " AND COLUMN_NAME IN ('EMBD_VCTR','BODY_UNIT_ID')")
                cols = {r['COLUMN_NAME']:r for r in rows}
                if set(cols) != {'BODY_UNIT_ID','EMBD_VCTR'}:
                    raise Stop('DEV_VECTOR_COLUMNS_MISSING:' + canonical(list(cols)))
                body, vector = cols['BODY_UNIT_ID'], cols['EMBD_VCTR']
                self.item_metadata = {'VECTOR_INFO':vector['VECTOR_INFO'], 'VECTOR_TYPE':vector['DATA_TYPE'],
                                      'BODY_UNIT_ID_TYPE':body['DATA_TYPE'], 'DATA_LENGTH':body['DATA_LENGTH'],
                                      'CHAR_USED':body['CHAR_USED']}
                print('R5_ITEM_METADATA', canonical(self.item_metadata), flush=True)
                declaration = ''.join((vector['VECTOR_INFO'] or '').upper().split())
                if declaration not in accepted:
                    raise Stop('DEV_VECTOR_DECLARATION_NOT_VERIFIED: ' + str(vector['VECTOR_INFO']))
            super().preflight(db, key)

    db = connection({'params':params})
    try:
        identity = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER FROM DUAL")
        if identity != [{'LOGIN_USER':login}]:
            raise Stop('DEV_DB_USER_MISMATCH:' + str(identity))
        # Require Oracle's vector dictionary field before creating test objects.
        db.query('SELECT VECTOR_INFO FROM ALL_TAB_COLUMNS WHERE 1=0')
        with TemporaryDirectory(prefix='gold-dev-vector-r5-') as directory:
            path = Path(directory)/'contract.json'
            path.write_text(json.dumps(configured), encoding='utf-8')
            setup = DevTables(path)
            setup.create(db, lambda event, **fields: print(event, fields['table'], flush=True))
            contract = Contract(path)

        document = 'dev-r5-vector-document'
        unit = '한' * 33 + 'x'
        values = [0.25, -0.5, 0.75, 1.25] * 256
        item = {'id':'dev-r5-vector-segment', 'meta':{'document_id':document, 'source_id':unit}}
        post = digest('dev-r5-vector-post-v1')
        query = digest('dev-r5-vector-query-v1')
        check_coordinates(contract, [item], {document})
        rows = rows_for(post, [item], [values])
        post_body = canonical({'document':document, 'source':unit, 'segment':item['id'],
                               'dimensions':len(values), 'format':'FLOAT32'})
        # Read only the fixed test keys. Written rows and recovered rows must pass identical checks.
        def write_and_read(key, select, statement):
            records = db.query(select)
            action = 'REUSED'
            if not records:
                sql, binds = statement
                db.block(sql, binds, transaction_managed=True)
                action = 'INSERTED'
                records = db.query(select)
            if len(records) != 1:
                raise Stop('DEV_VECTOR_READBACK_COUNT:' + key + ':' + str(len(records)))
            return action, records[0]

        actions = {}
        select_item = (
            'SELECT RGLT_DOC_ID AS DOC_ID,BODY_UNIT_ID,LENGTHB(BODY_UNIT_ID) AS N_BYTES,'
            'VCTR_DTLS_IFMN_CTNT AS META,VECTOR_DIMENSION_COUNT(EMBD_VCTR) AS N_DIM,'
            'VECTOR_DIMENSION_FORMAT(EMBD_VCTR) AS FMT,'
            'VECTOR_SERIALIZE(EMBD_VCTR RETURNING CLOB) AS COORDS FROM ' + contract.table('VCTR_ITEM')
            + ' WHERE VCTR_POST_ID=' + literal(post) + ' AND VCTR_SCTN_ID=' + literal(item['id']))
        actions['VCTR_ITEM'], saved = write_and_read('VCTR_ITEM', select_item,
                                                     vector_sql(contract, rows, len(values)))
        if (saved['DOC_ID'] != document or saved['BODY_UNIT_ID'] != unit or saved['N_BYTES'] != 100
                or saved['N_DIM'] != len(values) or saved['FMT'] != 'FLOAT32'
                or json.loads(saved['META']) != item['meta'] or json.loads(saved['COORDS']) != values):
            raise Stop('DEV_VECTOR_ITEM_VALUE_MISMATCH: bytes=' + str(saved['N_BYTES'])
                       + ', dimensions=' + str(saved['N_DIM']) + ', format=' + str(saved['FMT']))
        post_row = {'VCTR_POST_ID':post, 'VCTR_POST_IFMN_CTNT':post_body}
        select_post = ('SELECT VCTR_POST_IFMN_CTNT AS BODY FROM ' + contract.table('VCTR_POST')
                       + ' WHERE VCTR_POST_ID=' + literal(post))
        actions['VCTR_POST'], saved_post = write_and_read('VCTR_POST', select_post,
                                                          contract.batch('VCTR_POST', [post_row]))
        if saved_post['BODY'] != post_body:
            raise Stop('DEV_VECTOR_POST_BODY_MISMATCH')

        head_row = {'RFRN_POST_HASH_VALU':query, 'VCTR_POST_ID':post, 'CHAN_NO':1}
        select_head = ('SELECT VCTR_POST_ID,CHAN_NO FROM ' + contract.table('VCTR_HEAD')
                       + ' WHERE RFRN_POST_HASH_VALU=' + literal(query))
        actions['VCTR_HEAD'], saved_head = write_and_read(
            'VCTR_HEAD', select_head, OracleContract.batch(contract, 'VCTR_HEAD', [head_row]))
        if saved_head != {'VCTR_POST_ID':post, 'CHAN_NO':1}:
            raise Stop('DEV_VECTOR_HEAD_LINK_MISMATCH')
        return {'status':'DEV_R5_VECTOR_3_TABLES_PASS', 'owner':owner, 'tables':names,
                'metadata':setup.item_metadata, 'stored_id_bytes':saved['N_BYTES'],
                'stored_dimensions':saved['N_DIM'], 'stored_format':saved['FMT'],
                'coordinates_compared':len(values), 'head_channel':saved_head['CHAN_NO'],
                'matching_rows':{key:1 for key in actions}, 'actions':actions}
    finally:
        db.close()
