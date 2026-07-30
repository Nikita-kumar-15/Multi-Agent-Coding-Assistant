import time
from datetime import datetime
# backend/agents/executor_agent.py
"""
Executor Agent: runs generated code in Podman sandbox.
Handles:
- Frontend-only (HTML/CSS/JS) → skip execution
- Web servers (Flask/FastAPI/Express) → skip execution, just validate syntax
- Pure Python scripts → run in sandbox
"""

from datetime import datetime
from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.sandbox import run_in_podman
from backend.services.executor import run_frontend_in_browser
from backend.terminal.logger import tlog

# Web server indicators — these projects can't run in sandbox (they don't exit)
WEB_SERVER_PATTERNS = [
    "app.run(", "uvicorn.run(", "app.listen(",
    "flask", "fastapi", "express", "django",
    "from flask", "from fastapi", "import flask",
    "http.server", "socketserver",
]

FRONTEND_EXTENSIONS = {".html", ".css", ".js", ".jsx", ".tsx", ".ts", ".vue", ".svelte"}
PYTHON_EXTENSIONS = {".py"}


def _get_file_ext(path: str) -> str:
    return "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""


def _is_frontend_only(project_files: dict) -> bool:
    """True if no Python files at all."""
    for path in project_files.keys():
        if _get_file_ext(path) in PYTHON_EXTENSIONS:
            return False
    return True


def _is_web_server_project(project_files: dict) -> bool:
    """True if any Python file contains web server code."""
    for path, content in project_files.items():
        if _get_file_ext(path) in PYTHON_EXTENSIONS:
            content_lower = content.lower()
            for pattern in WEB_SERVER_PATTERNS:
                if pattern in content_lower:
                    return True
    return False


def _validate_python_syntax(project_files: dict) -> dict:
    """
    For web server projects, validate Python syntax only.
    Uses python -c "compile()" instead of actually running.
    """
    python_files = {
        path: content
        for path, content in project_files.items()
        if _get_file_ext(path) in PYTHON_EXTENSIONS
    }

    if not python_files:
        return {"success": True, "stdout": "No Python files to validate.", "stderr": ""}

    # Create a syntax-check script
    check_script_lines = ["import py_compile, tempfile, os"]
    for filepath, content in python_files.items():
        escaped = content.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
        check_script_lines.append(
            f'code = """{content.replace(chr(39), chr(39)+chr(39)+chr(39))}"""'
        )
        check_script_lines.append(
            f"try:\n    compile(code, '{filepath}', 'exec')\n    print('✅ {filepath}: syntax OK')\nexcept SyntaxError as e:\n    print(f'❌ {filepath}: {{e}}')"
        )

    check_script = "\n".join(check_script_lines)

    result = run_in_podman(check_script)
    return result


