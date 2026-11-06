"""금액 계산 검증. 돈 계산이라 기대값을 손으로 적어 비교합니다."""

import pytest

from core.pricing import PricingError, calculate, make_line

DEMO = [  # 데모 시나리오: 모니터 20 + 무선키보드 30 + 무선마우스 30
    {"product_id": "P001", "product_name": "Monitor 24 inch FHD IPS",
     "quantity": 20, "unit_price": 2_850_000},
    {"product_id": "P005", "product_name": "Keyboard Wireless",
     "quantity": 30, "unit_price": 420_000},
    {"product_id": "P007", "product_name": "Mouse Wireless",
     "quantity": 30, "unit_price": 165_000},
]


def test_demo_scenario_vip_customer():
    """손으로 계산한 값:
       57,000,000 + 12,600,000 + 4,950,000 = 74,550,000
       할인 10% = 7,455,000  →  과세 67,095,000
       VAT 10%  = 6,709,500  →  합계 73,804,500
    """
    q = calculate(DEMO, discount_rate=0.10, tax_rate=0.10)
    assert [l.line_total for l in q.lines] == [57_000_000, 12_600_000, 4_950_000]
    assert q.subtotal == 74_550_000
    assert q.discount == 7_455_000
    assert q.taxable == 67_095_000
    assert q.tax == 6_709_500
    assert q.total == 73_804_500
    assert q.currency == "VND"


def test_discount_comes_before_tax():
    """순서가 바뀌면 금액이 달라집니다. 할인 먼저가 맞습니다."""
    q = calculate(DEMO, discount_rate=0.10, tax_rate=0.10)
    tax_without_discount = round(74_550_000 * 0.10)
    assert q.tax < tax_without_discount          # 할인된 금액에 과세
    assert q.tax == round(q.taxable * 0.10)


def test_no_discount_customer():
    q = calculate(DEMO, discount_rate=0.0, tax_rate=0.10)
    assert q.discount == 0 and q.taxable == q.subtotal
    assert q.total == 74_550_000 + 7_455_000


def test_zero_tax_rate():
    q = calculate(DEMO, discount_rate=0.0, tax_rate=0.0)
    assert q.tax == 0 and q.total == q.subtotal


def test_results_are_always_whole_vnd():
    q = calculate([{"product_id": "X", "product_name": "Odd", "quantity": 3,
                    "unit_price": 33_333}], discount_rate=0.07, tax_rate=0.08)
    for value in (q.subtotal, q.discount, q.taxable, q.tax, q.total):
        assert isinstance(value, int)


def test_half_is_rounded_up_not_to_even():
    """파이썬 기본 round() 는 '은행원 반올림' 이라 2.5 를 2 로 내립니다.
    우리는 ROUND_HALF_UP 이라 3 이 되어야 합니다. 이 테스트가 그 차이를 잡습니다."""
    q = calculate([{"product_id": "X", "product_name": "A", "quantity": 1,
                    "unit_price": 25}], discount_rate=0.1, tax_rate=0.0)
    assert q.discount == 3            # 2.5 → 3  (round(2.5) 는 2 를 돌려줌)
    assert round(2.5) == 2            # 기본 round() 를 쓰면 틀렸을 것이라는 증거

    q2 = calculate([{"product_id": "X", "product_name": "A", "quantity": 1,
                     "unit_price": 15}], discount_rate=0.1, tax_rate=0.0)
    assert q2.discount == 2           # 1.5 → 2


def test_rate_given_as_string_from_sheet():
    """Settings 탭의 tax_rate 는 문자열로 들어옵니다."""
    q = calculate(DEMO, discount_rate="0.10", tax_rate="0.10")
    assert q.total == 73_804_500


# --- 잘못된 데이터는 계산을 중단시킵니다 ---
def test_empty_quotation_is_rejected():
    with pytest.raises(PricingError, match="상품이 없습니다"):
        calculate([], 0.1, 0.1)


