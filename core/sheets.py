"""Google Sheets 읽기 전용 로더.

streamlit 을 import 하지 않습니다 — 2단계에서 FastAPI 로 UI 를 바꿔도 그대로 씁니다.
I/O 는 load_all() 하나뿐이고, 나머지 함수는 순수 함수라 네트워크 없이 테스트됩니다.
"""

from __future__ import annotations

from typing import NamedTuple

import gspread
import pandas as pd

from . import config

PRODUCT_COLUMNS = ["product_id", "product_name", "category", "unit_price",
                   "cost_price", "stock_quantity", "currency", "active"]
CUSTOMER_COLUMNS = ["customer_id", "company_name", "contact_name", "email",
                    "customer_tier", "discount_rate"]
REQUIRED_SETTINGS = ["company_name", "company_address", "company_email",
                     "quotation_valid_days", "default_currency", "tax_rate"]


class SheetError(Exception):
    """시트 구조가 잘못돼 견적을 만들 수 없는 상태. 사용자에게 그대로 보여줄 메시지."""


class SheetData(NamedTuple):
    products: pd.DataFrame
    customers: pd.DataFrame
    settings: dict[str, str]
    warnings: list[str]   # 일부 행을 버렸지만 견적은 낼 수 있는 경우


def _parse_table(rows: list[list[str]], required: list[str], label: str) -> pd.DataFrame:
    if len(rows) < 2:
        raise SheetError(f"'{label}' 탭에 데이터 행이 없습니다. 컬럼명 1행 + 데이터가 필요합니다.")
    header = [h.strip() for h in rows[0]]
    dupes = {h for h in header if header.count(h) > 1 and h}
    if dupes:
        raise SheetError(f"'{label}' 탭의 컬럼명이 중복됩니다: {', '.join(sorted(dupes))}")
    missing = [c for c in required if c not in header]
    if missing:
        raise SheetError(f"'{label}' 탭에 컬럼이 없습니다: {', '.join(missing)}")
    # 행 길이가 들쭉날쭉한 시트를 대비해 헤더 길이에 맞춤
    body = [(r + [""] * len(header))[:len(header)] for r in rows[1:]]
    df = pd.DataFrame(body, columns=header)[required]
    df = df.apply(lambda s: s.str.strip())
    return df[~(df == "").all(axis=1)].reset_index(drop=True)  # 완전히 빈 행 제거


def _require_unique_ids(df: pd.DataFrame, id_col: str, label: str) -> None:
    """중복 ID 는 경고로 넘기지 않습니다 — 엉뚱한 가격이 견적에 박힐 수 있어서."""
    dupes = df.loc[df[id_col].duplicated(), id_col].unique()
    if len(dupes):
        raise SheetError(f"'{label}' 탭에 중복된 {id_col} 가 있습니다: {', '.join(dupes)}")


def _drop_bad_rows(df: pd.DataFrame, numeric: list[str], id_col: str,
                   label: str, warnings: list[str]) -> pd.DataFrame:
    """숫자 칸이 비었거나 숫자가 아닌 행은 버리고 경고를 남깁니다."""
    bad = df[id_col] == ""
    for col in numeric:
        df[col] = pd.to_numeric(df[col].str.replace(",", "", regex=False), errors="coerce")
        bad |= df[col].isna()
    if bad.any():
        ids = [i or "(ID 없음)" for i in df.loc[bad, id_col]]
        warnings.append(f"'{label}' 탭에서 {int(bad.sum())}행을 건너뜀 (숫자 칸이 비었거나 "
                        f"숫자가 아님): {', '.join(ids[:10])}")
    return df[~bad].reset_index(drop=True)


def clean_products(rows: list[list[str]], warnings: list[str]) -> pd.DataFrame:
    df = _parse_table(rows, PRODUCT_COLUMNS, "Products")
    _require_unique_ids(df, "product_id", "Products")
    df = _drop_bad_rows(df, ["unit_price", "cost_price", "stock_quantity"],
                        "product_id", "Products", warnings)
    df["active"] = df["active"].str.upper().isin(["TRUE", "1", "Y", "YES"])
    negative = df["unit_price"] <= 0
    if negative.any():
        warnings.append(f"'Products' 탭에 단가가 0 이하인 상품 {int(negative.sum())}개를 제외함: "
                        f"{', '.join(df.loc[negative, 'product_id'])}")
    return df[~negative].reset_index(drop=True)


