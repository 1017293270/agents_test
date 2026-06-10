from typing import Any, Literal

from pydantic import BaseModel, Field


class MySqlConnection(BaseModel):
    host: str
    port: int = 3306
    user: str
    password: str = ""
    database: str
    connect_timeout: int = 10


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    key: str | None = None
    comment: str | None = None


class TableInfo(BaseModel):
    name: str
    comment: str | None = None
    columns: list[ColumnInfo]
    samples: list[dict[str, Any]] = Field(default_factory=list)


class SchemaInspectRequest(BaseModel):
    connection: MySqlConnection
    sample_rows: int = 3


class SchemaInspectResponse(BaseModel):
    database: str
    tables: list[TableInfo]


class RunCreateRequest(BaseModel):
    name: str = "MySQL benchmark run"
    connection: MySqlConnection
    business_context: str = ""
    question_count: int = Field(default=100, ge=1, le=200)
    sample_rows: int = Field(default=3, ge=0, le=10)


class RunResponse(BaseModel):
    id: int
    name: str
    db_engine: str
    db_host: str
    db_name: str
    question_count: int
    status: str
    business_context: str
    error: str | None = None
    created_at: str
    updated_at: str


class QuestionResponse(BaseModel):
    id: int
    run_id: int
    question: str
    business_intent: str
    tables: list[str]
    sql: str
    answer_summary: str
    result_preview: list[dict[str, Any]]
    row_count: int
    status: str
    error: str | None = None
    created_at: str


class RunDetailResponse(BaseModel):
    run: RunResponse
    questions: list[QuestionResponse]
    counts: dict[str, int]


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str


class HealthResponse(BaseModel):
    ok: bool
    status: str


class ClaudeHealthResponse(BaseModel):
    ok: bool
    version: str | None = None
    probe: str | None = None
    error: str | None = None


class ExportFormat(BaseModel):
    format: Literal["xlsx", "jsonl"]
