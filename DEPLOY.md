# 배포 가이드 — 수강생에게 공개 URL 로 보여주기

Streamlit Community Cloud 는 무료이고 유료 플랜이 없습니다.
무료 한도: 공개 앱 무제한 / 비공개 앱 1개 / 12시간 트래픽 없으면 휴면(접속하면 깨어남).

## 0. 공개하기 전에 반드시 확인

이 앱은 화면에 **상품 단가, 거래처 목록, 담당자 이메일, 등급별 할인율**을 보여줍니다.
공개 URL 은 링크를 아는 누구나 들어옵니다.

| 항목 | 현재 상태 |
|---|---|
| 거래처·회사명 | 가상 데모 데이터 (`Demo`, `Sample`, `Example`) |
| 이메일 | 전부 `@example.com` (예약 도메인, 메일이 가지 않음) |
| 상품·단가 | 가상 데이터 |

⚠️ **실제 회사 데이터를 시트에 넣은 뒤에는 공개 URL 로 배포하지 마세요.**
실제 데이터가 필요하면 비공개 앱(무료 1개) + 뷰어 이메일 허용 목록을 쓰세요.

## 1. AI 호출 상한 (공개 배포의 핵심)

공개 앱은 누구나 내 API 키로 Claude 를 호출할 수 있습니다. 그래서 상한이 있습니다.

| 설정 | 기본값 | 뜻 |
|---|---|---|
| `QUOTA_PER_SESSION` | 10 | 방문자 한 명(브라우저 세션)당 AI 호출 수 |
| `QUOTA_PER_DAY` | 200 | 앱 전체의 하루 AI 호출 수 |

상한을 넘기면 **거부하지 않고 Mock 모드로 내려갑니다.** 수강생은 전체 흐름을 계속
학습할 수 있고, 화면에 "Mock 결과 + 사유" 가 표시됩니다.

하루 카운터는 서버 프로세스 안에만 있어서 앱이 재시작되면 0 이 됩니다.
정확한 과금 상한이 필요하면 외부 저장소로 옮겨야 합니다 (`core/quota.py` 주석 참고).

사이드바에 `AI 호출 — 이 세션 3/10 · 오늘 전체 47/200` 처럼 남은 횟수가 보입니다.

## 2. GitHub 에 올리기

```bash
git remote add origin https://github.com/<계정>/<저장소>.git
git push -u origin main
```

올라가지 않는 파일: `.env`, `credentials.json`, `.streamlit/secrets.toml` (`.gitignore` 처리됨).
올라가는 파일: `assets/NotoSansKR.ttf` (10MB, 한글·베트남어 PDF 에 필요), `assets/logo.png`.

## 3. Streamlit Cloud 에서 배포

1. https://share.streamlit.io 에서 GitHub 계정으로 로그인
2. **New app** → 저장소·브랜치 선택 → Main file path: `app.py`
3. **Advanced settings → Python version: 3.12** (`.python-version` 에도 적어뒀습니다)
4. **Advanced settings → Secrets** 에 `.streamlit/secrets.toml.example` 내용을 참고해 붙여넣기
5. **Deploy**

첫 배포는 의존성 설치에 3~5분 걸립니다.

## 4. Secrets 에 넣을 값

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
GOOGLE_SHEET_ID = "..."
QUOTA_PER_SESSION = "10"
QUOTA_PER_DAY = "200"
GOOGLE_CREDENTIALS_JSON = '''{"type":"service_account", ... }'''
```

`GOOGLE_CREDENTIALS_JSON` 은 `credentials.json` 파일 **내용 전체**를 한 줄로 붙여넣습니다.
배포 환경에는 파일을 둘 수 없어서 이 방식이 필요합니다.
`private_key` 안의 `\n` 은 그대로 두세요.

## 5. 배포 후 확인

1. **Settings / Connection** 화면 → ✅ 4개
2. **Dashboard** → 상품 34종, 거래처 8곳
3. **New Quotation** → 데모 문의 붙여넣고 분석 → PDF 다운로드
4. 사이드바에 AI 호출 수가 올라가는지

## 6. 수업 중 주의사항

- 앱이 **12시간 유휴 후 잠듭니다.** 수업 직전에 한 번 열어 깨워두세요 (첫 접속은 30초~1분)
- 수강생이 동시에 몰리면 무료 티어 메모리(1~2.7GB)에서 느려질 수 있습니다
- 수강생이 **같은 시트를 공유**합니다. 시트는 읽기 전용이라 망가지지 않습니다
- 하루 상한을 다 쓰면 그날은 Mock 으로만 동작합니다. 상한을 올리려면 Secrets 에서 수정 후 재배포

## 7. 비용

| 항목 | 비용 |
|---|---|
| Streamlit (라이브러리 + Community Cloud) | 0원 |
| Google Sheets API | 0원 (무료 할당량 내) |
| Noto Sans KR 폰트 (OFL) | 0원 |
| **Claude API** | 사용량만큼 — `QUOTA_PER_DAY` 로 상한 |

견적 1건당 Claude 호출 2회(문의 분석 + 이메일 초안)입니다.
