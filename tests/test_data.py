"""가상 데이터 CSV 가 견적 계산에 쓸 수 있는 형태인지 검사.
3단계에서 Google Sheets 를 읽어올 때도 같은 규칙을 적용합니다."""

import pandas as pd
import pytest

from core.config import ROOT

REQUIRED_SETTINGS = {
    "company_name", "company_address", "company_email",
    "quotation_valid_days", "default_currency", "tax_rate",
}


@pytest.fixture(scope="module")
def products():
    return pd.read_csv(ROOT / "data" / "Products.csv")


@pytest.fixture(scope="module")
def customers():
    return pd.read_csv(ROOT / "data" / "Customers.csv")


@pytest.fixture(scope="module")
def settings():
    df = pd.read_csv(ROOT / "data" / "Settings.csv")
    return dict(zip(df["key"], df["value"]))


def test_product_ids_unique_and_filled(products):
    assert products["product_id"].is_unique
    assert products["product_id"].notna().all()
    assert products["product_name"].notna().all()


def test_prices_are_sane(products):
    assert (products["unit_price"] > 0).all()
    # 원가가 판매가보다 높으면 견적을 내면 손해 → 데이터 오류
    assert (products["cost_price"] <= products["unit_price"]).all()
    assert (products["stock_quantity"] >= 0).all()


def test_currency_is_vnd(products):
    assert set(products["currency"]) == {"VND"}


def test_customer_ids_unique_and_discount_in_range(customers):
    assert customers["customer_id"].is_unique
    assert customers["discount_rate"].between(0, 1).all()
    assert customers["email"].str.contains("@").all()


def test_settings_has_every_required_key(settings):
    assert REQUIRED_SETTINGS <= set(settings)
    assert 0 <= float(settings["tax_rate"]) < 1
    assert int(settings["quotation_valid_days"]) > 0


def test_demo_edge_cases_exist(products):
    """시나리오 테스트용으로 일부러 넣어둔 경우들이 지워지지 않았는지 확인."""
    assert (products["stock_quantity"] == 0).any(), "품절 상품 1개 필요"
    assert (products["active"] == False).any(), "단종 상품 1개 필요"  # noqa: E712
    assert products["product_name"].str.contains("Monitor").sum() >= 3, "유사 상품 다수 필요"
