"""PDF 생성 검증. 글자가 실제로 '보이는지'는 사람이 확인해야 하므로,
여기서는 폰트 커버리지·PDF 구조·경고 문구 포함 여부를 검사합니다."""

import re
from datetime import date

import pytest

from core import pdf
from core.pricing import calculate

QUOTE = calculate([
    {"product_id": "P001", "product_name": "Monitor 24 inch FHD IPS",
     "quantity": 20, "unit_price": 2_850_000},
    {"product_id": "P007", "product_name": "Mouse Wireless",
     "quantity": 30, "unit_price": 165_000},
], discount_rate=0.10, tax_rate=0.10)

CUSTOMER = {"company_name": "Bình Dương Garment JSC", "contact_name": "김재훈",
            "email": "huong.pham@bdgarment.vn", "customer_tier": "VIP"}
SETTINGS = {"company_name": "ANB Office Solutions Co., Ltd.",
            "company_address": "123 Nguyễn Huệ, District 1, Ho Chi Minh City",
            "company_email": "sales@anb-office.vn", "default_currency": "VND"}
META = {"valid_days": 14, "valid_until": "2026-11-20",
        "requested_delivery": "다음 주까지", "notes": "납품 장소는 1지점 창고",
        "customer_notes": "견적 요청", "shortages": [], "unmatched": []}


def _walk_nodes(node):
    """표 안쪽까지 포함해 모든 ReportLab 요소를 훑습니다."""
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from _walk_nodes(child)
    else:
        yield node
        if hasattr(node, "_cellvalues"):
            yield from _walk_nodes(node._cellvalues)


def _text(*args, **kwargs) -> str:
    """견적서에 들어가는 모든 글자를 모읍니다 (표 안쪽까지).

    PDF 바이트에서 읽지 않는 이유: 폰트가 서브셋 CID 로 인코딩돼 글자를 복원하려면
    PDF 파서가 필요합니다. 여기서는 렌더링 직전의 내용을 검사합니다.
    """
    def walk(node):
        if isinstance(node, (list, tuple)):
            for child in node:
                yield from walk(child)
        elif hasattr(node, "getPlainText"):
            yield node.getPlainText()
        elif hasattr(node, "_cellvalues"):
            yield from walk(node._cellvalues)

    return "\n".join(walk(pdf.story(*args, **kwargs)))


# --- 폰트 ---
def test_a_font_covering_korean_and_vietnamese_exists():
    path = pdf.find_font()
    assert path.is_file()
    assert pdf._covers(path)


def test_font_rejects_a_latin_only_font():
    """한글이 없는 폰트는 후보에서 걸러져야 합니다."""
    from pathlib import Path
    latin_only = Path("/System/Library/Fonts/Supplemental/Verdana.ttf")
    if not latin_only.is_file():
        pytest.skip("이 환경에 Verdana 가 없습니다")
    assert pdf._covers(latin_only) is False


def test_register_font_is_idempotent():
    assert pdf.register_font() == pdf.register_font() == pdf.FONT_NAME


# --- 견적 번호 ---
def test_quote_number_format():
    assert re.fullmatch(r"Q20260315-[0-9A-F]{4}", pdf.quote_number(date(2026, 3, 15)))


# --- PDF 구조 ---
def test_pdf_is_produced():
    data = pdf.build(QUOTE, CUSTOMER, SETTINGS, META, number="Q20261106-ABCD")
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    assert len(data) > 5000


def test_pdf_embeds_the_font_so_text_is_not_a_box():
    data = pdf.build(QUOTE, CUSTOMER, SETTINGS, META)
    assert b"/FontDescriptor" in data
    # 서브셋 접두사(ABCDEF+FontName) 가 있으면 폰트가 PDF 안에 포함된 것입니다
    assert re.search(rb"/[A-Z]{6}\+\w+", data), "폰트가 임베드되지 않았습니다"


def test_pdf_contains_the_quote_number_and_amounts():
    text = _text(QUOTE, CUSTOMER, SETTINGS, META, number="Q20261106-ABCD")
    assert "Q20261106-ABCD" in text
    assert f"{QUOTE.total:,}" in text
    assert f"{QUOTE.subtotal:,}" in text


