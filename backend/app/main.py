from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.claude_client import ClaudeClient, ClaudeClientError
from app.config import settings
from app.exporter import export_run_jsonl, export_run_xlsx
from app.generator import retry_failed_questions, run_generation
from app.models import (
    ClaudeHealthResponse,
    ConnectionTestResponse,
    DataSourceCreateRequest,
    DataSourceResponse,
    HealthResponse,
    MySqlConnection,
    RunCreateRequest,
    RunDetailResponse,
    SchemaInspectRequest,
    SchemaInspectResponse,
)
from app.mysql_service import inspect_schema, test_connection
from app.repository import Repository

settings.ensure_dirs()
repo = Repository(settings.sqlite_path)
repo.init()

app = FastAPI(title="MySQL Question Benchmark Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, status="ok")


@app.get("/api/health/claude", response_model=ClaudeHealthResponse)
def claude_health() -> ClaudeHealthResponse:
    client = ClaudeClient(settings.claude_bin, timeout_seconds=20, max_budget_usd=settings.claude_max_budget_usd)
    try:
        version = client.version()
    except Exception as exc:
        version = None
        version_error = str(exc)
    else:
        version_error = None
    try:
        probe = client.ask_text("Reply with exactly: ok", timeout_seconds=20)
        ok = "ok" in probe.lower()
        return ClaudeHealthResponse(ok=ok, version=version, probe=probe)
    except ClaudeClientError as exc:
        return ClaudeHealthResponse(ok=False, version=version, error=str(exc))
    except Exception as exc:
        return ClaudeHealthResponse(ok=False, version=version, error=version_error or str(exc))


@app.post("/api/connections/test", response_model=ConnectionTestResponse)
def api_test_connection(connection: MySqlConnection) -> ConnectionTestResponse:
    try:
        message = test_connection(connection)
        return ConnectionTestResponse(ok=True, message=message)
    except Exception as exc:
        return ConnectionTestResponse(ok=False, message=str(exc))


@app.post("/api/schema/inspect", response_model=SchemaInspectResponse)
def api_inspect_schema(request: SchemaInspectRequest) -> SchemaInspectResponse:
    try:
        return inspect_schema(request.connection, sample_rows=request.sample_rows)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/data-sources")
def list_data_sources():
    return {"data_sources": repo.list_data_sources()}


@app.post("/api/data-sources", response_model=DataSourceResponse)
def create_data_source(request: DataSourceCreateRequest) -> DataSourceResponse:
    data_source_id = repo.create_data_source(
        name=request.name,
        connection=request.connection.model_dump(),
        knowledge_base=request.knowledge_base,
    )
    data_source = repo.get_data_source(data_source_id)
    if not data_source:
        raise HTTPException(status_code=500, detail="Data source was not saved")
    return DataSourceResponse(**data_source)


@app.put("/api/data-sources/{data_source_id}", response_model=DataSourceResponse)
def update_data_source(data_source_id: int, request: DataSourceCreateRequest) -> DataSourceResponse:
    if not repo.get_data_source(data_source_id):
        raise HTTPException(status_code=404, detail="Data source not found")
    repo.update_data_source(
        data_source_id=data_source_id,
        name=request.name,
        connection=request.connection.model_dump(),
        knowledge_base=request.knowledge_base,
    )
    data_source = repo.get_data_source(data_source_id)
    if not data_source:
        raise HTTPException(status_code=500, detail="Data source was not saved")
    return DataSourceResponse(**data_source)


@app.get("/api/runs")
def list_runs():
    return {"runs": repo.list_runs()}


@app.post("/api/runs")
def create_run(request: RunCreateRequest, background_tasks: BackgroundTasks):
    connection, knowledge_base, data_source_id = resolve_run_inputs(request)
    run_id = repo.create_run(
        name=request.name,
        db_engine="mysql",
        db_host=f"{connection.host}:{connection.port}",
        db_name=connection.database,
        question_count=request.question_count,
        business_context=request.business_context,
        data_source_id=data_source_id,
        knowledge_base=knowledge_base,
    )
    background_tasks.add_task(
        run_generation,
        repo,
        settings,
        run_id,
        connection,
        request.business_context,
        request.question_count,
        request.sample_rows,
        knowledge_base,
    )
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: int) -> RunDetailResponse:
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    questions = repo.list_questions(run_id)
    return RunDetailResponse(run=run, questions=questions, counts=repo.counts(run_id))


@app.post("/api/runs/{run_id}/retry-failed")
def retry_failed(run_id: int, request: RunCreateRequest, background_tasks: BackgroundTasks):
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    connection, knowledge_base, _ = resolve_run_inputs(request, fallback_run=run)
    background_tasks.add_task(
        retry_failed_questions,
        repo,
        settings,
        run_id,
        connection,
        request.business_context,
        request.sample_rows,
        knowledge_base,
    )
    return {"run_id": run_id, "status": "retrying"}


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: int, format: str = Query(pattern="^(xlsx|jsonl)$")):
    if not repo.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    path = export_run_xlsx(repo, run_id, settings.export_dir) if format == "xlsx" else export_run_jsonl(repo, run_id, settings.export_dir)
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if format == "xlsx"
        else "application/x-ndjson"
    )
    return FileResponse(path, media_type=media_type, filename=path.name)


static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")


def resolve_run_inputs(
    request: RunCreateRequest,
    fallback_run: dict | None = None,
) -> tuple[MySqlConnection, str, int | None]:
    data_source_id = request.data_source_id or (fallback_run or {}).get("data_source_id")
    if data_source_id:
        data_source = repo.get_data_source(int(data_source_id))
        if not data_source:
            raise HTTPException(status_code=404, detail="Data source not found")
        return (
            MySqlConnection(**data_source["connection"]),
            data_source.get("knowledge_base") or "",
            int(data_source_id),
        )
    if request.connection is None:
        raise HTTPException(status_code=400, detail="connection or data_source_id is required")
    return request.connection, request.knowledge_base or (fallback_run or {}).get("knowledge_base", ""), None
