"""AI Quote Factory — Streamlit UI 전용. 비즈니스 로직은 core/ 에 둡니다."""

import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import (config, email_draft, extract, matching, pdf, pricing,
                  quota, sheets)

# Streamlit Cloud 에는 .env 파일이 없습니다. Secrets 를 환경변수로 넘겨
# core/ 가 streamlit 을 모르는 상태를 유지합니다. 로컬 .env 가 우선입니다.
for _key in ("ANTHROPIC_API_KEY", "GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_JSON",
             "FORCE_MOCK", "QUOTA_PER_SESSION", "QUOTA_PER_DAY"):
    try:
        if _key in st.secrets:
            os.environ.setdefault(_key, str(st.secrets[_key]))
    except Exception:
        pass   # secrets.toml 이 없는 로컬 환경

st.set_page_config(page_title="AI Quote Factory", page_icon="📄", layout="wide")

PAGES = ["Dashboard", "New Quotation", "Product Search", "Quotation Preview",
         "Settings / Connection"]


STOCK_LABEL = {
    matching.STOCK_OK: "✅ 정상",
    matching.STOCK_SHORT: "⚠️ 재고 부족",
    matching.STOCK_OUT: "🔴 품절",
    matching.STOCK_UNKNOWN: "❓ 확인 필요",
}


def remember(name, value):
    """Streamlit 은 화면을 옮기면 '렌더되지 않은 위젯' 의 상태를 버립니다.
    그래서 중요한 입력은 위젯 키와 별도로 보관해 두고 돌아올 때 되살립니다."""
    st.session_state[f"saved_{name}"] = value
    return value


def recall(name, default=None):
    return st.session_state.get(f"saved_{name}", default)


@st.cache_resource
def day_counter():
    """프로세스 전체가 공유하는 하루 호출 수 (모든 방문자 합산)."""
    return quota.DayCounter()


def ai_allowed():
    """상한을 넘겼으면 (False, 사유). 넘기지 않았으면 (True, "")."""
    if config.mock_mode():
        return True, ""        # 이미 Mock 이면 상한과 무관
    return quota.check(st.session_state.get("ai_calls", 0),
                       day_counter().current(), quota.limits_from_env())


