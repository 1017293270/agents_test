# MySQL 问数评测集生成器

一个本地 Web 工具，用 MySQL 库表、业务说明文档和少量样例值生成问数评测集。它调用 Claude Code CLI 生成自然语言问题和候选 SQL，后端只允许执行单条 `SELECT`，然后导出 Excel 和 JSONL 给数据治理平台做可靠性对比。

## 功能

- 连接 MySQL，读取表、字段、字段注释和少量样例值。
- 粘贴或上传 `.txt`、`.md`、`.csv`、`.xlsx` 业务说明。
- 调用 `claude -p --output-format json` 生成问题和 SQL。
- 后端执行 SELECT-only 校验、超时、默认行数限制和失败重试。
- SQLite 保存任务、问题、SQL、标准答案和错误。
- 导出 `run-<id>.xlsx` 与 `run-<id>.jsonl`，其中 `natural_answer` / `answer_summary` 是面向人工阅读的自然语言答案。

## 本地开发

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
npm install
```

启动后端：

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

启动前端：

```powershell
npm run dev
```

访问 `http://127.0.0.1:5173`。

## Docker 部署

服务器上可以用 Docker Compose 部署。注意：宿主机安装了 Claude Code CLI，不代表容器里自动可用；这个镜像会在容器内安装 `@anthropic-ai/claude-code`，还需要把认证信息挂进容器。

```powershell
docker compose up --build -d
```

访问 `http://服务器IP:8000`。

默认 compose 会挂载：

- `./data:/app/data`
- `./exports:/app/exports`
- `${CLAUDE_CONFIG_DIR:-~/.claude}:/root/.claude:ro`

如果你的 Claude Code 配置目录不在 `~/.claude`，启动前设置：

```powershell
$env:CLAUDE_CONFIG_DIR="C:\Users\你的用户名\.claude"
docker compose up --build -d
```

Linux 上如果 MySQL 在宿主机本机，容器里不要填 `localhost`，可以填 `host.docker.internal` 或宿主机内网地址。

## CI/CD

项目内置 GitHub Actions：

- `.github/workflows/ci.yml`：PR/push 时运行后端测试、前端构建、Docker Compose 校验和镜像构建。
- `.github/workflows/deploy.yml`：推送到 `main` 或手动触发时，通过 SSH 上传代码包到服务器并执行 `docker compose up --build -d`。

部署需要在 GitHub Actions Secrets 配置 `SERVER_HOST`、`SERVER_USER`、`SERVER_SSH_KEY`、`DEPLOY_PATH`，可选配置 `SERVER_PORT`、`CLAUDE_CONFIG_DIR`。详细说明见 `docs/deployment.md`。

## 健康检查

- `GET /api/health`
- `GET /api/health/claude`

`/api/health/claude` 会检查 `claude --version`，并执行一次最小非交互 prompt。

## 安全边界

- 建议使用 MySQL 只读账号。
- SQL 必须是单条 `SELECT`。
- 禁止多语句、DDL、DML、`INTO OUTFILE`、`FOR UPDATE` 等危险读写模式。
- MySQL 密码只用于当前请求，不写入 SQLite。
