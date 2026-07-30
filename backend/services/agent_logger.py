"""
Readable terminal logging for agent interactions.

Combines the original detailed logging with the new structured
TerminalLogger for real-time timestamped output.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from backend.terminal.logger import tlog


COLORS = {
    "reset": "\033[0m",
    "cyan": "\033[96m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "magenta": "\033[95m",
    "bold": "\033[1m",
}

# Map agent display names to tlog-friendly short names
_AGENT_SHORT = {
    "Planner Agent": "Planner",
    "Coder Agent": "Coder",
    "Reviewer Agent": "Reviewer",
    "Executor Agent": "Executor",
    "QA Agent": "QA",
    "Conversation Router": "System",
    "Conversation Update Agent": "Coder",
    "Conversation Rewrite Agent": "Coder",
    "Debugger Agent": "Executor",
}


def _format_value(value: object, limit: int = 4000) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def _token_usage(response: object) -> str:
    metadata = getattr(response, "response_metadata", {}) or {}
    usage = metadata.get("token_usage") or metadata.get("usage") or {}
    if not usage:
        usage = getattr(response, "usage_metadata", {}) or {}
    return str(usage) if usage else "unavailable"


@contextmanager
def agent_log(
    *,
    agent_name: str,
    model_name: str,
    input_text: object,
    next_agent: str | None = None,
) -> Iterator[dict]:
    short = _AGENT_SHORT.get(agent_name, agent_name.replace(" Agent", ""))

    # Real-time terminal log: agent started
    tlog.agent_start(short)
    tlog.info(short, f"Model: {model_name}")

    start = time.perf_counter()
    print(
        f"\n{COLORS['cyan']}{'-' * 48}{COLORS['reset']}\n"
        f"{COLORS['bold']}{agent_name}{COLORS['reset']}\n"
        f"{COLORS['cyan']}{'-' * 48}{COLORS['reset']}\n"
        f"Timestamp: {datetime.utcnow().isoformat()}Z\n"
        f"Model used: {model_name}\n"
        f"Input:\n{_format_value(input_text)}\n"
        f"{COLORS['yellow']}Thinking...{COLORS['reset']}",
        flush=True,
    )
    record: dict = {"response": None, "output": None, "next_agent": next_agent}
    try:
        yield record
    finally:
        elapsed = time.perf_counter() - start
        response = record.get("response")
        output = record.get("output")
        print(
            f"Output:\n{_format_value(output)}\n\n"
            f"Execution time: {elapsed:.3f}s\n"
            f"Token usage: {_token_usage(response)}\n"
            f"Next Agent: {record.get('next_agent') or 'None'}\n"
            f"{COLORS['green']}{'-' * 48}{COLORS['reset']}\n",
            flush=True,
        )

        # Real-time terminal log: agent finished
        tlog.info(short, f"LLM generation took {elapsed:.1f} seconds")
        with open("timing_logs.txt", "a") as f:
            f.write(f"[{datetime.utcnow().isoformat()}] [{short}] LLM generation took {elapsed:.1f} seconds\n")
        tlog.agent_end(short, elapsed=elapsed)
        if record.get("next_agent"):
            next_short = record["next_agent"].replace(" Agent", "")
            tlog.info("System", f"Next → {next_short}")
