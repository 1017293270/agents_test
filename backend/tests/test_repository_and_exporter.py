import json
from pathlib import Path

from openpyxl import load_workbook

from app.exporter import export_run_jsonl, export_run_xlsx
from app.repository import Repository


def test_repository_stores_run_items_and_failed_lookup(tmp_path: Path):
    repo = Repository(tmp_path / "app.sqlite3")
    repo.init()

    run_id = repo.create_run(
        name="demo",
        db_engine="mysql",
        db_host="127.0.0.1",
        db_name="analytics",
        question_count=100,
        business_context="字段说明",
    )
    repo.add_question(
        run_id=run_id,
        question="本月销售额是多少？",
        business_intent="统计销售额",
        tables=["orders"],
        sql="select sum(amount) from orders",
        status="failed",
        error="timeout",
    )

    failed = repo.list_questions(run_id=run_id, status="failed")

    assert failed[0]["question"] == "本月销售额是多少？"
    assert failed[0]["tables"] == ["orders"]
    assert failed[0]["error"] == "timeout"


def test_repository_saves_data_source_connection_and_knowledge_base(tmp_path: Path):
    repo = Repository(tmp_path / "app.sqlite3")
    repo.init()

    data_source_id = repo.create_data_source(
        name="Sales CRM",
        connection={
            "host": "127.0.0.1",
            "port": 3306,
            "user": "readonly",
            "password": "secret",
            "database": "crm",
            "connect_timeout": 10,
        },
        knowledge_base="Sales amount means expected contract value.",
    )

    saved = repo.get_data_source(data_source_id)
    assert saved["name"] == "Sales CRM"
    assert saved["connection"]["password"] == "secret"
    assert saved["knowledge_base"] == "Sales amount means expected contract value."

    repo.update_data_source(
        data_source_id,
        name="Sales CRM prod",
        connection={**saved["connection"], "database": "crm_prod"},
        knowledge_base="Updated glossary.",
    )

    updated = repo.list_data_sources()[0]
    assert updated["id"] == data_source_id
    assert updated["name"] == "Sales CRM prod"
    assert updated["connection"]["database"] == "crm_prod"
    assert updated["knowledge_base"] == "Updated glossary."


def test_repository_tracks_run_progress_stage(tmp_path: Path):
    repo = Repository(tmp_path / "app.sqlite3")
    repo.init()
    run_id = repo.create_run(
        name="demo",
        db_engine="mysql",
        db_host="127.0.0.1",
        db_name="analytics",
        question_count=10,
        business_context="",
    )

    repo.update_run_progress(run_id, stage="summarizing", stage_message="Polishing answers", processed_count=3)

    run = repo.get_run(run_id)
    assert run["stage"] == "summarizing"
    assert run["stage_message"] == "Polishing answers"
    assert run["processed_count"] == 3


def test_exporter_writes_jsonl_and_xlsx(tmp_path: Path):
    repo = Repository(tmp_path / "app.sqlite3")
    repo.init()
    run_id = repo.create_run(
        name="demo",
        db_engine="mysql",
        db_host="127.0.0.1",
        db_name="analytics",
        question_count=1,
        business_context="字段说明",
    )
    repo.add_question(
        run_id=run_id,
        question="客户数量是多少？",
        business_intent="统计客户数",
        tables=["customers"],
        sql="select count(*) as customer_count from customers",
        answer_summary="共 12 个客户",
        result_preview=[{"customer_count": 12}],
        row_count=1,
        status="success",
    )

    jsonl_path = export_run_jsonl(repo, run_id, tmp_path)
    xlsx_path = export_run_xlsx(repo, run_id, tmp_path)

    record = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["question"] == "客户数量是多少？"
    assert record["natural_answer"] == "共 12 个客户"
    assert record["result_preview"] == [{"customer_count": 12}]

    workbook = load_workbook(xlsx_path)
    sheet = workbook.active
    assert sheet["A1"].value == "id"
    assert sheet["B2"].value == "客户数量是多少？"
    assert "natural_answer" in [cell.value for cell in sheet[1]]
