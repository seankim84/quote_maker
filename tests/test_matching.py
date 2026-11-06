"""네트워크 없이 매칭·재고 규칙만 검사합니다 (시트 대신 작은 DataFrame 사용)."""

import pandas as pd
import pytest

from core.extract import Item
from core.matching import (CHOICE, MATCHED, NOT_FOUND, STOCK_OK, STOCK_OUT,
                           STOCK_SHORT, STOCK_UNKNOWN, choose, match_item,
                           search, unresolved)

ROWS = [
    # id, name, unit_price, stock, active
    ("P001", "Monitor 24 inch FHD IPS", 2850000, 45, True),
    ("P002", "Monitor 27 inch QHD IPS", 4650000, 18, True),
    ("P003", "Monitor 22 inch HD", 1950000, 5, False),      # 단종
    ("P007", "Mouse Wireless", 165000, 18, True),
    ("P008", "Mouse Wired USB", 95000, 310, True),
    ("P025", "Whiteboard Marker (box 12)", 132000, 0, True),  # 품절
    ("P030", "Office Chair Mesh Ergonomic", 2350000, 28, True),
]
PRODUCTS = pd.DataFrame(ROWS, columns=["product_id", "product_name", "unit_price",
                                       "stock_quantity", "active"])


def item(term, qty=10):
    return Item(raw_name=term, search_term=term, quantity=qty)


# --- 검색 ---
def test_inactive_product_is_never_returned():
    assert all(p["product_id"] != "P003" for p in search(PRODUCTS, "Monitor"))


def test_shorter_name_ranks_first():
    assert search(PRODUCTS, "Mouse")[0]["product_id"] == "P007"  # Wireless(1단어 추가) < Wired USB(2단어)


def test_case_and_order_do_not_matter():
    assert search(PRODUCTS, "wireless mouse")[0]["product_id"] == "P007"


def test_unknown_term_returns_no_close_name():
    assert search(PRODUCTS, "Forklift") == []


# --- 매칭 ---
def test_single_candidate_is_matched_automatically():
    m = match_item(PRODUCTS, item("Wireless Mouse", 5))
    assert m.status == MATCHED and m.product["product_id"] == "P007"


def test_several_candidates_require_a_choice():
    m = match_item(PRODUCTS, item("Monitor", 5))
    assert m.status == CHOICE and m.product is None
    assert {c["product_id"] for c in m.candidates} == {"P001", "P002"}   # 단종 제외


def test_missing_product_is_flagged_for_review():
    m = match_item(PRODUCTS, item("Forklift", 1))
    assert m.status == NOT_FOUND and m.product is None
    assert m.stock_status == STOCK_UNKNOWN


def test_exact_name_wins_over_longer_names():
    m = match_item(PRODUCTS, item("Mouse Wireless", 1))
    assert m.status == MATCHED and m.product["product_id"] == "P007"


# --- 재고 ---
def test_enough_stock():
    m = match_item(PRODUCTS, item("Office Chair", 20))
    assert m.stock_status == STOCK_OK and m.shortage == 0


def test_demo_shortage_case():
    """함정 데이터: 무선마우스 재고 18개에 30개 주문 → 12개 부족."""
    m = match_item(PRODUCTS, item("Wireless Mouse", 30))
    assert m.stock_status == STOCK_SHORT and m.shortage == 12


def test_exactly_enough_stock_is_not_a_shortage():
    m = match_item(PRODUCTS, item("Wireless Mouse", 18))
    assert m.stock_status == STOCK_OK and m.shortage == 0


def test_out_of_stock():
    m = match_item(PRODUCTS, item("Whiteboard Marker", 5))
    assert m.stock_status == STOCK_OUT and m.shortage == 5


# --- 사용자 선택 ---
def test_choose_from_candidates_updates_stock():
    m = match_item(PRODUCTS, item("Monitor", 20))
    chosen = choose(m, "P002")       # 27인치, 재고 18
    assert chosen.status == MATCHED and chosen.product["product_id"] == "P002"
    assert chosen.stock_status == STOCK_SHORT and chosen.shortage == 2


def test_choose_rejects_a_product_outside_the_candidates():
    m = match_item(PRODUCTS, item("Monitor", 5))
    for bad in ("P007", "P003", "NOPE"):      # 후보 아님 / 단종 / 없는 ID
        with pytest.raises(ValueError):
            choose(m, bad)


def test_unresolved_lists_only_what_needs_a_human():
    matches = [match_item(PRODUCTS, item("Wireless Mouse", 5)),
               match_item(PRODUCTS, item("Monitor", 5)),
               match_item(PRODUCTS, item("Forklift", 5))]
    assert [m.status for m in unresolved(matches)] == [CHOICE, NOT_FOUND]


def test_empty_catalogue_does_not_crash():
    empty = PRODUCTS.iloc[0:0]
    m = match_item(empty, item("Monitor", 5))
    assert m.status == NOT_FOUND and m.candidates == []
