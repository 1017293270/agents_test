import json
import sqlite3
from pathlib import Path
from typing import Any


class Repository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                create table if not exists data_sources (
                    id integer primary key autoincrement,
                    name text not null,
                    connection_json text not null,
                    knowledge_base text not null default '',
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists runs (
                    id integer primary key autoincrement,
                    data_source_id integer references data_sources(id) on delete set null,
                    name text not null,
                    db_engine text not null,
                    db_host text not null,
                    db_name text not null,
                    question_count integer not null,
                    status text not null,
                    stage text not null default 'pending',
                    stage_message text not null default '',
                    processed_count integer not null default 0,
                    business_context text not null default '',
                    knowledge_base text not null default '',
                    error text,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists questions (
                    id integer primary key autoincrement,
                    run_id integer not null references runs(id) on delete cascade,
                    question text not null,
                    business_intent text not null default '',
                    tables_json text not null default '[]',
                    sql text not null default '',
                    answer_summary text not null default '',
                    result_preview_json text not null default '[]',
                    row_count integer not null default 0,
                    status text not null,
                    error text,
                    created_at text not null default current_timestamp
                );
                """
            )
            self._ensure_column(db, "runs", "data_source_id", "integer references data_sources(id) on delete set null")
            self._ensure_column(db, "runs", "stage", "text not null default 'pending'")
            self._ensure_column(db, "runs", "stage_message", "text not null default ''")
            self._ensure_column(db, "runs", "processed_count", "integer not null default 0")
            self._ensure_column(db, "runs", "knowledge_base", "text not null default ''")

    def _ensure_column(self, db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {str(row["name"]) for row in db.execute(f"pragma table_info({table})").fetchall()}
        if column not in columns:
            db.execute(f"alter table {table} add column {column} {definition}")

    def create_data_source(self, name: str, connection: dict[str, Any], knowledge_base: str = "") -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                insert into data_sources (name, connection_json, knowledge_base)
                values (?, ?, ?)
                """,
                (name, json.dumps(connection, ensure_ascii=False), knowledge_base),
            )
            return int(cursor.lastrowid)

    def update_data_source(self, data_source_id: int, name: str, connection: dict[str, Any], knowledge_base: str = "") -> None:
        with self.connect() as db:
            db.execute(
                """
                update data_sources
                set name = ?, connection_json = ?, knowledge_base = ?, updated_at = current_timestamp
                where id = ?
                """,
                (name, json.dumps(connection, ensure_ascii=False), knowledge_base, data_source_id),
            )

    def get_data_source(self, data_source_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("select * from data_sources where id = ?", (data_source_id,)).fetchone()
        return _data_source_from_row(row) if row else None

    def list_data_sources(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("select * from data_sources order by updated_at desc, id desc").fetchall()
        return [_data_source_from_row(row) for row in rows]

    def create_run(
        self,
        name: str,
        db_engine: str,
        db_host: str,
        db_name: str,
        question_count: int,
        business_context: str,
        data_source_id: int | None = None,
        knowledge_base: str = "",
    ) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                insert into runs (
                    data_source_id, name, db_engine, db_host, db_name, question_count,
                    status, stage, stage_message, processed_count, business_context, knowledge_base
                )
                values (?, ?, ?, ?, ?, ?, 'pending', 'pending', 'Waiting to start', 0, ?, ?)
                """,
                (data_source_id, name, db_engine, db_host, db_name, question_count, business_context, knowledge_base),
            )
            return int(cursor.lastrowid)

    def update_run_status(self, run_id: int, status: str, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "update runs set status = ?, error = ?, updated_at = current_timestamp where id = ?",
                (status, error, run_id),
            )

    def update_run_progress(
        self,
        run_id: int,
        stage: str,
        stage_message: str,
        processed_count: int | None = None,
    ) -> None:
        with self.connect() as db:
            if processed_count is None:
                db.execute(
                    "update runs set stage = ?, stage_message = ?, updated_at = current_timestamp where id = ?",
                    (stage, stage_message, run_id),
                )
            else:
                db.execute(
                    """
                    update runs
                    set stage = ?, stage_message = ?, processed_count = ?, updated_at = current_timestamp
                    where id = ?
                    """,
                    (stage, stage_message, processed_count, run_id),
                )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("select * from runs where id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("select * from runs order by id desc").fetchall()
        return [dict(row) for row in rows]

    def add_question(
        self,
        run_id: int,
        question: str,
        business_intent: str = "",
        tables: list[str] | None = None,
        sql: str = "",
        answer_summary: str = "",
        result_preview: list[dict[str, Any]] | None = None,
        row_count: int = 0,
        status: str = "pending",
        error: str | None = None,
    ) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                insert into questions (
                    run_id, question, business_intent, tables_json, sql,
                    answer_summary, result_preview_json, row_count, status, error
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    question,
                    business_intent,
                    json.dumps(tables or [], ensure_ascii=False),
                    sql,
                    answer_summary,
                    json.dumps(result_preview or [], ensure_ascii=False, default=str),
                    row_count,
                    status,
                    error,
                ),
            )
            return int(cursor.lastrowid)

    def list_questions(self, run_id: int, status: str | None = None) -> list[dict[str, Any]]:
        query = "select * from questions where run_id = ?"
        params: list[Any] = [run_id]
        if status:
            query += " and status = ?"
            params.append(status)
        query += " order by id asc"
        with self.connect() as db:
            rows = db.execute(query, params).fetchall()
        return [_question_from_row(row) for row in rows]

    def delete_failed_questions(self, run_id: int) -> None:
        with self.connect() as db:
            db.execute("delete from questions where run_id = ? and status = 'failed'", (run_id,))

    def counts(self, run_id: int) -> dict[str, int]:
        with self.connect() as db:
            rows = db.execute(
                "select status, count(*) as count from questions where run_id = ? group by status",
                (run_id,),
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}


def _question_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["tables"] = json.loads(data.pop("tables_json") or "[]")
    data["result_preview"] = json.loads(data.pop("result_preview_json") or "[]")
    return data


def _data_source_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["connection"] = json.loads(data.pop("connection_json") or "{}")
    return data
