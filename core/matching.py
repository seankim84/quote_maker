"""검색어 → 시트의 실제 상품 매칭, 그리고 재고 비교.

AI 는 검색어만 만듭니다. 상품과 가격은 이 모듈이 시트에서 찾은 것만 씁니다.
표준 라이브러리(difflib)만 사용합니다.
"""

from __future__ import annotations

import difflib
import re
from typing import NamedTuple

import pandas as pd

from .extract import Item

FUZZY_CUTOFF = 0.5   # 토큰이 하나도 안 맞을 때 '비슷한 이름' 으로 볼 최소 유사도
MAX_CANDIDATES = 5

# 매칭 상태
MATCHED = "matched"       # 상품 1개로 확정
CHOICE = "choice"         # 후보 여러 개 → 사용자가 골라야 함
NOT_FOUND = "not_found"   # 확인 필요

# 재고 상태
STOCK_OK = "ok"
STOCK_SHORT = "short"
STOCK_OUT = "out"
STOCK_UNKNOWN = "unknown"


class Match(NamedTuple):
    item: Item
    status: str
    product: dict | None       # 확정된 상품 1행 (dict). 미확정이면 None
    candidates: list[dict]     # 고를 수 있는 후보들 (NOT_FOUND 면 '비슷한 이름' 참고용)
    stock_status: str
    shortage: int              # 부족 수량. 부족하지 않으면 0


def _tokens(text: str) -> set[str]:
    """대소문자·괄호·단위 기호를 무시한 단어 집합."""
    return {t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if t}


def _stock_state(product: dict | None, quantity: int) -> tuple[str, int]:
    if product is None:
        return STOCK_UNKNOWN, 0
    stock = int(product["stock_quantity"])
    if stock == 0:
        return STOCK_OUT, quantity
    if stock < quantity:
        return STOCK_SHORT, quantity - stock
    return STOCK_OK, 0


def search(products: pd.DataFrame, term: str, limit: int = MAX_CANDIDATES) -> list[dict]:
    """검색어로 판매중인 상품을 찾습니다. 단종(active=FALSE) 상품은 제외합니다."""
    active = products[products["active"]]
    wanted = _tokens(term)
    if active.empty or not wanted:
        return []

    names = active["product_name"].astype(str)
    # 1) 검색어의 모든 단어가 상품명에 있는 것만 후보. 군더더기가 적은 이름을 먼저.
    hits = [(len(_tokens(n) - wanted), i) for i, n in names.items()
            if wanted <= _tokens(n)]
    if hits:
        order = [i for _, i in sorted(hits)]
        return active.loc[order[:limit]].to_dict("records")

    # 2) 하나도 안 맞으면 '비슷한 이름' 을 참고용으로만 돌려줍니다 (확정에 쓰지 않음).
    scored = [(difflib.SequenceMatcher(None, term.lower(), n.lower()).ratio(), i)
              for i, n in names.items()]
    close = [i for ratio, i in sorted(scored, reverse=True) if ratio >= FUZZY_CUTOFF]
    return active.loc[close[:limit]].to_dict("records")


def match_item(products: pd.DataFrame, item: Item) -> Match:
    candidates = search(products, item.search_term)
    exact = [c for c in candidates
             if _tokens(c["product_name"]) == _tokens(item.search_term)]

    if exact:
        product, status = exact[0], MATCHED
    elif len(candidates) == 1 and _tokens(item.search_term) <= _tokens(candidates[0]["product_name"]):
        product, status = candidates[0], MATCHED
    elif candidates and _tokens(item.search_term) <= _tokens(candidates[0]["product_name"]):
        product, status = None, CHOICE
    else:
        product, status = None, NOT_FOUND

    stock_status, shortage = _stock_state(product, item.quantity)
    return Match(item, status, product, candidates, stock_status, shortage)


def match_items(products: pd.DataFrame, items: list[Item]) -> list[Match]:
    return [match_item(products, i) for i in items]


def choose(match: Match, product_id: str) -> Match:
    """사용자가 후보 중 하나를 고르면 그 상품으로 확정합니다.

    반드시 후보 목록 안에서만 고를 수 있습니다 — 임의의 ID 를 받지 않습니다.
    """
    product = next((c for c in match.candidates if c["product_id"] == product_id), None)
    if product is None:
        raise ValueError(f"후보에 없는 상품 ID 입니다: {product_id}")
    stock_status, shortage = _stock_state(product, match.item.quantity)
    return match._replace(status=MATCHED, product=product,
                          stock_status=stock_status, shortage=shortage)


def unresolved(matches: list[Match]) -> list[Match]:
    """견적을 내기 전에 사람이 처리해야 하는 항목들."""
    return [m for m in matches if m.status != MATCHED]
