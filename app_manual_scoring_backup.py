import pandas as pd
import streamlit as st

from scoring import (
    SCORE_WEIGHTS,
    calculate_feasibility_score,
    calculate_financials,
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
    "不提供醫療診斷或臨床治療建議。"
)


def format_currency(value: float) -> str:
    return f"NT$ {value:,.0f}"


with st.form("assessment_form"):
    st.header("一、專案基本資料")

    col1, col2 = st.columns(2)

    with col1:
        project_name = st.text_input(
            "專案名稱",
            value="急診胸部 X 光 AI 輔助判讀",
        )

        department = st.text_input(
            "導入科別",
            value="急診部、放射科",
        )

    with col2:
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
            "在急診導入胸部 X 光 AI，協助放射科與急診醫師"
            "優先辨識疑似氣胸、肺炎或其他高風險影像。"
        ),
        height=110,
    )

    st.divider()
    st.header("二、財務與營運數據")

    col3, col4, col5 = st.columns(3)

    with col3:
        monthly_cases = st.number_input(
            "每月案件數",
            min_value=0.0,
            value=3000.0,
            step=100.0,
        )

        minutes_saved = st.number_input(
            "每件預估節省時間（分鐘）",
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

    with col4:
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

    with col5:
        integration_cost = st.number_input(
            "一次性系統整合成本（元）",
            min_value=0.0,
            value=2_000_000.0,
            step=100_000.0,
        )

        annual_avoided_cost = st.number_input(
            "每年避免成本（元）",
            min_value=0.0,
            value=500_000.0,
            step=100_000.0,
        )

        annual_extra_revenue = st.number_input(
            "每年新增收入（元）",
            min_value=0.0,
            value=800_000.0,
            step=100_000.0,
        )

    st.divider()
    st.header("三、八面向可行性評分")

    st.caption("每項以 1 至 5 分評估，系統會依不同權重計算總分。")

    score_col1, score_col2 = st.columns(2)

    with score_col1:
        cost_saving = st.slider(
            "成本節省潛力",
            1,
            5,
            4,
        )

        efficiency = st.slider(
            "效率提升潛力",
            1,
            5,
            4,
        )

        revenue_growth = st.slider(
            "收入成長潛力",
            1,
            5,
            3,
        )

        clinical_value = st.slider(
            "臨床價值與風險改善",
            1,
            5,
            4,
        )

    with score_col2:
        data_readiness = st.slider(
            "資料準備程度",
            1,
            5,
            3,
        )

        integration_feasibility = st.slider(
            "系統整合可行性",
            1,
            5,
            3,
        )

        regulatory_control = st.slider(
            "法規與責任可控性",
            1,
            5,
            3,
        )

        clinical_adoption = st.slider(
            "臨床採用可行性",
            1,
            5,
            3,
        )

    st.divider()
    st.header("四、重大風險閘門")

    st.caption(
        "即使 ROI 很高，只要重大條件尚未具備，"
        "系統就不會直接建議全面導入。"
    )

    gate_col1, gate_col2 = st.columns(2)

    with gate_col1:
        has_clinical_owner = st.checkbox(
            "已有臨床負責人",
            value=True,
        )

        has_legal_data_basis = st.checkbox(
            "已確認資料使用與隱私治理依據",
            value=True,
        )

        has_integration_path = st.checkbox(
            "已確認 HIS／PACS／RIS／EMR 整合方式",
            value=False,
        )

    with gate_col2:
        has_baseline_metrics = st.checkbox(
            "已有現況基準與衡量指標",
            value=True,
        )

        has_human_oversight = st.checkbox(
            "已有人工覆核與異常處理流程",
            value=True,
        )

        certification_ready = st.checkbox(
            "已確認必要法規與產品認證",
            value=False,
        )

    submitted = st.form_submit_button(
        "開始評估",
        type="primary",
        use_container_width=True,
    )


if submitted:
    scores = {
        "cost_saving": cost_saving,
        "efficiency": efficiency,
        "revenue_growth": revenue_growth,
        "clinical_value": clinical_value,
        "data_readiness": data_readiness,
        "integration_feasibility": integration_feasibility,
        "regulatory_control": regulatory_control,
        "clinical_adoption": clinical_adoption,
    }

    financials = calculate_financials(
        monthly_cases=monthly_cases,
        minutes_saved_per_case=minutes_saved,
        hourly_labor_cost=hourly_labor_cost,
        adoption_rate=adoption_rate_percent / 100,
        annual_license_cost=annual_license_cost,
        annual_maintenance_cost=annual_maintenance_cost,
        one_time_integration_cost=integration_cost,
        annual_avoided_cost=annual_avoided_cost,
        annual_extra_revenue=annual_extra_revenue,
    )

    feasibility_score = calculate_feasibility_score(scores)

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

    result_col1, result_col2, result_col3, result_col4 = st.columns(4)

    with result_col1:
        st.metric(
            "可行性總分",
            f"{feasibility_score:.1f} / 100",
        )

    with result_col2:
        roi = financials["three_year_roi_percent"]

        st.metric(
            "三年 ROI",
            f"{roi:.1f}%" if roi is not None else "無法計算",
        )

    with result_col3:
        payback = financials["payback_months"]

        st.metric(
            "預估回本時間",
            f"{payback:.1f} 個月" if payback is not None else "無法回本",
        )

    with result_col4:
        st.metric(
            "重大風險數量",
            len(hard_gate_risks),
        )

    st.subheader("財務摘要")

    finance_col1, finance_col2, finance_col3 = st.columns(3)

    with finance_col1:
        st.metric(
            "年度人力節省",
            format_currency(financials["annual_labor_savings"]),
        )

        st.metric(
            "年度總效益",
            format_currency(financials["annual_total_benefit"]),
        )

    with finance_col2:
        st.metric(
            "第一年總成本",
            format_currency(financials["first_year_total_cost"]),
        )

        st.metric(
            "第一年淨效益",
            format_currency(financials["first_year_net_benefit"]),
        )

    with finance_col3:
        st.metric(
            "三年總成本",
            format_currency(financials["three_year_total_cost"]),
        )

        st.metric(
            "三年淨效益",
            format_currency(financials["three_year_net_benefit"]),
        )

    st.subheader("八面向評分")

    score_labels = {
        "cost_saving": "成本節省",
        "efficiency": "效率提升",
        "revenue_growth": "收入成長",
        "clinical_value": "臨床價值",
        "data_readiness": "資料準備",
        "integration_feasibility": "系統整合",
        "regulatory_control": "法規可控",
        "clinical_adoption": "臨床採用",
    }

    score_data = pd.DataFrame(
        {
            "面向": [
                score_labels[item]
                for item in SCORE_WEIGHTS
            ],
            "分數": [
                scores[item]
                for item in SCORE_WEIGHTS
            ],
        }
    )

    st.bar_chart(
        score_data.set_index("面向"),
        y="分數",
        horizontal=True,
    )

    st.subheader("重大風險")

    if hard_gate_risks:
        for risk in hard_gate_risks:
            st.warning(risk)
    else:
        st.success("目前沒有觸發重大風險閘門。")

    st.subheader("專案摘要")

    st.markdown(
        f"""
**專案名稱：** {project_name}  
**導入科別：** {department}  
**AI 應用類型：** {ai_type}  
**導入模式：** {implementation_model}  

**應用情境：**  
{use_case}
"""
    )
