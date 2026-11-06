"""PDF 견적서 생성. ReportLab 만 사용하고 streamlit 을 import 하지 않습니다.

폰트: 한글·베트남어·영문을 한 폰트로 처리합니다. ReportLab 은 글자별 폰트 대체를
해주지 않으므로, 세 언어를 모두 담은 폰트 하나를 찾아 씁니다.
"""

from __future__ import annotations

import io
import random
from datetime import date
from pathlib import Path
from typing import NamedTuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFontFile
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                               Table, TableStyle)

from .config import ROOT

FONT_NAME = "QuoteFont"
LOGO_PATH = ROOT / "assets" / "logo.png"

# 폰트가 반드시 담고 있어야 하는 글자들. 하나라도 빠지면 그 폰트는 쓰지 않습니다.
REQUIRED_GLYPHS = "견적서수량단가합계비고NguyễnHuệPhạmThịHươngĐàNẵngQUOTATION0123"

# assets/ 를 먼저 보는 이유: 배포 환경(Linux)에는 macOS 폰트가 없습니다.
# shortcut: 번들 폰트를 아직 넣지 않았습니다. 배포(10단계) 전에 OFL 폰트
# (예: Noto Sans KR) 를 assets/ 에 넣어야 Linux 에서도 한글이 나옵니다.
FONT_CANDIDATES = [
    *sorted(ROOT.glob("assets/*.ttf")),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),   # macOS
    Path("/Library/Fonts/Arial Unicode.ttf"),                       # macOS
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),  # Linux
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),  # Linux
    Path("C:/Windows/Fonts/malgun.ttf"),                            # Windows
]


class FontError(Exception):
    """세 언어를 모두 담은 폰트를 찾지 못한 상태. 사용자에게 보여줄 메시지."""


def _covers(path: Path) -> bool:
    try:
        cmap = TTFontFile(str(path)).charToGlyph
    except Exception:
        return False
    return all(ord(c) in cmap for c in REQUIRED_GLYPHS)


def find_font() -> Path:
    """한글·베트남어·영문을 모두 담은 폰트 경로. 없으면 FontError."""
    for path in FONT_CANDIDATES:
        if path.is_file() and _covers(path):
            return path
    raise FontError(
        "한글과 베트남어를 모두 담은 폰트를 찾지 못했습니다. "
        "Noto Sans KR 같은 폰트(.ttf)를 프로젝트의 assets/ 폴더에 넣어주세요. "
        "폰트가 없으면 견적서의 글자가 깨집니다."
    )


def register_font() -> str:
    """폰트를 ReportLab 에 등록하고 이름을 돌려줍니다 (한 번만 등록)."""
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(find_font())))
    return FONT_NAME


def quote_number(today: date | None = None) -> str:
    """데모용 견적 번호. 2단계에서 DB 기반 고유 번호로 교체합니다.

    shortcut: 뒤 4자리가 난수라 아주 낮은 확률로 중복될 수 있습니다.
    실제 발행 번호가 필요해지면 DB 시퀀스로 바꾸세요.
    """
    today = today or date.today()
    return f"Q{today:%Y%m%d}-{random.randint(0, 0xFFFF):04X}"


class Company(NamedTuple):
    name: str
    address: str
    email: str


def _style(font: str, size: int, **kw) -> ParagraphStyle:
    return ParagraphStyle(f"s{size}{kw}", fontName=font, fontSize=size,
                          leading=size * 1.35, **kw)