def test_pdf_always_states_delivery_is_not_confirmed():
    text = _text(QUOTE, CUSTOMER, SETTINGS, META)
    assert "not confirmed" in text


def test_pdf_states_prices_are_pre_tax():
    text = _text(QUOTE, CUSTOMER, SETTINGS, META)
    assert "exclusive of VAT" in text


def test_pdf_shows_a_shortage_instead_of_hiding_it():
    meta = dict(META, shortages=[{"product_name": "Mouse Wireless", "shortage": 12}])
    text = _text(QUOTE, CUSTOMER, SETTINGS, meta)
    assert "Short by 12 units" in text


def test_pdf_shows_unidentified_items():
    meta = dict(META, unmatched=["지게차"])
    text = _text(QUOTE, CUSTOMER, SETTINGS, meta)
    assert "Not identified" in text


def test_logo_is_used_when_the_file_exists():
    from reportlab.platypus import Image
    if not pdf.LOGO_PATH.is_file():
        pytest.skip("assets/logo.png 가 없습니다")
    flow = pdf.story(QUOTE, CUSTOMER, SETTINGS, META)
    images = [n for n in _walk_nodes(flow) if isinstance(n, Image)]
    assert images, "로고 파일이 있는데 PDF 에 들어가지 않았습니다"
    data = pdf.build(QUOTE, CUSTOMER, SETTINGS, META)
    assert b"/Image" in data          # PDF 안에 이미지 객체가 존재


def test_company_name_replaces_a_missing_logo(monkeypatch, tmp_path):
    """로고가 없으면 회사명 텍스트로 대체되고, 생성은 계속됩니다."""
    monkeypatch.setattr(pdf, "LOGO_PATH", tmp_path / "nope.png")
    text = _text(QUOTE, CUSTOMER, SETTINGS, META)
    assert SETTINGS["company_name"] in text
    assert pdf.build(QUOTE, CUSTOMER, SETTINGS, META).startswith(b"%PDF-")


def test_logo_keeps_its_aspect_ratio():
    """비율을 무시하고 늘리면 로고가 찌그러집니다."""
    from reportlab.platypus import Image
    if not pdf.LOGO_PATH.is_file():
        pytest.skip("assets/logo.png 가 없습니다")
    img = next(n for n in _walk_nodes(pdf.story(QUOTE, CUSTOMER, SETTINGS, META))
               if isinstance(n, Image))
    from PIL import Image as PILImage
    with PILImage.open(pdf.LOGO_PATH) as original:
        source_ratio = original.width / original.height
    assert abs(img.drawWidth / img.drawHeight - source_ratio) < 0.02


def test_pdf_survives_empty_optional_fields():
    bare = {"valid_days": 1, "valid_until": "2026-11-07", "requested_delivery": "",
            "notes": "", "customer_notes": "", "shortages": [], "unmatched": []}
    assert pdf.build(QUOTE, CUSTOMER, SETTINGS, bare).startswith(b"%PDF-")


def test_content_includes_korean_and_vietnamese_as_typed():
    text = _text(QUOTE, CUSTOMER, SETTINGS, META)
    assert "김재훈" in text                      # 한글 담당자명
    assert "Bình Dương Garment JSC" in text      # 베트남어 회사명
    assert "Nguyễn Huệ" in text                  # 베트남어 주소
    assert "견적서" in text and "QUOTATION" in text


def test_every_character_in_the_document_exists_in_the_font():
    """폰트에 없는 글자가 하나라도 있으면 PDF 에서 빈칸/네모로 나옵니다."""
    from reportlab.pdfbase.ttfonts import TTFontFile
    cmap = TTFontFile(str(pdf.find_font())).charToGlyph
    text = _text(QUOTE, CUSTOMER, SETTINGS,
                 dict(META, shortages=[{"product_name": "Mouse Wireless", "shortage": 12}],
                      unmatched=["지게차"]))
    missing = {c for c in text if c not in "\n\t" and ord(c) not in cmap}
    assert not missing, f"폰트에 없는 글자: {sorted(missing)}"
