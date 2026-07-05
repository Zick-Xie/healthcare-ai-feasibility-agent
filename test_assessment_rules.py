from scoring import (
    calculate_feasibility_score,
    calculate_financials,
)

from assessment_rules import calculate_automatic_scores


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


scores, reasons = calculate_automatic_scores(
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


total_score = calculate_feasibility_score(scores)


print("\n=== 自動評分結果 ===")

for item, score in scores.items():
    print(f"{item}: {score} / 5")
    print(f"原因：{reasons[item]}")
    print()

print("=== 加權總分 ===")
print(f"{total_score} / 100")
