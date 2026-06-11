from app.generator import build_generation_prompt, summarize_result, summarize_result_with_claude
from app.models import SchemaInspectResponse


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


def test_generation_prompt_includes_data_source_knowledge_base():
    schema = SchemaInspectResponse(database="crm", tables=[])

    prompt = build_generation_prompt(
        schema=schema,
        business_context="Question style: sales operations.",
        question_count=3,
        knowledge_base="expected_amount means forecast contract value",
    )

    assert "Question style: sales operations." in prompt
    assert "expected_amount means forecast contract value" in prompt


def test_summarize_result_with_claude_uses_query_result_and_knowledge_base():
    class FakeClient:
        def __init__(self):
            self.prompts = []

        def summarize_answer(self, prompt: str) -> str:
            self.prompts.append(prompt)
            return "Super Admin leads the forecast, followed by Xiao Wang and Luo Ying."

    client = FakeClient()

    answer = summarize_result_with_claude(
        client=client,
        question="Which sales reps have the highest forecast contract value?",
        sql="select sales_name, total_expected_amount from sales_stats",
        preview=[
            {"sales_name": "Super Admin", "dept_name": "HQ", "total_expected_amount": 572.0},
            {"sales_name": "Xiao Wang", "dept_name": "HQ", "total_expected_amount": 300.0},
            {"sales_name": "Luo Ying", "dept_name": "Southwest", "total_expected_amount": 111.0},
        ],
        row_count=3,
        knowledge_base="total_expected_amount is forecast contract value in CNY",
    )

    assert answer == "Super Admin leads the forecast, followed by Xiao Wang and Luo Ying."
    prompt = client.prompts[0]
    assert "Which sales reps have the highest forecast contract value?" in prompt
    assert "total_expected_amount is forecast contract value in CNY" in prompt
    assert "Super Admin" in prompt
