"""AI Quote Factory — Streamlit UI 전용. 비즈니스 로직은 core/ 에 둡니다."""

import streamlit as st

from core import config, extract, matching, sheets

st.set_page_config(page_title="AI Quote Factory", page_icon="📄", layout="wide")

PAGES = ["Dashboard", "New Quotation", "Product Search", "Quotation Preview",
         "Settings / Connection"]


STOCK_LABEL = {
    matching.STOCK_OK: "✅ 정상",
    matching.STOCK_SHORT: "⚠️ 재고 부족",
    matching.STOCK_OUT: "🔴 품절",
    matching.STOCK_UNKNOWN: "❓ 확인 필요",
}


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

elif page == "New Quotation":
    st.header("New Quotation")

    done = "extraction" in st.session_state
    stages = ["고객 문의 입력", "AI 요청 분석", "상품 자동 매칭",
              "가격·재고 확인", "견적 검토", "PDF 다운로드"]
    st.caption(" → ".join(f"{'✅' if i < (2 if done else 0) else '⬜'} {name}"
                          for i, name in enumerate(stages)))
    st.divider()

    st.subheader("1. 고객 문의 입력")
    inquiry = st.text_area(
        "고객이 보낸 메일이나 메시지를 그대로 붙여넣으세요.",
        height=160, key="inquiry",
        placeholder="안녕하세요. 모니터 20대, 키보드 30개, 무선 마우스 30개가 필요합니다.\n"
                    "다음 주까지 납품 가능한지 확인해 주시고 견적 부탁드립니다.",
    )
    if st.button("🤖 AI 로 분석하기", type="primary"):
        try:
            with st.spinner("문의 내용을 분석하는 중…"):
                st.session_state["extraction"] = extract.extract(inquiry)
            # 이전 문의에서 고른 상품이 새 결과에 섞이지 않도록 비움
            for key in [k for k in st.session_state if str(k).startswith("choice_")]:
                del st.session_state[key]
        except extract.ExtractError as e:
            st.session_state.pop("extraction", None)
            st.error(str(e))

    result = st.session_state.get("extraction")
    if result:
        st.divider()
        st.subheader("2. AI 요청 분석 결과")
        if result.source == "mock":
            st.warning("🧪 **Mock 결과입니다.** 실제 Claude API 가 아니라 단순 키워드 규칙으로 "
                       "추출했습니다. 실무 견적에 쓰지 마세요.")
        else:
            st.success(f"🟢 Claude API ({extract.MODEL}) 분석 결과")

        if result.items:
            st.dataframe(
                [{"고객 표현": i.raw_name, "검색어": i.search_term, "수량": i.quantity}
                 for i in result.items],
                hide_index=True, width="stretch",
            )
        else:
            st.info("문의 내용에서 상품 요청을 찾지 못했습니다. 상품명과 수량이 포함돼 있는지 확인하세요.")

        c1, c2 = st.columns(2)
        c1.metric("요청 납기 (고객 표현 그대로)", result.requested_delivery or "언급 없음")
        c2.metric("추출된 품목", f"{len(result.items)}건")
        if result.notes:
            st.write("**기타 요구사항** —", result.notes)
        for w in result.warnings:
            st.warning(w)

        st.info("⚠️ 납기일은 **확정된 것이 아닙니다.** 위 표현은 고객이 쓴 문장을 그대로 옮긴 것이며, "
                "재고 정보만으로 납품일을 보장할 수 없습니다.")

    if result and result.items:
        st.divider()
        st.subheader("3. 상품 자동 매칭 · 재고 확인")
        st.caption("상품과 단가는 Google Sheets 에만 존재합니다. AI 가 만들어낸 값은 쓰지 않습니다.")

        resolved = []
        for idx, m in enumerate(matching.match_items(data.products, result.items)):
            with st.container(border=True):
                head, body = st.columns([1, 3])
                head.markdown(f"**{m.item.raw_name}**")
                head.caption(f"검색어 `{m.item.search_term}` · {m.item.quantity:,}개 요청")

                if m.status == matching.CHOICE:
                    body.warning(f"비슷한 상품이 {len(m.candidates)}개 있습니다. 하나를 고르세요.")
                    labels = ["(선택하세요)"] + [
                        f"{c['product_id']} · {c['product_name']} · "
                        f"{int(c['unit_price']):,} ₫ · 재고 {int(c['stock_quantity']):,}"
                        for c in m.candidates]
                    picked = body.selectbox("상품 선택", labels, key=f"choice_{idx}",
                                            label_visibility="collapsed")
                    if picked != "(선택하세요)":
                        m = matching.choose(m, picked.split(" · ")[0])

                if m.status == matching.NOT_FOUND:
                    body.error("**확인 필요** — 시트에서 이 상품을 찾지 못했습니다. "
                               "상품을 시트에 추가하거나 고객에게 정확한 품명을 확인하세요.")
                    if m.candidates:
                        body.caption("이름이 비슷한 상품 (참고용, 자동 선택하지 않음): "
                                     + ", ".join(c["product_name"] for c in m.candidates))
                elif m.status == matching.MATCHED:
                    p = m.product
                    body.markdown(f"→ **{p['product_name']}** (`{p['product_id']}`)")
                    k1, k2, k3 = body.columns(3)
                    k1.metric("단가 (세전)", f"{int(p['unit_price']):,} ₫")
                    k2.metric("재고", f"{int(p['stock_quantity']):,}개")
                    k3.metric("재고 상태", STOCK_LABEL[m.stock_status])
                    if m.shortage:
                        body.warning(f"**{m.shortage:,}개 부족** — 요청 {m.item.quantity:,}개 / "
                                     f"재고 {int(p['stock_quantity']):,}개. "
                                     f"이 부족분은 견적서에도 표시됩니다.")
            resolved.append(m)

        st.session_state["matches"] = resolved
        pending = matching.unresolved(resolved)
        short = [m for m in resolved if m.shortage]
        c1, c2, c3 = st.columns(3)
        c1.metric("확정된 상품", f"{len(resolved) - len(pending)} / {len(resolved)}")
        c2.metric("재고 부족·품절", f"{len(short)}건")
        c3.metric("처리 필요", f"{len(pending)}건")

        if pending:
            st.warning(f"**{len(pending)}건이 미확정입니다.** 상품을 고르거나 확인해야 "
                       f"다음 단계(가격 계산)로 넘어갈 수 있습니다.")
        else:
            st.success("모든 상품이 확정되었습니다. 다음 단계(6단계)에서 금액을 계산합니다.")

elif page == "Product Search":
    st.header("Product Search")
    st.caption("견적 작성 중에 상품을 직접 확인할 때 쓰는 화면입니다. "
               "검색어의 모든 단어가 상품명에 들어있는 상품을 찾습니다 (대소문자·순서 무관).")
    term = st.text_input("검색어", placeholder="Monitor / Wireless Mouse / A4 Paper / 의자")
    if term:
        found = matching.search(data.products, term, limit=20)
        if found:
            st.dataframe(
                [{"ID": p["product_id"], "상품명": p["product_name"], "분류": p["category"],
                  "단가 (VND, 세전)": f"{int(p['unit_price']):,}",
                  "재고": f"{int(p['stock_quantity']):,}"} for p in found],
                hide_index=True, width="stretch")
            st.caption(f"{len(found)}건. 단종(active=FALSE) 상품은 제외됩니다.")
        else:
            st.info("찾지 못했습니다. 영어 품명으로 검색해 보세요 (시트의 상품명이 영어입니다).")

else:
    st.header(page)
    st.info("아직 구현 전입니다. 다음 단계에서 채웁니다.")
    st.caption("8단계: PDF 미리보기·다운로드, 이메일 초안")
