"""AI Quote Factory — Streamlit UI 전용. 비즈니스 로직은 core/ 에 둡니다."""

import streamlit as st

from core import config

st.set_page_config(page_title="AI Quote Factory", page_icon="📄", layout="wide")

PAGES = [
    "Dashboard",
    "New Quotation",
    "Product Search",
    "Quotation Preview",
    "Settings / Connection",
]

with st.sidebar:
    st.title("📄 AI Quote Factory")
    st.caption("B2B 견적서 자동 생성 (1단계)")
    page = st.radio("메뉴", PAGES, label_visibility="collapsed")
    st.divider()
    if config.mock_mode():
        st.warning("🧪 Mock 모드\nClaude API 를 호출하지 않습니다.")
    else:
        st.success("🟢 실제 Claude API 연결")

if page == "Settings / Connection":
    st.header("Settings / Connection")
    st.write("`.env` 파일에서 읽은 설정 상태입니다. 키 값 자체는 표시하지 않습니다.")
    for name, (ok, detail) in config.status().items():
        st.write(f"{'✅' if ok else '⚠️'} **{name}** — {detail}")
    st.divider()
    with st.expander("설정 방법"):
        st.markdown(
            "1. `.env.example` 를 복사해 `.env` 를 만듭니다.\n"
            "2. `ANTHROPIC_API_KEY` 에 Claude API 키를 넣습니다.\n"
            "3. Google 서비스 계정 JSON 을 `credentials.json` 으로 저장합니다.\n"
            "4. `GOOGLE_SHEET_ID` 에 스프레드시트 ID 를 넣습니다.\n\n"
            "키가 없어도 Mock 모드로 전체 흐름을 연습할 수 있습니다."
        )
else:
    st.header(page)
    st.info("아직 구현 전입니다. 다음 단계에서 채웁니다.")
    st.caption(
        {
            "Dashboard": "3단계 이후: 상품/고객 수, 최근 견적 요약",
            "New Quotation": "4~7단계: 문의 입력 → AI 분석 → 상품 매칭 → 재고/가격 → 검토",
            "Product Search": "5단계: Google Sheets 상품 검색",
            "Quotation Preview": "8단계: PDF 미리보기·다운로드, 이메일 초안",
        }[page]
    )
