# backend/services/report_generator.py
"""
Generates a markdown execution report from the LangGraph execution trace.
"""

def generate_execution_report(state: dict) -> str:
    trace = state.get("execution_trace", [])
    if not trace:
        return "# Project Execution Report\n\nNo execution trace available."

    final_verdict = state.get("orchestrator_verdict", "N/A")
    total_attempts = state.get("revision_count", 0) + 1
    
    workspace_status = "NEEDS_FIXING" if (final_verdict == "FAIL" and total_attempts > state.get("max_revisions", 3)) else "ACTIVE"
    workflow_id = state.get("artifact_id", "Unknown")

    lines = [
        "# Project Execution Report",
        "",
        "## Summary",
        f"- **Final Verdict:** {final_verdict}",
        f"- **Workspace Status:** {workspace_status}",
        f"- **Workflow ID:** `{workflow_id}`",
        f"- **Total Attempts:** {total_attempts}",
        "",
        "## Latest Review Comments",
    ]
    
    if state.get("review_feedback"):
        lines.append(state.get("review_feedback").replace("\n", "\n> "))
    else:
        lines.append("No review comments.")
        
    lines.extend([
        "",
        "## Latest QA Comments",
    ])
    
    if state.get("qa_feedback"):
        lines.append(state.get("qa_feedback").replace("\n", "\n> "))
    else:
        lines.append("No QA comments.")
        
    lines.extend([
        "",
        "## Timeline",
        ""
    ])

    # Group by attempt
    attempts = {}
    for entry in trace:
        attempt = entry.get("attempt", 1)
        if attempt not in attempts:
            attempts[attempt] = []
        attempts[attempt].append(entry)

    for attempt in sorted(attempts.keys()):
        lines.append(f"### Attempt {attempt}")
        for entry in attempts[attempt]:
            agent = entry.get("agent", "Unknown Agent")
            verdict = entry.get("verdict", "")
            details = entry.get("details", "")
            
            # Format the output cleanly
            agent_header = f"**{agent}:**"
            if verdict:
                agent_header += f" [{verdict}]"
                
            if "\n" in details:
                lines.append(f"{agent_header}")
                # Indent multi-line details for better readability
                indented_details = "\n".join([f"  {line}" for line in details.strip().split("\n")])
                lines.append(f"{indented_details}\n")
            else:
                lines.append(f"{agent_header} — {details}\n")

    report_content = "\n".join(lines)
    print(f"[REPORT] Saving report to: execution_report.md, length: {len(report_content)}")
    return report_content
