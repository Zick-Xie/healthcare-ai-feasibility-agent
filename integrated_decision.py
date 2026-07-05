from __future__ import annotations

from typing import Any, Dict, List, Optional


TAIWAN_MARKET_WEIGHT = 30
HOSPITAL_FEASIBILITY_WEIGHT = 40
FINANCIAL_RESILIENCE_WEIGHT = 30


class IntegratedDecisionError(ValueError):
    """整合決策所需資料不完整或格式不正確。"""


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _score_roi(roi_percent: Optional[float]) -> float:
    """將三年 ROI 轉成 0 至 100 分。"""

    if roi_percent is None:
        return 0.0
    if roi_percent <= 0:
        return 10.0
    if roi_percent < 25:
        return 35.0
    if roi_percent < 75:
        return 60.0
    if roi_percent < 150:
        return 80.0
    return 100.0


def _score_payback(payback_months: Optional[float]) -> float:
    """將回本時間轉成 0 至 100 分。"""

    if payback_months is None:
        return 0.0
    if payback_months <= 12:
        return 100.0
    if payback_months <= 24:
        return 80.0
    if payback_months <= 36:
        return 55.0
    if payback_months <= 48:
        return 30.0
    return 10.0


def calculate_financial_resilience(
    baseline_financials: Dict[str, Any],
    conservative_financials: Dict[str, Any],
) -> Dict[str, Any]:
    """
    根據基準與保守情境計算財務韌性。

    分數不是財務預測，而是用於比較專案對關鍵假設的敏感程度。
    """

    baseline_roi = baseline_financials.get("three_year_roi_percent")
    baseline_payback = baseline_financials.get("payback_months")
    conservative_roi = conservative_financials.get("three_year_roi_percent")
    conservative_payback = conservative_financials.get("payback_months")
    conservative_first_year_net = conservative_financials.get(
        "first_year_net_benefit"
    )

    baseline_roi_score = _score_roi(baseline_roi)
    baseline_payback_score = _score_payback(baseline_payback)
    conservative_roi_score = _score_roi(conservative_roi)
    conservative_payback_score = _score_payback(conservative_payback)

    score = (
        baseline_roi_score * 0.30
        + baseline_payback_score * 0.20
        + conservative_roi_score * 0.30
        + conservative_payback_score * 0.20
    )

    warnings: List[str] = []

    if baseline_roi is None or baseline_roi <= 0:
        warnings.append("基準情境三年 ROI 不為正，商業模式需要重新設計。")

    if baseline_payback is None:
        warnings.append("基準情境無法估計回本時間。")
    elif baseline_payback > 24:
        warnings.append("基準情境回本時間超過 24 個月。")

    if conservative_roi is None or conservative_roi <= 0:
        warnings.append("保守情境三年 ROI 不為正，專案對假設變動較敏感。")

    if conservative_payback is None:
        warnings.append("保守情境無法估計回本時間。")
    elif conservative_payback > 24:
        warnings.append("保守情境回本時間超過 24 個月。")

    if (
        isinstance(conservative_first_year_net, (int, float))
        and conservative_first_year_net < 0
    ):
        warnings.append("保守情境第一年淨效益為負，需注意初期預算壓力。")

    return {
        "score": round(_clamp(score, 0, 100), 1),
        "baseline_roi_percent": baseline_roi,
        "baseline_payback_months": baseline_payback,
        "conservative_roi_percent": conservative_roi,
        "conservative_payback_months": conservative_payback,
        "conservative_first_year_net_benefit": conservative_first_year_net,
        "warnings": warnings,
    }


def _extract_taiwan_market_score(
    research_result: Dict[str, Any],
) -> Dict[str, Any]:
    maturity = research_result.get("taiwan_market_maturity", {})
    coverage = maturity.get("coverage_percent", 0)
    overall_score = maturity.get("overall_score")

    if coverage != 100 or overall_score is None:
        return {
            "ready": False,
            "coverage_percent": coverage,
            "score": None,
            "score_100": None,
            "stage": maturity.get(
                "maturity_stage",
                "台灣研究尚未完整",
            ),
            "reason": "四項台灣研究任務尚未完整，不產生正式整合決策。",
        }

    score_100 = float(overall_score) / 5 * 100

    return {
        "ready": True,
        "coverage_percent": coverage,
        "score": float(overall_score),
        "score_100": round(score_100, 1),
        "stage": maturity.get("maturity_stage", "未分類"),
        "reason": "台灣市場分數只使用 TFDA、台灣醫院、台灣臨床與台灣產品證據。",
    }


def _get_market_dimension(
    research_result: Dict[str, Any],
    dimension_id: str,
) -> Optional[float]:
    dimensions = research_result.get(
        "taiwan_market_maturity",
        {},
    ).get("dimensions", {})

    dimension = dimensions.get(dimension_id)
    if not isinstance(dimension, dict):
        return None

    score = dimension.get("score")
    if isinstance(score, (int, float)):
        return float(score)

    return None


