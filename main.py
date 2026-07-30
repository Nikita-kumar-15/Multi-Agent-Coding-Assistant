# main.py
"""
Quick test runner for Phase 1.
Run: python main.py
"""

from backend.graph.workflow import build_workflow

def run():
    app = build_workflow()

    initial_state = {
        "user_request": "Write a Python function that checks if a number is prime.",
        "plan": None,
        "generated_code": None,
        "code_explanation": None,
        "review_feedback": None,
        "review_passed": None,
        "revision_count": 0,
        "max_revisions": 3,
        "current_node": None,
        "history": [],
    }

    final_state = app.invoke(initial_state)

    print("\n--- PLAN ---")
    print(final_state["plan"])
    print("\n--- FINAL CODE ---")
    print(final_state["generated_code"])
    print("\n--- REVIEW FEEDBACK ---")
    print(final_state["review_feedback"])
    print("\n--- HISTORY ---")
    for h in final_state["history"]:
        print("-", h)

if __name__ == "__main__":
    run()