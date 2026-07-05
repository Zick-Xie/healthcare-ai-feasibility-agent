import pandas as pd
import streamlit as st

from ai_report import generate_management_report
from assessment_rules import calculate_automatic_scores
from scenario_analysis import (
    SCENARIO_ASSUMPTIONS,
    calculate_scenarios,
)
from scoring import (
    SCORE_WEIGHTS,
    calculate_feasibility_score,
    check_hard_gates,
    make_decision,
)


st.set_page_config(
    page_title="Hospital AI Value Assessment Agent",
    page_icon="🏥",
    layout="wide",
)

st.title("🏥 Hospital AI Value Assessment Agent")
st.caption("醫療 AI 商業價值、導入可行性與風險評估工具")

st.info(
    "本工具用於醫療 AI 專案的商業與導入可行性初評，"
    "不提供醫療診斷或治療建議。"
)


SCORE_LABELS = {
    "cost_saving": "成本節省潛力",
    "efficiency": "效率提升潛力",
    "revenue_growth": "收入成長潛力",
    "clinical_value": "臨床價值與風險改善",
    "data_readiness": "資料準備程度",
    "integration_feasibility": "系統整合可行性",
    "regulatory_control": "法規與責任可控性",
    "clinical_adoption": "臨床採用可行性",
}


if "assessment_result" not in st.session_state:
    st.session_state.assessment_result = None

if "ai_management_report" not in st.session_state:
    st.session_state.ai_management_report = None


def format_currency(value: float) -> str:
    return f"NT$ {value:,.0f}"


def level_select(
    label: str,
    descriptions: list[str],
    default_level: int = 3,
) -> int:
    selected = st.selectbox(
        label,
        descriptions,
        index=default_level - 1,
    )

    return descriptions.index(selected) + 1


