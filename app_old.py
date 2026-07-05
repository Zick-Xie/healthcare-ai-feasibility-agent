import os
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


# =========================================================
# 基本設定
# =========================================================

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

st.set_page_config(
    page_title="醫療 AI 商業可行性分析",
    page_icon="🏥",
    layout="wide",
)

if "analysis_report" not in st.session_state:
    st.session_state.analysis_report = ""

if "last_result" not in st.session_state:
    st.session_state.last_result = None


# =========================================================
# 計算函式
# =========================================================

def calculate_financials(
    annual_cases: float,
    minutes_saved: float,
    hourly_labor_cost: float,
    realization_rate: float,
    initial_cost: float,
    annual_ai_cost: float,
    annual_extra_revenue: float,
) -> dict[str, Any]:
    """
    根據使用者輸入的假設，計算年度效益、ROI、回收期與損益兩平案件量。

    realization_rate:
        節省工時中，真正能轉化成財務或營運價值的比例。
        例如節省醫師時間不一定等於直接減少薪資支出。
    """

    hours_saved = annual_cases * minutes_saved / 60

    theoretical_labor_value = hours_saved * hourly_labor_cost

    realized_labor_value = theoretical_labor_value * realization_rate

    total_annual_benefit = realized_labor_value + annual_extra_revenue

    annual_net_benefit = total_annual_benefit - annual_ai_cost

    total_first_year_cost = initial_cost + annual_ai_cost

    if total_first_year_cost > 0:
        first_year_roi = (
            total_annual_benefit - total_first_year_cost
        ) / total_first_year_cost * 100
    else:
        first_year_roi = None

    if annual_ai_cost > 0:
        steady_state_roi = annual_net_benefit / annual_ai_cost * 100
    elif total_annual_benefit > 0:
        steady_state_roi = float("inf")
    else:
        steady_state_roi = None

    if annual_net_benefit > 0:
        payback_years = initial_cost / annual_net_benefit
    else:
        payback_years = None

    realized_value_per_case = (
        minutes_saved / 60
        * hourly_labor_cost
        * realization_rate
    )

    remaining_cost_after_revenue = max(
        annual_ai_cost - annual_extra_revenue,
        0,
    )

    if realized_value_per_case > 0:
        break_even_cases = (
            remaining_cost_after_revenue / realized_value_per_case
        )
    elif remaining_cost_after_revenue == 0:
        break_even_cases = 0
    else:
        break_even_cases = None

    return {
        "annual_cases": annual_cases,
        "minutes_saved": minutes_saved,
        "hourly_labor_cost": hourly_labor_cost,
        "realization_rate": realization_rate,
        "initial_cost": initial_cost,
        "annual_ai_cost": annual_ai_cost,
        "annual_extra_revenue": annual_extra_revenue,
        "hours_saved": hours_saved,
        "theoretical_labor_value": theoretical_labor_value,
        "realized_labor_value": realized_labor_value,
        "total_annual_benefit": total_annual_benefit,
        "annual_net_benefit": annual_net_benefit,
        "first_year_roi": first_year_roi,
        "steady_state_roi": steady_state_roi,
        "payback_years": payback_years,
        "break_even_cases": break_even_cases,
    }


