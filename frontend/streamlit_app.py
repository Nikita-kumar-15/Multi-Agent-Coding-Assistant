# frontend/streamlit_app.py
"""
AI Coding Assistant — Streamlit Frontend

SHORT TERM MEMORY:
- app_run_sessions tracks sessions created THIS run only
- Restart = clean sidebar

FEATURES:
- Conversational AI (chat, code, update, rewrite)
- Agent conversation dropdown
- File tree with clickable file links
- ZIP download button
- Language preference detection
- Debug tab
"""

import time
import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="AI Coding Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.agent-card {
    background: #1a1a2e;
    border-left: 3px solid #7c3aed;
    padding: 8px 14px;
    margin: 5px 0;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
}
.agent-name {
    color: #a78bfa;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 4px;
}
.file-tree-box {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 12px 16px;
    font-family: monospace;
    font-size: 13px;
    color: #8b949e;
    margin: 8px 0;
    white-space: pre;
}
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────
# SHORT TERM MEMORY: only track sessions from THIS run
if "app_run_sessions" not in st.session_state:
    st.session_state.app_run_sessions = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "downloads" not in st.session_state or isinstance(st.session_state.downloads, list):
    st.session_state.downloads = {}


# ── Helpers ───────────────────────────────────────────────────
def backend_ok() -> bool:
    try:
        r = requests.get(f"{API_BASE_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def create_new_session():
    try:
        r = requests.post(f"{API_BASE_URL}/sessions", timeout=5)
        if r.status_code == 200:
            sid = r.json()["session_id"]
            st.session_state.session_id = sid
            st.session_state.messages = []
            if sid not in st.session_state.app_run_sessions:
                st.session_state.app_run_sessions.append(sid)
    except Exception as e:
        st.error(f"Backend error: {e}")


def switch_session(sid: str):
    st.session_state.session_id = sid
    st.session_state.messages = []
    try:
        r = requests.get(f"{API_BASE_URL}/sessions/{sid}/messages", timeout=5)
        if r.status_code == 200:
            st.session_state.messages = r.json().get("messages", [])
    except Exception:
        pass


def delete_session_fn(sid: str):
    try:
        requests.delete(f"{API_BASE_URL}/conversation/{sid}", timeout=5)
    except Exception:
        pass
    if sid in st.session_state.app_run_sessions:
        st.session_state.app_run_sessions.remove(sid)
    if st.session_state.session_id == sid:
        create_new_session()


def get_run_sessions() -> list:
    """Only return sessions from THIS app run."""
    if not st.session_state.app_run_sessions:
        return []
    try:
        r = requests.get(f"{API_BASE_URL}/sessions", timeout=5)
        if r.status_code == 200:
            all_s = r.json().get("sessions", [])
            run_ids = set(st.session_state.app_run_sessions)
            return [s for s in all_s if s["session_id"] in run_ids]
    except Exception:
        pass
    return []


def fetch_events(workflow_id: str) -> list:
    try:
        r = requests.get(
            f"{API_BASE_URL}/workflow/{workflow_id}/events", timeout=5
        )
        if r.status_code == 200:
            return r.json().get("events", [])
    except Exception:
        pass
    return []


def get_zip(artifact_id: str) -> bytes | None:
    try:
        r = requests.get(
            f"{API_BASE_URL}/artifacts/{artifact_id}/download", timeout=15
        )
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


def parse_files_from_code(raw: str) -> dict:
    """Parse fenced code blocks into separate files."""
    import re

    def infer_path(language: str, existing: set, index: int) -> str:
        language = language.lower()
        if language in ("html",):
            base = "index"
            ext = ".html"
        elif language in ("css",):
            base = "styles"
            ext = ".css"
        elif language in ("javascript", "js", "jsx", "tsx", "typescript", "ts"):
            base = "script"
            ext = ".js" if language in ("javascript", "js") else ".ts"
        else:
            base = "file"
            ext = ".txt"
        path = f"{base}{index if index > 1 else ''}{ext}"
        while path in existing:
            index += 1
            path = f"{base}{index if index > 1 else ''}{ext}"
        return path

    files = {}
    existing = set()
    pattern = r"```([\w+-]*)\s+([^\n]+)\n(.*?)```"
    for match in re.finditer(pattern, raw, re.DOTALL):
        info = match.group(2).strip()
        code = match.group(3).strip()
        filepath = None
        language = match.group(1).strip() or "text"

        for part in info.split():
            if part.startswith(("path=", "filename=", "file=")):
                filepath = part.split("=", 1)[1]
                break

        if filepath is None:
            candidate = info
            if "/" in candidate or "." in candidate:
                filepath = candidate

        if filepath:
            filepath = filepath.strip()
        else:
            filepath = infer_path(language, existing, len(existing) + 1)

        if filepath in files:
            stem, ext = (filepath.rsplit(".", 1) + [""])[:2]
            suffix = 1
            while filepath in files:
                filepath = f"{stem}_{suffix}.{ext}" if ext else f"{stem}_{suffix}"
                suffix += 1

        files[filepath] = code
        existing.add(filepath)

    return files


def render_file_tree(files: dict) -> str:
    if not files:
        return ""
    
    tree = {}
    for path in files.keys():
        parts = path.split("/")
        current = tree
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = None

    lines = ["project/"]
    
    def _render(node, prefix=""):
        items = sorted(node.items(), key=lambda x: (x[1] is None, x[0]))
        for i, (name, children) in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            if children is None:
                lines.append(prefix + connector + name)
            else:
                lines.append(prefix + connector + name + "/")
                extension = "    " if is_last else "│   "
                _render(children, prefix + extension)
                
    _render(tree)
    return "\n".join(lines)


def lang_from_ext(ext: str) -> str:
    return {
        "py": "python", "js": "javascript", "ts": "typescript",
        "jsx": "javascript", "tsx": "typescript", "html": "html",
        "css": "css", "json": "json", "md": "markdown",
        "sh": "bash", "yml": "yaml", "yaml": "yaml",
    }.get(ext, "text")


# ── Backend check ─────────────────────────────────────────────
if not backend_ok():
    st.error("""
⚠️ **Backend not running!**

```bash
cd /Users/nikitakumar/Desktop/codingAssistant
source venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```
""")
    st.stop()

if not st.session_state.session_id:
    create_new_session()


# ── SIDEBAR ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧠 AI Dev Team")
    st.markdown("---")

    if st.button("🆕 New Chat", use_container_width=True, key="nc"):
        create_new_session()
        st.rerun()

    st.markdown("### 💬 Chat History")
    sessions = get_run_sessions()

    if not sessions:
        st.caption("No chats yet — start one!")
    else:
        for s in sessions:
            sid = s["session_id"]
            title = s.get("title", "") or f"Chat {sid[:8]}"
            if title == "New Chat":
                title = f"Chat {sid[:8]}"
            is_active = sid == st.session_state.session_id
            label = f"🟢 {title}" if is_active else title

            c1, c2 = st.columns([5, 1])
            with c1:
                if st.button(label, key=f"s_{sid}", use_container_width=True):
                    switch_session(sid)
                    st.rerun()
            with c2:
                if st.button("🗑", key=f"d_{sid}"):
                    delete_session_fn(sid)
                    st.rerun()

    if st.session_state.downloads:
        st.markdown("---")
        st.markdown("### 📦 Downloads")
        for sid, dl in st.session_state.downloads.items():
            zd = get_zip(dl["artifact_id"])
            if zd:
                session_title = "Current Project"
                for s in sessions:
                    if s["session_id"] == sid:
                        session_title = s.get("title", "") or f"Project {sid[:8]}"
                        if session_title == "New Chat":
                            session_title = f"Project {sid[:8]}"
                        break
                st.download_button(
                    f"⬇️ {session_title[:20]}.zip",
                    data=zd,
                    file_name=f"{session_title.replace(' ', '_')}.zip",
                    mime="application/zip",
                    key=f"sdl_{dl['artifact_id']}",
                    use_container_width=True,
                )


# ── MAIN ─────────────────────────────────────────────────────
st.markdown("# 🤖 A Coding Assistant")
st.caption("Multi-agent pipeline — planner → coder → reviewer → QA → executor")

tab1, tab2 = st.tabs(["🛠️ Build & Chat", "🐞 Debug Code"])


# ════════════════════════════════════════════════
# RENDER ASSISTANT MESSAGE
# ════════════════════════════════════════════════
def render_assistant(msg: dict, idx: int):
    content = msg.get("content", "")
    events = msg.get("agent_events", [])
    wid = msg.get("workflow_id")
    art_id = msg.get("artifact_id")
    gen_files = msg.get("generated_files", {})

    # Fetch events if needed
    if not events and wid:
        events = fetch_events(wid)

    # Agent conversation dropdown
    if events:
        with st.expander(
            f"🤖 View full agent conversation ({len(events)} steps)",
            expanded=False,
        ):
            for ev in events:
                name = ev.get("agent", "AGENT").upper()
                ev_text = ev.get("content", "")
                icon = "✅" if any(
                    w in ev_text.upper()
                    for w in ["PASS", "APPROVED", "GENERATED"]
                ) else "🔄"
                st.markdown(
                    f'<div class="agent-card">'
                    f'<div class="agent-name">{icon} {name}</div>'
                    f'{ev_text[:600]}</div>',
                    unsafe_allow_html=True,
                )

    # Files tree + expandable code
    if gen_files:
        soft_err = msg.get("_soft_failure_error")
        if soft_err:
            st.warning(f"⚠️ {soft_err}\n\nThis project did not pass all quality checks after multiple attempts. Remaining issues are listed in the Execution Report below. You can still download and review the code.")
            
        tree = render_file_tree(gen_files)
        st.markdown("**📁 Generated Project Structure:**")
        st.markdown(
            f'<div class="file-tree-box">{tree}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("**📄 Generated Files** *(click to view code)*:")
        for fp, code in gen_files.items():
            ext = fp.rsplit(".", 1)[-1] if "." in fp else "text"
            with st.expander(f"📄 `{fp}`", expanded=False):
                st.code(code, language=lang_from_ext(ext))
                
        if "execution_report.md" in gen_files:
            with st.expander("📋 View Execution Report", expanded=False):
                st.markdown(gen_files["execution_report.md"])

        # ZIP download
        if art_id:
            zd = get_zip(art_id)
            if zd:
                st.success("✅ Project ready!")
                st.download_button(
                    "⬇️ Download Complete Project ZIP",
                    data=zd,
                    file_name="project.zip",
                    mime="application/zip",
                    key=f"z_{art_id}_{idx}",
                    use_container_width=True,
                )
    elif content:
        st.markdown(content)

    if art_id and not gen_files:
        zd = get_zip(art_id)
        if zd:
            st.download_button(
                "⬇️ Download ZIP",
                data=zd,
                file_name="project.zip",
                mime="application/zip",
                key=f"z2_{art_id}_{idx}",
            )


# ════════════════════════════════════════════════
# TAB 1 — Build & Chat
# ════════════════════════════════════════════════
with tab1:
    # Show history
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg.get("content", ""))
            else:
                render_assistant(msg, i)

    # Input
    user_input = st.chat_input(
        "🛠 Describe what you want to build, or ask anything...",
        key="ci",
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        print(f"\n[STREAMLIT] --- NEW REQUEST ---")
        print(f"[STREAMLIT] Sending request with session_id: {st.session_state.session_id}")

        try:
            r = requests.post(
                f"{API_BASE_URL}/process",
                json={"message": user_input, "session_id": st.session_state.session_id},
                timeout=180,
            )
        except Exception:
            st.error("❌ Cannot reach backend!")
            st.stop()

        if r.status_code != 200:
            try:
                err_detail = r.json().get("detail", r.text)
            except Exception:
                err_detail = r.text
            
            if r.status_code in (502, 503):
                st.error(f"⚠️ AI service is temporarily unavailable: {err_detail}")
            else:
                st.error(f"Error {r.status_code}: {err_detail}")
            st.stop()

        resp = r.json()
        job_id = resp.get("job_id")
        wid = resp.get("workflow_id")

        with st.chat_message("assistant"):

            # Direct (chat/update/rewrite)
            if resp.get("status") == "completed":
                result = resp.get("result", {})
                direct = result.get("direct_response", "")
                st.markdown(direct)
                st.session_state.messages.append({
                    "role": "assistant", "content": direct
                })
                st.rerun()

            else:
                # Full pipeline polling
                pb = st.progress(0)
                st_text = st.empty()
                live_box = st.empty()
                events = []
                final = None
                
                stale_count = 0
                last_p = -1
                last_node = ""

                for _ in range(2000):
                    try:
                        url = f"{API_BASE_URL}/status/{job_id}"
                        if stale_count > 30:
                            # Cache-busting parameter for stale requests
                            url += f"?t={time.time()}"
                            
                        pr = requests.get(url, timeout=30).json()
                    except Exception:
                        time.sleep(1)
                        continue

                    p = min(pr.get("progress", 0), 100)
                    node = pr.get("current_node") or "Starting..."
                    pb.progress(p)
                    
                    if p == last_p and node == last_node:
                        stale_count += 1
                        if stale_count > 90:
                            st_text.warning(f"⏳ Still working on **{node}**... (This step is taking longer than usual)")
                        else:
                            st_text.markdown(f"🔄 **{node}** `{p}%`")
                    else:
                        stale_count = 0
                        last_p = p
                        last_node = node
                        st_text.markdown(f"🔄 **{node}** `{p}%`")

                    if wid:
                        evs = fetch_events(wid)
                        if evs and len(evs) > len(events):
                            events = evs
                            with live_box.container():
                                for ev in evs[-3:]:
                                    st.caption(
                                        f"✅ {ev.get('agent','').upper()}"
                                    )

                    if pr["status"] == "completed":
                        final = pr.get("result", {})
                        break
                    elif pr["status"] == "failed":
                        final = pr.get("result", {})
                        err = pr.get("error", "Unknown error")
                        if final and final.get("project_files"):
                            final["_soft_failure_error"] = err
                            break
                        else:
                            st_text.error(f"❌ {err}")
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"❌ Failed: {err}",
                                "agent_events": events,
                            })
                            st.rerun()
                            break

                    time.sleep(2)
                else:
                    st_text.error("❌ Timeout waiting for backend response. The job may still be running in the background.")
                    st.stop()

                if final:
                    pb.progress(100)
                    if final.get("_soft_failure_error"):
                        st_text.warning(f"⚠️ {final['_soft_failure_error']}\n\nThis project did not pass all quality checks after 3 attempts.")
                    else:
                        st_text.markdown("✅ **Done!**")
                    live_box.empty()

                    direct = final.get("direct_response")
                    if direct:
                        st.markdown(direct)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": direct,
                            "agent_events": events,
                        })
                    else:
                        gen_code = final.get("generated_code", "")
                        plan = final.get("plan", "")
                        review = final.get("review_feedback", "")
                        review_ok = final.get("review_passed", False)
                        pytest_out = final.get("pytest_output", "")
                        pytest_ok = final.get("pytest_passed", False)
                        qa = final.get("qa_feedback", "")
                        art_id = final.get("artifact_id")

                        # Parse files
                        gen_files = {}
                        if final.get("project_files"):
                            gen_files = final["project_files"]
                        elif gen_code:
                            gen_files = parse_files_from_code(gen_code)

                        # Agent dropdown
                        if events:
                            with st.expander(
                                f"🤖 Agent conversation ({len(events)} steps)",
                                expanded=False,
                            ):
                                for ev in events:
                                    name = ev.get("agent", "AGENT").upper()
                                    txt = ev.get("content", "")
                                    icon = "✅" if "PASS" in txt.upper() else "🔄"
                                    st.markdown(
                                        f'<div class="agent-card">'
                                        f'<div class="agent-name">{icon} {name}</div>'
                                        f'{txt[:500]}</div>',
                                        unsafe_allow_html=True,
                                    )

                        # File tree
                        if gen_files:
                            tree = render_file_tree(gen_files)
                            st.markdown("**📁 Project Structure:**")
                            st.markdown(
                                f'<div class="file-tree-box">{tree}</div>',
                                unsafe_allow_html=True,
                            )
                            st.markdown("**📄 Files** *(click to view)*:")
                            for fp, code in gen_files.items():
                                ext = fp.rsplit(".", 1)[-1] if "." in fp else "text"
                                with st.expander(f"📄 `{fp}`", expanded=False):
                                    st.code(code, language=lang_from_ext(ext))
                        elif gen_code:
                            st.markdown("**💻 Generated Code:**")
                            st.code(gen_code, language="python")

                        # Collapsibles
                        if plan:
                            with st.expander("📋 Plan", expanded=False):
                                st.markdown(plan)
                        if review:
                            with st.expander(
                                f"{'✅' if review_ok else '❌'} Review",
                                expanded=False,
                            ):
                                st.markdown(review)
                        if pytest_out:
                            with st.expander(
                                f"{'✅' if pytest_ok else '⚠️'} Tests",
                                expanded=False,
                            ):
                                st.code(pytest_out)
                        if qa:
                            with st.expander("✅ QA", expanded=False):
                                st.markdown(qa)
                                
                        if "execution_report.md" in gen_files:
                            with st.expander("📋 View Execution Report", expanded=False):
                                st.markdown(gen_files["execution_report.md"])

                        # ZIP
                        if art_id:
                            zd = get_zip(art_id)
                            if zd:
                                st.success("✅ Project complete!")
                                st.download_button(
                                    "⬇️ Download Complete Project ZIP",
                                    data=zd,
                                    file_name="project.zip",
                                    mime="application/zip",
                                    key=f"znew_{art_id}",
                                    use_container_width=True,
                                )
                                st.session_state.downloads[st.session_state.session_id] = {
                                    "artifact_id": art_id,
                                    "title": user_input[:25],
                                }

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"⚠️ Generated {len(gen_files)} files (with issues)." if final.get("_soft_failure_error") else (f"Generated {len(gen_files)} files." if gen_files else (plan[:200] if plan else "Done.")),
                            "agent_events": events,
                            "workflow_id": wid,
                            "artifact_id": art_id,
                            "generated_files": gen_files,
                            "_soft_failure_error": final.get("_soft_failure_error"),
                        })

                    st.rerun()


