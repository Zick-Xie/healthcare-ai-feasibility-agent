import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


DEFAULT_MODEL = "gpt-5.4-mini"
MAX_RETRIES = 2

T = TypeVar("T")


class ResearchAgentError(RuntimeError):
    """Research Agent 執行失敗時使用的自訂錯誤。"""


class MarketMaturity(BaseModel):
    product_maturity: int = Field(ge=1, le=5)
    product_maturity_reason: str

    clinical_evidence: int = Field(ge=1, le=5)
    clinical_evidence_reason: str

    regulatory_maturity: int = Field(ge=1, le=5)
    regulatory_maturity_reason: str

    hospital_adoption: int = Field(ge=1, le=5)
    hospital_adoption_reason: str

    business_model_maturity: int = Field(ge=1, le=5)
    business_model_maturity_reason: str

    overall_score: float = Field(ge=1, le=5)
    maturity_stage: str
    overall_reason: str


class CompanyProduct(BaseModel):
    company: str
    product: str
    country_or_region: str
    use_case: str

    regulatory_status: str
    clinical_evidence: str
    hospital_adoption: str
    business_model: str

    strengths: List[str]
    limitations: List[str]
    source_urls: List[str]


class ResearchFinding(BaseModel):
    finding: str
    confidence: str
    source_urls: List[str]


class StructuredResearchResult(BaseModel):
    research_topic: str
    research_date_context: str
    executive_summary: str

    market_maturity: MarketMaturity
    representative_products: List[CompanyProduct]

    clinical_evidence_findings: List[ResearchFinding]
    regulatory_findings: List[ResearchFinding]
    hospital_adoption_findings: List[ResearchFinding]
    business_model_findings: List[ResearchFinding]
    integration_findings: List[ResearchFinding]

    missing_information: List[str]
    cautions: List[str]


def run_with_retry(
    operation: Callable[[], T],
    operation_name: str,
) -> T:
    """
    簡易重試機制。

    網路暫時中斷、API 忙碌或限流時，最多嘗試兩次。
    """

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return operation()

        except Exception as error:
            last_error = error

            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)

    raise ResearchAgentError(
        f"{operation_name}失敗：{last_error}"
    )


def collect_sources(response: Any) -> List[Dict[str, str]]:
    """
    從 Responses API 回傳物件中收集來源 URL。

    同時檢查：
    1. web_search_call.action.sources
    2. 回答文字中的 url_citation annotations
    """

    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    else:
        payload = response

    collected: Dict[str, Dict[str, str]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            url = value.get("url")

            if isinstance(url, str) and url.startswith("http"):
                title = value.get("title")

                if not isinstance(title, str) or not title.strip():
                    title = url

                collected[url] = {
                    "title": title.strip(),
                    "url": url,
                }

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)

    return list(collected.values())


def build_research_prompt(
    case_description: str,
    target_region: str,
) -> str:
    return f"""
你是一個醫療 AI 市場研究與商業可行性 Research Agent。

請針對以下醫療 AI 應用進行網路研究：

【研究主題】
{case_description}

【主要市場範圍】
{target_region}

你需要主動規劃並完成下列研究：

1. 市場目前處於概念驗證、早期商用、規模化，
   還是成熟市場。
2. 尋找 3 至 5 家具有代表性的公司與產品。
3. 查證產品用途、主要客戶、醫院採用案例。
4. 查證 FDA、TFDA、CE／MDR 或其他法規狀態。
5. 尋找臨床研究、真實世界證據或公開驗證結果。
6. 研究商業模式，例如年度授權、按次計費、
   SaaS、設備綁定或共同開發。
7. 研究 HIS、PACS、RIS、EMR、HL7、FHIR、
   DICOM 等整合需求。
8. 指出公開資料中仍然缺少哪些資訊。

來源優先順序：

1. 政府與監管機構
2. 同行評審論文、PubMed 或正式臨床研究
3. 醫院或醫療機構官方公告
4. 公司官方產品資料
5. 可信產業媒體或研究機構

研究規則：

- 每個可查證的重要結論都必須附來源。
- 優先使用近年的資料，但不得忽略重要的歷史核准。
- 必須寫清楚資料日期。
- 不得猜測未公開價格。
- 查不到時直接寫「未找到可靠公開資料」。
- 公司宣稱與獨立臨床證據必須分開。
- 不得把 FDA 核准錯寫成臨床效果保證。
- 不得把 CE 標誌直接視為所有市場皆可銷售。
- 不得提供疾病診斷或治療建議。

請以繁體中文輸出研究筆記，內容至少包含：

# 研究摘要
# 市場成熟度
# 代表公司與產品
# 臨床證據
# 法規與認證
# 醫院採用情況
# 商業模式
# 系統整合需求
# 資料缺口
# 主要來源
"""


