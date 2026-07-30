import time
from datetime import datetime
# backend/agents/orchestrator_pre_search_agent.py
import json
from datetime import datetime
from backend.graph.state import AgentState
from backend.services.agent_logger import agent_log
from backend.services.model_router import get_model, LLMProviderError
from backend.terminal.logger import tlog
from backend.services.web_search import web_search, fetch_page_content

PRE_SEARCH_PROMPT = """You are the Lead Technical Researcher.
Based on the following request and architecture plan, extract exactly ONE search query 
to find the most up-to-date best practices, library versions, and documentation for the stack.
If no specific tech stack is mentioned, return an empty string.
Prioritize official docs (e.g. developer.mozilla.org, react.dev) over community sites in the search query keywords.

User Request:
{request}

Architecture Plan:
{architecture}

Respond ONLY with the search query text, or "NONE" if not applicable.
"""

def orchestrator_pre_search_agent(state: AgentState) -> AgentState:
    overall_start = time.time()
    print(f"[{datetime.utcnow().isoformat()}] START: Pre-Search Agent")
    tlog.info("PreSearch", f"Running pre-generation search for stack: {state.get('language_preference', 'Unknown')}")
    llm = get_model("orchestrator")
    
    prompt = PRE_SEARCH_PROMPT.format(
        request=state.get("user_request", ""),
        architecture=state.get("architecture_plan", "")
    )
    
    try:
        with agent_log(
            agent_name="PreSearch Agent",
            model_name=llm.model_name,
            input_text=prompt,
            next_agent="Coder Agent",
        ) as log:
            response = llm.invoke(prompt)
            log["response"] = response
            query = response.content.strip().strip('"').strip("'")
            log["output"] = query
    except LLMProviderError as e:
        state["success"] = False
        state["error"] = str(e)
        elapsed = time.time() - overall_start
        print(f"[{datetime.utcnow().isoformat()}] END: Pre-Search Agent (took {elapsed:.2f}s)")
        return state

    search_context = ""
    results = []
    if query and query.upper() != "NONE":
        tlog.info("PreSearch", f"Executing search query: {query}")
        results = web_search(query, max_results=3)
        if results:
            search_context = "--- INITIAL SEARCH CONTEXT (CURRENT BEST PRACTICES) ---\n"
            for res in results:
                search_context += f"Title: {res.get('title')}\nURL: {res.get('href')}\nSnippet: {res.get('body')}\n\n"
            
            # Fetch content of the first result for deeper context
            for res in results:
                first_url = res.get('href')
                if first_url:
                    content = fetch_page_content(first_url)
                    if content:
                        search_context += f"\n--- DEEP CONTEXT FROM {first_url} ---\n{content[:3000]}\n"
                        break
                    
            tlog.success("PreSearch", "Web search completed successfully.")
        else:
            tlog.warning("PreSearch", "Web search returned no results.")
    else:
        tlog.info("PreSearch", "No search query generated. Skipping.")

    state["initial_search_context"] = search_context
    state["current_node"] = "orchestrator_pre_search_agent"
    
    if "execution_trace" not in state:
        state["execution_trace"] = []
    state["execution_trace"].append({
        "agent": "OrchestratorPreSearch",
        "attempt": state.get("revision_count", 0) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "Completed",
        "details": f"Query: {query}\nFound {len(results)} results."
    })
    
    elapsed = time.time() - overall_start
    print(f"[{datetime.utcnow().isoformat()}] END: Pre-Search Agent (took {elapsed:.2f}s)")
    return state
