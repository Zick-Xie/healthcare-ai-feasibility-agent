from ai_report import generate_management_report
from assessment_rules import calculate_automatic_scores
from scenario_analysis import calculate_scenarios
from scoring import (
    calculate_feasibility_score,
    check_hard_gates,
    make_decision,
)


project_info = {
    "project_name": "急診胸部 X 光 AI 輔助判讀",
    "department": "急診部、放射科",
    "ai_type": "醫療影像",
    "implementation_model": "購買現成產品",
    "use_case": (
        "在急診導入胸部 X 光 AI，協助急診與放射科醫師"
        "優先辨識疑似高風險影像。"
    ),
}


base_financial_inputs = {
    "monthly_cases": 3000,
    "minutes_saved_per_case": 8,
    "hourly_labor_cost": 1200,
    "adoption_rate": 0.70,
    "annual_license_cost": 1_500_000,
    "annual_maintenance_cost": 300_000,
    "one_time_integration_cost": 2_000_000,
    "annual_avoided_cost": 500_000,
    "annual_extra_revenue": 800_000,
}


scenario_results = calculate_scenarios(
    base_financial_inputs
)

financials = scenario_results[
    "基準情境"
]["financials"]


scores, score_reasons = calculate_automatic_scores(
    financials=financials,
    baseline_minutes_per_case=25,
    minutes_saved_per_case=8,
    annual_avoided_cost=500_000,
    annual_extra_revenue=800_000,
    revenue_is_objective=True,
    clinical_impact_level=4,
    evidence_level=3,
    data_readiness_level=3,
    integration_level=2,
    regulatory_level=2,
    adoption_level=3,
)


feasibility_score = calculate_feasibility_score(
    scores
)


hard_gate_risks = check_hard_gates(
    has_clinical_owner=True,
    has_legal_data_basis=True,
    has_integration_path=False,
    has_baseline_metrics=True,
    has_human_oversight=True,
    certification_ready=False,
)


decision = make_decision(
    feasibility_score=feasibility_score,
    financials=financials,
    hard_gate_risks=hard_gate_risks,
)


project_info["feasibility_score"] = feasibility_score


print("正在產生 AI 管理層報告……\n")


report = generate_management_report(
    project_info=project_info,
    financials=financials,
    scenario_results=scenario_results,
    scores=scores,
    score_reasons=score_reasons,
    hard_gate_risks=hard_gate_risks,
    decision=decision,
)


print(report)
