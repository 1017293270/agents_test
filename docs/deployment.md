# 自动部署说明

这个项目支持 GitHub Actions + SSH + Docker Compose 部署到一台 Linux 服务器。

## 服务器准备

服务器需要安装：

- Docker
- Docker Compose
- 能访问目标 MySQL 的网络

不需要在服务器宿主机安装 Node.js / npm。这个项目是 Docker 部署，前端构建和 Claude Code CLI 安装都会在镜像构建过程中完成；宿主机只要能运行 Docker，并且构建镜像时能访问 npm registry 即可。

建议创建部署目录：

```bash
sudo mkdir -p /opt/mysql-question-evaluator
sudo chown -R "$USER":"$USER" /opt/mysql-question-evaluator
mkdir -p /opt/mysql-question-evaluator/data /opt/mysql-question-evaluator/exports
```

如果 MySQL 在宿主机本机，页面里不要填 `localhost`，填：

```text
host.docker.internal
```

或者填服务器内网 IP。

## Claude Code 认证方式

项目后端仍然通过容器内的 `claude` 命令调用 Claude Code CLI，但认证可以有两种方式。

### 方式 A：外接 API / 无 Node.js 服务器，推荐给你当前场景

服务器宿主机不需要安装 Node.js、npm 或 Claude Code。只需要在 GitHub Actions Secrets 里配置 API 相关变量，部署脚本会把它们作为环境变量传进容器。

最常用配置：

```text
ANTHROPIC_API_KEY=你的 Anthropic API Key
```

如果你走第三方网关、企业代理或兼容服务，可以按你的网关要求补充：

```text
ANTHROPIC_AUTH_TOKEN=你的 Bearer token
ANTHROPIC_BASE_URL=https://你的网关地址
ANTHROPIC_MODEL=你的网关支持的模型名
ANTHROPIC_SMALL_FAST_MODEL=你的网关支持的小模型名
```

只要配置了 API 方式，`CLAUDE_CONFIG_DIR` 可以不填。

### 方式 B：挂载服务器上的 Claude Code 登录目录

Docker 镜像会在容器内执行：

```bash
npm install -g @anthropic-ai/claude-code
```

所以容器里会有 `claude` 命令。但 Claude Code 的认证不会写进镜像，你仍然需要在服务器宿主机上登录一次，生成可挂载的认证目录。

服务器宿主机安装和登录示例：

```bash
# 安装 Node.js 20+ 或 22+ 后执行
npm install -g @anthropic-ai/claude-code

# 检查安装
claude --version

# 首次登录/认证，按提示完成
claude

# 验证非交互调用
echo "Reply with exactly ok" | claude -p --output-format json --no-session-persistence
```

认证成功后，通常会生成：

```text
~/.claude
```

然后在 GitHub Secrets 里设置：

```text
CLAUDE_CONFIG_DIR=/home/你的用户/.claude
```

如果你用 `root` 用户登录服务器，通常是：

```text
CLAUDE_CONFIG_DIR=/root/.claude
```

如果你没有设置 `CLAUDE_CONFIG_DIR`，compose 会默认挂载服务器上的 `~/.claude` 到容器里的 `/root/.claude`。

## GitHub Secrets

在 GitHub 仓库里进入 `Settings -> Secrets and variables -> Actions`，添加：

| Secret | 必填 | 示例 | 说明 |
| --- | --- | --- | --- |
| `SERVER_HOST` | 是 | `1.2.3.4` | 服务器公网 IP 或域名 |
| `SERVER_USER` | 是 | `ubuntu` | SSH 用户 |
| `SERVER_SSH_KEY` | 二选一 | 私钥内容 | 能登录服务器的 SSH 私钥，推荐 |
| `SERVER_PASSWORD` | 二选一 | `your-password` | SSH 密码，不推荐但可用 |
| `SERVER_PORT` | 否 | `22` | SSH 端口，不填默认 22 |
| `DEPLOY_PATH` | 是 | `/opt/mysql-question-evaluator` | 服务器部署目录 |
| `ANTHROPIC_API_KEY` | 推荐 | `sk-ant-...` | 外接 API 模式，最简单 |
| `ANTHROPIC_AUTH_TOKEN` | 否 | `...` | 第三方网关/代理模式 Bearer token |
| `ANTHROPIC_BASE_URL` | 否 | `https://api.example.com` | 第三方网关/代理地址 |
| `ANTHROPIC_MODEL` | 否 | `your-model-name` | 指定 Claude Code 使用的大模型 |
| `ANTHROPIC_SMALL_FAST_MODEL` | 否 | `your-small-model-name` | 指定小模型/快速模型 |
| `CLAUDE_CONFIG_DIR` | 否 | `/home/ubuntu/.claude` | 登录目录挂载模式才需要 |
| `NODE_BASE_IMAGE` | 否 | `docker.m.daocloud.io/library/node:22-bookworm-slim` | Docker Hub 拉取慢时覆盖 Node 基础镜像 |
| `PYTHON_BASE_IMAGE` | 否 | `docker.m.daocloud.io/library/python:3.12-slim` | Docker Hub 拉取慢时覆盖 Python 基础镜像 |
| `NPM_REGISTRY` | 否 | `https://registry.npmmirror.com` | npm registry 慢时覆盖 |

`SERVER_SSH_KEY` 和 `SERVER_PASSWORD` 选一个即可。推荐使用 `SERVER_SSH_KEY`，因为密码长期放在 GitHub Secrets 里风险更高；如果先图快，可以先用 `SERVER_PASSWORD` 跑通，后续再换成 SSH key。

## 部署流程

推送到 `main` 会自动执行：

1. 后端测试
2. 前端构建
3. Docker Compose 配置校验
4. 打包代码并上传服务器
5. 在服务器执行 `docker compose up --build -d`
6. 检查 `/api/health` 和 `/api/health/claude`

也可以在 GitHub Actions 页面手动运行 `Deploy` workflow。

## 服务器上手动检查

```bash
cd /opt/mysql-question-evaluator
docker compose ps
docker compose logs -f evaluator
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/claude
```

## Docker Hub 超时

如果部署日志出现类似：

```text
failed to resolve source metadata for docker.io/library/python:3.12-slim
dial tcp ... registry-1.docker.io:443: i/o timeout
```

说明服务器访问 Docker Hub 超时。自动部署默认会在服务器构建时使用下面的国内镜像配置：

```text
NODE_BASE_IMAGE=docker.m.daocloud.io/library/node:22-bookworm-slim
PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
NPM_REGISTRY=https://registry.npmmirror.com
```

如果你的服务器能直连 Docker Hub，也可以在 GitHub Secrets 里把 `NODE_BASE_IMAGE`、`PYTHON_BASE_IMAGE` 改回官方镜像。

## Claude Code 注意事项

镜像会安装 Claude Code CLI，但认证不写进镜像。外接 API 模式下，认证来自环境变量：

```yaml
environment:
  ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
  ANTHROPIC_AUTH_TOKEN: ${ANTHROPIC_AUTH_TOKEN:-}
  ANTHROPIC_BASE_URL: ${ANTHROPIC_BASE_URL:-}
```

登录目录模式下，可以通过 compose 挂载认证目录：

```yaml
volumes:
  - ${CLAUDE_CONFIG_DIR:-~/.claude}:/root/.claude:ro
```

部署失败时，优先看：

```bash
docker compose exec evaluator claude --version
docker compose exec evaluator claude -p --output-format json --no-session-persistence <<< "Reply with exactly ok"
```
