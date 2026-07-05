import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_MODEL = "gpt-5.4-mini"


def generate_management_report(
    project_info: Dict[str, Any],
    financials: Dict[str, Any],
    scenario_results: Dict[str, Any],
    scores: Dict[str, int],
    score_reasons: Dict[str, str],
    hard_gate_risks: List[str],
    decision: str,
) -> str:
    """
    根據規則引擎與財務模型的既有結果，產生管理層報告。

    AI 只負責解釋，不負責重新計算或修改分數。
    """

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(
            "找不到 OPENAI_API_KEY，請確認 .env 是否設定正確。"
        )

    model_name = os.getenv(
        "OPENAI_MODEL",
        DEFAULT_MODEL,
    )

    client = OpenAI(api_key=api_key)

    scenario_summary = {}

    for scenario_name, scenario_data in scenario_results.items():
        scenario_summary[scenario_name] = {
            "financials": scenario_data["financials"],
            "assumptions": scenario_data["assumptions"],
        }

    analysis_data = {
        "project_information": project_info,
        "baseline_financials": financials,
        "scenario_analysis": scenario_summary,
        "feasibility_scores": scores,
        "score_reasons": score_reasons,
        "hard_gate_risks": hard_gate_risks,
        "rule_based_decision": decision,
    }

    analysis_json = json.dumps(
        analysis_data,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
以下是一個醫療 AI 專案的結構化商業可行性評估結果。

這些財務數字、分數、風險和決策已經由 Python 規則引擎完成。
你只能解釋既有結果，不得重新計算、修改分數或推翻規則引擎決策。

【評估資料】
{analysis_json}

請使用繁體中文，產生一份給醫院管理層閱讀的報告，格式如下：

# 管理層摘要

用 4 至 6 句說明：
- 專案要解決的問題
- 目前商業可行性
- 財務結果
- 最重要的限制
- 規則引擎建議的決策

# 決策理由

說明為什麼規則引擎得到目前的決策。

必須同時考慮：
- 可行性總分及各面向表現
- 基準情境的 ROI 與回本時間
- 保守情境是否出現第一年虧損
- 重大風險閘門

# 商業價值來源

分別說明：
1. 人力與成本節省
2. 流程效率提升
3. 收入或服務量增加
4. 臨床品質與風險管理

沒有資料支持的項目，請明確寫「目前無法確認」。

# 三情境解讀

分別解讀：
- 保守情境
- 基準情境
- 樂觀情境

不可把樂觀情境當成預測結果。

# 目前重大風險

逐項解釋風險為何會影響專案導入。

# 建議補充資料

列出正式投資決策前最需要取得的 5 項資料。

# 建議試點方案

提出一個規模合理的受控試點，包括：
- 建議期間
- 建議試點範圍
- 參與角色
- 4 至 6 項 KPI
- 成功標準
- 中止條件

試點內容必須符合目前規則引擎決策。
若決策是暫緩導入，不可直接建議全面試點。

# 結論

再次呈現規則引擎的原始決策，並用 2 至 3 句說明下一步。

重要規則：
1. 不得提供疾病診斷或治療建議。
2. 不得捏造研究、法規、認證、價格或醫院內部資料。
3. 不得自行增加未提供的財務數字。
4. 必須區分使用者輸入、系統計算結果與情境假設。
5. 金額使用新台幣表示。
6. 保持務實，不要因為是 AI 專案而過度樂觀。
"""

    response = client.responses.create(
        model=model_name,
        instructions=(
            "你是審慎、務實的醫療 AI 商業可行性分析顧問。"
            "你只能根據提供的結構化資料解釋結果，"
            "不得自行重新計算、虛構事實或提供臨床診斷。"
        ),
        input=prompt,
    )

    report = response.output_text.strip()

    if not report:
        raise RuntimeError("模型沒有回傳可用的報告內容。")

    return report
