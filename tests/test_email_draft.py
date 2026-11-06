"""이메일 초안 검증. 네트워크 없이 Mock·검증·보호장치만 검사합니다."""

import pytest

from core.email_draft import (DELIVERY_DISCLAIMER, LANGUAGES, Draft,
                              DraftError, _finish, facts, generate_mock)
from core.pricing import calculate

QUOTE = calculate([
    {"product_id": "P001", "product_name": "Monitor 24 inch FHD IPS",
     "quantity": 20, "unit_price": 2_850_000},
    {"product_id": "P007", "product_name": "Mouse Wireless",
     "quantity": 30, "unit_price": 165_000},
], discount_rate=0.10, tax_rate=0.10)

CUSTOMER = {"company_name": "Bình Dương Sample Garment JSC", "contact_name": "Phạm Thị Hương",
            "email": "demo.c005@example.com", "customer_tier": "Gold"}
SETTINGS = {"company_name": "Demo Office Solutions Co., Ltd.",
            "company_email": "sales@example.com"}
META = {"valid_until": "2026-11-20", "requested_delivery": "다음 주까지",
        "shortages": [{"product_name": "Mouse Wireless", "shortage": 12}],
        "unmatched": [], "notes": ""}
ARGS = (QUOTE, CUSTOMER, SETTINGS, META, "Q20261106-ABCD")


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_mock_draft_in_every_language(lang):
    d = generate_mock(*ARGS, lang)
    assert isinstance(d, Draft) and d.language == lang and d.source == "mock"
    assert d.subject and d.body
    assert "Q20261106-ABCD" in d.subject or "Q20261106-ABCD" in d.body
    assert f"{QUOTE.total:,}" in d.body          # 금액은 계산된 값 그대로
    assert "2026-11-20" in d.body                # 유효기간


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_every_draft_carries_the_delivery_disclaimer(lang):
    assert DELIVERY_DISCLAIMER[lang] in generate_mock(*ARGS, lang).body


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_shortage_is_mentioned_not_hidden(lang):
    d = generate_mock(*ARGS, lang)
    assert "Mouse Wireless" in d.body and "12" in d.body


def test_no_shortage_means_no_shortage_line():
    d = generate_mock(QUOTE, CUSTOMER, SETTINGS, dict(META, shortages=[]),
                      "Q1", "en")
    assert "shortage" not in d.body.lower()


def test_disclaimer_is_added_even_if_the_model_omits_it():
    """AI 가 납기 문구를 빼먹어도 파이썬이 붙입니다."""
    d = _finish("제목", "본문만 있고 납기 안내가 없습니다.", "ko", "claude")
    assert DELIVERY_DISCLAIMER["ko"] in d.body


def test_disclaimer_is_not_duplicated():
    body = f"안녕하세요.\n\n{DELIVERY_DISCLAIMER['ko']}"
    assert _finish("제목", body, "ko", "claude").body.count(DELIVERY_DISCLAIMER["ko"]) == 1


@pytest.mark.parametrize("subject,body", [("", "본문"), ("제목", ""), ("  ", "  ")])
def test_empty_draft_is_rejected(subject, body):
    with pytest.raises(DraftError, match="비어 있습니다"):
        _finish(subject, body, "ko", "claude")


def test_long_output_is_capped():
    d = _finish("제" * 500, "본" * 9000, "ko", "claude")
    assert len(d.subject) == 200 and len(d.body) <= 4000 + len(DELIVERY_DISCLAIMER["ko"]) + 2


def test_unsupported_language_is_rejected():
    from core.email_draft import generate
    with pytest.raises(DraftError, match="지원하지 않는 언어"):
        generate(*ARGS, "ja")


# --- AI 에게 넘기는 사실 묶음 ---
def test_facts_contain_calculated_amounts_only():
    text = facts(*ARGS, "en")
    assert f"{QUOTE.total:,}" in text and f"{QUOTE.subtotal:,}" in text
    assert "Monitor 24 inch FHD IPS / 20 / 2,850,000" in text


def test_facts_tell_the_model_not_to_confirm_the_delivery_date():
    text = facts(*ARGS, "ko")
    assert "do NOT confirm" in text and "다음 주까지" in text


def test_facts_include_the_shortage():
    assert "short by 12 units" in facts(*ARGS, "en")


def test_facts_never_include_cost_price():
    """원가는 고객에게 나가면 안 됩니다. 애초에 사실 묶음에 넣지 않습니다."""
    text = facts(*ARGS, "en").lower()
    assert "cost" not in text
