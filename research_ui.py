import json
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from research_agent import (
    TASK_CONFIGS,
    ResearchAgentError,
    load_research_snapshot,
    run_next_incomplete_task,
    run_research_task,
)


PRESET_CASES = {
    "案例一｜急診胸部 X 光 AI": (
        "評估林口長庚醫院在急診與放射科導入胸部 X 光 AI，"
        "用於輔助判讀與高風險病例優先排序的台灣法規成熟度、"
        "台灣醫院採用、台灣臨床證據、可取得產品、商業模式與系統整合需求。"
    ),
    "案例二｜住院病歷摘要生成式 AI": (
        "評估林口長庚醫院導入住院病歷摘要生成式 AI，"
        "協助醫師整理病程紀錄、出院摘要與住院資料的台灣法規、"
        "醫院採用、台灣臨床證據、可取得產品、幻覺與個資風險、"
        "商業模式及 EMR 整合需求。"
    ),
    "案例三｜門診預約與客服 AI": (
        "評估林口長庚醫院導入門診預約與智慧客服 AI，"
        "用於預約修改、常見問題、就醫提醒與服務分流的台灣市場成熟度、"
        "醫院採用、可取得產品、個資治理、商業模式及院內系統整合需求。"
    ),
    "自訂台灣研究題目": "",
}


TASK_STATUS_LABELS = {
    "success": "完成",
    "cached": "快取完成",
    "stale_cache": "舊快取",
    "technical_failure": "技術性未完成",
    "not_started": "尚未執行",
}


def load_selected_case() -> None:
    selected = st.session_state.tw_research_case_selector
    if selected != "自訂台灣研究題目":
        st.session_state.tw_research_topic = PRESET_CASES[selected]
    else:
        st.session_state.tw_research_topic = ""
    st.session_state.tw_research_result = None


def build_source_map(result: Dict[str, Any]) -> Dict[str, str]:
    return {
        source["url"]: source.get("title", source["url"])
        for source in result.get("sources", [])
        if source.get("url")
    }


def show_source_links(
    urls: List[str],
    source_map: Dict[str, str],
) -> None:
    valid_urls = [url for url in urls if url]
    if not valid_urls:
        st.caption("此項目沒有可顯示的公開來源。")
        return

    for url in valid_urls:
        st.markdown(f"- [{source_map.get(url, url)}]({url})")


def show_findings(
    findings: List[Dict[str, Any]],
    source_map: Dict[str, str],
    empty_message: str,
) -> None:
    if not findings:
        st.caption(empty_message)
        return

    for index, finding in enumerate(findings, start=1):
        confidence = finding.get("confidence", "未標示")
        evidence_type = finding.get("evidence_type", "公開資料")
        with st.expander(
            f"{index}. {finding.get('claim', '研究發現')}｜可信度：{confidence}"
        ):
            st.write(f"證據類型：{evidence_type}")
            st.markdown("**來源**")
            show_source_links(finding.get("source_urls", []), source_map)


def render_task_status(result: Dict[str, Any]) -> None:
    rows = []
    for task in result.get("tasks", {}).values():
        rows.append(
            {
                "台灣研究任務": task.get("task_label", task.get("task_id", "")),
                "狀態": TASK_STATUS_LABELS.get(task.get("status"), task.get("status")),
                "資料來源數": len(task.get("sources", [])),
                "錯誤類型": task.get("error_type") or "—",
                "說明": task.get("warning")
                or task.get("error_message")
                or "研究任務已完成。",
            }
        )

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_maturity(result: Dict[str, Any]) -> None:
    maturity = result["taiwan_market_maturity"]

    st.subheader("台灣市場成熟度")

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric(
        "台灣證據覆蓋率",
        f"{maturity['coverage_percent']}%",
    )

    if maturity["overall_score"] is not None:
        metric_col2.metric(
            "正式成熟度",
            f"{maturity['overall_score']:.2f} / 5",
        )
    elif maturity["partial_score"] is not None:
        metric_col2.metric(
            "已完成面向暫定值",
            f"{maturity['partial_score']:.2f} / 5",
        )
    else:
        metric_col2.metric("成熟度", "無法計算")

    metric_col3.metric("市場階段", maturity["maturity_stage"])

    if not maturity["is_complete"]:
        st.warning(
            "台灣研究任務尚未全部完成，因此不產生正式市場成熟度。"
            "暫定值只反映已完成的面向，不能直接用於林口長庚投資決策。"
        )

    dimension_rows = []
    for dimension in maturity["dimensions"].values():
        dimension_rows.append(
            {
                "評估面向": dimension["label"],
                "台灣成熟度": f"{dimension['score']} / 5",
                "權重": f"{dimension['weight']}%",
            }
        )

    if dimension_rows:
        st.dataframe(
            pd.DataFrame(dimension_rows),
            width="stretch",
            hide_index=True,
        )


