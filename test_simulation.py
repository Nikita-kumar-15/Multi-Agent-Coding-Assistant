import uuid
import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath("."))

from backend.services.session_store import create_session, get_active_project_state
from backend.agents.conversation_agent import route_message
from backend.services.job_runner import run_job

def run_simulation():
    session_id = str(uuid.uuid4())
    
    print(f"--- SIMULATING TURN 1 ---")
    print(f"\n[STREAMLIT] --- NEW REQUEST ---")
    print(f"[STREAMLIT] Sending request with session_id: {session_id}")
    
    create_session(session_id)
    
    state1 = get_active_project_state(session_id)
    prev_code1 = ""
    if state1 and state1.get("files"):
        prev_code1 = "YES"
    
    route1 = route_message("build a tic-tac-toe game in HTML/JS", [], previous_code=prev_code1)
    
    if route1["route"] == "code":
        run_job("job_1", "build a tic-tac-toe game in HTML/JS", session_id=session_id)
        
    print(f"\n--- SIMULATING TURN 2 ---")
    print(f"\n[STREAMLIT] --- NEW REQUEST ---")
    print(f"[STREAMLIT] Sending request with session_id: {session_id}")
    
    state2 = get_active_project_state(session_id)
    prev_code2 = ""
    if state2 and state2.get("files"):
        prev_code2 = "YES"
        
    route2 = route_message("add dark mode", [{"role": "user", "content": "build a tic-tac-toe game in HTML/JS"}], previous_code=prev_code2)
    
    if route2["route"] == "update":
        run_job("job_2", "add dark mode", session_id=session_id, is_update=True, active_project_state=state2)

if __name__ == "__main__":
    run_simulation()
