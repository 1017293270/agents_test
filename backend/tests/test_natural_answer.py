from app.generator import summarize_result


def test_summarize_single_metric_as_natural_answer():
    answer = summarize_result("客户数量是多少？", [{"customer_count": 12}], 1)

    assert answer == "针对“客户数量是多少？”，答案是：12。"


def test_summarize_multiple_rows_as_readable_preview():
    answer = summarize_result(
        "销售额最高的客户有哪些？",
        [
            {"customer_name": "华东客户", "total_amount": 9200},
            {"customer_name": "华南客户", "total_amount": 8100},
        ],
        2,
    )

    assert "共查询到 2 条结果" in answer
    assert "第 1 条：customer name 为华东客户，total amount 为9200" in answer
