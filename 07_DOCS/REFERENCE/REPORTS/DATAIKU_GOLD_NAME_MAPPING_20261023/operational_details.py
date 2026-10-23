"""Operational review metadata only; no database access or executable migration."""
from metadata_details import IO, MIG, ASSET, CAT, STATE

RUN = '08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r1/src/dataiku_run.py'
PACKAGE = '02_BACKEND/lawrag/pipeline/oracle_query_package.py'

LOAD = {
    'document': ('일반 적재', 'source.transfer(run→verify)', 'DATASET_VERSION + DOCUMENT_ID', '불변 INSERT; 기존 동일 PK의 전체 값 대조, 다른 값이면 중단', MIG),
    'source_unit': ('일반 적재', 'source.transfer(run→verify)', 'DATASET_VERSION + DOCUMENT_ID + UNIT_ID', '불변 INSERT; 부모 ID·원천 JSON까지 비교, 다른 값이면 중단', MIG),
    'block_payload': ('일반 적재', 'source.transfer(run→verify)', 'DATASET_VERSION + DOCUMENT_ID + BLOCK_ID', '불변 INSERT; TEXT·JSON·NULL·생략 여부를 비교, 다른 값이면 중단', MIG),
    'asset_part': ('일반 적재', 'assets.publish / put_part', 'ASSET_SHA256 + PART_NO', '같은 hash·순번의 압축 해제 바이트가 같으면 재사용; 다르면 중단', ASSET),
    'source_release': ('일반 적재', 'assets.publish / put_release', 'RELEASE_ID', '같은 완료 manifest면 재사용; 등록일시는 신규 INSERT 기본값, 기존 행 시각 유지', ASSET),
    'query_row': ('일반 적재', 'query.import_db / insert_records', 'RELEASE_ID + KIND + ROW_ID', '동일 PK의 행 hash·JSON·보조키 대조; 다른 내용 덮어쓰기 금지', CAT+'; '+PACKAGE),
    'query_release': ('일반 적재', 'query.import_db', 'RELEASE_ID', '조회 행 검증 후 완료 manifest INSERT; 기존 동일 게시본 재확인', PACKAGE),
    'query_active': ('별도 활성화', 'activate', 'CHANNEL', '기대 release·revision을 조건으로 INSERT 또는 UPDATE; 현재 선택을 다시 읽어 응답 불명 해소', CAT),
    'query_state': ('별도 상태 소비자', 'State.put/read', 'SCOPE_HASH + STATE_KEY', '기대 revision·이전 hash를 조건으로 갱신; 정확히 같은 목표 상태면 재사용', STATE),
}


def lineage(key, name):
    """Return source field/object and transform boundary, not an invented JSON schema."""
    if key in {'document', 'source_unit', 'block_payload'}:
        if name == 'DATASET_VERSION':
            return 'returned/generation/manifest.json 원시 바이트', 'SHA-256 파생값', MIG+':source_binding'
        return ('returned/generation/store.sqlite :: '+key+'.'+('json' if name == 'SOURCE_JSON' else name.lower()),
                '원천 값 유지; 물리명만 변환', MIG+':source_batch')
    if key == 'query_row':
        if name == 'RELEASE_ID':
            return 'query/query-data.db :: metadata[query_manifest]', '완료 명세 digest', PACKAGE+':import_db'
        field = {'ROW_SHA256':'sha256','VALUE_JSON':'value'}.get(name, name.lower())
        return ('query/query-data.db :: query_row.body.'+field,
                '검증된 논리 행 필드 보존; VALUE_JSON은 json_body(value)', PACKAGE+':import_db; '+CAT+':insert_records')
    if key == 'source_release':
        field = {'RELEASE_ID':'검증 완료 source release 객체', 'DATASET_VERSION':'source release.dataset_version',
                 'RELEASE_JSON':'검증 완료 source release 객체', 'CREATED_AT':'대상 Oracle DB SYSTIMESTAMP'}[name]
        return field, 'digest/직렬화/신규 DB 기본값은 컬럼 생성 규칙 참조', ASSET+':put_release'
    if key == 'query_release':
        return 'query/query-data.db :: metadata[query_manifest]', 'RELEASE_ID=digest; MANIFEST_JSON=JSON 직렬화', PACKAGE+':import_db'
    if key == 'asset_part':
        field = {'ASSET_SHA256':'선택 자산 manifest의 파일 SHA-256', 'PART_NO':'파일 분할 순번(0부터)',
                 'RAW_BYTES':'압축 전 조각 바이트 길이', 'PART_SHA256':'압축 전 조각 SHA-256',
                 'DATA_B64':'선택 자산의 원본 조각 바이트'}[name]
        return field, '분할·zlib·Base64; 컬럼 생성 규칙 참조', ASSET+':put_part'
    if key == 'query_active':
        return '명시 활성화 요청과 현재 채널 선택', 'release 검증 및 기대 revision 비교 후 저장', CAT+':activate'
    return '상태 소비자의 scope·key·value와 현재 revision', '복합 hash와 기대 revision을 결속; 자동 이력 이행 아님', STATE+':State.put'


