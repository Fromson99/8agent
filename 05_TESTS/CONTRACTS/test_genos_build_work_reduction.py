"""Deterministic lexical reuse never changes indexed tokens or grows unbounded."""
from semantic_runtime import fulltext


def reset():
    with fulltext._TOKEN_FORM_LOCK:
        fulltext._TOKEN_FORMS.clear();fulltext._TOKEN_FORM_BYTES=0


def test_cached_forms_are_exact_for_korean_and_native_markers():
    reset()
    for text in ('제2조의3 승인 절차', '가. 신용등급 (1) A+ 업무용어0042', '은행 임직원 및 보증채무', '', 'αβ Ⅳ－３ ①\n예외\t공시', '본 문서의 별표 1 및 제12조를 따른다.'):
        expected=fulltext._uncached_search_forms(text)
        assert fulltext._search_forms(text)==expected
        assert fulltext._search_forms(text)==expected


def test_cache_reuses_only_completed_forms_and_is_bounded(monkeypatch):
    reset();calls=[]
    def compute(text):calls.append(len(text));return text*3
    monkeypatch.setattr(fulltext,'_uncached_search_forms',compute)
    assert fulltext._search_forms('반복')=='반복'*3
    assert fulltext._search_forms('반복')=='반복'*3
    assert calls==[2]
    for i in range(400):
        fulltext._search_forms(str(i)+'X'*15000)
        assert fulltext._TOKEN_FORM_BYTES<=fulltext._TOKEN_FORM_LIMIT
        assert len(fulltext._TOKEN_FORMS)<=256
    count=len(fulltext._TOKEN_FORMS);large='Z'*16385
    fulltext._search_forms(large);fulltext._search_forms(large)
    assert len(fulltext._TOKEN_FORMS)==count
    assert calls[-2:]==[16385,16385]
    reset()
