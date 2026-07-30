"""
Conversation Agent: Acts as the front-door of the system.
Decides whether the user wants:
  - General conversation (greet, explain, discuss)
  - Code generation (build something new)
  - Code update/fix (modify previously generated code)
  - Language change (rewrite in another language)
"""

from backend.services.agent_logger import agent_log
from backend.services.artifacts import parse_project_files
from backend.services.model_router import get_model, LLMProviderError


ROUTER_PROMPT = """You are a smart AI assistant that is ALSO an expert software engineer.

Conversation history so far:
{history}

User's latest message:
{message}

Previously generated code (if any):
{previous_code}

Your job:

Classify the user's latest message into EXACTLY ONE of the following intents.

1. NEW_PROJECT: The user wants to build an entirely new project from scratch (e.g., "Build Flipkart clone", "Create Tic Tac Toe"). ONLY use this if no project exists, or if they explicitly ask to abandon the existing project.
2. UPDATE_PROJECT: The user wants to modify, extend, or fix the existing project (e.g., "Add dark mode", "Add login page", "Make navbar responsive", "Make login functional", "Wire up the UI", "Hide chatbot until login"). If `previous_code` is present, default to this for ANY request that implies changing how the app works or looks.
3. DEBUG_PROJECT: The user is reporting an error, bug, or issue with the existing code that needs fixing (e.g., "Fix CSS", "It's throwing an error on line 5").
4. REFACTOR: The user wants to improve, optimize, or clean up the existing code without adding new features (e.g., "Optimize performance", "Use Tailwind").
5. TRANSLATE: The user wants to rewrite the existing code in another programming language (e.g., "Convert this to React", "Rewrite in Rust").
6. TESTING: The user explicitly wants test cases generated for the code.
7. DOCUMENTATION: The user explicitly wants documentation (README, comments) written for the code.
8. EXPLAIN_CODE: The user is asking how the code works or asking for a code walkthrough.
9. GENERAL_CHAT: Greetings, general conversation, or any non-coding request.

Reply using ONLY one of the following exact strings:
ROUTE:NEW_PROJECT
ROUTE:UPDATE_PROJECT
ROUTE:DEBUG_PROJECT
ROUTE:REFACTOR
ROUTE:TRANSLATE:<language>
ROUTE:TESTING
ROUTE:DOCUMENTATION
ROUTE:EXPLAIN_CODE
ROUTE:GENERAL_CHAT

Respond now:
"""


UPDATE_PROMPT = """You are an expert software developer.

The user previously had this code generated:

{previous_code}

Conversation history:

{history}

The user now wants this change/fix:

{message}

Please provide the updated COMPLETE code.

Do not remove existing functionality unless requested.

Return ONLY the updated code.

CRITICAL FORMAT REQUIREMENT:
You MUST return each file using this EXACT format, one per file, with no exceptions:

```<language> path=<filename>
<complete file content>
```

Do NOT use markdown headers like **filename** or any other format. Do NOT add explanations outside code blocks. Return ALL files in the project (even unchanged ones) in this format, not just the changed file, so the full project can be rebuilt.

Target language:
{language}
"""


REWRITE_PROMPT = """You are an expert software developer.

Rewrite the following code in {target_language}:

{previous_code}

Keep exactly the same functionality.

Return ONLY the rewritten code.

CRITICAL FORMAT REQUIREMENT:
You MUST return each file using this EXACT format, one per file, with no exceptions:

```<language> path=<filename>
<complete file content>
```

Do NOT use markdown headers like **filename** or any other format. Do NOT add explanations outside code blocks. Return ALL files in the project.
"""


