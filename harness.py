# Copyright 2026 Yudhi Sutawan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cryptoboy PLE harness: planner -> worker -> calc-verifier -> verifier.

Architecture (why four roles instead of one loop — see README.md):
  1. PLANNER (read-only): explores the task files, writes a structured plan —
     every deliverable with path/format, the engineering method per
     deliverable, and how each result will be checked.
  2. WORKER (bash/read/write): executes the plan. Hard rules: every number
     comes from code, never from mental arithmetic; every computed value is
     recorded in a units ledger (`calc/UNITS.md`) with value, unit, source
     formula, and the script that produced it.
  3. CALC-VERIFIER (read-only + bash): independent re-computation. Re-runs the
     worker's calculation scripts from scratch, checks units and dimensional
     consistency, and checks every hard constraint (safety/feasibility) from
     the task instruction. This is the stage that separates engineering
     passes from failures: a wrong number in a memo is a wrong memo.
  4. DELIVERABLE-VERIFIER (read-only): fresh conversation, sees only the
     instruction, the plan, and the worker's summary — never the worker's
     reasoning. Replies PASS or a numbered list of issues. Issues go back to
     the worker for a fix round (max 2 rounds).

Time budget (fractions of the task's total time limit):
  planner 10% | worker until 25% remains | calc-verify until 18% remains |
  verifier until 12.5% remains | fix rounds until 4 minutes remain.
A stage only starts if >= 2 minutes remain before its wrap-up deadline.

Model access: OpenAI-compatible client against the endpoint the evaluator
injects (OPENAI_BASE_URL / OPENAI_API_KEY / MODEL_NAME). During local dev the
same client points at a personal model (Claude via NaraRouter, Hermes via
9Router, or a local open-weight server) — see README.md. No web search, no
external APIs, no API keys in the repo: the evaluator blocks all of that.
"""

from __future__ import annotations

import asyncio
import json
import os
import re

import openai
import taskbridge

# --- Tunables (env-overridable) -------------------------------------------

MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "32000"))
RESULT_CHARS = 20_000          # longer tool results lose their middle
RETRY_WAITS = (5, 15, 30, 60, 120)
WRAP_UP_SEC = 240              # ask for the summary this far before deadline
MIN_STEP_SEC = 120             # a stage needs at least this much time to start
MAX_FIX_ROUNDS = 2
MAX_NUDGES = 3
CUT_KEEP = 1000                # chars a tool result keeps once context is full

# Time shares of the total task limit (see module docstring).
PLAN_SHARE = 0.10
WORK_UNTIL_LEFT = 0.25
CALC_UNTIL_LEFT = 0.18
VERIFY_UNTIL_LEFT = 0.125

CONTEXT_FULL = re.compile(
    r"context.?(length|window)|prompt is too long|maximum prompt length"
    r"|exceed[^.]{0,40}(token|context)",
    re.I,
)

# --- Prompts ----------------------------------------------------------------

PLANNER = """You are the PLANNER for an engineering task. You can read files and run
read-only commands in the task container (workdir: {workdir}). You cannot write
files.

1. Read the whole task instruction and every file it points to (drawings, specs,
   code tables, templates, prior memos).
2. List every deliverable the task asks for, with its EXACT path and format.
3. For each deliverable, state the engineering method: which code clause /
   standard / formula applies, which inputs come from which file, and what
   calculation or check produces it.
4. State the hard constraints (safety, feasibility, code limits) that must
   never be violated, and how each will be verified.
5. State what a licensed engineer would do first, and where an agent most
   commonly goes wrong on this kind of task.

Reply with the plan only, structured as: DELIVERABLES / METHOD / CONSTRAINTS /
VERIFICATION / RISKS. Do not start the work itself."""

WORKER = """You are the WORKER engineer. You work in the task container (workdir:
{workdir}) with bash, read_file, and write_file. Follow the plan below exactly;
if the plan is wrong, say so in your summary and fix it, but never silently
skip a deliverable.

HARD RULES — breaking one fails the task:
1. COMPUTE WITH CODE, NEVER BY HAND. Every number in a deliverable must be
   produced by a script you ran (python in bash). Keep the script in
   `calc/` next to the deliverable so it can be re-run.
2. UNITS LEDGER. Maintain `calc/UNITS.md`: one line per computed value —
   value, unit, formula/source, script that produced it. A number with no
   unit and no script does not exist.
3. CHECK WHAT YOU WROTE. After writing each deliverable, open it again and
   read it: right path, right format, numbers match the ledger, no
   placeholders, no TODOs.
4. Deliverables go EXACTLY where the task instruction asks, in the format it
   asks. If a path is ambiguous, write to the most literal reading and note it.
5. Never invent a code clause, standard value, or input. If a value is not in
   the task files, say so in the summary — do not guess.

PLAN:
{plan}

When you are done, reply WITHOUT calling a tool: a short summary of each
deliverable, where it is, and the key results (with units)."""

CALC_VERIFIER = """You are the CALC-VERIFIER, an independent checker. You can read files
and run bash in the task container (workdir: {workdir}). You cannot write
files. You have NOT seen the worker's reasoning — only its deliverables,
its calculation scripts, and its units ledger.

1. Re-run every calculation script in `calc/` from scratch. Do the numbers in
   the deliverables match the script outputs exactly?
2. Check units and dimensional consistency for every value in
   `calc/UNITS.md`: is each unit right for the quantity, and are unit
   conversions (mm/m, kN/N, kPa/MPa, kW/W, ...) correct?
3. Check every hard constraint from the task instruction against the
   deliverables (safety factors, code limits, feasibility). One broken hard
   constraint caps the score — list it first if any.
4. Check that each deliverable is at the exact path and format the task asked.

Reply with: RECOMPUTED (match/mismatch per value) / UNIT ERRORS / CONSTRAINT
VIOLATIONS / PATH & FORMAT. End with one line: `CALC: PASS` or
`CALC: FAIL — <numbered issues>`. Be specific: give the wrong value, the
right value, and where it is."""

VERIFIER = """You are the DELIVERABLE-VERIFIER. You can read files and run read-only
commands in the task container (workdir: {workdir}). You have NOT seen the
worker's reasoning — only the task instruction, the plan, and the worker's
summary below.

1. Open every deliverable at its required path. Is it there, in the requested
   format, complete (no placeholders, no missing sections)?
2. Does the content answer what the task asked — the right quantities, the
   right decisions, the right level of justification a licensed engineer
   would expect?
3. Spot-check two numbers against the units ledger: do they match?

TASK INSTRUCTION:
{instruction}

PLAN:
{plan}

WORKER SUMMARY:
{summary}

Reply with either the single word `PASS`, or a numbered list of concrete
issues (file, problem, what to change). Do not rewrite the deliverables
yourself."""

FIX = """Fix the following issues in the deliverables, then re-check what you
changed. Keep the units ledger and calculation scripts consistent with any
number you change.

ISSUES:
{issues}

Reply WITHOUT calling a tool when done: a short summary of what changed."""

WRAP_UP = {
    "role": "user",
    "content": "Time is almost up. Stop and reply with your summary.",
}


# --- Tools ------------------------------------------------------------------

def _tool(name, description, **params):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": v} for k, v in params.items()},
                "required": list(params),
            },
        },
    }


READ_TOOLS = [
    _tool("bash", "Run a bash command (120 s limit); return exit code/output.",
          command="string"),
    _tool("read_file", "Read a text file.", path="string"),
]

WRITE_TOOLS = READ_TOOLS + [
    _tool("write_file", "Create/overwrite a file; parents are created.",
          path="string", content="string"),
]


# --- Client (lazy: importing this module must never need env/network) ------

_client = None


def get_client():
    """Returns the shared OpenAI-compatible async client (created on demand)."""
    global _client
    if _client is None:
        # The evaluator sets OPENAI_BASE_URL/OPENAI_API_KEY for every model;
        # local dev sets the same vars to a personal endpoint. The SDK reads
        # them from the environment, so no key ever lives in this repo.
        _client = openai.AsyncOpenAI(max_retries=5, timeout=1800)
    return _client


def model_name() -> str:
    return os.environ.get("MODEL_NAME", "unknown-model")


def reasoning_effort() -> str:
    """Highest reasoning level the model family accepts (env overrides)."""
    if os.environ.get("REASONING_EFFORT"):
        return os.environ["REASONING_EFFORT"]
    m = model_name().lower()
    if any(x in m for x in ("claude", "glm", "gpt-6", "deepseek-v4")):
        return "max"
    return "high"  # Gemini refuses "max"


# --- Helpers ------------------------------------------------------------------

def clip(text: str) -> str:
    if len(text) <= RESULT_CHARS:
        return text
    half = RESULT_CHARS // 2
    return (f"{text[:half]}\n[... {len(text) - RESULT_CHARS} characters cut"
            f" ...]\n{text[-half:]}")


async def run_tool(session: taskbridge.Session, fn: dict) -> str:
    """Runs one tool call in the task container; failures become error text."""
    name = fn["name"]
    try:
        args = json.loads(fn["arguments"] or "{}")
        if not isinstance(args, dict):
            raise TypeError("not a JSON object")
        fn["arguments"] = json.dumps(args, allow_nan=False)
    except (TypeError, ValueError) as exc:
        fn["arguments"] = "{}"
        return (f"error: the arguments are not a JSON object ({exc}); "
                "send the call again")
    try:
        if name == "bash":
            result = await session.exec(args["command"])
            return clip(f"exit code {result['exit_code']}\n{result['output']}")
        if name == "read_file":
            return clip((await session.read_file(args["path"]))
                        .decode("utf-8", "replace"))
        if name == "write_file":
            n = await session.write_file(args["path"], args["content"])
            return f"wrote {n} bytes to {args['path']}"
        return f"error: there is no tool named {name}"
    except (taskbridge.TaskError, KeyError, ValueError) as exc:
        return f"error: {type(exc).__name__}: {exc}"


async def _shorten(session, messages) -> bool:
    """Truncates the older half of long tool results when context is full."""
    long = [n for n, m in enumerate(messages)
            if m["role"] == "tool" and len(m["content"]) > 2 * CUT_KEEP]
    if not long:
        return False
    for n in long[: max(1, len(long) // 2)]:
        messages[n]["content"] = (
            messages[n]["content"][:CUT_KEEP]
            + "\n[... cut to save context; run the tool again if needed]"
        )
    await session.log(f"context full: cut {len(long)} old tool results")
    return True


async def _recover(session, messages, exc, waits, until) -> bool:
    """Retry-or-give-up after a failed model call. Returns True to retry."""
    status = getattr(exc, "status_code", None)
    if status == 400 and CONTEXT_FULL.search(str(exc)):
        return await _shorten(session, messages)
    wait = next(waits, None)
    if wait is None or not (status is None or status in (408, 409, 429)
                            or status >= 500):
        return False
    left = session.time_left()
    if left is not None and left > until:
        wait = min(wait, left - until)
    await session.log(
        f"model call failed ({str(exc)[:200]}); again in {wait:.0f} s")
    await asyncio.sleep(wait)
    return True


# --- The reusable agent loop --------------------------------------------------

async def agent_loop(session, messages, tools, wrap_up_left_sec, client=None,
                     log_prefix=""):
    """Runs one tool-calling role until it answers without a tool call.

    Args:
        session: Active `taskbridge.Session`.
        messages: Starting conversation (system + user).
        tools: Tool definitions this role may use.
        wrap_up_left_sec: Start wrapping up when this much time is left in
            the task (stage deadline). None = run until the task limit.
        client: OpenAI-compatible client (default: shared client).
        log_prefix: Prefix for session log lines.

    Returns:
        The role's final text reply (also stored as `session.final_message`
        while the loop runs, so a timeout still leaves a summary).
    """
    client = client or get_client()
    model = model_name()
    nudges, head, waits = 0, "", iter(RETRY_WAITS)
    while True:
        left = session.time_left()
        # Wrap up at the stage deadline, or at the global WRAP_UP_SEC,
        # whichever comes first.
        stage_left = wrap_up_left_sec if wrap_up_left_sec is not None else 0
        wrap_up = left is not None and left <= max(stage_left, WRAP_UP_SEC)
        if wrap_up and messages[-1:] != [WRAP_UP]:
            messages.append(dict(WRAP_UP))
        try:
            # A call still running when the wrap-up starts is stopped: cap
            # its wait at the time left before wrap-up begins.
            call_timeout = None
            if left is not None and not wrap_up:
                call_timeout = max(60.0, left - max(stage_left, WRAP_UP_SEC))
            reply = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="none" if wrap_up else "auto",
                    reasoning_effort=reasoning_effort(),
                    max_completion_tokens=MAX_OUTPUT_TOKENS,
                ),
                call_timeout,
            )
        except asyncio.TimeoutError:
            continue
        except openai.APIError as exc:
            if await _recover(session, messages, exc, waits, WRAP_UP_SEC):
                continue
            raise
        waits = iter(RETRY_WAITS)
        if reply.usage:
            details = getattr(reply.usage, "prompt_tokens_details", None)
            await session.usage(
                model,
                reply.usage.prompt_tokens,
                reply.usage.completion_tokens,
                getattr(details, "cached_tokens", 0) or 0,
            )
        message = reply.choices[0].message
        cut = reply.choices[0].finish_reason == "length"
        text = head + (message.content or "")
        if text:
            session.final_message = text
        turn = message.model_dump(exclude_none=True)
        if wrap_up or not message.tool_calls:
            if wrap_up or (message.content and not cut) or nudges == MAX_NUDGES:
                return session.final_message
            nudges, head = nudges + 1, text
            if message.content:
                messages.append(turn)
            messages.append({
                "role": "user",
                "content": ("Your reply was cut off; continue where it stopped."
                            if cut else
                            "Continue the task, and finish with your summary."),
            })
            continue
        nudges, head = 0, ""
        messages.append(turn)
        for call in turn["tool_calls"]:
            await session.log(
                f"{log_prefix}{call['function']['name']} "
                f"{call['function']['arguments'][:200]}")
            content = await run_tool(session, call["function"])
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": content})
        if session.time_left() is not None:
            messages[-1]["content"] += (
                f"\n[{int(session.time_left() // 60)} minutes left]")


def _left_at(total_sec, share_left):
    """Seconds of task time left when a stage's wrap-up must start."""
    if total_sec is None:
        return None
    return total_sec * share_left


