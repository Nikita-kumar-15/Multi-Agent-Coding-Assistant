# backend/agents/coder_agent.py
"""
Coder Agent: generates complete projects.
Uses simple format to avoid token limits.
Splits large projects into focused files.
"""

from datetime import datetime

from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.artifacts import parse_project_files, parse_deleted_files
import json
from backend.services.model_router import get_model, LLMProviderError
from backend.terminal.logger import tlog

GOLDEN_RULES = """
MANDATORY ENGINEERING STANDARDS — apply to EVERY project, regardless of what is being built:

1. IMAGES & EXTERNAL ASSETS:
   - NEVER use external image URLs (no placeholder.com, picsum.photos, unsplash, external CDNs, random image APIs).
   - For any image/photo/banner/icon, use inline SVG or CSS-styled <div> placeholders with descriptive text/gradient backgrounds. Zero external network image requests allowed — this environment has no internet access during execution testing.

2. MODALS, DIALOGS & OVERLAYS:
   - Must be hidden by default (`hidden` attribute or `display:none`), with visibility toggled ONLY by explicit user click events — never on page load/DOMContentLoaded.
   - No CSS rule may force a modal visible outside of a `.open`/`.active` state class controlled by JS.

3. SECURITY:
   - NEVER use `innerHTML` with any dynamic/variable data. Always use `textContent`, `createElement`, or explicit attribute setting to prevent XSS.
   - Sanitize all user-provided input before rendering or storing it.

4. ACCESSIBILITY (WCAG basics, non-negotiable):
   - All interactive elements (buttons, dropdowns, modals) must be keyboard-navigable (focus, Enter/Space, Escape to close).
   - All icon-only buttons must have `aria-label`.
   - All images must have descriptive `alt` text (or `alt=""` for decorative ones).
   - Modals must use `role="dialog"`, `aria-modal="true"`, and trap focus while open.

5. SCOPE COMPLETENESS:
   - Build EVERY section/feature mentioned in the implementation plan — do not silently drop sections (hero banners, footers, navigation, etc.) for simplicity.
   - If a plan lists 6 required sections, the code must contain all 6, fully functional, in the FIRST attempt.

6. STATE & DATA INTEGRITY:
   - Any filter/category/search logic must only reference data fields that ACTUALLY EXIST in the mock data. Verify field names match between data structure and filter logic before finalizing.

7. GRACEFUL ERROR HANDLING:
   - Any JSON.parse, localStorage read, or async operation must be wrapped in try/catch with sensible fallbacks — never let a parsing error crash the whole app.

8. CODE ORGANIZATION:
   - Split HTML/CSS/JS logically. No single giant file dumping everything unless the project is trivially small.
   - CRITICAL: NEVER use `<script type="module">` or ES module import/export syntax (`import`/`export` statements) for frontend-only HTML/CSS/JS projects. This environment serves files via the `file://` protocol, which blocks ES modules with a CORS error. Always use plain `<script src="script.js"></script>` (no type="module") and organize code using regular function/variable scoping or IIFEs instead of ES modules.
"""

CONDENSED_GOLDEN_RULES = """
MANDATORY ENGINEERING STANDARDS (RETRY REFERENCE):
1. No external image URLs; use inline SVG/CSS placeholders.
2. Modals hidden by default, toggled via JS classes only.
3. Use textContent/createElement, NEVER innerHTML.
4. WCAG basics (aria-label, keyboard focus, alt text).
5. Build EVERY feature/section mentioned in the plan completely.
6. Verify data fields exist before filtering.
7. Wrap JSON.parse/async in try/catch.
8. No <script type="module"> or ES module imports in frontend-only projects.
"""