with st.form("assessment_form"):
    st.header("一、專案基本資料")

    basic_col1, basic_col2 = st.columns(2)

    with basic_col1:
        project_name = st.text_input(
            "專案名稱",
            value="急診胸部 X 光 AI 輔助判讀",
        )

        department = st.text_input(
            "導入科別",
            value="急診部、放射科",
        )

    with basic_col2:
        ai_type = st.selectbox(
            "AI 應用類型",
            [
                "醫療影像",
                "臨床決策支援",
                "病歷摘要與生成式 AI",
                "行政流程自動化",
                "病床與排程管理",
                "患者服務",
                "其他",
            ],
        )

        implementation_model = st.selectbox(
            "導入模式",
            [
                "購買現成產品",
                "與廠商共同開發",
                "醫院自行開發",
            ],
        )

    use_case = st.text_area(
        "應用情境",
        value=(
            "在急診導入胸部 X 光 AI，協助急診與放射科醫師"
            "優先辨識疑似氣胸、肺炎或其他高風險影像。"
        ),
        height=110,
    )

    st.divider()
    st.header("二、現況與財務數據")

    finance_col1, finance_col2, finance_col3 = st.columns(3)

    with finance_col1:
        monthly_cases = st.number_input(
            "每月案件數",
            min_value=0.0,
            value=3000.0,
            step=100.0,
        )

        baseline_minutes = st.number_input(
            "目前每件案件處理時間（分鐘）",
            min_value=0.0,
            value=25.0,
            step=1.0,
        )

        minutes_saved = st.number_input(
            "導入後每件預估節省時間（分鐘）",
            min_value=0.0,
            value=8.0,
            step=1.0,
        )

        hourly_labor_cost = st.number_input(
            "每小時人力成本（元）",
            min_value=0.0,
            value=1200.0,
            step=100.0,
        )

    with finance_col2:
        adoption_rate_percent = st.slider(
            "預估實際採用率",
            min_value=0,
            max_value=100,
            value=70,
            step=5,
            format="%d%%",
        )

        annual_license_cost = st.number_input(
            "每年軟體授權費（元）",
            min_value=0.0,
            value=1_500_000.0,
            step=100_000.0,
        )

        annual_maintenance_cost = st.number_input(
            "每年維護成本（元）",
            min_value=0.0,
            value=300_000.0,
            step=100_000.0,
        )

        integration_cost = st.number_input(
            "一次性系統整合成本（元）",
            min_value=0.0,
            value=2_000_000.0,
            step=100_000.0,
        )

    with finance_col3:
        annual_avoided_cost = st.number_input(
            "每年可避免的其他成本（元）",
            min_value=0.0,
            value=500_000.0,
            step=100_000.0,
        )

        revenue_is_objective = st.checkbox(
            "創造額外收入是此專案的主要目標",
            value=True,
        )

        annual_extra_revenue = st.number_input(
            "每年預估新增收入（元）",
            min_value=0.0,
            value=800_000.0,
            step=100_000.0,
            disabled=not revenue_is_objective,
        )

    st.divider()
    st.header("三、導入成熟度問卷")

    st.caption(
        "系統會根據財務數據與下列答案，自動產生八面向評分。"
    )

    maturity_col1, maturity_col2 = st.columns(2)

    with maturity_col1:
        clinical_impact_level = level_select(
            "臨床影響程度",
            [
                "1｜幾乎不影響臨床品質或風險",
                "2｜僅改善少部分非關鍵流程",
                "3｜可改善一般臨床效率或品質",
                "4｜可明顯改善重要臨床流程",
                "5｜可改善重大病人安全或醫療風險",
            ],
            default_level=4,
        )

        evidence_level = level_select(
            "產品或技術的證據成熟度",
            [
                "1｜只有概念，尚無驗證資料",
                "2｜只有內部測試或小型案例",
                "3｜已有初步臨床研究或外部案例",
                "4｜已有多中心研究或穩定實際案例",
                "5｜已有充分實證與長期真實世界資料",
            ],
            default_level=3,
        )

        data_readiness_level = level_select(
            "醫院資料準備程度",
            [
                "1｜尚未確認資料是否存在",
                "2｜有資料，但分散且尚未整理",
                "3｜資料已結構化，可進行初步使用",
                "4｜已有標註、品質檢查與存取流程",
                "5｜已有穩定且持續更新的資料管線",
            ],
            default_level=3,
        )

    with maturity_col2:
        integration_level = level_select(
            "系統整合成熟度",
            [
                "1｜尚未盤點需要整合的系統",
                "2｜知道目標系統，但尚未確認介面",
                "3｜已確認 API、HL7 或 DICOM 等方式",
                "4｜已完成技術測試或測試環境串接",
                "5｜已有正式整合經驗與維護流程",
            ],
            default_level=2,
        )

        regulatory_level = level_select(
            "法規與責任準備程度",
            [
                "1｜尚未判斷是否涉及醫療器材或法規",
                "2｜已初步盤點，但責任與認證尚不明確",
                "3｜已確認主要法規要求與責任分工",
                "4｜產品已有所需認證並完成院內審查規劃",
                "5｜已完成必要認證、審查與持續監測制度",
            ],
            default_level=2,
        )

        adoption_level = level_select(
            "臨床採用準備程度",
            [
                "1｜尚未確認實際使用者",
                "2｜已確認使用者，但尚未參與設計",
                "3｜已有臨床代表參與需求討論",
                "4｜已完成流程測試、教育訓練規劃",
                "5｜已有正式支持、負責人與持續改善機制",
            ],
            default_level=3,
        )

    st.divider()
    st.header("四、重大風險閘門")

    gate_col1, gate_col2 = st.columns(2)

    with gate_col1:
        has_clinical_owner = st.checkbox(
            "已有明確臨床負責人",
            value=True,
        )

        has_legal_data_basis = st.checkbox(
            "已確認資料使用、隱私與授權依據",
            value=True,
        )

        has_integration_path = st.checkbox(
            "已確認 HIS／PACS／RIS／EMR 整合路徑",
            value=False,
        )

    with gate_col2:
        has_baseline_metrics = st.checkbox(
            "已有可衡量導入前後差異的現況指標",
            value=True,
        )

        has_human_oversight = st.checkbox(
            "已有人工覆核與 AI 異常處理流程",
            value=True,
        )

        certification_ready = st.checkbox(
            "已確認必要的產品認證與法規要求",
            value=False,
        )

    submitted = st.form_submit_button(
        "開始自動評估",
        type="primary",
        use_container_width=True,
    )


