# backend/services/artifacts.py
"""
Stores generated multi-file projects under workflow/ and creates zip bundles.
Robust parse_project_files handles all LLM output formats.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

WORKFLOW_DIR = Path("workflow")
MANIFEST = "manifest.json"


def _safe_relative_path(path: str) -> str | None:
    cleaned = path.strip().strip("`").strip().strip("'").strip('"')
    cleaned = cleaned.replace("\\", "/").lstrip("/")
    if not cleaned or cleaned.startswith("../") or "/../" in cleaned:
        return None
    if cleaned in {".", ".."}:
        return None
    return cleaned


def _guess_extension(language: str) -> str:
    lang = language.lower().strip()
    return {
        "python": ".py", "py": ".py",
        "javascript": ".js", "js": ".js",
        "jsx": ".jsx", "typescript": ".ts", "ts": ".ts", "tsx": ".tsx",
        "html": ".html", "css": ".css", "json": ".json",
        "markdown": ".md", "md": ".md", "text": ".txt", "txt": ".txt",
        "yaml": ".yaml", "yml": ".yaml", "toml": ".toml",
        "sh": ".sh", "bash": ".sh", "dockerfile": "",
        "sql": ".sql", "java": ".java", "cpp": ".cpp",
        "c": ".c", "go": ".go", "rust": ".rs", "ruby": ".rb",
    }.get(lang, ".txt")


def parse_deleted_files(generated: str) -> list[str]:
    """Parses explicit DELETE: filepath commands from LLM output."""
    deleted_files = []
    pattern = re.compile(r"^\s*DELETE:\s*([^\s]+)", re.MULTILINE)
    for m in pattern.finditer(generated):
        path = _safe_relative_path(m.group(1))
        if path and path not in deleted_files:
            deleted_files.append(path)
    return deleted_files


def parse_project_files(generated: str) -> dict[str, str]:
    """
    Robust parser — handles ALL LLM output formats.

    Priority order:
    1. ```lang path=filepath  (preferred)
    2. ```lang\n# path: filepath
    3. ## filepath\n```\ncode```
    4. Raw code blocks by language (fallback)
    """
    files: dict[str, str] = {}

    # ── Strategy 1: ```lang path=filepath ─────────────────────
    # Handles: ```html path=index.html
    #           ```python path=backend/main.py
    #           ```js path="src/App.js"
    pattern1 = re.compile(
        r"```(?:[\w+#.-]*)\s+path=['\"]?([^\s'\">\n`]+)['\"]?\s*\n(.*?)```",
        re.DOTALL,
    )
    for m in pattern1.finditer(generated):
        path = _safe_relative_path(m.group(1))
        if path:
            files[path] = m.group(2).rstrip()

    if files:
        return files

    # ── Strategy 2: ```lang\n# path: filepath ─────────────────
    pattern2 = re.compile(
        r"```([\w+#.-]*)\s*\n(?:#|//|<!--)\s*(?:path|file|filename):\s*([^\s\n>]+)[^\n]*\n(.*?)```",
        re.DOTALL,
    )
    for m in pattern2.finditer(generated):
        path = _safe_relative_path(m.group(2))
        if path:
            files[path] = m.group(3).rstrip()

    if files:
        return files

    # ── Strategy 3: ## filepath\n```\ncode``` ─────────────────
    pattern3 = re.compile(
        r"(?:^|\n)#{1,3}\s+(?:File:\s*)?`?([^\s`\n]+\.(?:py|js|jsx|ts|tsx|html|css|json|md|sh|yml|yaml|txt|java|cpp|c|go|rb))`?\s*\n+```[\w]*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern3.finditer(generated):
        path = _safe_relative_path(m.group(1))
        if path:
            files[path] = m.group(2).rstrip()

    if files:
        return files

    # ── Strategy 4: Raw blocks by language (last resort) ──────
    pattern4 = re.compile(r"```([\w+#.-]+)\n(.*?)```", re.DOTALL)

    default_names = {
        "html": "index.html",
        "css": "styles.css",
        "javascript": "script.js",
        "js": "script.js",
        "python": "main.py",
        "py": "main.py",
        "jsx": "App.jsx",
        "tsx": "App.tsx",
        "typescript": "main.ts",
        "ts": "main.ts",
        "json": "package.json",
        "markdown": "README.md",
        "md": "README.md",
        "sh": "run.sh",
        "bash": "run.sh",
        "java": "Main.java",
        "cpp": "main.cpp",
        "c": "main.c",
        "go": "main.go",
        "ruby": "main.rb",
        "rb": "main.rb",
        "sql": "schema.sql",
        "yaml": "config.yml",
        "yml": "config.yml",
    }

    used_names: set[str] = set()

    for m in pattern4.finditer(generated):
        lang = m.group(1).strip().lower()
        body = m.group(2).strip()

        if not body or len(body) < 10:
            continue

        default = default_names.get(lang)
        if not default:
            continue

        # Avoid duplicate filenames
        if default in used_names:
            ext = "." + default.rsplit(".", 1)[-1] if "." in default else ""
            base = default.rsplit(".", 1)[0] if "." in default else default
            i = 2
            while f"{base}_{i}{ext}" in used_names:
                i += 1
            default = f"{base}_{i}{ext}"

        used_names.add(default)
        files[default] = body

    return files


def save_project(
    project_files: dict[str, str],
    session_id: str | None = None,
    title: str = "Generated Project",
    workflow_id: str | None = None,
) -> dict:
    """Saves project files and creates a ZIP. Returns artifact metadata."""
    artifact_id = workflow_id or str(uuid.uuid4())
    artifact_dir = WORKFLOW_DIR / artifact_id / "project"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for rel_path, content in project_files.items():
        safe = _safe_relative_path(rel_path)
        if not safe:
            continue
        dest = artifact_dir / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Smart Overwrite: Only write if file doesn't exist or content changed
        should_write = True
        if dest.exists():
            try:
                existing_content = dest.read_text(encoding="utf-8")
                if existing_content == content:
                    should_write = False
            except Exception:
                pass
                
        if should_write:
            dest.write_text(content, encoding="utf-8")
            
        saved_files.append(safe)

    # Clean up orphaned files on disk (files not in project_files)
    import os
    for root, _, filenames in os.walk(artifact_dir):
        for filename in filenames:
            filepath = Path(root) / filename
            rel_path = filepath.relative_to(artifact_dir).as_posix()
            if rel_path not in saved_files and rel_path != MANIFEST:
                try:
                    filepath.unlink()
                except Exception:
                    pass

    # Create ZIP
    zip_path = WORKFLOW_DIR / artifact_id / "project.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in saved_files:
            file_path = artifact_dir / rel_path
            zf.write(file_path, rel_path)

    # Write manifest
    manifest = {
        "artifact_id": artifact_id,
        "session_id": session_id,
        "title": title,
        "files": saved_files,
        "zip_path": str(zip_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = WORKFLOW_DIR / artifact_id / MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest


def get_artifact(artifact_id: str) -> dict | None:
    manifest_path = WORKFLOW_DIR / artifact_id / MANIFEST
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def list_artifacts(session_id: str | None = None) -> list[dict]:
    if not WORKFLOW_DIR.exists():
        return []
    artifacts = []
    for manifest_path in WORKFLOW_DIR.glob(f"*/{MANIFEST}"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if session_id is None or data.get("session_id") == session_id:
                artifacts.append(data)
        except Exception:
            continue
    return sorted(
        artifacts,
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )


def delete_artifact(artifact_id: str) -> bool:
    artifact_path = WORKFLOW_DIR / artifact_id
    if artifact_path.exists():
        shutil.rmtree(artifact_path)
        return True
    return False


def delete_all_artifacts() -> int:
    if not WORKFLOW_DIR.exists():
        return 0
    count = 0
    for path in WORKFLOW_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
            count += 1
    return count


def delete_artifacts_for_session(session_id: str) -> int:
    artifacts = list_artifacts(session_id)
    count = 0
    for art in artifacts:
        if delete_artifact(art["artifact_id"]):
            count += 1
    return count