# AI Quote Factory — 1단계 (AI Quote Maker)

베트남 B2B 사무용품 유통사를 가정한 **AI 견적서 자동 생성 도구**.
고객의 자연어 문의 → Claude API 로 구조화 → Google Sheets 상품 조회 → 견적 계산 → PDF 다운로드.

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # 키를 채웁니다 (없으면 Mock 모드)
streamlit run app.py
```

브라우저에서 http://localhost:8501 이 열립니다.

## 테스트

```bash
.venv/bin/python -m pytest -q
```

## 폴더 구조

| 경로 | 역할 |
|---|---|
| `app.py` | Streamlit 화면만. 계산·API 호출 로직 없음 |
| `core/` | 재사용 가능한 비즈니스 로직 (2단계 FastAPI 에서 그대로 사용) |
| `core/config.py` | `.env` 읽기, Mock 모드 판정, 연결 상태 |
| `data/` | 가상 상품·고객 CSV (2단계) |
| `assets/` | 회사 로고, PDF 폰트 |
| `tests/` | pytest |

**UI 와 로직 분리 원칙**: `core/` 안의 코드는 `streamlit` 을 import 하지 않습니다.
그래서 2단계에서 UI 를 FastAPI 로 바꿔도 `core/` 는 그대로 재사용됩니다.

## 금액 계산 규칙 (6단계에서 구현)

1. 상품별 합계 = 단가 × 수량 (세전)
2. 할인 = 상품별 합계의 합 × 고객 등급 할인율
3. 과세 대상 = 합계 − 할인
4. 세금 = 과세 대상 × Settings 의 `tax_rate`
5. 최종 금액 = 과세 대상 + 세금

모든 숫자 계산은 Python 이 합니다. Claude 에게 금액을 계산시키지 않습니다.
표시 가격은 모두 **세전(VND)** 이며 화면에 명시합니다.

## 견적서 PDF

### 폰트
한글·베트남어·영문을 **한 폰트**로 처리합니다. ReportLab 은 글자별 폰트 대체를 하지 않으므로,
세 언어를 모두 담은 폰트를 찾아 씁니다. 찾는 순서:

1. `assets/*.ttf` — 번들 폰트 (배포 환경용)
2. macOS: `Arial Unicode.ttf`
3. Linux: Noto Sans CJK
4. Windows: `malgun.ttf`

각 후보는 실제로 한글·베트남어 글자를 담고 있는지 검사한 뒤 채택됩니다. 없으면 PDF 생성을
중단하고 안내합니다 — 글자가 깨진 견적서를 내보내지 않습니다.

⚠️ **배포(10단계) 전에 OFL 폰트(예: Noto Sans KR)를 `assets/` 에 넣어야 합니다.**
Streamlit Cloud 는 Linux 라서 macOS 폰트가 없습니다.

### 로고
`assets/logo.png` 를 넣으면 견적서 머리말에 들어갑니다. 없으면 회사명 텍스트로 대체됩니다.

### 견적 번호
`Q20261106-A1B2` 형식. **뒤 4자리가 난수라 드물게 중복될 수 있는 데모용**입니다.
2단계에서 DB 시퀀스로 바꿉니다.

## 이메일 초안

한국어·영어·베트남어. **이 단계에서는 발송하지 않습니다.**

- 금액은 파이썬이 계산한 값을 사실로 넘깁니다. AI 가 계산하지 않습니다
- 납기 미확정 문구는 **AI 출력과 무관하게 파이썬이 항상 덧붙입니다**
- 원가(`cost_price`)는 AI 에게 넘기는 사실 묶음에 아예 들어가지 않습니다

## 안전 규칙

- API 키는 `.env` 에만. `.env` 와 `credentials.json` 은 `.gitignore` 에 등록됨
- 로그·화면에 키나 개인정보를 출력하지 않음 (Settings 화면은 키 뒤 4자리만 표시)
- Google Sheets 는 **읽기 전용** 권한으로만 사용
- 상품명·가격은 Sheets 에만 존재. AI 가 만들어낸 상품/가격은 사용하지 않음
- 납기일은 확정하지 않음. 재고 정보만 표시하고 "확인 필요" 로 남김

## 개발 단계

- [x] 1. 프로젝트 초기화 및 폴더 구조
- [x] **2. 가상 데이터 CSV + Google Sheets 구조 설계** — `data/SHEET_SETUP.md`
- [x] **3. Google Sheets 연결** (`core/sheets.py`) — Dashboard 에 실데이터 표시
- [x] **4. 고객 문의 AI 구조화** (`core/extract.py`, Mock 포함)
- [x] **5. 상품 매칭 및 재고 확인** (`core/matching.py`)
- [x] **6. 가격 계산** (`core/pricing.py`)
- [x] **7. 견적 검토 화면**
- [x] **8. PDF 생성 + 이메일 초안** (`core/pdf.py`, `core/email_draft.py`)
- [ ] **9. 오류 처리와 전체 테스트** ← 다음
- [ ] 10. 배포 준비
