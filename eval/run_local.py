"""Local dev-set runner (week-1 baseline) — drives serve.py over the PLE
serve protocol WITHOUT the official kit (kit execution is blocked pending
Yudhi's go-ahead after an execution-risk flag) and WITHOUT the gated HF
dataset (needs an HF account + access request + HF_TOKEN).

This is my own code. It speaks the protocol documented in the kit's
docs/protocol.md: it sends one `task` frame, answers the harness's
`exec` / `read_file` / `write_file` / `http` requests against a local
workdir, records `log` / `usage` frames, and collects `done` / `error`.

Usage:
  python eval/run_local.py --task-dir eval/tasks-local/synthetic-smoke \
      --timeout-sec 600 --out eval/runs/synthetic-smoke-1

The model key is read from the mode-600 key file at runtime and NEVER
printed or written anywhere. No grading is done here: official scores
need the kit's eval/run.py + the task graders. The self-check only
verifies each declared deliverable exists, is non-empty, has no
TODO/placeholder markers, and (for .py) compiles.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import py_compile
import subprocess
import sys
import time

import websockets

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_FILE_100MS = os.path.expanduser(
    "~/workspace/goals/100milionseek-signup-monitoring/hidden_files/api-key.txt"
)
MAX_OUTPUT_BYTES = 100_000
MAX_READ_BYTES = 10_000_000


def _truncate_output(data: bytes) -> tuple[str, bool]:
    if len(data) <= MAX_OUTPUT_BYTES:
        return data.decode("utf-8", "replace"), False
    half = MAX_OUTPUT_BYTES // 2
    head = data[:half].decode("utf-8", "replace")
    tail = data[-half:].decode("utf-8", "replace")
    return (f"{head}\n[... {len(data) - MAX_OUTPUT_BYTES} bytes cut ...]\n"
            f"{tail}"), True


class LocalEvaluator:
    """Answers harness protocol requests against a local workdir."""

    def __init__(self, workdir: str):
        self.workdir = workdir
        self.requests: dict[str, int] = {}
        self.usage = {"input_tokens": 0, "output_tokens": 0,
                      "cache_read_tokens": 0, "calls": 0}
        self.log_lines: list[str] = []

    def _count(self, kind: str) -> None:
        self.requests[kind] = self.requests.get(kind, 0) + 1

    def _resolve(self, path: str) -> str:
        if os.path.isabs(path):
            p = os.path.normpath(path)
        else:
            p = os.path.normpath(os.path.join(self.workdir, path))
        if os.path.commonpath([p, self.workdir]) != self.workdir:
            raise ValueError(f"path escapes workdir: {path}")
        return p

    async def handle(self, msg: dict) -> dict | None:
        kind = msg.get("type")
        rid = msg.get("id")
        if kind == "exec":
            self._count("exec")
            return await self._exec(rid, msg)
        if kind == "read_file":
            self._count("read_file")
            return self._read_file(rid, msg)
        if kind == "write_file":
            self._count("write_file")
            return self._write_file(rid, msg)
        if kind == "http":
            self._count("http")
            return {"type": "result", "id": rid, "ok": False,
                    "error": "no MCP servers in local runs"}
        if kind == "log":
            self._count("log")
            text = str(msg.get("text") or "")
            self.log_lines.append(text)
            return None
        if kind == "usage":
            self._count("usage")
            self.usage["calls"] += 1
            for key in ("input_tokens", "output_tokens", "cache_read_tokens"):
                try:
                    self.usage[key] += int(msg.get(key) or 0)
                except (TypeError, ValueError):
                    pass
            return None
        return None  # done / error handled by the caller

    async def _exec(self, rid: str, msg: dict) -> dict:
        command = msg.get("command") or ""
        timeout = msg.get("timeout_sec") or 120
        try:
            timeout = max(1, min(int(timeout), 600))
        except (TypeError, ValueError):
            timeout = 120
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c", command, cwd=self.workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(),
                                                timeout=timeout)
                timed_out = False
                code = proc.returncode
            except asyncio.TimeoutError:
                proc.kill()
                out, _ = await proc.communicate()
                timed_out = True
                code = 124
        except Exception as exc:  # noqa: BLE001
            return {"type": "result", "id": rid, "ok": False, "error": str(exc)}
        text, truncated = _truncate_output(out or b"")
        return {"type": "result", "id": rid, "ok": True, "exit_code": code,
                "output": text, "truncated": truncated, "timed_out": timed_out}

    def _read_file(self, rid: str, msg: dict) -> dict:
        try:
            path = self._resolve(str(msg.get("path") or ""))
            if not os.path.isfile(path):
                return {"type": "result", "id": rid, "ok": False,
                        "error": f"no such file: {msg.get('path')}"}
            size = os.path.getsize(path)
            if size > MAX_READ_BYTES:
                return {"type": "result", "id": rid, "ok": False,
                        "error": f"file over 10 MB: {size} bytes"}
            with open(path, "rb") as f:
                data = f.read()
            return {"type": "result", "id": rid, "ok": True,
                    "content_b64": base64.b64encode(data).decode(),
                    "size": size, "truncated": False}
        except ValueError as exc:
            return {"type": "result", "id": rid, "ok": False, "error": str(exc)}
        except OSError as exc:
            return {"type": "result", "id": rid, "ok": False, "error": str(exc)}

    def _write_file(self, rid: str, msg: dict) -> dict:
        try:
            path = self._resolve(str(msg.get("path") or ""))
            data = base64.b64decode(msg.get("content_b64") or "")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            mode = "ab" if msg.get("append") else "wb"
            with open(path, mode) as f:
                f.write(data)
            return {"type": "result", "id": rid, "ok": True,
                    "size": os.path.getsize(path)}
        except (ValueError, OSError) as exc:
            return {"type": "result", "id": rid, "ok": False, "error": str(exc)}


def self_check(workdir: str, deliverables: list[str]) -> dict:
    """Deliverable presence/format check (no grading, no code execution
    except py_compile on agent-produced .py files)."""
    results = {}
    for rel in deliverables:
        path = os.path.join(workdir, rel)
        entry: dict = {"path": rel}
        if not os.path.isfile(path):
            entry.update(status="MISSING")
        else:
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                data = f.read()
            text = data.decode("utf-8", "replace")
            markers = [m for m in ("TODO", "PLACEHOLDER", "Lorem ipsum",
                                   "[...]", "TBD")
                       if m in text]
            entry.update(status="OK" if size > 0 and not markers
                         else "SUSPECT", size=size, markers=markers)
            if rel.endswith(".py"):
                try:
                    py_compile.compile(path, doraise=True)
                    entry["compiles"] = True
                except py_compile.PyCompileError as exc:
                    entry["compiles"] = False
                    entry["compile_error"] = str(exc)[:300]
        results[rel] = entry
    return results


async def run_task(args) -> dict:
    with open(os.path.join(args.task_dir, "instruction.md")) as f:
        instruction = f.read()
    with open(os.path.join(args.task_dir, "task.json")) as f:
        spec = json.load(f)
    deliverables = spec.get("deliverables", [])

    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    # Copy the task's input files (everything except instruction/task spec).
    subprocess.run(["cp", "-r", os.path.join(args.task_dir, "files") + "/.",
                    workdir + "/"], check=False)
    with open(KEY_FILE_100MS) as f:
        api_key = f.read().strip()

    port = args.port
    env = dict(os.environ)
    env.update({
        "PORT": str(port),
        "OPENAI_BASE_URL": "https://100milionseek.top/v1",
        "OPENAI_API_KEY": api_key,
        "MODEL_NAME": "deepseek-v4.1-flash-free",
    })
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "serve.py", cwd=HARNESS_DIR, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    evaluator = LocalEvaluator(workdir)
    record: dict = {"task": spec.get("id"), "model": env["MODEL_NAME"],
                    "timeout_sec": args.timeout_sec, "started": time.time()}
    try:
        uri = f"ws://127.0.0.1:{port}"
        ws = None
        for _ in range(60):
            try:
                ws = await websockets.connect(uri, max_size=16 << 20,
                                              ping_interval=None)
                break
            except OSError:
                await asyncio.sleep(0.5)
        if ws is None:
            record.update(status="SERVER_NOT_UP",
                          server_log=(await _drain(proc))[:2000])
            return record
        async with ws:
            await ws.send(json.dumps({
                "type": "task", "protocol": 1, "session": "local-run",
                "instruction": instruction, "workdir": workdir,
                "limits": {"agent_timeout_sec": args.timeout_sec,
                           "exec_timeout_sec": 600,
                           "max_output_bytes": 100000,
                           "max_write_bytes": 10000000},
                "mcp_servers": []}))
            deadline = time.monotonic() + args.timeout_sec + 120
            final_message = ""
            status = "TIMEOUT"
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(), timeout=max(1, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                mtype = msg.get("type")
                if mtype == "done":
                    final_message = msg.get("final_message") or ""
                    status = "DONE"
                    break
                if mtype == "error":
                    final_message = msg.get("message") or ""
                    status = "ERROR"
                    break
                if mtype == "cancel":
                    status = "CANCELLED"
                    break
                reply = await evaluator.handle(msg)
                if reply is not None:
                    await ws.send(json.dumps(reply))
            record.update(status=status, final_message=final_message)
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 10)
            except asyncio.TimeoutError:
                proc.kill()
        out, _ = await proc.communicate()
        record["server_log_tail"] = (out or b"").decode(
            "utf-8", "replace")[-2000:]
    record.update(ended=time.time(),
                  duration_sec=round(time.time() - record["started"], 1),
                  requests=evaluator.requests, usage=evaluator.usage,
                  log=evaluator.log_lines,
                  self_check=self_check(workdir, deliverables))
    return record


async def _drain(proc) -> str:
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 5)
        return (out or b"").decode("utf-8", "replace")
    except asyncio.TimeoutError:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-dir", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--timeout-sec", type=int, default=600)
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    record = asyncio.run(run_task(args))
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "run.json"), "w") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    print(f"task={record.get('task')} status={record.get('status')} "
          f"duration={record.get('duration_sec')}s "
          f"usage_in={record['usage']['input_tokens']} "
          f"usage_out={record['usage']['output_tokens']} "
          f"requests={record['requests']}")
    for rel, check in record.get("self_check", {}).items():
        print(f"  deliverable {rel}: {check.get('status')}"
              + (f" size={check.get('size')}" if check.get("size") else "")
              + (f" markers={check.get('markers')}" if check.get("markers")
                 else ""))
    print(f"  final_message: {(record.get('final_message') or '')[:400]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
