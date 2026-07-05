import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Type

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, Field, ValidationError


DEFAULT_MODEL = "gpt-4.1-mini"
CACHE_VERSION = "taiwan-first-v6-no-web-filters"
CACHE_DIR = Path(".cache/taiwan_research")
CACHE_VALID_DAYS = 14
REQUEST_TIMEOUT_SECONDS = 120.0
STRUCTURE_RETRY_DELAY_SECONDS = 2.0


class ResearchAgentError(RuntimeError):
    """台灣醫療 AI Research Agent 無法完成工作時使用的錯誤。"""


class EvidenceFinding(BaseModel):
    claim: str
    evidence_type: str
    confidence: Literal["高", "中", "低"]
    source_urls: List[str] = Field(default_factory=list)


class RegulatoryProduct(BaseModel):
    company: str
    product: str
    permit_or_listing: str
    intended_use: str
    source_urls: List[str] = Field(default_factory=list)


class RegulatoryResearch(BaseModel):
    executive_summary: str
    medical_device_likelihood: Literal["高", "中", "低", "無法判斷"]
    classification_reason: str
    tfda_status_summary: str
    identified_tfda_products: List[RegulatoryProduct] = Field(default_factory=list)
    regulatory_score: int = Field(ge=1, le=5)
    score_reason: str
    key_findings: List[EvidenceFinding] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


class HospitalAdoptionResearch(BaseModel):
    executive_summary: str
    hospital_adoption_score: int = Field(ge=1, le=5)
    score_reason: str
    chang_gung_findings: List[EvidenceFinding] = Field(default_factory=list)
    other_taiwan_hospital_findings: List[EvidenceFinding] = Field(default_factory=list)
    procurement_or_pilot_findings: List[EvidenceFinding] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


class ClinicalStudy(BaseModel):
    title: str
    institution_or_authors: str
    study_type: str
    population_or_dataset: str
    main_result: str
    limitation: str
    source_urls: List[str] = Field(default_factory=list)


class ClinicalEvidenceResearch(BaseModel):
    executive_summary: str
    clinical_evidence_score: int = Field(ge=1, le=5)
    score_reason: str
    taiwan_validation_status: str
    studies: List[ClinicalStudy] = Field(default_factory=list)
    key_findings: List[EvidenceFinding] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


class TaiwanProduct(BaseModel):
    company: str
    product: str
    company_origin: str
    use_case: str
    taiwan_availability: str
    tfda_status: str
    business_model: str
    public_pricing_status: str
    strengths: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


class ProductMarketResearch(BaseModel):
    executive_summary: str
    product_availability_score: int = Field(ge=1, le=5)
    product_score_reason: str
    business_model_score: int = Field(ge=1, le=5)
    business_score_reason: str
    representative_products: List[TaiwanProduct] = Field(default_factory=list)
    integration_requirements: List[str] = Field(default_factory=list)
    key_findings: List[EvidenceFinding] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class TaskConfig:
    task_id: str
    label: str
    schema: Type[BaseModel]
    research_output_tokens: int
    structure_output_tokens: int
    allowed_domains: Optional[List[str]]


TASK_CONFIGS = [
    TaskConfig(
        task_id="regulatory",
        label="TFDA 與台灣法規研究",
        schema=RegulatoryResearch,
        research_output_tokens=2200,
        structure_output_tokens=2600,
        allowed_domains=[
            "gov.tw",
            "fda.gov.tw",
            "mohw.gov.tw",
            "law.moj.gov.tw",
            "data.gov.tw",
        ],
    ),
    TaskConfig(
        task_id="adoption",
        label="台灣醫院採用與長庚公開案例研究",
        schema=HospitalAdoptionResearch,
        research_output_tokens=2400,
        structure_output_tokens=3000,
        allowed_domains=[
            "cgmh.org.tw",
            "ntuh.gov.tw",
            "vghtpe.gov.tw",
            "kmuh.org.tw",
            "cch.org.tw",
            "tpech.gov.taipei",
            "mohw.gov.tw",
            "pcc.gov.tw",
        ],
    ),
    TaskConfig(
        task_id="clinical",
        label="台灣臨床證據研究",
        schema=ClinicalEvidenceResearch,
        research_output_tokens=2600,
        structure_output_tokens=3200,
        allowed_domains=[
            "pubmed.ncbi.nlm.nih.gov",
            "ncbi.nlm.nih.gov",
            "clinicaltrials.gov",
            "airitilibrary.com",
            "cgmh.org.tw",
            "ntu.edu.tw",
            "nycu.edu.tw",
            "tmu.edu.tw",
        ],
    ),
    TaskConfig(
        task_id="market",
        label="台灣可取得產品與商業模式研究",
        schema=ProductMarketResearch,
        research_output_tokens=2600,
        structure_output_tokens=3200,
        allowed_domains=None,
    ),
]