def calculate_scenarios(
    annual_cases: float,
    minutes_saved: float,
    hourly_labor_cost: float,
    realization_rate: float,
    initial_cost: float,
    annual_ai_cost: float,
    annual_extra_revenue: float,
) -> pd.DataFrame:
    """
    產生保守、基準與樂觀三種情境。

    這些倍率是本專案的分析假設，不代表真實醫院數據。
    """

    scenarios = {
        "保守情境": {
            "case_multiplier": 0.85,
            "time_multiplier": 0.70,
            "realization_multiplier": 0.70,
            "revenue_multiplier": 0.50,
            "annual_cost_multiplier": 1.15,
        },
        "基準情境": {
            "case_multiplier": 1.00,
            "time_multiplier": 1.00,
            "realization_multiplier": 1.00,
            "revenue_multiplier": 1.00,
            "annual_cost_multiplier": 1.00,
        },
        "樂觀情境": {
            "case_multiplier": 1.10,
            "time_multiplier": 1.25,
            "realization_multiplier": 1.15,
            "revenue_multiplier": 1.30,
            "annual_cost_multiplier": 0.95,
        },
    }

    rows = []

    for scenario_name, multipliers in scenarios.items():
        adjusted_realization_rate = min(
            realization_rate
            * multipliers["realization_multiplier"],
            1.0,
        )

        result = calculate_financials(
            annual_cases=annual_cases
            * multipliers["case_multiplier"],
            minutes_saved=minutes_saved
            * multipliers["time_multiplier"],
            hourly_labor_cost=hourly_labor_cost,
            realization_rate=adjusted_realization_rate,
            initial_cost=initial_cost,
            annual_ai_cost=annual_ai_cost
            * multipliers["annual_cost_multiplier"],
            annual_extra_revenue=annual_extra_revenue
            * multipliers["revenue_multiplier"],
        )

        rows.append(
            {
                "情境": scenario_name,
                "年案件量": round(result["annual_cases"]),
                "每件節省分鐘": round(
                    result["minutes_saved"],
                    2,
                ),
                "工時效益實現率": (
                    f"{result['realization_rate'] * 100:.0f}%"
                ),
                "年度總效益": round(
                    result["total_annual_benefit"],
                ),
                "年度淨效益": round(
                    result["annual_net_benefit"],
                ),
                "首年 ROI": (
                    f"{result['first_year_roi']:.1f}%"
                    if result["first_year_roi"] is not None
                    else "無法計算"
                ),
                "回收期": (
                    f"{result['payback_years']:.2f} 年"
                    if result["payback_years"] is not None
                    else "無法回收"
                ),
            }
        )

    return pd.DataFrame(rows)


def calculate_feasibility_score(
    clinical_need: int,
    financial_value: int,
    data_readiness: int,
    regulatory_readiness: int,
    integration_readiness: int,
    user_acceptance: int,
) -> dict[str, Any]:
    """
    依自訂權重計算商業可行性分數。
    """

    weights = {
        "臨床或營運需求": 0.20,
        "財務效益潛力": 0.25,
        "資料準備程度": 0.15,
        "法規與倫理可行性": 0.15,
        "院內系統整合": 0.15,
        "使用者接受度": 0.10,
    }

    scores = {
        "臨床或營運需求": clinical_need,
        "財務效益潛力": financial_value,
        "資料準備程度": data_readiness,
        "法規與倫理可行性": regulatory_readiness,
        "院內系統整合": integration_readiness,
        "使用者接受度": user_acceptance,
    }

    weighted_score = sum(
        scores[name] / 5 * 100 * weight
        for name, weight in weights.items()
    )

    minimum_score = min(scores.values())

    lowest_dimensions = [
        name
        for name, score in scores.items()
        if score == minimum_score
    ]

    # 限制條件：
    # 即使總分高，只要資料或法規準備程度太低，
    # 也不應直接建議試辦。
    critical_readiness = min(
        data_readiness,
        regulatory_readiness,
    )

    if weighted_score < 50:
        recommendation = "暫不建議"
    elif weighted_score >= 75 and critical_readiness >= 3:
        recommendation = "建議小規模試辦"
    else:
        recommendation = "建議進一步研究"

    return {
        "weights": weights,
        "scores": scores,
        "weighted_score": weighted_score,
        "lowest_dimensions": lowest_dimensions,
        "recommendation": recommendation,
    }


def format_currency(value: float) -> str:
    return f"NT$ {value:,.0f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "無法計算"

    if value == float("inf"):
        return "正效益且無年度系統費用"

    return f"{value:,.1f}%"


