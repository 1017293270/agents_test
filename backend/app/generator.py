import json
from typing import Any

from app.claude_client import ClaudeClient
from app.config import Settings
from app.models import MySqlConnection, SchemaInspectResponse
from app.mysql_service import execute_select, inspect_schema
from app.repository import Repository
from app.sql_safety import validate_select_sql


def run_generation(
    repo: Repository,
    settings: Settings,
    run_id: int,
    connection: MySqlConnection,
    business_context: str,
    question_count: int,
    sample_rows: int,
    knowledge_base: str = "",
) -> None:
    repo.update_run_status(run_id, "running")
    client = ClaudeClient(
        claude_bin=settings.claude_bin,
        timeout_seconds=settings.claude_timeout_seconds,
        max_budget_usd=settings.claude_max_budget_usd,
    )

    try:
        repo.update_run_progress(run_id, "reading_schema", "正在实时读取库表结构和样例数据", 0)
        schema = inspect_schema(connection, sample_rows=sample_rows)

        repo.update_run_progress(run_id, "generating_questions", "正在结合知识库生成问题和 SQL", 0)
        prompt = build_generation_prompt(schema, business_context, question_count, knowledge_base=knowledge_base)
        payload = client.generate_questions(prompt)
        questions = payload.get("questions", [])
        if not isinstance(questions, list) or not questions:
            raise ValueError("Claude did not return any questions")

        selected_questions = questions[:question_count]
        for index, item in enumerate(selected_questions, start=1):
            repo.update_run_progress(
                run_id,
                "executing_questions",
                f"正在执行第 {index}/{len(selected_questions)} 个问题并组织自然答案",
                index - 1,
            )
            _process_question(repo, settings, run_id, connection, schema, business_context, knowledge_base, client, item)

        counts = repo.counts(run_id)
        status = "completed" if counts.get("success", 0) else "failed"
        message = "评测集生成完成" if status == "completed" else "没有生成成功的问题"
        repo.update_run_progress(run_id, status, message, len(selected_questions))
        repo.update_run_status(run_id, status)
    except Exception as exc:
        repo.update_run_progress(run_id, "failed", str(exc))
        repo.update_run_status(run_id, "failed", str(exc))


def retry_failed_questions(
    repo: Repository,
    settings: Settings,
    run_id: int,
    connection: MySqlConnection,
    business_context: str,
    sample_rows: int,
    knowledge_base: str = "",
) -> None:
    failed = repo.list_questions(run_id, status="failed")
    if not failed:
        return
    repo.delete_failed_questions(run_id)
    repo.update_run_status(run_id, "running")
    try:
        repo.update_run_progress(run_id, "reading_schema", "正在重试前实时读取库表结构", 0)
        schema = inspect_schema(connection, sample_rows=sample_rows)
        client = ClaudeClient(settings.claude_bin, settings.claude_timeout_seconds, settings.claude_max_budget_usd)
        for index, original in enumerate(failed, start=1):
            repo.update_run_progress(
                run_id,
                "retrying_failed",
                f"正在重试第 {index}/{len(failed)} 个失败问题",
                index - 1,
            )
            prompt = build_repair_prompt(
                schema=schema,
                business_context=business_context,
                question=original["question"],
                sql=original["sql"],
                error=original["error"] or "unknown error",
                knowledge_base=knowledge_base,
            )
            item = client.repair_sql(prompt)
            item.setdefault("question", original["question"])
            item.setdefault("business_intent", original["business_intent"])
            item.setdefault("tables", original["tables"])
            _process_question(
                repo,
                settings,
                run_id,
                connection,
                schema,
                business_context,
                knowledge_base,
                client,
                item,
                allow_repair=False,
            )
        repo.update_run_progress(run_id, "completed", "失败问题重试完成", len(failed))
        repo.update_run_status(run_id, "completed")
    except Exception as exc:
        repo.update_run_progress(run_id, "failed", str(exc))
        repo.update_run_status(run_id, "failed", str(exc))


def _process_question(
    repo: Repository,
    settings: Settings,
    run_id: int,
    connection: MySqlConnection,
    schema: SchemaInspectResponse,
    business_context: str,
    knowledge_base: str,
    client: ClaudeClient,
    item: dict[str, Any],
    allow_repair: bool = True,
) -> None:
    question = str(item.get("question") or "").strip()
    business_intent = str(item.get("business_intent") or "").strip()
    tables = item.get("tables") if isinstance(item.get("tables"), list) else []
    sql = str(item.get("sql") or "").strip()

    try:
        safe_sql = validate_select_sql(sql, default_limit=settings.default_query_limit)
        rows, row_count = execute_select(connection, safe_sql, timeout_seconds=settings.mysql_query_timeout_seconds)
        preview = rows[:50]
        try:
            answer_summary = summarize_result_with_claude(
                client=client,
                question=question,
                sql=safe_sql,
                preview=preview,
                row_count=row_count,
                knowledge_base=knowledge_base,
                business_context=business_context,
            )
        except Exception:
            answer_summary = summarize_result(question, preview, row_count)
        repo.add_question(
            run_id=run_id,
            question=question,
            business_intent=business_intent,
            tables=[str(table) for table in tables],
            sql=safe_sql,
            answer_summary=answer_summary,
            result_preview=preview,
            row_count=row_count,
            status="success",
        )
    except Exception as exc:
        if allow_repair:
            try:
                repair_prompt = build_repair_prompt(
                    schema=schema,
                    business_context=business_context,
                    question=question,
                    sql=sql,
                    error=str(exc),
                    knowledge_base=knowledge_base,
                )
                repaired = client.repair_sql(repair_prompt)
                return _process_question(
                    repo,
                    settings,
                    run_id,
                    connection,
                    schema,
                    business_context,
                    knowledge_base,
                    client,
                    repaired,
                    allow_repair=False,
                )
            except Exception as repair_exc:
                exc = repair_exc
        repo.add_question(
            run_id=run_id,
            question=question or "Untitled question",
            business_intent=business_intent,
            tables=[str(table) for table in tables],
            sql=sql,
            status="failed",
            error=str(exc),
        )


