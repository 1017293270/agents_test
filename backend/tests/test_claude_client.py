import json
import subprocess

from app.claude_client import ClaudeClient, ClaudeClientError, resolve_claude_bin


class FakeRunner:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], self.returncode, stdout=self.stdout, stderr="")


def test_claude_client_parses_json_text_response():
    payload = {
        "result": json.dumps(
            {
                "questions": [
                    {
                        "question": "本月销售额是多少？",
                        "business_intent": "统计本月销售额",
                        "tables": ["orders"],
                        "sql": "select sum(amount) as sales from orders",
                    }
                ]
            },
            ensure_ascii=False,
        )
    }
    runner = FakeRunner(json.dumps(payload, ensure_ascii=False))
    client = ClaudeClient(claude_bin="claude", timeout_seconds=5, runner=runner, resolver=lambda value: value)

    result = client.generate_questions("prompt")

    assert result["questions"][0]["question"] == "本月销售额是多少？"
    command = runner.calls[0][0][0]
    assert command[:2] == ["claude", "-p"]
    assert "--output-format" in command
    assert runner.calls[0][1]["input"] == "prompt"


def test_claude_client_parses_direct_json_response():
    runner = FakeRunner(
        json.dumps(
            {
                "questions": [
                    {
                        "question": "客户数量是多少？",
                        "business_intent": "统计客户数",
                        "tables": ["customers"],
                        "sql": "select count(*) from customers",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )
    client = ClaudeClient(claude_bin="claude", timeout_seconds=5, runner=runner, resolver=lambda value: value)

    result = client.generate_questions("prompt")

    assert result["questions"][0]["tables"] == ["customers"]


def test_resolve_claude_bin_uses_full_cmd_path(monkeypatch):
    def fake_which(name: str):
        if name == "claude":
            return r"D:\nodejs\node_global\claude.CMD"
        return None

    monkeypatch.setattr("app.claude_client.shutil.which", fake_which)

    assert resolve_claude_bin("claude") == r"D:\nodejs\node_global\claude.CMD"


def test_missing_claude_cli_returns_actionable_error():
    def missing_runner(*args, **kwargs):
        raise FileNotFoundError()

    client = ClaudeClient(
        claude_bin="claude",
        timeout_seconds=5,
        runner=missing_runner,
        resolver=lambda value: value,
    )

    try:
        client.generate_questions("prompt")
    except ClaudeClientError as exc:
        assert "CLAUDE_BIN" in str(exc)
        assert "claude.cmd" in str(exc)
    else:
        raise AssertionError("Expected ClaudeClientError")