def generate_prompt(
    inputs: dict[str, Any],
    financials: dict[str, Any],
    feasibility: dict[str, Any],
    scenario_df: pd.DataFrame,
) -> str:
    scenario_text = scenario_df.to_string(index=False)

    score_text = "\n".join(
        f"- {name}：{score}/5"
        for name, score in feasibility["scores"].items()
    )

    return f"""
你是一名協助民間醫院進行醫療 AI 商業模式與投資可行性分析的研究助理。

你的任務不是設計醫療 AI 模型，也不是提供醫療診斷，而是協助院方判斷：
1. 這個應用是否可能降低成本。
2. 是否可能提升醫療或行政效率。
3. 是否可能創造額外收入。
4. 是否具備資料、法規、臨床和系統整合條件。
5. 下一步應該研究、試辦，還是暫緩。

請根據以下資料完成分析。

【基本資料】
- 醫療 AI 應用：{inputs["topic"]}
- 院方主要目標：{inputs["analysis_goal"]}
- 導入方式偏好：{inputs["deployment_preference"]}
- 評分信心程度：{inputs["confidence_level"]}
- 評分依據：{inputs["score_evidence"] or "使用者尚未提供具體依據"}

【院方輸入假設】
- 每年案件量：{financials["annual_cases"]:,.0f} 件
- 每件預估節省時間：{financials["minutes_saved"]:.2f} 分鐘
- 相關人員平均每小時成本：{format_currency(financials["hourly_labor_cost"])}
- 節省工時的效益實現率：{financials["realization_rate"] * 100:.0f}%
- 一次性導入成本：{format_currency(financials["initial_cost"])}
- AI 系統年度費用：{format_currency(financials["annual_ai_cost"])}
- 預估年度新增收入：{format_currency(financials["annual_extra_revenue"])}

【基準情境計算】
- 每年節省工時：{financials["hours_saved"]:,.0f} 小時
- 理論工時價值：{format_currency(financials["theoretical_labor_value"])}
- 實際認列工時效益：{format_currency(financials["realized_labor_value"])}
- 年度總效益：{format_currency(financials["total_annual_benefit"])}
- 年度淨效益：{format_currency(financials["annual_net_benefit"])}
- 首年 ROI：{format_percent(financials["first_year_roi"])}
- 後續年度 ROI：{format_percent(financials["steady_state_roi"])}
- 回收期：{
        f'{financials["payback_years"]:.2f} 年'
        if financials["payback_years"] is not None
        else '目前無法回收'
    }
- 年度損益兩平案件量：{
        f'{financials["break_even_cases"]:,.0f} 件'
        if financials["break_even_cases"] is not None
        else '目前無法計算'
    }

【三情境比較】
{scenario_text}

【可行性主觀評分】
{score_text}

- 加權分數：{feasibility["weighted_score"]:.0f}/100
- 目前主要短板：{"、".join(feasibility["lowest_dimensions"])}
- 規則式建議：{feasibility["recommendation"]}

請使用繁體中文，依照以下結構回答：

## 一、決策摘要
用四至六句話說明：
- 目前最可能成立的價值
- 最大不確定性
- 最重要的限制
- 初步建議

## 二、應用情境與價值主張
說明：
- 主要使用者
- 涉及的院內部門
- 使用流程
- 欲解決的臨床或營運問題
- 院方為何可能願意投入

## 三、財務試算解讀
解釋基準情境結果，並明確區分：
- 使用者輸入的假設
- 程式依公式計算的結果
- 尚未經院內資料驗證的推論

必須特別提醒：
節省工時不一定等於現金成本下降，也可能轉化為提高案件量、減少加班、縮短等待時間或改善品質。

## 四、三情境比較
比較保守、基準、樂觀情境。
說明在哪些條件下：
- 方案可能無法回收
- 方案接近損益兩平
- 方案具有合理投資價值

不得把樂觀情境視為必然結果。

## 五、降低成本與提升效率
分別分析：
- 人力與時間
- 工作流程
- 資源與設備利用
- 等待時間
- 服務案件量
- 可能新增的隱性成本

不得在沒有證據時宣稱 AI 必然降低誤診、醫療糾紛或重複檢查。

## 六、創造額外收入
將收入機會分成：
1. 近期較可行
2. 需要進一步驗證
3. 高度推測

分析可能的：
- 自費服務
- 服務量增加
- 研究合作
- 廠商共同開發
- 技術或成果授權

除非具有智慧財產權、共同開發或契約基礎，
不得直接假設醫院可以把外購 AI 技術授權給其他醫院。

## 七、商業模式選項
提出三種不同模式，例如：
- 軟體訂閱或按量付費
- 院內部署與授權
- 醫院與廠商共同試辦或共同開發

每種模式都要說明：
- 付費者
- 價值來源
- 收入或節省來源
- 成本結構
- 醫院投入
- 資料與智慧財產權問題
- 優點
- 風險
- 適合階段

## 八、可行性評分解讀
分析六項評分：
- 哪些構面較強
- 哪些構面較弱
- 哪些分數可能只是主觀判斷
- 目前最應優先改善的構面

如果評分信心程度偏低，
必須降低對總分的依賴。

## 九、法規、資料與落地限制
分析：
- 資料品質與代表性
- 個人資料與倫理
- 資料使用權與契約
- 醫療器材或軟體法規路徑
- 本地臨床驗證
- PACS、HIS、EMR 整合
- 資訊安全
- 系統停機與責任歸屬
- 醫護人員接受度

不得自行宣稱特定產品已取得任何法規核可。

## 十、敏感度分析
找出最可能改變決策的三至五項變數。
說明每項變數若被高估或低估，會怎樣影響 ROI、回收期或導入建議。

## 十一、正式決策前需蒐集的資料
列出七至十項具體資料。
每項都要說明：
- 資料來源
- 用來驗證什麼假設
- 對決策有何影響

## 十二、建議的試辦設計
若適合進一步研究或試辦，提出一個小規模方案，包括：
- 試辦範圍
- 期間
- 對照方式
- KPI
- 停止條件
- 成功後的擴大條件

## 十三、初步建議
只能從以下三項選擇一項：
- 暫不建議
- 建議進一步研究
- 建議小規模試辦

比較你的分析與規則式建議是否一致。
若不一致，必須說明原因。

最後以粗體顯示：
**最終初步建議：上述三項之一**

重要規則：
1. 不提供個人醫療建議或診斷。
2. 不虛構醫院、市場、產品或法規資料。
3. 所有使用者輸入數字都要稱為「假設」。
4. 所有尚未確認的效益都要標示「需要驗證」。
5. 不得因為總分高就忽略資料或法規短板。
6. 這只是初步商業分析，不是正式醫療、財務、法律或法規判定。
"""


