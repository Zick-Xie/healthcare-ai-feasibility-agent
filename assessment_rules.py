from typing import Dict, Tuple


def validate_level(name: str, value: int) -> None:
    if value < 1 or value > 5:
        raise ValueError(f"{name} 必須介於 1 到 5。")


def score_cost_saving(
    annual_labor_savings: float,
    annual_avoided_cost: float,
    annual_recurring_cost: float,
) -> Tuple[int, str]:
    annual_savings = annual_labor_savings + annual_avoided_cost

    if annual_savings <= 0:
        return 1, "目前沒有可量化的年度成本節省。"

    if annual_recurring_cost <= 0:
        return 5, "具有成本節省，且目前未列入持續性營運成本。"

    ratio = annual_savings / annual_recurring_cost

    if ratio < 0.5:
        score = 2
    elif ratio < 1:
        score = 3
    elif ratio < 2:
        score = 4
    else:
        score = 5

    return score, (
        f"年度可節省成本約為持續性營運成本的 {ratio:.2f} 倍。"
    )


def score_efficiency(
    baseline_minutes_per_case: float,
    minutes_saved_per_case: float,
) -> Tuple[int, str]:
    if baseline_minutes_per_case <= 0:
        return 1, "缺少目前每件案件的基準處理時間。"

    saving_rate = (
        minutes_saved_per_case / baseline_minutes_per_case
    )

    if saving_rate <= 0:
        score = 1
    elif saving_rate < 0.10:
        score = 2
    elif saving_rate < 0.20:
        score = 3
    elif saving_rate < 0.35:
        score = 4
    else:
        score = 5

    return score, (
        f"預估每件案件可縮短 {saving_rate:.1%} 的處理時間。"
    )


def score_revenue_growth(
    annual_extra_revenue: float,
    annual_recurring_cost: float,
    revenue_is_objective: bool,
) -> Tuple[int, str]:
    if not revenue_is_objective:
        return 3, "增加收入不是此專案的主要目標，因此給予中性評分。"

    if annual_extra_revenue <= 0:
        return 1, "收入成長是專案目標，但目前沒有可量化的新收入。"

    if annual_recurring_cost <= 0:
        return 5, "具有可量化新增收入，且目前未列入持續性成本。"

    ratio = annual_extra_revenue / annual_recurring_cost

    if ratio < 0.25:
        score = 2
    elif ratio < 0.75:
        score = 3
    elif ratio < 1.5:
        score = 4
    else:
        score = 5

    return score, (
        f"預估新增收入約為持續性營運成本的 {ratio:.2f} 倍。"
    )


def score_clinical_value(
    clinical_impact_level: int,
    evidence_level: int,
) -> Tuple[int, str]:
    validate_level("臨床影響程度", clinical_impact_level)
    validate_level("證據成熟度", evidence_level)

    weighted_score = round(
        clinical_impact_level * 0.6
        + evidence_level * 0.4
    )

    score = max(1, min(5, weighted_score))

    return score, (
        f"臨床影響程度為 {clinical_impact_level} 分，"
        f"證據成熟度為 {evidence_level} 分。"
    )


def calculate_automatic_scores(
    financials: Dict[str, float],
    baseline_minutes_per_case: float,
    minutes_saved_per_case: float,
    annual_avoided_cost: float,
    annual_extra_revenue: float,
    revenue_is_objective: bool,
    clinical_impact_level: int,
    evidence_level: int,
    data_readiness_level: int,
    integration_level: int,
    regulatory_level: int,
    adoption_level: int,
) -> Tuple[Dict[str, int], Dict[str, str]]:
    validate_level("資料準備程度", data_readiness_level)
    validate_level("系統整合成熟度", integration_level)
    validate_level("法規準備程度", regulatory_level)
    validate_level("臨床採用準備程度", adoption_level)

    cost_score, cost_reason = score_cost_saving(
        annual_labor_savings=financials["annual_labor_savings"],
        annual_avoided_cost=annual_avoided_cost,
        annual_recurring_cost=financials["annual_recurring_cost"],
    )

    efficiency_score, efficiency_reason = score_efficiency(
        baseline_minutes_per_case=baseline_minutes_per_case,
        minutes_saved_per_case=minutes_saved_per_case,
    )

    revenue_score, revenue_reason = score_revenue_growth(
        annual_extra_revenue=annual_extra_revenue,
        annual_recurring_cost=financials["annual_recurring_cost"],
        revenue_is_objective=revenue_is_objective,
    )

    clinical_score, clinical_reason = score_clinical_value(
        clinical_impact_level=clinical_impact_level,
        evidence_level=evidence_level,
    )

    scores = {
        "cost_saving": cost_score,
        "efficiency": efficiency_score,
        "revenue_growth": revenue_score,
        "clinical_value": clinical_score,
        "data_readiness": data_readiness_level,
        "integration_feasibility": integration_level,
        "regulatory_control": regulatory_level,
        "clinical_adoption": adoption_level,
    }

    reasons = {
        "cost_saving": cost_reason,
        "efficiency": efficiency_reason,
        "revenue_growth": revenue_reason,
        "clinical_value": clinical_reason,
        "data_readiness": (
            f"資料準備程度問卷結果為 {data_readiness_level} 分。"
        ),
        "integration_feasibility": (
            f"系統整合成熟度問卷結果為 {integration_level} 分。"
        ),
        "regulatory_control": (
            f"法規準備程度問卷結果為 {regulatory_level} 分。"
        ),
        "clinical_adoption": (
            f"臨床採用準備程度問卷結果為 {adoption_level} 分。"
        ),
    }

    return scores, reasons
