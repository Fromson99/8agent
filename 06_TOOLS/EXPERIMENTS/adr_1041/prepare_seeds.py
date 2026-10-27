#!/usr/bin/env python3
"""Materialize source-bound, unapproved ADR-1041 seed drafts without model calls.

Selections below were made by reading the selected generation's own unit blocks.
No subtree expansion, product registry selection, approval, or live calls occur.
The review corpus is separate from runtime bundles. Use --output for a fresh copy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import sqlite3
import unicodedata

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / '01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
SEEDS = ROOT / '07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/SEED_ARTICLES_20261024.json'
CM = ROOT / '09_ARTIFACTS/AUDITS/20261024-cm-rebind/CM51_SOURCE_PACKAGE_SELECTION_20261015.json'
STAMP = '2026-10-24T00:00:00+09:00'  # source-review date; not a live-run timestamp
DOCS = {
 'gov':'금융회사의 지배구조에 관한 법률', 'govd':'금융회사의 지배구조에 관한 법률 시행령',
 'ven':'벤처기업육성에 관한 특별법','vend':'벤처기업육성에 관한 특별법 시행령',
 'com':'상법','gift':'상속세 및 증여세법','giftd':'상속세 및 증여세법 시행령',
 'income':'소득세법','incomed':'소득세법 시행령','credit':'신용정보의 이용 및 보호에 관한 법률',
 'cap':'자본시장과 금융투자업에 관한 법률','capd':'자본시장과 금융투자업에 관한 법률 시행령',
 'capr':'자본시장과 금융투자업에 관한 법률 시행규칙','tax':'조세특례제한법',
 'audit':'주식회사 등의 외부감사에 관한 법률','auditd':'주식회사 등의 외부감사에 관한 법률 시행령',
 'sme':'중소기업기본법','startupd':'중소기업창업 지원법 시행령',
 'uw':'증권 인수업무 등에 관한 규정','disclose':'증권의 발행 및 공시 등에 관한 규정',
 'kosdaq':'코스닥시장 상장규정','kosdaqr':'코스닥시장 상장규정 시행세칙',
 'risk':'금융투자회사의 리스크관리 모범규준','fin':'금융투자업규정',
 'annex1':'금융투자회사의 리스크관리 모범규준 별표 17-1',
 'annex2':'금융투자회사의 리스크관리 모범규준 별표 17-2',
}
ANNEX = {'annex1':'4b6659619110921b','annex2':'d15cde8add9a9d74'}
R='REQUIREMENT'; S='SCOPE'; D='DEFINITION'; E='EXCEPTION'; P='PROCEDURE'; T='THRESHOLD'; F='EFFECT'
def group(doc, units, role, note):
 return (doc, [int(x) for x in units.split()] if isinstance(units,str) else list(units), role, note)
def edge(a,u,kind,b,v): return (a,u,kind,b,v)
# Deliberate, enumerated own-block selections. Ranges below are explicit reviewed
# adjacent unit IDs, never a runtime subtree read or a document-wide expansion.
PLANS = [
('금융회사 상근임원의 겸직 제한과 승인·보고 범위',[
 group('gov',range(79,88),S,'상근 임원 겸직의 원칙과 법정 예외 범위'),
 group('gov','96 97 98 99 100',P,'겸직 승인·보고의 적용범위와 보고사항'),
 group('govd','245',P,'사외이사·비상임이사·비상근감사의 겸직 보고 범위')],
 [edge('gov',96,'CITES','gov',83),edge('gov',100,'DELEGATES_TO','govd',245)],
 ['제10조제4항의 금융지주회사 그룹 특례와 시행령 제11조의 전체 승인절차는 이 묶음에 넣지 않았다. 비상근 겸직의 적용성은 원문과 사실관계로 별도 판단한다.']),
('준법감시인·위험관리책임자의 겸직 금지와 예외',[
 group('gov',range(244,250),R,'겸직 금지 업무의 본문과 각 호'),
 group('govd','389 401',S,'상호저축은행 본질적 업무의 위임 범위'),
 group('govd','403 404 405',E,'준법감시·위험관리 겸직과 자산총액 조건')],
 [edge('gov',246,'DELEGATES_TO','govd',389),edge('gov',249,'DELEGATES_TO','govd',403)],
 ['시행령 제20조제2항과 자산총액 판단시점의 외부 근거는 이 묶음에서 확보하지 않았다.']),
('금융회사 주요주주의 사실상 영향력 범위',[
 group('gov','2 15 17',D,'대주주 중 주요주주의 정의와 상위 본문'),
 group('govd',range(28,33),D,'주요주주의 위임받은 범위')],
 [edge('gov',17,'DELEGATES_TO','govd',28)],[]),
('벤처기업 주식매수선택권의 시가 평가',[
 group('vend','169',R,'시가 평가에 관한 명시 준용 및 기간 치환'),
 group('gift','616 617 619 620',S,'시가 원칙·상장주식과 보충적 평가의 범위'),
 group('giftd',range(1038,1057),R,'평가기간·거래유형·제외조건·판단일·유사재산·자본적지출')],
 [edge('vend',169,'APPLIES_MUTATIS_MUTANDIS','gift',616),edge('vend',169,'APPLIES_MUTATIS_MUTANDIS','giftd',1038)],
 ['준용 시 평가기간 문구의 치환은 시행령 제11조의3제2항 원문에 따른다. 상증세법 시행령 제49조의 감정기관 제재 등 제6항 이후는 제외했다. 외부 평가방법의 모든 하위 위임을 확보한 것은 아니다.']),
('벤처기업 주식매수선택권의 부여·행사가격 기준',[
 group('ven',range(245,258),R,'부여대상·방법·한도·행사가격 및 예외'),
 group('ven','277 278',S,'벤처법 우선 적용과 보충 적용 범위'),
 group('com','1060 1066 1067 1068',R,'상법의 부여 원칙과 행사가액 기준'),
 group('com','1087',P,'신주발행 시 명시 준용 조문'),
 group('com','1772',T,'주주총회 특별결의 정족수'),
 group('vend',range(169,178),R,'시가 평가·제외대상·전문가·저가부여 한도')],
 [edge('ven',245,'APPLIES_MUTATIS_MUTANDIS','com',1772),edge('ven',277,'CITES','com',1060),edge('ven',277,'CITES','com',1087),edge('ven',257,'DELEGATES_TO','vend',177),edge('ven',248,'DELEGATES_TO','vend',171)],
 ['제16조의6제3항의 우선 적용 조건을 먼저 확인한다. 상법 제340조의2·제340조의5를 벤처법보다 우선하는 규칙으로 적용하지 않는다. 상법 시행령 제30조제2항은 남은 연결이다.']),
('벤처기업 주식매수선택권의 행사기간과 예외',[
 group('ven','272 273',R,'재임·재직기간과 양도금지·상속 예외'),
 group('vend','179 180 181 182',E,'비귀책 퇴직·전문가 용역계약과 간주 조건'),
 group('ven','245 248',S,'전문가 부여대상과 상위 본문'),
 group('ven','270',P,'이사회가 부여사항을 정하는 경우의 조건')],
 [edge('ven',272,'DELEGATES_TO','vend',179),edge('ven',272,'DELEGATES_TO','vend',181),edge('ven',272,'CITES','ven',245),edge('ven',272,'CITES','ven',270),edge('vend',181,'DEEMS','vend',182)],[]),
('벤처기업 주식매수선택권의 신고',[
 group('ven','275',P,'부여·취소·철회의 신고 의무'),
 group('vend',range(184,189),P,'신고서와 첨부서류'),
 group('ven',range(265,271),P,'신고의 전제가 되는 주총·이사회 결의')],
 [edge('ven',275,'DELEGATES_TO','vend',184),edge('ven',275,'CITES','ven',265),edge('ven',275,'CITES','ven',270)],[]),
('자기주식 소각 원칙과 주총 승인 보유·처분 예외',[
 group('com',range(1109,1117),R,'소각기한과 보유·처분 예외 및 매년 승인'),
 group('com','1772',T,'경영상 목적 사유를 정관에 정하는 특별결의')],
 [edge('com',1109,'HAS_EXCEPTION','com',1110),edge('com',1115,'CITES','com',1772)],
 ['자기주식보유처분계획의 기재사항(제4항)은 별도 검토 대상이다. 시행일·경과조치는 이 묶음에서 확인하지 않았다.']),
('자기주식의 주주 외 처분 범위',[
 group('com',range(1127,1134),R,'균등 처분 원칙·예외·결정사항·준용'),
 group('com','1110 1112 1113 1114 1115',E,'참조된 제341조의4제2항 본문과 제2호부터 제5호')],
 [edge('com',1127,'HAS_EXCEPTION','com',1128),edge('com',1128,'CITES','com',1112),edge('com',1128,'CITES','com',1113),edge('com',1128,'CITES','com',1114),edge('com',1128,'CITES','com',1115)],
 ['제341조의4제2항의 계획·주총 승인 본문을 함께 포함했다. 제1호의 균등 처분은 제342조제2항이 지정한 예외 범위에 넣지 않았다.']),
('감사 보수 결정과 상장회사 별도 의결',[
 group('com','1676',S,'감사에 이사 보수 규정의 준용'),group('com','1502',R,'정관 또는 주총의 보수 결정'),group('com','2460',P,'상장회사의 감사 보수 의안 별도 상정·의결')],
 [edge('com',1676,'APPLIES_MUTATIS_MUTANDIS','com',1502),edge('com',2460,'BASED_ON','com',1502)],
 ['제542조의12제5항은 같은 보수 결정의 절차 조건으로 연결한 의미 제안이다. 보수 위임의 구체적 허용 범위에 관한 판례는 이 묶음에 없다.']),
('상장회사 독립이사와 사외이사 정의',[
 group('com','2412',R,'독립이사 정의 및 구성비율'),group('com',range(1467,1475),D,'사외이사 정의와 결격 조건')],
 [edge('com',2412,'USES_DEFINITION','com',1467)],
 ['현행 선택 원문의 독립이사·사외이사 문구를 그대로 결속했다. 개정 전후 차이와 시행일은 이 묶음의 원문만으로 확정하지 않는다.']),
('주식 상장이익 계산과 취득·증여가액',[
 group('giftd',range(498,502),R,'이익 산식의 피감수·차감액'),group('gift','279 280 281',S,'저가양수 이익의 증여 범위'),group('gift',range(296,302),S,'저가 신주 발행에 따른 증여 범위')],
 [edge('giftd',500,'UNKNOWN','gift',279),edge('giftd',500,'UNKNOWN','gift',296)],
 ['선정표는 제35조·제39조를 조건·예외로 제시했으나, 선택 원문의 시행령 제31조의3에서 이 조문을 직접 참조하거나 이미 과세된 저가분의 조정을 정하는 문구를 확인하지 못했다. 관계는 UNKNOWN이며 조정 결론을 제공하지 않는다. 사용자 검토가 필요하다.']),
('시가 인정 평가기간과 평가심의',[
 group('giftd',range(1038,1050),R,'평가기간·매매·감정·수용 등과 제외조건'),
 group('giftd','1068 1069 1089 1090',P,'평가기간 밖 가액의 심의·신청 근거'),
 group('giftd','1514 1515 1516',T,'법정결정기한의 구분')],
 [edge('giftd',1038,'CITES','giftd',1068),edge('giftd',1038,'CITES','giftd',1514),edge('giftd',1069,'CITES','giftd',1038)],
 ['제49조의2·제78조는 직접 인용으로 결속했다. 선정표의 준용·위임 구분을 원문상 명시된 관계보다 강하게 확정하지 않았다.']),
('기업공개 준비 주식의 평가기간과 공모가격',[
 group('giftd','1227 1228 1229 1230',R,'기업공개·등록 준비기간과 큰 가액 선택'),
 group('gift','641 642 643 644 647 648 649',S,'상장·비상장 주식 평가와 기업공개 특례의 상위 조건')],
 [edge('gift',648,'DELEGATES_TO','giftd',1227),edge('gift',649,'DELEGATES_TO','giftd',1230),edge('giftd',1229,'CITES','gift',643),edge('giftd',1229,'CITES','gift',644)],[]),
('주식 상장에 따른 이익 증여의 성립과 계산',[
 group('gift',range(346,360),R,'주체·취득 경로·기간·정산·간주·부정행위 예외'),
 group('giftd',range(498,512),R,'이익 계산·시장 범위·기준금액·기업가치 증가·조정')],
 [edge('gift',359,'DELEGATES_TO','giftd',498),edge('gift',346,'DELEGATES_TO','giftd',502),edge('gift',346,'DELEGATES_TO','giftd',503),edge('gift',348,'DELEGATES_TO','giftd',506)],[]),
('주식매수선택권 행사취득 주식의 취득가액',[
 group('incomed','2414',F,'행사 당시 시가를 취득가액으로 하는 규정'),
 group('income','1191 1192 1193 1194',S,'필요경비 중 취득가액과 상위 조건')],
 [edge('incomed',2414,'CITES','income',1192)],
 ['행사취득 특칙을 취득가액 일반 규정과 연결했다. 문언은 준용이 아니라 취득가액으로 정하는 규정이므로 CITES로 보존했다.']),
('개인신용정보의 식별 가능성과 처리 위탁',[
 group('credit','289 292 293 294',R,'위탁·보호조치·관리·이용 및 제3자 제공'),
 group('credit','2 3 4 7 24 25 37 38 39 40 71 73 74 75 76 77 78',D,'신용정보·개인신용정보·처리·가명·익명의 해당 정의')],
 [edge('credit',289,'USES_DEFINITION','credit',3),edge('credit',292,'USES_DEFINITION','credit',37),edge('credit',289,'USES_DEFINITION','credit',71)],
 ['다른 정보와의 결합 가능성은 개별 사실관계로 판단한다. 이름·계좌번호 삭제만으로 익명처리를 확정하지 않는다.']),
('사업보고서 제출의무와 증권별 소유자 수 예외',[
 group('cap','1459',R,'사업보고서 제출 원칙과 위임된 예외'),
 group('capd','2991 2999 3000 3001 3003 3007',E,'모집·매출 발행인과 증권별 소유자 수 면제 조건')],
 [edge('cap',1459,'DELEGATES_TO','capd',2991),edge('cap',1459,'DELEGATES_TO','capd',3003)],
 ['제167조제1항제1호 각 목의 증권 전체 목록은 남은 연결이다. 소유자 수 계산방법의 고시는 이 묶음에 포함하지 않았다.']),
('우리사주조합원 우선배정 특례',[
 group('cap','1565 1566 1567 1568',R,'우선배정 비율과 제외·초과 조건'),
 group('com','1700 1701',S,'주주의 신주인수권 일반 원칙과 제3자 배정')],
 [edge('com',1700,'HAS_EXCEPTION','cap',1565)],
 ['제165조의7의 문언은 상법 제418조에도 불구하고 적용되는 특례다. 선정표의 준용·편입을 그대로 준용 관계로 사용하지 않았다. 위임된 시행령 예외는 남은 연결이다.']),
('금융투자업 업무위탁과 계약·보고',[
 group('cap',range(427,433),R,'업무위탁 허용 범위와 계약사항'),
 group('cap','438 439 440 441 442',R,'인가·재위탁·정보·운영기준·통지'),
 group('capd',range(792,802),P,'업무위탁 보고시점·첨부서류·계약내용')],
 [edge('cap',428,'DELEGATES_TO','capd',792),edge('cap',432,'DELEGATES_TO','capd',798)],
 ['제3자 투자자문을 참고하는 행위가 업무위탁인지는 실제 업무수행 구조에 대한 판단으로 남긴다.']),
('벤처기업 주식매수선택권 행사이익 비과세 범위',[
 group('tax','487 488 489',R,'비과세 기간·한도·적용 선택권·절차 위임'),
 group('ven','245 246 247',D,'벤처기업 임직원·인수기업 임직원 선택권'),
 group('com','1060 2385',D,'상법상 주식매수선택권과 상장회사 관계회사 대상')],
 [edge('tax',488,'USES_DEFINITION','ven',245),edge('tax',488,'USES_DEFINITION','com',1060),edge('tax',488,'USES_DEFINITION','com',2385)],
 ['상법 선택권에는 코넥스상장기업이라는 적용 제한이 붙는 제16조의2제2항을 함께 유지한다.']),
('적격주식매수선택권의 행사·양도 과세특례',[
 group('tax',range(498,513),R,'적격요건·행사 및 양도 과세·사후과세·전용계좌'),
 group('ven','245 246 247',D,'선택권 정의와 부여 대상'),
 group('income','1152 1158 1159 1160 1161',S,'주식 양도소득의 일반 범위')],
 [edge('tax',499,'USES_DEFINITION','ven',245),edge('income',1158,'HAS_EXCEPTION','tax',501)],
 ['소득세법 제94조제1항제3호와의 관계는 준용이 아니라 특례다. 조특법 시행령의 추가 적격요건은 남은 연결이다.']),
('내부회계관리제도 구축의무와 면제범위',[
 group('audit',range(52,59),R,'구축 의무와 규정에 포함할 사항'),
 group('auditd',range(88,97),E,'위임된 면제대상 및 면제의 제외조건')],
 [edge('audit',52,'DELEGATES_TO','auditd',88)],
 ['시행령 제9조제2항의 내부회계관리규정 세부사항은 별도 연결로 남긴다.']),
('인수업무 이해관계 보유비율의 완화 적용대상',[
 group('uw','274 276 277 278',R,'이해관계 범위와 10퍼센트 기준 적용대상'),
 group('sme',range(2,10),D,'중소기업의 대상·조건과 제외 범위'),
 group('sme','11',E,'규모 확대 시 중소기업 간주와 제외'),
 group('startupd',range(43,49),E,'제외 업종과 분류 기준')],
 [edge('uw',276,'USES_DEFINITION','sme',2),edge('uw',276,'EXCLUDES','startupd',43)],
 ['원문 파서가 제15조제4항제2호의 가~라목을 한 own-block에 보존했다. 더 작은 독립 unit이 없어 그 전체 블록을 결속한다.']),
('공동주관 의무와 보유비율 산정·제외',[
 group('uw',range(96,114),R,'공동주관 기준·예외·보유비율·확약과 의무보유'),
 group('kosdaq','180 181 182 183',S,'제13조제5항제1호의 국내기업 의무취득 범위'),
 group('uw','2 11 15',D,'이해관계인·주식등 정의와 상위 본문'),
 group('uw','274 276 277 278',E,'완화된 보유비율이 적용되는 발행회사 조건'),
 group('capr',range(126,138),R,'명시 준용된 주식등 수의 산정방법')],
 [edge('uw',99,'APPLIES_MUTATIS_MUTANDIS','capr',126),edge('uw',100,'CITES','kosdaq',181),edge('uw',96,'USES_DEFINITION','uw',11),edge('uw',96,'USES_DEFINITION','uw',15),edge('uw',96,'CITES','uw',276)],
 ['시행규칙 제14조제1항만 명시 준용하므로 제2항·제3항을 자동 편입하지 않았다.']),
('증권신고서 분기 검토보고서 첨부 범위',[
 group('disclose','275 276 280',P,'기존 법인 지분증권의 분기보고서 첨부'),
 group('disclose','169 182 186',D,'분기감사·검토보고서의 적용대상과 상위 본문'),
 group('capd','3036 3040 3041 3045 3046 3050',S,'분기 감사의견·첨부서류 대상의 원문 범위')],
 [edge('disclose',280,'USES_DEFINITION','disclose',186),edge('disclose',186,'CITES','capd',3040)],
 ['제2-4조의 참조는 시행령 제170조제1항제2호 단서이고, 현 선택 원문에는 제2항제2호와 제3항제2호도 함께 존재한다. 참조 시점·항 이동 여부는 임의 정정하지 않고 검토 대상으로 남긴다.']),
('상장주선인 취득가격과 공모가격의 괴리율',[
 group('kosdaqr','231 232 233 234',R,'괴리율의 취득가격·공모가격·산식'),
 group('uw','40 41 42 43 44',D,'명시 참조된 공모가격 결정방법')],
 [edge('kosdaqr',233,'USES_DEFINITION','uw',40)],[]),
('상장주선인의 국내기업 의무취득·보유기간과 면제',[
 group('kosdaq','180 181 182 183 187 188 189',R,'국내기업 의무취득·보유와 면제 범위'),
 group('kosdaqr','90',E,'혁신기술기업 주선 시 기간 연장 조건'),
 group('kosdaq','350 351 352 353 358 359 360',S,'면제 제외에 인용된 신속이전기업 마·바목과 공통 요건')],
 [edge('kosdaq',183,'DELEGATES_TO','kosdaqr',90),edge('kosdaq',188,'CITES','kosdaq',358),edge('kosdaq',188,'CITES','kosdaq',359)],
 ['제31조제1항제3호의 마·바목만 선택했으며 무관한 가~라목은 편입하지 않았다.']),
('제3자배정과 벤처금융·전문투자자 신규상장 의무보유',[
 group('kosdaq','283 286 287',R,'제3자배정·벤처금융 및 전문투자자의 기준과 상위 본문'),
 group('kosdaqr','218 220 227 228 229 230',E,'제3호의 벤처금융·전문투자자 예외와 제4호의 예외')],
 [edge('kosdaq',286,'DELEGATES_TO','kosdaqr',218),edge('kosdaq',287,'DELEGATES_TO','kosdaqr',227)],
 ['제23조제4항에서는 이 개념에 해당하는 제2호와 상위 본문만 골랐다. 다른 취득자에 대한 예외는 포함하지 않았다.']),
('PF 사업성평가·건전성·충당금과 경공매 기준',[
 group('risk','509 510 511',R,'평가·분류·충당금 및 경공매의 본문 기준'),
 group('annex1','0 2 3',S,'사업성 평가원칙·건전성 연결·사후관리 및 예외'),
 group('annex2','0 1 2',E,'경공매 착수 원칙·연기·제외와 기록'),
 group('fin','507 508 516 517 518',S,'건전성 분류 대상과 상위 본문'),
 group('fin','524',R,'충당금·대손준비금 구분'),
 group('fin',range(530,542),T,'PF 자산 표준비율과 일반 예외')],
 [edge('risk',510,'ANNEX_STANDARD','annex1',0),edge('risk',510,'ANNEX_STANDARD','annex1',2),edge('risk',511,'ANNEX_STANDARD','annex2',0),edge('risk',509,'BASED_ON','fin',507),edge('risk',509,'BASED_ON','fin',524)],
 ['별표는 별도 파일의 실제 document_id로 결속했다. 별표17-1의 개별 평가등급 예시 전체와 별표17-2의 공매 절차·가격은 이 묶음의 최소 범위 밖이다. 모범규준과 금융투자업규정의 BASED_ON은 검토할 의미관계 제안이다.']),
('자본적지출액 등 필요경비의 범위',[
 group('income','1191 1195',S,'필요경비의 상위 본문과 자본적지출액 위임'),
 group('incomed','2378',R,'각 항목에 공통인 증빙 조건'),
 group('incomed',range(2379,2386),S,'위임받은 자본적지출액 등 각 호')],
 [edge('income',1195,'DELEGATES_TO','incomed',2378)],
 ['필요경비 전체 중 자본적지출액만 온톨로지화한 묶음이다. 취득가액·양도비 및 제67조제2항 등 세부 참조는 남은 연결로 조사한다.']),
]


def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def encode(value) -> bytes: return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def exact_write(path: Path,data: bytes):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  if path.read_bytes()!=data: raise RuntimeError(f'Refusing to overwrite immutable output: {path}')
 else:
  with path.open('xb') as f: f.write(data)

class Store:
 def __init__(self):
  self.db=sqlite3.connect(GEN.joinpath('store.sqlite').as_uri()+'?mode=ro',uri=True)
  self.db.row_factory=sqlite3.Row
  self.db.execute('PRAGMA query_only=ON');self.db.execute('PRAGMA cache_size=-8192')
  self.docs={}
 def doc(self,key):
  if key in self.docs:return self.docs[key]
  if key in ANNEX: rows=list(self.db.execute('SELECT * FROM document WHERE document_id=?',(ANNEX[key],)))
  else:rows=list(self.db.execute('SELECT * FROM document WHERE name=? OR name LIKE ?',(DOCS[key],'% > '+DOCS[key])))
  if len(rows)!=1:raise ValueError(f'Ambiguous document {key}: {len(rows)}')
  self.docs[key]=dict(rows[0]);return self.docs[key]
 def unit(self,key,uid):
  d=self.doc(key);rows=list(self.db.execute('SELECT * FROM source_unit WHERE document_id=? AND unit_id=?',(d['document_id'],str(uid))))
  if len(rows)!=1:raise ValueError(f'Missing/duplicate unit {key}/{uid}')
  u=dict(rows[0]);j=json.loads(u['json'])
  blocks=list(self.db.execute('SELECT block_id,text,source_artifact_sha256 FROM block_payload WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(d['document_id'],str(uid))))
  if not blocks or any(not str(b['block_id']).isdigit() for b in blocks):raise ValueError(f'Invalid own blocks {key}/{uid}')
  if any(b['source_artifact_sha256']!=d['source_artifact_sha256'] for b in blocks):raise ValueError(f'Artifact mismatch {key}/{uid}')
  text='\n'.join(b['text'] for b in blocks)
  if not text.strip():raise ValueError(f'Empty text {key}/{uid}')
  coordinate=j.get('coordinate_key');suffix=coordinate.split(':',1)[1] if coordinate else (j.get('title') or j.get('surface'))
  if not suffix:raise ValueError(f'Missing label {key}/{uid}')
  anchor={'document_id':d['document_id'],'version':d['source_artifact_sha256'],'unit_id':str(uid),'content_sha256':sha(text.encode('utf-8')),'label':DOCS[key]+' '+suffix}
  review={'anchor':anchor,'document_name':d['name'],'coordinate_key':coordinate,'parent_id':u['parent_id'],'block_ids':[b['block_id'] for b in blocks],'text':text}
  return anchor,review

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'01_DATA/ONTOLOGY_WORK');args=parser.parse_args()
 resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
 s=json.loads(SEEDS.read_text());cm=json.loads(CM.read_text());manifest=json.loads(GEN.joinpath('manifest.json').read_text())
 if len(PLANS)!=31 or len(s['seeds'])!=31:raise ValueError('Expected exactly 31 seeds')
 st=Store();bundle_records=[];source_reviews={};questions=set()
 for i,(concept,groups,edges,notes) in enumerate(PLANS):
  selected={};provisions=[];selected_reviews=[]
  for key,units,role,note in groups:
   for uid in units:
    ident=(key,uid)
    if ident in selected:raise ValueError(f'Duplicate provision in seed {i}: {ident}')
    a,rv=st.unit(key,uid);selected[ident]=a['label'];provisions.append({'anchor':a,'role':role,'value':None,'note':note});selected_reviews.append(rv)
    source_reviews[(a['document_id'],a['unit_id'])]=rv
  if len(set(selected.values()))!=len(selected):raise ValueError('Duplicate labels')
  relations=[{'from':selected[(a,u)],'type':kind,'to':selected[(b,v)],'target_status':'CONFIRMED'} for a,u,kind,b,v in edges]
  # Exact published ID serialization: normalized name + newline + sorted unit IDs.
  name=' '.join(unicodedata.normalize('NFC',concept).split())
  id_input=name+'\n'+'\n'.join(sorted(p['anchor']['unit_id'] for p in provisions))
  bid='cb-'+sha(id_input.encode('utf-8'))[:12]
  bundle={'schema_version':'ontology-bundle-v0','bundle_id':bid,'revision':1,'status':'CANDIDATE','concept':{'label':concept,'glossary_ref':None,'kind':'NEW_CONCEPT_CANDIDATE'},'provisions':provisions,'relations':relations,
   'review_notes':['사용자 미승인 초안. CONFIRMED는 연결 끝점의 원문 위치 확인을 뜻하며 법률 의미·적용성 승인을 뜻하지 않는다.','원문 판본은 현재 선택 세대의 source_artifact_sha256이다. 법령 시행일을 대신하는 날짜 표기가 아니다.','기존 조사 범위 안에서만 읽고 범위 밖 조항은 미확보로 표시한다. 승인으로 조사 범위가 넓어지지 않는다.']+notes,
   'evidence_judgments':[],'proposed_by':{'model':None,'run_id':'ADR-1041/manual-seed','at':STAMP},'history':[]}
  path=Path('bundles')/bid/'r1.json';data=encode(bundle)
  exact_write(args.output/path,data);exact_write(args.output/'bundles'/bid/'HEAD.json',encode({'bundle_id':bid,'revision':1,'status':'CANDIDATE'}))
  qids=[q['case_id'] for q in s['seeds'][i]['questions']];questions.update(qids)
  bundle_records.append({'seed_index':i+1,'seed_article':s['seeds'][i]['anchor'],'bundle_id':bid,'concept':concept,'path':str(path),'sha256':sha(data),'status':'CANDIDATE','question_ids':qids,'provision_count':len(provisions),'relations':len(relations),'bundle_bytes':len(data),'source_text_chars':sum(len(r['text']) for r in selected_reviews),'review_notes':notes})
 # Rebind audit verifies metadata/coordinates; no reference answers enter outputs.
 rebind=[]
 for case in cm['cases']:
  if case['case_id'] not in questions:continue
  for e in case['entries']:
   row=st.db.execute("SELECT d.source_artifact_sha256,u.json FROM document d JOIN source_unit u ON d.document_id=u.document_id WHERE d.document_id=? AND u.unit_id=?",(e['selected_document_id'],e['selected_unit_id'])).fetchone()
   if row is None or row['source_artifact_sha256']!=e['source_artifact_sha256'] or json.loads(row['json']).get('coordinate_key')!=e['coordinate_key']:raise ValueError('CM rebind mismatch')
   rebind.append({'case_id':case['case_id'],'document_id':e['selected_document_id'],'unit_id':e['selected_unit_id'],'coordinate_key':e['coordinate_key'],'source_artifact_sha256':e['source_artifact_sha256']})
 if len(questions)!=37:raise ValueError(f'Expected 37 distinct question IDs, got {len(questions)}')
 review={'schema_version':'ontology-seed-review-v0','status':'CANDIDATE_USER_REVIEW_REQUIRED','run_id':'ADR-1041/manual-seed','created_on':'2026-10-24','source_generation_id':manifest['generation_id'],'source_manifest_sha256':sha(GEN.joinpath('manifest.json').read_bytes()),'store_sha256_declared_in_manifest':manifest['store_sha256'],'store_full_hash_recomputed':False,'seed_selection_sha256':sha(SEEDS.read_bytes()),'cm_rebind_sha256':sha(CM.read_bytes()),'source_text_hash_rule':'sha256(UTF-8(newline.join(own block text ordered by numeric block_id)))','version_representation':'source_artifact_sha256','bundle_id_input_rule':'NFC normalized concept with collapsed whitespace + newline + lexicographically sorted unit_id strings joined by newline','approval':None,'runtime_snapshot_created':False,'live_model_calls':0,'counts':{'bundles':len(bundle_records),'questions':len(questions),'unique_source_units':len(source_reviews),'max_provisions':max(b['provision_count'] for b in bundle_records),'max_source_text_chars':max(b['source_text_chars'] for b in bundle_records)},'bundles':bundle_records,'cm_rebind_checks':rebind,'limitations':['모든 묶음은 CANDIDATE이며 사용자 승인 전 실험에 사용할 수 없다.','관계·역할·최소 범위는 원문을 읽고 작성한 검토 제안이며 법률 정답이 아니다.','기준답변과 판정 주석은 생성 입력·출력에 넣지 않았다.','선정표의 오래된 CANDIDATE 상태와 무관하게 시험문항 수는 사용자 확정 37개를 사용한다.','일부 직접 연결되지 않는 의미관계는 UNKNOWN 또는 검토 메모로 보존했다.','SOURCE_REVIEW.jsonl은 검토용 원문이며 제품 묶음 스냅샷에 넣지 않는다.']}
 exact_write(args.output/'review/ADR-1041/SEED_REVIEW.json',encode(review))
 raw=b''.join((json.dumps(v,ensure_ascii=False)+'\n').encode() for _,v in sorted(source_reviews.items()))
 exact_write(args.output/'review/ADR-1041/SOURCE_REVIEW.jsonl',raw)
 cols=['seed_index','concept','seed_article','bundle_id','provision_count','question_ids','review_notes']
 rows=['\t'.join(cols)]+['\t'.join(str(b[k]) if k not in ('question_ids','review_notes') else ' | '.join(b[k]) for k in cols) for b in bundle_records]
 exact_write(args.output/'review/ADR-1041/SEED_REVIEW.tsv',('\n'.join(rows)+'\n').encode())
 print(json.dumps({'output':str(args.output),'counts':review['counts'],'status':review['status'],'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},ensure_ascii=False))

if __name__=='__main__':main()
