import json
import shutil
import subprocess
from typing import Any, Callable


Runner = Callable[..., subprocess.CompletedProcess[str]]
Resolver = Callable[[str], str]


class ClaudeClientError(RuntimeError):
    pass


class ClaudeClient:
    def __init__(
        self,
        claude_bin: str,
        timeout_seconds: int,
        max_budget_usd: float | None = None,
        runner: Runner = subprocess.run,
        resolver: Resolver | None = None,
    ):
        self.requested_claude_bin = claude_bin
        self.claude_bin = (resolver or resolve_claude_bin)(claude_bin)
        self.timeout_seconds = timeout_seconds
        self.max_budget_usd = max_budget_usd
        self.runner = runner

    def generate_questions(self, prompt: str) -> dict[str, Any]:
        return self.ask_json(prompt)

    def repair_sql(self, prompt: str) -> dict[str, Any]:
        return self.ask_json(prompt)

    def ask_text(self, prompt: str, timeout_seconds: int | None = None) -> str:
        completed = self._run(prompt, timeout_seconds=timeout_seconds)
        try:
            payload = json.loads(completed.stdout)
            return str(payload.get("result") or payload.get("text") or completed.stdout)
        except json.JSONDecodeError:
            return completed.stdout.strip()

    def version(self) -> str:
        try:
            completed = self.runner(
                [self.claude_bin, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeClientError("Claude version check timed out") from exc
        except FileNotFoundError as exc:
            raise ClaudeClientError(_missing_cli_message(self.requested_claude_bin, self.claude_bin)) from exc
        if completed.returncode != 0:
            raise ClaudeClientError((completed.stderr or completed.stdout or "Claude version check failed").strip())
        return completed.stdout.strip()

    def ask_json(self, prompt: str) -> dict[str, Any]:
        completed = self._run(prompt)
        return _parse_json_response(completed.stdout)

    def _run(self, prompt: str, timeout_seconds: int | None = None) -> subprocess.CompletedProcess[str]:
        command = [
            self.claude_bin,
            "-p",
            "--output-format",
            "json",
            "--no-session-persistence",
        ]
        if self.max_budget_usd is not None:
            command.extend(["--max-budget-usd", str(self.max_budget_usd)])

        try:
            completed = self.runner(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeClientError("Claude CLI timed out") from exc
        except FileNotFoundError as exc:
            raise ClaudeClientError(_missing_cli_message(self.requested_claude_bin, self.claude_bin)) from exc

        if completed.returncode != 0:
            raise ClaudeClientError((completed.stderr or completed.stdout or "Claude CLI failed").strip())
        return completed


def resolve_claude_bin(claude_bin: str) -> str:
    resolved = shutil.which(claude_bin)
    if resolved:
        return resolved

    for suffix in (".cmd", ".exe", ".bat", ".ps1"):
        resolved = shutil.which(f"{claude_bin}{suffix}")
        if resolved:
            return resolved

    return claude_bin


def _missing_cli_message(requested: str, resolved: str) -> str:
    return (
        "找不到 Claude Code CLI 可执行文件。"
        f" 当前配置 CLAUDE_BIN={requested!r}，解析结果={resolved!r}。"
        " 请确认已安装 Claude Code，或把 CLAUDE_BIN 设置为 claude.cmd 的完整路径。"
    )


def _parse_json_response(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeClientError("Claude CLI returned invalid JSON") from exc

    if isinstance(payload, dict) and "questions" in payload:
        return payload

    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.removeprefix("json").strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ClaudeClientError("Claude result was not JSON") from exc
        if isinstance(parsed, dict):
            return parsed

    raise ClaudeClientError("Claude response did not contain a JSON object")