OUTPUT_FORMAT = """
OUTPUT FORMAT — use EXACTLY this format for EVERY file:

```html path=index.html
code here
```

```css path=styles.css
code here
```

```javascript path=script.js
code here
```

```python path=main.py
code here
```

RULES:
- Use path= in EVERY fence header
- IMPORTANT: If the project has both a frontend and backend, organize files into folders (e.g., path=frontend/src/App.jsx or path=backend/main.py)
- Write COMPLETE code — no placeholders
- For HTML/CSS/JS: all 3 files required
- For React: package.json + src/App.jsx + src/main.jsx + index.html
- For Python backend: main.py + requirements.txt
- Write ALL game logic, ALL styles, ALL functionality
- NO descriptions outside code blocks

CRITICAL WIRING INSTRUCTION:
After defining all render/handler functions, you MUST include an initialization block (e.g. wrapped in DOMContentLoaded or called directly at the bottom of the script) that:
(a) Calls every render function so content appears on page load.
(b) Attaches ALL event listeners (e.g. modals, buttons, forms).
A project with functions defined but never invoked is a FAILED submission — always finish with the wiring step!

WRITE CODE NOW:
"""

UPDATE_PROMPT = """You are an expert software developer.

The user is continuing development on an EXISTING project.

ABSOLUTE DEFAULT RULE — NO NEW FILES UNLESS EXPLICITLY REQUESTED:
For ANY update or feature request, you MUST add the new functionality into the EXISTING project files (the same index.html, styles.css, script.js — or whatever the current file set is) that already exist in the Current Project State shown above.

You are FORBIDDEN from creating new HTML, CSS, or JS files UNLESS the user's message explicitly and unambiguously requests a separate page/file — using words like 'separate page', 'new page', 'different file', 'own URL', 'standalone', or similar explicit language. A request like 'add login', 'add a login page', 'add login feature', 'add authentication' — WITHOUT explicit separate-file language — means: add this functionality directly into the CURRENT existing index.html (as a new section/form/modal), add its styles into the CURRENT existing styles.css, and add its logic into the CURRENT existing script.js.

Before creating any new file, you must ask yourself: 'Did the user explicitly say they want a separate file/page?' If the answer is no, do NOT create a new file — integrate everything into the existing ones, no matter how large the feature is.

EXAMPLE: User says 'add login page' → WRONG: create login.html, login.css, login.js. CORRECT: add a <section id='login-section'> or a login modal directly inside the existing index.html body, add .login-section/.login-modal styles to the existing styles.css, and add the login form handling logic to the existing script.js.

- IMPORTANT CROSS-FILE WIRING: If your change legitimately requires a new file (e.g., a completely new login page, a new CSS file, or a new independent script module), you MUST also update any EXISTING file that needs to reference, link to, or trigger this new file (e.g., updating `index.html`'s navigation links or buttons to point to the new page, adding `<link>` or `<script>` tags). A new file created without being wired into the existing project structure is an incomplete update.

EXISTING PROJECT FILES (you MUST reuse these EXACT paths when modifying them):
{existing_files_list}

RULES:
- If you are modifying an existing file, use its EXACT path exactly as listed above.

Current Project State (Files):
{previous_code}

Original Plan & Acceptance Criteria:
{plan}

Established Conventions:
{conventions}

Change History (Recent actions):
{change_history}

Conversation history:
{history}

The user now wants this change/fix/enhancement:
{message}

INSTRUCTIONS for UPDATE:
1. Modify ONLY the files that need to change to fulfill this request.
2. Preserve EVERY existing feature, file, and piece of functionality that isn't directly related to this request.
3. Do NOT recreate the whole project from scratch.
4. Do NOT rename existing files unless explicitly asked.
5. Do NOT create new files unless the requested feature genuinely requires a new file (e.g., a new page/component).
6. Return ONLY the files that you have changed or newly created. The backend will automatically merge these back into the project state.
7. WARNING: Do NOT use placeholders like "// existing code here". You must output the ENTIRE file from top to bottom, including ALL unchanged lines. Our system replaces the old file entirely with what you output here. If you use placeholders, you will corrupt the file and delete the existing code!
8. DELETING ORPHANED FILES: If you have restructured code and an old file is no longer needed (e.g., you consolidated separate files into a single file), you MUST explicitly delete the old, unused files. To delete a file, write:
DELETE: path/to/filename
on a new line anywhere outside of a code block.

CRITICAL WIRING INSTRUCTION:
After adding or modifying any render/handler functions, you MUST ensure they are properly invoked — either by calling them directly, or by confirming they remain correctly wired inside the existing DOMContentLoaded/init block. If you modify or add to the initialization logic, the final code must still call ALL functions (both previously existing and newly added) that need to run on page load or in response to events. Never leave a function defined without it being called somewhere in the execution flow.

CRITICAL FORMAT REQUIREMENT:
You MUST return each changed/new file using this EXACT format, one per file, with no exceptions:

```<language> path=<filename>
<complete file content>
```

Do NOT use markdown headers like **filename** or any other format. Do NOT add explanations outside code blocks.

Target language:
{language}
"""

def estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        return len(text) // 4


def build_coder_prompt(task, stack, search_context="", previous_code="", issues="", original_plan="", is_retry=False):
    rules = CONDENSED_GOLDEN_RULES
    
    plan_to_use = original_plan
    if is_retry and "Acceptance Criteria" in original_plan:
        parts = original_plan.split("Acceptance Criteria", 1)
        if len(parts) > 1:
            plan_to_use = "Acceptance Criteria" + parts[1].split("##", 1)[0]
            
    prompt = f"You are a senior developer. Write COMPLETE working code.\n\n{rules}\n\n"
    prompt += f"TASK: {task}\nSTACK: {stack}\n"
    
    if search_context and not is_retry:
        prompt += f"\n--- CURRENT BEST PRACTICES ---\n{search_context}\n"
        
    if previous_code and issues:
        prompt += f"\nORIGINAL PLAN (must remain fully satisfied):\n{plan_to_use}\n"
        prompt += f"\nPREVIOUS CODE:\n{previous_code}\n\nISSUES TO FIX:\n{issues}\n"
        
    prompt += OUTPUT_FORMAT
    return prompt


def classify_change_type(user_request: str) -> str:
    prompt = f"""
Classify this follow-up request into EXACTLY ONE type:

Request: "{user_request}"

- STYLE_ONLY: Changes only visual appearance (theme, colors, fonts, spacing, animations, 
  "pixelated"/"dark mode"/"minimalist" aesthetics) without changing content, structure, or 
  functionality.
- CONTENT_CHANGE: Changes text/content/data shown on the page without changing layout structure 
  or functionality.
- FUNCTIONAL_CHANGE: Adds/modifies/removes a feature, behavior, or interactive element.
- STRUCTURAL_CHANGE: Adds/removes major sections or reorganizes the page layout.

Respond with ONLY one of: STYLE_ONLY, CONTENT_CHANGE, FUNCTIONAL_CHANGE, STRUCTURAL_CHANGE
"""
    try:
        from backend.services.model_router import get_model
        llm = get_model("coder")
        resp = llm.invoke(prompt)
        content = resp.content.strip().upper()
        for t in ["STYLE_ONLY", "CONTENT_CHANGE", "FUNCTIONAL_CHANGE", "STRUCTURAL_CHANGE"]:
            if t in content:
                return t
        return "FUNCTIONAL_CHANGE"
    except Exception as e:
        print(f"[CODER] Classification failed: {e}")
        return "FUNCTIONAL_CHANGE"


