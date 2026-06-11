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


class DataSourceCreateRequest(BaseModel):
    name: str = "MySQL data source"
    connection: MySqlConnection
    knowledge_base: str = ""


class DataSourceResponse(BaseModel):
    id: int
    name: str
    connection: MySqlConnection
    knowledge_base: str
    created_at: str
    updated_at: str


class RunCreateRequest(BaseModel):
    name: str = "MySQL benchmark run"
    connection: MySqlConnection | None = None
    data_source_id: int | None = None
    business_context: str = ""
    knowledge_base: str = ""
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
    stage: str = "pending"
    stage_message: str = ""
    processed_count: int = 0
    business_context: str
    data_source_id: int | None = None
    knowledge_base: str = ""
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
