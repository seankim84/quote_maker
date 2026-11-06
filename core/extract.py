"""고객 문의문(자연어) → 구조화된 요청. Claude 또는 Mock.

Claude 가 하는 일은 '글에서 상품명과 수량을 뽑아내는 것' 뿐입니다.
가격·재고·납기 판단은 전부 파이썬이 합니다 (core/matching.py, core/pricing.py).
AI 응답은 스키마로 강제한 뒤 파이썬에서 한 번 더 검증합니다.
"""

from __future__ import annotations

import json
import re
from typing import NamedTuple

import anthropic

from . import config

MAX_INPUT_CHARS = 4000      # 외부 호출 전 입력 크기 제한
MAX_QUANTITY = 1_000_000    # 이 이상은 오타로 간주
MAX_ITEMS = 50
MODEL = "claude-opus-5-5"


class ExtractError(Exception):
    """사용자에게 그대로 보여줄 메시지."""


class Item(NamedTuple):
    raw_name: str      # 고객이 쓴 표현 그대로 (화면 표시용)
    search_term: str   # 시트 검색에 쓸 영어 키워드
    quantity: int


class Extraction(NamedTuple):
    items: list[Item]
    requested_delivery: str   # 고객이 쓴 표현 그대로. 날짜로 환산하지 않습니다.
    notes: str
    source: str               # "claude" | "mock"
    warnings: list[str]


