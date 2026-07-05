from scenario_analysis import calculate_scenarios


base_inputs = {
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


scenario_results = calculate_scenarios(base_inputs)


print("\n=== 三情境分析 ===")

for scenario_name, result in scenario_results.items():
    financials = result["financials"]

    roi = financials["three_year_roi_percent"]
    payback = financials["payback_months"]

    print(f"\n{scenario_name}")
    print(
        f"年度總效益："
        f"NT$ {financials['annual_total_benefit']:,.0f}"
    )
    print(
        f"第一年淨效益："
        f"NT$ {financials['first_year_net_benefit']:,.0f}"
    )
    print(
        f"三年 ROI："
        f"{roi:.2f}%" if roi is not None else "三年 ROI：無法計算"
    )
    print(
        f"回本時間："
        f"{payback:.1f} 個月"
        if payback is not None
        else "回本時間：無法回本"
    )
