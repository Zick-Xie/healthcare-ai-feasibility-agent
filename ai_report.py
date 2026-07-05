from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_REPORT_MODEL = "gpt-4.1-mini"
REPORT_VERSION = "linkou-integrated-report-v2"
MAX_REPORT_OUTPUT_TOKENS = 3600
REQUEST_TIMEOUT_SECONDS = 120.0


class ManagementReportError(RuntimeError):
    """完整管理層報告無法建立時使用的錯誤。"""


def _format_currency(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"NT$ {value:,.0f}"
    return "無法計算"


def _format_percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1f}%"
    return "無法計算"


def _format_months(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1f} 個月"
    return "無法計算"


def _safe_text(value: Any, fallback: str = "未提供") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _dedupe_text(items: List[Any], limit: Optional[int] = None) -> List[str]:
    output: List[str] = []
    seen = set()

    for item in items:
        text = _safe_text(item, "")
        if text and text not in seen:
            seen.add(text)
            output.append(text)

        if limit is not None and len(output) >= limit:
            break

    return output


def _completed_task_result(
    research_result: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    task = research_result.get("tasks", {}).get(task_id, {})
    result = task.get("result")
    return result if isinstance(result, dict) else {}


def _compact_findings(findings: Any, limit: int = 4) -> List[Dict[str, str]]:
    if not isinstance(findings, list):
        return []

    compact: List[Dict[str, str]] = []

    for finding in findings[:limit]:
        if not isinstance(finding, dict):
            continue

        compact.append(
            {
                "claim": _safe_text(finding.get("claim")),
                "evidence_type": _safe_text(finding.get("evidence_type")),
                "confidence": _safe_text(finding.get("confidence")),
            }
        )

    return compact


def _compact_research_result(
    research_result: Dict[str, Any],
) -> Dict[str, Any]:
    maturity = research_result.get("taiwan_market_maturity", {})
    regulatory = _completed_task_result(research_result, "regulatory")
    adoption = _completed_task_result(research_result, "adoption")
    clinical = _completed_task_result(research_result, "clinical")
    market = _completed_task_result(research_result, "market")

    products: List[Dict[str, str]] = []
    for product in market.get("representative_products", [])[:3]:
        if not isinstance(product, dict):
            continue
        products.append(
            {
                "company": _safe_text(product.get("company")),
                "product": _safe_text(product.get("product")),
                "use_case": _safe_text(product.get("use_case")),
                "taiwan_availability": _safe_text(
                    product.get("taiwan_availability")
                ),
                "tfda_status": _safe_text(product.get("tfda_status")),
                "business_model": _safe_text(product.get("business_model")),
                "public_pricing_status": _safe_text(
                    product.get("public_pricing_status")
                ),
            }
        )

    studies: List[Dict[str, str]] = []
    for study in clinical.get("studies", [])[:3]:
        if not isinstance(study, dict):
            continue
        studies.append(
            {
                "title": _safe_text(study.get("title")),
                "institution_or_authors": _safe_text(
                    study.get("institution_or_authors")
                ),
                "study_type": _safe_text(study.get("study_type")),
                "main_result": _safe_text(study.get("main_result")),
                "limitation": _safe_text(study.get("limitation")),
            }
        )

    return {
        "status": research_result.get("status"),
        "case_description": research_result.get("case_description"),
        "source_count": len(research_result.get("sources", [])),
        "market_maturity": maturity,
        "regulatory": {
            "executive_summary": regulatory.get("executive_summary"),
            "medical_device_likelihood": regulatory.get(
                "medical_device_likelihood"
            ),
            "tfda_status_summary": regulatory.get("tfda_status_summary"),
            "regulatory_score": regulatory.get("regulatory_score"),
            "score_reason": regulatory.get("score_reason"),
            "key_findings": _compact_findings(
                regulatory.get("key_findings", [])
            ),
        },
        "hospital_adoption": {
            "executive_summary": adoption.get("executive_summary"),
            "hospital_adoption_score": adoption.get(
                "hospital_adoption_score"
            ),
            "score_reason": adoption.get("score_reason"),
            "chang_gung_findings": _compact_findings(
                adoption.get("chang_gung_findings", [])
            ),
            "other_taiwan_hospital_findings": _compact_findings(
                adoption.get("other_taiwan_hospital_findings", [])
            ),
        },
        "clinical_evidence": {
            "executive_summary": clinical.get("executive_summary"),
            "clinical_evidence_score": clinical.get(
                "clinical_evidence_score"
            ),
            "score_reason": clinical.get("score_reason"),
            "taiwan_validation_status": clinical.get(
                "taiwan_validation_status"
            ),
            "studies": studies,
        },
        "products_and_business_model": {
            "executive_summary": market.get("executive_summary"),
            "product_availability_score": market.get(
                "product_availability_score"
            ),
            "business_model_score": market.get("business_model_score"),
            "products": products,
            "integration_requirements": market.get(
                "integration_requirements", []
            )[:6],
        },
        "missing_information": research_result.get(
            "missing_information", []
        )[:15],
        "linkou_public_assessment": research_result.get(
            "linkou_chang_gung_assessment", {}
        ),
    }


def _compact_scenarios(
    scenario_results: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    compact: Dict[str, Dict[str, Any]] = {}

    for scenario_name, scenario_payload in scenario_results.items():
        financials = scenario_payload.get("financials", {})
        compact[scenario_name] = {
            "annual_total_benefit": financials.get("annual_total_benefit"),
            "first_year_net_benefit": financials.get(
                "first_year_net_benefit"
            ),
            "three_year_net_benefit": financials.get(
                "three_year_net_benefit"
            ),
            "three_year_roi_percent": financials.get(
                "three_year_roi_percent"
            ),
            "payback_months": financials.get("payback_months"),
        }

    return compact


def _build_ai_payload(
    project_info: Dict[str, Any],
    financials: Dict[str, Any],
    scenario_results: Dict[str, Any],
    scores: Dict[str, int],
    score_reasons: Dict[str, str],
    hard_gate_risks: List[str],
    rule_based_decision: str,
    research_result: Dict[str, Any],
    integrated_decision: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "project_information": project_info,
        "taiwan_research": _compact_research_result(research_result),
        "hospital_feasibility": {
            "score": project_info.get("feasibility_score"),
            "dimension_scores": scores,
            "dimension_reasons": score_reasons,
            "hard_gate_risks": hard_gate_risks,
            "rule_based_decision": rule_based_decision,
        },
        "baseline_financials": financials,
        "scenario_analysis": _compact_scenarios(scenario_results),
        "integrated_decision": integrated_decision,
    }


def _build_fallback_narrative(payload: Dict[str, Any]) -> str:
    integrated = payload.get("integrated_decision", {})
    project = payload.get("project_information", {})
    market = integrated.get("market", {})
    financial = integrated.get("financial", {})
    decision = integrated.get(
        "decision",
        payload.get("hospital_feasibility", {}).get(
            "rule_based_decision",
            "尚未形成正式決策",
        ),
    )

    blockers = integrated.get("blockers", [])
    warnings = integrated.get("warnings", [])
    actions = integrated.get("next_actions", [])

    lines = [
        "# 管理層摘要",
        "",
        (
            f"本報告評估「{_safe_text(project.get('project_name'))}」在"
            "林口長庚的台灣市場成熟度、院內導入可行性及財務韌性。"
        ),
        (
            f"目前整合建議為：**{decision}**。"
            f"台灣市場成熟度為 {_safe_text(market.get('score'))} / 5，"
            f"財務韌性分數為 {_safe_text(financial.get('score'))} / 100。"
        ),
        "此摘要由規則引擎依既有資料產生，未使用 AI 敘事模型。",
        "",
        "# 決策理由",
        "",
    ]

    if blockers:
        lines.append("## 主要決策阻礙")
        lines.extend(f"- {item}" for item in blockers)
        lines.append("")

    if warnings:
        lines.append("## 重要警示")
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")

    lines.append("# 建議下一步")
    lines.append("")
    if actions:
        lines.extend(f"- {item}" for item in actions)
    else:
        lines.append("- 召集臨床、資訊、法遵、採購與財務單位確認試點條件。")

    return "\n".join(lines)


def _build_prompt(payload: Dict[str, Any]) -> str:
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
你是一位協助台灣醫學中心進行醫療 AI 投資審查的資深顧問。

以下資料已由 Taiwan-first Research Agent、Python 財務模型、風險閘門與
整合決策引擎完成。你只負責管理層敘事，不得修改或重新計算任何分數、
ROI、回本期、法規分數、決策或風險。

【結構化資料】
{payload_json}

請以繁體中文產生下列 Markdown 章節：

# 管理層摘要
用 5 至 7 句說明專案、台灣市場證據、院內可行性、財務韌性、重大限制與最終建議。

# 整合決策解讀
解釋台灣市場成熟度、林口長庚院內可行性與財務韌性如何共同形成決策。
不得自行改變整合決策。

# 台灣市場與長庚公開證據解讀
分別說明 TFDA／法規、台灣醫院採用、台灣臨床證據、產品與商業模式。
公開資料沒有支持的內容必須寫「目前無法確認」。

# 財務與情境風險解讀
解釋基準、保守與樂觀情境。不得把樂觀情境當成預測。

# 林口長庚建議試點方案
提出：建議期間、範圍、參與角色、5 項 KPI、成功標準與中止條件。
內容必須符合整合決策；若決策為補件或暫緩，不得建議直接全面導入。

# 正式投資前必要補件
列出最重要的 5 至 8 項院內或供應商資料。

# 結論
重述整合決策，並說明下一個管理層動作。

規則：
- 不得提供疾病診斷或治療建議。
- 不得捏造研究、法規許可、產品價格、醫院案例或院內資料。
- 不得新增未提供的財務數字。
- 明確區分公開外部證據、使用者輸入、系統計算與情境假設。
- 金額使用新台幣。
- 不需要在這些章節中重複列出網址；完整來源會由系統附在報告後方。
- 保持審慎、務實，適合醫院管理層閱讀。
"""


def _build_market_table(research_result: Dict[str, Any]) -> str:
    maturity = research_result.get("taiwan_market_maturity", {})
    dimensions = maturity.get("dimensions", {})

    lines = [
        "# 台灣市場成熟度明細",
        "",
        "| 評估面向 | 分數 | 權重 |",
        "|---|---:|---:|",
    ]

    for dimension in dimensions.values():
        lines.append(
            f"| {_safe_text(dimension.get('label'))} | "
            f"{_safe_text(dimension.get('score'))} / 5 | "
            f"{_safe_text(dimension.get('weight'))}% |"
        )

    lines.extend(
        [
            "",
            f"- **證據覆蓋率：** {_safe_text(maturity.get('coverage_percent'))}%",
            f"- **正式成熟度：** {_safe_text(maturity.get('overall_score'))} / 5",
            f"- **市場階段：** {_safe_text(maturity.get('maturity_stage'))}",
        ]
    )

    return "\n".join(lines)


def _build_financial_tables(
    financials: Dict[str, Any],
    scenario_results: Dict[str, Any],
) -> str:
    lines = [
        "# 財務計算明細",
        "",
        "## 基準情境摘要",
        "",
        "| 指標 | 結果 |",
        "|---|---:|",
        f"| 年度人力節省 | {_format_currency(financials.get('annual_labor_savings'))} |",
        f"| 年度總效益 | {_format_currency(financials.get('annual_total_benefit'))} |",
        f"| 第一年總成本 | {_format_currency(financials.get('first_year_total_cost'))} |",
        f"| 第一年淨效益 | {_format_currency(financials.get('first_year_net_benefit'))} |",
        f"| 三年總成本 | {_format_currency(financials.get('three_year_total_cost'))} |",
        f"| 三年淨效益 | {_format_currency(financials.get('three_year_net_benefit'))} |",
        f"| 三年 ROI | {_format_percent(financials.get('three_year_roi_percent'))} |",
        f"| 回本時間 | {_format_months(financials.get('payback_months'))} |",
        "",
        "## 三情境比較",
        "",
        "| 情境 | 年度總效益 | 第一年淨效益 | 三年淨效益 | 三年 ROI | 回本時間 |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for name, payload in scenario_results.items():
        values = payload.get("financials", {})
        lines.append(
            f"| {name} | "
            f"{_format_currency(values.get('annual_total_benefit'))} | "
            f"{_format_currency(values.get('first_year_net_benefit'))} | "
            f"{_format_currency(values.get('three_year_net_benefit'))} | "
            f"{_format_percent(values.get('three_year_roi_percent'))} | "
            f"{_format_months(values.get('payback_months'))} |"
        )

    return "\n".join(lines)


def _build_product_table(research_result: Dict[str, Any]) -> str:
    market = _completed_task_result(research_result, "market")
    products = market.get("representative_products", [])

    lines = [
        "# 台灣代表產品與商業模式",
        "",
    ]

    if not products:
        lines.append("未找到足夠可靠、可確認在台取得的代表產品資料。")
        return "\n".join(lines)

    lines.extend(
        [
            "| 公司 | 產品 | 用途 | 台灣可取得性 | TFDA 狀態 | 商業模式 | 公開價格 |",
            "|---|---|---|---|---|---|---|",
        ]
    )

    for product in products:
        if not isinstance(product, dict):
            continue
        cells = [
            product.get("company"),
            product.get("product"),
            product.get("use_case"),
            product.get("taiwan_availability"),
            product.get("tfda_status"),
            product.get("business_model"),
            product.get("public_pricing_status"),
        ]
        safe_cells = [
            _safe_text(cell).replace("|", "／").replace("\n", " ")
            for cell in cells
        ]
        lines.append("| " + " | ".join(safe_cells) + " |")

    return "\n".join(lines)


def _build_risk_appendix(
    hard_gate_risks: List[str],
    integrated_decision: Dict[str, Any],
    research_result: Dict[str, Any],
) -> str:
    lines = ["# 風險、阻礙與資料缺口", ""]

    lines.append("## 院內重大風險閘門")
    if hard_gate_risks:
        lines.extend(f"- {item}" for item in hard_gate_risks)
    else:
        lines.append("- 目前沒有觸發重大院內風險閘門。")

    lines.append("")
    lines.append("## 整合決策阻礙")
    blockers = integrated_decision.get("blockers", [])
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- 目前沒有額外的整合決策阻礙。")

    lines.append("")
    lines.append("## 重要警示")
    warnings = integrated_decision.get("warnings", [])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- 目前沒有額外警示。")

    lines.append("")
    lines.append("## 台灣公開資料與院內資料缺口")
    missing = _dedupe_text(
        research_result.get("missing_information", []),
        limit=15,
    )
    internal_needed = _dedupe_text(
        research_result.get("linkou_chang_gung_assessment", {}).get(
            "internal_data_needed", []
        ),
        limit=10,
    )
    combined = _dedupe_text(missing + internal_needed, limit=20)
    if combined:
        lines.extend(f"- {item}" for item in combined)
    else:
        lines.append("- 目前沒有整理出額外資料缺口。")

    return "\n".join(lines)


def _build_source_appendix(research_result: Dict[str, Any]) -> str:
    sources = research_result.get("sources", [])
    grouped: Dict[str, List[Dict[str, str]]] = {}

    for source in sources:
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        label = _safe_text(source.get("task_label"), "其他來源")
        grouped.setdefault(label, []).append(
            {
                "title": _safe_text(source.get("title"), url),
                "url": url,
            }
        )

    lines = [
        "# 台灣公開資料來源",
        "",
        (
            f"本次 Taiwan-first 研究共保留 **{sum(len(v) for v in grouped.values())}** "
            "筆公開來源。來源連結用於查核，不代表系統為來源內容背書。"
        ),
    ]

    if not grouped:
        lines.extend(["", "目前沒有可顯示的公開來源。"])
        return "\n".join(lines)

    for label, items in grouped.items():
        lines.extend(["", f"## {label}"])
        seen_urls = set()
        index = 1
        for item in items:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            title = item["title"].replace("[", "（").replace("]", "）")
            lines.append(f"{index}. [{title}]({item['url']})")
            index += 1

    return "\n".join(lines)


def _build_methodology_appendix(
    scores: Dict[str, int],
    score_reasons: Dict[str, str],
    integrated_decision: Dict[str, Any],
) -> str:
    lines = [
        "# 方法與限制",
        "",
        "## 院內八面向評分",
        "",
        "| 評估面向代碼 | 分數 | 評分原因 |",
        "|---|---:|---|",
    ]

    for key, score in scores.items():
        reason = _safe_text(score_reasons.get(key)).replace("|", "／")
        lines.append(f"| {key} | {score} / 5 | {reason} |")

    weights = integrated_decision.get("weights", {})
    lines.extend(
        [
            "",
            "## 整合決策權重",
            "",
            (
                f"- 台灣市場成熟度：{weights.get('taiwan_market', 30)}%"
            ),
            (
                "- 林口長庚院內可行性："
                f"{weights.get('hospital_feasibility', 40)}%"
            ),
            (
                f"- 財務韌性：{weights.get('financial_resilience', 30)}%"
            ),
            "",
            "## 使用限制",
            "",
            "- 台灣公開資料可能不包含未公開採購、院內試點或商業合約。",
            "- ROI 與回本期依使用者輸入及情境假設計算，不是報酬保證。",
            "- 法規結果為公開資料初評，不取代正式 TFDA、法遵或醫材顧問意見。",
            "- 本工具不提供疾病診斷、治療建議或臨床決策。",
        ]
    )

    return "\n".join(lines)


def build_complete_markdown_report(
    narrative: str,
    project_info: Dict[str, Any],
    financials: Dict[str, Any],
    scenario_results: Dict[str, Any],
    scores: Dict[str, int],
    score_reasons: Dict[str, str],
    hard_gate_risks: List[str],
    research_result: Dict[str, Any],
    integrated_decision: Dict[str, Any],
    generated_at: str,
    model_name: Optional[str],
    ai_used: bool,
    warning: Optional[str],
) -> str:
    report_title = _safe_text(
        project_info.get("project_name"),
        "林口長庚醫療 AI 專案",
    )

    header = [
        f"# {report_title}｜整合商業可行性報告",
        "",
        f"- **評估機構：** {_safe_text(project_info.get('department'))}",
        f"- **AI 應用類型：** {_safe_text(project_info.get('ai_type'))}",
        f"- **導入模式：** {_safe_text(project_info.get('implementation_model'))}",
        f"- **報告產生時間：** {generated_at}",
        f"- **報告版本：** {REPORT_VERSION}",
        f"- **AI 敘事：** {'已使用 ' + _safe_text(model_name) if ai_used else '未使用，採規則式備援摘要'}",
        "",
        "> 本報告用於醫療 AI 市場與商業可行性初評，不提供醫療診斷或治療建議。",
    ]

    if warning:
        header.extend(["", f"> **系統提醒：** {warning}"])

    sections = [
        "\n".join(header),
        narrative.strip(),
        _build_market_table(research_result),
        _build_product_table(research_result),
        _build_financial_tables(financials, scenario_results),
        _build_risk_appendix(
            hard_gate_risks,
            integrated_decision,
            research_result,
        ),
        _build_methodology_appendix(
            scores,
            score_reasons,
            integrated_decision,
        ),
        _build_source_appendix(research_result),
    ]

    return "\n\n---\n\n".join(section for section in sections if section.strip())


def generate_management_report(
    project_info: Dict[str, Any],
    financials: Dict[str, Any],
    scenario_results: Dict[str, Any],
    scores: Dict[str, int],
    score_reasons: Dict[str, str],
    hard_gate_risks: List[str],
    decision: str,
    research_result: Optional[Dict[str, Any]] = None,
    integrated_decision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    建立包含 Taiwan-first 來源、院內評估、財務情境與整合決策的完整報告。

    AI 僅負責管理層敘事。所有表格、分數、財務數字與來源附錄均由
    Python 依結構化資料產生。AI 失敗時仍會回傳可下載的規則式報告。
    """

    research_result = research_result or {}
    integrated_decision = integrated_decision or {}

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )

    payload = _build_ai_payload(
        project_info=project_info,
        financials=financials,
        scenario_results=scenario_results,
        scores=scores,
        score_reasons=score_reasons,
        hard_gate_risks=hard_gate_risks,
        rule_based_decision=decision,
        research_result=research_result,
        integrated_decision=integrated_decision,
    )

    fallback_narrative = _build_fallback_narrative(payload)
    narrative = fallback_narrative
    ai_used = False
    warning: Optional[str] = None
    model_name: Optional[str] = None

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_REPORT_MODEL", DEFAULT_REPORT_MODEL)

    if not api_key:
        warning = "找不到 OPENAI_API_KEY，因此使用規則式備援摘要。"
    else:
        try:
            client = OpenAI(
                api_key=api_key,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=1,
            )

            response = client.responses.create(
                model=model_name,
                max_output_tokens=MAX_REPORT_OUTPUT_TOKENS,
                instructions=(
                    "你是審慎、務實的台灣醫療 AI 商業決策顧問。"
                    "只能根據提供的結構化資料撰寫管理層敘事，不得重新計算、"
                    "修改決策、捏造來源或新增財務數字。"
                ),
                input=_build_prompt(payload),
            )

            candidate = (response.output_text or "").strip()
            if not candidate:
                raise ManagementReportError("模型沒有回傳可用的管理層敘事。")

            narrative = candidate
            ai_used = True

        except Exception as error:
            warning = (
                "AI 敘事產生失敗，已自動改用規則式備援摘要；"
                f"財務表、整合決策與台灣來源仍完整保留。錯誤類型：{type(error).__name__}。"
            )

    markdown = build_complete_markdown_report(
        narrative=narrative,
        project_info=project_info,
        financials=financials,
        scenario_results=scenario_results,
        scores=scores,
        score_reasons=score_reasons,
        hard_gate_risks=hard_gate_risks,
        research_result=research_result,
        integrated_decision=integrated_decision,
        generated_at=generated_at,
        model_name=model_name,
        ai_used=ai_used,
        warning=warning,
    )

    audit_payload = {
        "report_version": REPORT_VERSION,
        "generated_at": generated_at,
        "ai_used": ai_used,
        "model": model_name if ai_used else None,
        "warning": warning,
        "project_info": project_info,
        "research_result": research_result,
        "hospital_assessment": {
            "financials": financials,
            "scenario_results": scenario_results,
            "scores": scores,
            "score_reasons": score_reasons,
            "hard_gate_risks": hard_gate_risks,
            "rule_based_decision": decision,
        },
        "integrated_decision": integrated_decision,
    }

    return {
        "markdown": markdown,
        "audit_json": json.dumps(
            audit_payload,
            ensure_ascii=False,
            indent=2,
        ),
        "generated_at": generated_at,
        "report_version": REPORT_VERSION,
        "ai_used": ai_used,
        "model": model_name if ai_used else None,
        "warning": warning,
        "source_count": len(research_result.get("sources", [])),
    }