def route_message(
    message: str,
    history: list,
    previous_code: str = None,
    previous_language: str = "Python",
    language_preference: str | None = None,
) -> dict:
    """
    Routes the user message to the appropriate handler.

    Returns:
        dict(route, response, updated_code)
    """

    if language_preference:
        previous_language = language_preference

    llm = get_model("conversation")

    history_text = (
        "\n".join(
            [f"{m['role'].upper()}: {m['content']}" for m in history]
        )
        if history
        else "No previous conversation."
    )
    
    previous_code_summary = (
        "YES (An active project with generated files exists in this session)."
        if previous_code
        else "No code generated yet."
    )

    prompt = ROUTER_PROMPT.format(
        history=history_text,
        message=message,
        previous_code=previous_code_summary,
    )

    try:
        with agent_log(
            agent_name="Conversation Router",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent="LangGraph Workflow or Direct Response",
        ) as log:
            raw_decision = llm.invoke(prompt)
            log["response"] = raw_decision
    
            decision = raw_decision.content.strip()
    
            log["output"] = decision
    except LLMProviderError as e:
        return {
            "success": False,
            "error_type": "llm_provider_error",
            "message": str(e),
        }

    if not decision.startswith("ROUTE:"):
        decision = "ROUTE:GENERAL_CHAT"
        
    route = decision.replace("ROUTE:", "").strip()

    has_existing_project = bool(previous_code)
    
    if route == "NEW_PROJECT" and has_existing_project:
        explicit_new = any(word in message.lower() for word in ["new project", "start over", "scratch", "delete everything"])
        if not explicit_new:
            print(f"[ROUTER] Overriding LLM route NEW_PROJECT -> UPDATE_PROJECT because has_existing_project=True")
            route = "UPDATE_PROJECT"
            
    print(f"[ROUTER] has_existing_project: {has_existing_project} | Final intent: {route}")

    if route == "NEW_PROJECT":
        return {
            "route": "code",
            "response": None,
            "updated_code": None,
        }

    if route in ("UPDATE_PROJECT", "DEBUG_PROJECT", "REFACTOR", "TESTING", "DOCUMENTATION"):
        if not previous_code:
            return {
                "route": "update",
                "response": "I don't see an active project in this session to update — would you like me to start a new one, or can you re-share what you'd like me to work on?",
                "project_files": None,
            }
        # The background worker (job_runner) will intercept this and queue the full LangGraph pipeline
        return {
            "route": "update",
            "response": "Applying your requested update to the project. Please wait...",
            "project_files": None,
        }

    if route.startswith("TRANSLATE:"):
        target_lang = route.replace("TRANSLATE:", "").strip()

        rewrite_prompt = REWRITE_PROMPT.format(
            target_language=target_lang,
            previous_code=previous_code or "",
        )

        try:
            with agent_log(
                agent_name="Conversation Rewrite Agent",
                model_name=llm.model_name,
                input_text=rewrite_prompt,
                next_agent="Completed",
            ) as log:
                raw_rewritten = llm.invoke(rewrite_prompt)
                log["response"] = raw_rewritten
                rewritten = raw_rewritten.content
                log["output"] = rewritten
        except LLMProviderError as e:
            return {
                "success": False,
                "error_type": "llm_provider_error",
                "message": str(e),
            }

        project_files = parse_project_files(rewritten)

        # Validation & Retry
        if not project_files:
            retry_prompt = rewrite_prompt + "\n\nYour last response was not in the correct format. You MUST use ```language path=filename code fences."
            try:
                with agent_log(
                    agent_name="Conversation Rewrite Agent (Retry)",
                    model_name=llm.model_name,
                    input_text=retry_prompt,
                    next_agent="Completed",
                ) as retry_log:
                    raw_rewritten = llm.invoke(retry_prompt)
                    retry_log["response"] = raw_rewritten
                    rewritten = raw_rewritten.content
                    retry_log["output"] = rewritten
                project_files = parse_project_files(rewritten)
            except LLMProviderError as e:
                return {
                    "success": False,
                    "error_type": "llm_provider_error",
                    "message": str(e),
                }

        return {
            "route": "rewrite",
            "response": f"Here's your code rewritten in {target_lang}.",
            "project_files": project_files,
        }

    # Fallback for EXPLAIN_CODE and GENERAL_CHAT
    return {
        "route": "chat",
        "response": decision,
        "updated_code": None,
    }