# --- The four stages -----------------------------------------------------------

async def solve(session: taskbridge.Session, client=None) -> str:
    """Runs planner -> worker -> calc-verifier -> verifier (+fix rounds).

    Returns the final summary message sent to the graders as `done`.
    """
    workdir = session.workdir
    total = session.time_left()  # seconds; None when no limit (local smoke)
    if total is None:
        total = 21600  # 6 h, the competition's per-task limit

    # 1. PLANNER (read-only, 10% of budget)
    plan = ""
    try:
        plan = await agent_loop(
            session,
            [{"role": "system",
              "content": PLANNER.format(workdir=workdir)},
             {"role": "user", "content": session.instruction}],
            READ_TOOLS,
            wrap_up_left_sec=_left_at(total, 1.0 - PLAN_SHARE),
            client=client, log_prefix="plan: ",
        )
    except Exception as exc:  # planner failed: worker still runs on raw task
        await session.log(f"planner failed ({exc}); worker runs without plan")
        plan = "(planner failed; work from the task instruction directly)"

    # 2. WORKER (until 25% of budget remains)
    worker_msgs = [
        {"role": "system", "content": WORKER.format(workdir=workdir, plan=plan)},
        {"role": "user", "content": session.instruction},
    ]
    summary = await agent_loop(
        session, worker_msgs, WRITE_TOOLS,
        wrap_up_left_sec=_left_at(total, WORK_UNTIL_LEFT),
        client=client, log_prefix="work: ",
    )

    # The graders read `session.final_message` as the closing summary: it
    # must be the WORKER's summary (or the last fix round's), never a
    # verifier verdict like "PASS". agent_loop overwrites final_message on
    # every text reply, so we restore the worker summary at the end.
    final = summary

    # 3. CALC-VERIFIER (until 18% remains) — only if time allows
    issues = ""
    if session.time_left() is None or session.time_left() > MIN_STEP_SEC:
        try:
            calc = await agent_loop(
                session,
                [{"role": "system",
                  "content": CALC_VERIFIER.format(workdir=workdir)},
                 {"role": "user",
                  "content": session.instruction + "\n\nWORKER SUMMARY:\n"
                             + summary}],
                READ_TOOLS,
                wrap_up_left_sec=_left_at(total, CALC_UNTIL_LEFT),
                client=client, log_prefix="calc: ",
            )
            if "CALC: FAIL" in calc:
                issues = calc
        except Exception as exc:
            await session.log(f"calc-verifier failed ({exc}); continuing")

    # 4. DELIVERABLE-VERIFIER (until 12.5% remains) + fix rounds
    for round_no in range(MAX_FIX_ROUNDS + 1):
        if session.time_left() is not None and session.time_left() <= MIN_STEP_SEC:
            break
        try:
            verdict = await agent_loop(
                session,
                [{"role": "system",
                  "content": VERIFIER.format(
                      workdir=workdir, instruction=session.instruction,
                      plan=plan, summary=summary)},
                 {"role": "user",
                  "content": "Verify the deliverables now. Reply PASS or "
                             "a numbered list of issues."}],
                READ_TOOLS,
                wrap_up_left_sec=_left_at(total, VERIFY_UNTIL_LEFT),
                client=client, log_prefix="verify: ",
            )
        except Exception as exc:
            await session.log(f"verifier failed ({exc}); keeping worker output")
            break
        if verdict.strip().upper().startswith("PASS"):
            break
        if round_no >= MAX_FIX_ROUNDS:
            break
        issues = verdict
        try:
            summary = await agent_loop(
                session,
                [{"role": "system",
                  "content": "You are the WORKER engineer. " + FIX.format(
                      issues=issues)},
                 {"role": "user",
                  "content": "Fix the issues above in the deliverables."}],
                WRITE_TOOLS,
                wrap_up_left_sec=WRAP_UP_SEC,
                client=client, log_prefix=f"fix{round_no + 1}: ",
            )
            final = summary
        except Exception as exc:
            await session.log(f"fix round failed ({exc}); keeping prior output")
            break

    if issues and "CALC: FAIL" in issues:
        await session.log("calc-verifier reported FAIL; see trajectory")
    session.final_message = final
    return final or "(harness stopped without summary)"
