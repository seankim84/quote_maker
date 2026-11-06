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

`assets/NotoSansKR.ttf` (OFL, 10MB) 를 번들로 포함했습니다 — Linux 배포 환경에도 한글·베트남어가
나옵니다. 라이선스는 `assets/FONT_LICENSE.md` 참고.

### 로고
`assets/logo.png` 를 넣으면 견적서 머리말에 들어갑니다. 없으면 회사명 텍스트로 대체됩니다.

⚠️ **로고는 긴 변 1200px 정도로 줄여서 넣으세요.** 원본을 그대로 임베드하므로
7500px 로고를 쓰면 PDF 가 220KB·0.8초가 됩니다 (1200px 면 36KB·0.1초).
원본은 `assets/logo_source.png` 에 보관해 뒀습니다.

### 견적 번호
`Q20261106-A1B2` 형식. **뒤 4자리가 난수라 드물게 중복될 수 있는 데모용**입니다.
2단계에서 DB 시퀀스로 바꿉니다.

## 이메일 초안

한국어·영어·베트남어. **이 단계에서는 발송하지 않습니다.**

- 금액은 파이썬이 계산한 값을 사실로 넘깁니다. AI 가 계산하지 않습니다
- 납기 미확정 문구는 **AI 출력과 무관하게 파이썬이 항상 덧붙입니다**
- 원가(`cost_price`)는 AI 에게 넘기는 사실 묶음에 아예 들어가지 않습니다

## 미확정 상품 처리

| 상태 | 뜻 | 견적 생성 |
|---|---|---|
| **선택 요청** | 비슷한 상품이 여러 개 | **차단** — 사용자가 고르면 해결됨 |
| **확인 필요** | 시트에 없음 | **진행** — 제외하고 견적서에 명시 |

시트에 없는 품목 하나 때문에 견적 전체를 못 내면 쓸 수 없는 도구가 됩니다.
대신 그 품목은 견적에서 빠지고, 화면과 **PDF 견적서에 "확인 필요"로 표시**됩니다.

## 테스트

```bash
.venv/bin/python -m pytest -q          # 138개
```

`tests/conftest.py` 가 테스트 중 **Mock 모드를 강제**하고, 실제 Claude API 를 호출하려 하면
테스트를 실패시킵니다 — 테스트가 요금을 발생시키거나 결과가 매번 달라지는 것을 막습니다.

실제 API·시트를 쓰는 확인은 수동 스크립트로만 합니다 (저장소에 포함하지 않음).

## 배포 (공개 URL)

`DEPLOY.md` 참고. 요약:

- Streamlit Community Cloud 무료 (유료 플랜 없음)
- `.env` 대신 **Streamlit Secrets** 사용 — `.streamlit/secrets.toml.example` 참고
- 서비스 계정은 파일 대신 `GOOGLE_CREDENTIALS_JSON` 환경변수로
- **공개 앱은 AI 호출 상한이 필수**: 세션당 10회 / 하루 200회 (`QUOTA_PER_*`).
  상한 초과 시 거부가 아니라 **Mock 으로 내려가고 사유를 표시**합니다
- ⚠️ 공개 URL 에는 **가상 데모 데이터만** 올립니다. 실제 거래처 정보를 넣은 뒤에는
  공개하지 말고 비공개 앱(무료 1개) + 뷰어 허용 목록을 쓰세요

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
- [x] **9. 오류 처리와 전체 테스트**
- [x] **10. 배포 준비** — `DEPLOY.md`
