# Google Sheets 초기화 가이드

`data/` 의 CSV 3개를 스프레드시트 `product_info` 에 탭 3개로 올립니다.
**앱은 시트를 읽기만 합니다. 쓰는 건 사람만 합니다.**

## 올리는 방법

CSV 하나당 아래를 반복합니다 (Products → Customers → Settings).

1. 스프레드시트에서 **파일 → 가져오기**
2. **업로드** 탭 → `data/Products.csv` 선택
3. 가져오기 위치: **새 시트 삽입** 선택
4. 구분 문자: **쉼표** / "텍스트를 숫자로 변환" **체크된 상태 유지**
5. **데이터 가져오기**

파일명이 대문자로 시작하니 탭 이름이 자동으로 `Products` 가 됩니다. **탭 이름을 바꾸지 마세요** — 코드가 이 이름으로 찾습니다.

마지막으로 비어 있는 기본 탭 `시트1` 을 우클릭 → 삭제.

### 다 끝나면 이렇게 보여야 합니다

탭 3개: `Products` | `Customers` | `Settings`

## 탭별 구조

### Products (1행 = 컬럼명, 34개 상품)

| 컬럼 | 뜻 | 형식 |
|---|---|---|
| product_id | 고유 ID. 중복 금지 | P001 형식 |
| product_name | 상품명. **견적서에 이 글자가 그대로 찍힙니다** | 텍스트 |
| category | 분류 | Electronics / Paper / Stationery / Furniture |
| unit_price | 판매 단가 (**세전**) | 숫자만. 콤마·"₫" 금지 |
| cost_price | 원가. 마진 확인용, 견적서에 **안 나감** | 숫자만 |
| stock_quantity | 현재 재고 | 0 이상 정수 |
| currency | 통화 | VND |
| active | 판매 중 여부 | TRUE / FALSE |

`active=FALSE` 인 상품은 검색에서 제외됩니다 (단종품).

### Customers (8개 거래처)

| 컬럼 | 뜻 | 형식 |
|---|---|---|
| customer_id | 고유 ID. 중복 금지 | C001 형식 |
| company_name | 회사명. 견적서 수신자 | 텍스트 |
| contact_name | 담당자명 | 텍스트 |
| email | 이메일. 이메일 초안 수신자 | @ 포함 |
| customer_tier | 등급 라벨 (표시용) | VIP / Gold / Silver / Standard |
| discount_rate | **실제 계산에 쓰이는 할인율** | 0~1 소수. 0.10 = 10% |

⚠️ 할인은 `customer_tier` 글자가 아니라 **`discount_rate` 숫자**로 계산합니다.
등급 체계를 바꾸려면 이 숫자를 고치세요.

### Settings (key / value 2열)

| key | 이 데모 값 | 쓰이는 곳 |
|---|---|---|
| company_name | Demo Office Solutions Co., Ltd. | 견적서 머리말 |
| company_address | 123 Nguyễn Huệ, District 1, HCMC | 견적서 머리말 |
| company_email | sales@example.com | 견적서 연락처 |
| quotation_valid_days | 14 | 견적 유효기간 계산 |
| default_currency | VND | 금액 표시 |
| tax_rate | 0.10 | 세금 계산 |

**`company_name` 등은 실제 당신 회사 정보로 바꾸세요.** 지금 값은 가상입니다.

행을 추가하면 자동으로 읽힙니다. 전화번호를 견적서에 넣고 싶으면 `company_phone` 행을 추가하면 됩니다 (표시는 8단계에서).

⚠️ **tax_rate 는 세무 담당자에게 확인하세요.** 베트남 VAT 표준세율은 10% 이고, 품목·시기에 따라 8% 감면이 적용된 기간이 있었습니다. 이 값은 코드에 고정돼 있지 않고 시트에서만 읽으므로, 바뀌면 시트만 고치면 됩니다.

## 일부러 넣어둔 테스트 케이스

데모 시나리오를 전부 확인할 수 있게 데이터에 함정을 심어뒀습니다. **지우지 마세요.**

| 상품 | 상황 | 확인되는 기능 |
|---|---|---|
| P007 Mouse Wireless, 재고 **18** | 30개 주문하면 12개 부족 | 재고 부족 경고 |
| P025 Whiteboard Marker, 재고 **0** | 품절 | 품절 표시 |
| P001/P002/P003 Monitor 3종 | "모니터"로 검색하면 여러 개 | 사용자에게 선택 요청 |
| P003 Monitor 22", **active=FALSE** | 단종품 | 검색 결과에서 제외 |
| C008 Can Tho Trading, 할인율 **0.00** | 할인 없는 고객 | 할인 0원 처리 |
| C003 김재훈 / C005 Phạm Thị Hương | 한글·베트남어 이름 | PDF 폰트 (8단계) |

## 상품명을 왜 영어로 했는가

고객 문의는 한국어로 오는데 상품명은 영어입니다. 의도된 것입니다.

- 견적서(PDF)는 **베트남 고객**이 받습니다. 영어 상품명이 실무에 맞습니다
- 한국어 "모니터" → 영어 "Monitor" 변환은 **4단계에서 Claude가** 담당합니다
- Claude는 **검색어만** 만듭니다. 상품과 가격은 이 시트에만 존재합니다

상품명을 한국어로 쓰고 싶으면 `product_name` 을 바꿔도 동작합니다. 그 경우 PDF도 한국어로 나갑니다.

## 수정했으면 검증

CSV 를 고친 뒤에는 데이터가 깨지지 않았는지 확인하세요.

```bash
.venv/bin/python -m pytest tests/test_data.py -q
```

ID 중복, 원가가 판매가보다 높음, 할인율 범위 초과, Settings 키 누락을 잡아냅니다.
