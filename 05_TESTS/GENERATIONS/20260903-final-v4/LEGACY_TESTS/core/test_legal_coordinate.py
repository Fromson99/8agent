from lawrag.core.legal_coordinate import (
    LegalCoordinate,
    find_coordinates,
    parse_label,
)
from lawrag.core.rag import refs


def test_문서_라벨과_질문_참조가_같은_조문_키를_쓴다():
    cases = [
        ("제4조(목적)", "이 법 제4조에 따른다", ("조", 4, None)),
        ("제4조의2(특례)", "제4조의2제3항에 따른다", ("조", 4, 2)),
        ("제2-42조(감독)", "제2-42조제2항을 적용한다",
         ("조", 2, ("dash", 42, None))),
        ("제3장", "제3장의 규율", ("장", 3, None)),
        ("별지 제2호", "별지 제2호를 제출한다", ("별지", 2, None)),
    ]

    for label, question, expected in cases:
        document_coordinate = parse_label(label)
        question_coordinate = find_coordinates(question)[0].coordinate
        assert document_coordinate is not None
        assert document_coordinate.key() == question_coordinate.key() == expected
        assert refs.label_key(label) == refs.find(question)[0].key() == expected


def test_질문_하강_사슬도_LegalCoordinate에_보존된다():
    coordinate = find_coordinates("제15조제2항제1호나목")[0].coordinate

    assert coordinate == LegalCoordinate(
        "조", 15, chain=(("항", 2), ("호", 1), ("목", 2)))
    assert parse_label("제2항").key() == ("항", 2, None)
    assert parse_label("제1호").key() == ("호", 1, None)
    assert parse_label("나.").key() == ("목", 2, None)


def test_열거_참조는_앞_조문을_공유한다():
    coordinates = [row.coordinate for row in
                   find_coordinates("제22조제1항ㆍ제3항 또는 제4항")]

    assert [coordinate.n for coordinate in coordinates] == [22, 22, 22]
    assert [coordinate.chain for coordinate in coordinates] == [
        (("항", 1),), (("항", 3),), (("항", 4),),
    ]


def test_Ref는_공통_좌표를_공개하면서_기존_필드를_유지한다():
    ref = refs.find("제2-4조제5항제3호다목")[0]

    assert ref.coordinate == LegalCoordinate(
        "조", 2, dash=4,
        chain=(("항", 5), ("호", 3), ("목", 3)))
    assert (ref.unit, ref.n, ref.dash, ref.sub) == ("조", 2, 4, None)
    assert ref.key() == ("조", 2, ("dash", 4, None))


def test_비좌표_문구는_공통_파서가_추측하지_않는다():
    assert parse_label("목적") is None
    assert find_coordinates("15조 2항을 알려줘") == []
    assert find_coordinates("제2항만 알려줘") == []


def test_XML에서_쓰는_큰_항번호도_공통_좌표로_정규화한다():
    assert parse_label("㊿").canonical_surface() == "제50항"
    assert parse_label("<16>").canonical_surface() == "제16항"
    assert find_coordinates("제1000조제50항")[0].coordinate.canonical_surface() \
        == "제1000조제50항"