def executor_agent(state: AgentState) -> AgentState:
    overall_start = time.time()
    print(f"[{datetime.utcnow().isoformat()}] START: Executor Agent")
    tlog.info("Executor", "Analyzing project type...")

    project_files = state.get("project_files") or {}

    # No files
    if not project_files:
        tlog.warning("Executor", "No files to execute.")
        state["execution_success"] = True
        state["execution_output"] = "No executable files found."
        state["execution_error"] = ""
        state["current_node"] = "executor_agent"
        state["history"].append("Executor: no files.")
        
        if "execution_trace" not in state:
            state["execution_trace"] = []
        state["execution_trace"].append({
            "agent": "Executor",
            "attempt": state.get("revision_count", 0) + 1,
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": "PASS" if state["execution_success"] else "FAIL",
            "details": state.get("execution_output") or state.get("execution_error") or ""
        })
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Executor Agent (took {elapsed:.2f}s)")
        return state

    file_list = ", ".join(sorted(project_files.keys()))
    tlog.info("Executor", f"Project files: {file_list}")

    # Case 1: Frontend-only (no Python at all)
    if _is_frontend_only(project_files):
        tlog.info("Executor", "Frontend-only project — running in headless browser...")
        
        result = run_frontend_in_browser(project_files)
        
        state["execution_success"] = result["success"]
        
        if result["success"]:
            state["execution_output"] = (
                f"✅ Frontend project executed successfully in headless browser.\n"
                f"Files: {file_list}\n\nConsole logs:\n{result['stdout']}"
            )
            state["execution_error"] = ""
            tlog.success("Executor", "Frontend execution passed.")
        else:
            state["execution_output"] = f"Frontend execution failed.\nConsole logs:\n{result['stdout']}"
            state["execution_error"] = result["stderr"]
            tlog.error("Executor", "Frontend execution encountered errors.")

        state["current_node"] = "executor_agent"
        state["history"].append(
            f"Executor: frontend-only ({len(project_files)} files), "
            f"browser execution {'passed' if result['success'] else 'failed'}."
        )
        
        if "execution_trace" not in state:
            state["execution_trace"] = []
        state["execution_trace"].append({
            "agent": "Executor",
            "attempt": state.get("revision_count", 0) + 1,
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": "PASS" if state["execution_success"] else "FAIL",
            "details": state.get("execution_output") or state.get("execution_error") or ""
        })
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Executor Agent (took {elapsed:.2f}s)")
        return state

    # Case 2: Web server project (Flask, FastAPI, Express etc.)
    if _is_web_server_project(project_files):
        tlog.info("Executor", "Web server detected — validating syntax only.")

        # Just validate Python syntax — don't actually run the server
        python_files = {
            p: c for p, c in project_files.items()
            if _get_file_ext(p) in PYTHON_EXTENSIONS
        }

        # Simple syntax validation using compile()
        syntax_ok = True
        syntax_results = []
        for filepath, content in python_files.items():
            try:
                compile(content, filepath, "exec")
                syntax_results.append(f"✅ {filepath}: syntax OK")
            except SyntaxError as e:
                syntax_ok = False
                syntax_results.append(f"❌ {filepath}: SyntaxError at line {e.lineno}: {e.msg}")

        output = (
            f"Web server project detected.\n"
            f"Files: {file_list}\n\n"
            f"Syntax validation:\n" + "\n".join(syntax_results)
        )

        state["execution_success"] = syntax_ok
        state["execution_output"] = output
        state["execution_error"] = "" if syntax_ok else "\n".join(
            r for r in syntax_results if r.startswith("❌")
        )
        state["current_node"] = "executor_agent"
        state["history"].append(
            f"Executor: web server project, syntax {'OK' if syntax_ok else 'ERRORS'}."
        )

        if syntax_ok:
            tlog.success("Executor", "Web server syntax validation passed.")
        else:
            tlog.error("Executor", "Syntax errors found.")
            
        if "execution_trace" not in state:
            state["execution_trace"] = []
        state["execution_trace"].append({
            "agent": "Executor",
            "attempt": state.get("revision_count", 0) + 1,
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": "PASS" if state["execution_success"] else "FAIL",
            "details": state.get("execution_output") or state.get("execution_error") or ""
        })
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Executor Agent (took {elapsed:.2f}s)")
        return state

    # Case 3: Pure Python script — run in sandbox
    tlog.info("Executor", "Running Python script in Podman sandbox...")

    # Find the main Python file
    python_files = {
        p: c for p, c in project_files.items()
        if _get_file_ext(p) in PYTHON_EXTENSIONS
    }

    entrypoints = ["main.py", "app.py", "run.py", "index.py"]
    main_file = None
    for ep in entrypoints:
        if ep in python_files:
            main_file = ep
            break
    if not main_file:
        main_file = list(python_files.keys())[0]

    code_to_run = python_files[main_file]

    with agent_log(
        agent_name="Executor Agent",
        model_name="podman sandbox",
        input_text={"file": main_file},
        next_agent="QA Agent",
    ) as log:
        result = run_in_podman(code_to_run)
        log["output"] = result

    state["execution_success"] = result["success"]
    state["execution_output"] = result["stdout"]
    state["execution_error"] = result["stderr"]
    state["current_node"] = "executor_agent"
    state["history"].append(
        f"Executor: {'success' if result['success'] else 'failed'} "
        f"in {result.get('execution_time', 0)}s"
    )

    if result["success"]:
        tlog.success("Executor", "Code execution passed.")
    else:
        tlog.error(
            "Executor",
            f"Execution failed: {result.get('stderr', '')[:100]}"
        )

    if "execution_trace" not in state:
        state["execution_trace"] = []
    state["execution_trace"].append({
        "agent": "Executor",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "PASS" if state["execution_success"] else "FAIL",
        "details": state.get("execution_output") or state.get("execution_error") or ""
    })
    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Executor Agent (took {elapsed:.2f}s)")
    return state