# backend/services/sandbox.py
"""
Secure Podman sandbox.
Fix: PYTHONDONTWRITEBYTECODE=1 + --tmpfs /root prevents read-only error.
"""

import os
import time
import tempfile
import subprocess

PODMAN_IMAGE = "coding-assistant-sandbox:latest"

def _ensure_base_image():
    # Check if image exists
    result = subprocess.run(["podman", "image", "exists", PODMAN_IMAGE])
    if result.returncode != 0:
        print(f"[{PODMAN_IMAGE}] not found. Building cached base image to speed up executions...")
        dockerfile_content = """FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask requests pytest
"""
        with open("sandbox.Dockerfile", "w") as f:
            f.write(dockerfile_content)
        subprocess.run(["podman", "build", "-t", PODMAN_IMAGE, "-f", "sandbox.Dockerfile", "."], check=True)
        print(f"[{PODMAN_IMAGE}] Base image built successfully.")

try:
    _ensure_base_image()
except Exception as e:
    print(f"Warning: Failed to ensure base podman image: {e}")
MEMORY_LIMIT = "512m"
CPU_LIMIT = "1"
TIMEOUT_SECONDS = 30


def run_in_podman(code: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        code_file = os.path.join(tmp_dir, "solution.py")
        with open(code_file, "w") as f:
            f.write(code)

        cmd = [
            "podman", "run", "--rm",
            "--network=none",
            f"--memory={MEMORY_LIMIT}",
            f"--cpus={CPU_LIMIT}",
            "--read-only",
            "--tmpfs", "/tmp",
            "--tmpfs", "/root",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "PYTHONUNBUFFERED=1",
            "--volume", f"{tmp_dir}:/sandbox:ro",
            "--workdir", "/sandbox",
            PODMAN_IMAGE,
            "python3", "-B", "solution.py",
        ]

        start = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": round(time.time() - start, 3),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False, "stdout": "",
                "stderr": f"Timed out after {TIMEOUT_SECONDS}s.",
                "exit_code": -1, "execution_time": TIMEOUT_SECONDS,
            }
        except Exception as e:
            return {
                "success": False, "stdout": "",
                "stderr": f"Sandbox error: {e}",
                "exit_code": -1, "execution_time": 0.0,
            }


def run_project_in_podman(files: dict[str, str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        for path, content in files.items():
            full_path = os.path.join(tmp_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        entrypoints = [
            "main.py", "app.py",
            "backend/main.py", "backend/app.py",
        ]
        entrypoint = None
        for ep in entrypoints:
            if os.path.exists(os.path.join(tmp_dir, ep)):
                entrypoint = ep
                break

        if not entrypoint:
            for root, dirs, fnames in os.walk(tmp_dir):
                for fname in fnames:
                    if fname.endswith(".py") and "test" not in fname:
                        entrypoint = os.path.relpath(
                            os.path.join(root, fname), tmp_dir
                        )
                        break
                if entrypoint:
                    break

        if not entrypoint:
            return {
                "success": False, "stdout": "",
                "stderr": "No Python entrypoint found.",
                "exit_code": -1, "execution_time": 0.0,
            }

        has_req = os.path.exists(os.path.join(tmp_dir, "requirements.txt"))

        script = "#!/bin/bash\nset -e\n"
        script += "export PYTHONDONTWRITEBYTECODE=1\n"
        script += "export PYTHONUNBUFFERED=1\n"
        script += f"python3 -B /project/{entrypoint}\n"

        script_path = os.path.join(tmp_dir, "_run.sh")
        with open(script_path, "w") as f:
            f.write(script)
        os.chmod(script_path, 0o755)

        network = "bridge" if has_req else "none"
        cmd = [
            "podman", "run", "--rm",
            f"--network={network}",
            f"--memory={MEMORY_LIMIT}",
            f"--cpus={CPU_LIMIT}",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "PYTHONUNBUFFERED=1",
            "--volume", f"{tmp_dir}:/project",
            "--workdir", "/project",
            PODMAN_IMAGE,
            "bash", "/project/_run.sh",
        ]

        start = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": round(time.time() - start, 3),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False, "stdout": "",
                "stderr": "Timed out (120s).",
                "exit_code": -1, "execution_time": 120.0,
            }
        except Exception as e:
            return {
                "success": False, "stdout": "",
                "stderr": f"Error: {e}",
                "exit_code": -1, "execution_time": 0.0,
            }