"""One target-free JDBC roundtrip before loading with the new codec."""
from jdbc_transport import expression, utf8_chunks


def check(db):
    # Exceeds the gzip branch threshold; includes supplementary Unicode and SQL-looking text.
    value = ("한글𠀀😀'\\\n:payload -- /* */\t" * 1200) + '끝'
    parts = [
        'DECLARE expected CLOB; comparison INTEGER; BEGIN',
        'DBMS_LOB.CREATETEMPORARY(expected,TRUE,DBMS_LOB.CALL);',
    ]
    # Independent, uncompressed reference. No target table reads or writes.
    parts.extend('DBMS_LOB.APPEND(expected,TO_CLOB('+expression(raw)+'));'
                 for raw in utf8_chunks(value))
    parts.extend([
        'comparison:=DBMS_LOB.COMPARE(:transport_check,expected);',
        "IF comparison IS NULL OR comparison<>0 THEN RAISE_APPLICATION_ERROR(-20064,'TRANSPORT_ROUNDTRIP_MISMATCH'); END IF;",
        'DBMS_LOB.FREETEMPORARY(expected);',
        'EXCEPTION WHEN OTHERS THEN',
        'IF DBMS_LOB.ISTEMPORARY(expected)=1 THEN DBMS_LOB.FREETEMPORARY(expected); END IF;',
        'RAISE; END;',
    ])
    db.block('\n'.join(parts), [('transport_check',value,'CLOB')], rollback=True)