if submitted:
    try:
        effective_extra_revenue = (
            annual_extra_revenue
            if revenue_is_objective
            else 0.0
        )

        project_info = {
            "project_name": project_name,
            "department": department,
            "ai_type": ai_type,
            "implementation_model": implementation_model,
            "use_case": use_case,
        }

        base_financial_inputs = {
            "monthly_cases": monthly_cases,
            "minutes_saved_per_case": minutes_saved,
            "hourly_labor_cost": hourly_labor_cost,
            "adoption_rate": adoption_rate_percent / 100,
            "annual_license_cost": annual_license_cost,
            "annual_maintenance_cost": annual_maintenance_cost,
            "one_time_integration_cost": integration_cost,
            "annual_avoided_cost": annual_avoided_cost,
            "annual_extra_revenue": effective_extra_revenue,
        }

        scenario_results = calculate_scenarios(
            base_financial_inputs
        )

        financials = scenario_results[
            "基準情境"
        ]["financials"]

        scores, score_reasons = calculate_automatic_scores(
            financials=financials,
            baseline_minutes_per_case=baseline_minutes,
            minutes_saved_per_case=minutes_saved,
            annual_avoided_cost=annual_avoided_cost,
            annual_extra_revenue=effective_extra_revenue,
            revenue_is_objective=revenue_is_objective,
            clinical_impact_level=clinical_impact_level,
            evidence_level=evidence_level,
            data_readiness_level=data_readiness_level,
            integration_level=integration_level,
            regulatory_level=regulatory_level,
            adoption_level=adoption_level,
        )

        feasibility_score = calculate_feasibility_score(
            scores
        )

        hard_gate_risks = check_hard_gates(
            has_clinical_owner=has_clinical_owner,
            has_legal_data_basis=has_legal_data_basis,
            has_integration_path=has_integration_path,
            has_baseline_metrics=has_baseline_metrics,
            has_human_oversight=has_human_oversight,
            certification_ready=certification_ready,
        )

        decision = make_decision(
            feasibility_score=feasibility_score,
            financials=financials,
            hard_gate_risks=hard_gate_risks,
        )

        project_info["feasibility_score"] = feasibility_score

        st.session_state.assessment_result = {
            "project_info": project_info,
            "base_financial_inputs": base_financial_inputs,
            "financials": financials,
            "scenario_results": scenario_results,
            "scores": scores,
            "score_reasons": score_reasons,
            "feasibility_score": feasibility_score,
            "hard_gate_risks": hard_gate_risks,
            "decision": decision,
        }

        st.session_state.ai_management_report = None

    except ValueError as error:
        st.error(f"輸入資料有誤：{error}")


result = st.session_state.assessment_result