def render_regulatory_task(
    task: Dict[str, Any],
    source_map: Dict[str, str],
) -> None:
    if task.get("result") is None:
        message = task.get("error_message", "法規研究尚未完成。")
        if task.get("status") == "not_started":
            st.info(message)
        else:
            st.error(message)
        return

    data = task["result"]
    st.write(data["executive_summary"])

    col1, col2 = st.columns(2)
    col1.metric("台灣法規成熟度", f"{data['regulatory_score']} / 5")
    col2.metric("可能屬醫療器材程度", data["medical_device_likelihood"])

    st.markdown(f"**評分理由：** {data['score_reason']}")
    st.markdown(f"**分類判斷：** {data['classification_reason']}")
    st.markdown(f"**TFDA 狀態摘要：** {data['tfda_status_summary']}")

    products = data.get("identified_tfda_products", [])
    if products:
        rows = [
            {
                "公司": item["company"],
                "產品": item["product"],
                "許可／登錄資訊": item["permit_or_listing"],
                "用途": item["intended_use"],
            }
            for item in products
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    show_findings(
        data.get("key_findings", []),
        source_map,
        "未整理出其他法規發現。",
    )

    with st.expander("法規研究整體來源"):
        show_source_links(data.get("source_urls", []), source_map)


def render_adoption_task(
    task: Dict[str, Any],
    source_map: Dict[str, str],
) -> None:
    if task.get("result") is None:
        message = task.get("error_message", "醫院採用研究尚未完成。")
        if task.get("status") == "not_started":
            st.info(message)
        else:
            st.error(message)
        return

    data = task["result"]
    st.write(data["executive_summary"])
    st.metric("台灣醫院採用成熟度", f"{data['hospital_adoption_score']} / 5")
    st.markdown(f"**評分理由：** {data['score_reason']}")

    st.markdown("### 長庚醫療體系公開證據")
    show_findings(
        data.get("chang_gung_findings", []),
        source_map,
        "未找到足夠可靠的長庚公開採用、試點或研究資料。",
    )

    st.markdown("### 其他台灣醫院公開證據")
    show_findings(
        data.get("other_taiwan_hospital_findings", []),
        source_map,
        "未找到足夠可靠的其他台灣醫院案例。",
    )

    st.markdown("### 採購、試點與合作線索")
    show_findings(
        data.get("procurement_or_pilot_findings", []),
        source_map,
        "未找到足夠可靠的採購或試點公開資料。",
    )

    with st.expander("醫院採用研究整體來源"):
        show_source_links(data.get("source_urls", []), source_map)


def render_clinical_task(
    task: Dict[str, Any],
    source_map: Dict[str, str],
) -> None:
    if task.get("result") is None:
        message = task.get("error_message", "臨床證據研究尚未完成。")
        if task.get("status") == "not_started":
            st.info(message)
        else:
            st.error(message)
        return

    data = task["result"]
    st.write(data["executive_summary"])

    col1, col2 = st.columns(2)
    col1.metric("台灣臨床證據成熟度", f"{data['clinical_evidence_score']} / 5")
    col2.metric("台灣驗證狀態", data["taiwan_validation_status"])
    st.markdown(f"**評分理由：** {data['score_reason']}")

    studies = data.get("studies", [])
    if studies:
        study_rows = [
            {
                "研究": study["title"],
                "機構／作者": study["institution_or_authors"],
                "研究類型": study["study_type"],
                "族群／資料集": study["population_or_dataset"],
                "主要結果": study["main_result"],
                "限制": study["limitation"],
            }
            for study in studies
        ]
        st.dataframe(pd.DataFrame(study_rows), width="stretch", hide_index=True)

        for study in studies:
            with st.expander(f"研究來源｜{study['title']}"):
                show_source_links(study.get("source_urls", []), source_map)

    show_findings(
        data.get("key_findings", []),
        source_map,
        "未整理出其他台灣臨床證據。",
    )

    with st.expander("臨床研究整體來源"):
        show_source_links(data.get("source_urls", []), source_map)


def render_market_task(
    task: Dict[str, Any],
    source_map: Dict[str, str],
) -> None:
    if task.get("result") is None:
        message = task.get("error_message", "產品與商業模式研究尚未完成。")
        if task.get("status") == "not_started":
            st.info(message)
        else:
            st.error(message)
        return

    data = task["result"]
    st.write(data["executive_summary"])

    col1, col2 = st.columns(2)
    col1.metric("台灣可取得產品成熟度", f"{data['product_availability_score']} / 5")
    col2.metric("商業模式成熟度", f"{data['business_model_score']} / 5")

    st.markdown(f"**產品評分理由：** {data['product_score_reason']}")
    st.markdown(f"**商業模式評分理由：** {data['business_score_reason']}")

    products = data.get("representative_products", [])
    if products:
        product_rows = [
            {
                "公司": product["company"],
                "產品": product["product"],
                "來源地": product["company_origin"],
                "用途": product["use_case"],
                "台灣可取得性": product["taiwan_availability"],
                "TFDA 狀態": product["tfda_status"],
                "商業模式": product["business_model"],
                "公開價格": product["public_pricing_status"],
                "優勢": "；".join(product.get("strengths", [])),
                "限制": "；".join(product.get("limitations", [])),
            }
            for product in products
        ]
        st.dataframe(pd.DataFrame(product_rows), width="stretch", hide_index=True)

        for product in products:
            with st.expander(f"產品來源｜{product['company']}｜{product['product']}"):
                show_source_links(product.get("source_urls", []), source_map)
    else:
        st.warning("未找到足夠可靠、可確認在台取得的代表產品資料。")

    st.markdown("### 對林口長庚可能涉及的整合需求")
    for item in data.get("integration_requirements", []):
        st.markdown(f"- {item}")

    show_findings(
        data.get("key_findings", []),
        source_map,
        "未整理出其他市場與商業模式發現。",
    )

    with st.expander("產品與商業模式研究整體來源"):
        show_source_links(data.get("source_urls", []), source_map)


def render_linkou_assessment(result: Dict[str, Any], source_map: Dict[str, str]) -> None:
    assessment = result["linkou_chang_gung_assessment"]

    st.subheader("林口長庚決策適用性")
    st.info(assessment["important_note"])
    st.markdown(f"**目前建議下一步：** {assessment['recommended_next_step']}")

    failures = assessment.get("technical_failures", [])
    if failures:
        st.error("尚有技術性未完成任務：" + "、".join(failures))

    st.markdown("### 長庚公開證據")
    show_findings(
        assessment.get("public_chang_gung_evidence", []),
        source_map,
        "目前未找到足夠可靠的長庚公開證據；這不代表院內沒有相關專案。",
    )

    st.markdown("### 正式決策仍需長庚院內提供")
    for item in assessment.get("internal_data_needed", []):
        st.markdown(f"- {item}")


def render_research_section() -> None:
    ui_version = "taiwan-single-task-v5"

    if st.session_state.get("tw_research_ui_version") != ui_version:
        st.session_state.tw_research_ui_version = ui_version
        st.session_state.tw_research_result = None

    if "tw_research_case_selector" not in st.session_state:
        st.session_state.tw_research_case_selector = "案例一｜急診胸部 X 光 AI"

    if "tw_research_topic" not in st.session_state:
        st.session_state.tw_research_topic = PRESET_CASES[
            "案例一｜急診胸部 X 光 AI"
        ]

    if "tw_selected_task" not in st.session_state:
        st.session_state.tw_selected_task = TASK_CONFIGS[0].task_id

    st.header("🇹🇼 台灣醫療 AI Research Agent")
    st.caption(
        "針對林口長庚決策，分別研究 TFDA 法規、台灣醫院採用、"
        "台灣臨床證據及台灣可取得產品。新版一次只執行一個任務，"
        "避免四個搜尋同時消耗 API 每分鐘額度。"
    )

    st.selectbox(
        "選擇預設案例",
        list(PRESET_CASES.keys()),
        key="tw_research_case_selector",
        on_change=load_selected_case,
    )

    case_description = st.text_area(
        "台灣市場研究題目",
        key="tw_research_topic",
        height=130,
    )

    st.text_input(
        "研究市場",
        value="台灣市場（林口長庚決策）",
        disabled=True,
    )

    try:
        current_snapshot = load_research_snapshot(case_description)
    except ValueError:
        current_snapshot = None

    if st.session_state.tw_research_result is None and current_snapshot is not None:
        st.session_state.tw_research_result = current_snapshot

    result = st.session_state.tw_research_result

    next_label = None
    if result is not None:
        next_label = result.get("next_task_label")

    if next_label:
        st.info(f"下一個未完成任務：{next_label}")
    elif result is not None and result.get("status") == "success":
        st.success("四項台灣研究任務都已完成。")

    button_col1, button_col2 = st.columns([2, 1])

    with button_col1:
        continue_research = st.button(
            "執行下一個未完成任務",
            type="primary",
            width="stretch",
            help=(
                "每次只執行一項。成功結果會立即寫入快取；"
                "下一次按鈕會接著跑下一項。"
            ),
        )

    task_options = {
        task.task_id: task.label
        for task in TASK_CONFIGS
    }

    with button_col2:
        selected_task_id = st.selectbox(
            "指定重跑任務",
            options=list(task_options.keys()),
            format_func=lambda task_id: task_options[task_id],
            key="tw_selected_task",
        )

        rerun_selected = st.button(
            "重新執行選定任務",
            width="stretch",
            help="只忽略選定任務的快取，不會重跑其他三項。",
        )

    if continue_research or rerun_selected:
        progress_box = st.empty()

        def update_progress(message: str) -> None:
            progress_box.info(message)

        try:
            if rerun_selected:
                updated_result = run_research_task(
                    case_description=case_description,
                    task_id=selected_task_id,
                    force_refresh=True,
                    progress_callback=update_progress,
                )
            else:
                updated_result = run_next_incomplete_task(
                    case_description=case_description,
                    progress_callback=update_progress,
                )

            st.session_state.tw_research_result = updated_result
            result = updated_result
            progress_box.empty()

        except (ValueError, ResearchAgentError) as error:
            progress_box.empty()
            st.error(str(error))

        except Exception as error:
            progress_box.empty()
            st.error("台灣研究流程發生未預期錯誤。")
            with st.expander("查看技術錯誤"):
                st.exception(error)

    result = st.session_state.tw_research_result
    if result is None:
        st.info("選擇案例後，按下「執行下一個未完成任務」。")
        return

    if result["status"] == "success":
        st.success("四項台灣研究任務均已完成。")
    elif result["status"] == "partial_success":
        st.warning(
            "部分台灣研究任務已完成。請繼續按下按鈕，"
            "系統每次只會執行下一項未完成任務。"
        )
    elif result["status"] == "technical_failure":
        st.error(
            "目前尚無成功任務，但這是技術性未完成，不代表台灣沒有資料。"
            "請先查看下方『錯誤類型』與『說明』。若是 rate_limit，等待約 60 秒後"
            "再重跑選定任務；若是 output_too_long 或格式解析錯誤，直接重跑新版任務。"
        )
    else:
        st.info("台灣研究尚未開始。每次按鈕只會執行一項研究任務。")

    completed_count = sum(
        1
        for task in result.get("tasks", {}).values()
        if task.get("result") is not None
        and task.get("status") in {"success", "cached", "stale_cache"}
    )

    st.progress(
        completed_count / len(TASK_CONFIGS),
        text=f"台灣研究進度：{completed_count} / {len(TASK_CONFIGS)} 項完成",
    )

    st.caption(
        f"模型：{result['model']}｜研究範圍：{result['target_region']}｜"
        f"公開來源：{len(result.get('sources', []))} 項"
    )

    st.subheader("任務執行狀態")
    render_task_status(result)

    failed_tasks = [
        task
        for task in result.get("tasks", {}).values()
        if task.get("status") == "technical_failure"
    ]

    if failed_tasks:
        with st.expander("查看技術診斷資訊", expanded=True):
            for task in failed_tasks:
                st.markdown(f"**{task.get('task_label', task.get('task_id', '研究任務'))}**")
                st.code(
                    f"error_type: {task.get('error_type') or 'unknown'}\n"
                    f"message: {task.get('error_message') or '未提供'}",
                    language="text",
                )

    render_maturity(result)

    source_map = build_source_map(result)
    tasks = result["tasks"]

    regulatory_tab, adoption_tab, clinical_tab, market_tab = st.tabs(
        [
            "TFDA／法規",
            "台灣醫院／長庚採用",
            "台灣臨床證據",
            "產品／商業模式",
        ]
    )

    with regulatory_tab:
        render_regulatory_task(tasks["regulatory"], source_map)

    with adoption_tab:
        render_adoption_task(tasks["adoption"], source_map)

    with clinical_tab:
        render_clinical_task(tasks["clinical"], source_map)

    with market_tab:
        render_market_task(tasks["market"], source_map)

    render_linkou_assessment(result, source_map)

    st.subheader("跨任務資料缺口")
    missing_information = result.get("missing_information", [])
    if missing_information:
        for item in missing_information:
            st.warning(item)
    else:
        st.info("完成更多任務後，系統會在這裡整合跨任務資料缺口。")

    st.subheader("完整台灣資料來源")
    sources = result.get("sources", [])
    if sources:
        for index, source in enumerate(sources, start=1):
            st.markdown(
                f"{index}. [{source.get('title', source['url'])}]({source['url']}) "
                f"— {source.get('task_label', '')}"
            )
    else:
        st.info("完成至少一項研究任務後，這裡會顯示台灣公開來源。")

    st.download_button(
        label="下載目前台灣市場研究資料（JSON）",
        data=json.dumps(result, ensure_ascii=False, indent=2),
        file_name="taiwan_medical_ai_research.json",
        mime="application/json",
        width="stretch",
    )