SYSTEM_PROMPT = """You extract order lines from a B2B customer inquiry for an office-supply distributor in Vietnam.

Rules:
- Only extract what the text actually says. Never invent products, quantities or dates.
- `raw_name`: the product as the customer wrote it, verbatim, in their language.
- `search_term`: a short English keyword for searching a product catalogue
  (e.g. "모니터" -> "Monitor", "무선 마우스" -> "Wireless Mouse", "A4 용지" -> "A4 Paper").
  Use the generic product noun. Do not add brands, sizes or specs the customer did not write.
- `quantity`: a positive integer. If no quantity is stated, omit that item entirely.
- `requested_delivery`: the delivery wish copied verbatim from the text
  (e.g. "다음 주까지"). Never convert it to a calendar date. Empty string if not mentioned.
- `notes`: other requests or conditions the customer mentioned, in their language. Empty string if none.
- If the text contains no product request at all, return an empty items list."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_name": {"type": "string"},
                    "search_term": {"type": "string"},
                    "quantity": {"type": "integer"},
                },
                "required": ["raw_name", "search_term", "quantity"],
                "additionalProperties": False,
            },
        },
        "requested_delivery": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["items", "requested_delivery", "notes"],
    "additionalProperties": False,
}


def check_input(text: str) -> str:
    """외부 서비스에 보내기 전 입력 검증."""
    text = (text or "").strip()
    if not text:
        raise ExtractError("문의 내용을 입력해 주세요.")
    if len(text) > MAX_INPUT_CHARS:
        raise ExtractError(f"문의 내용이 너무 깁니다 ({len(text):,}자). "
                           f"{MAX_INPUT_CHARS:,}자 이하로 줄여주세요. "
                           f"견적에 필요한 상품·수량 부분만 남기면 됩니다.")
    return text


def validate(payload: dict, source: str) -> Extraction:
    """AI(또는 Mock) 결과를 신뢰하지 않고 검증합니다. 스키마가 통과해도 값은 틀릴 수 있습니다."""
    warnings: list[str] = []
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ExtractError("AI 응답 형식이 올바르지 않습니다 (items 가 목록이 아님). 다시 시도해 주세요.")

    items: list[Item] = []
    for entry in raw_items[:MAX_ITEMS]:
        if not isinstance(entry, dict):
            warnings.append("항목 하나를 건너뜀 (형식 오류)")
            continue
        raw_name = str(entry.get("raw_name", "")).strip()
        search_term = str(entry.get("search_term", "")).strip() or raw_name
        qty = entry.get("quantity")
        if not raw_name:
            warnings.append("상품명이 비어 있는 항목을 건너뜀")
            continue
        if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= MAX_QUANTITY:
            warnings.append(f"'{raw_name}' 의 수량을 읽을 수 없어 건너뜀 (값: {qty!r})")
            continue
        items.append(Item(raw_name[:120], search_term[:120], qty))

    if len(raw_items) > MAX_ITEMS:
        warnings.append(f"항목이 {len(raw_items)}개라 앞 {MAX_ITEMS}개만 사용했습니다.")

    return Extraction(
        items=items,
        requested_delivery=str(payload.get("requested_delivery", "")).strip()[:200],
        notes=str(payload.get("notes", "")).strip()[:1000],
        source=source,
        warnings=warnings,
    )


def extract_with_claude(text: str) -> Extraction:
    try:
        response = anthropic.Anthropic(api_key=config.anthropic_key()).messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        )
    except anthropic.AuthenticationError:
        raise ExtractError("Claude API 키가 거부되었습니다. .env 의 ANTHROPIC_API_KEY 를 확인하세요.") from None
    except anthropic.RateLimitError:
        raise ExtractError("Claude API 호출 한도에 걸렸습니다. 잠시 후 다시 시도해 주세요.") from None
    except anthropic.APIConnectionError:
        raise ExtractError("Claude API 에 연결할 수 없습니다. 인터넷 연결을 확인하세요.") from None
    except anthropic.APIStatusError as e:
        raise ExtractError(f"Claude API 오류 ({e.status_code}). 잠시 후 다시 시도해 주세요.") from None

    if response.stop_reason == "refusal":
        raise ExtractError("Claude 가 이 요청의 처리를 거부했습니다. 문의 내용을 확인해 주세요.")
    body = next((b.text for b in response.content if b.type == "text"), "")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise ExtractError("AI 응답을 JSON 으로 읽을 수 없습니다. 다시 시도해 주세요.") from None
    return validate(payload, "claude")


# --- Mock 모드 ---------------------------------------------------------------
# API 키 없이 전체 흐름을 연습하기 위한 규칙 기반 추출. Claude 보다 훨씬 단순합니다.

_TERMS = {
    "모니터": "Monitor", "키보드": "Keyboard", "마우스": "Mouse", "헤드셋": "Headset",
    "웹캠": "Webcam", "용지": "A4 Paper", "종이": "A4 Paper", "토너": "Toner Cartridge",
    "잉크": "Ink Cartridge", "볼펜": "Ballpoint Pen", "펜": "Gel Pen",
    "형광펜": "Highlighter", "스테이플러": "Stapler", "포스트잇": "Sticky Notes",
    "의자": "Office Chair", "책상": "Office Desk", "캐비넷": "Filing Cabinet",
    "화이트보드": "Whiteboard", "파쇄기": "Paper Shredder", "스탠드": "Desk Lamp",
    "멀티탭": "Power Strip", "허브": "USB-C Hub", "SSD": "External SSD",
}
_MODIFIERS = {"무선": "Wireless", "유선": "Wired"}
_DELIVERY_PATTERNS = [r"다음\s*주\w*", r"이번\s*주\w*", r"내일\w*", r"모레\w*",
                      r"다음\s*달\w*", r"이번\s*달\w*", r"\d+월\s*\d+일\w*",
                      r"\d+/\d+\w*", r"\d+\s*일\s*내\w*", r"\d+\s*주\s*내\w*"]
# "A4 용지" 의 4 를 수량으로 읽지 않도록 숫자 앞에 영문/숫자가 오는 경우를 제외
_QTY = re.compile(r"(?<![A-Za-z0-9])(\d[\d,]*)\s*"
                  r"(?:대|개|장|박스|박|세트|매|권|ea|EA|pcs|PCS|box|BOX)?")


def extract_mock(text: str) -> Extraction:
    items = []
    for chunk in re.split(r"(?<!\d),(?!\d)|[\n;·、]|그리고", text):
        term = next((v for k, v in _TERMS.items() if k in chunk), None)
        if not term:
            continue
        qty_match = _QTY.search(chunk)
        if not qty_match:
            continue
        modifier = next((v for k, v in _MODIFIERS.items() if k in chunk), "")
        items.append({
            "raw_name": chunk.strip()[:120],
            "search_term": f"{modifier} {term}".strip(),
            "quantity": int(qty_match.group(1).replace(",", "")),
        })

    delivery = ""
    for pattern in _DELIVERY_PATTERNS:
        found = re.search(pattern, text)
        if found:
            delivery = found.group(0)
            break

    result = validate({"items": items, "requested_delivery": delivery, "notes": ""}, "mock")
    return result._replace(warnings=result.warnings + [
        "Mock 모드입니다. 단순 키워드 규칙으로 추출했으므로 실제 Claude 결과와 다릅니다."])


def extract(text: str) -> Extraction:
    """진입점. Mock 여부는 config 가 결정합니다."""
    text = check_input(text)
    return extract_mock(text) if config.mock_mode() else extract_with_claude(text)
