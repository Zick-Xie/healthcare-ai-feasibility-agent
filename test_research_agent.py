import json
from pathlib import Path

from research_agent import (
    ResearchAgentError,
    research_medical_ai_case,
)


CASE_DESCRIPTION = (
    "評估大型醫院導入胸部 X 光 AI 輔助判讀與"
    "高風險病例優先排序的市場成熟度、代表產品、"
    "臨床證據、法規狀態與商業模式。"
)


def show_progress(message: str) -> None:
    print(f"→ {message}", flush=True)


def main() -> None:
    print("=== Hospital AI Fast Research Agent ===")

    try:
        result = research_medical_ai_case(
            case_description=CASE_DESCRIPTION,
            target_region="台灣、美國與歐洲市場",
            force_refresh=False,
            progress_callback=show_progress,
        )

    except (ResearchAgentError, ValueError) as error:
        print(f"\n研究失敗：{error}")
        return

    structured = result["structured_result"]
    maturity = structured["market_maturity"]
    products = structured["representative_products"]

    print("\n=== 研究完成 ===")
    print(f"狀態：{result['status']}")
    print(f"是否使用快取：{result['cache_hit']}")
    print(f"模型：{result['model']}")
    print(f"來源數量：{len(result['sources'])}")

    print("\n=== 市場成熟度 ===")
    print(f"{maturity['overall_score']:.1f} / 5")
    print(maturity["maturity_stage"])
    print(maturity["reason"])

    print("\n=== 代表公司與產品 ===")

    if products:
        for product in products:
            print(
                f"- {product['company']}｜"
                f"{product['product']}"
            )
    else:
        print("- 未找到足夠可靠的公開產品資料")

    print("\n=== 資料缺口 ===")

    for item in structured["missing_information"]:
        print(f"- {item}")

    Path("research_output.json").write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n結果已儲存至 research_output.json")


if __name__ == "__main__":
    main()
