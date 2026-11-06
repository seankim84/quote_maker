"""네트워크 없이 입력 검증·응답 검증·Mock 추출만 검사합니다."""

import pytest

from core.extract import (MAX_INPUT_CHARS, ExtractError, check_input,
                          extract_mock, validate)

DEMO = ("안녕하세요. 모니터 20대, 키보드 30개,\n무선 마우스 30개가 필요합니다.\n"
        "다음 주까지 납품 가능한지 확인해 주시고 견적 부탁드립니다.")


# --- 입력 검증 (외부 호출 전) ---
def test_empty_input_rejected():
    for bad in ("", "   ", "\n", None):
        with pytest.raises(ExtractError, match="입력해 주세요"):
            check_input(bad)


def test_too_long_input_rejected_not_truncated():
    with pytest.raises(ExtractError, match="너무 깁니다"):
        check_input("가" * (MAX_INPUT_CHARS + 1))


def test_input_is_stripped():
    assert check_input("  모니터 10대  ") == "모니터 10대"


# --- AI 응답 검증 (스키마를 통과해도 값은 틀릴 수 있다) ---
def test_valid_payload():
    e = validate({"items": [{"raw_name": "모니터 20대", "search_term": "Monitor", "quantity": 20}],
                  "requested_delivery": "다음 주까지", "notes": "설치 포함"}, "claude")
    assert e.items == [("모니터 20대", "Monitor", 20)]
    assert e.requested_delivery == "다음 주까지" and e.source == "claude" and e.warnings == []


@pytest.mark.parametrize("qty", [0, -5, 1.5, "20", None, True, 10**9])
def test_bad_quantity_is_dropped_with_warning(qty):
    e = validate({"items": [{"raw_name": "모니터", "search_term": "Monitor", "quantity": qty}],
                  "requested_delivery": "", "notes": ""}, "claude")
    assert e.items == [] and len(e.warnings) == 1


def test_missing_name_is_dropped():
    e = validate({"items": [{"raw_name": "  ", "search_term": "Monitor", "quantity": 5}],
                  "requested_delivery": "", "notes": ""}, "claude")
    assert e.items == [] and "비어 있는" in e.warnings[0]


def test_search_term_falls_back_to_raw_name():
    e = validate({"items": [{"raw_name": "특수부품", "search_term": "", "quantity": 2}],
                  "requested_delivery": "", "notes": ""}, "claude")
    assert e.items[0].search_term == "특수부품"


def test_items_not_a_list_is_fatal():
    with pytest.raises(ExtractError, match="items"):
        validate({"items": "모니터 20대"}, "claude")


def test_garbage_entries_are_skipped():
    e = validate({"items": ["모니터", None, 42], "requested_delivery": "", "notes": ""}, "claude")
    assert e.items == [] and len(e.warnings) == 3


def test_missing_keys_default_to_empty():
    e = validate({"items": []}, "claude")
    assert e.requested_delivery == "" and e.notes == ""


def test_long_strings_are_capped():
    e = validate({"items": [], "requested_delivery": "다" * 500, "notes": "노" * 5000}, "claude")
    assert len(e.requested_delivery) == 200 and len(e.notes) == 1000


# --- Mock 추출 ---
def test_mock_extracts_the_demo_inquiry():
    e = extract_mock(DEMO)
    assert e.source == "mock"
    assert [(i.search_term, i.quantity) for i in e.items] == [
        ("Monitor", 20), ("Keyboard", 30), ("Wireless Mouse", 30)]


def test_mock_keeps_delivery_wish_verbatim_without_making_a_date():
    e = extract_mock(DEMO)
    assert e.requested_delivery == "다음 주까지"
    assert "2026" not in e.requested_delivery   # 날짜를 임의로 만들지 않음


def test_mock_always_warns_that_it_is_mock():
    assert any("Mock" in w for w in extract_mock(DEMO).warnings)


def test_mock_returns_nothing_for_unrelated_text():
    e = extract_mock("안녕하세요, 지난번 송장 사본 좀 보내주시겠어요?")
    assert e.items == []


def test_mock_handles_comma_formatted_quantity():
    e = extract_mock("A4 용지 1,200장 주문합니다")
    assert e.items[0].quantity == 1200
