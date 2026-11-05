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

## 안전 규칙

- API 키는 `.env` 에만. `.env` 와 `credentials.json` 은 `.gitignore` 에 등록됨
- 로그·화면에 키나 개인정보를 출력하지 않음 (Settings 화면은 키 뒤 4자리만 표시)
- Google Sheets 는 **읽기 전용** 권한으로만 사용
- 상품명·가격은 Sheets 에만 존재. AI 가 만들어낸 상품/가격은 사용하지 않음
- 납기일은 확정하지 않음. 재고 정보만 표시하고 "확인 필요" 로 남김

## 개발 단계

- [x] **1. 프로젝트 초기화 및 폴더 구조** ← 현재
- [ ] 2. 가상 데이터 CSV + Google Sheets 구조 설계
- [ ] 3. Google Sheets 연결 (`core/sheets.py`)
- [ ] 4. 고객 문의 AI 구조화 (`core/extract.py`, Mock 포함)
- [ ] 5. 상품 매칭 및 재고 확인 (`core/matching.py`)
- [ ] 6. 가격 계산 (`core/pricing.py`)
- [ ] 7. 견적 검토 화면
- [ ] 8. PDF 생성 + 이메일 초안 (`core/pdf.py`, `core/email_draft.py`)
- [ ] 9. 오류 처리와 전체 테스트
- [ ] 10. 배포 준비
