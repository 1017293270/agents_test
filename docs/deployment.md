# 自动部署说明

这个项目支持 GitHub Actions + SSH + Docker Compose 部署到一台 Linux 服务器。

## 服务器准备

服务器需要安装：

- Docker
- Docker Compose
- 能访问目标 MySQL 的网络
- Claude Code 认证目录，例如 `/home/ubuntu/.claude`

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

## GitHub Secrets

在 GitHub 仓库里进入 `Settings -> Secrets and variables -> Actions`，添加：

| Secret | 必填 | 示例 | 说明 |
| --- | --- | --- | --- |
| `SERVER_HOST` | 是 | `1.2.3.4` | 服务器公网 IP 或域名 |
| `SERVER_USER` | 是 | `ubuntu` | SSH 用户 |
| `SERVER_SSH_KEY` | 是 | 私钥内容 | 能登录服务器的 SSH 私钥 |
| `SERVER_PORT` | 否 | `22` | SSH 端口，不填默认 22 |
| `DEPLOY_PATH` | 是 | `/opt/mysql-question-evaluator` | 服务器部署目录 |
| `CLAUDE_CONFIG_DIR` | 否 | `/home/ubuntu/.claude` | 服务器上的 Claude Code 认证目录 |

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

## Claude Code 注意事项

镜像会安装 Claude Code CLI，但认证不写进镜像，需要通过 compose 挂载认证目录：

```yaml
volumes:
  - ${CLAUDE_CONFIG_DIR:-~/.claude}:/root/.claude:ro
```

部署失败时，优先看：

```bash
docker compose exec evaluator claude --version
docker compose exec evaluator claude -p --output-format json --no-session-persistence <<< "Reply with exactly ok"
```
