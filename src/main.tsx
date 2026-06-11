import React from "react";
import ReactDOM from "react-dom/client";
import {
  Activity,
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Database,
  Download,
  FileText,
  Play,
  Plus,
  RefreshCw,
  Save,
  Table2,
  Upload,
  XCircle
} from "lucide-react";
import "./styles.css";

type Connection = {
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
  connect_timeout: number;
};

type DataSource = {
  id: number;
  name: string;
  connection: Connection;
  knowledge_base: string;
  created_at: string;
  updated_at: string;
};

type ColumnInfo = {
  name: string;
  type: string;
  nullable: boolean;
  key?: string | null;
  comment?: string | null;
};

type TableInfo = {
  name: string;
  comment?: string | null;
  columns: ColumnInfo[];
  samples: Record<string, unknown>[];
};

type Run = {
  id: number;
  name: string;
  db_engine: string;
  db_host: string;
  db_name: string;
  question_count: number;
  status: string;
  stage: string;
  stage_message: string;
  processed_count: number;
  business_context: string;
  data_source_id?: number | null;
  knowledge_base: string;
  error?: string | null;
  created_at: string;
  updated_at: string;
};

type Question = {
  id: number;
  question: string;
  business_intent: string;
  tables: string[];
  sql: string;
  answer_summary: string;
  result_preview: Record<string, unknown>[];
  row_count: number;
  status: string;
  error?: string | null;
};

type RunDetail = {
  run: Run;
  questions: Question[];
  counts: Record<string, number>;
};

const defaultConnection: Connection = {
  host: "127.0.0.1",
  port: 3306,
  user: "",
  password: "",
  database: "",
  connect_timeout: 10
};