def story(quote, customer: dict, settings: dict, meta: dict,
          number: str | None = None, today: date | None = None,
          width: float = A4[0] - 36 * mm) -> list:
    """견적서를 구성하는 ReportLab 요소 목록. 렌더링 전에 내용을 검사할 수 있습니다."""
    font = register_font()
    today = today or date.today()
    number = number or quote_number(today)
    body = _style(font, 9)
    small = _style(font, 7.5, textColor=colors.HexColor("#555555"))
    warn = _style(font, 8, textColor=colors.HexColor("#B00020"))

    flow = []

    # --- 머리말: 로고 + 회사 정보 / QUOTATION ---
    if LOGO_PATH.is_file():
        brand = Image(str(LOGO_PATH), width=38 * mm, height=13 * mm, kind="proportional")
    else:
        brand = Paragraph(f"<b>{settings.get('company_name', '')}</b>",
                          _style(font, 15))
    seller = [brand,
              Paragraph(settings.get("company_address", ""), small),
              Paragraph(settings.get("company_email", ""), small)]
    if settings.get("company_phone"):
        seller.append(Paragraph(settings["company_phone"], small))

    head = Table([[seller, Paragraph("<b>QUOTATION</b><br/>견적서",
                                     _style(font, 22, alignment=2))]],
                 colWidths=[width * 0.6, width * 0.4])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow += [head, Spacer(1, 6 * mm)]

    # --- 견적 정보 / 고객 정보 ---
    info = [["견적 번호 / No.", number, "고객사 / To", customer.get("company_name", "")],
            ["견적 일자 / Date", f"{today:%Y-%m-%d}", "담당자 / Attn",
             customer.get("contact_name", "")],
            ["유효기간 / Valid until", meta.get("valid_until", ""), "이메일 / Email",
             customer.get("email", "")],
            ["통화 / Currency", quote.currency, "등급 / Tier",
             customer.get("customer_tier", "")]]
    info_table = Table([[Paragraph(c, body) for c in row] for row in info],
                       colWidths=[width * 0.16, width * 0.26, width * 0.14, width * 0.44])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F4F7")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F2F4F7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow += [info_table, Spacer(1, 6 * mm)]

    # --- 품목 표 ---
    header = ["No.", "상품명 / Description", "수량\nQty", "단가 / Unit Price",
              "금액 / Amount"]
    rows = [[Paragraph(f"<b>{h}</b>", _style(font, 8.5, textColor=colors.white))
             for h in header]]
    for i, line in enumerate(quote.lines, 1):
        rows.append([Paragraph(str(i), body),
                     Paragraph(line.product_name, body),
                     Paragraph(f"{line.quantity:,}", _style(font, 9, alignment=2)),
                     Paragraph(f"{line.unit_price:,}", _style(font, 9, alignment=2)),
                     Paragraph(f"{line.line_total:,}", _style(font, 9, alignment=2))])
    items = Table(rows, colWidths=[width * 0.07, width * 0.45, width * 0.11,
                                   width * 0.18, width * 0.19], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#344054")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow += [items, Spacer(1, 1 * mm)]
    flow += [Paragraph("※ 위 단가와 금액은 모두 <b>세전(VAT 별도)</b> 기준입니다. "
                       f"All prices are exclusive of VAT. ({quote.currency})", small),
             Spacer(1, 4 * mm)]

    # --- 합계 ---
    totals = [["소계 / Subtotal", f"{quote.subtotal:,}"],
              [f"할인 / Discount ({quote.discount_rate:.1%})", f"-{quote.discount:,}"],
              ["과세 대상 / Taxable", f"{quote.taxable:,}"],
              [f"VAT ({quote.tax_rate:.0%})", f"{quote.tax:,}"],
              ["<b>합계 / TOTAL</b>", f"<b>{quote.total:,} {quote.currency}</b>"]]
    total_table = Table(
        [[Paragraph(a, body), Paragraph(b, _style(font, 9, alignment=2))]
         for a, b in totals[:-1]]
        + [[Paragraph(totals[-1][0], _style(font, 11)),
            Paragraph(totals[-1][1], _style(font, 11, alignment=2))]],
        colWidths=[width * 0.25, width * 0.25], hAlign="RIGHT")
    total_table.setStyle(TableStyle([
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#344054")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F4F7")),
    ]))
    flow += [total_table, Spacer(1, 6 * mm)]

    # --- 재고·납기 안내 (숨기지 않습니다) ---
    shortages = meta.get("shortages") or []
    unmatched = meta.get("unmatched") or []
    if shortages or unmatched:
        flow.append(Paragraph("<b>재고 확인 필요 / Stock notice</b>", _style(font, 9.5)))
        for s in shortages:
            flow.append(Paragraph(
                f"• {s['product_name']} — 현재 재고로는 {s['shortage']:,}개가 부족합니다. "
                f"Short by {s['shortage']:,} units at present.", warn))
        for name in unmatched:
            flow.append(Paragraph(
                f"• “{name}” — 품목을 특정하지 못했습니다. 이 견적에 포함되지 않았습니다. "
                f"Not identified; excluded from this quotation.", warn))
        flow.append(Spacer(1, 4 * mm))

    delivery = meta.get("requested_delivery")
    flow.append(Paragraph("<b>납기 / Delivery</b>", _style(font, 9.5)))
    flow.append(Paragraph(
        (f"고객 요청: “{delivery}”. " if delivery else "")
        + "납기일은 <b>확정되지 않았습니다.</b> 재고 현황만으로는 납품일을 보장할 수 없으며, "
          "별도 확인 후 회신드립니다. Delivery date is <b>not confirmed</b> and will be "
          "advised separately.", body))
    flow.append(Spacer(1, 4 * mm))

    # --- 비고 ---
    notes = [n for n in (meta.get("notes"), meta.get("customer_notes")) if n]
    if notes:
        flow.append(Paragraph("<b>비고 / Remarks</b>", _style(font, 9.5)))
        for n in notes:
            flow.append(Paragraph(f"• {n}", body))
        flow.append(Spacer(1, 4 * mm))

    flow.append(Paragraph(
        f"본 견적은 {meta.get('valid_until', '')} 까지 유효합니다 "
        f"({meta.get('valid_days', '')}일). 문의: {settings.get('company_email', '')} — "
        f"{settings.get('company_name', '')}", small))

    return flow


def build(quote, customer: dict, settings: dict, meta: dict,
          number: str | None = None, today: date | None = None) -> bytes:
    """견적서 PDF 바이트. quote 는 core.pricing.Quotation.

    meta 키: valid_days, valid_until, requested_delivery, notes,
             customer_notes, shortages, unmatched
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=f"Quotation {number or ''}",
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    doc.build(story(quote, customer, settings, meta, number, today, width=doc.width))
    return buffer.getvalue()