def perform_web_research(
    client: OpenAI,
    model_name: str,
    case_description: str,
    target_region: str,
) -> tuple[str, List[Dict[str, str]]]:
    """
    第一階段：使用 Web Search 取得研究內容與來源。
    """

    prompt = build_research_prompt(
        case_description=case_description,
        target_region=target_region,
    )

    def call_api() -> Any:
        return client.responses.create(
            model=model_name,
            reasoning={"effort": "medium"},
            tools=[
                {
                    "type": "web_search",
                    "search_context_size": "medium",
                    "filters": {
                        "blocked_domains": [
                            "reddit.com",
                            "quora.com",
                            "wikipedia.org",
                        ]
                    },
                }
            ],
            tool_choice="auto",
            include=[
                "web_search_call.action.sources"
            ],
            instructions=(
                "你是一個審慎的醫療 AI 市場研究 Agent。"
                "你必須使用網路搜尋查證資料，"
                "優先使用官方與第一手來源，"
                "並清楚標示未知資訊。"
            ),
            input=prompt,
        )

    response = run_with_retry(
        operation=call_api,
        operation_name="網路研究",
    )

    research_text = response.output_text.strip()

    if not research_text:
        raise ResearchAgentError(
            "網路研究完成，但沒有取得可用文字。"
        )

    sources = collect_sources(response)

    return research_text, sources


def structure_research_result(
    client: OpenAI,
    model_name: str,
    case_description: str,
    target_region: str,
    research_text: str,
    sources: List[Dict[str, str]],
) -> StructuredResearchResult:
    """
    第二階段：將網路研究筆記轉換成固定資料格式。
    """

    source_catalog = json.dumps(
        sources,
        ensure_ascii=False,
        indent=2,
    )

    extraction_prompt = f"""
請將以下醫療 AI 網路研究內容整理成指定的結構化格式。

【原始研究主題】
{case_description}

【研究市場】
{target_region}

【網路研究筆記】
{research_text}

【實際取得的來源清單】
{source_catalog}

整理規則：

1. 不得新增研究筆記中不存在的事實。
2. 不得捏造公司、產品、法規核准、價格或客戶。
3. source_urls 只能使用上方來源清單中實際存在的 URL。
4. 無可靠資訊時寫「未找到可靠公開資料」。
5. 市場成熟度每項使用 1 至 5 分。
6. overall_score 請根據五項成熟度的平均值計算。
7. confidence 只能使用：
   - 高
   - 中
   - 低
8. 代表公司最多五家。
9. 公司官方宣稱不能當成獨立臨床證據。
10. 以繁體中文輸出。
"""

    def call_api() -> Any:
        return client.responses.parse(
            model=model_name,
            reasoning={"effort": "low"},
            instructions=(
                "你負責把已完成的醫療 AI 研究筆記轉成"
                "嚴格的結構化資料。不可自行搜尋或補寫事實。"
            ),
            input=extraction_prompt,
            text_format=StructuredResearchResult,
        )

    response = run_with_retry(
        operation=call_api,
        operation_name="研究結果結構化",
    )

    parsed_result = response.output_parsed

    if parsed_result is None:
        raise ResearchAgentError(
            "研究結果無法轉換成結構化資料。"
        )

    return parsed_result


def research_medical_ai_case(
    case_description: str,
    target_region: str = "台灣與國際市場",
) -> Dict[str, Any]:
    """
    Research Agent 主流程。

    1. 驗證輸入
    2. 主動搜尋網路
    3. 收集來源
    4. 轉成結構化資料
    5. 回傳完整研究結果
    """

    clean_description = case_description.strip()

    if len(clean_description) < 10:
        raise ValueError(
            "研究主題過短，請提供至少 10 個字的應用描述。"
        )

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ResearchAgentError(
            "找不到 OPENAI_API_KEY，請檢查 .env。"
        )

    model_name = os.getenv(
        "OPENAI_RESEARCH_MODEL",
        DEFAULT_MODEL,
    )

    client = OpenAI(api_key=api_key)

    research_text, sources = perform_web_research(
        client=client,
        model_name=model_name,
        case_description=clean_description,
        target_region=target_region,
    )

    structured_result = structure_research_result(
        client=client,
        model_name=model_name,
        case_description=clean_description,
        target_region=target_region,
        research_text=research_text,
        sources=sources,
    )

    return {
        "status": "success",
        "model": model_name,
        "case_description": clean_description,
        "target_region": target_region,
        "raw_research": research_text,
        "sources": sources,
        "structured_result": structured_result.model_dump(
            mode="json"
        ),
    }