def build_integrated_decision(
    research_result: Dict[str, Any],
    hospital_feasibility_score: float,
    financials: Dict[str, Any],
    scenario_results: Dict[str, Any],
    hard_gate_risks: List[str],
) -> Dict[str, Any]:
    """
    整合台灣市場證據、林口長庚院內可行性與財務韌性。

    整合分數僅在四項台灣研究都完成時產生。
    重大風險與關鍵市場分數會限制最終決策，不會只看總分。
    """

    if not isinstance(research_result, dict):
        raise IntegratedDecisionError("缺少台灣市場研究結果。")

    market = _extract_taiwan_market_score(research_result)

    if "保守情境" not in scenario_results:
        raise IntegratedDecisionError("缺少保守情境財務結果。")

    conservative_financials = scenario_results["保守情境"].get(
        "financials",
        {},
    )

    financial = calculate_financial_resilience(
        baseline_financials=financials,
        conservative_financials=conservative_financials,
    )

    hospital_score = round(
        _clamp(float(hospital_feasibility_score), 0, 100),
        1,
    )

    blockers: List[str] = []
    warnings: List[str] = []

    if not market["ready"]:
        blockers.append(
            f"台灣研究證據覆蓋率為 {market['coverage_percent']}%，尚未達 100%。"
        )

    regulatory_score = _get_market_dimension(
        research_result,
        "regulatory",
    )
    adoption_score = _get_market_dimension(
        research_result,
        "hospital_adoption",
    )
    clinical_score = _get_market_dimension(
        research_result,
        "clinical_evidence",
    )

    if regulatory_score is not None and regulatory_score <= 2:
        blockers.append("台灣法規成熟度偏低，需先確認 TFDA 路徑與候選產品許可。")

    if adoption_score is not None and adoption_score <= 2:
        warnings.append("台灣醫院採用成熟度偏低，建議先做小規模 POC。")

    if clinical_score is not None and clinical_score <= 2:
        warnings.append("台灣臨床證據偏弱，試點需納入本地驗證設計。")

    if len(hard_gate_risks) >= 3:
        blockers.append("院內重大風險閘門達 3 項以上。")
    elif hard_gate_risks:
        warnings.extend(hard_gate_risks)

    warnings.extend(financial["warnings"])

    baseline_roi = financial["baseline_roi_percent"]
    conservative_roi = financial["conservative_roi_percent"]

    if baseline_roi is None or baseline_roi <= 0:
        blockers.append("基準情境三年 ROI 不為正。")

    if conservative_roi is None or conservative_roi <= 0:
        blockers.append("保守情境三年 ROI 不為正。")

    if not market["ready"]:
        return {
            "status": "research_incomplete",
            "formal_score_available": False,
            "integrated_score": None,
            "decision": "建議先完成台灣研究，再形成正式投資建議",
            "decision_level": "暫不決策",
            "market": market,
            "hospital": {
                "score": hospital_score,
            },
            "financial": financial,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": [
                "完成四項 Taiwan-first 研究任務。",
                "確認研究題目與院內評估專案為同一應用情境。",
                "保留目前院內 ROI 與風險分析，待研究完成後重新整合。",
            ],
        }

    integrated_score = (
        market["score_100"] * TAIWAN_MARKET_WEIGHT / 100
        + hospital_score * HOSPITAL_FEASIBILITY_WEIGHT / 100
        + financial["score"] * FINANCIAL_RESILIENCE_WEIGHT / 100
    )
    integrated_score = round(_clamp(integrated_score, 0, 100), 1)

    if blockers:
        if baseline_roi is None or baseline_roi <= 0:
            decision = "建議暫緩，重新設計商業模式"
            decision_level = "暫緩"
        elif regulatory_score is not None and regulatory_score <= 2:
            decision = "建議先完成法規與產品許可盤點，再考慮 POC"
            decision_level = "補件"
        elif conservative_roi is None or conservative_roi <= 0:
            decision = "建議縮小試點範圍並重新談判成本"
            decision_level = "重設方案"
        else:
            decision = "建議先解除重大阻礙，再進入受控試點"
            decision_level = "補件"
    elif integrated_score >= 75:
        decision = "建議進入跨部門受控試點"
        decision_level = "試點"
    elif integrated_score >= 65:
        decision = "建議補充關鍵資料後規劃小規模 POC"
        decision_level = "POC"
    elif integrated_score >= 50:
        decision = "建議重新設計導入方案並補充證據"
        decision_level = "重設方案"
    else:
        decision = "建議暫緩導入"
        decision_level = "暫緩"

    next_actions: List[str] = []

    if regulatory_score is not None and regulatory_score <= 3:
        next_actions.append("由法遵／醫材單位確認候選產品 TFDA 許可與預定用途。")

    if adoption_score is not None and adoption_score <= 3:
        next_actions.append("以單一科別、有限病例量進行 POC，補足台灣採用證據。")

    if clinical_score is not None and clinical_score <= 3:
        next_actions.append("設計林口長庚本地資料驗證與人工覆核 KPI。")

    if hard_gate_risks:
        next_actions.append("逐項關閉院內重大風險閘門，指定負責單位與完成期限。")

    if financial["warnings"]:
        next_actions.append("重新確認授權費、整合費、採用率與節省時間假設。")

    if not next_actions:
        next_actions.append("召集臨床、資訊、法遵、採購與財務單位設計受控試點。")

    return {
        "status": "complete",
        "formal_score_available": True,
        "integrated_score": integrated_score,
        "decision": decision,
        "decision_level": decision_level,
        "weights": {
            "taiwan_market": TAIWAN_MARKET_WEIGHT,
            "hospital_feasibility": HOSPITAL_FEASIBILITY_WEIGHT,
            "financial_resilience": FINANCIAL_RESILIENCE_WEIGHT,
        },
        "market": market,
        "hospital": {
            "score": hospital_score,
        },
        "financial": financial,
        "blockers": blockers,
        "warnings": list(dict.fromkeys(warnings)),
        "next_actions": list(dict.fromkeys(next_actions)),
    }
