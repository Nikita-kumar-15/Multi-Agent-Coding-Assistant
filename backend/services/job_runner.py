"""
Runs the LangGraph workflow in background.
Saves project files as artifact and creates ZIP.
"""

from backend.graph.workflow import build_workflow
from backend.services.job_store import update_job
from backend.services.progress import get_stage_info
from backend.services.session_store import (
    add_message,
    session_exists,
    create_session,
    update_session_title,
    update_active_project_state,
    get_session_workflow_id,
    set_session_workflow_id,
)
from backend.services.artifacts import save_project

workflow_app = build_workflow()


def run_job(
    job_id: str,
    user_request: str,
    session_id: str = None,
    language_preference: str = None,
    is_update: bool = False,
    active_project_state: dict = None,
    user_history: list = None,
) -> None:
    is_job_failed = False
    
    if session_id and not session_exists(session_id):
        create_session(session_id)

    if session_id:
        add_message(session_id, "user", user_request)
        short_title = user_request[:40] + ("..." if len(user_request) > 40 else "")
        update_session_title(session_id, short_title)

    import uuid
    current_workflow_id = get_session_workflow_id(session_id) if session_id else None
    workflow_id = current_workflow_id if (is_update and current_workflow_id) else str(uuid.uuid4())

    previous_code = None
    if active_project_state and active_project_state.get("files"):
        previous_code = "\n\n".join([f"```{fp.split('.')[-1]} path={fp}\n{content}\n```" for fp, content in active_project_state["files"].items()])

    safe_state = active_project_state or {
        "files": {},
        "plan": "",
        "architecture": "",
        "change_history": [],
        "conventions": language_preference or ""
    }

    initial_state = {
        "user_request": user_request,
        "user_history": user_history or [],
        "language_preference": language_preference or "Use best stack for the task",
        "plan": safe_state.get("plan"),
        "architecture_plan": safe_state.get("architecture"),
        "active_project_state": safe_state,
        "generated_code": None,
        "project_files": {},
        "code_explanation": None,
        "review_feedback": None,
        "review_passed": None,
        "orchestrator_feedback": None,
        "orchestrator_verdict": None,
        "execution_output": None,
        "execution_error": None,
        "execution_success": None,
        "execution_time": None,
        "generated_tests": None,
        "pytest_output": None,
        "pytest_passed": None,
        "qa_feedback": None,
        "artifact_id": None,
        "revision_count": 0,
        "max_revisions": 3,
        "test_revision_count": 0,
        "max_test_revisions": 1,
        "current_node": None,
        "history": [],
        "execution_trace": [],
        "is_update": is_update,
        "previous_code": previous_code,
    }

    update_job(job_id, status="running", progress=5)

    final_state = None

    import threading
    import time
    last_progress_time = time.time()
    stop_watchdog = False

    def watchdog():
        while not stop_watchdog:
            if time.time() - last_progress_time > 300:
                update_job(
                    job_id,
                    status="failed",
                    error="Watchdog Timeout: Job has been processing for more than 5 minutes with no new agent step logged.",
                )
                break
            time.sleep(10)

    threading.Thread(target=watchdog, daemon=True).start()

    try:
        overall_start_time = time.time()
        for step_output in workflow_app.stream(initial_state):
            if time.time() - overall_start_time > 300:
                print(f"[JOB_RUNNER] Pipeline Timeout! Halting job {job_id} after 5 minutes.")
                update_job(job_id, status="running", error="[PIPELINE TIMEOUT] Exceeded max total time (5 minutes), returning best-effort result.")
                final_state = list(step_output.values())[0] if step_output else final_state
                break
                
            last_progress_time = time.time()
            for node_name, node_state in step_output.items():
                stage_label, progress_pct = get_stage_info(node_name)

                update_job(
                    job_id,
                    status="running",
                    current_node=stage_label,
                    progress=progress_pct,
                )

                final_state = node_state
                
                if node_state.get("success") is False:
                    error_msg = node_state.get("error", "Unknown LLM Provider Error")
                    print(f"[JOB_RUNNER] Halting pipeline due to error in {node_name}: {error_msg}")
                    update_job(job_id, status="failed", error=error_msg)
                    return
                
            # Sleep 15 seconds between agents to reduce tokens per minute
            time.sleep(15)

        # ==========================================================
        # Save project files with an auto-generated README.md
        # ==========================================================
        artifact_id = None

        if final_state and final_state.get("project_files"):

            project_files = dict(final_state["project_files"])

            files = list(project_files.keys())

            has_python = any(f.endswith(".py") for f in files)
            has_react = any(
                f.endswith(".jsx")
                or f.endswith(".tsx")
                for f in files
            )
            has_html = any(f.endswith(".html") for f in files)
            has_requirements = "requirements.txt" in files

            readme_lines = [
                f"# {user_request[:50]}",
                "",
                "## Generated by AI Coding Assistant",
                "",
                "## 📁 Project Files",
                "",
            ]

            for f in sorted(files):
                readme_lines.append(f"- `{f}`")

            readme_lines += [
                "",
                "## 🚀 How to Run",
                "",
            ]

            if has_python and has_react:

                readme_lines += [
                    "### Backend (Python)",
                    "```bash",
                    (
                        "pip install -r requirements.txt"
                        if has_requirements
                        else "pip install flask flask-cors"
                    ),
                    "python main.py",
                    "```",
                    "",
                    "### Frontend",
                    "```bash",
                    "npm install",
                    "npm start",
                    "```",
                ]

            elif has_python:

                readme_lines += [
                    "```bash",
                ]

                if has_requirements:
                    readme_lines.append("pip install -r requirements.txt")

                readme_lines += [
                    "python main.py",
                    "```",
                ]

            elif has_html:

                readme_lines += [
                    "Simply open `index.html` in your browser.",
                    "",
                    "Or run a local server:",
                    "",
                    "```bash",
                    "python -m http.server 8080",
                    "# Then open http://localhost:8080",
                    "```",
                ]

            else:

                readme_lines += [
                    "Refer to the generated source files for setup instructions.",
                ]

            project_files["README.md"] = "\n".join(readme_lines)

            # Generate and attach the execution report
            try:
                update_job(job_id, status="running", current_node="Generating Report", progress=90)
                from backend.services.report_generator import generate_execution_report
                report_md = generate_execution_report(final_state)
                project_files["execution_report.md"] = report_md
                print(f"[JOB RUNNER] Added execution_report.md to project_files. Keys: {list(project_files.keys())}")
            except Exception as e:
                print(f"[job_runner] Failed to generate execution report: {e}")

            # Generate and attach test cases
            try:
                update_job(job_id, status="running", current_node="Generating Test Cases", progress=95)
                from backend.services.test_case_generator import generate_test_cases
                test_cases_md = generate_test_cases(final_state)
                project_files["test_cases.md"] = test_cases_md
            except Exception as e:
                print(f"[job_runner] Failed to generate test cases: {e}")

            try:
                manifest = save_project(
                    project_files=project_files,
                    session_id=session_id,
                    title=user_request[:50],
                    workflow_id=workflow_id,
                )

                artifact_id = manifest["artifact_id"]

                final_state["artifact_id"] = artifact_id

                final_state["project_files"] = project_files

            except Exception as e:
                print(f"[job_runner] Failed to save artifact: {e}")

        # Moved update_job(status="completed") to the end of the function to avoid race condition
        is_job_failed = final_state and final_state.get("orchestrator_verdict") == "FAIL" and final_state.get("revision_count", 0) >= final_state.get("max_revisions", 3)

        # Always update persistent memory if files were generated or if it's an update
        if session_id and final_state and (final_state.get("project_files") or is_update):
            # Save the active workflow_id so the next request resumes it
            set_session_workflow_id(session_id, workflow_id)
            
            # Persistent State Update
            from datetime import datetime
            safe_state = final_state.get("active_project_state", {
                "files": {},
                "plan": "",
                "architecture": "",
                "change_history": [],
                "conventions": ""
            })
            
            # Set workspace status
            safe_state["status"] = "NEEDS_FIXING" if is_job_failed else "ACTIVE"
            
            # Merge files (only overwrite changed/new files, keep untouched ones)
            if final_state.get("project_files"):
                safe_state["files"].update(final_state["project_files"])
                
            # Update plans if they changed
            if final_state.get("plan"):
                safe_state["plan"] = final_state["plan"]
            if final_state.get("architecture_plan"):
                safe_state["architecture"] = final_state["architecture_plan"]
                
            # Append change history
            safe_state["change_history"].append(f"[{datetime.utcnow().isoformat()[:16]}] Updated based on request: {user_request[:100]}")
            
            # Save back to database with retry and error handling
            save_success = False
            save_error = ""
            for attempt in range(2):
                try:
                    success = update_active_project_state(session_id, safe_state)
                    if success:
                        save_success = True
                        break
                    else:
                        save_error = "update_active_project_state returned False (session might not exist)"
                except Exception as e:
                    save_error = str(e)
                    print(f"[JOB_RUNNER] Error saving active project state on attempt {attempt+1}: {save_error}")
            
            print(f"[JOB_RUNNER] Saving active project state for session {session_id} (Success={save_success})")

            files = safe_state.get("files", {})

            if not save_success:
                summary = (
                    f"Generated {len(files)} file(s), but encountered an error saving the session state: {save_error}\n\n"
                    f"⚠️ Note: this update was generated but may not have been saved for future updates — please verify before continuing."
                )
            elif is_job_failed:
                attempts = final_state.get('revision_count', 0) + 1
                summary = (
                    f"Project generated with issues after {attempts} attempts.\n\n"
                    f"Our automated review found some issues. The workspace is active and saved.\n"
                    f"Check the execution report and tell me what you'd like to fix!"
                )
            else:
                summary = (
                    f"Generated {len(files)} file(s): "
                    f"{', '.join(sorted(files.keys()))}"
                )

            add_message(session_id, "assistant", summary)

        # ==========================================================
        # Set Final Job Status
        # ==========================================================

        if is_job_failed:
            update_job(
                job_id,
                status="completed",
                current_node="Completed (Needs Fixing)",
                progress=100,
                result=final_state,
                error="Project generated with warnings — see execution report for remaining issues"
            )
        else:
            update_job(
                job_id,
                status="completed",
                current_node="Completed",
                progress=100,
                result=final_state,
            )

    except Exception as e:
        update_job(
            job_id,
            status="failed",
            error=str(e),
        )
    finally:
        stop_watchdog = True