def record_ai_call():
    st.session_state["ai_calls"] = st.session_state.get("ai_calls", 0) + 1
    day_counter().record()


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
    if not config.mock_mode():
        lim = quota.limits_from_env()
        if lim.per_session or lim.per_day:
            st.caption(f"AI 호출 — 이 세션 {st.session_state.get('ai_calls', 0)}"
                       f"/{lim.per_session or '∞'} · 오늘 전체 "
                       f"{day_counter().current()}/{lim.per_day or '∞'}")
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

    stages = ["고객 문의 입력", "AI 요청 분석", "상품 자동 매칭",
              "거래처 선택", "견적 검토", "PDF 다운로드"]
    # 이전 실행에서 세션에 남은 값으로 진행 상태를 표시합니다 (8단계 PDF 는 아직 없음)
    stage_done = [
        bool(str(st.session_state.get("inquiry", "")).strip()),
        "extraction" in st.session_state,
        "matches" in st.session_state and not matching.unresolved(st.session_state["matches"]),
        "quote_customer" in st.session_state,
        "quote" in st.session_state,
        "pdf_bytes" in st.session_state,
    ]
    st.caption(" → ".join(f"{'✅' if ok else '⬜'} {name}"
                          for ok, name in zip(stage_done, stages)))
    st.divider()

    st.subheader("1. 고객 문의 입력")
    inquiry = st.text_area(
        "고객이 보낸 메일이나 메시지를 그대로 붙여넣으세요.",
        height=160, key="inquiry", value=recall("inquiry", ""),
        placeholder="안녕하세요. 모니터 20대, 키보드 30개, 무선 마우스 30개가 필요합니다.\n"
                    "다음 주까지 납품 가능한지 확인해 주시고 견적 부탁드립니다.",
    )
    remember("inquiry", inquiry)
    if st.button("🤖 AI 로 분석하기", type="primary"):
        allowed, reason = ai_allowed()
        # rerun 하면 화면이 다시 그려지므로 사유를 세션에 남겨야 사라지지 않습니다.
        st.session_state["quota_notice"] = "" if allowed else reason
        try:
            with st.spinner("문의 내용을 분석하는 중…"):
                st.session_state["extraction"] = extract.extract(
                    inquiry, mock=None if allowed else True)
            if allowed and not config.mock_mode():
                record_ai_call()
            # 이전 문의의 흔적이 새 견적에 섞이지 않도록 모두 비웁니다.
            # 특히 draft/pdf_bytes 를 남기면 다른 고객에게 보낼 초안이 화면에 남습니다.
            for key in [k for k in st.session_state if str(k).startswith("choice_")] + [
                    "quote", "quote_customer", "quote_meta", "quote_number",
                    "draft", "draft_for", "pdf_bytes", "pdf_for", "matches", "lines_signature",
                    "lines_editor", "saved_choices", "saved_lines", "saved_customer_id",
                    "saved_discount_pct", "saved_valid_days", "saved_notes"]:
                st.session_state.pop(key, None)
        except extract.ExtractError as e:
            st.session_state.pop("extraction", None)
            st.error(str(e))
        else:
            # 사이드바는 버튼 처리보다 먼저 실행되므로, 갱신된 호출 수를 보여주려면
            # 한 번 다시 그려야 합니다.
            st.rerun()

    result = st.session_state.get("extraction")
    if result:
        st.divider()
        st.subheader("2. AI 요청 분석 결과")
        if result.source == "mock":
            notice = st.session_state.get("quota_notice")
            st.warning("🧪 **Mock 결과입니다.** 실제 Claude API 가 아니라 단순 키워드 규칙으로 "
                       "추출했습니다. 실무 견적에 쓰지 마세요."
                       + (f"\n\n사유: {notice}" if notice else ""))
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
                    saved = (recall("choices") or {}).get(str(idx))
                    picked = body.selectbox(
                        "상품 선택", labels, key=f"choice_{idx}",
                        index=labels.index(saved) if saved in labels else 0,
                        label_visibility="collapsed")
                    st.session_state["saved_choices"] = {
                        **(recall("choices") or {}), str(idx): picked}
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
        # 선택만 하면 해결되는 항목은 견적을 막습니다. 시트에 없는 항목은
        # 여기서 해결할 수 없으므로 제외하고 진행하며, 견적서에 '확인 필요' 로 표시합니다.
        needs_choice = matching.needs_choice(resolved)
        not_found = matching.not_found(resolved)
        short = [m for m in resolved if m.shortage]
        c1, c2, c3 = st.columns(3)
        c1.metric("확정된 상품", f"{len(resolved) - len(needs_choice) - len(not_found)}"
                              f" / {len(resolved)}")
        c2.metric("재고 부족·품절", f"{len(short)}건")
        c3.metric("확인 필요", f"{len(not_found)}건")

        if needs_choice:
            st.warning(f"**{len(needs_choice)}건을 골라야 합니다.** 상품을 선택하면 "
                       f"금액을 계산합니다.")
        if not_found:
            st.error(f"**{len(not_found)}건은 시트에서 찾지 못했습니다** — "
                     + ", ".join(f"“{m.item.raw_name}”" for m in not_found)
                     + ". 이 항목은 견적에서 제외되며, **견적서에 '확인 필요' 로 명시**됩니다. "
                       "포함해야 한다면 시트에 상품을 추가하고 🔄 로 다시 읽으세요.")

        st.divider()
        st.subheader("4. 거래처 선택")
        customers = data.customers
        labels = [f"{r.company_name} · {r.customer_tier} · 할인 {r.discount_rate:.0%}"
                  for r in customers.itertuples()]
        options = ["(선택하세요)"] + labels
        saved_cid = recall("customer_id")
        default = next((i + 1 for i, r in enumerate(customers.itertuples())
                        if r.customer_id == saved_cid), 0)
        picked = st.selectbox("거래처", options, index=default, key="customer")
        customer = None if picked == "(선택하세요)" else customers.iloc[labels.index(picked)]
        remember("customer_id", None if customer is None else customer.customer_id)
        if customer is not None:
            st.caption(f"담당자 {customer.contact_name} · {customer.email}")

        if customer is None:
            st.info("거래처를 선택하면 등급 할인이 적용된 견적을 계산합니다.")
        elif needs_choice:
            st.warning("먼저 위에서 상품을 선택하세요.")
        else:
            st.divider()
            st.subheader("5. 견적 검토 · 수정")
            st.caption("수량·단가를 고치면 금액이 바로 다시 계산됩니다. "
                       "상품명은 시트의 값이라 바꿀 수 없습니다 — 다른 상품이 필요하면 위에서 다시 고르세요.")

            base = pricing.rows_from_matches(resolved)
            # 확정된 상품이 바뀌면 편집 중이던 표를 초기화합니다
            signature = tuple((r["product_id"], r["quantity"]) for r in base)
            if st.session_state.get("lines_signature") != signature:
                st.session_state["lines_signature"] = signature
                st.session_state.pop("lines_editor", None)
                st.session_state.pop("saved_lines", None)

            # 컬럼 이름은 영문(pricing 이 기대하는 키)으로 두고 화면 라벨만 따로 지정합니다.
            edited = st.data_editor(
                pd.DataFrame(recall("lines") or [{"include": True, **r} for r in base]),
                key="lines_editor", hide_index=True, width="stretch",
                num_rows="fixed", disabled=["product_id", "product_name"],
                column_order=["include", "product_id", "product_name", "quantity", "unit_price"],
                column_config={
                    "include": st.column_config.CheckboxColumn(
                        "포함", help="체크를 풀면 이 상품을 견적에서 뺍니다"),
                    "product_id": st.column_config.TextColumn("ID"),
                    "product_name": st.column_config.TextColumn("상품명"),
                    "quantity": st.column_config.NumberColumn("수량", min_value=1, step=1, format="%d"),
                    "unit_price": st.column_config.NumberColumn("단가 (세전)", min_value=1,
                                                                step=1000, format="%d"),
                })

            c1, c2 = st.columns(2)
            discount_pct = c1.number_input(
                f"할인율 (%) — {customer.customer_tier} 등급 기본값 {customer.discount_rate:.0%}",
                min_value=0.0, max_value=99.0, step=0.5,
                value=float(recall("discount_pct", customer.discount_rate * 100)),
                key="discount_pct")
            valid_days = c2.number_input(
                "견적 유효기간 (일)", min_value=1, max_value=365, step=1,
                value=int(recall("valid_days", float(data.settings["quotation_valid_days"]))),
                key="valid_days")
            special_notes = st.text_area(
                "특이사항 (견적서 비고란에 그대로 들어갑니다)", key="special_notes",
                value=recall("notes", ""),
                placeholder="예: 납품 장소는 1지점 창고. 설치 지원 포함.")

            remember("lines", edited.to_dict("records"))
            remember("discount_pct", float(discount_pct))
            remember("valid_days", int(valid_days))
            remember("notes", special_notes)
            included = edited[edited["include"]]
            if included.empty:
                st.info("견적에 포함할 상품을 하나 이상 체크하세요.")
                st.session_state.pop("quote", None)
            else:
                try:
                    quote = pricing.calculate(
                        included.drop(columns=["include"]).to_dict("records"),
                        discount_rate=discount_pct / 100,
                        tax_rate=data.settings["tax_rate"],
                        currency=data.settings["default_currency"],
                    )
                except pricing.PricingError as e:
                    st.session_state.pop("quote", None)
                    st.error(f"**금액을 계산할 수 없습니다** — {e}")
                else:
                    st.session_state["quote"] = quote
                    st.session_state["quote_customer"] = customer.to_dict()
                    st.session_state["quote_meta"] = {
                        "valid_days": int(valid_days),
                        "valid_until": (date.today() + timedelta(days=int(valid_days))).isoformat(),
                        "requested_delivery": result.requested_delivery,
                        "notes": special_notes.strip(),
                        "customer_notes": result.notes,
                        "shortages": [{"product_name": m.product["product_name"],
                                       "shortage": m.shortage} for m in resolved if m.shortage],
                        "unmatched": [m.item.raw_name for m in not_found],
                    }

                    st.divider()
                    st.subheader("6. 견적 요약")
                    left, right = st.columns([2, 1])
                    with left:
                        st.dataframe(
                            [{"상품명": l.product_name, "수량": f"{l.quantity:,}",
                              "단가 (세전)": f"{l.unit_price:,}",
                              "금액 (세전)": f"{l.line_total:,}"} for l in quote.lines],
                            hide_index=True, width="stretch")
                        st.caption("계산 순서: 상품별 합계 → 소계 → **할인** → 과세 대상 → **세금** → 최종 금액. "
                                   "모든 단가는 **세전**이며 계산은 전부 파이썬이 합니다.")
                    with right:
                        for label, amount in [
                                ("소계 (세전)", quote.subtotal),
                                (f"할인 ({quote.discount_rate:.1%})", -quote.discount),
                                ("과세 대상", quote.taxable),
                                (f"VAT ({quote.tax_rate:.0%})", quote.tax)]:
                            st.write(f"{label}  \n**{amount:,} {quote.currency}**")
                        st.divider()
                        st.metric("최종 견적 금액", f"{quote.total:,} {quote.currency}")

                    if discount_pct / 100 != customer.discount_rate:
                        st.info(f"ℹ️ 할인율을 등급 기본값 {customer.discount_rate:.0%} 에서 "
                                f"**{discount_pct:.1f}%** 로 직접 조정했습니다.")
                    m1, m2 = st.columns(2)
                    m1.metric("견적 유효기간", f"{valid_days}일 (~{st.session_state['quote_meta']['valid_until']})")
                    m2.metric("요청 납기 (고객 표현)", result.requested_delivery or "언급 없음")

                    for s in st.session_state["quote_meta"]["shortages"]:
                        st.warning(f"⚠️ **{s['product_name']}** — {s['shortage']:,}개 부족. "
                                   f"견적서에도 표시됩니다.")
                    if st.session_state["quote_meta"]["unmatched"]:
                        st.error("확인 필요 상품이 견적에서 빠졌습니다: "
                                 + ", ".join(st.session_state["quote_meta"]["unmatched"]))
                    st.caption("**Quotation Preview** 화면에서 PDF 견적서와 이메일 초안을 "
                               "만들 수 있습니다.")

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

