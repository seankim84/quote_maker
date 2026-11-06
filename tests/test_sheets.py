"""네트워크 없이 시트 파싱 규칙만 검사합니다."""

import pytest

from core.sheets import (SheetError, clean_customers, clean_products,
                         parse_settings)

P_HEAD = ["product_id", "product_name", "category", "unit_price",
          "cost_price", "stock_quantity", "currency", "active"]
C_HEAD = ["customer_id", "company_name", "contact_name", "email",
          "customer_tier", "discount_rate"]
S_OK = [["key", "value"],
        ["company_name", "ANB"], ["company_address", "HCMC"],
        ["company_email", "a@b.vn"], ["quotation_valid_days", "14"],
        ["default_currency", "VND"], ["tax_rate", "0.1"]]


def test_products_parse_and_types():
    w = []
    df = clean_products([P_HEAD,
                         ["P001", "Monitor", "E", "2850000", "2280000", "45", "VND", "TRUE"],
                         ["P002", "Mouse", "E", "165000", "115000", "0", "VND", "FALSE"]], w)
    assert len(df) == 2 and w == []
    assert df.loc[0, "unit_price"] == 2850000          # 문자열이 아니라 숫자
    assert df.loc[0, "active"] is True or bool(df.loc[0, "active"])
    assert not df.loc[1, "active"]


def test_comma_formatted_price_is_accepted():
    w = []
    df = clean_products([P_HEAD,
                         ["P001", "Monitor", "E", "2,850,000", "2,280,000", "45", "VND", "TRUE"]], w)
    assert df.loc[0, "unit_price"] == 2850000


def test_duplicate_product_id_is_fatal():
    with pytest.raises(SheetError, match="중복"):
        clean_products([P_HEAD,
                        ["P001", "A", "E", "1000", "900", "1", "VND", "TRUE"],
                        ["P001", "B", "E", "2000", "900", "1", "VND", "TRUE"]], [])


def test_missing_column_is_fatal():
    with pytest.raises(SheetError, match="컬럼이 없습니다"):
        clean_products([P_HEAD[:-1], ["P001", "A", "E", "1000", "900", "1", "VND"]], [])


def test_bad_number_row_is_dropped_with_warning():
    w = []
    df = clean_products([P_HEAD,
                         ["P001", "A", "E", "1000", "900", "5", "VND", "TRUE"],
                         ["P002", "B", "E", "", "900", "5", "VND", "TRUE"],
                         ["P003", "C", "E", "abc", "900", "5", "VND", "TRUE"]], w)
    assert list(df["product_id"]) == ["P001"]
    assert len(w) == 1 and "P002" in w[0] and "P003" in w[0]


def test_blank_rows_are_ignored():
    w = []
    df = clean_products([P_HEAD,
                         ["P001", "A", "E", "1000", "900", "5", "VND", "TRUE"],
                         ["", "", "", "", "", "", "", ""]], w)
    assert len(df) == 1 and w == []


def test_zero_price_product_is_excluded():
    w = []
    df = clean_products([P_HEAD,
                         ["P001", "A", "E", "0", "0", "5", "VND", "TRUE"]], w)
    assert df.empty and "단가가 0 이하" in w[0]


def test_customers_and_discount_range():
    w = []
    df = clean_customers([C_HEAD,
                          ["C001", "Saigon", "Minh", "a@b.vn", "VIP", "0.1"],
                          ["C002", "Bad", "X", "x@y.vn", "VIP", "10"]], w)
    assert list(df["customer_id"]) == ["C001"]
    assert df.loc[0, "discount_rate"] == 0.1
    assert "0~1 범위" in w[0]


def test_settings_ok():
    s = parse_settings(S_OK)
    assert s["tax_rate"] == "0.1" and s["company_name"] == "ANB"


def test_settings_missing_key_is_fatal():
    with pytest.raises(SheetError, match="값이 없습니다"):
        parse_settings([r for r in S_OK if r[0] != "tax_rate"])


@pytest.mark.parametrize("bad", ["10", "-0.1", "1"])
def test_tax_rate_out_of_range_is_fatal(bad):
    rows = [r if r[0] != "tax_rate" else ["tax_rate", bad] for r in S_OK]
    with pytest.raises(SheetError, match="tax_rate"):
        parse_settings(rows)


def test_empty_tab_is_fatal():
    with pytest.raises(SheetError, match="데이터 행이 없습니다"):
        clean_products([P_HEAD], [])