def clean_customers(rows: list[list[str]], warnings: list[str]) -> pd.DataFrame:
    df = _parse_table(rows, CUSTOMER_COLUMNS, "Customers")
    _require_unique_ids(df, "customer_id", "Customers")
    df = _drop_bad_rows(df, ["discount_rate"], "customer_id", "Customers", warnings)
    out_of_range = ~df["discount_rate"].between(0, 1)
    if out_of_range.any():
        warnings.append(f"'Customers' 탭의 discount_rate 가 0~1 범위를 벗어난 고객 "
                        f"{int(out_of_range.sum())}명을 제외함 (0.1 = 10%): "
                        f"{', '.join(df.loc[out_of_range, 'customer_id'])}")
    return df[~out_of_range].reset_index(drop=True)


def parse_settings(rows: list[list[str]]) -> dict[str, str]:
    df = _parse_table(rows, ["key", "value"], "Settings")
    settings = dict(zip(df["key"], df["value"]))
    missing = [k for k in REQUIRED_SETTINGS if not settings.get(k)]
    if missing:
        raise SheetError(f"'Settings' 탭에 값이 없습니다: {', '.join(missing)}")
    try:
        tax = float(settings["tax_rate"])
        days = int(float(settings["quotation_valid_days"]))
    except ValueError as e:
        raise SheetError(f"'Settings' 탭의 tax_rate / quotation_valid_days 가 숫자가 아닙니다: {e}") from e
    if not 0 <= tax < 1:
        raise SheetError(f"tax_rate 는 0~1 사이 소수여야 합니다 (10% = 0.1). 현재 값: {tax}")
    if days <= 0:
        raise SheetError(f"quotation_valid_days 는 1 이상이어야 합니다. 현재 값: {days}")
    return settings


def load_all() -> SheetData:
    """시트 전체를 한 번에 읽습니다. 호출할 때마다 API 를 쓰므로 UI 에서 캐시하세요."""
    creds = config.credentials_path()
    if not creds.is_file():
        raise SheetError(f"서비스 계정 파일이 없습니다: {creds.name} (.env 의 GOOGLE_CREDENTIALS_FILE 확인)")
    if not config.sheet_id():
        raise SheetError(".env 에 GOOGLE_SHEET_ID 가 비어 있습니다.")
    try:
        client = gspread.service_account(filename=str(creds))
        book = client.open_by_key(config.sheet_id())
        tabs = {ws.title.strip().lower(): ws for ws in book.worksheets()}
    except gspread.exceptions.APIError as e:
        raise SheetError(f"Google Sheets API 오류입니다. 서비스 계정 이메일에 시트를 "
                         f"'뷰어'로 공유했는지 확인하세요. ({e.response.status_code})") from e
    except gspread.exceptions.SpreadsheetNotFound as e:
        raise SheetError("스프레드시트를 찾을 수 없습니다. GOOGLE_SHEET_ID 와 공유 설정을 확인하세요.") from e
    except Exception as e:  # 인증 파일 손상, 네트워크 등
        raise SheetError(f"시트에 연결할 수 없습니다: {type(e).__name__}") from e

    missing = [n for n in ("products", "customers", "settings") if n not in tabs]
    if missing:
        raise SheetError(f"탭이 없습니다: {', '.join(missing)}. "
                         f"현재 탭: {', '.join(t.title for t in book.worksheets())}")

    warnings: list[str] = []
    return SheetData(
        products=clean_products(tabs["products"].get_all_values(), warnings),
        customers=clean_customers(tabs["customers"].get_all_values(), warnings),
        settings=parse_settings(tabs["settings"].get_all_values()),
        warnings=warnings,
    )