def build_operational_details(mapping):
    tables = mapping['tables']
    lineages, loads, access, approvals = [], [], [], []
    for key, table in tables.items():
        mode, entry, duplicate, behavior, evidence = LOAD[key]
        load = {'논리테이블ID':key, '테이블명후보':table['candidate_name'], '실행구분':mode,
                '적재진입점':entry, '중복판단키':duplicate, '갱신재처리규칙':behavior,
                '완료판정':table['metadata']['description_fields']['갱신주기와완료기준'],
                '실패재개': '원래 입력·대상·예산·단계 receipt 보존 후 재조회; 원인 해소 전 맹목 재실행 금지',
                '삭제교체':'기존 판본 자동 삭제 없음. 보유기간·참조 중인 판본·복원 경로 확인 후 별도 정책',
                '현재구현근거':evidence, '현장검증':'미수행; 현재 코드 계약과 개명 후 실행 성공은 별도'}
        loads.append(load)
        json_fields = [c['candidate_name'] for c in table['columns'].values()
                       if c['legacy_name'] in {'SOURCE_JSON','VALUE_JSON','MANIFEST_JSON','RELEASE_JSON'}]
        scope = ('문서별 공개/내부·권한 범위를 보존; 문서명·본문·JSON만으로 공개 판정 금지'
                 if key in {'document','source_unit','block_payload','query_row'} else
                 '범위 hash 자체가 접근권한은 아님; 상태 소비자의 사용자·세션 권한 결속 필요'
                 if key=='query_state' else '명세·선택값·자산도 원문 범위에 종속; 전체 공개 권한으로 자동 취급하지 않음')
        permissions = ('게시 담당 SELECT/INSERT/UPDATE; 서빙 SELECT'
                       if key=='query_active' else '상태 소비자 SELECT/INSERT/UPDATE'
                       if key=='query_state' else '적재 담당 SELECT/INSERT; 조회 담당 SELECT')
        if key=='asset_part':
            permissions='이관·검증 담당 SELECT/INSERT; 서빙의 전체 자산 복원 경로 사용 금지'
        ac = {'논리테이블ID':key, '테이블명후보':table['candidate_name'], '저장책임':table['storage_role'],
              '권한범위':scope, '최소업무권한초안':permissions,
              '민감정보확인':'미실측. 원문 및 JSON 내부의 개인정보·내부정보 포함 여부를 원천 책임자와 확인',
              'JSON내부계약':(', '.join(json_fields)+'의 필수키·판본·종류별 계약은 기존 소비자/manifest를 따름. IS JSON만으로 의미 검증 완료 아님') if json_fields else '해당 없음: 별도 JSON 컬럼 없음',
              '보유와삭제':'공식 보유기간·삭제/비활성화 절차 미확정. 원문·완료판본·실패 이력 임의 삭제 금지',
              '권한확인':'계정·역할·교차 owner grant·문서 범위 적용을 Silver/Gold에서 각각 확인; 현재 미검증'}
        access.append(ac)
        stage = {'논리테이블ID':key, '테이블명후보':table['candidate_name'],
                 '명칭상태':'미승인 후보','메타신청번호':'미신청','메타승인번호일자':'미승인',
                 'DBA생성신청':'미신청','개발생성':'미수행','개발검증근거':'미수행',
                 '운영생성':'미수행','운영검증근거':'미수행','활성전환':'미수행',
                 '담당자와목표일':'현장 확인 필요',
                 'DBA검토':'행 수·일 증가량·CLOB/인덱스 용량·문자셋·BYTE/CHAR·실행계획·파티션 필요성 미실측; 임의 기본값 지정 안 함',
                 '물리객체정의':'YAML의 PK/FK/CHECK/index 정의와 실제 DB 대조. PK에 따른 인덱스와 추가 조회 인덱스 4개 구분',
                 '복원기준':'이전 승인 map/profile·테이블·릴리스 보존; 신규 적재와 활성 선택 전환을 구분'}
        approvals.append(stage)
        table['metadata']['operational_review'] = {'status':'DESIGN_ONLY_NOT_ENFORCED',
            'load':load, 'access_retention':ac, 'approval_tracking':stage}
        for cid, col in table['columns'].items():
            source, transform, ev = lineage(key, col['legacy_name'])
            row = {'논리테이블ID':key,'테이블명후보':table['candidate_name'],'컬럼명후보':col['candidate_name'],
                   '한글논리명':col['logical_name_ko_candidate'],'원천필드객체':source,
                   '변환경계':transform,'상세생성규칙':col['metadata']['derivation'],
                   '비교기준':'기존 내부 키·값으로 복원해 대조; 컬럼 개명 때문에 payload key·내용 hash를 바꾸지 않음',
                   '근거':ev,'확인상태':'코드 계약 대조; 현장 전수검증 미수행'}
            col['metadata']['lineage_review']=row
            lineages.append(row)

    # Logical references include manifest bindings; only one is a physical FK today.
    relations=[]
    definitions=[
        ('source_unit','document','DATA_VER_ID + DOC_ID','여러 구조 단위 → 문서 1건','논리 관계; 물리 FK 없음','UNIT_ID만으로 타 문서와 결합 금지'),
        ('source_unit','source_unit','같은 DATA_VER_ID + DOC_ID에서 PRNT_UNIT_ID = UNIT_ID','루트 제외 단위 → 상위 단위 1건','논리 관계; 물리 FK 없음','편·장·절 표시 번호만 비교 금지; 순환·고아 관계 검사 필요'),
        ('block_payload','document','DATA_VER_ID + DOC_ID','여러 블록 → 문서 1건','논리 관계; 물리 FK 없음','문서명으로 결합 금지'),
        ('block_payload','source_unit','DATA_VER_ID + DOC_ID + UNIT_ID','여러 블록 → 구조 단위 0 또는 1건','논리 관계; 물리 FK 없음','NULL UNIT_ID는 별도 상태로 보존; 임의 부모 생성 금지'),
        ('query_row','query_release','SRCH_PBLS_ID','여러 조회 행 → 완료 조회 게시 1건','논리 관계; 물리 FK 없음','조회 행 선적재와 완료 manifest 게시를 구분'),
        ('query_active','query_release','SRCH_PBLS_ID','여러 채널 → 완료 조회 게시 1건','현행 DDL 물리 FK 있음','채널별 현재 선택; 전체 과거 이력은 포함 안 됨'),
        ('query_release','source_release','조회 manifest.source_release_id = SRC_PBLS_ID','조회 게시 → 원문 게시 1건','manifest 내부 참조','두 테이블의 게시 ID끼리 단순 동등 조인 금지'),
        ('query_row','document','조회 manifest의 DATA_VER_ID + 조회 행 DOC_ID','문서 소속 조회 행 → 문서 1건; 공통 용어 행은 해당 없음','manifest + 논리 관계','ROW_ID를 DOC_ID로 사용 금지; 문서 없는 행의 권한도 별도 확인'),
        ('source_release','asset_part','원문 manifest.assets[].sha256 = FILE_HASH_VAL; PART_SEQ_NO','게시 ↔ 자산 여러 개; 자산 → 조각 여러 개','manifest 내부 참조','파일 hash 기준 공유 가능. 조각 순서·전체 hash 확인 필요'),
    ]
    for i,(left,right,join,cardinality,kind,caution) in enumerate(definitions,1):
        relations.append({'관계ID':f'R{i:02d}','출발논리ID':left,'도착논리ID':right,
                          '출발테이블':tables[left]['candidate_name'],'도착테이블':tables[right]['candidate_name'],
                          '결합조건':join,'관계와건수':cardinality,'물리FK여부':kind,'주의':caution,
                          '검증상태':'설계/DDL 계약 대조; 데이터 고아·중복 검사 미수행'})

    quality=[]
    checks=[
        ('대상과 스키마','원격 작업 요청 전','owner·컬럼·타입·NULL·PK/FK/CHECK/index·권한이 승인 map과 일치','현재 고정 이름 검사 존재; 공통 SchemaMap 검사 미구현','불일치 대상을 명시하고 해당 대상 작업 중단','사전 검사 담당'),
        ('원천과 적재 내용','적재 및 재개','테이블별 원천 범위의 행 수·PK·본문·NULL·hash 일치','현재 원문/자산/조회 readback 존재; 개명 경로 미구현','확정 receipt 보존 후 같은 PK 재조회; 다른 값 덮어쓰기 금지','Dataiku 적재 담당'),
        ('구조 결합','게시 전','같은 세대·문서에서 부모 참조와 순환·고아 관계 확인','관계 정의 보강; 이 문서가 전수 구조 검증을 수행한 것은 아님','결함 원문·경로를 기록하고 해당 판본 게시 판단 분리','구조화 검증 담당'),
        ('JSON 내부 계약','투영 생성 및 조회','종류별 schema/필수키·판본·값/hash 계약 일치','JSON/manifest/hash 검사 존재; 전 종류 필드 사전은 후속 명세화 필요','미지원 종류·버전·구문 오류를 정상 빈 값으로 바꾸지 않음','투영 계약 담당'),
        ('완료 판정과 ACK','결과 수신부터 DB 검증','최종 성공은 목표 DB readback 뒤; ACK 전 반환물의 승인 저장소 보존 확인','현재 로컬 반환물 복원 후 ACK, 이후 Oracle 적재. 지속 보관 자동 보장 미확인','GENOS 완료·다운로드·적재 완료를 분리; 보관 검증 또는 적재 후 ACK로 개선','Dataiku 실행 담당'),
        ('부분 실패와 재개','중단·중복 요청·응답 유실','동일 job/입력/대상/결과와 누적 예산을 보존하고 미완료 단계 재개','단계 receipt 존재; notebook 소실 이후 자동 복구 미구현/미확인','자동 재시도는 복구 담당 한 곳; 설정된 한도 소진 시 원인 보존 종료','해당 단계 실행 담당'),
        ('권한과 정보 범위','원문·검색·상태 조회','허용 문서·세션·판본 범위 밖 반환/저장 없음','Records 문서 필터 존재; 실제 계정·grant·소비자 연결 현장 검증 필요','권한 오류를 빈 검색 결과나 원문 부재로 표시하지 않음','인증된 조회/상태 소비자'),
        ('채널 선택과 복원','게시 검증 후 별도 활성화','완료 조회 게시만 revision 조건으로 선택, 변경 후 재조회','activate CAS 존재; 일반 load_oracle은 active_changed=false','응답 불명 시 현 선택 재조회; 이전 release와 현재 revision으로 명시 복원','게시 전환 담당'),
        ('원문 시점 구분','메타 정의와 소비자 연결','법령 시행일·데이터 구축 세대·DB 등록일시를 구분','CREATED_AT은 DB 등록일시. 모든 테이블에 시행일/갱신일 컬럼은 없음','필요 필드는 원천 위치 확인 후 별도 스키마 변경; 날짜 추정 금지','데이터 모델 담당'),
        ('업무 의미 미확인','LLM 해석/연결 결과 검토','불확실성·미확보는 설명과 근거에 보존; 기술 오류와 구분','기존 정책 기준; 이번 매핑은 의미 정확도 시험이 아님','의미 불확실성만으로 전체 배치 자동 중단 금지; 권한/hash 오류는 별도 차단','업무 검토 담당'),
    ]
    for i,(name,when,rule,current,failure,owner) in enumerate(checks,1):
        quality.append({'검사ID':f'Q{i:02d}','항목':name,'검사시점':when,'통과목표':rule,
                        '현재확인과차이':current,'실패시처리':failure,'복구책임':owner,
                        '새이름현장검사결과':'미수행','실행증거경로':'미확보'})
    mapping['operational_review']={'status':'DESIGN_ONLY_NOT_ENFORCED','relationships':relations,
                                   'quality_checks':quality,
                                   'runtime_policy_note':'아래 검토 설명은 실행 설정이 아님. 갱신/권한/검증 규칙을 실제 코드 설정으로 구현할 때는 별도 버전과 실행 지문에 포함.'}
    return [
        ('컬럼계보','COLUMN_LINEAGE.csv',lineages),('관계결합','TABLE_RELATIONSHIPS.csv',relations),
        ('적재재처리','LOAD_RULES.csv',loads),('품질완료기준','QUALITY_RULES.csv',quality),
        ('권한보존','ACCESS_RETENTION.csv',access),('승인진행','APPROVAL_TRACKING.csv',approvals),
    ]
