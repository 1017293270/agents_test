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


@app.get("/api/runs")
def list_runs():
    return {"runs": repo.list_runs()}


@app.post("/api/runs")
def create_run(request: RunCreateRequest, background_tasks: BackgroundTasks):
    run_id = repo.create_run(
        name=request.name,
        db_engine="mysql",
        db_host=f"{request.connection.host}:{request.connection.port}",
        db_name=request.connection.database,
        question_count=request.question_count,
        business_context=request.business_context,
    )
    background_tasks.add_task(
        run_generation,
        repo,
        settings,
        run_id,
        request.connection,
        request.business_context,
        request.question_count,
        request.sample_rows,
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
    if not repo.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    background_tasks.add_task(
        retry_failed_questions,
        repo,
        settings,
        run_id,
        request.connection,
        request.business_context,
        request.sample_rows,
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
