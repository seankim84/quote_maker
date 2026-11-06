"""견적 금액 계산. 모든 숫자는 파이썬이 계산합니다 — Claude 에게 맡기지 않습니다.

계산 순서 (이 순서가 금액을 바꿉니다):
  1. 상품별 합계 = 단가 x 수량            (세전)
  2. 소계       = 상품별 합계의 합
  3. 할인       = 소계 x 할인율            (반올림)
  4. 과세 대상  = 소계 - 할인
  5. 세금       = 과세 대상 x 세율         (반올림)
  6. 최종 금액  = 과세 대상 + 세금

즉 '할인 먼저, 세금 나중' 입니다. 할인된 금액에 세금을 매깁니다.
VND 는 소수점이 없는 통화라 모든 결과를 정수로 반올림(0.5 는 올림)합니다.
부동소수점 대신 Decimal 을 쓰는 이유는 0.1 같은 비율이 2진수로 정확히 표현되지 않아서입니다.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import NamedTuple

MAX_QUANTITY = 1_000_000


class PricingError(Exception):
    """계산을 중단시키는 데이터 오류. 사용자에게 그대로 보여줄 메시지."""


class Line(NamedTuple):
    product_id: str
    product_name: str
    quantity: int
    unit_price: int     # 세전 단가
    line_total: int     # 단가 x 수량


class Quotation(NamedTuple):
    lines: list[Line]
    subtotal: int        # 세전 소계
    discount_rate: float
    discount: int
    taxable: int         # 과세 대상 (소계 - 할인)
    tax_rate: float
    tax: int
    total: int           # 고객이 지불할 최종 금액
    currency: str


def _whole(value, label: str) -> int:
    """정수여야 하는 금액·수량을 검증합니다. 소수가 섞이면 중단합니다."""
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError, TypeError):
        raise PricingError(f"{label}이(가) 숫자가 아닙니다: {value!r}") from None
    if number != number.to_integral_value():
        raise PricingError(f"{label}은(는) 정수여야 합니다 (VND 는 소수점이 없습니다): {value!r}")
    return int(number)


def _rate(value, label: str) -> Decimal:
    try:
        rate = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError):
        raise PricingError(f"{label}이(가) 숫자가 아닙니다: {value!r}") from None
    if not 0 <= rate < 1:
        raise PricingError(f"{label}은(는) 0 이상 1 미만의 소수여야 합니다 (10% = 0.1). "
                           f"현재 값: {value!r}")
    return rate


def _round(amount: Decimal) -> int:
    """0.5 는 올림. 금융 관행이자 고객이 예상하는 방향입니다."""
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def make_line(product_id: str, product_name: str, quantity, unit_price) -> Line:
    qty = _whole(quantity, f"'{product_name}' 의 수량")
    price = _whole(unit_price, f"'{product_name}' 의 단가")
    if qty < 1:
        raise PricingError(f"'{product_name}' 의 수량은 1 이상이어야 합니다. 현재 값: {qty}")
    if qty > MAX_QUANTITY:
        raise PricingError(f"'{product_name}' 의 수량이 비정상적으로 큽니다 ({qty:,}). "
                           f"입력을 확인하세요.")
    if price <= 0:
        raise PricingError(f"'{product_name}' 의 단가는 0 보다 커야 합니다. 현재 값: {price:,}")
    return Line(str(product_id), str(product_name), qty, price, qty * price)


def calculate(rows, discount_rate, tax_rate, currency: str = "VND") -> Quotation:
    """rows: product_id / product_name / quantity / unit_price 를 가진 dict 들."""
    if not rows:
        raise PricingError("견적에 담긴 상품이 없습니다.")

    lines = [make_line(r["product_id"], r["product_name"], r["quantity"], r["unit_price"])
             for r in rows]
    discount_d = _rate(discount_rate, "할인율")
    tax_d = _rate(tax_rate, "세율")

    subtotal = sum(line.line_total for line in lines)
    discount = _round(Decimal(subtotal) * discount_d)
    taxable = subtotal - discount
    tax = _round(Decimal(taxable) * tax_d)

    return Quotation(
        lines=lines, subtotal=subtotal,
        discount_rate=float(discount_d), discount=discount,
        taxable=taxable, tax_rate=float(tax_d), tax=tax,
        total=taxable + tax, currency=str(currency),
    )


def rows_from_matches(matches) -> list[dict]:
    """확정된 매칭 결과를 계산 입력으로 바꿉니다. 미확정 항목은 제외합니다."""
    return [{"product_id": m.product["product_id"],
             "product_name": m.product["product_name"],
             "quantity": m.item.quantity,
             "unit_price": int(m.product["unit_price"])}
            for m in matches if m.product is not None]