def build_generation_prompt(
    schema: SchemaInspectResponse,
    business_context: str,
    question_count: int,
    knowledge_base: str = "",
) -> str:
    return f"""
你是一个数据治理平台的问数可靠性评测集生成器。
请根据 MySQL schema、字段说明、少量样例值、业务说明和数据源知识库，生成 {question_count} 个真实业务用户会问的问题。

要求：
- 输出必须是严格 JSON，不要 Markdown。
- JSON shape: {{"questions":[{{"question":"...","business_intent":"...","tables":["..."],"sql":"select ..."}}]}}
- SQL 必须是 MySQL 单条 SELECT。
- 问题要偏真实业务问法，覆盖核心业务对象、指标、筛选、分组、排序、Top N、时间条件和必要 Join。
- 不要生成修改数据、建表、删表、导出文件、调用存储过程的 SQL。
- 优先使用知识库中的业务口径、字段含义、别名和指标定义。

业务说明：
{business_context or "无额外业务说明，请根据表名、字段名、字段注释和样例值生成。"}

数据源知识库：
{knowledge_base or "无额外知识库。"}

Schema 与样例：
{_schema_to_prompt(schema)}
""".strip()


def build_repair_prompt(
    schema: SchemaInspectResponse,
    business_context: str,
    question: str,
    sql: str,
    error: str,
    knowledge_base: str = "",
) -> str:
    return f"""
请修复下面这个 MySQL 问数题目的 SQL。只输出严格 JSON，不要 Markdown。
JSON shape: {{"question":"...","business_intent":"...","tables":["..."],"sql":"select ..."}}

业务说明：
{business_context or "无额外业务说明。"}

数据源知识库：
{knowledge_base or "无额外知识库。"}

问题：{question}
失败 SQL：{sql}
错误：{error}

Schema 与样例：
{_schema_to_prompt(schema)}
""".strip()


def _schema_to_prompt(schema: SchemaInspectResponse) -> str:
    compact = {
        "database": schema.database,
        "tables": [
            {
                "name": table.name,
                "comment": table.comment,
                "columns": [column.model_dump() for column in table.columns],
                "samples": table.samples,
            }
            for table in schema.tables
        ],
    }
    return json.dumps(compact, ensure_ascii=False, default=str)


def summarize_result_with_claude(
    client: Any,
    question: str,
    sql: str,
    preview: list[dict[str, Any]],
    row_count: int,
    knowledge_base: str = "",
    business_context: str = "",
) -> str:
    prompt = build_answer_prompt(question, sql, preview, row_count, knowledge_base, business_context)
    answer = str(client.summarize_answer(prompt)).strip()
    if not answer:
        return summarize_result(question, preview, row_count)
    return answer


def build_answer_prompt(
    question: str,
    sql: str,
    preview: list[dict[str, Any]],
    row_count: int,
    knowledge_base: str = "",
    business_context: str = "",
) -> str:
    result_payload = {
        "row_count": row_count,
        "preview_rows": preview[:20],
    }
    return f"""
你是数据分析助理。请把 SQL 查询结果组织成面向业务用户的自然语言答案。

要求：
- 直接回答问题，不要输出 Markdown 表格。
- 使用业务含义解释字段，不要机械复述字段名。
- 如果有多行结果，请总结排序、差异和关键结论，而不是逐字段流水账。
- 如果没有结果，请说明没有查询到符合条件的数据。
- 不要编造查询结果中不存在的数值。

业务说明：
{business_context or "无额外业务说明。"}

数据源知识库：
{knowledge_base or "无额外知识库。"}

用户问题：
{question}

执行 SQL：
{sql}

查询结果 JSON：
{json.dumps(result_payload, ensure_ascii=False, default=str)}
""".strip()


def summarize_result(question: str, preview: list[dict[str, Any]], row_count: int) -> str:
    if row_count == 0:
        return f"针对“{question}”，没有查询到符合条件的数据。"
    if row_count == 1 and preview:
        row = preview[0]
        if len(row) == 1:
            return f"针对“{question}”，答案是：{_format_value(next(iter(row.values())))}。"
        return f"针对“{question}”，查询到 1 条结果：{_format_row(row)}。"

    examples = "；".join(
        f"第 {index + 1} 条：{_format_row(row)}"
        for index, row in enumerate(preview[:5])
    )
    if examples:
        return f"针对“{question}”，共查询到 {row_count} 条结果。前 {min(len(preview), 5)} 条为：{examples}。"
    return f"针对“{question}”，共查询到 {row_count} 条结果。"


def _format_row(row: dict[str, Any]) -> str:
    return "，".join(f"{_format_key(key)} 为{_format_value(value)}" for key, value in row.items())


def _format_key(key: str) -> str:
    return str(key).replace("_", " ")


def _format_value(value: Any) -> str:
    if value is None:
        return "空"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)
