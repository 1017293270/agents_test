import json
from typing import Any

from app.claude_client import ClaudeClient
from app.config import Settings
from app.models import MySqlConnection, SchemaInspectResponse
from app.mysql_service import execute_select, inspect_schema
from app.repository import Repository
from app.sql_safety import SqlSafetyError, validate_select_sql


def run_generation(
    repo: Repository,
    settings: Settings,
    run_id: int,
    connection: MySqlConnection,
    business_context: str,
    question_count: int,
    sample_rows: int,
) -> None:
    repo.update_run_status(run_id, "running")
    client = ClaudeClient(
        claude_bin=settings.claude_bin,
        timeout_seconds=settings.claude_timeout_seconds,
        max_budget_usd=settings.claude_max_budget_usd,
    )

    try:
        schema = inspect_schema(connection, sample_rows=sample_rows)
        prompt = build_generation_prompt(schema, business_context, question_count)
        payload = client.generate_questions(prompt)
        questions = payload.get("questions", [])
        if not isinstance(questions, list) or not questions:
            raise ValueError("Claude did not return any questions")

        for item in questions[:question_count]:
            _process_question(repo, settings, run_id, connection, schema, business_context, client, item)

        counts = repo.counts(run_id)
        repo.update_run_status(run_id, "completed" if counts.get("success", 0) else "failed")
    except Exception as exc:
        repo.update_run_status(run_id, "failed", str(exc))


def retry_failed_questions(
    repo: Repository,
    settings: Settings,
    run_id: int,
    connection: MySqlConnection,
    business_context: str,
    sample_rows: int,
) -> None:
    failed = repo.list_questions(run_id, status="failed")
    if not failed:
        return
    repo.delete_failed_questions(run_id)
    repo.update_run_status(run_id, "running")
    try:
        schema = inspect_schema(connection, sample_rows=sample_rows)
        client = ClaudeClient(settings.claude_bin, settings.claude_timeout_seconds, settings.claude_max_budget_usd)
        for original in failed:
            prompt = build_repair_prompt(
                schema=schema,
                business_context=business_context,
                question=original["question"],
                sql=original["sql"],
                error=original["error"] or "unknown error",
            )
            item = client.repair_sql(prompt)
            item.setdefault("question", original["question"])
            item.setdefault("business_intent", original["business_intent"])
            item.setdefault("tables", original["tables"])
            _process_question(repo, settings, run_id, connection, schema, business_context, client, item, allow_repair=False)
        repo.update_run_status(run_id, "completed")
    except Exception as exc:
        repo.update_run_status(run_id, "failed", str(exc))


def _process_question(
    repo: Repository,
    settings: Settings,
    run_id: int,
    connection: MySqlConnection,
    schema: SchemaInspectResponse,
    business_context: str,
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
        repo.add_question(
            run_id=run_id,
            question=question,
            business_intent=business_intent,
            tables=[str(table) for table in tables],
            sql=safe_sql,
            answer_summary=summarize_result(question, preview, row_count),
            result_preview=preview,
            row_count=row_count,
            status="success",
        )
    except Exception as exc:
        if allow_repair:
            try:
                repair_prompt = build_repair_prompt(schema, business_context, question, sql, str(exc))
                repaired = client.repair_sql(repair_prompt)
                return _process_question(
                    repo, settings, run_id, connection, schema, business_context, client, repaired, allow_repair=False
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


def build_generation_prompt(schema: SchemaInspectResponse, business_context: str, question_count: int) -> str:
    return f"""
你是一个数据治理平台的问数可靠性评测集生成器。
请根据 MySQL schema、字段说明、少量样例值和业务说明，生成 {question_count} 个真实业务用户会问的问题。

要求：
- 输出必须是严格 JSON，不要 Markdown。
- JSON shape: {{"questions":[{{"question":"...","business_intent":"...","tables":["..."],"sql":"select ..."}}]}}
- SQL 必须是 MySQL 单条 SELECT。
- 问题要偏真实业务问法，覆盖核心业务对象、指标、筛选、分组、排序、Top N、时间条件和必要 Join。
- 不要生成修改数据、建表、删表、导出文件、调用存储过程的 SQL。

业务说明：
{business_context or "无额外业务说明，请根据表名、字段名、字段注释和样例值生成。"}

Schema 与样例：
{_schema_to_prompt(schema)}
""".strip()


def build_repair_prompt(
    schema: SchemaInspectResponse,
    business_context: str,
    question: str,
    sql: str,
    error: str,
) -> str:
    return f"""
请修复下面这个 MySQL 问数题目的 SQL。只输出严格 JSON，不要 Markdown。
JSON shape: {{"question":"...","business_intent":"...","tables":["..."],"sql":"select ..."}}

业务说明：
{business_context or "无额外业务说明。"}

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
