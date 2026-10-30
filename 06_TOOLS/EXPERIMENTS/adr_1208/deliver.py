"""Publish the independent local entry and evidence only after all checks pass."""
from pathlib import Path
import json,hashlib,sys,shutil,csv,datetime
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector';D=A/'artifacts/design';RUN=A/'artifacts/run-001';OUT=R/'08_DEPLOYMENT/LOCAL/gold_connection_cm_r12'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(R))
def main():
    imported=read(RUN/'import-result.json');vectors=read(RUN/'vector-result.json');data_checks=read(RUN/'checks-result.json');vector_checks=read(RUN/'vector-checks-result.json')
    assert imported['status']=='COMPLETE_SCOPED_DATA' and vectors['status']=='COMPLETE'
    assert data_checks['status']=='PASS_SCOPED_NATIVE_DATA_CONTRACTS' and vector_checks['status']=='PASS_NATIVE_VECTOR_CONTRACTS'
    assert read(RUN/'readonly-checks.json')['status']=='PASS'
    freeze=read(D/'freeze.json');entry=R/freeze['code_root']/'08_DEPLOYMENT/LOCAL/gold_connection_r12/gold_api.py'
    sys.path.insert(0,str(entry.parent));import gold_lab as g
    preserved={};before=read(R/'09_ARTIFACTS/AUDITS/20261029-old-db-cleanup/current-db-after.json')
    for name,h in before.items():
        preserved[name]=sha(R/name)
        if preserved[name]!=h:raise RuntimeError('CURRENT_ORIGINAL_CHANGED:'+name)
    for name,h in freeze['files'].items():
        if sha(R/name)!=h:raise RuntimeError('FROZEN_INPUT_CHANGED:'+name)
    save(RUN/'originals-after.json',preserved)
    with g.owner_connection() as c,g.admin() as admin:
        cfg=g.config(g.read(g.PRIVATE)['user'])
        counts={t['suffix']:g.scalar(c,'SELECT COUNT(*) FROM '+cfg.table(t['suffix'])) for t in cfg.model['tables']}
        total=g.oracle_guard(admin);target=g.scalar(c,'SELECT SUM(bytes) FROM user_segments')
        segments=list(c.cursor().execute('SELECT segment_type,SUM(bytes) FROM user_segments GROUP BY segment_type'))
        resources=g.guard()
    selected=read(D/'selected-documents.json');plan=read(RUN/'vector-plan.json')
    result={'status':'COMPLETE_SCOPED_NATIVE_GOLD_EXPERIMENT','selected_documents':len(selected['documents']),'parent_documents':1547,'whole_corpus_migrated':False,'CM':data_checks['details']['cm'],'oracle_total_user_bytes':total,'oracle_target_bytes':target,'oracle_limit_bytes':12000000000,'oracle_budget_bytes':9600000000,'oracle_limit_used_percent':total/120000000,'native_counts':counts,'segments':segments,'data_checks':data_checks['passed'],'vector_checks':vector_checks['passed'],'vectors':vectors,'vector_coverage':plan,'resources':resources,'original_databases_unchanged':len(preserved),'selected_MAIN118_and_pointer_unchanged':True,'new_external_model_calls':0,'new_generative_model_calls':0,'existing_full_reasoning_application_tested':False,'legal_answer_quality_tested':False,'active_vector_head':vector_checks['active_head'],'final_frozen_revision':freeze['revision_id'],'import_revision':'rev-008'}
    save(RUN/'result.json',result)
    OUT.mkdir(parents=True,exist_ok=True);shutil.copyfile(entry.parent/'config_b03.json',OUT/'config_b03.json');save(OUT/'documents.json',selected)
    (OUT/'schema_B03.sql').write_text('-- Exact hash-pinned R12 DDL; reference only, target already exists.\n'+';\n\n'.join(cfg.ddl())+';\n')
    (OUT/'확인용_SELECT.sql').write_text('\n\n'.join([
        'SELECT DOC_ID,DOC_NAME FROM '+cfg.table('DOC_VER')+' ORDER BY DOC_ID;',
        'SELECT RFRN_CHNL_NAME,RFRN_POST_HASH_VALU,CHAN_NO FROM '+cfg.table('SRCH_CHNL')+';',
        'SELECT RFRN_POST_HASH_VALU,VCTR_POST_ID,CHAN_NO FROM '+cfg.table('VCTR_HEAD')+';',
        'SELECT DOC_ID,COUNT(*) AS SEGMENTS FROM '+cfg.table('VCTR_ITEM')+' GROUP BY DOC_ID ORDER BY DOC_ID;',
        'SELECT VCTR_POST_ID,VCTR_POST_IFMN_CTNT FROM '+cfg.table('VCTR_POST')+';'])+'\n')
    candidate=read(R/freeze['manifest_path']);revision=next(x for x in candidate['revisions'] if x['revision_id']==freeze['revision_id'])
    base=read(D/'baseline.json')['manifest']['code_root']
    pins={p:h for p,h in freeze['files'].items() if p.startswith(base+'/') or p.startswith('02_BACKEND/lawrag/pipeline/oracle') or p==rel(D/'baseline.json')}
    pins.update({row['frozen_path']:row['snapshot_sha256'] for row in revision['files']})
    for p in [OUT/'connect.py',OUT/'config_b03.json',OUT/'documents.json']:pins[rel(p)]=sha(p)
    save(OUT/'runtime.json',{'entry':rel(entry),'revision':freeze['revision_id'],'runtime_files':pins,'source_reads':'Oracle GOLD only; no SQLite fallback in the data API','credential_file':'~/.local/state/8-agent/gold-r12-1208/readonly-connection.json'})
    with (OUT/'선정문서.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['문서ID','문서명','CM필수','원문구간','구조단위'])
        for d in selected['documents']:w.writerow([d['document_id'],d['name'],True,d['source_blocks'],d['source_units']])
    guide=f'''R12 골드 연결 실험 — CM 필수 21문서

결과: Oracle에 13테이블·60컬럼을 만들고 CM 필수 문서 21종의 원문 전체를 적재했다.
원문 구간 {counts['DOC_BLK']:,}, 구조 단위 {counts['DOC_UNIT']:,}, 검색/연결 행 {counts['SRCH_ROW']:,}, 실제 BGE-M3 벡터 {counts['VCTR_ITEM']:,}개.
전체 비시스템 사용자 데이터/색인/LOB 사용량 {total/1e9:.3f} GB / 한도 12 GB ({total/120000000:.2f}%). 실험 상한 9.6 GB.
Oracle 용량과 C/WSL 파일 사용량은 별개다. 벡터·전체 원문/행 해시·SQL·권한·활성 선택 검증 증거는 ADR1208 artifacts/run-001에 있다.

실행 위치: /home/jin/8-AGENT
  .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py documents
  .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py search 이사회
  .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py references 3521c3aaa5a735fd
  .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py vector-search '상장주선인의 의무 인수와 보유 기간'
  .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py source 3521c3aaa5a735fd 0

공통 옵션은 명령 앞에 둔다:
  --config <R12 설정 JSON> --connection <비공개 연결 JSON> --scope <허용문서 JSON> --channel cm-r12
연결 JSON은 user/password/dsn 필드이며 소유자만 읽을 수 있는 0600 권한이어야 한다.
기본 연결 파일: ~/.local/state/8-agent/gold-r12-1208/readonly-connection.json
로컬 DSN: 127.0.0.1:11524/FREEPDB1, 독립 소유자: A8_GR12_CM1208.
기본 로그인 A8_GR12_CM1208_RO는 13테이블 SELECT만 허용한다. 스키마 소유자는 config_b03.json의 owner로 별도 지정한다. 적재 계정 파일 connection.json은 게시자 전용이다.
문서 범위는 documents.json의 documents[].document_id를 사용한다. 게시된 21종 밖으로 넓히면 거절한다.
reference-targets <출발문서ID> <참조ID>는 저장된 참조의 실제 원문을 반환한다. 허용·게시 범위 밖 대상은 TARGET_NOT_AVAILABLE_IN_SCOPE로 남긴다.
vector-search는 로컬 CPU 모델을 읽으므로 최초 로딩 시간이 든다. 512토큰을 넘는 질문은 잘라내지 않고 거절한다.

범위와 한계
- CM 51질문·100문서참조는 전부 문서에 대응한다. 조문 좌표는 99건 확인했고 cm-046 상법 1건은 기준 데이터에 좌표가 없어 문서 포함으로만 기록한다.
- CM 과거 ID 14개는 문서명으로 현행 원문에 대응했다. 과거 판본의 내용 동일성이나 법률 답변 정확성을 보장하지 않는다.
- 기존 1,547문서 전체를 넣은 결과가 아니다. 사용자 선택 3번에 따라 80% 한도 안의 21문서를 선정했다.
- 기존 검색 테이블에 전문검색 토큰 위치를 보존했다. 별도 전문검색 테이블은 추가하지 않았다.
- 문서/조문/블록, 참조 payload/body, 용어 출현과 연결된 의미 그래프는 보존했다. SQLite 물리 rowid 쌍과 재구성 가능한 참조 편의 VIEW는 중복 적재하지 않았다.
- 외부 전체 용어사전의 저작/이력 묶음과 기존 전체 추론 엔진은 이 실험 범위 밖이다. 온톨로지 3테이블은 빈 상태이며 승인된 온톨로지를 지어 넣지 않았다.
- 원문 선택과 법률 판단을 대신하는 자동 참조 조사 기능을 추가하지 않았다. 별도 데이터 API/CLI 연결이다.
- MAIN118, 기존 제품 코드 및 원본 DB 9개는 유지한다. B03 이름으로 실증했으며 B05 전체 적재나 GENOS 배포는 하지 않았다.

시험 DB 운영 변경
컨테이너 메모리 상한을 2.44GiB에서 4GiB로 늘리고, 10MiB redo 2개를 256MiB redo 3개로 교체했다.
기존 작은 redo 파일은 삭제하지 않았다. Oracle 자체 데이터/메모리 라이선스 제한은 유지한다.
로그 변경 중 CURRENT 로그 삭제는 Oracle이 거절했고, INACTIVE 확인/전환 후 완료했다. 실패 기록은 보존했다.
이 컨테이너의 다른 사용자 스키마는 삭제하지 않았다.
대량 입력 중 새 SRCH_ROW의 보조 색인4개를 일시 제거했다가 적재 후 동일 정의로 재생성했다. 기본키는 유지했고 최종11개 일반 색인을 검증했다. 중간 사용량 감소를 최종 절감으로 계산하지 않았다.
'''
    (OUT/'연결안내.txt').write_text(guide)
    (A/'artifacts/실험결과.txt').write_text(guide)
    m=read(A/'실험/manifest.json')
    m['dataset']['name']='CM51 mandatory current 21-document subset of MAIN118 corpus'
    m['runs'][0].update(status='complete',selection_rule='User chose subset Oracle option 3 with 80% ceiling. Every CM target document is mandatory; stratified native sample and 15% margin determine scope. All original text in the final 21 documents is retained.',sha256=sha(RUN/'result.json'))
    m['results'].update(status='complete',by_arm={'baseline':{'original_databases_unchanged':9},'gold-b03':result},comparisons=[],judge_disagreements=None,usage={'external_model_calls':0,'generative_model_calls':0,'document_vector_rows':counts['VCTR_ITEM']},latency={'import_seconds':imported['seconds'],'vector_build_seconds':vectors['seconds_this_attempt']},error_taxonomy=[{'kind':'29-document capacity exceeds limit','resolution':'user mandatory documents retained; scoped candidate reduced'},{'kind':'21-document global terms exceed conservative margin','resolution':'preserve selected occurrences and full connected term closure; remove unrelated global labels'},{'kind':'selected serving snapshot lacks offline publisher import path','resolution':'pin helper files separately'},{'kind':'redo checkpoint waits and one CURRENT-log drop rejection','resolution':'preserve failure; checkpoint/switch and replace only inactive redo groups'},{'kind':'question exact-title first audit used path-qualified source labels','resolution':'preserve initial result; canonical title pass finds 7 mentions and zero outside scope'}])
    m['results']['error_taxonomy'].extend([
        {'kind':'read-only negative test expected ORA-01031 but this server returned ORA-41900','resolution':'retain failed test log; accept the verified missing UPDATE privilege code; data privileges unchanged'},
        {'kind':'CM name check normalized only one side of a path-qualified title','resolution':'restore exact original/full-title comparison; original and GOLD names were already equal'},
        {'kind':'FP16 approximately normalized fresh cache probe produced dots slightly above one','resolution':'retain initial probe; independently re-encode three samples and renormalize in float32 for actual cosine'},
        {'kind':'fresh SRCH_ROW optimizer statistics absent; common-token query slow','resolution':'gather only this experiment schema statistics; one subsequent same-term query observed at 1.319 seconds, not a controlled benchmark'}])
    save(A/'실험/manifest.json',m)
    original=(A/'README.md').read_text();front=original.split('---',2)[1]
    front=front.replace('R12 골드 전체 이관·원문 연결·실제 벡터 및 독립 서비스 검증','R12 골드 CM 필수 문서 이관·원문 연결·실제 벡터 검증')
    body=f'''# ADR-1208: R12 골드 CM 필수 문서 이관·원문 연결·실제 벡터 검증

## 1. 결정 요약

사용자가 선택한 3번(Oracle 한도 내 부분 corpus)으로 CM 필수 21문서를 독립 B03 골드에 적재했다. 원문 전체와 연결/검색 행, 실제 BGE-M3 벡터를 검증했다. 전체 1,547문서 이관이나 기존 추론 엔진의 답변 품질 통과는 아니다. MAIN118 유지, 승격·GENOS 배포·메일 없음. Proposed / decision_eligible=false는 운영 승격 판단을 하지 않았음을 뜻한다.

## 2. 문제와 변경 전 구조

SQLite corpus 9파일 약 4.73GiB를 Oracle에 단순 복제하면 문자열 키와 PK·일반 색인만 약 12.40GiB로 Free 한도를 넘었다. 초기 전체 이관은 실행하지 않고 사용자의 부분 문서 선택을 반영했다. R12는 13테이블·60컬럼이며 전문검색은 기존 SRCH_ROW를 재사용한다.

## 3. 가설과 사전 판정 기준

고정한 스키마, 원문/행 무결성, 권한, 연결, 실제 벡터, 별도 파라미터 진입점을 보존하면서 9.6GB 상한 안에 CM 문서를 담을 수 있는지 확인한다. 누락·해시 오류·권한 확장·벡터의 암묵적 잘라내기·자원 한도 초과는 완료와 활성 선택을 거절한다. 원문 체인과 각 행 envelope 전수 해시 외에 기본키/저장 해시 multiset을 원본 stage와 별도 대조했다. 순서 없는 행집합에 대한 SHA256 합/건수 검증과 원문 순서 체인을 구분한다.

사전 기준과 사용자 선택에 따른 변경 이력은 artifacts/design/criteria.json, criteria-before-user-subset.json 및 selected-documents.json에 보존한다. 표본 용량 추정은 15% 여유와 512MiB 벡터 예산을 포함했다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | 읽기 전용 원본 | 현재 원문 9DB, MAIN118 | 원문/논리 행 대조 |
| gold-b03 | 독립 Oracle B03 | R12 13/60, CM21문서, 로컬 모델 | 구조·권한·실제 조회 계약 |

29문서 표본 예측은 초과했고, 21문서에 전체 용어 목록을 보존한 안도 보수적 한도를 넘었다. 최종안은 선택 원문 출현 용어와 연결된 의미 성분 전체를 유지하고 관련 없는 전역 용어를 제외했다. 중복 SQLite rowid 쌍과 재구성 가능한 참조 VIEW를 제외했으며 논리 출현쌍과 참조 payload/body는 보존했다. 후보/실패 기록을 덮어쓰지 않는다.

## 5. 데이터·모델·재현성

선택 코드 source-accordion-20261029-r1 466파일과 원문 세대를 hash 고정했다. 최종 후보 {freeze['revision_id']}, 적재 후보 rev-008. 데이터와 입력 해시는 artifacts/design/freeze*.json, source-release.json, query-release.json에 있다. BAAI/bge-m3 로컬 고정 파일, 1024차원 FLOAT32, COSINE, L2 정규화다. 입력은 최대 800문자·512토큰, 겹침 최대100문자로 원문을 빠짐없이 분할한다. 정확한 입력 hash/토큰/모델 파일/벡터 shard가 일치하는 과거 부분 캐시만 재사용하고 세 구간을 새 임베딩과 비교했다. 생성형 모델·외부 API 호출은 0이다.

CM 51질문의 100문서참조가 21현행문서에 대응하며 좌표는99건 확인했다. cm-046 상법1건은 기준 좌표가 없어 문서 포함만 확인한다. 과거 문서ID14개는 정확 문서명으로 대응했으며 판본 의미 동일성·정답의 법률 유효성은 검증하지 않았다.

## 6. 결과

| 항목 | 실제 결과 |
|---|---:|
| 문서 / 구조 단위 / 원문 구간 | {counts['DOC_VER']} / {counts['DOC_UNIT']} / {counts['DOC_BLK']} |
| 검색·연결 행 | {counts['SRCH_ROW']} |
| 실제 벡터 / 전수 재조회 검증 | {counts['VCTR_ITEM']} / {vectors['readback_verified']} |
| 데이터 계약 / 벡터 계약 통과 | {data_checks['passed']} / {vector_checks['passed']} |
| 전체 비시스템 사용자 데이터/색인/LOB | {total:,} bytes |
| 원본 DB / MAIN118 보존 | 9DB / 466파일과 active pointer |

원문·부모·블록 관계 누락 0. 전문검색3용어의 문서별 조문/단위 건수는 원 SQLite와 일치했다. CM 007/009/046 질문 벡터의 그룹별 exact cosine top10을 NumPy와 대조했고 단일문서 권한 필터에서도 확인했다. 정답/회귀율·paired answer 비교·법률 정확도는 측정하지 않았다.

## 7. 사례별 오류 분석

초기 offline publisher import 경로 오류, 용량 초과 29문서/21문서 전역용어안, CLOB 입력 방식 진단, 작은 redo 로그의 checkpoint 대기, CURRENT 로그 삭제 거절을 보존했다. 경로를 별도 pin하고, 필수 문서 보존 범위에서 중복/관련 없는 행을 줄였다. 메모리 상한4GiB와 redo256MiB 3개로 시험 환경을 조정했다. 오래된 작은 redo 파일은 삭제하지 않았다. 새 SRCH_ROW 보조 색인4개는 대량 입력 후 동일 정의로 재생성했고 PK는 유지했다. 최종 용량은 색인 복원 후 측정했다. 참조 원문이 게시 범위 밖이면 확보 완료로 표시하지 않는다. 질문명 감사 첫 버전의 경로 포함 이름 불일치도 보존하고 정정했다.

## 8. 비용·지연·회수 규모

전체 부모 corpus1,547문서 중21문서의 원문 전체를 사용했다. 적재 {imported['seconds']:.1f}초(진단·일시 정지 포함), 벡터 생성 단계 {vectors['seconds_this_attempt']:.1f}초이며 장치·다른 프로세스가 통제된 성능 비교는 아니다. 외부 비용·생성형 호출0. 실제 공간 {total/1e9:.3f}GB는12GB의{total/120000000:.2f}%이고9.6GB 실험 상한 안이다. C/WSL 여유 및 프로세스 자원은 result.json을 참조한다. 질문 정답을 위한 회수/탈락 실험이나 golden recall은 해당 없다. 기술 top10 검증을 검색 품질 인증으로 해석하지 않는다.

## 9. 해석

선정한21문서에 대해 R12 골드의 원문/구조/연결/전문검색/벡터 조회가 실제 Oracle에서 동작한다. JSON으로 묶은 메타와 활성 선택의 변경순번으로 hash 결속 및 stale/ABA 거절을 확인했다. 이 결과는 범위가 다른 전체 corpus의 용량이나 완성 답변의 정확성을 증명하지 않는다.

## 10. 한계와 일반화 가능 범위

독립 CLI와 데이터 API를 검증했으며 기존 전체 추론 엔진은 연결하지 않았다. 외부 전체 용어사전 저작/이력 묶음은 제외했다. ONTL3테이블은 빈 상태다. 선택 문서 밖의 참조는 식별자를 보존하되 원문 접근을 하지 않는다. B03만 실제 대량 적재했으며 B05는 이름 대안이다. 원문이 최신 법령인지, CM 과거 기준답변과 의미적으로 같은지, 실제007/009 답변이 통과하는지는 미검증이다.

## 11. 운영 결정·롤백 조건

기존 제품과 MAIN118은 유지한다. 독립 진입점은 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py이며 운영 승격은 아니다. 문제가 있으면 이 독립 진입점 사용을 중단하면 기존 서비스에 영향이 없다. 벡터 변경은 기존 publication/revision을 조건으로 CAS한다. 시험 owner만 별도 관리하며 다른 스키마·현재 원문9DB는 삭제하지 않는다. 불완전 publication을 활성화하지 않는다.

## 12. 재현 명령

```bash
.venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py search 이사회
.venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_cm_r12/connect.py vector-search '상장주선인의 의무 인수와 보유 기간'
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1208/exec_module.py gold_check
```

원시 결과는 [artifacts/run-001/result.json](artifacts/run-001/result.json), 연결 안내는 [실험결과.txt](artifacts/실험결과.txt), 질문/실험 범위는 [실험 manifest](실험/manifest.json)와 [질문 인덱스](실험/README.md)에 있다. 재이관 명령은 이미 있는 owner를 보존하며 자동 덮어쓰지 않는다.
'''
    (A/'README.md').write_text('---'+front+'---\n\n'+body)
    (A/'실험/README.md').write_text('''# ADR-1208 실험 인덱스

## 작업 선점

원본 reservation events는 manifest.json에 보존한다. 사용자 선택3번과80% 상한, CM필수 문서 보존을 반영했다.

## 계보

ADR-1208-experiment-v1 / gold-r12 / ROOT. baseline은 읽기 전용 현재 corpus, gold-b03은 별도 Oracle 후보다.

## 병합

해당 없음. 기존 MAIN118 유지.

## 다른 ADR과의 관계

0971의 입력/모델 hash가 맞는 부분 벡터 shard만 검증해 재사용했다. 과거 실패한 전체 publication을 활성화하지 않았다.

## Arm

baseline: 현재 원문/논리 검색행. gold-b03: CM필수21문서의 R12 Oracle 독립 연결.

## 질문 인덱스

새 생성형 답변 평가가 없으므로 질문별 답변/채점 파일은 없다. CM51질문의100문서참조와99좌표 대조는 checks-result.json, CM007/009/046의 실제 질문 벡터 수치/권한 검증은 vector-checks-result.json에 있다. 답변 정확도 통과를 의미하지 않는다.

## 집계

run-001 / complete. native schema·원문·논리행·권한·벡터 계약 결과는 ../artifacts/run-001/result.json. 정답률·paired 회귀·judge 불일치는 해당 없다.

## 단계별 회수·탈락 집계

retrieval-stage-ledger는 not_applicable이다. 데이터 이관과 exact 검색의 기술 계약을 확인했으며 회수 품질 또는 답변 품질 비교를 수행하지 않았다.
''')
    return result
if __name__=='__main__':print(json.dumps(main(),ensure_ascii=False,indent=2))