if result is not None:
    project_info = result["project_info"]
    financials = result["financials"]
    scenario_results = result["scenario_results"]
    scores = result["scores"]
    score_reasons = result["score_reasons"]
    feasibility_score = result["feasibility_score"]
    hard_gate_risks = result["hard_gate_risks"]
    decision = result["decision"]

    st.divider()
    st.header("評估結果")

    if decision == "建議優先進入受控試點":
        st.success(f"### {decision}")
    elif decision in {
        "建議補充資料後進入受控試點",
        "建議補充資料後再評估",
    }:
        st.warning(f"### {decision}")
    else:
        st.error(f"### {decision}")

    result_col1, result_col2, result_col3, result_col4 = (
        st.columns(4)
    )

    result_col1.metric(
        "可行性總分",
        f"{feasibility_score:.1f} / 100",
    )

    roi = financials["three_year_roi_percent"]

    result_col2.metric(
        "基準情境三年 ROI",
        f"{roi:.1f}%" if roi is not None else "無法計算",
    )

    payback = financials["payback_months"]

    result_col3.metric(
        "基準情境回本時間",
        (
            f"{payback:.1f} 個月"
            if payback is not None
            else "無法回本"
        ),
    )

    result_col4.metric(
        "重大風險數量",
        len(hard_gate_risks),
    )

    st.subheader("基準情境財務摘要")

    finance_result_col1, finance_result_col2, finance_result_col3 = (
        st.columns(3)
    )

    finance_result_col1.metric(
        "年度人力節省",
        format_currency(
            financials["annual_labor_savings"]
        ),
    )

    finance_result_col1.metric(
        "年度總效益",
        format_currency(
            financials["annual_total_benefit"]
        ),
    )

    finance_result_col2.metric(
        "第一年總成本",
        format_currency(
            financials["first_year_total_cost"]
        ),
    )

    finance_result_col2.metric(
        "第一年淨效益",
        format_currency(
            financials["first_year_net_benefit"]
        ),
    )

    finance_result_col3.metric(
        "三年總成本",
        format_currency(
            financials["three_year_total_cost"]
        ),
    )

    finance_result_col3.metric(
        "三年淨效益",
        format_currency(
            financials["three_year_net_benefit"]
        ),
    )

    st.subheader("三情境財務分析")

    scenario_rows = []
    scenario_chart_rows = []

    for scenario_name, scenario_result in scenario_results.items():
        scenario_financials = scenario_result["financials"]

        scenario_roi = scenario_financials[
            "three_year_roi_percent"
        ]

        scenario_payback = scenario_financials[
            "payback_months"
        ]

        scenario_rows.append(
            {
                "情境": scenario_name,
                "年度總效益": format_currency(
                    scenario_financials[
                        "annual_total_benefit"
                    ]
                ),
                "第一年淨效益": format_currency(
                    scenario_financials[
                        "first_year_net_benefit"
                    ]
                ),
                "三年淨效益": format_currency(
                    scenario_financials[
                        "three_year_net_benefit"
                    ]
                ),
                "三年 ROI": (
                    f"{scenario_roi:.1f}%"
                    if scenario_roi is not None
                    else "無法計算"
                ),
                "預估回本時間": (
                    f"{scenario_payback:.1f} 個月"
                    if scenario_payback is not None
                    else "無法回本"
                ),
            }
        )

        scenario_chart_rows.append(
            {
                "情境": scenario_name,
                "第一年淨效益": scenario_financials[
                    "first_year_net_benefit"
                ],
                "三年淨效益": scenario_financials[
                    "three_year_net_benefit"
                ],
            }
        )

    st.dataframe(
        pd.DataFrame(scenario_rows),
        use_container_width=True,
        hide_index=True,
    )

    scenario_chart_dataframe = pd.DataFrame(
        scenario_chart_rows
    ).set_index("情境")

    st.bar_chart(scenario_chart_dataframe)

    conservative_financials = scenario_results[
        "保守情境"
    ]["financials"]

    conservative_first_year_net = conservative_financials[
        "first_year_net_benefit"
    ]

    conservative_roi = conservative_financials[
        "three_year_roi_percent"
    ]

    conservative_payback = conservative_financials[
        "payback_months"
    ]

    if conservative_first_year_net < 0:
        st.warning(
            "保守情境下第一年淨效益為負，"
            "代表專案可能面臨初期預算與現金流壓力。"
        )

    if (
        conservative_roi is not None
        and conservative_roi > 0
        and conservative_first_year_net < 0
    ):
        st.info(
            "保守情境第一年可能虧損，但三年 ROI 仍為正，"
            "代表專案可能具有長期價值，但需要較長回收期間。"
        )

    if (
        conservative_payback is not None
        and conservative_payback > 24
    ):
        st.warning(
            f"保守情境預估需 {conservative_payback:.1f} 個月回本，"
            "建議確認醫院是否能接受超過兩年的資金回收期。"
        )

    with st.expander("查看三情境假設"):
        assumption_rows = []

        for scenario_name, assumptions in (
            SCENARIO_ASSUMPTIONS.items()
        ):
            assumption_rows.append(
                {
                    "情境": scenario_name,
                    "案件量倍率": (
                        f"{assumptions['monthly_cases_multiplier']:.0%}"
                    ),
                    "節省時間倍率": (
                        f"{assumptions['minutes_saved_multiplier']:.0%}"
                    ),
                    "採用率倍率": (
                        f"{assumptions['adoption_rate_multiplier']:.0%}"
                    ),
                    "避免成本倍率": (
                        f"{assumptions['annual_avoided_cost_multiplier']:.0%}"
                    ),
                    "新增收入倍率": (
                        f"{assumptions['annual_extra_revenue_multiplier']:.0%}"
                    ),
                    "整合成本倍率": (
                        f"{assumptions['integration_cost_multiplier']:.0%}"
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(assumption_rows),
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "情境分析是根據透明假設進行的敏感度測試，"
            "不代表實際結果或保證報酬。"
        )

    st.subheader("八面向自動評分")

    score_rows = []

    for item in SCORE_WEIGHTS:
        score_rows.append(
            {
                "評估面向": SCORE_LABELS[item],
                "分數": scores[item],
                "權重": f"{SCORE_WEIGHTS[item]}%",
                "評分原因": score_reasons[item],
            }
        )

    score_dataframe = pd.DataFrame(score_rows)

    st.dataframe(
        score_dataframe,
        use_container_width=True,
        hide_index=True,
    )

    st.bar_chart(
        score_dataframe[
            ["評估面向", "分數"]
        ].set_index("評估面向")
    )

    st.subheader("重大風險")

    if hard_gate_risks:
        for risk in hard_gate_risks:
            st.warning(risk)
    else:
        st.success("目前沒有觸發重大風險閘門。")

    st.divider()
    st.header("AI 管理層報告")

    st.caption(
        "AI 僅負責解讀既有計算結果，不會修改 ROI、"
        "可行性分數、重大風險或規則引擎決策。"
    )

    generate_report = st.button(
        "產生 AI 管理層報告",
        type="primary",
        use_container_width=True,
    )

    if generate_report:
        with st.spinner("正在整理管理層摘要與試點建議……"):
            try:
                st.session_state.ai_management_report = (
                    generate_management_report(
                        project_info=project_info,
                        financials=financials,
                        scenario_results=scenario_results,
                        scores=scores,
                        score_reasons=score_reasons,
                        hard_gate_risks=hard_gate_risks,
                        decision=decision,
                    )
                )

            except Exception as error:
                st.error(
                    "AI 報告產生失敗，請檢查 API key、"
                    "API 額度或網路狀態。"
                )
                st.exception(error)

    report = st.session_state.ai_management_report

    if report:
        st.success("AI 管理層報告已完成")
        st.markdown(report)

        st.download_button(
            label="下載管理層報告（Markdown）",
            data=report,
            file_name="hospital_ai_management_report.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with st.expander("查看專案輸入摘要"):
        st.markdown(
            f"""
**專案名稱：** {project_info["project_name"]}

**導入科別：** {project_info["department"]}

**AI 應用類型：** {project_info["ai_type"]}

**導入模式：** {project_info["implementation_model"]}

**應用情境：**

{project_info["use_case"]}
"""
        )

    if st.button(
        "清除本次評估結果",
        use_container_width=True,
    ):
        st.session_state.assessment_result = None
        st.session_state.ai_management_report = None
        st.rerun()
