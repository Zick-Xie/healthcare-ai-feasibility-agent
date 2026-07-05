from typing import Dict, List, Optional


SCORE_WEIGHTS = {
    "cost_saving": 15,
    "efficiency": 15,
    "revenue_growth": 10,
    "clinical_value": 10,
    "data_readiness": 15,
    "integration_feasibility": 10,
    "regulatory_control": 10,
    "clinical_adoption": 15,
}


def calculate_financials(
    monthly_cases: float,
    minutes_saved_per_case: float,
    hourly_labor_cost: float,
    adoption_rate: float,
    annual_license_cost: float,
    annual_maintenance_cost: float,
    one_time_integration_cost: float,
    annual_avoided_cost: float = 0,
    annual_extra_revenue: float = 0,
) -> Dict[str, Optional[float]]:
    """
    計算醫療 AI 專案的年度效益、成本、ROI 與回本時間。

    adoption_rate 使用 0 到 1，例如 70% 請輸入 0.7。
    """

    if monthly_cases < 0:
        raise ValueError("每月案件數不可小於 0。")

    if minutes_saved_per_case < 0:
        raise ValueError("每件節省時間不可小於 0。")

    if hourly_labor_cost < 0:
        raise ValueError("每小時人力成本不可小於 0。")

    if not 0 <= adoption_rate <= 1:
        raise ValueError("採用率必須介於 0 到 1。")

    annual_labor_savings = (
        monthly_cases
        * 12
        * minutes_saved_per_case
        / 60
        * hourly_labor_cost
        * adoption_rate
    )

    annual_total_benefit = (
        annual_labor_savings
        + annual_avoided_cost
        + annual_extra_revenue
    )

    annual_recurring_cost = (
        annual_license_cost
        + annual_maintenance_cost
    )

    first_year_total_cost = (
        one_time_integration_cost
        + annual_recurring_cost
    )

    first_year_net_benefit = (
        annual_total_benefit
        - first_year_total_cost
    )

    three_year_total_benefit = annual_total_benefit * 3

    three_year_total_cost = (
        one_time_integration_cost
        + annual_recurring_cost * 3
    )

    three_year_net_benefit = (
        three_year_total_benefit
        - three_year_total_cost
    )

    if three_year_total_cost > 0:
        three_year_roi_percent = (
            three_year_net_benefit
            / three_year_total_cost
            * 100
        )
    else:
        three_year_roi_percent = None

    monthly_net_cash_flow = (
        annual_total_benefit
        - annual_recurring_cost
    ) / 12

    if monthly_net_cash_flow > 0:
        payback_months = (
            one_time_integration_cost
            / monthly_net_cash_flow
        )
    else:
        payback_months = None

    return {
        "annual_labor_savings": round(annual_labor_savings, 2),
        "annual_total_benefit": round(annual_total_benefit, 2),
        "annual_recurring_cost": round(annual_recurring_cost, 2),
        "first_year_total_cost": round(first_year_total_cost, 2),
        "first_year_net_benefit": round(first_year_net_benefit, 2),
        "three_year_total_benefit": round(
            three_year_total_benefit, 2
        ),
        "three_year_total_cost": round(
            three_year_total_cost, 2
        ),
        "three_year_net_benefit": round(
            three_year_net_benefit, 2
        ),
        "three_year_roi_percent": (
            round(three_year_roi_percent, 2)
            if three_year_roi_percent is not None
            else None
        ),
        "payback_months": (
            round(payback_months, 1)
            if payback_months is not None
            else None
        ),
    }


def calculate_feasibility_score(
    scores: Dict[str, int],
) -> float:
    """
    接收八個面向的 1 至 5 分，計算 0 至 100 的加權總分。
    """

    missing_items = set(SCORE_WEIGHTS) - set(scores)

    if missing_items:
        raise ValueError(
            f"缺少評分項目：{', '.join(sorted(missing_items))}"
        )

    total_score = 0.0

    for item, weight in SCORE_WEIGHTS.items():
        score = scores[item]

        if score < 1 or score > 5:
            raise ValueError(
                f"{item} 的分數必須介於 1 到 5。"
            )

        total_score += score / 5 * weight

    return round(total_score, 1)


def check_hard_gates(
    has_clinical_owner: bool,
    has_legal_data_basis: bool,
    has_integration_path: bool,
    has_baseline_metrics: bool,
    has_human_oversight: bool,
    certification_ready: bool,
) -> List[str]:
    """
    檢查不能只靠高 ROI 或高總分忽略的重大風險。
    """

    risks = []

    if not has_clinical_owner:
        risks.append("尚未指定負責此專案的臨床單位或臨床負責人。")

    if not has_legal_data_basis:
        risks.append("尚未確認醫療資料的合法使用依據與隱私治理方式。")

    if not has_integration_path:
        risks.append("尚未確認與 HIS、PACS、RIS 或 EMR 的整合方式。")

    if not has_baseline_metrics:
        risks.append("缺少現況基準數據，無法可靠衡量導入效益。")

    if not has_human_oversight:
        risks.append("尚未設計人工覆核與 AI 異常處理流程。")

    if not certification_ready:
        risks.append("尚未確認產品是否符合所需的醫療器材或法規要求。")

    return risks


def make_decision(
    feasibility_score: float,
    financials: Dict[str, Optional[float]],
    hard_gate_risks: List[str],
) -> str:
    """
    根據分數、ROI 與重大風險產生初步決策。
    """

    roi = financials.get("three_year_roi_percent")
    payback = financials.get("payback_months")

    if len(hard_gate_risks) >= 3:
        return "建議暫緩導入"

    if (
        feasibility_score >= 70
        and roi is not None
        and roi > 0
        and len(hard_gate_risks) == 0
    ):
        return "建議優先進入受控試點"

    if (
        feasibility_score >= 60
        and roi is not None
        and roi > 0
        and len(hard_gate_risks) <= 2
    ):
        return "建議補充資料後進入受控試點"

    if feasibility_score >= 50:
        return "建議補充資料後再評估"

    if payback is None or roi is None or roi <= 0:
        return "建議重新設計商業模式"

    return "建議暫緩導入"