def coder_agent(state: AgentState) -> AgentState:
    import time
    from datetime import datetime
    print(f"[{datetime.utcnow().isoformat()}] START: Coder Agent")
    overall_start = time.time()
    
    is_revision = bool(state.get("review_feedback") or state.get("qa_feedback"))
    is_update = bool(state.get("is_update"))
    
    lang_pref = state.get("language_preference", "Use best stack for the task")
    
    # Extract behaviors if it's an update (Fix D)
    task = state.get("user_request") or state.get("plan") or ""
    if len(task) > 500: task = task[:500]
    
    extracted_behaviors = ""
    change_type = "FUNCTIONAL_CHANGE"
    
    if is_update and not is_revision:
        change_type = classify_change_type(task)
        tlog.info("Coder", f"Classified update request as: {change_type}")
        
        user_history_list = state.get("user_history", [])
        history_text_for_behavior = "\n".join([f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in user_history_list[-5:]]) if user_history_list else "No history."
        
        behavior_prompt = f"""Conversation history:
{history_text_for_behavior}

Current request: "{task}"

Extract the SPECIFIC functional behavior(s) the user expects as a result of this request. 
Be concrete about trigger -> effect relationships (e.g. "on X action, Y should happen").

Respond in JSON ONLY:
{{
  "behaviors": ["on successful login, hide the login form and show the chatbot interface"]
}}
"""
        fast_llm = get_model("coder")
        try:
            beh_resp = fast_llm.invoke(behavior_prompt)
            content_json = beh_resp.content
            if "```json" in content_json:
                content_json = content_json.split("```json")[1].split("```")[0]
            beh_data = json.loads(content_json)
            behaviors = beh_data.get("behaviors", [])
            if behaviors:
                extracted_behaviors = "\n".join([f"- {b}" for b in behaviors])
                tlog.info("Coder", f"Extracted {len(behaviors)} behaviors")
        except Exception as e:
            print(f"[CODER] Behavior extraction failed: {e}")

    # Determine base variables
    issues = ""
    original_plan = ""
    search_context = ""
    base_code = ""

    is_minor_fix = False
    if is_revision:
        tlog.info("Coder", "Revising code...")
        
        review_feedback = state.get('review_feedback', '')
        qa_feedback = state.get('qa_feedback', '')
        
        import re
        critical_count = 0
        major_count = 0
        if m := re.search(r"CRITICAL:\s*(\d+)", review_feedback, re.IGNORECASE):
            critical_count = int(m.group(1))
        if m := re.search(r"MAJOR:\s*(\d+)", review_feedback, re.IGNORECASE):
            major_count = int(m.group(1))
            
        if critical_count == 0 and major_count <= 1 and "QA_VERDICT: REJECT" in qa_feedback:
            is_minor_fix = True

        issues = (
            f"Reviewer: {review_feedback}\n"
            f"QA: {qa_feedback}\n"
            f"Orchestrator: {state.get('orchestrator_feedback', '')}"
        )
        base_code = state.get("generated_code", "")
        original_plan = state.get("plan") or ""
    elif is_update:
        tlog.info("Coder", "Applying requested update to existing code...")
        base_code = state.get("previous_code", "")
        search_context = state.get("initial_search_context", "")
    else:
        tlog.info("Coder", "Generating code...")
        search_context = state.get("initial_search_context", "")

    # Dynamic model selection
    num_files = len(state.get("active_project_state", {}).get("files", {})) if is_update else 0
    llm = get_model("coder")

    max_coder_retries = 1
    coder_retry_count = 0
    
    while coder_retry_count <= max_coder_retries:
        # Token Truncation Loop
        max_tokens = 7000
        truncate_lengths = [None, 3000, 1500, 500]
        prompt = ""
        
        for length in truncate_lengths:
            code_to_use = base_code
            if length is not None and base_code:
                code_to_use = base_code[:length]
                
            if is_minor_fix:
                active_state = state.get("active_project_state") or {}
                if is_update:
                    affected_files = list(active_state.get("files", {}).keys())
                else:
                    affected_files = list(state.get("project_files", {}).keys())
                    
                prompt = f"""Fix ONLY this specific issue in the existing code, do not change anything else:

Issue: {issues}

File(s) to fix: {affected_files}

Current Code:
{code_to_use}

Return the complete corrected file(s) with ONLY the syntax/formatting issue fixed. 
Do not regenerate unrelated code or add new features.
{OUTPUT_FORMAT}
"""
            elif is_update:
                active_state = state.get("active_project_state") or {}
                # Use user_history for conversation history in prompt instead of agent history
                user_hist = state.get("user_history", [])
                history_text = "\n".join([f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in user_hist[-5:]]) if user_hist else ""
                
                existing_files = active_state.get("files", {})
                existing_files_list = "\n".join([f"- {fp}" for fp in existing_files.keys()]) if existing_files else "- (No existing files found)"

                prompt = UPDATE_PROMPT.format(
                    history=history_text,
                    message=task,
                    previous_code=code_to_use,
                    language=state.get("language_preference", "Unknown"),
                    plan=state.get("plan", active_state.get("plan", "")),
                    conventions=active_state.get("conventions", ""),
                    change_history="\n".join(active_state.get("change_history", [])[-5:]),
                    existing_files_list=existing_files_list
                )
                
                if change_type == "STYLE_ONLY":
                    prompt += """
THIS IS A STYLE-ONLY CHANGE. You MUST:
- Keep 100% of the existing HTML structure, elements, IDs, classes, and content EXACTLY as they are (do not remove, rename, or restructure anything).
- Keep 100% of the existing JavaScript logic and functionality unchanged.
- ONLY modify styles.css (and add minimal new CSS classes/variables if needed for the new theme). You may add new CSS custom properties or a new stylesheet import, but the underlying page structure and behavior must remain identical.
- Do NOT regenerate index.html or script.js from scratch. Return them UNCHANGED unless a specific class/attribute must be added to support the new theme (e.g. adding a 'pixelated-theme' class to the body tag), in which case make the MINIMAL edit only.
"""
                
                if extracted_behaviors:
                    prompt += f"\n\nMANDATORY BEHAVIORS TO IMPLEMENT (do not skip any of these):\n{extracted_behaviors}\n\nYou MUST write actual working logic (JS event handlers, conditional rendering/display toggling, etc.) to implement each behavior above. Do not leave any UI element non-functional if a behavior describing its expected function has been specified.\n"
                
                if coder_retry_count > 0:
                    prompt += f"\n\nCRITICAL REVIEW FEEDBACK FROM PREVIOUS ATTEMPT:\n{issues}\nYOU MUST FIX THIS."

            else:
                prompt = build_coder_prompt(
                    task=task,
                    stack=lang_pref,
                    search_context=search_context,
                    previous_code=code_to_use,
                    issues=issues,
                    original_plan=original_plan,
                    is_retry=is_revision
                )
            
            if estimate_tokens(prompt) <= max_tokens:
                break
                
        if estimate_tokens(prompt) > max_tokens and search_context:
            prompt = build_coder_prompt(
                task=task, stack=lang_pref, search_context="", 
                previous_code=base_code[:500] if base_code else "", 
                issues=issues, original_plan=original_plan, is_retry=is_revision
            )

        start_time = time.time()
        try:
            with agent_log(
                agent_name="Coder Agent",
                model_name=llm.model_name,
                input_text=prompt,
                next_agent="Executor Agent",
            ) as log:
                response = llm.invoke(prompt)
                log["response"] = response
                log["output"] = response.content
        except LLMProviderError as e:
            state["success"] = False
            state["error"] = str(e)
            print(f"[{datetime.utcnow().isoformat()}] END: Coder Agent (Error)")
            return state
        elapsed = time.time() - start_time
        tlog.info("Coder", f"LLM generation took {elapsed:.1f} seconds")

        generated = response.content
        
        if not generated or not generated.strip() or "path=" not in generated:
            coder_retry_count += 1
            tlog.warning("Coder", f"CODER FAILED - EMPTY RESPONSE. Retrying ({coder_retry_count}/{max_coder_retries})...")
            if coder_retry_count > max_coder_retries:
                state["success"] = False
                state["error"] = "Code generation failed after multiple attempts (empty or invalid output). Please try again."
                print(f"[{datetime.utcnow().isoformat()}] END: Coder Agent (Error - Empty Response)")
                return state
            continue
        project_files = parse_project_files(generated)
        deleted_files = parse_deleted_files(generated)
        
        # MERGE LOGIC
        if is_update:
            if is_revision and state.get("project_files"):
                existing_files = state["project_files"]
            else:
                active_state = state.get("active_project_state") or {}
                existing_files = active_state.get("files") or {}
            
            # Check for silent failures / unchanged code
            if is_revision and project_files:
                # project_files is just the files that were outputted. If they match the existing files exactly, no changes were made.
                is_unchanged = True
                for fp, content in project_files.items():
                    if fp not in existing_files or existing_files[fp] != content:
                        is_unchanged = False
                        break
                
                if is_unchanged:
                    coder_retry_count += 1
                    tlog.warning("Coder", f"Coder made no changes to the files. Forcing retry ({coder_retry_count}/{max_coder_retries})...")
                    if coder_retry_count > max_coder_retries:
                        state["success"] = False
                        state["error"] = "Coder repeatedly returned unchanged code."
                        return state
                    continue
            
            import os
            normalized_project_files = {}
            for new_fp, new_content in project_files.items():
                matched_fp = new_fp
                for ex_fp in existing_files.keys():
                    if os.path.basename(ex_fp) == os.path.basename(new_fp):
                        matched_fp = ex_fp
                        break
                normalized_project_files[matched_fp] = new_content
                
            merged_files = {**existing_files, **normalized_project_files}
            for df in deleted_files:
                if df in merged_files:
                    del merged_files[df]
            project_files = merged_files
            generated = "\n\n".join([f"```{fp.split('.')[-1]} path={fp}\n{content}\n```" for fp, content in project_files.items()])

        # STYLE_ONLY strict diff check
        if change_type == "STYLE_ONLY" and is_update and coder_retry_count < max_coder_retries:
            import difflib
            large_diff_found = False
            for fp, content in project_files.items():
                if fp.endswith(".html") or fp.endswith(".js"):
                    ex_content = existing_files.get(fp, "")
                    if ex_content:
                        diff = list(difflib.ndiff(ex_content.splitlines(), content.splitlines()))
                        changes = sum(1 for line in diff if line.startswith("+ ") or line.startswith("- "))
                        total = len(ex_content.splitlines())
                        if total > 0 and (changes / total) > 0.2:
                            large_diff_found = True
                            tlog.warning("Coder", f"[WARNING] STYLE_ONLY change resulted in large {fp} diff ({changes}/{total} lines). Forcing retry.")
                            break
            
            if large_diff_found:
                coder_retry_count += 1
                issues = "Your previous response rewrote the HTML/JS structure. This was a STYLE_ONLY request — return the EXACT same HTML/JS as before, only with updated CSS."
                is_revision = True
                base_code = generated
                continue

        # Behavior verification
        if extracted_behaviors and not is_revision and coder_retry_count < max_coder_retries:
            verify_prompt = f"""You are a QA bot.
The user requested these behaviors:
{extracted_behaviors}

Here is the generated code:
{generated}

Verify if the behaviors were actually implemented in code with working logic (not just static UI).
If ALL behaviors are fully implemented, reply with exactly "PASS".
If any behavior is missing or just static UI without logic, reply with "FAIL: <reason>".
"""
            fast_llm = get_model("coder")
            try:
                v_resp = fast_llm.invoke(verify_prompt)
                if "FAIL" in v_resp.content:
                    coder_retry_count += 1
                    tlog.warning("Coder", f"Behavior verification failed. Retrying... Reason: {v_resp.content}")
                    issues = f"CRITICAL: The previous code failed behavior verification. {v_resp.content}"
                    is_revision = True  # We need to pass issues next time
                    base_code = generated
                    continue
            except Exception as e:
                print(f"[CODER] Behavior verification failed to run: {e}")
        
        break # Exit retry loop

    tlog.success("Coder", f"Generated/Merged to {len(project_files)} file(s): {list(project_files.keys())}")

    state["generated_code"] = generated
    state["project_files"] = project_files
    state["current_node"] = "coder_agent"
    state["history"].append(
        f"Coder generated {len(project_files)} files."
    )

    if "execution_trace" not in state:
        state["execution_trace"] = []
    
    details = f"Generated {len(project_files)} files:\n" + "\n".join([f"- {f}" for f in project_files.keys()])
    if is_revision:
        details = f"Revising code based on feedback.\n{details}"

    state["execution_trace"].append({
        "agent": "Coder",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "Completed",
        "details": details
    })

    for fp in sorted(project_files.keys()):
        tlog.file_generated("Coder", fp)

    overall_elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Coder Agent (took {overall_elapsed:.2f}s)")
    return state
