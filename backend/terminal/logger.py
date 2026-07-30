# backend/terminal/logger.py
"""
Centralized real-time terminal logger for the AI Dev Team pipeline.

Provides structured, timestamped, color-coded, dedup-aware logging
that streams output to the terminal in chronological order.

Usage:
    from backend.terminal.logger import tlog
    tlog.agent_start("Planner")
    tlog.info("Planner", "Created implementation plan")
    tlog.agent_end("Planner")
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime
from typing import ClassVar


class _Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    # Agent colors
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    WHITE = "\033[97m"


AGENT_COLORS = {
    "System": _Colors.WHITE,
    "Planner": _Colors.CYAN,
    "Coder": _Colors.GREEN,
    "Reviewer": _Colors.YELLOW,
    "Executor": _Colors.MAGENTA,
    "QA": _Colors.BLUE,
    "Orchestrator": _Colors.WHITE,
    "User": _Colors.DIM,
}

AGENT_ICONS = {
    "System": "⚙️ ",
    "Planner": "📋",
    "Coder": "💻",
    "Reviewer": "🔍",
    "Executor": "▶️ ",
    "QA": "✅",
    "Orchestrator": "🎯",
    "User": "👤",
}


class TerminalLogger:
    """Thread-safe, singleton terminal logger with dedup."""

    _instance: ClassVar[TerminalLogger | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls) -> TerminalLogger:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._seen: set[str] = set()
                    inst._seen_lock = threading.Lock()
                    cls._instance = inst
        return cls._instance

    # ---- internal helpers ----

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _is_duplicate(self, key: str) -> bool:
        with self._seen_lock:
            if key in self._seen:
                return True
            self._seen.add(key)
            return False

    def reset_seen(self) -> None:
        """Clear the dedup set (call at the start of a new job)."""
        with self._seen_lock:
            self._seen.clear()

    def _print(
        self,
        agent: str,
        message: str,
        *,
        color: str | None = None,
        bold: bool = False,
        dedup: bool = True,
    ) -> None:
        if dedup:
            key = f"{agent}:{message}"
            if self._is_duplicate(key):
                return

        ts = self._timestamp()
        c = color or AGENT_COLORS.get(agent, _Colors.WHITE)
        icon = AGENT_ICONS.get(agent, "  ")
        b = _Colors.BOLD if bold else ""
        line = (
            f"{_Colors.DIM}{ts}{_Colors.RESET} "
            f"{icon} {c}{b}[{agent}]{_Colors.RESET} {message}"
        )
        print(line, flush=True, file=sys.stderr)

    # ---- public API ----

    def system(self, message: str) -> None:
        self._print("System", message, bold=True)

    def agent_start(self, agent: str) -> None:
        self._print(agent, "Started", bold=True)

    def agent_end(self, agent: str, elapsed: float | None = None) -> None:
        suffix = f" ({elapsed:.1f}s)" if elapsed is not None else ""
        self._print(agent, f"Finished{suffix}", bold=True)

    def info(self, agent: str, message: str) -> None:
        self._print(agent, message)

    def file_generated(self, agent: str, filepath: str) -> None:
        self._print(agent, f"Generating {filepath}", color=_Colors.GREEN)

    def success(self, agent: str, message: str) -> None:
        self._print(agent, f"✅ {message}", color=_Colors.GREEN)

    def error(self, agent: str, message: str) -> None:
        self._print(agent, f"❌ {message}", color=_Colors.RED, dedup=False)

    def warning(self, agent: str, message: str) -> None:
        self._print(agent, f"⚠️  {message}", color=_Colors.YELLOW)

    def task_received(self, request: str) -> None:
        short = request[:80] + ("..." if len(request) > 80 else "")
        self._print("System", f"Task received: {short}", bold=True)

    def task_completed(self) -> None:
        self._print(
            "System",
            "Task Completed",
            color=_Colors.GREEN,
            bold=True,
            dedup=False,
        )

    def task_failed(self, error_msg: str) -> None:
        short = error_msg[:120] + ("..." if len(error_msg) > 120 else "")
        self._print(
            "System",
            f"Task Failed: {short}",
            color=_Colors.RED,
            bold=True,
            dedup=False,
        )

    def divider(self) -> None:
        line = f"{_Colors.DIM}{'─' * 60}{_Colors.RESET}"
        print(line, flush=True, file=sys.stderr)


# Module-level singleton
tlog = TerminalLogger()