def call_openai(prompt: str) -> str:
    if not API_KEY:
        raise ValueError(
            "找不到 OPENAI_API_KEY，請檢查 .env 檔案。"
        )

    client = OpenAI(api_key=API_KEY)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


# =========================================================
# 頁面內容
# =========================================================

st.title("🏥 醫療 AI 商業可行性分析 Agent")

st.write(
    "協助醫院從降本、增效、創收、資料、法規與落地條件，"
    "初步評估一項醫療 AI 應用是否值得進一步研究或試辦。"
)

st.info(
    "本工具中的金額、效益、評分與情境皆為使用者輸入或專案自訂假設，"
    "不代表真實醫院資料或正式決策。"
)


# =========================================================
# 輸入表單
# =========================================================

with st.form("feasibility_form"):
    st.subheader("一、專案基本資料")

    topic = st.text_input(
        "醫療 AI 應用主題",
        value="AI 輔助胸部 X 光判讀",
    )

    basic_col1, basic_col2 = st.columns(2)

    with basic_col1:
        analysis_goal = st.selectbox(
            "院方主要分析目標",
            [
                "綜合評估",
                "降低營運成本",
                "提升醫療與行政效率",
                "創造額外收入",
            ],
        )

    with basic_col2:
        deployment_preference = st.selectbox(
            "目前偏好的導入方式",
            [
                "尚未決定",
                "雲端訂閱",
                "按使用量付費",
                "院內部署",
                "與廠商共同試辦",
                "共同開發",
            ],
        )

    st.subheader("二、院方營運與財務假設")

    finance_col1, finance_col2 = st.columns(2)

    with finance_col1:
        annual_cases = st.number_input(
            "每年案件量",
            min_value=0,
            value=100000,
            step=1000,
        )

        minutes_saved = st.number_input(
            "每件預估節省時間（分鐘）",
            min_value=0.0,
            value=1.0,
            step=0.1,
        )

        hourly_labor_cost = st.number_input(
            "相關人員平均每小時成本（元）",
            min_value=0,
            value=1200,
            step=100,
        )

        realization_percent = st.slider(
            "節省工時的效益實現率",
            min_value=0,
            max_value=100,
            value=50,
            step=5,
            help=(
                "節省的時間不一定能全部轉化為現金節省。"
                "例如可能只是增加處理量、減少加班或縮短等待時間。"
            ),
        )

    with finance_col2:
        initial_cost = st.number_input(
            "一次性導入成本（元）",
            min_value=0,
            value=2000000,
            step=100000,
        )

        annual_ai_cost = st.number_input(
            "AI 系統年度費用（元）",
            min_value=0,
            value=1500000,
            step=100000,
        )

        annual_extra_revenue = st.number_input(
            "預估年度新增收入（元）",
            min_value=0,
            value=0,
            step=100000,
        )

    st.subheader("三、商業可行性評分假設")

    st.caption(
        "請依目前掌握的資訊評分。1 分代表條件很弱，"
        "5 分代表條件相對成熟。"
    )

    score_col1, score_col2 = st.columns(2)

    with score_col1:
        clinical_need = st.slider(
            "臨床或營運需求強度",
            1,
            5,
            3,
        )

        financial_value = st.slider(
            "財務效益潛力",
            1,
            5,
            3,
        )

        data_readiness = st.slider(
            "資料準備程度",
            1,
            5,
            3,
        )

    with score_col2:
        regulatory_readiness = st.slider(
            "法規與倫理可行性",
            1,
            5,
            3,
        )

        integration_readiness = st.slider(
            "院內系統整合可行性",
            1,
            5,
            3,
        )

        user_acceptance = st.slider(
            "醫護與使用者接受度",
            1,
            5,
            3,
        )

    confidence_level = st.selectbox(
        "目前評分的信心程度",
        [
            "低：多數為初步推測",
            "中：已有部分訪談或資料",
            "高：已有院內數據或試辦結果",
        ],
    )

    score_evidence = st.text_area(
        "評分依據或目前掌握的資訊",
        placeholder=(
            "例如：已有放射科醫師訪談、院內年案件量統計、"
            "廠商報價或初步系統整合評估。"
        ),
        height=100,
    )

    submitted = st.form_submit_button(
        "開始分析",
        type="primary",
        use_container_width=True,
    )


