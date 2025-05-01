import httpx
from typing import Any, Dict, List, Optional, Tuple, Set
from mcp.server.fastmcp import FastMCP, Context
import os
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO, StringIO
import re
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv


load_dotenv()
# 상수 정의
# API 설정
API_KEY = os.environ.get("DART_API_KEY")  # 환경 변수에서 API 키 로드, 없으면 기본값 사용
BASE_URL = "https://opendart.fss.or.kr/api"

# 보고서 코드
REPORT_CODE = {
    "사업보고서": "11011",
    "반기보고서": "11012",
    "1분기보고서": "11013",
    "3분기보고서": "11014"
}

# 재무상태표 항목 리스트 - 확장
BALANCE_SHEET_ITEMS = [
    "유동자산", "비유동자산", "자산총계", 
    "유동부채", "비유동부채", "부채총계", 
    "자본금", "자본잉여금", "이익잉여금", "기타자본항목", "자본총계"
]

# 현금흐름표 항목 리스트
CASH_FLOW_ITEMS = ["영업활동 현금흐름", "투자활동 현금흐름", "재무활동 현금흐름"]

# 보고서 유형별 contextRef 패턴 정의
REPORT_PATTERNS = {
    "연간": "FY",
    "3분기": "TQQ",  # 손익계산서는 TQQ
    "반기": "HYA",
    "1분기": "FQA"
}

# 현금흐름표용 특별 패턴
CASH_FLOW_PATTERNS = {
    "연간": "FY",
    "3분기": "TQA",  # 현금흐름표는 TQA
    "반기": "HYA",
    "1분기": "FQA"
}

# 재무상태표용 특별 패턴
BALANCE_SHEET_PATTERNS = {
    "연간": "FY",
    "3분기": "TQA",  # 재무상태표도 TQA
    "반기": "HYA",
    "1분기": "FQA"
}

# 데이터 무효/오류 상태 표시자
INVALID_VALUE_INDICATORS = {"N/A", "XBRL 파싱 오류", "데이터 추출 오류"}

# MCP 서버 초기화
mcp = FastMCP("dart")

# 재무제표 유형 정의
STATEMENT_TYPES = {
    "재무상태표": "BS",
    "손익계산서": "IS", 
    "현금흐름표": "CF"
}

