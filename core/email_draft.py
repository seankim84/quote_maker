"""견적서와 함께 보낼 비즈니스 이메일 초안. 한국어·영어·베트남어.

이 단계에서는 실제로 발송하지 않습니다. 초안만 만듭니다.
Claude 가 문장을 쓰고, 숫자는 파이썬이 계산한 값을 그대로 넣습니다.
납기 미확정 문구는 AI 출력과 무관하게 파이썬이 반드시 덧붙입니다.
"""

from __future__ import annotations

import json
from typing import NamedTuple

import anthropic

from . import config

MODEL = "claude-opus-5-5"
LANGUAGES = {"ko": "한국어", "en": "English", "vi": "Tiếng Việt"}

# AI 가 무엇을 쓰든 이 문구는 항상 들어갑니다. 납기를 약속하지 않기 위한 보호장치입니다.
DELIVERY_DISCLAIMER = {
    "ko": "※ 납기일은 아직 확정되지 않았습니다. 재고 확인 후 별도로 안내드리겠습니다.",
    "en": "Note: the delivery date is not yet confirmed. We will advise separately "
          "after checking stock.",
    "vi": "Lưu ý: ngày giao hàng chưa được xác nhận. Chúng tôi sẽ thông báo riêng "
          "sau khi kiểm tra hàng tồn kho.",
}


class DraftError(Exception):
    """사용자에게 그대로 보여줄 메시지."""


class Draft(NamedTuple):
    subject: str
    body: str
    language: str
    source: str   # "claude" | "mock"


