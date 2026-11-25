"""Smoke tests for the Cryptoboy PLE harness (no network, no model calls).

Run:  python -m pytest tests/ -q        (or: python tests/test_smoke.py)
Covers:
  - module imports without env vars / API keys set
  - tool definitions are valid OpenAI function specs
  - prompt templates render with all placeholders filled
  - time-budget math (stage wrap-up points)
  - agent_loop returns a final message against a stubbed model client
  - solve() runs end-to-end against a fake session + stubbed client
"""

import asyncio
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importing must work with NO env vars set (no MODEL_NAME, no API key).
for var in ("MODEL_NAME", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
    os.environ.pop(var, None)

import harness  # noqa: E402


# --- Fake OpenAI client -------------------------------------------------------

class _FakeMessage:
    def __init__(self, content, tool_calls=None, finish_reason="stop"):
        self.content = content
        self.tool_calls = tool_calls
        self.finish_reason = finish_reason

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


class _FakeChoice:
    def __init__(self, message):
        self.message = message
        self.finish_reason = message.finish_reason


class _FakeReply:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]
        self.usage = None


class FakeCompletions:
    """First call per role returns a tool call, then a plain final answer."""

    def __init__(self, script):
        self.script = script  # list of (tool_name, args) or ("TEXT", text)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        if step[0] == "TEXT":
            return _FakeReply(_FakeMessage(step[1]))
        name, args = step
        call = {
            "id": f"call_{self.calls}",
            "type": "function",
            "function": {"name": name, "arguments": args},
        }
        return _FakeReply(_FakeMessage("", tool_calls=[call]))


class FakeClient:
    def __init__(self, script):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(script))


# --- Fake taskbridge session --------------------------------------------------

class FakeSession:
    def __init__(self):
        self.instruction = ("Design check: verify the beam. Deliverable: "
                            "write /tmp/smoke/memo.md with the result.")
        self.workdir = "/tmp/smoke"
        self.mcp_servers = []
        self.final_message = ""
        self.files = {}
        self.logs = []
        self._left = 21600.0

    def time_left(self):
        return self._left

    async def log(self, msg):
        self.logs.append(msg)

    async def usage(self, *args, **kwargs):
        pass

    async def exec(self, command):
        return {"exit_code": 0, "output": "ok\n"}

    async def read_file(self, path):
        return self.files.get(path, "").encode()

    async def write_file(self, path, content):
        self.files[path] = content
        return len(content.encode())


# --- Tests ----------------------------------------------------------------------

def test_import_without_env():
    assert harness.model_name() == "unknown-model"
    assert harness.reasoning_effort() == "high"


def test_tool_specs_valid():
    for tool in harness.READ_TOOLS + harness.WRITE_TOOLS:
        fn = tool["function"]
        assert fn["name"] in ("bash", "read_file", "write_file")
        assert fn["parameters"]["type"] == "object"
        assert set(fn["parameters"]["required"]) == set(
            fn["parameters"]["properties"])
    names = [t["function"]["name"] for t in harness.WRITE_TOOLS]
    assert names == ["bash", "read_file", "write_file"]
    assert [t["function"]["name"] for t in harness.READ_TOOLS] == [
        "bash", "read_file"]


def test_prompts_render():
    for template, kwargs in [
        (harness.PLANNER, {"workdir": "/app"}),
        (harness.WORKER, {"workdir": "/app", "plan": "PLAN"}),
        (harness.CALC_VERIFIER, {"workdir": "/app"}),
        (harness.VERIFIER, {"workdir": "/app", "instruction": "I",
                            "plan": "P", "summary": "S"}),
        (harness.FIX, {"issues": "1. x"}),
    ]:
        rendered = template.format(**kwargs)
        assert "{" not in rendered, f"unfilled placeholder in {template[:40]}"


def test_time_budget_math():
    total = 21600  # 6 h
    assert harness._left_at(total, 1.0 - harness.PLAN_SHARE) == 19440.0
    assert harness._left_at(total, harness.WORK_UNTIL_LEFT) == 5400.0
    assert harness._left_at(total, harness.CALC_UNTIL_LEFT) == 3888.0
    assert harness._left_at(total, harness.VERIFY_UNTIL_LEFT) == 2700.0
    assert harness._left_at(None, 0.25) is None


def test_clip():
    assert harness.clip("abc") == "abc"
    long = "x" * (harness.RESULT_CHARS + 100)
    assert len(harness.clip(long)) < len(long)
    assert "characters cut" in harness.clip(long)


def test_agent_loop_with_stub():
    async def _run():
        session = FakeSession()
        client = FakeClient([
            ("bash", '{"command": "echo hi"}'),
            ("TEXT", "Done: beam verified, memo written."),
        ])
        out = await harness.agent_loop(
            session,
            [{"role": "system", "content": "test"},
             {"role": "user", "content": "do it"}],
            harness.WRITE_TOOLS,
            wrap_up_left_sec=1000,
            client=client,
        )
        assert out == "Done: beam verified, memo written."
        assert session.final_message == out
        return True

    assert asyncio.run(_run())


def test_solve_end_to_end_with_stub():
    """solve() with a stub model: planner -> worker writes -> calc PASS ->
    verifier PASS. No real model, no network."""
    async def _run():
        session = FakeSession()
        # Every stage gets: one tool call, then a final text answer.
        # Planner: read a file. Worker: write the memo. Calc: bash re-run.
        # Verifier: plain PASS (no tool call).
        script = [
            ("read_file", '{"path": "/tmp/smoke/input.txt"}'),
            ("TEXT", "PLAN: deliver memo.md; method: python calc; "
                     "constraints: none."),
            ("write_file", '{"path": "/tmp/smoke/memo.md", '
                           '"content": "# Memo\\nResult: 42 kN.\\n"}'),
            ("TEXT", "Done: memo.md written, result 42 kN."),
            ("bash", '{"command": "python3 -c \\"print(42)\\""}'),
            ("TEXT", "CALC: PASS"),
            ("TEXT", "PASS"),
        ]
        client = FakeClient(script)
        out = await harness.solve(session, client=client)
        assert "memo.md" in out or "42 kN" in out, out
        assert "/tmp/smoke/memo.md" in session.files
        assert "42 kN" in session.files["/tmp/smoke/memo.md"]
        return True

    assert asyncio.run(_run())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all smoke tests passed")