# =========================================================
# 送出後計算
# =========================================================

if submitted:
    if not topic.strip():
        st.error("請先輸入醫療 AI 應用主題。")
        st.stop()

    realization_rate = realization_percent / 100

    financials = calculate_financials(
        annual_cases=annual_cases,
        minutes_saved=minutes_saved,
        hourly_labor_cost=hourly_labor_cost,
        realization_rate=realization_rate,
        initial_cost=initial_cost,
        annual_ai_cost=annual_ai_cost,
        annual_extra_revenue=annual_extra_revenue,
    )

    scenario_df = calculate_scenarios(
        annual_cases=annual_cases,
        minutes_saved=minutes_saved,
        hourly_labor_cost=hourly_labor_cost,
        realization_rate=realization_rate,
        initial_cost=initial_cost,
        annual_ai_cost=annual_ai_cost,
        annual_extra_revenue=annual_extra_revenue,
    )

    feasibility = calculate_feasibility_score(
        clinical_need=clinical_need,
        financial_value=financial_value,
        data_readiness=data_readiness,
        regulatory_readiness=regulatory_readiness,
        integration_readiness=integration_readiness,
        user_acceptance=user_acceptance,
    )

    inputs = {
        "topic": topic,
        "analysis_goal": analysis_goal,
        "deployment_preference": deployment_preference,
        "confidence_level": confidence_level,
        "score_evidence": score_evidence,
    }

    result = {
        "inputs": inputs,
        "financials": financials,
        "scenario_df": scenario_df,
        "feasibility": feasibility,
    }

    st.session_state.last_result = result

    prompt = generate_prompt(
        inputs=inputs,
        financials=financials,
        feasibility=feasibility,
        scenario_df=scenario_df,
    )

    try:
        with st.spinner(
            "正在計算情境並產生商業可行性分析……"
        ):
            report = call_openai(prompt)

        st.session_state.analysis_report = report

    except Exception as error:
        st.session_state.analysis_report = ""
        st.error("呼叫 AI 時發生錯誤。")
        st.code(str(error))


