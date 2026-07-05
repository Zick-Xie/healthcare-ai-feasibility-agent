from typing import Dict

from scoring import calculate_financials


SCENARIO_ASSUMPTIONS = {
    "保守情境": {
        "monthly_cases_multiplier": 0.90,
        "minutes_saved_multiplier": 0.75,
        "adoption_rate_multiplier": 0.75,
        "annual_avoided_cost_multiplier": 0.75,
        "annual_extra_revenue_multiplier": 0.60,
        "integration_cost_multiplier": 1.20,
    },
    "基準情境": {
        "monthly_cases_multiplier": 1.00,
        "minutes_saved_multiplier": 1.00,
        "adoption_rate_multiplier": 1.00,
        "annual_avoided_cost_multiplier": 1.00,
        "annual_extra_revenue_multiplier": 1.00,
        "integration_cost_multiplier": 1.00,
    },
    "樂觀情境": {
        "monthly_cases_multiplier": 1.05,
        "minutes_saved_multiplier": 1.25,
        "adoption_rate_multiplier": 1.15,
        "annual_avoided_cost_multiplier": 1.15,
        "annual_extra_revenue_multiplier": 1.25,
        "integration_cost_multiplier": 0.90,
    },
}


REQUIRED_INPUTS = {
    "monthly_cases",
    "minutes_saved_per_case",
    "hourly_labor_cost",
    "adoption_rate",
    "annual_license_cost",
    "annual_maintenance_cost",
    "one_time_integration_cost",
    "annual_avoided_cost",
    "annual_extra_revenue",
}


def calculate_scenarios(
    base_inputs: Dict[str, float],
) -> Dict[str, Dict]:
    """
    根據基準輸入，計算保守、基準與樂觀三種財務情境。

    所有情境假設都必須透明呈現，不能把預測當成確定結果。
    """

    missing_inputs = REQUIRED_INPUTS - set(base_inputs)

    if missing_inputs:
        raise ValueError(
            "缺少情境分析輸入："
            + ", ".join(sorted(missing_inputs))
        )

    scenario_results = {}

    for scenario_name, assumptions in SCENARIO_ASSUMPTIONS.items():
        adjusted_adoption_rate = min(
            1.0,
            base_inputs["adoption_rate"]
            * assumptions["adoption_rate_multiplier"],
        )

        adjusted_inputs = {
            "monthly_cases": (
                base_inputs["monthly_cases"]
                * assumptions["monthly_cases_multiplier"]
            ),
            "minutes_saved_per_case": (
                base_inputs["minutes_saved_per_case"]
                * assumptions["minutes_saved_multiplier"]
            ),
            "hourly_labor_cost": base_inputs["hourly_labor_cost"],
            "adoption_rate": adjusted_adoption_rate,
            "annual_license_cost": (
                base_inputs["annual_license_cost"]
            ),
            "annual_maintenance_cost": (
                base_inputs["annual_maintenance_cost"]
            ),
            "one_time_integration_cost": (
                base_inputs["one_time_integration_cost"]
                * assumptions["integration_cost_multiplier"]
            ),
            "annual_avoided_cost": (
                base_inputs["annual_avoided_cost"]
                * assumptions["annual_avoided_cost_multiplier"]
            ),
            "annual_extra_revenue": (
                base_inputs["annual_extra_revenue"]
                * assumptions["annual_extra_revenue_multiplier"]
            ),
        }

        financials = calculate_financials(**adjusted_inputs)

        scenario_results[scenario_name] = {
            "inputs": adjusted_inputs,
            "assumptions": assumptions,
            "financials": financials,
        }

    return scenario_results