# 세부 항목 태그 정의
DETAILED_TAGS = {
    "재무상태표": {
        "유동자산": ["ifrs-full:CurrentAssets"],
        "비유동자산": ["ifrs-full:NoncurrentAssets"],
        "자산총계": ["ifrs-full:Assets"],
        "유동부채": ["ifrs-full:CurrentLiabilities"],
        "비유동부채": ["ifrs-full:NoncurrentLiabilities"],
        "부채총계": ["ifrs-full:Liabilities"],
        "자본금": ["ifrs-full:IssuedCapital"],
        "자본잉여금": ["ifrs-full:SharePremium"],
        "이익잉여금": ["ifrs-full:RetainedEarnings"],
        "기타자본항목": ["dart:ElementsOfOtherStockholdersEquity"],
        "자본총계": ["ifrs-full:Equity"]
    },
    "손익계산서": {
        "매출액": ["ifrs-full:Revenue"],
        "매출원가": ["ifrs-full:CostOfSales"],
        "매출총이익": ["ifrs-full:GrossProfit"],
        "판매비와관리비": ["dart:TotalSellingGeneralAdministrativeExpenses"],
        "영업이익": ["dart:OperatingIncomeLoss"],
        "금융수익": ["ifrs-full:FinanceIncome"],
        "금융비용": ["ifrs-full:FinanceCosts"],
        "법인세비용차감전순이익": ["ifrs-full:ProfitLossBeforeTax"],
        "법인세비용": ["ifrs-full:IncomeTaxExpenseContinuingOperations"],
        "당기순이익": ["ifrs-full:ProfitLoss"],
        "기본주당이익": ["ifrs-full:BasicEarningsLossPerShare"]
    },
    "현금흐름표": {
        "영업활동 현금흐름": ["ifrs-full:CashFlowsFromUsedInOperatingActivities"],
        "영업에서 창출된 현금": ["ifrs-full:CashFlowsFromUsedInOperations"],
        "이자수취": ["ifrs-full:InterestReceivedClassifiedAsOperatingActivities"],
        "이자지급": ["ifrs-full:InterestPaidClassifiedAsOperatingActivities"],
        "배당금수취": ["ifrs-full:DividendsReceivedClassifiedAsOperatingActivities"],
        "법인세납부": ["ifrs-full:IncomeTaxesPaidRefundClassifiedAsOperatingActivities"],
        "투자활동 현금흐름": ["ifrs-full:CashFlowsFromUsedInInvestingActivities"],
        "유형자산의 취득": ["ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
        "무형자산의 취득": ["ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities"],
        "유형자산의 처분": ["ifrs-full:ProceedsFromSalesOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
        "재무활동 현금흐름": ["ifrs-full:CashFlowsFromUsedInFinancingActivities"],
        "배당금지급": ["ifrs-full:DividendsPaidClassifiedAsFinancingActivities"],
        "현금및현금성자산의순증가": ["ifrs-full:IncreaseDecreaseInCashAndCashEquivalents"],
        "기초현금및현금성자산": ["dart:CashAndCashEquivalentsAtBeginningOfPeriodCf"],
        "기말현금및현금성자산": ["dart:CashAndCashEquivalentsAtEndOfPeriodCf"]
    }
}

chat_guideline = "\n* 제공된 공시정보들은 분기, 반기, 연간이 섞여있을 수 있습니다. \n사용자가 특별히 연간이나 반기데이터만을 원하는게 아니라면, 주어진 데이터를 적당히 가공하여 분기별로 사용자에게 제공하세요." ; 


# Helper 함수

async def get_corp_code_by_name(corp_name: str) -> Tuple[str, str]:
    """
    회사명으로 회사의 고유번호를 검색하는 함수
    
    Args:
        corp_name: 검색할 회사명
        
    Returns:
        (고유번호, 기업이름) 튜플, 찾지 못한 경우 ("", "")
    """
    url = f"{BASE_URL}/corpCode.xml?crtfc_key={API_KEY}"
    
    try:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                
                if response.status_code != 200:
                    return ("", f"API 요청 실패: HTTP 상태 코드 {response.status_code}")
                
                try:
                    with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
                        try:
                            with zip_file.open('CORPCODE.xml') as xml_file:
                                try:
                                    tree = ET.parse(xml_file)
                                    root = tree.getroot()
                                    
                                    # 검색어를 포함하는 모든 회사 찾기
                                    matches = []
                                    for company in root.findall('.//list'):
                                        name = company.find('corp_name').text
                                        stock_code = company.find('stock_code').text
                                        
                                        # stock_code가 비어있거나 공백만 있는 경우 건너뛰기
                                        if not stock_code or stock_code.strip() == "":
                                            continue
                                            
                                        if name and corp_name in name:
                                            # 일치도 점수 계산 (낮을수록 더 정확히 일치)
                                            score = 0
                                            if name != corp_name:
                                                score += abs(len(name) - len(corp_name))
                                                if not name.startswith(corp_name):
                                                    score += 10
                                            
                                            code = company.find('corp_code').text
                                            matches.append((name, code, score))
                                    
                                    # 일치하는 회사가 없는 경우
                                    if not matches:
                                        return ("", f"'{corp_name}' 회사를 찾을 수 없습니다.")
                                    
                                    # 일치도 점수가 가장 낮은 (가장 일치하는) 회사 반환
                                    matches.sort(key=lambda x: x[2])
                                    matched_name = matches[0][0]
                                    matched_code = matches[0][1]
                                    return (matched_code, matched_name)
                                except ET.ParseError as e:
                                    return ("", f"XML 파싱 오류: {str(e)}")
                        except Exception as e:
                            return ("", f"ZIP 파일 내부 파일 접근 오류: {str(e)}")
                except zipfile.BadZipFile:
                    return ("", "다운로드한 파일이 유효한 ZIP 파일이 아닙니다.")
                except Exception as e:
                    return ("", f"ZIP 파일 처리 중 오류 발생: {str(e)}")
            except httpx.RequestError as e:
                return ("", f"API 요청 중 네트워크 오류 발생: {str(e)}")
    except Exception as e:
        return ("", f"회사 코드 조회 중 예상치 못한 오류 발생: {str(e)}")
    
    return ("", "알 수 없는 오류로 회사 정보를 찾을 수 없습니다.")


async def get_disclosure_list(corp_code: str, start_date: str, end_date: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    기업의 정기공시 목록을 조회하는 함수
    
    Args:
        corp_code: 회사 고유번호(8자리)
        start_date: 시작일(YYYYMMDD)
        end_date: 종료일(YYYYMMDD)
    
    Returns:
        (공시 목록 리스트, 오류 메시지) 튜플. 성공 시 (목록, None), 실패 시 (빈 리스트, 오류 메시지)
    """
    # 정기공시(A) 유형만 조회
    url = f"{BASE_URL}/list.json?crtfc_key={API_KEY}&corp_code={corp_code}&bgn_de={start_date}&end_de={end_date}&pblntf_ty=A&page_count=100"
    
    try:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                
                if response.status_code != 200:
                    return [], f"API 요청 실패: HTTP 상태 코드 {response.status_code}"
                
                try:
                    result = response.json()
                    
                    if result.get('status') != '000':
                        status = result.get('status', '알 수 없음')
                        msg = result.get('message', '알 수 없는 오류')
                        return [], f"DART API 오류: {status} - {msg}"
                    
                    return result.get('list', []), None
                except Exception as e:
                    return [], f"응답 JSON 파싱 오류: {str(e)}"
            except httpx.RequestError as e:
                return [], f"API 요청 중 네트워크 오류 발생: {str(e)}"
    except Exception as e:
        return [], f"공시 목록 조회 중 예상치 못한 오류 발생: {str(e)}"
    
    return [], "알 수 없는 오류로 공시 목록을 조회할 수 없습니다."


async def get_financial_statement_xbrl(rcept_no: str, reprt_code: str) -> str:
    """
    재무제표 원본파일(XBRL)을 다운로드하여 XBRL 텍스트를 반환하는 함수

    Args:
        rcept_no: 공시 접수번호(14자리)
        reprt_code: 보고서 코드 (11011: 사업보고서, 11012: 반기보고서, 11013: 1분기보고서, 11014: 3분기보고서)

    Returns:
        추출된 XBRL 텍스트 내용, 실패 시 오류 메시지 문자열
    """
    url = f"{BASE_URL}/fnlttXbrl.xml?crtfc_key={API_KEY}&rcept_no={rcept_no}&reprt_code={reprt_code}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

            if response.status_code != 200:
                return f"API 요청 실패: HTTP 상태 코드 {response.status_code}"

            try:
                with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
                    xbrl_content = ""
                    for file_name in zip_file.namelist():
                        if file_name.lower().endswith('.xbrl'):
                            with zip_file.open(file_name) as xbrl_file:
                                # XBRL 파일을 텍스트로 읽기 (UTF-8 시도, 실패 시 EUC-KR)
                                try:
                                    xbrl_content = xbrl_file.read().decode('utf-8')
                                except UnicodeDecodeError:
                                    try:
                                        xbrl_file.seek(0)
                                        xbrl_content = xbrl_file.read().decode('euc-kr')
                                    except UnicodeDecodeError:
                                        xbrl_content = "<인코딩 오류: XBRL 내용을 읽을 수 없습니다>"
                            break 
                    
                    if not xbrl_content:
                        return "ZIP 파일 내에서 XBRL 파일을 찾을 수 없습니다."
                    
                    return xbrl_content

            except zipfile.BadZipFile:
                # 응답이 ZIP 파일 형식이 아닐 경우 (DART API 오류 메시지 등)
                try:
                    error_content = response.content.decode('utf-8')
                    try:
                        root = ET.fromstring(error_content)
                        status = root.findtext('status')
                        message = root.findtext('message')
                        if status and message:
                            return f"DART API 오류: {status} - {message}"
                        else:
                            return f"유효하지 않은 ZIP 파일이며, 오류 메시지 파싱 실패: {error_content[:200]}"
                    except ET.ParseError:
                         return f"유효하지 않은 ZIP 파일이며, XML 파싱 불가: {error_content[:200]}"
                except Exception:
                    return "다운로드한 파일이 유효한 ZIP 파일이 아닙니다 (내용 확인 불가)."
            except Exception as e:
                return f"ZIP 파일 처리 중 오류 발생: {str(e)}"

    except httpx.RequestError as e:
        return f"API 요청 중 네트워크 오류 발생: {str(e)}"
    except Exception as e:
        return f"XBRL 데이터 처리 중 예상치 못한 오류 발생: {str(e)}"


def detect_namespaces(xbrl_content: str, base_namespaces: Dict[str, str]) -> Dict[str, str]:
    """
    XBRL 문서에서 네임스페이스를 추출하고 기본 네임스페이스와 병합
    
    Args:
        xbrl_content: XBRL 문서 내용
        base_namespaces: 기본 네임스페이스 딕셔너리
    
    Returns:
        업데이트된 네임스페이스 딕셔너리
    """
    namespaces = base_namespaces.copy()
    detected = {}
    
    try:
        for event, node in ET.iterparse(StringIO(xbrl_content), events=['start-ns']):
            prefix, uri = node
            if prefix and prefix not in namespaces:
                namespaces[prefix] = uri
                detected[prefix] = uri
            elif prefix and namespaces.get(prefix) != uri:
                namespaces[prefix] = uri
                detected[prefix] = uri
    except Exception:
        pass  # 네임스페이스 감지 실패 시 기본값 사용
    
    return namespaces, detected


def extract_fiscal_year(context_refs: Set[str]) -> str:
    """
    contextRef 집합에서 회계연도 추출
    
    Args:
        context_refs: XBRL 문서에서 추출한 contextRef 집합
    
    Returns:
        감지된 회계연도 또는 현재 연도
    """
    for context_ref in context_refs:
        if 'CFY' in context_ref and len(context_ref) > 7:
            match = re.search(r'CFY(\d{4})', context_ref)
            if match:
                return match.group(1)
    
    # 회계연도를 찾지 못한 경우, 현재 연도를 사용
    return str(datetime.now().year)


def get_pattern_by_item_type(item_name: str) -> Dict[str, str]:
    """
    항목 유형에 따른 적절한 패턴 선택
    
    Args:
        item_name: 재무 항목 이름
    
    Returns:
        항목 유형에 맞는 패턴 딕셔너리
    """
    # 현금흐름표 항목 확인
    if item_name in CASH_FLOW_ITEMS or item_name in DETAILED_TAGS["현금흐름표"]:
        return CASH_FLOW_PATTERNS
    
    # 재무상태표 항목 확인
    elif item_name in BALANCE_SHEET_ITEMS or item_name in DETAILED_TAGS["재무상태표"]:
        return BALANCE_SHEET_PATTERNS
    
    # 손익계산서 항목 (기본값)
    else:
        return REPORT_PATTERNS


def format_numeric_value(value_text: str, decimals: str) -> str:
    """
    XBRL 숫자 값을 포맷팅
    
    Args:
        value_text: 숫자 텍스트
        decimals: 소수점 자리수 지정 (숫자 또는 "INF")
    
    Returns:
        포맷팅된 숫자 문자열
    """
    numeric_value = float(value_text.replace(',', ''))
    
    # decimals가 "INF"인 경우 원본 값 그대로 사용
    if decimals == "INF":
        if numeric_value == int(numeric_value):
            return f"{int(numeric_value):,}"
        else:
            return f"{numeric_value:,.2f}"
    
    # 일반적인 경우 decimals에 따라 스케일 조정
    numeric_value *= (10 ** -int(decimals))
    
    if numeric_value == int(numeric_value):
        return f"{int(numeric_value):,}"
    else:
        return f"{numeric_value:,.2f}"


def parse_xbrl_financial_data(xbrl_content: str, items_and_tags: Dict[str, List[str]]) -> Dict[str, str]:
    """
    XBRL 텍스트 내용을 파싱하여 지정된 항목의 재무 데이터를 추출
    
    Args:
        xbrl_content: XBRL 파일의 전체 텍스트 내용
        items_and_tags: 추출할 항목과 태그 리스트 딕셔너리
                       {'항목명': ['태그1', '태그2', ...]}
                       
    Returns:
        추출된 재무 데이터 딕셔너리 {'항목명': '값'}
    """
    extracted_data = {item_name: "N/A" for item_name in items_and_tags}
    
    # 기본 네임스페이스 정의
    base_namespaces = {
        'ifrs-full': 'http://xbrl.ifrs.org/taxonomy/2021-03-24/ifrs-full',
        'dart': 'http://dart.fss.or.kr/xbrl/dte/2019-10-31',
        'kor-ifrs': 'http://www.fss.or.kr/xbrl/kor/kor-ifrs/2021-03-24',
    }

    try:
        # XBRL 파싱
        root = ET.fromstring(xbrl_content)
        
        # 네임스페이스 추출 및 업데이트
        namespaces, detected_namespaces = detect_namespaces(xbrl_content, base_namespaces)
        
        # 모든 contextRef 값 수집
        all_context_refs = set()
        for elem in root.findall('.//*[@contextRef]'):
            all_context_refs.add(elem.get('contextRef'))
        
        # 회계연도 추출
        fiscal_year = extract_fiscal_year(all_context_refs)
        
        # 각 항목별 태그 검색 및 값 추출
        for item_name, tag_list in items_and_tags.items():
            item_found = False
            
            for tag in tag_list:
                if item_found:
                    break
                    
                # 해당 태그 요소 검색
                elements = root.findall(f'.//{tag}', namespaces)
                if not elements:
                    continue
                
                # 항목 유형에 맞는 패턴 선택
                patterns = get_pattern_by_item_type(item_name)
                
                # 각 보고서 유형별 패턴 시도
                for report_type, pattern_code in patterns.items():
                    if item_found:
                        break
                    
                    # 기존 접두사 로직은 참조용으로만 사용 (실제 패턴 매칭에는 사용하지 않음)
                    # 패턴에서 접두사 부분을 (.): 어떤 한 글자라도 매칭되도록 함
                    pattern_base = f"CFY{fiscal_year}.{pattern_code}_ifrs-full_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs-full_ConsolidatedMember"
                    # 패턴의 끝에 $ 추가하여 정확히 일치하는 패턴만 매칭
                    pattern_regex = re.compile(f"^{pattern_base}$")
                    
                    # 패턴과 일치하는 요소 찾기
                    for elem in elements:
                        context_ref = elem.get('contextRef')
                        
                        # 정규식으로 패턴 매칭 확인 (완전 일치)
                        if context_ref and pattern_regex.match(context_ref):
                            unit_ref = elem.get('unitRef')
                            value_text = elem.text
                            decimals = elem.get('decimals', '0')
                            
                            if value_text and unit_ref:
                                try:
                                    formatted_value = format_numeric_value(value_text, decimals)
                                    extracted_data[item_name] = f"{formatted_value} ({report_type})"
                                    item_found = True
                                    break
                                except (ValueError, TypeError) as e:
                                    pass
                    
                    if item_found:
                        break

    except ET.ParseError as e:
        extracted_data = {key: "XBRL 파싱 오류" for key in items_and_tags}
    except Exception as e:
        traceback.print_exc()
        extracted_data = {key: "데이터 추출 오류" for key in items_and_tags}

    return extracted_data


def determine_report_code(report_name: str) -> Optional[str]:
    """
    보고서 이름으로부터 보고서 코드 결정
    
    Args:
        report_name: 보고서 이름
    
    Returns:
        해당하는 보고서 코드 또는 None
    """
    if "사업보고서" in report_name:
        return REPORT_CODE["사업보고서"]
    elif "반기보고서" in report_name:
        return REPORT_CODE["반기보고서"]
    elif "분기보고서" in report_name:
        if ".03)" in report_name or "(1분기)" in report_name:
            return REPORT_CODE["1분기보고서"]
        elif ".09)" in report_name or "(3분기)" in report_name:
            return REPORT_CODE["3분기보고서"]
    
    return None


def adjust_end_date(end_date: str) -> Tuple[str, bool]:
    """
    공시 제출 기간을 고려하여 종료일 조정
    
    Args:
        end_date: 원래 종료일 (YYYYMMDD)
    
    Returns:
        조정된 종료일과 조정 여부
    """
    try:
        # 입력된 end_date를 datetime 객체로 변환
        end_date_obj = datetime.strptime(end_date, "%Y%m%d")
        
        # 95일 추가
        adjusted_end_date_obj = end_date_obj + timedelta(days=95)
        
        # 현재 날짜보다 미래인 경우 현재 날짜로 조정
        current_date = datetime.now()
        if adjusted_end_date_obj > current_date:
            adjusted_end_date_obj = current_date
        
        # 포맷 변환하여 문자열로 반환
        adjusted_end_date = adjusted_end_date_obj.strftime("%Y%m%d")
        
        # 조정 여부 반환
        return adjusted_end_date, adjusted_end_date != end_date
    except Exception:
        # 오류 발생 시 원래 값 그대로 반환
        return end_date, False


def extract_business_section(document_text: str, section_type: str) -> str:
    """
    공시서류 원본파일 텍스트에서 특정 비즈니스 섹션만 추출하는 함수
    
    Args:
        document_text: 공시서류 원본 텍스트
        section_type: 추출할 섹션 유형 
                     ('사업의 개요', '주요 제품 및 서비스', '원재료 및 생산설비',
                      '매출 및 수주상황', '위험관리 및 파생거래', '주요계약 및 연구개발활동',
                      '기타 참고사항')
    
    Returns:
        추출된 섹션 텍스트 (태그 제거 및 정리된 상태)
    """
    import re
    
    # SECTION 태그 형식 확인
    section_tags = re.findall(r'<SECTION[^>]*>', document_text)
    section_end_tags = re.findall(r'</SECTION[^>]*>', document_text)
    
    # TITLE 태그가 있는지 확인
    title_tags = re.findall(r'<TITLE[^>]*>(.*?)</TITLE>', document_text)
    
    # 섹션 타입별 패턴 매핑 (번호가 포함된 경우도 처리)
    section_patterns = {
        '사업의 개요': r'<TITLE[^>]*>(?:\d+\.\s*)?사업의\s*개요[^<]*</TITLE>(.*?)(?=<TITLE|</SECTION)',
        '주요 제품 및 서비스': r'<TITLE[^>]*>(?:\d+\.\s*)?주요\s*제품[^<]*</TITLE>(.*?)(?=<TITLE|</SECTION)',
        '원재료 및 생산설비': r'<TITLE[^>]*>(?:\d+\.\s*)?원재료[^<]*</TITLE>(.*?)(?=<TITLE|</SECTION)',
        '매출 및 수주상황': r'<TITLE[^>]*>(?:\d+\.\s*)?매출[^<]*</TITLE>(.*?)(?=<TITLE|</SECTION)',
        '위험관리 및 파생거래': r'<TITLE[^>]*>(?:\d+\.\s*)?위험관리[^<]*</TITLE>(.*?)(?=<TITLE|</SECTION)',
        '주요계약 및 연구개발활동': r'<TITLE[^>]*>(?:\d+\.\s*)?주요\s*계약[^<]*</TITLE>(.*?)(?=<TITLE|</SECTION)',
        '기타 참고사항': r'<TITLE[^>]*>(?:\d+\.\s*)?기타\s*참고사항[^<]*</TITLE>(.*?)(?=<TITLE|</SECTION)',
    }
    
    # 요청된 섹션 패턴 확인
    if section_type not in section_patterns:
        return f"지원하지 않는 섹션 유형입니다. 지원되는 유형: {', '.join(section_patterns.keys())}"
    
    # 해당 섹션과 일치하는 제목 찾기
    section_keyword = section_type.split(' ')[0]
    matching_titles = [title for title in title_tags if section_keyword.lower() in title.lower()]
    
    # 정규표현식 패턴으로 섹션 추출 시도 1: 기본 패턴
    pattern = section_patterns[section_type]
    matches = re.search(pattern, document_text, re.DOTALL | re.IGNORECASE)
    
    # 정규표현식 패턴으로 섹션 추출 시도 2: SECTION 태그 종료 패턴 수정
    if not matches:
        # SECTION-숫자 형태의 종료 태그 지원
        pattern = section_patterns[section_type].replace('</SECTION', '</SECTION(?:-\\d+)?')
        matches = re.search(pattern, document_text, re.DOTALL | re.IGNORECASE)
    
    # 정규표현식 패턴으로 섹션 추출 시도 3: 개별 TITLE 직접 검색
    if not matches and matching_titles:
        for title in matching_titles:
            escaped_title = re.escape(title)
            direct_pattern = f'<TITLE[^>]*>{escaped_title}</TITLE>(.*?)(?=<TITLE|</SECTION(?:-\\d+)?)'
            matches = re.search(direct_pattern, document_text, re.DOTALL | re.IGNORECASE)
            if matches:
                break
    
    if not matches:
        return f"'{section_type}' 섹션을 찾을 수 없습니다."
    
    # 추출된 텍스트
    section_text = matches.group(1)
    
    # 태그 제거 및 텍스트 정리
    clean_text = re.sub(r'<[^>]*>', ' ', section_text)  # HTML 태그 제거
    clean_text = re.sub(r'USERMARK\s*=\s*"[^"]*"', '', clean_text)  # USERMARK 제거
    clean_text = re.sub(r'\s+', ' ', clean_text)  # 연속된 공백 제거
    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)  # 빈 줄 처리
    clean_text = clean_text.strip()  # 앞뒤 공백 제거
    
    return clean_text


async def extract_business_section_from_dart(rcept_no: str, section_type: str) -> str:
    """
    DART API를 통해 공시서류를 다운로드하고 특정 비즈니스 섹션만 추출하는 함수
    
    Args:
        rcept_no: 공시 접수번호(14자리)
        section_type: 추출할 섹션 유형 
                    ('사업의 개요', '주요 제품 및 서비스', '원재료 및 생산설비',
                     '매출 및 수주상황', '위험관리 및 파생거래', '주요계약 및 연구개발활동',
                     '기타 참고사항')
    
    Returns:
        추출된 섹션 텍스트 또는 오류 메시지
    """
    # 원본 문서 다운로드
    document_text, binary_data = await get_original_document(rcept_no)
    
    # 다운로드 실패 시
    if binary_data is None:
        return f"공시서류 다운로드 실패: {document_text}"
    
    # 섹션 추출
    section_text = extract_business_section(document_text, section_type)
    
    return section_text


async def get_original_document(rcept_no: str) -> Tuple[str, Optional[bytes]]:
    """
    DART 공시서류 원본파일을 다운로드하여 텍스트로 변환해 반환하는 함수
    
    Args:
        rcept_no: 공시 접수번호(14자리)
        
    Returns:
        (파일 내용 문자열 또는 오류 메시지, 원본 바이너리 데이터(성공 시) 또는 None(실패 시))
    """
    url = f"{BASE_URL}/document.xml?crtfc_key={API_KEY}&rcept_no={rcept_no}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                return f"API 요청 실패: HTTP 상태 코드 {response.status_code}", None
            
            # API 오류 메시지 확인 시도 (XML 형식일 수 있음)
            try:
                root = ET.fromstring(response.content)
                status = root.findtext('status')
                message = root.findtext('message')
                if status and message:
                    return f"DART API 오류: {status} - {message}", None
            except ET.ParseError:
                # 파싱 오류는 정상적인 ZIP 파일일 수 있으므로 계속 진행
                pass
            
            try:
                # ZIP 파일 처리
                with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
                    # 압축 파일 내의 파일 목록
                    file_list = zip_file.namelist()
                    
                    if not file_list:
                        return "ZIP 파일 내에 파일이 없습니다.", None
                    
                    # 파일명이 가장 짧은 파일 선택 (일반적으로 메인 파일일 가능성이 높음)
                    target_file = min(file_list, key=len)
                    file_ext = target_file.split('.')[-1].lower()
                    
                    # 파일 내용 읽기
                    with zip_file.open(target_file) as doc_file:
                        file_content = doc_file.read()
                        
                        # 텍스트 파일인 경우 (txt, html, xml 등)
                        if file_ext in ['txt', 'html', 'htm', 'xml', 'xbrl']:
                            # 다양한 인코딩 시도
                            encodings = ['utf-8', 'euc-kr', 'cp949']
                            text_content = None
                            
                            for encoding in encodings:
                                try:
                                    text_content = file_content.decode(encoding)
                                    break
                                except UnicodeDecodeError:
                                    continue
                            
                            if text_content:
                                return text_content, file_content
                            else:
                                return "파일을 텍스트로 변환할 수 없습니다 (인코딩 문제).", file_content
                        # PDF 또는 기타 바이너리 파일
                        else:
                            return f"파일이 텍스트 형식이 아닙니다 (형식: {file_ext}).", file_content
                        
            except zipfile.BadZipFile:
                return "다운로드한 파일이 유효한 ZIP 파일이 아닙니다.", None
                
    except httpx.RequestError as e:
        return f"API 요청 중 네트워크 오류 발생: {str(e)}", None
    except Exception as e:
        return f"공시 원본 다운로드 중 예상치 못한 오류 발생: {str(e)}", None


# MCP 도구
@mcp.tool()
async def search_disclosure(
    company_name: str, 
    start_date: str, 
    end_date: str, 
    ctx: Context,
    requested_items: Optional[List[str]] = None,
) -> str:
    """
    회사의 주요 재무 정보를 검색하여 제공하는 도구.
    requested_items가 주어지면 해당 항목 관련 데이터가 있는 공시만 필터링합니다.
    
    Args:
        company_name: 회사명 (예: 삼성전자, 네이버 등)
        start_date: 시작일 (YYYYMMDD 형식, 예: 20230101)
        end_date: 종료일 (YYYYMMDD 형식, 예: 20231231)
        ctx: MCP Context 객체
        requested_items: 사용자가 요청한 재무 항목 이름 리스트 (예: ["매출액", "영업이익"]). None이면 모든 주요 항목을 대상으로 함. 사용 가능한 항목: 매출액, 영업이익, 당기순이익, 영업활동 현금흐름, 투자활동 현금흐름, 재무활동 현금흐름, 자산총계, 부채총계, 자본총계
        
    Returns:
        검색된 각 공시의 주요 재무 정보 요약 텍스트 (요청 항목 관련 데이터가 있는 경우만)
    """
    # 결과 문자열 초기화
    result = ""
    
    try:
        # 진행 상황 알림
        info_msg = f"{company_name}의"
        if requested_items:
            info_msg += f" {', '.join(requested_items)} 관련"
        info_msg += " 재무 정보를 검색합니다."
        ctx.info(info_msg)
        
        # end_date 조정
        original_end_date = end_date
        adjusted_end_date, was_adjusted = adjust_end_date(end_date)
        
        if was_adjusted:
            ctx.info(f"공시 제출 기간을 고려하여 검색 종료일을 {original_end_date}에서 {adjusted_end_date}로 자동 조정했습니다.")
            end_date = adjusted_end_date
        
        # 회사 코드 조회
        corp_code, matched_name = await get_corp_code_by_name(company_name)
        if not corp_code:
            return f"회사 검색 오류: {matched_name}"
        
        ctx.info(f"{matched_name}(고유번호: {corp_code})의 공시를 검색합니다.")
        
        # 공시 목록 조회
        disclosures, error_msg = await get_disclosure_list(corp_code, start_date, end_date)
        if error_msg:
            return f"공시 목록 조회 오류: {error_msg}"
            
        if not disclosures:
            date_range_msg = f"{start_date}부터 {end_date}까지"
            if was_adjusted:
                date_range_msg += f" (원래 요청: {start_date}~{original_end_date}, 공시 제출 기간 고려하여 확장)"
            return f"{date_range_msg} '{matched_name}'(고유번호: {corp_code})의 정기공시가 없습니다."
        
        ctx.info(f"{len(disclosures)}개의 정기공시를 찾았습니다. XBRL 데이터 조회 및 분석을 시도합니다.")

        # 추출할 재무 항목 및 가능한 태그 리스트 정의
        all_items_and_tags = {
            "매출액": ["ifrs-full:Revenue"],
            "영업이익": ["dart:OperatingIncomeLoss"],
            "당기순이익": ["ifrs-full:ProfitLoss"],
            "영업활동 현금흐름": ["ifrs-full:CashFlowsFromUsedInOperatingActivities"],
            "투자활동 현금흐름": ["ifrs-full:CashFlowsFromUsedInInvestingActivities"],
            "재무활동 현금흐름": ["ifrs-full:CashFlowsFromUsedInFinancingActivities"],
            "자산총계": ["ifrs-full:Assets"],
            "부채총계": ["ifrs-full:Liabilities"],
            "자본총계": ["ifrs-full:Equity"]
        }

        # 사용자가 요청한 항목만 추출하도록 구성
        if requested_items:
            items_to_extract = {item: tags for item, tags in all_items_and_tags.items() if item in requested_items}
            if not items_to_extract:
                 unsupported_items = [item for item in requested_items if item not in all_items_and_tags]
                 return f"요청하신 항목 중 지원되지 않는 항목이 있습니다: {', '.join(unsupported_items)}. 지원 항목: {', '.join(all_items_and_tags.keys())}"
        else:
            items_to_extract = all_items_and_tags
        
        # 결과 문자열 초기화
        result = f"# {matched_name} 주요 재무 정보 ({start_date} ~ {end_date})\n"
        if requested_items: 
            result += f"({', '.join(requested_items)} 관련)\n"
        result += "\n"
        
        # 최대 5개의 공시만 처리 (API 호출 제한 및 시간 고려)
        disclosure_count = min(5, len(disclosures))
        processed_count = 0
        relevant_reports_found = 0
        api_errors = []
        
        # 각 공시별 처리
        for disclosure in disclosures[:disclosure_count]:
            report_name = disclosure.get('report_nm', '제목 없음')
            rcept_dt = disclosure.get('rcept_dt', '날짜 없음')
            rcept_no = disclosure.get('rcept_no', '')

            # 보고서 코드 결정
            reprt_code = determine_report_code(report_name)
            if not rcept_no or not reprt_code:
                continue

            # 진행 상황 보고
            processed_count += 1
            await ctx.report_progress(processed_count, disclosure_count) 
            
            ctx.info(f"공시 {processed_count}/{disclosure_count} 분석 중: {report_name} (접수번호: {rcept_no})")
            
            # XBRL 데이터 조회
            try:
                xbrl_text = await get_financial_statement_xbrl(rcept_no, reprt_code)
                
                # XBRL 파싱 및 데이터 추출
                financial_data = {}
                parse_error = None
                
                if not xbrl_text.startswith(("DART API 오류:", "API 요청 실패:", "ZIP 파일", "<인코딩 오류:")):
                     try:
                         financial_data = parse_xbrl_financial_data(xbrl_text, items_to_extract)
                     except Exception as e:
                         parse_error = e
                         ctx.warning(f"XBRL 파싱/분석 중 오류 발생 ({report_name}): {e}")
                         financial_data = {key: "분석 중 예외 발생" for key in items_to_extract}
                elif xbrl_text.startswith("DART API 오류: 013"):
                    financial_data = {key: "데이터 없음(API 013)" for key in items_to_extract}
                else:
                    error_summary = xbrl_text.split('\n')[0][:100]
                    financial_data = {key: f"오류({error_summary})" for key in items_to_extract}
                    api_errors.append(f"{report_name}: {error_summary}")

                # 요청된 항목 관련 데이터가 있는지 확인
                is_relevant = True
                if requested_items:
                    is_relevant = any(
                        item in financial_data and 
                        financial_data[item] not in INVALID_VALUE_INDICATORS and 
                        not financial_data[item].startswith("오류(") and
                        not financial_data[item].startswith("분석 중")
                        for item in requested_items
                    )

                # 관련 데이터가 있는 공시만 결과에 추가
                if is_relevant:
                    relevant_reports_found += 1
                    result += f"## {report_name} ({rcept_dt})\n"
                    result += f"접수번호: {rcept_no}\n\n"
                    
                    if financial_data:
                        for item, value in financial_data.items():
                             result += f"- {item}: {value}\n"
                    elif parse_error:
                         result += f"- XBRL 분석 중 오류 발생: {parse_error}\n"
                    else:
                         result += "- 주요 재무 정보를 추출하지 못했습니다.\n"
                    
                    result += "\n" + "-" * 50 + "\n\n"
                else:
                     ctx.info(f"[{report_name}] 건너뜀: 요청하신 항목({', '.join(requested_items) if requested_items else '전체'}) 관련 유효 데이터 없음.")
            except Exception as e:
                ctx.error(f"공시 처리 중 예상치 못한 오류 발생 ({report_name}): {e}")
                api_errors.append(f"{report_name}: {str(e)}")
                traceback.print_exc()

        # 최종 결과 메시지 추가
        if api_errors:
            result += "\n## 처리 중 발생한 오류\n"
            for error in api_errors:
                result += f"- {error}\n"
            result += "\n"
            
        if relevant_reports_found == 0 and processed_count > 0:
             no_data_reason = "요청하신 항목 관련 유효한 데이터를 찾지 못했거나" if requested_items else "주요 재무 데이터를 찾지 못했거나"
             result += f"※ 처리된 공시에서 {no_data_reason}, 데이터가 제공되지 않는 보고서일 수 있습니다.\n"
        elif processed_count == 0 and disclosures:
             result += "조회된 정기공시가 있으나, XBRL 데이터를 포함하는 보고서 유형(사업/반기/분기)이 아니거나 처리 중 오류가 발생했습니다.\n"
             
        if len(disclosures) > disclosure_count:
            result += f"※ 총 {len(disclosures)}개의 정기공시 중 최신 {disclosure_count}개에 대해 분석을 시도했습니다.\n"
        
        if relevant_reports_found > 0 and requested_items:
             result += f"\n※ 요청하신 항목({', '.join(requested_items)}) 관련 정보가 있는 {relevant_reports_found}개의 보고서를 표시했습니다.\n"

    except Exception as e:
        return f"재무 정보 검색 중 예상치 못한 오류가 발생했습니다: {str(e)}\n\n{traceback.format_exc()}"

    result += chat_guideline
    return result.strip()


@mcp.tool()
async def search_detailed_financial_data(
    company_name: str,
    start_date: str,
    end_date: str,
    ctx: Context,
    statement_type: Optional[str] = None,
) -> str:
    """
    회사의 세부적인 재무 정보를 제공하는 도구.
    XBRL 파일을 파싱하여 상세한 재무 데이터를 추출합니다.
    
    Args:
        company_name: 회사명 (예: 삼성전자, 네이버 등)
        start_date: 시작일 (YYYYMMDD 형식, 예: 20230101)
        end_date: 종료일 (YYYYMMDD 형식, 예: 20231231)
        ctx: MCP Context 객체
        statement_type: 재무제표 유형 ("재무상태표", "손익계산서", "현금흐름표" 중 하나 또는 None)
                       None인 경우 모든 유형의 재무제표 정보를 반환합니다.
        
    Returns:
        선택한 재무제표 유형(들)의 세부 항목 정보가 포함된 텍스트
    """
    # 결과 문자열 초기화
    result = ""
    api_errors = []
    
    try:
        # 재무제표 유형 검증
        if statement_type is not None and statement_type not in STATEMENT_TYPES:
            return f"지원하지 않는 재무제표 유형입니다. 지원되는 유형: {', '.join(STATEMENT_TYPES.keys())}"
        
        # 모든 재무제표 유형을 처리할 경우
        if statement_type is None:
            all_statement_types = list(STATEMENT_TYPES.keys())
            ctx.info(f"{company_name}의 모든 재무제표(재무상태표, 손익계산서, 현금흐름표) 세부 정보를 검색합니다.")
        else:
            all_statement_types = [statement_type]
            ctx.info(f"{company_name}의 {statement_type} 세부 정보를 검색합니다.")
        
        # end_date 조정
        original_end_date = end_date
        adjusted_end_date, was_adjusted = adjust_end_date(end_date)
        
        if was_adjusted:
            ctx.info(f"공시 제출 기간을 고려하여 검색 종료일을 {original_end_date}에서 {adjusted_end_date}로 자동 조정했습니다.")
            end_date = adjusted_end_date
        
        # 회사 코드 조회
        corp_code, matched_name = await get_corp_code_by_name(company_name)
        if not corp_code:
            return f"회사 검색 오류: {matched_name}"
        
        ctx.info(f"{matched_name}(고유번호: {corp_code})의 공시를 검색합니다.")
        
        # 공시 목록 조회
        disclosures, error_msg = await get_disclosure_list(corp_code, start_date, end_date)
        if error_msg:
            return error_msg
            
        if not disclosures:
            date_range_msg = f"{start_date}부터 {end_date}까지"
            if was_adjusted:
                date_range_msg += f" (원래 요청: {start_date}~{original_end_date}, 공시 제출 기간 고려하여 확장)"
            return f"{date_range_msg} '{matched_name}'(고유번호: {corp_code})의 정기공시가 없습니다."
        
        ctx.info(f"{len(disclosures)}개의 정기공시를 찾았습니다. XBRL 데이터 조회 및 분석을 시도합니다.")

        # 결과 문자열 초기화
        result = f"# {matched_name}의 세부 재무 정보 ({start_date} ~ {end_date})\n\n"
        
        # 최대 5개의 공시만 처리 (API 호출 제한 및 시간 고려)
        disclosure_count = min(5, len(disclosures))
        
        # 각 공시별로 XBRL 데이터 조회 및 저장
        processed_disclosures = []
        
        for disclosure in disclosures[:disclosure_count]:
            try:
                report_name = disclosure.get('report_nm', '제목 없음')
                rcept_dt = disclosure.get('rcept_dt', '날짜 없음')
                rcept_no = disclosure.get('rcept_no', '')

                # 보고서 코드 결정
                reprt_code = determine_report_code(report_name)
                if not rcept_no or not reprt_code:
                    continue

                ctx.info(f"공시 분석 중: {report_name} (접수번호: {rcept_no})")
                
                # XBRL 데이터 조회
                xbrl_text = await get_financial_statement_xbrl(rcept_no, reprt_code)
                
                if not xbrl_text.startswith(("DART API 오류:", "API 요청 실패:", "ZIP 파일", "<인코딩 오류:")):
                    processed_disclosures.append({
                        'report_name': report_name,
                        'rcept_dt': rcept_dt,
                        'rcept_no': rcept_no,
                        'reprt_code': reprt_code,
                        'xbrl_text': xbrl_text
                    })
                else:
                    error_summary = xbrl_text.split('\n')[0][:100]
                    api_errors.append(f"{report_name}: {error_summary}")
                    ctx.warning(f"XBRL 데이터 조회 오류 ({report_name}): {error_summary}")
            except Exception as e:
                api_errors.append(f"{report_name if 'report_name' in locals() else '알 수 없는 보고서'}: {str(e)}")
                ctx.error(f"공시 데이터 처리 중 예상치 못한 오류 발생: {e}")
                traceback.print_exc()
        
        # 각 재무제표 유형별 처리
        for current_statement_type in all_statement_types:
            result += f"## {current_statement_type}\n\n"
            
            # 해당 재무제표 유형에 대한 태그 목록 조회
            items_to_extract = DETAILED_TAGS[current_statement_type]
            
            # 재무제표 유형별 결과 저장
            reports_with_data = 0
            
            # 각 공시별 처리
            for disclosure in processed_disclosures:
                try:
                    report_name = disclosure['report_name']
                    rcept_dt = disclosure['rcept_dt']
                    rcept_no = disclosure['rcept_no']
                    xbrl_text = disclosure['xbrl_text']
                    
                    # XBRL 파싱 및 데이터 추출
                    try:
                        financial_data = parse_xbrl_financial_data(xbrl_text, items_to_extract)
                        
                        # 유효한 데이터가 있는지 확인 (최소 1개 항목 이상)
                        valid_items_count = sum(1 for value in financial_data.values() 
                                              if value not in INVALID_VALUE_INDICATORS 
                                              and not value.startswith("오류(") 
                                              and not value.startswith("분석 중"))
                        
                        if valid_items_count >= 1:
                            reports_with_data += 1
                            
                            # 데이터 결과에 추가
                            result += f"### {report_name} ({rcept_dt})\n"
                            result += f"접수번호: {rcept_no}\n\n"
                            
                            # 테이블 형식으로 데이터 출력
                            result += "| 항목 | 값 |\n"
                            result += "|------|------|\n"
                            
                            for item, value in financial_data.items():
                                if value not in INVALID_VALUE_INDICATORS and not value.startswith("오류(") and not value.startswith("분석 중"):
                                    result += f"| {item} | {value} |\n"
                                else:
                                    # 매칭되지 않은 항목은 '-'로 표시
                                    result += f"| {item} | - |\n"
                            
                            result += "\n"
                        else:
                            ctx.info(f"[{report_name}] {current_statement_type}의 유효한 데이터가 없습니다.")
                    except Exception as e:
                        ctx.warning(f"XBRL 파싱/분석 중 오류 발생 ({report_name}): {e}")
                        api_errors.append(f"{report_name} 분석 중 오류: {str(e)}")
                except Exception as e:
                    ctx.error(f"공시 데이터 처리 중 예상치 못한 오류 발생: {e}")
                    api_errors.append(f"공시 데이터 처리 오류: {str(e)}")
                    traceback.print_exc()
            
            # 재무제표 유형별 결과 요약
            if reports_with_data == 0:
                result += f"조회된 공시에서 유효한 {current_statement_type} 데이터를 찾지 못했습니다.\n\n"
            
            result += "-" * 50 + "\n\n"
        
        # 최종 결과 메시지 추가
        if api_errors:
            result += "\n## 처리 중 발생한 오류\n"
            for error in api_errors:
                result += f"- {error}\n"
            result += "\n"
            
        if len(disclosures) > disclosure_count:
            result += f"※ 총 {len(disclosures)}개의 정기공시 중 최신 {disclosure_count}개에 대해 분석을 시도했습니다.\n"
        
        if len(processed_disclosures) == 0:
            result += "※ 모든 공시에서 XBRL 데이터를 추출하는데 실패했습니다. 오류 메시지를 확인해주세요.\n"
        
    except Exception as e:
        return f"세부 재무 정보 검색 중 예상치 못한 오류가 발생했습니다: {str(e)}\n\n{traceback.format_exc()}"

    result += chat_guideline
    return result.strip()


@mcp.tool()
async def search_business_information(
    company_name: str,
    start_date: str,
    end_date: str,
    information_type: str,
    ctx: Context,
) -> str:
    """
    회사의 사업 관련 현황 정보를 제공하는 도구
    
    Args:
        company_name: 회사명 (예: 삼성전자, 네이버 등)
        start_date: 시작일 (YYYYMMDD 형식, 예: 20230101)
        end_date: 종료일 (YYYYMMDD 형식, 예: 20231231)
        information_type: 조회할 정보 유형 
            '사업의 개요' - 회사의 전반적인 사업 내용
            '주요 제품 및 서비스' - 회사의 주요 제품과 서비스 정보
            '원재료 및 생산설비' - 원재료 조달 및 생산 설비 현황
            '매출 및 수주상황' - 매출과 수주 현황 정보
            '위험관리 및 파생거래' - 리스크 관리 방안 및 파생상품 거래 정보
            '주요계약 및 연구개발활동' - 주요 계약 현황 및 R&D 활동
            '기타 참고사항' - 기타 사업 관련 참고 정보
        ctx: MCP Context 객체
        
    Returns:
        요청한 정보 유형에 대한 해당 회사의 사업 정보 텍스트
    """
    # 결과 문자열 초기화
    result = ""
    
    try:
        # 지원하는 정보 유형 검증
        supported_types = [
            '사업의 개요', '주요 제품 및 서비스', '원재료 및 생산설비',
            '매출 및 수주상황', '위험관리 및 파생거래', '주요계약 및 연구개발활동',
            '기타 참고사항'
        ]
        
        if information_type not in supported_types:
            return f"지원하지 않는 정보 유형입니다. 지원되는 유형: {', '.join(supported_types)}"
        
        # 진행 상황 알림
        ctx.info(f"{company_name}의 {information_type} 정보를 검색합니다.")
        
        # end_date 조정
        original_end_date = end_date
        adjusted_end_date, was_adjusted = adjust_end_date(end_date)
        
        if was_adjusted:
            ctx.info(f"공시 제출 기간을 고려하여 검색 종료일을 {original_end_date}에서 {adjusted_end_date}로 자동 조정했습니다.")
            end_date = adjusted_end_date
        
        # 회사 코드 조회
        corp_code, matched_name = await get_corp_code_by_name(company_name)
        if not corp_code:
            return f"회사 검색 오류: {matched_name}"
        
        ctx.info(f"{matched_name}(고유번호: {corp_code})의 공시를 검색합니다.")
        
        # 공시 목록 조회
        disclosures, error_msg = await get_disclosure_list(corp_code, start_date, end_date)
        if error_msg:
            return error_msg
            
        ctx.info(f"{len(disclosures)}개의 정기공시를 찾았습니다. 적절한 공시를 선택하여 정보를 추출합니다.")
        
        # 사업정보를 포함할 가능성이 높은 정기보고서를 우선순위에 따라 필터링
        priority_reports = [
            "사업보고서", "반기보고서", "분기보고서"
        ]
        
        selected_disclosure = None
        
        # 우선순위에 따라 공시 선택
        for priority in priority_reports:
            for disclosure in disclosures:
                report_name = disclosure.get('report_nm', '')
                if priority in report_name:
                    selected_disclosure = disclosure
                    break
            if selected_disclosure:
                break
        
        # 우선순위에 따른 공시를 찾지 못한 경우 첫 번째 공시 선택
        if not selected_disclosure and disclosures:
            selected_disclosure = disclosures[0]
        
        if not selected_disclosure:
            return f"'{matched_name}'의 적절한 공시를 찾을 수 없습니다."
        
        # 선택된 공시 정보
        report_name = selected_disclosure.get('report_nm', '제목 없음')
        rcept_dt = selected_disclosure.get('rcept_dt', '날짜 없음')
        rcept_no = selected_disclosure.get('rcept_no', '')
        
        ctx.info(f"'{report_name}' (접수번호: {rcept_no}, 접수일: {rcept_dt}) 공시에서 '{information_type}' 정보를 추출합니다.")
        
        # 섹션 추출
        try:
            section_text = await extract_business_section_from_dart(rcept_no, information_type)
            
            # 추출 결과 확인
            if section_text.startswith(f"공시서류 다운로드 실패") or section_text.startswith(f"'{information_type}' 섹션을 찾을 수 없습니다"):
                api_error = section_text
                result = f"# {matched_name} - {information_type}\n\n"
                result += f"## 출처: {report_name} (접수일: {rcept_dt})\n\n"
                result += f"정보 추출 실패: {api_error}\n\n"
                result += "다음과 같은 이유로 정보를 추출하지 못했습니다:\n"
                result += "1. 해당 공시에 요청하신 정보가 포함되어 있지 않을 수 있습니다.\n"
                result += "2. DART API 호출 중 오류가 발생했을 수 있습니다.\n"
                result += "3. 섹션 추출 과정에서 패턴 매칭에 실패했을 수 있습니다.\n"
                return result
            else:
                # 결과 포맷팅
                result = f"# {matched_name} - {information_type}\n\n"
                result += f"## 출처: {report_name} (접수일: {rcept_dt})\n\n"
                result += section_text
                # 텍스트가 너무 길 경우 앞부분만 반환
                max_length = 5000  # 적절한 최대 길이 설정
                if len(result) > max_length:
                    result = result[:max_length] + f"\n\n... (이하 생략, 총 {len(result)} 자)"
        except Exception as e:
            ctx.error(f"섹션 추출 중 예상치 못한 오류 발생: {e}")
            result = f"# {matched_name} - {information_type}\n\n"
            result += f"## 출처: {report_name} (접수일: {rcept_dt})\n\n"
            result += f"정보 추출 중 오류 발생: {str(e)}\n\n"
            result += "다음과 같은 이유로 정보를 추출하지 못했습니다:\n"
            result += "1. 섹션 추출 과정에서 예외가 발생했습니다.\n"
            result += "2. 오류 상세 정보: " + traceback.format_exc().replace('\n', '\n   ') + "\n"
            
    except Exception as e:
        return f"사업 정보 검색 중 예상치 못한 오류가 발생했습니다: {str(e)}\n\n{traceback.format_exc()}"

    return result


@mcp.tool()
async def get_current_date(
    ctx: Context = None
) -> str:
    """
    현재 날짜를 YYYYMMDD 형식으로 반환하는 도구
    
    Args:
        ctx: MCP Context 객체 (선택 사항)
        
    Returns:
        YYYYMMDD 형식의 현재 날짜 문자열
    """
    # 현재 날짜를 YYYYMMDD 형식으로 포맷팅
    formatted_date = datetime.now().strftime("%Y%m%d")
    
    # 컨텍스트가 제공된 경우 로그 출력
    if ctx:
        ctx.info(f"현재 날짜: {formatted_date}")
    
    return formatted_date


async def get_financial_json(corp_code: str, bsns_year: str, reprt_code: str, fs_div: str = "OFS") -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    DART API를 통해 단일회사 전체 재무제표를 JSON 형태로 가져오는 함수
    
    Args:
        corp_code: 회사 고유번호(8자리)
        bsns_year: 사업연도(4자리) 예: "2023"
        reprt_code: 보고서 코드 (11011: 사업보고서, 11012: 반기보고서, 11013: 1분기보고서, 11014: 3분기보고서)
        fs_div: 개별/연결구분 (OFS:재무제표, CFS:연결재무제표)
        
    Returns:
        (재무 데이터 리스트, 오류 메시지) 튜플. 성공 시 (리스트, None), 실패 시 (빈 리스트, 오류 메시지)
    """
    url = f"{BASE_URL}/fnlttSinglAcntAll.json?crtfc_key={API_KEY}&corp_code={corp_code}&bsns_year={bsns_year}&reprt_code={reprt_code}&fs_div={fs_div}"
    
    try:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                
                if response.status_code != 200:
                    return [], f"API 요청 실패: HTTP 상태 코드 {response.status_code}"
                
                try:
                    result = response.json()
                    
                    if result.get('status') != '000':
                        status = result.get('status', '알 수 없음')
                        msg = result.get('message', '알 수 없는 오류')
                        return [], f"DART API 오류: {status} - {msg}"
                    
                    return result.get('list', []), None
                except Exception as e:
                    return [], f"응답 JSON 파싱 오류: {str(e)}"
            except httpx.RequestError as e:
                return [], f"API 요청 중 네트워크 오류 발생: {str(e)}"
    except Exception as e:
        return [], f"재무 데이터 조회 중 예상치 못한 오류 발생: {str(e)}"
    
    return [], "알 수 없는 오류로 재무 데이터를 조회할 수 없습니다."


def get_report_code_name(reprt_code: str) -> str:
    """
    보고서 코드에 해당하는 보고서 이름을 반환하는 함수
    
    Args:
        reprt_code: 보고서 코드
        
    Returns:
        보고서 이름
    """
    code_to_name = {
        "11011": "사업보고서",
        "11012": "반기보고서",
        "11013": "1분기보고서",
        "11014": "3분기보고서"
    }
    
    return code_to_name.get(reprt_code, "알 수 없는 보고서")


def get_statement_name(sj_div: str) -> str:
    """
    재무제표 구분 코드에 해당하는 재무제표 이름을 반환하는 함수
    
    Args:
        sj_div: 재무제표 구분 코드
        
    Returns:
        재무제표 이름
    """
    div_to_name = {
        "BS": "재무상태표",
        "IS": "손익계산서",
        "CIS": "포괄손익계산서",
        "CF": "현금흐름표",
        "SCE": "자본변동표"
    }
    
    return div_to_name.get(sj_div, "알 수 없는 재무제표")


@mcp.tool()
async def search_json_financial_data(
    company_name: str,
    bsns_year: str,
    ctx: Context,
    reprt_code: Optional[str] = "11011",
    fs_div: Optional[str] = "OFS",
    statement_type: Optional[str] = None
) -> str:
    """
    회사의 재무 정보를 JSON API를 통해 제공하는 실패시 보완하는 보조 도구.
    search_disclosure, search_detailed_financial_data이 2023년 9월 이전 자료 분석에 실패했을 때 대안으로 활용.
    
    Args:
        company_name: 회사명 (예: 삼성전자, 네이버 등)
        bsns_year: 사업연도 (4자리, 예: "2023")
        ctx: MCP Context 객체
        reprt_code: 보고서 코드 ("11011": 사업보고서, "11012": 반기보고서, "11013": 1분기보고서, "11014": 3분기보고서)
        fs_div: 개별/연결구분 ("OFS": 재무제표, "CFS": 연결재무제표)
        statement_type: 재무제표 유형 ("BS": 재무상태표, "IS": 손익계산서, "CIS": 포괄손익계산서, "CF": 현금흐름표, "SCE": 자본변동표)
                       None인 경우 모든 유형의 재무제표 정보를 반환합니다.
        
    Returns:
        선택한 재무제표 유형(들)의 세부 항목 정보가 포함된 텍스트 (당기 데이터만 표시)
    """
    # 결과 문자열 초기화
    result = ""
    api_errors = []
    
    try:
        # 보고서 코드 검증
        valid_report_codes = {"11011", "11012", "11013", "11014"}
        if reprt_code not in valid_report_codes:
            return f"지원하지 않는 보고서 코드입니다. 지원되는 코드: {', '.join(valid_report_codes)} (11011: 사업보고서, 11012: 반기보고서, 11013: 1분기보고서, 11014: 3분기보고서)"
        
        # 개별/연결 구분 검증
        valid_fs_divs = {"OFS", "CFS"}
        if fs_div not in valid_fs_divs:
            return f"지원하지 않는 개별/연결 구분입니다. 지원되는 구분: {', '.join(valid_fs_divs)} (OFS: 재무제표, CFS: 연결재무제표)"
        
        # 재무제표 유형 검증
        valid_statement_types = {"BS", "IS", "CIS", "CF", "SCE"}
        if statement_type is not None and statement_type not in valid_statement_types:
            return f"지원하지 않는 재무제표 유형입니다. 지원되는 유형: {', '.join(valid_statement_types)} (BS: 재무상태표, IS: 손익계산서, CIS: 포괄손익계산서, CF: 현금흐름표, SCE: 자본변동표)"
        
        # 진행상황 알림
        report_name = get_report_code_name(reprt_code)
        fs_div_name = "개별재무제표" if fs_div == "OFS" else "연결재무제표"
        
        if statement_type is None:
            ctx.info(f"{company_name}의 {bsns_year}년 {report_name} {fs_div_name} 전체 재무정보를 검색합니다.")
        else:
            statement_name = get_statement_name(statement_type)
            ctx.info(f"{company_name}의 {bsns_year}년 {report_name} {fs_div_name} 중 {statement_name} 정보를 검색합니다.")
        
        # 회사 코드 조회
        corp_code, matched_name = await get_corp_code_by_name(company_name)
        if not corp_code:
            return f"회사 검색 오류: {matched_name}"
        
        ctx.info(f"{matched_name}(고유번호: {corp_code})의 재무정보를 검색합니다.")
        
        # JSON API를 통해 재무 데이터 조회
        financial_data, error_msg = await get_financial_json(corp_code, bsns_year, reprt_code, fs_div)
        
        if error_msg:
            return f"재무 데이터 조회 오류: {error_msg}"
            
        if not financial_data:
            return f"{matched_name}의 {bsns_year}년 {report_name} {fs_div_name} 정보가 없습니다."
        
        # 결과 문자열 초기화
        result = f"# {matched_name}의 {bsns_year}년 {report_name} {fs_div_name} 정보 (당기 데이터만 표시)\n\n"
        
        # 재무제표 유형별 데이터 분류
        statement_data = {}
        for item in financial_data:
            sj_div = item.get('sj_div', '')
            if sj_div not in statement_data:
                statement_data[sj_div] = []
            statement_data[sj_div].append(item)
        
        # 각 재무제표 유형 처리
        if statement_type is None:
            # 모든 재무제표 유형 처리
            for sj_div, data in statement_data.items():
                if not data:
                    continue
                
                statement_name = get_statement_name(sj_div)
                result += f"## {statement_name}\n\n"
                
                # 테이블 형식으로 데이터 출력 (당기 데이터만)
                result += f"| 계정명 | 당기 ({data[0].get('thstrm_nm', '당기')}) |\n"
                result += "|---|---|\n"
                
                # 데이터 행 추가 (당기 데이터만)
                for item in data:
                    account_nm = item.get('account_nm', '')
                    thstrm_amount = item.get('thstrm_amount', '')
                    
                    # 3분기나 1분기, 반기 보고서이면서 손익계산서인 경우 당기 누적금액도 고려
                    if reprt_code in ["11012", "11013", "11014"] and sj_div in ["IS", "CIS"]:
                        thstrm_amount = item.get('thstrm_add_amount', thstrm_amount) or thstrm_amount
                    
                    result += f"| {account_nm} | {thstrm_amount} |\n"
                
                result += "\n"
        else:
            # 특정 재무제표 유형만 처리
            data = statement_data.get(statement_type, [])
            if not data:
                result += f"선택한 재무제표 유형({get_statement_name(statement_type)})의 데이터가 없습니다.\n\n"
            else:
                statement_name = get_statement_name(statement_type)
                result += f"## {statement_name}\n\n"
                
                # 테이블 형식으로 데이터 출력 (당기 데이터만)
                result += f"| 계정명 | 당기 ({data[0].get('thstrm_nm', '당기')}) |\n"
                result += "|---|---|\n"
                
                # 데이터 행 추가 (당기 데이터만)
                for item in data:
                    account_nm = item.get('account_nm', '')
                    thstrm_amount = item.get('thstrm_amount', '')
                    
                    # 3분기나 1분기, 반기 보고서이면서 손익계산서인 경우 당기 누적금액도 고려
                    if reprt_code in ["11012", "11013", "11014"] and statement_type in ["IS", "CIS"]:
                        thstrm_amount = item.get('thstrm_add_amount', thstrm_amount) or thstrm_amount
                    
                    result += f"| {account_nm} | {thstrm_amount} |\n"
        
        # 최종 결과 메시지 추가
        result += "\n## 참고사항\n"
        result += "- 금액 단위: 원\n"
        result += f"- 데이터 출처: DART 오픈API - 단일회사 전체 재무제표\n"
        result += f"- 회사명: {matched_name} (고유번호: {corp_code})\n"
        result += f"- 사업연도: {bsns_year}년\n"
        result += f"- 보고서: {report_name}\n"
        result += f"- 재무제표 구분: {fs_div_name}\n"
        result += "- 표시 정보: 당기 데이터만 표시됨 (전기/전전기 데이터는 제외됨)\n"
        
    except Exception as e:
        return f"재무 정보 검색 중 예상치 못한 오류가 발생했습니다: {str(e)}\n\n{traceback.format_exc()}"
    
    result += chat_guideline
    return result.strip()


# 서버 실행 코드
if __name__ == "__main__":
    mcp.run(transport='stdio')
