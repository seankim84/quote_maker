"""AI Quote Factory — Streamlit UI 전용. 비즈니스 로직은 core/ 에 둡니다."""

import streamlit as st

from core import config, sheets

st.set_page_config(page_title="AI Quote Factory", page_icon="📄", layout="wide")

PAGES = ["Dashboard", "New Quotation", "Product Search", "Quotation Preview",
         "Settings / Connection"]


@st.cache_data(ttl=300, show_spinner="Google Sheets 읽는 중…")
def load_sheet():
    """5분 캐시. 시트를 고쳤으면 사이드바의 '새로 읽기' 를 누르세요."""
    return sheets.load_all()


with st.sidebar:
    st.title("📄 AI Quote Factory")
    st.caption("B2B 견적서 자동 생성 (1단계)")
    page = st.radio("메뉴", PAGES, label_visibility="collapsed")
    st.divider()
    if config.mock_mode():
        st.warning("🧪 Mock 모드\nClaude API 를 호출하지 않습니다.")
    else:
        st.success("🟢 실제 Claude API 연결")
    if st.button("🔄 시트 새로 읽기", width="stretch"):
        load_sheet.clear()
        st.rerun()

# 시트는 거의 모든 화면에서 필요하므로 한 번만 읽고 실패하면 그 자리에서 멈춥니다.
data, sheet_error = None, None
try:
    data = load_sheet()
except sheets.SheetError as e:
    sheet_error = str(e)

if sheet_error and page != "Settings / Connection":
    st.error(f"**Google Sheets 를 읽을 수 없습니다**\n\n{sheet_error}")
    st.info("`Settings / Connection` 화면에서 설정 상태를 확인하세요.")
    st.stop()

if data and data.warnings:
    with st.expander(f"⚠️ 시트 데이터 경고 {len(data.warnings)}건 — 일부 행을 건너뛰었습니다", expanded=True):
        for w in data.warnings:
            st.write("•", w)

if page == "Dashboard":
    st.header("Dashboard")
    active = data.products[data.products["active"]]
    out_of_stock = active[active["stock_quantity"] == 0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("판매 상품", f"{len(active)}종", f"단종 {len(data.products) - len(active)}종")
    c2.metric("품절", f"{len(out_of_stock)}종")
    c3.metric("거래처", f"{len(data.customers)}곳")
    c4.metric("세율 (VAT)", f"{float(data.settings['tax_rate']):.0%}")

    st.divider()
    left, right = st.columns([2, 1])
    with left:
        st.subheader("상품 (세전 단가)")
        st.dataframe(
            active[["product_id", "product_name", "category", "unit_price", "stock_quantity"]]
            .rename(columns={"product_id": "ID", "product_name": "상품명",
                             "category": "분류", "unit_price": "단가 (VND, 세전)",
                             "stock_quantity": "재고"})
            .style.format({"단가 (VND, 세전)": "{:,.0f}", "재고": "{:,.0f}"}),
            hide_index=True, width="stretch", height=360,
        )
        st.caption("※ 모든 단가는 **세전** 금액입니다. 원가(cost_price)는 견적서에 나가지 않습니다.")
    with right:
        st.subheader("거래처")
        st.dataframe(
            data.customers[["company_name", "customer_tier", "discount_rate"]]
            .rename(columns={"company_name": "거래처", "customer_tier": "등급",
                             "discount_rate": "할인율"})
            .style.format({"할인율": "{:.0%}"}),
            hide_index=True, width="stretch", height=360,
        )
    if len(out_of_stock):
        st.warning("품절 상품: " + ", ".join(out_of_stock["product_name"]))

elif page == "Settings / Connection":
    st.header("Settings / Connection")
    st.write("`.env` 파일에서 읽은 설정 상태입니다. 키 값 자체는 표시하지 않습니다.")
    for name, (ok, detail) in config.status().items():
        st.write(f"{'✅' if ok else '⚠️'} **{name}** — {detail}")

    st.divider()
    st.subheader("Google Sheets")
    if sheet_error:
        st.error(sheet_error)
    else:
        st.success(f"연결됨 — 상품 {len(data.products)}종, 거래처 {len(data.customers)}곳 "
                   f"(읽기 전용)")
        st.table([{"항목": k, "값": v} for k, v in data.settings.items()])

    with st.expander("설정 방법"):
        st.markdown(
            "1. `.env.example` 를 복사해 **`.env`** 를 만듭니다 (`.env.example` 에 키를 넣지 마세요).\n"
            "2. `ANTHROPIC_API_KEY` 에 Claude API 키를 넣습니다.\n"
            "3. Google 서비스 계정 JSON 을 `credentials.json` 으로 저장합니다.\n"
            "4. 시트를 서비스 계정 이메일에 **뷰어**로 공유합니다.\n"
            "5. `GOOGLE_SHEET_ID` 에 스프레드시트 ID 를 넣습니다.\n\n"
            "탭 이름은 대소문자를 구분하지 않습니다 (`products` / `Products` 모두 인식)."
        )

else:
    st.header(page)
    st.info("아직 구현 전입니다. 다음 단계에서 채웁니다.")
    st.caption({
        "New Quotation": "4~7단계: 문의 입력 → AI 분석 → 상품 매칭 → 재고/가격 → 검토",
        "Product Search": "5단계: 상품명 유사 검색과 재고 확인",
        "Quotation Preview": "8단계: PDF 미리보기·다운로드, 이메일 초안",
    }[page])