@pytest.mark.parametrize("qty", [0, -1, 2_000_000])
def test_bad_quantity_stops_calculation(qty):
    with pytest.raises(PricingError):
        calculate([{"product_id": "X", "product_name": "A", "quantity": qty,
                    "unit_price": 1000}], 0.1, 0.1)


def test_fractional_quantity_stops_calculation():
    with pytest.raises(PricingError, match="정수여야"):
        make_line("X", "A", 2.5, 1000)


def test_fractional_price_stops_calculation():
    with pytest.raises(PricingError, match="정수여야"):
        make_line("X", "A", 1, 1000.5)


@pytest.mark.parametrize("price", [0, -1000])
def test_bad_price_stops_calculation(price):
    with pytest.raises(PricingError, match="단가"):
        make_line("X", "A", 1, price)


@pytest.mark.parametrize("bad", ["", None, "abc", "1,0,0,0a"])
def test_non_numeric_stops_calculation(bad):
    with pytest.raises(PricingError, match="숫자가 아닙니다"):
        make_line("X", "A", 1, bad)


@pytest.mark.parametrize("rate", [1, 1.5, -0.1, 10, "10%"])
def test_bad_rate_stops_calculation(rate):
    with pytest.raises(PricingError):
        calculate(DEMO, discount_rate=rate, tax_rate=0.1)


def test_comma_formatted_price_is_accepted():
    """시트에서 '2,850,000' 처럼 들어오는 경우."""
    line = make_line("X", "A", 2, "2,850,000")
    assert line.line_total == 5_700_000


def test_error_message_names_the_product():
    with pytest.raises(PricingError, match="Monitor 24 inch"):
        make_line("P001", "Monitor 24 inch FHD IPS", 0, 2_850_000)


# --- 검토 화면(표 편집) 이 넘기는 형태 그대로 검증 ---
# app.py 는 st.data_editor 의 DataFrame 에서 include 열만 떼어 calculate() 에 넘깁니다.
# AppTest 가 data_editor 를 조작할 수 없어서, 같은 변환을 여기서 직접 검사합니다.

def _editor_df(rows, include=None):
    import pandas as pd
    include = [True] * len(rows) if include is None else include
    return pd.DataFrame([{"include": inc, **r} for inc, r in zip(include, rows)])


def _recalculate(df, discount_pct, tax_rate="0.10"):
    included = df[df["include"]]
    return calculate(included.drop(columns=["include"]).to_dict("records"),
                     discount_rate=discount_pct / 100, tax_rate=tax_rate)


def test_review_screen_default_matches_sheet_values():
    q = _recalculate(_editor_df(DEMO), discount_pct=10.0)
    assert q.total == 73_804_500


def test_review_screen_quantity_edit_changes_total():
    edited = [dict(DEMO[0], quantity=10), DEMO[1], DEMO[2]]   # 모니터 20 → 10
    q = _recalculate(_editor_df(edited), discount_pct=10.0)
    assert q.subtotal == 74_550_000 - 28_500_000
    assert q.total == round((74_550_000 - 28_500_000) * 0.9 * 1.1)


def test_review_screen_price_edit_changes_total():
    edited = [dict(DEMO[0], unit_price=2_700_000), DEMO[1], DEMO[2]]  # 단가 할인 협상
    q = _recalculate(_editor_df(edited), discount_pct=10.0)
    assert q.lines[0].line_total == 54_000_000


def test_review_screen_unchecking_a_row_removes_it():
    q = _recalculate(_editor_df(DEMO, include=[True, False, True]), discount_pct=10.0)
    assert [l.product_id for l in q.lines] == ["P001", "P007"]
    assert q.subtotal == 57_000_000 + 4_950_000


def test_review_screen_manual_discount_override():
    q = _recalculate(_editor_df(DEMO), discount_pct=15.0)
    assert q.discount == 11_182_500
    assert q.taxable == 63_367_500
    assert q.tax == 6_336_750
    assert q.total == 69_704_250


def test_review_screen_rejects_zero_quantity():
    broken = [dict(DEMO[0], quantity=0), DEMO[1], DEMO[2]]
    with pytest.raises(PricingError):
        _recalculate(_editor_df(broken), discount_pct=10.0)
