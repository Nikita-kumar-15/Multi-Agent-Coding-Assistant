# backend/services/executor.py
"""
Safely executes generated Python code in a subprocess.
Captures stdout, stderr, and runtime errors with a timeout
to prevent infinite loops or hangs from crashing the system.
"""

import subprocess
import tempfile
import os
import time

def run_frontend_in_browser(project_files: dict) -> dict:
    """
    Writes HTML/CSS/JS to a temp directory and opens it in Playwright.
    Captures console errors and checks if the DOM is empty.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "stdout": "", "stderr": "Playwright is not installed."}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for path, content in project_files.items():
            full_path = os.path.join(tmp_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        
        index_path = os.path.join(tmp_dir, "index.html")
        if not os.path.exists(index_path):
            return {"success": True, "stdout": "No index.html found. Skipping browser execution.", "stderr": ""}
            
        logs = []
        errors = []
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                page.on("console", lambda msg: logs.append(msg.text) if msg.type != "error" else errors.append(f"Console Error: {msg.text}"))
                page.on("pageerror", lambda err: errors.append(f"Uncaught Exception: {err}"))
                
                file_url = f"file://{index_path}"
                
                # Block external network requests to prevent hangs (allow only file:// and data:)
                page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file://") or route.request.url.startswith("data:") else route.abort())
                
                try:
                    page.goto(file_url, wait_until="networkidle", timeout=10000)
                except Exception as goto_err:
                    errors.append(f"Page Load Error (Timeout or Network): {goto_err}")

                time.sleep(2.5)
                
                body_text = page.locator("body").inner_text().strip()
                body_html = page.locator("body").inner_html().strip()
                
                if len(body_text) < 5 and len(body_html) < 50 and "<script" not in body_html:
                    if not errors:
                        errors.append("Blank Page Detected: The body or main content area appears completely empty after rendering. Check if your JavaScript actually mounts components to the DOM.")
                        
                browser.close()
                
        except Exception as e:
            errors.append(f"Playwright Execution Failed: {str(e)}")
            
        return {
            "success": len(errors) == 0,
            "stdout": "\n".join(logs),
            "stderr": "\n".join(errors)
        }


def run_python_code(code: str, timeout: int = 10) -> dict:
    """
    Writes code to a temp file and executes it in an isolated subprocess.

    Returns:
        dict with keys: success (bool), stdout (str), stderr (str)
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as tmp_file:
        tmp_file.write(code)
        tmp_path = tmp_file.name

    try:
        result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds.",
        }
    finally:
        os.remove(tmp_path)