# DART MCP 서버

[![smithery badge](https://smithery.ai/badge/@2geonhyup/dart-mcp)](https://smithery.ai/server/@2geonhyup/dart-mcp)

## 소개
DART MCP 서버는 금융감독원의 전자공시시스템(DART) API를 활용하여 한국 기업의 재무정보 및 사업 정보를 검색하고 분석할 수 있는 도구입니다. 이 프로젝트는 사용자가 손쉽게 기업의 공시 정보를 조회하고 필요한 재무 데이터를 추출할 수 있도록 설계되었습니다.

## 설치 방법

### Installing via Smithery

To install dart-mcp for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@2geonhyup/dart-mcp):

```bash
npx -y @smithery/cli install @2geonhyup/dart-mcp --client claude
```

### 필수 요구사항
- Python 3.10 이상
- DART API 키 (금융감독원 OPEN DART에서 발급 가능)

### 설치 과정
1. 저장소 복제
```bash
git clone [저장소 URL]
cd dart-mcp
```

2. 가상환경 생성 및 활성화
```bash
python -m venv .venv
source .venv/bin/activate  # 리눅스/맥
# 또는
.venv\Scripts\activate  # 윈도우
```

3. 의존성 설치
```bash
pip install -e .
```

## 환경 변수 설정
프로젝트 루트에 `.env` 파일을 생성하여 다음과 같이 API 키를 설정합니다:
```
DART_API_KEY=your_api_key_here
```

## 사용 가능한 도구

### 1. 회사 재무 정보 검색
회사의 주요 재무 정보(매출액, 영업이익, 당기순이익 등)를 검색합니다.

### 2. 세부 재무 정보 검색
회사의 재무상태표, 손익계산서, 현금흐름표 등 세부 재무 정보를 분석합니다.

### 3. 사업 정보 검색
회사의 사업 개요, 주요 제품 및 서비스, 매출 현황 등의 사업 관련 정보를 검색합니다.

### 4. 현재 날짜 조회
현재 날짜를 YYYYMMDD 형식으로 반환합니다.

## 도구별 상세 설명

### 재무 정보 검색
```python
# 회사의 주요 재무 정보 검색
search_disclosure(
    company_name="삼성전자",  # 회사명
    start_date="20230101",    # 시작일(YYYYMMDD)
    end_date="20231231",      # 종료일(YYYYMMDD)
    requested_items=["매출액", "영업이익"]  # 조회할 항목(선택 사항)
)
```

### 세부 재무 정보 검색
```python
# 회사의 세부 재무 정보 검색
search_detailed_financial_data(
    company_name="삼성전자",      # 회사명
    start_date="20230101",       # 시작일(YYYYMMDD)
    end_date="20231231",         # 종료일(YYYYMMDD)
    statement_type="손익계산서"   # 재무제표 유형(재무상태표, 손익계산서, 현금흐름표 중 선택, 선택 사항)
)
```

### 사업 정보 검색
```python
# 회사의 사업 관련 정보 검색
search_business_information(
    company_name="삼성전자",           # 회사명
    start_date="20230101",            # 시작일(YYYYMMDD)
    end_date="20231231",              # 종료일(YYYYMMDD)
    information_type="사업의 개요"     # 정보 유형
)
```

### 현재 날짜 조회
```python
# 현재 날짜를 YYYYMMDD 형식으로 반환
get_current_date()
```

## 참고사항
- 최대 5개의 최신 공시 정보를 기반으로 데이터를 제공합니다.
- 공시 제출 기간을 고려하여 검색 종료일이 자동으로 조정될 수 있습니다.
- XBRL 파싱 과정에서 일부 데이터 추출이 실패할 수 있습니다.

## 라이선스
이 프로젝트는 [라이선스 정보]에 따라 사용이 허가됩니다.