# =========================================================
# 顯示結果
# =========================================================

if st.session_state.last_result is not None:
    result = st.session_state.last_result
    financials = result["financials"]
    feasibility = result["feasibility"]
    scenario_df = result["scenario_df"]

    st.divider()
    st.header("分析結果")

    st.subheader("商業可行性評分")

    score_metric1, score_metric2, score_metric3 = st.columns(3)

    score_metric1.metric(
        "加權可行性分數",
        f"{feasibility['weighted_score']:.0f} / 100",
    )

    score_metric2.metric(
        "目前主要短板",
        "、".join(feasibility["lowest_dimensions"]),
    )

    score_metric3.metric(
        "規則式初步建議",
        feasibility["recommendation"],
    )

    st.progress(
        min(
            max(int(feasibility["weighted_score"]), 0),
            100,
        )
    )

    st.caption(
        "此分數依專案自訂權重及使用者主觀輸入計算，"
        "不能取代院內資料、法規或臨床評估。"
    )

    st.subheader("基準情境財務試算")

    metric1, metric2, metric3, metric4 = st.columns(4)

    metric1.metric(
        "年度節省工時",
        f"{financials['hours_saved']:,.0f} 小時",
    )

    metric2.metric(
        "實際認列工時效益",
        format_currency(
            financials["realized_labor_value"]
        ),
        help=(
            "理論工時價值乘上使用者設定的效益實現率。"
        ),
    )

    metric3.metric(
        "年度淨效益",
        format_currency(
            financials["annual_net_benefit"]
        ),
    )

    metric4.metric(
        "首年 ROI",
        format_percent(
            financials["first_year_roi"]
        ),
    )

    detail_col1, detail_col2, detail_col3 = st.columns(3)

    with detail_col1:
        st.write("**後續年度 ROI**")
        st.write(
            format_percent(
                financials["steady_state_roi"]
            )
        )

    with detail_col2:
        st.write("**導入成本回收期**")

        if financials["payback_years"] is not None:
            st.write(
                f"{financials['payback_years']:.2f} 年"
            )
        else:
            st.write("目前年度淨效益不足，無法回收")

    with detail_col3:
        st.write("**年度損益兩平案件量**")

        if financials["break_even_cases"] is not None:
            st.write(
                f"{financials['break_even_cases']:,.0f} 件"
            )
        else:
            st.write("目前無法計算")

    if financials["annual_net_benefit"] <= 0:
        st.warning(
            "依目前基準假設，年度效益不足以支付年度 AI 成本。"
            "需要調整成本、案件量、節省時間或新增收入假設。"
        )

    st.caption(
        "節省工時不必然等於現金成本下降，也可能表現在增加服務量、"
        "減少加班、縮短等待時間或改善流程。"
    )

    st.subheader("保守／基準／樂觀三情境")

    display_df = scenario_df.copy()

    for column in ["年度總效益", "年度淨效益"]:
        display_df[column] = display_df[column].map(
            lambda value: f"NT$ {value:,.0f}"
        )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "情境倍率為本專案自訂假設，目的在測試決策對不同條件的敏感度，"
        "不代表未來一定會發生。"
    )

    if st.session_state.analysis_report:
        st.subheader("AI 商業可行性報告")

        st.markdown(
            st.session_state.analysis_report
        )

        report_text = (
            f"# 醫療 AI 商業可行性分析報告\n\n"
            f"分析主題：{result['inputs']['topic']}\n\n"
            f"{st.session_state.analysis_report}"
        )

        st.download_button(
            label="下載分析報告",
            data=report_text,
            file_name="醫療AI商業可行性分析報告.md",
            mime="text/markdown",
            use_container_width=True,
        )

    st.divider()

    st.caption(
        "本工具僅供醫療 AI 商業模式的初步研究與決策討論，"
        "不構成醫療、法律、法規、投資或財務建議。"
    )