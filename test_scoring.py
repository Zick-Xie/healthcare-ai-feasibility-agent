from pprint import pprint

from scoring import (
    calculate_feasibility_score,
    calculate_financials,
    check_hard_gates,
    make_decision,
)


financials = calculate_financials(
    monthly_cases=3000,
    minutes_saved_per_case=8,
    hourly_labor_cost=1200,
    adoption_rate=0.7,
    annual_license_cost=1_500_000,
    annual_maintenance_cost=300_000,
    one_time_integration_cost=2_000_000,
    annual_avoided_cost=500_000,
    annual_extra_revenue=800_000,
)


scores = {
    "cost_saving": 4,
    "efficiency": 4,
    "revenue_growth": 3,
    "clinical_value": 4,
    "data_readiness": 3,
    "integration_feasibility": 3,
    "regulatory_control": 3,
    "clinical_adoption": 3,
}


feasibility_score = calculate_feasibility_score(scores)


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


print("\n=== 財務分析 ===")
pprint(financials)

print("\n=== 可行性評分 ===")
print(f"{feasibility_score} / 100")

print("\n=== 重大風險 ===")
for risk in hard_gate_risks:
    print(f"- {risk}")

print("\n=== 建議決策 ===")
print(decision)