TASK_CONFIG_BY_ID = {task.task_id: task for task in TASK_CONFIGS}
TASK_ORDER = [task.task_id for task in TASK_CONFIGS]

TAIWAN_SCORE_WEIGHTS = {
    "regulatory": 25,
    "hospital_adoption": 25,
    "clinical_evidence": 20,
    "product_availability": 15,
    "business_model": 15,
}


def notify(
    callback: Optional[Callable[[str], None]],
    message: str,
) -> None:
    if callback is not None:
        callback(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_cache_key(
    case_description: str,
    task_id: str,
    model_name: str,
) -> str:
    raw_key = "|".join(
        [
            CACHE_VERSION,
            case_description.strip(),
            task_id,
            model_name,
        ]
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]


def get_cache_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"


def get_notes_cache_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.notes.json"


def load_notes_cache(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload.get("raw_research"), str):
            return None
        if not isinstance(payload.get("sources"), list):
            return None
        return payload
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_notes_cache(
    cache_path: Path,
    raw_research: str,
    sources: List[Dict[str, str]],
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "raw_research": raw_research,
                "sources": sources,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def load_cache(
    cache_path: Path,
    allow_expired: bool = False,
) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(payload["generated_at"])

        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - generated_at

        if not allow_expired and age > timedelta(days=CACHE_VALID_DAYS):
            return None

        return payload
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_cache(cache_path: Path, payload: Dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def collect_sources(response: Any) -> List[Dict[str, str]]:
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    else:
        payload = response

    collected: Dict[str, Dict[str, str]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            url = value.get("url")
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                title = value.get("title")
                if not isinstance(title, str) or not title.strip():
                    title = url
                collected[url] = {"title": title.strip(), "url": url}

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return list(collected.values())


def clean_source_urls(
    model: BaseModel,
    sources: List[Dict[str, str]],
) -> BaseModel:
    valid_urls = {
        source["url"]
        for source in sources
        if isinstance(source.get("url"), str)
    }
    payload = model.model_dump(mode="json")

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: Dict[str, Any] = {}
            for key, child in value.items():
                if key == "source_urls" and isinstance(child, list):
                    cleaned[key] = [url for url in child if url in valid_urls]
                else:
                    cleaned[key] = clean(child)
            return cleaned

        if isinstance(value, list):
            return [clean(item) for item in value]

        return value

    return type(model).model_validate(clean(payload))


def build_web_search_tool(
    allowed_domains: Optional[List[str]],
) -> Dict[str, Any]:
    """
    建立可由 gpt-4.1-mini 使用的 Web Search 工具設定。

    某些模型雖支援 Responses API 的 web_search，卻不接受
    tools[].filters。為避免 400 BadRequest，這裡不傳 filters；
    來源優先順序與建議網域改由研究 Prompt 明確指定。
    allowed_domains 仍保留作為 Prompt 提示資料。
    """

    return {
        "type": "web_search",
        "search_context_size": "low",
        "user_location": {
            "type": "approximate",
            "country": "TW",
            "city": "Taoyuan",
            "region": "Taiwan",
            "timezone": "Asia/Taipei",
        },
    }


def build_task_prompt(
    task_id: str,
    case_description: str,
) -> str:
    today = datetime.now(timezone.utc).date().isoformat()

    common_rules = f"""
今天日期：{today}

研究對象：台灣市場，最終使用情境是協助林口長庚醫院進行醫療 AI 商業與導入決策。

研究主題：
{case_description}

共同規則：
- 只用台灣證據判斷台灣市場成熟度。
- 國際資料不得代替台灣法規、台灣醫院採用或台灣臨床證據。
- 若沒有可靠公開資料，必須明確寫「未找到可靠公開資料」。
- 搜尋成功但查無資料，可以給低成熟度分數；技術失敗不得假裝成查無資料。
- 公司新聞稿與獨立研究必須分開。
- 不得猜測售價、採購金額、醫院客戶或法規許可。
- 每個重要結論應附本次搜尋取得的來源 URL。
- 回答使用繁體中文，句子精簡。
"""

    task_prompts = {
        "regulatory": """
任務：TFDA 與台灣法規研究。

請研究：
1. 此用途在台灣是否可能屬醫療器材軟體或醫療器材。
2. TFDA 公開資料中是否找到同類或相關產品許可／登錄資訊。
3. 可能涉及的法規、責任、資安或持續監測要求。
4. 尚缺哪些產品級資訊才能正式判斷。

評分 regulatory_score：1 至 5。
最多列出 3 項 key_findings、2 個相關產品、4 項資料缺口。
每個說明盡量控制在 80 個中文字內。
""",
        "adoption": """
任務：台灣醫院採用與長庚公開案例研究。

請研究：
1. 長庚醫療體系，尤其林口長庚，是否有相關公開研究、合作、試點、採購或導入案例。
2. 其他台灣醫學中心或醫院是否有公開採用案例。
3. 區分研究合作、概念驗證、試點、正式上線與正式採購。
4. 是否公開 KPI、使用量、臨床流程或投資效益。

評分 hospital_adoption_score：1 至 5。
最多列出 3 項長庚發現、4 項其他醫院發現、3 項採購／試點發現。
每個說明盡量控制在 80 個中文字內。
""",
        "clinical": """
任務：台灣臨床證據研究。

請研究：
1. 是否有台灣醫院、台灣研究團隊或台灣病人／資料集的驗證。
2. 研究類型是回溯性、前瞻性、外部驗證、多中心或真實世界研究中的哪一類。
3. 主要結果、限制，以及能否支持醫院實際導入。
4. 不得把公司效能宣稱視為獨立臨床證據。

評分 clinical_evidence_score：1 至 5。
最多整理 3 篇研究、3 項關鍵發現、4 項資料缺口。
每個說明盡量控制在 80 個中文字內。
""",
        "market": """
任務：台灣可取得產品、廠商、商業模式與整合需求研究。

請研究：
1. 最多 3 個在台灣有公開可取得、代理、合作、許可或導入線索的產品。
2. 清楚說明台灣可取得性與 TFDA 狀態；無法確認就寫未知。
3. 公開商業模式，例如年度授權、按量、SaaS、設備綁定或共同開發。
4. 未公開價格不得估算。
5. 林口長庚可能涉及的 HIS、PACS、RIS、EMR、DICOM、HL7、FHIR、身分驗證、稽核與資安需求。

分別評分：
- product_availability_score：1 至 5
- business_model_score：1 至 5

每項優勢與限制最多 2 點；整合需求最多 5 項；資料缺口最多 4 項。
每個說明盡量控制在 80 個中文字內。
""",
    }

    task = TASK_CONFIG_BY_ID[task_id]
    domain_guidance = ""

    if task.allowed_domains:
        domain_guidance = (
            "\n建議優先查詢的台灣或正式網域：\n- "
            + "\n- ".join(task.allowed_domains)
            + "\n若其他第一手來源更直接，也可以使用，但必須保留來源 URL。\n"
        )

    return common_rules + domain_guidance + task_prompts[task_id]


def perform_web_research(
    client: OpenAI,
    task: TaskConfig,
    case_description: str,
    model_name: str,
    progress_callback: Optional[Callable[[str], None]],
) -> tuple[str, List[Dict[str, str]]]:
    """
    第一階段只做網路研究，回傳精簡研究筆記與實際來源。

    不在含 Web Search 的同一個請求中強迫模型輸出大型 Pydantic
    結構，避免搜尋內容尚未整理完成時觸發結構化解析失敗。
    """

    prompt = build_task_prompt(task.task_id, case_description)
    tool = build_web_search_tool(task.allowed_domains)

    notify(
        progress_callback,
        f"正在搜尋：{task.label}。本階段只蒐集台灣證據……",
    )

    response = client.responses.create(
        model=model_name,
        max_output_tokens=task.research_output_tokens,
        tools=[tool],
        tool_choice="required",
        include=["web_search_call.action.sources"],
        store=True,
        instructions=(
            "你是台灣醫療 AI 研究員。請先搜尋，再產生精簡、可供後續"
            "結構化整理的研究筆記。不得捏造資料。每項重要結論附 URL。"
            "此階段不要輸出 JSON，也不要嘗試符合 Pydantic 格式。"
        ),
        input=prompt,
    )

    sources = collect_sources(response)
    research_text = (response.output_text or "").strip()

    if not research_text:
        status = getattr(response, "status", None)
        incomplete_details = getattr(response, "incomplete_details", None)
        incomplete_reason = getattr(incomplete_details, "reason", None)

        notify(
            progress_callback,
            (
                f"{task.label}已完成搜尋，但尚未產生文字摘要；"
                "正在沿用同一搜尋結果補寫研究筆記……"
            ),
        )

        response_id = getattr(response, "id", None)
        if response_id:
            followup = client.responses.create(
                model=model_name,
                previous_response_id=response_id,
                max_output_tokens=max(task.research_output_tokens, 2200),
                store=True,
                instructions=(
                    "根據上一個回合已完成的網路搜尋結果，立即輸出繁體中文"
                    "研究筆記。不要再次搜尋，不要輸出 JSON。每項重要結論附"
                    "上一回合已取得的來源 URL；查無資料時明確寫出。"
                ),
                input=(
                    "請現在整理並輸出可供後續結構化處理的研究筆記，"
                    "包含結論、證據、限制與資料缺口。"
                ),
            )
            research_text = (followup.output_text or "").strip()
            followup_sources = collect_sources(followup)
            if followup_sources:
                source_map = {item["url"]: item for item in sources}
                for item in followup_sources:
                    source_map[item["url"]] = item
                sources = list(source_map.values())

        if not research_text:
            detail = (
                f"status={status or 'unknown'}, "
                f"incomplete_reason={incomplete_reason or 'none'}, "
                f"sources={len(sources)}"
            )
            raise ResearchAgentError(
                f"{task.label}已執行搜尋，但沒有產生可用研究筆記。{detail}"
            )

    return research_text, sources


def structure_research_notes(
    client: OpenAI,
    task: TaskConfig,
    case_description: str,
    research_text: str,
    sources: List[Dict[str, str]],
    model_name: str,
    progress_callback: Optional[Callable[[str], None]],
) -> BaseModel:
    """
    第二階段不再搜尋網路，只把已取得的研究筆記轉成固定格式。

    將搜尋與結構化拆開後，模型不必同時處理工具呼叫、來源整理與
    大型 JSON Schema，可大幅降低 output_parsed 驗證失敗機率。
    """

    source_catalog = json.dumps(sources, ensure_ascii=False, indent=2)
    extraction_prompt = f"""
研究主題：
{case_description}

已完成的台灣研究筆記：
{research_text}

本次實際取得的來源清單：
{source_catalog}

請把研究筆記整理成指定結構。規則：
- 不得新增筆記中不存在的事實。
- source_urls 只能使用來源清單中實際存在的 URL。
- 沒有可靠資訊時填寫「未找到可靠公開資料」。
- 所有必填欄位都必須完整輸出；沒有項目時使用空陣列。
- 分數只能使用 1 到 5。
- 文字使用繁體中文並保持精簡。
"""

    notify(
        progress_callback,
        f"已完成搜尋，正在整理成可驗證格式：{task.label}……",
    )

    try:
        response = client.responses.parse(
            model=model_name,
            max_output_tokens=task.structure_output_tokens,
            instructions=(
                "你只負責將既有研究筆記轉成指定結構。"
                "不得搜尋、補寫或推測新事實。請完整填滿所有必填欄位。"
            ),
            input=extraction_prompt,
            text_format=task.schema,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ResearchAgentError("結構化整理沒有回傳 output_parsed。")
        return parsed

    except (RateLimitError, APITimeoutError, APIConnectionError):
        raise

    except Exception as first_error:
        notify(
            progress_callback,
            "第一次格式整理未完成，正在用更精簡指令重整一次……",
        )
        time.sleep(STRUCTURE_RETRY_DELAY_SECONDS)

        retry_prompt = f"""
請將下列研究筆記轉成指定結構。不要解釋，不要加前言。
沒有資料的清單一律輸出空陣列；沒有可靠資訊的字串填入
「未找到可靠公開資料」。不得使用來源清單以外的 URL。

研究筆記：
{research_text}

允許使用的來源：
{source_catalog}
"""

        response = client.responses.parse(
            model=model_name,
            max_output_tokens=task.structure_output_tokens + 1000,
            instructions=(
                "嚴格依 Pydantic 結構輸出。所有必填欄位都要存在。"
                "只整理提供的文字，不新增任何事實。"
            ),
            input=retry_prompt,
            text_format=task.schema,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ResearchAgentError(
                "第二次格式整理仍未回傳 output_parsed。"
            ) from first_error
        return parsed

def format_unexpected_error(error: Exception) -> tuple[str, str]:
    """將技術錯誤轉成可安全顯示的診斷資訊。"""

    error_type = type(error).__name__
    raw_message = str(error).strip()

    if "LengthFinishReason" in error_type or "length" in raw_message.lower():
        return (
            "output_too_long",
            "模型輸出達到長度上限，尚未完成結構化結果。"
            "新版已提高此任務的輸出上限；請重新執行選定任務。",
        )

    if isinstance(error, ResearchAgentError) and "沒有產生可用研究筆記" in raw_message:
        return (
            "empty_research_output",
            raw_message,
        )

    if "Validation" in error_type:
        return (
            "structured_output_validation",
            "模型回傳內容未完整符合結構化格式。"
            "這是格式解析問題，不代表台灣沒有資料。",
        )

    if "BadRequest" in error_type:
        safe_detail = raw_message[:500] if raw_message else "API 請求格式不被接受。"
        return ("bad_request", safe_detail)

    safe_detail = raw_message[:500] if raw_message else "未取得更詳細的錯誤訊息。"
    return (error_type, safe_detail)

def _has_meaningful_text(value: Any, minimum_length: int = 6) -> bool:
    if not isinstance(value, str):
        return False
    normalized = " ".join(value.split()).strip()
    return len(normalized) >= minimum_length


def validate_structured_result(task: TaskConfig, parsed: BaseModel) -> None:
    """避免空字串通過 Pydantic 後被誤標為研究成功。"""
    data = parsed.model_dump(mode="json")

    required_text_fields: Dict[str, List[str]] = {
        "regulatory": [
            "executive_summary",
            "classification_reason",
            "tfda_status_summary",
            "score_reason",
        ],
        "adoption": ["executive_summary", "score_reason"],
        "clinical": [
            "executive_summary",
            "score_reason",
            "taiwan_validation_status",
        ],
        "market": [
            "executive_summary",
            "product_score_reason",
            "business_score_reason",
        ],
    }

    field_names = required_text_fields.get(task.task_id, ["executive_summary"])
    missing_fields = [
        field_name
        for field_name in field_names
        if not _has_meaningful_text(data.get(field_name))
    ]

    summary = data.get("executive_summary")
    if not _has_meaningful_text(summary, minimum_length=12):
        if "executive_summary" not in missing_fields:
            missing_fields.append("executive_summary")

    if missing_fields:
        raise ResearchAgentError(
            f"{task.label}已完成搜尋，但結構化結果缺少有效內容："
            + "、".join(sorted(set(missing_fields)))
            + "。這是輸出品質問題，不代表台灣沒有資料。"
        )


def is_meaningful_task_payload(task_payload: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(task_payload, dict):
        return False

    result = task_payload.get("result")
    task_id = task_payload.get("task_id")
    if not isinstance(result, dict) or not isinstance(task_id, str):
        return False

    required_text_fields: Dict[str, List[str]] = {
        "regulatory": [
            "executive_summary",
            "classification_reason",
            "tfda_status_summary",
            "score_reason",
        ],
        "adoption": ["executive_summary", "score_reason"],
        "clinical": [
            "executive_summary",
            "score_reason",
            "taiwan_validation_status",
        ],
        "market": [
            "executive_summary",
            "product_score_reason",
            "business_score_reason",
        ],
    }

    fields = required_text_fields.get(task_id, ["executive_summary"])
    return all(_has_meaningful_text(result.get(field)) for field in fields)


def run_single_task(
    task: TaskConfig,
    case_description: str,
    model_name: str,
    force_refresh: bool,
    progress_callback: Optional[Callable[[str], None]],
) -> Dict[str, Any]:
    cache_key = make_cache_key(case_description, task.task_id, model_name)
    cache_path = get_cache_path(cache_key)
    notes_cache_path = get_notes_cache_path(cache_key)

    if not force_refresh:
        fresh_cache = load_cache(cache_path)
        if fresh_cache is not None and is_meaningful_task_payload(fresh_cache):
            fresh_cache["status"] = "cached"
            fresh_cache["cache_hit"] = True
            return fresh_cache

    stale_cache = load_cache(cache_path, allow_expired=True)
    if stale_cache is not None and not is_meaningful_task_payload(stale_cache):
        stale_cache = None

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )

    research_text: Optional[str] = None
    sources: List[Dict[str, str]] = []

    try:
        notes_cache = None if force_refresh else load_notes_cache(notes_cache_path)

        if notes_cache is not None:
            research_text = notes_cache["raw_research"]
            sources = notes_cache["sources"]
            notify(
                progress_callback,
                f"已找到先前完成的搜尋筆記，直接重新整理格式：{task.label}……",
            )
        else:
            research_text, sources = perform_web_research(
                client=client,
                task=task,
                case_description=case_description,
                model_name=model_name,
                progress_callback=progress_callback,
            )
            save_notes_cache(
                cache_path=notes_cache_path,
                raw_research=research_text,
                sources=sources,
            )

        parsed = structure_research_notes(
            client=client,
            task=task,
            case_description=case_description,
            research_text=research_text,
            sources=sources,
            model_name=model_name,
            progress_callback=progress_callback,
        )

        parsed = clean_source_urls(parsed, sources)
        validate_structured_result(task, parsed)

        payload = {
            "task_id": task.task_id,
            "task_label": task.label,
            "status": "success",
            "cache_hit": False,
            "generated_at": now_iso(),
            "sources": sources,
            "raw_research": research_text,
            "result": parsed.model_dump(mode="json"),
            "error_type": None,
            "error_message": None,
        }
        save_cache(cache_path, payload)
        return payload

    except RateLimitError:
        if stale_cache is not None:
            stale_cache["status"] = "stale_cache"
            stale_cache["cache_hit"] = True
            stale_cache["warning"] = "即時研究遇到流量限制，顯示相同台灣任務的舊快取。"
            return stale_cache
        return {
            "task_id": task.task_id,
            "task_label": task.label,
            "status": "technical_failure",
            "cache_hit": False,
            "generated_at": now_iso(),
            "sources": sources,
            "raw_research": research_text,
            "result": None,
            "error_type": "rate_limit",
            "error_message": (
                "API 每分鐘 Token 使用量暫時達到上限。"
                "請等待約 60 秒，再使用『重新執行選定任務』。"
            ),
        }

    except APITimeoutError:
        if stale_cache is not None:
            stale_cache["status"] = "stale_cache"
            stale_cache["cache_hit"] = True
            stale_cache["warning"] = "即時研究逾時，顯示相同台灣任務的舊快取。"
            return stale_cache
        return {
            "task_id": task.task_id,
            "task_label": task.label,
            "status": "technical_failure",
            "cache_hit": False,
            "generated_at": now_iso(),
            "sources": sources,
            "raw_research": research_text,
            "result": None,
            "error_type": "timeout",
            "error_message": "研究請求超過時間限制；其他任務不受影響。",
        }

    except APIConnectionError:
        if stale_cache is not None:
            stale_cache["status"] = "stale_cache"
            stale_cache["cache_hit"] = True
            stale_cache["warning"] = "即時研究連線失敗，顯示相同台灣任務的舊快取。"
            return stale_cache
        return {
            "task_id": task.task_id,
            "task_label": task.label,
            "status": "technical_failure",
            "cache_hit": False,
            "generated_at": now_iso(),
            "sources": sources,
            "raw_research": research_text,
            "result": None,
            "error_type": "connection",
            "error_message": "目前無法連線至研究服務；其他任務不受影響。",
        }

    except Exception as error:
        if stale_cache is not None:
            stale_cache["status"] = "stale_cache"
            stale_cache["cache_hit"] = True
            stale_cache["warning"] = "即時研究未完成，顯示相同台灣任務的舊快取。"
            return stale_cache

        error_type, error_message = format_unexpected_error(error)
        return {
            "task_id": task.task_id,
            "task_label": task.label,
            "status": "technical_failure",
            "cache_hit": False,
            "generated_at": now_iso(),
            "sources": sources,
            "raw_research": research_text,
            "result": None,
            "error_type": error_type,
            "error_message": error_message,
        }

def is_completed_task(task_payload: Optional[Dict[str, Any]]) -> bool:
    return bool(
        task_payload
        and task_payload.get("status") in {"success", "cached", "stale_cache"}
        and is_meaningful_task_payload(task_payload)
    )


def empty_task_payload(task: TaskConfig) -> Dict[str, Any]:
    return {
        "task_id": task.task_id,
        "task_label": task.label,
        "status": "not_started",
        "cache_hit": False,
        "generated_at": None,
        "sources": [],
        "result": None,
        "error_type": None,
        "error_message": "尚未執行。",
    }


def load_task_state(
    case_description: str,
    task: TaskConfig,
    model_name: str,
) -> Dict[str, Any]:
    cache_key = make_cache_key(case_description, task.task_id, model_name)
    cache_path = get_cache_path(cache_key)
    cached = load_cache(cache_path, allow_expired=True)

    if cached is None:
        return empty_task_payload(task)

    if not is_meaningful_task_payload(cached):
        payload = empty_task_payload(task)
        payload["error_message"] = (
            "先前快取被偵測為內容不完整，請重新執行此任務。"
        )
        return payload

    cached["status"] = "cached" if load_cache(cache_path) is not None else "stale_cache"
    cached["cache_hit"] = True
    return cached


def build_taiwan_score(tasks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    dimensions: Dict[str, Dict[str, Any]] = {}

    regulatory = tasks.get("regulatory")
    if is_completed_task(regulatory):
        dimensions["regulatory"] = {
            "label": "TFDA／法規成熟度",
            "score": regulatory["result"]["regulatory_score"],
            "weight": TAIWAN_SCORE_WEIGHTS["regulatory"],
        }

    adoption = tasks.get("adoption")
    if is_completed_task(adoption):
        dimensions["hospital_adoption"] = {
            "label": "台灣醫院採用程度",
            "score": adoption["result"]["hospital_adoption_score"],
            "weight": TAIWAN_SCORE_WEIGHTS["hospital_adoption"],
        }

    clinical = tasks.get("clinical")
    if is_completed_task(clinical):
        dimensions["clinical_evidence"] = {
            "label": "台灣臨床證據",
            "score": clinical["result"]["clinical_evidence_score"],
            "weight": TAIWAN_SCORE_WEIGHTS["clinical_evidence"],
        }

    market = tasks.get("market")
    if is_completed_task(market):
        dimensions["product_availability"] = {
            "label": "台灣可取得產品",
            "score": market["result"]["product_availability_score"],
            "weight": TAIWAN_SCORE_WEIGHTS["product_availability"],
        }
        dimensions["business_model"] = {
            "label": "商業模式與採購透明度",
            "score": market["result"]["business_model_score"],
            "weight": TAIWAN_SCORE_WEIGHTS["business_model"],
        }

    coverage = sum(item["weight"] for item in dimensions.values())
    weighted_points = sum(
        item["score"] * item["weight"]
        for item in dimensions.values()
    )

    partial_score = round(weighted_points / coverage, 2) if coverage > 0 else None
    overall_score = partial_score if coverage == 100 else None

    if overall_score is None:
        maturity_stage = "資料尚未完整，暫不產生正式成熟度"
    elif overall_score < 1.8:
        maturity_stage = "台灣概念／探索階段"
    elif overall_score < 2.8:
        maturity_stage = "台灣早期導入階段"
    elif overall_score < 3.8:
        maturity_stage = "台灣早期規模化階段"
    elif overall_score < 4.5:
        maturity_stage = "台灣規模化市場"
    else:
        maturity_stage = "台灣成熟市場"

    return {
        "coverage_percent": coverage,
        "overall_score": overall_score,
        "partial_score": partial_score,
        "maturity_stage": maturity_stage,
        "dimensions": dimensions,
        "is_complete": coverage == 100,
    }


def collect_missing_information(tasks: Dict[str, Dict[str, Any]]) -> List[str]:
    collected: List[str] = []
    seen = set()

    for task in tasks.values():
        if not is_completed_task(task):
            continue
        for item in task["result"].get("missing_information", []):
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                collected.append(text)

    return collected[:15]


def collect_all_sources(tasks: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    sources: Dict[str, Dict[str, str]] = {}

    for task in tasks.values():
        for source in task.get("sources", []):
            url = source.get("url")
            if isinstance(url, str) and url:
                sources[url] = {
                    "title": source.get("title", url),
                    "url": url,
                    "task_label": task.get("task_label", ""),
                }

    return list(sources.values())


def build_linkou_chang_gung_assessment(
    tasks: Dict[str, Dict[str, Any]],
    score_summary: Dict[str, Any],
) -> Dict[str, Any]:
    adoption = tasks.get("adoption")
    chang_gung_findings: List[Dict[str, Any]] = []

    if is_completed_task(adoption):
        chang_gung_findings = adoption["result"].get("chang_gung_findings", [])

    technical_failures = [
        task["task_label"]
        for task in tasks.values()
        if task.get("status") == "technical_failure"
    ]

    not_started = [
        task["task_label"]
        for task in tasks.values()
        if task.get("status") == "not_started"
    ]

    internal_data_needed = [
        "林口長庚目前案件量、處理時間、人力成本與現況 KPI",
        "院內 HIS／PACS／RIS／EMR 介面、資料流與資安限制",
        "候選產品正式報價、授權範圍、維護費與退出條款",
        "臨床負責人、資訊單位、法遵與採購單位的責任分工",
        "試點成功標準、人工覆核流程與異常事件處理機制",
    ]

    if technical_failures:
        next_step = "先重新執行技術性未完成任務，再進入正式商業決策。"
    elif not_started:
        next_step = "繼續逐項完成台灣研究任務；目前尚不能形成正式市場成熟度。"
    elif not score_summary["is_complete"]:
        next_step = "目前台灣證據覆蓋仍不完整，先補齊公開證據與院內資料。"
    else:
        reg_score = score_summary["dimensions"]["regulatory"]["score"]
        adoption_score = score_summary["dimensions"]["hospital_adoption"]["score"]
        overall = score_summary["overall_score"] or 0

        if reg_score <= 2:
            next_step = "先進行 TFDA 路徑與候選產品許可盤點，不宜直接採購。"
        elif adoption_score <= 2:
            next_step = "建議先做小規模 POC 與流程驗證，補足台灣醫院採用證據。"
        elif overall >= 3.5:
            next_step = "可進入跨部門受控試點設計，但仍需院內成本與整合資料驗證。"
        else:
            next_step = "建議補充供應商、法規及院內流程資料後再決定是否試點。"

    return {
        "public_chang_gung_evidence": chang_gung_findings,
        "technical_failures": technical_failures,
        "not_started_tasks": not_started,
        "internal_data_needed": internal_data_needed,
        "recommended_next_step": next_step,
        "important_note": (
            "公開資料只能支持市場與外部證據初評；"
            "林口長庚的正式投資決策仍須使用院內營運、成本、資訊架構與治理資料。"
        ),
    }


def build_research_snapshot(
    case_description: str,
    model_name: str,
    tasks: Optional[Dict[str, Dict[str, Any]]] = None,
    target_region: str = "台灣市場（林口長庚決策）",
) -> Dict[str, Any]:
    if tasks is None:
        tasks = {
            task.task_id: load_task_state(case_description, task, model_name)
            for task in TASK_CONFIGS
        }

    score_summary = build_taiwan_score(tasks)
    missing_information = collect_missing_information(tasks)
    all_sources = collect_all_sources(tasks)
    linkou_assessment = build_linkou_chang_gung_assessment(
        tasks=tasks,
        score_summary=score_summary,
    )

    completed_count = sum(is_completed_task(task) for task in tasks.values())
    failed_count = sum(
        task.get("status") == "technical_failure"
        for task in tasks.values()
    )

    if completed_count == len(TASK_CONFIGS):
        status = "success"
    elif completed_count > 0:
        status = "partial_success"
    elif failed_count > 0:
        status = "technical_failure"
    else:
        status = "not_started"

    next_task_id = next(
        (
            task_id
            for task_id in TASK_ORDER
            if not is_completed_task(tasks.get(task_id))
        ),
        None,
    )

    return {
        "status": status,
        "generated_at": now_iso(),
        "model": model_name,
        "case_description": case_description,
        "target_region": target_region,
        "tasks": tasks,
        "next_task_id": next_task_id,
        "next_task_label": (
            TASK_CONFIG_BY_ID[next_task_id].label
            if next_task_id is not None
            else None
        ),
        "taiwan_market_maturity": score_summary,
        "linkou_chang_gung_assessment": linkou_assessment,
        "missing_information": missing_information,
        "sources": all_sources,
    }


def load_research_snapshot(
    case_description: str,
    target_region: str = "台灣市場（林口長庚決策）",
) -> Dict[str, Any]:
    clean_description = case_description.strip()
    if len(clean_description) < 10:
        raise ValueError("研究主題過短，請至少輸入 10 個字。")

    load_dotenv()
    model_name = os.getenv("OPENAI_RESEARCH_MODEL", DEFAULT_MODEL)
    return build_research_snapshot(
        case_description=clean_description,
        model_name=model_name,
        target_region=target_region,
    )


def run_research_task(
    case_description: str,
    task_id: str,
    force_refresh: bool = False,
    progress_callback: Optional[Callable[[str], None]] = None,
    target_region: str = "台灣市場（林口長庚決策）",
) -> Dict[str, Any]:
    clean_description = case_description.strip()

    if len(clean_description) < 10:
        raise ValueError("研究主題過短，請至少輸入 10 個字。")

    if task_id not in TASK_CONFIG_BY_ID:
        raise ValueError(f"未知研究任務：{task_id}")

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ResearchAgentError("找不到 OPENAI_API_KEY，請檢查 .env。")

    model_name = os.getenv("OPENAI_RESEARCH_MODEL", DEFAULT_MODEL)
    task = TASK_CONFIG_BY_ID[task_id]

    notify(progress_callback, f"本次只執行：{task.label}……")

    task_payload = run_single_task(
        task=task,
        case_description=clean_description,
        model_name=model_name,
        force_refresh=force_refresh,
        progress_callback=progress_callback,
    )

    tasks = {
        config.task_id: load_task_state(clean_description, config, model_name)
        for config in TASK_CONFIGS
    }
    tasks[task_id] = task_payload

    notify(progress_callback, f"{task.label}已完成本次執行，正在更新整體進度……")

    return build_research_snapshot(
        case_description=clean_description,
        model_name=model_name,
        tasks=tasks,
        target_region=target_region,
    )


def run_next_incomplete_task(
    case_description: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    target_region: str = "台灣市場（林口長庚決策）",
) -> Dict[str, Any]:
    snapshot = load_research_snapshot(
        case_description=case_description,
        target_region=target_region,
    )

    task_id = snapshot.get("next_task_id")
    if task_id is None:
        notify(progress_callback, "四項台灣研究任務均已完成。")
        return snapshot

    return run_research_task(
        case_description=case_description,
        task_id=task_id,
        force_refresh=False,
        progress_callback=progress_callback,
        target_region=target_region,
    )


def research_medical_ai_case(
    case_description: str,
    target_region: str = "台灣市場（林口長庚決策）",
    force_refresh: bool = False,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    保留舊函式名稱，避免其他檔案匯入失敗。

    新版一次只執行一個任務：
    - force_refresh=False：執行下一個未完成任務。
    - force_refresh=True：重新執行目前第一個未完成任務；若全部完成，重新執行 TFDA 任務。
    """

    snapshot = load_research_snapshot(
        case_description=case_description,
        target_region=target_region,
    )

    if force_refresh:
        task_id = snapshot.get("next_task_id") or TASK_ORDER[0]
        return run_research_task(
            case_description=case_description,
            task_id=task_id,
            force_refresh=True,
            progress_callback=progress_callback,
            target_region=target_region,
        )

    return run_next_incomplete_task(
        case_description=case_description,
        progress_callback=progress_callback,
        target_region=target_region,
    )