# ════════════════════════════════════════════════
# TAB 2 — Debug
# ════════════════════════════════════════════════
with tab2:
    st.subheader("🐞 Debug Your Code")
    st.caption("Upload buggy code → AI finds issues, fixes them, explains changes")

    dbf = st.file_uploader(
        "Choose a code file",
        type=["py", "js", "ts", "java", "c", "cpp", "h", "jsx", "tsx"],
        key="dbf",
    )

    if dbf:
        st.info(f"📄 **{dbf.name}** ({len(dbf.getvalue()):,} bytes)")
        if st.button("🔍 Analyze & Fix", use_container_width=True):
            with st.spinner("Analyzing..."):
                try:
                    dr = requests.post(
                        f"{API_BASE_URL}/debug",
                        files={"file": (dbf.name, dbf.getvalue())},
                        timeout=180,
                    )
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.stop()

            if dr.status_code == 200:
                res = dr.json()
                lang = res.get("language", "Unknown")
                st.success(f"Language: **{lang}**")

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 🔎 Issues Found")
                    st.markdown(res.get("issues_found", "None"))
                with c2:
                    st.markdown("### 📝 Explanation")
                    st.markdown(res.get("explanation", ""))

                st.markdown("### ✅ Fixed Code")
                fixed = res.get("corrected_code", "")
                st.code(fixed, language=lang.lower())

                if fixed:
                    st.download_button(
                        f"⬇️ Download fixed_{dbf.name}",
                        data=fixed,
                        file_name=f"fixed_{dbf.name}",
                        mime="text/plain",
                        use_container_width=True,
                    )
            else:
                st.error(f"Failed: {dr.text}")