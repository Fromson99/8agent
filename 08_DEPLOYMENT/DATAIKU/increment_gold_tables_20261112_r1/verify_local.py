"""로컬 Oracle(a8-legal-mapped) 임시 계정 2개로 전달 SQL을 소유자만 바꿔 그대로 실행하고 엑셀을 설계와 대조한다."""
import hashlib, json, secrets, sys
from pathlib import Path
import openpyxl, oracledb
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / '09_ARTIFACTS/AUDITS/20261110-dev-gold-align'))
from oracle_conn import connect  # noqa: E402
DSN = '127.0.0.1:11524/FREEPDB1'


def main():
    tag = secrets.token_hex(2).upper(); S, P = f'A8_IGS_{tag}', f'A8_IGP_{tag}'; pw = 'P' + secrets.token_hex(8)

    def stmts(name, old):
        out = {}
        for b in (HERE / name).read_text().split('-- [')[1:]:
            k = b.split(']', 1)[0]; q = b.split('\n', 1)[1].strip()
            out[k] = q.replace(old + '.', S + '.').replace("'%s'" % old, "'%s'" % S).replace('PIDD2APP', P)
        return out
    res = {}
    with connect() as admin:
        c = admin.cursor()
        for u in (S, P):
            c.execute(f'CREATE USER {u} IDENTIFIED BY "{pw}" QUOTA 20M ON USERS'); c.execute(f'GRANT CREATE SESSION TO {u}')
        c.execute(f'GRANT CREATE TABLE TO {S}')
        try:
            for sfx in ('SIDDS', 'SIDDG'):
                with oracledb.connect(user=S, password=pw, dsn=DSN) as cs:
                    for q in stmts(f'CREATE_INCREMENT_GOLD_{sfx}_R3.txt', sfx).values(): cs.cursor().execute(q)
                    for q in stmts(f'GRANT_INCREMENT_GOLD_{sfx}_R3.txt', sfx).values(): cs.cursor().execute(q)
                with oracledb.connect(user=P, password=pw, dsn=DSN) as cp:
                    cur = cp.cursor(); chk = stmts(f'CHECK_INCREMENT_GOLD_{sfx}_R3.txt', sfx)
                    for k in chk:
                        cur.execute(chk[k]); res[sfx + k] = cur.fetchall()
                    sha = hashlib.sha256(b'x').hexdigest()
                    cur.execute(f"INSERT INTO {S}.IDD_B003_LGL_RGLT_DOC (ORIG_DOC_ID,RGLT_DOC_NAME,ORIG_TYPE_VALU) VALUES ('LAW:012345',:n,'LAW')", n=('금융회사의 지배구조에 관한 법률 시행령' * 30)[:740])
                    cur.execute(f"INSERT INTO {S}.IDD_B003_LGL_RGLT_VER (RGLT_VER_ID,ORIG_DOC_ID,RGLT_DOC_ID,ORIG_FILE_NAME,OFNN_ASTM,ENFR_ASTM,VER_STAS_VALU,VER_ADDN_IFMN_CTNT) "
                                f"VALUES (:v,'LAW:012345',:d,:f,TIMESTAMP '2025-10-01 00:00:00 Asia/Seoul',TIMESTAMP '2026-01-01 00:00:00 Asia/Seoul','APPLIED','{{\"promulgation_no\":\"제2025-12호\"}}')",
                                v=sha, d=sha[:16], f=('금융회사의 지배구조에 관한 법률 본문' * 30)[:740] + '.xml')
                    cur.execute(f"UPDATE {S}.IDD_B003_LGL_RGLT_DOC SET ATIV_VER_ID=:v, CHAN_ASTM=SYSTIMESTAMP", v=sha)
                    cur.execute(f"INSERT INTO {S}.IDD_B003_LGL_ARTC_CMPR (RGLT_VER_ID,CMPR_NO,CHAN_TYPE_VALU,TRNF_CTNT_KEY_ID,AFTE_CTNT_KEY_ID,TRNF_CTNT,AFTE_CTNT,CMPR_ADDN_IFMN_CTNT) "
                                f"VALUES (:v,1,'AMEND','제26조','제26조','이전','이후','{{\"similarity\":0.8732}}')", v=sha)
                    cur.execute(f"SELECT TO_CHAR(ENFR_ASTM AT TIME ZONE 'Asia/Seoul','YYYYMMDD') FROM {S}.IDD_B003_LGL_RGLT_VER"); res[sfx + 'enfc'] = cur.fetchone()[0]
                    try:
                        cur.execute(f"DELETE FROM {S}.IDD_B003_LGL_ARTC_CMPR"); res[sfx + 'del'] = 'allowed'
                    except oracledb.DatabaseError as e:
                        res[sfx + 'del'] = str(e).split(':')[0]
                    cp.rollback()
                with oracledb.connect(user=S, password=pw, dsn=DSN) as cs:
                    for k in ('ARTC_CMPR', 'RGLT_VER', 'RGLT_DOC'): cs.cursor().execute(f'DROP TABLE IDD_B003_LGL_{k} PURGE')
        finally:
            for u in (P, S): c.execute(f'DROP USER {u} CASCADE')
    out = {}
    for sfx in ('SIDDS', 'SIDDG'):
        out[sfx] = {'tables': len(res[sfx + 'Q01']), 'column_diffs': len(res[sfx + 'Q02']), 'key_diffs': len(res[sfx + 'Q03']),
                    'grants': [r[1] for r in res[sfx + 'Q04']], 'enforcement_date': res[sfx + 'enfc'], 'delete': res[sfx + 'del']}
        assert out[sfx]['tables'] == 3 and not out[sfx]['column_diffs'] and not out[sfx]['key_diffs'] and len(out[sfx]['grants']) == 3
    assert out['SIDDS']['delete'] == 'allowed' and out['SIDDG']['delete'] != 'allowed'
    wb = openpyxl.load_workbook(HERE / '법률에이전트_B003_증분Gold_메타등록_R3.xlsx')
    D = json.loads((HERE / 'INCREMENT_GOLD_DESIGN_R3.json').read_text())
    diffs = 0
    for key, sheet in zip(['RGLT_DOC', 'RGLT_VER', 'ARTC_CMPR'], ['01_규정문서', '02_규정판본', '03_조문비교']):
        rows = list(wb[sheet].iter_rows(values_only=True)); i = next(i for i, r in enumerate(rows) if r[0] == '논리명') + 1
        diffs += sum((r[0], r[1], r[5]) != (c['logical'], c['name'], c['type']) for r, c in zip(rows[i:], D[key]['columns']))
    assert diffs == 0
    out['excel_vs_design_diffs'] = diffs
    out['result'] = 'PASS'
    print(json.dumps(out, ensure_ascii=False))
    return out


if __name__ == '__main__':
    main()