function App() {
  const [dataSources, setDataSources] = React.useState<DataSource[]>([]);
  const [selectedDataSourceId, setSelectedDataSourceId] = React.useState<number | null>(null);
  const [dataSourceName, setDataSourceName] = React.useState("");
  const [connection, setConnection] = React.useState<Connection>(defaultConnection);
  const [knowledgeBase, setKnowledgeBase] = React.useState("");
  const [businessContext, setBusinessContext] = React.useState("");
  const [questionCount, setQuestionCount] = React.useState(100);
  const [schema, setSchema] = React.useState<TableInfo[]>([]);
  const [runs, setRuns] = React.useState<Run[]>([]);
  const [currentRunId, setCurrentRunId] = React.useState<number | null>(null);
  const [currentRun, setCurrentRun] = React.useState<RunDetail | null>(null);
  const [message, setMessage] = React.useState("准备连接 MySQL 数据源。");
  const [loading, setLoading] = React.useState<string | null>(null);
  const [schemaError, setSchemaError] = React.useState<string | null>(null);
  const [connectionMessage, setConnectionMessage] = React.useState<string | null>(null);
  const [isDataSourceDirty, setIsDataSourceDirty] = React.useState(false);

  React.useEffect(() => {
    void refreshDataSources(true);
    void refreshRuns();
  }, []);

  React.useEffect(() => {
    if (!currentRunId) return;
    void refreshRun(currentRunId);
    const timer = window.setInterval(() => {
      void refreshRun(currentRunId);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [currentRunId]);

  async function api<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options?.headers || {})
      }
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    return response.json() as Promise<T>;
  }

  async function refreshDataSources(autoSelect = false) {
    try {
      const payload = await api<{ data_sources: DataSource[] }>("/api/data-sources");
      setDataSources(payload.data_sources);
      if (autoSelect && payload.data_sources.length > 0 && selectedDataSourceId === null) {
        void applyDataSource(payload.data_sources[0]);
      }
    } catch (error) {
      setDataSources([]);
      setMessage(readableError(error, "读取数据源失败"));
    }
  }

  async function refreshRuns() {
    try {
      const payload = await api<{ runs: Run[] }>("/api/runs");
      setRuns(payload.runs);
      if (!currentRunId && payload.runs.length) setCurrentRunId(payload.runs[0].id);
      if (currentRunId && !payload.runs.some((run) => run.id === currentRunId)) {
        setCurrentRunId(null);
        setCurrentRun(null);
      }
    } catch {
      setRuns([]);
    }
  }

  async function refreshRun(runId: number) {
    try {
      const payload = await api<RunDetail>(`/api/runs/${runId}`);
      setCurrentRun(payload);
      if (payload.run.stage_message) setMessage(payload.run.stage_message);
      await refreshRuns();
    } catch (error) {
      if (error instanceof Error && error.message.includes("Run not found")) {
        setCurrentRunId(null);
        setCurrentRun(null);
        await refreshRuns();
        return;
      }
      setMessage(readableError(error, "刷新任务失败"));
    }
  }

  async function applyDataSource(source: DataSource) {
    setSelectedDataSourceId(source.id);
    setDataSourceName(source.name);
    setConnection(source.connection);
    setKnowledgeBase(source.knowledge_base || "");
    setSchema([]);
    setSchemaError(null);
    setConnectionMessage(null);
    setIsDataSourceDirty(false);
    setMessage(`已选择数据源：${source.name}`);
    try {
      await inspect(source.connection);
    } catch {
      // inspect() already updates the visible error state.
    }
  }

  function startNewDataSource() {
    setSelectedDataSourceId(null);
    setDataSourceName("");
    setConnection(defaultConnection);
    setKnowledgeBase("");
    setSchema([]);
    setSchemaError(null);
    setConnectionMessage(null);
    setIsDataSourceDirty(false);
    setMessage("正在添加新的数据源。");
  }

  function updateConnection(patch: Partial<Connection>) {
    setConnection((current) => ({ ...current, ...patch }));
    setIsDataSourceDirty(true);
  }

  async function saveDataSource() {
    setLoading("save-source");
    try {
      const payload = {
        name: dataSourceName.trim() || `${connection.database || connection.host || "MySQL"} 数据源`,
        connection,
        knowledge_base: knowledgeBase
      };
      const saved = selectedDataSourceId
        ? await api<DataSource>(`/api/data-sources/${selectedDataSourceId}`, {
            method: "PUT",
            body: JSON.stringify(payload)
          })
        : await api<DataSource>("/api/data-sources", {
            method: "POST",
            body: JSON.stringify(payload)
          });
      await applyDataSource(saved);
      await refreshDataSources();
      setMessage(`数据源已保存：${saved.name}`);
    } catch (error) {
      setMessage(readableError(error, "保存数据源失败"));
    } finally {
      setLoading(null);
    }
  }

  async function testConnection() {
    setLoading("connection");
    try {
      const payload = await api<{ ok: boolean; message: string }>("/api/connections/test", {
        method: "POST",
        body: JSON.stringify(connection)
      });
      setMessage(payload.message);
      setConnectionMessage(payload.message);
    } catch (error) {
      const nextMessage = readableError(error, "连接测试失败");
      setMessage(nextMessage);
      setConnectionMessage(nextMessage);
    } finally {
      setLoading(null);
    }
  }

  async function inspect(nextConnection: Connection = connection): Promise<TableInfo[]> {
    setLoading("schema");
    try {
      const payload = await api<{ database: string; tables: TableInfo[] }>("/api/schema/inspect", {
        method: "POST",
        body: JSON.stringify({ connection: nextConnection, sample_rows: 3 })
      });
      setSchema(payload.tables);
      setSchemaError(null);
      setMessage(`已实时读取 ${payload.tables.length} 张表。`);
      return payload.tables;
    } catch (error) {
      const nextMessage = readableError(error, "读取 schema 失败");
      setSchemaError(nextMessage);
      setMessage(nextMessage);
      throw error;
    } finally {
      setLoading(null);
    }
  }

  function buildRunPayload() {
    const useSavedSource = selectedDataSourceId !== null && !isDataSourceDirty;
    return {
      name: `${dataSourceName || connection.database || "MySQL"} benchmark`,
      data_source_id: useSavedSource ? selectedDataSourceId : undefined,
      connection: useSavedSource ? undefined : connection,
      knowledge_base: useSavedSource ? undefined : knowledgeBase,
      business_context: businessContext,
      question_count: questionCount,
      sample_rows: 3
    };
  }

  async function startRun() {
    setLoading("run");
    try {
      setMessage("正在实时读取库表结构...");
      await inspect();
      setLoading("run");
      const payload = await api<{ run_id: number }>("/api/runs", {
        method: "POST",
        body: JSON.stringify(buildRunPayload())
      });
      setCurrentRunId(payload.run_id);
      setMessage(`任务 #${payload.run_id} 已启动。`);
      await refreshRun(payload.run_id);
    } catch (error) {
      setMessage(readableError(error, "启动任务失败"));
    } finally {
      setLoading(null);
    }
  }

  async function retryFailed() {
    if (!currentRunId) return;
    setLoading("retry");
    try {
      await api(`/api/runs/${currentRunId}/retry-failed`, {
        method: "POST",
        body: JSON.stringify(buildRunPayload())
      });
      setMessage(`任务 #${currentRunId} 已开始重试失败题。`);
    } catch (error) {
      setMessage(readableError(error, "重试失败"));
    } finally {
      setLoading(null);
    }
  }

  async function readContextFile(file: File): Promise<string> {
    if (file.name.endsWith(".xlsx")) {
      const { read, utils } = await import("xlsx");
      const bytes = await file.arrayBuffer();
      const workbook = read(bytes);
      return workbook.SheetNames.map((name) => {
        const rows = utils.sheet_to_csv(workbook.Sheets[name]);
        return `# ${name}\n${rows}`;
      }).join("\n\n");
    }
    return file.text();
  }

  async function handleKnowledgeFile(file: File | null) {
    if (!file) return;
    const text = await readContextFile(file);
    setKnowledgeBase((current) => [current, text].filter(Boolean).join("\n\n"));
    setIsDataSourceDirty(true);
  }

  const success = currentRun?.counts.success || 0;
  const failed = currentRun?.counts.failed || 0;
  const total = currentRun?.questions.length || 0;
  const processed = currentRun?.run.processed_count || total;
  const progress = currentRun ? Math.min(100, Math.round((processed / currentRun.run.question_count) * 100)) : 0;
  const currentRunError = currentRun?.run.error || null;
  const schemaColumnCount = schema.reduce((sum, table) => sum + table.columns.length, 0);
  const hasMessageError = message.includes("失败") || message.includes("error") || message.includes("detail");

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local benchmark generator</p>
          <h1>MySQL 问数评测集生成器</h1>
        </div>
        <div className={`status-pill ${hasMessageError ? "danger" : ""}`}>
          {hasMessageError ? <XCircle size={16} /> : <Activity size={16} />}
          {message}
        </div>
      </header>

      <section className="workspace">
        <aside className="panel setup-panel">
          <div className="panel-title-row">
            <PanelTitle icon={<Database size={18} />} title="数据源" />
            <button className="icon-button" onClick={startNewDataSource} title="新增数据源">
              <Plus size={16} />
            </button>
          </div>

          <div className="source-list">
            {dataSources.length === 0 && <p className="muted">暂无保存的数据源。</p>}
            {dataSources.map((source) => (
              <button
                key={source.id}
                className={source.id === selectedDataSourceId ? "source-card active" : "source-card"}
                onClick={() => void applyDataSource(source)}
              >
                <span>{source.name}</span>
                <small>
                  {source.connection.host}:{source.connection.port}/{source.connection.database}
                </small>
              </button>
            ))}
          </div>

          <Field
            label="数据源名称"
            value={dataSourceName}
            onChange={(name) => {
              setDataSourceName(name);
              setIsDataSourceDirty(true);
            }}
          />
          <div className="grid two">
            <Field label="Host" value={connection.host} onChange={(host) => updateConnection({ host })} />
            <Field
              label="Port"
              value={String(connection.port)}
              onChange={(port) => updateConnection({ port: Number(port) || 3306 })}
            />
          </div>
          <div className="grid two">
            <Field label="User" value={connection.user} onChange={(user) => updateConnection({ user })} />
            <Field
              label="Password"
              type="password"
              value={connection.password}
              onChange={(password) => updateConnection({ password })}
            />
          </div>
          <Field label="Database" value={connection.database} onChange={(database) => updateConnection({ database })} />

          <div className="button-row">
            <button onClick={saveDataSource} disabled={loading === "save-source"}>
              <Save size={16} />
              保存数据源
            </button>
            <button onClick={testConnection} disabled={loading === "connection"}>
              <CheckCircle2 size={16} />
              测试连接
            </button>
            <button onClick={() => void inspect()} disabled={loading === "schema"}>
              <Table2 size={16} />
              读取库表
            </button>
          </div>
          {isDataSourceDirty && <div className="inline-note">当前数据源有未保存修改。</div>}
          {connectionMessage && (
            <div className={connectionMessage.includes("ok") ? "inline-note success" : "inline-note"}>
              {connectionMessage}
            </div>
          )}

          <PanelTitle icon={<BookOpen size={18} />} title="数据源知识库" />
          <textarea
            className="knowledge-area"
            value={knowledgeBase}
            onChange={(event) => {
              setKnowledgeBase(event.target.value);
              setIsDataSourceDirty(true);
            }}
            placeholder="粘贴 README、指标口径、字段含义、别名、业务规则..."
          />
          <label className="file-input">
            <Upload size={16} />
            上传 txt / md / csv / xlsx
            <input
              type="file"
              accept=".txt,.md,.csv,.xlsx"
              onChange={(event) => void handleKnowledgeFile(event.target.files?.[0] || null)}
            />
          </label>

          <PanelTitle icon={<FileText size={18} />} title="本次生成补充" />
          <textarea
            className="context-area"
            value={businessContext}
            onChange={(event) => setBusinessContext(event.target.value)}
            placeholder="临时补充本次评测偏好的问题范围、业务场景或排除项..."
          />

          <PanelTitle icon={<Play size={18} />} title="生成设置" />
          <Field
            label="问题数量"
            value={String(questionCount)}
            onChange={(value) => setQuestionCount(Math.max(1, Math.min(200, Number(value) || 100)))}
          />
          <button className="primary" onClick={startRun} disabled={loading === "run"}>
            <Play size={16} />
            {loading === "run" ? "正在启动..." : "生成评测集"}
          </button>
        </aside>

        <section className="main-panel">
          <div className="panel">
            <PanelTitle icon={<Activity size={18} />} title="任务状态" />
            {currentRun && (
              <div className="stage-banner">
                <div>
                  <span>{currentRun.run.stage}</span>
                  <strong>{currentRun.run.stage_message || currentRun.run.status}</strong>
                </div>
                <small>
                  {processed}/{currentRun.run.question_count}
                </small>
              </div>
            )}
            <div className="metrics">
              <Metric label="成功" value={success} tone="success" />
              <Metric label="失败" value={failed} tone="danger" />
              <Metric label="已处理" value={total} />
              <Metric label="进度" value={`${progress}%`} />
            </div>
            <div className="progress-track">
              <div style={{ width: `${progress}%` }} />
            </div>
            {currentRun && (
              <div className="run-summary">
                <span>任务 #{currentRun.run.id}</span>
                <span>{currentRun.run.db_name}</span>
                <span>{currentRun.run.status}</span>
                <span>{currentRun.run.updated_at}</span>
              </div>
            )}
            {currentRunError && (
              <div className="alert danger">
                <strong>任务失败原因</strong>
                <span>{currentRunError}</span>
              </div>
            )}
            <div className="button-row">
              <button onClick={() => currentRunId && void refreshRun(currentRunId)}>
                <RefreshCw size={16} />
                刷新
              </button>
              <button onClick={retryFailed} disabled={!currentRunId || failed === 0 || loading === "retry"}>
                <AlertCircle size={16} />
                重试失败题
              </button>
              {currentRunId && (
                <>
                  <a className="button-link" href={`/api/runs/${currentRunId}/export?format=xlsx`}>
                    <Download size={16} />
                    Excel
                  </a>
                  <a className="button-link" href={`/api/runs/${currentRunId}/export?format=jsonl`}>
                    <Download size={16} />
                    JSONL
                  </a>
                </>
              )}
            </div>
          </div>

          <div className="split-panels">
            <div className="panel">
              <div className="panel-title-row">
                <PanelTitle icon={<Table2 size={18} />} title="库表预览" />
                <span className="mini-stat">
                  {schema.length} 表 / {schemaColumnCount} 字段
                </span>
              </div>
              <div className="table-list">
                {loading === "schema" && <StateBox title="正在读取库表" text="正在连接 MySQL 并读取 information_schema。" />}
                {schemaError && <StateBox tone="danger" title="库表读取失败" text={schemaError} />}
                {!schemaError && schema.length === 0 && loading !== "schema" && (
                  <StateBox title="尚未读取库表" text="选择或保存数据源后，可实时读取当前库表结构。" />
                )}
                {schema.map((table) => (
                  <details key={table.name}>
                    <summary>
                      <span>{table.name}</span>
                      <small>{table.columns.length} columns</small>
                    </summary>
                    {table.comment && <p className="table-comment">{table.comment}</p>}
                    <div className="columns">
                      {table.columns.map((column) => (
                        <span key={column.name} title={column.comment || column.type}>
                          {column.name}
                          <small>{column.type}</small>
                        </span>
                      ))}
                    </div>
                    {table.samples.length > 0 && (
                      <pre className="sample-preview">{JSON.stringify(table.samples.slice(0, 2), null, 2)}</pre>
                    )}
                  </details>
                ))}
              </div>
            </div>

            <div className="panel">
              <PanelTitle icon={<Database size={18} />} title="历史任务" />
              <div className="run-list">
                {runs.length === 0 && <p className="muted">暂无历史任务。</p>}
                {runs.map((run) => (
                  <button
                    key={run.id}
                    className={run.id === currentRunId ? "run active" : "run"}
                    onClick={() => setCurrentRunId(run.id)}
                  >
                    <span>
                      #{run.id} {run.db_name}
                    </span>
                    <small className={run.status === "failed" ? "danger-text" : ""}>{run.status}</small>
                    {run.stage_message && <em>{run.stage_message}</em>}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="panel">
            <PanelTitle icon={<FileText size={18} />} title="问题与标准答案" />
            <div className="question-list">
              {!currentRun && <StateBox title="尚未选择任务" text="启动或选择历史任务后，这里会显示题目、SQL、答案和错误。" />}
              {currentRun && currentRun.questions.length === 0 && currentRun.run.status === "failed" && (
                <StateBox tone="danger" title="任务没有生成题目" text={currentRun.run.error || "任务在生成问题前失败。"} />
              )}
              {currentRun && currentRun.questions.length === 0 && currentRun.run.status !== "failed" && (
                <StateBox title="等待题目生成" text="任务运行中时，题目会逐步出现在这里。" />
              )}
              {currentRun?.questions.map((question) => (
                <article className="question" key={question.id}>
                  <div className="question-head">
                    <strong>{question.question}</strong>
                    <span className={question.status === "success" ? "badge success" : "badge danger"}>
                      {question.status}
                    </span>
                  </div>
                  {question.answer_summary && (
                    <div className="natural-answer">
                      <span>自然答案</span>
                      <p>{question.answer_summary}</p>
                    </div>
                  )}
                  {question.business_intent && <p className="intent">业务意图：{question.business_intent}</p>}
                  {question.error && (
                    <div className="alert danger compact">
                      <strong>执行错误</strong>
                      <span>{question.error}</span>
                    </div>
                  )}
                  <pre>{question.sql}</pre>
                  {question.result_preview.length > 0 && (
                    <pre className="sample-preview">{JSON.stringify(question.result_preview.slice(0, 3), null, 2)}</pre>
                  )}
                </article>
              ))}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

function StateBox({ title, text, tone }: { title: string; text: string; tone?: "danger" }) {
  return (
    <div className={`state-box ${tone || ""}`}>
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

function PanelTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text"
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Metric({ label, value, tone }: { label: string; value: number | string; tone?: "success" | "danger" }) {
  return (
    <div className={`metric ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function readableError(error: unknown, fallback: string): string {
  if (!(error instanceof Error)) return fallback;
  try {
    const parsed = JSON.parse(error.message);
    return parsed.detail || parsed.message || error.message;
  } catch {
    return error.message || fallback;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