else:   # Quotation Preview
    st.header("Quotation Preview")
    quote = st.session_state.get("quote")
    customer = st.session_state.get("quote_customer")
    meta = st.session_state.get("quote_meta")

    if not (quote and customer and meta):
        st.info("먼저 **New Quotation** 화면에서 견적을 만들고 거래처를 선택하세요.")
        st.stop()

    number = st.session_state.setdefault("quote_number", pdf.quote_number())
    c1, c2, c3 = st.columns(3)
    c1.metric("견적 번호", number)
    c2.metric("고객사", customer["company_name"])
    c3.metric("최종 금액", f"{quote.total:,} {quote.currency}")
    st.caption("견적 번호는 1단계에서는 데모용입니다 (끝 4자리가 난수라 드물게 중복될 수 있음). "
               "2단계에서 DB 기반 고유 번호로 바꿉니다.")

    st.divider()
    st.subheader("PDF 견적서")
    # 견적 내용이 바뀌지 않았으면 PDF 를 다시 만들지 않습니다.
    # 로고가 들어간 PDF 생성은 ~0.8 초라, 매 클릭마다 다시 만들면 화면이 눌립니다.
    fingerprint = (number, quote.total,
                   tuple((l.product_id, l.quantity, l.unit_price) for l in quote.lines),
                   meta.get("valid_until"), meta.get("notes"),
                   tuple(s["product_name"] for s in meta.get("shortages") or []),
                   tuple(meta.get("unmatched") or []))

    try:
        # 변수명을 data 로 쓰면 시트 데이터(data)를 덮어씁니다
        if st.session_state.get("pdf_for") != fingerprint:
            st.session_state["pdf_bytes"] = pdf.build(
                quote, customer, data.settings, meta, number=number)
            st.session_state["pdf_for"] = fingerprint
        pdf_bytes = st.session_state["pdf_bytes"]
    except pdf.FontError as e:
        st.error(f"**폰트 문제로 PDF 를 만들 수 없습니다** — {e}")
    except Exception as e:
        st.error(f"**PDF 생성 실패** — {type(e).__name__}: {e}")
    else:
        st.download_button(
            "⬇️ 견적서 PDF 다운로드", data=pdf_bytes,
            file_name=f"Quotation_{number}_{customer['company_name'][:20]}.pdf",
            mime="application/pdf", type="primary")
        st.caption(f"{len(pdf_bytes):,} bytes · 폰트 `{pdf.find_font().name}` "
                   f"(한글·베트남어·영문 포함)")
        for s_ in meta.get("shortages") or []:
            st.warning(f"⚠️ 견적서에 재고 부족이 명시됩니다: {s_['product_name']} "
                       f"{s_['shortage']:,}개 부족")
        if meta.get("unmatched"):
            st.error("견적서에 '확인 필요' 로 명시됩니다: " + ", ".join(meta["unmatched"]))

    st.divider()
    st.subheader("고객 이메일 초안")
    st.caption("이 단계에서는 **발송하지 않습니다.** 초안을 만들어 복사해 쓰세요.")
    lang_label = st.radio("언어", list(email_draft.LANGUAGES.values()), horizontal=True)
    language = next(k for k, v in email_draft.LANGUAGES.items() if v == lang_label)

    if st.button("✉️ 이메일 초안 만들기"):
        allowed, reason = ai_allowed()
        st.session_state["quota_notice"] = "" if allowed else reason
        try:
            with st.spinner("초안을 작성하는 중…"):
                st.session_state["draft"] = email_draft.generate(
                    quote, customer, data.settings, meta, number, language,
                    mock=None if allowed else True)
                st.session_state["draft_for"] = fingerprint
            if allowed and not config.mock_mode():
                record_ai_call()
        except email_draft.DraftError as e:
            st.session_state.pop("draft", None)
            st.error(str(e))
        else:
            st.rerun()   # 사이드바 호출 수 갱신

    draft = st.session_state.get("draft")
    if draft and st.session_state.get("draft_for") != fingerprint:
        # 틀린 금액이 적힌 초안이 고객에게 가는 것을 막습니다
        st.session_state.pop("draft", None)
        st.session_state.pop("draft_for", None)
        draft = None
        st.warning("견적 내용이 바뀌었습니다. 이전 초안은 금액이 맞지 않아 삭제했습니다. "
                   "초안을 다시 만들어 주세요.")
    if draft:
        if draft.source == "mock":
            notice = st.session_state.get("quota_notice")
            st.warning("🧪 **Mock 초안입니다.** 고정 템플릿으로 만들었습니다. "
                       "실제 Claude 가 쓴 문장이 아닙니다."
                       + (f"\n\n사유: {notice}" if notice else ""))
        else:
            st.success(f"🟢 Claude API ({email_draft.MODEL}) 가 작성한 초안 "
                       f"· {email_draft.LANGUAGES[draft.language]}")
        st.text_input("제목", value=draft.subject, key="draft_subject")
        st.text_area("본문", value=draft.body, height=420, key="draft_body")
        st.caption("납기 미확정 문구는 AI 출력과 별개로 항상 자동 삽입됩니다. "
                   "보내기 전에 반드시 내용을 검토하세요.")