SYSTEM_PROMPT = """You draft a polite B2B sales email that accompanies a price quotation,
for an office-supply distributor in Vietnam writing to a corporate customer.

Rules:
- Write in the requested language only.
- Use ONLY the facts given. Never invent prices, products, quantities or dates.
- Never promise or imply a delivery date, even if the customer asked for one.
- If a stock shortage is listed, mention it honestly and briefly.
- Mention that the quotation is attached and state its validity date.
- State that prices are exclusive of VAT where it reads naturally.
- Professional, warm, concise. No marketing fluff, no emoji. 120-200 words.
- Sign off with the company name given."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}


def facts(quote, customer: dict, settings: dict, meta: dict, number: str,
          language: str) -> str:
    """AI 에게 넘길 사실만 모은 요약. 금액은 이미 계산된 값입니다."""
    lines = [f"Write the email in: {LANGUAGES[language]}",
             f"Our company: {settings.get('company_name', '')}",
             f"Our email: {settings.get('company_email', '')}",
             f"Customer company: {customer.get('company_name', '')}",
             f"Customer contact person: {customer.get('contact_name', '')}",
             f"Quotation number: {number}",
             f"Quotation valid until: {meta.get('valid_until', '')}",
             f"Currency: {quote.currency}",
             "Items (name / quantity / unit price, all pre-tax):"]
    lines += [f"  - {l.product_name} / {l.quantity} / {l.unit_price:,}"
              for l in quote.lines]
    lines += [f"Subtotal (pre-tax): {quote.subtotal:,}",
              f"Discount ({quote.discount_rate:.1%}): {quote.discount:,}",
              f"VAT ({quote.tax_rate:.0%}): {quote.tax:,}",
              f"Total payable: {quote.total:,} {quote.currency}"]
    if meta.get("requested_delivery"):
        lines.append(f"Customer's delivery wish (verbatim, do NOT confirm it): "
                     f"{meta['requested_delivery']}")
    for s in meta.get("shortages") or []:
        lines.append(f"Stock shortage: {s['product_name']} is short by {s['shortage']} units")
    for name in meta.get("unmatched") or []:
        lines.append(f"Could not identify this requested item, excluded: {name}")
    if meta.get("notes"):
        lines.append(f"Special note from us: {meta['notes']}")
    return "\n".join(lines)


def _finish(subject: str, body: str, language: str, source: str) -> Draft:
    """검증 + 납기 문구 보강. AI 가 빠뜨려도 여기서 반드시 들어갑니다."""
    subject = str(subject).strip()[:200]
    body = str(body).strip()[:4000]
    if not subject or not body:
        raise DraftError("이메일 초안이 비어 있습니다. 다시 시도해 주세요.")
    disclaimer = DELIVERY_DISCLAIMER[language]
    if disclaimer not in body:
        body = f"{body}\n\n{disclaimer}"
    return Draft(subject, body, language, source)


def generate_with_claude(quote, customer, settings, meta, number, language) -> Draft:
    try:
        response = anthropic.Anthropic(api_key=config.anthropic_key()).messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user",
                       "content": facts(quote, customer, settings, meta, number, language)}],
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        )
    except anthropic.AuthenticationError:
        raise DraftError("Claude API 키가 거부되었습니다. .env 를 확인하세요.") from None
    except anthropic.RateLimitError:
        raise DraftError("Claude API 호출 한도에 걸렸습니다. 잠시 후 다시 시도해 주세요.") from None
    except anthropic.APIConnectionError:
        raise DraftError("Claude API 에 연결할 수 없습니다. 인터넷 연결을 확인하세요.") from None
    except anthropic.APIStatusError as e:
        raise DraftError(f"Claude API 오류 ({e.status_code}). 잠시 후 다시 시도해 주세요.") from None

    if response.stop_reason == "refusal":
        raise DraftError("Claude 가 이 요청의 처리를 거부했습니다.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise DraftError("AI 응답을 JSON 으로 읽을 수 없습니다. 다시 시도해 주세요.") from None
    return _finish(payload.get("subject", ""), payload.get("body", ""), language, "claude")


# --- Mock 모드 -----------------------------------------------------------
_TEMPLATES = {
    "ko": ("[견적서] {company} — 견적번호 {number}",
           "{contact}님 안녕하세요.\n\n{our_company} 입니다. 문의해 주신 내용에 대한 견적서를 "
           "첨부드립니다.\n\n- 견적번호: {number}\n- 품목 수: {item_count}건\n"
           "- 합계: {total} {currency} (VAT 포함, 표시 단가는 세전)\n"
           "- 유효기간: {valid_until}\n{shortage}\n"
           "검토 후 문의사항이 있으시면 언제든 연락 주시기 바랍니다.\n\n"
           "감사합니다.\n{our_company}\n{our_email}"),
    "en": ("[Quotation] {company} — No. {number}",
           "Dear {contact},\n\nThank you for your enquiry. Please find our quotation "
           "attached.\n\n- Quotation no.: {number}\n- Items: {item_count}\n"
           "- Total: {total} {currency} (VAT included; listed unit prices are pre-tax)\n"
           "- Valid until: {valid_until}\n{shortage}\n"
           "Please let us know if you have any questions.\n\n"
           "Best regards,\n{our_company}\n{our_email}"),
    "vi": ("[Báo giá] {company} — Số {number}",
           "Kính gửi {contact},\n\nCảm ơn Quý công ty đã liên hệ. Chúng tôi xin gửi kèm "
           "báo giá.\n\n- Số báo giá: {number}\n- Số mặt hàng: {item_count}\n"
           "- Tổng cộng: {total} {currency} (đã bao gồm VAT; đơn giá niêm yết chưa có VAT)\n"
           "- Hiệu lực đến: {valid_until}\n{shortage}\n"
           "Nếu Quý công ty có câu hỏi, xin vui lòng liên hệ với chúng tôi.\n\n"
           "Trân trọng,\n{our_company}\n{our_email}"),
}
_SHORTAGE_LINE = {
    "ko": "- 재고 부족: {items}\n",
    "en": "- Stock shortage: {items}\n",
    "vi": "- Thiếu hàng tồn kho: {items}\n",
}


def generate_mock(quote, customer, settings, meta, number, language) -> Draft:
    shortages = meta.get("shortages") or []
    shortage = ""
    if shortages:
        shortage = _SHORTAGE_LINE[language].format(
            items=", ".join(f"{s['product_name']} ({s['shortage']})" for s in shortages))
    subject, body = _TEMPLATES[language]
    values = {
        "company": customer.get("company_name", ""),
        "contact": customer.get("contact_name", "") or customer.get("company_name", ""),
        "our_company": settings.get("company_name", ""),
        "our_email": settings.get("company_email", ""),
        "number": number, "item_count": len(quote.lines),
        "total": f"{quote.total:,}", "currency": quote.currency,
        "valid_until": meta.get("valid_until", ""), "shortage": shortage,
    }
    return _finish(subject.format(**values), body.format(**values), language, "mock")


def generate(quote, customer: dict, settings: dict, meta: dict, number: str,
             language: str) -> Draft:
    if language not in LANGUAGES:
        raise DraftError(f"지원하지 않는 언어입니다: {language!r} "
                         f"(가능: {', '.join(LANGUAGES)})")
    args = (quote, customer, settings, meta, number, language)
    return generate_mock(*args) if config.mock_mode() else generate_with_claude(*args)
